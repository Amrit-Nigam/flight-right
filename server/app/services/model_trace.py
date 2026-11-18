"""A readable, per-update record of what every model said, for watching the backend work.

Written to ``server/logs/model_trace.log`` (and the general log to ``server/logs/backend.log``).
Open either in VS Code while the backend runs; the file grows as updates arrive. Each ten-second
update is one block:

    ===== data time 20:51:30 UTC (replay: session_c_20260904_204503_combined) ...
    IGO086 x FDB1346
      Rule (straight line)   : closest approach 2.61 NM / 950 ft in 180 s -> CONFLICT, severity high
      Model 1b (5 paths each): P(conflict) 0.43, 7 of 25 path combinations breach ...
      Model 2 (XGBoost)      : P(conflict) 0.75 -> ALERT; top reasons ...
      Escalation             : tier 1 ALARM via classifier, 3 consecutive updates, notify
      Model 3 (resolution)   : 2 options from 26 simulated: ...

Pairs that are on the controller's screen (or that any model flags) get the full block; every
other assessed pair gets one line, so the file shows that they were checked too.

Nothing here decides anything; it only writes down decisions made elsewhere.
"""
from __future__ import annotations

import datetime as dt
import logging
from logging.handlers import RotatingFileHandler

from ..config import PROJECT_ROOT

LOG_DIR = PROJECT_ROOT / "server" / "logs"
_trace = logging.getLogger("flightright.trace")


