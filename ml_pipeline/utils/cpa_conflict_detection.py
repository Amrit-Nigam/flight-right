"""Closest-point-of-approach calculations and transparent rule-based labels."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


EARTH_RADIUS_M = 6_371_000.0
METRES_PER_NAUTICAL_MILE = 1_852.0
METRES_TO_FEET = 3.28084
HORIZON_SECONDS = {"1min": 60, "3min": 180, "5min": 300, "10min": 600}


def haversine_distance_nm(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Return great-circle lateral distance between latitude/longitude points in NM."""
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (latitude_a, longitude_a, latitude_b, longitude_b))
    delta_lat, delta_lon = lat_b - lat_a, lon_b - lon_a
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return (2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))) / METRES_PER_NAUTICAL_MILE


def _position(prediction: Any) -> tuple[float, float, float]:
    """Accept the baseline tuple format, plus named dictionaries for convenience."""
    if isinstance(prediction, Mapping):
        return float(prediction["latitude"]), float(prediction["longitude"]), float(prediction["altitude_m"])
    latitude, longitude, altitude_m = prediction
    return float(latitude), float(longitude), float(altitude_m)


def compute_cpa(aircraft_a_predictions: Mapping[str, Any], aircraft_b_predictions: Mapping[str, Any]) -> dict[str, Any]:
    """Find the minimum predicted lateral separation in the four-horizon window."""
    common_horizons = [label for label in HORIZON_SECONDS if label in aircraft_a_predictions and label in aircraft_b_predictions]
    if not common_horizons:
        raise ValueError("Aircraft predictions have no matching standard horizons.")

    per_horizon: dict[str, dict[str, float]] = {}
    for label in common_horizons:
        lat_a, lon_a, altitude_a = _position(aircraft_a_predictions[label])
        lat_b, lon_b, altitude_b = _position(aircraft_b_predictions[label])
        per_horizon[label] = {
            "horizon_seconds": HORIZON_SECONDS[label],
            "lateral_distance_nm": haversine_distance_nm(lat_a, lon_a, lat_b, lon_b),
            "vertical_separation_ft": abs(altitude_a - altitude_b) * METRES_TO_FEET,
        }

    cpa_label = min(per_horizon, key=lambda label: per_horizon[label]["lateral_distance_nm"])
    cpa = per_horizon[cpa_label]
    return {
        "cpa_horizon_seconds": cpa["horizon_seconds"],
        "cpa_lateral_distance_nm": cpa["lateral_distance_nm"],
        "cpa_vertical_separation_ft": cpa["vertical_separation_ft"],
        "per_horizon": per_horizon,
    }


def classify_conflict(
    cpa_result: Mapping[str, Any], lateral_threshold_nm: float = 5.0, vertical_threshold_ft: float = 1000.0
) -> dict[str, bool | str]:
    """Apply configurable separation thresholds and the project's severity rules."""
    lateral = float(cpa_result["cpa_lateral_distance_nm"])
    vertical = float(cpa_result["cpa_vertical_separation_ft"])
    cpa_seconds = float(cpa_result["cpa_horizon_seconds"])
    is_conflict = lateral < lateral_threshold_nm and vertical < vertical_threshold_ft

    # Severity describes lateral encounter urgency. A high severity can therefore
    # still have is_conflict=False when vertical separation remains safe.
    if lateral < 3.0 and vertical < 700.0 and cpa_seconds <= 180:
        severity = "critical"
    elif lateral < 5.0 and cpa_seconds <= 300:
        severity = "high"
    elif lateral < lateral_threshold_nm and cpa_seconds <= 600:
        severity = "medium"
    else:
        distances = [item["lateral_distance_nm"] for item in cpa_result.get("per_horizon", {}).values()]
        # A decreasing range that never crossed the configured threshold is a
        # low-risk convergence; otherwise there is no meaningful convergence.
        severity = "low" if len(distances) >= 2 and min(distances[1:]) < distances[0] else "none"
    return {"is_conflict": is_conflict, "severity": severity}
