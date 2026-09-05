# Archit — everything left to finish Flight Right, in order

You can follow this yourself, or paste the whole file into Claude Code with the line
"Read CLAUDE.md first, then do ARCHIT_TODO.md step by step." Each step says what to
run, what "done" looks like, and what to send back.

The state of things: all the model code is finished and tested. What is missing is
(1) one real training run on your laptop, (2) one decision only you can make, and
(3) the web server and dashboard on top. Steps 1-3 take one evening. Steps 4-6 are the
rest of the project.

---

## Step 1 — Set up the laptop (15 minutes, once)

```powershell
git pull
git checkout fable-backend          # or backend, once merged
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r ml_pipeline/requirements.txt
python ml_pipeline/check_environment.py
```

**Done when:** every line of the check says `OK` or `WARN`, and the GPU line names the
RTX 4060. If PyTorch says it cannot see a GPU, you got the CPU build: run
`pip uninstall torch` and repeat the torch line with the `--index-url`.

Full detail: `ml_pipeline/README_TRAINING.md`.

## Step 2 — Train everything (20-30 minutes)

```powershell
python ml_pipeline/run_pipeline.py
```

Seven steps run in order. Do not run any OpenSky poll script at the same time.

**Done when:** the last lines say `Overall: OK` and name a report file in
`ml_pipeline/reports/`. Open it. The two sections that matter are **Gates** and the
`HEADLINE METRIC` block inside the `xgboost` step.

What to expect, based on the 5 September run:

| gate | expected |
|---|---|
| LSTM beats constant velocity at every horizon | PASS |
| Reference tree beats constant velocity | PASS (and it will beat the LSTM at 10 min; that is known and documented) |
| Multi-path, 5 options, arrivals at 10 min > 60% | PASS (was 63.6%) |
| Classifier Gate 1, recall >= 0.95 | **FAIL by about half a point** — expected, see Step 3 |
| Classifier Gate 2, beats the rule | PASS |
| Headline: conflicts caught with 3 minutes warning | around 93-94% |

Also new in this run, and worth reading: the multi-path `Calibration:` line and the
`Expected calibration error ... -> ...` line (the arrow should go down), and the
classifier's `CALIBRATION` block.

**Send back:** the whole `ml_pipeline/reports/` folder and
`server/app/ml/saved_models/xgboost_conflict_model_card.json`. Commit the report `.md`
(the `logs/` folder is gitignored, zip it separately).

Then run the inference check, which loads all three models exactly as the server will:

```powershell
python ml_pipeline/tests/inference_check.py
```

**Done when:** it prints four `update N:` lines ending in `notify True` on update 3, and
a "Why" block with five feature contributions.

## Step 3 — The one decision only you can make (10 minutes)

In the `xgboost` step of the report, find the block

```
WHAT-IF -- selecting the threshold with a recall margin above the 0.95 floor (NOT applied)
```

It has four rows: margin 0.000 (what is saved now), 0.005, 0.010, 0.020. Each row shows
what the classifier would do on the held-out test week: conflicts caught, false alarms
per 1,000 pairs, conflicts missed, the headline metric, and whether Gate 1 passes.

The question is: **how many extra false alarms per 1,000 pairs are you willing to pay
so that Gate 1 passes with margin?** Pick the smallest margin whose Gate 1 says PASS
and whose false-alarm cost you can defend out loud. My expectation is 0.010, but read
the table.

Then apply it and retrain only the classifier:

```powershell
$env:FLIGHT_RIGHT_RECALL_MARGIN = "0.01"        # the value you chose
python ml_pipeline/run_pipeline.py --only xgboost
```

The run prints `DECISION APPLIED` and writes the margin into the model card, so the
decision is on record. Then add a five-line entry to CLAUDE.md Section 15 saying which
margin you chose and why, quoting the row from the table. That is the whole rule from
Part 6: threshold changes need your sign-off, and your sign-off is that entry.

**Do not** pick a margin because it makes a number look nicer. Pick it because the
false-alarm cost is one you can explain to a controller.

## Step 4 — The FastAPI server (the next big piece)

