"""Audit a validation-frozen multi-path finalist on the shared later-date cohort."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
sys.path.insert(0, str(ROOT))
import tune_multipath as tuning
from ml_pipeline.utils import route_features


def main():
    reports, work = tuning.REPORTS, tuning.WORK
    study = json.loads((reports / "summary.json").read_text())
    assert (reports / "selection_frozen_before_test.json").exists()
    path = ROOT / "ml_pipeline/data/processed/trajectory_experiments/20261101_horizon_head/future_holdout.npz"
    with np.load(path, allow_pickle=True) as data:
        X, y, mask, callsigns = data["X"], data["y"], data["mask"], data["callsign"]
    # Existing local route records only. Memoization avoids rereading the same JSON
    # thousands of times; it changes neither the inputs nor the lookup result.
    original_route = route_features.route
    route_features.route = functools.lru_cache(maxsize=10000)(original_route)
    try:
        extra = route_features.route_matrix(callsigns, X[:, -1, 0], X[:, -1, 1],
                                             route_features.track_from_window(X), fetch=False)
    finally:
        route_features.route = original_route
    baseline = pickle.loads((work / "baseline_multipath.pkl").read_bytes())
    chunks = []
    for start in range(0, len(X), 8192):
        stop = start + 8192
        chunks.append(tuning.prediction(baseline, X[start:stop], extra[start:stop]))
        print(f"Later-date baseline: {min(stop,len(X)):,}/{len(X):,} windows", flush=True)
    base = tuple(np.concatenate([c[i] for c in chunks]) for i in range(4))
    np.savez_compressed(work / "baseline_future_predictions.npz", positions=base[1], probabilities=base[0])
    metrics = tuning.score(base[1], X, y, mask, base[0])
    audits = []
    for finalist in study["finalists_validation"]:
        candidate = pickle.loads((ROOT / finalist["artifact"]).read_bytes())
        predictions = []
        for start in range(0, len(X), 8192):
            stop = start + 8192
            part = tuple(v[start:stop] for v in base)
            predictions.append(tuning.prediction(candidate, X[start:stop], extra[start:stop], part)[1])
        positions = np.concatenate(predictions)
        np.savez_compressed(work / f"candidate_seed{finalist['seed']}_future_predictions.npz", positions=positions, probabilities=base[0])
        score = tuning.score(positions, X, y, mask, base[0])
        audits.append({"seed": finalist["seed"], "metrics": score, "comparison": tuning.compare(score, metrics)})
        print("Later-date audit seed", finalist["seed"], audits[-1]["comparison"], flush=True)
    out = {"files": ["archive_20260910.parquet", "archive_20260920.parquet"], "samples": len(X),
           "data_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
           "route_known_fraction": float(np.isfinite(extra[:, 0]).mean()),
           "baseline": metrics, "audits": audits,
           "scope": "Shared exploratory later-date trajectory audit. No labels used for selection; no labelled encounter outcomes exist for this cohort, so alert-chain claims use the separate encounter test."}
    tuning.write(reports / "future_audit.json", out)
    print("Wrote later-date audit")


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()
