"""Build conflict-classifier training data from PAIRED REAL trajectories.

WHAT CHANGED AND WHY (the circular-label defect, fixed).

The previous version of this file took one real aircraft, INVENTED a second aircraft
beside it, extrapolated both in a straight line, and then labelled the pair by
applying the separation rule to that extrapolation. Two of the nine features handed
to the classifier were the extrapolated closest-approach distances, and the label was

    is_conflict = predicted_lateral < 5 NM and predicted_vertical < 1000 ft

so the label was a function of two of the inputs. Measured on the file it produced:
the label was reproducible from those two features alone for 40,000 of 40,000 rows,
exactly 100%. The classifier scored a perfect PR-AUC of 1.0 because it was
rediscovering an if-statement it had been handed. It could not learn anything, and
every number reported about it -- recall, precision, warning time -- described the
arithmetic rather than a model.

The fix is a different question, not a different model:

    FEATURES come from what we PREDICT at decision time.
    The LABEL comes from where the aircraft ACTUALLY went.

That requires both aircraft to be real, because an invented aircraft has no real
future to check against -- its only future is the straight line we drew for it, which
is what made the old setup circular by construction. So both aircraft here are real
recorded flights with a real observed ten-minute future.

The pairing is still synthetic, exactly as Section 9 of CLAUDE.md requires: real
losses of separation are vanishingly rare, so the INTRODUCTION between two aircraft
has to be manufactured. The FLYING does not. Aircraft B's whole future track is moved
and rotated as one rigid piece, which preserves its real turns, climbs, descents and
speed changes exactly. It is a real flight path, relocated -- never an invented one.

What the model can now learn, which it could not before: where OUR OWN PREDICTIONS
go wrong. A predicted 6 NM miss between two aircraft turning near the airport is far
less trustworthy than a predicted 6 NM miss between two aircraft cruising straight,
and the features carry the evidence for that distinction (turn rate, vertical
acceleration, distance to the field). That is a real contribution on top of the
geometry, and it is the layered arrangement certified systems use: a deterministic
safety net, with a learned layer above it.

SECOND FIX, INDEPENDENT: encounters must DEVELOP.

45.5% of scenarios in the old file had their closest approach at t = 0, meaning the
two aircraft were already as close as they would ever get at the moment we first saw
them. There is no warning to give in that situation and nothing a controller could
do, which made every warning-time figure meaningless -- and warning time is the
headline metric of this project. Any pair already inside the alert volume at t = 0 is
now rejected and resampled, so every conflict in this dataset is one that develops
while being watched.

Run: venv/Scripts/python.exe ml_pipeline/training/conflict_classifier/generate_synthetic_scenarios.py
"""

from __future__ import annotations

import glob
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


# FLIGHT_RIGHT_N_SCENARIOS exists so the smoke test can run this file end to end in
# seconds; leave it unset for a real run.
N_SCENARIOS = int(os.environ.get("FLIGHT_RIGHT_N_SCENARIOS", 40_000))
# The share of pairs we deliberately aim at each other. It is higher than the old
# 0.30 because aiming no longer guarantees a conflict: B is aimed using only what is
# knowable at t = 0, and whether the pair actually loses separation depends on what
# both aircraft really did afterwards. That gap between intent and outcome IS the
# learning problem, so we over-generate intent to end up with enough positives.
INTENDED_ENCOUNTER_RATIO = 0.55
RANDOM_SEED = 42

EARTH_RADIUS_M = 6_371_000.0
NM_TO_M = 1_852.0
M_TO_FT = 3.28084
METRES_PER_DEGREE = 111_320.0

# The label needs a complete real future for BOTH aircraft, on the same dense grid
# the rule-based detector uses. 15 s from 0 to 600 s is 41 points.
GRID_STEP_SECONDS = 15
GRID_END_SECONDS = 600
GRID_TIMES = np.arange(0, GRID_END_SECONDS + 1, GRID_STEP_SECONDS, dtype=np.int64)

# Real observations must bracket every grid point this closely, otherwise the
# "actual" future is being invented by interpolation rather than measured.
MAX_INTERPOLATION_GAP_SECONDS = 120
# Past states needed to describe how the aircraft is manoeuvring right now. These
# feed the trust features -- turn rate, accelerations -- that let the model judge
# how reliable the straight-line prediction is.
PAST_STEPS = 10
MAX_TRACK_GAP_SECONDS = 600
SESSION_BREAK_SECONDS = 1800

# En-route only, per the 30 Aug decision: the 5 NM / 1000 ft rule is an en-route
# standard, and arrivals are legitimately closer than that because approach
# sequencing separates them instead. Feeding approach traffic in trains the model to
# flag routine landings.
MIN_ALTITUDE_FT = 10_000.0
MIN_VELOCITY_MS = 50.0

