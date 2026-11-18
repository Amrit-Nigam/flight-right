"""Plan 9.1: which Mumbai runway is in use, derived from our own recorded landings.

    %LOCALAPPDATA%/FlightRight/venv_traffic/Scripts/python.exe scripts/derive_runways.py

Runs in its OWN environment. The `traffic` library (the plan names its Flight.landing(),
which detects alignment with a runway's approach path) imports a pandas internal that
pandas 3 removed, and this project runs pandas 3. Downgrading pandas under the training
stack was not acceptable, so traffic lives in %LOCALAPPDATA%/FlightRight/venv_traffic with
pandas 2 (the plan's own remedy for an incompatible stack: a separate environment). This
script only reads parquet and writes parquet, so the two environments never share objects.

Reads every session in ml_pipeline/data/raw/, keeps states within 40 NM of VABB, and for
each aircraft asks traffic for its landings at VABB. Writes:

  ml_pipeline/data/processed/runway_landings.parquet  one row per detected landing
  docs/figures/runway_spotcheck.png                   eight landings drawn over the runways,
                                                     for the manual check the plan requires
  ml_pipeline/reports/runway_landings_<stamp>.json    counts per runway and per session

The plan says: spot-check five to ten detected landings by eye before trusting the set.
That check is a person's job; the figure exists for it.
"""
from __future__ import annotations

import glob
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VABB = (19.0887, 72.8679)


def load_states() -> pd.DataFrame:
    frames = []
    for path in sorted(glob.glob(str(ROOT / "ml_pipeline/data/raw/*.parquet"))):
        d = pd.read_parquet(path, columns=["icao24", "callsign", "time_position", "latitude", "longitude",
                                           "baro_altitude", "velocity", "true_track", "vertical_rate", "on_ground"])
        d["session"] = Path(path).stem
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d = d.dropna(subset=["time_position", "latitude", "longitude", "baro_altitude", "velocity", "true_track"])
    d = d[d["on_ground"] == False]  # noqa: E712
    north = (d["latitude"] - VABB[0]) * 60.0
    east = (d["longitude"] - VABB[1]) * 60.0 * math.cos(math.radians(VABB[0]))
    d = d[np.hypot(north, east) < 40.0].copy()
    d["timestamp"] = pd.to_datetime(d["time_position"], unit="s", utc=True)
    d["altitude"] = d["baro_altitude"] * 3.28084
    d["groundspeed"] = d["velocity"] * 1.943844
    d["track"] = d["true_track"]
    d["vertical_rate"] = d["vertical_rate"].fillna(0.0) * 196.850394
    d["callsign"] = d["callsign"].fillna("").str.strip()
    return d.drop_duplicates(["icao24", "timestamp"]).sort_values(["icao24", "timestamp"])


def main() -> None:
    from traffic.core import Traffic

    states = load_states()
    print(f"{len(states):,} airborne states within 40 NM of VABB, {states['icao24'].nunique():,} aircraft")
    traffic = Traffic(states[["icao24", "callsign", "timestamp", "latitude", "longitude", "altitude",
                              "groundspeed", "track", "vertical_rate", "session"]])
    rows, examples = [], []
    for flight in traffic:
        for segment in flight.split("20 min"):
            for landing in segment.landing("VABB"):
                data = landing.data
                runway = data["ILS"].iloc[0] if "ILS" in data else None
                rows.append({"icao24": flight.icao24, "callsign": flight.callsign, "session": data["session"].iloc[0],
                             "runway": runway, "start": landing.start, "stop": landing.stop, "points": len(data),
                             "min_altitude_ft": float(data["altitude"].min()),
                             "mean_track_deg": float(np.degrees(np.arctan2(np.sin(np.radians(data["track"])).mean(),
                                                                            np.cos(np.radians(data["track"])).mean())) % 360)})
                if len(examples) < 40:
                    examples.append((flight.callsign, runway, segment.data, landing.data))
    landings = pd.DataFrame(rows)
    landings.to_parquet(ROOT / "ml_pipeline/data/processed/runway_landings.parquet")
    counts = landings.groupby("runway").size().to_dict() if len(landings) else {}
    per_session = landings.groupby("session")["runway"].agg(lambda s: s.value_counts().to_dict()).to_dict() if len(landings) else {}
    print(f"{len(landings)} landings detected; by runway {counts}")

    # Eight landings drawn for the manual spot-check.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from traffic.data import airports
    rng = np.random.default_rng(0)
    pick = rng.choice(len(examples), size=min(8, len(examples)), replace=False) if examples else []
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    runways = airports["VABB"].runways
    for ax, index in zip(axes.flat, pick):
        callsign, runway, whole, landed = examples[index]
        ax.plot(whole["longitude"], whole["latitude"], color="0.6", lw=1, label="track (40 NM)")
        ax.plot(landed["longitude"], landed["latitude"], color="tab:red", lw=2, label=f"detected: {runway}")
        for r in runways.list:
            ax.plot(r.longitude, r.latitude, "k^", ms=4)
        ax.plot(VABB[1], VABB[0], "ks", ms=5)
        ax.set_title(f"{callsign} -> {runway}", fontsize=10)
        ax.set_xlim(VABB[1] - 0.6, VABB[1] + 0.6); ax.set_ylim(VABB[0] - 0.6, VABB[0] + 0.6)
        ax.legend(fontsize=7, loc="lower left")
    fig.suptitle("Runway-in-use detection, 8 random landings -- CHECK BY EYE (plan 9.1): does each red segment "
                 "line up with the runway named?", fontsize=11)
    fig.tight_layout()
    fig.savefig(ROOT / "docs/figures/runway_spotcheck.png", dpi=110)

    report = {"states": int(len(states)), "aircraft": int(states["icao24"].nunique()), "landings": int(len(landings)),
              "by_runway": counts, "by_session": per_session,
              "spot_check": "docs/figures/runway_spotcheck.png -- NOT YET CHECKED BY A PERSON"}
    out = ROOT / "ml_pipeline/reports" / f"runway_landings_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
