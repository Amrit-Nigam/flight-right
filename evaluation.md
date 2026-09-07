# Flight Right — Evaluation

Every model built so far, measured on held-out data, with the baseline it has to beat
reported beside it in every table.

**Measured:** 6–7 September 2026. Training run
`ml_pipeline/reports/training_report_20260906_140317.md`.
**Reproduce:** `python ml_pipeline/run_pipeline.py` (full retrain, ~20 min on an RTX 4050),
then `python ml_pipeline/utils/verify_pipeline.py` (110 checks, ~1 min).
**Figures:** regenerated from the saved model artifacts; raw values in
[`docs/metrics.json`](docs/metrics.json).

---

## The headline number

> **94.0% of conflicts are caught with at least three minutes of warning.**
> 267 of 284. The best rule-based detector catches 87.3% of the same set.

![Headline metric](docs/figures/headline_metric.png)

Three minutes is not a round number. It is response geometry: alert → controller decision
(15 s) → radio call and readback (15 s) → pilot begins manoeuvring (8 s) = 38 s before
anything moves, then ~40 s for a 1,000 ft level change or ~96 s for a 30° turn at 450 kt.
Model 3's simulation reaches the same boundary independently — at 90 seconds to closest
approach, **all 26 candidate instructions are rejected** because nothing an airliner can
fly opens 5 NM in the time left.

## How to read every number in this document

Five rules are applied throughout. They exist because breaking them has already cost this
project weeks.

1. **Splits are by time, on whole collection sessions.** Test data is strictly later than
   validation, which is strictly later than training. Adjacent aircraft states leak across
   a random split.
2. **The constant-velocity baseline is reported on identical data in the same run.** A
   model that lost to plain arithmetic at every horizon went unnoticed for three weeks
   because nobody printed the comparison.
3. **Never one averaged figure.** Always per horizon and per flight regime. The average is
   what hid the failure in rule 2.
4. **Probabilities are calibrated before any threshold is applied.** An uncalibrated
   threshold compares against a number that does not mean what it says.
5. **Best-of-K is never reported as accuracy.** They measure different things.

---

# Model 1 — Trajectory prediction

A 2-layer unidirectional LSTM (hidden 128, dropout 0.3) predicting a **residual correction
to the constant-velocity extrapolation** — not absolute position. A zero output reproduces
the physics exactly, so the model starts at the baseline and can only be pushed off it by
evidence. Loss `SmoothL1Loss(beta=0.05)`. Trained on 291,008 samples from 627,344 airborne
states across 33 collection sessions.

**Test split: 39,614 samples, 6 sessions, 4 Sep 08:01 → 5 Sep 09:28 IST.**

| Horizon | n | CV mean | **LSTM mean** | Tree ref. | CV <5 NM | **LSTM <5 NM** | Tree ref. |
|---|---|---|---|---|---|---|---|
| 1 min | 38,110 | 0.49 NM | **0.45 NM** | 0.43 NM | 98.4% | **98.5%** | 98.5% |
| 3 min | 32,324 | 1.69 NM | **1.38 NM** | 1.27 NM | 89.5% | **92.0%** | 92.6% |
| 5 min | 27,587 | 3.65 NM | **2.69 NM** | 2.39 NM | 77.3% | **82.9%** | 85.1% |
| 10 min | 18,662 | 10.30 NM | **6.41 NM** | 5.57 NM | 50.5% | **61.3%** | 65.7% |

![Within 5 NM by horizon](docs/figures/traj_within5nm.png)

![Mean error by horizon](docs/figures/traj_mean_error.png)

**Error decomposition (LSTM).** Cross-track error is the safety-relevant component —
along-track error means an aircraft is late on a route it is still following.

| Horizon | Along-track MAE | Cross-track MAE | Altitude MAE |
|---|---|---|---|
| 1 min | 0.37 NM | 0.13 NM | 99 ft |
| 3 min | 0.83 NM | 0.81 NM | 304 ft |
| 5 min | 1.45 NM | 1.80 NM | 510 ft |
| 10 min | 2.81 NM | 4.96 NM | 1,109 ft |

**Where the remaining error lives** (10 minutes, % within 5 NM):

