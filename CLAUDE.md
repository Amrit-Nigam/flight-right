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
| **Model 1b — multi-path output** | **DONE and calibrated on real data.** Full run 6 Sep 2026: temperature 1.729, calibration error 0.054 -> 0.019 on arrivals and 0.040 -> 0.012 overall. Best-of-5 at ten minutes 63.6%. |
| **Model 2 — conflict detection** | **WORKING** as of 5 Sep 2026. Circular label fixed; beats the rule at equal false-alarm cost. Rule path still runs underneath. 6 Sep: Platt calibration, SHAP explanations, GPU training and the recall-margin what-if table are coded; alerts unchanged. |
| **Model 3 — resolution engine** | **DONE (rule-based)** as of 6 Sep 2026. Three explained, costed, ranked options per tier 1 alarm. 7 Sep: checked against the other aircraft's 5 predicted paths and against all nearby traffic, so a fix that would cause a new conflict is rejected. ML ranker still deferred. |
| **Training pipeline** | **ONE COMMAND** as of 6 Sep 2026: `python ml_pipeline/run_pipeline.py` (see `ml_pipeline/README_TRAINING.md`). Smoke-tested end to end on fake data; the real run on the RTX 4060 laptop is pending. |
| **Backend (FastAPI server)** | **RUNNING** as of 8 Sep 2026. `server/app/` — 13 REST endpoints plus `/ws/stream`, OpenSky OAuth2 live mode, recorded-session replay with fallback, the full model chain per pair, the alert feed, and an append-only SQLite audit log. Start with `python -m uvicorn server.app.main:app --port 8000`. |
| **Alert feed (what the controller sees)** | **DONE** as of 7 Sep 2026: `ml_pipeline/utils/alert_feed.py`. Repeat suppression and low-confidence collapsing, both display-only. Interruptions down 63-65% on real traffic replay and prominent-list precision 0.386 -> 0.503, with **zero** pairs lost from the reported set. Not yet called by anything — the API layer and the frontend are still to come. |
| **Frontend dashboard** | **CONNECTED** as of 8 Sep 2026. Aircraft, conflicts, resolutions, suggestions, metrics, timeline and the audit trail all come from the backend over a WebSocket, with polling fallback. No mock data remains for anything a model produces. Runways, weather and the NLP transcript have no data source and are labelled DEMO on screen. |

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
