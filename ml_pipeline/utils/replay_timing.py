"""Time the real backend tick over a whole recorded session, in one multipath offset mode.

Drives AircraftService (replay) and ConflictService.assess frame by frame -- the same
code the ingest loop runs -- stepping the frame index directly instead of waiting on the
replay clock, so two runs in different modes see identical frames. Written 23 Sep 2026 to
decide whether FLIGHT_RIGHT_MULTIPATH_OFFSETS=per_mode fits the ten-second budget.

Usage: python ml_pipeline/utils/replay_timing.py <session filename> <table|per_mode> <out.json>
Optional LIMIT_FRAMES=<n> for a quick run. One process per mode: the mode is read by
inference.py at import, so it is set here before any backend import.
"""
import json
import os
import sys
import time
from pathlib import Path

session, mode, out = sys.argv[1], sys.argv[2], str(Path(sys.argv[3]).resolve())
os.environ["FLIGHT_RIGHT_MULTIPATH_OFFSETS"] = mode
os.environ["FLIGHT_RIGHT_REPLAY_SEEK"] = "start"      # no seeking: every frame, in order
os.environ["FLIGHT_RIGHT_DATA_MODE"] = "replay"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import logging  # noqa: E402
logging.disable(logging.WARNING)

from server.app.config import RAW_DIRECTORY  # noqa: E402
from server.app.services.aircraft_service import AircraftService  # noqa: E402
from server.app.services.conflict_service import ConflictService  # noqa: E402
from server.app.ml import inference  # noqa: E402

# Count and time every multi-path model call, wherever it comes from.
mp_calls = []
original = inference.MultiPathPredictor.predict


def timed(self, X, top_k=None):
    started = time.perf_counter()
    result = original(self, X, top_k)
    mp_calls.append((len(X), time.perf_counter() - started))
    return result


inference.MultiPathPredictor.predict = timed

aircraft = AircraftService(mode="replay")
aircraft.replay.load(RAW_DIRECTORY / session)
index = [0]
aircraft.replay._current_frame_index = lambda: index[0]
conflicts = ConflictService()
conflicts.load()
assert conflicts.engine.multipath.offsets == mode, conflicts.engine.multipath.offsets

START = 12                       # enough recorded past for warm_up to seed ten states
LIMIT = int(os.environ.get("LIMIT_FRAMES", "100000"))
ticks = []
for i in range(START, min(len(aircraft.replay.frames), START + LIMIT)):
    index[0] = i
    aircraft.refresh()
    if i == START:
        aircraft.warm_up()
    mp_calls.clear()
    started = time.perf_counter()
    result = conflicts.assess(aircraft.histories_for_models())
    total = time.perf_counter() - started
    active = result["active"]
    ticks.append({
        "frame": i, "total_s": total,
        "multipath_s": sum(d for _, d in mp_calls), "multipath_calls": len(mp_calls),
        "multipath_rows": sum(n for n, _ in mp_calls),
        "aircraft": len(aircraft.flights), "eligible": result["eligibleAircraft"],
        "pairs": result["pairsAssessed"],
        "tier1": sum(1 for a in active if a.get("tier") == 1),
        "tier2": sum(1 for a in active if a.get("tier") == 2),
        "notifications": len(result["notifications"]),
        "active_pairs": sorted("|".join(a.get("pair", [])) + f"#{a.get('tier')}" for a in active),
    })
    if len(ticks) % 50 == 0:
        print(f"{mode} {session} tick {len(ticks)} last {total:.2f}s", flush=True)

with open(out, "w") as handle:
    json.dump({"session": session, "mode": mode, "version": conflicts.engine.multipath.version,
               "ticks": ticks}, handle)
print(f"done {mode} {session}: {len(ticks)} ticks -> {out}", flush=True)
