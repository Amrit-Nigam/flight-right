"""Plan 9.0: turn fetched adsb.lol traces into one table, and measure coverage first.

    python ml_pipeline/utils/adsblol_parse.py

Reads ml_pipeline/data/adsblol/traces/<date>/<icao24>.json.gz (scripts/fetch_adsblol_traces.py)
and writes ml_pipeline/data/adsblol/intent.parquet: one row per trace point that carries the
detailed aircraft object (trace element 8), with the fields that describe INTENT and the air
the aircraft is flying in:

  nav_altitude_mcp   selected altitude on the autopilot panel (ft) -- the level-off target
  nav_altitude_fms   flight-management target altitude (ft)
  nav_heading        selected heading (deg)
  wd, ws, oat        wind direction/speed (deg, kt) and outside air temperature (C), as
                     measured by the aircraft itself (plan 9.6 needs these)

readsb's trace format (README-json.md): each point is [seconds after `timestamp`, lat, lon,
altitude ft or "ground", ground speed kt, track deg, flags, vertical rate fpm, detail object
or null, ...]. Only points with a detail object are kept; about a quarter of points carry one.

Plan 9.0 says to measure coverage before building on it, so the script prints and writes it:
the share of aircraft-days, and of airborne detail points within 60 NM of VABB, that carry a
selected altitude. Writes ml_pipeline/reports/adsblol_coverage_<stamp>.json.
"""
from __future__ import annotations

import glob
import gzip
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TRACES = ROOT / "ml_pipeline/data/adsblol/traces"
OUT = ROOT / "ml_pipeline/data/adsblol/intent.parquet"
VABB = (19.0887, 72.8679)
FIELDS = ("nav_altitude_mcp", "nav_altitude_fms", "nav_heading", "nav_qnh", "wd", "ws", "oat", "tas", "ias", "mach")


def parse(path: Path) -> list[dict]:
    trace = json.loads(gzip.decompress(path.read_bytes()))
    base, hexid, rows = float(trace["timestamp"]), str(trace.get("icao", path.stem.split(".")[0])).lower(), []
    for point in trace.get("trace", []):
        if len(point) < 9 or not isinstance(point[8], dict):
            continue
        detail = point[8]
        altitude = point[3] if isinstance(point[3], (int, float)) else None
        rows.append({"icao24": hexid, "time": base + float(point[0]), "lat": point[1], "lon": point[2],
                     "alt_baro_ft": altitude, "vertical_rate_fpm": point[7] if len(point) > 7 else None,
                     **{f: detail.get(f) for f in FIELDS}})
    return rows


def distance_nm(lat, lon) -> np.ndarray:
    north = (np.asarray(lat) - VABB[0]) * 60.0
    east = (np.asarray(lon) - VABB[1]) * 60.0 * math.cos(math.radians(VABB[0]))
    return np.hypot(north, east)


def main() -> None:
    files = sorted(glob.glob(str(TRACES / "*" / "*.json.gz")))
    missing = len(glob.glob(str(TRACES / "*" / "*.missing")))
    rows, per_file, info = [], [], {}
    for f in files:
        points = parse(Path(f))
        meta = json.loads(gzip.decompress(Path(f).read_bytes()))
        info[str(meta.get("icao", Path(f).name.split(".")[0])).lower()] = {
            "registration": meta.get("r"), "type": meta.get("t"), "description": meta.get("desc")}
        rows.extend(points)
        per_file.append({"date": Path(f).parent.name, "icao24": Path(f).name.split(".")[0],
                         "detail_points": len(points),
                         "mcp_points": sum(p["nav_altitude_mcp"] is not None for p in points)})
    table = pd.DataFrame(rows)
    table.to_parquet(OUT)
    # Plan 9.4: the aircraft type comes free with every trace file (readsb's "t").
    pd.DataFrame([{"icao24": k, **v} for k, v in info.items()]).to_parquet(OUT.parent / "aircraft_info.parquet")
    files_df = pd.DataFrame(per_file)
    near = table[(distance_nm(table["lat"], table["lon"]) < 60) & table["alt_baro_ft"].notna()]
    coverage = {
        "aircraft_days_requested": len(files) + missing, "traces_served": len(files), "traces_404": missing,
        "aircraft_days_with_any_selected_altitude": int((files_df["mcp_points"] > 0).sum()),
        "share_aircraft_days_with_selected_altitude": float((files_df["mcp_points"] > 0).mean()),
        "detail_points": int(len(table)),
        "detail_points_with_selected_altitude": int(table["nav_altitude_mcp"].notna().sum()),
        "airborne_detail_points_within_60nm_vabb": int(len(near)),
        "share_of_those_with_selected_altitude": float(near["nav_altitude_mcp"].notna().mean()) if len(near) else None,
        "share_with_wind": float(near["ws"].notna().mean()) if len(near) else None,
        "by_date": files_df.groupby("date").apply(lambda g: {"traces": int(len(g)),
                                                             "with_selected_altitude": int((g["mcp_points"] > 0).sum())}).to_dict(),
        "licence": "adsb.lol historical data, ODbL 1.0 (attribution; share-alike for distributed derived databases)",
    }
    out = ROOT / "ml_pipeline/reports" / f"adsblol_coverage_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(coverage, indent=2, default=str))
    print(json.dumps({k: v for k, v in coverage.items() if k != "by_date"}, indent=2))
    print(f"wrote {OUT.relative_to(ROOT)} ({len(table):,} rows) and {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