def setup_file_logging() -> None:
    """backend.log (everything the console shows) and model_trace.log (this module)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(name)-24s %(message)s", "%H:%M:%S")
    backend = RotatingFileHandler(LOG_DIR / "backend.log", maxBytes=20_000_000, backupCount=2, encoding="utf8")
    backend.setFormatter(fmt)
    logging.getLogger().addHandler(backend)

    trace = RotatingFileHandler(LOG_DIR / "model_trace.log", maxBytes=50_000_000, backupCount=2, encoding="utf8")
    trace.setFormatter(logging.Formatter("%(message)s"))
    _trace.addHandler(trace)
    _trace.setLevel(logging.INFO)
    _trace.propagate = False          # keep the console readable; the trace lives in its file


def _ft(x) -> str:
    return "-" if x is None else f"FL{int(round(float(x) / 100)):03d}"


def _pair_block(pair: tuple, result: dict, on_screen: bool) -> list[str]:
    rule = result.get("rule", {})
    mp = result.get("multipath")
    clf = result.get("classifier")
    esc = result.get("escalation", {})
    res = result.get("resolution", {})
    name = " x ".join(result.get("callsigns") or pair)
    lines = [f"{name}{'   [ON SCREEN]' if on_screen else ''}"]
    lines.append(
        f"  Rule (straight line)   : closest approach {rule.get('cpa_lateral_distance_nm', 0):.2f} NM / "
        f"{rule.get('cpa_vertical_separation_ft', 0):.0f} ft in {rule.get('time_to_cpa_seconds', 0):.0f} s -> "
        f"{'CONFLICT' if rule.get('is_conflict') else 'no conflict'}, severity {rule.get('severity')}")
    if mp:
        top_a = max(mp.get("candidates_a") or [{"probability": 0}], key=lambda c: c["probability"])
        top_b = max(mp.get("candidates_b") or [{"probability": 0}], key=lambda c: c["probability"])
        lines.append(
            f"  Model 1b (5 paths each): P(conflict) {mp['conflict_probability']:.2f}, "
            f"{mp['combinations_breaching']} of {mp['combinations_checked']} path combinations inside the alert volume; "
            f"closest {mp['cpa_lateral_distance_nm']:.2f} NM / {mp['cpa_vertical_separation_ft']:.0f} ft in "
            f"{mp['time_to_cpa_seconds']:.0f} s; likeliest path p={top_a['probability']:.2f} / {top_b['probability']:.2f}")
        for side in ("clearance_a", "clearance_b"):
            if mp.get(side):
                lines.append(f"      clearance applied ({side[-1].upper()}): {mp[side]}")
    if clf:
        reasons = ", ".join(f"{e['feature']}={e['value']:.3g} ({e['contribution']:+.2f})"
                            for e in clf.get("explanation", [])[:3])
        dialled = clf.get("dialled_levels_ft", {})
        lines.append(
            f"  Model 2 (XGBoost)      : P(conflict) {clf['conflict_probability']:.3f} "
            f"(raw {clf['raw_probability']:.3f}, alert at raw >= {clf['decision_threshold']:.4f}) -> "
            f"{'ALERT' if clf['alert'] else 'no alert'}; dialled levels {_ft(dialled.get('a'))} / {_ft(dialled.get('b'))}")
        lines.append(f"                           top reasons: {reasons}")
    lines.append(
        f"  Escalation             : tier {esc.get('tier')} {str(esc.get('tier_name', '')).upper()}, "
        f"gate {esc.get('gate')}, qualifies {esc.get('qualifies_this_update')}, "
        f"{esc.get('consecutive_updates')} consecutive update(s), notify {esc.get('notify')}")
    if res.get("offered"):
        lines.append(f"  Model 3 (resolution)   : {len(res.get('options', []))} option(s) from "
                     f"{res.get('candidates_evaluated')} simulated manoeuvres "
                     f"({res.get('blocked_unsafe')} blocked unsafe, {res.get('rejected_new_conflict')} would hit a third aircraft)")
        for rank, o in enumerate(res.get("options", []), 1):
            lines.append(f"      {rank}. {o['manoeuvre_type']} {o['aircraft']} {o['magnitude']:g} {o['unit']}: "
                         f"-> {o['resulting_lateral_separation_nm']:.1f} NM / {o['resulting_vertical_separation_ft']:.0f} ft, "
                         f"confidence {o['confidence']:.2f}, score {o['score']:.3f}")
    else:
        lines.append(f"  Model 3 (resolution)   : none offered - {res.get('reason')}")
    return lines


def write_tick(aircraft_service, conflict_service) -> None:
    """One block per update. Called by the ingest loop after assess()."""
    if not _trace.handlers:
        return
    snap = conflict_service.last_result or {}
    results = getattr(conflict_service, "last_assessments", {}) or {}
    on_screen = {tuple(sorted(a["pair"])) for a in snap.get("active", [])}
    try:
        data_time = dt.datetime.fromtimestamp(aircraft_service.data_time(), dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:                                          # noqa: BLE001
        data_time = "?"
    session = ""
    if aircraft_service.source == "replay":
        session = f": {(aircraft_service.replay.status() or {}).get('session', '')}"
    counts = snap.get("counts", {})
    lines = [
        "",
        f"===== data time {data_time} UTC ({aircraft_service.source}{session}) | wall {dt.datetime.now():%H:%M:%S} | "
        f"{snap.get('eligibleAircraft', 0)} en-route aircraft, {snap.get('pairsAssessed', 0)} pairs assessed in "
        f"{snap.get('durationMs', 0):.0f} ms | on screen: {len(on_screen)} "
        f"(tier 1 {counts.get('tier_1', counts.get('alarm', '?'))}, tier 2 {counts.get('tier_2', counts.get('advisory', '?'))})",
    ]
    quiet = []
    for pair, result in sorted(results.items(),
                               key=lambda kv: kv[1].get("rule", {}).get("cpa_lateral_distance_nm", 999)):
        esc, rule, clf = result.get("escalation", {}), result.get("rule", {}), result.get("classifier") or {}
        interesting = (pair in on_screen or esc.get("qualifies_this_update") or rule.get("is_conflict")
                       or clf.get("alert") or (result.get("multipath") or {}).get("conflict_probability", 0) > 0)
        if interesting:
            lines.extend(_pair_block(pair, result, pair in on_screen))
        else:
            quiet.append(f"{' x '.join(result.get('callsigns') or pair)} "
                         f"({rule.get('cpa_lateral_distance_nm', 0):.1f} NM / {rule.get('cpa_vertical_separation_ft', 0):.0f} ft, "
                         f"P {clf.get('conflict_probability', 0):.3f})")
    if quiet:
        lines.append(f"  checked, nothing flagged by any model: {'; '.join(quiet)}")
    _trace.info("\n".join(lines))
