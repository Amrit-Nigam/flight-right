"""Plan 7.3's proof, before any UI: does a clearance visibly change a tier 2 pair?

    python ml_pipeline/utils/clearance_demo.py [session filename]

Two passes over the same recorded frames through the real backend (AircraftService in
replay + ConflictService.assess, as replay_timing.py does):

  1. no clearances. The first tier 2 (watch list) pair that stays notified for five
     updates is chosen.
  2. the same frames, with a clearance for one aircraft of that pair submitted through
     clearance_service -- the door the speech chain will use -- at the moment the pair
     first appears. The clearance is read from the RECORDING's own future (the level the
     aircraft actually reached ten minutes later, else the track it turned onto), so it
     is an oracle: labelled as such, never a recognition result.

Printed side by side, per update: tier, notify, which gate fired, the multi-path conflict
probability, the classifier probability and what the clearance did. The plan predicted
that narrowing the fan pushes the probability under 0.60 and the pair leaves the watch
list. Since 22 Sep the classifier and the straight-line safety net decide WHO is alerted
(alert_gate), so this script measures what a clearance actually moves now instead of
assuming it. Writes ml_pipeline/reports/clearance_demo_<stamp>.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["FLIGHT_RIGHT_REPLAY_SEEK"] = "start"
os.environ["FLIGHT_RIGHT_DATA_MODE"] = "replay"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import logging  # noqa: E402
logging.disable(logging.WARNING)

from server.app.config import RAW_DIRECTORY  # noqa: E402
from server.app.services.aircraft_service import AircraftService  # noqa: E402
from server.app.services.clearance_service import clearance_service  # noqa: E402
from server.app.services.conflict_service import ConflictService  # noqa: E402
from server.app.services.database import database  # noqa: E402

SESSION = sys.argv[1] if len(sys.argv) > 1 else "session_20260905_003006_combined.parquet"
START, FRAMES_AHEAD, HOLD = 12, 60, 5      # 60 frames = ten minutes at 10 s per frame


def run(until: int, conflicts: ConflictService, on_frame=None) -> dict[int, dict]:
    aircraft = AircraftService(mode="replay")
    aircraft.replay.load(RAW_DIRECTORY / SESSION)
    index = [START]
    aircraft.replay._current_frame_index = lambda: index[0]
    per_frame = {}
    for i in range(START, until):
        index[0] = i
        aircraft.refresh()
        if i == START:
            aircraft.warm_up()
        if on_frame:
            on_frame(i, aircraft)
        result = conflicts.assess(aircraft.histories_for_models())
        per_frame[i] = {"active": result["active"],
                        "latest": {key: history[-1] for key, history in conflicts.pair_histories.items()},
                        "flights": {f["callsign"].strip(): f for f in aircraft.flights}}
    return per_frame, aircraft


def row(frame: dict, pair: tuple) -> dict:
    result = frame["latest"].get(pair)
    if result is None:
        return {"assessed": False}
    esc, mp, clf = result["escalation"], result.get("multipath", {}), result.get("classifier", {})
    return {"assessed": True, "tier": esc["tier"], "notify": esc["notify"], "gate": esc["gate"],
            "time_to_cpa_s": esc["time_to_cpa_seconds"], "multipath_probability": mp.get("conflict_probability"),
            "combinations_breaching": mp.get("combinations_breaching"),
            "classifier_probability": clf.get("conflict_probability"),
            "clearance": [c for c in (mp.get("clearance_a"), mp.get("clearance_b")) if c]}


def main() -> None:
    database.initialise()
    clearance_service.clear()
    print(f"session {SESSION}; pass 1 (no clearances)")
    probe = AircraftService(mode="replay")
    probe.replay.load(RAW_DIRECTORY / SESSION)
    last = len(probe.replay.frames) - FRAMES_AHEAD - 1
    base, _ = run(last, ConflictService())

    # Every tier 2 pair that holds for HOLD updates, not just the first: the plan's own
    # advice is "if nothing moves, pick a different pair", and testing all of them in one
    # pass is how that is done without hand-picking.
    streak, chosen = {}, {}
    for i in sorted(base):
        tier2 = {tuple(sorted(a["pair"])) for a in base[i]["active"] if a["tier"] == 2}
        streak = {p: streak.get(p, 0) + 1 for p in tier2}
        for p, n in streak.items():
            if n >= HOLD and p not in chosen:
                chosen[p] = i - HOLD + 1
    if not chosen:
        raise SystemExit("no tier 2 pair held for five updates in this session")
    print(f"{len(chosen)} tier 2 pairs held for {HOLD}+ updates")

    # One oracle clearance per aircraft, read from the recording ten minutes later: the
    # level it reached if it changed by 1,000 ft or more, else the track it flew.
    clearances, used = [], set()
    for pair, first in sorted(chosen.items(), key=lambda kv: kv[1]):
        now_flights = base[first]["flights"]
        future = {f["callsign"].strip(): f for f in probe.replay._aircraft_at(first + FRAMES_AHEAD)}
        for callsign in pair:
            if callsign in used or callsign not in now_flights or callsign not in future:
                continue
            now_ft, later_ft = now_flights[callsign]["altitudeFt"], future[callsign]["altitudeFt"]
            if abs(later_ft - now_ft) >= 1000:
                c = {"callsign": callsign, "action": "CLIMB" if later_ft > now_ft else "DESCEND",
                     "value": round(later_ft / 1000) * 1000}
            else:
                c = {"callsign": callsign, "action": "TURN", "value": round(future[callsign]["heading"] / 5) * 5 % 360}
            clearances.append((first, {**c, "valid_seconds": 3600}))
            used.add(callsign)
    print(f"{len(clearances)} oracle clearances: "
          f"{sum(c['action'] != 'TURN' for _, c in clearances)} level, {sum(c['action'] == 'TURN' for _, c in clearances)} heading")

    submitted = []

    def inject(i, aircraft):
        for first, clearance in clearances:
            if i == first:
                submitted.append(clearance_service.submit(clearance, aircraft.flights, source="oracle:recording"))

    clearance_service.clear()
    last_frame = max(chosen.values()) + HOLD + 6
    with_clearance, _ = run(last_frame, ConflictService(), on_frame=inject)
    clearance_service.clear()
    print(f"submitted {len(submitted)}: {sum(bool(s.get('ok')) for s in submitted)} applied")

    pairs_out = []
    for pair, first in sorted(chosen.items(), key=lambda kv: kv[1]):
        frames = list(range(first, first + HOLD + 6))
        table = [{"frame": i, "without": row(base[i], pair), "with": row(with_clearance[i], pair)} for i in frames]
        moved = [r for r in table if r["without"].get("assessed") and r["with"].get("assessed") and any(
            r["without"][k] != r["with"][k] for k in ("multipath_probability", "tier", "notify", "combinations_breaching"))]
        eliminated = [rep.get("candidates_before", 5) - rep.get("candidates_after", rep.get("candidates_before", 5))
                      for r in table for side in r["with"].get("clearance", []) for rep in side if rep.get("applied")]
        capped = [rep.get("candidates_capped", 0) for r in table for side in r["with"].get("clearance", []) for rep in side]
        pairs_out.append({"pair": pair, "first_frame": first, "updates": len(table), "updates_moved": len(moved),
                          "gates": sorted({r["without"]["gate"] for r in table if r["without"].get("assessed")}),
                          "tier_changes": sum(r["without"]["tier"] != r["with"]["tier"] for r in moved),
                          "notify_changes": sum(r["without"]["notify"] != r["with"]["notify"] for r in moved),
                          "max_probability_shift": max((abs((r["with"]["multipath_probability"] or 0) - (r["without"]["multipath_probability"] or 0)) for r in moved), default=0.0),
                          "candidates_eliminated_total": int(sum(eliminated)), "candidates_capped_total": int(sum(capped)),
                          "table": table})
    print(f"\n{'pair':<22}{'gate(s)':<34}{'moved':>7}{'tier chg':>9}{'notify chg':>11}{'max dP':>8}{'elim':>6}{'capped':>7}")
    for p in pairs_out:
        print(f"{' x '.join(p['pair']):<22}{','.join(p['gates']):<34}{p['updates_moved']:>4}/{p['updates']:<2}"
              f"{p['tier_changes']:>9}{p['notify_changes']:>11}{p['max_probability_shift']:>8.3f}"
              f"{p['candidates_eliminated_total']:>6}{p['candidates_capped_total']:>7}")
    best = max(pairs_out, key=lambda p: (p["updates_moved"], p["max_probability_shift"]))
    print(f"\nmost responsive pair: {best['pair']}")
    print(f"{'frame':>6} | {'tier':>4} {'notify':>6} {'gate':>18} {'mp prob':>8} {'breach':>6} | "
          f"{'tier':>4} {'notify':>6} {'gate':>18} {'mp prob':>8} {'breach':>6}   (without | with clearance)")
    for r in best["table"]:
        a, b = r["without"], r["with"]
        fmt = lambda x: (f"{x['tier']:>4} {str(x['notify']):>6} {x['gate']:>18} "
                         f"{(x['multipath_probability'] or 0):>8.3f} {str(x['combinations_breaching']):>6}") if x["assessed"] else f"{'not assessed':>47}"
        print(f"{r['frame']:>6} | {fmt(a)} | {fmt(b)}")
    out = ROOT / "ml_pipeline/reports" / f"clearance_demo_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"session": SESSION, "label": "oracle clearances read from the recording",
                               "clearances": clearances, "submitted_rows": [s.get("id") for s in submitted],
                               "pairs": pairs_out}, indent=2, default=str))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
