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

**Research grounding (cite if asked "why this approach"):**
- AWARE/AI4ATM: conflict detection/resolution should integrate into
  controller workflow, not be a black box → drove the single-dashboard
  design with alerts + suggestions + explanations + audit log together.
- Guleria et al.: conflict resolution as multi-output prediction
  (aircraft, maneuver, timing, magnitude) → rule-based first, ML ranker
  later.
- XGBoost-on-ADS-B paper: XGBoost/engineered features work well and are
  explainable for conflict detection → chosen as the MVP classifier.
- 4D trajectory CTGAN/C-CTGAN paper: generative trajectory models are
  powerful but data-hungry/hard to explain → kept as stretch goal only,
  MVP uses constant-velocity baseline then Bi-LSTM.
- M2ATS: multimodal ATC understanding → NLP/datalink kept as future
  roadmap, not MVP.

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
- **Trajectory prediction model:** Bi-LSTM (bidirectional, 2 layers,
  hidden size 128, dropout 0.3, batch size 64, Adam optimizer, lr 0.001).
  4 output heads predicting future lat/lon/altitude at 1, 3, 5, and 10
  minute horizons. Input: last 10 aircraft states — lat, lon, altitude,
  speed, heading (as sin/cos, never raw degrees — avoids the 360°
  wraparound problem), vertical rate, time gap between points, and an
  MSSR-quality flag (India-specific: inject noise during training to
  simulate poor radar data and make the model robust to it).
  **Constant-velocity extrapolation is the required baseline** —
  implement and evaluate it before training the Bi-LSTM; the Bi-LSTM must
  be shown to beat it, not just replace it on faith.
- **Conflict detection model:** XGBoost binary classifier (0 = no
  conflict, 1 = potential conflict) over pairwise tabular features:
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
    never remove it once the ML classifier ships.** Thresholds for MVP:
    lateral 5 NM, vertical 1000 ft, lookahead window 5–10 minutes. These
    are simplified academic thresholds, not full regulatory separation
    standards — say so if asked.
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
  → Prediction Pipeline → Trajectory Prediction (Bi-LSTM) + Conflict Detection (XGBoost + CPA rules)
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
transforms are needed, PyTorch for the Bi-LSTM, joblib to persist
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
2. **Synthetic conflict scenarios** — generate artificial pairwise
   conflicts: pick two aircraft near the same region, assign converging
   headings, vary altitude difference/speed/time-to-CPA, label via CPA
   rules. Used for conflict classifier training, resolution engine
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
metrics on replay/synthetic scenarios. XGBoost and the Bi-LSTM come after
that deterministic baseline works, not before.

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
  XGBoost exists, never delete constant-velocity once the Bi-LSTM
  exists).
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
