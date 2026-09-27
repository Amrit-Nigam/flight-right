"""Plan 9.0 / 9.4 / 9.5 / 9.6: context features for every trajectory window, past-only.

    python ml_pipeline/utils/context_features.py

For each window in trajectory_{train,val,test}.npz (keyed by icao24 and the decision time
`timestamps`, the time of the last input state), attach what was knowable AT THAT MOMENT:

  intent  (9.0) selected altitude and selected heading from the autopilot panel, as the
                aircraft broadcast them (adsb.lol, ml_pipeline/utils/adsblol_parse.py):
                sel_alt_delta_ft = selected - current altitude; fms_alt_delta_ft;
                sel_heading_delta_deg = selected heading - current track; intent_age_s
  wind    (9.6) the wind the aircraft itself measured: headwind_kt, crosswind_kt, oat_c
  type    (9.4) aircraft type (from the adsb.lol trace file) -> OpenAP: mtow_kg, cruise_mach
  traffic (9.5) aircraft within 20 NM and 2,000 ft at the same poll (our own sessions):
                traffic_count, nearest_nm
  route   (26 Sep) where the flight is going and where it came from, from adsbdb's
                callsign -> route answer (plan 9.2 measured it: exactly right for 49% of all
                flights and 69% of Mumbai flights), airports placed with OurAirports
                (public domain, https://ourairports.com/data/): dest_dist_nm,
                dest_bearing_sin / dest_bearing_cos (bearing to the destination relative to
                the current track), orig_dist_nm. A route is schedule information, known
                before the flight, so it cannot leak the future.

    python ml_pipeline/utils/context_features.py route    # add only the route group

LEAKAGE RULE (CLAUDE.md Part 3 rule 6): every value is joined BACKWARD in time -- the most
recent report at or before the decision time, and no older than MAX_AGE_S. Nothing after
the decision time can enter. A missing value stays NaN; HistGradientBoosting handles NaN
natively, so "not broadcast" is information, not an imputed guess.

Writes ml_pipeline/data/processed/context_<split>.npz (one array per feature plus a `groups`
map) and ml_pipeline/reports/context_features_<stamp>.json with coverage per split.
"""
from __future__ import annotations

import glob
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "ml_pipeline/data/processed"
ADSBLOL = ROOT / "ml_pipeline/data/adsblol"
FT_PER_M = 3.28084
MAX_AGE_S = 300.0
GROUPS = {
    "intent": ["sel_alt_delta_ft", "fms_alt_delta_ft", "sel_heading_delta_deg", "intent_age_s"],
    "wind": ["headwind_kt", "crosswind_kt", "oat_c"],
    "type": ["mtow_kg", "cruise_mach"],
    "traffic": ["traffic_count", "nearest_nm"],
    "route": ["dest_dist_nm", "dest_bearing_sin", "dest_bearing_cos", "orig_dist_nm"],
}



def _wrap(deg: np.ndarray) -> np.ndarray:
    return (deg + 180.0) % 360.0 - 180.0


def windows(split: str) -> pd.DataFrame:
    z = np.load(PROCESSED / f"trajectory_{split}.npz", allow_pickle=True)
    X = z["X"]
    track = np.degrees(np.arctan2(X[:, -1, 4], X[:, -1, 5])) % 360.0
    return pd.DataFrame({"row": np.arange(len(X)), "icao24": z["icao24"].astype(str),
                         "time": z["timestamps"].astype(np.int64),
                         "alt_ft": X[:, -1, 2].astype(np.float64) * FT_PER_M,
                         "track": track, "lat": X[:, -1, 0], "lon": X[:, -1, 1]})