# Geometry of the manufactured introduction.
NATURAL_OFFSET_NM = (6.0, 45.0)
NATURAL_ALTITUDE_OFFSET_FT = (-4000.0, 4000.0)
INTENDED_ALTITUDE_OFFSET_FT = (-1100.0, 1100.0)
# Aim B at where A is PREDICTED to be at this time, never at where A actually goes.
# Using A's real future to place B would manufacture a correlation between "A turned"
# and "conflict", which is an artifact of the generator rather than a fact about
# traffic. Aiming with only t = 0 knowledge lets a real deviation push the pair
# either into or out of conflict, which is the honest situation.
INTENDED_MEETING_TIME_RANGE = (180.0, 600.0)
# Aim error, in degrees of bearing. Kept small on purpose: at a 40 NM approach
# distance even 12 degrees throws B about 8 NM wide, which suppressed almost every
# intended encounter in a trial run. The uncertainty this dataset is meant to carry
# must come from what the aircraft REALLY did afterwards, not from a sloppy setup.
INTENDED_AIM_JITTER_DEG = 2.0
MAX_RESAMPLE_ATTEMPTS = 12
# Cap on how many anchors are held in memory; pairs are drawn from these with reuse.
MAX_ANCHORS = 60_000

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# Data lives under the project root unless FLIGHT_RIGHT_DATA_ROOT points elsewhere
# (the smoke test uses a temporary directory so it can never touch real data).
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
RAW_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "raw"
SYNTHETIC_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "synthetic"

# Single source of truth for prediction and for closest-approach geometry. Both the
# FEATURE side (constant-velocity prediction) and the LABEL side (real positions) are
# put through the same audited functions, so the two cannot drift apart.
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    ALERT_LATERAL_NM,
    ALERT_VERTICAL_FT,
    SEPARATION_LATERAL_NM,
    SEPARATION_VERTICAL_FT,
    classify_conflict,
    compute_cpa,
    compute_cpa_from_states,
)

RNG = np.random.default_rng(RANDOM_SEED)
VABB_LAT, VABB_LON = 19.0887, 72.8679

# Features the classifier is allowed to see. Every one is computable at t = 0 from
# observation and from the constant-velocity prediction. NOTHING here is derived from
# the future positions that produce the label -- that separation is the entire point
# of this rewrite, and train_xgboost.py re-checks it before training.
FEATURE_COLUMNS = [
    # What we can see right now.
    "current_lateral_separation_nm",
    "current_vertical_separation_ft",
    "relative_speed_ms",
    "relative_heading_deg",
    "closing_speed_ms",
    "vertical_convergence_rate_ms",
    # What the straight-line prediction says will happen.
    "predicted_cpa_lateral_nm",
    "predicted_cpa_vertical_ft",
    "predicted_time_to_cpa_seconds",
    "predicted_is_converging",
    # How much that prediction can be trusted. A straight-line prediction is exact
    # for an aircraft flying straight and level, and worthless for one in a turn.
    "max_abs_turn_rate_deg_s",
    "a_abs_turn_rate_deg_s",
    "b_abs_turn_rate_deg_s",
    "a_abs_vertical_rate_ms",
    "b_abs_vertical_rate_ms",
    "a_abs_vertical_accel_ms2",
    "b_abs_vertical_accel_ms2",
    "a_abs_along_accel_ms2",
    "b_abs_along_accel_ms2",
    "min_distance_to_vabb_nm",
    "a_altitude_ft",
    "b_altitude_ft",
    "a_velocity_ms",
    "b_velocity_ms",
]

# Recorded for analysis and for warning-time reporting. NEVER given to the model.
OUTCOME_COLUMNS = [
    "actual_cpa_lateral_nm",
    "actual_cpa_vertical_ft",
    "actual_time_to_cpa_seconds",
    "is_conflict",
    "severity",
]


