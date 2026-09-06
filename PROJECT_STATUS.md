# Flight Right — Where The Project Stands

**Written 5 September 2026, updated 6 September 2026.** Plain English, no assumed knowledge of machine
learning or aviation. Every aviation word is defined the first time it is used.

This document answers five questions: where are we, what does each file do, what exactly
is the LSTM doing, what was wrong with the conflict classifier and how it was fixed, and
what the resolution engine proposes.

---

## 0. The aviation words you need, once

You do not need to know aviation to read the rest of this. You need nine words.

| Word | What it means |
|---|---|
| **Nautical mile (NM)** | A distance unit used in aviation. 1 NM = 1,852 metres, about 1.15 ordinary miles. |
| **Knot** | One nautical mile per hour. An airliner cruises around 450-500 knots. |
| **Heading / track** | Which compass direction the aircraft is pointing, in degrees. 0 = north, 90 = east, 180 = south, 270 = west. |
| **Altitude** | Height above sea level. We store it in metres and report it in feet. A cruising airliner is around 35,000 ft. |
| **Vertical rate** | How fast it is climbing or descending, in metres per second. Positive is up, negative is down. |
| **Separation** | The legally required gap between two aircraft. In our simplified academic version: 5 NM apart sideways, **or** 1,000 ft apart vertically. Either one alone is enough to be safe. |
| **Conflict** | Two aircraft predicted to end up closer than that gap. Not a crash. A rule violation that a controller must prevent. |
| **CPA (Closest Point of Approach)** | The moment in the future when two aircraft will be nearest to each other, and how near that is. This is the core thing we compute. |
| **En-route vs terminal** | En-route = cruising high, far from the airport. Terminal = near the airport, climbing out or coming in to land. They follow different separation rules, which matters a lot later. |

Two more, specific to us:

- **VABB** is the airport code for Mumbai. Everything is measured relative to it.
- **ADS-B** is the system by which aircraft broadcast their own position, speed and
  altitude over radio, roughly once a second. Anyone with a receiver can listen.
  **OpenSky Network** is a free public service that collects these broadcasts
  worldwide and hands them out over the internet. That is where all our real data
  comes from. It is not a certified air-traffic-control feed, and we must always say
  so.

---

## 1. The one number

> **Percentage of conflicts caught with at least 3 minutes of warning: 93.7%.**

Everything else in this document is a supporting detail.

**Read the basis, not just the number.** This was 93% before 5 September. That older
figure was scored against an answer key the straight-line arithmetic had written
itself, so it measured whether the arithmetic agreed with the arithmetic. The 93.7% is
scored against where real aircraft actually went. The two landing so close together is
a coincidence, not a continuity. What genuinely improved is that the number now means
something. On the same honest basis the straight-line rule scores 87.3%.

Three minutes is not a round number chosen for neatness. It is how long the human
loop physically takes:

| Step | Time |
|---|---|
| Controller sees the alert and decides | 15 s |
| Radio call to the pilot, and the pilot reads it back | 15 s |
| Pilot actually starts moving the aircraft | 8 s |
| **Nothing has moved yet** | **38 s** |
| Then: a 1,000 ft climb or descent takes | ~40 s |
| Or: a 30-degree turn at 450 knots takes | ~96 s |

So the minimum useful warning is about 90 seconds for a height change and about 135
seconds for a turn. Three minutes is that, with margin. A warning shorter than this
is technically correct and operationally useless.

**Where the 93.7% comes from.** It is measured by
`ml_pipeline/training/conflict_classifier/train_xgboost.py` on 4,690 held-out
encounters from 4 and 5 September, all later in time than anything the model trained
on. Both aircraft in every encounter are real, and the answer comes from their real
recorded positions.

---

## 2. Status at a glance

