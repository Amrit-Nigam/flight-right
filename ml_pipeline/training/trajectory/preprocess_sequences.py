"""Prepare chronologically split trajectory sequences from raw OpenSky snapshots."""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_STEPS = 10
HORIZONS_SECONDS = np.array([60, 180, 300, 600], dtype=np.int64)
# A target is interpolated between the two real observations that bracket it.
# Beyond this bracket width the interpolation stops describing the aircraft and
# starts inventing it, so the horizon is marked invalid instead.
MAX_INTERPOLATION_GAP_SECONDS = 120
# A track is cut here rather than spanned. Sessions are collected in separate
# 90-minute blocks, so without this a ten-state "trajectory" can silently bridge
# a multi-day gap between sessions.
MAX_TRACK_GAP_SECONDS = 600
# Samples further apart than this belong to different collection sessions.
SESSION_BREAK_SECONDS = 1800
# Ten input states plus the two future observations needed to bracket the
# nearest horizon. Requiring enough states to bracket all four horizons would
# re-exclude the descending arrivals that per-horizon masking exists to keep.
MIN_TRACK_LENGTH = INPUT_STEPS + 2
# on_ground is unreliable: aircraft on approach and taxiing report False. These
# floors drop ground and near-ground rows that would otherwise pollute training.
MIN_ALTITUDE_FT = 1000.0
MIN_VELOCITY_MS = 50.0
METRES_TO_FEET = 3.28084
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15

PROJECT_ROOT = Path(__file__).resolve().parents[3]
# FLIGHT_RIGHT_DATA_ROOT relocates data and saved models (used by the smoke test so
# it can never touch real data). Unset, everything lives under the project root.
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
RAW_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "raw"
OUTPUT_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "processed"


def load_valid_states() -> pd.DataFrame:
    """Read every raw parquet, retaining states usable by the trajectory model."""
    paths = sorted(glob.glob(str(RAW_DIRECTORY / "*.parquet")))
    if not paths:
        raise FileNotFoundError(f"No Parquet files found in {RAW_DIRECTORY}")
    frame = pd.concat((pd.read_parquet(path) for path in paths), ignore_index=True)
    required = ["icao24", "time_position", "on_ground", "latitude", "longitude", "baro_altitude", "velocity", "true_track"]
    missing = set(required).difference(frame.columns)
    if missing:
        raise ValueError(f"Raw files are missing columns: {sorted(missing)}")

    # vertical_rate is a useful feature but can be absent in valid OpenSky data;
    # level flight is a safer replacement than discarding otherwise good tracks.
    if "vertical_rate" not in frame:
        frame["vertical_rate"] = 0.0
    frame = frame.loc[(frame["on_ground"] == False) & frame[required].notna().all(axis=1)].copy()  # noqa: E712
    frame["vertical_rate"] = frame["vertical_rate"].fillna(0.0)
    frame = frame.loc[
        (frame["baro_altitude"] * METRES_TO_FEET > MIN_ALTITUDE_FT)
        & (frame["velocity"] > MIN_VELOCITY_MS)
    ]
    return frame.sort_values(["icao24", "time_position"]).reset_index(drop=True)


def interpolated_future_state(
    times: np.ndarray,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    altitudes: np.ndarray,
    first_future_index: int,
    target_time: int,
) -> tuple[float, float, float] | None:
    """Linearly interpolate position at target_time between the observations bracketing it.

    Snapping to the nearest observation instead, as this previously did, accepted a
    mismatch of up to 30 s. An airliner covers ~13.6 km per minute, so that put as
    much as 3.7 NM of pure label noise into the one-minute target -- larger than the
    error the model is being trained to achieve. Only real bracketing observations
    are used: nothing is extrapolated past the end of a track.
    """
    if first_future_index >= times.size:
        return None
    future_times = times[first_future_index:]
    offset = int(np.searchsorted(future_times, target_time, side="left"))
    if offset >= future_times.size:
        return None  # The track stops before the target time; do not extrapolate.
    after = first_future_index + offset
    if times[after] == target_time:
        return float(latitudes[after]), float(longitudes[after]), float(altitudes[after])
    if offset == 0:
        return None  # No observation at or before the target time within the future track.

    before = after - 1
    span = float(times[after] - times[before])
    if span > MAX_INTERPOLATION_GAP_SECONDS:
        return None  # The bracket is too wide to describe what happened between the two.
    fraction = (float(target_time) - float(times[before])) / span
    return (
        float(latitudes[before] + fraction * (latitudes[after] - latitudes[before])),
        float(longitudes[before] + fraction * (longitudes[after] - longitudes[before])),
        float(altitudes[before] + fraction * (altitudes[after] - altitudes[before])),
    )


