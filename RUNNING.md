# Running Flight Right

Two processes: a Python backend on port 8000 and the React dashboard on port 5173.

## First time

```bash
pip install -r server/requirements.txt
cd client && npm install
```

## Every time — two terminals

**Terminal 1, backend:**
```bash
python -m uvicorn server.app.main:app --port 8000
```

**Terminal 2, dashboard:**
```bash
cd client && npm run dev
```

Open <http://localhost:5173>. Interactive API docs are at <http://127.0.0.1:8000/docs>.

The backend must be running first, or the dashboard shows **BACKEND UNREACHABLE** in the
bar under the top strip. That is deliberate: it does not fall back to invented traffic.

---

## Data modes

Set `FLIGHT_RIGHT_DATA_MODE` before starting the backend.

| Mode | What it does |
|---|---|
| `auto` *(default)* | Live OpenSky; falls back to replay if the feed is down or credits run low |
| `replay` | A recorded session only. Repeatable, works offline, best for a demo |
| `live` | Live only. Shows the error rather than falling back |

```bash
FLIGHT_RIGHT_DATA_MODE=replay python -m uvicorn server.app.main:app --port 8000
```

Live mode needs `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET` in the project-root
`.env`. The backend stops using live data below 200 remaining credits, leaving the reserve
the scheduled collection runs need.

**For a demo, use `replay`.** It needs no internet, it is identical every time, and by
default it starts three minutes before a genuine encounter in the recording — real
aircraft that really did converge over Mumbai.

## Useful settings

| Variable | Default | What it changes |
|---|---|---|
| `FLIGHT_RIGHT_DATA_MODE` | `auto` | live / replay / auto |
| `FLIGHT_RIGHT_REPLAY_SEEK` | `conflict` | `conflict` starts near a real encounter; `start` begins at the beginning |
| `FLIGHT_RIGHT_REPLAY_SPEED` | `1.0` | Replay speed multiplier |
| `FLIGHT_RIGHT_POLL_SECONDS` | `10` | Seconds between updates |
| `FLIGHT_RIGHT_CONFLICT_FLOOR_FT` | `10000` | En-route floor for conflict detection |
| `FLIGHT_RIGHT_MAX_PAIRS` | `120` | Cap on pairs assessed per update |
| `VITE_API_URL` | `http://127.0.0.1:8000` | Set in `client/.env` if the backend moves |

## What to expect

- **33–38 aircraft**, of which **20–28** clear the 10,000 ft en-route floor.
- **15–30 pairs** assessed per update, in **1.8–2.5 s** against a ten-second budget.
- A tier 1 alarm needs the pair to qualify on **three consecutive updates**, so allow about
  30 seconds after startup before anything fires.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/aircraft/latest` | Current aircraft |
| GET | `/api/aircraft/source` | Which data mode is feeding the screen |
| POST | `/api/aircraft/mode` | Switch mode at runtime |
| GET | `/api/aircraft/history` | One aircraft's recent states |
| GET | `/api/conflicts/active` | The alert feed: `active`, `notifications`, counts |
| POST | `/api/predict/conflicts` | Force a fresh assessment |
| GET | `/api/recommend/resolution` | Model 3's options for one pair |
| POST | `/api/actions/accept` · `/dismiss` | Record a controller decision |
| GET · POST | `/api/audit` | The append-only audit log |
| GET | `/api/health` | Aircraft, conflicts, model versions, audit count |
| WS | `/ws/stream` | Aircraft and conflicts pushed together |

**A note on `/api/conflicts/active`:** render `active` in full. `notifications` is the
subset that should interrupt. Rendering only `notifications` turns a display rule into a
detection rule, which the alert feed exists to prevent.

## Troubleshooting

**"BACKEND UNREACHABLE"** — the backend is not running, or it is on another port. Check
<http://127.0.0.1:8000/api/health>.

**Dashboard says "polling" instead of "streaming"** — the WebSocket did not connect.
Everything still works, just less efficiently. Usually `pip install websockets`.

**No conflicts appear** — allow 30 s for the three-consecutive-updates rule. Only en-route
traffic above 10,000 ft is assessed, so quiet periods genuinely produce nothing. In replay
mode the log line "Replay starts N frames before a real encounter" names the pair to watch.

**Map is blank** — map tiles come from the Carto CDN and need internet. Aircraft still
appear in the list and the radar-sweep view.

**Port 8000 already in use** — on Windows:
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```
