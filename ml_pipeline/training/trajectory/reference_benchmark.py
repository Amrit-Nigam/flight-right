"""Non-neural reference implementation of the residual-prediction fix.

This exists to prove the data pipeline and the framing module are correct before any
neural model is trained, and to set the bar that model has to clear. A gradient
boosted tree on the same features and the same residual targets is a fair, cheap
reference: if it beats constant velocity and the LSTM does not, the problem is the
LSTM, not the framing.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

import framing


MAX_ITERATIONS = 400
LEARNING_RATE = 0.06
MAX_LEAF_NODES = 63
MIN_SAMPLES_LEAF = 40
L2_REGULARIZATION = 1.0
RANDOM_SEED = 0

AXIS_NAMES = ["along", "cross", "altitude"]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# FLIGHT_RIGHT_DATA_ROOT relocates data and saved models (used by the smoke test so
# it can never touch real data). Unset, everything lives under the project root.
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
DATA_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "processed"


def load_split(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = DATA_DIRECTORY / f"trajectory_{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run preprocess_sequences.py first.")
    with np.load(path) as data:
        if "mask" not in data:
            raise KeyError(f"{path} predates per-horizon masking. Re-run preprocess_sequences.py.")
        return data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)


def build_feature_matrix(X: np.ndarray) -> np.ndarray:
    """Flatten the local-frame sequence and append the window-level scalars."""
    sequence, scalars = framing.to_local_features(X)
    return np.concatenate([sequence.reshape(len(X), -1), scalars], axis=1)


def check_round_trip(X: np.ndarray, y: np.ndarray, cv: np.ndarray) -> None:
    """apply_residual must exactly undo residual_targets, or every metric below is fiction."""
    residual = framing.residual_targets(X, y, cv)
    rebuilt = framing.apply_residual(X, cv, residual)
    worst = np.abs(rebuilt - y.astype(np.float64)).max(axis=(0, 1))
    print(f"Round-trip max error: lat {worst[0]:.3e} deg, lon {worst[1]:.3e} deg, alt {worst[2]:.3e} m")
    assert worst[0] < 1e-6 and worst[1] < 1e-6, "apply_residual does not invert residual_targets"
    print("Round-trip assertion passed (< 1e-6 degrees).")


def summarise(predicted: np.ndarray, actual: np.ndarray, mask: np.ndarray) -> list[dict[str, float]]:
    """Per-horizon mean error and threshold hit rates, over mask-valid rows only."""
    errors = framing.error_nm(predicted, actual)
    rows = []
    for horizon_index in range(len(framing.HORIZONS_SECONDS)):
        valid = errors[mask[:, horizon_index], horizon_index]
        rows.append({
            "n": len(valid),
            "mean_nm": float(valid.mean()),
            "within_1": float((valid < 1.0).mean() * 100),
            "within_2_5": float((valid < 2.5).mean() * 100),
            "within_5": float((valid < 5.0).mean() * 100),
        })
    return rows


def print_comparison(baseline_rows, model_rows) -> None:
    print("")
    print(f"{'horizon':<9}{'n':>8}{'CV mean':>10}{'ref mean':>10}{'CV <1NM':>10}{'ref <1NM':>10}"
          f"{'CV <2.5':>10}{'ref <2.5':>10}{'CV <5NM':>10}{'ref <5NM':>10}")
    print("-" * 97)
    for index, horizon in enumerate(framing.HORIZONS_SECONDS):
        baseline, model = baseline_rows[index], model_rows[index]
        print(f"{int(horizon) // 60:>3} min  {baseline['n']:>8}"
              f"{baseline['mean_nm']:>9.2f}N{model['mean_nm']:>9.2f}N"
              f"{baseline['within_1']:>9.1f}%{model['within_1']:>9.1f}%"
              f"{baseline['within_2_5']:>9.1f}%{model['within_2_5']:>9.1f}%"
              f"{baseline['within_5']:>9.1f}%{model['within_5']:>9.1f}%")


def print_residual_spread(residual: np.ndarray, mask: np.ndarray) -> None:
    """Per-horizon residual standard deviations; these set the per-horizon normalisation."""
    print("")
    print("Training residual standard deviation (metres), mask-valid rows only:")
    print(f"{'horizon':<9}{'along':>12}{'cross':>12}{'altitude':>12}")
    for horizon_index, horizon in enumerate(framing.HORIZONS_SECONDS):
        valid = residual[mask[:, horizon_index], horizon_index, :]
        print(f"{int(horizon) // 60:>3} min  " + "".join(f"{valid[:, axis].std():>12.1f}" for axis in range(3)))


def main() -> None:
    train_x, train_y, train_mask = load_split("train")
    test_x, test_y, test_mask = load_split("test")
    print(f"Samples: {len(train_x)} train / {len(test_x)} test")

    train_cv = framing.constant_velocity_predict(train_x)
    test_cv = framing.constant_velocity_predict(test_x)
    check_round_trip(train_x, train_y, train_cv)

    train_residual = framing.residual_targets(train_x, train_y, train_cv)
    print_residual_spread(train_residual, train_mask)

    train_features = build_feature_matrix(train_x)
    test_features = build_feature_matrix(test_x)
    print(f"\nFeature matrix: {train_features.shape[1]} columns "
          f"({train_x.shape[1]} steps x {len(framing.SEQUENCE_FEATURE_NAMES)} sequence features "
          f"+ {len(framing.SCALAR_FEATURE_NAMES)} scalars)")

    predicted_residual = np.zeros_like(test_cv)
    for horizon_index, horizon in enumerate(framing.HORIZONS_SECONDS):
        rows = train_mask[:, horizon_index]
        for axis in range(3):
            # absolute_error, not squared_error. This was measured: MSE improves the
            # mean but collapses the 10-minute within-1-NM rate from 22.4% to 2.5%,
            # because squared loss is dominated by the small manoeuvring tail and will
            # push thousands of already-accurate predictions off target to shrink a
            # few large errors. Absolute error regresses the conditional median
            # residual, which is near zero for most aircraft, so easy cases are left
            # alone. Do not "improve" this to squared_error.
            regressor = HistGradientBoostingRegressor(
                loss="absolute_error",
                max_iter=MAX_ITERATIONS,
                learning_rate=LEARNING_RATE,
                max_leaf_nodes=MAX_LEAF_NODES,
                min_samples_leaf=MIN_SAMPLES_LEAF,
                l2_regularization=L2_REGULARIZATION,
                random_state=RANDOM_SEED,
            )
            regressor.fit(train_features[rows], train_residual[rows, horizon_index, axis])
            predicted_residual[:, horizon_index, axis] = regressor.predict(test_features)
            print(f"  fitted {int(horizon) // 60:>2} min / {AXIS_NAMES[axis]:<8} on {rows.sum()} rows")

    predicted = framing.apply_residual(test_x, test_cv, predicted_residual)
    baseline_rows = summarise(test_cv, test_y, test_mask)
    model_rows = summarise(predicted, test_y, test_mask)
    print_comparison(baseline_rows, model_rows)

    passed = all(model_rows[i]["within_5"] >= baseline_rows[i]["within_5"] for i in range(4))
    print("")
    print(f"GATE (reference beats constant velocity at every horizon on <5 NM): "
          f"{'PASS' if passed else 'FAIL'}")
    print(f"10-minute within-5-NM: {model_rows[3]['within_5']:.1f}% "
          f"(needs to be comfortably above 60%)")


if __name__ == "__main__":
    main()
