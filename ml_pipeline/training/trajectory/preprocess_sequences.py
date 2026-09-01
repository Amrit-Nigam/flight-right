"""Prepare chronologically split trajectory sequences from raw OpenSky snapshots."""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_STEPS = 10
HORIZONS_SECONDS = np.array([60, 180, 300, 600], dtype=np.int64)
# Measured mean gap between OpenSky position updates is ~18 s, so a 15 s window
# discarded usable samples; 30 s keeps them at a modest cost in target precision.
HORIZON_TOLERANCE_SECONDS = 30
# A track is cut here rather than spanned. Sessions are collected in separate
# 90-minute blocks, so without this a ten-state "trajectory" can silently bridge
# a multi-day gap between sessions.
MAX_TRACK_GAP_SECONDS = 600
# Samples further apart than this belong to different collection sessions.
SESSION_BREAK_SECONDS = 1800
# on_ground is unreliable: aircraft on approach and taxiing report False. These
# floors drop ground and near-ground rows that would otherwise pollute training.
MIN_ALTITUDE_FT = 1000.0
MIN_VELOCITY_MS = 50.0
METRES_TO_FEET = 3.28084
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "raw"
OUTPUT_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "processed"


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


def nearest_future_state(track: pd.DataFrame, target_time: int) -> pd.Series | None:
    """Find the real observation closest to target_time, within the set tolerance."""
    # The final windows of a track have no observations after them at all.
    if track.empty:
        return None
    offsets = (track["time_position"] - target_time).abs()
    index = offsets.idxmin()
    return track.loc[index] if offsets.loc[index] <= HORIZON_TOLERANCE_SECONDS else None


def build_samples(states: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build ten-state windows with all four real future-position targets present."""
    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    sample_times: list[int] = []

    for _, whole_track in states.groupby("icao24", sort=False):
        whole_track = whole_track.drop_duplicates("time_position", keep="last").reset_index(drop=True)
        # Cut the track wherever observation stops, so no window spans a break.
        times = whole_track["time_position"].to_numpy()
        cut_points = np.flatnonzero(np.diff(times) > MAX_TRACK_GAP_SECONDS) + 1
        segments = np.split(np.arange(len(whole_track)), cut_points)

        for segment in segments:
            track = whole_track.iloc[segment].reset_index(drop=True)
            # Fourteen is the minimum requested track length; the horizon matching
            # below provides the stricter real-time requirement when snapshots vary.
            if len(track) < 14:
                continue
            _extend_samples_from_track(track, inputs, targets, sample_times)

    if not inputs:
        return (np.empty((0, INPUT_STEPS, 8), dtype=np.float32), np.empty((0, 4, 3), dtype=np.float32), np.empty(0, dtype=np.int64))
    return np.stack(inputs), np.stack(targets), np.asarray(sample_times, dtype=np.int64)


def _extend_samples_from_track(track, inputs, targets, sample_times) -> None:
    """Append every valid window from one gap-free segment of a single aircraft."""
    for end_index in range(INPUT_STEPS - 1, len(track)):
            history = track.iloc[end_index - INPUT_STEPS + 1 : end_index + 1]
            end_time = int(history.iloc[-1]["time_position"])
            future = [nearest_future_state(track.iloc[end_index + 1 :], end_time + int(horizon)) for horizon in HORIZONS_SECONDS]
            if any(state is None for state in future):
                continue

            headings = np.deg2rad(history["true_track"].to_numpy(dtype=np.float32))
            # The first time gap is zero because it has no previous state inside
            # its input window. Subsequent gaps retain irregular collection timing.
            time_gaps = np.diff(history["time_position"].to_numpy(dtype=np.float32), prepend=history.iloc[0]["time_position"])
            sequence = np.column_stack((
                history["latitude"], history["longitude"], history["baro_altitude"], history["velocity"],
                np.sin(headings), np.cos(headings), history["vertical_rate"], time_gaps,
            )).astype(np.float32)
            future_targets = np.array(
                [[state["latitude"], state["longitude"], state["baro_altitude"]] for state in future], dtype=np.float32
            )
            inputs.append(sequence)
            targets.append(future_targets)
            sample_times.append(end_time)


def save_time_splits(inputs: np.ndarray, targets: np.ndarray, sample_times: np.ndarray) -> None:
    """Split chronologically on whole-session boundaries, then persist DataLoader-ready arrays.

    Splitting on raw row position puts part of one collection session in train and
    the rest in test, so the test score measures memorising one 90-minute window
    rather than generalising. Data is collected in discrete sessions, so each is
    kept intact and assigned whole to one split.
    """
    if not len(sample_times):
        raise ValueError("No valid samples were generated; collect more temporally dense tracks.")
    order = np.argsort(sample_times)
    inputs, targets, sample_times = inputs[order], targets[order], sample_times[order]

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
            X=inputs[index], y=targets[index], timestamps=sample_times[index],
        )
        span = pd.to_datetime(sample_times[index][[0, -1]], unit="s", utc=True) + pd.Timedelta(hours=5, minutes=30)
        print(
            f"{name:<5} {len(index):>6} samples from {len(blocks_for_split):>2} session(s)  "
            f"{span[0]:%d %b %H:%M} -> {span[1]:%d %b %H:%M} IST"
        )


def main() -> None:
    states = load_valid_states()
    inputs, targets, sample_times = build_samples(states)
    print(f"Built {len(inputs)} valid samples from {len(states)} airborne raw states.")
    save_time_splits(inputs, targets, sample_times)


if __name__ == "__main__":
    main()