def load_valid_states() -> pd.DataFrame:
    """Read every raw parquet and keep en-route airborne states only."""
    paths = sorted(glob.glob(str(RAW_DIRECTORY / "*.parquet")))
    if not paths:
        raise FileNotFoundError(f"No raw parquet files found in {RAW_DIRECTORY}.")
    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    required = ["icao24", "time_position", "on_ground", "latitude", "longitude",
                "baro_altitude", "velocity", "true_track"]
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"Raw files are missing columns: {sorted(missing)}")
    if "vertical_rate" not in frame:
        frame["vertical_rate"] = 0.0

    total = len(frame)
    frame = frame.loc[(frame["on_ground"] == False) & frame[required].notna().all(axis=1)].copy()  # noqa: E712
    frame["vertical_rate"] = frame["vertical_rate"].fillna(0.0)
    airborne = len(frame)
    frame = frame.loc[
        (frame["baro_altitude"] * M_TO_FT >= MIN_ALTITUDE_FT)
        & (frame["velocity"] > MIN_VELOCITY_MS)
    ]
    print("Raw state filtering")
    print(f"  rows loaded from {len(paths)} parquet file(s):        {total:>9,}")
    print(f"  airborne with no missing fields:                {airborne:>9,}  ({airborne / total:6.1%})")
    print(f"  en-route (>= {MIN_ALTITUDE_FT:,.0f} ft, > {MIN_VELOCITY_MS:.0f} m/s):    {len(frame):>9,}  ({len(frame) / total:6.1%})")
    if frame.empty:
        raise ValueError("No en-route states remain after filtering.")
    return frame.sort_values(["icao24", "time_position"]).reset_index(drop=True)


def _dense_future(times: np.ndarray, latitudes: np.ndarray, longitudes: np.ndarray,
                  altitudes: np.ndarray, anchor_index: int) -> np.ndarray | None:
    """Real observed positions on the 15 s grid, or None if the track does not cover it.

    Every grid point must sit between two real observations no more than
    MAX_INTERPOLATION_GAP_SECONDS apart. Nothing is extrapolated past the end of a
    track: if the aircraft stops being observed before ten minutes are up, this anchor
    is discarded rather than guessed at. That is what makes the label a measurement.
    """
    target_times = times[anchor_index] + GRID_TIMES
    if target_times[-1] > times[-1]:
        return None
    after = np.searchsorted(times, target_times, side="left")
    before = np.maximum(after - 1, 0)
    exact = (after < times.size) & (times[np.minimum(after, times.size - 1)] == target_times)
    spans = times[np.minimum(after, times.size - 1)] - times[before]
    if np.any((~exact) & (spans > MAX_INTERPOLATION_GAP_SECONDS)):
        return None
    future = np.empty((GRID_TIMES.size, 3), dtype=np.float64)
    for column, values in enumerate((latitudes, longitudes, altitudes)):
        future[:, column] = np.interp(target_times, times, values)
    return future


