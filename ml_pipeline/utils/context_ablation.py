"""Plan 9.0 / 9.4 / 9.5 / 9.6 ablation rows: does each kind of context help, measured alone?

    python ml_pipeline/utils/context_ablation.py [group ...]    (default: all rows)

One change at a time (plan rule 3), each a full multipath.py training run with seed 42 /
offset seed 0 (the served configuration), writing to a side path so the served model is
never touched:

  none      baseline, no extras (re-run so its summary carries the same height / 3-D fields)
  intent    9.0 selected altitude and heading (adsb.lol)
  wind      9.6 wind the aircraft measured (adsb.lol)
  type      9.4 aircraft type -> OpenAP performance
  traffic   9.5 surrounding traffic from our own sessions
  all       every group together

Plus one row that needs no training, the sourced way to use a selected level: EUROCONTROL
STCA Option E ("Cleared and/or Selected Flight Level used for Vertical Prediction"). The
SERVED model's candidates are capped at the aircraft's broadcast selected altitude, where
one was broadcast within five minutes -- the same cap_at_level the clearance chain uses,
fed by an observed field instead of a heard one.

Writes ml_pipeline/reports/context_ablation_<stamp>.json. Extra features reach the OFFSET
regressors only, so the candidate shapes and probabilities are identical in every row.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
RUNS = ROOT / "ml_pipeline/data/processed/seed_runs"
ROWS = {"none": "", "intent": "intent", "wind": "wind", "type": "type", "traffic": "traffic",
        "all": "intent,wind,type,traffic"}


def train(name: str, groups: str) -> dict:
    out = RUNS / f"multipath_ctx_{name}.pkl"
    env = {**os.environ, "FLIGHT_RIGHT_MULTIPATH_SEED": "42", "FLIGHT_RIGHT_OFFSET_SEED": "0",
           "FLIGHT_RIGHT_MULTIPATH_OUT": str(out), "FLIGHT_RIGHT_MULTIPATH_EXTRA": groups}
    log = RUNS / f"multipath_ctx_{name}.log"
    with log.open("w") as handle:
        subprocess.run([sys.executable, str(ROOT / "ml_pipeline/training/trajectory/multipath.py")],
                       env=env, check=True, stdout=handle, stderr=subprocess.STDOUT)
    summary = json.loads(out.with_suffix(".summary.json").read_text())
    out.unlink()                                   # ~120 MB each; the summary is what matters
    return summary


def selected_level_cap() -> dict:
    """Served model, candidates capped at the broadcast selected altitude (STCA Option E)."""
    import framing
    import multipath as mp
    from ml_pipeline.utils.clearance import Clearance, cap_at_level
    from server.app.ml.inference import MULTIPATH_PATH, MultiPathPredictor

    z = np.load(ROOT / "ml_pipeline/data/processed/trajectory_test.npz", allow_pickle=True)
    X, y, mask = z["X"].astype(np.float32), z["y"].astype(np.float32), z["mask"].astype(bool)
    ctx = np.load(ROOT / "ml_pipeline/data/processed/context_test.npz", allow_pickle=True)
    delta = ctx["sel_alt_delta_ft"]
    _, positions, _ = MultiPathPredictor(MULTIPATH_PATH, offsets="per_mode").predict(X)
    capped = positions.copy()
    applied = 0
    for i in np.flatnonzero(np.isfinite(delta) & (np.abs(delta) >= 300.0)):
        now_ft = float(X[i, -1, framing.ALTITUDE]) * 3.28084
        c = Clearance(icao24="obs", action="CLIMB" if delta[i] > 0 else "DESCEND", value=now_ft + float(delta[i]),
                      source="observed:nav_altitude_mcp")
        capped[i], report = cap_at_level(positions[i], float(X[i, -1, framing.ALTITUDE]), c)
        applied += bool(report.get("applied"))
    arrivals = mp.arrival_rows(X)
    ten = mask[:, 3]
    out = {"windows_with_selected_level": int(np.isfinite(delta).sum()), "cap_applied": applied}
    for name, p in (("served", positions), ("served + selected-level cap", capped)):
        lat = np.stack([framing.error_nm(p[:, k], y) for k in range(5)], 1)[:, :, 3]
        ver = np.abs(p[:, :5, 3, 2] - y[:, None, 3, 2]) * 3.28084
        both = (lat < 5) & (ver < 1000)
        out[name] = {g: {"top1_altitude_mean_ft": float(ver[r, 0].mean()), "top1_both": float(both[r, 0].mean() * 100),
                         "best5_both": float(both[r].any(1).mean() * 100),
                         "best5_within_1000ft": float((ver[r] < 1000).any(1).mean() * 100)}
                     for g, r in (("arrivals", arrivals & ten), ("all", ten),
                                  ("with a selected level", ten & np.isfinite(delta)))}
    return out


def main() -> None:
    wanted = sys.argv[1:] or list(ROWS)
    results = {}
    for name in wanted:
        print(f"training row: {name} ({ROWS[name] or 'no extras'})", flush=True)
        s = train(name, ROWS[name])
        results[name] = {"extra_features": s.get("extra_features", []),
                         "arrivals_best5_5nm": s["best_of_k"]["per_mode"]["5"]["arrivals"],
                         "arrivals_top1_5nm": s["best_of_k"]["per_mode"]["1"]["arrivals"],
                         "all_best5_5nm": s["best_of_k"]["per_mode"]["5"]["all"],
                         "three_d": s["three_d"]["per_mode"], "gates": s["gates"]}
        a = results[name]
        print(f"  {name:<8} arrivals b5 {a['arrivals_best5_5nm']:.1f} top1 {a['arrivals_top1_5nm']:.1f} | "
              f"3-D b5 {a['three_d']['arrivals']['best5_both']:.1f} top1 {a['three_d']['arrivals']['top1_both']:.1f} | "
              f"alt err {a['three_d']['all']['top1_altitude_mean_ft']:.0f} ft", flush=True)
    results["selected_level_cap"] = selected_level_cap()
    out = ROOT / "ml_pipeline/reports" / f"context_ablation_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(results, indent=2))
    print(json.dumps(results["selected_level_cap"], indent=2))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
