"""Deterministic constant-velocity trajectory baseline for short look-aheads."""

from __future__ import annotations

import math
from collections.abc import Mapping


EARTH_RADIUS_M = 6_371_000.0
HORIZONS_SECONDS = {"1min": 60, "3min": 180, "5min": 300, "10min": 600}


def predict_future_position(
    latitude: float,
    longitude: float,
    altitude_m: float,
    velocity_ms: float,
    heading_deg: float,
    vertical_rate_ms: float,
    time_delta_seconds: float,
) -> tuple[float, float, float]:
    """Extrapolate a state along a constant ground-speed and vertical-rate vector.

    A spherical great-circle destination-point calculation is used. It costs very
    little and avoids longitude-scale distortions at different latitudes; over a
    one-to-ten-minute aircraft displacement it agrees closely with the usual
    equirectangular approximation while remaining safe near the poles/dateline.
    """
    distance_m = float(velocity_ms) * float(time_delta_seconds)
    bearing_rad = math.radians(float(heading_deg) % 360.0)
    latitude_rad, longitude_rad = math.radians(latitude), math.radians(longitude)
    angular_distance = distance_m / EARTH_RADIUS_M

    # Aviation headings are clockwise from north: 0 degrees points north and
    # 90 degrees east. The bearing form below therefore uses sin for eastward
    # movement and cos for northward movement (not the standard x-axis angle).
    predicted_latitude_rad = math.asin(
        math.sin(latitude_rad) * math.cos(angular_distance)
        + math.cos(latitude_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    predicted_longitude_rad = longitude_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(latitude_rad),
        math.cos(angular_distance) - math.sin(latitude_rad) * math.sin(predicted_latitude_rad),
    )
    predicted_longitude = ((math.degrees(predicted_longitude_rad) + 540.0) % 360.0) - 180.0
    predicted_altitude_m = float(altitude_m) + float(vertical_rate_ms) * float(time_delta_seconds)
    return math.degrees(predicted_latitude_rad), predicted_longitude, predicted_altitude_m


def predict_multiple_horizons(
    latitude: float | Mapping[str, float],
    longitude: float | None = None,
    altitude_m: float | None = None,
    velocity_ms: float | None = None,
    heading_deg: float | None = None,
    vertical_rate_ms: float | None = None,
) -> dict[str, tuple[float, float, float]]:
    """Return deterministic positions at the project's 1/3/5/10 minute horizons.

    The primary API is the six positional state values specified above. Passing a
    mapping with those same field names is additionally supported so existing
    state-dict callers can reuse this deterministic baseline without adapters.
    """
    if isinstance(latitude, Mapping):
        state = latitude
        latitude = state["latitude"]
        longitude = state["longitude"]
        altitude_m = state["altitude_m"]
        velocity_ms = state["velocity_ms"]
        heading_deg = state["heading_deg"]
        vertical_rate_ms = state["vertical_rate_ms"]
    if any(value is None for value in (longitude, altitude_m, velocity_ms, heading_deg, vertical_rate_ms)):
        raise ValueError("latitude, longitude, altitude_m, velocity_ms, heading_deg, and vertical_rate_ms are required")

    return {
        label: predict_future_position(latitude, longitude, altitude_m, velocity_ms, heading_deg, vertical_rate_ms, seconds)
        for label, seconds in HORIZONS_SECONDS.items()
    }
