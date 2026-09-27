"""Where each flight is going: four destination features, computed the same way everywhere.

Training (context_features.py), the alarm-chain check (destination_row.py) and the live backend
(server/app/ml/inference.py) all call route_matrix(), so the numbers a model learned from are the
numbers it is served. Order is fixed by ROUTE_FEATURES and must match context_features.GROUPS.

  dest_dist_nm        great-circle distance to the destination airport
  dest_bearing_sin    sin / cos of the bearing to the destination, relative to the current track
  dest_bearing_cos    (so "straight ahead" is cos = 1, "behind" is cos = -1)
  orig_dist_nm        distance from the departure airport (says how far into the flight it is)

Sources, stated because a mentor will ask:
- The route (origin, destination) per callsign: adsbdb, https://www.adsbdb.com/ (plan 9.2 measured it
  over India: the route is exactly right for 49% of all our flights and 69% of Mumbai flights).
  Cached one file per callsign under ml_pipeline/data/routes/adsbdb/ (gitignored). A route is
  schedule information, known before the flight, so it cannot leak what the aircraft later did.
- Airport coordinates: OurAirports, public domain, https://ourairports.com/data/ (the airport-metadata
  source CLAUDE.md Section 3 names).
Unknown route or airport -> NaN, which the gradient-boosted regressors treat as "missing".
"""
from __future__ import annotations

import json
import math
import ssl
import time
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "ml_pipeline/data/routes"
OURAIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
ROUTE_FEATURES = ["dest_dist_nm", "dest_bearing_sin", "dest_bearing_cos", "orig_dist_nm"]
HEADERS = {"User-Agent": "FlightRight-research/1.0 (academic project; cached, 2 req/s)"}
_last_fetch = [0.0]


def _context() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


@lru_cache(maxsize=1)
def airports() -> dict[str, tuple[float, float]]:
    """ICAO code -> (latitude, longitude)."""
    import pandas as pd
    path = ROUTES / "ourairports_airports.csv"
    if not path.exists():
        ROUTES.mkdir(parents=True, exist_ok=True)
        path.write_bytes(urllib.request.urlopen(OURAIRPORTS_URL, context=_context(), timeout=120).read())
    a = pd.read_csv(path, usecols=["ident", "gps_code", "icao_code", "latitude_deg", "longitude_deg"],
                    keep_default_na=False, low_memory=False)
    out: dict[str, tuple[float, float]] = {}
    for column in ("icao_code", "gps_code", "ident"):
        rows = a[a[column].str.fullmatch(r"[A-Z]{4}")]
        for code, lat, lon in zip(rows[column], rows["latitude_deg"], rows["longitude_deg"]):
            out.setdefault(code, (float(lat), float(lon)))
    return out


def route(callsign: str, fetch: bool = False) -> tuple[str | None, str | None]:
    """(origin, destination) ICAO codes for a callsign, from the cache; optionally fetch once."""
    callsign = str(callsign or "").strip().upper()
    if not callsign:
        return None, None
    path = ROUTES / "adsbdb" / f"{callsign}.json"
    if not path.exists() and fetch:
        wait = 0.5 - (time.monotonic() - _last_fetch[0])
        if wait > 0:
            time.sleep(wait)
        _last_fetch[0] = time.monotonic()
        record = {"status": 0}
        try:
            url = f"https://api.adsbdb.com/v0/callsign/{urllib.parse.quote(callsign)}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), context=_context(),
                                        timeout=20) as response:
                fr = json.load(response)["response"]["flightroute"]
                record = {"status": 200, "origin": fr["origin"]["icao_code"],
                          "destination": fr["destination"]["icao_code"]}
        except urllib.error.HTTPError as error:
            record = {"status": error.code}
        except Exception:                                    # noqa: BLE001 -- unknown stays unknown
            record = {"status": 0}
        if record["status"] in (200, 404):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
    if not path.exists():
        return None, None
    answer = json.loads(path.read_text())
    return answer.get("origin"), answer.get("destination")


def _distance_nm(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)
    return 3440.065 * math.acos(max(-1.0, min(1.0, c)))


def _bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                   math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)))


def route_matrix(callsigns, lat, lon, track_deg, fetch: bool = False) -> np.ndarray:
    """(N, 4) in ROUTE_FEATURES order. A None / empty callsign gives a row of NaN."""
    places = airports()
    out = np.full((len(callsigns), len(ROUTE_FEATURES)), np.nan)
    for i, callsign in enumerate(callsigns):
        if callsign is None or (isinstance(callsign, float) and math.isnan(callsign)):
            continue
        origin, dest = route(callsign, fetch=fetch)
        if dest in places:
            dlat, dlon = places[dest]
            out[i, 0] = _distance_nm(lat[i], lon[i], dlat, dlon)
            rel = math.radians(((_bearing_deg(lat[i], lon[i], dlat, dlon) - track_deg[i]) + 180.0) % 360.0 - 180.0)
            out[i, 1], out[i, 2] = math.sin(rel), math.cos(rel)
        if origin in places:
            olat, olon = places[origin]
            out[i, 3] = _distance_nm(lat[i], lon[i], olat, olon)
    return out


def track_from_window(X: np.ndarray) -> np.ndarray:
    """Current track in degrees from model windows (N, 10, 8): column 4 is sin, 5 is cos."""
    return np.degrees(np.arctan2(X[:, -1, 4], X[:, -1, 5])) % 360.0
