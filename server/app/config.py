"""Settings for the Flight Right backend, all overridable from the environment.

Defaults match the decisions recorded in CLAUDE.md so that running the server with no
configuration at all reproduces the documented behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
RAW_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "raw"
AUDIT_DATABASE = Path(os.environ.get("FLIGHT_RIGHT_AUDIT_DB", DATA_ROOT / "server" / "audit.sqlite3"))

# PostgreSQL connection string, written into .env by scripts/postgres.py. When it is set
# and reachable the store uses Postgres, where the audit log is append-only because the
# application role is not granted UPDATE or DELETE on it. When it is absent or the server
# is down, the store falls back to the SQLite file above and says so on /api/health.
# It contains a password: never log it, never return it from an endpoint.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Three data modes, exactly as CLAUDE.md Section 3 requires. "auto" tries live and falls
# back to replay when OpenSky is unreachable or out of credits, which is the documented
# behaviour ("always build a fallback to replay").
DATA_MODE = os.environ.get("FLIGHT_RIGHT_DATA_MODE", "auto").strip().lower()

# Mumbai demo bounding box (CLAUDE.md Section 2).
BOUNDS = {
    "lat_min": float(os.environ.get("OPENSKY_LAMIN", 16.0)),
    "lat_max": float(os.environ.get("OPENSKY_LAMAX", 23.5)),
    "lon_min": float(os.environ.get("OPENSKY_LOMIN", 68.0)),
    "lon_max": float(os.environ.get("OPENSKY_LOMAX", 77.5)),
}

# OpenSky OAuth2 client credentials. The old Node backend used Basic auth with a
# username and password; OpenSky retired that, and the project's .env carries the
# client-credentials pair instead.
OPENSKY_CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID", "").strip()
OPENSKY_CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "").strip()
OPENSKY_TOKEN_URL = ("https://auth.opensky-network.org/auth/realms/opensky-network/"
                     "protocol/openid-connect/token")
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"

# How often the ingestion loop refreshes. Ten seconds matches the collection scripts and
# the surveillance-update assumption the alert feed's re-announcement rules are built on.
POLL_SECONDS = float(os.environ.get("FLIGHT_RIGHT_POLL_SECONDS", 10.0))

# Where a replay starts. "conflict" scans the session for its first real encounter and
# begins shortly before it, because 90 minutes of recording is mostly uneventful and a
# demo that opens on empty sky is not a demo. "start" begins at the beginning. This
# chooses a starting point in real data; it does not invent anything.
REPLAY_SEEK = os.environ.get("FLIGHT_RIGHT_REPLAY_SEEK", "conflict").strip().lower()

# Replay speed multiplier, so a demo does not have to run in real time.
REPLAY_SPEED = float(os.environ.get("FLIGHT_RIGHT_REPLAY_SPEED", 1.0))

# Conflict detection is en-route only (CLAUDE.md, 30 Aug 2026). Applying the en-route
# 5 NM rule to approach traffic flagged something in 91-94% of all snapshots, because
# landing aircraft are legitimately close together. This floor is applied at inference,
# not only when building training data.
CONFLICT_MIN_ALTITUDE_FT = float(os.environ.get("FLIGHT_RIGHT_CONFLICT_FLOOR_FT", 10_000.0))
CONFLICT_MIN_VELOCITY_MS = 50.0

# Cheap geometric pre-filter before the model chain runs on a pair. Pairs further apart
# than this cannot reach the alert volume inside ten minutes, so assessing them is wasted
# work. Measured on real traffic: this leaves tens of pairs per update, not hundreds.
PAIR_PREFILTER_NM = float(os.environ.get("FLIGHT_RIGHT_PREFILTER_NM", 60.0))
PAIR_PREFILTER_FT = float(os.environ.get("FLIGHT_RIGHT_PREFILTER_FT", 5_000.0))

# Upper bound on pairs pushed through the full learned chain in one update, so a busy
# snapshot degrades by assessing the closest pairs rather than by missing the update.
MAX_PAIRS_PER_UPDATE = int(os.environ.get("FLIGHT_RIGHT_MAX_PAIRS", 120))

# How many past states each aircraft keeps. The trajectory models need 10; a few more
# gives the manoeuvre summary a stable window.
HISTORY_LENGTH = 24

CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "FLIGHT_RIGHT_CORS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

# --- Clearances and the (future) voice chain: plan Phases 4-7 -------------------------
# A clearance -- "descend FL130", "turn heading 090" -- adjusts that aircraft's candidate
# paths (ml_pipeline/utils/clearance.py). Today a clearance comes from the manual API
# (POST /api/clearances). The speech chain, when built, produces the same object and
# posts it through the same service, so nothing downstream changes when voice arrives.
#
# ASR_MODEL_ID is the ONE place the speech model will be named (plan 4.3). Empty means no
# speech model is installed: transcription endpoints report that, rather than failing.
# Default: our own fine-tune (whisper-small + LoRA, ml_pipeline/voice/train_whisper.py), chosen
# 27 Sep 2026 after the four-model comparison (reports/voice_eval_20260927_015420.json): on held-out
# ATCO2 it gets the whole clearance right 64.5% of the time against 35.5% for
# jlvdoorn/whisper-large-v3-atco2-asr-atcosim, 15.1% word error on unseen Czech radio against 46.9%,
# and runs ~3.5x faster. Used when its directory exists on this machine; otherwise empty.
OWN_ASR_MODEL = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FlightRight/voice/models/flightright-whisper-small-atc-p1"
ASR_MODEL_ID = os.environ.get("FLIGHT_RIGHT_ASR_MODEL_ID",
                              str(OWN_ASR_MODEL) if OWN_ASR_MODEL.exists() else "").strip()
ASR_QUANTISATION = os.environ.get("FLIGHT_RIGHT_ASR_QUANTISATION", "int8_float16").strip()
# Demo clips for the dashboard's radio panel: <id>.wav plus index.json. Outside OneDrive,
# beside the speech cache. Every clip there is labelled with where its audio came from.
SPEECH_DEMO_DIR = Path(os.environ.get(
    "FLIGHT_RIGHT_SPEECH_DEMO_DIR",
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "FlightRight" / "voice" / "demo_clips"))
# A clearance below this confidence is recorded but not applied. Manual entries carry
# 1.0; a heard one carries extractor confidence x callsign-match score. Set 26 Sep by
# Archit ("good for numbers and good for safety") from the measurement on our own model and
# real ATCO2 radio, 24 heard clearances with a known truth: 0.90 applied 10 of 20 correct and
# 0 wrong; 0.85 applied 12 of 20 correct and 0 wrong; 0.60 applied 18 of 20 and 1 wrong.
# Our own design, not from a standard; small sample, so re-measure on Mumbai-accent audio.
# A heard clearance only reshapes predicted paths -- it cannot switch an alarm off.
# Live dialled (selected) altitude from adsb.lol for the conflict classifier (plan 9.0, served
# 26 Sep). Polled every 30 s in live and auto mode; replay uses the recorded history instead.
# "off" disables the poller; the classifier then sees "unknown", as for aircraft that do not
# broadcast it.
INTENT_FEED = os.environ.get("FLIGHT_RIGHT_INTENT_FEED", "on").strip().lower()
CLEARANCE_MIN_CONFIDENCE = float(os.environ.get("FLIGHT_RIGHT_CLEARANCE_MIN_CONFIDENCE", 0.85))
# How long a clearance stays in force without a newer one for the same aircraft.
CLEARANCE_VALID_SECONDS = float(os.environ.get("FLIGHT_RIGHT_CLEARANCE_VALID_SECONDS", 600.0))
