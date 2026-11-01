# Trajectory experiments — 1 November 2026

An isolated residual-LSTM candidate improves several ten-minute metrics while leaving
the one-, three-, and five-minute predictions unchanged. It passes the predeclared
practical regression checks at three seeds on validation, the historical test split,
and the later-date audit. It is **not deployed**. The served multi-path model and the
recorded 95.1% conflict-warning headline are unchanged.

The original project was committed and pushed **before** any experiments:
[checkpoint/pre-trajectory-tuning-20261101](https://github.com/Amrit-Nigam/flight-right/commit/a502c7e),
commit `a502c7e`. Source, reports and this summary are on
[fine-tuning](https://github.com/Amrit-Nigam/flight-right/tree/fine-tuning).
Datasets, private configuration and model binaries remain excluded from Git.

## Studies completed

Ten configurations, sixteen training runs including repeated seeds, 92 epochs total.
All training used the original training split and original normalization. Parameters
and epochs were selected using the later validation split. Rejected results are retained.

| Study | What was tested | Outcome |
|---|---|---|
| [Initial fine-tuning](trajectory_tuning_20261101.md) | Adam/AdamW, learning rate, weight decay, frozen encoder | Mean and tail errors improved, but sharp-turn five-minute hit rate regressed; rejected |
| [Refinement](trajectory_tuning_20261101_refinement.md) | Lower learning rate and checkpoint averaging | Later-date results improved, but validation/historical guardrails were not consistently met across seeds; rejected |
| [Ten-minute head](trajectory_tuning_20261101_horizon_head.md) | Freeze encoder, shared block and shorter heads; tune only 387 output-head parameters | Passes the recorded validation, historical-test and later-date guards at all three seeds; retained as an isolated candidate |

## Candidate results

Fixed configuration: Adam, learning rate **0.0001**, batch size 256, SmoothL1 beta 0.05,
gradient norm cap 1. Seed 42 and validation-selected epoch 4 are the predeclared
representative checkpoint; seeds 43 and 44 check fine-tuning variability. No seed was
chosen based on test scores. This is a small controlled adaptation, not a new architecture.

| Ten-minute metric | Original historical test | Candidate historical test | Original later dates | Candidate later dates |
|---|---:|---:|---:|---:|
| Mean horizontal error, NM ↓ | 6.4093 | 6.3481 | 6.6726 | 6.6277 |
| RMSE, NM ↓ | 10.4673 | 10.3976 | 10.9027 | 10.8616 |
| 90th-percentile error, NM ↓ | 17.1508 | 16.9222 | 17.6431 | 17.5250 |
| Altitude MAE, ft ↓ | 1,108.57 | 1,103.95 | 816.02 | 809.72 |
| Within 1 NM ↑ | 24.73% | 25.95% | 22.98% | 23.27% |
| Within 5 NM ↑ | 61.31% | 61.39% | 60.39% | 60.52% |
| Within 5 NM **and** 1,000 ft ↑ | 50.46% | 50.59% | 52.75% | 52.88% |

The gains are modest. Not every metric improves: along-track MAE rises slightly
(2.8066 → 2.8124 NM on the historical test, 2.5628 → 2.5652 NM on later dates).
The full report lists every metric and regime. Its later-date aircraft-group bootstrap
interval for the within-5-NM gain crosses zero, so that small hit-rate gain is inconclusive.
The resampling diagnostic supports improvements in mean/RMSE/altitude errors and the
within-1-NM rate within these evaluated dates; it does not establish performance on
additional days or airports.

The later-date audit uses 10 and 20 September 2026: 213,482 windows, of which 120,679
have ten-minute targets, grouped into 925 aircraft. Those dates are later than all original
training/validation/test windows. They were not used for fitting or parameter selection.
The follow-up studies share this exploratory audit cohort; they do not each have a new
independent test set. The head-only grid was declared before inspecting its later-date scores.

## Local artifact and reproducibility

- Candidate: `ml_pipeline/data/processed/trajectory_experiments/20261101_horizon_head/trajectory_residual_candidate.pt`.
- [Candidate model card](../../ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/candidate_model_card.json): its own metrics, source fingerprint and unchanged architecture.
- [Complete results](../../ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/summary.json), [protocol](../../ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/protocol.json), and [reproducibility manifest](../../ml_pipeline/reports/trajectory_tuning_20261101_horizon_head/reproducibility_manifest.json).
- Each study directory retains its exact training-source snapshot, trial histories, rejected configurations, frozen selection and original model fingerprints.
- Baseline checkpoint copies and all trial weights/predictions are retained locally under the experiment data directories; they are not in Git.

Validation completed: 28 unit checks passed; the production `TrajectoryPredictor` loads
the packaged candidate and emits finite predictions. Shorter-horizon outputs were
checked against the baseline, and the original served artifact SHA-256 fingerprints
remain unchanged. The candidate's old source-training metadata is separated from its
own fine-tuning metrics in the packaged artifact.

These are **Model 1 LSTM** results. They do not improve the deployed alert-chain headline:
that chain uses **Model 1b multi-path trajectories**, which needs its own tuning and
full-chain regression evaluation before any operational improvement can be claimed.


## Multi-path model ? local, uncommitted experiment

[Complete multi-path experiment report](multipath_tuning_20261101.md). Three configurations were tested. Continuing the ten-minute regressors to 800 iterations passed the recorded checks; the stronger-regularization refit was rejected. The packaged candidate is local and is **not served, committed or pushed**.

| Historical ten-minute arrival-bucket metric | Baseline | Candidate |
|---|---:|---:|
| Top-1 mean error (NM) | 9.93943 | 9.89244 |
| Top-1 altitude MAE (ft) | 1289.81773 | 1288.77336 |
| Best-of-five within 5 NM (%) | 76.46254 | 76.90729 |
| Best-of-five joint 3-D hit (%) | 48.78549 | 49.02497 |
| Energy score (lower is better) | 2.03300 | 2.02671 |

The full-chain test retains 271/284 early catches and 28 real / 20 false tier-1 alarms. Pair-level audit found no lost real alerts or real tier-1 memberships. Route classifier/probabilities and earlier-horizon predictions are unchanged.

The benefit is modest: isolated CPU inference median rose from 350.48 to 390.30 ms per 64 aircraft; raw model size rose by 5.85 MiB. Later-date arrival coverage confidence intervals cross zero, and later-date P90 error worsens slightly. These tradeoffs are included in the report.

Candidate: `ml_pipeline/data/processed/multipath_experiments/20261101/trajectory_multipath_candidate.pkl`. [Model card](../../ml_pipeline/reports/multipath_tuning_20261101/candidate_model_card.json). No further commits or pushes will be made without Archit?s explicit instruction.

## Conflict false-alert experiments - 1 November 2026

[Complete conflict study](conflict_false_alerts_20261101.md). A validation-selected
threshold reduces historical test full-chain false alerts from **478 to 463**, retaining
the same **290 true-positive pairs**, **271/284 early catches**, and **28 real tier-1 alerts**.
Full-chain precision increases from 37.76% to 38.51%; F1 increases from .54155 to .54924.
The classifier alone also retains all 289 true positives, with false positives 460 to 444.

Six learned filters were tested with and without four multi-path summary features.
The validation-selected existing-input and multi-path filters lose four and two true
test conflicts respectively and are rejected. The served classifier currently receives
straight-line CPA/state/history/selected-altitude inputs, not the five paths; the 25
path combinations affect separate geometry and tiering. The hard safety net is preserved.
All candidates and the threshold proposal remain local, uncommitted and undeployed.

## Further conflict refinement - 1 November 2026

[Second false-alert batch](conflict_refinement_20261101.md): 28 configurations test
multi-path conjunction rules, conservative ensembles and classifier continuation/refits.
The validation-selected unweighted refit, used as a conservative filter, reduces test
false alerts **478 -> 459** (previous proposal: 463), preserving the same **290 real
system detections**, **289 real classifier detections**, and **271/284 early catches**.
False tier-1 alarms fall **20 -> 19**; all 28 real tier-1 alarms remain. Full-chain
precision is 38.72%, recall 95.71%, F1 .55133. All 40 tests and actual escalation audits
pass. This remains a repeated historical benchmark, not a future no-loss guarantee.
No candidate is deployed, committed or pushed.
