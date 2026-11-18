"""Isolated trajectory LSTM fine-tuning; validation selects, test only audits the finalist.

python ml_pipeline/training/trajectory/tune_trajectory.py --epochs 6
Models/predictions go under gitignored processed data. Reports and the predeclared
protocol go under reports/trajectory_tuning_20261101. No served artifact is written.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

import evaluate
import framing
import train_trajectory as tt

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import register_reference, resolve_artifact, FUTURE_COHORT, FUTURE_BASELINE, save_shared_array
REPORTS = ROOT / "ml_pipeline/reports/trajectory_tuning_20261101"
WORK = ROOT / "ml_pipeline/data/processed/trajectory_experiments/20261101"
SAVED = ROOT / "server/app/ml/saved_models"
TRIALS = [
    {"name": "adam_lr1e4", "optimizer": "adam", "lr": 1e-4, "weight_decay": 0.0, "heads_only": False},
    {"name": "adamw_lr1e4_wd1e3", "optimizer": "adamw", "lr": 1e-4, "weight_decay": 1e-3, "heads_only": False},
    {"name": "adamw_lr3e4_wd1e2", "optimizer": "adamw", "lr": 3e-4, "weight_decay": 1e-2, "heads_only": False},
    {"name": "heads_adamw_lr3e4", "optimizer": "adamw", "lr": 3e-4, "weight_decay": 1e-3, "heads_only": True},
]
REFINEMENT_TRIALS = [
    {"name": "adam_lr3e5", "optimizer": "adam", "lr": 3e-5, "weight_decay": 0., "heads_only": False},
    {"name": "averaged_adam_lr1e4", "optimizer": "adam", "lr": 1e-4, "weight_decay": 0., "heads_only": False, "average_checkpoints": True},
    {"name": "averaged_adam_lr3e5", "optimizer": "adam", "lr": 3e-5, "weight_decay": 0., "heads_only": False, "average_checkpoints": True},
]
HORIZON_HEAD_TRIALS = [
    {"name": "last_head_adam_lr1e4", "optimizer": "adam", "lr": 1e-4, "weight_decay": 0., "heads_only": False, "last_head_only": True},
    {"name": "last_head_adam_lr3e4", "optimizer": "adam", "lr": 3e-4, "weight_decay": 0., "heads_only": False, "last_head_only": True},
    {"name": "last_head_adam_lr1e3", "optimizer": "adam", "lr": 1e-3, "weight_decay": 0., "heads_only": False, "last_head_only": True},
]
ERROR_KEYS = ("mean_nm", "rmse_nm", "median_nm", "p90_nm", "altitude_mae_ft", "cross_mae_nm")
RATE_KEYS = ("within_1_nm", "within_5_nm", "within_3d")


def write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_predictions(predictions, X, y, mask, label):
    result = evaluate.evaluate(predictions, y, mask, X, label)
    horizontal = framing.error_nm(predictions, y)
    vertical = np.abs(predictions[..., 2] - y[..., 2]) * 3.28084
    for i, row in enumerate(result["per_horizon"]):
        rows = mask[:, i]
        row["within_3d"] = float(((horizontal[rows, i] < 5) & (vertical[rows, i] < 1000)).mean() * 100)
    return result


def compare(candidate, baseline):
    """Fixed validation objective and guardrails. Lower score is better (baseline 0)."""
    deltas, failures = [], []
    for c, b in zip(candidate["per_horizon"], baseline["per_horizon"]):
        for key in ERROR_KEYS:
            deltas.append(c[key] / max(b[key], 1e-8) - 1)
            absolute_slack = 1.0 if key.endswith("_ft") else 0.01
            if c[key] > b[key] * 1.02 + absolute_slack:
                failures.append(f"{c['horizon']}: {key} increased beyond 2% + {absolute_slack}")
        for key in RATE_KEYS:
            deltas.append((b[key] - c[key]) / 100)
            if c[key] < b[key] - 0.5:
                failures.append(f"{c['horizon']}: {key} dropped by more than 0.5 percentage points")
    for c, b in zip(candidate["per_bucket"], baseline["per_bucket"]):
        if c["n"] < 100:
            continue
        if c["mean_nm"] > b["mean_nm"] * 1.05 + 0.01 or c["within_5_nm"] < b["within_5_nm"] - 1.0:
            failures.append(f"regime {c['family']}/{c['bucket']}/{c['horizon']}: error >5% or hit-rate drop >1 pp")
    return {"objective": float(np.mean(deltas)), "guardrail_failures": failures,
            "passes_guardrails": not failures, "improves_objective": bool(np.mean(deltas) < -1e-4)}


def make_model(checkpoint, device):
    model = tt.ResidualTrajectoryModel().to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    return model


def predict(model, tensors, X, residual_statistics, device):
    return tt.predict_absolute(model, tensors[0], tensors[1], X, tensors[4], residual_statistics, device)


def epoch(model, tensors, optimizer, criterion, batch_size, seed, deterministic_encoder=False):
    model.train()
    if deterministic_encoder:
        model.eval()  # frozen LSTM dropout off; the trainable linear head still receives gradients
    generator = torch.Generator(device=tensors[0].device).manual_seed(seed)
    order = torch.randperm(len(tensors[0]), generator=generator, device=tensors[0].device)
    total = 0.0
    for start in range(0, len(order), batch_size):
        index = order[start:start + batch_size]
        sequence, scalars, target, mask = [t[index] for t in tensors]
        optimizer.zero_grad(set_to_none=True)
        loss = tt.masked_loss(model(sequence, scalars), target, mask, criterion)
        if not torch.isfinite(loss):
            raise RuntimeError("Non-finite training loss")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        optimizer.step()
        total += float(loss.detach()) * len(index)
    return total / len(order)


def train_trial(config, seed, checkpoint, train_tensors, val_tensors, val, baseline, epochs, device, feature_stats, residual_stats):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = make_model(checkpoint, device)
    if config["heads_only"]:
        for p in model.lstm.parameters():
            p.requires_grad_(False)
    if config.get("last_head_only"):
        for p in model.parameters():
            p.requires_grad_(False)
        for p in model.heads[-1].parameters():
            p.requires_grad_(True)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer_class = torch.optim.AdamW if config["optimizer"] == "adamw" else torch.optim.Adam
    optimizer = optimizer_class(params, lr=config["lr"], weight_decay=config["weight_decay"])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=1)
    criterion = torch.nn.SmoothL1Loss(beta=0.05, reduction="none")
    averaged = torch.optim.swa_utils.AveragedModel(model) if config.get("average_checkpoints") else None
    best, best_state, history, patience = None, None, [], 0
    started = time.perf_counter()
    for number in range(1, epochs + 1):
        loss = epoch(model, train_tensors, optimizer, criterion, 256, seed + number,
                     deterministic_encoder=config.get("last_head_only", False))
        validation_loss = tt.run_epoch(model, tuple(t.to(device) for t in val_tensors[:4]), criterion)
        scheduler.step(validation_loss)
        if averaged is not None and number >= 2:
            averaged.update_parameters(model)
        evaluation_model = averaged.module if averaged is not None and number >= 2 else model
        predictions = predict(evaluation_model, val_tensors, val[0], residual_stats, device)
        metrics = score_predictions(predictions, *val, config["name"])
        comparison = compare(metrics, baseline)
        # Prefer a guardrail-passing epoch; otherwise retain the least-bad diagnostic epoch.
        key = (not comparison["passes_guardrails"], comparison["objective"])
        current = {"epoch": number, "train_loss": loss, "validation_loss": validation_loss,
                   "lr": optimizer.param_groups[0]["lr"], **comparison}
        history.append(current)
        print(f"{config['name']} seed {seed} epoch {number}: loss {validation_loss:.6f} "
              f"objective {comparison['objective']:+.5f} guards {comparison['passes_guardrails']}", flush=True)
        if best is None or key < best[0]:
            best = (key, current, metrics)
            best_state = {k: v.detach().cpu().clone() for k, v in evaluation_model.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= 3:
            break
    model.load_state_dict(best_state)
    artifact = copy.deepcopy(checkpoint)
    artifact["model_state_dict"] = best_state
    artifact["experiment"] = {"config": config, "seed": seed, "best_epoch": best[1]["epoch"],
                              "source_sha256": sha(SAVED / "trajectory_residual.pt")}
    artifact_path = WORK / f"{config['name']}_seed{seed}.pt"
    torch.save(artifact, artifact_path)
    result = {"config": config, "seed": seed, "history": history, "best": best[1],
              "validation": best[2], "training_seconds": time.perf_counter() - started,
              "artifact": str(artifact_path.relative_to(ROOT)), "artifact_sha256": sha(artifact_path)}
    write(REPORTS / f"{config['name']}_seed{seed}.json", result)
    del model, optimizer, train_tensors
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def main():
    global REPORTS, WORK, TRIALS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--run-id", default="20261101")
    parser.add_argument("--trial-set", choices=("initial", "refinement", "horizon_head"), default="initial")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        parser.error("run-id must contain only letters, numbers, underscores and hyphens")
    REPORTS = ROOT / f"ml_pipeline/reports/trajectory_tuning_{args.run_id}"
    WORK = ROOT / f"ml_pipeline/data/processed/trajectory_experiments/{args.run_id}"
    if args.trial_set == "refinement":
        TRIALS = REFINEMENT_TRIALS
    elif args.trial_set == "horizon_head":
        TRIALS = HORIZON_HEAD_TRIALS
    REPORTS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    if (REPORTS / "summary.json").exists():
        raise RuntimeError("Completed experiment already exists; use a new dated experiment rather than overwrite results")
    torch.set_num_threads(4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        torch.backends.cudnn.benchmark = True
    print("Device:", device, torch.cuda.get_device_name(0) if device.type == "cuda" else "", flush=True)
    original_hashes = {p.name: sha(p) for p in SAVED.iterdir() if p.is_file() and p.suffix in (".pt", ".pkl", ".json")}
    protocol = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "checkpoint_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "trials": TRIALS, "max_epochs": args.epochs, "batch_size": 256, "loss": "SmoothL1 beta 0.05",
                "clip_grad_norm": 1.0, "scheduler": "ReduceLROnPlateau factor .5 patience 1",
                "selection_seed": 42, "confirmation_seeds": [43, 44],
                "selection": "Validation only; passing guardrails first, then minimum mean relative-error/rate-gap objective. Baseline objective zero.",
                "guardrails": "Per horizon: errors <= baseline*1.02 + .01 NM (1 ft altitude); rates drop <= .5 pp. Regime n>=100: mean error <= baseline*1.05+.01 NM; within-5-NM drop <=1 pp.",
                "objective": {"error_ratios_minus_one": ERROR_KEYS, "rate_gap_divided_by_100": RATE_KEYS},
                "test_policy": "Freeze one configuration before opening test labels. Audit that config at seeds 42,43,44; never choose a seed from test.",
                "deployment_policy": "Experiment artifacts only; no automatic replacement of served models.",
                "served_sha256_before": original_hashes,
                "sources": ["https://docs.pytorch.org/docs/main/generated/torch.optim.AdamW.html",
                            "https://docs.pytorch.org/docs/main/generated/torch.optim.lr_scheduler.ReduceLROnPlateau.html",
                            "https://docs.pytorch.org/docs/main/generated/torch.nn.utils.clip_grad_norm_.html",
                            "https://scikit-learn.org/stable/common_pitfalls.html"],
                "design_note": "Trial values, objective weights and practical guardrails are our own experimental design, not thresholds prescribed by a paper."}
    protocol["experiment_source_sha256"] = sha(Path(__file__))
    protocol["adaptive_followup"] = args.trial_set != "initial"
    if args.trial_set == "refinement":
        protocol["checkpoint_averaging"] = "Uniform average of training endpoints from epoch 2 through the current epoch; evaluated using validation only. Same LSTM architecture, no batch-normalization layers. This is a low-rate checkpoint-averaging adaptation, not a reproduction of the original SWA learning-rate schedule."
        protocol["sources"].append("https://proceedings.mlr.press/r16/izmailov18a.html")
        protocol["future_holdout_files"] = ["archive_20260910.parquet", "archive_20260920.parquet"]
        protocol["future_holdout_policy"] = "Build and evaluate these later dates only after freezing the configuration and all three seed checkpoints. Never use their labels to choose parameters, epochs, or seeds. The original test split is an already-examined diagnostic in this adaptive follow-up."
    if args.trial_set == "horizon_head":
        protocol["trial_set"] = "horizon_head"
        protocol["trainable_parameters"] = "Only the final 10-minute linear head (387 parameters). Encoder, shared block and shorter heads frozen; encoder dropout disabled while fitting. Same targets and model architecture."
        protocol["rationale"] = "Full-model tuning changed shorter-horizon outputs. Isolate the ten-minute head to test whether late-horizon improvements can avoid those side effects. Hypothesis and grid declared before viewing the later-date scores from the refinement round."
        protocol["future_holdout_files"] = ["archive_20260910.parquet", "archive_20260920.parquet"]
        protocol["future_holdout_policy"] = "Reuse the later-date cohort only after freezing configuration/epochs/seeds. This is an exploratory shared audit cohort across follow-up studies, not a new independent test for each trial set; it must not drive parameter or seed selection."
    write(REPORTS / "protocol.json", protocol)
    register_reference(WORK / "baseline_trajectory_residual.pt", SAVED / "trajectory_residual.pt")
    shutil.copy2(Path(__file__), WORK / "tune_trajectory_source.py")
    checkpoint = torch.load(SAVED / "trajectory_residual.pt", map_location="cpu", weights_only=False)
    feature_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["feature_normalization"].items()}
    residual_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["residual_normalization"].items()}
    train, val = tt.load_split("train"), tt.load_split("val")
    with np.load(tt.DATA_DIRECTORY / "trajectory_train.npz") as train_data, np.load(tt.DATA_DIRECTORY / "trajectory_val.npz") as val_data:
        assert train_data["timestamps"].max() < val_data["timestamps"].min()
    train_tensors = tt.prepare(*train, feature_stats, residual_stats)
    val_tensors = tt.prepare(*val, feature_stats, residual_stats)
    batches = tuple(t.to(device) for t in train_tensors[:4])
    baseline_model = make_model(checkpoint, device)
    baseline = score_predictions(predict(baseline_model, val_tensors, val[0], residual_stats, device), *val, "original LSTM")
    write(REPORTS / "baseline_validation.json", baseline)
    del baseline_model
    trials = [train_trial(c, 42, checkpoint, batches, val_tensors, val, baseline, args.epochs, device, feature_stats, residual_stats) for c in TRIALS]
    winner = min(trials, key=lambda r: (not r["best"]["passes_guardrails"], r["best"]["objective"]))
    selection = {"config": winner["config"], "seed": 42, "best_epoch": winner["best"]["epoch"],
                 "passes_validation_guardrails": winner["best"]["passes_guardrails"],
                 "improves_validation_objective": winner["best"]["improves_objective"],
                 "selected_at_utc": datetime.now(timezone.utc).isoformat()}
    write(REPORTS / "selection_frozen_before_test.json", selection)
    confirmations = [train_trial(winner["config"], seed, checkpoint, batches, val_tensors, val, baseline, args.epochs, device, feature_stats, residual_stats) for seed in (43, 44)]
    # Only now open the historical test labels, for the one already-fixed configuration.
    test = tt.load_split("test")
    with np.load(tt.DATA_DIRECTORY / "trajectory_val.npz") as v, np.load(tt.DATA_DIRECTORY / "trajectory_test.npz") as t:
        assert v["timestamps"].max() < t["timestamps"].min()
    test_tensors = tt.prepare(*test, feature_stats, residual_stats)
    baseline_model = make_model(checkpoint, device)
    baseline_predictions = predict(baseline_model, test_tensors, test[0], residual_stats, device)
    baseline_test = score_predictions(baseline_predictions, *test, "original LSTM")
    cv_test = score_predictions(test_tensors[4], *test, "constant velocity")
    final = []
    for result in [winner] + confirmations:
        model = make_model(checkpoint, device)
        artifact = torch.load(ROOT / result["artifact"], map_location="cpu", weights_only=False)
        model.load_state_dict(artifact["model_state_dict"])
        predictions = predict(model, test_tensors, test[0], residual_stats, device)
        if winner["config"].get("last_head_only"):
            assert np.allclose(predictions[:, :3], baseline_predictions[:, :3], rtol=0, atol=1e-8), "Frozen shorter horizons changed"
        metrics = score_predictions(predictions, *test, result["config"]["name"])
        np.save(WORK / f"finalist_seed{result['seed']}_test_predictions.npy", predictions)
        final.append({"seed": result["seed"], "metrics": metrics, "comparison": compare(metrics, baseline_test),
                      "validation": result["best"], "artifact": result["artifact"]})
    future_audit = None
    if args.trial_set != "initial":
        import preprocess_sequences as pre
        if FUTURE_COHORT.exists():
            with np.load(FUTURE_COHORT, allow_pickle=True) as cohort:
                future_x, future_y, future_mask, timestamps, aircraft, callsigns = (cohort[k] for k in ("X", "y", "mask", "timestamps", "icao24", "callsign"))
        else:
            paths = [ROOT / "ml_pipeline/data/archive" / name for name in protocol["future_holdout_files"]]
            states = pre.load_valid_states(paths=paths)
            future_x, future_y, future_mask, timestamps, aircraft, callsigns = pre.build_samples(states)
            FUTURE_COHORT.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(FUTURE_COHORT, X=future_x, y=future_y, mask=future_mask, timestamps=timestamps, icao24=aircraft, callsign=callsigns)
        with np.load(tt.DATA_DIRECTORY / "trajectory_test.npz") as old_test:
            assert timestamps.min() > old_test["timestamps"].max() + 600
        register_reference(WORK / "future_holdout.npz", FUTURE_COHORT)
        future = (future_x, future_y, future_mask)
        future_tensors = tt.prepare(*future, feature_stats, residual_stats)
        baseline_model = make_model(checkpoint, device)
        original_future = predict(baseline_model, future_tensors, future_x, residual_stats, device)
        save_shared_array(FUTURE_BASELINE, original_future)
        register_reference(WORK / "original_future_predictions.npy", FUTURE_BASELINE)
        baseline_future = score_predictions(original_future, *future, "original LSTM future dates")
        audits = []
        for result in [winner] + confirmations:
            model = make_model(checkpoint, device)
            artifact = torch.load(ROOT / result["artifact"], map_location="cpu", weights_only=False)
            model.load_state_dict(artifact["model_state_dict"])
            predictions = predict(model, future_tensors, future_x, residual_stats, device)
            np.save(WORK / f"finalist_seed{result['seed']}_future_predictions.npy", predictions)
            metrics = score_predictions(predictions, *future, "fine-tuned future dates")
            audits.append({"seed": result["seed"], "metrics": metrics, "comparison": compare(metrics, baseline_future)})
        future_audit = {"files": protocol["future_holdout_files"], "samples": len(future_x),
                        "min_timestamp": int(timestamps.min()), "max_timestamp": int(timestamps.max()),
                        "baseline": baseline_future, "constant_velocity": score_predictions(future_tensors[4], *future, "constant velocity future dates"),
                        "finalists": audits}
    after = {p.name: sha(p) for p in SAVED.iterdir() if p.is_file() and p.suffix in (".pt", ".pkl", ".json")}
    assert original_hashes == after, "Served artifacts changed during experiment"
    report = {"completed_at_utc": datetime.now(timezone.utc).isoformat(), "protocol": protocol,
              "baseline_validation": baseline, "trials": trials, "selection": selection,
              "confirmation_validation": [{"seed": r["seed"], "best": r["best"]} for r in confirmations],
              "baseline_test": baseline_test, "constant_velocity_test": cv_test, "finalist_test": final,
              "future_holdout": future_audit,
              "served_artifacts_unchanged": original_hashes == after,
              "headline_note": "No deployed change: classifier warning metric remains the prior recorded 95.1%; it was not remeasured here.",
              "scope": "Residual LSTM only; the served multi-path predictor is a separate model. LSTM has no probability output, so calibration is not applicable."}
    write(REPORTS / "summary.json", report)
    print("Completed. Frozen selection:", selection, flush=True)
    for result in final:
        print("Test seed", result["seed"], result["comparison"], flush=True)


if __name__ == "__main__":
    main()
