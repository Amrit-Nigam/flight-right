"""End-to-end check of the whole chain on real recorded Mumbai traffic, speech included.

    python ml_pipeline/voice/chain_check.py

Replays the demo encounter (IGO086 x FDB1346, the pair replay mode opens on) through the
REAL backend services -- AircraftService in replay, ConflictService.assess, the speech
service, the clearance door -- twice over identical frames:

  A. no speech;
  B. at the first update where the pair is assessed, a controller transmission for IGO086
     goes through speech_service.hear(), exactly as the radio panel sends one: text ->
     extractor -> callsign snapped onto the aircraft visible at that moment ->
     clearance_service.submit() -> the clearance caps IGO086's five candidate paths on every
     later update.

The transmission is text, not audio: generated Indian-accented audio needs Indic Parler-TTS,
whose licence gate is not yet accepted. The level in it is an ORACLE -- the level IGO086
actually held later in the same recording -- so it is labelled as such and never used as a
recognition result. What this script proves is the plumbing and what a correctly heard
clearance does downstream; recognition accuracy is evaluate_voice.py's job.

Checked and printed per update: the five candidate paths per aircraft and that their
probabilities sum to one; what the clearance did to IGO086's fan; the multi-path conflict
probability over the K x K combinations; tier, notify and which gate fired; and Model 3's
answer (offered or not, how many candidates it flew, what it checked against). Writes
ml_pipeline/reports/chain_check_<stamp>.json.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["FLIGHT_RIGHT_REPLAY_SEEK"] = "start"
os.environ["FLIGHT_RIGHT_DATA_MODE"] = "replay"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
logging.disable(logging.WARNING)

from server.app.config import RAW_DIRECTORY  # noqa: E402
from server.app.services.aircraft_service import AircraftService  # noqa: E402
from server.app.services.clearance_service import clearance_service  # noqa: E402
from server.app.services.conflict_service import ConflictService  # noqa: E402
from server.app.services.database import database  # noqa: E402
from server.app.services.speech_service import speech_service  # noqa: E402
from ml_pipeline.voice.callsigns import spoken_forms  # noqa: E402

SESSION = "session_c_20260904_204503_combined.parquet"
PAIR = ("IGO086", "FDB1346")
SPEAKER_TARGET = "IGO086"
START, END = 37, 72            # the replay seek starts at 37 (18 frames before frame 55)
DIGITS = "zero one two three four five six seven eight nine".split()


def oracle_level(probe: AircraftService, first: int) -> float:
    """The flight level IGO086 was actually at ten minutes after the heard transmission."""
    future = {f["callsign"].strip(): f for f in probe.replay._aircraft_at(min(first + 60, len(probe.replay.frames) - 1))}
    now = {f["callsign"].strip(): f for f in probe.replay._aircraft_at(first)}
    target = future.get(SPEAKER_TARGET) or now[SPEAKER_TARGET]
    feet = float(target["altitudeFt"])
    return round(feet / 1000.0) * 1000.0


def run(on_frame=None) -> dict[int, dict]:
    aircraft = AircraftService(mode="replay")
    aircraft.replay.load(RAW_DIRECTORY / SESSION)
    index = [START]
    aircraft.replay._current_frame_index = lambda: index[0]
    conflicts, out = ConflictService(), {}
    for i in range(START, END):
        index[0] = i
        aircraft.refresh()
        if i == START:
            aircraft.warm_up()
        if on_frame:
            on_frame(i, aircraft)
        out[i] = conflicts.assess(aircraft.histories_for_models())
        # The full assessment (with each aircraft's five candidates) for our pair, if assessed.
        full = next((h[-1] for h in conflicts.pair_histories.values()
                     if h and set(h[-1].get("callsigns", [])) == set(PAIR)), None)
        out[i]["_pair_full"] = full if full and full is not out.get(i - 1, {}).get("_pair_full") else None
    return out


def row(result: dict) -> dict:
    hit = next((c for c in result.get("active", []) + result.get("all", [])
                if set(c.get("pair", [])) == set(PAIR)), None)
    if hit is None:
        return {"on_list": False}
    res = hit.get("resolution") or {}
    return {"on_list": True, "tier": hit.get("tier"), "severity": hit.get("severity"),
            "multipath_probability": hit.get("multipathProbability"),
            "combinations_breaching": hit.get("combinationsBreaching"),
            "classifier_probability": hit.get("classifierProbability"),
            "clearance_effect": hit.get("clearanceEffect"),
            "resolution_offered": res.get("offered"), "options": [o.get("explanation") for o in res.get("options", [])],
            "checked_against": res.get("checkedAgainst"), "candidates_flown": res.get("candidatesEvaluated"),
            "reason": hit.get("reason")}


def main() -> None:
    probe = AircraftService(mode="replay")
    probe.replay.load(RAW_DIRECTORY / SESSION)
    base = run()
    first = next((i for i in range(START, END) if row(base[i])["on_list"]), None)
    if first is None:
        raise SystemExit(f"{PAIR} never reached the active list between frames {START} and {END}")
    level = oracle_level(probe, first)
    words = spoken_forms(next(f["callsign"] for f in probe.replay._aircraft_at(first)
                              if f["callsign"].strip() == SPEAKER_TARGET))[0]
    spoken_level = (f"flight level {' '.join(DIGITS[int(c)] for c in f'{int(level // 100):03d}')}"
                    if level >= 10_000 else f"{' '.join(DIGITS[int(c)] for c in str(int(level // 1000)))} thousand feet")
    heard_text = f"{words} descend {spoken_level}"

    heard = {}

    def speak(i, aircraft):
        if i == first:
            clearance_service.clear()
            heard.update(speech_service.hear(None, "chain_check:oracle-text", aircraft.snapshot()["flights"],
                                             transcript=heard_text))

    with_speech = run(on_frame=speak)
    clearance_service.clear()

    table = None
    five = []
    for i in range(first, END):
        mp = (with_speech[i].get("_pair_full") or {}).get("multipath") or {}
        for key in ("candidates_a", "candidates_b"):
            if mp.get(key):
                five.append((len(mp[key]), round(sum(c["probability"] for c in mp[key]), 6)))
        if mp:
            with_speech[i]["_fans"] = {"checked": mp.get("combinations_checked"), "a": [round(c["probability"], 3) for c in mp["candidates_a"]],
                                       "b": [round(c["probability"], 3) for c in mp["candidates_b"]],
                                       "clearance_a": mp.get("clearance_a"), "clearance_b": mp.get("clearance_b")}

    table = [{"frame": i, "without": row(base[i]), "with": row(with_speech[i]), "fans_with": with_speech[i].get("_fans")}
             for i in range(first, END)]
    report = {"measured_at_utc": datetime.now().isoformat(), "session": SESSION, "pair": PAIR,
              "first_frame_on_list": first, "heard_text": heard_text,
              "heard_text_is": "oracle: the level IGO086 held ten minutes later in the recording",
              "speech_chain": {k: heard.get(k) for k in ("ok", "transcript", "extracted", "callsignMatch",
                                                         "clearance", "reason", "modelId")},
              "candidate_fans_seen": {"count": len(five), "sizes": sorted({s for s, _ in five}),
                                      "probability_sums": sorted({p for _, p in five})},
              "updates": table}
    out = ROOT / "ml_pipeline/reports" / f"chain_check_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=str))

    c = heard.get("clearance") or {}
    print(f"heard: '{heard_text}'  (oracle level {level:.0f} ft)")
    print(f"  extracted: {heard.get('extracted', {}).get('action')} {heard.get('extracted', {}).get('value')}"
          f" | matched {heard.get('callsignMatch', {}).get('code')} (score {heard.get('callsignMatch', {}).get('score')})"
          f" | clearance {'APPLIED' if c.get('ok') else 'NOT applied'} {c.get('problems') or ''} {c.get('effect') or ''}")
    print(f"  candidate fans seen: {report['candidate_fans_seen']}")
    print(f"{'frame':>5} | {'tier':>4} {'mp prob':>7} {'breach':>6} | {'tier':>4} {'mp prob':>7} {'breach':>6} {'model 3':>9} clearance effect")
    for r in table:
        a, b = r["without"], r["with"]
        fmt = lambda x: (f"{str(x['tier']):>4} {(x['multipath_probability'] or 0):>7.3f} {str(x['combinations_breaching']):>6}"
                         if x["on_list"] else f"{'-':>4} {'-':>7} {'-':>6}")  # noqa: E731
        effect = "; ".join(f"{e.get('action')} {e.get('reason') or e.get('applied')}" for e in (b.get("clearance_effect") or [])
                           for e in (e if isinstance(e, list) else [e]) if isinstance(e, dict))[:70]
        m3 = ("offered" if b.get("resolution_offered") else "no") if b["on_list"] else "-"
        print(f"{r['frame']:>5} | {fmt(a)} | {fmt(b)} {m3:>9} {effect}")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