| Component | Status |
|---|---|
| Data collection from OpenSky | **WORKING.** 35 raw session files on disk; the last full run used 627,344 airborne positions. |
| Model 1 — trajectory prediction (LSTM) | **DONE.** Beats the physics baseline at all four time horizons. |
| Model 1b — multi-path prediction | **DONE.** Its confidence numbers were wrong (Section 5); the correction is now coded and will be measured on the next real training run. |
| Model 2 — conflict classifier (XGBoost) | **WORKING** as of 5 Sep. Rebuilt so it no longer restates the rule it was handed. See Section 6. |
| Rule-based conflict detection | **WORKING.** This is the safety net and it is sound. |
| Automated end-to-end check | **WORKING** as of 6 Sep. 80 of 80 checks pass. |
| Model 3 — resolution recommendations | **DONE (rule-based)** as of 6 Sep. Three explained, ranked options per alarm. |
| **Training pipeline** | **ONE COMMAND** since 6 Sep: `python ml_pipeline/run_pipeline.py`. See `ml_pipeline/README_TRAINING.md`. |
| **Backend server (FastAPI)** | **NOT STARTED**, but `server/app/ml/inference.py` now runs the complete chain for a pair, ending in Model 3's ranked suggestions. The web API on top is next. |
| **Frontend dashboard** | **Back on this branch** (6 Sep, restored from `main`). Runs on mock data until the backend exists. |

### The backend, specifically, since you asked

**There is no backend.** Not "partially built" — there is no server code at all.

Here is literally everything inside `server/`:

```
server/requirements.txt              a list of Python libraries to install
server/app/api/.gitkeep              empty placeholder folder
server/app/db/.gitkeep               empty placeholder folder
server/app/models/.gitkeep           empty placeholder folder
server/app/services/.gitkeep         empty placeholder folder
server/app/ml/saved_models/          <- the only real content
    trajectory_residual.pt           the trained LSTM             (0.9 MB)
    trajectory_multipath.pkl         the trained multi-path model (83 MB)
    xgboost_conflict.json            the trained classifier       (0.5 MB)
    bilstm_trajectory.pt             an obsolete old model        (2.2 MB)
```

A `.gitkeep` file is an empty file whose only purpose is to make Git keep an
otherwise-empty folder. So the folder structure for the backend was planned and
created, and then nothing was put in it.

Not started, from CLAUDE.md Section 5: every API endpoint, the WebSocket live-update
stream, the PostgreSQL database, and the audit log. None of these exist.

### The frontend

**Update 6 Sep:** `client/` is back on this branch, restored from `main`. The paragraph below is history.

CLAUDE.md Section 8 says the React dashboard exists and works against mock data.
**On this branch it did not exist until 6 Sep.** It was deleted by commit `9b6800b` on
30 August, which retired the old Express and React code so the branch would contain
only the Python pipeline.

Nothing is lost. It is recoverable with:

```
git checkout 91720e7 -- client
```

This is worth knowing before any demo is planned, because "wire the frontend to the
backend" currently means restoring the frontend first.

---

## 3. Every file that carries code, explained

18 Python files, about 5,900 lines. Grouped by job.

### 3a. Getting the data — `ml_pipeline/ingestion/`

| File | Lines | What it does |
|---|---|---|
| `fetch_once.py` | 133 | Asks OpenSky for one single snapshot of every aircraft over western India right now, and saves it. A test that the connection works. |
| `scheduled_poll.py` | 331 | The real collector. Asks repeatedly, every 10 seconds for 90 minutes, and saves the whole session as one file. |
| `scheduled_poll_b.py` | 342 | Same, using a second OpenSky account. |
| `scheduled_poll_c.py` | 342 | Same, using a third OpenSky account. |

Why three near-identical files: OpenSky limits each free account to 4,000 "credits"
per rolling 24 hours, and one 90-minute session costs 1,080. Three accounts means
three sessions per day. The box we ask about is western India, from latitude 16 to
23.5 and longitude 68 to 77.5, which contains Mumbai.

**Correction (6 Sep).** An earlier version of this note said there was no incremental
saving. The current scripts write a `_partial.parquet` checkpoint every 60 polls (about
ten minutes), so a hard kill now loses at most the last ten minutes rather than the
session. The 30 August loss of 249 snapshots happened before that was added.