| Regime | LSTM | | Regime | LSTM |
|---|---|---|---|---|
| Straight flight | 64.3% | | Level flight | 70.1% |
| Gentle turn | 63.1% | | Gentle climb/descent | 42.8% |
| Moderate turn | 49.9% | | Fast climb/descent | 32.7% |
| **Sharp turn (>30°)** | **21.2%** | | En-route (>100 NM from VABB) | 68.3% |
| | | | **Terminal (<40 NM from VABB)** | **34.8%** |

## Two findings that must not be buried

**1. A non-neural tree beats the LSTM at ten minutes, and has on every split measured.**
`HistGradientBoostingRegressor` with `absolute_error` on identical features reaches 65.7%
against the LSTM's 61.3% — a **4.4-point lead**. Across three test splits the gap has been
8.1, 2.2 and 4.4 points; the tree has never lost. It fits 12 independent models (4 horizons
× 3 axes) against one shared LSTM trunk. **The LSTM must not be described as our best
trajectory model.**

**2. At ten minutes the LSTM is worse than the baseline at the very best predictions.**
Within-1-NM is **24.7% against constant velocity's 29.0%** (tree: 33.1%). The LSTM pulls the
whole distribution inward — mean 10.30 → 6.41 NM — but sacrifices some already-near-perfect
predictions doing it. This is the SmoothL1 beta tension; `beta = 0.05` is the best setting
found and raising it makes this worse, not better.

Training was overfitting rather than under-trained on all three runs: validation loss flat
from ~epoch 12 while training loss kept falling. More epochs will not close the tree gap.

---

# Model 1b — Multi-path prediction

40 route patterns (KMeans on the ten-minute residual, fitted on a class-balanced sample),
a `HistGradientBoostingClassifier` mapping the 83 flattened features to a pattern, top
**K = 5** returned with renormalised probabilities.

The justification is measured, not assumed: two aircraft in an **identical** situation end
up **7.9 NM apart on average** at ten minutes, and 64% of such pairs finish more than 5 NM
apart. The future is genuinely uncertain, not merely hard — whether a controller turns an
aircraft now or in two minutes is information we never receive. For conflict detection we
never have to pick one: check every plausible path and warn if any conflicts.

| Method | Arrivals (<40 NM from VABB) | All test traffic |
|---|---|---|
| Constant velocity | 15.8% | 50.5% |
| Single-answer residual LSTM | 34.8% | 61.3% |
| Multi-path, 1 option | 38.6% | 64.0% |
| Multi-path, 3 options | 57.9% | 79.0% |
| **Multi-path, 5 options (shipped)** | **63.6%** | **83.0%** |
| Multi-path, 10 options | 68.8% | 86.5% |

![Best-of-K](docs/figures/multipath_bestofk.png)

> **63.6% is best-of-5, not accuracy.** It means one of the five candidates landed within
> 5 NM. Top-1 is 38.6%. Both are true and they measure different things. The conflict
> checker examines all five, so a hit on any is a genuine hit — but this must never be
> reported as "the model predicts the right answer 63.6% of the time."

## Calibration

The raw classifier was badly over-confident: when it said 90%, it was right 67% of the time.
Temperature scaling (Guo et al. 2017) fits one scalar on the validation split. It is
**monotone by construction**, so the top-5 set and every best-of-K figure above are
provably unchanged — only the stated probabilities move.

| | Before | After |
|---|---|---|
| Fitted temperature | — | **1.729** |
| Calibration error, arrivals | 0.054 | **0.019** |
| Calibration error, all test | 0.040 | **0.012** |

![Multi-path calibration](docs/figures/multipath_calibration.png)

This matters directly: the tier thresholds (0.85 tier 1, 0.60 tier 2) are compared against
these numbers. **The thresholds have not been revisited against the calibrated values yet.**

---

# Model 2 — Conflict classifier

XGBoost (300 trees, depth 6, lr 0.05, `scale_pos_weight` for ~6% positives) over 24 pairwise
features. **Features come from the constant-velocity prediction; the label comes from where
two real aircraft actually went.** Both aircraft are real; only the pairing is manufactured,
by moving one aircraft's entire real future track as a rigid piece — so every real turn,
climb and speed change survives exactly.

