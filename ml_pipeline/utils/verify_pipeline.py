"""End-to-end check that every stage of the pipeline runs and produces sane output.

This answers one question: does the whole thing actually work, from raw collected data
through to a tiered conflict alert, with every saved model loading in a fresh process
and returning output of the right shape and the right magnitude?

It is deliberately NOT a model-quality script. It does not care whether the LSTM is
good, only whether it loads, runs, returns latitude and longitude in the right places,
and clears the one gate the project defines for it (beating constant velocity). Quality
lives in evaluate.py and in the training scripts.

Why this exists. The project has no automated tests, and the two most expensive defects
so far were both silent: a trajectory model that lost to plain arithmetic at every
horizon went unnoticed for three weeks because nobody printed the comparison, and a
conflict classifier trained on a circular label scored a perfect 1.0 for weeks because
nothing checked whether the answer could be recomputed from the question. Neither was a
crash. Both would have been caught by a script that looked at the output.

Run: venv/Scripts/python.exe ml_pipeline/utils/verify_pipeline.py
Exit code 0 if every check passes, 1 otherwise.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "training" / "trajectory"
CLASSIFIER_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "training" / "conflict_classifier"
for path in (PROJECT_ROOT, TRAJECTORY_DIRECTORY, CLASSIFIER_DIRECTORY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import framing  # noqa: E402
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    ALERT_LATERAL_NM,
    assign_tier,
    classify_conflict,
    compute_cpa,
    compute_cpa_from_paths,
    compute_cpa_from_states,
    conflict_probability,
    escalate_pair,
    predict_dense_grid,
)

DATA_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "processed"
SYNTHETIC_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "synthetic"
MODEL_DIRECTORY = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models"

# Mumbai collection box, from the ingestion scripts. Any predicted position far
# outside this is a framing or unit error, not a bad prediction.
LATITUDE_BOUNDS = (14.0, 26.0)
LONGITUDE_BOUNDS = (66.0, 80.0)
SAMPLE_ROWS = 3000


def sample(array: np.ndarray, count: int = SAMPLE_ROWS) -> np.ndarray:
    """Take rows spread evenly across the split, not the first N.

    The splits are in time order, so the first N rows are one stretch of one
    afternoon. Spreading the sample keeps the check representative of the whole
    test period without loading all of it.
    """
    if len(array) <= count:
        return array
    return array[np.linspace(0, len(array) - 1, count).astype(int)]

results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  --  {detail}" if detail else ""))
    return passed


def section(title: str) -> None:
    print("")
    print("=" * 92)
    print(title)
    print("=" * 92)


# --------------------------------------------------------------------------------------
def verify_trajectory_data() -> dict | None:
    section("1. TRAJECTORY DATA -- the sequences the trajectory models train on")
    splits = {}
    for name in ("train", "val", "test"):
        path = DATA_DIRECTORY / f"trajectory_{name}.npz"
        if not check(f"{name} split exists", path.exists(), str(path.name)):
            return None
        with np.load(path) as data:
            keys = set(data.files)
            if not check(f"{name} split carries X, y, mask, timestamps",
                         {"X", "y", "mask", "timestamps"}.issubset(keys), f"has {sorted(keys)}"):
                return None
            splits[name] = {key: data[key] for key in ("X", "y", "mask", "timestamps")}

    train, val, test = splits["train"], splits["val"], splits["test"]
    check("input window is 10 states x 8 raw features",
          train["X"].shape[1:] == (10, 8), f"shape {train['X'].shape}")
    check("targets are 4 horizons x (lat, lon, altitude)",
          train["y"].shape[1:] == (4, 3), f"shape {train['y'].shape}")

    # The mask contract: invalid targets are 0.0 placeholders and must never be read.
    # If a masked-out slot ever held a real coordinate, code that ignored the mask would
    # silently train on it, so the placeholder must actually be zero.
    invalid = ~train["mask"]
    leaked = int(np.count_nonzero(train["y"][invalid])) if invalid.any() else 0
    check("masked-out targets are 0.0 placeholders, as the contract states",
          leaked == 0, f"{leaked} non-zero values behind the mask")

    # The split must be by time. Test data has to be strictly later than training data.
    train_end, val_start = train["timestamps"].max(), val["timestamps"].min()
    val_end, test_start = val["timestamps"].max(), test["timestamps"].min()
    check("validation starts after training ends (time-based split)",
          val_start > train_end, f"gap {int(val_start - train_end)} s")
    check("test starts after validation ends (time-based split)",
          test_start > val_end, f"gap {int(test_start - val_end)} s")

    spans = {name: pd.to_datetime(split["timestamps"][[0, -1]], unit="s", utc=True)
             + pd.Timedelta(hours=5, minutes=30) for name, split in splits.items()}
    for name, span in spans.items():
        print(f"         {name:<5} {len(splits[name]['X']):>7,} samples   "
              f"{span[0]:%d %b %H:%M} -> {span[1]:%d %b %H:%M} IST")
    return splits


def verify_framing(splits: dict) -> None:
    section("2. COORDINATE FRAMING -- the maths shared by training, evaluation and inference")
    X = sample(splits["test"]["X"])
    y = sample(splits["test"]["y"])

    cv = framing.constant_velocity_predict(X)
    check("constant-velocity baseline returns (N, 4, 3)", cv.shape == (len(X), 4, 3), f"{cv.shape}")
    inside = ((cv[..., 0] > LATITUDE_BOUNDS[0]) & (cv[..., 0] < LATITUDE_BOUNDS[1])
              & (cv[..., 1] > LONGITUDE_BOUNDS[0]) & (cv[..., 1] < LONGITUDE_BOUNDS[1]))
    check("baseline predictions land in the Mumbai region",
          inside.mean() > 0.98, f"{inside.mean():.2%} inside the collection box")

    # residual_targets and apply_residual must invert each other exactly, because
    # training writes one and inference reads the other. Any drift silently corrupts
    # every prediction the backend would ever serve.
    residual = framing.residual_targets(X, y, cv)
    rebuilt = framing.apply_residual(X, cv, residual)
    error_deg = float(np.abs(rebuilt[..., :2] - y[..., :2].astype(np.float64)).max())
    check("residual transform inverts exactly (apply(residual(y)) == y)",
          error_deg < 1e-9, f"worst error {error_deg:.2e} degrees")

    sequence, scalars = framing.to_local_features(X)
    check("local features are (N, 10, 7) sequence + (N, 13) scalars",
          sequence.shape == (len(X), 10, 7) and scalars.shape == (len(X), 13),
          f"{sequence.shape} and {scalars.shape}")
    check("local features contain no NaN or infinity",
          bool(np.isfinite(sequence).all() and np.isfinite(scalars).all()))


def verify_trajectory_model(splits: dict) -> np.ndarray | None:
    section("3. MODEL 1 -- the residual trajectory LSTM, loaded fresh from its saved file")
    path = MODEL_DIRECTORY / "trajectory_residual.pt"
    if not check("saved model file exists", path.exists(), str(path.name)):
        return None
    try:
        import torch
        from train_trajectory import ResidualTrajectoryModel
    except Exception as error:  # noqa: BLE001
        check("torch and the model class import", False, str(error))
        return None

    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    needed = {"model_state_dict", "feature_normalization", "residual_normalization", "config"}
    if not check("checkpoint carries weights, both normalisations and a config",
                 needed.issubset(checkpoint), f"has {sorted(checkpoint)}"):
        return None
    config = checkpoint["config"]
    print(f"         config: {config['num_layers']} layers, hidden {config['hidden_size']}, "
          f"horizons {config['horizons_seconds']}")

    model = ResidualTrajectoryModel()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    X = sample(splits["test"]["X"])
    y = sample(splits["test"]["y"])
    mask = sample(splits["test"]["mask"])
    cv = framing.constant_velocity_predict(X)
    sequence, scalars = framing.to_local_features(X)
    feature_stats = checkpoint["feature_normalization"]
    residual_stats = checkpoint["residual_normalization"]
    normalised_sequence = (sequence - feature_stats["sequence_mean"]) / feature_stats["sequence_std"]
    normalised_scalars = (scalars - feature_stats["scalar_mean"]) / feature_stats["scalar_std"]
    with torch.no_grad():
        raw = model(torch.from_numpy(normalised_sequence.astype(np.float32)),
                    torch.from_numpy(normalised_scalars.astype(np.float32))).numpy()
    residual = raw.astype(np.float64) * residual_stats["residual_std"] + residual_stats["residual_mean"]
    predictions = framing.apply_residual(X, cv, residual)

    check("output is (N, 4 horizons, 3 values)", predictions.shape == (len(X), 4, 3), f"{predictions.shape}")
    check("output contains no NaN or infinity", bool(np.isfinite(predictions).all()))
    inside = ((predictions[..., 0] > LATITUDE_BOUNDS[0]) & (predictions[..., 0] < LATITUDE_BOUNDS[1])
              & (predictions[..., 1] > LONGITUDE_BOUNDS[0]) & (predictions[..., 1] < LONGITUDE_BOUNDS[1]))
    check("predicted positions are real latitudes and longitudes in the Mumbai region",
          inside.mean() > 0.97, f"{inside.mean():.2%} inside the collection box")
    altitude_ok = (predictions[..., 2] > -500) & (predictions[..., 2] < 20000)
    check("predicted altitudes are physically plausible (metres)",
          altitude_ok.mean() > 0.98, f"{altitude_ok.mean():.2%} between -500 m and 20,000 m")

    # THE GATE. This is the check whose absence hid a failing model for three weeks.
    model_error = framing.error_nm(predictions, y)
    baseline_error = framing.error_nm(cv, y)
    print("")
    print(f"         {'horizon':<10}{'model <5NM':>12}{'baseline <5NM':>15}{'delta':>9}")
    beats_everywhere = True
    for index, horizon in enumerate(framing.HORIZONS_SECONDS):
        rows = mask[:, index]
        if not rows.any():
            continue
        model_rate = float((model_error[rows, index] < 5.0).mean() * 100)
        baseline_rate = float((baseline_error[rows, index] < 5.0).mean() * 100)
        beats_everywhere &= model_rate >= baseline_rate
        print(f"         {int(horizon) // 60:>2} min    {model_rate:>11.1f}%{baseline_rate:>14.1f}%"
              f"{model_rate - baseline_rate:>+8.1f}")
    check("model beats constant velocity at every horizon (the project gate)", beats_everywhere)
    return predictions


def verify_multipath(splits: dict) -> tuple | None:
    section("4. MODEL 1b -- multi-path candidates, loaded fresh from its saved file")
    path = MODEL_DIRECTORY / "trajectory_multipath.pkl"
    if not check("saved model file exists", path.exists(), str(path.name)):
        return None
    with path.open("rb") as handle:
        payload = pickle.load(handle)
    if not check("payload carries clusters, classifier, pattern residuals and config",
                 {"kmeans", "classifier", "pattern_residuals", "config"}.issubset(payload),
                 f"has {sorted(payload)}"):
        return None
    config = payload["config"]
    print(f"         config: {config['n_patterns']} route patterns, top {config['top_k']} returned")

    from multipath import candidate_paths
    X = sample(splits["test"]["X"])
    probabilities, positions, patterns, _ = candidate_paths(
        payload["classifier"], payload["kmeans"], payload["pattern_residuals"], X, config["top_k"]
    )
    top_k = config["top_k"]
    check(f"returns {top_k} candidate paths per aircraft, each 4 horizons x 3 values",
          positions.shape == (len(X), top_k, 4, 3), f"{positions.shape}")
    sums = probabilities.sum(axis=1)
    check("the returned probabilities sum to 1 for every aircraft",
          bool(np.allclose(sums, 1.0, atol=1e-9)), f"worst deviation {abs(sums - 1).max():.2e}")
    ordered = bool((np.diff(probabilities, axis=1) <= 1e-12).all())
    check("candidates are ordered most likely first", ordered)
    inside = ((positions[..., 0] > LATITUDE_BOUNDS[0]) & (positions[..., 0] < LATITUDE_BOUNDS[1])
              & (positions[..., 1] > LONGITUDE_BOUNDS[0]) & (positions[..., 1] < LONGITUDE_BOUNDS[1]))
    check("every candidate path lands in the Mumbai region",
          inside.mean() > 0.97, f"{inside.mean():.2%} inside the collection box")
    spread = float(np.median(np.hypot(
        (positions[:, :, 3, 0].max(axis=1) - positions[:, :, 3, 0].min(axis=1)) * 111320.0,
        (positions[:, :, 3, 1].max(axis=1) - positions[:, :, 3, 1].min(axis=1)) * 111320.0,
    ) / 1852.0))
    check("the candidates actually differ from each other at ten minutes",
          spread > 0.5, f"median spread across the 5 options {spread:.1f} NM")
    return probabilities, positions


def verify_conflict_classifier() -> None:
    section("5. MODEL 2 -- the conflict classifier, loaded fresh from its saved file")
    path = MODEL_DIRECTORY / "xgboost_conflict.json"
    if not check("saved model file exists", path.exists(), str(path.name)):
        return
    import json

    import xgboost as xgb

    booster = xgb.Booster()
    booster.load_model(path)
    threshold_attr = booster.attr("decision_threshold")
    features_attr = booster.attr("feature_columns")
    if not check("model file carries its own decision threshold and feature list",
                 threshold_attr is not None and features_attr is not None):
        return
    threshold = json.loads(threshold_attr)
    saved_features = json.loads(features_attr)
    print(f"         threshold {threshold:.4f}, {len(saved_features)} features, "
          f"trained on {booster.attr('training_dataset')}")

    from generate_synthetic_scenarios import FEATURE_COLUMNS, OUTCOME_COLUMNS
    check("saved feature list matches the generator that produces the data",
          saved_features == FEATURE_COLUMNS,
          "identical" if saved_features == FEATURE_COLUMNS else "MISMATCH -- retrain required")
    overlap = sorted(set(saved_features).intersection(OUTCOME_COLUMNS))
    check("no outcome column is being used as a feature (the circular-label defect)",
          not overlap, f"overlap {overlap}" if overlap else "features and outcomes are disjoint")

    files = sorted(SYNTHETIC_DIRECTORY.glob("encounters_real_outcome_*.parquet"))
    if not check("a real-outcome encounter dataset exists", bool(files)):
        return
    dataset = pd.read_parquet(files[-1])
    from train_xgboost import rule_predictions, split_by_session
    splits = split_by_session(dataset)
    test = splits["test"]
    probabilities = booster.inplace_predict(test[saved_features].to_numpy(dtype=np.float32))
    check("probabilities are in [0, 1]",
          bool((probabilities >= 0).all() and (probabilities <= 1).all()),
          f"range {probabilities.min():.4f} to {probabilities.max():.4f}")

    truth = test["is_conflict"].to_numpy()
    alerts = (probabilities >= threshold).astype(int)
    recall = float((alerts[truth == 1] == 1).mean())
    saved_recall = json.loads(booster.attr("test_recall"))
    check("recall reproduces the value recorded at training time",
          abs(recall - saved_recall) < 0.02, f"now {recall:.4f}, recorded {saved_recall:.4f}")

    rule = rule_predictions(test, ALERT_LATERAL_NM, 1500.0)
    rule_recall = float((rule[truth == 1] == 1).mean())
    check("model catches more real conflicts than the geometric rule it sits on top of",
          recall > rule_recall, f"model {recall:.4f} vs rule {rule_recall:.4f}")

    # The defect this whole dataset was rebuilt to remove.
    circular = ((test["predicted_cpa_lateral_nm"] < 5.0)
                & (test["predicted_cpa_vertical_ft"] < 1000.0)).astype(int).to_numpy()
    agreement = float((circular == truth).mean())
    check("the label cannot be recomputed from the features (no circular label)",
          agreement < 0.99, f"rule reproduces the label for {agreement:.2%} of rows, not ~100%")


def verify_end_to_end(splits: dict, multipath_output: tuple | None) -> None:
    section("6. END TO END -- two aircraft states straight through to a tiered alert")
    X = splits["test"]["X"]

    def state_from_window(row: int) -> dict:
        window = X[row, -1]
        heading = float(np.degrees(np.arctan2(window[4], window[5]))) % 360.0
        return {
            "latitude": float(window[0]), "longitude": float(window[1]),
            "altitude_m": float(window[2]), "velocity_ms": float(window[3]),
            "heading_deg": heading, "vertical_rate_ms": float(window[6]),
        }

    state_a = state_from_window(0)
    state_b = state_from_window(1)
    print(f"         aircraft A: {state_a['latitude']:.3f}, {state_a['longitude']:.3f} at "
          f"{state_a['altitude_m'] * 3.28084:,.0f} ft heading {state_a['heading_deg']:.0f}")
    print(f"         aircraft B: {state_b['latitude']:.3f}, {state_b['longitude']:.3f} at "
          f"{state_b['altitude_m'] * 3.28084:,.0f} ft heading {state_b['heading_deg']:.0f}")

    grid = predict_dense_grid(state_a)
    check("dense grid is 41 points, every 15 s out to 10 minutes",
          len(grid) == 41 and max(grid) == 600, f"{len(grid)} points ending at {max(grid)} s")

    cpa = compute_cpa_from_states(state_a, state_b)
    required = {"time_to_cpa_seconds", "cpa_lateral_distance_nm", "cpa_vertical_separation_ft",
                "is_converging", "grid", "per_horizon"}
    check("CPA result carries every field the downstream code reads",
          required.issubset(cpa), f"missing {sorted(required - set(cpa))}" if not required.issubset(cpa) else "")
    check("CPA is found on the dense grid, not only at the 4 named horizons",
          len(cpa["grid"]) == 41 and cpa["time_to_cpa_seconds"] % 15 == 0,
          f"CPA at {cpa['time_to_cpa_seconds']} s, {cpa['cpa_lateral_distance_nm']:.2f} NM")
    check("the four named horizons are still available for the dashboard",
          set(cpa["per_horizon"]) == {"1min", "3min", "5min", "10min"})

    classification = classify_conflict(cpa)
    check("classification returns a conflict flag and a severity",
          {"is_conflict", "severity"}.issubset(classification),
          f"is_conflict={classification['is_conflict']}, severity={classification['severity']}")

    tier_result = assign_tier(cpa)
    check("tier is one of background, alarm or advisory",
          tier_result["tier"] in (0, 1, 2),
          f"tier {tier_result['tier']} ({tier_result['tier_name']})")

    probability = conflict_probability(cpa)
    check("conflict probability is a number in [0, 1]",
          0.0 <= probability <= 1.0, f"{probability:.3f}")

    # Escalation needs several consecutive updates before it is allowed to notify, so a
    # single noisy position report cannot raise an alarm. history is the previous CPA
    # results for this same pair, oldest first.
    history: list = []
    outcome = escalate_pair(cpa, history)
    check("a single update never notifies, however alarming it looks",
          not outcome["notify"], f"after 1 update: notify={outcome['notify']}")
    for _ in range(3):
        outcome = escalate_pair(cpa, history)
        history.append(cpa)
    check("escalation returns a tier, a notify flag and a human-readable reason",
          {"tier", "notify", "reason"}.issubset(outcome), f"reason: {outcome.get('reason', '')[:60]}")
    check("nothing reaches the UI without an explanation string",
          bool(str(outcome.get("reason", "")).strip()))
    if outcome.get("notify"):
        check("a resolution is only offered for a notifying tier 1 pair",
              outcome.get("suggest_resolution", False) == (outcome["tier"] == 1),
              f"tier {outcome['tier']}, suggest_resolution {outcome.get('suggest_resolution')}")

    # The pair above is whatever the data happened to give us, and two aircraft picked
    # at random are almost always far apart -- so the plumbing gets exercised but the
    # ALARM never fires. This second pair is built to conflict, so the path that
    # actually interrupts a controller is tested rather than assumed.
    print("")
    print("         deliberately converging pair (head-on, same altitude, CPA about 2 minutes):")
    converging_a = {"latitude": 19.00, "longitude": 72.0000, "altitude_m": 10668.0,
                    "velocity_ms": 230.0, "heading_deg": 90.0, "vertical_rate_ms": 0.0}
    converging_b = {"latitude": 19.01, "longitude": 72.5226, "altitude_m": 10668.0,
                    "velocity_ms": 230.0, "heading_deg": 270.0, "vertical_rate_ms": 0.0}
    head_on = compute_cpa_from_states(converging_a, converging_b)
    check("a converging pair is detected as closing",
          head_on["is_converging"],
          f"CPA {head_on['cpa_lateral_distance_nm']:.2f} NM at {head_on['time_to_cpa_seconds']} s")
    head_on_class = classify_conflict(head_on)
    check("a genuine loss of separation is classified as a conflict",
          head_on_class["is_conflict"], f"severity {head_on_class['severity']}")
    check("its closest approach falls in tier 1, the alarm tier",
          assign_tier(head_on)["tier"] == 1, f"tier {assign_tier(head_on)['tier_name']}")

    alarm_history: list = []
    alarm = escalate_pair(head_on, alarm_history)
    check("the alarm does NOT fire on the first update (anti-flicker holds)",
          not alarm["notify"], "1 of 3 required consecutive updates")
    for _ in range(2):
        alarm_history.append(head_on)
        alarm = escalate_pair(head_on, alarm_history)
    check("the alarm DOES fire once the pair has held for 3 consecutive updates",
          alarm["notify"], f"notify={alarm['notify']}, tier {alarm['tier']}")
    check("a tier 1 alarm is the only thing allowed to offer a resolution",
          alarm.get("suggest_resolution") is True, f"suggest_resolution={alarm.get('suggest_resolution')}")
    print(f"         reason given to the controller: {alarm['reason']}")

    if multipath_output is not None:
        probabilities, positions = multipath_output
        horizons = [60, 180, 300, 600]
        paths_a = [(float(probabilities[0, k]),
                    {horizons[h]: tuple(positions[0, k, h]) for h in range(4)})
                   for k in range(positions.shape[1])]
        paths_b = [(float(probabilities[1, k]),
                    {horizons[h]: tuple(positions[1, k, h]) for h in range(4)})
                   for k in range(positions.shape[1])]
        multi = compute_cpa_from_paths(paths_a, paths_b)
        check("multi-path CPA returns a real probability, not the 1.0/0.0 placeholder",
              "conflict_probability" in multi,
              f"probability {multi.get('conflict_probability', float('nan')):.3f} "
              f"over {positions.shape[1]}x{positions.shape[1]} path combinations")
        check("the multi-path result drops into classify_conflict unchanged",
              {"is_conflict", "severity"}.issubset(classify_conflict(multi)))


def verify_resolution_engine() -> None:
    section("7. MODEL 3 -- the rule-based resolution engine")
    from ml_pipeline.utils.cpa_conflict_detection import compute_cpa_from_states, escalate_pair
    from ml_pipeline.utils import resolution_engine as engine

    total = (engine.WEIGHT_SAFETY + engine.WEIGHT_DELAY + engine.WEIGHT_FUEL
             + engine.WEIGHT_WORKLOAD + engine.WEIGHT_CONFIDENCE)
    check("the ranking weights sum to 1.0, as Section 3 specifies",
          abs(total - 1.0) < 1e-9, f"safety {engine.WEIGHT_SAFETY}, delay {engine.WEIGHT_DELAY}, "
          f"fuel {engine.WEIGHT_FUEL}, workload {engine.WEIGHT_WORKLOAD}, "
          f"confidence {engine.WEIGHT_CONFIDENCE}")
    check("the response delay is the documented 38 s",
          abs(engine.RESPONSE_DELAY_SECONDS - 38.0) < 1e-9,
          f"{engine.RESPONSE_DELAY_SECONDS:.0f} s before the aircraft moves")

    # Nothing may happen before the response delay elapses. If a manoeuvred aircraft
    # has moved at 30 s, the simulation is pretending the pilot reacted instantly and
    # every option would look better than it is.
    state = {"latitude": 19.0, "longitude": 72.0, "altitude_m": 10668.0,
             "velocity_ms": 230.0, "heading_deg": 90.0, "vertical_rate_ms": 0.0}
    turn = engine.Manoeuvre("A", "heading", 45.0, "deg")
    times = [30, 300]
    straight = engine.simulate_manoeuvre(state, None, times)
    turned = engine.simulate_manoeuvre(state, turn, times)
    check("nothing moves during the 38 s response delay",
          max(abs(a - b) for a, b in zip(straight[30], turned[30])) < 1e-9,
          "position at 30 s is identical with and without the instruction")
    check("the aircraft has diverged by the end of the window",
          max(abs(a - b) for a, b in zip(straight[300], turned[300])) > 1e-4,
          "the manoeuvre does take effect after the delay")

    def head_on(seconds_to_cpa: float):
        import math as _math
        speed = 230.0
        offset = (speed * 2 * seconds_to_cpa) / (engine.METRES_PER_DEGREE * _math.cos(_math.radians(19.0)))
        first = {"latitude": 19.000, "longitude": 72.0, "altitude_m": 10668.0,
                 "velocity_ms": speed, "heading_deg": 90.0, "vertical_rate_ms": 0.0}
        second = {"latitude": 19.003, "longitude": 72.0 + offset, "altitude_m": 10668.0,
                  "velocity_ms": speed, "heading_deg": 270.0, "vertical_rate_ms": 0.0}
        return first, second

    def escalated(pair):
        cpa = compute_cpa_from_states(*pair)
        history: list = []
        outcome = escalate_pair(cpa, history)
        for _ in range(2):
            history.append(cpa)
            outcome = escalate_pair(cpa, history)
        return cpa, outcome

    # Tier 1: a real conflict with time to act must produce ranked, explained options.
    pair = head_on(170.0)
    cpa, escalation = escalated(pair)
    check("a confirmed tier 1 alarm is allowed a resolution",
          escalation["suggest_resolution"], f"tier {escalation['tier']}")
    result = engine.generate_resolutions(*pair, cpa, escalation, "AI2841", "6E455")
    check("options are produced for a tier 1 conflict",
          result["offered"] and bool(result["options"]), f"{len(result['options'])} options")
    check("options are ranked best first",
          all(a.score >= b.score for a, b in zip(result["options"], result["options"][1:])))
    check("every option carries a controller-readable explanation",
          all(len(option.explanation.strip()) > 40 for option in result["options"]))
    check("every option reports its resulting separation, cost and confidence",
          all(option.resulting_lateral_nm == option.resulting_lateral_nm
              and option.delay_seconds == option.delay_seconds
              and 0.0 <= option.confidence <= 1.0 for option in result["options"])) 
    check("every offered option actually restores legal separation",
          all(option.resolves for option in result["options"]))
    check("no blocked or unsafe manoeuvre is ever offered",
          all(option.blocked_reason is None for option in result["options"]))
    check("options are one per manoeuvre type, so the controller gets a real choice",
          len({option.manoeuvre.kind for option in result["options"]}) == len(result["options"]),
          f"types offered: {[option.manoeuvre.kind for option in result['options']]}")
    best = result["options"][0]
    print(f"         top option: {best.explanation[:96]}...")

    # Tier 2 is a watch list and must never be given a manoeuvre.
    pair2 = head_on(300.0)
    cpa2, escalation2 = escalated(pair2)
    result2 = engine.generate_resolutions(*pair2, cpa2, escalation2, "AI2841", "6E455")
    check("a tier 2 advisory is never offered a manoeuvre",
          not result2["offered"] and not result2["options"],
          f"tier {escalation2['tier']}, suggest_resolution {escalation2['suggest_resolution']}")

    # Too late to act: every option must be rejected rather than something unusable offered.
    pair3 = head_on(90.0)
    cpa3, escalation3 = escalated(pair3)
    result3 = engine.generate_resolutions(*pair3, cpa3, escalation3, "AI2841", "6E455")
    check("when no manoeuvre can work in time, none is offered",
          not result3["options"] and result3["counts"]["rejected_ineffective"] > 0,
          f"all {result3['counts']['evaluated']} candidates rejected at 90 s to run")
    check("the engine explains why each rejected option failed",
          all(len(option.explanation.strip()) > 40 for option in result3["rejected"]))

    # The safety envelope must actually block things, not just be declared.
    low = {"latitude": 19.0, "longitude": 72.0, "altitude_m": 10_500.0 / engine.METRES_TO_FEET,
           "velocity_ms": 230.0, "heading_deg": 90.0, "vertical_rate_ms": 0.0}
    descend = engine.Manoeuvre("A", "altitude", -2000.0, "ft")
    blocked_option = engine.evaluate_manoeuvre(
        descend, dict(low) | {"callsign": "A"}, dict(low) | {"callsign": "B"}, 200.0, list(range(0, 601, 15))
    )
    check("a descent below the en-route floor is blocked, not offered",
          blocked_option.blocked_reason is not None and not blocked_option.is_offerable,
          str(blocked_option.blocked_reason))


def verify_inference_bridge() -> None:
    """The backend bridge must run the WHOLE chain, ending in what to do about it.

    This section exists because the bridge and Model 3 were written on separate
    branches and the bridge shipped without ever calling the engine. Nothing crashed;
    it simply stopped at "there is a conflict". That is the kind of gap only a check
    that looks at the output can catch.
    """
    section("8. BACKEND BRIDGE -- the whole chain, alert through to suggestions")
    import math as _math
    try:
        from server.app.ml.inference import ConflictEngine
    except Exception as error:  # noqa: BLE001
        check("inference bridge imports", False, str(error))
        return
    check("inference bridge imports", True)

    engine = ConflictEngine.load()

    def steady_history(latitude, longitude, altitude_m, speed, heading, callsign):
        states = []
        for index in range(10, -1, -1):
            back = speed * 10 * index
            states.append({
                "latitude": latitude - (back * _math.cos(_math.radians(heading))) / 111320.0,
                "longitude": longitude - (back * _math.sin(_math.radians(heading)))
                             / (111320.0 * _math.cos(_math.radians(latitude))),
                "altitude_m": altitude_m, "velocity_ms": speed, "heading_deg": heading,
                "vertical_rate_ms": 0.0, "time_position": 1787600000 - index * 10,
                "callsign": callsign,
            })
        return states

    def assess(seconds_to_cpa):
        speed = 230.0
        offset = (speed * 2 * seconds_to_cpa) / (111320.0 * _math.cos(_math.radians(19.0)))
        a = steady_history(19.000, 72.0, 10668.0, speed, 90.0, "AI2841")
        b = steady_history(19.003, 72.0 + offset, 10668.0, speed, 270.0, "6E455")
        history: list = []
        for _ in range(4):
            outcome = engine.assess_pair(a, b, history)
            history.append(outcome)
        return outcome

    alarm = assess(165.0)
    check("a result always carries a resolution section",
          "resolution" in alarm, f"keys: {sorted(k for k in alarm if not k.startswith('_'))}")
    check("a confirmed tier 1 alarm is offered resolutions",
          alarm["resolution"]["offered"], alarm["resolution"]["reason"][:60])
    options = alarm["resolution"]["options"]
    check("options come back as ranked, explained, plain data",
          bool(options) and all(isinstance(o, dict) and len(o["explanation"]) > 40 for o in options)
          and all(a["score"] >= b["score"] for a, b in zip(options, options[1:])),
          f"{len(options)} options, best: {options[0]['manoeuvre_type'] if options else 'none'}")
    check("Model 3 is named among the sources for that result",
          any("resolution engine" in source for source in alarm["sources"]),
          f"{len(alarm['sources'])} sources")

    advisory = assess(300.0)
    check("a tier 2 advisory is still refused a manoeuvre through the bridge",
          not advisory["resolution"]["offered"] and not advisory["resolution"]["options"],
          f"tier {advisory['escalation']['tier']}")

    too_late = assess(60.0)
    check("when nothing can work in time the bridge says so rather than inventing one",
          not too_late["resolution"]["offered"] and bool(too_late["resolution"]["reason"]),
          too_late["resolution"]["reason"][:60])


def verify_resolution_against_traffic() -> None:
    """Model 3 must consider the other aircraft's PREDICTED paths, and the whole picture.

    Two behaviours, both added 7 Sep, both of which fail silently if they regress:

      1. The aircraft that is NOT moving is checked as several weighted predicted
         futures rather than one straight line. Flying it straight is measurably wrong
         at the far end of a tier 1 alarm.
      2. A manoeuvre is checked against every OTHER aircraft nearby and rejected if it
         would create a new conflict. Without this the engine resolves one pair by
         breaking another, which the literature calls the domino effect and which level
         changes cause most often.

    The scenario is built so the second one MUST fire: two aircraft head-on at FL350,
    and a third 2000 ft below flying the opposite way to one of them. Descending that
    aircraft solves the first conflict and creates a head-on at the lower level.
    """
    section("9. MODEL 3 AGAINST PREDICTED PATHS AND SURROUNDING TRAFFIC")
    import math as _math
    from server.app.ml.inference import ConflictEngine
    from ml_pipeline.utils.cpa_conflict_detection import compute_cpa_from_states, escalate_pair
    from ml_pipeline.utils import resolution_engine as engine_module

    engine = ConflictEngine.load()
    metres_per_degree = 111320.0

    def steady(latitude, longitude, altitude_m, speed, heading, callsign):
        return [{"latitude": latitude - (speed * 10 * i * _math.cos(_math.radians(heading))) / metres_per_degree,
                 "longitude": longitude - (speed * 10 * i * _math.sin(_math.radians(heading)))
                              / (metres_per_degree * _math.cos(_math.radians(latitude))),
                 "altitude_m": altitude_m, "velocity_ms": speed, "heading_deg": heading,
                 "vertical_rate_ms": 0.0, "time_position": 1787600000 - i * 10,
                 "callsign": callsign}
                for i in range(10, -1, -1)]

    speed, seconds = 230.0, 165.0
    offset = (speed * 2 * seconds) / (metres_per_degree * _math.cos(_math.radians(19.0)))
    a = steady(19.000, 72.0, 10668.0, speed, 90.0, "AI2841")
    b = steady(19.003, 72.0 + offset, 10668.0, speed, 270.0, "6E455")
    third = steady(19.000, 72.0 + offset / 2, 10668.0 - 2000.0 / 3.28084, speed, 90.0, "UK955")

    def assess(with_traffic):
        history: list = []
        outcome = None
        for _ in range(4):
            outcome = engine.assess_pair(a, b, history,
                                         traffic=[{"callsign": "UK955", "history": third}]
                                         if with_traffic else ())
            history.append(outcome)
        return outcome

    alone = assess(False)
    check("resolutions are checked against the other aircraft's predicted paths, not one line",
          "predicted paths" in str(alone["resolution"].get("checked_against", "")),
          str(alone["resolution"].get("checked_against")))
    check("each option reports how much predicted-path risk it leaves behind",
          all("residual_risk" in option for option in alone["resolution"]["options"]),
          f"{len(alone['resolution']['options'])} options")

    with_third = assess(True)
    check("the surrounding traffic is named in what the check covered",
          "other aircraft nearby" in str(with_third["resolution"].get("checked_against", "")),
          str(with_third["resolution"].get("checked_against")))
    rejected = with_third["resolution"].get("rejected_new_conflict", 0)
    check("a manoeuvre that would hit a third aircraft is rejected",
          rejected > 0, f"{rejected} rejected for causing a new conflict")
    detail = with_third["resolution"].get("new_conflict_detail", [])
    check("the rejection names the aircraft it would have endangered",
          bool(detail) and detail[0].get("would_conflict_with") == "UK955",
          str(detail[0]) if detail else "no detail recorded")
    check("nothing offered would create a new conflict",
          all(option["new_conflict_risk"] <= engine_module.RESIDUAL_RISK_LIMIT
              for option in with_third["resolution"]["options"]),
          f"{len(with_third['resolution']['options'])} options offered")
    check("adding the third aircraft never ADDS options, it only removes them",
          len(with_third["resolution"]["options"]) <= len(alone["resolution"]["options"]),
          f"{len(alone['resolution']['options'])} without it, "
          f"{len(with_third['resolution']['options'])} with it")


def main() -> int:
    print("FLIGHT RIGHT -- END-TO-END PIPELINE VERIFICATION")
    print("Checks that every stage runs and returns output of the right shape and magnitude.")
    print("It does NOT judge model quality; that is evaluate.py and the training scripts.")

    splits = verify_trajectory_data()
    if splits is None:
        print("\nTrajectory data is missing. Run preprocess_sequences.py first.")
        return 1
    verify_framing(splits)
    verify_trajectory_model(splits)
    multipath_output = verify_multipath(splits)
    verify_conflict_classifier()
    verify_end_to_end(splits, multipath_output)
    verify_resolution_engine()
    verify_inference_bridge()
    verify_resolution_against_traffic()

    section("SUMMARY")
    failed = [name for name, passed, _ in results if not passed]
    print(f"  {len(results) - len(failed)} of {len(results)} checks passed.")
    if failed:
        print("")
        print("  FAILED:")
        for name in failed:
            print(f"    - {name}")
        return 1
    print("  Every stage of the pipeline runs and produces output of the expected shape.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
