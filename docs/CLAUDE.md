# Flight Right — Full Project Context for Claude Code

Read this entire file at the start of every session. It is the single
source of truth for this project — you should not need to open README.md
or the ML approach doc separately, though they still exist in the repo
for anyone who wants the long-form version.

---

## 1. What this project is

Flight Right is an AI-assisted air traffic monitoring, conflict
prediction, and controller decision-support dashboard for the Indian ATC
context. It is a final-year engineering project, evaluated academically —
not a certified ATC product, not autonomous aircraft control.

It supports controllers by: monitoring live/replayed aircraft data,
predicting near-term conflicts, recommending explainable resolution
options, and keeping an audit trail of every action. The controller (ATCO)
always keeps final authority — every AI suggestion can be accepted,
dismissed, or overridden, and that decision is logged.

**Current state:** the frontend dashboard is built and works against mock
scenario data (`client/mockData.js`). Nothing backend/ML exists yet. The
work ahead is: build a real backend, connect it to live/replay aircraft
data, add prediction/detection/recommendation models, and wire the
existing frontend to real data instead of mocks.

## 1a. OPERATING RULES

Read this section before acting on anything else in this file. Sections 2-14
give the detail and the evidence trail; this section says what matters most,
what is already settled, what is still broken, and when to stop and ask.

Why this section exists: instructions were being relayed into this repo from
another AI and results relayed back out, which left Archit without the
reasoning behind the decisions and left each new session without the context to
make its own calls. This section closes both gaps. After reading it, make most
calls yourself.

### PART 1 — THE ONE NUMBER

The project's headline metric is:

> **percentage of conflicts caught with at least 3 minutes of warning**

**Currently 94.0%**, measured 6 September 2026 on held-out test data by
`ml_pipeline/training/conflict_classifier/train_xgboost.py`. Everything else in this
file is a supporting detail.

**Read the basis, not just the number.** The earlier figure of 93% came from the
rule-based detector scored against labels the same straight-line arithmetic had
produced, so it measured self-consistency. The 93.7% is measured against where real
aircraft actually went. The two numbers are nearly identical and that is a
coincidence, not a continuity: they are different measurements and only the second
one means anything. On the same honest basis the rule-based detector scores 87.3%
and the bare legal-minimum rule scores 81.7%.

**There are TWO numbers here and they must never be merged (added 22 Sep 2026).**

| what is being scored | number | what it answers |
|---|---|---|
| the classifier **in isolation**, at its own threshold | **94.0%** (267 of 284) | how good is the model? |
| the **running system**, through the real escalation gate | **94.7%** (269 of 284) | what does the controller actually get? |
| the running system **including the multi-path step it really takes** (`offsets_ab_test.py`, added 24 Sep) | **94.7%** (269 of 284), 101.1 false alarms per 1000 | the same question, measured completely |

**Correction and fix, 24 Sep 2026.** The 94.7% row scores the gate on straight-line geometry
only, and `reevaluate_models.py` does not model the multi-path step. Measured with that step
(`ml_pipeline/utils/offsets_ab_test.py`), the system as served **until 24 Sep** caught
**94.4%** (268), at 113.0 false alarms per 1000. The cause: the safety net checked the model's
worst path combination instead of the straight line. The net was put back on the straight
line and per-mode offsets were switched on the same day (plan 3.2, signed off). The served
system is now **94.7% (269), 101.1 per 1000, tier 1 28 real / 17 false**. Until
`reevaluate_models.py` gains the multi-path step, `offsets_ab_test.py` is the source for this
figure.

**94.0% remains the headline.** It is the model's number, it is what the gates are
defined on, and it is what every published figure in `docs/evaluation.md` refers to.
The runtime figure exists because until 22 September the two were **87.3% and 94.0%** —
the classifier gated nothing, so the system the controller used was measurably worse
than the model the documents described. Both are now measured on every re-score
(`reevaluate_models.py`, under `model2.escalation_runtime`) so that gap cannot reopen
unnoticed. When quoting either, say which one it is.

**Rule:** whenever reporting progress, lead with this number and how the change
affected it. Raise any other metric only if (a) it changed this number, or (b)
it reveals a defect. Do not open a progress report with trajectory error, loss
curves, or dataset size.

### PART 2 — WHERE THE PROJECT IS

Keep this table current on every change. When Archit asks "where am I", answer
with this table.

| Component | Status |
|---|---|
| **Model 1 — trajectory prediction** | **DONE.** Beats the physics baseline everywhere. |
| **Model 1b — multi-path output** | **DONE and calibrated on real data.** Full run 6 Sep 2026: temperature 1.729, calibration error 0.054 -> 0.019 on arrivals and 0.040 -> 0.012 overall. Best-of-5 at ten minutes 63.6%. **23 Sep, Phase 3.1: per-mode offsets built and measured — best-of-5 on arrivals 63.6% -> 71.5%, top-1 38.6% -> 44.2%, one seed. Saved in the same pickle but NOT serving: the backend defaults to the old table (`FLIGHT_RIGHT_MULTIPATH_OFFSETS=table`) until Archit signs off.** **24 Sep: SERVING by default (`FLIGHT_RIGHT_MULTIPATH_OFFSETS` unset = `per_mode`), switched on with sign-off after measurement on 4,690 labelled test pairs (`offsets_ab_test.py`). With plan 3.2's straight-line safety net: 269 of 284 caught at 3 min, 101.1 false alarms per 1000, tier 1 28 real / 17 false, against table's 28 / 18. An old pickle without offset models still starts the backend on the table. Phase 3.3 done 25 Sep: four seeds, per-mode best-of-5 72.0% ± 0.4 vs table 63.4% ± 1.3, top-1 43.7% ± 0.8 vs 38.3%; per-mode wins on every seed. Archive row (+400k windows from 12 pre-validation archive days): best-of-5 75.4%, top-1 46.8%, temperature 1.73 -> 1.07. Archive model NOT served: 4 seeds confirm 75.6% ± 0.6 / 46.7% ± 0.4, but through the alert chain it is identical on test and costs one real tier 1 alarm on validation. 25 Sep: multi-path ALTITUDE scored for the first time: the table was no better than a straight line; per-mode halves ten-minute height error (2,231 -> 1,116 ft); honest 3-D figure for arrivals (5 NM AND 1,000 ft, best-of-5) is 44.1%.** |
| **Model 2 — conflict detection** | **WORKING AND NOW GATING** as of 22 Sep 2026. Circular label fixed; beats the rule at equal false-alarm cost. Rule path still runs underneath and still outranks the model. 6 Sep: Platt calibration, SHAP explanations, GPU training and the recall-margin what-if table. **22 Sep: the classifier finally gates escalation — until then it was computed, displayed and ignored by the alarm decision.** Runtime headline 87.3% -> 94.7%; tier 1 false alarms 24 -> 14 with the same 27 real conflicts. The reported 94.0% is unchanged because it scores the classifier in isolation. GATE 1 still fails at 0.9439 and was not touched. **24 Sep (plan 3.2): the 5 NM / 1,000 ft safety net again judges the straight-line prediction (`RULE_GEOMETRY_KEY`). Beyond three minutes it had been judging the multi-path model's worst path combination: that added 61 alarms and dropped a real conflict. Candidate pruning was measured and not adopted.** |
| **Model 3 — resolution engine** | **DONE (rule-based), AND LIVE IN PRODUCTION** as of 22 Sep 2026. Three explained, costed, ranked options per tier 1 alarm. 7 Sep: checked against the other aircraft's 5 predicted paths and against all nearby traffic, so a fix that would cause a new conflict is rejected — **but the nearby-traffic list was never passed in by the backend, so that check ran on an empty list in production until 22 Sep.** Now wired; costs ~0.01 s per update against a ten-second budget. ML ranker still deferred. **25 Sep (plan 9.7): C1 and C2 FIXED.** A manoeuvre is offered only when the do-nothing simulation loses separation, and the separation it reports is measured from the end of the 38 s response delay. Instructions for conflicts that never happen 38 -> 11; for real conflicts 38 -> 35. Every other re-scored value is unchanged. |
| **Training pipeline** | **ONE COMMAND** as of 6 Sep 2026: `python ml_pipeline/run_pipeline.py` (see `ml_pipeline/README_TRAINING.md`). Smoke-tested end to end on fake data; the real run on the RTX 4060 laptop is pending. |
| **Backend (FastAPI server)** | **RUNNING** as of 8 Sep 2026. `server/app/` — 14 REST endpoints plus `/ws/stream`, OpenSky OAuth2 live mode, recorded-session replay with fallback, the full model chain per pair, the alert feed, and a **PostgreSQL** store where the audit log is append-only *because the database refuses UPDATE and DELETE*, not because the code avoids them. SQLite remains an automatic fallback. See `RUNNING.md`. |
| **Alert feed (what the controller sees)** | **DONE** as of 7 Sep 2026: `ml_pipeline/utils/alert_feed.py`. Repeat suppression and low-confidence collapsing, both display-only. Interruptions down **73.7% and 74.1%** on the two replayed sessions (the 63-65% first recorded on 7 Sep came from a pre-filter that was never committed; the committed re-score supersedes it) and prominent-list precision 0.386 -> 0.503, with **zero** pairs lost from the reported set. **Wired in and running**: `conflict_service.assess` passes every update through it. |
| **Data availability (Phase 2)** | **ANSWERED** 23 Sep 2026 — see `docs/phase2_findings.md`. OpenSky's historical archive (Trino) is **open**. **OpenSky has no selected-altitude table and never will** — the archive stores only a flag saying which aircraft *could* broadcast one. **Corrected 23 Sep: the value itself is available from adsb.lol** (live and in daily per-aircraft traces, ODbL 1.0), so the feature is reopened as plan item 9.0, not out of scope. **Indian low-altitude coverage near VABB begins January 2025 and is categorically absent before it**: nine sampled months in 2023-24 carry cruise traffic over Mumbai and *zero* states below 10,000 ft near the airport. Usable window Feb 2025 - Sep 2026. One archive day at 10 s = 203,849 rows, so **three days ≈ the entire twelve-day polling effort**. Speech: the public ATC test set carries **no callsign/action/value labels**, and **12.5% of it is the same audio the shipped model trained on**, leaving 762 clean clips. **24 Sep, 2.6 answered: adsb.lol per-aircraft history files can be fetched directly for a rolling ~6 weeks (every day from 13 Aug 2026, both airframes checked); older days are patchy (Feb-Jul 2026 absent, Dec 2025 refused). Phase 2 is now complete: all six questions answered.** |
| **Clearances (plan Phase 7, the seam for speech)** | **BUILT 25 Sep, no audio.** `ml_pipeline/utils/clearance.py` + `clearance_service.py` + `POST/GET/DELETE /api/clearances`. Tables `transcriptions` / `extracted_clearances` are append-only in PostgreSQL. Oracle UPPER BOUND, arrivals 10 min, 3-D best-of-5: 43.4% -> 53.8% (level cap + heading filter). Speech chain (Phases 4-6) deferred by Archit; it only has to produce a `Clearance`. |
| **Evidence (plan Phase 8)** | **DONE 25 Sep.** `docs/ablation.md` generated by `ablation.py`; `docs/claims.md`. |
| **Frontend dashboard** | **CONNECTED** as of 8 Sep 2026. Aircraft, conflicts, resolutions, suggestions, metrics, timeline and the audit trail all come from the backend over a WebSocket, with polling fallback. No mock data remains for anything a model produces. Runways, weather and the NLP transcript have no data source and are labelled DEMO on screen. 22 Sep: the radio panel's `APPROVE & TRANSMIT VIA DATALINK` button and its "clearance transmitted" toast are gone — the system cannot transmit and no longer says it does. **25 Sep: H1 FIXED** (every `logAudit` also reaches the server audit log; `/logs` opens on the server log), **H2 FIXED** (the server stamps the model versions on every audit row), **H3 FIXED** (a dismissal is remembered per episode, not per pair forever). |

### PART 3 — RULES THAT ARE NOT UP FOR DEBATE

Each of these was learned by measurement, usually the expensive way. Do not
undo them, and do not "simplify" them back. If you think one is wrong, say so
and show the measurement that changes it — an argument alone does not move any
of these.

1. **NEVER MSE for trajectory loss.** Measured: MSE gives 6.4% of predictions
   within 1 NM at 10 minutes; SmoothL1 with beta=0.05 gives 27.7%; the physics
   baseline alone gives 30.0%. MSE optimises the average and destroys the
   near-perfect predictions.
2. **SmoothL1 beta matters as much as the loss family.** beta=1.0 scores 6.1% —
   as bad as MSE, because at that setting the quadratic region covers most of
   the data. **Keep beta=0.05.**
3. **ALWAYS split data by time, never randomly.** Test data must come from
   later dates than training data, split on whole collection sessions.
4. **ALWAYS report against the constant-velocity baseline on identical data, in
   the same run.** This is non-negotiable. A model that lost to plain
   arithmetic at every horizon went unnoticed for three weeks because nobody
   printed the comparison.
5. **NEVER report a single averaged error figure.** Always per horizon and per
   flight regime. The average is what hid the failure in rule 4.
6. **NO feature may be computable from the label.** Learned the hard way — see
   Part 4, item 3.
7. **Synthetic data means synthetic PAIRINGS of real trajectories.** Never
   synthetic flight paths. A model trained on invented turns learns our
   assumptions, not Mumbai's.
8. **Alert on a volume WIDER than the legal separation minimum.** At the bare
   5 NM / 1000 ft trigger we catch 46% of real conflicts; at 8 NM / 1500 ft we
   catch 99% at one minute.
9. **Probabilities must be calibrated before any threshold means anything.**
10. **Never conflate top-1 accuracy with best-of-K.** Top-1 is 38.6% on
    arrivals; best-of-5 is 63.6%. Both are true and they measure different
    things.

### PART 4 — OPEN PROBLEMS, IN PRIORITY ORDER

1. **The conflict classifier misses its recall floor.** Test recall is **0.9439**
   against a 0.95 gate (full run, 6 Sep; was 0.9406 before retraining). **Diagnosed, and it is not a bug in the
   model.** The threshold is chosen as the *highest* value still reaching 0.95 on
   validation, which by construction lands exactly on the edge of the floor
   (validation recall 0.9511). A later, different test split then falls slightly
   below it. Selecting the edge point leaves no margin for the shift between splits.
   The obvious remedy is to select for a small margin above the floor, but that
   **changes when a controller gets alerted, so it needs Archit's sign-off** and has
   not been done. Reported, not tuned away. **As of 6 Sep `train_xgboost.py` prints a
   WHAT-IF table** (margins 0.005 / 0.01 / 0.02: threshold, test recall, false alarms
   per 1000, headline metric) so the decision can be made from numbers; the saved
   model still uses the zero-margin threshold.
   **Do not read the 22 Sep runtime result as closing this.** Since the classifier
   began gating escalation, the *system's* recall is 0.9505, above the floor — but
   that is the system, helped by the geometric safety net catching pairs the
   classifier misses. **The gate is defined on the classifier alone, and on that
   measurement it is still 0.9439 and still failing.** The margin decision is still
   open and still Archit's.
3. **Tier thresholds 0.85 / 0.60 were chosen for a truthful probability.** The
   multi-path probabilities are now calibrated in code (item resolved below), but the
   thresholds have not been revisited against the calibrated numbers. Do that only
   after the real run, and only with Archit.
4. **The dataset has roughly doubled since the docs were written.** Re-run
   evaluation and refresh the numbers in `Flight_Right_ML_Approach.docx` before
   submission.

**Resolved 6 September 2026, and confirmed by the full training run that day:**

- ~~*Multi-path probabilities are badly calibrated.*~~ `multipath.py` now fits a
  single temperature on the validation split (Guo et al. 2017) and saves it in the
  pickle; `inference.py` applies it. Ranking, and therefore best-of-5, is untouched by
  construction. The script prints reliability and expected calibration error before and
  after on the test split. Temperature scaling was chosen over `CalibratedClassifierCV`
  because it cannot change the top-K and cannot overfit 40 classes on a thin
  validation split; the reasoning is in the Section 14 entry.
- ~~*The K x K path pairing checks only the four named horizons.*~~
  `densify_path()` in `cpa_conflict_detection.py` interpolates each candidate path onto
  the 15 s grid from the aircraft's current position; `compute_cpa_from_paths()` does it
  automatically when given the two current positions. Unit-tested on a crossing at
  t = 240 s that the four-point check misses (16 NM reported) and the dense check finds
  (under 1 NM).

**Resolved 5 September 2026, kept here so the trail is readable:**

- ~~*Model 2 is circular.*~~ Fixed. Features now come from the constant-velocity
  prediction and the label from where two real aircraft actually went. Label
  reproducibility from the features fell from **100.00% to 95.60%**, PR-AUC from a
  meaningless 1.0 to **0.8024**, and a leakage guard in `train_xgboost.py` now
  refuses to train on any dataset above 99%.
- ~~*The scenario generator starts encounters already in progress.*~~ Fixed. Any pair
  already inside the alert volume at t=0 is rejected and resampled, so **0.00%** of
  conflicts now sit at zero warning, against 25.33% before.

### PART 5 — ALREADY TESTED, DO NOT RETRY

Save time by not re-proposing these. All measured on our own data.

- **Bidirectional LSTM:** 56.7% vs 58.0% one-directional at 10 min, with 2.5x
  the parameters. No benefit — reading the past backwards cannot reveal the
  future.
- **Tripling the input window (99 s to 316 s):** no improvement at any horizon,
  and it costs 29% of the dataset. 74% of aircraft flying straight over 99 s
  are still straight over 316 s.
- **Bigger or more advanced models:** a gradient-boosted tree and a 2-layer
  LSTM land 2 points apart on identical features. When unrelated architectures
  converge, the limit is the information in the features, not model capacity. A
  Transformer will land in the same place.
- **Per-horizon equal loss weighting:** 63.7% vs 64.5%. Slightly worse.
- **Warning only when the conflict probability is climbing.** The idea was to cut false
  alarms by showing the controller only the pairs whose danger is visibly increasing.
  Measured on 220 encounters against what the real aircraft actually did: it removed
  4 false alarms and **5 real conflicts**. Recall fell from 93.8% to 62.5% while
  precision rose only 62.5% to 66.7%. False alarms were 37.5% of all alerts and 44% of
  what the filter removed, so it is barely better than deleting alerts at random --
  which also improves precision. The cause: whether the dominant path combination is
  momentarily strengthening is noise (it moves about 0.04 per update with a quarter of
  steps jumping over 0.10), and noise cannot separate real conflicts from false ones.
  **The false-alarm problem it targets is real** -- roughly six alerts in
  ten are for conflicts that never happen. The supported levers are the recall-margin
  threshold table and suppressing repeat alerts for the same pair, not a trend filter.
  **Repeat suppression is now built** (`ml_pipeline/utils/alert_feed.py`, 7 Sep):
  interruptions down 63-65% on real traffic with zero pairs lost from the reported set.
  The recall-margin decision is still open and still yours.
- **The level-flight filter for false alarms.** Suppress a pair when both aircraft read
  level and the predicted vertical gap already clears 1,000 ft. Targets the dominant
  false-alarm mode: 64.8% of false alarms are pairs that closed laterally but stayed
  stacked (median 2.44 NM / 1,930 ft real closest approach, against 1.69 NM / 535 ft for
  true conflicts). Measured: cuts **46% of false alarms** and costs **21 real
  conflicts** -- recall 0.9439 -> 0.875, headline **94.0% -> 86.6%**. The 21 read
  0.00-0.33 m/s vertical rate at decision time and then descended; several predicted
  2,200-2,450 ft apart ended 240-530 ft apart. EUROCONTROL run this filter as STCA
  Option E using the **cleared flight level** from the flight data system, and warn in
  the same sentence that it "reduces warning time in the event of level bust". Our proxy
  is observed vertical rate, and level bust is exactly what a proxy misses. Not
  retryable without flight-plan data.
- **The hard ceiling:** two aircraft in an IDENTICAL situation end up 7.9 NM
  apart on average at 10 minutes, and 64% of such pairs end more than 5 NM
  apart. The outcome depends on a controller instruction we never receive. This
  is why multi-path exists — not to guess better, but to cover the
  possibilities.

### PART 6 — HOW TO DECIDE, AND WHEN TO ASK

**Decide yourself, without asking:**

- Any bug fix, any implementation detail, any refactor.
- Which experiment to run to diagnose a failure.
- Anything Part 3 or Part 4 already tells you to do.

**Stop and ask Archit:**

- Any change to what a model predicts, or what the label means.
- Any change to a threshold that affects when a controller gets alerted.
- Anything that would make a reported number look better without the system
  actually improving.

**When a gate fails: find the bug.** Do NOT tune hyperparameters, move the
threshold, or change the gate to make it pass. Report the failure with the
diagnosis. A failing gate that is honestly reported is more useful than a
passing one that was massaged.

### PART 7 — HOW TO EXPLAIN THINGS TO ARCHIT

He is learning machine learning while building this, and outputs get forwarded
to mentors who know neither ML nor aviation. So:

- **Plain language.** No jargon without defining it in the same sentence.
- **Lead with the headline number and whether it moved.** Then the detail.
- **Say explicitly whether something is a real problem or just a detail.**
- **When reporting a subset result** (arrivals, 10 minutes, sharp turns), always
  say what the overall number is too, so a hard case does not read as project
  failure.
- **Never present a wall of tables** without saying which row matters.


### PART 8 — EVERY CHANGE GETS WRITTEN DOWN IN PLAIN ENGLISH

Archit is learning ML while building this, and for a while instructions were being
relayed in from another AI. That left him without the reasoning behind his own
project. The cure is that **no change is finished until it is explained.**

After every change, append an entry to **Section 15, the plain-English change log**,
containing all five of these:

1. **Which file or files changed** — full path, so it can be opened.
2. **What it was before** — the old behaviour, described, not just a diff.
3. **What it is now** — the new behaviour.
4. **Why** — the problem this solves, and the measurement that proves it was a
   problem. "It seemed cleaner" is not a reason.
5. **Did the headline number move?** — the Part 1 number. If it did not move, say so
   explicitly. "No effect on the headline number, this was a correctness fix" is a
   complete and acceptable answer.

Write it for someone who has never opened the code. Define every term in the same
sentence you use it. If an entry cannot be understood by a reader who knows neither
machine learning nor aviation, it is not finished.

This is not optional and it is not "documentation to do later". A change that is not
logged did not happen.

### PART 9 — EVERY PROPOSED FIX MUST SAY WHERE IT CAME FROM

When you hit a problem, the report has three parts, in this order:

1. **The problem, in beginner terms.** What is wrong, what it causes, and whether it
   is a real problem or just a detail. Say which of those two it is, out loud.
2. **The proposed fix.**
3. **The source of the fix**, which must be one of exactly two things:
   - **A citation** — a research paper, an official standard, or a technical article,
     **with a working link**. Prefer the papers already listed in Section 2, which
     were read in full. If you bring in something new, link it and say in one line
     what it actually demonstrates.
   - **Or an explicit statement that there is no source**: "This is our own design.
     It is not taken from any paper or article." Then justify it by measurement on
     our data instead.

Never let a proposal sit in between. An unsourced idea presented as though it were
established practice is the exact failure mode that put five irrelevant papers into
the original proposal — two of them about converting radio speech to text, cited to
justify a flight-path model. Archit gets asked "where did this come from" by mentors,
and he must always have the answer.


## 2. Problem framing (for when features need justifying)

Indian airspace is dense and growing, especially around metro airports.
Existing systems (ADS-B, MSSR, FDPS, OLDI, VCCS) supply data but don't
integrate AI-driven prediction, prioritization, explanation, and workflow
automation in one interface. The MVP target:

> Build an AI-assisted ATC decision-support dashboard that consumes
> aircraft surveillance data, predicts near-term conflicts, recommends
> explainable resolution actions, and records every operator action in an
> audit log.

**Why Mumbai/BOM specifically:** it's one of India's busiest, most
constrained airport environments — high arrival/departure density, strong
monsoon weather impact, dense mixed traffic, runway sequencing pressure.
It gives a demonstrable, defensible MVP story without needing certified
national ATC data. Demo bounding box for OpenSky queries:
`lat_min=16.0, lat_max=23.5, lon_min=68.0, lon_max=77.5`. (Delhi is a
secondary option: `lat_min=25.0, lat_max=31.5, lon_min=74.0, lon_max=80.5`.)

**Research grounding — read the correction first.** The five papers cited in
the original proposal (AWARE/AI4ATM, Guleria et al., the XGBoost-on-ADS-B
paper, the 4D trajectory CTGAN paper, M2ATS) have been read in full. **None
of them proposes, trains or evaluates a flight-path prediction model.** Two
are about converting controller-pilot radio speech to text, one is about
controller staffing, and two are literature summaries — one marked by its
publisher as not peer reviewed. The word "bidirectional" appears once across
all five, in the speech paper, explaining why those authors *removed* it. The
1/3/5/10 minute horizons do not come from them either.

**So do not justify the trajectory architecture by citing them.** The
architecture is our own design, justified by measurement on held-out test
data — every choice in Section 3 traces to a dated entry in the Section 14
decisions log, and each is repeatable from the project code. "We designed
this and here is the measurement" is stronger in review than a citation that
does not survive being checked.

- What the original five *do* still support: the single-dashboard workflow
  design (alerts + suggestions + explanations + audit log together, rather
  than a black box); conflict resolution as a multi-output problem, hence
  rule-based first and an ML ranker later; XGBoost with engineered features
  as an explainable pairwise conflict classifier; NLP/datalink as future
  roadmap rather than MVP; and CTGAN as a data-hungry stretch goal only.
- Genuine trajectory-prediction references, for the multi-path work:
  Barratt, Kochenderfer & Boyd (IEEE T-ITS, arXiv:1810.09568) — probabilistic
  terminal-airspace trajectory models from position data alone; Zhang et al.
  2025 (Eng. Applications of AI) — flight-pattern-guided Social LSTM; Sun
  et al. 2024 (Neurocomputing 128843) — intent from local history when no
  flight plan exists; Aerospace 2025 12(9) 855 — Bayesian spatio-temporal
  prediction with conflict alerting; Gariel, Srivastava & Feron (NASA
  DASHlink) — trajectory clustering into route patterns; Wang et al. (SESAR
  Innovation Days 2017) — cluster arrivals into routes, then a model per
  route; Mercat et al. (arXiv:1908.11472) and PERL (arXiv:2309.15284) —
  predicting a *correction* to a simple physical model rather than predicting
  position directly.
- Conflict-detection references: EUROCONTROL/SKYbrary Short Term Conflict
  Alert and Medium Term Conflict Detection — the two-tier split, the
  ~2-minute safety-net look-ahead, and MTCD being a planning tool rather than
  a safety net. SKYbrary *Basic Controller Techniques: Vectoring* and the NASA
  TCAS-II resolution advisory algorithm — how much deviation is achievable at
  what time-to-conflict, and the 15-35 s onboard last-resort window.

**Honest framing — what to claim vs. not claim (use this language, don't
invent stronger claims):**
- Claim: "AI-assisted ATC decision-support MVP," "prototype,"
  "human-in-the-loop," "simulation-backed," "OpenSky-based live demo,"
  "research-informed architecture."
- Never claim: certified ATC system, production-ready safety-critical
  automation, replacement for ATCOs, guaranteed conflict resolution in
  real airspace. OpenSky is not a certified feed — always note that
  production use would need certified surveillance, flight plans,
  weather, NOTAMs, and regulatory validation.

## 3. Decisions already made — do not re-derive or second-guess these

- **Backend:** Python FastAPI (not Express, not a Node ML service).
  Chosen because ML integration, WebSocket streaming, and OpenSky
  ingestion are simplest in one Python service, and FastAPI gives
  auto-generated OpenAPI docs. Existing Express server is a placeholder
  to be replaced, not extended.
- **Database:** PostgreSQL for aircraft states, conflicts, resolution
  options, users, and audit logs. Redis is optional, only for caching the
  latest aircraft state. Celery/APScheduler optional for scheduled
  OpenSky ingestion jobs.
- **Data source:** OpenSky Network REST API as primary. Supplement with
  OurAirports (airport metadata) and Open-Meteo (weather features) only
  if/when weather-aware features are actually built. The system MUST
  support three data modes, not just live:
  1. **Live OpenSky mode** — real traffic, proves integration, but may
     show no conflicts during a demo.
  2. **Recorded replay mode** — replays previously collected OpenSky
     data, for a stable, repeatable evaluation demo.
  3. **Scenario simulation mode** — injects controlled
     conflict/emergency/weather scenarios, to reliably demonstrate
     conflict prediction, the resolution modal, and audit logs even if
     live data has nothing interesting happening.
  Always build a fallback to replay if OpenSky is down or rate-limited.
- **Frontend:** Keep the existing React 19 + Vite + Tailwind + Framer
  Motion + Leaflet/React-Leaflet + Lucide + React Router stack as-is. Do
  not rewrite or replace components — the work is wiring existing
  components to real APIs/WebSockets instead of `mockData.js`.
- **Trajectory prediction model:** **one-directional** LSTM (2 layers,
  hidden size 128, dropout 0.3, batch size 64, Adam optimizer, lr 0.001)
  predicting a **residual correction to the constant-velocity
  extrapolation** — not a Bi-LSTM, and not absolute lat/lon/altitude.
  4 output heads, each giving (along-track, cross-track, altitude)
  corrections in metres at 1, 3, 5 and 10 minutes; the pipeline converts
  those back to lat/lon/altitude.
  - **Why residual, not position.** A zero output reproduces constant
    velocity exactly, so the model starts at the physics and can only be
    pushed off it by evidence — it cannot do worse than plain arithmetic.
    Predicting position directly is what made the first model fail: it had
    to rediscover geography and arithmetic from scratch, never got there,
    and settled on answering "somewhere over the Mumbai region" for every
    aircraft.
  - **Why not bidirectional.** Reading the window backwards only re-reads
    the same ten past snapshots in reverse; at inference there is no future
    inside the input. Tested rather than assumed: 58.0% vs 56.7% within
    5 NM at ten minutes, with 2.5x the parameters and twice the training
    time. The simpler model won.
  - **Loss is `SmoothL1Loss(beta=0.05)`, never `MSELoss`.** Squared error is
    dominated by a small manoeuvring tail and trades away thousands of
    near-perfect predictions to shrink a few large ones — measured, it
    collapsed the within-1-NM rate at ten minutes from 22.4% to 2.5%. The
    beta is in normalised units and interacts with the per-horizon residual
    normalisation; **do not raise it** (see Section 14, 1 Sep).
  - **Input: last 10 aircraft states, expressed relative to the aircraft
    itself** — 7 per-step measurements (distance ahead, distance to the
    side, height difference, speed, vertical rate, signed heading change,
    time gap) plus 13 window summary scalars (turn rate, total turn,
    along-track acceleration, vertical acceleration, distance and relative
    bearing to VABB, and so on). Headings are carried as sin/cos and
    unwrapped before differencing, never raw degrees. The original input
    list had position, height, speed, direction and vertical rate — **none
    of which describes change**, so the model was never told that an
    aircraft was turning.
  - **No MSSR noise injection.** The original plan called for injecting
    artificial radar noise during training. Dropped: our data is
    self-reported ADS-B position, not radar, and we have no measurement of
    Indian radar noise to base an injection on. Treat radar degradation as a
    robustness *test* if it comes up, not as training data.
  - **Constant-velocity extrapolation remains the required baseline** and is
    reported alongside the model at every horizon on every run. It is now
    also the model's own starting point, so it can never be deleted.
  - **Model 1b (planned, not built): several candidate paths with
    probabilities**, not one answer. Measured justification: for arriving
    aircraft, the 25 most similar historical situations finish an average of
    7.9 NM apart at ten minutes, and 64% of such pairs finish >5 NM apart —
    the future is genuinely uncertain, not merely hard, because whether a
    controller turns an aircraft now or in two minutes is information we do
    not receive. Five options drawn from 60 route patterns reach 69.3%
    within 5 NM at ten minutes against 30% for the single answer; the
    workable range is 25-60 patterns. For conflict detection we never have
    to pick one — check every plausible path and warn if any of them
    conflicts. Safety comes from covering the possibilities, not from
    guessing right.
- **Conflict detection — TWO TIERS, not one check.** A single conflict
  check run out to ten minutes is wrong for our accuracy: a ten-minute
  prediction does not justify telling an aircraft to change course, and
  turning an aircraft that was never going to conflict costs real fuel and
  real delay. The function splits, exactly as certified systems split it
  (short-range safety net vs. medium-term planning aid):
  - **Tier 1 — alarm, 0 to 3 minutes.** Raises a real alert **and**
    generates resolution options. We catch 93-99% of conflicts here.
  - **Tier 2 — advisory, 3 to 10 minutes.** Watch-list entry only.
    **Never suggests a manoeuvre.** We catch 69-82% here.
  - **Tier 0 — background.** Everything else; tracked, not shown.
  - **The 3-minute boundary is geometry, not a round number.** Alert →
    controller decision (15 s) → radio call and readback (15 s) → pilot
    starts manoeuvring (8 s) = 38 s before anything moves. A 1000 ft level
    change then takes ~40 s; a 30° turn at 450 kt takes ~96 s. So the
    minimum useful warning is ~90 s for a level change and ~135 s for a
    turn, and the practical floor with margin is about three minutes.
  - **Escalation requires all three of:** conflict probability over the
    tier threshold (0.85 tier 1, 0.60 tier 2); time-to-CPA inside that
    tier's range; and the pair qualifying on **3 consecutive updates**, so
    one noisy position report cannot make an alert flicker. Pairs are
    dropped from tracking once separation is increasing on consecutive
    updates *and* the pair is outside the alert volume. Implemented in
    `ml_pipeline/utils/cpa_conflict_detection.py`.
  - **Alert on a volume WIDER than the legal minimum.** Legal separation is
    5 NM / 1000 ft, but alerting at exactly that lets a prediction 1 NM out
    flip the decision. Measured: triggering at the bare minimum catches only
    46% of real conflicts; **8 NM / 1500 ft** catches 99% at one minute and
    93% at three, for 32-34 false alarms per 1000 pairs. Both pairs of
    numbers are named constants at the top of the module so the trade can be
    re-tuned; the false-alarm rate is the price and it is a dial we set
    deliberately.
  - **Tier 1 uses the constant-velocity path, not the neural model.**
    Measured: at one minute the straight-line method already catches more
    conflicts, because it is near-perfect there and the model's small
    corrections nudge both aircraft. The model earns its place in tier 2.
- **Conflict classifier (the ML layer inside the tiers):** XGBoost binary
  classifier (0 = no conflict, 1 = potential conflict) over pairwise
  tabular features:
  relative distance, relative altitude, relative speed, relative
  heading, closing speed, time-to-CPA, predicted minimum separation,
  vertical convergence rate, sector (e.g. Mumbai), uncertainty flag.
  Hyperparameters: 300 trees, depth 6, learning rate 0.05, subsample 0.8,
  feature sample 0.7. Required handling:
  - **Class imbalance:** conflicts are ~5% of cases → use
    `scale_pos_weight ≈ 19`.
  - **Loss/metric:** optimize for recall via F-beta (β=2) — a missed
    conflict is worse than a false alarm, so never optimize for plain
    accuracy or a balanced F1 alone.
  - **Explainability:** use SHAP to filter to important features only,
    and expose feature importance — controllers must be able to see why
    an alert fired.
  - **Severity sub-model:** a second model/rule layer predicts Low /
    Medium / High severity (e.g. Critical: CPA <3 NM or vertical
    separation <700 ft within 3 min; High: CPA <5 NM within 5 min;
    Medium: CPA below threshold within 10 min; Low: potential convergence,
    not immediate).
  - **CPA rule-based detection is the required deterministic baseline,
    always kept in place alongside the ML classifier as a safety net —
    never remove it once the ML classifier ships.** Legal-minimum
    thresholds for MVP: lateral 5 NM, vertical 1000 ft (alert volume 8 NM /
    1500 ft, above). These are simplified academic thresholds, not full
    regulatory separation standards — say so if asked.
  - **CPA is computed on a dense 15-second grid from 0 to 600 s (41
    points), never at the four named horizons.** The true closest approach
    almost never lands on 60/180/300/600 s: a pair passing at t = 240 s used
    to be recorded at its separation at 180 s and 300 s and silently
    dropped. Measured on 4,000 synthetic pairs, the four-point rule labelled
    856 conflicts against the dense grid's 1,089 — **21.4% of true
    conflicts were invisible to it.** The four named horizons are still
    returned under `per_horizon` for the dashboard, but they are a display
    convenience, not the detection path.
