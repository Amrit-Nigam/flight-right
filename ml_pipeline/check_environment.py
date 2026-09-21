"""Check that this machine can run the training pipeline, and say what is missing.

Run this FIRST on the training laptop:

    python ml_pipeline/check_environment.py

It verifies the Python version, every required package, whether PyTorch and XGBoost
can see the GPU (the RTX 4060 should appear by name), how many raw data sessions are
on disk, and which trained models already exist. Exit code 0 means "go", 1 means
something needs fixing and the message says what.
"""

from __future__ import annotations

import glob
import importlib
import os
import platform
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
RAW = DATA_ROOT / "ml_pipeline" / "data" / "raw"
PROCESSED = DATA_ROOT / "ml_pipeline" / "data" / "processed"
SYNTHETIC = DATA_ROOT / "ml_pipeline" / "data" / "synthetic"
MODELS = DATA_ROOT / "server" / "app" / "ml" / "saved_models"

REQUIRED = ["numpy", "pandas", "pyarrow", "sklearn", "xgboost", "torch", "joblib", "requests", "dotenv"]
MIN_PYTHON = (3, 10)
# The full pipeline on 36 sessions needs roughly this much free disk for processed
# arrays, the synthetic encounter file and model artifacts.
MIN_FREE_GB = 3.0

OK, WARN, FAIL = "  OK   ", "  WARN ", "  FAIL "


def main() -> int:
    problems = 0
    print(f"Flight Right environment check on {platform.node()} ({platform.system()} {platform.release()})")
    print("")

    version = sys.version_info[:3]
    if version >= MIN_PYTHON:
        print(f"{OK} Python {'.'.join(map(str, version))}")
    else:
        print(f"{FAIL} Python {'.'.join(map(str, version))}; need {'.'.join(map(str, MIN_PYTHON))}+")
        problems += 1

    for name in REQUIRED:
        try:
            module = importlib.import_module(name)
            print(f"{OK} {name:<10} {getattr(module, '__version__', '')}")
        except Exception as error:  # noqa: BLE001
            print(f"{FAIL} {name:<10} not importable: {error}")
            problems += 1

    print("")
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            memory_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"{OK} PyTorch sees GPU: {name} ({memory_gb:.1f} GB), CUDA {torch.version.cuda}")
            if "4060" not in name:
                print(f"{WARN} expected an RTX 4060; found {name}. Training still works.")
        elif os.environ.get("FLIGHT_RIGHT_ALLOW_CPU"):
            print(f"{WARN} no GPU; FLIGHT_RIGHT_ALLOW_CPU is set so training will run on the CPU (slow).")
        else:
            print(f"{FAIL} PyTorch cannot see a GPU. torch {torch.__version__} (CUDA build: {torch.version.cuda}).")
            print("        Install the CUDA build: see ml_pipeline/README_TRAINING.md, step 2.")
            print("        To train on CPU anyway, set FLIGHT_RIGHT_ALLOW_CPU=1.")
            problems += 1
    except Exception as error:  # noqa: BLE001
        print(f"{FAIL} torch check failed: {error}")
        problems += 1

    try:
        import numpy as np
        import xgboost
        probe = xgboost.XGBClassifier(n_estimators=1, device="cuda", tree_method="hist")
        probe.fit(np.array([[0.0], [1.0], [0.0], [1.0]]), np.array([0, 1, 0, 1]))
        print(f"{OK} XGBoost {xgboost.__version__} trains on the GPU")
    except Exception as error:  # noqa: BLE001
        print(f"{WARN} XGBoost cannot use the GPU ({str(error).splitlines()[0][:80]}). It will train on CPU in seconds; fine.")

    print("")
    raw_files = sorted(glob.glob(str(RAW / "*.parquet")))
    if raw_files:
        total_mb = sum(Path(p).stat().st_size for p in raw_files) / 1e6
        print(f"{OK} raw data: {len(raw_files)} session file(s), {total_mb:.0f} MB in {RAW}")
        if len(raw_files) < 3:
            print(f"{FAIL} need at least 3 sessions to make train/val/test splits")
            problems += 1
    else:
        print(f"{FAIL} no raw parquet files in {RAW}. Copy the session_*.parquet files there.")
        problems += 1

    for label, path, pattern in (("processed splits", PROCESSED, "trajectory_*.npz"),
                                 ("synthetic encounters", SYNTHETIC, "encounters_real_outcome_*.parquet")):
        found = sorted(glob.glob(str(path / pattern)))
        print(f"{OK if found else WARN} {label}: {len(found)} file(s){'' if found else ' (the pipeline will create them)'}")

    print("")
    for model in ("trajectory_residual.pt", "trajectory_multipath.pkl", "xgboost_conflict.json"):
        path = MODELS / model
        if path.exists():
            print(f"{OK} model present: {model} ({path.stat().st_size / 1e6:.1f} MB) -- will be overwritten by a new run")
        else:
            print(f"{WARN} model absent:  {model} (the pipeline will train it)")

    free_gb = shutil.disk_usage(DATA_ROOT).free / 1e9
    print("")
    if free_gb >= MIN_FREE_GB:
        print(f"{OK} free disk: {free_gb:.1f} GB")
    else:
        print(f"{FAIL} free disk: {free_gb:.1f} GB; need about {MIN_FREE_GB:.0f} GB")
        problems += 1

    print("")
    if problems:
        print(f"{problems} problem(s). Fix the FAIL lines above, then re-run this check.")
        return 1
    print("Ready. Run:  python ml_pipeline/run_pipeline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