### 3b. The physics baseline — `ml_pipeline/utils/trajectory_baseline.py` (78 lines)

The simplest possible prediction: *this aircraft will keep going in exactly the same
direction, at the same speed, climbing or descending at the same rate.* Straight-line
arithmetic. No learning of any kind.

This tiny file is the most important one in the project. Every model is measured
against it, in the same run, on the same data. A model that cannot beat it is
worthless, and the project has already been burned once by not checking: a model that
lost to this arithmetic at every horizon went unnoticed for three weeks.

### 3c. Geometry and rules — `ml_pipeline/utils/cpa_conflict_detection.py` (421 lines)

The heart of the deterministic system. Given two aircraft, it answers: when will they
be closest, how close, and is that a problem?

What it holds:

- **The dense grid.** It checks separation every 15 seconds from now to 10 minutes —
  41 checkpoints. It used to check only 4 (at 1, 3, 5 and 10 minutes), which missed
  conflicts happening in between. Measured: **21.4% of real conflicts were invisible**
  to the 4-point version.
- **The two thresholds.** Legal separation is 5 NM / 1,000 ft. We *alert* at the wider
  8 NM / 1,500 ft, deliberately, because a prediction that is 1 NM off would otherwise
  flip the answer. At the bare legal minimum we catch 46% of conflicts; at the wider
  volume, 99% at one minute and 93% at three.
- **Two tiers.** Tier 1 (0-3 minutes) raises a real alert and offers a fix. Tier 2
  (3-10 minutes) adds a watch-list row and **never** suggests a manoeuvre, because a
  ten-minute prediction is not accurate enough to justify turning an aircraft.
- **Anti-flicker.** A pair must qualify on 3 consecutive updates before alerting, so
  one bad radio report cannot cause a false alarm.

### 3d. Preparing training data — `ml_pipeline/training/trajectory/`

| File | Lines | What it does |
|---|---|---|
| `preprocess_sequences.py` | 247 | Turns raw snapshots into training examples: 10 past positions in, 4 future positions out. Splits by date. |
| `framing.py` | 204 | The maths that converts between "where on Earth" and "where relative to this aircraft". Shared by training, evaluation and future backend code so they cannot drift apart. |
| `train_trajectory.py` | 318 | Trains the LSTM. Explained fully in Section 4. |
| `evaluate.py` | 207 | Scores predictions, per time horizon and per flight type. Never averages across horizons. |
| `reference_benchmark.py` | 154 | A non-neural gradient-boosted tree on identical data. The standing bar the LSTM must clear. It currently does not. |
| `multipath.py` | 403 | Model 1b. Predicts several possible futures instead of one. Section 5. |

Two details in `preprocess_sequences.py` worth knowing:

- **Targets are interpolated.** If we want to know where an aircraft was at exactly
  60 seconds, and we have readings at 55 s and 68 s, we compute the point between
  them. Previously we snapped to the nearest reading, which introduced up to 5.2 NM
  of pure noise into the answer key.
- **The mask.** An aircraft that lands after 6 minutes has no 10-minute answer. We
  keep it and mark the 10-minute slot invalid, rather than discarding it. Requiring
  all four horizons silently deleted every aircraft landing at Mumbai, biasing the
  data towards easy high-altitude cruising. Keeping them doubled the dataset from
  73,254 to 151,613 examples.

### 3e. The conflict classifier — `ml_pipeline/training/conflict_classifier/`

| File | Lines | What it does |
|---|---|---|
| `generate_synthetic_scenarios.py` | 664 | Pairs up **two real aircraft**, moves one so their paths cross, and records what actually happened to them. |
| `train_xgboost.py` | 411 | Trains the classifier, and refuses to run if the answer key can be worked out from the questions. |

Both were rewritten on 5 September. Section 6 explains what was wrong and what changed.

### 3f. Checks — `ml_pipeline/utils/`

