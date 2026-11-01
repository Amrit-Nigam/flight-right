"""Publish non-speech evaluation results. Earlier evaluation files stay in evaluation-history.

Run after reevaluate_models.py, multipath_3d_eval.py and offsets_ab_test.py:
python scripts/update_evaluation.py --reevaluation PATH --multipath PATH --runtime PATH
Speech results deliberately do not enter the document or metrics.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def confusion_plot(matrix, labels, path, title):
    matrix = np.asarray(matrix)
    many = len(labels) > 5
    if many:
        totals = matrix.sum(axis=1, keepdims=True)
        matrix = np.divide(matrix, totals, out=np.zeros_like(matrix, dtype=float), where=totals != 0)
    fig, ax = plt.subplots(figsize=(12, 10) if many else (5.5, 4.5))
    im = ax.imshow(matrix, cmap="Blues", **({"vmin": 0, "vmax": 1} if many else {}))
    ax.set(xticks=range(len(labels)), yticks=range(len(labels)),
           xticklabels=labels, yticklabels=labels, xlabel="Predicted class",
           ylabel="Actual class", title=title)
    ax.tick_params(labelsize=7 if many else 10)
    if not many:
        for (i, j), value in np.ndenumerate(matrix):
            ax.text(j, i, str(value), ha="center", va="center",
                    color="white" if value > matrix.max() / 2 else "black")
    fig.colorbar(im, ax=ax, label="Fraction of actual class" if many else "Test examples")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def binary_matrix(block):
    return [[block["true_negative"], block["false_positive"]],
            [block["false_negative"], block["true_positive"]]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reevaluation", "multipath", "runtime"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    r, three, runtime = read(args.reevaluation), read(args.multipath), read(args.runtime)
    import evaluate
    import multipath as mp
    test_x, test_y, test_mask = evaluate.load_split("test")
    tree_path = ROOT / "ml_pipeline/data/processed/tree_reference_test_predictions.npy"
    tree = evaluate.evaluate(np.load(tree_path), test_y, test_mask, test_x, "tree reference")
    tree["provenance"] = "Re-scored saved test predictions; benchmark estimators are not retained or refitted."
    served = runtime["results"]["per_mode rule_only"]
    classifier = r["model2"]["test"]
    cluster = r["model1b"]["route_classification"]
    hashes = {}
    saved = ROOT / "server/app/ml/saved_models"
    for name in ("trajectory_residual.pt", "trajectory_multipath.pkl", "xgboost_conflict.json",
                 "xgboost_conflict_model_card.json"):
        hashes[relative(saved / name)] = hashlib.sha256((saved / name).read_bytes()).hexdigest()
    sources = {name: relative(getattr(args, name)) for name in ("reevaluation", "multipath", "runtime")}
    out = {"measured_at_utc": datetime.now(timezone.utc).isoformat(), "sources": sources,
           "artifact_sha256": hashes, "saved_tree_predictions_sha256": hashlib.sha256(tree_path.read_bytes()).hexdigest(),
           "model1": r["model1"], "model1b": r["model1b"], "model2": r["model2"],
           "model3": r["model3"], "alert_feed": r["alert_feed"],
           "multipath_3d": three, "full_alert_chain": served, "tree_reference": tree}
    docs = ROOT / "docs"
    figures = docs / "figures"
    figures.mkdir(exist_ok=True)
    confusion_plot(binary_matrix(classifier), ["No conflict", "Conflict"],
                   figures / "confusion_classifier.png", "Conflict classifier: fixed saved threshold")
    confusion_plot(binary_matrix(served), ["No conflict", "Conflict"],
                   figures / "confusion_runtime.png", "Full alert chain: held-out encounter pairs")
    confusion_plot(cluster["confusion_matrix"], cluster["labels"],
                   figures / "confusion_route_clusters.png", "Route-pattern classifier: fraction within each actual class")
    np.savetxt(figures / "confusion_route_clusters.csv", cluster["confusion_matrix"], delimiter=",", fmt="%d")
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for name, rows in (("Constant velocity", r["model1"]["baseline_per_horizon"]),
                       ("Residual LSTM", r["model1"]["per_horizon"]),
                       ("Tree reference", tree["per_horizon"])):
        ax.plot([1, 3, 5, 10], [row["within_5_nm"] for row in rows], marker="o", label=name)
    ax.set(xlabel="Prediction horizon (minutes)", ylabel="Predictions within 5 NM (%)", ylim=(0, 100))
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    fig.savefig(figures / "traj_within5nm.png", dpi=160); plt.close(fig)
    lines = ["# Flight Right — Evaluation", "",
             f"Refreshed {out['measured_at_utc']}. Saved artifacts were evaluated without retraining or changing thresholds.", "",
             f"**Headline: {classifier['headline']['rate']:.2%} ({classifier['headline']['caught']}/{classifier['headline']['total']}) of eligible conflicts caught with at least three minutes of warning.** "
             f"The full alert chain catches {served['headline']['rate']:.2%} ({served['headline']['caught']}/{served['headline']['total']}).", "",
             "Speech evaluations are maintained separately and are intentionally excluded from this document and `metrics.json`.", "",
             "## Earlier evaluations and reproducibility", "",
             "- [Previous evaluation, preserved verbatim](evaluation-history/20261030_before_refresh/evaluation.md), with its original metrics, figures and ablations in the same directory.",
             "- [Initial training report](../ml_pipeline/reports/training_report_20260906_140317.md).",
             "- [Earlier saved-model evaluation](../ml_pipeline/reports/reevaluation_20260908_093417.json). All earlier dated reports remain available.",
             "- [Current machine-readable results](metrics.json), including full confusion matrices, per-class metrics and SHA-256 fingerprints of the model files.", ""]
    for name, path in sources.items():
        lines.append(f"- {name}: [{path}](../{path})")
    lines += ["", "Reproduce the scoring, then publish the resulting dated report paths:", "", "```powershell",
              "venv\\Scripts\\python.exe ml_pipeline/utils/reevaluate_models.py",
              "venv\\Scripts\\python.exe ml_pipeline/utils/multipath_3d_eval.py",
              "venv\\Scripts\\python.exe ml_pipeline/utils/offsets_ab_test.py",
              "venv\\Scripts\\python.exe scripts/update_evaluation.py --reevaluation PATH --multipath PATH --runtime PATH", "```", "",
              "## What each component is evaluated on", "",
              "| Component | Evaluation | Interpretation |", "|---|---|---|",
              "| Model 1: residual LSTM | Horizontal mean, RMSE, median, 90th percentile; altitude MAE; within-distance rates, per horizon and regime | Predicts a single future position |",
              "| Tree reference | Same trajectory metrics from saved test predictions | Comparison benchmark; not served |",
              "| Model 1b: multi-path | Top-1 and best-of-5 coverage, horizontal and vertical, calibration; cluster confusion matrix and precision/recall/F1 | Five candidates cover alternatives; best-of-5 is not single-guess accuracy |",
              "| Model 2: conflict classifier | Precision, recall, F1, F2, confusion matrix, PR-AUC, calibration, warning time | Conflict is the positive class |",
              "| Full alert chain | Same binary metrics, warning rate and alarm tiers, including multi-path geometry | Evaluates the served decision logic on encounter pairs |",
              "| Model 3: deterministic resolution engine | Candidates simulated, rejected, offered; real/false-alarm coverage | No learned class labels; classification F1 is not applicable |",
              "| Alert feed | Interruptions before/after and pairs retained | Display suppression, not another predictive model |", "",
              f"The trajectory test set contains {len(test_x):,} windows, with a mask selecting available future targets. "
              f"The conflict test set contains {sum(sum(row) for row in binary_matrix(classifier)):,} pairs. "
              "Both splits follow collection time. Encounter labels use the recorded futures of real tracks, "
              "with one track relocated to create encounters; these are not observed real-world near misses. "
              "The warning metric is a subset of conflict recall, restricted to conflicts with at least 180 seconds until their recorded closest approach.", "",
              "## Model 1 and the tree reference", "",
              "Lower errors are better; higher within-distance rates are better. NM means nautical miles. MAE means mean absolute error.", "",
              "| Model | Horizon | n | Mean NM | RMSE NM | Median NM | P90 NM | Within 1 NM | Within 5 NM | Altitude MAE ft |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, rows in (("Constant velocity", r["model1"]["baseline_per_horizon"]), ("Residual LSTM", r["model1"]["per_horizon"]), ("Tree reference", tree["per_horizon"])):
        for h in rows:
            lines.append(f"| {name} | {h['horizon']} | {h['n']} | {h['mean_nm']:.3f} | {h['rmse_nm']:.3f} | {h['median_nm']:.3f} | {h['p90_nm']:.3f} | {h['within_1_nm']:.2f}% | {h['within_5_nm']:.2f}% | {h['altitude_mae_ft']:.1f} |")
    lines += ["", "![Trajectory comparison](figures/traj_within5nm.png)", "",
              f"The LSTM beats constant velocity at every horizon on the within-5-NM gate: **{r['model1']['gate_beats_constant_velocity']}**. "
              "The tree row re-scores saved predictions rather than refitting a new benchmark. Detailed turn, vertical-motion and airport-distance breakdowns are in `metrics.json`.", "",
              "## Model 1b: multi-path trajectories", "",
              "A 3-D hit requires the **same candidate** to be within both 5 NM horizontally and 1,000 ft vertically at ten minutes. "
              "Arrivals are the existing near-airport evaluation bucket; all-traffic includes those arrivals.", "",
              "| Method | Group | n | Top-1 within 5 NM | Best-of-5 within 5 NM | Top-1 3-D hit | Best-of-5 3-D hit |", "|---|---|---|---|---|---|---|"]
    for name, key in (("Constant velocity", "constant_velocity"), ("Previous table offsets", "served_table"), ("Served per-mode offsets + destination", "served_per_mode")):
        for group, scores in three[key]["ten_minutes"].items():
            one, five = scores["best_of_1"], scores.get("best_of_5")
            n = int((test_mask[:, 3] & (mp.arrival_rows(test_x) if group == 'arrivals' else np.ones(len(test_x), bool))).sum())
            lines.append(f"| {name} | {group} | {n} | {one['within_5nm']:.2f}% | {five['within_5nm'] if five else one['within_5nm']:.2f}% | {one['within_both']:.2f}% | {five['within_both'] if five else one['within_both']:.2f}% |")
    lines += ["", "### Route-pattern classification", "",
              f"This internal classifier selects among {len(cluster['labels'])} learned route clusters, using {cluster['samples']:,} test windows with ten-minute targets. "
              "The target cluster is assigned from the actual future horizontal residual by the saved KMeans model. "
              "These scores describe cluster selection, not conflict detection or final trajectory accuracy.", "",
              "| Average | Precision | Recall | F1 |", "|---|---|---|---|"]
    for name in ("macro avg", "weighted avg"):
        s = cluster["classification_report"][name]
        lines.append(f"| {name} | {s['precision']:.4f} | {s['recall']:.4f} | {s['f1-score']:.4f} |")
    lines += ["", f"Top-1 cluster accuracy / micro precision, recall and F1: **{cluster['accuracy']:.4f}**. "
              "Macro averages give every cluster equal weight; weighted averages use the true cluster frequencies. "
              "All cluster labels, including those absent from test, are retained and zero-division metrics are zero.", "",
              "![Route-cluster confusion matrix](figures/confusion_route_clusters.png)", "",
              "[Full 40 × 40 counts as CSV](figures/confusion_route_clusters.csv); per-class scores are in `metrics.json`. "
              "Rows are actual classes and columns are predicted classes. The heatmap divides each row by its support "
              "so frequent clusters do not hide rare-cluster errors; the CSV retains the unnormalized integer counts. "
              "Classes absent from the test split have zero rows.", "",
              f"Temperature: {r['model1b']['temperature']:.4f}. Cluster calibration error (lower is better), before → after: "
              f"arrivals {r['model1b']['ece_arrivals'][0]:.3f} → {r['model1b']['ece_arrivals'][1]:.3f}; "
              f"all traffic {r['model1b']['ece_all'][0]:.3f} → {r['model1b']['ece_all'][1]:.3f}. "
              "This measures cluster-probability calibration, not the probability of a conflict.", "",
              "## Model 2 and the full alert chain", "",
              "Precision is the share of alerts that are real conflicts. Recall is the share of real conflicts caught. "
              "F1 balances both; F2 puts more weight on recall. All scores below use the saved operating threshold, not a threshold selected on this test set.", "",
              "| Decision | Precision | Recall | F1 | F2 | TN | FP | FN | TP | Caught ≥3 min |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, b in (("Conflict classifier", classifier), ("Rule 8 NM / 1,500 ft", r['model2']['rule_alert_volume']), ("Rule 5 NM / 1,000 ft", r['model2']['rule_legal_minimum']), ("Full served alert chain", served)):
        lines.append(f"| {name} | {b['precision']:.4f} | {b['recall']:.4f} | {b['f1']:.4f} | {b['fbeta_2']:.4f} | {b['true_negative']} | {b['false_positive']} | {b['false_negative']} | {b['true_positive']} | {b['headline']['caught']}/{b['headline']['total']} |")
    cal = r['model2']['calibration']
    lines += ["", "TN = correctly quiet; FP = false alarm; FN = missed conflict; TP = caught conflict.", "",
              f"Saved raw threshold: **{r['model2']['threshold']:.8f}**. PR-AUC (average precision): **{r['model2']['pr_auc']:.4f}**. "
              f"Brier score, raw → calibrated: {cal['raw']['brier']:.4f} → {cal['platt']['brier']:.4f}; "
              f"calibration error: {cal['raw']['ece']:.4f} → {cal['platt']['ece']:.4f}. "
              f"Calibration preserves the alert set: {cal['alert_set_identical']}.", "",
              "![Classifier confusion matrix](figures/confusion_classifier.png)", "",
              "![Full alert-chain confusion matrix](figures/confusion_runtime.png)", "",
              f"Full-chain tier 1: {served['tier_1']['real']} real / {served['tier_1']['false']} false; "
              f"tier 2: {served['tier_2']['real']} real / {served['tier_2']['false']} false. "
              f"False alarms per 1,000 pairs: {served['false_alarms_per_1000']:.2f}.", "",
              "The full-chain test checks the actual escalation decision against its measured implementation on every pair. "
              "It assumes unchanged geometry for three updates to satisfy persistence. It is an encounter-level offline evaluation, "
              "not a timing or end-to-end live-surveillance test. The geometry-only runtime block retained in the JSON is diagnostic and omits multi-path geometry.", "",
              "## Model 3: resolution engine", ""]
    m = r['model3']
    lines += [f"Evaluated {m['alarms']} classifier-triggered tier-1 candidate encounters ({m['alarms_real']} real, {m['alarms_false']} false). "
              f"Simulated {m['candidates_evaluated']} manoeuvres; blocked {m['blocked_unsafe']} unsafe candidates, "
              f"rejected {m['rejected_ineffective']} ineffective and {m['rejected_domino']} secondary-conflict candidates. "
              f"Offered {m['instructions_offered']} instructions across {m['alarms_with_options']} encounters; "
              f"{m['alarms_with_nothing']} received none. "
              f"Instructions on real conflicts: {m['instructions_for_real']}; on false alarms: {m['instructions_for_false']}.", "",
              "This harness reconstructs the pair's instantaneous geometry; it does not supply all surrounding traffic or the "
              "complete multi-path alert stream. A zero secondary-conflict rejection count therefore does not establish runtime "
              "domino-check effectiveness. These are simulation outcomes, not proof that a manoeuvre is safe in actual operations. "
              "Precision, recall and confusion matrices are not defined for the engine's ranked manoeuvre outputs.", "",
              "## Alert-feed display suppression", "",
              "| Recorded session | Frames | Notifications before | After | Reduction | Pairs lost |", "|---|---|---|---|---|---|"]
    for feed in r['alert_feed']:
        lines.append(f"| {feed['session']} | {feed['frames']} | {feed['interruptions_before']} | {feed['interruptions_after']} | {feed['cut_percent']:.1f}% | {feed['lost']} |")
    lines += ["", "This replay uses rule-generated assessments to isolate the display filter. It does not measure "
              "the full learned alert chain, controller workload, or reduction in real-world errors. A pair retained in the "
              "active list can produce fewer repeated notifications.", "",
              "## Limits and interpretation", "",
              "- These are repeated measurements on the existing test split, not new independent test data. Improvements developed against this split need a fresh held-out evaluation before a generalization claim.",
              "- No model weights, target definitions, thresholds or alert decisions were changed by this refresh.",
              "- Per-class support, all trajectory regime breakdowns, probability diagnostics and model fingerprints are in `metrics.json`.",
              "- [Historical ablation study](ablation.md) contains its original experiment comparisons; it is a dated study, not a new multi-seed experiment from this refresh.", ""]
    (docs / "metrics.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    (docs / "evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print("Updated docs/evaluation.md, docs/metrics.json and current evaluation figures.")


if __name__ == "__main__":
    main()