**Dataset:** 40,000 encounters, 2,581 real conflicts (6.45%), 31 sessions.
**Test:** 4,690 rows, 303 real conflicts (6.46%), strictly later than train and validation.

## Leakage guard

The previous version of this dataset was circular: two of its nine features were the
extrapolated CPA distances and the label was the separation rule applied to those same two
numbers. Recomputing the label from those features alone reproduced it for **40,000 of
40,000 rows — exactly 100.00%**, which fully explained its reported PR-AUC of 1.0.

After the rebuild, the separation rule applied to the predicted CPA reproduces the label for
**95.60%** of rows. The 1,760 disagreeing rows *are* the learning problem.
`assert_no_leakage()` refuses to train above 99%.

## Results

| Method | Recall | Precision | F-β(2) | FA/1000 | Missed | Headline (≥3 min) |
|---|---|---|---|---|---|---|
| Rule at legal minimum 5 NM / 1000 ft | 0.8251 | 0.6203 | 0.7740 | 32.6 | 53 | 81.7% |
| Rule at alert volume 8 NM / 1500 ft | 0.8812 | 0.4356 | 0.7315 | 73.8 | 36 | 87.3% |
| **XGBoost at threshold 0.0851** | **0.9439** | 0.3865 | 0.7326 | 96.8 | **17** | **94.0%** |

**PR-AUC 0.804** against a conflict rate of 0.065. Median warning time on caught
conflicts: **330 s**.

![PR curve](docs/figures/classifier_pr.png)

![Confusion matrix](docs/figures/confusion_classifier.png)

|  | Really a conflict | Not a conflict |
|---|---|---|
| **Alert raised** | 286 (TP) | 454 (FP) |
| **No alert** | 17 (FN) | 3,933 (TN) |

**Why it beats the rule, and it is explainable.** Of the real conflicts the alert-volume
rule misses, **99.0% are vertical misses**: the pair is correctly predicted to pass within
8 NM laterally, but straight-line extrapolation puts them a median **2,825 ft** apart
vertically when they actually end up **498 ft** apart. On those rows the faster climber's
vertical rate is a median **2.60 m/s against 0.33 m/s across all rows** — eight times
higher. The model learned to distrust predicted vertical separation when an aircraft is
climbing or descending hard. The top SHAP contributions agree:

| Feature | Mean abs. SHAP |
|---|---|
| `predicted_cpa_lateral_nm` | 1.954 |
| `current_vertical_separation_ft` | 1.792 |
| `predicted_cpa_vertical_ft` | 1.183 |
| `predicted_time_to_cpa_seconds` | 0.427 |
| `closing_speed_ms` | 0.334 |
| `vertical_convergence_rate_ms` | 0.240 |
| `min_distance_to_vabb_nm` | 0.194 |
| `a_altitude_ft` | 0.183 |

## Calibration

Platt scaling on validation. Sigmoid rather than isotonic because it is strictly monotone:
the threshold is mapped through the same function, and the script **raises if the test alert
set differs by a single row**.

| | Brier | Calibration error |
|---|---|---|
| Raw XGBoost | 0.0298 | 0.0322 |
| **Platt-calibrated** | **0.0236** | **0.0074** |

**The alert set is identical before and after — the same 740 situations are flagged.**
Calibration changed what the number *means*, not who gets warned. That property is worth
keeping: recalibrating can never silently change who is alerted.

![Classifier calibration](docs/figures/classifier_calibration.png)

## Gates

| Gate | Result |
|---|---|
| **1. Recall ≥ 0.95** | **FAIL — 0.9439** |
| 2. Beats the rule-based detector on F-β(2) | PASS — 0.7326 vs 0.7315 |

**Gate 1 fails and was not tuned away.** The cause is diagnosed and is not a defect in the
model: `select_threshold` returns the *highest* threshold still meeting the floor on
validation, which by construction lands exactly on the edge (validation recall 0.9511). A
later, different test split then falls slightly below. Selecting for a small margin above
the floor is the obvious remedy, but it **changes when a controller is alerted**, so it
needs Archit's sign-off. The what-if table is printed for that decision and **not applied**:

