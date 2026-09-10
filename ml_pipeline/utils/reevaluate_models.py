"""Re-score every saved model on the held-out test data, WITHOUT retraining anything.

    python ml_pipeline/utils/reevaluate_models.py

Loads each artifact from server/app/ml/saved_models/ in a fresh process and measures it
again, then writes ml_pipeline/reports/reevaluation_<stamp>.json. Nothing here fits a
model, moves a threshold or writes a model file: it answers "do the numbers in
evaluation.md still describe the artifacts on disk?", which is a different question from
"what happens if we retrain?" -- that is run_pipeline.py.

Five sections, in the order evaluation.md reports them:

  1  Model 1   trajectory LSTM and the constant-velocity baseline, per horizon and per
               flight regime. Refreshes eval_*.csv in ml_pipeline/data/processed/.
  2  Model 1b  multi-path best-of-K and calibration, from the saved pickle.
  3  Model 2   conflict classifier: recall, precision, F-beta(2), PR-AUC, the headline
               three-minute-warning metric, and the same model scored at the rule's
               exact false-alarm cost so recall cannot be bought with alarms.
  4  Model 3   every tier 1 alarm on the test split run through the resolution engine.
  5  Feed      two recorded OpenSky sessions replayed with and without the alert feed.

The tree reference (reference_benchmark.py) refits 12 small models and so stays in its
own script; run that separately to refresh those columns.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

SAVED = ROOT / "server/app/ml/saved_models"
FT_M, NM_M = 0.3048, 1852.0


def banner(text: str) -> None:
    print("\n" + "=" * 88 + "\n" + text + "\n" + "=" * 88)


# =====================================================================  1. Model 1
def model1() -> dict:
    banner("MODEL 1 -- trajectory prediction, saved LSTM vs the constant-velocity baseline")
    import torch
    import evaluate                       # noqa
    import train_trajectory as tt         # noqa

    test_x, test_y, test_mask = tt.load_split("test")
    print(f"test split: {len(test_x):,} samples, valid per horizon "
          f"{'/'.join(str(int(c)) for c in test_mask.sum(axis=0))}")

    checkpoint = torch.load(tt.MODEL_PATH, map_location="cpu", weights_only=False)
    feature_statistics = {k: np.asarray(v, dtype=np.float64)
                          for k, v in checkpoint["feature_normalization"].items()}
    residual_statistics = {k: np.asarray(v, dtype=np.float64)
                           for k, v in checkpoint["residual_normalization"].items()}
    model = tt.ResidualTrajectoryModel()
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    tensors = tt.prepare(test_x, test_y, test_mask, feature_statistics, residual_statistics)
    predictions = tt.predict_absolute(model, tensors[0], tensors[1], test_x, tensors[4],
                                      residual_statistics, torch.device("cpu"))

    # The baseline is measured on identical data in the same run. Non-negotiable.
    evaluate.write_results(evaluate.evaluate(tensors[4], test_y, test_mask, test_x,
                                             "constant velocity"))
    results, baseline, passed = evaluate.compare(predictions, tensors[4], test_y, test_mask,
                                                 test_x, "residual LSTM", "constant velocity")
    evaluate.print_report(results)
    evaluate.write_results(results)
    print("\nGATE (LSTM beats constant velocity at every horizon on <5 NM): "
          + ("PASS" if passed else "FAIL"))
    return {"samples": int(len(test_x)), "gate_beats_constant_velocity": bool(passed),
            "training_summary": checkpoint.get("training_summary", {}),
            "per_horizon": results["per_horizon"],
            "baseline_per_horizon": baseline["per_horizon"],
            "per_bucket": results["per_bucket"]}


# ====================================================================  2. Model 1b
def model1b() -> dict:
    banner("MODEL 1b -- multi-path, best-of-K and calibration, from the saved pickle")
    import pickle
    import framing                        # noqa
    import multipath as mp                # noqa

    test_x, test_y, test_mask = mp.load_split("test")
    bundle = pickle.loads((SAVED / "trajectory_multipath.pkl").read_bytes())
    kmeans, classifier = bundle["kmeans"], bundle["classifier"]
    pattern_residuals = bundle["pattern_residuals"]
    temperature = float(bundle.get("temperature", 1.0))

    valid = test_mask[:, mp.TEN_MINUTE_INDEX]
    arrivals = mp.arrival_rows(test_x) & valid
    print(f"temperature {temperature:.3f}; test rows with a ten-minute target "
          f"{int(valid.sum()):,}, of which arrivals {int(arrivals.sum()):,}")

    max_k = 10
    _, _, patterns, raw_before = mp.candidate_paths(classifier, kmeans, pattern_residuals,
                                                    test_x, max_k, temperature=1.0)
    _, positions, patterns_after, raw_after = mp.candidate_paths(
        classifier, kmeans, pattern_residuals, test_x, max_k, temperature=temperature)
    assert np.array_equal(patterns, patterns_after), "temperature must not change the ranking"

    cv = framing.constant_velocity_predict(test_x)

    def within(candidate, rows):
        error = framing.error_nm(candidate, test_y)[rows, mp.TEN_MINUTE_INDEX]
        return float((error < mp.WITHIN_NM).mean() * 100)

    table = [{"method": "Constant velocity", "arrivals": round(within(cv, arrivals), 1),
              "all": round(within(cv, valid), 1)},
             {"method": "Single-answer LSTM",
              "arrivals": round(mp.single_answer_within(test_x, test_y, arrivals), 1),
              "all": round(mp.single_answer_within(test_x, test_y, valid), 1)}]
    for k in (1, 3, 5, 10):
        table.append({"method": f"Multi-path, {k} option{'s' if k > 1 else ''}",
                      "arrivals": round(mp.best_of_k_within(positions, test_y, arrivals, k), 1),
                      "all": round(mp.best_of_k_within(positions, test_y, valid, k), 1)})
    print(f"\n  {'method':<34} {'arrivals':>10} {'all test':>10}")
    for row in table:
        print(f"  {row['method']:<34} {row['arrivals']:>9.1f}% {row['all']:>9.1f}%")

    residual = framing.residual_targets(test_x, test_y, cv)
    true_labels = np.full(len(test_x), -1, dtype=np.int64)
    true_labels[valid] = kmeans.predict(
        residual[valid][:, mp.TEN_MINUTE_INDEX, :2] / framing.METRES_PER_NAUTICAL_MILE)

    ece = {}
    for name, rows in (("arrivals", arrivals), ("all", valid)):
        ece[name] = [
            round(mp.print_reliability(raw_before, patterns, true_labels, rows,
                                       "BEFORE calibration -- " + name), 3),
            round(mp.print_reliability(raw_after, patterns, true_labels, rows,
                                       "AFTER temperature scaling -- " + name), 3)]

    def bands(stated, correct):
        edges = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.01]
        rows = []
        for lower, upper in zip(edges, edges[1:]):
            inside = (stated >= lower) & (stated < upper)
            if inside.sum() >= 20:
                rows.append([round(float(stated[inside].mean()), 3),
                             round(float(correct[inside].mean()), 3), int(inside.sum())])
        return rows

    correct = (patterns[arrivals] == true_labels[arrivals][:, None]).ravel().astype(float)
    return {"temperature": temperature, "best_of_k": table,
            "ece_arrivals": ece["arrivals"], "ece_all": ece["all"],
            "reliability_before": bands(raw_before[arrivals].ravel(), correct),
            "reliability_after": bands(raw_after[arrivals].ravel(), correct)}


# =====================================================================  3. Model 2
def model2() -> dict:
    banner("MODEL 2 -- conflict classifier, saved model re-scored on the held-out test split")
    import xgboost
    from sklearn.metrics import average_precision_score, brier_score_loss
    from train_xgboost import (latest_dataset_path, split_by_session, metrics_at_threshold,
                               metrics_from_predictions, rule_predictions, headline_metric,
                               assert_no_leakage, expected_calibration_error, TARGET_RECALL)
    from generate_synthetic_scenarios import FEATURE_COLUMNS
    from ml_pipeline.utils.cpa_conflict_detection import (
        ALERT_LATERAL_NM, ALERT_VERTICAL_FT, SEPARATION_LATERAL_NM, SEPARATION_VERTICAL_FT)

    card = json.loads((SAVED / "xgboost_conflict_model_card.json").read_text())
    threshold = card["decision_threshold"]
    data = pd.read_parquet(latest_dataset_path())
    print(f"dataset {latest_dataset_path().name}: {len(data):,} rows, "
          f"{int(data['is_conflict'].sum()):,} conflicts ({data['is_conflict'].mean():.2%})")
    leakage = assert_no_leakage(data)
    test = split_by_session(data)["test"].reset_index(drop=True)
    y = test["is_conflict"].to_numpy()
    print(f"test: {len(test):,} rows, {int(y.sum())} conflicts, "
          f"{test['session_id'].nunique()} sessions")

    booster = xgboost.Booster()
    booster.load_model(str(SAVED / "xgboost_conflict.json"))
    raw = booster.predict(xgboost.DMatrix(test[FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS))
    alerts = (raw >= threshold).astype(int)

    out = {"dataset": latest_dataset_path().name, "leakage_reproducibility": leakage,
           "threshold": threshold, "pr_auc": float(average_precision_score(y, raw)),
           "test": metrics_at_threshold(y, raw, threshold)}
    rate, caught, total = headline_metric(test, alerts)
    out["test"]["headline"] = {"rate": rate, "caught": caught, "total": total}
    for name, lateral, vertical in (("rule_alert_volume", ALERT_LATERAL_NM, ALERT_VERTICAL_FT),
                                    ("rule_legal_minimum", SEPARATION_LATERAL_NM,
                                     SEPARATION_VERTICAL_FT)):
        predicted = rule_predictions(test, lateral, vertical)
        out[name] = metrics_from_predictions(y, predicted)
        rate, caught, total = headline_metric(test, predicted)
        out[name]["headline"] = {"rate": rate, "caught": caught, "total": total}

    def platt(p, a, b):
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return 1.0 / (1.0 + np.exp(-(a * np.log(p / (1 - p)) + b)))

    calibrated = platt(raw, card["platt"]["a"], card["platt"]["b"])
    out["calibration"] = {
        "raw": {"brier": float(brier_score_loss(y, raw)),
                "ece": float(expected_calibration_error(raw, y))},
        "platt": {"brier": float(brier_score_loss(y, calibrated)),
                  "ece": float(expected_calibration_error(calibrated, y))},
        "alerts": int(alerts.sum()),
        # Calibration must move what the number MEANS, never who is alerted.
        "alert_set_identical": bool(np.array_equal(
            alerts, (calibrated >= card["calibrated_decision_threshold"]).astype(int)))}

    warning = test.loc[(alerts == 1) & (y == 1), "actual_time_to_cpa_seconds"].astype(float)
    out["warning_seconds"] = {"n": int(len(warning)), "min": float(warning.min()),
                              "p10": float(warning.quantile(0.10)),
                              "median": float(warning.median()),
                              "p90": float(warning.quantile(0.90)), "max": float(warning.max())}
    out["gates"] = {"gate_1_recall_floor": bool(out["test"]["recall"] >= TARGET_RECALL),
                    "gate_2_beats_rule": bool(out["test"]["fbeta_2"]
                                              > out["rule_alert_volume"]["fbeta_2"])}

    # Recall is easy to buy with false alarms, so score the model at the rule's exact cost.
    target = out["rule_alert_volume"]["false_alarms_per_1000"]
    matched = None
    for value in np.unique(np.round(raw, 5)):
        candidate = metrics_at_threshold(y, raw, float(value))
        if candidate["false_alarms_per_1000"] <= target:
            matched = candidate
            break
    if matched:
        rate, caught, total = headline_metric(test, (raw >= matched["threshold"]).astype(int))
        matched["headline"] = {"rate": rate, "caught": caught, "total": total}
    out["at_rule_false_alarm_cost"] = matched

    # What the rule gets wrong, which is what there is for the model to learn.
    rule = rule_predictions(test, ALERT_LATERAL_NM, ALERT_VERTICAL_FT)
    missed = test[(y == 1) & (rule == 0)]
    lateral_ok = missed[missed["predicted_cpa_lateral_nm"] < ALERT_LATERAL_NM]
    fastest_missed = np.maximum(missed["a_abs_vertical_rate_ms"], missed["b_abs_vertical_rate_ms"])
    fastest_all = np.maximum(test["a_abs_vertical_rate_ms"], test["b_abs_vertical_rate_ms"])
    out["rule_misses"] = {
        "n": int(len(missed)), "vertical_only": int(len(lateral_ok)),
        "median_predicted_vertical_ft": float(lateral_ok["predicted_cpa_vertical_ft"].median()),
        "median_actual_vertical_ft": float(lateral_ok["actual_cpa_vertical_ft"].median()),
        "climbing_share_missed": float((fastest_missed > 2.5).mean()),
        "climbing_share_all": float((fastest_all > 2.5).mean()),
        "caught_by_model": int((alerts[(y == 1) & (rule == 0)] == 1).sum()),
        "model_misses_caught_by_rule": int((rule[(y == 1) & (alerts == 0)] == 1).sum())}
    print(json.dumps({key: out[key] for key in
                      ("test", "rule_alert_volume", "rule_legal_minimum",
                       "at_rule_false_alarm_cost", "gates", "rule_misses")},
                     indent=2, default=float))
    return out


# =====================================================================  4. Model 3
def _move(latitude, longitude, bearing_deg, metres):
    bearing = math.radians(bearing_deg)
    return (latitude + metres * math.cos(bearing) / 111_320.0,
            longitude + metres * math.sin(bearing) / (111_320.0 * math.cos(math.radians(latitude))))


def _reconstruct(row):
    """Two aircraft states whose constant-velocity CPA reproduces this row's own features.

    The encounter dataset stores derived pair features, not raw states, so the geometry
    has to be rebuilt before the engine can be run on it: A flies east from a fixed point
    at its recorded speed and altitude, and B is placed and oriented so that the closest
    approach lands at the row's predicted distance, vertical gap and time. This is our
    own construction, not taken from any paper; model3() checks each rebuilt geometry
    against the row it came from and reports the median disagreement.
    """
    seconds = max(float(row["predicted_time_to_cpa_seconds"]), 1.0)
    speed_a, speed_b = float(row["a_velocity_ms"]), float(row["b_velocity_ms"])
    heading_a = 90.0
    heading_b = (90.0 + float(row["relative_heading_deg"])) % 360.0
    altitude_a = float(row["a_altitude_ft"]) * FT_M
    gap_now = float(row["current_vertical_separation_ft"])
    gap_at_cpa = float(row["predicted_cpa_vertical_ft"])
    latitude_c, longitude_c = _move(19.0, 72.87, heading_a, speed_a * seconds)
    latitude_m, longitude_m = _move(latitude_c, longitude_c, (heading_a + 90.0) % 360.0,
                                    float(row["predicted_cpa_lateral_nm"]) * NM_M)
    latitude_b, longitude_b = _move(latitude_m, longitude_m, (heading_b + 180.0) % 360.0,
                                    speed_b * seconds)
    return ({"latitude": 19.0, "longitude": 72.87, "altitude_m": altitude_a,
             "velocity_ms": speed_a, "heading_deg": heading_a, "vertical_rate_ms": 0.0},
            {"latitude": latitude_b, "longitude": longitude_b,
             "altitude_m": altitude_a + gap_now * FT_M, "velocity_ms": speed_b,
             "heading_deg": heading_b,
             "vertical_rate_ms": (gap_at_cpa - gap_now) * FT_M / seconds})


def model3() -> dict:
    banner("MODEL 3 -- resolution engine over every tier 1 alarm on the test split")
    import xgboost
    from train_xgboost import latest_dataset_path, split_by_session
    from generate_synthetic_scenarios import FEATURE_COLUMNS
    from ml_pipeline.utils.cpa_conflict_detection import (compute_cpa_from_states,
                                                          TIER_1_MAX_SECONDS)
    from ml_pipeline.utils.resolution_engine import generate_resolutions

    card = json.loads((SAVED / "xgboost_conflict_model_card.json").read_text())
    test = split_by_session(pd.read_parquet(latest_dataset_path()))["test"].reset_index(drop=True)
    booster = xgboost.Booster()
    booster.load_model(str(SAVED / "xgboost_conflict.json"))
    raw = booster.predict(xgboost.DMatrix(test[FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS))
    alarms = test[(raw >= card["decision_threshold"])
                  & (test["predicted_time_to_cpa_seconds"] <= TIER_1_MAX_SECONDS)]
    print(f"tier 1 alarms: {len(alarms)} ({int(alarms['is_conflict'].sum())} real, "
          f"{int((alarms['is_conflict'] == 0).sum())} false)")

    totals, kinds = Counter(), Counter()
    offered_real = offered_false = with_options = nothing = 0
    buckets = {"0-60 s": [0, 0], "60-120 s": [0, 0], "120-180 s": [0, 0]}
    drift = []
    for _, row in alarms.iterrows():
        state_a, state_b = _reconstruct(row)
        cpa = compute_cpa_from_states(state_a, state_b)
        drift.append(abs(float(cpa["cpa_lateral_distance_nm"])
                         - float(row["predicted_cpa_lateral_nm"])))
        result = generate_resolutions(state_a, state_b, cpa, callsign_a="A", callsign_b="B")
        totals.update(result["counts"])
        count = len(result["options"])
        totals["offered"] += count
        for option in result["options"]:
            kinds[option.manoeuvre.kind] += 1
        with_options += bool(count)
        nothing += (not count)
        if row["is_conflict"] == 1:
            offered_real += count
        else:
            offered_false += count
        seconds = float(row["predicted_time_to_cpa_seconds"])
        key = "0-60 s" if seconds <= 60 else ("60-120 s" if seconds <= 120 else "120-180 s")
        buckets[key][0] += 1
        buckets[key][1] += count

    print(f"geometry check: median |reconstructed CPA - row CPA| = {np.median(drift):.3f} NM")
    out = {"alarms": int(len(alarms)), "alarms_real": int(alarms["is_conflict"].sum()),
           "alarms_false": int((alarms["is_conflict"] == 0).sum()),
           "candidates_evaluated": totals["evaluated"],
           "blocked_unsafe": totals["blocked_unsafe"],
           "rejected_ineffective": totals["rejected_ineffective"],
           "rejected_domino": totals["rejected_domino"],
           "alarms_with_options": with_options, "alarms_with_nothing": nothing,
           "instructions_offered": totals["offered"], "instructions_for_real": offered_real,
           "instructions_for_false": offered_false, "by_kind": dict(kinds),
           "by_time": [[k, v[0], v[1], round(v[1] / v[0], 2) if v[0] else 0.0]
                       for k, v in buckets.items()],
           "geometry_median_error_nm": float(np.median(drift))}
    print(json.dumps(out, indent=2))
    return out


# ========================================================================  5. Feed
FLOOR_FT, MIN_VELOCITY_MS = 10_000.0, 50.0
PREFILTER_NM, PREFILTER_FT = 60.0, 5_000.0     # server/app/config.py
REPLAY_SESSIONS = [("05 Sep, 00:30 IST", "session_20260905_003006_combined.parquet"),
                   ("03 Sep, 20:45 IST", "session_c_20260903_204503_combined.parquet")]


def _airborne(frame):
    """En-route states only: the same floor the detector uses, per the 30 Aug measurement."""
    states = {}
    for row in frame.itertuples():
        if row.on_ground or pd.isna(row.latitude) or pd.isna(row.longitude):
            continue
        if pd.isna(row.baro_altitude) or pd.isna(row.velocity) or pd.isna(row.true_track):
            continue
        if row.baro_altitude / FT_M < FLOOR_FT or row.velocity < MIN_VELOCITY_MS:
            continue
        key = (row.callsign or row.icao24).strip() or row.icao24
        states[key] = {"latitude": float(row.latitude), "longitude": float(row.longitude),
                       "altitude_m": float(row.baro_altitude), "velocity_ms": float(row.velocity),
                       "heading_deg": float(row.true_track),
                       "vertical_rate_ms": (0.0 if pd.isna(row.vertical_rate)
                                            else float(row.vertical_rate))}
    return states


def _why(text: str) -> str:
    lowered = text.lower()
    for needle, label in (("new conflict", "Genuinely new conflict"),
                          ("escalated from tier", "Escalated to a shorter tier"),
                          ("severity rose", "Severity rose"),
                          ("resolution options", "Resolution options changed"),
                          ("no manoeuvre now", "Resolution options changed"),
                          ("now inside", "Crossed into a shorter time band"),
                          ("has closed by", "Closed by more than 1 NM"),
                          ("probability rose", "Probability rose"),
                          ("still active after", "Heartbeat")):
        if needle in lowered:
            return label
    return "other"


def alert_feed_replay() -> list[dict]:
    banner("ALERT FEED -- two recorded sessions replayed with and without repeat suppression")
    from ml_pipeline.utils.alert_feed import AlertFeed
    from ml_pipeline.utils.cpa_conflict_detection import (
        compute_cpa_from_states, classify_conflict, escalate_pair,
        should_drop_from_tracking, haversine_distance_nm)

    results = []
    for label, filename in REPLAY_SESSIONS:
        path = ROOT / "ml_pipeline/data/raw" / filename
        if not path.exists():
            print(f"  skipped {filename} (not present)")
            continue
        data = pd.read_parquet(path)
        # The poll timestamp is the real snapshot boundary; time_position is when each
        # aircraft last reported itself and scatters one snapshot across many frames.
        data["frame"] = (data["fetch_timestamp_utc"].dt.tz_localize(None)
                         .astype("datetime64[s]").astype("int64"))
        frames = sorted(data["frame"].unique())
        feed, histories, reasons = AlertFeed(), defaultdict(list), Counter()
        before = after = active_rows = 0
        pairs_before, pairs_after = set(), set()
        for step, stamp in enumerate(frames):
            current = _airborne(data[data["frame"] == stamp])
            names = sorted(current)
            assessments = {}
            for index, name_a in enumerate(names):
                for name_b in names[index + 1:]:
                    state_a, state_b = current[name_a], current[name_b]
                    if abs(state_a["altitude_m"] - state_b["altitude_m"]) / FT_M >= PREFILTER_FT:
                        continue
                    if haversine_distance_nm(state_a["latitude"], state_a["longitude"],
                                             state_b["latitude"], state_b["longitude"]) >= PREFILTER_NM:
                        continue
                    cpa = compute_cpa_from_states(state_a, state_b)
                    verdict = classify_conflict(cpa)
                    key = (name_a, name_b)
                    escalation = escalate_pair(cpa, histories[key])
                    histories[key].append(cpa)
                    if should_drop_from_tracking(cpa, histories[key]):
                        histories.pop(key, None)
                    if not escalation["notify"]:
                        continue
                    before += 1                   # one message per confirmed pair-update
                    pairs_before.add(key)
                    assessments[key] = {
                        "rule": {**cpa, "is_conflict": bool(verdict["is_conflict"]),
                                 "severity": verdict["severity"]},
                        "classifier": {}, "escalation": escalation,
                        "resolution": {"offered": False, "options": [], "reason": ""}}
            shown = feed.update(assessments, now=float(step * 10))
            after += len(shown["notifications"])
            active_rows += len(shown["active"])
            for note in shown["notifications"]:
                reasons[_why(note.get("notification_reason", ""))] += 1
            for row in shown["active"]:
                pairs_after.add(row.get("pair", row.get("key")))
        entry = {"session": label, "frames": len(frames), "pairs_before": len(pairs_before),
                 "pairs_after": len(pairs_after), "lost": len(pairs_before - pairs_after),
                 "interruptions_before": before, "interruptions_after": after,
                 "active_rows": active_rows,
                 "cut_percent": round(100.0 * (1 - after / before), 1) if before else 0.0,
                 "reasons": dict(reasons.most_common())}
        print(json.dumps(entry))
        results.append(entry)
    return results


def main() -> None:
    report = {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
              "model1": model1(), "model1b": model1b(), "model2": model2(),
              "model3": model3(), "alert_feed": alert_feed_replay()}
    directory = ROOT / "ml_pipeline" / "reports"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = directory / f"reevaluation_{stamp}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    banner(f"Wrote {path}")


if __name__ == "__main__":
    main()
