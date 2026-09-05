"""Coordinate and target transformations shared by training, evaluation and inference.

Everything here is deliberately plain numpy on whole arrays: the same functions run
during training, during evaluation, and later inside the backend inference service,
so any drift between those three would silently corrupt predictions.

The central idea is the local frame. Absolute latitude/longitude targets span the
whole collection region (~1.9 degrees of latitude), so 5 NM -- the difference
between a useful prediction and a useless one -- is 4.5% of one standard deviation.
Predicting the *residual from constant velocity*, in metres, in a frame rotated onto
the aircraft's own heading, puts the quantity that matters on the scale that matters.
"""

from __future__ import annotations

import numpy as np


HORIZONS_SECONDS = np.array([60, 180, 300, 600], dtype=np.float64)
METRES_PER_DEGREE = 111320.0
METRES_PER_NAUTICAL_MILE = 1852.0
VABB_LAT, VABB_LON = 19.0887, 72.8679

# Input feature column order produced by preprocess_sequences.py.
LATITUDE, LONGITUDE, ALTITUDE, VELOCITY, SIN_TRACK, COS_TRACK, VERTICAL_RATE, TIME_GAP = range(8)

SEQUENCE_FEATURE_NAMES = [
    "along_track_m", "cross_track_m", "altitude_delta_m",
    "velocity_ms", "vertical_rate_ms", "heading_delta_rad", "time_gap_s",
]
SCALAR_FEATURE_NAMES = [
    "last_altitude_m", "last_velocity_ms", "last_vertical_rate_ms",
    "turn_rate_rad_s", "along_accel_ms2", "vertical_accel_ms2",
    "total_turn_rad", "abs_turn_rate_rad_s", "abs_vertical_rate_ms",
    "distance_to_vabb_km", "sin_relative_bearing_vabb", "cos_relative_bearing_vabb",
    "lateral_accel_proxy",
]