| Margin | Threshold | Test recall | Precision | FA/1000 | Missed | Headline | Gate 1 |
|---|---|---|---|---|---|---|---|
| **0.000 (shipped)** | 0.0851 | 0.9439 | 0.3865 | 96.8 | 17 | 94.0% | FAIL |
| 0.005 | 0.0809 | 0.9439 | 0.3798 | 99.6 | 17 | 94.0% | FAIL |
| 0.010 | 0.0717 | 0.9439 | 0.3562 | 110.2 | 17 | 94.0% | FAIL |
| 0.020 | 0.0479 | **0.9637** | 0.3026 | 143.5 | 11 | **96.1%** | **PASS** |

Set `FLIGHT_RIGHT_RECALL_MARGIN` to apply one; the chosen value is written into the model
card so the decision is on record with the numbers it was made from.

**Gate 2 is now marginal and should not be glossed over.** The margin is 0.0011, where the
previous run had 0.7480 vs 0.7315. Recall rose (0.9406 → 0.9439) but precision fell
(0.4113 → 0.3865). The model still beats the rule on every individual comparison, but on the
combined measure it is barely ahead. Watch this on the next run.

---

# Model 3 — Resolution engine

Rule-based. For a confirmed tier 1 alarm it proposes up to three ways out — one altitude,
one heading, one speed — each with resulting separation, delay and fuel estimates,
confidence, and a controller-readable sentence. Ranked by the project's fixed weights:
safety 0.60, delay 0.15, fuel 0.10, workload 0.10, confidence 0.05.

**Manoeuvres are flown, not teleported.** Every candidate is simulated at 1-second
resolution through `RESPONSE_DELAY_SECONDS = 38` during which **nothing moves**, then at
real rates: standard rate turn 3°/s, level change 1,500 ft/min, speed change 0.35 m/s².
The naive version would move the aircraft instantly and report conflicts solved that
physically cannot be — wrong in the dangerous direction.

**Measured over all 41 tier 1 alarms in the test split:**

| | Count |
|---|---|
| Candidate instructions evaluated | 1,066 |
| Blocked as unsafe (outside the flight envelope) | 0 |
| Rejected — separation still lost | 565 |
| Alarms producing at least one option | 31 |
| **Alarms where nothing works** | **10** |
| **Instructions actually offered** | **77** |
| — for real conflicts | 36 |
| — for conflicts that never happen | **41 (53.2%)** |

![Model 3 options by time](docs/figures/model3_options.png)

**At 90 seconds to closest approach, all 26 candidate instructions are rejected.** Not the
climb, not the turn, not the speed change. 38 of those 90 seconds are gone before the
aircraft moves. This is independent confirmation of the three-minute tier boundary, reached
by simulation rather than by the pencil calculation that set it.

**Checked against the whole picture.** Each option is tested against the other aircraft's
five weighted predicted futures (must work across futures carrying ≥95% of the probability)
**and** against every other nearby aircraft. Verified by hand: descending 6E455 by 2,000 ft
resolves its conflict with AI2841 and puts it head-on into UK955, losing separation at 79 s.
The engine rejects it and names UK955. That is the domino effect, a named failure in the
literature with level changes as its most common cause.

Delay and fuel are coarse track-mile proxies with a climb cost of 120 equivalent
cruise-seconds per 1,000 ft. No engine data, no weight, no wind. Good enough to rank three
options against each other; every explanation string says "approximate".

---

# What actually reaches the controller

This is the section that matters operationally, and it is not what the classifier's
precision of 0.386 suggests on its own.

Between detection and the dashboard sits `ml_pipeline/utils/alert_feed.py`, which
suppresses repeat interruptions and collapses low-confidence watch-list rows. **Both are
display decisions.** The guarantee is structural: every pair the escalation rule confirms
is on the `active` list on every update, and the module contains no code path that removes
one. Suppression can only change whether a pair raises a *new* interruption, and whether it
gets its own row or sits in a counted group.

![Alert funnel](docs/figures/alert_funnel.png)

## Confusion matrix of the warnings shown to the controller

