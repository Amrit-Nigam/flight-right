"""Prepare chronologically split trajectory sequences from raw OpenSky snapshots."""

from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_STEPS = 10
HORIZONS_SECONDS = np.array([60, 180, 300, 600], dtype=np.int64)
HORIZON_TOLERANCE_SECONDS = 15
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
    return frame.sort_values(["icao24", "time_position"]).reset_index(drop=True)


def nearest_future_state(track: pd.DataFrame, target_time: int) -> pd.Series | None:
    """Find the real observation closest to target_time, within the set tolerance."""
    offsets = (track["time_position"] - target_time).abs()
    index = offsets.idxmin()
    return track.loc[index] if offsets.loc[index] <= HORIZON_TOLERANCE_SECONDS else None


def build_samples(states: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build ten-state windows with all four real future-position targets present."""
    inputs: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    sample_times: list[int] = []

    for _, track in states.groupby("icao24", sort=False):
        track = track.drop_duplicates("time_position", keep="last").reset_index(drop=True)
        # Fourteen is the minimum requested track length; the horizon matching
        # below provides the stricter real-time requirement when snapshots vary.
        if len(track) < 14:
            continue

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

    if not inputs:
        return (np.empty((0, INPUT_STEPS, 8), dtype=np.float32), np.empty((0, 4, 3), dtype=np.float32), np.empty(0, dtype=np.int64))
    return np.stack(inputs), np.stack(targets), np.asarray(sample_times, dtype=np.int64)


def save_time_splits(inputs: np.ndarray, targets: np.ndarray, sample_times: np.ndarray) -> None:
    """Split by sample timestamp, never by random row, then persist DataLoader-ready arrays."""
    if not len(sample_times):
        raise ValueError("No valid samples were generated; collect more temporally dense tracks.")
    order = np.argsort(sample_times)
    inputs, targets, sample_times = inputs[order], targets[order], sample_times[order]
    train_end = int(len(inputs) * TRAIN_FRACTION)
    validation_end = int(len(inputs) * (TRAIN_FRACTION + VALIDATION_FRACTION))
    splits = {"train": slice(0, train_end), "val": slice(train_end, validation_end), "test": slice(validation_end, None)}
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, split in splits.items():
        np.savez_compressed(OUTPUT_DIRECTORY / f"trajectory_{name}.npz", X=inputs[split], y=targets[split], timestamps=sample_times[split])
        print(f"{name}: {len(inputs[split])} valid sequence samples")


def main() -> None:
    states = load_valid_states()
    inputs, targets, sample_times = build_samples(states)
    print(f"Built {len(inputs)} valid samples from {len(states)} airborne raw states.")
    save_time_splits(inputs, targets, sample_times)


if __name__ == "__main__":
    main()