def _last_heading_components(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalised (sin, cos) of the final observed heading, guarding against drift.

    The stored sin/cos pair comes from float32 round-tripping and does not always sum
    to exactly one; renormalising keeps the rotation orthonormal so the round-trip in
    apply_residual is exact.
    """
    sin_heading = X[:, -1, SIN_TRACK].astype(np.float64)
    cos_heading = X[:, -1, COS_TRACK].astype(np.float64)
    magnitude = np.hypot(sin_heading, cos_heading)
    magnitude[magnitude < 1e-9] = 1.0
    return sin_heading / magnitude, cos_heading / magnitude


def _rotate_to_local(north_m: np.ndarray, east_m: np.ndarray, sin_heading: np.ndarray, cos_heading: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotate a north/east offset onto the aircraft's heading: +x ahead, +y to the right."""
    along = north_m * cos_heading + east_m * sin_heading
    cross = -north_m * sin_heading + east_m * cos_heading
    return along, cross


def _rotate_from_local(along_m: np.ndarray, cross_m: np.ndarray, sin_heading: np.ndarray, cos_heading: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Exact inverse of _rotate_to_local."""
    north = along_m * cos_heading - cross_m * sin_heading
    east = along_m * sin_heading + cross_m * cos_heading
    return north, east


def constant_velocity_predict(X: np.ndarray) -> np.ndarray:
    """Extrapolate the last observed state at constant speed, heading and vertical rate.

    Equirectangular rather than great-circle: over a ten-minute airliner displacement
    the two agree to well under a metre, and this form stays fully vectorised.
    """
    last_latitude = X[:, -1, LATITUDE].astype(np.float64)
    last_longitude = X[:, -1, LONGITUDE].astype(np.float64)
    last_altitude = X[:, -1, ALTITUDE].astype(np.float64)
    velocity = X[:, -1, VELOCITY].astype(np.float64)
    vertical_rate = X[:, -1, VERTICAL_RATE].astype(np.float64)
    sin_heading, cos_heading = _last_heading_components(X)

    times = HORIZONS_SECONDS[None, :]
    distance_m = velocity[:, None] * times
    north_m = distance_m * cos_heading[:, None]
    east_m = distance_m * sin_heading[:, None]

    predicted = np.empty((len(X), len(HORIZONS_SECONDS), 3), dtype=np.float64)
    predicted[..., 0] = last_latitude[:, None] + north_m / METRES_PER_DEGREE
    predicted[..., 1] = last_longitude[:, None] + east_m / (METRES_PER_DEGREE * np.cos(np.radians(last_latitude))[:, None])
    predicted[..., 2] = last_altitude[:, None] + vertical_rate[:, None] * times
    return predicted


def to_local_features(X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Re-express each input window relative to its own final state.

    Returns (sequence, scalars) with shapes (N, 10, 7) and (N, 13). See
    SEQUENCE_FEATURE_NAMES and SCALAR_FEATURE_NAMES for the column order.
    """
    latitudes = X[:, :, LATITUDE].astype(np.float64)
    longitudes = X[:, :, LONGITUDE].astype(np.float64)
    altitudes = X[:, :, ALTITUDE].astype(np.float64)
    velocities = X[:, :, VELOCITY].astype(np.float64)
    vertical_rates = X[:, :, VERTICAL_RATE].astype(np.float64)
    time_gaps = X[:, :, TIME_GAP].astype(np.float64)

    last_latitude = latitudes[:, -1:]
    last_longitude = longitudes[:, -1:]
    last_altitude = altitudes[:, -1:]
    sin_heading, cos_heading = _last_heading_components(X)

    north_m = (latitudes - last_latitude) * METRES_PER_DEGREE
    east_m = (longitudes - last_longitude) * METRES_PER_DEGREE * np.cos(np.radians(last_latitude))
    along_m, cross_m = _rotate_to_local(north_m, east_m, sin_heading[:, None], cos_heading[:, None])

    # Unwrap before differencing: without this a 359 -> 001 crossing reads as a
    # 358 degree turn and the turn-rate features become nonsense on exactly the
    # north-bound traffic they are supposed to describe.
    headings = np.unwrap(np.arctan2(X[:, :, SIN_TRACK].astype(np.float64), X[:, :, COS_TRACK].astype(np.float64)), axis=1)
    heading_delta = headings - headings[:, -1:]

    sequence = np.stack(
        (along_m, cross_m, altitudes - last_altitude, velocities, vertical_rates, heading_delta, time_gaps),
        axis=-1,
    )

    # The first gap in each window is zero by construction, so the span is the sum
    # over the remaining steps. Floored at one second so a degenerate window cannot
    # divide by zero.
    window_span = np.maximum(time_gaps[:, 1:].sum(axis=1), 1.0)
    total_turn = headings[:, -1] - headings[:, 0]
    turn_rate = total_turn / window_span
    along_accel = (velocities[:, -1] - velocities[:, 0]) / window_span
    vertical_accel = (vertical_rates[:, -1] - vertical_rates[:, 0]) / window_span

    north_to_vabb = (VABB_LAT - latitudes[:, -1]) * METRES_PER_DEGREE
    east_to_vabb = (VABB_LON - longitudes[:, -1]) * METRES_PER_DEGREE * np.cos(np.radians(latitudes[:, -1]))
    # Bearing to the field expressed in the aircraft's own frame, so "the airport is
    # ahead of me" is one value regardless of which compass heading that happens to be.
    along_to_vabb, cross_to_vabb = _rotate_to_local(north_to_vabb, east_to_vabb, sin_heading, cos_heading)
    distance_to_vabb = np.hypot(north_to_vabb, east_to_vabb)
    safe_distance = np.maximum(distance_to_vabb, 1.0)

    scalars = np.stack((
        altitudes[:, -1], velocities[:, -1], vertical_rates[:, -1],
        turn_rate, along_accel, vertical_accel,
        total_turn, np.abs(turn_rate), np.abs(vertical_rates[:, -1]),
        distance_to_vabb / 1000.0,
        cross_to_vabb / safe_distance, along_to_vabb / safe_distance,
        turn_rate * velocities[:, -1],
    ), axis=-1)

    return sequence.astype(np.float64), scalars.astype(np.float64)


def residual_targets(X: np.ndarray, y: np.ndarray, cv: np.ndarray) -> np.ndarray:
    """Truth minus constant velocity, in metres, in the local frame: (along, cross, altitude)."""
    sin_heading, cos_heading = _last_heading_components(X)
    reference_latitude = X[:, -1, LATITUDE].astype(np.float64)

    north_m = (y[..., 0].astype(np.float64) - cv[..., 0]) * METRES_PER_DEGREE
    east_m = (y[..., 1].astype(np.float64) - cv[..., 1]) * METRES_PER_DEGREE * np.cos(np.radians(reference_latitude))[:, None]
    along_m, cross_m = _rotate_to_local(north_m, east_m, sin_heading[:, None], cos_heading[:, None])

    residual = np.empty_like(cv)
    residual[..., 0] = along_m
    residual[..., 1] = cross_m
    residual[..., 2] = y[..., 2].astype(np.float64) - cv[..., 2]
    return residual


def apply_residual(X: np.ndarray, cv: np.ndarray, residual: np.ndarray) -> np.ndarray:
    """Exact inverse of residual_targets: local-frame residual -> absolute lat/lon/altitude."""
    sin_heading, cos_heading = _last_heading_components(X)
    reference_latitude = X[:, -1, LATITUDE].astype(np.float64)

    north_m, east_m = _rotate_from_local(residual[..., 0], residual[..., 1], sin_heading[:, None], cos_heading[:, None])

    predicted = np.empty_like(cv)
    predicted[..., 0] = cv[..., 0] + north_m / METRES_PER_DEGREE
    predicted[..., 1] = cv[..., 1] + east_m / (METRES_PER_DEGREE * np.cos(np.radians(reference_latitude))[:, None])
    predicted[..., 2] = cv[..., 2] + residual[..., 2]
    return predicted


def error_nm(predicted: np.ndarray, actual: np.ndarray) -> np.ndarray:
    """Horizontal position error in nautical miles, shape (N, 4)."""
    latitude_scale = np.cos(np.radians(actual[..., 0].astype(np.float64)))
    north_m = (predicted[..., 0] - actual[..., 0].astype(np.float64)) * METRES_PER_DEGREE
    east_m = (predicted[..., 1] - actual[..., 1].astype(np.float64)) * METRES_PER_DEGREE * latitude_scale
    return np.hypot(north_m, east_m) / METRES_PER_NAUTICAL_MILE


def error_along_cross_nm(X: np.ndarray, predicted: np.ndarray, actual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Signed along-track and cross-track error in NM, each shape (N, 4).

    Cross-track is the safety-relevant one: an aircraft that is late along its own
    route is still on it, whereas one displaced sideways is somewhere it should not be.
    """
    sin_heading, cos_heading = _last_heading_components(X)
    latitude_scale = np.cos(np.radians(actual[..., 0].astype(np.float64)))
    north_m = (predicted[..., 0] - actual[..., 0].astype(np.float64)) * METRES_PER_DEGREE
    east_m = (predicted[..., 1] - actual[..., 1].astype(np.float64)) * METRES_PER_DEGREE * latitude_scale
    along_m, cross_m = _rotate_to_local(north_m, east_m, sin_heading[:, None], cos_heading[:, None])
    return along_m / METRES_PER_NAUTICAL_MILE, cross_m / METRES_PER_NAUTICAL_MILE
