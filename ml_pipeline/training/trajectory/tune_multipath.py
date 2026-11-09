"""Isolated Model 1b tuning: ten-minute offset regressors; frozen routes/probabilities.

Run with the project venv. Reports are local uncommitted files. No Git commands,
served-model writes, alert-threshold changes or model downloads are performed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import pickle
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "4")
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import classification_report, confusion_matrix, log_loss
from threadpoolctl import threadpool_limits

import evaluate
import framing
import multipath as mp

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import resolve_artifact, register_reference
sys.path.insert(0, str(ROOT / "ml_pipeline/utils"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))
REPORTS = ROOT / "ml_pipeline/reports/multipath_tuning_20261101"
WORK = ROOT / "ml_pipeline/data/processed/multipath_experiments/20261101"
DATA = ROOT / "ml_pipeline/data/processed/archive_row/combined_root/ml_pipeline/data/processed"
SAVED = ROOT / "server/app/ml/saved_models"
TRIALS = [
    {"name": "continue_600", "method": "continue", "max_iter": 600},
    {"name": "continue_800", "method": "continue", "max_iter": 800},
    {"name": "regularized31", "method": "refit", "max_iter": 400, "learning_rate": .06,
     "max_leaf_nodes": 31, "min_samples_leaf": 80, "l2_regularization": 5.0},
]
ERRORS = ("top1_mean_nm", "top1_rmse_nm", "top1_p90_nm", "top1_altitude_mae_ft", "energy_score")
RATES = ("top1_within_1nm", "top1_within_5nm", "best5_within_5nm", "top1_both", "best5_both")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def load(split):
    with np.load(resolve_artifact(DATA / f"trajectory_{split}.npz"), allow_pickle=True) as data:
        return {k: data[k] for k in data.files}


def extras(split, names):
    with np.load(resolve_artifact(DATA / f"context_{split}.npz"), allow_pickle=True) as data:
        return np.column_stack([data[k] for k in names]).astype(np.float64)


def model_features(X, extra):
    return mp._offset_inputs(mp.build_feature_matrix(X), extra)


def energy_score(points, truth, probabilities):
    """Negative orientation of Gneiting/Raftery Eq.22, beta=1; lower is better."""
    first = (probabilities * np.linalg.norm(points - truth[:, None], axis=2)).sum(axis=1)
    second = np.zeros(len(points))
    for a in range(points.shape[1]):
        for b in range(a + 1, points.shape[1]):
            second += probabilities[:, a] * probabilities[:, b] * np.linalg.norm(points[:, a] - points[:, b], axis=1)
    return first - second


def score(positions, X, y, mask, probabilities):
    lateral = np.stack([framing.error_nm(positions[:, k], y) for k in range(5)], axis=1)
    vertical = np.abs(positions[..., 2] - y[:, None, :, 2]) * 3.28084
    cv = framing.constant_velocity_predict(X)
    scale = np.array([5 * 1852., 5 * 1852., 1000 / 3.28084])
    points = np.stack([framing.residual_targets(X, positions[:, k], cv)[:, 3] / scale for k in range(5)], axis=1)
    truth = framing.residual_targets(X, y, cv)[:, 3] / scale
    energy = energy_score(points, truth, probabilities)
    out = {"groups": {}, "top1_per_horizon": evaluate.evaluate(positions[:, 0], y, mask, X, "multi-path top-1"),
           "regimes": []}
    for name, sel in (("all", mask[:, 3]), ("arrivals", mask[:, 3] & mp.arrival_rows(X))):
        lat, ver = lateral[sel, :, 3], vertical[sel, :, 3]
        both = (lat < 5) & (ver < 1000)
        out["groups"][name] = {
            "n": int(sel.sum()), "top1_mean_nm": float(lat[:, 0].mean()),
            "top1_rmse_nm": float(np.sqrt((lat[:, 0] ** 2).mean())),
            "top1_median_nm": float(np.median(lat[:, 0])), "top1_p90_nm": float(np.percentile(lat[:, 0], 90)),
            "top1_altitude_mae_ft": float(ver[:, 0].mean()), "best5_mean_nm": float(lat.min(axis=1).mean()),
            "top1_within_1nm": float((lat[:, 0] < 1).mean() * 100),
            "top1_within_5nm": float((lat[:, 0] < 5).mean() * 100),
            "best5_within_5nm": float((lat < 5).any(axis=1).mean() * 100),
            "top1_within_1000ft": float((ver[:, 0] < 1000).mean() * 100),
            "best5_within_1000ft": float((ver < 1000).any(axis=1).mean() * 100),
            "top1_both": float(both[:, 0].mean() * 100), "best5_both": float(both.any(axis=1).mean() * 100),
            "energy_score": float(energy[sel].mean()),
        }
    for family, (values, buckets) in evaluate.bucket_assignments(X).items():
        for label, low, high in buckets:
            sel = mask[:, 3] & (values >= low) & (values < high)
            if not sel.any():
                continue
            err = lateral[sel, 0, 3]
            out["regimes"].append({"family": family, "name": label, "n": int(sel.sum()),
                                   "mean_nm": float(err.mean()), "within_5nm": float((err < 5).mean() * 100)})
    return out


def compare(candidate, baseline):
    deltas, failures = [], []
    for group in ("all", "arrivals"):
        c, b = candidate["groups"][group], baseline["groups"][group]
        for key in ERRORS:
            deltas.append(c[key] / max(b[key], 1e-8) - 1)
            slack = 1. if key.endswith("_ft") else .01 if key.endswith("_nm") else .001
            if c[key] > b[key] * 1.02 + slack:
                failures.append(f"{group}/{key}: error increased >2% + slack")
        for key in RATES:
            deltas.append((b[key] - c[key]) / 100)
            if c[key] < b[key] - .5:
                failures.append(f"{group}/{key}: rate fell >0.5 pp")
    for c, b in zip(candidate["regimes"], baseline["regimes"]):
        assert (c["family"], c["name"], c["n"]) == (b["family"], b["name"], b["n"])
        if c["n"] >= 100 and (c["mean_nm"] > b["mean_nm"] * 1.05 + .01 or c["within_5nm"] < b["within_5nm"] - 1):
            failures.append(f"regime {c['family']}/{c['name']}: mean error >5% or hit drop >1 pp")
    objective = float(np.mean(deltas))
    return {"objective": objective, "passes_guardrails": not failures,
            "guardrail_failures": failures, "improves_objective": objective < -1e-4}


def prediction(bundle, X, extra, base=None):
    if base is None:
        p, pos, ids, raw = mp.candidate_paths(bundle["classifier"], bundle["kmeans"], bundle["pattern_residuals"], X, 5,
                                              bundle["temperature"], bundle["offset_models"], extra)
        return p, pos, ids, raw
    p, original, ids, raw = base
    positions = original.copy()
    inputs = mp._with_pattern(np.repeat(model_features(X, extra), 5, axis=0), ids.ravel())
    residual = np.zeros((len(inputs), 4, 3))
    for axis in range(3):
        residual[:, 3, axis] = bundle["offset_models"]["models"][(3, axis)].predict(inputs)
    cv = framing.constant_velocity_predict(X)
    for k in range(5):
        positions[:, k, 3] = framing.apply_residual(X, cv, residual.reshape(len(X), 5, 4, 3)[:, k])[:, 3]
    assert np.array_equal(positions[:, :, :3], original[:, :, :3])
    return p, positions, ids, raw


def split_validation(timestamps):
    times = np.unique(timestamps)
    blocks = np.split(times, np.where(np.diff(times) > 1800)[0] + 1)
    mid = len(blocks) // 2
    if mid:
        early, late = timestamps <= blocks[mid - 1][-1], timestamps >= blocks[mid][0]
    else:
        cut = np.median(times)
        early, late = timestamps <= cut - 600, timestamps >= cut + 600
    assert timestamps[early].max() + 600 < timestamps[late].min()
    return early, late


def train(config, seed, source, train_input, train_target, early_input, early_target):
    artifact = WORK / f"{config['name']}_seed{seed}.pkl"
    log_path = REPORTS / f"{config['name']}_seed{seed}_fit.json"
    candidate = copy.deepcopy(source)
    start, diagnostics = time.perf_counter(), {}
    categorical = np.zeros(train_input.shape[1], dtype=bool)
    categorical[-1] = True
    for axis in range(3):
        axis_start = time.perf_counter()
        if config["method"] == "continue":
            assert seed == 0, "Warm start must keep the original random state and same data"
            regressor = copy.deepcopy(source["offset_models"]["models"][(3, axis)])
            regressor.set_params(warm_start=True, max_iter=config["max_iter"])
            regressor.fit(train_input, train_target[:, axis])
        else:
            params = {k: v for k, v in config.items() if k not in ("name", "method")}
            regressor = HistGradientBoostingRegressor(loss="absolute_error", categorical_features=categorical,
                                                       early_stopping=True, random_state=seed, **params)
            regressor.fit(train_input, train_target[:, axis], X_val=early_input, y_val=early_target[:, axis])
        candidate["offset_models"]["models"][(3, axis)] = regressor
        diagnostics[str(axis)] = {"iterations": int(regressor.n_iter_), "seconds": time.perf_counter() - axis_start}
        print(f"{config['name']} seed {seed}: axis {axis} fitted, {regressor.n_iter_} trees, {diagnostics[str(axis)]['seconds']:.1f}s", flush=True)
    candidate["experiment"] = {"config": config, "seed": seed, "source_sha256": sha(SAVED / "trajectory_multipath.pkl"),
                               "changed": "Only ten-minute per-mode offset regressors; classifier/temperature/K/earlier horizons unchanged"}
    artifact.write_bytes(pickle.dumps(candidate, protocol=pickle.HIGHEST_PROTOCOL))
    info = {"config": config, "seed": seed, "artifact": str(artifact.relative_to(ROOT)),
            "sha256": sha(artifact), "fit": diagnostics, "seconds": time.perf_counter() - start}
    write(log_path, info)
    return candidate, info


def alert_audit(path, split, tag):
    path = resolve_artifact(path)
    import alert_prominence as ap
    from destination_row import a_callsigns
    from offsets_ab_test import score as binary_score
    from ml_pipeline.utils.cpa_conflict_detection import (CLASSIFIER_ALERT_KEY, RULE_GEOMETRY_KEY,
                                                         compute_cpa_from_paths, escalate_pair, assign_tier)
    from server.app.ml.inference import MultiPathPredictor
    frame, X, current = ap.inputs(split)
    ap.OUT = WORK / "alert_tables"
    ap.OUT.mkdir(exist_ok=True)
    calls = a_callsigns(frame, current[:len(frame)]) + [None] * len(frame)
    table = ap.table(split, path, tag, callsigns=calls)
    metrics = binary_score(frame, table.y.to_numpy(), table.fired.to_numpy(), table.tier.to_numpy(), table.route.to_numpy())
    metrics["display"] = ap.summary(table)
    # Check the optimized offline gate against the actual escalation function, pair by pair.
    predictor = MultiPathPredictor(path, offsets="per_mode")
    probabilities, positions, _ = predictor.predict(X, extra=predictor.route_inputs(X, calls))
    for i in range(len(frame)):
        rule = {"cpa_lateral_distance_nm": float(frame.predicted_cpa_lateral_nm.iloc[i]),
                "cpa_vertical_separation_ft": float(frame.predicted_cpa_vertical_ft.iloc[i]),
                "time_to_cpa_seconds": float(frame.predicted_time_to_cpa_seconds.iloc[i]), "is_converging": True}
        if assign_tier(rule)["tier"] == 1:
            chosen = rule
        else:
            chosen = {**compute_cpa_from_paths(predictor.paths_for_cpa(X, i, probabilities, positions),
                                                predictor.paths_for_cpa(X, len(frame) + i, probabilities, positions),
                                                tuple(current[i]), tuple(current[len(frame) + i])), RULE_GEOMETRY_KEY: rule}
        chosen[CLASSIFIER_ALERT_KEY] = bool(table.classifier_alert.iloc[i])
        actual = escalate_pair(chosen, [chosen, chosen])
        expected = bool(table.fired.iloc[i])
        assert bool(actual["notify"]) == expected, f"Gate differs on pair {i}"
        if expected:
            assert int(actual["tier"]) == int(table.tier.iloc[i]), f"Tier differs on pair {i}"
    metrics["real_gate_verified_pairs"] = len(frame)
    return metrics


def alert_compare(candidate, baseline):
    failures = []
    if candidate["headline"]["caught"] < baseline["headline"]["caught"]:
        failures.append("three-minute warning count decreased")
    if candidate["true_positive"] < baseline["true_positive"]:
        failures.append("real conflicts detected decreased")
    if candidate["tier_1"]["real"] < baseline["tier_1"]["real"]:
        failures.append("real tier-1 count decreased")
    if candidate["false_positive"] > baseline["false_positive"]:
        failures.append("total false alerts increased")
    if candidate["tier_1"]["false"] > baseline["tier_1"]["false"]:
        failures.append("false tier-1 count increased")
    c, b = candidate["display"], baseline["display"]
    if c["prominent_real_with_3min"] < b["prominent_real_with_3min"]:
        failures.append("prominent real conflicts with three-minute warning decreased")
    if c["collapsed_real"] > b["collapsed_real"]:
        failures.append("more real conflicts collapsed")
    if c["tier1_false"] + c["prominent_false"] > b["tier1_false"] + b["prominent_false"]:
        failures.append("false alarms shown prominently increased")
    return {"passes_guardrails": not failures, "guardrail_failures": failures}


def class_metrics(bundle, X, y, mask):
    residual = framing.residual_targets(X, y, framing.constant_velocity_predict(X))
    valid = mask[:, 3]
    labels = bundle["kmeans"].predict(residual[valid, 3, :2] / 1852.)
    probabilities = mp.pattern_probabilities(bundle["classifier"], mp.build_feature_matrix(X[valid]), bundle["temperature"])
    classes = bundle["classifier"].classes_
    predicted = classes[probabilities.argmax(axis=1)]
    truth_onehot = (labels[:, None] == classes).astype(float)
    return {"samples": int(valid.sum()), "labels": classes.tolist(),
            "classification_report": classification_report(labels, predicted, labels=classes, output_dict=True, zero_division=0),
            "confusion_matrix": confusion_matrix(labels, predicted, labels=classes).tolist(),
            "negative_log_likelihood": float(log_loss(labels, probabilities, labels=classes)),
            "multiclass_brier": float(((probabilities - truth_onehot) ** 2).sum(axis=1).mean()),
            "top1_ece": mp.expected_calibration_error(probabilities.max(axis=1), (predicted == labels).astype(float)),
            "note": "Route-cluster calibration; not calibration of within-distance hits or conflict probabilities. Frozen for every candidate."}


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    if (REPORTS / "summary.json").exists():
        raise RuntimeError("Completed study exists; do not overwrite it")
    hashes = {p.name: sha(p) for p in SAVED.iterdir() if p.suffix in (".pkl", ".pt", ".json")}
    source = pickle.loads((SAVED / "trajectory_multipath.pkl").read_bytes())
    source_path = register_reference(WORK / "baseline_multipath.pkl", SAVED / "trajectory_multipath.pkl")
    shutil.copy2(Path(__file__), REPORTS / "source_snapshot.txt")
    train_data, val = load("train"), load("val")
    early, later = split_validation(val["timestamps"])
    assert train_data["timestamps"].max() + 600 < val["timestamps"].min()
    protocol = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "trials": TRIALS,
                "scope": "Model 1b ten-minute per-mode offsets only; all 40 route patterns, classifier, calibration temperature, top-K=5, destination features, horizons and alert rules frozen",
                "training_windows": len(train_data["X"]), "early_validation_windows": int(early.sum()),
                "selection_validation_windows": int(later.sum()), "selection_seed": 0,
                "validation_partition": "Whole time blocks separated by >1800 s; first two blocks for fresh-model early stopping, last three for ranking. Gap exceeds 600-second horizon.",
                "warm_start_caveat": "Continuation preserves the source's original seed-0 internal random holdout and identical training data, as required by sklearn warm_start. Fresh refits use explicit earlier chronological validation. This legacy internal split is reported, not presented as a new chronological training control.",
                "selection": "Rank by trajectory guards then fixed combined error/coverage objective on later validation only; validation alert-chain veto determines eligible candidate. If none pass, audit the best trajectory candidate as rejected diagnostic, never adopt.",
                "objective": {"relative_error_ratios": ERRORS, "coverage_gap_divided_by_100": RATES, "equal_groups": ["all", "arrivals"]},
                "trajectory_guards": "Errors <= baseline*1.02 + .01 NM or 1 ft or .001 energy; coverage drop <= .5 pp; regimes n>=100: mean error <=+5%+.01 NM and top1 within5 drop <=1 pp. Earlier horizons must be identical.",
                "alert_guards": "No loss in real detections, three-minute catches, real tier1, prominent early real conflicts; no increase in total false alerts, false tier1, collapsed real, or prominent false plus false tier1.",
                "confirmation": "Fresh-refit winner: repeat training seeds 1 and 2. Warm continuation is deterministic from a fixed seed-0 source and cannot claim independent multi-seed replication.",
                "test_policy": "Freeze candidate from validation before opening historical test targets. Later Sep10/Sep20 cohort is shared with prior LSTM studies and is an exploratory audit, never used for ranking.",
                "energy_score": "Lower-is-better beta=1 energy score of normalized top-five mixture in local residual coordinates scaled by 5 NM along/cross and 1000 ft altitude. Scaling is our design. Not the full forty-class distribution or conflict risk.",
                "source_sha256": hashes, "source_code_sha256": sha(Path(__file__)),
                "sources": ["https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html",
                            "https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_early_stopping.html",
                            "https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf"],
                "git_policy": "No commits or pushes without Archit's explicit instruction. Current study is local and uncommitted."}
    write(REPORTS / "protocol.json", protocol)
    names = source["offset_models"]["extra_features"]
    train_extra, val_extra = extras("train", names), extras("val", names)
    train_cv = framing.constant_velocity_predict(train_data["X"])
    train_residual = framing.residual_targets(train_data["X"], train_data["y"], train_cv)
    valid_train = train_data["mask"][:, 3]
    labels = source["kmeans"].predict(train_residual[valid_train, 3, :2] / 1852.)
    train_inputs = mp._with_pattern(model_features(train_data["X"][valid_train], train_extra[valid_train]), labels)
    train_target = train_residual[valid_train, 3]
    early_rows = early & val["mask"][:, 3]
    early_residual = framing.residual_targets(val["X"][early_rows], val["y"][early_rows], framing.constant_velocity_predict(val["X"][early_rows]))
    early_labels = source["kmeans"].predict(early_residual[:, 3, :2] / 1852.)
    early_inputs = mp._with_pattern(model_features(val["X"][early_rows], val_extra[early_rows]), early_labels)
    X, y, mask, extra = val["X"][later], val["y"][later], val["mask"][later], val_extra[later]
    print(f"Training ten-minute rows: {len(train_inputs):,}; chronological early stop: {len(early_inputs):,}; selection: {len(X):,}", flush=True)
    base_prediction = prediction(source, X, extra)
    base_metrics = score(base_prediction[1], X, y, mask, base_prediction[0])
    write(REPORTS / "baseline_selection.json", base_metrics)
    trials = []
    for config in TRIALS:
        candidate, info = train(config, 0, source, train_inputs, train_target, early_inputs, early_residual[:, 3])
        predicted = prediction(candidate, X, extra, base_prediction)
        metrics = score(predicted[1], X, y, mask, predicted[0])
        info.update(validation=metrics, comparison=compare(metrics, base_metrics))
        write(REPORTS / f"{config['name']}_seed0.json", info)
        trials.append(info)
        print(config["name"], info["comparison"], flush=True)
        del candidate
    baseline_val_alert = alert_audit(source_path, "val", "baseline")
    ranked = sorted(trials, key=lambda t: (not t["comparison"]["passes_guardrails"], t["comparison"]["objective"]))
    winner, eligible = ranked[0], False
    for trial in ranked:
        trial["validation_alerts"] = alert_audit(ROOT / trial["artifact"], "val", trial["config"]["name"])
        trial["alert_comparison"] = alert_compare(trial["validation_alerts"], baseline_val_alert)
        if trial["comparison"]["passes_guardrails"] and trial["comparison"]["improves_objective"] and trial["alert_comparison"]["passes_guardrails"]:
            winner, eligible = trial, True
            break
    write(REPORTS / "selection_frozen_before_test.json", {"config": winner["config"], "seed": 0, "eligible": eligible,
                                                          "selected_at_utc": datetime.now(timezone.utc).isoformat()})
    finalists = [winner]
    if winner["config"]["method"] == "refit":
        for seed in (1, 2):
            candidate, info = train(winner["config"], seed, source, train_inputs, train_target, early_inputs, early_residual[:, 3])
            pred = prediction(candidate, X, extra, base_prediction)
            info.update(validation=score(pred[1], X, y, mask, pred[0]))
            info["comparison"] = compare(info["validation"], base_metrics)
            info["validation_alerts"] = alert_audit(ROOT / info["artifact"], "val", f"confirm{seed}")
            info["alert_comparison"] = alert_compare(info["validation_alerts"], baseline_val_alert)
            finalists.append(info)
    test = load("test")
    test_extra = extras("test", names)
    base_test_pred = prediction(source, test["X"], test_extra)
    base_test = score(base_test_pred[1], test["X"], test["y"], test["mask"], base_test_pred[0])
    base_test_alert = alert_audit(source_path, "test", "baseline")
    audits = []
    for info in finalists:
        bundle = pickle.loads(resolve_artifact(ROOT / info["artifact"]).read_bytes())
        pred = prediction(bundle, test["X"], test_extra, base_test_pred)
        metrics = score(pred[1], test["X"], test["y"], test["mask"], pred[0])
        alerts = alert_audit(ROOT / info["artifact"], "test", f"candidate{info['seed']}")
        audits.append({"seed": info["seed"], "metrics": metrics, "comparison": compare(metrics, base_test),
                       "alerts": alerts, "alert_comparison": alert_compare(alerts, base_test_alert)})
        np.savez_compressed(WORK / f"candidate_seed{info['seed']}_test_predictions.npz", positions=pred[1], probabilities=pred[0])
    classes = class_metrics(source, test["X"], test["y"], test["mask"])
    after = {p.name: sha(p) for p in SAVED.iterdir() if p.suffix in (".pkl", ".pt", ".json")}
    assert hashes == after, "Served files changed"
    result = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "protocol": protocol,
              "baseline_selection": base_metrics, "trials": trials, "winner": winner, "validation_eligible": eligible,
              "finalists_validation": finalists, "baseline_validation_alerts": baseline_val_alert,
              "baseline_test": base_test, "baseline_test_alerts": base_test_alert, "test_audits": audits,
              "route_classification": classes, "served_artifacts_unchanged": hashes == after}
    write(REPORTS / "summary.json", result)
    print("Completed multi-path study; eligible from validation:", eligible, flush=True)
    print("Winner:", winner["config"], flush=True)
    for audit in audits:
        print("Test", audit["seed"], audit["comparison"], audit["alert_comparison"], flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()
