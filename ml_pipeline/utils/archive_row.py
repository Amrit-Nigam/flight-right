"""Plan 3.3's "+ more data" row: retrain the multi-path model with archive days added.

    python ml_pipeline/utils/archive_row.py

The OpenSky archive days in ml_pipeline/data/archive/ (Phase 2) are deliberately NOT in
data/raw/, so nothing published can shift under them. This script measures what they add,
as a separate row, without touching the served model or any published split:

  1. Choose archive days strictly BEFORE the validation period (CLAUDE.md Part 3 rule 3:
     split by time; a day from after the test period in training would leak the future).
     Every third usable day, so the row spans Feb 2025 - Aug 2026 rather than one season.
  2. Run the real preprocess_sequences.py on them in a throwaway data root.
  3. Add a seeded sample of those windows to the EXISTING training split. Validation and
     test are the existing files, untouched, so the row is scored on the same held-out
     data as every other row.
  4. Train multipath.py (seed 42 / offset seed 0, same as served) into a side path.

Everything lives under ml_pipeline/data/processed/archive_row/ (gitignored).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "ml_pipeline/data/archive"
PROCESSED = ROOT / "ml_pipeline/data/processed"
WORK = PROCESSED / "archive_row"
ARCHIVE_ROOT = WORK / "archive_root"      # preprocess_sequences.py over archive days
COMBINED_ROOT = WORK / "combined_root"    # existing train + archive sample; existing val/test
EVERY_NTH_DAY = 3
ARCHIVE_SAMPLES = 400_000                 # about twice the existing training split
SEED = 0


def choose_days() -> list[Path]:
    with np.load(PROCESSED / "trajectory_val.npz") as val:
        validation_start = pd.Timestamp(int(val["timestamps"].min()), unit="s", tz="UTC")
    usable = []
    for path in sorted(ARCHIVE.glob("archive_*.parquet")):
        day = pd.Timestamp(path.stem.split("_")[1], tz="UTC")
        if day + pd.Timedelta(days=1) <= validation_start.floor("D") and len(pd.read_parquet(path, columns=["icao24"])) > 10_000:
            usable.append(path)
    chosen = usable[::EVERY_NTH_DAY]
    print(f"validation starts {validation_start:%Y-%m-%d %H:%M} UTC; {len(usable)} usable archive days before it, "
          f"using every {EVERY_NTH_DAY}rd: {len(chosen)} ({chosen[0].stem[8:]} .. {chosen[-1].stem[8:]})")
    return chosen


def preprocess(days: list[Path]) -> dict[str, np.ndarray]:
    raw = ARCHIVE_ROOT / "ml_pipeline/data/raw"
    if raw.exists():
        shutil.rmtree(raw)
    raw.mkdir(parents=True)
    for path in days:
        shutil.copy2(path, raw / path.name)
    env = {**os.environ, "FLIGHT_RIGHT_DATA_ROOT": str(ARCHIVE_ROOT)}
    subprocess.run([sys.executable, str(ROOT / "ml_pipeline/training/trajectory/preprocess_sequences.py")],
                   env=env, check=True)
    parts = [np.load(ARCHIVE_ROOT / f"ml_pipeline/data/processed/trajectory_{s}.npz") for s in ("train", "val", "test")]
    return {key: np.concatenate([p[key] for p in parts]) for key in ("X", "y", "mask", "timestamps")}


def combine(archive: dict[str, np.ndarray]) -> None:
    with np.load(PROCESSED / "trajectory_val.npz") as val:
        assert archive["timestamps"].max() < val["timestamps"].min(), "archive sample reaches into validation time"
    rng = np.random.default_rng(SEED)
    pick = np.sort(rng.choice(len(archive["X"]), size=min(ARCHIVE_SAMPLES, len(archive["X"])), replace=False))
    target = COMBINED_ROOT / "ml_pipeline/data/processed"
    target.mkdir(parents=True, exist_ok=True)
    with np.load(PROCESSED / "trajectory_train.npz") as train:
        np.savez_compressed(target / "trajectory_train.npz",
                            **{k: np.concatenate([train[k], archive[k][pick]]) for k in ("X", "y", "mask", "timestamps")})
        print(f"training split: {len(train['X']):,} existing + {len(pick):,} archive windows "
              f"(of {len(archive['X']):,} available); 10-min valid {archive['mask'][pick, 3].mean():.1%} archive "
              f"vs {train['mask'][:, 3].mean():.1%} existing")
    for split in ("val", "test"):
        shutil.copy2(PROCESSED / f"trajectory_{split}.npz", target / f"trajectory_{split}.npz")


def train(seed: int) -> Path:
    """One run. Seed 42 uses offset seed 0, matching the served model; others use the seed for both."""
    out = PROCESSED / f"seed_runs/multipath_archive_seed{seed}.pkl"
    env = {**os.environ, "FLIGHT_RIGHT_DATA_ROOT": str(COMBINED_ROOT),
           "FLIGHT_RIGHT_MULTIPATH_SEED": str(seed), "FLIGHT_RIGHT_OFFSET_SEED": "0" if seed == 42 else str(seed),
           "FLIGHT_RIGHT_MULTIPATH_OUT": str(out)}
    subprocess.run([sys.executable, str(ROOT / "ml_pipeline/training/trajectory/multipath.py")], env=env, check=True)
    return out


if __name__ == "__main__":
    # python archive_row.py [seed ...]   (default: 42). The combined training split is
    # rebuilt only if missing, so extra seeds train on byte-identical data.
    seeds = [int(value) for value in sys.argv[1:]] or [42]
    if not (COMBINED_ROOT / "ml_pipeline/data/processed/trajectory_train.npz").exists():
        combine(preprocess(choose_days()))
    for seed in seeds:
        train(seed)