def backward_join(w: pd.DataFrame, reports: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Latest report at or before each window's time, per aircraft, within MAX_AGE_S."""
    left = w.sort_values("time")
    right = reports.sort_values("time")[["icao24", "time", *columns]].copy()
    right["time"] = right["time"].astype(np.int64)
    right["report_time"] = right["time"]
    out = pd.merge_asof(left, right, on="time", by="icao24", direction="backward",
                        tolerance=int(MAX_AGE_S), allow_exact_matches=True)
    return out.sort_values("row").reset_index(drop=True)


def type_performance(types: pd.Series) -> pd.DataFrame:
    from openap import prop
    cache = {}
    for t in types.dropna().unique():
        try:
            a = prop.aircraft(str(t))
            cache[t] = (float(a.get("mtow") or np.nan), float((a.get("cruise") or {}).get("mach") or np.nan))
        except Exception:  # noqa: BLE001 -- a type OpenAP does not know stays NaN
            cache[t] = (np.nan, np.nan)
    values = np.array([cache.get(t, (np.nan, np.nan)) for t in types])
    return pd.DataFrame({"mtow_kg": values[:, 0], "cruise_mach": values[:, 1]})


def traffic_features(w: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """Aircraft within 20 NM and 2,000 ft of the window's aircraft at the same poll."""
    states = states.assign(bucket=(states["time"] // 10).astype(np.int64))
    by_bucket = {b: g for b, g in states.groupby("bucket")}
    count = np.full(len(w), np.nan)
    nearest = np.full(len(w), np.nan)
    for i, (icao, t, lat, lon, alt) in enumerate(zip(w["icao24"], w["time"], w["lat"], w["lon"], w["alt_ft"])):
        g = by_bucket.get(int(t // 10))
        if g is None:
            continue
        g = g[g["icao24"] != icao]
        north = (g["latitude"].to_numpy() - lat) * 60.0
        east = (g["longitude"].to_numpy() - lon) * 60.0 * math.cos(math.radians(lat))
        dist = np.hypot(north, east)
        near = (dist < 20.0) & (np.abs(g["alt_ft"].to_numpy() - alt) < 2000.0)
        count[i] = float(near.sum())
        nearest[i] = float(dist.min()) if len(dist) else np.nan
    return pd.DataFrame({"traffic_count": count, "nearest_nm": nearest})


def route_features(w: pd.DataFrame, callsigns: np.ndarray) -> pd.DataFrame:
    """Destination and origin features; the arithmetic lives in route_features.py so that
    training, the alarm-chain check and the live backend compute exactly the same numbers."""
    import sys
    sys.path.insert(0, str(ROOT))
    from ml_pipeline.utils.route_features import ROUTE_FEATURES, route_matrix
    assert ROUTE_FEATURES == GROUPS["route"]
    values = route_matrix(callsigns, w["lat"].to_numpy(np.float64), w["lon"].to_numpy(np.float64),
                          w["track"].to_numpy(np.float64))
    return pd.DataFrame(values, columns=ROUTE_FEATURES)


def add_route_only() -> None:
    """Append the route group to existing context_<split>.npz files without recomputing the rest."""
    coverage = {}
    for split in ("train", "val", "test"):
        path = PROCESSED / f"context_{split}.npz"
        existing = dict(np.load(path, allow_pickle=True))
        existing.pop("groups", None)
        z = np.load(PROCESSED / f"trajectory_{split}.npz", allow_pickle=True)
        route = route_features(windows(split), z["callsign"])
        existing.update({k: route[k].to_numpy(np.float64) for k in GROUPS["route"]})
        np.savez_compressed(path, groups=np.array(GROUPS, dtype=object), **existing)
        coverage[split] = {k: float(np.isfinite(route[k]).mean()) for k in GROUPS["route"]}
        print(split, {k: round(v, 3) for k, v in coverage[split].items()})
    report = ROOT / "ml_pipeline/reports" / f"context_features_route_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(json.dumps({"source": "adsbdb callsign route cache + OurAirports",
                                  "coverage_share_non_missing": coverage, "groups": GROUPS}, indent=2))
    print(f"wrote {report.relative_to(ROOT)}")


def main() -> None:
    import sys
    if sys.argv[1:] == ["route"]:
        add_route_only()
        return
    intent = pd.read_parquet(ADSBLOL / "intent.parquet")
    intent["time"] = intent["time"].astype(np.int64)
    info = pd.read_parquet(ADSBLOL / "aircraft_info.parquet")
    raw = pd.concat([pd.read_parquet(f, columns=["icao24", "time_position", "latitude", "longitude", "baro_altitude"])
                     for f in sorted(glob.glob(str(ROOT / "ml_pipeline/data/raw/*.parquet")))]).dropna()
    raw = raw.rename(columns={"time_position": "time"})
    raw["time"] = raw["time"].astype(np.int64)
    raw["alt_ft"] = raw["baro_altitude"] * FT_PER_M
    raw = raw.drop_duplicates(["icao24", "time"])

    coverage = {}
    for split in ("train", "val", "test"):
        w = windows(split)
        sel = backward_join(w, intent[intent["nav_altitude_mcp"].notna()],
                            ["nav_altitude_mcp", "nav_altitude_fms", "nav_heading"])
        wind = backward_join(w, intent[intent["ws"].notna()], ["wd", "ws", "oat"])
        out = {
            "sel_alt_delta_ft": sel["nav_altitude_mcp"] - w["alt_ft"],
            "fms_alt_delta_ft": sel["nav_altitude_fms"] - w["alt_ft"],
            "sel_heading_delta_deg": _wrap(sel["nav_heading"] - w["track"]),
            "intent_age_s": w["time"] - sel["report_time"],
            "headwind_kt": wind["ws"] * np.cos(np.radians(wind["wd"] - w["track"])),
            "crosswind_kt": wind["ws"] * np.sin(np.radians(wind["wd"] - w["track"])),
            "oat_c": wind["oat"],
        }
        types = w["icao24"].map(info.set_index("icao24")["type"])
        perf = type_performance(types)
        out.update({"mtow_kg": perf["mtow_kg"], "cruise_mach": perf["cruise_mach"]})
        out.update(traffic_features(w, raw).to_dict("series"))
        z = np.load(PROCESSED / f"trajectory_{split}.npz", allow_pickle=True)
        out.update(route_features(w, z["callsign"]).to_dict("series"))
        assert (out["intent_age_s"].dropna() >= 0).all(), "a future report leaked into a window"
        arrays = {k: np.asarray(v, dtype=np.float64) for k, v in out.items()}
        np.savez_compressed(PROCESSED / f"context_{split}.npz", groups=np.array(GROUPS, dtype=object), **arrays)
        coverage[split] = {"windows": int(len(w)),
                           **{k: float(np.isfinite(v).mean()) for k, v in arrays.items()}}
        print(split, {k: round(v, 3) for k, v in coverage[split].items()})
    report = ROOT / "ml_pipeline/reports" / f"context_features_{datetime.now():%Y%m%d_%H%M%S}.json"
    report.write_text(json.dumps({"max_age_s": MAX_AGE_S, "coverage_share_non_missing": coverage,
                                  "groups": GROUPS}, indent=2))
    print(f"wrote {report.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