| File | Lines | What it does |
|---|---|---|
| `verify_pipeline.py` | 659 | **The automated check.** Runs 80 assertions across the whole pipeline and exits non-zero if any fails. |
| `resolution_engine.py` | 699 | **Model 3.** Proposes, simulates, costs and explains ways out of a conflict. See section 7. |
| `test_baseline_demo.py` | 65 | Sanity check that the physics baseline and CPA rules run on real data. |
| `test_two_tier_demo.py` | 247 | Checks the two-tier alerting on three hand-built situations: a conflict hiding between horizons, a one-off bad reading, and a pair that safely passes. |

`verify_pipeline.py` was added on 6 September and closes what had been a real gap. Run it
with one command and it prints PASS or FAIL for every check:

```
venv/Scripts/python.exe ml_pipeline/utils/verify_pipeline.py
```

It opens each saved model the way the future backend will, cold, with no help from the
training scripts, and asks three kinds of question. Is the output the right shape, so
does the trajectory model really return four future positions each with a latitude, a
longitude and an altitude? Are the numbers physically sensible, so are the predicted
positions actually over western India at possible altitudes? And are the known traps
still shut, so can the conflict answer key still be worked out from the questions, and
is the test data still strictly later than the training data?

It also walks two aircraft the whole way through to a controller alert and on into the
resolution engine, including a pair deliberately set on a collision course. It checks the
alarm refuses to fire on a single reading but does fire once the situation has held for
three readings, that every suggestion offered genuinely restores a safe gap and carries an
explanation, and that an unsafe instruction is blocked rather than offered.

These are demonstration scripts you run and read. **Since 6 September there is also an
automated test suite** in `ml_pipeline/tests/`: `test_units.py` (8 unit tests, no data
needed) and `smoke_test.py` (runs the entire pipeline on invented data in a temporary
folder, then loads the models through the backend module). Run them with
`python -m unittest ml_pipeline.tests.test_units` and `python ml_pipeline/tests/smoke_test.py`.

### 3g. Added 6 September 2026

| File | What it does |
|---|---|
| `ml_pipeline/run_pipeline.py` | Runs the seven training steps in order with one command, logs each, writes a report. |
| `ml_pipeline/check_environment.py` | Says whether this laptop can train: GPU visible, packages, data present. |
| `ml_pipeline/README_TRAINING.md` | Setup and run instructions for the RTX 4060 laptop. |
| `server/app/ml/inference.py` | Loads the models; `assess_pair` runs rule → multi-path → classifier → tier → **Model 3 suggestions** for two aircraft. |
| `ml_pipeline/tests/*` | The tests above, plus `inference_check.py` which runs one converging pair through the loaded models. |

---

## 4. Model 1, the LSTM, explained from scratch

### 4a. What problem it solves

Given where an aircraft has been for the last minute and a half, predict where it
will be in 1, 3, 5 and 10 minutes.

### 4b. What an LSTM is, in one paragraph

LSTM stands for Long Short-Term Memory. It is a type of neural network built for
data that arrives in order, where what happened earlier changes the meaning of what
happens later. It reads a sequence one step at a time and carries a running memory.
For us: it reads ten position reports in order, and the memory lets it notice things
like "this aircraft has been steadily turning left for the last thirty seconds",
which no single report contains on its own.

Ours has 2 layers, a memory of 128 numbers, and reads **forwards only**. There is a
variant called bidirectional that also reads backwards. We tested it and rejected it,
because reading the past in reverse cannot reveal the future, and at prediction time
there is no future inside the input to read. It scored worse (56.7% vs 58.0%) with
2.5 times the parameters.

### 4c. What goes in

Ten consecutive position reports, covering about 100 seconds (measured median 101 s, mean 126 s). Crucially, **nothing
is given as an absolute world position.** Everything is expressed relative to where
the aircraft is right now and which way it is pointing.

Per report, 7 numbers:

