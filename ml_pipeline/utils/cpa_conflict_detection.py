"""Closest-point-of-approach calculations and transparent rule-based labels."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ml_pipeline.utils.trajectory_baseline import predict_future_position


EARTH_RADIUS_M = 6_371_000.0
METRES_PER_NAUTICAL_MILE = 1_852.0
METRES_TO_FEET = 3.28084
HORIZON_SECONDS = {"1min": 60, "3min": 180, "5min": 300, "10min": 600}
# The true closest point of approach almost never lands on one of the four named
# horizons. Two aircraft passing at t = 240 s used to be recorded at whatever their
# separation happened to be at 180 s and at 300 s -- often well outside threshold --
# and the conflict was silently dropped, capping detection recall. Fifteen seconds
# at a 500 m/s closing speed moves the pair by ~4 NM, which is fine enough to resolve
# a 5 NM threshold.
CPA_GRID_STEP_SECONDS = 15
CPA_GRID_END_SECONDS = 600


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


def cpa_grid_times(step_seconds: int = CPA_GRID_STEP_SECONDS, end_seconds: int = CPA_GRID_END_SECONDS) -> list[int]:
    """The default look-ahead grid: every step_seconds from now to end_seconds inclusive."""
    return list(range(0, int(end_seconds) + 1, int(step_seconds)))


def predict_dense_grid(
    state: Mapping[str, float],
    times_seconds: Sequence[int] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Constant-velocity positions on a dense time grid, keyed by seconds from now.

    This keeps the rule-based conflict path working without the neural model, which
    matters because the CPA rule is the deterministic safety net that stays in place
    alongside any learned detector.
    """
    times = cpa_grid_times() if times_seconds is None else [int(value) for value in times_seconds]
    return {
        seconds: predict_future_position(
            state["latitude"], state["longitude"], state["altitude_m"],
            state["velocity_ms"], state["heading_deg"], state["vertical_rate_ms"], seconds,
        )
        for seconds in times
    }


def _seconds_for_key(key: Any) -> int | None:
    """Resolve a prediction key to seconds, accepting both named horizons and a grid."""
    if key in HORIZON_SECONDS:
        return HORIZON_SECONDS[key]
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


def compute_cpa(aircraft_a_predictions: Mapping[Any, Any], aircraft_b_predictions: Mapping[Any, Any]) -> dict[str, Any]:
    """Find minimum predicted lateral separation over every time both aircraft share.

    Accepts either the four named horizons (as the dashboard still supplies) or a
    dense grid keyed by seconds from predict_dense_grid. Denser input gives a truer
    CPA; the code path is the same.
    """
    times_a = {seconds: key for key in aircraft_a_predictions if (seconds := _seconds_for_key(key)) is not None}
    times_b = {seconds: key for key in aircraft_b_predictions if (seconds := _seconds_for_key(key)) is not None}
    common_times = sorted(set(times_a).intersection(times_b))
    if not common_times:
        raise ValueError("Aircraft predictions have no matching look-ahead times.")

    samples: list[dict[str, float]] = []
    for seconds in common_times:
        lat_a, lon_a, altitude_a = _position(aircraft_a_predictions[times_a[seconds]])
        lat_b, lon_b, altitude_b = _position(aircraft_b_predictions[times_b[seconds]])
        samples.append({
            "horizon_seconds": int(seconds),
            "lateral_distance_nm": haversine_distance_nm(lat_a, lon_a, lat_b, lon_b),
            "vertical_separation_ft": abs(altitude_a - altitude_b) * METRES_TO_FEET,
        })

    cpa = min(samples, key=lambda sample: sample["lateral_distance_nm"])
    # Whether the pair is closing right now, rather than merely close at some point.
    # A pair already separating is a different operational picture from one converging.
    is_converging = len(samples) >= 2 and samples[1]["lateral_distance_nm"] < samples[0]["lateral_distance_nm"]

    # The four named horizons stay available for the dashboard, when they are present.
    per_horizon = {
        label: sample
        for label, seconds in HORIZON_SECONDS.items()
        for sample in samples
        if sample["horizon_seconds"] == seconds
    }
    return {
        "time_to_cpa_seconds": cpa["horizon_seconds"],
        # Retained under its old name so existing callers keep working.
        "cpa_horizon_seconds": cpa["horizon_seconds"],
        "cpa_lateral_distance_nm": cpa["lateral_distance_nm"],
        "cpa_vertical_separation_ft": cpa["vertical_separation_ft"],
        "is_converging": is_converging,
        "grid": samples,
        "per_horizon": per_horizon,
    }


def compute_cpa_from_states(
    state_a: Mapping[str, float],
    state_b: Mapping[str, float],
    times_seconds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Convenience path: two raw aircraft states straight to a dense-grid CPA result."""
    return compute_cpa(predict_dense_grid(state_a, times_seconds), predict_dense_grid(state_b, times_seconds))


def classify_conflict(
    cpa_result: Mapping[str, Any], lateral_threshold_nm: float = 5.0, vertical_threshold_ft: float = 1000.0
) -> dict[str, bool | str]:
    """Apply configurable separation thresholds and the project's severity rules."""
    lateral = float(cpa_result["cpa_lateral_distance_nm"])
    vertical = float(cpa_result["cpa_vertical_separation_ft"])
    cpa_seconds = float(cpa_result.get("time_to_cpa_seconds", cpa_result.get("cpa_horizon_seconds", 0.0)))
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
        # A decreasing range that never crossed the configured threshold is a
        # low-risk convergence; otherwise there is no meaningful convergence. The
        # dense grid answers this directly; the per-horizon fallback covers callers
        # still passing the four named horizons only.
        if "is_converging" in cpa_result:
            converging = bool(cpa_result["is_converging"])
        else:
            distances = [item["lateral_distance_nm"] for item in cpa_result.get("per_horizon", {}).values()]
            converging = len(distances) >= 2 and min(distances[1:]) < distances[0]
        severity = "low" if converging else "none"
    return {"is_conflict": is_conflict, "severity": severity}
