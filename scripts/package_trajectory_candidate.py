"""Package the predeclared seed-42 finalist with its own metrics; never deploy it."""
import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_pipeline.artifact_paths import resolve_artifact
RUN = "20261101_horizon_head"
REPORTS = ROOT / f"ml_pipeline/reports/trajectory_tuning_{RUN}"
WORK = ROOT / f"ml_pipeline/data/processed/trajectory_experiments/{RUN}"


def main():
    summary = json.loads((REPORTS / "summary.json").read_text())
    assert summary["selection"]["passes_validation_guardrails"]
    assert summary["selection"]["improves_validation_objective"]
    for r in summary["confirmation_validation"]:
        assert r["best"]["passes_guardrails"] and r["best"]["improves_objective"]
    for cohort in (summary["finalist_test"], summary["future_holdout"]["finalists"]):
        for r in cohort:
            assert r["comparison"]["passes_guardrails"] and r["comparison"]["improves_objective"]
    selected = summary["finalist_test"][0]
    assert selected["seed"] == 42, "Do not select a seed based on test performance"
    artifact = torch.load(ROOT / selected["artifact"], map_location="cpu", weights_only=False)
    baseline = torch.load(resolve_artifact(WORK / "baseline_trajectory_residual.pt"), map_location="cpu", weights_only=False)
    for key, weights in baseline["model_state_dict"].items():
        if not key.startswith("heads.3."):
            assert torch.equal(weights, artifact["model_state_dict"][key]), key
    artifact["source_training_summary"] = artifact.pop("training_summary")
    artifact["training_summary"] = {
        "method": "Fine-tune ten-minute head only; original encoder/shared/shorter heads frozen",
        "best_epoch": summary["selection"]["best_epoch"],
        "seed": 42, "learning_rate": summary["selection"]["config"]["lr"],
        "loss": "SmoothL1 beta 0.05", "samples": {"train": 205757, "val": 45637, "test": 39614},
        "test_per_horizon": selected["metrics"]["per_horizon"],
        "test_per_bucket": selected["metrics"]["per_bucket"],
        "gate_beats_constant_velocity": all(c["within_5_nm"] >= b["within_5_nm"] for c, b in
                                             zip(selected["metrics"]["per_horizon"], summary["constant_velocity_test"]["per_horizon"])),
        "later_date_audit": summary["future_holdout"]["finalists"][0]["metrics"],
        "guardrails_all_three_seeds": True,
        "shorter_horizons_unchanged": True,
        "source_model_sha256": summary["protocol"]["served_sha256_before"]["trajectory_residual.pt"],
        "experiment_report": f"ml_pipeline/reports/trajectory_tuning_{RUN}/summary.json",
        "deployment_status": "isolated candidate; not served",
    }
    path = WORK / "trajectory_residual_candidate.pt"
    torch.save(artifact, path)
    manifest = {"artifact": str(path.relative_to(ROOT)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "config": artifact["config"], "training_summary": artifact["training_summary"]}
    (REPORTS / "candidate_model_card.json").write_text(json.dumps(manifest, indent=2))
    print("Packaged", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