Everything the server needs from the models is already in
`server/app/ml/inference.py`: `ConflictEngine.load()`, `engine.predict_trajectory(history)`,
`engine.assess_pair(history_a, history_b, pair_history)`. Build the API from CLAUDE.md
Section 5 on top of it, in this order:

1. `server/app/main.py` with FastAPI, `/health` returning `engine.status()`.
2. `services/opensky_client.py` and `services/ingestion_service.py`: poll OpenSky (reuse
   the token and request code from `ml_pipeline/ingestion/scheduled_poll.py`), keep the
   last 10 states per aircraft in memory, fall back to replaying a raw parquet from
   `ml_pipeline/data/raw/` when OpenSky is down or credits are low. Three modes: live,
   replay, scenario (Section 3).
3. `GET /api/aircraft/latest`, `WS /ws/aircraft`.
4. `services/conflict_service.py`: every poll, for every pair of en-route aircraft
   within 60 NM, call `assess_pair` with that pair's history; keep pairs whose
   escalation says `notify`. `GET /api/conflicts/active`, `WS /ws/alerts`.
5. `POST /api/audit`, `GET /api/audit`: PostgreSQL, append-only, fields from Section 6.
   SQLite is acceptable for the demo if Postgres is not set up; say so in the README.
6. `POST /api/actions/accept` and `/dismiss` writing audit rows.

**Done when:** `uvicorn server.app.main:app` runs, `/docs` lists every endpoint in
Section 5, and `/api/conflicts/active` returns a tier 1 alert during a replay of a
session that contains one (use the scenario mode to inject one if not).

Suggested Claude prompt for this step: *"Read CLAUDE.md Sections 3-7 and 12-13 and
`server/app/ml/inference.py`. Build the FastAPI backend described in Section 5 on top of
`ConflictEngine`, with live/replay/scenario data modes and an append-only audit log.
Do not change anything under `ml_pipeline/`. Write a Section 15 entry when done."*

## Step 5 — Restore the dashboard and connect it

```powershell
git checkout 91720e7 -- client
cd client && npm install && npm run dev
```

Then follow CLAUDE.md Section 8: replace `mockData.js` with the API, add
`useAircraftStream`, `useConflicts`, `useAuditLogger`, and the live/replay/scenario
indicator. Do not rewrite components.

**Done when:** the map shows aircraft from `/ws/aircraft`, the conflict banner shows
alerts from `/ws/alerts` with the `reason` string and the SHAP explanation, and
accepting or dismissing writes an audit row you can see at `/api/audit`.

## Step 6 — Model 3, the rule-based resolution engine

Only for tier 1 alerts (Section 3). Three options per conflict: altitude change,
heading change, speed change. For each: simulate it with `predict_dense_grid` from
`ml_pipeline/utils/cpa_conflict_detection.py`, re-run `compute_cpa`, and keep it only
if separation is restored. Score with `safety*0.60 + delay*0.15 + fuel*0.10 +
workload*0.10 + confidence*0.05`, prefer altitude as time-to-conflict falls, and attach
the explanation string format from Section 3. `POST /api/recommend/resolution`.

**Done when:** for a scenario-mode head-on conflict the endpoint returns three ranked
options, each with expected separation after the manoeuvre, and the top one is an
altitude change when time-to-CPA is under about 120 s.

## Step 7 — Report

Re-run `run_pipeline.py` once more on the final data, refresh the numbers in
`Flight_Right_ML_Approach.docx` from the report (Part 4 item 4), and put the headline
number first, with its basis, exactly as CLAUDE.md Part 1 says.

---

## Rules that apply to every step (from CLAUDE.md, the short version)

- Lead every report with the headline number and whether it moved.
- Never compare against a table from an earlier run; compare against the baseline or
  the rule measured in the same run.
- A failing gate is reported, not tuned away. Find out why first.
- Every change gets a Section 15 entry in plain English: file, before, now, why,
  did the headline move.
- Every proposed fix names its source, or says "our own design" and shows the measurement.
- The controller always has the final say. Nothing auto-applies a manoeuvre.