| Input | Plain meaning |
|---|---|
| `along_track_m` | How far behind its current position it was, in its own direction of travel |
| `cross_track_m` | How far to the left or right of its current line it was |
| `altitude_delta_m` | How much higher or lower it was |
| `velocity_ms` | Speed at that moment |
| `vertical_rate_ms` | Climb or descent rate at that moment |
| `heading_delta_rad` | How much its direction differed from its current direction |
| `time_gap_s` | Seconds since the previous report |

Plus 13 summary numbers about the whole window, including turn rate, total turn,
acceleration, vertical acceleration, distance to Mumbai airport, and whether the
airport is ahead of or behind the aircraft.

**Why relative and not absolute.** This is the single most important design decision.
The first version fed in raw latitude and longitude, and it failed completely — it
learned to answer "somewhere over the Mumbai region" for every aircraft. Two reasons:

1. Raw latitude and longitude were scaled against the whole collection region, about
   1.9 degrees of latitude. 5 NM — the difference between a useful and a useless
   prediction — is 0.083 degrees, i.e. **4.5% of one standard deviation.** The entire
   range from perfect to worthless was invisibly small to the model.
2. The aircraft's movement inside its own 10-step window was **1.9%** of one standard
   deviation of the latitude feature. The model could see *where* the aircraft was
   but not *which way it was going.*

Also: the original input list was position, altitude, speed, direction, vertical
rate. **None of those describes change.** The model was never told an aircraft was
turning. That is why turn rate and total turn are now explicit inputs.

One small but real bug fixed along the way: compass headings wrap around at 360. An
aircraft going from 359 degrees to 001 degrees has turned 2 degrees, but naive
subtraction reads it as a 358-degree turn. The code "unwraps" headings before
comparing them. Without this, the turn features were nonsense for exactly the
northbound traffic they were meant to describe.

### 4d. What comes out — and the clever part

The model does **not** output a position. It outputs a **correction to the physics
baseline.**

For each of the four horizons it produces three numbers, in metres:

- how much further along its track than the straight-line guess
- how much to the side of the straight-line guess
- how much higher or lower than the straight-line guess

The pipeline adds these to the straight-line prediction to get a real latitude,
longitude and altitude.

**Why this matters enormously.** If the model outputs zero, you get the physics
baseline exactly. So the model *starts* at the physics and can only be moved off it
by evidence. It cannot do worse than plain arithmetic without actively working at it.
Compare the earlier design, which had to rediscover geography and arithmetic from
nothing and never got there.

It also means the baseline is now impossible to delete by accident. It is not a
comparison sitting beside the model, it is inside the model.

### 4e. How good is it

Test data is 6 collection sessions from 4-5 September, never seen during training,
all later in time than every training example.

| Time ahead | Physics baseline | **LSTM** | Tree reference |
|---|---|---|---|
| 1 minute | 98.4% | **98.5%** | 98.5% |
| 3 minutes | 89.5% | **92.1%** | 92.6% |
| 5 minutes | 77.3% | **83.2%** | 85.1% |
| 10 minutes | 50.5% | **60.9%** | 65.7% |

The figures are the percentage of predictions landing within 5 NM of the truth. The
LSTM beats the physics baseline at every horizon, which is the gate, and it passes.

**Three honest caveats, none of which should be hidden:**

1. **A simpler non-neural model is still better.** A gradient-boosted tree reaches
   65.7% at ten minutes against the LSTM's 60.9%. It has beaten the LSTM on all three
   test splits measured so far, by between 2 and 8 points. Do not describe the LSTM
   as the best available.
2. **One metric went backwards.** At ten minutes the LSTM lands within 1 NM only
   25.2% of the time, against the physics baseline's 29.0%. It pulls the whole error
   distribution inward — average error drops from 10.30 to 6.41 NM — but sacrifices
   some already-near-perfect predictions to do it.
3. **The hard cases stay hard.** At ten minutes: sharp turns 22.8%, fast climbs and
   descents 28.6%, traffic near the airport 35.8%, against 67.9% for cruising
   traffic. Neither model knows the aircraft's intended route or its clearance.

