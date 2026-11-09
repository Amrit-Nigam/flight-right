"""Verify production-loader compatibility and measure isolated CPU batch inference."""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import resolve_artifact
from server.app.ml.inference import MultiPathPredictor


def main():
    report_dir = ROOT / "ml_pipeline/reports/multipath_tuning_20261101"
    study = json.loads((report_dir / "summary.json").read_text())
    policy = json.loads((report_dir / "benchmark_policy.json").read_text())
    work = ROOT / "ml_pipeline/data/processed/multipath_experiments/20261101"
    source_path, candidate_path = resolve_artifact(work / "baseline_multipath.pkl"), resolve_artifact(ROOT / study["winner"]["artifact"])
    source, candidate = MultiPathPredictor(source_path, "per_mode"), MultiPathPredictor(candidate_path, "per_mode")
    data = ROOT / "ml_pipeline/data/processed"
    with np.load(data / "trajectory_val.npz") as d:
        X = d["X"][:policy["batch_size"]]
    with np.load(data / "context_val.npz", allow_pickle=True) as d:
        extra = np.column_stack([d[k][:len(X)] for k in source.extra_features])
    before, after = source.predict(X, extra=extra), candidate.predict(X, extra=extra)
    assert np.array_equal(before[0], after[0]), "Probabilities changed"
    assert np.array_equal(before[2], after[2]), "Route pattern ranking changed"
    assert np.array_equal(before[1][:, :, :3], after[1][:, :, :3]), "Earlier horizons changed"
    assert np.isfinite(after[1]).all()
    timings = {"baseline": [], "candidate": []}
    for _ in range(policy["warmups"]):
        source.predict(X, extra=extra); candidate.predict(X, extra=extra)
    for _ in range(policy["interleaved_repetitions"]):
        for name, predictor in (("baseline", source), ("candidate", candidate)):
            start = time.perf_counter(); predictor.predict(X, extra=extra)
            timings[name].append(time.perf_counter() - start)
    medians = {k: float(np.median(v)) for k, v in timings.items()}
    result = {"policy": policy, "times_seconds": timings, "median_seconds": medians,
              "passes_cost_guard": medians["candidate"] <= medians["baseline"] * 1.25 + .010,
              "probabilities_identical": True, "patterns_identical": True, "earlier_horizons_identical": True,
              "finite_output": True, "artifact_bytes": {"baseline": source_path.stat().st_size,
                                                         "candidate": candidate_path.stat().st_size},
              "candidate_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest()}
    (report_dir / "inference_benchmark.json").write_text(json.dumps(result, indent=2))
    print(result)


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()
