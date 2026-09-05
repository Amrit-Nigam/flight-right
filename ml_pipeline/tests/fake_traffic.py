"""Generate FAKE OpenSky-shaped session files for exercising the code paths.

THIS DATA MUST NEVER BE USED FOR TRAINING A MODEL THAT IS REPORTED ANYWHERE.

CLAUDE.md rule 7: synthetic flight PATHS teach a model our assumptions rather than
Mumbai's traffic. That is exactly what these are -- invented straight legs, turns,
climbs and descents. Their one legitimate use is to prove the pipeline runs end to
end (preprocessing, training, generation, saving, loading, inference) on a machine
that has no real data, in a few minutes, before the real run on the training laptop.
The smoke test writes them to a temporary directory and deletes them afterwards.

The tracks are made deliberately manoeuvre-heavy so that the straight-line prediction
is often wrong: otherwise the leakage guard in train_xgboost.py (correctly) refuses to
train, because on perfectly straight traffic the rule reproduces the label.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

VABB_LAT, VABB_LON = 19.0887, 72.8679
METRES_PER_DEGREE = 111_320.0
STATE_COLUMNS = [
    "icao24", "callsign", "origin_country", "time_position", "last_contact", "longitude", "latitude",
    "baro_altitude", "on_ground", "velocity", "true_track", "vertical_rate", "sensors", "geo_altitude",
    "squawk", "spi", "position_source", "category", "fetch_timestamp_utc",
]


def _track(rng: np.random.Generator, start_time: int, polls: int, step_s: int, icao: str,
           near_field: bool) -> list[tuple]:
    """One aircraft's snapshots. Roughly a third straight, a third turning, a third vertical."""
    if near_field:
        lat = VABB_LAT + rng.uniform(-0.45, 0.45)
        lon = VABB_LON + rng.uniform(-0.45, 0.45)
    else:
        lat, lon = rng.uniform(16.5, 23.0), rng.uniform(68.5, 77.0)
    altitude_m = rng.uniform(3_500.0, 11_500.0)   # 11,500 - 37,700 ft: en-route
    speed = rng.uniform(180.0, 260.0)
    heading = rng.uniform(0.0, 360.0)
    vertical = 0.0
    kind = rng.choice(["straight", "turn", "vertical", "turn+vertical"], p=[0.3, 0.3, 0.2, 0.2])
    turn_rate = rng.uniform(-1.5, 1.5) if "turn" in kind else 0.0
    turn_start = rng.integers(0, polls // 2)
    turn_length = rng.integers(polls // 6, polls // 2)
    if "vertical" in kind:
        vertical = rng.uniform(-12.0, 12.0)
    rows = []
    for k in range(polls):
        t = start_time + k * step_s
        turning = turn_start <= k < turn_start + turn_length
        if turning:
            heading = (heading + turn_rate * step_s) % 360.0
        if "vertical" in kind and k == polls // 2:
            vertical = -vertical * rng.uniform(0.3, 1.0)   # level-off or reversal mid-track
        lat += speed * step_s * math.cos(math.radians(heading)) / METRES_PER_DEGREE
        lon += speed * step_s * math.sin(math.radians(heading)) / (METRES_PER_DEGREE * math.cos(math.radians(lat)))
        altitude_m = max(1_500.0, altitude_m + vertical * step_s)
        speed = float(np.clip(speed + rng.normal(0.0, 0.4), 150.0, 280.0))
        rows.append((icao, f"FK{icao[-3:].upper()}", "India", t, t, lon, lat, altitude_m, False, speed,
                     heading, vertical + rng.normal(0.0, 0.2), None, altitude_m + 30.0, None, False, 0, 0,
                     pd.Timestamp(t, unit="s", tz="UTC")))
    return rows


def write_fake_sessions(raw_directory: Path, sessions: int = 7, aircraft_per_session: int = 25,
                        polls: int = 270, step_s: int = 10, seed: int = 7) -> list[Path]:
    """Write `sessions` fake parquet files, three hours apart, and return their paths."""
    rng = np.random.default_rng(seed)
    raw_directory.mkdir(parents=True, exist_ok=True)
    base = 1_757_000_000  # early Sept 2025 in unix seconds; the value is irrelevant
    paths = []
    for session in range(sessions):
        start = base + session * 3 * 3600
        rows: list[tuple] = []
        for aircraft in range(aircraft_per_session):
            icao = f"f{session:02d}{aircraft:03d}"
            rows.extend(_track(rng, start, polls, step_s, icao, near_field=(aircraft % 3 == 0)))
        frame = pd.DataFrame(rows, columns=STATE_COLUMNS)
        path = raw_directory / f"session_fake_{session:02d}_combined.parquet"
        frame.to_parquet(path, index=False)
        paths.append(path)
    return paths


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fake_raw")
    for p in write_fake_sessions(out):
        print(p)
