# Trajectory experiments — 1 November 2026

An isolated residual-LSTM candidate improves several ten-minute metrics while leaving
the one-, three-, and five-minute predictions unchanged. It passes the predeclared
practical regression checks at three seeds on validation, the historical test split,
and the later-date audit. It is **not deployed**. The served multi-path model and the
recorded 95.1% conflict-warning headline are unchanged.

The original project was committed and pushed **before** any experiments:
[checkpoint/pre-trajectory-tuning-20261101](https://github.com/Amrit-Nigam/flight-right/tree/checkpoint/pre-trajectory-tuning-20261101),
commit `a502c7e`. Source, reports and this summary are on
[experiment/trajectory-tuning-20261101](https://github.com/Amrit-Nigam/flight-right/tree/experiment/trajectory-tuning-20261101).
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
