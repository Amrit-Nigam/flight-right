"""Render the completed, isolated LSTM tuning results without updating deployed metrics."""
from __future__ import annotations

import json
import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import resolve_artifact, FUTURE_BASELINE, save_shared_array
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
import framing
import train_trajectory as tt

REPORTS = ROOT / "ml_pipeline/reports/trajectory_tuning_20261101"
WORK = ROOT / "ml_pipeline/data/processed/trajectory_experiments/20261101"
DOC = ROOT / "docs/experiments/trajectory_tuning_20261101.md"


def main():
    global REPORTS, WORK, DOC
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="20261101")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        parser.error("Invalid run id")
    REPORTS = ROOT / f"ml_pipeline/reports/trajectory_tuning_{args.run_id}"
    WORK = ROOT / f"ml_pipeline/data/processed/trajectory_experiments/{args.run_id}"
    DOC = ROOT / f"docs/experiments/trajectory_tuning_{args.run_id}.md"
    report = json.loads((REPORTS / "summary.json").read_text())
    torch.set_num_threads(4)
    checkpoint = torch.load(resolve_artifact(WORK / "baseline_trajectory_residual.pt"), weights_only=False, map_location="cpu")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = tt.ResidualTrajectoryModel().to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    future = report.get("future_holdout")
    if future:
        with np.load(resolve_artifact(WORK / "future_holdout.npz"), allow_pickle=True) as data:
            X, y, mask = data["X"], data["y"], data["mask"]
    else:
        X, y, mask = tt.load_split("test")
    feature_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["feature_normalization"].items()}
    residual_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["residual_normalization"].items()}
    tensors = tt.prepare(X, y, mask, feature_stats, residual_stats)
    baseline_pred = tt.predict_absolute(model, tensors[0], tensors[1], X, tensors[4], residual_stats, device)
    if future:
        save_shared_array(FUTURE_BASELINE, baseline_pred)
    else:
        np.save(WORK / "original_lstm_test_predictions.npy", baseline_pred)
    candidate = np.load(WORK / ("finalist_seed42_future_predictions.npy" if future else "finalist_seed42_test_predictions.npy"))
    data_path = resolve_artifact(WORK / "future_holdout.npz") if future else tt.DATA_DIRECTORY / "trajectory_test.npz"
    with np.load(data_path, allow_pickle=True) as test_data:
        aircraft = test_data["icao24"].astype(str)
    eligible = mask[:, 3]
    labels, groups = np.unique(aircraft[eligible], return_inverse=True)
    n_groups = len(labels)
    counts = np.bincount(groups, minlength=n_groups)
    generator = np.random.default_rng(20261101)
    weights = generator.multinomial(n_groups, np.full(n_groups, 1 / n_groups), size=1000)
    denominators = weights @ counts

    def statistics(pred):
        horizontal = framing.error_nm(pred, y)[eligible, 3]
        vertical = (np.abs(pred[..., 2] - y[..., 2]) * 3.28084)[eligible, 3]
        return {"mean_nm": horizontal, "rmse_nm": horizontal ** 2,
                "altitude_mae_ft": vertical, "within_1_nm": (horizontal < 1).astype(float) * 100,
                "within_5_nm": (horizontal < 5).astype(float) * 100,
                "within_3d": ((horizontal < 5) & (vertical < 1000)).astype(float) * 100}

    original_stats, candidate_stats = statistics(baseline_pred), statistics(candidate)
    intervals = {}
    for name in original_stats:
        before = weights @ np.bincount(groups, weights=original_stats[name], minlength=n_groups) / denominators
        after = weights @ np.bincount(groups, weights=candidate_stats[name], minlength=n_groups) / denominators
        if name == "rmse_nm":
            before, after = np.sqrt(before), np.sqrt(after)
        delta = after - before
        intervals[name] = {"delta_ci95": np.percentile(delta, [2.5, 97.5]).tolist()}
    diagnostics = {"method": "1,000 paired bootstrap resamples of whole aircraft, seed 20261101; ten-minute valid windows only",
                   "dataset": "later archive dates" if future else "historical test",
                   "aircraft_groups": n_groups, "windows": int(eligible.sum()), "seed": 42,
                   "purpose": "Post-selection diagnostic, never used to choose a configuration or seed",
                   "limitation": "Only the evaluated dates; aircraft resampling does not represent between-day or airport shift.",
                   "metrics": intervals}
    (REPORTS / "bootstrap_diagnostics.json").write_text(json.dumps(diagnostics, indent=2))
    baseline = report["baseline_test"]["per_horizon"]
    finalist = report["finalist_test"][0]["metrics"]["per_horizon"]
    selected = report["selection"]
    head_only = bool(selected["config"].get("last_head_only"))
    passed = (selected["passes_validation_guardrails"] and selected["improves_validation_objective"]
              and all(r["best"]["passes_guardrails"] and r["best"]["improves_objective"] for r in report["confirmation_validation"]))
    all_test_pass = all(r["comparison"]["passes_guardrails"] and r["comparison"]["improves_objective"] for r in report["finalist_test"])
    if future:
        all_test_pass = all_test_pass and all(r["comparison"]["passes_guardrails"] and r["comparison"]["improves_objective"] for r in future["finalists"])
    decision = ("The isolated finalist improves the combined validation objective and passes the recorded guards on all three test seeds. "
                "It is a candidate for a later integration review, not a deployed change.") if passed and all_test_pass else (
                "This round does not establish an improvement that passes every recorded validation and three-seed test guard. "
                "Retain the deployed baseline; inspect the regressions below before another experiment.")
    DOC.parent.mkdir(exist_ok=True)
    lines = ["# Trajectory tuning — 1 November 2026" + (" (ten-minute head)" if head_only else " (refinement)" if future else ""), "", decision, "",
             "The checkpoint is preserved remotely at [checkpoint/pre-trajectory-tuning-20261101](https://github.com/Amrit-Nigam/flight-right/commit/a502c7e), commit `a502c7e`. "
             "Experiments are on `fine-tuning`.", "",
             "## Scope and method", "",
             "This round fine-tunes **Model 1, the residual LSTM** from the existing checkpoint. "
             "Model 1b, the multi-path model used by the served alert chain, is separate and is unchanged. "
             "The LSTM has no probability output, so probability calibration is not a defined metric for this round.", "",
             "Training uses all 205,757 existing training windows. The 45,637 later validation windows choose "
             "hyperparameters and epochs. One configuration is frozen before the 39,614 historical test windows "
             "are opened by the experiment. The already-frozen configuration is repeated at seeds 43 and 44, "
             "in addition to selection seed 42. No seed is selected based on its test score. "
             "The historical test split has been examined in earlier project work, so this is not a new untouched external evaluation.", "",
             "Architecture, feature normalization, inputs, targets, SmoothL1 beta 0.05 and the constant-velocity "
             "baseline are held fixed. All trials use batch size 256, gradient norm cap 1 and a validation-loss "
             "learning-rate scheduler (factor 0.5, patience 1). Maximum six epochs; early stopping after three "
             "epochs without improving the guarded validation ranking. Heads-only freezes the LSTM encoder; "
             "the shared output block and horizon heads remain trainable.", "",
             "The fixed validation objective averages six relative error changes (horizontal mean, RMSE, median, "
             "90th percentile, cross-track MAE and altitude MAE) and three hit-rate gaps divided by 100 "
             "(within 1 NM, within 5 NM and the joint 5-NM/1,000-ft hit) at each horizon. Lower is better; "
             "the original checkpoint scores zero. This is our experimental ranking, not a standard aviation metric.", "",
             "Guardrails: each per-horizon error may rise at most 2% plus 0.01 NM (1 ft for altitude); "
             "a hit rate may fall at most 0.5 percentage points. For regime buckets with at least 100 examples, "
             "mean error may rise at most 5% plus 0.01 NM and within-5-NM may fall at most one point. "
             "These practical tolerances were declared before training; passing does not mean every metric improves.", "",
             "## Validation search", "",
             "| Trial | Optimizer | Learning rate | Weight decay | Best epoch | Objective | Guards pass |", "|---|---|---|---|---|---|---|"]
    for trial in report["trials"]:
        c, b = trial["config"], trial["best"]
        lines.append(f"| {c['name']} | {c['optimizer']} | {c['lr']} | {c['weight_decay']} | {b['epoch']} | {b['objective']:+.5f} | {b['passes_guardrails']} |")
    if head_only:
        lines += ["", "**Targeted ablation:** only the ten-minute output head's 387 parameters are trainable. "
                  "The encoder, shared layer and all shorter-horizon heads remain frozen. Encoder dropout is "
                  "disabled while fitting this linear head. The test audit asserts that one-, three- and "
                  "five-minute predictions remain identical to the original within 1e-8 absolute coordinate units. "
                  "This is our own isolation experiment, not a new model architecture.", ""]
    lines += ["", f"Frozen configuration: **{selected['config']['name']}**. "
              f"Validation guards pass: {selected['passes_validation_guardrails']}; objective improves: {selected['improves_validation_objective']}.", "",
              "## Test audit: original checkpoint versus fixed seed-42 finalist", "",
              "Within-3-D means the same prediction is within 5 NM horizontally and 1,000 ft vertically. "
              "All horizons use only windows with available ground truth. Percentages below are hit rates, not classification accuracy.", "",
              "| Horizon | Model | Mean NM | RMSE NM | Median NM | P90 NM | Altitude MAE ft | Within 1 NM | Within 5 NM | Within 3-D |", "|---|---|---|---|---|---|---|---|---|---|"]
    for before, after in zip(baseline, finalist):
        for name, row in (("Original", before), ("Fine-tuned", after)):
            lines.append(f"| {row['horizon']} | {name} | {row['mean_nm']:.4f} | {row['rmse_nm']:.4f} | {row['median_nm']:.4f} | {row['p90_nm']:.4f} | {row['altitude_mae_ft']:.1f} | {row['within_1_nm']:.2f}% | {row['within_5_nm']:.2f}% | {row['within_3d']:.2f}% |")
    lines += ["", "### Complete ten-minute metric audit", "",
              "Every existing per-horizon metric is listed, including small regressions. "
              "Error values are better when lower; hit rates (percent) are better when higher.", "",
              "| Metric | Original historical | Candidate historical | Original later dates | Candidate later dates |", "|---|---|---|---|---|"]
    for key, value in baseline[3].items():
        if key in ("horizon", "n"):
            continue
        f0 = future["baseline"]["per_horizon"][3][key] if future else None
        f1 = future["finalists"][0]["metrics"]["per_horizon"][3][key] if future else None
        lines.append(f"| {key} | {value:.5f} | {finalist[3][key]:.5f} | " + (f"{f0:.5f} | {f1:.5f} |" if future else "— | — |"))
    lines += ["", "Along-track and cross-track are errors parallel and perpendicular to the aircraft's current heading. "
              "The aggregate position error can improve while one directional component worsens slightly. "
              "Passing the practical guardrails is not a claim that every component or regime improves.", ""]
    lines += ["", "## Repeated-seed check", "",
              "Same fixed configuration for every seed. This measures fine-tuning randomness, not full retraining variability.", "",
              "| Seed | Validation guards pass | Test objective | Test guards pass | 10-min mean NM | 10-min P90 NM | 10-min altitude MAE ft | 10-min within 5 NM |", "|---|---|---|---|---|---|---|---|"]
    for r in report["finalist_test"]:
        row = r["metrics"]["per_horizon"][3]
        lines.append(f"| {r['seed']} | {r['validation']['passes_guardrails']} | {r['comparison']['objective']:+.5f} | {r['comparison']['passes_guardrails']} | {row['mean_nm']:.4f} | {row['p90_nm']:.4f} | {row['altitude_mae_ft']:.1f} | {row['within_5_nm']:.2f}% |")
    lines += ["", "### Regression details", ""]
    for r in report["finalist_test"]:
        failures = r["comparison"]["guardrail_failures"]
        lines.append(f"- Seed {r['seed']}: " + ("; ".join(failures) if failures else "no recorded guardrail failure"))
    lines += ["", "### Manoeuvring and terminal traffic at ten minutes", "",
              "The original bucket definitions are retained. These are separate, sometimes overlapping slices.", "",
              "| Regime | n | Original mean NM | Fine-tuned mean NM | Original within 5 NM | Fine-tuned within 5 NM |", "|---|---|---|---|---|---|"]
    for before, after in zip(report["baseline_test"]["per_bucket"], report["finalist_test"][0]["metrics"]["per_bucket"]):
        if before["horizon"] != "10 min":
            continue
        lines.append(f"| {before['family']}: {before['bucket']} | {before['n']} | {before['mean_nm']:.3f} | {after['mean_nm']:.3f} | {before['within_5_nm']:.2f}% | {after['within_5_nm']:.2f}% |")
    if future:
        lines += ["", "## Later-date audit: 10 and 20 September 2026", "",
                  "This is an adaptive follow-up after inspecting the first round. The original test set is therefore "
                  "an already-examined diagnostic, not fresh independent evidence. These two later archive dates were "
                  "predeclared in the refinement protocol and built/scored only after the configuration and all three "
                  "seed checkpoints were fixed. No archive window was used for training or parameter selection. "
                  "The ordinary preprocessing rules (real observation interpolation, gaps, speed/altitude floors and "
                  f"per-horizon masks) produced {future['samples']:,} windows. Their dates are later than every original test window.", "",
                  "For averaged trials, the evaluated weights uniformly average training endpoints from epoch 2 "
                  "through the current epoch. This adapts checkpoint averaging to Adam fine-tuning; it does not "
                  "reproduce the original SWA paper's SGD learning-rate schedule. The exact rule is in the protocol.", ""]
        if head_only:
            lines += ["", "This head-only grid was declared before inspecting the refinement round's later-date "
                      "scores. It shares that cohort for an exploratory audit; the dates are not a new independent "
                      "test set for every follow-up, and no configuration, epoch or seed was selected using them.", ""]
        lines += ["| Horizon | Model | n | Mean NM | RMSE NM | P90 NM | Altitude MAE ft | Within 1 NM | Within 5 NM | Within 3-D |", "|---|---|---|---|---|---|---|---|---|---|"]
        for b, c in zip(future["baseline"]["per_horizon"], future["finalists"][0]["metrics"]["per_horizon"]):
            for name, h in (("Original", b), ("Fine-tuned seed 42", c)):
                lines.append(f"| {h['horizon']} | {name} | {h['n']} | {h['mean_nm']:.4f} | {h['rmse_nm']:.4f} | {h['p90_nm']:.4f} | {h['altitude_mae_ft']:.1f} | {h['within_1_nm']:.2f}% | {h['within_5_nm']:.2f}% | {h['within_3d']:.2f}% |")
        lines += ["", "| Seed | Later-date objective | Guards pass | Failures |", "|---|---|---|---|"]
        for a in future["finalists"]:
            c = a["comparison"]
            lines.append(f"| {a['seed']} | {c['objective']:+.5f} | {c['passes_guardrails']} | " + ("; ".join(c['guardrail_failures']) or "none") + " |")
    lines += ["", "## Paired uncertainty diagnostic", "",
              ("Dataset: later archive dates. " if future else "Dataset: historical test. ") +
              f"At ten minutes: {diagnostics['windows']:,} windows, grouped into {n_groups} aircraft. "
              "1,000 paired bootstrap resamples retain all windows of an aircraft together. "
              "The table gives candidate-minus-original percentile 95% intervals for seed 42. "
              "Negative error differences and positive hit-rate differences favor the candidate. "
              "Intervals crossing zero do not provide a clear direction in this diagnostic. "
              "This does not measure generalization to a new date, airport or traffic source and was not used for selection.", "",
              "| Metric | 95% interval of difference |", "|---|---|"]
    for name, values in intervals.items():
        lo, hi = values["delta_ci95"]
        lines.append(f"| {name} | {lo:+.4f} to {hi:+.4f} |")
    lines += ["", "## Research basis and reproducibility", "",
              "- [AdamW](https://docs.pytorch.org/docs/main/generated/torch.optim.AdamW.html): tests decoupled weight decay against the current Adam optimizer.",
              "- [ReduceLROnPlateau](https://docs.pytorch.org/docs/main/generated/torch.optim.lr_scheduler.ReduceLROnPlateau.html): lowers learning rate when validation loss stalls.",
              "- [Gradient norm clipping](https://docs.pytorch.org/docs/main/generated/torch.nn.utils.clip_grad_norm_.html): caps update gradients; it is tested here rather than assumed to improve this dataset.",
              "- [Data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html): selection and preprocessing must not fit on test data.", "",
              "The exact learning rates, grid size, ranking and tolerance values are our own predeclared design. "
              "The sources explain the mechanisms, not evidence that these settings work for Mumbai traffic.", "",
              "- [Checkpoint averaging research](https://proceedings.mlr.press/r16/izmailov18a.html): motivation for the averaging ablation, not proof that this adaptation will work.", "",
              f"- [Protocol recorded before training](../../ml_pipeline/reports/trajectory_tuning_{args.run_id}/protocol.json)",
              f"- [Selection frozen before test audit](../../ml_pipeline/reports/trajectory_tuning_{args.run_id}/selection_frozen_before_test.json)",
              f"- [All raw results and histories](../../ml_pipeline/reports/trajectory_tuning_{args.run_id}/summary.json)",
              f"- [Bootstrap diagnostic](../../ml_pipeline/reports/trajectory_tuning_{args.run_id}/bootstrap_diagnostics.json)", "",
              f"Local fine-tuned checkpoints and predictions: `ml_pipeline/data/processed/trajectory_experiments/{args.run_id}/` "
              f"(gitignored, retained on this computer). Run `venv\\Scripts\\python.exe ml_pipeline/training/trajectory/tune_trajectory.py --epochs 6 --run-id {args.run_id} --trial-set {'horizon_head' if head_only else 'refinement' if future else 'initial'}` "
              "only in a fresh experiment directory; the script refuses to overwrite a completed run. "
              f"Then generate this report with `venv\\Scripts\\python.exe scripts/report_trajectory_tuning.py --run-id {args.run_id}`.", "",
              f"Served artifact hashes unchanged: **{report['served_artifacts_unchanged']}**. "
              "The recorded 95.1% conflict-warning headline is unchanged; this experiment does not evaluate or improve the deployed alert chain.", ""]
    if head_only:
        lines += ["[Packaged candidate model card](../../ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/candidate_model_card.json). "
                  "Use the separately packaged `trajectory_residual_candidate.pt` for integration review. "
                  "Its metrics describe its own weights; the raw trial checkpoints retain source-checkpoint metadata for provenance.", ""]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    for ax, key, title in zip(axes.ravel(), ("mean_nm", "p90_nm", "altitude_mae_ft", "within_5_nm"),
                              ("Mean horizontal error (NM)", "90th percentile error (NM)", "Altitude MAE (ft)", "Within 5 NM (%)")):
        ax.plot([1, 3, 5, 10], [row[key] for row in baseline], marker="o", label="Original")
        values = np.array([[row[key] for row in r["metrics"]["per_horizon"]] for r in report["finalist_test"]])
        ax.plot([1, 3, 5, 10], values[0], marker="s", label="Fine-tuned seed 42")
        ax.fill_between([1, 3, 5, 10], values.min(0), values.max(0), alpha=.18, label="Three-seed range")
        ax.set(title=title, xlabel="Minutes ahead"); ax.grid(alpha=.25)
    axes[0, 0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(DOC.with_suffix(".png"), dpi=160)
    plt.close(fig)
    lines += ["![Trajectory experiment comparison](trajectory_tuning_20261101.png)", ""]
    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(decision)
    print("Wrote", DOC.relative_to(ROOT))


if __name__ == "__main__":
    main()