### 4f. The ceiling nobody can train past

Take two aircraft in an **identical** situation — same position, altitude, heading,
descent rate. Ten minutes later they are an average of **7.9 NM apart**, and 64% of
such pairs end more than 5 NM apart.

The information that decides the difference is a controller's radio instruction, and
we never receive it. This is uncertainty in the world, not error in the model. No
larger model fixes it. It is why Model 1b exists.

---

## 5. Model 1b, multi-path

Instead of one answer, produce five, each with a probability.

It works by learning 40 typical route patterns from historical data, then predicting
which patterns this aircraft is likely to follow. For conflict detection we never
have to choose: we check all five, and warn if **any** of them conflicts. Safety
comes from covering the possibilities, not from guessing right.

Measured on arrivals into Mumbai at ten minutes:

| Method | Within 5 NM |
|---|---|
| Physics baseline | 15.8% |
| Single-answer LSTM | 35.8% |
| Multi-path, best of 5 | **63.6%** |

**Do not misreport this.** 63.6% means *one of the five* candidates was close. The
top single guess is right 38.6% of the time. Both numbers are true and they answer
different questions.

**What is broken here.** The probabilities are badly wrong, always in the
over-confident direction:

| It claims | It is actually right |
|---|---|
| 90% | 67% |
| 85% | 41% |
| 65% | 28% |

This matters because the alerting thresholds are 0.85 for tier 1 and 0.60 for tier 2.
Those numbers were chosen for a *truthful* probability. Fed an inflated one, tier 1
fires more readily than its stated confidence justifies.

Worse in the other direction: below a stated 0.20, the true risk is **higher** than
claimed. A genuinely risky pair can sit unnoticed in the background list. That is the
dangerous direction of error.

**The fix, and where it comes from.** Wrap the classifier in scikit-learn's
`CalibratedClassifierCV`, fitted on validation data that the model never trained on.
This is standard practice, not our invention. The technique is Platt scaling and
isotonic regression; scikit-learn's own documentation covers exactly this failure
mode and notes that boosted classifiers are characteristically over-confident:
<https://scikit-learn.org/stable/modules/calibration.html>

Do not touch the tier thresholds until this is done.

---
## 6. Model 2, the conflict classifier — fixed on 5 September 2026

### 6a. What was wrong

The model was being asked a question it had already been given the answer to.

The practice situations took one **real** aircraft and **invented** a second one beside
it. Both were then assumed to fly in a perfectly straight line, and the answer key was
written by checking whether those two straight lines came too close. But two of the
nine facts handed to the model were *how close those straight lines came*. So the
answer key was calculated from the model's own inputs.

Verified rather than argued:

```
label reproducible from 2 of its own features: 40000 / 40000  (100.0000%)
```

Every row. That is why it scored a perfect 1.0. A perfect score on a real-world task is
evidence of a broken setup, not a good model. The name for this is **target leakage**:
an input that already contains the answer. The standard reference is Kaufman, Rosset and
Perlich, *Leakage in Data Mining*, KDD 2011, at
<https://dl.acm.org/doi/10.1145/2020408.2020496>

A second, separate problem: 45.5% of practice situations, and 25.3% of the conflicts,
were already at their closest point at the very first moment. No warning to give,
nothing a controller could do. Since warning time is this project's headline metric,
that made the metric unmeasurable.

### 6b. What was changed

**Both aircraft are now real, with real recorded futures.** That is forced by the fix:
an invented aircraft has no real future to check against, so its only future is the
straight line we drew for it, which is what made the old setup circular.

The introduction between them is still manufactured, because genuine near-misses are
vanishingly rare and we would wait forever for one. But aircraft B's real flight path is
picked up and moved as **one rigid piece**, like sliding a photograph across a table and
rotating it. Every real turn, climb, descent and speed change inside it survives exactly.
Only where it is and which way it points change. **Nothing about the flying is invented.**

Then the split that matters:

