"""End-to-end smoke test: run the whole pipeline on FAKE data in a temporary directory.

    python ml_pipeline/tests/smoke_test.py

Takes a few minutes on a laptop CPU. It proves every script runs, every artifact is
written, and the inference module can load and use all three models. It proves
NOTHING about model quality -- the data is invented (see fake_traffic.py) and every
gate is expected to say whatever it says. Real numbers come only from the real run.

Nothing here touches ml_pipeline/data or server/app/ml/saved_models: FLIGHT_RIGHT_DATA_ROOT
points every script at a temporary directory, which is deleted at the end unless
--keep is passed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "ml_pipeline" / "tests"))

from fake_traffic import write_fake_sessions  # noqa: E402

STEPS = ["check", "preprocess", "train_lstm", "benchmark", "multipath", "encounters", "xgboost"]


def run(cmd: list[str], env: dict[str, str]) -> None:
    started = time.monotonic()
    print(f"\n$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    print(f"  -> exit {result.returncode} in {time.monotonic() - started:.0f} s", flush=True)
    if result.returncode != 0:
        raise SystemExit(f"smoke test FAILED at: {' '.join(cmd)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep the temporary data root")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--scenarios", type=int, default=3000)
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="flight_right_smoke_"))
    print(f"Temporary data root: {root}")
    write_fake_sessions(root / "ml_pipeline" / "data" / "raw")
    env = dict(os.environ,
               FLIGHT_RIGHT_DATA_ROOT=str(root),
               FLIGHT_RIGHT_NUM_EPOCHS=str(args.epochs),
               FLIGHT_RIGHT_N_SCENARIOS=str(args.scenarios),
               FLIGHT_RIGHT_ALLOW_CPU="1",
               PYTHONIOENCODING="utf-8")
    try:
        run([sys.executable, "ml_pipeline/run_pipeline.py", "--only", *STEPS], env)

        models = root / "server" / "app" / "ml" / "saved_models"
        for artifact in ("trajectory_residual.pt", "trajectory_multipath.pkl", "xgboost_conflict.json",
                         "xgboost_conflict_model_card.json"):
            assert (models / artifact).exists(), f"missing artifact {artifact}"
            print(f"  artifact ok: {artifact} ({(models / artifact).stat().st_size / 1e6:.2f} MB)")

        # Load everything through the backend's inference module and assess one pair.
        run([sys.executable, "ml_pipeline/tests/inference_check.py"], env)
        print("\nSMOKE TEST PASSED -- the pipeline runs end to end. (Model quality is NOT tested here.)")
        return 0
    finally:
        if args.keep:
            print(f"Kept {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
