"""Load the saved models through server/app/ml/inference.py and run one pair through them.

Used by smoke_test.py, and usable on its own after a real training run:

    python ml_pipeline/tests/inference_check.py

Prints the engine status, one trajectory prediction, and one pair assessment with the
rule result, the multi-path probability, the classifier's calibrated probability and
its SHAP explanation, and the tier/escalation decision.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server.app.ml.inference import ConflictEngine  # noqa: E402


def make_history(lat: float, lon: float, altitude_m: float, speed: float, heading: float,
                 vertical: float = 0.0, start: int = 1_800_000_000, steps: int = 10, step_s: int = 10):
    import math
    rows = []
    for k in range(steps):
        rows.append({"latitude": lat, "longitude": lon, "altitude_m": altitude_m, "velocity_ms": speed,
                     "heading_deg": heading, "vertical_rate_ms": vertical, "time_position": start + k * step_s})
        lat += speed * step_s * math.cos(math.radians(heading)) / 111_320.0
        lon += speed * step_s * math.sin(math.radians(heading)) / (111_320.0 * math.cos(math.radians(lat)))
        altitude_m += vertical * step_s
    return rows


def main() -> int:
    engine = ConflictEngine.load()
    print("Engine status:", json.dumps(engine.status(), indent=2))
    if engine.missing:
        print(f"WARNING: missing models {engine.missing}; rule path only.")

    # Two aircraft converging on a point roughly 4 minutes ahead, same level.
    a = make_history(19.5, 72.3, 10_000.0, 230.0, 90.0)
    b = make_history(19.5 + 0.42, 72.3 + 0.55, 10_050.0, 230.0, 200.0)

    trajectory = engine.predict_trajectory(a)
    print("\nTrajectory for aircraft A (1/3/5/10 min):")
    print(json.dumps({k: v for k, v in trajectory.items() if k != "multipath"}, indent=2, default=str))
    if "multipath" in trajectory:
        print(f"  multipath options: {len(trajectory['multipath'])}, probabilities "
              f"{[round(o['probability'], 3) for o in trajectory['multipath']]}")

    history: list[dict] = []
    for update in range(4):
        # Advance both aircraft 15 s per update, as the live feed would.
        a_hist = make_history(**_advance(a, update * 15))
        b_hist = make_history(**_advance(b, update * 15))
        result = engine.assess_pair(a_hist, b_hist, history)
        history.append(result)
        esc = result["escalation"]
        line = (f"update {update + 1}: rule CPA {result['rule']['cpa_lateral_distance_nm']:.2f} NM / "
                f"{result['rule']['cpa_vertical_separation_ft']:.0f} ft at {result['rule']['time_to_cpa_seconds']:.0f} s, "
                f"severity {result['rule']['severity']}; tier {esc['tier']} ({esc['tier_name']}), "
                f"p={esc['probability']:.2f}, runs {esc['consecutive_updates']}, notify {esc['notify']}")
        if "multipath" in result:
            line += f"; multipath p={result['multipath']['conflict_probability']:.2f}"
        if "classifier" in result:
            c = result["classifier"]
            line += f"; xgb p={c['conflict_probability']:.2f} alert={c['alert']}"
        print(line)
    if "classifier" in result:
        print("\nWhy (top SHAP contributions for the last update):")
        for item in result["classifier"]["explanation"]:
            print(f"  {item['feature']:<34} value {item['value']:>10.3f}  contribution {item['contribution']:>+8.4f}")
    print("\nSources used:", result["sources"])
    assert "rule" in result and "escalation" in result
    return 0


def _advance(history: list[dict], seconds: int) -> dict:
    import math
    last = history[0]
    lat, lon, alt = last["latitude"], last["longitude"], last["altitude_m"]
    heading, speed, vertical = last["heading_deg"], last["velocity_ms"], last["vertical_rate_ms"]
    lat += speed * seconds * math.cos(math.radians(heading)) / 111_320.0
    lon += speed * seconds * math.sin(math.radians(heading)) / (111_320.0 * math.cos(math.radians(lat)))
    return {"lat": lat, "lon": lon, "altitude_m": alt + vertical * seconds, "speed": speed, "heading": heading,
            "vertical": vertical, "start": last["time_position"] + seconds}


if __name__ == "__main__":
    raise SystemExit(main())