- **What the model is told:** what our straight-line prediction says will happen, plus
  how much that prediction can be trusted. That last part is new and it is the load-bearing
  idea. It includes how hard each aircraft is turning, how fast it is climbing or
  descending, how much its speed is changing, and how near the airport it is.
- **What the model must predict:** whether the two aircraft **actually** lost separation,
  read off their real recorded positions.

Encounters that begin already at their closest point are now rejected and regenerated.

### 6c. Does it work

Yes, and for a reason that can be explained out loud.

**The straight-line rule's mistakes are almost entirely vertical.** Of the real conflicts
it misses, 99% are cases where it correctly sees the two aircraft passing close
side-to-side but wrongly believes they will stay far apart in height. It predicts a gap
of about 2,825 feet where the real gap turns out to be about 498 feet. On exactly those
rows the faster climber is going up or down about eight times faster than average. A
straight-line guess handles a hard climb badly, and the model learned to distrust the
predicted height gap in precisely that situation.

The fair test is whether it wins **without simply raising more alarms**, because catching
more conflicts is trivially easy if you are willing to cry wolf. Measured at exactly the
same false-alarm cost as the rule, on held-out later data:

| | Straight-line rule | **The model** |
|---|---|---|
| Real conflicts caught | 88.1% | **93.7%** |
| Headline metric, caught with 3 minutes to spare | 87.3% | **93.3%** |
| False alarms per 1,000 pairs | 73.8 | 73.8 |

The leakage check now reads **95.60%** where it used to read 100%, and the score is
**0.80** where it used to be a meaningless 1.0. The 1,760 rows where our own prediction
disagrees with reality are the entire learning problem, and they are what the model feeds
on.

A guard now runs before every training run. It recomputes the answer key from the inputs
and **stops with an error above 99%**. The old data files are deliberately not matched by
name, so one cannot be picked up by accident and quietly undo the fix.

### 6d. One gate is still failing, on purpose

The project requires the classifier to catch at least 95% of real conflicts. It catches
**94.06%**. It fails by six tenths of a point, and it has been left failing.

**This is not the model falling short.** It is how the alarm sensitivity gets picked. The
script chooses the least twitchy setting that still reaches 95% on the practice data,
which by definition lands exactly on the boundary, at 95.11%. Tested on a later week of
traffic it slips just underneath. Choosing a setting with a little margin would fix it,
and the model clears 95% comfortably at any slightly more sensitive setting.

It was left alone for two reasons. Changing it changes when a real controller gets
interrupted, which needs Archit's decision. And a failing gate reported honestly is worth
more than a passing one that was massaged into passing.

The second gate, which asks whether the model actually beats the simple rule, **passed**.

---

## 7. Model 3, the resolution engine — built 6 September 2026

### 7a. What it does

Once a conflict is confirmed as a tier 1 alarm, this proposes up to three ways out, one
of each kind: change an altitude, change a heading, change a speed. Each one comes with
what separation it actually achieves, roughly what it costs in delay and fuel, a
confidence figure, and a sentence a controller could read aloud. Here is a real one from
the engine:

> Descend AI2841 to FL330. Reason: holds vertical separation at 2,000 ft where the paths
> cross. Fully established about 118 s from now, against a closest approach in 165 s.
> Confidence 0.79. Tradeoff: about 1.0 min of extra fuel burn.

They are ranked by the project's fixed formula, safety 60%, delay 15%, fuel 10%,
workload 10%, confidence 5%.

**Nothing is ever applied automatically.** The system offers options. The controller
accepts, dismisses or overrides, and that decision gets logged. Nothing in this file can
command an aircraft, and that is a hard rule of the project rather than an oversight.

### 7b. The one design decision that matters

The easy version of this would move the aircraft to its new heading instantly, check the
geometry, and report the conflict solved. That would be wrong in the dangerous
direction, because it would confidently recommend turns that no real aircraft could
complete in time.

So every suggestion is actually **flown** in simulation, second by second:

