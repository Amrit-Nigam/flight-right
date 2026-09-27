"""Score a multi-path pickle in THREE dimensions, not only horizontally.

    python ml_pipeline/utils/multipath_3d_eval.py [label=path.pkl ...]

multipath.py's gates score "within 5 NM" -- horizontal distance only. A conflict is
5 NM AND 1,000 ft, and the constant-velocity rule's misses were almost all vertical, so
the altitude side of each candidate path matters as much. Measured 25 Sep 2026: the
per-pattern table's altitude is no better than a straight line (its KMeans patterns are
2-D), while the per-mode regressors halve the ten-minute altitude error.

For each pickle, on the existing test split: altitude error of the likeliest path per
horizon, and best-of-K within 5 NM, within 1,000 ft, and within BOTH, for arrivals and
all traffic. Constant velocity is scored beside it (Part 3 rule 4). No argument = the
served pickle in both offset modes. Writes ml_pipeline/reports/multipath_3d_<stamp>.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))

import framing  # noqa: E402
import multipath as mp  # noqa: E402

FT = 3.28084
HORIZONS = ("1 min", "3 min", "5 min", "10 min")


def score(positions: np.ndarray, X: np.ndarray, y: np.ndarray, mask: np.ndarray) -> dict:
    """positions (N, K, 4, 3). K = 1 for a single-answer method."""
    arrivals = mp.arrival_rows(X)
    lateral = np.stack([framing.error_nm(positions[:, k], y) for k in range(positions.shape[1])], 1)
    vertical = np.abs(positions[..., 2] - y[:, None, :, 2]) * FT
    out = {"top1_altitude": {}, "ten_minutes": {}}
    for h, name in enumerate(HORIZONS):
        e = vertical[mask[:, h], 0, h]
        out["top1_altitude"][name] = {"mean_ft": float(e.mean()), "within_1000_ft": float((e < 1000).mean() * 100)}
    rows10 = mask[:, 3]
    for label, rows in (("arrivals", arrivals & rows10), ("all", rows10)):
        lat, ver = lateral[rows][:, :, 3], vertical[rows][:, :, 3]
        out["ten_minutes"][label] = {
            f"best_of_{k}": {"within_5nm": float(np.any(lat[:, :k] < 5, 1).mean() * 100),
                             "within_1000ft": float(np.any(ver[:, :k] < 1000, 1).mean() * 100),
                             "within_both": float(np.any((lat[:, :k] < 5) & (ver[:, :k] < 1000), 1).mean() * 100)}
            for k in sorted({1, min(5, positions.shape[1])})}
    return out


def main() -> None:
    from server.app.ml.inference import MULTIPATH_PATH, MultiPathPredictor

    data = np.load(ROOT / "ml_pipeline/data/processed/trajectory_test.npz")
    X, y, mask = data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)
    models = [arg.split("=", 1) for arg in sys.argv[1:]] or [["served_table", f"{MULTIPATH_PATH}|table"],
                                                             ["served_per_mode", f"{MULTIPATH_PATH}|per_mode"]]
    results = {"constant_velocity": score(framing.constant_velocity_predict(X)[:, None], X, y, mask)}
    for label, spec in models:
        path, _, offsets = spec.partition("|")
        predictor = MultiPathPredictor(Path(path), offsets=offsets or "per_mode")
        _, positions, _ = predictor.predict(X, extra=predictor.saved_split_inputs("test"))
        results[label] = score(positions, X, y, mask)
    for label, block in results.items():
        ten = block["ten_minutes"]["arrivals"]
        k = "best_of_5" if "best_of_5" in ten else "best_of_1"
        print(f"{label:<24} alt 10 min mean {block['top1_altitude']['10 min']['mean_ft']:6.0f} ft | arrivals {k}: "
              f"5 NM {ten[k]['within_5nm']:5.1f}%  1,000 ft {ten[k]['within_1000ft']:5.1f}%  BOTH {ten[k]['within_both']:5.1f}% "
              f"| top-1 BOTH {ten['best_of_1']['within_both']:5.1f}%")
    out = ROOT / "ml_pipeline/reports" / f"multipath_3d_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
