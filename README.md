# Flight Right

**An AI-assisted air traffic control decision-support dashboard for the Indian airspace
context.** It monitors aircraft, predicts near-term conflicts, recommends explainable
resolution manoeuvres, and records every decision in an append-only audit log.

The controller always decides. Every suggestion can be accepted, dismissed or overridden,
and that choice is logged.

> **Prototype — decision support, not automation.** This is a final-year engineering
> project. It is not a certified ATC system, it does not control aircraft, and it is not
> a replacement for a controller. OpenSky is not a certified surveillance feed;
> production use would require certified surveillance, flight plans, weather, NOTAMs and
> regulatory validation.

---

## The headline result

> **94.0% of conflicts are caught with at least three minutes of warning.**

Three minutes is not a round number — it is the minimum useful warning. An alert takes
about 38 s to turn into aircraft movement (controller decision 15 s, radio call and
readback 15 s, pilot reaction 8 s), and a 1,000 ft level change then takes ~40 s while a
30° turn at 450 kt takes ~96 s. Below about three minutes, no manoeuvre an airliner can
fly opens a safe gap in time — which we confirmed by simulating every option, not just by
arithmetic.

Measured on held-out test data from later dates than anything the models trained on:

| Method | Conflicts caught with at least 3 min warning |
|---|---|
| Rule at the legal minimum (5 NM / 1000 ft) | 81.7% |
| Rule at the alert volume (8 NM / 1500 ft) | 87.3% |
| **XGBoost classifier** | **94.0%** |

Full metrics, charts and the rejected experiments are in **[docs/evaluation.md](docs/evaluation.md)**.

---

## What it does

```
OpenSky live feed ─┐
recorded replay    ├─→ normalize ─→ Model 1 / 1b: where each aircraft is going
scenario data     ─┘                      │
                          Model 2: is this pair going to lose separation?
                                          │
                    Two tiers: alarm (0–3 min) vs watch list (3–10 min)
                                          │
                          Model 3: three costed, explained ways out
                                          │
                    alert feed (repeat suppression) → dashboard
                                          │
             controller accepts / dismisses → append-only audit log
```

### The four models

| | What it does | Status |
|---|---|---|
| **Model 1** — trajectory | A 2-layer LSTM predicting a *correction* to constant-velocity extrapolation at 1/3/5/10 min. A zero output reproduces the physics exactly, so it can never do worse than plain arithmetic. | Done |
| **Model 1b** — multi-path | Five candidate paths with calibrated probabilities, from 40 learned route patterns. Best-of-5 reaches 63.6% within 5 NM at ten minutes where a single answer reaches 38.6%. For conflict detection we never have to pick one — we check all five. | Done |
| **Model 2** — conflict classifier | XGBoost over 24 pairwise features. Features come from the constant-velocity *prediction*; the label comes from where two real aircraft *actually went*. SHAP explains every alert. | Done |
| **Model 3** — resolution engine | Rule-based. Simulates every candidate manoeuvre at 1-second resolution through a 38 s response delay and real turn/climb rates, checks it against the other aircraft's five predicted futures *and* all nearby traffic, then ranks by safety 0.60 / delay 0.15 / fuel 0.10 / workload 0.10 / confidence 0.05. | Done |

Every learned layer has a deterministic one underneath that still works: constant velocity
under the LSTM, the geometric CPA rule under the classifier, recorded replay under the live
feed, SQLite under PostgreSQL.

### Two tiers, not one alarm

- **Tier 1 (0–3 min)** — audible alarm *and* resolution options.
- **Tier 2 (3–10 min)** — watch-list entry only. Never suggests a manoeuvre, because a
  ten-minute prediction does not justify turning an aircraft.
- Escalation needs all three: probability over the tier threshold, time-to-CPA inside the
  tier's range, and the pair qualifying on **three consecutive updates**, so one noisy
  position report cannot make an alert flicker.

### The audit log cannot be edited

The application connects to PostgreSQL as a role granted `INSERT, SELECT` on `audit_logs`
and nothing else. The database itself refuses an UPDATE or DELETE, regardless of what the
code asks for:

```
[PASS] UPDATE on audit_logs is refused  --  permission denied for table audit_logs
[PASS] DELETE on audit_logs is refused  --  permission denied for table audit_logs
```

Run `python scripts/postgres.py verify` to see it. If Postgres is not running the backend
falls back to SQLite and says so on `/api/health` under `store`, including
`appendOnlyEnforced: false` — the weaker guarantee is never silently in force.

---

## Running it

Full detail, including data modes and troubleshooting, is in **[docs/RUNNING.md](docs/RUNNING.md)**.

### First time

```bash
pip install -r server/requirements.txt
cd client && npm install && cd ..

python scripts/postgres.py install   # official PostgreSQL 17.2 binaries, ~300 MB, once
python scripts/postgres.py init      # cluster, roles, schema, grants
python scripts/postgres.py verify    # proves the audit log is append-only
```

`init` writes `DATABASE_URL` into the project-root `.env`.

### Every time

```bash
python scripts/postgres.py start
```

Terminal 1 — backend:

```bash
python -m uvicorn server.app.main:app --port 8000
```

Terminal 2 — dashboard:

```bash
cd client && npm run dev
```

Open <http://localhost:5173>. Interactive API docs at <http://127.0.0.1:8000/docs>.

The backend must be up first, or the dashboard shows **BACKEND UNREACHABLE**. That is
deliberate — it does not fall back to invented traffic.

### Data modes

| `FLIGHT_RIGHT_DATA_MODE` | Behaviour |
|---|---|
| `auto` *(default)* | Live OpenSky, falling back to replay if the feed is down or credits run low |
| `replay` | A recorded session only. Repeatable, offline, **best for a demo** |
| `live` | Live only; shows the error rather than falling back |

For a demo use `replay`: it needs no internet, it is identical every run, and by default
it starts three minutes before a genuine encounter in the recording — real aircraft that
really did converge over Mumbai.

---

## Repository layout

```
client/                 React 19 + Vite + Tailwind + MapLibre dashboard
server/app/             FastAPI backend
  api/routes.py           REST endpoints
  main.py                 app, CORS, the ten-second ingest loop, /ws/stream
  services/               OpenSky client, replay, normalizer, aircraft, conflicts, database
  ml/inference.py         loads all three saved models; assess_pair() runs the full chain
ml_pipeline/
  ingestion/              OpenSky collection scripts (credit-aware, checkpointed)
  training/trajectory/    preprocessing, Model 1, Model 1b, evaluation, tree benchmark
  training/conflict_classifier/   encounter generation and Model 2
  utils/                  CPA detection, resolution engine, alert feed, verification
  tests/                  unit tests and an end-to-end smoke test on fake data
scripts/postgres.py     project-owned PostgreSQL: install, init, start, verify, reset
docs/                   all project documentation, plus the figures and metrics.json
                        backing evaluation.md
CLAUDE.md               a pointer that imports docs/CLAUDE.md, so Claude Code loads
                        the project instructions automatically
```

