"""Paired aircraft-group diagnostics on the already-frozen later-date candidate."""
import json
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")
import sys
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
import framing
import multipath as mp
from tune_multipath import energy_score


def main():
    reports = ROOT / "ml_pipeline/reports/multipath_tuning_20261101"
    assert (reports / "future_audit.json").exists(), "Finish the fixed-candidate audit first"
    work = ROOT / "ml_pipeline/data/processed/multipath_experiments/20261101"
    with np.load(ROOT / "ml_pipeline/data/processed/trajectory_experiments/20261101_horizon_head/future_holdout.npz", allow_pickle=True) as d:
        X, y, mask, aircraft = d["X"], d["y"], d["mask"], d["icao24"].astype(str)
    with np.load(work / "baseline_future_predictions.npz") as d:
        original, probabilities = d["positions"], d["probabilities"]
    with np.load(work / "candidate_seed0_future_predictions.npz") as d:
        candidate = d["positions"]
        assert np.array_equal(probabilities, d["probabilities"])
    cv = framing.constant_velocity_predict(X)
    scale = np.array([5 * 1852., 5 * 1852., 1000 / 3.28084])
    truth = framing.residual_targets(X, y, cv)[:, 3] / scale

    def observations(positions):
        lat = np.stack([framing.error_nm(positions[:, k], y)[:, 3] for k in range(5)], axis=1)
        ver = np.abs(positions[:, :, 3, 2] - y[:, None, 3, 2]) * 3.28084
        points = np.stack([framing.residual_targets(X, positions[:, k], cv)[:, 3] / scale for k in range(5)], axis=1)
        return {"top1_mean_nm": lat[:, 0], "top1_altitude_mae_ft": ver[:, 0],
                "best5_within_5nm": (lat < 5).any(axis=1).astype(float) * 100,
                "best5_both": ((lat < 5) & (ver < 1000)).any(axis=1).astype(float) * 100,
                "energy_score": energy_score(points, truth, probabilities)}
    baseline, tuned = observations(original), observations(candidate)
    result = {"method": "1000 paired bootstrap resamples of whole aircraft, seed 20261101; candidate minus baseline",
              "purpose": "Post-selection descriptive diagnostic; not used to rank candidates",
              "limitation": "Shared two-date cohort; aircraft resampling does not quantify between-day or airport generalization",
              "groups": {}}
    for group, rows in (("all", mask[:, 3]), ("arrivals", mask[:, 3] & mp.arrival_rows(X))):
        groups, inverse = np.unique(aircraft[rows], return_inverse=True)
        counts = np.bincount(inverse)
        weights = np.random.default_rng(20261101).multinomial(len(groups), np.full(len(groups), 1/len(groups)), size=1000)
        denominators = weights @ counts
        stats = {}
        for key in baseline:
            delta = tuned[key][rows] - baseline[key][rows]
            values = weights @ np.bincount(inverse, weights=delta, minlength=len(groups)) / denominators
            stats[key] = {"mean_difference": float(delta.mean()), "ci95": np.percentile(values, [2.5,97.5]).tolist()}
        result["groups"][group] = {"aircraft": len(groups), "windows": int(rows.sum()), "metrics": stats}
    (reports / "bootstrap_diagnostics.json").write_text(json.dumps(result, indent=2))
    print(result)


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()
