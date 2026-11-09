"""Generate the local Model 1b experiment report and package only a guarded candidate."""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import resolve_artifact
REPORTS = ROOT / "ml_pipeline/reports/multipath_tuning_20261101"
WORK = ROOT / "ml_pipeline/data/processed/multipath_experiments/20261101"
DOC = ROOT / "docs/experiments/multipath_tuning_20261101.md"


def read(path):
    return json.loads(path.read_text())


def matrix(block):
    return np.array([[block["true_negative"], block["false_positive"]],
                     [block["false_negative"], block["true_positive"]]])


def main():
    r = read(REPORTS / "summary.json")
    future = read(REPORTS / "future_audit.json") if (REPORTS / "future_audit.json").exists() else None
    timing = read(REPORTS / "inference_benchmark.json") if (REPORTS / "inference_benchmark.json").exists() else None
    identity = read(REPORTS / "pair_identity_audit.json") if (REPORTS / "pair_identity_audit.json").exists() else None
    bootstrap = read(REPORTS / "bootstrap_diagnostics.json") if (REPORTS / "bootstrap_diagnostics.json").exists() else None
    winner = r["winner"]
    test = r["test_audits"][0]
    checks = {"validation_eligible": r["validation_eligible"],
              "all_test_trajectory_guards": all(a["comparison"]["passes_guardrails"] and a["comparison"]["improves_objective"] for a in r["test_audits"]),
              "all_test_alert_guards": all(a["alert_comparison"]["passes_guardrails"] for a in r["test_audits"]),
              "all_available_finalists_validation_guards": all(a["comparison"]["passes_guardrails"] and a["alert_comparison"]["passes_guardrails"] for a in r["finalists_validation"]),
              "pair_identity_safety_check": identity is not None and all(a["lost_real_alerts"] == 0 and a["lost_real_tier1"] == 0 for a in identity.values()),
              "later_date_guards": future is not None and all(a["comparison"]["passes_guardrails"] and a["comparison"]["improves_objective"] for a in future["audits"]),
              "inference_cost_guard": timing is not None and timing["passes_cost_guard"],
              "served_files_unchanged": r["served_artifacts_unchanged"]}
    accepted = all(checks.values())
    path = resolve_artifact(ROOT / winner["artifact"])
    card = {"candidate": winner["config"], "seed": winner["seed"], "accepted_as_isolated_candidate": accepted,
            "checks": checks, "artifact": winner["artifact"], "source_sha256": r["protocol"]["source_sha256"],
            "validation": winner["validation"], "test": test, "future": future,
            "calibration_note": "Classifier and temperature frozen. Route-cluster calibration is unchanged; geometric hit and conflict-event calibration are different questions.",
            "status": "local uncommitted candidate, not deployed or pushed"}
    if accepted:
        bundle = pickle.loads(path.read_bytes())
        packaged = WORK / "trajectory_multipath_candidate.pkl"
        # A historical raw export may resolve to this already packaged, pinned model.
        # Preserve its bytes and provenance instead of overwriting its embedded card.
        if path.resolve() != packaged.resolve():
            bundle["tuning_model_card"] = {k: v for k, v in card.items() if k not in ("future",)}
            packaged.write_bytes(pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL))
        card["packaged_artifact"] = str(packaged.relative_to(ROOT))
        card["packaged_sha256"] = hashlib.sha256(packaged.read_bytes()).hexdigest()
    (REPORTS / "candidate_model_card.json").write_text(json.dumps(card, indent=2))
    decision = ("The candidate passes the recorded trajectory, alert-chain, later-date and inference-cost checks. "
                "It is packaged separately for review; it has not replaced the served model.") if accepted else (
                "The selected candidate does not pass every recorded check (or an audit is pending). "
                "Retain the served baseline; the measured improvements and failures are documented below.")
    lines = ["# Multi-path tuning — 1 November 2026", "", decision, "",
             "All new work is **local and uncommitted** on `fine-tuning`, based on `2bcaba1`. "
             "At Archit's instruction, no new commits or pushes have been made. The original checkpoint "
             "is preserved in that branch's history at `a502c7e`; the obsolete checkpoint and LSTM experiment branch names were removed.", "",
             "## Scope and predeclared method", "",
             "This studies Model 1b, the multi-path predictor used by the alert chain. Only the three "
             "ten-minute per-mode offset regressors change. Forty learned route patterns, the route classifier, "
             "temperature calibration, top-K=5, destination features, earlier horizons, labels, conflict classifier "
             "and alert thresholds stay fixed. Best-of-five is coverage, not single-guess accuracy.", "",
             "`arrivals` retains the project's existing near-airport bucket: distance less than 40 NM "
             "from VABB. It is not an independently labelled arrival/departure classification.", "",
             "The existing archive-augmented training split has 605,757 windows, including 342,606 ten-minute targets. "
             "The five chronological validation collection blocks are divided into 20,091 early windows "
             "(10,192 ten-minute targets) for fresh-refit early stopping, and 25,546 later windows "
             "(12,499 ten-minute targets) for ranking. Their gap exceeds the 600-second target horizon. "
             "Continuation keeps the original identical training data and seed-0 legacy internal random holdout, "
             "as required for a valid scikit-learn warm start. It is not claimed to replace that original holdout "
             "with chronological early stopping. The fresh refit does use explicit chronological early validation.", "",
             "The fixed objective averages relative changes in top-1 mean/RMSE/P90 horizontal errors, altitude "
             "MAE and energy score, plus rate gaps divided by 100 for within-1-NM, top-1/best-of-five within-5-NM "
             "and top-1/best-of-five joint 3-D hits, equally over arrivals and all traffic. Lower is better; "
             "the baseline scores zero. These weights and tolerances are our experimental design, not aviation standards.", "",
             "Trajectory guards: errors may rise at most 2% plus 0.01 NM, 1 ft altitude or 0.001 energy; "
             "coverage may fall at most 0.5 percentage points. Regimes with at least 100 examples allow at most "
             "5%+0.01 NM mean-error rise or a one-point top-1 hit-rate drop. Earlier-horizon predictions remain identical. "
             "A trajectory candidate also faces a validation alert-chain veto before selection is frozen for test.", "",
             "## Trials and validation selection", "",
             "| Trial | Hypothesis | Fitted trees: along / cross / altitude | Objective | Trajectory guards | Validation alert guards |", "|---|---|---|---|---|---|"]
    for t in r["trials"]:
        c = t["config"]
        hypothesis = ("Continue the original capped models without changing training data" if c["method"] == "continue" else
                      "31 leaves, minimum 80 samples per leaf, L2=5, chronological early stopping")
        fits = " / ".join(str(t["fit"][str(i)]["iterations"]) for i in range(3))
        alerts = t.get("alert_comparison", {}).get("passes_guardrails", "not evaluated after earlier passing selection")
        lines.append(f"| {c['name']} | {hypothesis} | {fits} | {t['comparison']['objective']:+.5f} | {t['comparison']['passes_guardrails']} | {alerts} |")
    lines += ["", f"Validation-frozen choice: **{winner['config']['name']}**, seed **{winner['seed']}**. "
              f"Eligible from validation: **{r['validation_eligible']}**.", ""]
    if winner["config"]["method"] == "continue":
        lines += ["Continuation is deterministic from a fixed fitted source. Its original training seed is retained; "
                  "this study does **not** claim independent multi-seed replication. Fresh-model seeds cannot be "
                  "substituted without changing the warm-start data partition and requiring full baseline retraining.", ""]
    lines += ["### Rejected and diagnostic results", ""]
    for t in r["trials"]:
        failures = t["comparison"]["guardrail_failures"] + t.get("alert_comparison", {}).get("guardrail_failures", [])
        lines.append(f"- {t['config']['name']}: " + ("; ".join(failures) if failures else "no recorded failure in the checks evaluated"))
    lines += ["", "## Historical held-out trajectory audit", "",
              "No rejected candidate was selected using test results. The historical split has been examined in "
              "earlier project studies, so it is not a new untouched benchmark. Joint 3-D coverage requires "
              "the **same candidate** to be within 5 NM horizontally and 1,000 ft vertically.", "",
              "| Group | Metric at ten minutes | Baseline | Candidate | Difference |", "|---|---|---|---|---|"]
    for group in ("all", "arrivals"):
        b, c = r["baseline_test"]["groups"][group], test["metrics"]["groups"][group]
        for key in b:
            if key == "n":
                continue
            lines.append(f"| {group} (n={b['n']}) | {key} | {b[key]:.5f} | {c[key]:.5f} | {c[key]-b[key]:+.5f} |")
    lines += ["", "### Per-horizon top-1 metrics", "",
              "| Horizon | Model | Mean NM | RMSE NM | P90 NM | Altitude MAE ft | Within 5 NM |", "|---|---|---|---|---|---|---|"]
    for b, c in zip(r["baseline_test"]["top1_per_horizon"]["per_horizon"], test["metrics"]["top1_per_horizon"]["per_horizon"]):
        for name, row in (("Baseline", b), ("Candidate", c)):
            lines.append(f"| {row['horizon']} | {name} | {row['mean_nm']:.4f} | {row['rmse_nm']:.4f} | {row['p90_nm']:.4f} | {row['altitude_mae_ft']:.1f} | {row['within_5_nm']:.2f}% |")
    lines += ["", "## Full alert-chain audit", "",
              "The existing constructed encounter set relocates one real track while preserving its recorded "
              "future manoeuvres; these are not observed real-world near misses. The audit includes the "
              "multi-path step and verifies the actual escalation function pair by pair, assuming unchanged "
              "geometry for three updates to satisfy persistence. It is not a full live-tick timing test.", "",
              "| Split/model | Precision | Recall | F1 | TN | FP | FN | TP | ≥3-minute catches | Tier 1 real / false |", "|---|---|---|---|---|---|---|---|---|---|"]
    for name, a in (("Validation baseline", r["baseline_validation_alerts"]), ("Validation candidate", winner["validation_alerts"]),
                    ("Test baseline", r["baseline_test_alerts"]), ("Test candidate", test["alerts"])):
        lines.append(f"| {name} | {a['precision']:.4f} | {a['recall']:.4f} | {a['f1']:.4f} | {a['true_negative']} | {a['false_positive']} | {a['false_negative']} | {a['true_positive']} | {a['headline']['caught']}/{a['headline']['total']} | {a['tier_1']['real']} / {a['tier_1']['false']} |")
    lines += ["", "The classification target here is conflict/no conflict after the full chain. "
              "The standalone conflict classifier is unchanged; its previously recorded 95.1% warning figure "
              "must not be conflated with this full-chain rate. Alert guard failures: "
              + ("; ".join(test["alert_comparison"]["guardrail_failures"]) or "none") + ".", "",
              "![Full-chain confusion counts](multipath_tuning_20261101_confusion.png)", "",
              "Display/prominence and collapse counts are also retained in the JSON. Validation acceptance "
              "requires no lost early real catches or real tier-1 alarms and no increase in the specified "
              "false-alert/collapse counts; it does not tune controller thresholds.", ""]
    if identity:
        lines += ["### Pair-level identity check", "",
                  "Counts alone could hide a lost real case offset by a gained one. This additional "
                  "post-selection check compares the individual pair decisions and real tier-1 memberships.", "",
                  "| Split | Changed alert decisions | Changed computed tiers | Lost real alerts | Lost real tier 1 |", "|---|---|---|---|---|"]
        for name, values in identity.items():
            lines.append(f"| {name} | {values['changed_alert_pairs']} | {values['changed_tier_pairs']} | {values['lost_real_alerts']} | {values['lost_real_tier1']} |")
        lines += [""]
    classes = r["route_classification"]
    lines += ["## Route classification and probability calibration", "",
              "The route classifier, cluster identities and temperature are frozen. These values therefore "
              "apply equally to the baseline and candidate, not an improvement caused by offset tuning.", "",
              "| Average | Precision | Recall | F1 |", "|---|---|---|---|"]
    for name in ("macro avg", "weighted avg"):
        c = classes["classification_report"][name]
        lines.append(f"| {name} | {c['precision']:.4f} | {c['recall']:.4f} | {c['f1-score']:.4f} |")
    lines += ["", f"Multiclass negative log likelihood: {classes['negative_log_likelihood']:.5f}; "
              f"Brier score: {classes['multiclass_brier']:.5f}; top-1 ten-bin calibration error: {classes['top1_ece']:.5f}. "
              "These score the actual ten-minute residual's KMeans cluster. They do not establish calibration "
              "of geometric within-distance hits or the probability of a conflict.", "",
              "[Full route-cluster confusion counts](../../ml_pipeline/reports/multipath_tuning_20261101/route_confusion.csv) "
              "and per-class precision/recall/F1 are retained in the raw summary.", "",
              "## Distribution quality: energy score", "",
              "The lower-is-better score is E||Z−y|| − 0.5 E||Z−Z′|| for independent draws from the "
              "normalized retained five-path distribution. Local residual coordinates are scaled by "
              "5 NM along/cross track and 1,000 ft altitude. This fixed scaling is our design, not an "
              "aviation standard. A low best-of-five distance alone can hide poor probabilities or "
              "unhelpful other modes; the energy score evaluates the mixture. It is not a score for the "
              "discarded probability tail or for the conflict event.", ""]
    if future:
        lines += ["## Shared later-date trajectory audit", "",
                  f"10 and 20 September 2026: {future['samples']:,} windows. Destination is known in the "
                  f"existing local route cache for {future['route_known_fraction']:.1%} of windows. "
                  "No online lookups were made. These dates were used in prior LSTM studies and form a "
                  "shared exploratory audit, not a fresh independent test for each follow-up. Labels were "
                  "not used for parameter or candidate selection. This cohort has no labelled encounter "
                  "outcomes; it supports trajectory, not alert-chain, conclusions.", "",
                  "| Group | Metric at ten minutes | Baseline | Candidate | Difference |", "|---|---|---|---|---|"]
        for group in ("all", "arrivals"):
            b, c = future["baseline"]["groups"][group], future["audits"][0]["metrics"]["groups"][group]
            for key in ("top1_mean_nm", "top1_p90_nm", "top1_altitude_mae_ft", "best5_within_5nm", "best5_both", "energy_score"):
                lines.append(f"| {group} (n={b['n']}) | {key} | {b[key]:.5f} | {c[key]:.5f} | {c[key]-b[key]:+.5f} |")
        lines += ["", "Later-date trajectory guard failures: " + ("; ".join(future['audits'][0]['comparison']['guardrail_failures']) or "none") + ".", ""]
    if timing:
        b, c = timing["median_seconds"]["baseline"], timing["median_seconds"]["candidate"]
        lines += ["## Inference and artifact cost", "",
                  f"Production loader, CPU limited to four threads, batch 64, two warmups and seven interleaved "
                  f"measurements: median {b*1000:.2f} ms baseline → {c*1000:.2f} ms candidate. "
                  f"Recorded practical cost guard passes: {timing['passes_cost_guard']}. "
                  f"Raw model size: {timing['artifact_bytes']['baseline']/1048576:.1f} → {timing['artifact_bytes']['candidate']/1048576:.1f} MiB. "
                  "This measures isolated prediction, not the full ingestion/update loop. Timing varies with laptop load.", ""]
    if bootstrap:
        lines += ["## Paired uncertainty diagnostic", "",
                  "1,000 paired resamples of whole aircraft on the later-date cohort, seed 20261101. "
                  "Differences are candidate minus baseline: negative errors/energy or positive coverage favor "
                  "the candidate. Intervals crossing zero are inconclusive within this diagnostic. "
                  "This post-selection check was not used for ranking; it does not measure between-day or "
                  "airport generalization from only two shared dates.", "",
                  "| Group | Metric | Mean difference | 95% percentile interval |", "|---|---|---|---|"]
        for group, values in bootstrap["groups"].items():
            for key, result in values["metrics"].items():
                lo, hi = result["ci95"]
                lines.append(f"| {group} ({values['aircraft']} aircraft) | {key} | {result['mean_difference']:+.5f} | {lo:+.5f} to {hi:+.5f} |")
        lines += [""]
    lines += ["## Acceptance and reproducibility", "", "| Check | Passed |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in checks.items()]
    lines += ["", "Passing practical tolerances is not a claim that every individual component or regime improved. "
              "No served weights, alert thresholds, original data splits or historical evaluation tables were overwritten.", "",
              "- [Protocol](../../ml_pipeline/reports/multipath_tuning_20261101/protocol.json)",
              "- [Exact training source](../../ml_pipeline/reports/multipath_tuning_20261101/source_snapshot.txt)",
              "- [Data/source fingerprints](../../ml_pipeline/reports/multipath_tuning_20261101/reproducibility_manifest.json)",
              "- [Validation-frozen selection](../../ml_pipeline/reports/multipath_tuning_20261101/selection_frozen_before_test.json)",
              "- [Full results, including rejected trials](../../ml_pipeline/reports/multipath_tuning_20261101/summary.json)",
              "- [Candidate card](../../ml_pipeline/reports/multipath_tuning_20261101/candidate_model_card.json)", "",
              "Local trial models: `ml_pipeline/data/processed/multipath_experiments/20261101/`. "
              "If all checks pass, the packaged file is `trajectory_multipath_candidate.pkl` in that directory. "
              "Binary models are local, not committed or uploaded.", "",
              "## Research basis", "",
              "- [scikit-learn HistGradientBoostingRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html): warm-start same-data requirement, regularization and explicit early-stopping validation.",
              "- [Early stopping example](https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_early_stopping.html): motivation for testing iteration limits against validation performance.",
              "- [Gneiting and Raftery (2007), Section 4.3](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf): energy score for multivariate distributions; this report uses negative orientation so lower is better.", "",
              "The candidate grids, coordinate scaling, objective weights and regression tolerances are our "
              "own experimental choices. These sources describe the mechanisms, not evidence that these "
              "settings improve Mumbai traffic. All reported benefits and failures come from the local measurements.", ""]
    np.savetxt(REPORTS / "route_confusion.csv", classes["confusion_matrix"], fmt="%d", delimiter=",")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3))
    for ax, title, block in ((axes[0], "Baseline full chain", r["baseline_test_alerts"]), (axes[1], "Candidate full chain", test["alerts"])):
        counts = matrix(block)
        ax.imshow(counts, cmap="Blues")
        for (i, j), value in np.ndenumerate(counts):
            ax.text(j, i, str(value), ha="center", va="center", color="white" if value > counts.max()/2 else "black")
        ax.set(xticks=[0, 1], yticks=[0, 1], xticklabels=["No conflict", "Conflict"],
               yticklabels=["No conflict", "Conflict"], xlabel="Predicted", ylabel="Actual", title=title)
    fig.tight_layout(); fig.savefig(DOC.with_name("multipath_tuning_20261101_confusion.png"), dpi=160); plt.close(fig)
    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(decision)
    print("Acceptance checks:", checks)


if __name__ == "__main__":
    main()