**Not in the repository** (all gitignored, all reproducible): raw OpenSky data, processed
datasets, trained model files, the PostgreSQL binaries and cluster, and `.env`. Train the
models with `python ml_pipeline/run_pipeline.py` — see
[ml_pipeline/README_TRAINING.md](ml_pipeline/README_TRAINING.md).

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/aircraft/latest` | Current aircraft states |
| GET | `/api/aircraft/source` | Which data mode is feeding the screen |
| POST | `/api/aircraft/mode` | Switch data mode at runtime |
| GET | `/api/aircraft/history` | One aircraft's recent states |
| GET | `/api/conflicts/active` | The alert feed: `active`, `notifications`, counts |
| GET | `/api/conflicts/history` | Conflicts raised, from the database |
| POST | `/api/predict/conflicts` | Force a fresh assessment |
| GET | `/api/recommend/resolution` | Model 3's options for one pair |
| POST | `/api/actions/accept` · `/api/actions/dismiss` | Record a controller decision |
| GET · POST | `/api/audit` | The append-only audit log |
| GET | `/api/health` | Aircraft, conflicts, model versions, store, audit count |
| WS | `/ws/stream` | Aircraft and conflicts pushed together |

**One WebSocket, not two.** An alert states a separation and a time, which is only
meaningful against the positions it was computed from. Two sockets give no ordering
guarantee, so an alert could arrive before the positions it refers to and the map would
draw it against stale data. Both are computed in the same tick and sent in the same
message; the envelope is typed so a client can still route them separately.

**On `/api/conflicts/active`:** render `active` in full. `notifications` is only the
subset that should interrupt. Rendering `notifications` alone turns a display rule into a
detection rule, which the alert feed exists to prevent.

---

## Verification

```bash
python ml_pipeline/utils/verify_pipeline.py     # 110 checks, cold start, from saved models
python -m pytest ml_pipeline/tests/test_units.py
python ml_pipeline/utils/reevaluate_models.py   # re-scores every model from its saved file
```

`verify_pipeline.py` loads each artifact in a fresh process with no access to the training
scripts, and asserts on shape, physical plausibility and the known traps — including that
the conflict label still cannot be recomputed from its own features, and that the test
split is still strictly later than the training split.

`reevaluate_models.py` re-measures everything from the saved files and writes a dated JSON.
Re-running it reproduced the headline number and the full scorecard exactly, which is what
makes "our results are reproducible" a command rather than a claim.

---

## Honest limitations

Stated here rather than left for a reviewer to find.

- **En-route traffic only**, above 10,000 ft. The en-route 5 NM / 1000 ft rule applied to
  approach traffic flags something in 91–94% of all snapshots, because landing aircraft
  are legitimately close together. Terminal-area conflicts need their own thresholds
  (~3 NM) and their own labels; out of scope here.
- **No flight-plan data.** We receive position reports, not clearances. The standard
  vertical nuisance-alert filter (EUROCONTROL STCA Option E) needs the *cleared* flight
  level; using observed vertical rate as a proxy costs 21 real conflicts and drops the
  headline from 94.0% to 86.6%. Measured, and therefore rejected.
- **False alarms are real**, but not where the headline precision suggests: of 740 alerts,
  only 41 are audible tier 1 alarms (precision 0.659). 96.9% of false alarms are silent
  watch-list rows. Repeat suppression cuts interruptions by about 74% on real traffic with
  **zero pairs removed from the active list**.
- **The non-neural benchmark still wins at ten minutes.** A `HistGradientBoostingRegressor`
  on identical features leads the LSTM by 2–8 points across every split measured. It stays
  in the repo as the standing bar; the LSTM is not presented as best-available.
- **Best-of-5 is not accuracy.** 63.6% means one of five candidates landed within 5 NM.
  Top-1 is 38.6%. Both are true and they measure different things.
- **Runway status, the weather overlay and the radio transcript have no data source** and
  are labelled DEMO on screen. NLP is explicitly out of MVP scope.
- **No authentication.** A fixed demo controller profile, per the MVP security posture.

---

## Documentation

| File | What it is |
|---|---|
| [docs/RUNNING.md](docs/RUNNING.md) | How to run everything, data modes, troubleshooting |
| [docs/ISSUES.md](docs/ISSUES.md) | Known issues — what does not work yet, found by testing the running system |
| [docs/evaluation.md](docs/evaluation.md) | Every metric beside the baseline it has to beat, with charts |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | Plain-English status, vocabulary, file-by-file walkthrough |
| [docs/CLAUDE.md](docs/CLAUDE.md) | The full decision log — every choice, the measurement behind it, and the experiments that failed |
| [ml_pipeline/README_TRAINING.md](ml_pipeline/README_TRAINING.md) | Training the models end to end |

---

## Stack

**Backend** — FastAPI · PyTorch · XGBoost · scikit-learn · PostgreSQL 17 · pandas / NumPy
**Frontend** — React 19 · Vite · Tailwind · Framer Motion · MapLibre GL · Recharts
**Data** — OpenSky Network REST API (OAuth2), Mumbai bounding box
