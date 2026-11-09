"""Display the most probable existing candidate; never change the alert chain."""
import math
import threading
from collections import OrderedDict

from .normalizer import to_engine_state

HORIZONS = (("1min", 60), ("3min", 180), ("5min", 300), ("10min", 600))


class TrajectoryService:
    def __init__(self):
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    def predict(self, engine, states, clearances):
        if len(states) < 10:
            return {"status": "warming", "reason": "Waiting for 10 position reports"}
        if engine is None or engine.multipath is None:
            return {"status": "unavailable", "reason": "Multi-path model unavailable"}
        recent = states[-10:]
        key = recent[-1].get("icao24") or recent[-1]["callsign"]
        history = [to_engine_state(s) for s in recent]
        # Repeat requests for the same reports/instructions share a bounded cache.
        signature = repr((id(engine), history, clearances))
        with self._lock:
            if signature in self._cache:
                return self._cache[signature]
            candidates = engine.multipath_candidates({key: history}, clearances={key: clearances})
            paths = candidates.get(key, {}).get("paths", [])
            valid = []
            for probability, positions in paths:
                if not math.isfinite(probability) or not 0 <= probability <= 1:
                    continue
                points = [positions.get(label) for label, _ in HORIZONS]
                if any(p is None or len(p) < 2 or not all(math.isfinite(float(v)) for v in p[:2])
                       or abs(p[0]) > 90 or abs(p[1]) > 180 for p in points):
                    continue
                valid.append((probability, points))
            if not valid:
                return {"status": "unavailable", "reason": "No valid predicted path"}
            probability, points = max(valid, key=lambda path: path[0])
            result = {"status": "ready", "probability": float(probability),
                      "modelVersion": engine.multipath.version,
                      "coordinates": [[recent[-1]["lng"], recent[-1]["lat"]]]
                          + [[float(p[1]), float(p[0])] for p in points],
                      "horizonsSeconds": [0] + [seconds for _, seconds in HORIZONS]}
            self._cache[signature] = result
            while len(self._cache) > 16:
                self._cache.popitem(last=False)
            return result


trajectory_service = TrajectoryService()
