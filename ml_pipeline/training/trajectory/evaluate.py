"""Per-horizon, per-regime evaluation of trajectory predictions.

The previous training script printed one MAE pooled across all four horizons. That
single number is how a model that was worse than the constant-velocity baseline at
every horizon went unnoticed: the 1-minute predictions are so easy that they mask a
10-minute failure when the two are averaged together. Nothing here is ever pooled
across horizons, and every metric is reported against the baseline.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import numpy as np

import framing


PROJECT_ROOT = Path(__file__).resolve().parents[3]
# FLIGHT_RIGHT_DATA_ROOT relocates data and saved models (used by the smoke test so
# it can never touch real data). Unset, everything lives under the project root.
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
DATA_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "processed"
METRES_TO_FEET = 3.28084

HORIZON_LABELS = ["1 min", "3 min", "5 min", "10 min"]
# Bucket edges are open-ended at both ends; each entry is (name, lower, upper).
TURN_BUCKETS = [("straight", 0.0, 1.0), ("gentle turn", 1.0, 10.0), ("moderate turn", 10.0, 30.0), ("sharp turn", 30.0, np.inf)]
VERTICAL_BUCKETS = [("level", 0.0, 300.0), ("gentle climb/descent", 300.0, 1500.0), ("fast climb/descent", 1500.0, np.inf)]
DISTANCE_BUCKETS = [("terminal", 0.0, 40.0), ("intermediate", 40.0, 100.0), ("en-route", 100.0, np.inf)]


def load_split(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = DATA_DIRECTORY / f"trajectory_{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run preprocess_sequences.py first.")
    with np.load(path) as data:
        if "mask" not in data:
            raise KeyError(f"{path} predates per-horizon masking. Re-run preprocess_sequences.py.")
        return data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)


def bucket_assignments(X: np.ndarray) -> dict[str, tuple[np.ndarray, list]]:
    """Derive the flight-regime buckets from the input window itself."""
    _, scalars = framing.to_local_features(X)
    turn_degrees = np.abs(np.degrees(scalars[:, framing.SCALAR_FEATURE_NAMES.index("total_turn_rad")]))
    vertical_fpm = np.abs(scalars[:, framing.SCALAR_FEATURE_NAMES.index("last_vertical_rate_ms")]) * METRES_TO_FEET * 60.0
    distance_nm = scalars[:, framing.SCALAR_FEATURE_NAMES.index("distance_to_vabb_km")] * 1000.0 / framing.METRES_PER_NAUTICAL_MILE
    return {
        "turn": (turn_degrees, TURN_BUCKETS),
        "vertical": (vertical_fpm, VERTICAL_BUCKETS),
        "distance to VABB": (distance_nm, DISTANCE_BUCKETS),
    }


def evaluate(predictions: np.ndarray, y: np.ndarray, mask: np.ndarray, X: np.ndarray, label: str) -> dict:
    """Full per-horizon and per-bucket report. Every metric uses mask-valid rows only."""
    horizontal = framing.error_nm(predictions, y)
    along, cross = framing.error_along_cross_nm(X, predictions, y)
    altitude_ft = (predictions[..., 2] - y[..., 2].astype(np.float64)) * METRES_TO_FEET
    buckets = bucket_assignments(X)

    per_horizon = []
    for index, horizon_label in enumerate(HORIZON_LABELS):
        rows = mask[:, index]
        errors = horizontal[rows, index]
        altitude_errors = np.abs(altitude_ft[rows, index])
        per_horizon.append({
            "horizon": horizon_label,
            "n": int(rows.sum()),
            "mean_nm": float(errors.mean()),
            "rmse_nm": float(np.sqrt((errors ** 2).mean())),
            "median_nm": float(np.median(errors)),
            "p90_nm": float(np.percentile(errors, 90)),
            "within_1_nm": float((errors < 1.0).mean() * 100),
            "within_2_5_nm": float((errors < 2.5).mean() * 100),
            "within_5_nm": float((errors < 5.0).mean() * 100),
            "along_mae_nm": float(np.abs(along[rows, index]).mean()),
            "cross_mae_nm": float(np.abs(cross[rows, index]).mean()),
            "altitude_mae_ft": float(altitude_errors.mean()),
            "within_500_ft": float((altitude_errors < 500.0).mean() * 100),
            "within_1000_ft": float((altitude_errors < 1000.0).mean() * 100),
        })

    per_bucket = []
    for family, (values, definitions) in buckets.items():
        for name, lower, upper in definitions:
            in_bucket = (values >= lower) & (values < upper)
            for index, horizon_label in enumerate(HORIZON_LABELS):
                rows = in_bucket & mask[:, index]
                count = int(rows.sum())
                per_bucket.append({
                    "family": family,
                    "bucket": name,
                    "horizon": horizon_label,
                    "n": count,
                    "within_5_nm": float((horizontal[rows, index] < 5.0).mean() * 100) if count else float("nan"),
                    "mean_nm": float(horizontal[rows, index].mean()) if count else float("nan"),
                })

    return {"label": label, "per_horizon": per_horizon, "per_bucket": per_bucket}


def print_report(results: dict) -> None:
    print("")
    print(f"=== {results['label']} ===")
    header = (f"{'horizon':<8}{'n':>7}{'mean':>8}{'RMSE':>8}{'median':>8}{'p90':>8}"
              f"{'<1NM':>8}{'<2.5NM':>8}{'<5NM':>8}{'along':>8}{'cross':>8}{'alt ft':>9}{'<500ft':>8}{'<1000ft':>9}")
    print(header)
    print("-" * len(header))
    for row in results["per_horizon"]:
        print(f"{row['horizon']:<8}{row['n']:>7}{row['mean_nm']:>8.2f}{row['rmse_nm']:>8.2f}"
              f"{row['median_nm']:>8.2f}{row['p90_nm']:>8.2f}"
              f"{row['within_1_nm']:>7.1f}%{row['within_2_5_nm']:>7.1f}%{row['within_5_nm']:>7.1f}%"
              f"{row['along_mae_nm']:>8.2f}{row['cross_mae_nm']:>8.2f}"
              f"{row['altitude_mae_ft']:>9.1f}{row['within_500_ft']:>7.1f}%{row['within_1000_ft']:>8.1f}%")

    print("")
    print("By flight regime (n and % within 5 NM):")
    current_family = None
    for family in dict.fromkeys(row["family"] for row in results["per_bucket"]):
        if family != current_family:
            print("")
            print(f"  {family}")
            print(f"    {'bucket':<22}" + "".join(f"{label:>18}" for label in HORIZON_LABELS))
            current_family = family
        for bucket in dict.fromkeys(row["bucket"] for row in results["per_bucket"] if row["family"] == family):
            cells = []
            for horizon_label in HORIZON_LABELS:
                row = next(r for r in results["per_bucket"] if r["family"] == family and r["bucket"] == bucket and r["horizon"] == horizon_label)
                cells.append("               n/a" if row["n"] == 0 else f"{row['n']:>9} {row['within_5_nm']:>6.1f}%")
            print(f"    {bucket:<22}" + "".join(cells))


def compare(predictions_a, predictions_b, y, mask, X, label_a: str, label_b: str) -> tuple[dict, dict, bool]:
    """Print the two evaluations side by side and decide whether A clears B."""
    results_a = evaluate(predictions_a, y, mask, X, label_a)
    results_b = evaluate(predictions_b, y, mask, X, label_b)

    print("")
    header = (f"{'horizon':<8}{'n':>7}  {label_a[:12]:>12}{label_b[:12]:>13}{'delta':>9}   "
              f"{label_a[:12]:>12}{label_b[:12]:>13}{'delta':>9}")
    print(f"{'':<8}{'':>7}  {'--- mean error NM ---':^34}   {'--- % within 5 NM ---':^34}")
    print(header)
    print("-" * len(header))
    passed = True
    for row_a, row_b in zip(results_a["per_horizon"], results_b["per_horizon"]):
        mean_delta = row_a["mean_nm"] - row_b["mean_nm"]
        within_delta = row_a["within_5_nm"] - row_b["within_5_nm"]
        passed &= within_delta >= 0
        print(f"{row_a['horizon']:<8}{row_a['n']:>7}  {row_a['mean_nm']:>12.2f}{row_b['mean_nm']:>13.2f}{mean_delta:>+9.2f}   "
              f"{row_a['within_5_nm']:>11.1f}%{row_b['within_5_nm']:>12.1f}%{within_delta:>+8.1f}%")

    print("")
    print(f"GATE: {label_a} beats {label_b} at every horizon on within-5-NM -> {'PASS' if passed else 'FAIL'}")
    return results_a, results_b, bool(passed)


def write_results(results: dict) -> tuple[Path, Path]:
    """Persist the full report as CSV (for analysis) and Markdown (for the report)."""
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    slug = results["label"].lower().replace(" ", "_").replace("/", "_")
    csv_path = DATA_DIRECTORY / f"eval_{slug}.csv"
    markdown_path = DATA_DIRECTORY / f"eval_{slug}.md"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["section"] + list(results["per_horizon"][0].keys()))
        for row in results["per_horizon"]:
            writer.writerow(["per_horizon"] + list(row.values()))
        writer.writerow([])
        writer.writerow(["section"] + list(results["per_bucket"][0].keys()))
        for row in results["per_bucket"]:
            writer.writerow(["per_bucket"] + list(row.values()))

    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write(f"# Trajectory evaluation: {results['label']}\n\n")
        handle.write("## Per horizon\n\n")
        columns = list(results["per_horizon"][0].keys())
        handle.write("| " + " | ".join(columns) + " |\n")
        handle.write("|" + "---|" * len(columns) + "\n")
        for row in results["per_horizon"]:
            handle.write("| " + " | ".join(f"{value:.2f}" if isinstance(value, float) else str(value) for value in row.values()) + " |\n")
        handle.write("\n## By flight regime\n\n")
        handle.write("| family | bucket | horizon | n | % within 5 NM | mean NM |\n|---|---|---|---|---|---|\n")
        for row in results["per_bucket"]:
            within = "n/a" if row["n"] == 0 else f"{row['within_5_nm']:.1f}"
            mean = "n/a" if row["n"] == 0 else f"{row['mean_nm']:.2f}"
            handle.write(f"| {row['family']} | {row['bucket']} | {row['horizon']} | {row['n']} | {within} | {mean} |\n")

    return csv_path, markdown_path


def main() -> None:
    """Standalone run: evaluate the constant-velocity baseline on the test split."""
    X, y, mask = load_split("test")
    predictions = framing.constant_velocity_predict(X)
    results = evaluate(predictions, y, mask, X, "constant velocity")
    print(f"Test split: {len(X)} samples, valid per horizon "
          f"{'/'.join(str(int(count)) for count in mask.sum(axis=0))}")
    print_report(results)
    csv_path, markdown_path = write_results(results)
    print("")
    print(f"Wrote {csv_path}")
    print(f"Wrote {markdown_path}")


if __name__ == "__main__":
    main()
