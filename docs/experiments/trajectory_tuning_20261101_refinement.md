# Trajectory tuning — 1 November 2026 (refinement)

This round does not establish an improvement that passes every recorded validation and three-seed test guard. Retain the deployed baseline; inspect the regressions below before another experiment.

The checkpoint is preserved remotely at [checkpoint/pre-trajectory-tuning-20261101](https://github.com/Amrit-Nigam/flight-right/tree/checkpoint/pre-trajectory-tuning-20261101), commit `a502c7e`. Experiments are on `experiment/trajectory-tuning-20261101`.

## Scope and method

This round fine-tunes **Model 1, the residual LSTM** from the existing checkpoint. Model 1b, the multi-path model used by the served alert chain, is separate and is unchanged. The LSTM has no probability output, so probability calibration is not a defined metric for this round.

Training uses all 205,757 existing training windows. The 45,637 later validation windows choose hyperparameters and epochs. One configuration is frozen before the 39,614 historical test windows are opened by the experiment. The already-frozen configuration is repeated at seeds 43 and 44, in addition to selection seed 42. No seed is selected based on its test score. The historical test split has been examined in earlier project work, so this is not a new untouched external evaluation.

Architecture, feature normalization, inputs, targets, SmoothL1 beta 0.05 and the constant-velocity baseline are held fixed. All trials use batch size 256, gradient norm cap 1 and a validation-loss learning-rate scheduler (factor 0.5, patience 1). Maximum six epochs; early stopping after three epochs without improving the guarded validation ranking. Heads-only freezes the LSTM encoder; the shared output block and horizon heads remain trainable.

The fixed validation objective averages six relative error changes (horizontal mean, RMSE, median, 90th percentile, cross-track MAE and altitude MAE) and three hit-rate gaps divided by 100 (within 1 NM, within 5 NM and the joint 5-NM/1,000-ft hit) at each horizon. Lower is better; the original checkpoint scores zero. This is our experimental ranking, not a standard aviation metric.

Guardrails: each per-horizon error may rise at most 2% plus 0.01 NM (1 ft for altitude); a hit rate may fall at most 0.5 percentage points. For regime buckets with at least 100 examples, mean error may rise at most 5% plus 0.01 NM and within-5-NM may fall at most one point. These practical tolerances were declared before training; passing does not mean every metric improves.

## Validation search

| Trial | Optimizer | Learning rate | Weight decay | Best epoch | Objective | Guards pass |
|---|---|---|---|---|---|---|
| adam_lr3e5 | adam | 3e-05 | 0.0 | 6 | -0.00995 | True |
| averaged_adam_lr1e4 | adam | 0.0001 | 0.0 | 3 | -0.00979 | True |
| averaged_adam_lr3e5 | adam | 3e-05 | 0.0 | 6 | -0.00984 | True |

Frozen configuration: **adam_lr3e5**. Validation guards pass: True; objective improves: True.

## Test audit: original checkpoint versus fixed seed-42 finalist

Within-3-D means the same prediction is within 5 NM horizontally and 1,000 ft vertically. All horizons use only windows with available ground truth. Percentages below are hit rates, not classification accuracy.

| Horizon | Model | Mean NM | RMSE NM | Median NM | P90 NM | Altitude MAE ft | Within 1 NM | Within 5 NM | Within 3-D |
|---|---|---|---|---|---|---|---|---|---|
| 1 min | Original | 0.4503 | 1.7310 | 0.0733 | 0.9672 | 98.6 | 90.28% | 98.46% | 97.74% |
| 1 min | Fine-tuned | 0.4494 | 1.7304 | 0.0729 | 0.9671 | 97.6 | 90.30% | 98.46% | 97.74% |
| 3 min | Original | 1.3755 | 3.1039 | 0.2348 | 4.1816 | 304.3 | 71.71% | 91.96% | 83.74% |
| 3 min | Fine-tuned | 1.3685 | 3.0910 | 0.2304 | 4.1804 | 303.2 | 71.75% | 91.97% | 83.81% |
| 5 min | Original | 2.6879 | 5.3719 | 0.6719 | 7.7785 | 509.6 | 56.11% | 82.90% | 71.71% |
| 5 min | Fine-tuned | 2.6618 | 5.3300 | 0.6633 | 7.7364 | 507.9 | 56.06% | 83.03% | 71.82% |
| 10 min | Original | 6.4093 | 10.4673 | 3.2340 | 17.1508 | 1108.6 | 24.73% | 61.31% | 50.46% |
| 10 min | Fine-tuned | 6.2858 | 10.2909 | 3.1622 | 16.7704 | 1101.6 | 26.50% | 61.86% | 50.80% |

### Complete ten-minute metric audit

Every existing per-horizon metric is listed, including small regressions. Error values are better when lower; hit rates (percent) are better when higher.

| Metric | Original historical | Candidate historical | Original later dates | Candidate later dates |
|---|---|---|---|---|
| mean_nm | 6.40930 | 6.28576 | 6.67261 | 6.59215 |
| rmse_nm | 10.46733 | 10.29088 | 10.90274 | 10.83891 |
| median_nm | 3.23403 | 3.16220 | 3.39780 | 3.27888 |
| p90_nm | 17.15084 | 16.77045 | 17.64306 | 17.45750 |
| within_1_nm | 24.72940 | 26.50305 | 22.97666 | 23.71581 |
| within_2_5_nm | 43.97171 | 44.45933 | 42.90639 | 43.59996 |
| within_5_nm | 61.31176 | 61.86368 | 60.39162 | 61.04459 |
| along_mae_nm | 2.80660 | 2.78497 | 2.56280 | 2.55854 |
| cross_mae_nm | 4.95698 | 4.83614 | 5.46812 | 5.38632 |
| altitude_mae_ft | 1108.57338 | 1101.55238 | 816.02242 | 801.07744 |
| within_500_ft | 64.84835 | 64.93945 | 75.16552 | 75.45140 |
| within_1000_ft | 71.92155 | 72.20019 | 80.17136 | 80.40007 |
| within_3d | 50.46083 | 50.79841 | 52.74820 | 53.31582 |

Along-track and cross-track are errors parallel and perpendicular to the aircraft's current heading. The aggregate position error can improve while one directional component worsens slightly. Passing the practical guardrails is not a claim that every component or regime improves.


## Repeated-seed check

Same fixed configuration for every seed. This measures fine-tuning randomness, not full retraining variability.

| Seed | Validation guards pass | Test objective | Test guards pass | 10-min mean NM | 10-min P90 NM | 10-min altitude MAE ft | 10-min within 5 NM |
|---|---|---|---|---|---|---|---|
| 42 | True | -0.00747 | False | 6.2858 | 16.7704 | 1101.6 | 61.86% |
| 43 | True | -0.00701 | True | 6.2918 | 16.7679 | 1102.3 | 61.77% |
| 44 | False | -0.00731 | True | 6.2877 | 16.7566 | 1101.6 | 61.85% |

### Regression details

- Seed 42: regime turn/sharp turn/5 min: error >5% or hit-rate drop >1 pp
- Seed 43: no recorded guardrail failure
- Seed 44: no recorded guardrail failure

### Manoeuvring and terminal traffic at ten minutes

The original bucket definitions are retained. These are separate, sometimes overlapping slices.

| Regime | n | Original mean NM | Fine-tuned mean NM | Original within 5 NM | Fine-tuned within 5 NM |
|---|---|---|---|---|---|
| turn: straight | 14302 | 5.899 | 5.763 | 64.33% | 64.97% |
| turn: gentle turn | 2268 | 5.884 | 5.843 | 63.14% | 62.57% |
| turn: moderate turn | 1273 | 7.562 | 7.543 | 49.88% | 50.51% |
| turn: sharp turn | 819 | 14.986 | 14.680 | 21.25% | 23.32% |
| vertical: level | 13320 | 5.061 | 4.989 | 70.05% | 70.37% |
| vertical: gentle climb/descent | 3602 | 9.186 | 8.876 | 42.81% | 44.00% |
| vertical: fast climb/descent | 1740 | 10.983 | 10.850 | 32.76% | 33.74% |
| distance to VABB: terminal | 2923 | 10.812 | 10.452 | 34.79% | 35.75% |
| distance to VABB: intermediate | 2744 | 7.682 | 7.657 | 56.56% | 56.12% |
| distance to VABB: en-route | 12995 | 5.150 | 5.059 | 68.28% | 68.95% |

## Later-date audit: 10 and 20 September 2026

This is an adaptive follow-up after inspecting the first round. The original test set is therefore an already-examined diagnostic, not fresh independent evidence. These two later archive dates were predeclared in the refinement protocol and built/scored only after the configuration and all three seed checkpoints were fixed. No archive window was used for training or parameter selection. The ordinary preprocessing rules (real observation interpolation, gaps, speed/altitude floors and per-horizon masks) produced 213,482 windows. Their dates are later than every original test window.

For averaged trials, the evaluated weights uniformly average training endpoints from epoch 2 through the current epoch. This adapts checkpoint averaging to Adam fine-tuning; it does not reproduce the original SWA paper's SGD learning-rate schedule. The exact rule is in the protocol.

| Horizon | Model | n | Mean NM | RMSE NM | P90 NM | Altitude MAE ft | Within 1 NM | Within 5 NM | Within 3-D |
|---|---|---|---|---|---|---|---|---|---|
| 1 min | Original | 208964 | 0.6913 | 2.6531 | 0.8600 | 69.3 | 90.66% | 94.36% | 93.91% |
| 1 min | Fine-tuned seed 42 | 208964 | 0.6896 | 2.6519 | 0.8490 | 68.5 | 90.73% | 94.36% | 93.92% |
| 3 min | Original | 183120 | 1.6151 | 4.2349 | 4.2561 | 211.1 | 74.85% | 91.25% | 85.40% |
| 3 min | Fine-tuned seed 42 | 183120 | 1.6064 | 4.2217 | 4.2295 | 209.8 | 74.98% | 91.31% | 85.39% |
| 5 min | Original | 162204 | 2.5592 | 5.1608 | 7.6400 | 352.4 | 57.88% | 84.13% | 75.73% |
| 5 min | Fine-tuned seed 42 | 162204 | 2.5367 | 5.1314 | 7.6350 | 348.1 | 58.21% | 84.23% | 75.92% |
| 10 min | Original | 120679 | 6.6726 | 10.9027 | 17.6431 | 816.0 | 22.98% | 60.39% | 52.75% |
| 10 min | Fine-tuned seed 42 | 120679 | 6.5921 | 10.8389 | 17.4575 | 801.1 | 23.72% | 61.04% | 53.32% |

| Seed | Later-date objective | Guards pass | Failures |
|---|---|---|---|
| 42 | -0.00796 | True | none |
| 43 | -0.00809 | True | none |
| 44 | -0.00814 | True | none |

## Paired uncertainty diagnostic

Dataset: later archive dates. At ten minutes: 120,679 windows, grouped into 925 aircraft. 1,000 paired bootstrap resamples retain all windows of an aircraft together. The table gives candidate-minus-original percentile 95% intervals for seed 42. Negative error differences and positive hit-rate differences favor the candidate. Intervals crossing zero do not provide a clear direction in this diagnostic. This does not measure generalization to a new date, airport or traffic source and was not used for selection.

| Metric | 95% interval of difference |
|---|---|
| mean_nm | -0.1076 to -0.0560 |
| rmse_nm | -0.1046 to -0.0241 |
| altitude_mae_ft | -19.2830 to -10.3673 |
| within_1_nm | +0.4505 to +1.0136 |
| within_5_nm | +0.4342 to +0.8787 |
| within_3d | +0.3990 to +0.7412 |

## Research basis and reproducibility

- [AdamW](https://docs.pytorch.org/docs/main/generated/torch.optim.AdamW.html): tests decoupled weight decay against the current Adam optimizer.
- [ReduceLROnPlateau](https://docs.pytorch.org/docs/main/generated/torch.optim.lr_scheduler.ReduceLROnPlateau.html): lowers learning rate when validation loss stalls.
- [Gradient norm clipping](https://docs.pytorch.org/docs/main/generated/torch.nn.utils.clip_grad_norm_.html): caps update gradients; it is tested here rather than assumed to improve this dataset.
- [Data leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html): selection and preprocessing must not fit on test data.

The exact learning rates, grid size, ranking and tolerance values are our own predeclared design. The sources explain the mechanisms, not evidence that these settings work for Mumbai traffic.

- [Checkpoint averaging research](https://proceedings.mlr.press/r16/izmailov18a.html): motivation for the averaging ablation, not proof that this adaptation will work.

- [Protocol recorded before training](../../ml_pipeline/reports/trajectory_tuning_20261101_refinement/protocol.json)
- [Selection frozen before test audit](../../ml_pipeline/reports/trajectory_tuning_20261101_refinement/selection_frozen_before_test.json)
- [All raw results and histories](../../ml_pipeline/reports/trajectory_tuning_20261101_refinement/summary.json)
- [Bootstrap diagnostic](../../ml_pipeline/reports/trajectory_tuning_20261101_refinement/bootstrap_diagnostics.json)

Local fine-tuned checkpoints and predictions: `ml_pipeline/data/processed/trajectory_experiments/20261101_refinement/` (gitignored, retained on this computer). Run `venv\Scripts\python.exe ml_pipeline/training/trajectory/tune_trajectory.py --epochs 6 --run-id 20261101_refinement --trial-set refinement` only in a fresh experiment directory; the script refuses to overwrite a completed run. Then generate this report with `venv\Scripts\python.exe scripts/report_trajectory_tuning.py --run-id 20261101_refinement`.

Served artifact hashes unchanged: **True**. The recorded 95.1% conflict-warning headline is unchanged; this experiment does not evaluate or improve the deployed alert chain.

![Trajectory experiment comparison](trajectory_tuning_20261101.png)