- **Resolution recommendation:** Hybrid, two steps.
  1. **Rule-based engine (MVP, required first):** generate 3 options —
     altitude change, heading change, speed/sequencing change. Each
     option must include: target aircraft, maneuver type, magnitude,
     expected separation after the maneuver, estimated delay/fuel
     impact, confidence, and a controller-readable explanation string
     (e.g. "Descend AI6302 to FL260. Reason: increases vertical
     separation to 1000+ ft and avoids lateral CPA below threshold.
     Confidence: 0.91. Tradeoff: +2 min delay.").
  2. **ML ranker (later):** XGBoost multi-class classifier or LightGBM
     ranker predicting which maneuver a controller would likely select,
     trained on simulated/rule-generated/annotated decisions.
  Scoring formula for ranking options:
  `score = safety*0.60 + delay*0.15 + fuel*0.10 + workload*0.10 + confidence*0.05`.
  (Delay 0.15 and fuel 0.10, in that order — an earlier draft had the two
  swapped.)
  3. **Prefer ALTITUDE changes as time-to-conflict falls.** A 1000 ft level
     change achieves separation in about 40 s; a 30° turn at 450 kt takes
     about 96 s and scales with the aircraft's speed. The ranker must
     therefore weight vertical options higher the less time remains. This is
     a physics-backed rule, not an arbitrary scoring weight, and it is
     defensible in review on exactly that basis.
  4. **Resolution options are generated for Tier 1 conflicts only.** Tier 2
     shows the pair on a watch list and proposes nothing.
  Never ship an unexplained suggestion — rules-only is "not smart," ML-only
  is "not safe"; the hybrid is the point.
- **NLP/transcript parsing:** Out of MVP scope entirely. If touched at
  all, use rule-based regex/phrase matching for callsign, altitude,
  heading, speed extraction (e.g. "AI6302 descend flight level 260" →
  `{callsign, intent: altitude_change, target_altitude}`). Do not build or
  propose a transformer/fine-tuned NLP model — that's explicitly future
  work (M2ATS direction).
- **CTGAN / C-CTGAN trajectory model:** Explicitly out of MVP scope
  (Phase 4/5+ stretch only). Needs more data than we'll have, harder to
  train and explain. Do not propose it as a first-pass trajectory model.
- **Audit logging:** every AI suggestion, controller action
  (accept/dismiss/override), and system decision must produce a
  server-side, authenticated audit log entry — timestamp, user/session
  id, source component, action, aircraft callsign if applicable, conflict
  id if applicable, before/after state, decision, model version,
  confidence score. Must be backend/DB-backed and append-only —
  frontend-only logs (the current `/logs` page) are demo-grade only, not
  the real thing.
- **Security posture for MVP (don't over- or under-build):** login or a
  fixed demo controller profile is enough; validate all backend inputs;
  never trust frontend-only decisions; store all actions server-side;
  keep model version attached to every prediction; always show
  confidence + explanation; manual override always available; fallback to
  replay if OpenSky is down. Full production security (strict RBAC,
  tamper-evident logs, model monitoring, regulatory compliance) is
  explicitly out of scope — don't gold-plate this.

## 4. System architecture (target)

```
OpenSky Network API → Ingestion Service → Data Cleaning/Normalization
  → PostgreSQL (history) + Latest Aircraft State Cache
  → Prediction Pipeline → Trajectory Prediction (residual LSTM) + Conflict Detection (XGBoost + dense-grid CPA rules)
  → Resolution Recommendation Engine
  → FastAPI REST API + WebSocket Stream
  → React ATC Dashboard
  → Operator Actions → Audit Log API → PostgreSQL
```

End-to-end workflow: fetch OpenSky states → normalize (lat, lon, altitude,
velocity, heading, callsign) → store latest + historical → predict future
positions (1/3/5/10 min) → detect separation-loss risk → if conflict:
raise alert → generate resolution options with explanation + confidence →
show in dashboard → controller accepts/dismisses/overrides → write audit
log → logs/predictions feed evaluation.

## 5. Backend API design (target endpoints)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/aircraft/latest` | Latest normalized aircraft states |
| GET | `/api/aircraft/history?icao24=...` | Aircraft history for charts/training |
| GET | `/api/conflicts/active` | Active predicted conflicts |
| POST | `/api/predict/conflicts` | Run conflict prediction on latest states |
| POST | `/api/recommend/resolution` | Generate resolution options for a conflict |
| POST | `/api/actions/accept` | Accept an AI suggestion |
| POST | `/api/actions/dismiss` | Dismiss an AI suggestion |
| POST | `/api/audit` | Store operator/system audit event |
| GET | `/api/audit` | Query audit logs |
| WS | `/ws/aircraft` | Stream aircraft state updates |
| WS | `/ws/alerts` | Stream conflict alerts |

## 6. Database schema (target)

- `USERS` — id, name, role, organization
- `AIRCRAFT` — icao24, callsign, origin_country
- `AIRCRAFT_STATES` — id, icao24, observed_at, lat, lon, altitude_m,
  velocity_ms, heading_deg, vertical_rate, on_ground
- `CONFLICTS` — id, aircraft_a, aircraft_b, predicted_at, cpa_seconds,
  cpa_distance_nm, severity, confidence
- `RESOLUTION_OPTIONS` — id, conflict_id, maneuver_type, target_aircraft,
  heading_delta, altitude_delta, speed_delta, confidence, explanation
- `AUDIT_LOGS` — id, timestamp, user_id, level, source, action,
  detail_json (references conflicts and users)

OpenSky state vector fields to ingest: ICAO24 address, callsign, origin
country, timestamp, longitude, latitude, barometric altitude, geometric
altitude, velocity, true track/heading, vertical rate, on-ground flag.
Ingestion: poll every 5–15 seconds, filter by the Mumbai/Delhi bounding
box, keep only rows with valid lat/lon/altitude/velocity/heading, store
latest state in cache + historical state in DB, push latest state over
WebSocket.

## 7. Suggested backend folder layout (not yet built)

```
server/
  app/
    main.py
    config.py
    api/            (aircraft.py, conflicts.py, recommendations.py, audit.py, websocket.py)
    services/       (opensky_client.py, ingestion_service.py, trajectory_service.py,
                      conflict_service.py, resolution_service.py, audit_service.py)
    models/         (schemas.py, db_models.py)
    ml/             (train_conflict_model.py, train_trajectory_model.py, inference.py, saved_models/)
    db/             (database.py, migrations/)
  requirements.txt
```

ML/data libraries to use: pandas, numpy, scikit-learn, xgboost (or
lightgbm), geopy/haversine for distance, pyproj only if coordinate
transforms are needed, PyTorch for the residual LSTM, joblib to persist
classical models, MLflow optional for experiment tracking.

## 8. Frontend — what exists and what changes

Existing components (do not rebuild, wire to real data instead):
`FlightListPanel`, `FlightDetailDrawer`, `FlightRadarMap`, `RadarCanvas`,
`ConflictBanner`, `ResolveModal`, `AISuggestionsPanel`,
`RunwayStatusPanel`, `NLPCommsPanel` (mock only — NLP is out of scope),
`TimelinePanel`, `AIAuditTrail`, `LogsPage`.

Frontend work needed:
1. Replace `mockData.js` aircraft list with real API data.
2. Add `useAircraftStream()` hook for WebSocket updates.
3. Add `useConflicts()` hook for active alerts.
4. Add `useAuditLogger()` hook sending audit events to the backend
   (`/api/audit`), replacing frontend-only logging.
5. Add loading and offline states.
6. Add role/user display in the top bar.
7. Add a "simulation mode" vs "live data mode" indicator (surfacing which
   of the 3 data modes is active).
8. Add a downloadable evaluation report page.

Run commands: `cd client && npm install && npm run dev` (dev),
`npm run build` (build). Current routes: `/` (dashboard), `/logs`
(session logs/audit viewer).

## 9. Training data strategy (real conflicts are rare — don't wait for them)

Three sources, combine all three:
1. **Real OpenSky data** — normal aircraft movement for trajectory
   prediction, visualization, and normal-behavior baseline.
2. **Synthetic conflict scenarios — synthetic PAIRINGS of real
   trajectories, never synthetic flight paths.** Take two *real* Mumbai
   flight paths and shift one in time so that they cross; vary the time
   offset, altitude difference and geometry; label via the dense-grid CPA
   rules. Real aircraft behaviour, artificial pairing.
   **Do not invent flight paths.** A model trained on invented turns learns
   our assumptions about how aircraft manoeuvre rather than Mumbai's — it
   always looks impressive and it means nothing. Real losses of separation
   are rare by design, so the *pairing* has to be manufactured; the flying
   does not. Used for conflict classifier training, resolution engine
   testing, and UI demo.
3. **Manual demo scenarios** — curated for the final presentation:
   head-on conflict, converging arrival traffic, runway congestion,
   emergency squawk 7700, weather deviation. Ensures the demo works even
   if live OpenSky has nothing interesting during evaluation.

**Critical rule: split train/validation/test by time, never by random
row** — adjacent aircraft states leak information across a random split.

## 10. Evaluation metrics (what "done" and "good" mean per component)

- **Trajectory prediction:** MAE, RMSE, cross-track error, along-track
  error, altitude error.
- **Conflict detection:** recall (most important — missed conflicts are
  dangerous), precision, false alarm rate, warning time before CPA, F1,
  PR-AUC (accuracy alone is a bad/misleading metric since conflicts are
  rare).
- **Resolution recommendation:** whether separation was maintained
  (conflict resolved in simulation), delay impact, fuel proxy, number of
  unsafe suggestions blocked, controller acceptance rate in demo
  scenarios.

## 11. Roadmap / build order — do not skip ahead

1. **Frontend stabilization** — polish UI/layout, keep mock scenarios
   working, ensure `/logs` shows all actions, add live/simulation mode
   indicator, aircraft detail drawer. *Deliverable: polished dashboard
   demo.*
2. **Backend foundation** — FastAPI replacing Express placeholder,
   `/api/aircraft/latest`, `/api/audit`, WebSocket stream, Postgres
   schema. *Deliverable: frontend reads aircraft from backend.*
3. **OpenSky integration** — ingestion service, store latest states,
   filter to Mumbai/Delhi region, stream to UI, replay fallback.
   *Deliverable: live aircraft map.*
4. **Conflict detection** — CPA rule-based detection, active conflicts
   API, conflict banner from backend, store conflict events.
   *Deliverable: real/simulated conflict alerts.*
5. **ML conflict classifier** — pairwise features, CPA-rule-derived
   labels, train XGBoost/LightGBM, compare against the rule baseline, add
   inference endpoint. *Deliverable: ML conflict prediction + metrics.*
6. **Resolution recommendation** — rule-based options, simulate each,
   rank by safety/delay/fuel/confidence, show explanations in UI.
   *Deliverable: explainable AI resolution options.*
7. **Evaluation and report** — run recorded test scenarios, export
   predictions/logs, calculate metrics, prepare evaluation slides.
   *Deliverable: final report, dashboard demo, metrics table.*

When asked to "build the next piece," infer the current phase from what
already exists in the repo and confirm before jumping ahead — e.g. don't
start the XGBoost classifier if the CPA baseline and backend API don't
exist yet. If time runs short, the minimum defensible cut is: FastAPI +
OpenSky/replay API → WebSocket stream to the existing dashboard → CPA
conflict detection → rule-based resolution → backend audit logging →
metrics on replay/synthetic scenarios. XGBoost and the residual LSTM come
after that deterministic baseline works, not before.

## 12. Constraints that affect how features get built, not just how they're described

- Never implement or suggest functionality that would let the system
  directly control aircraft or auto-apply a maneuver without controller
  acceptance.
- Every prediction/recommendation surfaced to the UI needs an attached
  confidence score and explanation field — don't build an endpoint that
  returns a bare prediction with no rationale.
- Reduce false alerts by requiring both lateral AND vertical risk checks,
  using the lookahead window, ranking by severity, using confidence
  scores, and suppressing duplicate alerts for the same aircraft pair —
  the UI should surface only the most urgent alerts, not everything.
- Labels for conflict training come from CPA rules + synthetic scenario
  generation, not real incident data (too rare, and ethically we don't
  want them).
- If a model's output looks wrong, the system must let the controller
  reject/override it, log that, and keep the rule-based safety check as a
  block on clearly unsafe suggestions — never let ML output execute
  unchecked.

## 13. Working style for this repo

- Ask before assuming which phase to build if it's ambiguous from current
  repo state.
- Prefer the deterministic/rule-based version of any component before its
  ML upgrade, and keep the deterministic version in place as a fallback
  even after the ML version ships (never delete the CPA baseline once
  XGBoost exists, never delete constant-velocity once the residual LSTM
  exists — and note that the residual formulation makes constant velocity
  impossible to delete, since it is the model's own starting point).
- For any new phase or non-trivial feature, plan the approach and get it
  confirmed before writing code (use plan mode).
- Keep justifications grounded in the research/framing in Section 2 and
  the decisions in Section 3 — don't invent new justifications for model
  or architecture choices.
- When a new decision gets made during a session that isn't already
  captured here (a specific threshold, a schema change, a library
  version pinned), append it under Section 14 below so future sessions
  inherit it.

## 14. Decisions log (append here as the project evolves)

### 2026-08-30 — Approach/terminal traffic needs a different separation rule than en-route

**Finding (measured, not assumed).** The CPA rule in
`ml_pipeline/utils/cpa_conflict_detection.py` (lateral < 5 NM AND vertical
< 1000 ft) was applied to 495,812 real aircraft pairs sampled from the first
7 OpenSky sessions. Results:

- 330 pairs met the "conflict" condition, and **91–94% of all snapshots
  contained at least one flagged pair** — i.e. the rule fires almost
  continuously on normal traffic.
- **65% of flagged pairs involved an aircraft below 2,000 ft**; 8.8% were
  below 500 ft.
- Minimum flagged separations reached 0.01 NM (~18 m), which is impossible
  for airborne aircraft.
- `on_ground == False` does NOT remove this. Adding an airborne filter
  (baro_altitude > 1000 ft AND velocity > 50 m/s) cut flagged pairs from 330
  to 116, but 91% of snapshots still contained one.

**Why.** 5 NM / 1000 ft is an **en-route** standard. Aircraft on final
approach or initial climb are legitimately much closer laterally — they are
separated by approach sequencing, runway occupancy and wake-turbulence
spacing under tower/approach control, not by en-route radar separation. As
simplified reference values: en-route radar separation is typically 5 NM,
terminal/approach radar separation typically 3 NM, and wake-turbulence
spacing on final varies roughly 2.5–6 NM by aircraft category pairing.
Vertical is typically 1000 ft below FL290. These remain **simplified
academic values, not certified regulatory standards** — same caveat as
Section 3.

**Rule going forward.**

1. Conflict detection operates on **en-route traffic only**. Apply an
   altitude floor before pairing aircraft — default **10,000 ft** — plus the
   airborne sanity filter (velocity > 50 m/s) to drop ground/taxi rows that
   `on_ground` misses.
2. Do **not** feed sub-floor pairs to the XGBoost classifier as positive
   labels. Left in, the model learns to flag routine arrivals, which is the
   false-alarm failure Section 12 explicitly warns against.
3. If terminal-area conflicts are ever modelled, they need their own
   thresholds (~3 NM) and their own label set — never the en-route numbers.
   Out of MVP scope; en-route only for now.
4. State this limitation explicitly in the evaluation report. "We restricted
   conflict detection to en-route traffic because the en-route rule
   misclassifies approach spacing" is a defensible, measured finding — and
   the 91% figure is the evidence for it.

### 2026-08-30 — OpenSky credits use a ROLLING 24h window, not a daily reset

**Correction to an earlier assumption.** Planning for the 9-slot week assumed
credits reset at 00:00 UTC. **They do not.** Evidence: account A ended 29 Aug
with 1,840 credits and the first poll of its 06:00 IST run on 30 Aug
(= 00:30 UTC, a new UTC day) reported `X-Rate-Limit-Remaining=1838`. A daily
reset would have shown ~4,000.

**Verified model (matches observation at three separate checkpoints):**

- Cost is **2 credits per poll** for the Mumbai box (71.25 sq deg, the 25–100
  tier). A 90-minute session at 10 s intervals = 540 polls = **1,080 credits**.
- Cap is **4,000 credits per rolling 24 hours, per account.** Credits return
  individually, 24 h after each poll — there is no fixed daily refill.
- `CREDIT_SAFETY_THRESHOLD = 200` stops a session early when remaining drops
  below it. `X-Rate-Limit-Remaining` **is** returned by the authenticated
  endpoint (confirmed on all three accounts), so this brake works.

**Consequences for scheduling:**

1. Three 90-minute sessions per account per day = 3,240 credits, leaving only
   **760 headroom**. This is sustainable in steady state — each day's spend
   ages out as the next day's is incurred — but the margin is thin.
2. There is **no daily headroom reset to fall back on.** Any ad-hoc manual
   session steals directly from a scheduled slot up to 24 h later. This
   happened on 29 Aug: two manual sessions on account A left it unable to
   complete its 12:00 IST scheduled run on 30 Aug.
3. Before running anything manually, check the account's live
   `X-Rate-Limit-Remaining` and confirm at least 1,280 (1,080 + threshold).

**Operational incident, same day.** The 12:00 IST run on 30 Aug started
correctly, polled for 41 minutes (249 polls), then was hard-killed with exit
code `3221225786` (`STATUS_CONTROL_C_EXIT`). Because the poll scripts hold all
data in memory and write the Parquet only in the `finally:` block, and a hard
kill bypasses `finally:`, **all 249 polls were lost — no file was written.**
The scripts have no incremental checkpointing; any crash, forced logoff or
process kill loses the entire session. Worth fixing before relying on a week
of unattended runs.

**Also recorded from the same analysis:** OpenSky returns `squawk` as null
for 100% of rows across all 774 aircraft observed. The "emergency squawk
7700" demo scenario in Section 9 therefore cannot come from live data and
must be synthetic.

### 2026-09-01 — Trajectory model rebuilt as a residual predictor; the old Bi-LSTM formulation is retired

**Why the previous model failed (measured, not assumed).** `train_bilstm.py`
normalised its targets with `y_std = train_y.std(axis=(0, 1))`, which collapses the
horizon axis and divides absolute latitude/longitude by the spatial spread of the
whole collection region (1.867 deg of latitude). 5 NM is 0.083 deg — **0.045 standard
deviations**. The entire range from a perfect prediction to a useless one occupied
0 to 0.045 of the space the loss could see. The same normalisation on the inputs
reduced the aircraft's motion inside its 10-step window to **1.9%** of one standard
deviation of the latitude feature: the network could see *where* an aircraft was but
not *which way it was going*. It scored worse than constant velocity at every horizon,
and this went unnoticed because the script printed a single MAE **pooled across all
four horizons** — the 1-minute horizon is easy enough to mask a 10-minute failure.

**Supersedes Section 3's "Bi-LSTM (bidirectional)".** The model is now a
**unidirectional** 2-layer LSTM (hidden 128, dropout 0.3) predicting the *residual
from constant velocity*, in `train_trajectory.py` (`train_bilstm.py` is deleted).
Bidirectional was wrong on principle: at inference there is no future to read
backwards from. Constant velocity is no longer merely a baseline to beat — it is the
model's own starting point, since a zero output reproduces it exactly. This satisfies
Section 13's "keep the deterministic version in place" more strongly than before: the
physics cannot be discarded, only corrected.

**New shared module `ml_pipeline/training/trajectory/framing.py`** holds the
coordinate transforms used by training, evaluation and (later) backend inference, so
the three cannot drift apart. Targets are residuals in **metres**, in a frame rotated
onto the aircraft's last observed heading: along-track, cross-track, altitude.
`apply_residual` inverts `residual_targets` exactly (verified to 1e-14 deg). Headings
are unwrapped before differencing so a 359->001 crossing is not read as a 358 deg turn.

**Data pipeline (`preprocess_sequences.py`), two fixes:**

1. Targets are now **linearly interpolated** between the two real observations
   bracketing each horizon (bracket <= 120 s, never extrapolated). The old
   nearest-observation snapping accepted a 30 s mismatch; at ~13.6 km/min that was
   **mean 0.42 NM, p95 1.40 NM, worst 5.2 NM** of pure label noise at the 1-minute
   horizon, with 28% of windows above 0.5 NM. Removing it dropped the measured
   constant-velocity 1-minute error from 0.62 NM to **0.21 NM** — that improvement
   was never the model's to win.
2. **Per-horizon masking.** A window is kept if **at least one** horizon resolves,
   with a `(N, 4)` bool `mask` array saved in each `.npz`. Requiring all four
   silently deleted every aircraft descending into Mumbai within ten minutes, biasing
   the dataset toward easy high-altitude cruise. Samples went **73,254 -> 151,613**.
   Per-horizon validity is 97.4 / 83.5 / 72.0 / **49.9%** — that 1-min-to-10-min gap
   *is* the arrival traffic. **The mask is the contract: invalid target values are
   0.0 placeholders and must never be read.**

**Loss — and a real trap.** Use `SmoothL1Loss`, never `MSELoss`; squared error is
dominated by the manoeuvring tail and trades away thousands of near-perfect
predictions to shrink a few large ones. **But `beta` is measured in normalised units,
so it interacts with the per-horizon normalisation.** At `beta=1.0` the quadratic
region reaches one residual standard deviation = **11.5 NM at the 10-minute horizon**,
putting 86% of along-track and 81% of cross-track targets inside it — i.e. it *was*
MSE for the bulk of the data. Measured consequence: 10-minute mean improved to
6.84 NM while within-1-NM **collapsed from the baseline's 32.6% to 12.9%**. At
`beta=0.05` (quadratic below ~0.5 NM at ten minutes) within-1-NM recovered to 30.6%.
**Do not raise this beta.**

**Per-horizon residual normalisation is load-bearing** now that targets are residuals:
their standard deviation grows from 540 m (1 min, along) to 21,296 m (10 min, along),
so a shared scale would let the 10-minute head dominate. On the old absolute-position
targets the equivalent weighting was a measured no-op (1.873 / 1.865 / 1.861 / 1.869).

**Evaluation is now per-horizon and per-regime** (`evaluate.py`, runnable standalone).
Never report a pooled-across-horizons metric again. Cross-track error is the
safety-relevant component; along-track error means an aircraft is late on a route it
is still following. Results are written to
`ml_pipeline/data/processed/eval_<label>.{csv,md}`.

**Measured results on the test split (3 held-out sessions, 20,611 samples):**

| horizon | CV mean | model mean | CV <5NM | model <5NM | GBT reference <5NM |
|---|---|---|---|---|---|
| 1 min | 0.21 NM | 0.16 NM | 100.0% | 100.0% | 100.0% |
| 3 min | 1.38 NM | 1.04 NM | 91.8% | 94.6% | 94.9% |
| 5 min | 3.45 NM | 2.48 NM | 79.5% | 85.0% | 87.6% |
| 10 min | 10.21 NM | 6.85 NM | 52.8% | **61.6%** | **69.7%** |

**Open finding, do not paper over it.** `reference_benchmark.py` — a non-neural
`HistGradientBoostingRegressor(loss='absolute_error')` on the identical features and
targets — reaches **69.7%** at ten minutes against the LSTM's 61.6%. The tree is
genuinely ahead, and it fits 12 independent models (4 horizons x 3 axes) versus one
shared LSTM trunk. Keep the benchmark in the repo as the standing bar and report the
gap honestly in the evaluation rather than presenting the neural model as the best
available. Validation loss was flat from epoch 12 while training loss kept falling, so
the LSTM was overfitting, not under-trained — more epochs will not close this.

**Where the remaining error lives** (10-minute, % within 5 NM): sharp turns
(>30 deg) **15.8%**, fast climb/descent **35.6%**, terminal-area traffic (<40 NM
from VABB) **38.6%**, versus en-route level flight at ~67-70%. Constant velocity
cannot model a turn, and neither model yet has route or intent information.

**Model artifact:** `server/app/ml/saved_models/trajectory_residual.pt`, holding
`model_state_dict`, feature normalisation, per-horizon residual normalisation, and a
config dict — verified sufficient to reconstruct predictions in a fresh process with
no access to the training script. The old `bilstm_trajectory.pt` is left in place.

**Training-loop note:** the whole split (~30 MB) is kept resident on the GPU and
batched by index rather than through a `DataLoader`. On this laptop GPU the per-batch
host-to-device copy, not the arithmetic, was setting the epoch time — 15 min/epoch
became ~25 s/epoch. Hyperparameters are unchanged by this.

### 2026-09-01 — CPA is evaluated on a dense 15 s grid, not the four named horizons

`compute_cpa()` took the minimum lateral separation across only the 60/180/300/600 s
predictions. The true closest point of approach almost never lands on one of those
four instants, so a pair passing within 2 NM at t = 240 s was recorded at its
separation at 180 s and 300 s — 16.2 NM — and the conflict was **silently dropped**.
This directly capped conflict-detection recall.

`compute_cpa()` now evaluates every time the two aircraft share, and
`predict_dense_grid()` / `compute_cpa_from_states()` produce a **15 s grid from 0 to
600 s (41 points)** from a raw state using the constant-velocity baseline, so the
rule-based path still runs without the neural model. The result adds
`time_to_cpa_seconds` and `is_converging` (separation decreasing at the start of the
window). The four named horizons still work as input and are still returned under
`per_horizon` for the dashboard; `cpa_horizon_seconds` is retained as an alias.
`classify_conflict()` thresholds and severity rules are unchanged.

**Measured on 4,000 synthetic pairs: the four-point rule labelled 856 conflicts, the
dense grid 1,089 — 21.4% of true conflicts were invisible to it.**
`generate_synthetic_scenarios.py` was therefore switched to the dense path: leaving it
on the sparse grid would have fixed detection while continuing to *train the XGBoost
classifier on labels produced by the bug*. `time_to_cpa_seconds` also goes from 4
distinct values to 41, making it an actually usable feature.

**Secrets status (audited 1 Sep 2026):** `.env`, the three
`OpenSky Credentials_*.json` files and `secrets/credentials.json` are all
gitignore-covered and **none is tracked, now or in any commit in history** — no
rotation and no history rewrite needed. `**/secrets/*` was added alongside the rooted
`secrets/*`, which would not cover a `server/secrets/` once the backend grows one.

### 2026-09-02 — Retrained on 23 sessions; the LSTM's gap to the tree reference nearly closed

**What changed.** Five collection sessions written since the 1 Sep run were added
(23 raw parquets, 21 session blocks after the 1800 s merge rule). Airborne states
424,414; samples **151,613 -> 198,537 (+31%)**. Splits re-cut chronologically on
whole-session boundaries: train 143,117 (15 sessions, to 1 Sep 03:43 IST), val
27,552 (3 sessions), test 27,868 (3 sessions, 2 Sep 06:01 -> 12:18 IST). Per-horizon
validity 97.4 / 83.7 / 72.4 / **50.4%** — essentially unchanged, so the arrival-traffic
skew the mask exists to preserve is stable across a week of collection.

**The new test split is harder than the old one**, so numbers are not comparable to
the 1 Sep table row-for-row — compare each model against the constant-velocity
baseline measured on the same split. CV 10-minute went from 10.21 NM / 52.8% within
5 NM to **11.02 NM / 51.8%**.

Measured on the new test split (27,868 samples):

| horizon | n | CV mean | LSTM mean | GBT mean | CV <5NM | LSTM <5NM | GBT <5NM |
|---|---|---|---|---|---|---|---|
| 1 min | 27,163 | 0.22 NM | 0.19 NM | 0.17 NM | 99.9% | 100.0% | 100.0% |
| 3 min | 23,312 | 1.40 NM | 1.13 NM | 1.02 NM | 91.5% | 93.5% | 94.5% |
| 5 min | 20,113 | 3.41 NM | 2.49 NM | 2.18 NM | 79.3% | 84.9% | 87.2% |
| 10 min | 14,030 | 11.02 NM | 6.41 NM | 5.65 NM | 51.8% | **64.5%** | **66.7%** |

**The open finding from 1 Sep is narrowing, not resolved.** The
`HistGradientBoostingRegressor` reference led the LSTM by **8.1 points** at ten
minutes on the old split (69.7% vs 61.6%); on the new split it leads by **2.2**
(66.7% vs 64.5%). The tree's own score *fell* (69.7 -> 66.7) on the harder split while
the LSTM's *rose* (61.6 -> 64.5), so the extra 31% of data helped the shared-trunk
neural model materially more than it helped 12 independent per-horizon-per-axis trees.
Keep reporting the gap honestly; do not present the LSTM as best-available yet.

**A metric that got worse, and should not be hidden.** At ten minutes the LSTM's
**within-1-NM rate is 25.9% against the baseline's 30.0%** (GBT: 32.7%). The LSTM
pulls the whole error distribution inward — mean 11.02 -> 6.41 NM, p90 32.75 ->
16.77 NM — but sacrifices some already-near-perfect predictions doing it. The GBT,
fitting the conditional median per axis with `absolute_error`, does not pay this. This
is the same beta/normalisation tension recorded on 1 Sep; `SMOOTH_L1_BETA = 0.05`
remains the best setting found, and raising it makes this worse, not better.

**Training behaviour unchanged in character.** Best checkpoint epoch 16, early stop at
epoch 26 of 60; validation loss flat from ~epoch 12 while training loss kept falling.
Still overfitting rather than under-trained — more epochs will not close the tree gap.
Wall clock ~4 minutes on the RTX 4050 with the split resident on the GPU.

**Where the error still lives** (10-minute, % within 5 NM, LSTM): sharp turns >30 deg
**24.5%** (was 15.8%), fast climb/descent **32.5%** (was 35.6%), terminal <40 NM from
VABB **38.2%** (was 38.6%), against en-route **70.1%** and level flight **75.9%**. The
extra data helped turns appreciably and vertical manoeuvres not at all. Neither model
has route or intent information, which is the obvious next lever.

**Collection note.** `session_20260902_063002_partial.parquet` is in the test split —
account A's 12:00 IST run stopped early but *did* write, so the `finally:` path works
on a caught interrupt. It is a hard kill (`STATUS_CONTROL_C_EXIT`, 30 Aug) that still
loses everything. Incremental checkpointing remains unfixed.

### 2026-09-05 — Full retrain on 33 sessions; best-checkpoint restore is now verified, not assumed

**Pipeline re-run end to end** (`preprocess_sequences.py` -> `train_trajectory.py` ->
`evaluate.py` -> `reference_benchmark.py`) over all 36 raw parquets, 33 session blocks
after the 1800 s merge rule. Airborne states 424,414 -> **627,344**; samples
198,537 -> **291,008 (+47%)**. Splits re-cut chronologically on whole sessions: train
205,757 (22 sessions, to 2 Sep 22:59 IST), val 45,637 (5 sessions), test 39,614
(6 sessions, 4 Sep 08:01 -> 5 Sep 09:28 IST). Per-horizon validity 97.3 / 83.5 /
72.0 / **49.9%** — stable across three retrains now, so the arrival-traffic skew the
mask preserves is a property of the traffic, not of any one week.

**Early stopping now proves it restored the best epoch.** `train_trajectory.py`
already reloaded `best_state` before evaluating and saving, but nothing checked it.
It now re-scores the restored weights on the validation split and raises if the result
differs from the recorded best loss by more than 1e-9 (evaluation is deterministic, so
this is an exact check), and it raises rather than silently saving an untracked model
if no checkpoint was ever recorded. This run: best epoch 19, early stop at 29 of 60,
val loss 0.235965 recorded and 0.235965 on restore.

**This test split is harder again**, so compare each model only against the
constant-velocity baseline measured on the same split — CV 10-minute went 11.02 NM /
51.8% (2 Sep split) to **10.30 NM / 50.5%**, and CV at 1 minute is notably worse
(0.22 -> 0.49 NM), so these six sessions carry more manoeuvring traffic throughout.

| horizon | n | CV mean | LSTM mean | GBT mean | CV <5NM | LSTM <5NM | GBT <5NM |
|---|---|---|---|---|---|---|---|
| 1 min | 38,110 | 0.49 NM | 0.45 NM | 0.43 NM | 98.4% | 98.5% | 98.5% |
| 3 min | 32,324 | 1.69 NM | 1.37 NM | 1.27 NM | 89.5% | 92.1% | 92.6% |
| 5 min | 27,587 | 3.65 NM | 2.69 NM | 2.39 NM | 77.3% | 83.2% | 85.1% |
| 10 min | 18,662 | 10.30 NM | 6.41 NM | 5.57 NM | 50.5% | **60.9%** | **65.7%** |

**The tree gap widened, and the 2 Sep "narrowing" should not be read as a trend.**
`HistGradientBoostingRegressor` leads the LSTM at ten minutes by **4.8 points**
(65.7% vs 60.9%), against 2.2 on the 2 Sep split and 8.1 on the 1 Sep one. Three
points across three different test splits is not a trajectory — the split changes each
time, so the honest statement is that 12 independent per-horizon-per-axis trees have
beaten the shared-trunk LSTM at ten minutes on every split measured so far, by
somewhere between 2 and 8 points. Keep `reference_benchmark.py` as the standing bar
and keep reporting the gap; do not present the LSTM as best-available.

**The within-1-NM regression is confirmed, not noise.** At ten minutes the LSTM
reaches **25.2% within 1 NM against the baseline's 29.0%** (GBT: 33.1%) — the same
sign and roughly the same size as the 2 Sep run (25.9% vs 30.0%). The LSTM pulls the
distribution inward overall (mean 10.30 -> 6.41 NM, p90 29.18 -> 16.96 NM) while
giving up some already-near-perfect predictions; the GBT's per-axis
`absolute_error` fit does not pay this. `SMOOTH_L1_BETA = 0.05` is still the best
setting found and raising it makes this worse.

**Overfitting, not under-training, again.** Validation loss was flat from ~epoch 12
while training loss fell monotonically from 0.310 to 0.216 through epoch 29. Three
runs have now shown the same shape; more epochs are not the missing ingredient.

**Where the error lives** (10-minute, % within 5 NM, LSTM vs CV): sharp turns >30 deg
**22.8%** vs 7.6%, fast climb/descent **28.6%** vs 5.5%, terminal <40 NM from VABB
**35.8%** vs 15.8%, against en-route **67.9%** and level flight **70.4%**. The model
roughly triples the baseline in exactly the regimes the baseline cannot represent,
which is the expected shape — but manoeuvring and terminal traffic remain where the
remaining error is concentrated, and neither model has route or intent information.

### 2026-09-05 — CLAUDE.md realigned to the rewritten ML approach doc; two-tier conflict classification implemented

**Source of truth.** `Flight_Right_ML_Approach.docx` was rewritten on 4 Sep and is
now authoritative for model design. Sections 2, 3, 4, 7, 9, 11 and 13 above were
corrected so they no longer contradict it. Nothing was removed from this decision log
— the entries below record how each of these positions was reached and stay as the
evidence trail.

**What changed in the sections above.**

1. **Section 2 research grounding, rewritten.** The five originally cited papers do
   not cover trajectory prediction at all: two are speech-to-text, one is controller
   staffing, two are literature summaries (one publisher-flagged as not peer
   reviewed). "Bidirectional" appears once across all five — in the speech paper,
   explaining why those authors removed it. The architecture is our own, justified by
   measurement; genuine trajectory-prediction and conflict-detection references are
   now listed for the claims that need them. **Do not cite the original five for the
   trajectory model.**
2. **Section 3 trajectory model.** Bi-LSTM predicting absolute position →
   one-directional LSTM predicting a residual correction to constant velocity; loss
   `SmoothL1Loss(beta=0.05)`, never MSE; the relative-motion input features spelled
   out; MSSR noise injection dropped (our data is ADS-B, not radar, and we have no
   Indian radar-noise measurement to base it on); Model 1b multi-path prediction
   recorded as planned-not-built with its 7.9 NM / 69.3% justification.
3. **Section 3 conflict detection.** Now two tiers — tier 1 alarm 0-3 min raises
   alerts *and* generates resolutions (93-99% caught), tier 2 advisory 3-10 min is a
   watch list that never suggests a manoeuvre (69-82% caught), tier 0 background. The
   3-minute boundary is response geometry: 38 s to get the aircraft moving, then ~40 s
   for a 1000 ft level change or ~96 s for a 30° turn at 450 kt. Also recorded: CPA on
   a dense 15 s grid rather than four horizons, and alerting on a volume wider than
   the legal minimum.
4. **Section 3 resolution.** Weights confirmed as safety .60 / delay .15 / fuel .10 /
   workload .10 / confidence .05 (an earlier draft had delay and fuel swapped), plus
   the new rule to prefer altitude changes as time-to-conflict falls, and the
   restriction that resolutions are generated for tier 1 only.
5. **Section 9 synthetic data.** Synthetic *pairings* of real trajectories, never
   synthetic flight paths — invented turns teach the model our assumptions rather than
   Mumbai's traffic.

**Alert volume is wider than the legal separation minimum, and this is deliberate.**
Legal minimum stays 5 NM / 1000 ft; the alert volume is **8 NM / 1500 ft**. Measured:
triggering at the bare minimum catches only **46%** of real conflicts, because a
prediction 1 NM out flips the decision; at 8 NM / 1500 ft we catch **99% at one minute
and 93% at three**, costing **32-34 false alarms per 1000 pairs** (rising to 36 at five
minutes and 39 at ten). Widening further to 18 NM / 2500 ft reaches 84% at ten minutes
but costs 90 false alarms per 1000 — the trade is a dial, and these are the measured
points on it. All four numbers are named constants at the top of
`ml_pipeline/utils/cpa_conflict_detection.py`.

**Tier 1 runs on constant velocity, not the neural model.** Measured: at one minute the
straight-line method catches *more* conflicts than the model, because it is already
near-perfect at that range and the model's small corrections nudge both aircraft. The
LSTM earns its place in tier 2, where the baseline degrades badly.

**Implemented this session** in `ml_pipeline/utils/cpa_conflict_detection.py`, extending
rather than replacing `compute_cpa` and `classify_conflict`:

- `assign_tier()` — tier from `time_to_cpa_seconds` alone (1 alarm ≤180 s, 2 advisory
  180-600 s, 0 background).
- `conflict_probability()` — **placeholder**, 1.0 inside the alert volume and 0.0
  outside, with a TODO marking where the real number comes from: multiplying the
  probabilities of each combination of the two aircraft's candidate paths and summing
  the combinations that conflict. That is Model 1b work; the 0.85/0.60 tier thresholds
  were chosen for that real probability, not for this placeholder.
- `escalate_pair()` — returns tier and a `notify` boolean, true only when probability
  clears the tier threshold AND time-to-CPA is inside the tier range AND both have held
  for `CONSECUTIVE_UPDATES_TO_NOTIFY = 3` consecutive updates. Also returns
  `suggest_resolution`, which is true only for a notifying tier 1 pair, and a `reason`
  string so nothing reaches the UI without an explanation (Section 12).
- `should_drop_from_tracking()` — retires a pair once separation has increased on two
  consecutive updates AND the pair is outside the alert volume. Both conditions are
  required: diverging alone is not enough, since a pair can drift apart and be
  predicted to converge again.

**Verified** by `ml_pipeline/utils/test_two_tier_demo.py` (synthetic geometry, since all
three behaviours have to be set up deliberately):

1. Converging pair with true CPA at **240 s**: the four named horizons report the
   closest approach as **9.80 NM at 300 s and classify it as no conflict**; the dense
   15 s grid reports **1.89 NM at 240 s, CONFLICT, severity high**. Escalation runs
   tier 2 advisory → notify on update 3 → tier 1 alarm on update 5, where a resolution
   is first offered.
2. Parallel traffic 12 NM apart with **one** bad heading report (180 instead of 090 on
   update 3 only): CPA collapses to 0.47 NM for that single update, probability 1.0 —
   and `notify` stays **False**, because the run reached 1 of the 3 consecutive updates
   required. Updates 4-5 return to 16.95 NM.
3. Crossing pair stepped through its closest approach: converging through update 5,
   then separation grows 3.78 → 8.74 → 19.50 → 30.43 NM and the pair is **dropped on
   update 7**, the first update with two consecutive increases while outside the alert
   volume.

**Note on numbers.** The approach doc quotes the 2 Sep training run (198,537 samples,
27,868 test). The 5 Sep entry above supersedes those figures with the 33-session
retrain (291,008 samples, 39,614 test). The doc's *design* conclusions all still hold;
only the accuracy table is one run behind.

### 2026-09-05 — Multi-path trajectory output; conflict probability is now real

**New file `ml_pipeline/training/trajectory/multipath.py`.** `train_trajectory.py` is
untouched — the single-answer residual LSTM stays as the fallback. 40 route patterns
(`N_PATTERNS`, do not reduce), KMeans on the ten-minute along/cross residual in NM,
`HistGradientBoostingClassifier` from the same 83 flattened features to the pattern
label, top `TOP_K = 5` patterns returned with renormalised probabilities and converted
to absolute positions through `framing.apply_residual`. Saved to
`server/app/ml/saved_models/trajectory_multipath.pkl`.

**Measured on test arrivals (<40 NM from VABB), ten minutes, within 5 NM:**

| method | arrivals | all test |
|---|---|---|
| constant velocity | 15.8% | 50.5% |
| single-answer residual LSTM | 35.8% | 60.9% |
| multi-path, 1 option | 38.6% | 64.0% |
| multi-path, 3 options | 57.9% | 79.0% |
| **multi-path, 5 options** | **63.6%** | **83.0%** |
| multi-path, 10 options | 68.8% | 86.5% |

**The first attempt failed the gate at 56.9%, and the cause was cluster PLACEMENT, not
cluster count.** KMeans puts centres where the data is dense, and 84% of our rows are
en-route cruise whose residual from constant velocity is near zero. Fitted on the raw
pool, one cluster absorbed **43.7%** of all rows and the remaining centres were spent
on the sparse tail. Measured oracle ceiling — the best any ranking could achieve, using
the nearest of all 40 centres:

| KMeans fitted on | arrivals ceiling | all-test ceiling | largest cluster |
|---|---|---|---|
| raw pool | 68.1% | 89.5% | 43.7% |
| arrivals only | 75.8% | 70.9% | 16.8% |
| **balanced 50/50** | **74.7%** | **88.8%** | 34.4% |

The raw-pool ceiling of 68.1% was already below a comfortable gate margin *before the
classifier made a single mistake*. Centres are now fitted on a balanced sample (all
16,638 training arrivals plus an equal random sample of en-route rows), after which
every valid row is assigned to its nearest centre — so no training data is discarded
and only placement is balanced. `N_PATTERNS` stayed at 40 throughout; the gate was not
moved to fit the number.

**Best-of-K is not an accuracy claim.** 63.6% means *one of the five* candidates landed
within 5 NM. The conflict checker examines all five, so a hit on any is a genuine hit —
but it must never be reported as "the model predicts the right answer 63.6% of the
time". Top-1 is 38.6%.

**The stated probabilities are badly over-confident, and this is load-bearing.**
Reliability on test arrivals, all candidate options pooled:

| stated band | mean stated | observed | gap |
|---|---|---|---|
| 0.30-0.40 | 0.348 | 0.238 | -0.110 |
| 0.60-0.70 | 0.649 | 0.276 | -0.373 |
| 0.80-0.90 | 0.852 | 0.410 | -0.442 |
| 0.90-1.01 | 0.972 | 0.674 | -0.298 |

When the classifier says 90%, it is right 67% of the time; at 60-70% it is right 28%.
This matters directly because `TIER_1_PROBABILITY_THRESHOLD = 0.85` and
`TIER_2_PROBABILITY_THRESHOLD = 0.60` are compared against these numbers — an
over-confident probability makes tier 1 fire more readily than its stated confidence
justifies. **Calibrate before tuning those thresholds any further**
(`CalibratedClassifierCV` on a held-out slice is the obvious next step). Note the
gap is *negative* everywhere above 0.20 and positive below it, which is the classic
shape of an uncalibrated boosted classifier, not a data problem.

**Wired into `ml_pipeline/utils/cpa_conflict_detection.py`.** New
`compute_cpa_from_paths(paths_a, paths_b)` takes `(probability, predictions)` pairs per
aircraft, checks all K x K combinations, and sums the joint probability of those
breaching the alert volume. `conflict_probability()` now returns that value when
present and falls back to the old 1.0/0.0 rule otherwise, so the rule-based path still
runs without the multi-path model. The returned result is a normal CPA result — it
drops straight into `classify_conflict`, `assign_tier` and `escalate_pair` — and
reports the worst breaching combination as its representative geometry, or the most
likely combination when nothing breaches. Measured over 200 test arrival pairs: 73% of
pairs score 0.0, 10% score 1.0, and **18% land strictly between**, so the placeholder's
binary output is genuinely replaced.

**Known limitation, not yet fixed.** The multi-path model predicts at the four named
horizons only, so the K x K CPA check runs on four points and reinherits exactly the
sparse-grid blind spot recorded on 1 Sep (a pair closest at t = 240 s is measured at
180 s and 300 s). The rule-based path is unaffected — it still builds its own dense
15 s grid from constant velocity. Interpolating the candidate paths onto the 15 s grid
before pairing is the fix and is the next thing to do here.

**Also unchanged and worth restating:** patterns are learned only from windows whose
ten-minute target exists (50.4% of samples), which are disproportionately flights still
airborne ten minutes later. Pattern 1 still holds 47.7% of *assigned* rows even after
balanced placement — that is the near-zero-residual straight-flight pattern and is a
property of the traffic, not a fitting artifact.

### 2026-09-05 — Conflict classifier rebuilt: predicted features, real-outcome labels

**The defect, verified rather than inferred.** `generate_synthetic_scenarios.py` took
one real aircraft, invented a second beside it, extrapolated both at constant velocity,
and labelled the pair by applying the separation rule to that extrapolation. Two of the
nine features were the extrapolated CPA distances and the label was
`lateral < 5 NM and vertical < 1000 ft` over those same two numbers. Recomputing the
label from those two features alone reproduced it for **40,000 of 40,000 rows, exactly
100.0000%**. The reported PR-AUC of 1.0 was fully explained by that. Standard target
leakage, symptom and definition per Kaufman, Rosset & Perlich, *Leakage in Data Mining*
(KDD 2011), <https://dl.acm.org/doi/10.1145/2020408.2020496>.

**The rebuild, signed off by Archit on 5 Sep.** Features from the constant-velocity
PREDICTION; label from where two REAL aircraft actually went. Both aircraft must
therefore be real, because an invented aircraft has no real future to check against —
its only future is the straight line we drew, which is what made the old setup circular
by construction.

- **Anchors.** Every point in the raw data where an aircraft has 10 past states and a
  **complete** observed ten-minute future on the 15 s grid (41 points), every point
  bracketed by real observations no more than 120 s apart. Nothing extrapolated past
  the end of a track. 539,568 en-route states yield well over 60,000 such anchors; the
  pool is capped at 60,000 for memory.
- **Pairing stays synthetic, the flying does not** (Section 9 unchanged). Aircraft B's
  entire future track is moved and rotated as one rigid piece, which preserves every
  distance and angle inside it, so its real turns, climbs and speed changes survive
  exactly. Only its position and orientation change.
- **Aiming uses t=0 knowledge only.** B is placed on a circle around A's
  *constant-velocity predicted* position at a random 180-600 s, at the radius B covers
  in that time, so both arrive together. A's real future is never consulted: aiming
  with the answer would manufacture a correlation between "A turned" and "conflict"
  that is an artifact of the generator rather than a fact about traffic.
  `INTENDED_AIM_JITTER_DEG` is **2.0**; a trial at 12.0 threw B about 8 NM wide at a
  40 NM approach and suppressed nearly every intended encounter.
- **Labels** come from `compute_cpa` on the two real tracks — the same audited function
  the rule-based detector uses, so feature side and label side cannot drift.
- **Developing encounters only.** Any pair already inside the alert volume at t=0 is
  rejected and resampled. 398 of 40,398 attempts were rejected.

**Output:** `ml_pipeline/data/synthetic/encounters_real_outcome_20260905_152853.parquet`,
40,000 rows, **2,581 real conflicts (6.45%)**, 24 features, 31 sessions,
24 Aug 22:10 → 5 Sep 09:19 IST. The old `conflict_scenarios_*.parquet` glob is
deliberately **not** matched by the trainer, so a circular file cannot be picked up by
accident.

**Leakage measured after the rebuild:** the separation rule applied to the *predicted*
CPA reproduces the label for **95.60%** of rows, not 100%. The **1,760 disagreeing
rows** are the entire learning problem. `assert_no_leakage()` in `train_xgboost.py`
raises above 99%.

**Test results (4,690 rows, 5 sessions, 4 Sep 08:01 → 5 Sep 09:19 IST, strictly later
than train and validation):**

| method | recall | precision | F-beta2 | FA/1000 | missed | headline (≥3 min) |
|---|---|---|---|---|---|---|
| rule at legal minimum 5 NM/1000 ft | 0.8251 | 0.6203 | 0.7740 | 32.6 | 53 | 81.7% |
| rule at alert volume 8 NM/1500 ft | 0.8812 | 0.4356 | 0.7315 | 73.8 | 36 | 87.3% |
| **XGBoost at selected threshold 0.0984** | **0.9406** | 0.4113 | 0.7480 | 87.0 | **18** | **93.7%** |

PR-AUC **0.8024** against a conflict rate of 0.0646. Not 1.0, which is the point.

**The comparison that settles whether the model earned its place.** Recall is easy to
buy with false alarms, so the model was also scored at the rule's *exact* false-alarm
rate: at 73.8 per 1000, model recall is **0.9373 vs the rule's 0.8812 (+5.6 points)**
and the headline metric is **93.3% vs 87.3% (+6.0 points)**. The gain is real, not
bought.

**Why it wins, and it is explainable.** Of the real conflicts the alert-volume rule
misses, **99.0% are vertical misses**: the pair is already predicted to pass within
8 NM laterally, but straight-line extrapolation puts them a median **2,825 ft** apart
vertically when they actually end up **498 ft** apart. On those rows the faster
climber's vertical rate is a median **2.60 m/s against 0.33 m/s across all rows** —
eight times higher. The model learned to distrust predicted vertical separation when an
aircraft is climbing or descending hard. Feature importance agrees:
`predicted_is_converging` 0.338 and `current_vertical_separation_ft` 0.207 lead, with
the vertical-rate and vertical-acceleration trust features behind them.

**GATE 1 FAILED and was not tuned away.** Test recall **0.9406 against the 0.95 floor**.
Diagnosis: `select_threshold` returns the *highest* threshold still meeting the floor on
validation, which by construction sits exactly on the edge (validation recall 0.9511).
A later test split then falls a little below. This is a property of the selection rule,
not of the model — the model clears 0.95 comfortably at any slightly lower threshold.
Selecting for a margin above the floor is the obvious remedy and **changes when a
controller is alerted, so it needs sign-off** and was not done. GATE 2 (beats the
rule-based detector on F-beta2) **PASSED**, 0.7480 vs 0.7315.

**Unchanged and still required:** the CPA rule remains in place underneath as the
deterministic safety net, per Section 13. It is now also the source of the model's
features, so it cannot be removed.

### 2026-09-06 — One-command training pipeline, calibration for both learned probabilities, dense-grid multi-path pairing, and the inference bridge

**Context.** Work done on this machine (no raw data, no GPU) on the local branch
`fable-backend`, to be trained for real by Archit on the RTX 4060 laptop. Nothing here
changes what any model predicts or what any label means. **No headline number in this
file changed**: every metric reported below the 5 Sep entries still stands until the
real run replaces it. Verified by an end-to-end smoke test on invented tracks
(`ml_pipeline/tests/smoke_test.py`), whose gate values are meaningless by design and
are not quoted anywhere.

**1. `ml_pipeline/run_pipeline.py` + `check_environment.py` + `README_TRAINING.md`.**
Runs the seven existing scripts in order as subprocesses, tees every line to
`ml_pipeline/reports/logs/<run>/<step>.log`, stops at the first failure, and writes
`ml_pipeline/reports/training_report_<run>.md` with every GATE line, the headline block,
tables and calibration numbers. `check_environment.py` refuses to start without a GPU
(override `FLIGHT_RIGHT_ALLOW_CPU=1`) or with fewer than 3 raw sessions. The README
covers the one Windows trap that matters: `pip install torch` installs the CPU build;
the CUDA build needs `--index-url https://download.pytorch.org/whl/cu128`.

**2. Multi-path calibration: temperature scaling, not `CalibratedClassifierCV`.**
Source: Guo, Pleiss, Sun & Weinberger, *On Calibration of Modern Neural Networks*,
ICML 2017, <https://arxiv.org/abs/1706.04599>. One scalar T divides the classifier's
raw per-class scores before the softmax; fitted on the validation split by minimising
negative log-likelihood (golden-section search on log T, convex objective). Reasons it
was preferred over the sklearn wrapper named in the 5 Sep entry: (a) it is monotone, so
the top-5 patterns and every best-of-K figure are identical before and after — asserted
in the script; (b) 40 classes on a validation split of ~20k rows leaves several patterns
with too few examples for a per-class sigmoid or isotonic fit, and one shared parameter
cannot overfit. The script prints reliability tables and expected calibration error
(Naeini et al., AAAI 2015) before/after, on arrivals and on all test rows, and stores
`temperature` plus the ECE numbers in the pickle. `inference.py` reads it; a pickle
without the key behaves exactly as before (T = 1).

**3. Dense-grid pairing for candidate paths.** `densify_path(current, predictions)` in
`cpa_conflict_detection.py` puts t = 0 at the aircraft's present position and linearly
interpolates between the four predicted horizons onto the 15 s grid; never extrapolates
past 600 s. `compute_cpa_from_paths(..., current_a, current_b)` applies it to every
candidate. Linear segments add no assumption the model did not make. Unit test: two
aircraft crossing at t = 240 s, four-point check reports > 8 NM and probability 0.0,
dense check reports < 1 NM at 240 s and probability 1.0. `multipath.py` now also
measures, on 300 relocated test pairs, how many pair probabilities change once
interpolated — the number is printed under "Dense-grid check".

**4. Conflict classifier (`train_xgboost.py`), four additions, alerts unchanged.**
- **GPU:** `device="cuda"` with `tree_method="hist"` when XGBoost can see one, probed
  rather than assumed; `FLIGHT_RIGHT_FORCE_CPU=1` overrides. Hyperparameters untouched.
- **Platt calibration on validation** (Platt 1999; Niculescu-Mizil & Caruana, ICML 2005,
  <https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf>). Sigmoid,
  not isotonic, because it is strictly monotone: the threshold is mapped through the same
  function and the script **raises if the test alert set differs by a single row**.
  Brier score and ECE before/after are printed; `platt_a`, `platt_b` and the calibrated
  threshold are saved as booster attributes.
- **WHAT-IF recall margins** 0.005 / 0.01 / 0.02: threshold, test recall, precision,
  false alarms per 1000, missed, headline metric and gate status per row, marked "NOT
  applied". Gives Archit the numbers for Part 4 item 2 without moving anything.
- **SHAP:** XGBoost's native TreeSHAP (`pred_contribs=True`; Lundberg, Erion & Lee,
  arXiv:1802.03888) — mean |contribution| per feature printed beside gain importance, and
  per-row contributions returned by `inference.py` as the alert's explanation. No new
  dependency. A `xgboost_conflict_model_card.json` is written beside the model with every
  number the run printed.

**5. `encounter_features()` and `manoeuvre_summary()` in `generate_synthetic_scenarios.py`.**
The 24 features were computed inline in `_try_build_row`; they are now one function
that both the generator and the backend call, with an assertion that its key order
equals `FEATURE_COLUMNS`. Pure refactor — the generator's output is byte-for-byte the
same computation.

**6. `server/app/ml/inference.py`.** `TrajectoryPredictor`, `MultiPathPredictor`,
`ConflictClassifier`, and `ConflictEngine.assess_pair(history_a, history_b, pair_history)`
which runs: rule CPA on the dense grid (always) → multi-path K x K on the dense grid
(tier 2 only; tier 1 stays on constant velocity per Section 3) → XGBoost calibrated
probability + top-5 SHAP reasons → `escalate_pair` with the 3-consecutive-updates rule.
Every result carries `sources`, `model_versions` and a `reason`. Missing model files
degrade to the rule path and are listed in `missing`. Verified on smoke-test models:
a converging pair escalates to tier 1 alarm on update 3 with all three sources present.

**7. `FLIGHT_RIGHT_DATA_ROOT`.** Every pipeline script now resolves its data and model
paths under this variable when set (default: project root). Exists so the smoke test can
run the real scripts in a temporary directory and never touch real data or saved
models. `FLIGHT_RIGHT_NUM_EPOCHS` and `FLIGHT_RIGHT_N_SCENARIOS` exist for the same
reason. Unset, nothing changes.

**8. First automated tests.** `ml_pipeline/tests/test_units.py` (8 tests: densify,
Platt monotonicity and slope, temperature NLL and ranking, ECE, feature order,
heading unwrap, window layout) and `smoke_test.py` (whole pipeline on fake data in a
temp dir, then `inference_check.py`). Both pass on this machine.

**Two platform findings recorded so nobody re-diagnoses them.** (a) `train_trajectory.py`
now enables cuDNN benchmark and TF32 on CUDA — fixed shapes every batch, loss in
normalised units, no precision concern. (b) On macOS, torch, scikit-learn and xgboost
each bundle a `libomp`; with all three in one process torch's first parallel region
deadlocks (exit -11 / hang in `load_state_dict`). `inference.py` imports xgboost first
and pins torch to one thread on macOS-without-CUDA. Not an issue on the Windows/CUDA
training machine; the workaround is guarded to macOS only.

**Corrections to earlier text.** PROJECT_STATUS.md says the poll scripts have no
incremental checkpointing; `scheduled_poll.py` (and b/c) do write a `_partial.parquet`
every 60 polls (`CHECKPOINT_EVERY_POLLS`), so a hard kill loses at most ~10 minutes,
not the session. Corrected there.


### 2026-09-06 — Full pipeline re-run from raw data; end-to-end verification script added

**Every stage was re-run in order on the current 35 raw parquets, and each reproduced
its documented result.** This was a workflow check, not a tuning run: nothing was
changed to improve a number.

| stage | script | result |
|---|---|---|
| 1. sequences | `preprocess_sequences.py` | 291,008 samples from 627,344 airborne states; per-horizon validity 97.3 / 83.5 / 72.0 / 49.9% |
| 2. trajectory LSTM | `train_trajectory.py` | GATE **PASS**; 10-min within-5-NM **60.8%** vs CV 50.5% |
| 3. tree reference | `reference_benchmark.py` | GATE **PASS**; 10-min **65.7%** |
| 4. multi-path | `multipath.py` | GATE **PASS**; best-of-5 on test arrivals at ten minutes **63.6%** |
| 5. encounters | `generate_synthetic_scenarios.py` | 40,000 rows, 2,581 real conflicts (6.45%), leakage 95.60%, 0.00% at t=0 |
| 6. classifier | `train_xgboost.py` | headline **93.7%**; GATE 1 **FAIL** (recall 0.9406 vs 0.95), GATE 2 **PASS** |
| 7. verification | `verify_pipeline.py` | **57 of 57 checks passed**, exit code 0 |

**Reproducibility is confirmed, with one honest caveat.** Stages 1, 3, 5 and 6 came back
bit-identical to the 5 Sep run, including the 40,000-row encounter file, because they
are fully seeded. Stage 2 returned 60.8% at ten minutes against the recorded 60.9%; that
0.1-point drift is cuDNN kernel non-determinism, not a change in the pipeline. The tree
reference remains **4.9 points ahead of the LSTM** at ten minutes (65.7% vs 60.8%),
consistent with the 4.8 recorded on 5 Sep. Do not present the LSTM as best-available.

**New file `ml_pipeline/utils/verify_pipeline.py`** — the project's first automated
check. It loads every saved artifact in a fresh process, with no access to the training
scripts' state, and asserts on shape and magnitude rather than on quality. Quality stays
in `evaluate.py`. What it covers:

- **Data contract.** Splits carry `X`, `y`, `mask`, `timestamps`; window is 10x8;
  targets are 4x3; **masked-out targets are actually 0.0** (the mask contract, previously
  documented but never enforced); validation starts after training ends and test after
  validation, so the time-based split is verified rather than assumed.
- **Framing.** `apply_residual(residual_targets(y))` round-trips to within 1e-9 degrees.
  This is load-bearing: training writes one and inference reads the other, so any drift
  would silently corrupt every prediction the backend would ever serve.
- **Model 1.** Rebuilds the architecture from the saved config, runs it, and checks the
  output is real latitude/longitude inside the collection box with plausible altitudes,
  then re-runs the constant-velocity gate.
- **Model 1b.** Five candidates per aircraft, probabilities summing to 1 (worst deviation
  3.33e-16), ordered most likely first, and genuinely distinct (median spread 28.3 NM at
  ten minutes).
- **Model 2.** The saved feature list must equal the generator's `FEATURE_COLUMNS`, no
  outcome column may appear among the features, recall must reproduce the value stored in
  the model file, the model must beat the geometric rule, and **the label must not be
  recomputable from the features** — the circular-label defect, now checked on every run.
- **End to end.** A real pair from the test data, plus a **deliberately converging
  head-on pair**, because two aircraft drawn at random are almost always far apart and the
  alarm path would otherwise never be exercised. The constructed pair produces CPA 0.62 NM
  at 120 s, severity critical, tier 1; the alarm correctly does **not** fire on update 1
  and does fire on update 3, carrying the reason string
  `"alarm: closest approach 0.62 NM / 0 ft in 120 s, confirmed on 3 consecutive updates."`
  and `suggest_resolution=True`, which only a notifying tier 1 pair may have.

**Two defects in the checker itself were found and fixed while writing it**, both worth
recording because they are the kind of thing that makes a green test meaningless. It
originally sampled the first 3,000 rows of each split, which is one stretch of one
afternoon rather than the test period; it now samples evenly across the split. And its
only end-to-end pair was 46 NM apart and diverging, so every alerting assertion passed
without the alarm ever firing.

**Unchanged by this session:** no model architecture, hyperparameter, threshold or gate
was touched. GATE 1 on the classifier still fails at 0.9406 for the reason diagnosed on
5 Sep, and was again left failing rather than tuned.


### 2026-09-06 — Model 3 built: rule-based resolution engine, and a measured correction to Section 3

**New file `ml_pipeline/utils/resolution_engine.py`** (699 lines). Generates the three
option types Section 3 requires — altitude, heading, speed — each carrying target
aircraft, manoeuvre type, magnitude, resulting separation, delay and fuel estimates,
confidence, and a controller-readable explanation. Ranked by the fixed weights
safety 0.60 / delay 0.15 / fuel 0.10 / workload 0.10 / confidence 0.05. Tier 1 only:
the `suggest_resolution` flag from `escalate_pair` is obeyed, so a tier 2 advisory is
never offered a manoeuvre. Nothing is ever applied; options are returned for the
controller to accept, dismiss or override.

**The design decision that makes it honest: manoeuvres are flown, not teleported.**
Every candidate is simulated at 1-second resolution through
`RESPONSE_DELAY_SECONDS = 38` (controller decision 15 s + radio and readback 15 s +
pilot reaction 8 s) during which **nothing moves at all**, then at real rates — standard
rate turn 3 deg/s, level change 1500 ft/min, speed change 0.35 m/s^2. The naive version
would move the aircraft instantly and report conflicts solved that physically cannot be,
which is wrong in the dangerous direction.

**A design simplification found during implementation.** The first version carried a
separate `achievable_in_time` test alongside `resolves`. That was redundant *and* wrong:
because the simulation already contains the response delay and the real turn rates, a
manoeuvre that is too slow simply fails to prevent the violation. The test now walks
every second of the window and asks whether **both** separations fail at once at any
instant, rather than testing only the closest-approach sample — a pair can be tightest
laterally while comfortably stacked vertically and lose separation at a different moment
entirely.

**MEASURED CORRECTION TO SECTION 3 — the "prefer altitude as time-to-conflict falls"
rule does not hold as a blanket rule.** Section 3 states it as a physics-backed
requirement on the ranker, citing 40 s for a 1000 ft level change against 96 s for a
30 degree turn at 450 kt. The arithmetic is right. The conclusion is not general.

Swept across a head-on pair at FL350, 230 m/s each, varying only time-to-CPA:

| time to CPA | altitude options that work | heading options that work |
|---|---|---|
| 90 s | 0 | 0 |
| 105 s | 4 | 4 |
| 120 s | 4 | 6 |
| 135 s and beyond | 4 | 8 |

**There is no window in which the climb works and the turn does not.** They become
available at the same time. In a head-on encounter a turn changes the crossing geometry
very quickly, so the 96-second figure — which is the time to open 5 NM of *lateral
displacement* — overstates what the turn actually needs when the two aircraft are
closing at 460 m/s.

Altitude does still rank first, but for a different reason than Section 3 gives: its
**workload score is 1.00 against the turn's 0.50**, because a level change is one
instruction the controller can watch working, whereas a vector must be remembered and
later undone. That is a real advantage and it survives; the physics-availability
argument does not.

**The engine therefore tests each encounter rather than applying a standing
preference.** That is the safer design either way: the standing preference would have
been wrong in this geometry, and a geometry where it is right is still caught, because
the option that fails is simply rejected. **Section 3 has not been edited** — this is
recorded here as the measurement that qualifies it, per Section 1a Part 3.

**A second measured result, and the more important one.** At 90 seconds to CPA, **all 26
candidate instructions are rejected**. Not the climb, not the turn, not the speed change.
38 of those 90 seconds are gone before the aircraft moves, and nothing an airliner can
fly in the remaining 52 seconds opens 5 NM or 1000 ft in time.

That is independent confirmation of the three-minute tier boundary. The boundary was
chosen from response geometry worked out on paper; this simulation reaches the same
place by flying every option and finding none arrives. **An alert raised well inside
three minutes is real and useless**, which is exactly why tier 1 stops where it does.

**Safety envelope, enforced rather than declared:** en-route floor 10,000 ft, ceiling
45,000 ft, speed 150-280 m/s. Violations are returned as `blocked` with a reason string
and can never be offered, so Section 10's "number of unsafe suggestions blocked" is
available as a metric.

**Delay and fuel are coarse proxies and the code says so.** Track-mile arithmetic with a
climb cost of 120 equivalent cruise-seconds per 1000 ft. No engine data, no weight, no
wind. Good enough to rank three options against each other, not good enough to quote to
an airline; every explanation string says "approximate".

**Verification.** `verify_pipeline.py` gained 16 checks covering Model 3 and now runs
**73 of 73 passing**. Among them: the weights sum to 1.0; nothing moves before 38 s;
options are ranked, explained, one per type, and all actually restore separation; a
tier 2 pair is refused; a 90-second pair produces no options at all with a reason on
each rejection; and a descent through the en-route floor is blocked.


### 2026-09-06 — The two branches merged, and Model 3 wired into the inference bridge

**The merge.** `origin/backend` carried three commits written while Model 3 lived only
on another branch. Both documents conflicted because both sides had appended to the same
sections. Resolved by keeping both sides in full: every change-log entry from each was
retained, and each status-table row was taken from whichever side was factually current.
The incoming rows were newer everywhere except **Model 3, which the incoming side
recorded as NOT STARTED** because it had not seen it.

**The gap the merge exposed.** `server/app/ml/inference.py` ran rule → multi-path →
classifier → escalation and stopped. It contained **zero references** to
`resolution_engine`, so the chain ended at "there is a conflict" and never reached "here
is what you could do about it". Nothing crashed and no test failed; the bridge simply had
no way to know Model 3 existed when it was written.

**Wired in as step 5 of `assess_pair`.** Three decisions worth recording:

1. **Model 3 is fed the RULE path CPA, not the multi-path result.** Tier 1 runs on
   constant velocity by decision (Section 3) and resolutions are tier 1 only, so the rule
   CPA is the geometry the alarm was actually raised on. The engine re-flies every
   candidate itself in any case, so it never inherits a predicted path.
2. **`escalation` is passed through rather than re-deriving the gate.** The engine obeys
   `suggest_resolution` internally, so tier 2 and a tier 1 pair that has not yet held for
   three consecutive updates both get a reason instead of a manoeuvre. Re-deriving the
   condition here would have created a second place for the tier rule to drift.
3. **Imported directly, not loaded like a model.** Model 3 is rules and kinematics with
   no saved artifact, so there is no version to check and nothing to degrade to.

The result always carries a `resolution` block, `offered` true or false with a reason, so
the dashboard never has to handle a missing key. Section 10's "unsafe suggestions
blocked" count is exposed as `blocked_unsafe` with per-instruction reasons.

**Verified across the three cases that matter**, via the bridge rather than the engine:

| time to CPA | tier | offered | outcome |
|---|---|---|---|
| 165 s | 1 | yes | 26 candidates evaluated, 2 ranked options, Model 3 named in `sources` |
| 60 s | 1 | no | "No manoeuvre in the candidate set restores separation in the time available" |
| 300 s | 2 | no | refused as an advisory, per the tier rule |

The 60-second case is the situation the existing `inference_check.py` sets up, which is
why that check shows three sources rather than four. That is correct behaviour, not a
regression.

**`verify_pipeline.py` gained a section 8**, seven checks on the bridge, and now runs
**80 of 80 passing**. It asserts that a result always carries a resolution block, that a
confirmed tier 1 alarm gets ranked and explained options as plain JSON-ready data, that
Model 3 is named among the sources, that tier 2 is still refused, and that an
unresolvable pair produces a reason rather than an invented suggestion. This section
exists specifically because the gap it covers was invisible to every existing test.

**Unchanged:** no model, threshold, hyperparameter or gate was touched. The teammate's
8 unit tests and `inference_check.py` both still pass.


### 2026-09-06 — First full pipeline run on real data; calibration measured, headline 94.0%

**Run via `ml_pipeline/run_pipeline.py`** on the laptop (RTX 4050, not the 4060 the
script expects; it warns and proceeds). All seven steps completed. Report:
`ml_pipeline/reports/training_report_20260906_140317.md`.

| step | outcome |
|---|---|
| preprocess | OK |
| Model 1 residual LSTM | GATE **PASS** |
| non-neural reference | GATE **PASS**, 65.7% at ten minutes |
| Model 1b multi-path | GATE **PASS**, 63.6% best-of-5 on arrivals |
| encounters | OK, 40,000 rows |
| Model 2 classifier | GATE 1 **FAIL** 0.9439, GATE 2 **PASS** |

**Headline metric 93.7% -> 94.0%** (267 of 284 conflicts caught with at least three
minutes of warning). Rule at the alert volume 87.3%, rule at the legal minimum 81.7%.

**Calibration ran for the first time and works.** Multi-path temperature **1.729**,
confirming the raw classifier was over-confident exactly as recorded. Expected
calibration error, arrivals **0.054 -> 0.019**, all test rows **0.040 -> 0.012**. Every
reliability band improved and the worst gap roughly halved. Classifier Platt
calibration: Brier 0.0298 -> 0.0236, calibration error 0.0322 -> 0.0074, and **the alert
set is identical before and after (740 alerts)** — calibration changed the meaning of the
number, not the decision. That property is worth keeping: it means recalibrating can
never silently change who gets alerted.

**GATE 2 is now marginal and this should not be glossed over.** The model beats the
rule-based detector on F-beta2 by **0.7326 to 0.7315**, a margin of 0.0011, where the
previous run had 0.7480 to 0.7315. Recall rose (0.9406 -> 0.9439) but precision fell
(0.4113 -> 0.3865) and false alarms rose (87.0 -> 96.8 per 1000). The threshold
selection landed on a more aggressive operating point this run. The model still catches
more real conflicts than the rule at every comparison, but on the combined measure it is
now barely ahead. Watch this on the next run rather than treating GATE 2 as safely passed.

**An operational defect in the runner, worked around rather than fixed.** The first
invocation stopped at `train_lstm` reporting exit **3221226505** (`0xC0000409`,
STATUS_STACK_BUFFER_OVERRUN). The step had in fact **succeeded**: the gate printed PASS,
the model file was written, and it loads cleanly in a fresh process with all 18 weight
tensors and the right config. The crash is at interpreter shutdown, the usual Windows
signature of a CUDA or OpenMP teardown failure, and has nothing to do with the training.
The runner treats any non-zero exit as a failed step and halts, so an unattended run
stops there every time. Resuming with `--from benchmark` completed the remaining four
steps. Worth fixing in `run_pipeline.py` — the runner should decide success from the
step's own gate line and artifacts, not from the exit code alone — but it is the
teammate's file and was left alone.

**Verified after the retrain:** `verify_pipeline.py` 80 of 80, teammate's 8 unit tests
OK, both against the newly written model files.


### 2026-09-07 — Model 3 checks predicted paths and surrounding traffic, not one line and one pair

**Two changes to `ml_pipeline/utils/resolution_engine.py`, both requested by Archit.**

**1. The aircraft that is NOT moving is now checked as weighted predicted futures.**
Previously it was flown in a straight line. The aircraft being told to manoeuvre still
must be simulated -- its learned prediction describes a future we are about to cancel --
but the other one is carrying on undisturbed, and the straight line is measurably wrong
at the far end of a tier 1 alarm: at three minutes it misses by more than 5 NM in a
tenth of cases, wider than the separation standard the suggestion exists to protect.

`path_grids()` interpolates each candidate through the audited `densify_path`, and
`_risk_against()` returns the summed probability of the futures in which the manoeuvre
still fails. `RESIDUAL_RISK_LIMIT = 0.05`: a manoeuvre must work across futures carrying
at least 95% of the probability. Demanding safety against all five including a
0.02-probability outlier would reject nearly everything; checking only the most likely
path is the behaviour being replaced. Residual risk also multiplies into the confidence,
so a manoeuvre that fails against 3% of futures is offered with lower confidence rather
than silently treated as certain.

**2. Every manoeuvre is checked against all other nearby aircraft.** This is the domino
effect, a named failure with an established metric (Domino Effect Parameter), and level
changes are specifically called out as its most common cause -- see the
[MDPI review of conflict resolution methods](https://www.mdpi.com/2226-4310/7/6/79) and
[Stability of Intersecting Aircraft Flows](https://arxiv.org/pdf/1010.0448). An option
that resolves this pair but endangers a third aircraft is rejected, carries
`creates_conflict_with`, and is counted separately as `rejected_domino`.

**Verified by hand, not assumed.** Scenario: AI2841 east and 6E455 west at FL350, in
conflict; UK955 east 2000 ft below. Descending 6E455 by 2000 ft resolves the first
conflict and puts it **head-on into UK955, losing separation at 79 s**. Checked against
each of UK955's five predicted paths individually and against a plain straight line --
all six agree it is a genuine secondary conflict. The engine rejects it and names UK955.
That is precisely the level-change domino the literature describes.

**Cost, measured earlier on real traffic density:** 0.5 s per conflict at median density
(34 aircraft), 0.9 s at the busiest snapshot (56). The data arrives every 10 s, so this
fits with the window mostly free. Candidate paths are densified once per aircraft rather
than once per manoeuvre, which is what keeps it affordable across 26 candidates.

**Backward compatible by design.** With no paths supplied the engine falls back to the
straight line and produces byte-identical output to before, so the deterministic path
still runs without the multi-path model, as Section 13 requires.

**`server/app/ml/inference.py`** passes the multi-path candidates through and accepts a
`traffic` argument. The result surfaces `checked_against`, `rejected_new_conflict`,
`new_conflict_detail`, and per-option `residual_risk` and `new_conflict_risk`.

**Verification:** `verify_pipeline.py` gained a section 9 with 7 checks and now runs
**87 of 87**. Among them: that a third aircraft is actually named in a rejection, that
nothing offered carries new-conflict risk over the limit, and that adding traffic can
only ever remove options and never add them. The teammate's 8 unit tests and
`inference_check.py` both still pass.


### 2026-09-07 — Alert feed: repeat suppression and low-confidence collapsing, with the no-loss guarantee made structural

**Measurement first, because it is what motivated the work.** On the held-out test split
the classifier raises **740 alerts, of which 454 (61.4%) are false — precision 0.386**.
Two decompositions matter more than that total:

- **Only 41 of the 740 are tier 1**, the audible alarm that also carries resolutions.
  27 are real and 14 false, precision **0.659**. The other 699 are tier 2 watch-list
  rows at precision 0.371. **96.9% of all false alarms are silent watch-list rows.**
- Feeding all 41 tier 1 alarms through Model 3: 1,066 candidate instructions evaluated,
  31 alarms produce at least one option, 10 produce none, **77 instructions offered in
  total — 36 for real conflicts and 41 for conflicts that never happen (53.2%)**.

Replaying the rule detector over two real one-hour OpenSky sessions, the same encounter
alerts **9.7x and 9.9x** over: 297 messages for 30 distinct encounters, 145 for 15.
Nothing in the repo suppressed that. `grep` over `ml_pipeline/` and `server/` returned
zero implementations, despite Section 12 requiring duplicate suppression and severity
ranking, and Part 5 naming repeat suppression as one of only two supported levers.

**New file `ml_pipeline/utils/alert_feed.py`.** Per-pair memory across updates, sitting
between `assess_pair` and the dashboard. It does two things and neither is a detection
change:

1. **Repeat suppression.** A pair already on screen does not raise a new interruption
   unless something got worse. Every escalation test in `_notification_decision` runs
   ahead of every suppression test, so nothing below can veto a decision made above it.
   Re-fires on: tier falling, severity rising, resolutions appearing, the option set
   changing or emptying, crossing 120/60/30 s to CPA, the predicted CPA closing by
   `REALERT_LATERAL_CLOSE_NM = 1.0`, probability rising by
   `REALERT_PROBABILITY_STEP = 0.15`, and a `REALERT_SECONDS = 120` heartbeat so a long
   encounter cannot go stale. A pair unseen for `FORGET_SECONDS = 300` is forgotten, so
   a later encounter between the same two aircraft is announced as new.
2. **Low-confidence collapsing.** A tier 2 pair below `LOW_CONFIDENCE_RAW_PROBABILITY
   = 0.25` raw is grouped into a counted row instead of taking its own. Guarded four
   ways, each a release valve rather than a filter: never tier 1, never a pair the
   deterministic rule calls a conflict (Section 13's safety net outranks the
   classifier), never severity high or critical, never a pair carrying resolutions.

**THE GUARANTEE IS STRUCTURAL, NOT TESTED-FOR.** Every pair `escalate_pair` confirms is
in `active` on every update; the module contains no code path that removes one.
Suppression can only change `is_new_notification` and `display`. The frontend contract
is stated in the module docstring: **render `active` in full**, use `attention` for
prominence and `notifications` for sound, and never render `notifications` alone —
that would turn a display rule into a detection rule.

**Measured, on the held-out test split (lever B alone, one feed per row):**

| | rows | real | false |
|---|---|---|---|
| alerts raised | 740 | 286 | 454 |
| given a prominent row | 555 | 279 | 276 |
| collapsed into the counted group | 185 | **7** | 178 |
| **removed from the active list** | **0** | **0** | **0** |

**39.2% of false alarms leave the prominent list; prominent-list precision goes 0.386
-> 0.503.** The 7 real conflicts that collapse are **all tier 2, all still on the active
list, with 6 to 9 minutes of real warning left** (360-540 s). The tier 2 guard releases
each one into a full alarm as it closes inside three minutes, which is verified rather
than asserted — see the "collapsed pair that closes to tier 1" check.

**Measured, on real traffic replay (lever A alone, rule path, no classifier so nothing
collapses):**

| session | pairs reported before | pairs on active after | lost | interruptions before | after | cut |
|---|---|---|---|---|---|---|
| `session_20260905_003006` | 20 | 20 | **0** | 241 | 89 | 63.1% |
| `session_c_20260903_204503` | 10 | 10 | **0** | 119 | 42 | 64.7% |

Total active rows rendered equals the old message count exactly (241 and 119), which is
the direct proof that no confirmed pair-update left the display.

**The cut is 63-65%, not the 90% the raw episode count suggests, and that gap is
deliberate.** Categorising the 131 remaining interruptions: 65 crossed a
time-to-CPA boundary, 30 were genuinely new conflicts, 23 closed by more than 1 NM, 12
escalated tier 2 to tier 1, 1 rose in severity, and **0 were the heartbeat** — the
heartbeat is a pure backstop that never had to fire. Every remaining interruption is a
real change of state. The ~25 points between 65% and 90% is what the safety re-fires
cost, and they are worth it.

**Not wired to anything yet.** `assess_pair` is unchanged and no caller constructs an
`AlertFeed`; the API layer that would own one does not exist. This is deliberate —
Section 11's build order puts the FastAPI layer next, and it can adopt the feed in one
line when it arrives.

**Verification:** `verify_pipeline.py` gained a section 10 with 23 checks and now runs
**110 of 110**. Among them: a confirmed pair is on the active list on every update; each
of six escalations overrides suppression; each of four guards refuses to collapse; a
collapsed pair released into tier 1 announces again; `attention` is a prefix of `active`
rather than a filter; the feed never promotes a pair `escalate_pair` has not confirmed;
and the whole thing once through the real `ConflictEngine` rather than hand-built dicts.
The teammate's 8 unit tests and `inference_check.py` both still pass.

**No model, threshold, hyperparameter or gate was touched. The headline number is
unmoved at 94.0%** — this layer runs after detection and cannot change what is detected.

### 2026-09-07 — The level-flight filter: tested, failed, do not retry

**The idea.** 64.8% of the classifier's false alarms are pairs that came close
laterally but stayed stacked vertically — median real closest approach **2.44 NM /
1,930 ft**, against 1.69 NM / 535 ft for true conflicts. So: suppress a pair when both
aircraft read level and the predicted vertical gap already clears 1,000 ft. Two aircraft
in level flight at different flight levels cannot lose vertical separation.

**Measured on the held-out test split: it cuts 46% of false alarms and costs 21 real
conflicts. Recall 0.9439 -> 0.875, headline 94.0% -> 86.6%.** Rejected.

**Why it fails, which is the useful part.** Those 21 pairs reported 0.00-0.33 m/s
vertical rate at the moment of the decision and then one aircraft descended. Several
were predicted 2,200-2,450 ft apart and ended 240-530 ft apart. "Level now" does not
mean "level in ten minutes" — the descent comes from a controller instruction we never
receive, which is the same information ceiling recorded in Part 5.

**This is a named, standard technique and it depends on data we do not have.**
EUROCONTROL's STCA guidelines list it as Option E, *"Cleared and/or Selected Flight
Level used for Vertical Prediction in Linear Prediction Filter — Reduces nuisance
alerts, particularly for level off situations. Can give extra warning time, but reduces
warning time in the event of level bust."* Real STCA runs this filter because the flight
data processing system supplies the cleared level; our proxy is observed vertical rate,
and the level-bust case is exactly what a proxy gets wrong. Their term for what we call
a false alarm is also worth adopting: *"nuisance alert: alert which is correctly
generated according to the rule set but is considered operationally inappropriate."*
Source: <https://www.eurocontrol.int/sites/default/files/2019-09/eurocontrol-guidelines-159-part-iii-1.0.pdf>
(read directly, not summarised from search).

**Use this in the evaluation report.** "We restricted ourselves to display-layer
suppression because the standard vertical filter needs cleared-flight-level data that
ADS-B does not carry, and we measured what it costs without it" is a defensible finding,
and the 21 lost conflicts are the evidence.

### 2026-09-08 — The backend exists, and the dashboard is connected to it

**What was actually wrong.** The two halves were never connected on this branch, and the
reason was not that a connection had never been built. Commit `1077117` (27 Apr 2026)
built a working Express backend and a client API layer; commit `9b6800b` (30 Aug 2026),
"retire legacy Express/React implementation from branch tip", deleted all of it -- server
routes, providers, `client/src/lib/api.js`, `client/src/hooks/useAircraftFeed.js` -- as
the first half of the documented migration to FastAPI (Section 3). The second half was
never written. `origin/main` never had the connected version at all; its `server.js` is a
ten-line hello-world.

**What was built.** `server/app/` as FastAPI, implementing the Section 5 endpoint list plus
the model endpoints that did not exist in April:

| file | what it does |
|---|---|
| `main.py` | app, CORS, the ten-second ingest loop, `/ws/stream` |
| `config.py` | every threshold and mode, overridable from the environment |
| `services/normalizer.py` | direct port of the deleted `aircraftNormalizer.js`, field-for-field, so the React components did not have to be rewritten |
| `services/opensky_client.py` | OAuth2 client credentials (the deleted Node provider used Basic auth, which OpenSky retired), with the 200-credit reserve the collection scripts use |
| `services/replay_service.py` | recorded sessions as a live feed |
| `services/aircraft_service.py` | snapshot, per-aircraft rolling history, live/replay/auto with fallback |
| `services/conflict_service.py` | pair pre-filter, the full chain per pair, the alert feed |
| `services/audit_service.py` | append-only audit log |
| `api/routes.py` | 13 endpoints |

**Measured, running against a recorded session:** 33-38 aircraft per update, 20-28 passing
the en-route floor, 15-30 pairs assessed per update in **1.8-2.5 s** against a ten-second
budget, and genuine tier 1 alarms with three Model 3 options each -- for example
`JZR533 x UAE325`, closest approach 4.23 NM / 1,100 ft in 30 s, offering a descent, a
speed reduction and a turn, each with its own confidence and score.

**Five defects found and fixed while wiring it up. All five were invisible until real data
flowed through.**

1. **Replay frames were built on the wrong timestamp.** Bucketing on `time_position` -- when
   each aircraft last reported *itself* -- scattered one snapshot across many frames,
   giving frames holding anywhere from 1 to 166 aircraft. The poll timestamp
   (`fetch_timestamp_utc`) is the real snapshot boundary: 536 frames of a steady 35.
2. **Alarms were raised about aircraft that had left the airspace.** `histories_for_models()`
   returned every aircraft with ten past states, including ones no longer in the current
   update, so a pair could be assessed on positions minutes stale. Verified live: an alarm
   named `AIC112 x UAE323` when neither was in the snapshot. Now both aircraft must be in
   the current update as well as have a history.
3. **The history warm-up wrapped past the start of the session**, splicing the tail of the
   recording -- ninety minutes and a different set of aircraft away -- onto the front as an
   aircraft's "recent past".
4. **The replay clock started before the models finished loading**, so the encounter it had
   seeked to was already two minutes gone by the time the server answered anything.
5. **The map dropped all real traffic.** `FlightRadarMap` merged incoming flights into a
   fixed list *by callsign* and silently discarded everything that did not match, which is
   every real aircraft.

**The en-route floor now applies at inference, not only when building training data.** This
was recorded as an open gap on 7 Sep: `assess_pair` had no altitude filter, so the API layer
could have fed approach traffic to a rule calibrated for cruise -- the failure that flagged
something in 91-94% of all snapshots on 30 Aug. `CONFLICT_MIN_ALTITUDE_FT = 10,000`.

**Two deviations from the plan, stated rather than buried.**

- **SQLite, not PostgreSQL** (Section 3 specifies Postgres). Same schema, ordinary SQL,
  a connection-string change to migrate; but it needs no database server installed, which
  means the audit trail runs today instead of after a setup. Only INSERT and SELECT appear
  in the module, so append-only is enforced by construction.
- **One WebSocket, not two.** Section 5 lists `/ws/aircraft` and `/ws/alerts` separately.
  They are served together because an alert about two aircraft is meaningless if it
  arrives before the positions it refers to.

**Replay now starts near a real encounter.** A recorded session is ninety minutes of mostly
uneventful traffic. `FLIGHT_RIGHT_REPLAY_SEEK=conflict` (the default) scans for the first
frame where two en-route aircraft are predicted inside the alert volume and starts three
minutes before it. A scan of six sessions found **4,049 such frames**, so this is choosing
where to begin in real data, not manufacturing anything.

**Headline number unmoved at 94.0%.** No model, threshold, gate or hyperparameter was
touched. `verify_pipeline.py` 110/110 and the 8 unit tests pass against the same artifacts.

### 2026-09-08 - PostgreSQL, and the append-only audit log becomes enforced rather than promised

**The decision and the reason to give for it.** Archit asked to move from SQLite to
PostgreSQL. The reason offered was that Postgres is currently fashionable; that is the
weakest available argument and would not survive an examiner asking a second question.
The defensible one, and the one now implemented:

> The audit log has to be append-only (Section 12). Under SQLite that was a *convention*
> - "this module contains only INSERT and SELECT" - which anyone editing it could break
> silently. Under PostgreSQL the application role is granted `INSERT, SELECT` on
> `audit_logs` and nothing else, so the **database** refuses an UPDATE or DELETE
> regardless of what the code asks for.

Two supporting reasons: real `timestamptz` and `JSONB` instead of ISO strings and TEXT,
so the detail blob is queryable and indexable; and Section 3 already specified
PostgreSQL, so this removes a documented deviation rather than adding one.

**`scripts/postgres.py`** manages a project-owned PostgreSQL 17.2 - the official
EnterpriseDB binaries-only archive, no installer, no administrator rights, nothing on
PATH. Subcommands: `install`, `init`, `start`, `stop`, `status`, `verify`, `psql`,
`reset`. `init` creates the cluster, the two roles, the schema and the grants, and writes
`DATABASE_URL` into `.env`.

**It cannot go in the venv, and it must not go in the project folder.** A venv holds
Python packages; only the driver (`psycopg`) belongs there. And the project sits inside
OneDrive: a database data directory in a cloud-synced folder is slow and
corruption-prone. **Measured: `initdb` into the project directory had not finished after
400 s; into LOCALAPPDATA it took 7 s.** Everything therefore lives under
`LOCALAPPDATA/FlightRight/postgres`.

**Roles.** `flightright_owner` owns the schema and may change it (migrations).
`flightright_app` is what the backend connects as: INSERT and SELECT on `audit_logs`,
full access to `conflicts` and `resolution_options` (working state, upserted every tick).
`scripts/postgres.py verify` runs 8 checks and proves the guarantee rather than asserting
it - it attempts an UPDATE and a DELETE and both come back `permission denied for table
audit_logs`.

**`server/app/services/database.py`** replaces `audit_service.py`. One API, two possible
backends: PostgreSQL when `DATABASE_URL` is set and reachable, SQLite otherwise. Which
one is live is reported by `/api/health` under `store`, including
`appendOnlyEnforced: false` when it has fallen back, so the weaker guarantee is never
silently in force. The fallback follows the project's existing pattern - constant
velocity under the LSTM, the CPA rule under the classifier, replay under live.

**Section 6 schema now actually exists.** `conflicts` and `resolution_options` are
persisted each ingest tick and served by the new `GET /api/conflicts/history`, so what
the system raised survives a restart. Aircraft states deliberately stay in memory: at
35 aircraft every ten seconds that is ~300,000 rows a day, and they are re-derivable
from the feed.

**Security, since this module is the only one taking arbitrary client input.** Every
statement is parameterised, including the free-text audit search. `level` is checked
against a fixed set. The `detail` blob is capped at 16 KB and text fields at 2,000
characters. The connection string carries a password and is never returned by an endpoint
or written to a log line - the fallback path logs the exception type and message only.
The cluster listens on 127.0.0.1 and nothing else. There is still no authentication:
Section 3 puts that out of MVP scope, and the recorded user is a server-side default
rather than whatever the client claims.

**THREE WINDOWS TRAPS, ALL OF WHICH COST REAL TIME. Recorded so nobody re-diagnoses them.**

1. **Never capture a Postgres tool's output through a pipe.** `initdb` and `pg_ctl` spawn
   children that inherit the parent's stdout and stderr handles. With
   `subprocess.run(capture_output=True)`, Python waits for those handles to reach
   end-of-file, and a lingering `postgres.exe` grandchild holds them open indefinitely -
   so the call blocks *after the tool itself has already exited*. Six orphaned postgres
   processes were found doing exactly this. Output now goes to a temporary file, and
   every call carries a timeout.
2. **Close stdin.** Otherwise `psql` prompts for a password and waits forever behind
   captured output, which is indistinguishable from a hang. `psql` is also invoked with
   `-w`, so it errors instead of prompting.
3. **"pre-existing shared memory block is still in use"** means an orphaned `postgres.exe`
   is still holding the segment. Kill it before `initdb`.

**One WebSocket, and this is now a decision rather than a deviation.** Section 5 listed
`/ws/aircraft` and `/ws/alerts` separately; Archit chose a single multiplexed
`/ws/stream` on 8 Sep. The reason is consistency: an alert states a separation and a
time, which is only meaningful against the positions it was computed from. Two sockets
give no ordering guarantee between them, so an alert can arrive before the position
update it refers to and the map draws the conflict against stale positions. The ingest
loop computes both in the same tick; they are sent in the same message. The envelope is
typed so a client can still route them separately.

**A measurement worth keeping.** During testing the assessment appeared to slow from
1.5 s to 22 s per tick. It had not: a backend left running from the previous session
eight hours earlier was still holding port 8000, and every request was being answered by
that stale process with its accumulated state. A fresh process measured 1.0-1.6 s for
10-15 pairs. **Check for a stale server before investigating a performance regression.**

**Verified end to end on the recorded session:** PostgreSQL selected, 33-40 aircraft,
two genuine tier 1 alarms (`JZR533 x UAE325` and `UAE325 x ABY821`, both 1,100 ft
vertical), 3 Model 3 options each, **6 resolution-option rows and both conflict rows
persisted**, audit round-trip through the API confirmed, and the frontend streaming with
zero console errors and zero mock leakage.

**Headline number unmoved at 94.0%.** No model, threshold, gate or hyperparameter was
touched. `verify_pipeline.py` 110/110 and the 8 unit tests pass.

### 2026-09-08 - The multi-path model is asked once per airspace, not once per pair

**A real defect, found by watching the clock rather than by a failing test.** With the
backend running against the recorded session, the assessment time per update climbed to
**46-53 seconds for 27-33 pairs** - about **1,600 ms per pair** - against a ten-second
surveillance budget. Nothing failed and no check caught it; the ingest loop simply fell
further behind on every tick.

**Diagnosed with cProfile, not by inspection.** 97% of the time was one line:

```
36000 calls   7.9 s   sklearn/.../_hist_gradient_boosting/predictor.py:49(predict)
```

12,000 individual tree evaluations *per pair*. `HistGradientBoostingClassifier` walks
every tree of every class on each call - 40 patterns x 300 trees - and that cost is paid
**per call, almost regardless of how many rows are in it**. `assess_pair` was calling it
once per pair with two rows, so a 30-pair update paid the full 12,000-tree cost thirty
times over to score sixty rows.

**The fix.** `ConflictEngine.multipath_candidates(histories)` predicts for every eligible
aircraft in **one** call; `conflict_service` does that once per tick and hands the
per-aircraft results to `assess_pair` through new optional `candidates_a` / `candidates_b`
arguments. When they are absent - `verify_pipeline.py` and `inference_check.py` call
`assess_pair` directly - the original per-pair path still runs unchanged, so nothing that
depended on the old signature broke.

**This changes when the arithmetic happens, not what it produces.** The model is
deterministic and each row is independent of the others, so the batched and per-pair
paths return identical candidates.

| | before | after |
|---|---|---|
| per pair | 1,600-3,000 ms | **21-34 ms** |
| per update (15 pairs) | ~24 s | **~350 ms** |
| per update with two tier 1 alarms (26 pairs) | 46 s | **1.7 s** |

Roughly **130x**, and stable rather than degrading. The 1.7 s figure includes Model 3
flying 26 candidate manoeuvres for each of two alarms, which is the expected cost.

**Verified unchanged afterwards:** the same two alarms (`JZR533 x UAE325`,
`UAE325 x ABY821`), same tiers, same severities, 3 Model 3 options each, multi-path
probability still computed, rows still persisted. `verify_pipeline.py` 110/110, 8 unit
tests, `inference_check.py` all pass.

**The lesson worth keeping.** A model that is cheap on a batch can be ruinous one row at
a time, and nothing in the test suite notices - every check still passed while the system
was thirty times over its time budget. Timing is a correctness property here, because an
update that takes 46 seconds is an update the controller does not get.

**Headline number unmoved at 94.0%.** No model, threshold or gate was touched.

### 2026-09-23 — Model 1b per-mode offsets: built, gated, saved, not serving

`multipath.py` now fits 12 `HistGradientBoostingRegressor(loss="absolute_error")` models
(4 horizons x 3 axes) on the 83 features plus the pattern id as a categorical feature,
settings copied unchanged from `reference_benchmark.py`. Trained on TRUE pattern ids,
scored only on the classifier's PREDICTED patterns. KMeans, classifier and temperature
are unchanged and reproduce bit-for-bit: the re-score's table path matches the shipped
pickle on all 669 prior values.

| test, ten minutes, within 5 NM | table (serving) | per-mode | 
|---|---|---|
| arrivals best-of-5 | 63.6% | **71.5%** |
| arrivals top-1 | 38.6% | **44.2%** |
| all best-of-5 | 83.0% | **86.6%** |
| all top-1 | 64.0% | **66.7%** |
| all top-1 within 1 NM | 31.5% | **38.4%** (CV 29.0%, tree 33.1%) |
| ceiling, true pattern — NOT a result | 74.7% | 81.0% |

Top-1 beats constant velocity on mean error at every horizon (0.45 / 1.47 / 2.70 / 5.67 NM
vs 0.49 / 1.69 / 3.65 / 10.30). Candidate diversity preserved: median spread of the five
candidates' ten-minute errors on arrivals 22.7 NM vs 23.4 NM. At ten minutes the per-mode
top-1 (66.7%) also edges the single-answer tree reference (65.7%) — one seed; do not claim
until Phase 3.3's three seeds.

**Pickle format 2** adds `format_version` and `offset_models` and keeps `pattern_residuals`,
so every existing reader works unchanged (117.7 MB, was 82.9 MB). The backend selects with
`FLIGHT_RIGHT_MULTIPATH_OFFSETS` (`table` default | `per_mode`); asking for `per_mode` on a
format-1 pickle raises rather than silently serving the table, and the choice is appended
to the model version string. Cost: 325 ms per batched call of 40 aircraft vs ~100 ms.
**Default stays `table`** because these paths feed the tier 2 conflict probability — switching
changes when a controller is alerted (Part 6).

**Full-tick latency, measured on replay the same day** (`ml_pipeline/utils/replay_timing.py`,
the real `AircraftService` + `ConflictService.assess`, every frame of two whole sessions,
both modes on identical frames, first tick reported apart as a cold start):

| session | updates | mode | median | p95 | worst | over 10 s |
|---|---|---|---|---|---|---|
| `session_20260905_003006` | 523 | table | 0.26 s | 0.73 s | 1.11 s | 0 |
| | | per_mode | 0.58 s | 1.23 s | 1.78 s | 0 |
| `session_c_20260903_204503` | 528 | table | 0.33 s | 1.11 s | 1.80 s | 0 |
| | | per_mode | 0.56 s | 1.38 s | 2.07 s | 0 |

Up to 52 aircraft and 70 assessed pairs per update. One batched multi-path call per tick in
both modes (per_mode 0.34-0.40 s median vs ~0.10 s). Cold first tick 2.3-3.0 s vs 1.6-2.1 s.
**Latency does not block switching.**

What switching changes, on these replays (no ground truth here, so direction only):
tier 2 pair-updates 55 -> 91 and 82 -> 101; the tier 2 pair sets differ (3 and 4 pairs only
under table, 8 and 5 only under per_mode). Tier 1 identical in session c; in session 1 one
extra pair (`IGO2051 x AKJ618`) reached tier 1 for two updates after first qualifying on
the tier 2 watch list — tier 1 geometry is unchanged, but the path into it runs through the
escalation history, so tier 2 inputs can affect it. Whether these changes are better or
worse is what Phase 3.2's labelled measurement answers; replay cannot.

### 2026-09-23 — The selected altitude is available after all — from adsb.lol, not OpenSky

**What was checked.** The Phase 2 finding that selected altitude is "permanently out of
scope" was tested against a second source. All five checks reproduced in substance
(details and dates in `docs/phase2_findings.md`, correction under 2.2):

1. `api.adsb.lol/v2/point/19.0887/72.8679/60`: 9 of 13 aircraft within 60 NM of VABB carry
   `nav_altitude_mcp` (9 of 11 airborne; misses are one ADS-B v0 transponder and one v2
   aircraft at 4,000 ft). Archit, earlier the same day: 12 of 12.
2. `trace_full_801742.json` and `trace_full_80180e.json`: trace element 8 is a non-null
   object on 834 of 3,339 and 816 of 3,266 points; 781 and 792 carry `nav_altitude_mcp`, and
   it steps through each flight. Archit's quoted IGO5323 sequence did not reproduce value for
   value because the file is a rolling ~25-hour window; the same flight number shows a
   different leg on a later fetch.
3. The same object carries `wd`, `ws`, `oat`, `tat`, `ias`, `tas`, `mach`, `roll`,
   `track_rate`, `nav_qnh`.
4. readsb `README-json.md` defines the field as MCP/FCU selected altitude and trace element 8
   as "aircraft object with extra details or null".
5. adsb.lol publishes daily per-aircraft JSON GZIP dumps as GitHub releases
   (`adsblol/globe_history`), ODbL 1.0. The ~2,115 GiB archive size is Archit's figure and
   was not re-measured.

**What was found.** The OpenSky finding stands — `supportstargetstatereport` is a
capability flag — and so does its explanation of the failed 7 Sep level-flight filter. The
general conclusion does not: the value is broadcast, decoded and kept by adsb.lol.
Selected altitude is what the crew dialled, normally but not always the cleared level
(EUROCONTROL STCA Option E names both), so it narrows the level-bust gap rather than
closing it.

**What changed in the plan** (`Claude outputs/Flight_Right_Plan_v8_temp.md`): 2.2 rewritten;
Phase 2 is now six questions with 2.6 (how far back direct trace fetches reach); new 9.0
(collect selected altitude and wind from adsb.lol, measure a week's coverage first, ablation
row, ODbL conditions); 9.6 wind sourced from the aircraft's own reports with Open-Meteo as
fallback; the "Permanently out" row narrowed to OpenSky specifically; one "can claim" bullet
and two "when something goes wrong" rows added. Documentation only: no model, threshold,
gate, published number or collection script changed.

### 2026-09-24 — Per-mode offsets measured on labelled pairs; the runtime figure was incomplete; Phase 2.6 answered

**`ml_pipeline/utils/offsets_ab_test.py` (new).** It re-runs the seeded encounter generator
with its RNG untouched, captures every placement (A/B anchor indices, rotation, relocation,
altitude offset), and **verifies the rebuild is identical to
`encounters_real_outcome_20260906_083724.parquet` on all 40,000 rows x 32 columns** before
scoring anything. Each test pair's 10-state windows are recovered, with B's window given the
same `transform_track` as its future. Both go through `MultiPathPredictor` in each offsets
mode, and then through the backend's exact decision: rule geometry if `assign_tier(rule) == 1`,
else `compute_cpa_from_paths`, plus the classifier verdict, then `escalate_pair(row, [row, row])`.
Report: `ml_pipeline/reports/offsets_ab_20260924_174836.json`.

| test split, 4,690 pairs, 303 real | alerts | recall | precision | FA/1000 | headline | t1 real/false | t2 real/false |
|---|---|---|---|---|---|---|---|
| no multi-path step (= `escalation_runtime.classifier_gated`) | 762 | 0.9505 | 0.3780 | 101.1 | 94.72% (269) | 27 / 14 | 261 / 460 |
| **table (serving)** | 817 | 0.9472 | 0.3513 | 113.0 | **94.37% (268)** | 28 / 18 | 259 / 512 |
| per_mode (Phase 3.1) | 809 | 0.9505 | 0.3560 | 111.1 | 94.72% (269) | 28 / 17 | 260 / 504 |

The first row reproduces the published runtime numbers exactly, which is the sanity check
on the rebuild. 2,757 of 4,690 pairs are tiered on multi-path geometry. table and per_mode
disagree on 124 alerts: 1 real + 65 false only under table, 2 real + 56 false only under
per_mode.

**Finding 1: `escalation_runtime` understates what the running system raises.** It
never ran the multi-path step. With it, the served system is **94.37%, not 94.72%**, and
FA/1000 is 113.0, not 101.1. The Part 1 table is corrected. `reevaluate_models.py` should
gain this step; not yet done, because it needs the windows this script rebuilds.

**Finding 2: the multi-path step adds alarms through the safety net.** Alerts raised by the
`separation-minimum` route: 403 with no multi-path step, 464 with the table, 463 with
per_mode. `compute_cpa_from_paths` reports the worst *breaching* combination as its
geometry, so any one of 25 combinations inside 5 NM / 1,000 ft forces an alarm whatever its
probability. The safety net is meant to be the deterministic straight-line rule (Section 13),
and here it is fed a low-probability model path. This is Phase 3.2's target. Changing it
changes when a controller is alerted, so it needs Archit.

**Finding 3: per_mode is better than table on every row, by a small margin:** +1 conflict
at 3 min, −1.9 FA/1000, −1 tier 1 false. One seed. Mean multi-path probability on real
conflicts 0.834 -> 0.861 and on non-conflicts 0.065 -> 0.061, so it separates slightly better.
**Not switched on; the decision is Archit's.**

**Phase 2.6** (`scripts/check_adsblol_history.py`, `adsblol_history_20260924_232209.json`):
`adsb.lol/globe_history/YYYY/MM/DD/traces/xx/trace_full_<hex>.json` served every day from
13 Aug 2026 for both VT-IWQ and VT-NHB (42 of the last 60), none Feb-Jul 2026, 403 for
Dec 2025, partial Dec 2024-Sep 2025. Detail in `docs/phase2_findings.md`.

**Phase 1 exit gate re-checked the same day:** `verify_pipeline.py` 110/110, 8 unit tests,
`inference_check.py`, `vite build` all pass.

### 2026-09-24 — Plan 3.2: the safety net judges the straight line again; per-mode offsets switched on

**Signed off in-session on 24 Sep** ("go on with 3.2 … turn both of them on if beneficial").
The adoption rule was written into `offsets_ab_test.beneficial()` **before** the variant
numbers were seen. Relative to the served configuration (table, net on the model's
representative path), a candidate must not lose any 3-minute catch, any recall or any real
tier 1 alarm, and must keep the deterministic safety net (Section 13). Among passing
candidates, fewest false alarms wins, with fewer false tier 1 alarms breaking ties.

**What the gate does with a classifier attached.** `alert_gate` fires iff the safety net
fires or the classifier alerts, and tier is never 0 because CPA time is at most 600 s. So
multi-path changes who is alerted **only through the safety net**; otherwise it only moves
pairs between tier 1 and tier 2. Before this change, `inference.assess_pair` replaced the
rule CPA with the multi-path representative (the worst alert-volume-breaching combination)
for every pair outside rule tier 1, and `breaches_separation_minimum` was applied to that.
Two consequences: any of the 25 combinations, whatever its probability, could force an
alarm; and a pair whose **rule** geometry breached 5 NM / 1,000 ft went unchecked by the
rule. That is the one real conflict the table configuration lost.

**Measured, 21 configurations** (`offsets_ab_20260924_181140.json`; test split 4,690 pairs,
303 real, 284 with ≥3 min):

| configuration | alerts | recall | 3-min | FA/1000 | t1 r/f | passes |
|---|---|---|---|---|---|---|
| none (no multi-path step) | 762 | 0.9505 | 269 | 101.1 | 27/14 | no (t1 real) |
| table, net on model path (**served until 24 Sep**) | 817 | 0.9472 | 268 | 113.0 | 28/18 | baseline |
| table, net on straight line | 762 | 0.9505 | 269 | 101.1 | 28/18 | yes |
| **per_mode, net on straight line (SHIPPED)** | **762** | **0.9505** | **269** | **101.1** | **28/17** | **yes, chosen** |
| per_mode, net on line OR any model path | 850 | 0.9571 | 271 | 119.4 | 28/17 | yes |
| per_mode, line OR model, fan pruned to 90% mass | 799 | 0.9538 | 270 | 108.7 | 28/20 | yes |
| per_mode, line OR model, paths ≥ 0.10 | 785 | 0.9538 | 270 | 105.8 | 28/21 | yes |
| per_mode, net on model path, 90% mass | 775 | 0.9472 | 268 | 104.1 | 28/20 | fails Section 13 |

The model paths added to the net contribute **0 real / 111 false** alerts with table and
**2 real / 86 false** with per_mode. Pruning (mass90, floor10, joint05) removes most of the
extra false alarms but not all of them, so the straight-line-only net has the fewest. The
higher-recall per_mode rows are recorded, not adopted: +1-2 conflicts for +4.7-18.3 FA/1000.
That trade is a legitimate choice for Archit to revisit; it is not what the pre-set rule
selects.

**Code.** `cpa_conflict_detection.RULE_GEOMETRY_KEY`: when the tiering geometry came from a
model, the rule CPA (lateral, vertical, time) rides along and `alert_gate` judges the net on
it. The notify reason quotes those straight-line numbers when the net fired. `inference.py`
attaches the key outside rule tier 1. The tier and the displayed geometry stay multi-path.
`FLIGHT_RIGHT_MULTIPATH_OFFSETS` unset now means `per_mode`, falling back to `table` on a
pickle without `offset_models`. Explicitly requesting `per_mode` on such a pickle still
raises. `offsets_ab_test.py` proves the shipped `escalate_pair` path equals the measured
variant on all 4,690 pairs in both modes. Three unit tests were added (`SafetyNetGeometryTests`);
the unit suite is now 11.

**Not changed:** the classifier, its threshold, the tier thresholds, the 8 NM / 1,500 ft
alert volume, the 5 NM / 1,000 ft minimum, and Model 3. **Still owed:** plan 3.3's three
seeds for per_mode, and the multi-path step inside `reevaluate_models.py`.

**Verification:** `verify_pipeline.py` 110/110, 11 unit tests, `inference_check.py`
(version `+per_mode`). `reevaluate_models.py` gives 698/698 values identical to 23 Sep
except `measured_at_utc`; the duplicate report was deleted. **Latency, replay of
`session_20260905_003006_combined`, machine measurably slow all day:** table median 0.89 s,
worst 2.99 s (23 Sep: 0.26 / 1.11). per_mode run 1 median 0.73 s, worst **17.43 s** at tick 55,
the only tick over 10 s, 15.4 s of it outside the multi-path call. per_mode run 2 median
2.14 s, worst 4.02 s, tick 55 = 1.54 s. The stall did not reproduce; treat it as a transient.
Re-time on a quiet machine. Tier 1 / tier 2 pair-updates were 116 / 34 in both modes on this
session.

### 2026-09-24 — Plan 3.2, second half: tier and prominence rules from the literature, measured, neither adopted

**Asked for:** research what 3.2 should be, and ship it only if it reduces false alarms shown
to the controller *without compromising a single real conflict*.

**Sources read.**
- Kuchar & Yang, *A Review of Conflict Detection and Resolution Modeling Methods*, IEEE
  T-ITS 1(4), 2000 ([PDF](http://www.mit.edu/~jkkuchar/ATC-102.pdf)). Worst-case propagation
  "can trigger conflict alerts whenever there is any possibility of a conflict … If such
  conflict-inducing maneuvers are unlikely … a high false alarm rate". The probabilistic
  approach lets "decisions … be made on the fundamental likelihood of a conflict".
- Paielli & Erzberger, *Conflict Probability Estimation for Free Flight*, NASA 1997
  ([NTRS](https://ntrs.nasa.gov/citations/19970001686)), and Prandini, Hu, Lygeros & Sastry
  2000 ([PDF](https://people.eecs.berkeley.edu/~sastry/pubs/OldSastryALL/PrandiniHuProbabilistic2000.pdf)).
  Both alert on estimated conflict probability.
- EUROCONTROL STCA Guidelines Part I
  ([PDF](https://www.eurocontrol.int/sites/default/files/2019-09/eurocontrol-guidelines-159-part-i-1.0.pdf)):
  STCA-10 (nuisance alerts "kept to an effective minimum"), STCA-12 (warning time), STCA-15
  (inhibitions "made known to all controllers"), and "multi-level or different types of
  alerts" as the direction of travel.

**Two rules derived from them,** chosen on the validation split (6,564 pairs, 450 real) and
confirmed once on test (4,690, 303). Tables built by `ml_pipeline/utils/alert_prominence.py`
with `per_mode` and the served rule-geometry net; `test` reproduces the served 762 alerts.
Report: `ml_pipeline/reports/alert_prominence_20260924_193159.json`.

| | val | test |
|---|---|---|
| **A** (tier 1 promotion only from a *breaching* combination): real tier 1 alarms, served → A | 31 → 31 | **28 → 27** |
| A: false tier 1 alarms | 26 → 24 | 17 → 14 |
| **B1** (collapse only if classifier raw < 0.25 AND multi-path P(alert volume) < 0.10): real rows collapsed, served → B1 | 10 → 3 | 7 → 3 |
| B1: false rows left prominent | 435 → 516 | 297 → 347 |
| B1: real conflicts prominent with ≥ 3 min | 396 → 403 | 262 → 266 |

**A is rejected.** The test split has one real conflict (row 1332: severity high, ≥3 min of
real warning, classifier alert) that reached tier 1 only through a non-breaching likeliest
combination closing inside 180 s. A demotes it to tier 2: still alerted and prominent, but
no audible alarm and no manoeuvres. Validation showed no such case. A was **not** re-tuned
after seeing test.

**B1 is not adopted, and is recorded as a safety option for Archit.** On validation no
likelihood rule of this form collapses more false rows without newly collapsing a real one:
real rows at classifier raw 0.2501, 0.2727 and 0.4097 have multi-path P(conflict) ≤ 0.04.
B1 is the safety direction instead. It collapses fewer real conflicts (4 more real
conflicts prominent with ≥3 min on test) at the cost of 50 more prominent false rows. That
fails the stated "reduce false alarms" condition.

**Safety observation, not previously quantified on the served configuration.** The served
collapse rule (`alert_feed.LOW_CONFIDENCE_RAW_PROBABILITY = 0.25`) puts **7 real conflicts on
test (10 on val) in the counted group**, all tier 2, all with ≥3 min of real warning. They
stay on `active` and are released at tier 1, so detection and the 94.7% are unaffected.
But the controller does not see them prominently until inside three minutes.

**Where the remaining false-alarm lever is.** Both rejected rules fail for the same reason
as the 7 Sep level-flight filter: without the aircraft's intent, the pairs that matter cannot
be separated. EUROCONTROL's own answer (STCA Option E) is the cleared or selected flight
level, which adsb.lol carries (plan 9.0, Phase 2.6). That is the next false-alarm reduction
with a source behind it.

**Nothing served changed in this entry.** No model, threshold, tier rule or display rule.

### 2026-09-25 — Plan 3.3: per-mode reproduces across four seeds; archive data adds ~4 points

**Code.** `multipath.py` gains `FLIGHT_RIGHT_MULTIPATH_SEED` (balanced sample, KMeans and
pattern classifier; default 42) beside the existing `FLIGHT_RIGHT_OFFSET_SEED`. It also gains
`FLIGHT_RIGHT_MULTIPATH_OUT`, which redirects the pickle and writes `<name>.summary.json`
with every gate number. Unset, behaviour is unchanged: the seed-42 run reproduced the served
pickle (temperature 1.729, KMeans centres within 2.1e-14 NM, every printed metric identical).
New `ml_pipeline/utils/archive_row.py` builds the "+ more data" row.

**Seeds** (`ml_pipeline/reports/multipath_seeds_20260925_012526.json`). Whole model varied,
identical splits. Test arrivals at ten minutes, within 5 NM:

| | 42 (served) | 1 | 2 | 3 | mean ± sd |
|---|---|---|---|---|---|
| per-mode best-of-5 | 71.5 | 72.1 | 72.4 | 71.8 | 72.0 ± 0.4 |
| table best-of-5 | 63.6 | 63.6 | 61.7 | 64.8 | 63.4 ± 1.3 |
| per-mode top-1 | 44.2 | 42.6 | 43.4 | 44.4 | 43.7 ± 0.8 |
| table top-1 | 38.6 | 37.8 | 37.1 | 39.8 | 38.3 ± 1.2 |

Per-mode beats table on every seed (+7.0 to +10.7 best-of-5, +4.6 to +6.4 top-1). All four
gates pass on all seeds. Per-mode top-1 mean error at ten minutes is 5.65-5.73 NM against CV
10.30. Temperature is 1.724-1.733 across seeds. The served seed-42 model is kept. It is the
lowest best-of-5 of the four, and swapping in the best seed would be selection on test.

**Archive row** (`ml_pipeline/reports/multipath_archive_seeds_20260925_030354.json`). 36 archive days
fall before the validation start (2026-09-02 20:46 UTC); every third was taken, 12 days
(9 Feb 2025 .. 20 Jul 2026). The real `preprocess_sequences.py` was run in a throwaway root:
2,126,784 windows, 59.7% with a ten-minute target (existing train 50.5%). A seeded 400,000 of
them were added to the existing 205,757 training windows; val and test are the existing
files. Assertion: every archive timestamp precedes validation. Seed 42 / offset seed 0:

| test, ten minutes | served | + archive |
|---|---|---|
| arrivals per-mode best-of-5 | 71.5 | **75.4** |
| arrivals per-mode top-1 | 44.2 | **46.8** |
| arrivals per-mode best-of-10 | 77.7 | 81.5 |
| all per-mode best-of-5 | 86.6 | 88.1 |
| arrivals table best-of-5 / top-1 | 63.6 / 38.6 | 64.2 / 41.3 |
| per-mode top-1 mean NM, 1/3/5/10 min | 0.45/1.47/2.70/5.67 | 0.44/1.34/2.53/5.57 |
| temperature / ECE arrivals | 1.729 / 0.019 | **1.065** / 0.017 |

The +3.9-point best-of-5 gain is about ten times the seed standard deviation. The temperature
falling to 1.065 means the pattern classifier trained on more data is almost calibrated before
any correction.

**Not served.** One seed, and a 400k subsample of the 2.1M available. Its effect on tier
assignment and Model 3 on labelled pairs is unmeasured, and swapping the served model changes
what the controller sees. Pickle kept at `ml_pipeline/data/processed/seed_runs/multipath_archive.pkl`
(gitignored). Next: three seeds of the archive row, `alert_prominence.py` against it, and the
same row for the single-answer LSTM and the conflict classifier's encounter set.

**Checks after these edits:** `verify_pipeline.py` 110/110, 11 unit tests, `inference_check.py`.
Raw data still 35 files; `trajectory_*.npz` unmodified since 22 Sep; served pickle unmodified
since 23 Sep.

### 2026-09-25 — Archive row finished (four seeds, alert effect): not served; multi-path altitude scored for the first time

**Archive row, seeds 42/1/2/3** (`archive_row.py` now takes seeds and rebuilds the combined
split only if missing; seed 42 reproduced the first archive run byte-for-byte). Report:
`ml_pipeline/reports/multipath_archive_seeds_20260925_030354.json`.

| test arrivals, ten minutes | per-mode (4 seeds) | + archive (4 seeds) |
|---|---|---|
| best-of-5 within 5 NM | 72.0 ± 0.4 (71.5-72.4) | 75.6 ± 0.6 (74.9-76.1) |
| top-1 within 5 NM | 43.7 ± 0.8 (42.6-44.4) | 46.7 ± 0.4 (46.3-47.2) |
| table best-of-5 (same run) | 63.4 ± 1.3 | 63.8 ± 1.1 |
| all traffic best-of-5 | 86.9 ± 0.2 | 88.2 ± 0.1 |
| temperature | 1.724-1.733 | 1.058-1.069 |

All gates pass on all eight runs. The per-mode top-1 ten-minute mean error is 5.51-5.57 NM with
the archive, 5.65-5.73 NM without.

**Adoption rule, set before the comparison.** On BOTH val and test: identical alert set; no
fewer real tier 1 alarms; no more real conflicts collapsed; no fewer real conflicts prominent
with ≥3 min; no more false alarms shown (tier 1 false + prominent false). Scored with
`alert_prominence.py tag=pickle` on archive seed 42, the served seed, chosen before the numbers
(`alert_prominence_compare_20260924_213320.json`):

| | val served | val archive | test served | test archive |
|---|---|---|---|---|
| alerts / real alerted | 1139 / 428 | 1139 / 428 | 762 / 288 | 762 / 288 |
| tier 1 real / false | 31 / 26 | **30** / 27 | 28 / 17 | 28 / 17 |
| collapsed real / false | 10 / 276 | 10 / 275 | 7 / 177 | 7 / 177 |
| prominent false | 435 | 436 | 297 | 297 |
| real prominent with ≥3 min | 396 | 396 | 262 | 262 |

**Fails on val: one real tier 1 alarm lost (row 2688, the worst breaching combination moved from
165 s to 240 s). Not served.** All 8 tier changes (4 val, 4 test) sit at the 180 s boundary. In 6
of the 8, the deciding geometry is a combination with P(alert volume) = 0, which is the same
likeliest-non-breaching-path tiering flaw examined as change A on 24 Sep. Tier assignment
outside rule tier 1 is noise-sensitive at the boundary, so a better trajectory model does not
translate into better tiering. That is the thing to fix before any trajectory gain can reach the
controller, and it needs Archit, because A cost a real alarm on test. Pickle kept:
`ml_pipeline/data/processed/seed_runs/multipath_archive_seed42.pkl` (gitignored).

**Multi-path altitude, scored for the first time** (`ml_pipeline/utils/multipath_3d_eval.py`,
`ml_pipeline/reports/multipath_3d_20260925_030155.json`). Every multi-path gate since 5 Sep has
been horizontal only (`framing.error_nm`). Test, ten minutes:

| | CV | table | per-mode (served) | + archive (4 seeds) |
|---|---|---|---|---|
| top-1 altitude mean error, all | 2,231 ft | 2,224 ft | 1,116 ft | 1,047-1,066 ft |
| top-1 within 1,000 ft, all | 62.6% | **57.0%** | 71.1% | 71.1-71.7% |
| arrivals best-of-5 within 1,000 ft | 26.9% | 43.9% | 72.4% | 65.5-67.2% |
| arrivals best-of-5 within 5 NM AND 1,000 ft | 14.7% | 21.2% | **44.1%** | 46.4-46.9% |
| all best-of-5 within 5 NM AND 1,000 ft | 41.9% | 52.2% | 66.0% | 66.5-67.1% |

The table's altitude was worse than a straight line at ten minutes. Its KMeans patterns are 2-D
(along/cross), so each pattern's mean altitude residual averages climbs and descents. The
per-mode regressors include altitude and halve the error, an unmeasured benefit of the 24 Sep
switch. **The conflict-relevant 3-D best-of-5 for arrivals is 44.1%; the 71.5% is horizontal
only.** Quote the 3-D figure for conflict questions.

**Selected altitude is still not an input** to any model. Inputs are barometric altitude, the
altitude change across the window, vertical rate and vertical acceleration. The dialled target
level is not in OpenSky; plan 9.0 collects it from adsb.lol.

**Checks:** served pickle unmodified since 23 Sep; raw data still 35 files; splits unmodified
since 22 Sep. Archive seed 1-3 pickles deleted (summaries kept).

### 2026-09-25 — Plan Phase 7 (without audio), Phase 8, and 9.7 / 9.8

**Scope decision (Archit, 25 Sep):** speech-to-text (plan Phases 4-6, 9.3) is deferred. The
architecture has to make adding it a producer change, not a rewrite. Speech data on disk:
ATCO2 1h test set (871 clips, 109 MB) and the ATCO2+ATCOSIM training corpus (2.4 GB), both in
the HF cache. Not on disk: the official ATCO2 XML annotations (free, located in Phase 2), any
Whisper model, and any Mumbai recording (Phase 5 needs classmates; flagged).

**The seam: `ml_pipeline/utils/clearance.py`.** A `Clearance` (icao24, action
CLIMB/DESCEND/TURN/DIRECT/SPEED, value, confidence, source "oracle"|"manual"|"asr:<model>",
issued_at, valid_seconds, transcription_id) is the one object the voice chain must produce.
`problems()` rejects implausible values, and `apply_clearance()` is what the system does with one.

**7.1 oracle, UPPER BOUND with perfect recognition** (`oracle_clearance.py`,
`reports/oracle_clearance_20260925_031547.json`; served per_mode; 17,189 test windows with a
5- and 10-minute truth, 2,597 arrivals). Truth-derived level = 10-min altitude rounded to 1,000
ft when the change is ≥ 1,000 ft; heading = 5→10 min true track rounded to 5° when the turn
is ≥ 15°. Arrivals, ten minutes:

| variant | top-1 5NM | best5 5NM | top-1 3D | best5 3D | closest candidate lost |
|---|---|---|---|---|---|
| none | 42.8 | 70.4 | 31.0 | 43.4 | — |
| level ELIMINATES (plan 7.2 as written) | 41.2 | **64.8** | 31.0 | 42.0 | **9.2%** |
| heading eliminates | 45.1 | 70.3 | 31.6 | 43.3 | 1.7% |
| level CAPS (STCA Option E) | 42.8 | 70.4 | 34.9 | **53.9** | 0 |
| level cap + heading eliminates (SHIPPED) | **45.1** | 70.3 | **36.0** | **53.8** | 1.7% |

The truth itself was never rejected by its own clearance (0 of 6,876 level checks and 0 of
4,169 heading checks), so the tolerances are not the problem. Eliminating by level fails
because a candidate's horizontal and vertical parts come as one route shape. **Plan 7.2's
"eliminate" is kept for headings only; level clearances cap altitude**, sourced to
EUROCONTROL STCA Option E ("Cleared and/or Selected Flight Level used for Vertical
Prediction"). A measurement survey found no universal ICAO minimum climb/descent rate
(Australia's AIP "standard rate" ≥ 500 ft/min; SERA.8015 caps the rate near the level), so
`MIN_PROGRESS_FT` = 1,000 ft and `HEADING_TOLERANCE_DEG` = 45 are our own design, justified by
the truth-rejection check above.

**7.3 serving.** `ConflictEngine.multipath_candidates(histories, clearances=...)` applies each
aircraft's clearances in turn, and each report rides on the candidates (`clearance_a/_b` in the
assessment, `clearanceEffect` in the API). `assess_pair` no longer stacks the two fans, because
a heading can leave them different sizes. New `server/app/services/clearance_service.py` is the
single door (validate, exact callsign match against visible aircraft, confidence floor
`FLIGHT_RIGHT_CLEARANCE_MIN_CONFIDENCE`=0.9 as a PLACEHOLDER until Phase 6 measures the
extractor, expiry `FLIGHT_RIGHT_CLEARANCE_VALID_SECONDS`=600). Each submission, accepted or
not, gets a row in `extracted_clearances` and an audit row. API: `POST/GET/DELETE
/api/clearances`. `ASR_MODEL_ID` and `ASR_QUANTISATION` exist in `config.py` and are empty
until Phase 4. New tables `transcriptions` and `extracted_clearances` (plan 7.3 fields plus
model_id / quantisation / asr_version, NOT NULL) exist in SQLite and PostgreSQL, applied to the
live cluster with the new `scripts/postgres.py migrate`. The app role has INSERT and SELECT
only, and `postgres.py verify` passes 12/12, including "UPDATE on transcriptions /
extracted_clearances is refused".

**7.3 proof** (`clearance_demo.py`: two replay passes through the real AircraftService +
ConflictService, with the oracle clearances read from the recording's own +10 min).
`session_20260905_003006`: one tier 2 pair held ≥ 5 updates (FDB1345 × IGO5197,
separation-minimum gate). The heading clearance matched all 5 candidates, so nothing moved.
`session_c_20260903_204503` (`reports/clearance_demo_20260925_040016.json`): FDB445 × IGO018,
classifier gate, level cap. **Multi-path conflict probability 0.04-0.24 → 0.000 and breaching
combinations 4-12 → 0 on 9 of 11 updates. Tier and notify unchanged.** The plan's demo beat ("the
pair leaves the watch list") cannot occur since 22 Sep: `alert_gate` decides membership from
the straight-line safety net and the classifier; multi-path moves only the stated probability,
the tier timing and Model 3's checks. **Exit gate met:** live API on :8001 (replay, PostgreSQL,
per_mode). A valid DESCEND for AXB1693 was applied; an unknown callsign and a 310,000 ft level
were refused with reasons (422). All three are in `extracted_clearances` and `audit_logs` and
were read back through `GET /api/clearances` and `GET /api/audit`. Port 8000 was held by an
unrelated project (NeerNiti_Demo, since 21 Sep), which was left untouched.

**Phase 8.** `ml_pipeline/utils/ablation.py` generates `docs/ablation.md` and
`docs/ablation.json`: every row from a saved artifact, per regime, four-seed variance with t
95% CIs, and Wilson 95% intervals on the headline (classifier 267/284: 90.6-96.2%; running
system 269/284: 91.5-96.8%, indistinguishable). Every earlier-quoted number reproduced
(63.6/38.6, 71.5/44.2, 75.4/46.8, 65.7 tree). New: at ten minutes the tree reference's
single answer is 40.5% for arrivals, below per-mode top-1 44.2%, so **per-mode multi-path now
beats the tree**, which beat every neural model on every earlier split.
`reference_benchmark.py` now saves `tree_reference_test_predictions.npy`, and its published CSV
came back byte-identical. **8.3:** `docs/claims.md` (can / cannot / must state, each number
with its source). Found while writing it: the "93.3% at the rule's false-alarm cost" figure
was the 5 Sep model; the current one is 93.7% (266/284), from the 23 Sep re-score. Stale
figures in `PROJECT_STATUS.md` were corrected (93.7→94.0 headline basis, 94.06→94.39 recall,
table 93.7/93.3→94.1/93.7).

**9.7 — C1 and C2 fixed** (`resolution_engine.py`). `_pair_geometry(report_from_seconds)`: the
reported "resulting separation" is measured from the end of the 38 s response delay, never from
t = 0 (C1). `generate_resolutions` computes each aircraft's do-nothing risk; `is_offerable`
requires `baseline_risk > RESIDUAL_RISK_LIMIT`, so no manoeuvre is offered when doing nothing
keeps separation, and the reason says so (C2). Re-score (`reevaluation_20260924_222306.json` vs
23 Sep): **683 of 698 values identical; the 15 that differ are all Model 3.** Instructions
offered 76 → 46; for false conflicts 38 → 11; for real 38 → 35 (those 3 were on alarms whose own
simulation showed no violation to prevent). Alarms with options 31 → 21. `verify_pipeline.py`
110/110, and 15 unit tests (11 + 4 clearance).

**9.8 — H1 fixed.** `siteLogger.logAudit` also calls `postAuditLog` (all 44 call sites);
failure is reported in the tab log. `/logs` opens on the server audit log and cannot clear it.
`vite build` passes. H2 is still open.

### 2026-09-25 — H2 and H3 fixed; plan 9.1 runway-in-use derived (spot-check flagged)

**H2** (`server/app/api/routes.py`, `_served_model_versions`): accept, dismiss and
`POST /api/audit` now carry the running engine's model versions (trajectory_residual,
trajectory_multipath with its offsets mode, xgboost_conflict, rule_path), stamped by the server.
The client's value is kept as `detail.clientModelVersion`. **H3** (`client/src/lib/adapters.js`,
`HomePage.jsx`): dismissals are keyed by `episodeKey` = pair | firstSeen | tier | best manoeuvre
type | magnitude. `vite build` passes.

**Plan 9.1** (`scripts/derive_runways.py`). `traffic` 2.13, the newest release, imports
`pandas.core.internals.blocks.DatetimeTZBlock`, which pandas 3 removed. This project runs pandas
3.0.5, so `traffic` runs in `%LOCALAPPDATA%/FlightRight/venv_traffic` (pandas 2.3.3), and the two
environments exchange only parquet. It was removed from the main venv again; `openap` 2.6.2
(its dependency, needed for 9.4) stays and is added to `ml_pipeline/requirements.txt` with
`certifi`. Core versions unchanged (numpy 2.5.2, pandas 3.0.5, torch 2.13.0+cu126, fsspec
2026.7.0). Over 91,554 airborne states within 40 NM of VABB from 905 aircraft,
`Flight.landing("VABB")` found **753 landings: 751 on runway 27 and 2 on 32**
(`ml_pipeline/reports/runway_landings_20260925_040126.json`,
`ml_pipeline/data/processed/runway_landings.parquet`). That fits the southwest monsoon
(westerlies), but it means runway in use carries almost no signal in the polled sessions, so no
ablation row was trained on it. The archive (all seasons) is where it would matter. **Spot-check
by a person is flagged** (`docs/figures/runway_spotcheck.png`, 8 random landings): Claude's
look found all 8 are straight westbound finals on the runway latitude after an easterly
approach, but the plan requires a human check.

### 2026-09-25 — Join-key bug found and fixed; plan 9.2 route-lookup accuracy; plan 9.0 coverage measured

**Bug: the icao24/callsign join keys in `trajectory_*.npz` belonged to other windows.** Phase 1.3
(22 Sep) added them, but `save_time_splits` reordered X/y/mask/timestamps by time and not the
keys. Found when plan 9.0 joined adsb.lol intent on them. Selected-altitude coverage came out at
6.7% of windows, with a median time gap of about 22 h to the nearest report at every distance
from VABB. Aircraft 8963ff was labelled on 4 Sep windows but exists in the raw data only on
29 Aug. Fixed in `preprocess_sequences.py`. On re-running, **X, y, mask and timestamps are
byte-identical in all three splits** (no published number can move; no model reads the keys),
and the keys changed on 99.9% of windows. New `verify_pipeline.py` check: 200 spread test
windows are joined to raw positions by (icao24, time), and 199/200 match on the new files, 0/200
on the old. **Suite: 111/111.** The 22 Sep verification had compared only the model arrays.

**Plan 9.2 — route lookups over Indian airspace** (`scripts/route_lookup_accuracy.py`,
`reports/route_lookup_20260925_*.json`; cached under `ml_pipeline/data/routes/`, gitignored). Truth:
OpenSky `flights_data4` est. departure/arrival for 1,923 of our flights (a flight is joined when
OpenSky's firstseen-lastseen span covers our observations). Truth cross-check: of 434 flights we
saw land at VABB (`runway_landings.parquet`), OpenSky says VABB for 418 (96.3%).

| | adsbdb | hexdb |
|---|---|---|
| answers | 91.9% | 34.0% |
| route exactly right, of all flights | **49.0%** | 19.0% |
| route exactly right, of answered | 53.4% | 56.0% |
| destination right, of all | 74.4% | 24.7% |
| Mumbai flights (540), route exactly right | **69.1%** | 16.1% |

To our knowledge this is the first such figure for India. It sits between the plan's cited
~60% (Southeast Asia) and 13–27% (US).

**Plan 9.0 — selected-altitude coverage, measured before building on it**
(`scripts/fetch_adsblol_traces.py`, `ml_pipeline/utils/adsblol_parse.py`,
`reports/adsblol_fetch_20260925_042403.json`, `reports/adsblol_coverage_20260925_042546.json`). All
4,142 aircraft-days in our 35 sessions (1,733 aircraft, 9 dates, 24 Aug–5 Sep 2026) were fetched
from adsb.lol globe_history at ≤ 2 req/s: 4,090 served, 52 not found (222 MB, gitignored,
ODbL 1.0). **99.6% of served aircraft-days carry `nav_altitude_mcp` at least once; 94.8% of
airborne detail points within 60 NM of VABB carry it; 72.4% carry the aircraft's own wind.**
Per training window (backward join, ≤ 300 s, `context_features.py`): selected altitude
51.5% (train), wind 49%, type 82–86%, surrounding traffic 100%. The shortfall from 95% is
windows far over the sea, beyond adsb.lol's receivers. **Time-critical:** adsb.lol serves
about six weeks directly, so these days would have become unfetchable from about 5 Oct 2026.
They are now on disk.

### 2026-09-25 — Plan 9.0 / 9.4 / 9.5 / 9.6 measured: context helps the classifier, not the trajectory model

**Trajectory rows** (`context_ablation.py`, `reports/context_ablation_20260925_050255.json`; offset
regressors only, seed 42; generated into `docs/ablation.md`). The baseline was re-run (71.5 / 44.2,
reproduced). Adding intent, wind, type, traffic or all four moves arrivals best-of-5 by
−0.0/+0.5/+0.4/+0.1/+0.2 points, top-1 by −0.6 to −0.2, and 3-D best-of-5 by −1.6 to +0.1. All of
that is within the four-seed spread (sd 0.4-0.8). **No context type helps the trajectory
model.** Not served.

**The dialled level is a step, not a destination.** Among test windows with a dialled level
≥ 300 ft from the current altitude (9,024), the true altitude is already > 1,000 ft past it
(re-cleared) for 0.6% at 1 min, 20.5% at 3 min, 45.3% at 5 min and **77.5% at 10 min**. Capping
the served candidates at it (STCA Option E, fed by `nav_altitude_mcp`): top-1 height error
238→232 ft at 1 min, but 697→869 at 3, 1,087→1,824 at 5 and 1,673→5,068 at 10. Consistent with
EUROCONTROL using the selected level for STCA's roughly 2-minute look-ahead, not for
10-minute prediction. It was not used as a cap anywhere.

**Conflict classifier + dialled level** (`classifier_intent_ablation.py`,
`reports/classifier_intent_20260925_050817.json`; the encounter set is rebuilt and verified
40,000 × 32 identical, now recording each side's icao24 via `offsets_ab_test`, and cached as
`processed/encounters_with_intent.parquet`). Features: `a_/b_sel_alt_delta_ft`, joined backward
≤ 300 s; B's is invariant to its altitude offset. Also `sel_level_separation_ft`. Coverage:
39.5% / 39.2% / 15.9% of encounters. Baseline retrained on CPU with identical settings (seed
42 reproduces the 5 Sep CPU figures, 0.9406 / 87.0; the served 6 Sep GPU model is 0.9439 / 96.8).

| seed | base recall / FA / 3-min | +intent | lost / gained | +intent at base FA: recall |
|---|---|---|---|---|
| 42 | 0.9406 / 87.0 / 266 | 0.9439 / 76.1 / 267 | 1 / 2 | 0.9505 |
| 1 | 0.9472 / 109.0 / 268 | 0.9406 / 67.4 / 266 | 4 / 2 | 0.9604 |
| 2 | 0.9505 / 99.1 / 269 | 0.9406 / 71.4 / 266 | 4 / 1 | 0.9505 |
| 3 | 0.9505 / 93.2 / 269 | 0.9538 / 92.8 / 270 | 0 / 1 | 0.9538 |

At equal false-alarm cost, +intent recall ≥ baseline in 4/4 seeds, so the information is
real. At the val-selected threshold, false alarms fall about 21% on average (97.1 → 76.9), but
2 of 4 seeds lose net real conflicts. The trade is a threshold decision, and serving needs a
live `nav_altitude_mcp` feed that does not exist yet. **Flagged, not served**
(`docs/DECISIONS_FOR_ARCHIT.md` item 1).

**Housekeeping.** New `docs/DECISIONS_FOR_ARCHIT.md` gathers every flagged item.
`ablation.py` now renders the plan 9 sections from their reports.

### 2026-09-25 — Pre-push verification of every non-speech number, a live demo, and one demo defect fixed

**Plan status.** Every non-speech item of plan v8 (Phases 0-3, 7, 8, 9 except 9.3) has code,
a report and a log entry. Outside the repo or waiting on a person: 0.3 (the README copy in the
Claude project), 9.1's eye spot-check, and the items in `docs/DECISIONS_FOR_ARCHIT.md`.

**Numbers re-measured, all CPU:** `verify_pipeline.py` 111/111; 15 unit tests;
`inference_check.py`; `reevaluate_models.py` 697 of 698 values identical to
`reevaluation_20260924_222306.json` (only `measured_at_utc` differs; duplicate deleted), so
headline **267/284 = 94.0%** and runtime gate 269/284; `offsets_ab_test.py` identical to
`offsets_ab_20260924_181140.json` apart from timestamps (served per_mode rule_only 762 alerts,
269/284, 101.1 FA/1000, t1 28/17; duplicate deleted); `ablation.py` regenerates
`docs/ablation.md` identically apart from its timestamp; `postgres.py verify` 12/12; `vite
build` passes.

**Demo defect: replay opened on an encounter that can no longer alarm.**
`server/app/services/replay_service._seek_to_first_encounter` chose the first pair predicted
inside the 8 NM / 1,500 ft alert volume. Since the 22 Sep classifier gate, a pair alarms only
when the straight-line safety net sees 5 NM / 1,000 ft breached or the classifier agrees. On
the newest session the seek chose `UAE325 x ABY821` (1,100 ft vertical), which correctly never
alarmed, and five minutes of replay passed with no alarm on screen. It now seeks on
`SEPARATION_LATERAL_NM` / `SEPARATION_VERTICAL_FT` and picks `IGO086 x FDB1346` (frame 55). This
chooses where playback starts, not when anything alarms.

**Demo, driven in headless Chrome (playwright-core, scratch folder, not a project dependency):**
alarm `IGO086 x FDB1346`, 2.61 NM / 950 ft, 180 s to CPA, classifier 0.75, two Model 3 options
(descend to FL364, confidence 0.87, score 0.989; turn right 30°, confidence 0.92); ACCEPT disabled
until one is selected; accepting wrote audit row `decision=accepted, confidence=0.87` with served
model versions. At 15 s to CPA the same dialog correctly offered nothing and disabled ACCEPT. API:
dismiss recorded; a DESCEND clearance matched IGO086 to `8015c9` and capped altitude; an unknown
callsign was refused (422). 0 console errors, 0 failed requests over three runs.
**Still visible and still open:** the top bar's invented `ATIS M · RWY 27R / 27L` (issue list,
"Hardcoded values"). Mumbai has no 27L/27R.

**Environment:** `peft` 0.21.0 and `accelerate` 1.15.0 installed for the speech fine-tune. The
dry run showed only those two packages would install; torch, numpy, pandas and fsspec are
unchanged.

## 15. Plain-English change log (every change, explained for a beginner)

Governed by Section 1a, Part 8. Every entry states: which file, what it was before,
what it is now, why, and whether the headline number moved. Newest entries at the
bottom. This log is for understanding; Section 14 is the technical evidence trail.
Neither replaces the other.

### 2026-09-05 — Added the OPERATING RULES section

**File:** `CLAUDE.md` (new Section 1a, inserted between Sections 1 and 2).

**Before:** The file opened with the project description and went straight into
research framing and a long list of technical decisions. There was no single place
saying which number matters most, which decisions were settled, or when to stop and
ask a human. Every session had to reconstruct all of that by reading 1,000 lines.

**Now:** A section at the top with nine parts: the one headline number, a status
table, ten settled rules, the open problems in priority order, the experiments
already tried and rejected, when to decide alone versus when to ask, how to explain
results to a non-expert, how to log changes, and how to source proposed fixes.

**Why:** Instructions had been relayed into this repo from another AI and results
relayed back out. That left Archit without the reasoning behind his own project, and
left each session without enough context to make its own calls. This section closes
both gaps.

**Headline number:** Unmoved. This is documentation, not code.

### 2026-09-05 — Added the change-logging and source-citing rules

**File:** `CLAUDE.md` (Section 1a, Parts 8 and 9).

**Before:** Changes were recorded in Section 14 in technical language aimed at
someone who already understood the pipeline. Proposed fixes did not have to say where
they came from.

**Now:** Part 8 requires every change to be logged here in five parts, in language a
non-specialist can follow. Part 9 requires every proposed fix to cite a paper,
standard or article with a working link, **or** to state explicitly that it is our own
design with no source.

**Why:** Archit gets asked "where did this come from" by mentors and must always have
an answer. The original project proposal cited five papers to justify a flight-path
model, two of which were about converting radio speech to text. An unsourced idea
presented as established practice is precisely the failure to prevent.

**Headline number:** Unmoved.

### 2026-09-05 — Corrected the t=0 figure in the open-problems list

**File:** `CLAUDE.md` (Section 1a, Part 4, item 4).

**Before:** The entry read "the scenario generator puts 45.5% of **conflicts** at
t=0".

**Now:** It states that 45.5% of **all scenarios** have their closest approach at
t=0, and separately that 25.3% of the labelled **conflicts** do (2,427 of 9,583).

**Why:** The original wording attached the 45.5% to the wrong population. Measured
directly on `ml_pipeline/data/synthetic/conflict_scenarios_20260905_092049.parquet`:
45.5% is the figure across all 40,000 scenarios, and the conflict-only figure is
25.3%. Both matter and they are different numbers. "Closest approach at t=0" means the
two aircraft are already as close as they will ever get at the moment we first see
them, so there is no warning to give — which makes any warning-time measurement taken
over those rows meaningless.

**Headline number:** Unmoved by the correction itself, but this defect is one of the
reasons the headline number cannot currently be measured from the classifier. It is
measured from the rule-based detector instead.

### 2026-09-05 — Status table now covers the backend and the frontend

**File:** `CLAUDE.md` (Section 1a, Part 2).

**Before:** The table listed only the four models.

**Now:** Two rows added. The backend is **NOT STARTED** — `server/` contains a
requirements list, four empty placeholder folders, and four trained model files, but
no server code whatsoever. The frontend was built but is **not on this branch**; it
was removed by commit `9b6800b` on 30 August and is recoverable with
`git checkout 91720e7 -- client`.

**Why:** Asked "where is the backend", the honest answer is "it does not exist yet",
and the table should say so rather than leaving it to be discovered. Section 8 of this
file still describes the frontend as present, which is no longer true of this branch;
anyone planning a demo needs to know that restoring it is a prerequisite step.

**Headline number:** Unmoved.

### 2026-09-05 — Added a full plain-English project status document

**File:** `PROJECT_STATUS.md` (new file, repository root).

**Before:** Understanding the project meant reading CLAUDE.md's 1,200 lines, most of
it written for a reader who already knew the pipeline, plus opening the code.

**Now:** A single document that defines the aviation vocabulary in nine lines,
states where every component stands, explains what each of the 16 code files does,
walks through the LSTM's inputs and outputs from scratch, and sets out exactly what is
wrong with the conflict classifier and how to fix it.

**Why:** Archit is learning ML while building this, and the outputs get forwarded to
mentors who know neither ML nor aviation. Keep it current as things change.

**Headline number:** Unmoved.

**One measurement taken while writing it, worth recording.** The circular-label defect
in the conflict classifier was verified rather than inferred. Recomputing the label
from just two of its own input features reproduces it for **40,000 of 40,000 rows,
exactly 100.000%**. The classifier's perfect PR-AUC of 1.0 is therefore fully
explained by leakage. This is the standard symptom described in Kaufman, Rosset &
Perlich, *Leakage in Data Mining* (KDD 2011),
<https://dl.acm.org/doi/10.1145/2020408.2020496>.

### 2026-09-05 — Rebuilt the conflict classifier so it is no longer asked a question it was given the answer to

**Files:**
`ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py` (rewritten)
and `ml_pipeline/training/conflict_classifier/train_xgboost.py` (rewritten).

**What it was before.** The practice situations were built by taking one **real**
aircraft from the OpenSky data and **inventing** a second aircraft beside it. Both were
then assumed to fly in a perfectly straight line, and the answer key was written by
checking whether those two straight lines came too close. Two of the nine facts given
to the model were how close those straight lines came. So the answer key was calculated
from the model's own inputs. Its job was to rediscover a rule it had already been
handed, which is why it scored perfectly. Verified rather than assumed: recomputing the
answer from just those two inputs gave the right answer for **40,000 rows out of
40,000**.

**What it is now.** Both aircraft are real, and each one has a real recorded ten-minute
future taken from the data. The two are still introduced to each other artificially,
because genuine near-misses almost never happen and we would be waiting forever for
one. But aircraft B's real flight path is picked up and moved as **one rigid piece**,
like sliding a photograph across a table and turning it. Every real turn, climb and
speed change inside it is preserved exactly. Nothing about the flying is invented.

The model is now told what our **straight-line prediction** says will happen, and is
asked what **actually** happened. Those are different things, which is the whole point.

**Why.** A model that is handed the answer learns nothing, and every number reported
about it describes the arithmetic rather than a model. Shipping it would have meant
putting an AI label on an if-statement. The new arrangement lets the model learn
something genuinely useful and available no other way: **where our own predictions go
wrong.**

**Did it work?** Yes, and the reason is understandable. The straight-line rule's
mistakes are almost entirely **vertical**. In 99% of the conflicts it misses, it
correctly sees the two aircraft passing close side-to-side, but wrongly believes they
will stay far apart in height. It predicts a gap of about 2,825 ft when the real gap
turns out to be about 498 ft. The reason is that those aircraft are climbing or
descending roughly eight times faster than average, and a straight-line guess handles
that badly. The model learned to distrust the predicted height gap when an aircraft is
climbing or descending hard.

The fair test is whether it wins **without simply raising more alarms**, since catching
more conflicts is easy if you are willing to cry wolf. Measured at exactly the same
false-alarm cost as the rule:

| | Rule | Model |
|---|---|---|
| Conflicts caught | 88.1% | 93.7% |
| Headline metric | 87.3% | 93.3% |
| False alarms per 1000 pairs | 73.8 | 73.8 |

**Headline number:** it moved, but read the basis before celebrating. It is now
**93.7%**, against 93% before. Those are not the same measurement. The old 93% was
scored against an answer key the straight-line arithmetic had written itself, so it
measured whether the arithmetic agreed with the arithmetic. The new figure is scored
against where real aircraft really went. The two landing so close together is a
coincidence. What genuinely improved is that the number now means something, and that
the model beats the rule by 6 points on the same honest basis.

### 2026-09-05 — Practice conflicts now develop while you watch, instead of starting already in progress

**File:** `ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py`.

**Before.** 45.5% of practice situations had the two aircraft already at their closest
point at the very first moment, and 25.3% of the actual conflicts did. In that
situation there is no warning to give and nothing a controller could do.

**Now.** Any pair that is already inside the alert zone at the first moment is thrown
away and replaced. **0.00%** of conflicts now start with no warning. Of the conflicts
generated, **95.0%** leave at least three minutes to act.

**Why.** The headline metric of this whole project is how much warning we give.
Measuring warning time on situations that have no warning time is self-defeating. The
figures produced before this fix could not be used for anything.

**Headline number:** this is the fix that makes the headline number measurable at all.

### 2026-09-05 — A guard that refuses to train on a circular dataset ever again

**File:** `ml_pipeline/training/conflict_classifier/train_xgboost.py`.

**Before.** Nothing checked whether the answer key could be worked out from the
questions. The defect survived for weeks and produced a model that looked perfect.

**Now.** Before any training happens, the script recomputes the answer key from the
inputs and reports how often that succeeds. Above 99% it stops with an error and
refuses to train. It also refuses if any column describing what actually happened has
been added to the input list by mistake. Current reading: **95.60%**, which passes.

The script now also loads only the new data files by name. The old circular files are
deliberately not matched, so one cannot be picked up by accident and quietly undo the
fix.

**Why.** A rule that lives only in someone's memory is not a rule. This one now fails
the run.

**Headline number:** unmoved. This protects the number rather than changing it.

### 2026-09-05 — Reported a failing gate instead of tuning it away

**File:** `ml_pipeline/training/conflict_classifier/train_xgboost.py`, Gate 1.

**What happened.** The project requires the classifier to catch at least 95% of real
conflicts. It catches **94.06%**. The gate fails by six tenths of a point.

**The diagnosis, which matters more than the number.** This is not the model falling
short. It is how the alarm sensitivity gets chosen. The script picks the *least*
sensitive setting that still reaches 95% on the practice data, which by definition
lands exactly on the boundary, at 95.11%. Tested later on a different week of traffic,
it slips just under. Choosing a setting with a little margin above the boundary would
fix it, and the model comfortably clears 95% at any slightly more sensitive setting.

**Why it was left failing.** Changing that setting changes when a real controller gets
interrupted, which is explicitly a decision that needs Archit's sign-off. Beyond that,
a failing gate that is honestly reported is worth more than a passing one that was
massaged. The second gate, which asks whether the model actually beats the simple rule,
**passed**.

**Headline number:** unaffected. The headline is measured at the chosen setting and is
93.7%.

### 2026-09-06 — Ran the whole pipeline from scratch to check it actually works

**Files:** none changed. Every training script was run in order, start to finish.

**Before.** Each stage had been run at some point, but never all of them in sequence on
the same day from the same raw data. So nobody could say for certain that the whole
chain worked, or that the saved model files matched the code that was supposed to have
produced them.

**Now.** All six stages ran in order and every one reproduced its recorded result.

| Stage | Outcome |
|---|---|
| Turning raw data into training examples | 291,008 examples, as recorded |
| Training the trajectory model | Passed its gate |
| The non-neural comparison model | Passed its gate |
| Training the multi-path model | Passed its gate |
| Building the conflict practice data | Identical file to the previous run |
| Training the conflict classifier | Headline 93.7%, as recorded |

**Why this matters.** Four of the six stages came back **bit for bit identical** to the
previous run, which means they are properly seeded and repeatable. If someone asks
whether these numbers can be reproduced, the answer is now yes and it has been checked.

**One honest wrinkle.** The trajectory model came back at 60.8% where it was recorded at
60.9%. That one-tenth of a point is the graphics card doing floating-point arithmetic in
a slightly different order between runs, not a change in the pipeline. Worth knowing so
nobody chases it. Also unchanged: the simple non-neural model is still **4.9 points
better** than the neural one at ten minutes, so the neural model must not be described as
our best.

**Headline number:** unmoved at 93.7%. Nothing was tuned. This was a check, not an
improvement.

### 2026-09-06 — The project now has an automatic check that everything still works

**File:** `ml_pipeline/utils/verify_pipeline.py`, new.

**Before.** There were no automatic tests at all. Two demonstration scripts existed that
a person had to run and read. Both of the project's worst defects were silent: the
trajectory model that lost to plain arithmetic for three weeks, and the conflict
classifier that scored a perfect result for weeks while having learned nothing. **Neither
of them crashed.** Nothing was broken in a way a computer would notice. They were only
visible to someone who looked at the output and asked whether it made sense.

**Now.** One command runs 57 checks and prints PASS or FAIL for each. It opens each saved
model file the way the future backend will, from a cold start with no help from the
training scripts, and asks three kinds of question:

- **Is the output the right shape?** Does the trajectory model return four future
  positions, each with a latitude, a longitude and an altitude?
- **Are the numbers physically sensible?** Are the predicted positions actually over
  western India, and are the altitudes possible for an aircraft?
- **Are the known traps still shut?** Can the conflict answer key still be worked out
  from the questions? Is any column describing what actually happened being fed in as an
  input? Is the test data still strictly later than the training data?

It also walks two aircraft all the way through to a controller alert, and checks the
alarm refuses to fire on a single reading but does fire once the situation has held for
three readings in a row, with a written explanation attached.

**Why.** A rule that lives in someone's memory is not a rule. Every hard-won lesson in
this project was previously written down and nothing enforced it. Now the important ones
fail the run.

**Two bugs in the checker itself, found while writing it, worth admitting.** It first
looked only at the earliest 3,000 examples, which is one afternoon rather than a fair
sample, so it now spreads its sample across the whole test period. And the two aircraft
it walked through the system were 46 nautical miles apart and moving away from each
other, so every alarm check passed **without the alarm ever going off**. A test that
passes without exercising the thing it claims to test is worse than no test, because it
creates confidence that has not been earned. It now uses a pair deliberately set on a
collision course as well.

**Headline number:** unmoved. This protects the number rather than changing it.

**Result:** 57 of 57 checks pass.

### 2026-09-06 — Built Model 3, the part that suggests what to actually do about a conflict

**File:** `ml_pipeline/utils/resolution_engine.py`, new.

**Before.** The system could spot a conflict and raise an alarm, and then it stopped. It
had a single true-or-false flag saying a suggestion *would be* allowed, and nothing that
produced one. A controller would have been told there is a problem and left to solve it
alone.

**Now.** For a confirmed alarm the system proposes up to three ways out, one of each
kind: change an altitude, change a heading, change a speed. Each comes with what
separation it actually achieves, roughly what it costs in delay and fuel, a confidence
figure, and a sentence a controller could read aloud. For example:

> Descend AI2841 to FL330. Reason: holds vertical separation at 2,000 ft where the
> paths cross. Fully established about 118 s from now, against a closest approach in
> 165 s. Confidence 0.79. Tradeoff: about 1.0 min of extra fuel burn.

They are ranked by the project's fixed formula, which weights safety at 60% and
everything else at 40% between them. **Nothing is ever applied automatically.** The
system offers; the controller decides.

**Why it is built the way it is.** The easy version would move the aircraft to its new
heading instantly and check whether that fixes things. That would be wrong in the
dangerous direction, because it would confidently recommend turns that no real aircraft
could complete in time.

So every suggestion is actually **flown** in simulation. For the first 38 seconds
nothing happens at all, because the controller has to decide, call the pilot, hear the
readback, and the pilot has to act. Only then does the aircraft begin to turn or climb,
at the speed a real airliner does it. Separation is measured from what comes out.

**Two things this taught us that we did not know before, both worth telling a mentor.**

**One: with 90 seconds left, nothing works.** Not the climb, not the turn, not the speed
change. All 26 possible instructions were rejected. Thirty-eight of those ninety seconds
are gone before the aircraft moves at all, and nothing an airliner can do in the
remaining fifty-two opens up a safe gap in time.

That is a strong independent confirmation of a decision the project had already made on
paper, that alarms should be raised at three minutes. Two separate methods, the pencil
calculation and this simulation, arrive at the same place. An alarm raised much later
than three minutes is genuine and completely useless.

**Two: one of our stated rules turns out to be too broad.** The project says to prefer
altitude changes when time is short, because a climb takes about 40 seconds while a turn
takes about 96. The arithmetic is correct but the rule does not hold generally. Testing
it directly, climbs and turns became available at exactly the same moment, between 90
and 105 seconds. There is no window where the climb works and the turn does not, because
in a head-on encounter a turn changes the geometry very quickly.

Altitude still comes out top, but for an honest and different reason: it is **easier to
manage**. A climb is one instruction the controller can watch working. A turn has to be
remembered and later undone.

Rather than hard-code a preference that turns out to be wrong in some geometries, the
engine simply tries every option on every conflict and rejects the ones that do not work.
That is safer in both directions. **The original rule in the project document has not
been edited**, because the process here is to record the measurement and let you decide,
not to quietly rewrite the specification.

**Headline number:** unmoved at 93.7%. Model 3 acts after a conflict is detected, so it
cannot change how many conflicts we catch. It changes what happens next.

### 2026-09-06 — The automatic check now covers Model 3 as well

**File:** `ml_pipeline/utils/verify_pipeline.py`.

**Before.** 57 checks, covering the data and the first three models.

**Now.** 73 checks. The 16 new ones confirm the suggestion engine behaves safely:
nothing moves during the 38-second delay, every suggestion offered genuinely restores a
safe gap, every one carries an explanation, a watch-list pair is never given a
manoeuvre, an instruction that would take an aircraft below the 10,000 ft floor is
blocked rather than offered, and when nothing can work the system says so instead of
suggesting something useless.

**Why.** This is the part of the system that would put words in a controller's mouth. It
is the last place where a silent mistake should be possible.

**Headline number:** unmoved. All 73 checks pass.
### 2026-09-06 — The whole training run is now one command, with a report at the end

**Files:** `ml_pipeline/run_pipeline.py`, `ml_pipeline/check_environment.py`,
`ml_pipeline/README_TRAINING.md` (all new).

**Before:** Training meant running seven scripts by hand in the right order, watching
each one's output scroll past, and copying numbers out of the terminal. Nothing checked
first whether the graphics card was actually being used.

**Now:** `python ml_pipeline/check_environment.py` says whether the laptop is ready
(Python, packages, the RTX 4060 visible to PyTorch, raw data present, disk space), and
`python ml_pipeline/run_pipeline.py` runs everything in order, saves every line of
output to a log per step, and writes a Markdown report listing each gate result, the
headline number and the key tables. If a step fails it stops there, so a model can never
be trained on half-processed data.

**Why:** Archit trains on a different machine from the one the code is written on. A
run that can be started with one command and hands back one folder is a run whose
results can be trusted and compared.

**Headline number:** Unmoved. This is plumbing; the numbers come from the real run.

### 2026-09-06 — The multi-path model's probabilities are now corrected on held-out data

**File:** `ml_pipeline/training/trajectory/multipath.py`.

**Before:** When the model said "90% likely" it was right about 67% of the time. It was
over-confident, and the two tier thresholds (0.85 and 0.60) compare against exactly
these numbers.

**Now:** After training, the script measures on the validation data (data the model
never trained on) how over-confident it is, and finds one correction number, called a
temperature, that flattens every stated probability by the right amount. It then shows
the before-and-after reliability on the test data. The correction cannot change which
five paths are offered, only how likely each is said to be, so the "one of the five was
right 63.6% of the time" figure is unaffected by construction.

**Why:** Rule 9 in Part 3: a threshold means nothing until the probability it is
compared to is truthful. Source: Guo et al., "On Calibration of Modern Neural
Networks", 2017, <https://arxiv.org/abs/1706.04599>.

**Headline number:** Unmoved. The multi-path probability feeds tier 2 (the watch list),
not the classifier that the headline number is measured on.

### 2026-09-06 — Candidate paths are now checked every 15 seconds, not at four instants

**File:** `ml_pipeline/utils/cpa_conflict_detection.py` (`densify_path`, and a new
optional argument to `compute_cpa_from_paths`).

**Before:** The multi-path model predicts positions at 1, 3, 5 and 10 minutes only, and
the conflict check between two aircraft's candidate paths looked only at those four
moments. Two paths crossing at four minutes were measured at three and five minutes,
where they were far apart, and the crossing was missed. This was the same blind spot
already fixed for the straight-line path on 1 September.

**Now:** Each candidate path is filled in between the known points with straight
segments, starting from where the aircraft is right now, so the check runs on the same
41-point grid the straight-line detector uses. A test with two paths crossing at exactly
four minutes: the old check reported them 16 NM apart, the new one finds the crossing.

**Why:** A model that predicts a conflict which the checker cannot see is a model whose
prediction was wasted.

**Headline number:** Unmoved (tier 2 path).

### 2026-09-06 — The conflict classifier explains itself, states honest probabilities, and shows the cost of a safer threshold

**File:** `ml_pipeline/training/conflict_classifier/train_xgboost.py`.

**Before:** It printed a probability that was not checked for truthfulness, printed
feature importance for the whole model but nothing per alert, and left the threshold
decision in Part 4 without numbers to decide it with.

**Now, four things, none of which changes a single alert:**
1. The probability is corrected on validation data (Platt scaling) and the script
   proves the set of alerts on test is identical before and after. It refuses to save
   otherwise.
2. For each alert the model can now say which facts pushed it towards "conflict" and
   by how much (SHAP values, computed by XGBoost itself). The backend returns the top
   five as the alert's explanation.
3. A "what-if" table shows, for three small safety margins on the recall floor, what
   the threshold would be, how many conflicts would be caught and how many false alarms
   it would cost. Marked "NOT applied". This is the information Archit needs for the
   decision in Part 4 item 2.
4. It trains on the graphics card when one is present, and writes a model card (a JSON
   file with every number from the run) beside the model.

**Why:** Section 3 requires SHAP so controllers can see why an alert fired; Section 12
forbids surfacing a prediction without a rationale; rule 9 requires calibration.

**Headline number:** Unmoved. Same alerts, same recall, same warning times.

### 2026-09-06 — A single place that turns two aircraft into the classifier's 24 inputs

**File:** `ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py`
(`encounter_features`, `manoeuvre_summary`).

**Before:** The 24 numbers the classifier sees were computed inside the training data
generator, in a block of code nothing else could call. The backend would have had to
copy it, and copies drift.

**Now:** One function computes them, both for training and, through
`server/app/ml/inference.py`, for live pairs. A check inside it fails the run if its
output ever stops matching the official feature list.

**Why:** A model fed slightly different features in production than in training gives
answers nobody measured. Same arithmetic, same result; just callable.

**Headline number:** Unmoved.

### 2026-09-06 — The backend can now load and run all three models

**File:** `server/app/ml/inference.py` (new), plus `ml_pipeline/tests/inference_check.py`.

**Before:** The models existed only as files. Nothing outside the training scripts could
load them.

**Now:** One module loads the trajectory model, the multi-path model and the conflict
classifier, and offers `assess_pair`, which for two aircraft runs the straight-line
rule (always), the multi-path probability (for the 3-10 minute watch list), the
classifier with its explanation, and the tiering rule with its three-consecutive-updates
requirement. Every answer says which sources it used and which model version produced
it. If a model file is missing, it says so and falls back to the rule.

**Why:** Section 5 lists the API endpoints; every one of them needs exactly this
underneath. The API itself is still to be written.

**Headline number:** Unmoved.

### 2026-09-06 — First automated tests, and a fake-data rehearsal of the whole pipeline

**Files:** `ml_pipeline/tests/` (`test_units.py`, `smoke_test.py`, `fake_traffic.py`,
`inference_check.py`).

**Before:** The project had no automated tests (recorded as a gap in PROJECT_STATUS.md).

**Now:** Eight unit tests cover the new geometry and calibration code. A smoke test
generates invented flight tracks into a temporary folder, runs the entire pipeline on
them in about three minutes on a laptop CPU, checks every model file was written, and
loads them through the backend module. It deletes the folder afterwards and never
touches real data.

**Why:** A pipeline that has never been run end to end on the machine that will run it
fails on the training laptop at step five, twenty minutes in. Rehearsing catches that
here. **The fake data proves the code runs; it proves nothing about the models** (rule 7:
invented paths teach nothing about Mumbai), and its gate results are never quoted.

**Headline number:** Unmoved.

### 2026-09-06 — The alert-threshold decision has a switch, and Archit has a to-do file

**Files:** `ml_pipeline/training/conflict_classifier/train_xgboost.py`
(`FLIGHT_RIGHT_RECALL_MARGIN`), `ARCHIT_TODO.md` (new).

**Before:** The what-if table showed what a safety margin on the recall floor would
cost, but applying the chosen margin meant editing code.

**Now:** Setting the environment variable `FLIGHT_RIGHT_RECALL_MARGIN` (for example
`0.01`) before running the classifier step selects the threshold for that margin above
the 0.95 floor. Unset, nothing changes. The run prints `DECISION APPLIED` and writes
the margin into the model card and the saved model, so the decision is on record with
the numbers it was made from. `ARCHIT_TODO.md` lists every remaining step of the
project in order, with what "done" looks like for each.

**Why:** Part 6 says threshold changes need Archit's sign-off. A switch with a default
of "unchanged" and a paper trail is how that sign-off becomes reproducible instead of a
one-off edit. This is a decision knob, not a way to make a number look better: the
report prints the false-alarm cost beside every option.

**Headline number:** Unmoved until the switch is set, and the run that sets it prints the
new value with its basis.

### 2026-09-06 — The frontend is back on this branch

**Files:** `client/` (48 files, restored from `origin/main` commit `c7fe5a0`).

**Before:** The React dashboard had been removed from this branch on 30 August so the
branch held only the Python pipeline. Anyone planning a demo had to restore it first.

**Now:** `client/` is the same code as on `main`, which is newer than the version the
30 August commit removed (it uses MapLibre instead of Leaflet). Frontend-only code lives
in `client/`; everything model-related stays in `ml_pipeline/` and `server/`. It still
runs on mock data; connecting it is Step 5 in `ARCHIT_TODO.md`.

**Why:** One branch that contains the whole project. `client/.env` and `node_modules`
remain gitignored.

**Headline number:** Unmoved.

### 2026-09-06 — The system now says what to do, not just that there is a problem

**File:** `server/app/ml/inference.py`, plus new checks in
`ml_pipeline/utils/verify_pipeline.py`.

**Before.** Two halves existed and neither knew about the other. The suggestion engine
worked perfectly on its own. The backend module that the web server will sit on also
worked, running two aircraft through the geometry, the route model and the classifier,
and deciding whether to raise an alarm. But it stopped there. It had **no idea the
suggestion engine existed**, because it was written on a different branch on the same day,
before that engine had been merged in.

Nothing was broken in a way any test could see. Every test passed. The system simply told
a controller "these two aircraft are going to lose separation" and then went quiet.

**Now.** A confirmed alarm carries its suggestions with it. The same result that says
there is a problem now also says what could be done about it, ranked, costed and written
out in a sentence a controller could read aloud.

**Why it needed care rather than one line.** Three things had to be right.

The suggestions are worked out from the **plain physics prediction**, not from the route
model, because that is the prediction the alarm was raised on in the first place. The
engine also re-flies every option itself, so it never inherits somebody else's guess about
where an aircraft is going.

The decision about **whether suggestions are allowed at all** is not re-made here. It is
handed to the engine, which already knows the rule: a watch-list pair is never given a
manoeuvre, and neither is an alarm that has not yet held steady for three readings.
Copying that rule into a second place is how two parts of a system start disagreeing.

Every result now carries a suggestions section **whether or not there are any**, with a
plain reason when there are none, so the dashboard never has to cope with a missing piece.

**Tested through the backend rather than the engine, in the three situations that matter:**

| Time until closest approach | What happens |
|---|---|
| Nearly three minutes | Two suggestions offered, best first, each explained |
| One minute | None offered, and it says why: nothing can work in that time |
| Five minutes | None offered, because that is a watch-list entry, not an alarm |

The one-minute row is the honest one. The system does not invent a suggestion when there
is no time to act on it. It says so.

**A protection against this happening again.** The gap existed because nothing checked
that the chain ran all the way to the end. Seven new checks now confirm it does, and the
automated check went from **73 to 80, all passing**. Your teammate's eight tests still pass
too.

**Headline number:** unmoved at 93.7%. This connects two finished parts. It does not
change how many conflicts are caught.

### 2026-09-06 — Trained everything on the real data for the first time, and the headline went up

**Files:** none changed. `python ml_pipeline/run_pipeline.py` ran all seven steps.

**Before.** Every model on disk had been trained by hand, one script at a time, and the
new probability-correction code had never actually run on real data. The numbers for it
were predictions about what would happen.

**Now.** The whole thing ran start to finish and the numbers are real.

**Headline number: 93.7% to 94.0%.** Of the conflicts that leave a controller at least
three minutes to act, we now catch 267 out of 284. The simple geometric rule catches
87.3% of the same set.

**The probability correction works, and this was the main thing to find out.** The route
model used to overstate its own confidence. Now, when it says something is 30% likely, it
happens about 28% of the time instead of about 24%. The overall measure of how honest
those numbers are improved roughly threefold. The same correction was applied to the
conflict classifier, and importantly **it did not change a single alert**: exactly the
same 740 situations get flagged before and after. It changed what the number means, not
who gets warned. That is the right kind of fix.

**One thing got worse and should not be buried.** The classifier is now only barely
better than the plain geometric rule on the combined score, 0.7326 against 0.7315, where
last run it was 0.7480. It catches slightly more real conflicts than before but raises
noticeably more false alarms doing it. It still beats the rule on every individual
comparison. Worth watching on the next run rather than assuming it is settled.

**A stumble worth knowing about.** The run stopped halfway with an alarming Windows error
code. The training had actually finished perfectly: the quality check passed, the model
was saved, and it loads correctly. The crash happened as the program was closing down,
which on Windows is usually the graphics driver failing to shut down tidily. The pipeline
runner only looks at whether a step exited cleanly, so it treated a successful step as a
failure and stopped. I restarted from the next step and everything completed. Left
unattended it would stop in the same place every time, so it is worth your teammate
fixing.

**Headline number:** moved, 93.7% to 94.0%, and for a real reason. Nothing was tuned.

### 2026-09-07 — Suggestions are now checked against the whole picture, not just two aircraft

**Files:** `ml_pipeline/utils/resolution_engine.py`, `server/app/ml/inference.py`.

**Before.** When the system suggested a way out of a conflict, it checked two things
only: the aircraft being moved, and the one it was in conflict with. It assumed that
second aircraft would fly in a perfectly straight line, and it never looked at anybody
else in the sky.

**Now.** Two changes.

The other aircraft is no longer assumed to fly straight. It is checked against the five
paths the model thinks it might take, weighted by how likely each is. A suggestion is
accepted only if it works across futures covering at least 95% of what could happen.

And every suggestion is now checked against all the other aircraft nearby. If moving one
aircraft out of trouble would fly it into somebody else, the suggestion is thrown out and
the system says which aircraft it would have endangered.

**Why the second one matters, with a real example from the test.** Two aircraft are
head-on and about to lose separation. A third is flying 2,000 ft below one of them, in
the opposite direction. The obvious fix is to descend one aircraft out of the way. The
old system offered exactly that. It would have put that aircraft head-on into the third
one, losing separation 79 seconds later.

So the "fix" would have swapped one conflict for another, and nobody would have noticed
until it happened. The system now rejects it and explains why.

This is a known problem in air traffic research with a name, the domino effect, and
level changes are its most common cause. That is not our observation, it is in the
published literature, and our own test reproduced it on the first try.

**What you will notice.** Slightly fewer suggestions, and the ones offered are checked
far more thoroughly. Each now also carries two new numbers: how much of the other
aircraft's possible futures it still fails against, and how much risk it creates
elsewhere. Both should normally read zero.

**Nothing breaks without the models.** If the path predictions are unavailable the
engine goes back to the straight line and behaves exactly as it did before. The simple
version is still underneath.

**Headline number:** unmoved at 94.0%. This changes what we suggest after a conflict is
found, not how many conflicts we find.

**Checks:** 80 to 87, all passing.

### 2026-09-07 — Counted what actually reaches the controller, and it is not what the headline suggests

**Files:** none changed. This was measurement only.

**What we did not know before.** We knew the classifier's precision was 0.386, which
sounds like six alerts in ten are wrong. What nobody had counted was **which** alerts,
and how often the same one repeats.

**What the counting found.** Of 740 alerts on the held-out test data, **only 41 are
actual alarms** — the kind that makes a noise and comes with suggested manoeuvres. The
other 699 are silent watch-list rows for aircraft still five to ten minutes apart.
**Almost 97% of the false alarms are in that silent list.** The alarms themselves are
right about two thirds of the time, not one third.

Of route-change suggestions, the system offers **77 individual instructions**, and **41
of them — slightly over half — are for conflicts that never happen.** It also evaluated
1,066 possible instructions to arrive at those 77, and on 10 of the 41 alarms it
correctly concluded that nothing would work in time and said so.

**The finding that mattered most.** Replaying real Mumbai traffic, the same pair of
aircraft raises an alert roughly **ten times over** — once per radar update, for as long
as the geometry lasts. One hour of real traffic produced 297 alert messages for **30
actual encounters**. Nothing in the system remembered what it had already told the
controller.

**Headline number:** unmoved at 94.0%. Nothing was changed; this was counting.

### 2026-09-07 — The system now remembers what it already told the controller

**File:** `ml_pipeline/utils/alert_feed.py`, new.

**Before.** Every ten seconds the system re-examined every pair of aircraft from
scratch, with no memory. A pair converging for four minutes generated an alert every
single update — about twenty-four alerts for one situation the controller understood
after the first. Everything also arrived looking equally important: a critical alarm
ninety seconds away and a low-confidence pair nine minutes away were the same size on
screen.

**Now.** Two changes, and **both are about presentation, not about detection.**

First, a pair already on screen does not raise a *new* interruption unless something has
actually got worse. Second, the least confident watch-list entries are gathered into one
counted line the controller can expand, instead of taking a row each.

**The safety rule, and how it is guaranteed rather than hoped for.** You asked that no
real conflict be lost. Rather than test for that afterwards, the module is built so it
cannot happen:

> **Every confirmed pair stays on the active list, every update, always. There is no
> code in the file that removes one.**

All the module can change is whether a pair makes a *noise*, and whether it gets its own
row or sits in a group. A conflict that stops interrupting is still on the screen. So
"stop interrupting" and "stop reporting" are different things, and only the first one is
possible here.

On top of that, anything that gets worse breaks through immediately: the conflict moving
into the three-minute alarm band, severity rising, suggested manoeuvres appearing or
running out, the aircraft closing by more than a nautical mile, crossing two minutes,
one minute or thirty seconds to closest approach, or the probability jumping. There is
also a two-minute heartbeat so a long-running conflict is re-announced rather than
quietly ageing off the top of the list.

**Proved on real traffic, not asserted.** Two one-hour sessions were replayed twice,
once with the feed and once without, and the two sets of reported aircraft pairs were
compared:

| | before | after |
|---|---|---|
| aircraft pairs reported | 30 | **30** |
| pairs lost | — | **0** |
| interruptions | 360 | **131** |

**Nothing stopped being reported. Interruptions fell 64%.**

**An honest number, not the flattering one.** A pure count of encounters suggests a 90%
reduction is available. We got 64%, and the difference is the safety re-announcements
doing their job. Breaking down the 131 that remained: 65 crossed into a shorter time
band, 30 were genuinely new, 23 had closed by more than a mile, 12 escalated into the
alarm band, 1 got more severe, and **none** were the heartbeat. Every remaining
interruption is a real change. The 26 points we gave up are what the guarantee costs.

**The collapsed group, and the seven conflicts in it.** On the test data, 185 of the 740
alerts get grouped rather than given their own row — 178 false and **7 real**. That
sounds alarming, so here is exactly what happens to those seven. All seven are watch-list
entries with **six to nine minutes** before the aircraft are closest. All seven remain on
the active list the whole time. And as each closes inside three minutes it stops
qualifying for the group and becomes a full alarm — which is checked automatically, not
assumed. The controller sees every one of them, with more than three minutes in hand,
which is precisely what the headline metric measures.

The benefit: **39% of false alarms leave the prominent list, and the precision of what
remains prominent goes from 0.386 to 0.503.**

**Four things can never be collapsed**, whatever the model says: a three-minute alarm, a
pair the simple geometric rule calls a conflict, anything at high or critical severity,
and anything carrying suggested manoeuvres. The geometric rule outranking the model is
deliberate — it is the safety net, and it is not allowed to be overruled by a
probability.

**What is not done.** Nothing calls this yet. There is no web server to own it and the
dashboard still runs on mock data. When the API is built it adopts the feed in one line.
The dashboard's obligation is written at the top of the file: **draw the whole active
list.** If it ever draws only the interruptions, the guarantee is broken — not by this
module, but by the thing using it.

**Headline number:** unmoved at 94.0%. This runs after detection, so it cannot change
how many conflicts are found.

**Checks:** 87 to 110, all passing.

### 2026-09-07 — Tried the obvious fix for false alarms; it failed, and the reason is worth keeping

**File:** none changed. This is a rejected experiment, recorded so nobody spends a week
rediscovering it.

**The idea, which is genuinely good.** Nearly two thirds of our false alarms are pairs
that passed close side-to-side but stayed comfortably stacked in height — typically
about 2.4 miles apart horizontally and 1,930 feet apart vertically. That is ordinary,
legal, everyday traffic at different flight levels. So: if both aircraft are flying
level and there is already more than 1,000 feet between them, say nothing.

**It works, and it is not usable.** It removes **46% of false alarms** — and it also
throws away **21 real conflicts**. The headline number drops from **94.0% to 86.6%**.

**Why, and this is the part to tell a mentor.** Those 21 aircraft *were* flying level
when we looked. Then one of them started descending. Several were predicted to pass over
2,000 feet apart and actually ended up 240 to 530 feet apart. The descent came from a
controller instruction that we never see, because we only receive position reports, not
clearances.

**Real systems do exactly this filter — using data we do not have.** EUROCONTROL's
official guidance for short-term conflict alert lists it, and warns in the same sentence
that it "reduces warning time in the event of level bust" — an aircraft leaving a level
it was supposed to hold. Real systems get away with it because the flight data system
tells them what level each aircraft has been cleared to. We are guessing from whether
the aircraft happens to be climbing right now, and that is exactly the guess that fails.

This is a clean, defensible argument for the report: it is a concrete measurement of why
a production version would need flight-plan data, rather than a generic disclaimer.

**Headline number:** unmoved at 94.0%, because the filter was measured and rejected, not
applied.

### 2026-09-07 — Two documents: the full evaluation, and a briefing for the people presenting

**Files:** `evaluation.md` (new), `docs/figures/*.png` (13 new charts),
`docs/metrics.json` (new), `docs/Flight_Right_Speaker_Briefing.pdf` (new).

**Before.** The numbers existed, but scattered: some in this file's change log, some in
`ml_pipeline/reports/`, some only in a training log, some only recoverable by re-running a
script. There was no single place to look up how well anything works, and no chart of
anything. There was also nothing a non-technical teammate could read before speaking about
the project.

**Now, two documents with different jobs.**

`evaluation.md` is the technical record: every model's metrics beside the baseline it has
to beat, the confusion matrix for the conflict classifier, **the confusion matrix for what
actually reaches the controller's screen**, the rejected experiments with the numbers that
killed them, and thirteen charts. Every figure is generated from the saved model files
rather than typed in, so the document cannot drift away from the models. The raw values are
in `docs/metrics.json`.

`docs/Flight_Right_Speaker_Briefing.pdf` is fourteen pages for teammates who know what the
project is but write no code and know no aviation, and who have to stand up and talk about
it. It defines five aviation words, explains each model in plain language, and has three
sections aimed squarely at questions: what the controller actually sees (because "six in ten
warnings are false" sounds much worse than it is), a table of **what we said we would build
against what we built and the measurement that changed our minds**, and the failed
level-flight filter written up as a finding rather than a mistake. It also says which
sentences to use and which to avoid — "we catch 94% of conflicts with three minutes of
warning", never "our model is 94% accurate".

**Why.** Two different failures were possible. The technical one: numbers that only exist
in a terminal cannot be checked, compared between runs, or put in a report. The presentation
one: someone answering "so how accurate is it?" with "63.6%" would be quoting a best-of-five
figure as if it were accuracy, which is wrong and an examiner would catch it.

**One thing that had to be fixed while building it.** The first version of the alert-funnel
chart used a logarithmic scale, which made 303 real conflicts out of 4,690 pairs look like a
clear majority of the bar. It was replaced with two linear panels. A chart whose proportions
do not match its data is worse than no chart.

**Headline number:** unmoved at 94.0%. Nothing was trained, tuned or changed — this was
collecting and explaining what was already measured.

### 2026-09-08 — The screen finally shows what the models actually think

**Files:** `server/app/` (the whole backend, new), `client/src/lib/api.js`,
`client/src/lib/adapters.js`, `client/src/hooks/useLiveData.js`,
`client/src/hooks/useAuditLog.js`, `client/src/components/DataSourceBar.jsx`,
`client/src/components/WatchListPanel.jsx` (all new), plus `HomePage`, `ResolveModal`,
`FlightRadarMap`, `RadarCanvas`, `AIAuditTrail`, `TimelinePanel`, `TopBar`, `MetricsRow`.

**Before.** The dashboard was beautiful and it was entirely make-believe. Every aircraft on
it, every conflict, every suggested manoeuvre and every number was typed into a file called
`mockData.js`. Nothing on the screen had ever been produced by any of the four models. The
part that would connect them did not exist.

**The reason, which is worth knowing.** It is not that nobody ever built the connection. A
teammate built a working one in April. It was deliberately deleted on 30 August, as the
first step of a planned move from one kind of server to another. The replacement was never
written, so the project spent a week with the old bridge demolished and the new one
unstarted.

**Now.** There is a backend. It reads aircraft — either live from the internet or from the
twelve days of real Mumbai traffic we recorded — works out which pairs are heading for
trouble, asks all three models, decides what deserves an alarm and what is only worth
watching, works out what could be done about it, and writes every decision to a database.
The dashboard reads all of that over a live connection and draws it.

**What is now real that was invented before:**

| On screen | Before | Now |
|---|---|---|
| The aircraft | 12 made-up flights | 33–38 real ones, updating every ten seconds |
| The conflict alert | One fixed scenario | Whatever the models actually predict |
| The three suggested manoeuvres | Written by hand | Model 3, re-simulated for this pair |
| "ATCO match: 94% (847 cases)" | **Invented** — that model was never built | Gone. Replaced by the real ranking score |
| Sector metrics | On-time rate, "AI optimisation score", wind, visibility — none measured by anything | Aircraft tracked, en-route, alarms, watch list, pairs assessed and how long it took |
| The audit trail | Kept in the browser tab, erased on close | Server-side, append-only |
| The timeline | Invented runway slots | Predicted closest approaches |

**What is still fake, and now says so.** Runway occupancy, the weather overlay and the
radio transcript have no data source at all, so each is labelled on screen — "DEMO DATA",
"WEATHER (DEMO)", "VHF / DATALINK TRANSCRIPT (DEMO — NOT IMPLEMENTED)" — with a note under
the transcript explaining its callsigns will not match the live traffic. Labelling them is
the honest option; quietly leaving them looking real is not.

**A bar across the top now says where the data came from.** Live or recorded, which
recording, how many aircraft, how many pairs the models assessed and how long it took, how
many repeat alerts were suppressed, and — permanently — "PROTOTYPE · DECISION SUPPORT ·
CONTROLLER DECIDES". A dashboard that cannot say whether it is showing live traffic or a
recording can quietly present yesterday's aircraft as if they were outside the window.

**The button no longer claims something untrue.** It used to say APPLY RESOLUTION, next to
another that offered to transmit by datalink. The system cannot move an aircraft and is not
permitted to. It now says **ACCEPT — RECORD DECISION**, and that is exactly what it does:
writes the controller's decision to the audit log.

**Five bugs that only appeared once real data flowed.** Worth listing because every one of
them was invisible while the screen was showing made-up data:

1. The recorded sessions were being cut into snapshots on the wrong clock, producing
   moments containing anywhere between 1 and 166 aircraft instead of a steady 35.
2. **The system raised an alarm about two aircraft that had already left the area** — it
   kept their last known positions and kept using them. Now an aircraft has to be visible
   right now, not merely remembered.
3. When filling in an aircraft's recent past at startup, the code ran off the beginning of
   the recording and grabbed the end instead — an hour and a half away, different aircraft
   entirely.
4. The recording started playing while the models were still loading, so the interesting
   part had already gone past before anything was on screen.
5. **The map threw away every real aircraft.** It matched incoming flights against its own
   fixed list by callsign and silently dropped anything that did not match, which was all
   of them.

**Headline number:** unmoved at 94.0%. Not one model, threshold or setting was touched.
This connected what already existed. The automatic checks still pass, 110 of 110.

### 2026-09-08 - The record of decisions moved to a database that will not let anyone edit it

**Files:** `scripts/postgres.py` (new), `server/app/services/database.py` (new, replaces
`audit_service.py`), plus `config.py`, `main.py`, `api/routes.py`, `RUNNING.md`.

**Before.** Every decision a controller made was written to a small file-based database
called SQLite. That worked, and the file was only ever added to - but *only because the
code happened not to contain any instruction that would change or delete a past entry*.
Nothing stopped someone adding one later. The promise that the record could not be
rewritten was a promise about the code, not about the storage.

**Now.** The project runs its own PostgreSQL database. The important part is not the name
on it. It is that the application now connects with an account that has been given
permission to **add** rows to the decision log and **read** them, and no permission to
change or remove one. If the program tried, the database itself would say no.

You can watch it refuse:

```
[PASS] UPDATE on audit_logs is refused  --  permission denied for table audit_logs
[PASS] DELETE on audit_logs is refused  --  permission denied for table audit_logs
```

**Why this is the answer to give, rather than "Postgres is popular".** An examiner who
hears "we used Postgres because it is trending" will ask what it actually bought you.
The answer is now concrete: *a record of safety decisions that the system itself cannot
go back and alter.* That is a real property, it is demonstrable in one command, and it is
what an audit trail is for. The popularity of the tool is not part of the argument.

**Two smaller gains.** Dates are now stored as real dates rather than as text, so
"everything between 14:00 and 15:00" is a proper question. And the details attached to
each decision are stored as structured data rather than as a string, so they can be
searched.

**Where it lives, and why not where you asked.** You asked for it inside the virtual
environment. That is not possible - a virtual environment holds Python code, and
PostgreSQL is a separate program, not a Python package. What *is* possible, and what has
been done, is to make it self-contained: the official PostgreSQL files, unpacked by a
script, needing no installer and no administrator permission, and started and stopped by
that same script.

It sits in your local application folder rather than in the project folder, and that is
deliberate. **This project lives inside OneDrive.** A database constantly writes thousands
of small files, and OneDrive would try to upload them while they are being written -
which is slow and can corrupt the database. It is not a theoretical worry: creating the
database inside the project folder **had not finished after nearly seven minutes**; in the
local folder it took **seven seconds**.

**What happens if the database is not running.** The system falls back to the old
file-based storage automatically and *says so on screen*, including a flag stating that
the no-editing guarantee is not in force. It does not pretend. This is the same approach
used everywhere else in the project: simple arithmetic underneath the neural network, the
geometric rule underneath the classifier, recorded data underneath the live feed.

**Something else that is now saved.** Conflicts and the manoeuvres suggested for them are
written to the database too, so they survive a restart and can be reviewed afterwards.
Aircraft positions are not - there are about 300,000 a day and they can be recreated from
the recording, so storing them would be a lot of disk for no benefit.

**One live connection, not two - your choice, and the right one.** The original plan had
two separate live connections to the dashboard: one for aircraft positions, one for
alerts. The trouble is that an alert says "these two aircraft will be 4.2 miles apart in
30 seconds", and that sentence is only true about the positions it was worked out from.
With two connections there is no guarantee which arrives first, so the screen can show an
alert drawn against where the aircraft *used* to be. One connection carries both,
calculated in the same instant, so they cannot disagree.

**Three Windows problems that ate real time, written down so nobody repeats them.**

1. The setup script kept freezing with no error at all. The cause: PostgreSQL's tools
   start helper programs that inherit the pipes Python uses to read their output, and
   Python waits for those pipes to close - which one lingering helper never did. Six
   abandoned database processes were found holding them open. The fix was to write output
   to a file instead of a pipe, and to put a time limit on every call.
2. A second freeze was a password prompt nobody could see, waiting for an answer behind
   captured output.
3. A leftover database process blocks a new one from starting, with the message
   "pre-existing shared memory block is still in use".

**And one false alarm worth admitting.** Midway through, the conflict calculation appeared
to slow from 1.5 seconds to 22. It had not. A backend left running from eight hours
earlier still held the port, so every request was being answered by that old, stale copy.
A fresh one was back to 1.5 seconds. Before investigating a slowdown, check you are
talking to the program you think you are.

**Headline number:** unmoved at 94.0%. No model, setting or threshold was touched. This
changes where decisions are recorded and what stops them being altered.

### 2026-09-08 - The system was doing the same expensive calculation thirty times over

**Files:** `server/app/ml/inference.py`, `server/app/services/conflict_service.py`.

**The problem, and how it showed up.** Watching the running system, the time to check the
airspace crept up to **46 seconds**. New aircraft positions arrive every ten seconds, so
it was falling further behind on every single update - the screen would have drifted
minutes out of date. Nothing crashed. Every automated check still passed. It was only
visible by looking at the clock.

**What was actually happening.** One of the models - the one that predicts the five paths
an aircraft might take - is expensive to ask a question of. Not expensive per *aircraft*:
expensive **per question**. Asking it about one aircraft costs almost exactly as much as
asking it about forty, because internally it walks through all 12,000 of its decision
trees either way.

The code was asking it separately for every pair of aircraft. With thirty pairs, that is
thirty full trips through 12,000 trees to answer questions about sixty aircraft - most of
them the same aircraft, asked about again and again.

**The fix.** Ask once per update, about every aircraft at the same time, then hand the
answers out to whichever pairs need them. One trip instead of thirty.

| | before | after |
|---|---|---|
| a typical update | 24 seconds | **0.35 seconds** |
| a busy update with two alarms | 46 seconds | **1.7 seconds** |

About **130 times faster**, and it no longer gets worse the longer it runs.

**Nothing about the answers changed**, and that is the point: the model gives the same
result whether you ask about one aircraft or forty, so this changed only *when* the
arithmetic happens. Checked afterwards: the same two conflicts were found, with the same
severity and the same three suggested manoeuvres each. All 110 automated checks still
pass.

**Why no test caught it.** Every check in this project asks "is the answer right?" None of
them asked "did the answer arrive in time?" For a system that is supposed to warn a
controller three minutes before two aircraft get too close, an answer that takes 46
seconds to produce is not really an answer. That is worth remembering when writing the
next test.

**Headline number:** unmoved at 94.0%. No model or setting was changed.

### 2026-09-08 - Every model re-scored from its saved file, and two published numbers turned out to be wrong

**Files:** `ml_pipeline/utils/reevaluate_models.py` (new), `evaluation.md` (rewritten),
`ml_pipeline/utils/build_evaluation_figures.py`, `docs/figures/*.png`, `docs/metrics.json`.

**Before.** The numbers in `evaluation.md` came from the training run of 6 September. To
check whether they still described the model files actually sitting on disk, you had to
retrain everything - twenty minutes and a graphics card - because several of the figures
lived only inside training scripts, and a few others were typed into the chart-building
script by hand from a terminal window that no longer exists.

**Now.** One command, `python ml_pipeline/utils/reevaluate_models.py`, opens every saved
model in a fresh program that has no access to the training code, measures it again on the
held-out data, and writes every number to a dated JSON file. It trains nothing and changes
no setting. Five sections: the trajectory model against plain arithmetic, the multi-path
model's five-option hit rate and honesty check, the conflict classifier's full scorecard,
the suggestion engine run over all 41 alarms, and two hours of recorded Mumbai traffic
replayed with and without the alert feed.

**What it found: almost everything reproduced exactly.** The headline number, the recall,
the precision, the confusion matrix, the calibration figures, the best-of-five rate - all
identical to the recorded values, to every decimal place printed. That is the answer to
"can you reproduce your results", and it is now a command rather than a claim.

**Two published numbers did not survive, and both are corrected in `evaluation.md`.**

1. **The explanation of *why* the classifier beats the geometric rule was partly wrong.**
   The document said that on the conflicts the rule misses, the faster aircraft is climbing
   or descending at "a median 2.60 m/s against 0.33 m/s across all rows - eight times
   higher". Re-measured on the current test split, the median is **0.33 m/s in both
   groups**, because most aircraft in both groups are flying level, so a median cannot
   separate them. The effect is real but it is distributional, not a median shift:
   **44.4% of the missed pairs have an aircraft climbing or descending faster than 2.5 m/s,
   against 32.6% of all pairs.** The rest of the explanation stands and is if anything
   stronger: **all 36** of the rule's misses are vertical misses (it predicts a median
   2,534 ft gap where the real gap turns out to be 565 ft), and the model catches **21 of
   those 36** while the rule catches only **2** of the model's 17 misses.
2. **The alert-feed replay could not be reproduced as published.** The 7 September table
   reported 20 and 10 aircraft pairs with a 63-65% cut in interruptions. The script that
   produced it was never committed, so its pair pre-filter is unrecoverable. Re-run with
   the pre-filter **the backend actually ships** (within 60 NM and 5,000 ft), the same two
   sessions give 49 and 56 pairs and a **73.7% and 74.1%** cut. The two facts the table
   exists to prove reproduce identically either way: **zero pairs lost**, and the number of
   rows drawn on screen equalling the old message count exactly (680 and 909). The replay
   now lives in the committed script.

**Model 3's counts moved by one or two for the same reason** - the earlier sweep's geometry
reconstruction was not kept either. The new one is committed and self-checking: it rebuilds
each encounter's geometry from the row's own features and confirms the rebuild reproduces
that row's predicted closest approach to a median of **0.004 NM**, about seven metres.
Result: 41 alarms, 1,066 instructions simulated, 31 alarms with at least one workable
option, 10 with none, **76 offered** (was 77), split 38 real / 38 false (was 36 / 41), and
**2** instructions blocked for leaving the safe flight envelope (was 0).

**`evaluation.md` was rewritten so every number is explained beside it**, in language
aimed at someone who knows neither machine learning nor aviation: what recall and precision
actually count, why accuracy is banned here (a model that says "no conflict" to everything
scores 93.5%), what the four boxes of a confusion matrix mean, what a calibration error of
0.019 is measuring, why best-of-five is not accuracy, and why the sideways error overtaking
the along-track error at ten minutes is the number to worry about. Two charts were also
rebuilt: the calibration chart had been drawn from four hand-copied points and now uses all
eleven measured bands, and the interruptions chart had labels sitting on top of each other.

**Headline number: unmoved at 94.0%**, and that is the main result - re-measuring the
saved models from scratch returned the same figure. Nothing was trained, tuned or changed.

### 2026-09-21 - Phase 0: the published numbers now come from the files on disk, and three "contradictions" turned out to be three different models

**Files:** `ml_pipeline/training/trajectory/reference_benchmark.py`,
`ml_pipeline/utils/build_evaluation_figures.py`, `docs/evaluation.md`,
`docs/metrics.json`, `docs/figures/*.png`, `Flight_Right_ML_Approach.docx`.

This is Phase 0 of the v8 plan: make the ground true before measuring anything new. No
model, threshold, gate or hyperparameter was touched, and nothing was retrained.

**1. The tree reference was being typed in by hand.**

*Before.* `build_evaluation_figures.py` carried the non-neural tree's twelve numbers as a
dictionary written directly into the source code, copied off a training run's terminal
output:

```
GBT = {"1 min": (0.43, 90.8, 98.5), ... "10 min": (5.57, 33.1, 65.7)}
```

`reference_benchmark.py`, which produces those numbers, only printed them. It wrote no
file. So the single rule this project states most firmly - *no number is ever typed by
hand into a document* - was being broken inside the very file that enforces it.

*Now.* `reference_benchmark.py` scores the tree through `evaluate.evaluate()`, the same
audited function the neural model is scored by, and writes the full result to
`ml_pipeline/data/processed/eval_tree_reference.csv`. The figure builder reads that file
and refuses to run if it is missing.

*Why it matters, and the honest outcome.* Re-running the benchmark reproduced the old
printed table exactly, and the twelve hand-typed values were **correct to one decimal in
all twelve cases**. Nothing published was ever wrong. But nothing enforced it either, and
the next person to re-run the benchmark would have had no way of knowing the document had
stopped matching it. The only change in `metrics.json` is those twelve values gaining
their full precision; every other number in the file came back **bit-for-bit identical**,
including the classifier, the alert-feed replay and the Model 3 sweep.

**2. Three figures for the same metric, and none of them is a mistake.**

`docs/CLAUDE.md` reports the trajectory model's ten-minute within-5-NM rate as **60.9%**
in one place, **60.8%** in another and **61.3%** in `evaluation.md`. That looks like the
documents disagreeing. They do not. **They are three different model files**, and only one
still exists.

The evidence, rather than an assumption: `trajectory_residual.pt` on disk is stamped
6 September 14:02:25, which is *earlier* than the start of the 14:03:17 pipeline run,
because that run resumed from a training step that had already succeeded and saved its
model before crashing on shutdown. The `multipath.log` written by that same run, reading
that same file, prints `single-answer residual LSTM  34.8%  61.3%`. Re-scoring the file
today returns 34.8 / 61.3 again. So 61.3% is the model the system actually runs; 60.9% was
the 5 September model and 60.8% a 6 September morning re-run, both long overwritten.

`CLAUDE.md` explains the 60.8-versus-60.9 gap as graphics-card rounding, which is correct,
but it never mentions the further step to 61.3 - because it never recorded evaluating the
model it shipped.

*What was done about it.* A new section, **"Which number belongs to which model file"**,
at the top of `docs/evaluation.md`, with the table above and the evidence for it. The
dated entries in this file were **left exactly as written**. They are a historical record
of what was measured on the day, and editing them to match today's artifact would destroy
the evidence trail and claim a run produced a number it did not. The same applies to "36
raw parquets" in the 5 September entry against the 35 on disk: the 6 September entry is
already the correction.

**From here on, `docs/evaluation.md` and `docs/metrics.json` are authoritative and
everything else quotes them.** Where this file and those disagree, those win.

**3. `Flight_Right_ML_Approach.docx` was a run and a half out of date.**

It was written against an 18-session dataset that has since roughly doubled, and it had
never been refreshed. Corrected, every value read from `metrics.json` or measured directly
in this session:

| It said | It now says |
|---|---|
| 18 sessions, 329,647 reports, 198,537 examples | 35 sessions over 9 days, **627,344** reports from **1,730** aircraft, **291,008** examples |
| accuracy table 99.93 / 91.49 / 79.28 / 51.82 vs 99.96 / 93.51 / 84.92 / 64.47 | **98.43 / 89.46 / 77.33 / 50.50** vs **98.46 / 91.96 / 82.90 / 61.31** |
| average error "from 11.02 to 6.41 NM" | **10.30 to 6.41 NM** |
| arrivals: straight line **1.4%**, our model **30%** | **15.8%** and **34.8%** |
| "five options from 60 route patterns reaches 69.3%" | the shipped build is **40 patterns, 63.6% best-of-five, 38.6% top-1** |
| "measured on 273,794 pairs", then a table of 99 / 93 / 82 / 69% | the one real operating point: **94.0% caught with three minutes of warning, 94.4% of all conflicts, 38.6% precision, 96.8 false alarms per 1,000**, with both rule-based detectors beside it |

The **1.4%** line was the worst single error in the document: it understated the
straight-line baseline by a factor of eleven, which made our own model look far better
than it is.

The sweep table of 8 / 25 / 60 / 150 route patterns was **kept**, because it is a real
experiment recorded in `multipath.py` - it is how the 25-to-60 range was chosen. What was
wrong was the sentence after it, which read as though 60 patterns were the configuration
and 69.3% the result. It now says 40 is shipped and gives the shipped measurement.

The alert-volume sweep table was also kept, and relabelled as what it is: the geometric
rule on its own, swept to choose the 8 NM / 1,500 ft alarm zone, **not** the performance of
the shipped system.

**4. Two results that do not flatter us are now in the document rather than only in this
one.** The `.docx` is what gets read by people who will never open `CLAUDE.md`, and it
omitted both of these:

- A plain non-neural tree on identical inputs and targets **beats the neural model at ten
  minutes, 65.7% against 61.3%** - a 4.4-point lead, on every split measured so far. The
  document now says so, and says we therefore do not call the neural model our best.
- At ten minutes the neural model is **worse than plain arithmetic at getting a prediction
  almost exactly right**: within 1 NM it manages 24.7% against the baseline's 29.0%, and
  the tree's 33.1%. It pulls the whole error distribution inward, which is why its average
  and its within-5-NM rate are much better, but it pays for that by nudging some
  already-near-perfect predictions off target. Both are true at once.

Burying either is the only way they become a problem in a review.

**5. The environment for the voice work is installed.** `transformers`, `faster-whisper`,
`ctranslate2`, `librosa`, `soundfile`, `jiwer`, `rapidfuzz` and `pyopensky`, all importing.

This was the step most likely to break the project, because installing a second large
machine-learning stack next to the training one usually drags `numpy` or `torch` to a
different version and quietly breaks everything already working. It was checked before
installing rather than after: a resolver dry run reported **53 new packages and zero
changes to anything already present**. After installing, `verify_pipeline.py` still passes
110 of 110 and the graphics card is still visible to both stacks. The plan's fallback of a
separate Python 3.11 environment for voice was therefore **not needed**, which also means
the speech model can be loaded by the backend directly instead of living behind a second
process.

`ctranslate2` sees the GPU and supports `int8` and `int8_float16`, which is what the
quantisation step of the voice phase depends on.

**Still open, and not something this session can close:** the stale copy of `README.md`
held in the Claude project knowledge base. The repository's own `README.md` was checked
and is clean - it carries none of the stale figures - and no second copy exists anywhere in
the repository. The stale copy lives outside it and has to be replaced or deleted by hand.

**6. One more document was quoting the wrong model, found by sweeping for it rather than
by being told.** `docs/PROJECT_STATUS.md` is a live status document, not a dated log, and
its whole trajectory section still carried the 5 September model: 92.1 / 83.2 / 60.9% where
the shipped model measures 92.0 / 82.9 / 61.3%, the within-1-NM regression as 25.2% rather
than 24.7%, the four per-regime figures from the old run, and 35.8% for arrivals instead of
34.8%. All corrected, every value read from `metrics.json` or the re-score report. The
dated entries in this file were again left alone; the distinction throughout is that a
**status** document must describe the system as it is today, while a **log** entry must
keep saying what was true on its own date.

**Headline number: unmoved at 94.0%.** Nothing was trained and no threshold moved. The
full re-score from the saved model files was run again at the end of this work and returned
a result **byte-for-byte identical** to the run made before any of it started, which is the
point: these were changes to what the documents say, not to what the system does.

### 2026-09-22 — Phase 1: the system that runs is now the system these documents describe

**Files:** `ml_pipeline/utils/cpa_conflict_detection.py`, `server/app/ml/inference.py`,
`server/app/services/conflict_service.py`,
`ml_pipeline/training/trajectory/preprocess_sequences.py`,
`ml_pipeline/utils/reevaluate_models.py`, `client/src/components/NLPCommsPanel.jsx`.

Four defects where the code did something other than what this file says it does. None of
them was a crash, and no test caught any of them. They were found by driving the running
system and comparing what it did against what it was supposed to do.

---

#### 1.1 — The model the headline is measured on now actually decides something

**Before.** To decide whether to raise an alarm, the system asked one question: *are these
two aircraft predicted to come within 8 nautical miles and 1,500 feet of each other?* That
is geometry. The XGBoost conflict classifier — the model the entire 94.0% headline is
measured on — was calculated, shown on screen, and then **ignored by the decision that
matters**.

The consequence was visible on the running system. Two alarms fired on aircraft that were
1,100 ft and 1,068 ft apart vertically. Both were legally separated, ordinary traffic. The
classifier scored them at 0.35% and 0.41% — it was confident there was no conflict, and
nobody asked it.

**Now.** The decision runs through three routes, in strict priority order:

1. **The geometric safety net.** If the pair is predicted to breach the legal minimum of
   5 NM and 1,000 ft, an alarm is raised whatever any model says. A model never overrules
   the deterministic rule (Section 13).
2. **The classifier**, when it has given a verdict on that pair.
3. **The old probability route**, unchanged, for when no classifier verdict is attached —
   so the rule-only path and every existing test behave exactly as they did before.

**A trap that would have destroyed the project's headline number, caught by measuring
before implementing.** The instruction was to compare the classifier's probability against
the existing tier thresholds, 0.85 and 0.60. That sounds obviously right and it is
completely wrong. Those two thresholds belong to a *different number* — the multi-path
model's joint probability. The classifier's own conflict line, after calibration, sits at
**0.0285**, roughly thirty times lower. Measured on the held-out test data before changing
anything: comparing the classifier against 0.85 would have dropped the conflicts caught
from **94.4% to 18.8%**, and the headline metric from **94.0% to 19.0%**. The classifier
carries its own threshold, and that is the one now used.

**What it changed, measured on the held-out test split.** Two different things are counted
here and they must not be confused:

| | conflicts caught | of those with at least 3 min warning | tier 1 alarms | tier 1 false |
|---|---|---|---|---|
| geometry only (before) | 0.8812 | 87.3% (248 of 284) | 51 | 24 |
| classifier-gated (now) | **0.9505** | **94.7%** (269 of 284) | **41** | **14** |

**Tier 1 — the audible alarm that also carries suggested manoeuvres — strictly improves.**
The same 27 real conflicts are caught, and the false alarms beside them fall from 24 to 14.
That is ten fewer interruptions for conflicts that were never going to happen, with nothing
real given up.

**Something got worse and must not be buried.** Total alerts rise from 613 to 762 and
overall precision falls from 0.436 to 0.378. All of that is in **tier 2, the silent watch
list**: its false rows rise from 322 to 460, while its real ones rise from 240 to 261. So
the system now watches 21 more genuine conflicts at the cost of 138 more watch-list rows
that come to nothing. That trade is defensible — tier 2 makes no sound and suggests no
manoeuvre, and the alert feed built on 7 September exists precisely to group low-confidence
watch-list rows — but it is a real cost and it is stated rather than averaged away.

**The recall floor, stated precisely so this does not read as a gate being massaged.**
The *system's* recall is now 0.9505, which is above the 0.95 floor. **GATE 1 has not been
passed and was not touched.** Gate 1 is defined on the classifier measured *in isolation*,
and that number is unchanged at **0.9439**, still short of 0.95, for exactly the reason
diagnosed on 5 September. Two different measurements; only one of them clears the floor,
and it is not the one the gate is about.

#### 1.2 — The check that stops a fix causing a new conflict was switched off in production

**Before.** On 7 September the system learned to check a suggested manoeuvre against all
the other aircraft nearby, so that a fix which would fly one aircraft into a third one gets
rejected. It worked — inside the test suite. In the running system the list of nearby
aircraft **was never passed in**, so the check ran against an empty list every time. It had
been dead in production since the day it was written.

**Now.** The backend assembles the surrounding traffic and passes it in. The proof is in
what the system says about its own reasoning: on a real replayed alarm the description goes
from *"the other aircraft's 5 predicted paths"* to *"the other aircraft's 5 predicted paths
**and 1 other aircraft nearby**"*.

**What it costs, measured rather than assumed**, on a replayed session of 44 aircraft and
36 assessed pairs: the median update goes from **0.34 s to 0.35 s**, against a ten-second
budget. Two things keep it that cheap. Neighbours are only assembled when a manoeuvre is
actually going to be proposed — for a silent watch-list pair the engine ignores them
anyway, so building them would be pure waste. And each aircraft's predicted paths are
reused from the single batched call already made for the whole airspace. Asking the
multi-path model once per neighbour per pair instead — which is the obvious way to write
this — is the same mistake that made a 30-pair update take 46 seconds before 8 September,
multiplied by the number of neighbours.

#### 1.3 — The callsign now survives preprocessing

**Before.** The step that turns raw position reports into training examples required eight
columns and threw away everything else, including the callsign — despite it being present
on 100% of rows.

**Now.** It is kept, following the pattern already used for vertical rate: not in the
hard-required list, with a documented fallback, because one missing value should not
discard an otherwise good flight track. **At this stage it is a join key, not something any
model learns from.** It is needed later, to match a callsign heard on the radio against the
aircraft actually flying in the area.

**Nothing needs retraining, and this was checked rather than assumed.** Preprocessing was
re-run from the raw data and the resulting arrays — the inputs, the targets, the validity
mask and the timestamps — came back **bit-for-bit identical**.

#### 1.4 — The button no longer claims to have transmitted a clearance

**Before.** The radio panel's button read `APPROVE & TRANSMIT VIA DATALINK`, the pop-up said
"Datalink clearance transmitted", and afterwards it read `TRANSMITTED`. The system cannot
send anything to an aircraft and is not permitted to. The panel header did say
"(DEMO — NOT IMPLEMENTED)", but a disclaimer at the top of a panel is not what a reviewer
remembers about a button that says it transmitted a clearance.

**Now.** `APPROVE — RECORD DECISION (DEMO)`, "Decision recorded. Nothing transmitted.", and
`RECORDED` — matching the wording the resolution dialog already used. Text only.

---

**Why the reported headline number did not move, and what did.** The published **94.0% is
unchanged**, because it scores the classifier on its own, and 1.1 changed nothing about the
classifier — not a weight, not a threshold, not a gate. What moved is a number that was
never being reported: what the *running system* actually catches, which went from **87.3%
to 94.7%**. The gap between those two figures was the defect. `docs/evaluation.md` now
carries both, labelled, so the gap cannot silently reopen.

**Verification.** `verify_pipeline.py` 110 of 110, the 8 unit tests, and
`inference_check.py` all pass. `reevaluate_models.py` was re-run end to end, and the
comparison against the previous run is the strongest evidence here: of every value in the
report, **the only ones that differ are the 32 newly added ones**. Every previously
published number came back byte-for-byte identical. New report:
`ml_pipeline/reports/reevaluation_20260922_042850.json`.

### 2026-09-22 — Phase 2: five questions asked before building on their answers, and three came back as limits

**Files:** `scripts/check_trino.py` (new), `ml_pipeline/voice/check_corpora.py` (new),
`docs/phase2_findings.md` (new). No model, threshold, gate or hyperparameter was touched
and nothing was retrained.

**Why this phase exists.** Each of these five questions takes minutes to answer and each
one changes what a later phase is allowed to do. Answering them first is cheaper than
discovering the answer halfway through building on the opposite assumption. Three came back
as hard limits, which is exactly the outcome that justifies asking early.

#### 2.1 — The OpenSky historical archive is not open to us

**What we hoped.** Years of history instead of our twelve days, and a way to test whether
Indian airspace is covered at low altitude.

**What we found.** The account authenticates perfectly — a valid token comes back — and is
then refused permission to run **any** query. Not a query we wrote wrongly: `SELECT 1`,
which touches no table at all and has nothing to filter, is refused with the same
`PERMISSION_DENIED`. That single probe eliminates the two cheap explanations (a missing
partition filter, a mistyped table) and leaves only one: the account has no query
permission.

**A distinction that explains why the credentials we already had were never going to
work.** We hold three `clientId`/`clientSecret` pairs, and they are **REST API** credentials
for polling live positions. The archive authenticates against the OpenSky **website account
username and password** instead. Holding one says nothing about having the other.

**What it costs:** question 2.3 could not run. **What it does not cost:** anything in
Phase 3, which was always planned to train on the data we already hold.

#### 2.2 — There is no table of selected altitudes, and that is permanent

**What this is about.** An aircraft can broadcast the altitude its crew has dialled in —
where it is *going*, rather than where it is. That would be the single most useful thing we
could add to conflict detection, because our biggest weakness is not knowing that a level
aircraft is about to descend.

**The answer is no, with a near miss that is worth understanding.** The archive has a
column called `supportstargetstatereport`. That records **which aircraft are capable of
broadcasting** that message. It does not record **what they broadcast**. So the archive can
tell you an aircraft could have told you its intended altitude, and cannot tell you what it
was.

**This closes a question that had been open and optimistic.** An earlier project document
listed selected altitude as *"Unverified — test once Trino access arrives"* and called it
possibly "the biggest conflict-detection improvement available". It is not available. It
also explains the failed level-flight filter from 7 September: that filter needed a cleared
level, we substituted observed vertical rate, and it cost 21 real conflicts. The archive
could not have rescued it.

**Honest caveat:** this is read from the client library's schema, which mirrors the server,
not from a live listing — because 2.1 refuses one. The script re-checks directly and
records `verified_directly` the moment permission arrives.

#### 2.3 — Not run, and not blocking

Both coverage tests are queries through Trino. Written, unchanged, waiting.

#### 2.4 — The speech test set has no labels, but its filenames do

Phase 6 turns a radio transcript into *which aircraft, what action, what value*, and has to
be scored against something. The public test set turns out to carry **only audio and a
transcript** — 871 clips, 59.2 minutes, six columns, none of them callsign, action or
value. Confirmed rather than assumed.

**Two things the plan did not know, both found by parsing the filenames**, all 871 of which
turn out to encode the airport, the radio frequency and the date.

1. **The corpus is not purely European.** 102 of the 871 clips — nearly 12% — are from
   **Sydney**. The plan states the clips are European and Phase 5 leans on that. The
   argument survives, because there is still no South Asian audio anywhere in it, but the
   sentence needs fixing before anyone says it in a review.
2. **There are 93 distinct recordings**, and that is genuinely useful. Phase 6 needs a list
   of "aircraft that might plausibly be the one being spoken to". Grouping by recording
   gives one: the callsigns heard in neighbouring transmissions on the same frequency, the
   same day, at the same airport. It has to be labelled as a stand-in rather than a real
   radar feed, but it can now be built without the official annotations — which is just as
   well, since `atco2.org` fails certificate verification from this machine.

#### 2.5 — An eighth of the public test set is the same audio the model trained on

**The question.** The speech model we intend to ship reports 22.27% word error rate on its
card, without naming what it was measured on. Its training corpus has no test split. So:
are the 871 evaluation clips inside the data it learned from? If they are, that 22.27 is
the model being marked on homework it had already seen.

**The answer is 12.5% — and getting there required not trusting the obvious method.**

| How you check | Answer | Why it is wrong |
|---|---|---|
| Do the transcripts match? | 27.7% | **Too high.** "Roger" and "good bye" recur everywhere, said by different people |
| Do the audio files match byte for byte? | 0.1% | **Too low.** Re-saving a file changes every byte without changing the sound |
| **Do the decoded sound waves match?** | **12.5%** | **Right.** A correlation of 1.000 is the same recording |

The two wrong methods are wrong in *opposite directions*, by factors of two and a hundred.
Either one alone would have produced a confident and false conclusion.

The breakdown shows why. Of transcripts 1–5 words long that matched, **none** was the same
recording. Of those 10 words or longer, **108 of 202 were**. Two controllers do not
coincidentally both say "oscar kilo bravo alfa lima request shortcut to vlasim if possible".

**What follows, and it is better than the plan expected.** The plan assumed high overlap
would leave only one usable model. It does not: **762 of the 871 clips are clean**, the 109
contaminated ones are listed by name in the report, so Phase 4 can simply exclude them and
measure a genuinely held-out result on the rest. What is now forbidden is quoting the
card's 22.27, or any figure over the full 871, as though it were held out.

**This is publishable on its own.** A publicly available air-traffic speech model reports an
accuracy figure without naming its test set, and an eighth of the obvious public test set
for it sits inside its own training data. As far as we can tell nobody has checked. The
check is waveform correlation and it reproduces from one committed script.

---

**Headline number: unmoved at 94.0%.** Nothing was trained, tuned or changed. This phase
only established what data exists.

**One risk avoided, worth recording because it nearly happened.** The obvious way to read
these datasets is the `datasets` package. Checked before installing, as Phase 0 established:
it requires `fsspec<=2026.6.0`, this environment runs 2026.7.0, and **torch depends on
fsspec** — installing it would have downgraded a package underneath the working training
stack to answer a question about speech data. `huggingface_hub`, already present, reads the
same files. **Nothing was installed.**

**Cross-verification after Phase 2, and one machine-level problem found by it.**
`verify_pipeline.py` 110 of 110, the 8 unit tests and `inference_check.py` all pass. The
full re-score was run again and compared key by key against the run made before Phase 2
started: **669 keys compared, 0 differ.** Both Phase 2 scripts reproduce their own output
identically on a second run.

**The GPU is no longer visible to this machine, and it is not something Phase 2 did.**
`torch.cuda.is_available()` returned True at the start of the session and False at the end,
with `nvidia-smi` reporting *"NVIDIA-SMI has failed because you do not have sufficient
permissions"*. Checked before blaming anything: **no package was installed** — `fsspec` is
still 2026.7.0, `torch` is still 2.13.0+cu126, `datasets` is still absent — and the fault
persists outside the sandbox, so it is at the driver or power-management level rather than
in the Python environment. This machine already has a recorded history of CUDA teardown
failures (see 6 Sep, exit code `0xC0000409` at interpreter shutdown), and many short-lived
CUDA processes were started during this session.

**What it does and does not block.** It does **not** affect anything measured here: the
full re-score ran on CPU and returned byte-identical numbers, which incidentally proves the
published figures do not depend on the GPU. It **does** block Phase 3, which retrains. Try a
reboot before investigating further.

**RESOLVED, 23 September, without intervention.** The GPU came back on its own: CUDA
available, `NVIDIA GeForce RTX 4050 Laptop GPU`, 5.3 GB of 6.4 GB free, and an actual
matrix multiply on the device succeeds. Nothing was reinstalled or reconfigured in between,
which fits the transient driver or power-management explanation and rules out the Python
environment for good. **Phase 3 is not blocked.** Worth remembering the shape of it: an
apparent environment catastrophe that needed no action, diagnosed correctly at the time by
checking that no package had changed rather than by assuming the last thing done caused it.

### 2026-09-23 — Trino access granted: the archive is open, and Indian low-altitude coverage turns out to start in January 2025

**Files:** `scripts/check_trino.py` (2.3 rewritten to sample rather than exhaust),
`scripts/download_archive.py` (new), `docs/phase2_findings.md`, `docs/CLAUDE.md`.
New data in `ml_pipeline/data/archive/`. **No model, threshold, gate or hyperparameter was
touched and nothing was retrained.**

**What changed since yesterday.** OpenSky applied the query permission to the account. The
same username and password that were refused on 22 September are accepted on 23 September,
with no change to the script or the credentials — which confirms yesterday's diagnosis was
right and the problem was never anything fixable from here.

#### 2.1 and 2.2 — resolved

Every probe passes. `SHOW TABLES` returns 14 tables and **still no target-state table**, so
the selected-altitude finding is now *verified directly against the live server* rather
than inferred from the client library. It also turned up three tables the library does not
declare — none of them carries a target state either. Selected altitude stays permanently
out of scope.

#### 2.3 — the finding that matters, and it is the exact trap the plan warned about

**The question was not "does the archive have Indian data". It was "does it have Indian
data low down".** Aircraft at cruise are easy for us to predict; the arrivals and
departures below 10,000 ft near Mumbai are our weakest regime, and receiving them needs an
antenna near the airport rather than anywhere in the region.

**Sampling three hours in each of the last 36 months** — a whole month cannot be queried,
it is of order 126 million rows and the server refuses it:

| | Months sampled | Months with data |
|---|---|---|
| Anything in the Mumbai box | 36 | **29** |
| Below 10,000 ft near the airport | 36 | **20** |

**Nine months carry cruise traffic over Mumbai and exactly zero traffic near the airport.**
March 2024 is the clearest: **188,407 position reports from 196 aircraft in the box, and
0 below 10,000 ft near VABB.** Not thin. Empty.

Then in January 2025 it switches on — 4 aircraft that month, and from February 2025
onward every sampled month is healthy, a median of 128 distinct aircraft below 10,000 ft
per three sampled hours. Somebody put a receiver near Mumbai at the turn of 2025.

**Why this needed asking before building.** Anyone checking only "is there Indian data"
would have found three years of it and built a training set silently missing every arrival
before 2025 — biasing the model back toward the easy cruise case, which is the same bias
the per-horizon mask exists to prevent. **Usable window: February 2025 to September 2026.**

**It is also a publishable measurement.** OpenSky's own coverage reporting calls South Asia
"still improving" without putting numbers on it. This dates the arrival of Indian
low-altitude coverage to within a month.

#### What was downloaded, and where it deliberately did not go

One archive day, airborne and model-usable at 10-second sampling, is **203,849 rows from
590 aircraft**. The entire existing dataset — twelve days of polling across 35 sessions —
is 627,344 states. So **three days of archive is the whole collection effort to date.**

`scripts/download_archive.py` pulls days down in the poller's own column names, so the
files are drop-in comparable with the recorded sessions. Two days per month across the
usable window were taken:

| | |
|---|---|
| days downloaded | **38 usable** (one more, 20 Apr 2026, came back with 6 rows) |
| span | 9 Feb 2025 → 20 Sep 2026 |
| total rows | **7,969,128** |
| median per day | 209,569 rows from 792 aircraft |
| below 10,000 ft | **20.0%** of rows |
| on disk / time taken | 243 MB / 23 minutes |

**That is 12.7× the existing dataset**, and the 20% below 10,000 ft is terminal traffic the
polled sessions are thin on. The empty April 2026 day is not a bug in the downloader — it
is the same gap the coverage sweep found independently in that month.

**It writes to `ml_pipeline/data/archive/`, and not to `ml_pipeline/data/raw/`. That is
the single most important line in this entry.** `preprocess_sequences.py` globs
`raw/*.parquet` and concatenates whatever it finds. A download dropped in there would have
silently changed the dataset underneath every number this project has ever published, with
nothing in the output to say it had happened. Adopting the archive is a separate,
deliberate, logged step, and Phase 3 must train on the existing sessions **first** so there
is something to compare against.

**Quality checked rather than assumed**, on a downloaded day: zero nulls in any column the
model requires, callsign present on 98.3% of rows, median gap between consecutive states
exactly 10 seconds, 590 of 627 aircraft carrying the 10 states the model needs — and
**26.7% of rows below 10,000 ft**, which is the terminal traffic the existing dataset is
thin on.

#### The archive is worth more per row than our own data, and that is an uncomfortable finding

The real preprocessing script was run against **three archive days alone**, in a throwaway
data root so nothing real was touched:

| | Airborne states | Training samples | 10-minute target valid |
|---|---|---|---|
| Entire existing dataset (35 sessions, 12 days) | 627,344 | 291,008 | **49.9%** |
| **Three archive days** | 642,945 | **568,867** | **61.2%** |

From a similar number of raw position reports, three days of archive yield **nearly twice
the training examples** of the whole collection effort. The cause is structural and
measurable: an archive day is 24 hours continuous, so the median aircraft track runs
**180.8 minutes**; a 90-minute polling session can never see more than 90 minutes of any
aircraft, and most enter or leave part-way through, so its median track is **19.1
minutes**.

A training example needs ten past positions *and* a real position at the target horizon.
Truncated tracks cost examples, and they cost them hardest at ten minutes — which is
precisely where the model is weakest and the data thinnest.

**Said plainly: the 90-minute collection window was itself capping the dataset,
independently of how many days were collected.** More sessions would have kept hitting the
same ceiling. This is worth saying out loud rather than quietly switching data sources.

#### 2.4 also resolved, and the blocker was ours rather than theirs

Phase 6 has to turn a radio transcript into *which aircraft, what action, what value*, and
needs labelled examples to be scored against. Yesterday's conclusion was that the public
dataset carries none, the official release could not be reached, and so 100–150 clips would
have to be labelled by hand.

**All of that was wrong, and for an embarrassing reason.** The official release page
`atco2.org/data` was recorded as unreachable because it failed certificate verification.
The certificate was fine. **Windows' default trust store was the problem.** Retried against
the `certifi` bundle — the one every Python HTTP library ships with — the page loads
instantly and offers a **50 KB file, free, no registration**, containing the annotations
for exactly the 871 clips in question.

They are better than what we would have produced by hand:

| | |
|---|---|
| annotated segments | **877** (one per clip) |
| with a callsign label | **786** |
| with an action and a value | **639** |
| with all three | **497** |
| **with the real aircraft identity of the pilot speaking** | **246** |

That last row matters most. Phase 6's actual contribution is matching a *heard* callsign to
a *real* aircraft, and the annotations name the real aircraft — `OK-PMB`, `RYR73AH` — so
that can be scored against truth instead of against a proxy.

**One caveat, recorded rather than glossed:** every segment is flagged as having a verified
transcript, but only 2 of 877 are flagged as having verified *tagging*. These should be
described as the corpus authors' annotations, not as doubly-checked gold labels. They are
still incomparably better than a few hundred clips labelled by us, and they cover the whole
set rather than a sample.

**Consequence: hand-labelling leaves the Phase 6 critical path**, and so does the "state
the sample size" caveat that would otherwise have attached to every extraction figure.

**The transferable lesson:** "the website is down" is a diagnosis, and it deserved the same
scepticism as any other. Two separate sessions repeated it without testing it.

#### A second door, recorded but not walked through

`flights_data4` carries `estdepartureairport`, `estarrivalairport` and the full track per
flight — **336 flights arriving at Mumbai on a single day**, tracks up to 2,400 points. That
is ground-truth destination, which an earlier project document listed as a pending
"Route A". It makes plan item 9.2 — how accurate callsign-to-route lookups are over India,
a figure nobody has published — measurable rather than aspirational. Not built. Recorded as
now possible.

**Headline number: unmoved at 94.0%.** Nothing was trained or tuned. This entry is about
what data exists.

**Cross-verification after the archive download.** `verify_pipeline.py` 110 of 110, the 8
unit tests and `inference_check.py` all pass. The full re-score was run again and compared
key by key against the run made before any of this work started: **669 keys compared, 0
differ.** `ml_pipeline/data/raw/` still holds exactly its 35 session files, which is the
check that matters most here — the 243 MB of new data went where it was supposed to go and
nothing downstream can have moved because of it. `fsspec` is still 2026.7.0 and `datasets`
is still absent.

### 2026-09-23 — Phase 2 verified, and Phase 3.1: each aircraft now gets its own predicted offset

**Files:** `ml_pipeline/training/trajectory/multipath.py`, `server/app/ml/inference.py`,
`ml_pipeline/utils/reevaluate_models.py`, `server/app/ml/saved_models/trajectory_multipath.pkl`
(retrained). Report: `ml_pipeline/reports/reevaluation_20260923_095646.json`.

**Phase 2 checked before building on it.** The raw folder still holds exactly the 35
session files (the other entries are logs, a CSV and a placeholder, none of which the
preprocessing reads). The archive holds 39 files, 7,969,128 rows, 38 usable days, 20.2%
below 10,000 ft, the same columns as our own sessions and no missing values in anything
the model needs. Every automated check passed and the full re-score matched the previous
one on all 669 values. Everything recorded for Phase 2 is true.

**What it was before.** The multi-path model (the one that offers five possible futures
for each aircraft) first decides which of 40 typical routes an aircraft is probably on —
call them patterns. Then it moved the aircraft by that pattern's *average* offset. Every
aircraft on pattern 17 got exactly the same correction, whatever its speed or position.
That design has a hard limit: even if the pattern were always guessed right, arrivals
could never be predicted better than 74.7% of the time within 5 nautical miles at ten
minutes.

**What it is now.** The pattern is still chosen the same way, by the same model. But the
offset is now *predicted for this aircraft*, by a set of tree models that are told which
pattern it is on and also see its own recent motion. Same pattern, different aircraft,
different correction.

**Why, and the measurement.** It was tested first as a separate experiment, then built in,
and both runs gave the same numbers. Arrivals ten minutes ahead, within 5 NM:

| | before | after |
|---|---|---|
| one of the five candidate paths is right | 63.6% | **71.5%** |
| the single most likely path is right | 38.6% | **44.2%** |

Across all aircraft the single most likely path is now within 1 NM at ten minutes 38.4% of
the time, against 29.0% for a straight line. That fixes a weakness recorded since
2 September: the old neural model was *worse* than a straight line at near-perfect
predictions. The five paths are still as spread out as before, so the model has not
quietly collapsed into offering the same answer five times.

**What had to be avoided.** The tree models learn from where each aircraft *actually*
went, but in use the pattern is a guess and sometimes wrong. So every number above is
measured with the guessed pattern. The figure using the true pattern (81.0%) is printed
as a ceiling and must never be quoted as a result.

**What is deliberately NOT switched on.** These paths feed the probability that decides
whether a pair goes on the watch list. Changing them changes when a controller is
alerted, and that needs Archit's decision. The model file therefore carries both the old
average table and the new models, and the running backend still uses the old table unless
`FLIGHT_RIGHT_MULTIPATH_OFFSETS=per_mode` is set. An old model file cannot be asked for the
new mode by mistake: the backend refuses rather than quietly using the table. The new mode
costs about 0.3 seconds per update for 40 aircraft, against a ten-second budget; a full
replay timing is still owed before it is switched on.

**Also still owed.** This is one training run. Phase 3.3 repeats it with three different
random seeds (starting settings) before any of these numbers is published as final.

**Did the headline number move?** No — **94.0% unchanged**, and the runtime figure is
unchanged at 94.7%. The headline measures the conflict classifier, which was not touched,
and the backend is still serving the old paths. The re-score changed nothing among its
669 earlier values; it only gained the 29 new per-mode values.

### 2026-09-23 — Timed the new path model on real replayed traffic: fast enough, but it changes the watch list

**Files:** `ml_pipeline/utils/replay_timing.py` (new). No model, threshold or setting changed.

**Before.** The new per-aircraft path model (Phase 3.1, entry above) had only been timed on
one batch of 40 aircraft: about 0.3 seconds. That is not the same as timing the whole
system, which also checks every nearby pair and works out suggested manoeuvres.

**Now.** A script replays two complete recorded sessions — about 90 minutes and 520
ten-second updates each, up to 52 aircraft and 70 pairs at once — through the real backend
code, once with the old paths and once with the new, on exactly the same frames.

**Result.** A typical update takes **0.56–0.58 seconds** with the new paths against
0.26–0.33 with the old. The slowest single update in over a thousand took **2.07 seconds**.
New positions arrive every **10 seconds**, so not one update came close. Speed is not a
reason to hold back.

**Something the timing run also showed.** Switching changes which aircraft pairs appear on
the watch list — more watch-list entries (55 to 91 and 82 to 101 over the two sessions) and
partly different pairs. In one session one extra pair went on to reach the alarm tier for
two updates, because it had first been picked up on the watch list. A replay cannot say
whether those changes are right or wrong, because it has no record of what happened next.
The next step (Phase 3.2) measures exactly that on labelled data.

**Did the headline number move?** No — **94.0% unchanged**; nothing was switched on.

### 2026-09-23 — The autopilot's "target height" was written off too early: it is available, just not from OpenSky

**Files:** `Claude outputs/Flight_Right_Plan_v8_temp.md`, `docs/phase2_findings.md`,
`docs/CLAUDE.md` (the status table row on data availability, and the two log entries).
Documentation only — no code, model or number changed.

**What the "selected altitude" is.** When a controller tells a pilot "climb to 30,000
feet", the pilot turns a dial on the autopilot to 30,000. The aircraft then climbs and
stops at exactly that number. Modern aircraft broadcast the dial setting over the same
radio signal that carries their position.

**Why it matters for false alarms.** Our system sees an aircraft climbing and has to guess
where it will stop. If it guesses "keeps climbing", it may raise an alarm about an aircraft
that was always going to level off 1,000 feet below another one. Knowing the dial setting
turns that guess into a known fact. Our biggest single source of false alarms is exactly
this kind of situation — two aircraft passing close side-to-side but at different heights
— and the September experiment that tried to filter them out failed because we could only
guess, not know.

**What we had said before.** On 22–23 September we checked the OpenSky archive (the free
database our project uses), found it records only *whether* an aircraft is able to send
the dial setting and not the setting itself, and wrote the feature off as permanently
unavailable.

**What is true now.** That was right about OpenSky and wrong in general — we had only
checked one source. A different free network, adsb.lol, keeps the dial setting. Checked on
23 September over Mumbai: 9 of the 13 aircraft in range were sending it at that moment (9
of the 11 actually flying), and the saved day-long track for an individual aircraft shows
the setting changing as the aircraft was cleared up and down through its flights. The same
records also carry the wind the aircraft measured and the outside temperature, which
OpenSky does not provide either.

**Why it was worth correcting openly rather than quietly.** The original finding is left in
place in `docs/phase2_findings.md` with a dated correction beneath it. Being wrong and
catching it is part of the project's record, and the lesson — check more than one source
before calling something impossible — is more useful than a tidy document.

**What happens next.** Nothing is built yet. The plan now has a new item (9.0) to collect
this data, starting with a measurement: over a full week, how many Mumbai aircraft actually
send it? One moment's snapshot is encouraging, not proof. The data comes with a licence
(ODbL 1.0) that requires attribution and sharing derived data on the same terms, which has
to be read before any of it goes in the report.

**Did the headline number move?** No — **94.0% unchanged**. This changes the plan, not the
system.

### 2026-09-23 — Repository cleanup: duplicates, stale backups and leftovers removed

**Files deleted:** `Flight_Right_ML_Approach.docx.bak`;
`ml_pipeline/ingestion/scheduled_poll.py.bak`, `scheduled_poll_b.py.bak`,
`scheduled_poll_c.py.bak`; `ml_pipeline/data/processed/_test_raw_scores.npy`;
`ml_pipeline/reports/reevaluation_20260921_170331.json`, `…_20260921_182951.json`,
`…_20260922_083519.json`, `…_20260923_025438.json`, `…_20260923_093828.json`,
`…_20260923_095413.json`; `ml_pipeline/reports/voice_corpora_20260922_083606.json`;
`client/prompt.json`; `client/dist/`; the eight `__pycache__` folders outside `venv`.

**Before.** The repository carried copies that did nothing: a Word backup identical to the
version already saved in git; older copies of the three collection scripts from before they
learned to save progress every ten minutes (every line of the old copies is still in the
new ones); a scratch file of raw classifier scores from 8 September; six re-score reports
that were exact repeats of others apart from the time they were run, and one repeated
speech-data report; a prompt written to get an AI to build the radar map, which has long
since been built; and folders that Python and the website build recreate on their own.

**Now.** All of those are gone. Kept deliberately: the three distinct re-score reports
(8 Sep, 22 Sep and the latest 23 Sep — the two the logs cite are among them), all three
Trino reports (each records a different stage of access being granted), the CSV copies of
the session and encounter data (Archit's choice), the 1 September model report PDF, the
sample flights CSV, the collection logs (the source of the credit figures in Section 14),
the research papers, and every model, dataset and document.

**Why.** Dead copies make it unclear which file is the real one — two re-score reports with
different names and identical contents invite the question of which to trust. Every deleted
item was checked first: backups compared line by line against the current files, reports
compared value by value, and every file searched for in the code and documents. Nothing
referenced any of them.

**Did the headline number move?** No — **94.0% unchanged**. `verify_pipeline.py` 110 of 110,
the 8 unit tests and `inference_check.py` all pass after the deletion.

### 2026-09-24 — Tested whether switching on the new path model gives better alerts, and found the "running system" figure was missing a step

**Files:** `ml_pipeline/utils/offsets_ab_test.py` (new), `scripts/check_adsblol_history.py`
(new), `docs/evaluation.md`, `docs/PROJECT_STATUS.md`, `docs/phase2_findings.md`,
`docs/CLAUDE.md`. No model, threshold or setting was changed, and nothing was switched on.

**What was known before.** Phase 3.1 made the "five possible futures" model better at
predicting where aircraft go. But the backend still uses the old version, because the new
one changes which aircraft pairs the controller is warned about. A replay of recorded traffic
could show *that* the warnings changed but not whether they got *better*, because a replay
does not say which pairs really came too close.

**What was done.** The 4,690 practice pairs held back for testing each come with the true
answer: whether the two real aircraft actually lost separation. The script rebuilds each
pair's last ten position reports (the saved file did not keep them), and checks first that
the rebuild matches the saved file exactly on all 40,000 rows. Then it runs every test pair
through the same alarm decision the backend makes, three ways: without the path model, with
the old version, and with the new one.

**What it found, in three parts.**

1. **The new version is slightly better than the old one, on every measure.** It catches one
   more real conflict with three minutes of warning (269 of 284 instead of 268). It raises
   about 2 fewer false alarms per 1,000 pairs, and one fewer false audible alarm. That is a
   real improvement but a small one, from a single training run.

2. **A number we published was incomplete, and it is now corrected.** We said the running
   system catches 94.7%. That measurement skipped one step the backend actually takes: for
   pairs more than three minutes away, it uses the path model's picture of the future
   instead of a straight line. With that step included, **the system as it runs today
   catches 94.4%, not 94.7%.** The documents now say so.

3. **Why the path model adds false alarms, which is the useful part.** A "false alarm" means
   a warning for a pair that never actually came too close. The safety net is a simple rule:
   "warn if the aircraft are predicted within 5 miles and 1,000 feet". It is meant to run
   on the plain straight-line prediction. With the path model switched in, it runs on the
   closest of 25 combinations of the two aircraft's possible paths, even one the model
   thinks is only 2% likely. That produced about 60 extra warnings, most of them false.
   Deciding how to change that is exactly the next plan step (3.2), and because it changes
   when a controller is warned, it is Archit's decision.

**Also answered: the last open Phase 2 question (2.6).** The free service adsb.lol, which
records the altitude the pilot has dialled into the autopilot, lets us download any single
aircraft's day for the **last six weeks** reliably. Older days are hit and miss. So a daily
collector can gather this going forward, but older history has to come from their bulk
releases. Phase 2 is now fully complete.

**Did the headline number move?** **No — 94.0% is unchanged**, because it scores the conflict
classifier on its own and the classifier was not touched. The *running-system* figure is
corrected downward from 94.7% to **94.4%**. The system did not get worse; the earlier
measurement had missed a step.

### 2026-09-24 — Plan 3.2 done: the safety net checks the straight line again, and the new path model is switched on

**Files:** `ml_pipeline/utils/cpa_conflict_detection.py`, `server/app/ml/inference.py`,
`ml_pipeline/utils/offsets_ab_test.py`, `ml_pipeline/tests/test_units.py`, plus comment
updates in `multipath.py` and `reevaluate_models.py`, and the docs (`evaluation.md`,
`PROJECT_STATUS.md`, this file). Switched on at the user's instruction in this session:
"turn both of them on if beneficial".

**What it was before.** The system has a simple safety rule: if the straight-line prediction
says two aircraft will come within 5 miles and 1,000 feet of each other, warn, whatever any
model thinks. But for aircraft pairs more than three minutes apart, the code had quietly
swapped the straight line for the path model's picture. That picture is five possible paths
per aircraft, so 25 combinations for a pair, and the rule checked the *closest* of them,
even one the model rated only 2% likely. Two things went wrong. Unlikely paths set off extra
warnings. And one real conflict was missed: the straight line said "too close", the model's
chosen path said "fine", and the straight line was never asked.

**What it is now.** The safety rule always looks at the straight line, exactly as the project
rules require. The path model still decides how urgent a warning is (audible alarm or watch
list) and still helps check suggested manoeuvres. And the improved path model from Phase 3.1,
which predicts each aircraft's own path rather than a group average, is now the default.

**Why, and how it was decided.** Before looking at any results, the rule for "beneficial" was
written into the script. A change must not miss a single conflict the current system
catches, must not lose any audible alarm for a real conflict, and must keep the straight-line
safety rule. Among changes that pass, the one with the fewest false warnings wins. Then 21
combinations were measured on the 4,690 practice pairs held back for testing:

| | caught with 3 min warning | false warnings per 1,000 pairs | false audible alarms |
|---|---|---|---|
| before | 268 of 284 | 113.0 | 18 |
| **now** | **269 of 284** | **101.1** | **17** |

That is one more real conflict caught and 55 fewer false warnings, with nothing given up.
Trimming the unlikely paths, which is what plan step 3.2 proposed, was also tried. It helped,
but less than simply keeping the model's paths out of the safety rule. One option caught two
extra conflicts, at the cost of about 86 extra false warnings; that trade is recorded for you
to revisit, not adopted.

**Checked, not assumed.** The shipped code was run through the real alarm logic on all 4,690
pairs and makes exactly the decision that was measured. All 110 pipeline checks, 11 unit
tests (three new ones on this rule), and the inference check pass. The full re-score matches
the previous one on all 698 values apart from its timestamp. An old model file still starts
the backend.

**Speed.** One replayed hour of real Mumbai traffic had a single update take 17 seconds,
against a 10-second budget. Re-running the same hour, that update took 1.5 seconds and none
exceeded 4 seconds. The computer was measurably slower all day: the *old* setting was also
three to six times slower than on 23 September. So it was a one-off stall, not the change.
Worth re-timing on a quiet machine.

**Still owed:** the new path model has been trained once; plan 3.3 repeats it with three
different random starting points to confirm the result holds.

**Did the headline number move?** **No — 94.0% is unchanged**, because it scores the conflict
classifier alone and the classifier was not touched. The *running-system* figure (what the
controller actually gets) goes from **94.4% to 94.7%**, with 55 fewer false warnings.

### 2026-09-24 — Looked up what plan step 3.2 should do, tried the two ideas the research supports, and switched neither on

**Files:** `ml_pipeline/utils/alert_prominence.py` (new), `ml_pipeline/utils/offsets_ab_test.py`
(its saved rebuild now covers all 40,000 practice pairs, not only the test ones),
`docs/ISSUES.md` (new item H5). Nothing the system does was changed.

**What was asked.** Find out what should be done in 3.2, and do it only if it shows the
controller fewer false alarms without costing a single real conflict.

**What the research says.** The standard review of conflict-detection methods (Kuchar & Yang,
2000) warns that checking every possible path raises "a high false alarm rate" when those
paths are unlikely, and recommends deciding on how *likely* a conflict is instead. NASA's
conflict-probability work (Paielli & Erzberger, 1997) builds alerting on exactly that
likelihood. Europe's air-traffic-control guidelines say false ("nuisance") alerts must be kept
to a minimum, and that any alert held back must still be made known to the controller.

**Two ideas followed from that, and both were tested fairly.** Each rule was chosen using one
set of practice pairs (the validation pairs) and then checked once on a separate set the
choice never saw (the test pairs). Choosing and checking on the same pairs would make "no
real conflict lost" true by construction and prove nothing.

1. **Only let the path model raise the loud alarm when one of its paths actually conflicts.**
   Today a pair can become a loud alarm because the model's *most likely* path reaches its
   closest point within three minutes, even though that path passes safely. On the validation
   pairs this removed 2 false loud alarms and lost nothing. On the test pairs it removed 3
   false loud alarms **but turned one real conflict's loud alarm into a quiet watch-list
   entry.** That breaks the "not a single real conflict" condition, so it was rejected. It
   was not adjusted afterwards, because adjusting it after seeing the test result would be
   cheating the check.

2. **Only tuck a watch-list entry into the collapsed group when both models agree it is
   unlikely.** No version of this showed fewer false alarms without hiding a new real
   conflict: a handful of real conflicts look unlikely to both models. What it *can* do is
   make the screen safer. It hides 3 real conflicts instead of 7, at the cost of 50 more false
   entries on the list. That is the opposite trade to the one asked for, so it was not switched
   on. It is written up as a decision for you.

**Something worth knowing that came out of this.** The existing collapsed group (entries the
classifier scores under 0.25) contains **7 real conflicts on the test pairs**, each with more
than three minutes of warning. They are not lost: they stay on the list and turn into a full
alarm inside three minutes. But until then the controller sees them only as part of a count.
This is now recorded as issue H5.

**What would actually cut false alarms safely.** Knowing where each aircraft has been told to
level off. That is the fix Europe's own alerting systems use, and the data exists (adsb.lol,
plan item 9.0). Without it, the pairs that cause false alarms and the pairs that are real
conflicts look the same, which is why both ideas failed.

**Did the headline number move?** No. **94.0% is unchanged**, and so is the running-system
figure of 94.7%. Nothing that runs was changed.

### 2026-09-25 — Plan 3.3: checked the new path model is not a lucky run, and measured what more data buys

**Files:** `ml_pipeline/training/trajectory/multipath.py` (two optional settings added),
`ml_pipeline/utils/archive_row.py` (new), `docs/evaluation.md`, reports
`multipath_seeds_20260925_012526.json` and `multipath_archive_seeds_20260925_030354.json`. The model
the system runs was not changed.

**What it was before.** The improved path model (the one that predicts each aircraft's own
path, switched on 24 September) had been trained exactly once. A machine-learning result
from one training run can be luck. Training starts from random choices, and a different
starting point can give a noticeably different score.

**What was done.** The whole model was trained three more times from different random
starting points, on exactly the same data, and scored the same way. The original run was
also repeated, and it reproduced itself exactly, which shows the setup is sound.

| Arrivals into Mumbai, ten minutes ahead | lowest of 4 runs | highest of 4 runs |
|---|---|---|
| New model: one of its five paths was right | 71.5% | 72.4% |
| Old model: one of its five paths was right | 61.7% | 64.8% |
| New model: its single best guess was right | 42.6% | 44.4% |
| Old model: its single best guess was right | 37.1% | 39.8% |

The new model's *worst* run beats the old model's *best* run on the five-path measure. On
every run it wins by 7 to 11 points. So the improvement is real, not luck. The version
already running was the lowest of the four, and it was deliberately left in place: picking
the best-looking run would flatter the numbers without making anything better.

**The second question: does more data help?** Earlier, 243 MB of past Mumbai traffic was
downloaded from the OpenSky archive and deliberately kept apart from the training data. This
time, 12 of those days were used, spread from February 2025 to July 2026. Only days *before*
the testing period were allowed in, because learning from the future would make the test
meaningless. 400,000 extra examples were added, and the model was retrained and tested on the
same test data as always.

The answer is yes, clearly. "One of five paths right" for arrivals rose from **71.5% to
75.4%**, and "single best guess right" from **44.2% to 46.8%**. The gain is about ten times
larger than the difference between random runs. The model also became far more honest about
its own confidence before any correction was applied.

**Why it is not switched on yet.** It has been trained once, on a fifth of the archive data
available, and nobody has yet measured how it changes which alerts the controller gets. That
measurement, plus three runs, comes first. Switching the running model changes what
controllers see, so it is a decision for you once those numbers exist.

**Did the headline number move?** No. **94.0% is unchanged**, and so is the running-system
94.7%. Nothing that runs was changed.


### 2026-09-25 — Finished testing the "more data" model (not switched on), and answered whether the model uses altitude

**Files:** `ml_pipeline/utils/archive_row.py` (can now train several seeds),
`ml_pipeline/utils/alert_prominence.py` (can now compare any saved path model),
`ml_pipeline/utils/multipath_3d_eval.py` (new), `docs/evaluation.md`. Nothing that runs was
changed.

**The "more data" model, finished.** Yesterday's model trained with extra archive data had been
run once. Now it has been run four times, from different random starting points. It is
consistently better at predicting where an aircraft will be. For arrivals, "one of five paths
right" is 75.6% (74.9-76.1%), against 72.0% (71.5-72.4%) for the model in use. Its worst run
beats the current model's best run.

**It was still not switched on, and the reason matters.** The rule was written down before
looking: switch it on only if no real conflict loses anything and false alarms do not go up.
The new model was put through exactly what the controller would see, on the labelled practice
pairs. On the test pairs, every alert came out identical. On the validation pairs, **one real
conflict lost its loud alarm** (it became a quiet watch-list entry) and one false alarm became
loud. So it fails the rule.

Why a more accurate model does not help: the path model now only decides whether a warning is
loud (under three minutes) or quiet. For a few pairs sitting right on the three-minute line,
that decision flips back and forth whichever model is used, sometimes on a path that does not
even conflict. Better predictions just reshuffle those borderline cases. That borderline
decision is what has to be fixed before better trajectories can reach the controller.

**Your question: does the prediction model use altitude?** Yes and no, and this check turned up
something important.

- **Yes:** every prediction model is given the aircraft's height, how its height changed over
  the last ten reports, how fast it is climbing or descending, and whether that rate is
  changing. And they predict height as well as position.
- **No:** the model does *not* know the height the pilot has been told to fly to (the
  autopilot's "selected altitude"). That is the most useful missing piece, and OpenSky does
  not carry it. Plan item 9.0 collects it from adsb.lol.
- **The important finding:** the height half of the five-path model had never been scored.
  Every result for it measured horizontal distance only. Scored now, **the old version was no
  better than a straight line at predicting height**. The version switched on on 24 September
  halves the height error, from about 2,230 ft to 1,120 ft at ten minutes. That is a real
  benefit nobody knew about. It also means the honest figure for "one of five paths close in
  *both* position and height" for arrivals is **44.1%**, not the 71.5% quoted before, which was
  position only. Both are now in `docs/evaluation.md`, and the three-dimensional one is the
  number to use when talking about conflicts.

**Did the headline number move?** No. **94.0% is unchanged**, and so is the running-system
94.7%. Nothing that runs was changed.


### 2026-09-25 — Built the plug for the future speech system, measured what it would be worth, and fixed three long-standing defects

**Files:** `ml_pipeline/utils/clearance.py`, `oracle_clearance.py`, `clearance_demo.py`,
`ablation.py` (all new); `server/app/services/clearance_service.py` (new);
`server/app/ml/inference.py`, `server/app/services/conflict_service.py`,
`server/app/services/database.py`, `server/app/api/routes.py`, `server/app/config.py`,
`scripts/postgres.py`; `ml_pipeline/utils/resolution_engine.py`; `client/src/lib/siteLogger.js`,
`client/src/pages/LogsPage.jsx`; `docs/ablation.md`, `docs/claims.md` (new),
`docs/ISSUES.md`, `docs/PROJECT_STATUS.md`.

**The plug for speech.** You asked for the system to be ready for speech-to-text without
building it yet. A controller's instruction, such as "descend to 13,000 feet" or "turn to
heading 090", now has one standard shape inside the system: a *clearance*. Today a clearance
can be typed in through the API. Later, the speech system only has to produce the same thing
and hand it over through the same door. Nothing else needs to change. The two database tables
the speech system will write to already exist, and like the audit log, the database will not
let anyone edit them afterwards.

**What would hearing the radio be worth?** This was measured using the *true* instructions
(what each aircraft actually did), as if the radio had been heard perfectly. That gives an
**upper bound**; a real speech system will do worse. The finding that matters: **the plan's
own idea was wrong for altitude.** The plan said to throw away predicted paths that disagree
with a heard instruction. For altitude, that threw away the best-guess path 9% of the time and
made predictions worse. What works is what European air-traffic systems do: keep every path,
but don't let any of them fly through the altitude the aircraft was told to stop at. Done that
way, "one of five paths close in both position and height" for arrivals rises from 43% to 54%.
Headings still work the plan's way.

**On the live system**, with a real recorded pair: when one aircraft's instruction was known,
the model's stated chance of conflict dropped from as high as 24% to zero. The pair stayed on
the watch list, because since 22 September that list is decided by the classifier and the
straight-line safety rule, not by this model. It was all tested end to end through the real
server and database. A good instruction was accepted; an unknown aircraft and an impossible
altitude were refused, with the reason given. All three were recorded.

**The evidence table (plan Phase 8)** is now generated by a script, never typed, so it cannot
drift from the models. One pleasant surprise: the model switched on on 24 September is now
better than the plain non-neural "tree" model, which had beaten every neural model since
September. A second document, `docs/claims.md`, lists what we may claim, what we may not, and
what we must admit. Writing it caught two old figures still being quoted.

**Three defects fixed:**
- **Suggested manoeuvres (C1, C2).** The system sometimes suggested a manoeuvre when doing
  nothing was already safe, and quoted a "result" that was really the situation *before* the
  aircraft could move. Now a manoeuvre is suggested only if the simulation shows that doing
  nothing loses separation, and results are measured only from when the aircraft can react.
  Suggestions for conflicts that never happen fell from 38 to 11. Nothing else in the system
  changed.
- **The audit log (H1).** Most things the controller clicked were recorded only in the browser
  tab and vanished when it closed. Every one now also goes to the permanent server log, and the
  Logs page shows that permanent log.

**Did the headline number move?** No. **94.0% is unchanged**, and so is the running system's
94.7%.


### 2026-09-25 — Two more small defects fixed, and which Mumbai runway is in use

**Files:** `server/app/api/routes.py`, `client/src/lib/adapters.js`, `client/src/pages/HomePage.jsx`,
`scripts/derive_runways.py` (new), `ml_pipeline/requirements.txt`, `docs/ISSUES.md`.

**What was wrong, and what it is now.**
- **The audit log didn't say which model made a suggestion (H2).** Every row had a blank
  model version. Now the server writes in the exact versions of the models it is running,
  because only the server knows them for certain.
- **Dismissing a suggestion hid that pair of aircraft forever (H3),** even if they later came
  into real danger. Now a dismissal only covers that particular moment. If the situation gets
  worse, or the two aircraft meet again later, the suggestion comes back.

**Which runway Mumbai was using (plan 9.1).** Using a standard aviation analysis library,
753 landings were found in our recordings: 751 on runway 27 and 2 on runway 32. That makes
sense, because in the monsoon the wind comes from the west, so aircraft land towards the west.
But it also means the runway hardly changes in our data, so there is nothing yet for the model
to learn from it. It will matter with data from other seasons. The library needed an older
version of one component, so it was given its own separate space on the computer rather than
risk breaking the working system.

**Needs you:** open `docs/figures/runway_spotcheck.png` and confirm that each of the eight red
lines sits on the runway it is labelled with. The plan asks for a person to check this. It
looked right to Claude, but that is not the same thing.

**Did the headline number move?** No. **94.0% is unchanged.**


### 2026-09-25 — A hidden mix-up in the training data's labels, fixed; and two new measurements about India

**Files:** `ml_pipeline/training/trajectory/preprocess_sequences.py`, `ml_pipeline/utils/verify_pipeline.py`,
`scripts/fetch_adsblol_traces.py`, `scripts/route_lookup_accuracy.py`, `ml_pipeline/utils/adsblol_parse.py`,
`ml_pipeline/utils/context_features.py` (new scripts), `docs/claims.md`.

**A mix-up, found and fixed.** Each training example carries a label saying which aircraft it
came from. On 22 September those labels were added, but through a small mistake they were
attached to the wrong examples, like shuffling the name tags at a party after sorting the
guests. No model ever read the labels, so no result was affected: the flight data itself was
checked and is identical to the byte. But today's work needed them to match each example with
what the pilot had dialled into the autopilot, and the mismatch showed up at once. It is fixed,
and a new automatic check now confirms the labels match on every run. On the old files the same
check fails completely, so it would have caught the mistake.

**Can we get the autopilot altitude over Mumbai? Yes, almost always.** For every aircraft in
our 12 days of recordings, the free service adsb.lol was asked for its full day of data: 4,090
aircraft-days out of 4,142. **Almost every aircraft (99.6%) broadcasts the altitude it has
been told to fly to, and 95% of reports near Mumbai include it.** That had been unknown for
Indian airspace. It had to be fetched now, because the service keeps only about six weeks of
history. It is saved locally, under a licence that requires credit to be given.

**How accurate are free "which route is this flight on" services for India?** The better one
(adsbdb) gets the full route right for 49% of our flights, and for 69% of flights to or from
Mumbai. The other (hexdb) mostly does not answer at all. Nobody had published this figure for
India.

**Did the headline number move?** No. **94.0% is unchanged.**


### 2026-09-25 — Tested four new kinds of information from the plan: one helps the alarm system, none helps path prediction

**Files:** `ml_pipeline/utils/context_features.py`, `context_ablation.py`, `classifier_intent_ablation.py`
(new), `ml_pipeline/training/trajectory/multipath.py` (an optional switch, off by default),
`ml_pipeline/utils/offsets_ab_test.py`, `ml_pipeline/utils/ablation.py`, `docs/ablation.md`,
`docs/DECISIONS_FOR_ARCHIT.md` (new).

**What was tested.** The plan's phase 9 listed four kinds of extra information that might help:
the altitude the pilot has dialled into the autopilot, the wind the aircraft measured, the
aircraft type, and how much other traffic is nearby. Each was added on its own and measured
fairly, one change at a time.

**For predicting where an aircraft will be, none of them helped.** Every difference was
smaller than the natural variation between training runs.

**Why the dialled altitude doesn't help predict ten minutes ahead, which is worth knowing.**
Near Mumbai, the altitude a pilot dials in is usually one *step* on the way, not the final
level. Within ten minutes, **three out of four aircraft that are climbing or descending have
already been cleared past it.** So treating it as "where the aircraft will stop" made
predictions much worse. It is reliable only for the next minute or two, which is exactly how
Europe's alerting systems use it.

**For the alarm system, the dialled altitude does help.** Given the same number of false alarms,
the system with this information caught as many or more real conflicts in all four training
runs. Tuned the usual way, it cut false alarms by about a fifth on average. But in two of the
four runs it also missed two or three more real conflicts. Whether to spend the improvement on
fewer false alarms or on catching more real conflicts is a decision about when controllers are
alerted, so it is yours. It would also need a live feed of the dialled altitude, which the
system does not have yet. It is **not switched on**. It is item 1 in the new
`docs/DECISIONS_FOR_ARCHIT.md`, which lists everything waiting for you.

**Did the headline number move?** No. **94.0% is unchanged.** Nothing that runs was changed.


### 2026-09-25 — Checked every number before publishing, ran the dashboard like a live demo, and fixed where the demo starts

**File changed:** `server/app/services/replay_service.py`.

**What was checked.** Before pushing to GitHub, every result that does not depend on speech was
measured again from the saved model files, on the computer's main processor rather than the
graphics card. All of it came back the same: the automatic checks (111 of 111), the unit tests,
the full re-score (every one of 697 numbers identical to the previous run), the running-system
measurement, the evidence table, and the database's refusal to let anyone edit the decision log.

**The demo, done the way a presenter would.** The backend and the dashboard were started, and a
script clicked through Chrome like a person. It waited for a real alarm, pressed RESOLVE NOW,
picked the top suggestion and pressed ACCEPT, then opened the logs page. It worked: two real
aircraft over Mumbai, **IGO086 and FDB1346**, were predicted to pass 2.6 miles apart and 950 feet
apart in three minutes. The system raised the alarm, offered two ranked manoeuvres with plain
explanations, and recorded the controller's choice permanently. There were no errors on the page.

When the same dialog was opened only 15 seconds before the aircraft met, it offered nothing and
said so, because no manoeuvre can work in that time. That is the honest answer.

**What was wrong, and what it is now.** Recorded traffic is mostly quiet, so replay mode skips
to three minutes before an interesting moment. It was choosing that moment with the old, wider
warning zone (8 miles / 1,500 feet). Since 22 September, though, an alarm needs the pair to be
predicted inside the legal minimum (5 miles / 1,000 feet), or the classifier to agree. So the
demo was opening on two aircraft 1,100 feet apart, which are legally separated and correctly
never alarm. A viewer would have watched five minutes of nothing. It now opens before a pair
that genuinely breaks the legal minimum, and the alarm appears within a minute.

**Did the headline number move?** No. **94.0% is unchanged**, and so is the running system's 94.7%.
This changes where the recording starts playing, not when an alarm fires.
