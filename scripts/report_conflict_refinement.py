"""Render the second false-alert batch without replacing any baseline evaluation."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'ml_pipeline/reports/conflict_refinement_20261101'
WORK = ROOT / 'ml_pipeline/data/processed/conflict_experiments/20261101_refinement'
DOC = ROOT / 'docs/experiments/conflict_refinement_20261101.md'


def main():
    r = json.loads((REPORT / 'results.json').read_text())
    name = r['winners']['classifier_training']
    c = next(c for c in r['candidates'] if c['name'] == name)
    old, prior = r['baselines']['test']['served'], r['baselines']['test']['prior_proposal']
    rows = []
    for trial in r['candidates']:
        b = trial['test']['system']
        rows.append(dict(name=trial['name'], family=trial['family'], selected_before_test=trial['selected_before_test'],
                         validation_fp=trial['validation']['system']['fp'], **b,
                         lost_system_true_pairs=len(trial['test']['lost_true_pair_rows']),
                         lost_classifier_true_pairs=len(trial['test']['lost_classifier_true_rows'])))
    with (REPORT / 'all_trials.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    fingerprints = {}
    for p in [ROOT/'scripts/experiment_conflict_refinement.py', ROOT/'scripts/audit_conflict_refinement.py',
              ROOT/'scripts/report_conflict_refinement.py', ROOT/'scripts/experiment_conflict_false_alerts.py',
              WORK/f'{name}.json', REPORT/'selection.json']:
        fingerprints[str(p.relative_to(ROOT))] = dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    (REPORT/'source_artifact_manifest.json').write_text(json.dumps(fingerprints, indent=2))
    model_card = dict(status='local exploratory filter candidate; not a drop-in production classifier',
                      name=name, configuration=c['config'], learned_score_floor=c['score_floor'],
                      baseline_raw_threshold=r['protocol']['base_threshold'],
                      operation='Preserve independent straight-line safety net. Otherwise require baseline classifier threshold AND learned filter score floor.',
                      features='Same 27 current-state, straight-line CPA, manoeuvre and selected-altitude inputs as the existing classifier.',
                      train_rows=28746, validation_rows=6564, historical_test_rows=4690,
                      validation=c['validation'], historical_test=c['test'],
                      probability_caveat='Filter score is not calibrated conflict risk. No replacement probability calibration is claimed.',
                      source_fingerprints=fingerprints, served_hashes_unchanged=r['hashes_after']==r['protocol']['hashes_before'])
    (REPORT/'candidate_model_card.json').write_text(json.dumps(model_card, indent=2))
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8))
    for ax, label, block in zip(axes, ['Served baseline', 'Refined proposal'], [old['system'], c['test']['system']]):
        matrix = np.array(block['confusion_matrix'])
        ax.imshow(matrix, cmap='Blues')
        for row in range(2):
            for col in range(2):
                ax.text(col, row, str(matrix[row,col]), ha='center', va='center', color='white' if matrix[row,col]>2000 else 'black')
        ax.set(xticks=[0,1], yticks=[0,1], xticklabels=['No alert','Alert'], yticklabels=['No conflict','Conflict'],
               xlabel='Prediction', ylabel='Real-future label', title=label)
    fig.suptitle('Historical full-chain test: all original true positives retained')
    fig.tight_layout()
    fig.savefig(DOC.with_name(DOC.stem+'_confusion.png'), dpi=160)
    plt.close(fig)
    metric_rows = []
    for label, block in [('Served full chain', old['system']), ('Previous threshold proposal', prior['system']),
                         ('Refined full-chain proposal', c['test']['system']),
                         ('Served classifier', old['classifier']), ('Refined classifier/filter', c['test']['classifier'])]:
        metric_rows.append(f"| {label} | {block['tp']} | {block['fp']} | {block['fn']} | {block['tn']} | {100*block['precision']:.3f}% | {100*block['recall']:.3f}% | {block['f1']:.6f} |")
    family_rows = []
    for family, chosen in r['winners'].items():
        trial = next(t for t in r['candidates'] if t['name']==chosen)
        b = trial['test']['system']
        family_rows.append(f"| {family} | `{chosen}` | {b['fp']} | {b['tp']} | {len(trial['test']['lost_true_pair_rows'])} |")
    text = f'''# Further false-alert experiments — 1 November 2026

Full-chain early catches remain **271/284 (95.42%)**. The validation-selected refined
proposal reduces historical test false alerts **478 → 459 (3.97%)**, improving on the
previous threshold-only proposal's 463. It retains exactly the same **290 full-chain
true-positive pairs** and **289 classifier true-positive pairs**. False tier-1 alarms
fall **20 → 19**, with **all 28 real tier-1 alarms retained**. Existing missed cases remain:
the full chain still misses 13 of the 303 labelled conflicts.

This is a **local, uncommitted, undeployed experiment**. Served weights, thresholds,
safety net and alert behaviour are unchanged. The initial evaluation and
[first false-alert study](conflict_false_alerts_20261101.md) remain intact.

## Problem and proposed change

False alerts interrupt a controller even when aircraft subsequently stay separated.
This is a real detection problem. Hiding alerts or removing repeated notifications
does not fix a wrongly predicted conflict, so this study measures pair-level decisions.

The new proposal keeps the earlier raw classifier threshold
{r['protocol']['base_threshold']:.12f}, then adds a conservative second learned filter.
The selected filter (`{name}`) is trained from scratch on the original 28,746 classifier
training pairs, using the same 27 inputs. It uses 400 depth-3 XGBoost trees, learning
rate .04, minimum child weight 20, L2 regularization 20, subsample .9 and seed 42.
Positive training examples receive no extra class weighting, unlike the original model.

Only when this filter's score is below **{c['score_floor']:.12f}** may it suppress a
baseline classifier alert. This score is half the lowest filter score among the
original classifier's true-positive validation pairs; the fixed half-score margin
is deliberately more conservative than suppressing up to that observed boundary.
The straight-line legal-separation safety net always bypasses this filter.
These raw scores are ranking outputs, **not calibrated real-world conflict probabilities**.
The filter cannot replace the production classifier by copying its file; it requires
the specified combined decision rule and deployment review.

**Source:** The conservative veto design, score margins and multi-path conjunctions
are our own design. They are not a published no-loss guarantee. Their support is the
paired validation/historical-test measurements below. XGBoost's
[official API](https://xgboost.readthedocs.io/en/stable/python/python_api.html) documents
continuing training with `xgb_model`; its [parameter documentation](https://xgboost.readthedocs.io/en/stable/parameter.html)
defines class weights and the regularization controls used in the training experiments.

## All approaches tried

**28 configurations** were declared before loading the test for this batch:

- **18 multi-path conjunction rules:** require both low original classifier score and
  low predicted path-combination conflict mass before suppressing an alert. Three
  probability summaries × six mass cutoffs; raw-score ceilings use an .8 validation
  safety factor and a .25 cap. These rules add no reduction beyond the prior proposal.
- **4 conservative ensembles:** combine the three earlier depth-2/3/4 filters with
  either a maximum or mean score, with and without multi-path inputs. A maximum keeps
  the alert if any filter remains concerned. They use half the minimum protected
  validation score. Earlier filters fit early validation sessions; only later sessions
  rank these ensembles. Full-validation summaries include those fitting rows and are
  not held-out performance for this family.
- **6 classifier training configurations:** two continuations of the original model
  with 150 additional depth-3 trees, and four fresh fits testing depths 2/3/4 and
  weighted versus unweighted training. These fit only the original training split;
  the entire validation split is separate for threshold selection and family ranking.

One candidate per family is frozen on validation before opening this batch's test.
Every candidate must retain each original classifier and full-system true-positive
validation pair, rather than merely retain the same number. No test scores are used
to choose family winners.

| Family | Validation-selected candidate | Test false alerts | Test true alerts | Lost true pairs |
|---|---|---:|---:|---:|
{chr(10).join(family_rows)}

Some unselected ensembles remove another one or two false test alerts. They are
reported as diagnostics, not selected using their test results. The original test
was already examined in earlier rounds, so this entire follow-up is an **exploratory
repeated-benchmark study**, not a fresh independent confirmation.

## Evaluation

| Historical test | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(metric_rows)}

The refined proposal loses zero original true-pair identities on both validation and
test, for both the standalone classifier and the full chain. Validation full-chain
false alerts fall 705 → {c['validation']['system']['fp']}; its 433 true detections and
411/428 early catches remain intact. Test early catches are unchanged at 271/284.
Real tier-1 detections remain 28, while false tier-1 alarms fall 20 → 19.
This improvement changes which false pairs are detected, not merely their display.

![Historical test confusion matrices](conflict_refinement_20261101_confusion.png)

The full-chain confusion matrix is **[[3928, 459], [13, 290]]**, with rows actual
non-conflict/conflict and columns no-alert/alert. Full confusion counts, precision,
recall, F1 and lost-pair indices for every configuration are retained in raw JSON and
the [all-trial CSV](../../ml_pipeline/reports/conflict_refinement_20261101/all_trials.csv).
The hard safety net still accounts for 153 false alerts and cannot be suppressed here.

## Tiering and resolution checks, simply

**Tiering means urgency.** If a predicted closest approach is within three minutes,
the pair is tier 1: after the alert gate and persistence checks pass, it may sound an
alarm and offer manoeuvre suggestions. From three to ten minutes it is tier 2: a
watch-list warning. Outside ten minutes it is tier 0, not a controller notification.
A tier alone is not sufficient to notify; the pair must also qualify and persist.

**Resolution checks mean testing a possible way out.** For a confirmed tier-1 alert,
the engine simulates candidate instructions such as a turn, climb or descent. It
checks whether the change clears the original pair and whether it creates another
conflict with nearby aircraft, using available predicted paths for the other traffic.
For example, a right turn may clear aircraft B but approach aircraft C, so that turn
should be rejected. These are suggestions for a controller, not automatic aircraft control.

The conflict classifier still receives straight-line CPA plus current/history/selected
altitude inputs. Five paths per aircraft are evaluated separately as 25 combinations
for geometry/tiering and resolution checks. The selected refined filter uses the same
27 classifier features; the multi-path-input approaches did not win this round.

## Verification and limitations

The [actual production-gate audit](../../ml_pipeline/reports/conflict_refinement_20261101/production_gate_audit.json)
recomputes served five-path geometry and compares the proposal with `escalate_pair` on
every validation and test pair. It assumes the geometry persists for three updates,
as in earlier evaluations; it is not a live alert-transition replay. Source served
model hashes remain unchanged. All 40 unit checks pass, including three new checks
for conservative-rule protection and threshold boundaries.

There is no mathematical guarantee of never losing a future conflict. Real-future
labels on relocated-track scenarios differ from observed operational incidents, and
reusing the historical benchmark limits generalization claims. A fresh labelled
encounter cohort is needed before treating this small improvement as deployment-ready.
Probability calibration for the combined filtered output is also not established.

Reproduce from the project root:

```powershell
venv\\Scripts\\python.exe scripts/experiment_conflict_refinement.py
venv\\Scripts\\python.exe scripts/audit_conflict_refinement.py
venv\\Scripts\\python.exe scripts/report_conflict_refinement.py
```

The training script refuses to overwrite completed results. Use a distinct experiment
directory for a new run. [Protocol](../../ml_pipeline/reports/conflict_refinement_20261101/protocol.json),
[frozen selection](../../ml_pipeline/reports/conflict_refinement_20261101/selection.json),
[complete results](../../ml_pipeline/reports/conflict_refinement_20261101/results.json),
[candidate card](../../ml_pipeline/reports/conflict_refinement_20261101/candidate_model_card.json),
and [source/artifact fingerprints](../../ml_pipeline/reports/conflict_refinement_20261101/source_artifact_manifest.json)
are preserved. Encounter and cached-input fingerprints are in the
[first study's input manifest](../../ml_pipeline/reports/conflict_false_alerts_20261101/input_source_manifest.json).
The exact experiment source snapshot is retained alongside the new reports.
Weights and decision arrays remain local under
`ml_pipeline/data/processed/conflict_experiments/20261101_refinement/`.
'''
    DOC.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    main()
