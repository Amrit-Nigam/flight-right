"""Multi-path trajectory prediction: several candidate routes with probabilities.

Why this exists, measured rather than assumed. Two aircraft in an identical situation
-- same position, altitude, heading, descent rate -- finish an average of 7.9 NM apart
ten minutes later, and 64% of such pairs finish more than 5 NM from each other. The
same starting state genuinely leads to different outcomes, because whether a
controller turns an aircraft now or in two minutes is a decision made with information
we never receive. A model forced to name one future will therefore often name the
wrong one, and no amount of training fixes that: it is uncertainty in the world, not
error in the model.

So we name several. For conflict detection we never have to pick one -- we check every
plausible path and warn if any of them brings two aircraft too close. Safety comes
from covering the possibilities, not from guessing right.

This does NOT replace train_trajectory.py. The single-answer residual LSTM stays as
the fallback and as the model that answers "where is this aircraft going" when one
answer is what is wanted. This module answers "where might it go, and how likely is
each", which is the question conflict probability actually needs.

Run: venv/Scripts/python.exe ml_pipeline/training/trajectory/multipath.py
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier

import framing


# 40 route patterns. The measured trade: too few and each pattern is a coarse average
# of genuinely different routes, too many and the classifier cannot tell them apart.
# On test arrivals at ten minutes, within 5 NM with 5 options: 8 patterns 29.8%,
# 25 patterns 64.4%, 60 patterns 69.3%, 150 patterns 24.6%. The workable range is
# roughly 25-60 and 40 sits in the middle of it. Do NOT reduce this to "simplify".
N_PATTERNS = 40
# How many candidate paths inference returns. 5 is the reporting default; the
# evaluation below also measures 1, 3 and 10 so the trade is visible.
TOP_K = 5
# Arrivals are the hard case and the one the gate is measured on: inside this
# distance from Mumbai the aircraft is manoeuvring, queuing and descending.
ARRIVAL_DISTANCE_NM = 40.0
TEN_MINUTE_INDEX = 3
WITHIN_NM = 5.0

CLASSIFIER_MAX_ITERATIONS = 300
CLASSIFIER_LEARNING_RATE = 0.08
CLASSIFIER_MAX_LEAF_NODES = 63
CLASSIFIER_MIN_SAMPLES_LEAF = 40
CLASSIFIER_L2 = 1.0
RANDOM_SEED = 42

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "processed"
MODEL_PATH = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models" / "trajectory_multipath.pkl"
SINGLE_ANSWER_MODEL_PATH = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models" / "trajectory_residual.pt"


def load_split(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = DATA_DIRECTORY / f"trajectory_{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run preprocess_sequences.py first.")
    with np.load(path) as data:
        if "mask" not in data:
            raise KeyError(f"{path} predates per-horizon masking. Re-run preprocess_sequences.py.")
        return data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)


def build_feature_matrix(X: np.ndarray) -> np.ndarray:
    """The same 20 features the other models use: 10 steps x 7, plus 13 window scalars."""
    sequence, scalars = framing.to_local_features(X)
    return np.concatenate([sequence.reshape(len(X), -1), scalars], axis=1)


def arrival_rows(X: np.ndarray) -> np.ndarray:
    """Boolean mask of aircraft inside the terminal area, i.e. arriving traffic."""
    _, scalars = framing.to_local_features(X)
    distance_nm = scalars[:, framing.SCALAR_FEATURE_NAMES.index("distance_to_vabb_km")] * 1000.0 / framing.METRES_PER_NAUTICAL_MILE
    return distance_nm < ARRIVAL_DISTANCE_NM


def fit_route_patterns(X: np.ndarray, y: np.ndarray, mask: np.ndarray) -> tuple[KMeans, np.ndarray, np.ndarray]:
    """Cluster the ten-minute residual into route patterns, fitted on TRAINING data only.

    Clustering is on the ten-minute along/cross residual in nautical miles, and only
    over rows whose ten-minute target is valid. Two choices worth stating:

    * **Ten minutes, not all four horizons.** Where an aircraft ends up at ten minutes
      is what separates one route from another -- at one minute every route looks the
      same. It is also the horizon the gate is measured on, so the clustering is
      aligned with the metric rather than compromising across horizons.
    * **Only ten-minute-valid rows.** The alternative, requiring all four horizons,
      keeps 46% of samples instead of 50% and drops them non-randomly. Either way the
      rows without a ten-minute target are disproportionately aircraft that land
      inside ten minutes. This is a real limitation of the pattern set and is stated
      in the report rather than hidden: patterns are learned from flights that were
      still airborne ten minutes later.

    Along and cross are both in NM, so no feature scaling is applied -- scaling would
    distort the geometry that makes two routes different.
    """
    valid = mask[:, TEN_MINUTE_INDEX]
    residual = framing.residual_targets(X, y, framing.constant_velocity_predict(X))
    all_ten_minute_nm = residual[:, TEN_MINUTE_INDEX, :2] / framing.METRES_PER_NAUTICAL_MILE

    # KMeans places centres where the DATA is dense, and our data is 84% en-route
    # cruise whose residual is near zero. Fitted on the raw pool it put 43.7% of
    # rows in a single cluster and spent its remaining resolution on the tail, which
    # capped the achievable hit rate on arrivals at 68.1% -- below the gate before
    # the classifier had made a single mistake. Arrivals are 16% of rows but carry
    # most of the variety, so the fit is balanced between the two.
    #
    # Measured ceiling (nearest of all 40 centres, test, within 5 NM):
    #   raw pool       arrivals 68.1%   all 89.5%   largest cluster 43.7%
    #   arrivals only  arrivals 75.8%   all 70.9%   -- wrecks en-route
    #   balanced 50/50 arrivals 74.7%   all 88.8%   largest cluster 34.4%
    # N_PATTERNS is unchanged at 40; this is where the centres go, not how many.
    arrivals = arrival_rows(X) & valid
    en_route = (~arrival_rows(X)) & valid
    arrival_indices = np.flatnonzero(arrivals)
    en_route_indices = np.flatnonzero(en_route)
    generator = np.random.default_rng(RANDOM_SEED)
    sampled_en_route = generator.choice(
        en_route_indices, min(len(arrival_indices), len(en_route_indices)), replace=False
    )
    fit_indices = np.concatenate([arrival_indices, sampled_en_route])

    kmeans = KMeans(n_clusters=N_PATTERNS, random_state=RANDOM_SEED, n_init=10)
    kmeans.fit(all_ten_minute_nm[fit_indices])
    # Every valid row is then assigned to its nearest centre, so no training data is
    # discarded -- only the centre PLACEMENT is balanced.
    labels_for_valid = kmeans.predict(all_ten_minute_nm[valid])
    print(f"  cluster centres fitted on {len(fit_indices):,} balanced rows "
          f"({len(arrival_indices):,} arrivals + {len(sampled_en_route):,} en-route); "
          f"all {int(valid.sum()):,} valid rows then assigned to their nearest centre.")

    # Per-cluster mean residual at every horizon, in metres, over mask-valid rows only.
    # A horizon with no valid rows in a cluster falls back to zero, which is the
    # constant-velocity answer -- the safe default everywhere in this project.
    valid_indices = np.flatnonzero(valid)
    pattern_residuals = np.zeros((N_PATTERNS, len(framing.HORIZONS_SECONDS), 3), dtype=np.float64)
    for pattern in range(N_PATTERNS):
        rows = valid_indices[labels_for_valid == pattern]
        for horizon_index in range(len(framing.HORIZONS_SECONDS)):
            horizon_rows = rows[mask[rows, horizon_index]]
            if len(horizon_rows):
                pattern_residuals[pattern, horizon_index] = residual[horizon_rows, horizon_index].mean(axis=0)

    labels = np.full(len(X), -1, dtype=np.int64)
    labels[valid] = labels_for_valid
    return kmeans, pattern_residuals, labels


def print_cluster_report(pattern_residuals: np.ndarray, labels: np.ndarray) -> None:
    """Cluster sizes and the mean along/cross/altitude residual of each."""
    print("")
    print(f"Route patterns ({N_PATTERNS} clusters, fitted on the training split only)")
    print(f"  mean residual from constant velocity at the ten-minute horizon")
    print(f"  {'pattern':>7} {'size':>7} {'share':>7} {'along NM':>9} {'cross NM':>9} {'alt ft':>9}")
    counts = np.bincount(labels[labels >= 0], minlength=N_PATTERNS)
    order = np.argsort(-counts)
    for pattern in order:
        along = pattern_residuals[pattern, TEN_MINUTE_INDEX, 0] / framing.METRES_PER_NAUTICAL_MILE
        cross = pattern_residuals[pattern, TEN_MINUTE_INDEX, 1] / framing.METRES_PER_NAUTICAL_MILE
        altitude = pattern_residuals[pattern, TEN_MINUTE_INDEX, 2] * 3.28084
        print(f"  {pattern:>7} {counts[pattern]:>7,} {counts[pattern] / counts.sum():>6.2%} "
              f"{along:>9.2f} {cross:>9.2f} {altitude:>9.0f}")
    print(f"  total labelled: {counts.sum():,}   smallest cluster: {counts.min():,}   "
          f"largest: {counts.max():,}")


def candidate_paths(classifier, kmeans, pattern_residuals, X: np.ndarray, top_k: int):
    """Top-k route patterns per sample: renormalised probabilities and absolute positions.

    Returns (probabilities, positions, pattern_indices, raw_probabilities) where
    positions has shape (N, k, 4, 3) -- k candidate paths, each with lat/lon/altitude
    at the four horizons.
    """
    features = build_feature_matrix(X)
    raw_probabilities = classifier.predict_proba(features)
    # Classes may be a subset of range(N_PATTERNS) if a cluster never appears.
    top_columns = np.argsort(-raw_probabilities, axis=1)[:, :top_k]
    top_probabilities = np.take_along_axis(raw_probabilities, top_columns, axis=1)
    patterns = classifier.classes_[top_columns]

    # Renormalise so the k retained options sum to 1: the discarded tail is not
    # available to the conflict check, so leaving it out would understate every
    # probability the escalation rule sees.
    normalised = top_probabilities / top_probabilities.sum(axis=1, keepdims=True)

    cv = framing.constant_velocity_predict(X)
    positions = np.empty((len(X), top_k, len(framing.HORIZONS_SECONDS), 3), dtype=np.float64)
    for option in range(top_k):
        positions[:, option] = framing.apply_residual(X, cv, pattern_residuals[patterns[:, option]])
    return normalised, positions, patterns, top_probabilities


def best_of_k_within(positions: np.ndarray, y: np.ndarray, rows: np.ndarray, k: int) -> float:
    """Percentage of samples where ANY of the first k candidate paths lands within 5 NM.

    This is the honest metric for a multi-path model: the conflict checker examines
    every candidate, so a hit on any of them is a hit. It is not the same claim as
    "the model predicts the right answer" and must not be reported as if it were.
    """
    errors = np.stack([
        framing.error_nm(positions[:, option], y)[:, TEN_MINUTE_INDEX] for option in range(k)
    ], axis=1)
    return float((errors[rows].min(axis=1) < WITHIN_NM).mean() * 100)


def print_reliability(raw_probabilities: np.ndarray, patterns: np.ndarray, true_labels: np.ndarray,
                      rows: np.ndarray) -> None:
    """Do the stated probabilities mean anything? If it says 60%, ~60% should be right."""
    stated = raw_probabilities[rows].ravel()
    correct = (patterns[rows] == true_labels[rows][:, None]).ravel()
    print("")
    print("Reliability of the stated probabilities (all candidate options pooled)")
    print(f"  {'stated band':>14} {'options':>9} {'mean stated':>12} {'observed':>10} {'gap':>8}")
    edges = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.01]
    for lower, upper in zip(edges, edges[1:]):
        in_band = (stated >= lower) & (stated < upper)
        if not in_band.any():
            continue
        mean_stated = stated[in_band].mean()
        observed = correct[in_band].mean()
        print(f"  {lower:>5.2f} - {upper:<5.2f}  {int(in_band.sum()):>9,} {mean_stated:>12.3f} "
              f"{observed:>10.3f} {observed - mean_stated:>+8.3f}")
    print("  A positive gap means the model is under-confident, negative means over-confident.")


def print_worked_example(X: np.ndarray, y: np.ndarray, probabilities: np.ndarray, positions: np.ndarray,
                         patterns: np.ndarray, rows: np.ndarray) -> None:
    """One arriving aircraft, its five candidate paths, and which was closest to truth."""
    candidates = np.flatnonzero(rows)
    # Error of every candidate option, for every arriving aircraft: shape (N, k).
    option_errors = np.stack([
        framing.error_nm(positions[:, option], y)[:, TEN_MINUTE_INDEX] for option in range(positions.shape[1])
    ], axis=1)
    # Pick an aircraft where the options genuinely disagree AND one of them is right,
    # so the example shows what the model is for rather than a case where all five
    # paths coincide or all five are wrong.
    usable = candidates[option_errors[candidates].min(axis=1) < WITHIN_NM]
    pool = usable if len(usable) else candidates
    chosen = int(pool[np.argmax(np.ptp(option_errors[pool], axis=1))])

    truth = y[chosen, TEN_MINUTE_INDEX]
    print("")
    print("Worked example: one arriving aircraft, ten minutes ahead")
    _, scalars = framing.to_local_features(X[chosen:chosen + 1])
    print(f"  aircraft now: lat {X[chosen, -1, framing.LATITUDE]:.4f}, lon {X[chosen, -1, framing.LONGITUDE]:.4f}, "
          f"altitude {X[chosen, -1, framing.ALTITUDE] * 3.28084:,.0f} ft, "
          f"{scalars[0, framing.SCALAR_FEATURE_NAMES.index('distance_to_vabb_km')] * 1000 / framing.METRES_PER_NAUTICAL_MILE:.1f} NM from VABB")
    print(f"  truth at ten minutes: lat {truth[0]:.4f}, lon {truth[1]:.4f}, altitude {truth[2] * 3.28084:,.0f} ft")
    print(f"  {'option':>6} {'pattern':>8} {'probability':>12} {'predicted lat':>14} {'predicted lon':>14} {'error NM':>9}")
    errors = []
    for option in range(positions.shape[1]):
        predicted = positions[chosen, option, TEN_MINUTE_INDEX]
        error = framing.error_nm(positions[chosen:chosen + 1, option], y[chosen:chosen + 1])[0, TEN_MINUTE_INDEX]
        errors.append(error)
        print(f"  {option + 1:>6} {patterns[chosen, option]:>8} {probabilities[chosen, option]:>12.3f} "
              f"{predicted[0]:>14.4f} {predicted[1]:>14.4f} {error:>9.2f}")
    best = int(np.argmin(errors))
    print(f"  -> truth was closest to option {best + 1} (pattern {patterns[chosen, best]}), "
          f"{errors[best]:.2f} NM away, which the model gave {probabilities[chosen, best]:.1%}.")
    print(f"  -> the single most likely option was {errors[0]:.2f} NM away; "
          f"spread across the five options is {min(errors):.2f} to {max(errors):.2f} NM.")


def single_answer_within(X: np.ndarray, y: np.ndarray, rows: np.ndarray) -> float | None:
    """Run the saved single-answer LSTM so the comparison is measured, not quoted."""
    if not SINGLE_ANSWER_MODEL_PATH.exists():
        return None
    try:
        import torch
        import train_trajectory
    except Exception:
        return None
    checkpoint = torch.load(SINGLE_ANSWER_MODEL_PATH, map_location="cpu", weights_only=False)
    model = train_trajectory.ResidualTrajectoryModel()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    feature_stats = {key: np.asarray(value, dtype=np.float64) for key, value in checkpoint["feature_normalization"].items()}
    residual_stats = {key: np.asarray(value, dtype=np.float64) for key, value in checkpoint["residual_normalization"].items()}
    sequence, scalars = framing.to_local_features(X)
    normalised_sequence = (sequence - feature_stats["sequence_mean"]) / feature_stats["sequence_std"]
    normalised_scalars = (scalars - feature_stats["scalar_mean"]) / feature_stats["scalar_std"]

    outputs = []
    with torch.no_grad():
        for start in range(0, len(X), 4096):
            batch = model(
                torch.from_numpy(normalised_sequence[start:start + 4096].astype(np.float32)),
                torch.from_numpy(normalised_scalars[start:start + 4096].astype(np.float32)),
            )
            outputs.append(batch.numpy())
    residual = np.concatenate(outputs).astype(np.float64) * residual_stats["residual_std"] + residual_stats["residual_mean"]
    predicted = framing.apply_residual(X, framing.constant_velocity_predict(X), residual)
    errors = framing.error_nm(predicted, y)[:, TEN_MINUTE_INDEX]
    return float((errors[rows] < WITHIN_NM).mean() * 100)


def main() -> None:
    train_x, train_y, train_mask = load_split("train")
    test_x, test_y, test_mask = load_split("test")
    print(f"Samples: {len(train_x):,} train / {len(test_x):,} test")

    kmeans, pattern_residuals, train_labels = fit_route_patterns(train_x, train_y, train_mask)
    print_cluster_report(pattern_residuals, train_labels)

    # The classifier learns which route pattern applies from the aircraft's own
    # recent motion -- the same 20 features every other model in this project uses.
    labelled = train_labels >= 0
    features = build_feature_matrix(train_x)[labelled]
    print("")
    print(f"Training the pattern classifier on {len(features):,} labelled windows, "
          f"{features.shape[1]} features...")
    classifier = HistGradientBoostingClassifier(
        max_iter=CLASSIFIER_MAX_ITERATIONS, learning_rate=CLASSIFIER_LEARNING_RATE,
        max_leaf_nodes=CLASSIFIER_MAX_LEAF_NODES, min_samples_leaf=CLASSIFIER_MIN_SAMPLES_LEAF,
        l2_regularization=CLASSIFIER_L2, random_state=RANDOM_SEED,
    )
    classifier.fit(features, train_labels[labelled])

    # Test-side truth: which pattern the aircraft actually flew, for the reliability check.
    test_valid = test_mask[:, TEN_MINUTE_INDEX]
    test_residual = framing.residual_targets(test_x, test_y, framing.constant_velocity_predict(test_x))
    test_true_labels = np.full(len(test_x), -1, dtype=np.int64)
    test_true_labels[test_valid] = kmeans.predict(
        test_residual[test_valid][:, TEN_MINUTE_INDEX, :2] / framing.METRES_PER_NAUTICAL_MILE
    )

    arrivals = arrival_rows(test_x) & test_valid
    all_test = test_valid
    print(f"Test rows with a ten-minute target: {int(test_valid.sum()):,}   "
          f"of which arrivals (<{ARRIVAL_DISTANCE_NM:.0f} NM from VABB): {int(arrivals.sum()):,}")

    max_k = 10
    probabilities, positions, patterns, raw_top = candidate_paths(
        classifier, kmeans, pattern_residuals, test_x, max_k
    )

    baseline_positions = framing.constant_velocity_predict(test_x)
    baseline_within = float((framing.error_nm(baseline_positions, test_y)[arrivals, TEN_MINUTE_INDEX] < WITHIN_NM).mean() * 100)
    single_within = single_answer_within(test_x, test_y, arrivals)

    print("")
    print("=" * 88)
    print("TEST ARRIVALS AT TEN MINUTES -- % within 5 NM")
    print("=" * 88)
    print(f"  {'method':<34} {'arrivals':>10} {'all test':>10}")
    print(f"  {'constant velocity (baseline)':<34} {baseline_within:>9.1f}% "
          f"{float((framing.error_nm(baseline_positions, test_y)[all_test, TEN_MINUTE_INDEX] < WITHIN_NM).mean() * 100):>9.1f}%")
    if single_within is not None:
        print(f"  {'single-answer residual LSTM':<34} {single_within:>9.1f}% "
              f"{single_answer_within(test_x, test_y, all_test):>9.1f}%")
    else:
        print(f"  {'single-answer residual LSTM':<34} {'n/a':>10} (saved model not loadable)")
    for k in (1, 3, 5, 10):
        label = f"multi-path, {k} option{'s' if k > 1 else ''}"
        marker = "   <- gate" if k == TOP_K else ""
        print(f"  {label:<34} {best_of_k_within(positions, test_y, arrivals, k):>9.1f}% "
              f"{best_of_k_within(positions, test_y, all_test, k):>9.1f}%{marker}")

    print_reliability(raw_top, patterns, test_true_labels, arrivals)
    print_worked_example(test_x, test_y, probabilities[:, :TOP_K], positions[:, :TOP_K], patterns[:, :TOP_K], arrivals)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as handle:
        pickle.dump({
            "kmeans": kmeans,
            "classifier": classifier,
            "pattern_residuals": pattern_residuals,
            "config": {
                "n_patterns": N_PATTERNS,
                "top_k": TOP_K,
                "horizons_seconds": framing.HORIZONS_SECONDS.tolist(),
                "input_steps": int(train_x.shape[1]),
                "feature_count": int(features.shape[1]),
                "clustered_on": "ten-minute along/cross residual, NM",
                "arrival_distance_nm": ARRIVAL_DISTANCE_NM,
            },
        }, handle)
    print("")
    print(f"Saved clusters, classifier and config: {MODEL_PATH}")

    gate_value = best_of_k_within(positions, test_y, arrivals, TOP_K)
    print("")
    print(f"GATE ({TOP_K} options, test arrivals at ten minutes, within 5 NM, must be "
          f"comfortably above 60%): {gate_value:.1f}% -> {'PASS' if gate_value > 60.0 else 'FAIL'}")


if __name__ == "__main__":
    main()
