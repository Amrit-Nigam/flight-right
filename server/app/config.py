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
