"""Turn a raw aircraft state into the shape the dashboard renders.

This is a direct port of the Node `aircraftNormalizer.js` that was deleted on 30 August
with the rest of the Express backend. The field names and the formatting rules are kept
byte-for-byte compatible on purpose: the React components were written against this
shape, so preserving it means the frontend needs rewiring rather than rewriting.

The one behavioural change is `status`, which is now allowed to say CONFLICT. The old
version could not know that, because nothing was detecting conflicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

METRES_TO_FEET = 3.28084
MS_TO_KNOTS = 1.94384
MS_TO_FPM = 196.8504


def format_altitude(altitude_ft: float) -> str:
    """FL280 above the transition level, plain feet below it, GND on the ground."""
    try:
        feet = float(altitude_ft)
    except (TypeError, ValueError):
        return "GND"
    if feet <= 0:
        return "GND"
    if feet >= 10_000:
        return f"FL{round(feet / 100)}"
    return f"{round(feet)}ft"


def format_speed(speed_kt: float) -> str:
    try:
        knots = max(0.0, float(speed_kt))
    except (TypeError, ValueError):
        knots = 0.0
    return f"{round(knots)} kt"


def infer_status(altitude_ft: float, speed_kt: float, vertical_rate_fpm: float,
                 on_ground: bool, source_status: str | None = None) -> str:
    """The flight phase, from the numbers alone.

    We have no flight plan, so this is inferred from height and vertical rate. It drives
    only the colour and the filter chips in the flight list, never a safety decision.
    """
    if source_status:
        return str(source_status).upper()
    if on_ground:
        return "DEPARTING"
    if altitude_ft < 10_000 and vertical_rate_fpm < -150:
        return "LANDING"
    if altitude_ft < 10_000 and vertical_rate_fpm > 150:
        return "TAKEOFF"
    if altitude_ft < 12_000:
        return "APPROACH"
    return "CRUISE"


def infer_waypoint(lat: float, lng: float, altitude_ft: float, heading: float) -> str:
    """A nearest-fix label for the detail drawer. Cosmetic, and approximate."""
    if lat is None or lng is None:
        return "TMA"
    if altitude_ft < 7000 and lng < 72.75:
        return "27L ILS"
    if altitude_ft < 7000 and 240 < heading < 300:
        return "27R ILS"
    if lat > 20:
        return "OKLOV"
    if lng > 73.2:
        return "DISHA"
    return "DEGAN"


def normalize(raw: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """One aircraft, in the shape the React components consume."""
    now = now or datetime.now(timezone.utc)
    altitude_ft = float(raw.get("altitudeFt") or 0.0)
    speed_kt = float(raw.get("speedKt") or 0.0)
    vertical_rate_fpm = float(raw.get("verticalRateFpm") or 0.0)
    heading = float(raw.get("heading") or 0.0)
    lat, lng = raw.get("lat"), raw.get("lng")

    return {
        "icao24": str(raw.get("icao24") or raw.get("callsign") or "").strip().lower(),
        "callsign": str(raw.get("callsign") or raw.get("icao24") or "UNKNOWN").strip(),
        "originCountry": raw.get("originCountry") or "Unknown",
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
        "altitude": raw.get("altitude") or format_altitude(altitude_ft),
        "altitudeFt": altitude_ft,
        "speed": raw.get("speed") or format_speed(speed_kt),
        "speedKt": speed_kt,
        "heading": heading,
        "verticalRateFpm": vertical_rate_fpm,
        "verticalRateMs": vertical_rate_fpm / MS_TO_FPM,
        "altitudeM": altitude_ft / METRES_TO_FEET,
        "velocityMs": speed_kt / MS_TO_KNOTS,
        "status": infer_status(altitude_ft, speed_kt, vertical_rate_fpm,
                               bool(raw.get("onGround")), raw.get("status")),
        "onGround": bool(raw.get("onGround")),
        # The fields below have no source in ADS-B. They are placeholders the dashboard
        # renders, and they are marked so the UI can label them rather than imply they
        # are measured. A flight-plan feed would fill route, eta and aircraft type.
        "route": raw.get("route") or "BOM TMA",
        "aircraft": raw.get("aircraft") or "UNK",
        "eta": raw.get("eta") or "--",
        "squawk": raw.get("squawk") or "----",
        "fuel": raw.get("fuel") or "--",
        "waypoint": raw.get("waypoint") or infer_waypoint(
            float(lat) if lat is not None else 0.0,
            float(lng) if lng is not None else 0.0, altitude_ft, heading),
        "estimatedFields": ["route", "eta", "aircraft", "fuel", "waypoint"],
        "timePosition": raw.get("timePosition"),
        "updatedAt": now.isoformat(),
        "source": raw.get("source") or "replay",
    }


def is_valid(aircraft: Mapping[str, Any]) -> bool:
    lat, lng = aircraft.get("lat"), aircraft.get("lng")
    return (lat is not None and lng is not None
            and -90 <= lat <= 90 and -180 <= lng <= 180)


def from_opensky_state(state: Sequence[Any], now: datetime | None = None) -> dict[str, Any]:
    """One row of the OpenSky /states/all response.

    Field order is fixed by the OpenSky API and documented in CLAUDE.md Section 6.
    Geometric altitude is preferred over barometric where both are present.
    """
    def at(index: int):
        return state[index] if index < len(state) else None

    icao24, callsign, origin_country = at(0), at(1), at(2)
    time_position, longitude, latitude = at(3), at(5), at(6)
    baro_altitude_m, on_ground, velocity_ms = at(7), at(8), at(9)
    true_track, vertical_rate_ms, geo_altitude_m, squawk = at(10), at(11), at(13), at(14)

    altitude_m = geo_altitude_m if geo_altitude_m is not None else baro_altitude_m
    return normalize({
        "icao24": icao24,
        "callsign": (str(callsign).strip() if callsign else None) or str(icao24 or "UNKNOWN").upper(),
        "originCountry": origin_country,
        "lat": latitude,
        "lng": longitude,
        "altitudeFt": (float(altitude_m) * METRES_TO_FEET) if altitude_m is not None else 0.0,
        "speedKt": (float(velocity_ms) * MS_TO_KNOTS) if velocity_ms is not None else 0.0,
        "heading": float(true_track) if true_track is not None else 0.0,
        "verticalRateFpm": (float(vertical_rate_ms) * MS_TO_FPM) if vertical_rate_ms is not None else 0.0,
        "onGround": bool(on_ground),
        "squawk": squawk,
        "timePosition": time_position,
        "route": "OpenSky live",
        "aircraft": "ADS-B",
        "eta": "LIVE",
        "source": "opensky",
    }, now)


def to_engine_state(aircraft: Mapping[str, Any]) -> dict[str, float]:
    """The field names ml_pipeline and server/app/ml/inference.py expect."""
    return {
        "latitude": float(aircraft["lat"]),
        "longitude": float(aircraft["lng"]),
        "altitude_m": float(aircraft["altitudeM"]),
        "velocity_ms": float(aircraft["velocityMs"]),
        "heading_deg": float(aircraft["heading"]),
        "vertical_rate_ms": float(aircraft["verticalRateMs"]),
        "time_position": float(aircraft.get("timePosition") or 0.0),
        "callsign": aircraft.get("callsign", "UNKNOWN"),
    }