def build_samples(states: pd.DataFrame) -> tuple[np.ndarray, ...]:
    """Build ten-state windows keeping every window with at least one valid horizon.

    Also returns the identity of the aircraft each window came from. That is a JOIN
    KEY, not a model feature -- nothing in training reads it. It exists so a window can
    be traced back to the real aircraft and the real moment it describes, which is what
    lets a heard radio callsign be matched against the traffic that was actually
    airborne at that timestamp. Carrying it costs a few hundred kilobytes and cannot
    change a single prediction, because the feature builder never sees these arrays.
    """
    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    masks: list[np.ndarray] = []
    sample_times: list[int] = []
    icao24s: list[str] = []
    callsigns: list[str] = []

    for _, whole_track in states.groupby("icao24", sort=False):
        whole_track = whole_track.drop_duplicates("time_position", keep="last").reset_index(drop=True)
        # Cut the track wherever observation stops, so no window spans a break.
        times = whole_track["time_position"].to_numpy()
        cut_points = np.flatnonzero(np.diff(times) > MAX_TRACK_GAP_SECONDS) + 1
        segments = np.split(np.arange(len(whole_track)), cut_points)

        for segment in segments:
            track = whole_track.iloc[segment]
            if len(track) < MIN_TRACK_LENGTH:
                continue
            _extend_samples_from_track(track, inputs, targets, masks, sample_times,
                                       icao24s, callsigns)

    if not inputs:
        return (
            np.empty((0, INPUT_STEPS, 8), dtype=np.float32),
            np.empty((0, 4, 3), dtype=np.float32),
            np.empty((0, 4), dtype=bool),
            np.empty(0, dtype=np.int64),
            np.empty(0, dtype="U8"),
            np.empty(0, dtype="U10"),
        )
    return (np.stack(inputs), np.stack(targets), np.stack(masks),
            np.asarray(sample_times, dtype=np.int64),
            np.asarray(icao24s), np.asarray(callsigns))


def _extend_samples_from_track(track, inputs, targets, masks, sample_times,
                               icao24s, callsigns) -> None:
    """Append every window from one gap-free segment that resolves at least one horizon."""
    times = track["time_position"].to_numpy(dtype=np.int64)
    # Identity is taken from the LAST input state, which is the aircraft as it was at
    # the moment the prediction is made from. callsign is not in the required-column
    # list and never filters a row out: a missing one should not discard an otherwise
    # good track, exactly as with vertical_rate in load_valid_states(). Measured on the
    # current 35 sessions, it is 0.00% null.
    icao_values = track["icao24"].astype(str).to_numpy()
    if "callsign" in track:
        callsign_values = track["callsign"].fillna("").astype(str).str.strip().to_numpy()
    else:
        callsign_values = np.full(len(track), "", dtype=object)
    latitudes = track["latitude"].to_numpy(dtype=np.float64)
    longitudes = track["longitude"].to_numpy(dtype=np.float64)
    altitudes = track["baro_altitude"].to_numpy(dtype=np.float64)
    velocities = track["velocity"].to_numpy(dtype=np.float64)
    headings = np.deg2rad(track["true_track"].to_numpy(dtype=np.float64))
    vertical_rates = track["vertical_rate"].to_numpy(dtype=np.float64)

    for end_index in range(INPUT_STEPS - 1, len(track)):
        start_index = end_index - INPUT_STEPS + 1
        end_time = int(times[end_index])
        window_targets = np.zeros((4, 3), dtype=np.float32)
        window_mask = np.zeros(4, dtype=bool)
        for horizon_index, horizon in enumerate(HORIZONS_SECONDS):
            state = interpolated_future_state(
                times, latitudes, longitudes, altitudes, end_index + 1, end_time + int(horizon)
            )
            if state is not None:
                window_targets[horizon_index] = state
                window_mask[horizon_index] = True

        # A window with no resolvable horizon teaches nothing. One with only the
        # near horizons is the descending arrival traffic that the old
        # all-four-or-nothing rule silently deleted from the dataset.
        if not window_mask.any():
            continue

        window = slice(start_index, end_index + 1)
        # The first time gap is zero because it has no previous state inside
        # its input window. Subsequent gaps retain irregular collection timing.
        time_gaps = np.diff(times[window].astype(np.float64), prepend=float(times[start_index]))
        sequence = np.column_stack((
            latitudes[window], longitudes[window], altitudes[window], velocities[window],
            np.sin(headings[window]), np.cos(headings[window]), vertical_rates[window], time_gaps,
        )).astype(np.float32)
        inputs.append(sequence)
        targets.append(window_targets)
        masks.append(window_mask)
        sample_times.append(end_time)
        icao24s.append(str(icao_values[end_index]))
        callsigns.append(str(callsign_values[end_index]))