def build_anchors(states: pd.DataFrame) -> dict[str, np.ndarray]:
    """Every point in the data where an aircraft has both a past and a full real future.

    An anchor is one aircraft at one moment, carrying the state we would see at
    decision time, the manoeuvre summary describing how it is flying, and the real
    positions it went on to occupy over the next ten minutes.
    """
    anchor_rows: list[tuple] = []
    futures: list[np.ndarray] = []

    for _, whole_track in states.groupby("icao24", sort=False):
        whole_track = whole_track.drop_duplicates("time_position", keep="last")
        times_all = whole_track["time_position"].to_numpy(dtype=np.int64)
        cuts = np.flatnonzero(np.diff(times_all) > MAX_TRACK_GAP_SECONDS) + 1
        for segment in np.split(np.arange(len(whole_track)), cuts):
            if len(segment) < PAST_STEPS + 2:
                continue
            track = whole_track.iloc[segment]
            times = track["time_position"].to_numpy(dtype=np.int64)
            latitudes = track["latitude"].to_numpy(dtype=np.float64)
            longitudes = track["longitude"].to_numpy(dtype=np.float64)
            altitudes = track["baro_altitude"].to_numpy(dtype=np.float64)
            velocities = track["velocity"].to_numpy(dtype=np.float64)
            headings = track["true_track"].to_numpy(dtype=np.float64)
            vertical_rates = track["vertical_rate"].to_numpy(dtype=np.float64)
            # Unwrapped so a 359 -> 001 degree crossing reads as a 2 degree turn
            # rather than a 358 degree one, which would make the turn-rate feature
            # nonsense for exactly the northbound traffic it describes.
            unwrapped = np.unwrap(np.deg2rad(headings))

            for index in range(PAST_STEPS - 1, len(track)):
                future = _dense_future(times, latitudes, longitudes, altitudes, index)
                if future is None:
                    continue
                window = slice(index - PAST_STEPS + 1, index + 1)
                span = max(float(times[index] - times[index - PAST_STEPS + 1]), 1.0)
                turn_rate = math.degrees(unwrapped[index] - unwrapped[index - PAST_STEPS + 1]) / span
                along_accel = (velocities[index] - velocities[index - PAST_STEPS + 1]) / span
                vertical_accel = (vertical_rates[index] - vertical_rates[index - PAST_STEPS + 1]) / span
                anchor_rows.append((
                    int(times[index]), latitudes[index], longitudes[index], altitudes[index],
                    velocities[index], headings[index] % 360.0, vertical_rates[index],
                    turn_rate, along_accel, vertical_accel,
                ))
                futures.append(future)

    if not anchor_rows:
        raise ValueError("No anchor had a complete ten-minute observed future.")

    columns = ["time", "latitude", "longitude", "altitude_m", "velocity_ms",
               "heading_deg", "vertical_rate_ms", "turn_rate_deg_s",
               "along_accel_ms2", "vertical_accel_ms2"]
    table = {name: np.asarray([row[i] for row in anchor_rows], dtype=np.float64)
             for i, name in enumerate(columns)}
    table["time"] = table["time"].astype(np.int64)
    table["future"] = np.stack(futures)

    order = np.argsort(table["time"])
    table = {key: value[order] for key, value in table.items()}
    table["session_id"] = np.concatenate(
        ([0], np.cumsum(np.diff(table["time"]) > SESSION_BREAK_SECONDS))
    )

    if len(table["time"]) > MAX_ANCHORS:
        keep = np.sort(RNG.choice(len(table["time"]), size=MAX_ANCHORS, replace=False))
        table = {key: value[keep] for key, value in table.items()}

    print("")
    print(f"Anchors with a complete real ten-minute future: {len(table['time']):,} "
          f"across {len(np.unique(table['session_id']))} collection session(s)")
    return table


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from the first point to the second, degrees clockwise from north."""
    d_lon = math.radians(lon2 - lon1)
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    y = math.sin(d_lon) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    return math.degrees(math.atan2(y, x)) % 360.0


def _offset_position(latitude: float, longitude: float, bearing_deg: float,
                     distance_m: float) -> tuple[float, float]:
    """Point reached by travelling a bearing and distance, equirectangular."""
    bearing = math.radians(bearing_deg)
    latitude_out = latitude + (distance_m * math.cos(bearing)) / METRES_PER_DEGREE
    longitude_out = longitude + (distance_m * math.sin(bearing)) / (
        METRES_PER_DEGREE * math.cos(math.radians(latitude))
    )
    return latitude_out, longitude_out


def transform_track(future: np.ndarray, anchor_latitude: float, anchor_longitude: float,
                    rotation_deg: float, new_latitude: float, new_longitude: float,
                    altitude_offset_m: float) -> np.ndarray:
    """Move and rotate a real future track as one rigid piece.

    This is the step that keeps the flying real. The track is converted to metres
    relative to its own starting point, rotated about that point, and re-anchored
    somewhere else. Rotation and translation preserve every distance and angle inside
    the track, so the aircraft's real turns, climbs, descents and speed changes
    survive untouched -- only where it happens to be, and which way it is pointing,
    change. Nothing about the flight path is invented.
    """
    north = (future[:, 0] - anchor_latitude) * METRES_PER_DEGREE
    east = (future[:, 1] - anchor_longitude) * METRES_PER_DEGREE * math.cos(math.radians(anchor_latitude))
    rotation = math.radians(rotation_deg)
    # Clockwise in compass terms, so every bearing inside the track gains rotation_deg.
    rotated_north = north * math.cos(rotation) - east * math.sin(rotation)
    rotated_east = east * math.cos(rotation) + north * math.sin(rotation)

    moved = np.empty_like(future)
    moved[:, 0] = new_latitude + rotated_north / METRES_PER_DEGREE
    moved[:, 1] = new_longitude + rotated_east / (
        METRES_PER_DEGREE * math.cos(math.radians(new_latitude))
    )
    moved[:, 2] = future[:, 2] + altitude_offset_m
    return moved


def _state(anchors: dict[str, np.ndarray], index: int, latitude: float | None = None,
           longitude: float | None = None, heading: float | None = None,
           altitude_m: float | None = None) -> dict[str, float]:
    """The decision-time state of one anchor, optionally relocated."""
    return {
        "latitude": float(anchors["latitude"][index] if latitude is None else latitude),
        "longitude": float(anchors["longitude"][index] if longitude is None else longitude),
        "altitude_m": float(anchors["altitude_m"][index] if altitude_m is None else altitude_m),
        "velocity_ms": float(anchors["velocity_ms"][index]),
        "heading_deg": float(anchors["heading_deg"][index] if heading is None else heading) % 360.0,
        "vertical_rate_ms": float(anchors["vertical_rate_ms"][index]),
    }


def _as_grid(track: np.ndarray) -> dict[int, tuple[float, float, float]]:
    """Positions keyed by seconds from now, the shape compute_cpa consumes."""
    return {int(seconds): (float(track[i, 0]), float(track[i, 1]), float(track[i, 2]))
            for i, seconds in enumerate(GRID_TIMES)}


def _relative_motion(state_a: dict[str, float], state_b: dict[str, float]) -> tuple[float, float, float]:
    """Relative speed, folded heading difference, and radial closing speed."""
    heading_a, heading_b = math.radians(state_a["heading_deg"]), math.radians(state_b["heading_deg"])
    velocity_a = np.array([state_a["velocity_ms"] * math.sin(heading_a),
                           state_a["velocity_ms"] * math.cos(heading_a)])
    velocity_b = np.array([state_b["velocity_ms"] * math.sin(heading_b),
                           state_b["velocity_ms"] * math.cos(heading_b)])
    relative_speed = float(np.linalg.norm(velocity_b - velocity_a))
    heading_difference = abs((state_b["heading_deg"] - state_a["heading_deg"] + 180) % 360 - 180)
    mean_latitude = math.radians((state_a["latitude"] + state_b["latitude"]) / 2)
    displacement = np.array([
        math.radians(state_b["longitude"] - state_a["longitude"]) * EARTH_RADIUS_M * math.cos(mean_latitude),
        math.radians(state_b["latitude"] - state_a["latitude"]) * EARTH_RADIUS_M,
    ])
    norm = float(np.linalg.norm(displacement))
    if norm < 1.0:
        return relative_speed, heading_difference, 0.0
    closing_speed = float(-np.dot(velocity_b - velocity_a, displacement / norm))
    return relative_speed, heading_difference, closing_speed


def _distance_to_vabb_nm(latitude: float, longitude: float) -> float:
    north = (VABB_LAT - latitude) * METRES_PER_DEGREE
    east = (VABB_LON - longitude) * METRES_PER_DEGREE * math.cos(math.radians(latitude))
    return float(math.hypot(north, east) / NM_TO_M)


def _place_second_aircraft(anchors: dict[str, np.ndarray], index_a: int, index_b: int,
                           intended: bool) -> tuple[float, float, float]:
    """Choose where aircraft B starts and which way it points.

    For an intended encounter, B is placed so that flying straight would bring it to
    the point where A is PREDICTED to be at some moment between three and ten minutes
    from now, arriving at roughly that same moment. Only t = 0 knowledge is used: A's
    real future is never consulted. Whether the encounter actually materialises then
    depends on what both aircraft really did, which is the thing being learned.
    """
    state_a = _state(anchors, index_a)
    if not intended:
        bearing = float(RNG.uniform(0.0, 360.0))
        distance_nm = float(RNG.uniform(*NATURAL_OFFSET_NM))
        latitude, longitude = _offset_position(
            state_a["latitude"], state_a["longitude"], bearing, distance_nm * NM_TO_M
        )
        return latitude, longitude, float(RNG.uniform(0.0, 360.0))

    meeting_time = float(RNG.uniform(*INTENDED_MEETING_TIME_RANGE))
    meeting_latitude, meeting_longitude = _offset_position(
        state_a["latitude"], state_a["longitude"], state_a["heading_deg"],
        state_a["velocity_ms"] * meeting_time,
    )
    # Put B on a circle around the meeting point whose radius is how far B travels in
    # that time, so both aircraft reach the point together rather than merely crossing.
    radius_m = float(anchors["velocity_ms"][index_b]) * meeting_time
    approach_bearing = float(RNG.uniform(0.0, 360.0))
    latitude, longitude = _offset_position(
        meeting_latitude, meeting_longitude, approach_bearing, radius_m
    )
    heading = _bearing_deg(latitude, longitude, meeting_latitude, meeting_longitude)
    heading += float(RNG.normal(0.0, INTENDED_AIM_JITTER_DEG))
    return latitude, longitude, heading % 360.0


def build_dataset(anchors: dict[str, np.ndarray], n_scenarios: int = N_SCENARIOS) -> pd.DataFrame:
    """Generate encounters: predicted features, real-outcome labels."""
    sessions = anchors["session_id"]
    by_session = {int(session): np.flatnonzero(sessions == session)
                  for session in np.unique(sessions)}
    # Pairing within a session keeps each collection block self-contained, so the
    # later time-based split cannot put one aircraft's real track on both sides.
    usable = {key: value for key, value in by_session.items() if len(value) >= 2}
    if not usable:
        raise ValueError("No collection session contains two usable anchors.")
    session_keys = np.array(sorted(usable))
    session_weights = np.array([len(usable[int(key)]) for key in session_keys], dtype=np.float64)
    session_weights /= session_weights.sum()

    intents = np.zeros(n_scenarios, dtype=bool)
    intents[: int(round(n_scenarios * INTENDED_ENCOUNTER_RATIO))] = True
    RNG.shuffle(intents)

    rows: list[dict] = []
    rejected_already_close = 0

    for intended in intents:
        session = int(RNG.choice(session_keys, p=session_weights))
        pool = usable[session]
        row = None
        for _ in range(MAX_RESAMPLE_ATTEMPTS):
            index_a, index_b = RNG.choice(pool, size=2, replace=False)
            candidate = _try_build_row(anchors, int(index_a), int(index_b), bool(intended))
            if candidate is not None:
                row = candidate
                break
            rejected_already_close += 1
        if row is not None:
            rows.append(row)

    print("")
    print(f"Scenarios kept: {len(rows):,} of {n_scenarios:,} attempted")
    print(f"Rejected for being inside the alert volume at t = 0 (no warning to give): "
          f"{rejected_already_close:,}")
    return pd.DataFrame(rows)


def _try_build_row(anchors: dict[str, np.ndarray], index_a: int, index_b: int,
                   intended: bool) -> dict | None:
    """One encounter, or None if the pair starts too close to be a developing one."""
    latitude_b, longitude_b, heading_b = _place_second_aircraft(anchors, index_a, index_b, intended)
    altitude_range = INTENDED_ALTITUDE_OFFSET_FT if intended else NATURAL_ALTITUDE_OFFSET_FT
    altitude_offset_m = float(RNG.uniform(*altitude_range)) / M_TO_FT
    altitude_b = float(anchors["altitude_m"][index_b]) + altitude_offset_m

    state_a = _state(anchors, index_a)
    state_b = _state(anchors, index_b, latitude_b, longitude_b, heading_b, altitude_b)

    rotation = heading_b - float(anchors["heading_deg"][index_b])
    actual_a = anchors["future"][index_a]
    actual_b = transform_track(
        anchors["future"][index_b],
        float(anchors["latitude"][index_b]), float(anchors["longitude"][index_b]),
        rotation, latitude_b, longitude_b, altitude_offset_m,
    )

    # THE FEATURES: what the straight-line prediction says, from t = 0 knowledge only.
    predicted_cpa = compute_cpa_from_states(state_a, state_b)
    # Separation right now, taken from the PREDICTED grid rather than the real one.
    # At t = 0 the two are the same number, because the prediction starts from the
    # observation -- but sourcing it here keeps every feature provably free of any
    # contact with the future positions that produce the label.
    first = predicted_cpa["grid"][0]
    # Reject encounters that are already at their closest when we first see them.
    # There is no warning to give and nothing a controller could do, and including
    # them is what made the old warning-time figures meaningless.
    if (first["lateral_distance_nm"] < ALERT_LATERAL_NM
            and first["vertical_separation_ft"] < ALERT_VERTICAL_FT):
        return None

    # THE LABEL: closest approach between the two REAL tracks, through the same
    # audited CPA function the rule-based detector uses.
    actual_cpa = compute_cpa(_as_grid(actual_a), _as_grid(actual_b))
    classification = classify_conflict(actual_cpa)

    manoeuvre_a = _manoeuvre(anchors, index_a)
    manoeuvre_b = _manoeuvre(anchors, index_b)
    row = {
        "seed_time_position": int(anchors["time"][index_a]),
        "session_id": int(anchors["session_id"][index_a]),
        "intended_encounter": bool(intended),
    }
    row.update(encounter_features(state_a, state_b, manoeuvre_a, manoeuvre_b, predicted_cpa))
    row.update({
        # --- outcome, never a feature ---
        "actual_cpa_lateral_nm": float(actual_cpa["cpa_lateral_distance_nm"]),
        "actual_cpa_vertical_ft": float(actual_cpa["cpa_vertical_separation_ft"]),
        "actual_time_to_cpa_seconds": float(actual_cpa["time_to_cpa_seconds"]),
        "is_conflict": int(classification["is_conflict"]),
        "severity": str(classification["severity"]),
    })
    return row


def _manoeuvre(anchors: dict[str, np.ndarray], index: int) -> dict[str, float]:
    """The three window-summary numbers describing how an anchor aircraft is flying."""
    return {
        "turn_rate_deg_s": float(anchors["turn_rate_deg_s"][index]),
        "along_accel_ms2": float(anchors["along_accel_ms2"][index]),
        "vertical_accel_ms2": float(anchors["vertical_accel_ms2"][index]),
    }


def manoeuvre_summary(times: np.ndarray, velocities: np.ndarray, headings_deg: np.ndarray,
                      vertical_rates: np.ndarray) -> dict[str, float]:
    """Turn rate and accelerations over a window of past states, oldest first.

    This is the same arithmetic build_anchors uses, exposed so the backend can compute
    the manoeuvre summary for a live aircraft from its recent history and hand it to
    encounter_features. Headings are unwrapped before differencing (359 -> 001 is a
    2 degree turn, not 358).
    """
    if len(times) < 2:
        return {"turn_rate_deg_s": 0.0, "along_accel_ms2": 0.0, "vertical_accel_ms2": 0.0}
    span = max(float(times[-1] - times[0]), 1.0)
    unwrapped = np.unwrap(np.deg2rad(np.asarray(headings_deg, dtype=np.float64)))
    return {
        "turn_rate_deg_s": math.degrees(unwrapped[-1] - unwrapped[0]) / span,
        "along_accel_ms2": (float(velocities[-1]) - float(velocities[0])) / span,
        "vertical_accel_ms2": (float(vertical_rates[-1]) - float(vertical_rates[0])) / span,
    }


def encounter_features(state_a: dict[str, float], state_b: dict[str, float],
                       manoeuvre_a: dict[str, float], manoeuvre_b: dict[str, float],
                       predicted_cpa: dict | None = None) -> dict[str, float]:
    """The FEATURE_COLUMNS for one pair of aircraft, from t = 0 knowledge only.

    This is the single definition of the classifier's inputs. The training generator
    calls it for every synthetic encounter, and the backend (server/app/ml/inference.py)
    calls it for every live pair, so the two can never disagree about what a feature
    means. Nothing here touches any future position.
    """
    if predicted_cpa is None:
        predicted_cpa = compute_cpa_from_states(state_a, state_b)
    first = predicted_cpa["grid"][0]
    relative_speed, relative_heading, closing_speed = _relative_motion(state_a, state_b)
    features = {
        "current_lateral_separation_nm": float(first["lateral_distance_nm"]),
        "current_vertical_separation_ft": float(first["vertical_separation_ft"]),
        "relative_speed_ms": relative_speed,
        "relative_heading_deg": relative_heading,
        "closing_speed_ms": closing_speed,
        "vertical_convergence_rate_ms": abs(state_b["vertical_rate_ms"] - state_a["vertical_rate_ms"]),
        "predicted_cpa_lateral_nm": float(predicted_cpa["cpa_lateral_distance_nm"]),
        "predicted_cpa_vertical_ft": float(predicted_cpa["cpa_vertical_separation_ft"]),
        "predicted_time_to_cpa_seconds": float(predicted_cpa["time_to_cpa_seconds"]),
        "predicted_is_converging": int(bool(predicted_cpa["is_converging"])),
        "max_abs_turn_rate_deg_s": float(max(abs(manoeuvre_a["turn_rate_deg_s"]),
                                             abs(manoeuvre_b["turn_rate_deg_s"]))),
        "a_abs_turn_rate_deg_s": float(abs(manoeuvre_a["turn_rate_deg_s"])),
        "b_abs_turn_rate_deg_s": float(abs(manoeuvre_b["turn_rate_deg_s"])),
        "a_abs_vertical_rate_ms": float(abs(state_a["vertical_rate_ms"])),
        "b_abs_vertical_rate_ms": float(abs(state_b["vertical_rate_ms"])),
        "a_abs_vertical_accel_ms2": float(abs(manoeuvre_a["vertical_accel_ms2"])),
        "b_abs_vertical_accel_ms2": float(abs(manoeuvre_b["vertical_accel_ms2"])),
        "a_abs_along_accel_ms2": float(abs(manoeuvre_a["along_accel_ms2"])),
        "b_abs_along_accel_ms2": float(abs(manoeuvre_b["along_accel_ms2"])),
        "min_distance_to_vabb_nm": float(min(
            _distance_to_vabb_nm(state_a["latitude"], state_a["longitude"]),
            _distance_to_vabb_nm(state_b["latitude"], state_b["longitude"]),
        )),
        "a_altitude_ft": float(state_a["altitude_m"] * M_TO_FT),
        "b_altitude_ft": float(state_b["altitude_m"] * M_TO_FT),
        "a_velocity_ms": float(state_a["velocity_ms"]),
        "b_velocity_ms": float(state_b["velocity_ms"]),
    }
    assert list(features) == FEATURE_COLUMNS, "encounter_features and FEATURE_COLUMNS have drifted apart"
    return features


def report_leakage_check(dataset: pd.DataFrame) -> None:
    """Prove the defect this rewrite exists to fix is actually gone.

    The old dataset's label was reproducible from two of its own features for 40,000
    of 40,000 rows. The same test is run here against the PREDICTED closest approach,
    which is the closest analogue in the new feature set. Anything near 100% would
    mean the circle had been rebuilt.
    """
    rule = ((dataset["predicted_cpa_lateral_nm"] < SEPARATION_LATERAL_NM)
            & (dataset["predicted_cpa_vertical_ft"] < SEPARATION_VERTICAL_FT)).astype(int)
    agreement = float((rule == dataset["is_conflict"]).mean())
    print("")
    print("=" * 92)
    print("LEAKAGE CHECK -- can the label be recomputed from the features?")
    print("=" * 92)
    print(f"  Applying the separation rule to the PREDICTED closest approach reproduces")
    print(f"  the real-outcome label for {agreement:.2%} of rows.")
    print(f"  (The old circular dataset scored 100.00%. Anything close to that means the")
    print(f"   label is still a function of the features and the model can learn nothing.)")
    disagree = int((rule != dataset["is_conflict"]).sum())
    missed = int(((rule == 0) & (dataset["is_conflict"] == 1)).sum())
    false = int(((rule == 1) & (dataset["is_conflict"] == 0)).sum())
    print(f"  Rows where prediction and reality disagree: {disagree:,} of {len(dataset):,}")
    print(f"    real conflicts the straight-line rule MISSED:      {missed:,}")
    print(f"    straight-line alarms that never actually happened: {false:,}")
    print(f"  Those {disagree:,} rows are the entire learning problem: they are where our")
    print(f"  own prediction is wrong, and nothing else in the pipeline models that.")
    if agreement > 0.99:
        raise RuntimeError(
            f"Label is reproducible from the features for {agreement:.4%} of rows. "
            "The circular-label defect has been reintroduced; do not train on this file."
        )


def report_warning_time(dataset: pd.DataFrame) -> None:
    """Warning time is the headline metric, so it gets reported at generation."""
    conflicts = dataset.loc[dataset["is_conflict"] == 1, "actual_time_to_cpa_seconds"]
    print("")
    print("Warning time on real conflicts (seconds from now to the actual closest approach)")
    if conflicts.empty:
        print("  no conflicts generated.")
        return
    at_zero = int((conflicts == 0).sum())
    print(f"  conflicts: {len(conflicts):,}")
    print(f"  min {conflicts.min():>5.0f} s   p10 {conflicts.quantile(0.10):>5.0f} s   "
          f"median {conflicts.median():>5.0f} s   p90 {conflicts.quantile(0.90):>5.0f} s   "
          f"max {conflicts.max():>5.0f} s")
    print(f"  already at closest approach at t = 0: {at_zero:,} ({at_zero / len(conflicts):.2%})   "
          f"(the old file: 25.33%)")
    for lower, upper, label in ((0, 90, "under 90 s, too late to act"),
                                (90, 180, "90-180 s, tier 1 alarm"),
                                (180, 300, "3-5 min, tier 2 advisory"),
                                (300, 601, "5-10 min, tier 2 advisory")):
        count = int(((conflicts >= lower) & (conflicts < upper)).sum())
        print(f"    {label:<28} {count:>6,} ({count / len(conflicts):6.2%})")
    at_least_three = int((conflicts >= 180).sum())
    print(f"  HEADLINE INPUT -- conflicts with at least 3 minutes of warning available: "
          f"{at_least_three:,} ({at_least_three / len(conflicts):.1%})")


def main() -> None:
    states = load_valid_states()
    anchors = build_anchors(states)
    dataset = build_dataset(anchors)

    output_directory = SYNTHETIC_DIRECTORY
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_directory / f"encounters_real_outcome_{timestamp}.parquet"
    dataset.to_parquet(output_path, index=False)

    span = pd.to_datetime(dataset["seed_time_position"].agg(["min", "max"]), unit="s", utc=True) \
        + pd.Timedelta(hours=5, minutes=30)
    print("")
    print(f"Scenarios: {len(dataset):,}   real conflicts: {int(dataset['is_conflict'].sum()):,} "
          f"({dataset['is_conflict'].mean():.2%})")
    print(f"Observation span: {span.iloc[0]:%d %b %H:%M} -> {span.iloc[1]:%d %b %H:%M} IST "
          f"across {dataset['session_id'].nunique()} session(s)")
    print("Severity balance:")
    for name, count in dataset["severity"].value_counts().items():
        print(f"  {name:<10} {count:>7,}")
    print("Conflict rate by intent:")
    for intended, group in dataset.groupby("intended_encounter"):
        label = "aimed at each other" if intended else "natural geometry"
        print(f"  {label:<22} {len(group):>7,} scenarios, {group['is_conflict'].mean():6.2%} conflict")

    report_leakage_check(dataset)
    report_warning_time(dataset)
    print("")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
