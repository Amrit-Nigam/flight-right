"""Plan 7.1: what would hearing the radio be worth? UPPER BOUND, perfect recognition.

    python ml_pipeline/utils/oracle_clearance.py

No audio is needed. For each test window, the clearance the aircraft was following is
read OUT OF THE TRUTH -- the level it ended ten minutes later at, and the track it
turned onto -- and handed to the constraint filter (ml_pipeline/utils/clearance.py) as
if heard perfectly. The filter eliminates the candidate paths that contradict it.

Run against the SERVED Phase 3 model (per-mode offsets), not the single-answer LSTM or
the old table, so the question answered is "what does a heard clearance add on top of
what we already have" (plan 7.1). Every number this prints is an UPPER BOUND: a real
recogniser mishears, and the truth-derived clearance is exactly what the aircraft did.

Also reported, because it is what makes the tolerances trustworthy: how often the filter
eliminates the candidate that was actually CLOSEST to the truth. A filter that throws
away the right answer is worse than none.

Writes ml_pipeline/reports/oracle_clearance_<stamp>.json.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))

import framing  # noqa: E402
import multipath as mp  # noqa: E402
from ml_pipeline.utils.clearance import (FT_PER_M, Clearance, _angle_between, _bearing_deg,  # noqa: E402
                                         cap_at_level, constrain, path_obeys)

LEVEL_CHANGE_FT = 1_000.0     # below this the aircraft held its level: no level clearance
TURN_DEG = 15.0               # below this the aircraft held its track: no heading clearance


def oracle_clearances(X: np.ndarray, y: np.ndarray, i: int) -> dict[str, Clearance | None]:
    """The clearances the aircraft actually followed, read from its true future."""
    now_ft = float(X[i, -1, framing.ALTITUDE]) * FT_PER_M
    final_ft = float(y[i, 3, 2]) * FT_PER_M
    level = None
    if abs(final_ft - now_ft) >= LEVEL_CHANGE_FT:
        level = Clearance(icao24=f"row{i}", action="CLIMB" if final_ft > now_ft else "DESCEND",
                          value=round(final_ft / 1000.0) * 1000.0, source="oracle")
    heading_now = math.degrees(math.atan2(float(X[i, -1, 4]), float(X[i, -1, 5]))) % 360.0
    track = _bearing_deg(y[i, 2], y[i, 3])
    turn = None
    if _angle_between(track, heading_now) >= TURN_DEG:
        turn = Clearance(icao24=f"row{i}", action="TURN", value=round(track / 5.0) * 5.0 % 360.0, source="oracle")
    return {"level": level, "turn": turn}


def main() -> None:
    from server.app.ml.inference import MultiPathPredictor

    data = np.load(ROOT / "ml_pipeline/data/processed/trajectory_test.npz")
    X, y, mask = data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)
    rows = np.flatnonzero(mask[:, 2] & mask[:, 3])          # need the 5- and 10-minute truth
    arrivals = mp.arrival_rows(X)
    predictor = MultiPathPredictor(offsets="per_mode")
    extra = predictor.saved_split_inputs("test")
    probabilities, positions, _ = predictor.predict(X[rows], extra=None if extra is None else extra[rows])
    print(f"model {predictor.version}; {len(rows):,} test windows with a 5- and 10-minute truth "
          f"({int(arrivals[rows].sum()):,} arrivals)")

    # "level" ELIMINATES candidates (plan 7.2 as written); "cap" is EUROCONTROL STCA Option E
    # (no elimination, altitude may not pass the cleared level).
    variants = {"none": (), "level only": ("level",), "heading only": ("turn",), "level + heading": ("level", "turn"),
                "level cap": ("cap",), "level cap + heading": ("cap", "turn")}
    per_variant = {name: {"top1_5nm": [], "best5_5nm": [], "top1_both": [], "best5_both": [], "applied": [],
                          "fallback": [], "dropped_closest": []} for name in variants}
    truth_rejected = {"level": [0, 0], "turn": [0, 0]}
    for j, i in enumerate(rows):
        oracle = oracle_clearances(X, y, i)
        truth = y[i][None]
        lateral = framing.error_nm(positions[j], np.repeat(truth, len(positions[j]), 0))[:, 3]
        closest = int(np.argmin(lateral))
        for kind in ("level", "turn"):
            if oracle[kind] is not None:
                verdict = path_obeys(y[i], float(X[i, -1, framing.ALTITUDE]), oracle[kind])
                truth_rejected[kind][0] += verdict is False
                truth_rejected[kind][1] += verdict is not None
        for name, kinds in variants.items():
            probs, pos, applied, fallback, dropped = probabilities[j], positions[j], False, False, False
            keep_index = np.arange(len(probs))
            for kind in kinds:
                clearance = oracle["level" if kind == "cap" else kind]
                if clearance is None:
                    continue
                if kind == "cap":
                    pos, report = cap_at_level(pos, float(X[i, -1, framing.ALTITUDE]), clearance)
                    applied = applied or bool(report.get("applied"))
                    continue
                before = keep_index
                probs, pos, report = constrain(probs, pos, float(X[i, -1, framing.ALTITUDE]), clearance)
                if report.get("applied"):
                    applied = True
                    # Track which original candidates survive, to know if the closest one went.
                    # Compared on lat/lon only: a level cap before this step changes altitudes, not identity.
                    survivors = [k for k in before if any(np.array_equal(positions[j][k][:, :2], p[:, :2]) for p in pos)]
                    keep_index = np.array(survivors)
                elif "contradicts every" in report["reason"]:
                    fallback = True
            dropped = closest not in keep_index
            order = np.argsort(-probs)
            err_lat = framing.error_nm(pos, np.repeat(truth, len(pos), 0))[:, 3][order]
            err_alt = np.abs(pos[:, 3, 2] - y[i, 3, 2])[order] * FT_PER_M
            both = (err_lat < 5.0) & (err_alt < 1000.0)
            block = per_variant[name]
            block["top1_5nm"].append(err_lat[0] < 5.0); block["best5_5nm"].append(bool((err_lat < 5.0).any()))
            block["top1_both"].append(bool(both[0])); block["best5_both"].append(bool(both.any()))
            block["applied"].append(applied); block["fallback"].append(fallback); block["dropped_closest"].append(dropped)

    arr = arrivals[rows]
    out = {"label": "UPPER BOUND, assuming perfect clearance recognition", "model": predictor.version,
           "windows": int(len(rows)), "arrivals": int(arr.sum()),
           "truth_itself_rejected": {k: {"rejected": v[0], "judged": v[1]} for k, v in truth_rejected.items()},
           "variants": {}}
    print("\nUPPER BOUND, assuming perfect clearance recognition -- ten minutes ahead")
    print(f"{'variant':<18}{'group':<10}{'top-1 5NM':>10}{'best5 5NM':>10}{'top-1 3D':>10}{'best5 3D':>10}"
          f"{'applied':>9}{'fallback':>9}{'lost closest':>13}")
    for name, block in per_variant.items():
        arrays = {k: np.array(v) for k, v in block.items()}
        out["variants"][name] = {}
        for group, sel in (("arrivals", arr), ("all", np.ones(len(rows), bool))):
            m = {k: float(arrays[k][sel].mean() * 100) for k in arrays}
            out["variants"][name][group] = m
            print(f"{name:<18}{group:<10}{m['top1_5nm']:>9.1f}%{m['best5_5nm']:>9.1f}%{m['top1_both']:>9.1f}%"
                  f"{m['best5_both']:>9.1f}%{m['applied']:>8.1f}%{m['fallback']:>8.1f}%{m['dropped_closest']:>12.1f}%")
    print(f"\ntruth itself rejected by its own clearance: {out['truth_itself_rejected']}")
    path = ROOT / "ml_pipeline/reports" / f"oracle_clearance_{datetime.now():%Y%m%d_%H%M%S}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