![Frontend confusion matrix](docs/figures/confusion_frontend.png)

| What the controller sees | Really a conflict | Not a conflict | Precision |
|---|---|---|---|
| **Own alert row (prominent)** | **279** | **276** | **0.503** |
| Collapsed group (still on screen, expandable) | 7 | 178 | 0.038 |
| Not shown at all | **17 (missed)** | 3,933 | — |
| **Removed from the active list** | **0** | 0 | — |

Broken down by tier — tier 1 is the audible alarm that also carries manoeuvres, tier 2 is a
silent watch-list row:

| Tier | Rows | Real | False | Precision |
|---|---|---|---|---|
| **1 — alarm (0–3 min)** | 41 | 27 | **14** | **0.659** |
| 2 — watch list (3–10 min) | 699 | 259 | 440 | 0.371 |

**96.9% of all false alarms are silent watch-list rows, not interruptions.** The alarms
themselves are right about two thirds of the time. The often-quoted "six in ten alerts are
wrong" is true of the raw alert count and misleading about the controller's experience —
provided the dashboard renders tier 2 as a passive list, which is its obligation.

## The seven real conflicts in the collapsed group

Seven real conflicts fall into the low-confidence group. This is the honest cost, so here is
exactly what happens to them: **all seven are tier 2 with 6 to 9 minutes of real warning**
(360–540 s), all seven stay on the active list throughout, and each is released into a full
alarm as it closes inside three minutes. That release is an automated check, not an
assumption. All seven therefore reach the controller with more than three minutes in hand —
which is precisely what the headline metric measures.

Four things can **never** be collapsed, whatever the model says: a tier 1 alarm, a pair the
deterministic geometric rule calls a conflict, anything at high or critical severity, and
anything carrying resolution options. The geometric rule outranking the model is deliberate:
it is the safety net and a probability does not get to overrule it.

![Precision by band](docs/figures/precision_by_band.png)

## Repeat suppression, measured on real traffic

Without memory, one converging pair alerts once per surveillance update for as long as the
geometry lasts. Two real one-hour OpenSky sessions replayed twice — with the feed and
without — comparing the **sets** of pairs reported:

| Session | Pairs reported before | Pairs on active after | **Lost** | Interruptions before | after | Cut |
|---|---|---|---|---|---|---|
| 05 Sep, 00:30 IST | 20 | 20 | **0** | 241 | 89 | 63.1% |
| 03 Sep, 20:45 IST | 10 | 10 | **0** | 119 | 42 | 64.7% |

Total active rows rendered equals the old message count exactly (241 and 119) — the direct
proof that no confirmed pair-update left the display.

![Interruptions](docs/figures/feed_interruptions.png)

**The cut is 64%, not the 90% a raw encounter count suggests, and the gap is deliberate.**
Every one of the 131 remaining interruptions is a real change of state: 65 crossed into a
shorter time band, 30 were genuinely new, 23 closed by more than 1 NM, 12 escalated to
tier 1, 1 rose in severity, and **0 were the heartbeat** — the heartbeat is a backstop that
never had to fire. The ~26 points between 64% and 90% is what the safety re-announcements
cost, and they are worth it.

---

# Rejected experiments, with the numbers

Recorded so they are not retried. All measured on our own data.

| Idea | Result | Verdict |
|---|---|---|
| **MSE for trajectory loss** | 6.4% within 1 NM at 10 min, vs 27.7% for SmoothL1(β=0.05) and 30.0% for the physics baseline | Rejected — optimises the average, destroys near-perfect predictions |
| **SmoothL1 with β=1.0** | 6.1% — as bad as MSE, because the quadratic region covers most of the data | Rejected — keep β=0.05 |
| **Bidirectional LSTM** | 56.7% vs 58.0% at 10 min, 2.5× the parameters | Rejected — no future to read backwards from at inference |
| **Tripling the input window (99 s → 316 s)** | No improvement at any horizon, costs 29% of the dataset | Rejected |
| **Per-horizon equal loss weighting** | 63.7% vs 64.5% | Rejected |
| **Warn only when probability is climbing** | Removed 4 false alarms and **5 real conflicts**; recall 93.8% → 62.5% for precision 62.5% → 66.7% | Rejected — the trend is noise (±0.04/update) |
| **Level-flight filter** | Cuts 46% of false alarms, costs **21 real conflicts**; recall 0.9439 → 0.875, headline 94.0% → **86.6%** | Rejected — see below |