| Phase | What happens |
|---|---|
| First 38 seconds | Nothing at all. Controller decides, calls, hears the readback, pilot acts. |
| Then | The aircraft turns at 3 degrees per second, or climbs at 1,500 feet per minute, or changes speed slowly. |
| Throughout | Separation is measured at every second, and a suggestion only counts if the gap is never lost. |

Because the delay and the real turn rates are inside the simulation, there is no need
for a separate "is there time?" test. A manoeuvre that is too slow simply fails to
prevent the conflict and gets rejected with a reason.

### 7c. Two things this taught us

**With 90 seconds left, nothing works.** All 26 possible instructions were rejected. Not
the climb, not the turn, not the speed change. Thirty-eight of those ninety seconds are
gone before the aircraft moves at all, and nothing an airliner can do in the remaining
fifty-two opens a safe gap in time.

That independently confirms a decision the project had already made on paper, that
alarms belong at three minutes. The pencil calculation and this simulation arrive at the
same answer by different routes. An alarm raised well inside three minutes is genuine
and completely useless, and now we can show that rather than assert it.

**One of our stated rules turned out to be too broad.** The project document says to
prefer altitude changes when time is short, because a climb takes about 40 seconds and a
turn about 96. The arithmetic is right, but the rule does not hold generally. Tested
directly on a head-on pair:

| Time until closest approach | Climbs that work | Turns that work |
|---|---|---|
| 90 seconds | 0 | 0 |
| 105 seconds | 4 | 4 |
| 120 seconds | 4 | 6 |
| 135 seconds or more | 4 | 8 |

There is no window where the climb works and the turn does not. They become available at
the same moment. In a head-on encounter a turn changes the geometry very quickly, so the
96-second figure overstates what a turn really needs.

Altitude still comes out top, but for an honest and different reason: it is **easier to
manage**. A climb is one instruction the controller can watch working. A turn has to be
remembered and later undone. That shows up in the scoring as a workload of 1.00 against
0.50.

Rather than hard-code a preference that is wrong in some geometries, the engine tries
every option on every conflict and rejects what does not work. The rule in the project
document has deliberately **not** been edited. The measurement is recorded next to it so
Archit can decide.

### 7d. What is deliberately rough, said out loud

Delay and fuel are coarse proxies, not an aircraft performance model. There is no engine
data, no aircraft weight, no wind. They are track-mile arithmetic, good enough to rank
three options against each other and not good enough to quote to an airline. Every
explanation string says "approximate" for that reason.

The machine learning ranker that the project document describes as a later upgrade has
not been built and is not needed for the MVP. The rule-based engine comes first by
design, and stays in place underneath if a ranker is ever added.

---

## 8. What is left, in order

| # | Task | Blocked on |
|---|---|---|
| 1 | Run `python ml_pipeline/run_pipeline.py` on the laptop and send back `ml_pipeline/reports/` | Nothing |
| 2 | Decide whether to give the alarm threshold a safety margin, using the WHAT-IF table the run prints | **Archit** |
| 3 | Decide what to do about the altitude-preference rule in CLAUDE.md Section 3 | **Archit** |
| 4 | Build the FastAPI backend and the database on top of `server/app/ml/inference.py` | Nothing |
| 5 | Connect the restored frontend to that backend | Task 4 |
| 6 | Refresh the numbers in the approach document | Tasks 1 and 2 |

Task 1 is the only one that needs a machine rather than a decision, and it unblocks the
rest. Tasks 2 and 3 are small decisions waiting on you.

**All four models are now built.** What stands between here and a working demonstration
is the web API and connecting the frontend, neither of which involves machine learning.

**Done on 5 September 2026:** the circular label, the zero-warning encounters, and the
missing leakage guard.

**Done on 6 September 2026:** the full pipeline retrain, the automated verification, and
Model 3, the resolution engine.

**Coded on 6 September 2026, numbers pending the real run:** multi-path probability
calibration, dense-grid checking of candidate paths, calibrated and SHAP-explained
conflict classifier, the one-command pipeline, the inference module, and the first tests.