def save_time_splits(inputs: np.ndarray, targets: np.ndarray, masks: np.ndarray, sample_times: np.ndarray,
                     icao24s: np.ndarray, callsigns: np.ndarray) -> None:
    """Split chronologically on whole-session boundaries, then persist DataLoader-ready arrays.

    Splitting on raw row position puts part of one collection session in train and
    the rest in test, so the test score measures memorising one 90-minute window
    rather than generalising. Data is collected in discrete sessions, so each is
    kept intact and assigned whole to one split.
    """
    if not len(sample_times):
        raise ValueError("No valid samples were generated; collect more temporally dense tracks.")
    order = np.argsort(sample_times)
    inputs, targets, masks, sample_times = inputs[order], targets[order], masks[order], sample_times[order]
    # The join keys must be reordered WITH the samples. Until 25 Sep 2026 they were not, so
    # every saved icao24/callsign belonged to a different window (added 22 Sep, Phase 1.3;
    # no model reads them, so no published number was affected -- found when plan 9.0
    # first joined on them). verify_pipeline.py now checks the keys against raw positions.
    icao24s, callsigns = np.asarray(icao24s)[order], np.asarray(callsigns)[order]

    # Any pause longer than a session length marks the start of a new session.
    session_id = np.concatenate(([0], np.cumsum(np.diff(sample_times) > SESSION_BREAK_SECONDS)))
    boundaries = np.flatnonzero(np.diff(session_id)) + 1
    blocks = np.split(np.arange(len(sample_times)), boundaries)

    train_target = len(inputs) * TRAIN_FRACTION
    validation_target = len(inputs) * (TRAIN_FRACTION + VALIDATION_FRACTION)
    assigned: dict[str, list[np.ndarray]] = {"train": [], "val": [], "test": []}
    running = 0
    for block in blocks:
        name = "train" if running < train_target else "val" if running < validation_target else "test"
        assigned[name].append(block)
        running += len(block)

    if not assigned["val"] or not assigned["test"]:
        raise ValueError(
            f"Only {len(blocks)} session(s) of samples; need at least 3 to fill train/val/test. "
            "Collect more sessions before training."
        )

    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, blocks_for_split in assigned.items():
        index = np.concatenate(blocks_for_split)
        np.savez_compressed(
            OUTPUT_DIRECTORY / f"trajectory_{name}.npz",
            X=inputs[index], y=targets[index], mask=masks[index], timestamps=sample_times[index],
            # Join keys, never features. See build_samples().
            icao24=icao24s[index], callsign=callsigns[index],
        )
        span = pd.to_datetime(sample_times[index][[0, -1]], unit="s", utc=True) + pd.Timedelta(hours=5, minutes=30)
        valid = masks[index].sum(axis=0)
        print(
            f"{name:<5} {len(index):>6} samples from {len(blocks_for_split):>2} session(s)  "
            f"{span[0]:%d %b %H:%M} -> {span[1]:%d %b %H:%M} IST  "
            f"valid per horizon: {valid[0]}/{valid[1]}/{valid[2]}/{valid[3]}"
        )


def report_horizon_coverage(masks: np.ndarray) -> None:
    """Show how many samples each horizon actually contributes a target to."""
    total = len(masks)
    print(f"Per-horizon valid targets (of {total} samples):")
    for horizon_index, horizon in enumerate(HORIZONS_SECONDS):
        valid = int(masks[:, horizon_index].sum())
        print(f"  {horizon // 60:>2} min: {valid:>6} ({valid / total:6.2%})")
    all_four = int(masks.all(axis=1).sum())
    print(f"  all four horizons valid: {all_four} ({all_four / total:.2%})")


def main() -> None:
    states = load_valid_states()
    inputs, targets, masks, sample_times, icao24s, callsigns = build_samples(states)
    print(f"Built {len(inputs)} valid samples from {len(states)} airborne raw states.")
    report_horizon_coverage(masks)
    save_time_splits(inputs, targets, masks, sample_times, icao24s, callsigns)


if __name__ == "__main__":
    main()