## Why the level-flight filter failed, and why it is worth reporting

64.8% of false alarms are pairs that came close laterally but stayed stacked vertically —
median real closest approach **2.44 NM / 1,930 ft**, against 1.69 NM / 535 ft for true
conflicts. Suppressing pairs where both aircraft read level and the predicted vertical gap
already clears 1,000 ft is the obvious fix, and it is what real systems do.

It fails here because those 21 lost conflicts reported **0.00–0.33 m/s vertical rate at
decision time and then descended.** Several were predicted 2,200–2,450 ft apart and ended
240–530 ft apart. "Level now" does not mean "level in ten minutes" — the descent comes from
a controller instruction we never receive.

EUROCONTROL's STCA guidelines list this exact technique as Option E: *"Cleared and/or
Selected Flight Level used for Vertical Prediction in Linear Prediction Filter — Reduces
nuisance alerts, particularly for level off situations. Can give extra warning time, **but
reduces warning time in the event of level bust**."* Real STCA runs it because the flight
data processing system supplies the cleared level. Our proxy is observed vertical rate, and
level bust is exactly what a proxy misses.

**This is a concrete, measured justification for the standing caveat that production use
would need certified surveillance and flight plans** — not a generic disclaimer.

---

# Known gaps and honest caveats

1. **Precision would be worse in the field, not better.** The test set is 6.46% real
   conflicts because 55% of pairings were deliberately aimed. Real airspace is far sparser
   in conflicts, so the 0.386 figure is optimistic. It is a relative comparison against the
   rule on identical data, not a field forecast.
2. **En-route only.** Conflict detection is restricted to ≥10,000 ft and >50 m/s. Applying
   the en-route 5 NM rule to all traffic flagged pairs in **91–94% of all snapshots**, with
   65% of flagged pairs involving an aircraft below 2,000 ft. Terminal separation is 3 NM
   (and 2.5 NM on final approach) with vertical **unchanged at 1,000 ft** — implementing it
   needs its own labelled dataset, which we do not have.
3. **The altitude gate lives in the training-data generator, not at inference.**
   `assess_pair` has no altitude filter. The API layer must add one.
4. **`classify_conflict`'s severity ladder hardcodes en-route numbers** (3.0 NM / 700 ft for
   critical, 5.0 NM for high) rather than deriving them from its own threshold parameters.
   Passing terminal thresholds would give a correct `is_conflict` and a wrong severity.
5. **Tier thresholds (0.85 / 0.60) have not been revisited against the now-calibrated
   probabilities.**
6. **Model 1's numbers drift ~0.1 points between runs** from cuDNN kernel non-determinism.
   Stages 1, 3, 5 and 6 reproduce bit-for-bit.
7. **Nothing is wired end to end.** `server/app/ml/inference.py` runs the full chain for a
   pair, but there is no API, no database, and the dashboard still runs on `mockData.js`.
   Every number here is measured offline.
8. **This is not a certified system.** OpenSky is not a certified feed. Separation values
   are simplified academic thresholds, not full regulatory standards.

# Verification

`python ml_pipeline/utils/verify_pipeline.py` — **110 checks, all passing.** It loads every
saved artifact in a fresh process with no access to the training scripts and asserts on
shape, magnitude and the known traps: that masked-out targets really are zero, that
`apply_residual(residual_targets(y))` round-trips to 1e-9 degrees, that the test split starts
after validation ends, that the saved feature list equals `FEATURE_COLUMNS`, that **the label
is not recomputable from the features**, that a confirmed alarm carries ranked explained
options, that a third aircraft is named when a manoeuvre is rejected for endangering it, and
that every confirmed pair stays on the active list on every update.

Plus 8 unit tests (`ml_pipeline/tests/test_units.py`) and an end-to-end smoke test on
synthetic data whose gate values are meaningless by design and are never quoted.
