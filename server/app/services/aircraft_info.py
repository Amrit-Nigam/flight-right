"""Real details for each aircraft, replacing the placeholders the normalizer used to send.

Before 27 Sep 2026 every aircraft reached the dashboard with route "BOM TMA", type "UNK",
fuel "--" and a "waypoint" guessed from its position (see normalizer.py's history). None of
that was data. Now:

- registration and type: adsb.lol. In replay, from the per-aircraft trace headers already
  on disk (ml_pipeline/data/adsblol/aircraft_info.parquet, 1,721 airframes, 97% with a type);
  live, from the adsb.lol feed intent_service polls every 30 s (fields r / t / desc / squawk).
  ODbL 1.0: "Contains data from adsb.lol".
- route (origin -> destination): adsbdb, from the cache route_features.py keeps
  (ml_pipeline/data/routes/adsbdb/). Measured over India (plan 9.2): the route is exactly right
  for 49% of all our flights and 69% of Mumbai flights, so it is labelled a lookup, not a plan.
- distance and bearing from Mumbai: computed from the position.
- ETA: only for aircraft whose looked-up destination is VABB, from distance and ground speed,
  and marked as an estimate.
- fuel: no public source exists, so the field is gone.
"""

from __future__ import annotations

import logging
import threading
import time

from ..config import PROJECT_ROOT
from .airport_service import ARP, bearing_deg, distance_nm

log = logging.getLogger("flightright.aircraft_info")

RECORDED_INFO = PROJECT_ROOT / "ml_pipeline" / "data" / "adsblol" / "aircraft_info.parquet"


class AircraftInfo:
    def __init__(self) -> None:
        self._recorded: dict[str, dict] | None = None
        self.live: dict[str, dict] = {}            # icao24 -> {registration, type, description, squawk, at}
        self._routes: dict[str, tuple[float, tuple]] = {}
        self._lock = threading.Lock()

    def _recorded_table(self) -> dict[str, dict]:
        if self._recorded is None:
            table: dict[str, dict] = {}
            try:
                import pandas as pd
                frame = pd.read_parquet(RECORDED_INFO)
                # Gaps come back as NaN, which JSON cannot carry (it broke /api/aircraft/latest):
                # every missing value becomes None.
                clean = lambda v: None if v is None or (isinstance(v, float) and v != v) or v == "" else str(v)  # noqa: E731
                for row in frame.itertuples(index=False):
                    table[str(row.icao24).lower()] = {"registration": clean(row.registration),
                                                      "type": clean(row.type),
                                                      "description": clean(row.description)}
            except Exception as failure:           # noqa: BLE001 -- no file: types are simply unknown
                log.info("Recorded aircraft info unavailable: %s", failure)
            self._recorded = table
        return self._recorded

    def record_live(self, ac: dict, now: float) -> None:
        """Called by intent_service for every aircraft in each adsb.lol poll."""
        hex_ = str(ac.get("hex") or "").lower().lstrip("~")
        if not hex_:
            return
        with self._lock:
            self.live[hex_] = {"registration": ac.get("r"), "type": ac.get("t"), "description": ac.get("desc"),
                               "squawk": ac.get("squawk"), "at": now}

    def route(self, callsign: str | None) -> tuple[str | None, str | None]:
        """(origin, destination) ICAO codes from the adsbdb cache; re-read every ten minutes."""
        key = str(callsign or "").strip().upper()
        if not key:
            return None, None
        cached = self._routes.get(key)
        if cached and time.time() - cached[0] < 600:
            return cached[1]
        try:
            from ml_pipeline.utils.route_features import route
            value = route(key, fetch=False)
        except Exception:                          # noqa: BLE001
            value = (None, None)
        self._routes[key] = (time.time(), value)
        return value

    def destination(self, callsign: str | None) -> str | None:
        return self.route(callsign)[1]

    def enrich(self, flight: dict) -> dict:
        icao24 = str(flight.get("icao24") or "").lower()
        live = self.live.get(icao24) or {}
        recorded = self._recorded_table().get(icao24) or {}
        info = {k: live.get(k) or recorded.get(k) for k in ("registration", "type", "description")}
        origin, destination = self.route(flight.get("callsign"))
        out = dict(flight)
        out.update({
            "registration": info["registration"],
            "aircraft": info["type"],
            "aircraftDescription": info["description"],
            "aircraftSource": ("adsb.lol live feed" if live.get("type") else
                               "adsb.lol recorded trace" if recorded.get("type") else None),
            "origin": origin,
            "destination": destination,
            "route": f"{origin or '?'} → {destination or '?'}" if (origin or destination) else None,
            "routeSource": "adsbdb route lookup (cached)" if (origin or destination) else None,
            "squawk": flight.get("squawk") or live.get("squawk"),
        })
        lat, lng = flight.get("lat"), flight.get("lng")
        if lat is not None and lng is not None:
            dist = distance_nm(lat, lng, *ARP)
            out["distanceToVabbNm"] = round(dist, 1)
            out["bearingFromVabbDeg"] = round(bearing_deg(*ARP, lat, lng))
            kt = float(flight.get("speedKt") or 0)
            if destination == "VABB" and kt > 60 and not flight.get("onGround"):
                out["etaMinutes"] = round(dist / kt * 60, 1)
                out["eta"] = f"~{round(dist / kt * 60)} min"
        estimated = ["status"]                         # flight phase from altitude + climb rate
        if out.get("eta"):
            estimated.append("eta")
        out["estimatedFields"] = estimated
        return out


aircraft_info = AircraftInfo()
