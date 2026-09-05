# Training the Flight Right models on the RTX 4060 laptop

Everything below is one command once the environment is set up. Expected wall clock
for the full run on 36 sessions: **about 20-30 minutes**, most of it the LSTM (about
25 s per epoch, 30-40 epochs) and the encounter generator (pure Python, a few minutes).

## 0. What you need on disk

- The raw session files: `ml_pipeline/data/raw/session_*.parquet` (35-36 files, ~0.6 GB).
  They are gitignored, so they only exist on the machine that collected them.
- About 3 GB free.

## 1. Python environment (Windows, PowerShell)

```powershell
cd path\to\flight-right
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 2. PyTorch with CUDA (this is the step people get wrong)

`pip install torch` on Windows installs the **CPU-only** build. The 4060 needs the
CUDA build from PyTorch's own index. Pick the newest CUDA line shown at
<https://pytorch.org/get-started/locally/> (any cu12x works with the 4060's driver):

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

Then verify:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
# True NVIDIA GeForce RTX 4060 Laptop GPU
```

If it prints `False`, the CPU build got installed. Fix: `pip uninstall torch` and
re-run the command above with the `--index-url`.

## 3. Everything else

```powershell
pip install -r ml_pipeline/requirements.txt
```

The default `xgboost` wheel on Windows includes GPU support. `check_environment.py`
tells you whether it is being used; if not, it trains on the CPU in a few seconds and
nothing is lost.

## 4. Check, then run

```powershell
python ml_pipeline/check_environment.py      # every line should say OK (WARN is fine)
python ml_pipeline/run_pipeline.py           # the whole pipeline, in order
```

`run_pipeline.py` runs the seven steps below, streams everything to the screen, saves
each step's full output to `ml_pipeline/reports/logs/<run>/<step>.log`, and writes
`ml_pipeline/reports/training_report_<run>.md` with every GATE line, the headline
metric, the per-horizon tables and the calibration numbers. It stops at the first
failure; fix it and continue with `--from <step>`.

| step | script | what it produces |
|---|---|---|
| `check` | `check_environment.py` | nothing; refuses to continue if the GPU or data is missing |
| `preprocess` | `training/trajectory/preprocess_sequences.py` | `data/processed/trajectory_{train,val,test}.npz` |
| `train_lstm` | `training/trajectory/train_trajectory.py` | `saved_models/trajectory_residual.pt` |
| `benchmark` | `training/trajectory/reference_benchmark.py` | the tree reference the LSTM is compared against |
| `multipath` | `training/trajectory/multipath.py` | `saved_models/trajectory_multipath.pkl` (now with calibration) |
| `encounters` | `training/conflict_classifier/generate_synthetic_scenarios.py` | `data/synthetic/encounters_real_outcome_<ts>.parquet` |
| `xgboost` | `training/conflict_classifier/train_xgboost.py` | `saved_models/xgboost_conflict.json` + `_model_card.json` |

Useful variants:

```powershell
python ml_pipeline/run_pipeline.py --list                 # show the steps
python ml_pipeline/run_pipeline.py --from multipath       # resume after a fix
python ml_pipeline/run_pipeline.py --only xgboost         # retrain just the classifier
python ml_pipeline/run_pipeline.py --skip encounters      # reuse the last encounter file
```

## 5. What to send back

Send the whole `ml_pipeline/reports/` folder (the `.md` report and the `logs/` folder)
plus `server/app/ml/saved_models/xgboost_conflict_model_card.json`. The report is
written for someone who was not watching the run; the first thing to look at is the
**Gates** section and the `HEADLINE METRIC` block in the `xgboost` step.

Then run the inference check, which loads all three models exactly the way the
backend will and runs one converging pair through them:

```powershell
python ml_pipeline/tests/inference_check.py
```

## 6. Before the real run: prove the code works (optional, 3-5 minutes)

```powershell
python -m unittest ml_pipeline.tests.test_units     # unit tests, no data needed
python ml_pipeline/tests/smoke_test.py              # whole pipeline on FAKE data in a temp folder
```

The smoke test uses invented flight paths (see `tests/fake_traffic.py`) purely to
exercise the code. **Its gate results mean nothing and must never be quoted.** It never
touches `ml_pipeline/data` or `saved_models`.

## 7. Things that will bite

- **Do not run any poll script while training.** They share OpenSky credits with the
  scheduled sessions (rolling 24 h window, CLAUDE.md Section 14, 30 Aug).
- **Do not delete old model files by hand.** Every run overwrites them; the report
  records which run produced the current files.
- **A failing GATE is a result, not a bug to hide.** Report it as printed. Gate 1 of the
  classifier is expected to fail by about half a point until Archit decides on the
  recall margin; the `WHAT-IF` table in the `xgboost` step shows the cost of each
  option so that decision can be made.
- **The numbers move with every new session.** Never compare a model's score to a
  table from a previous run; compare it to the constant-velocity baseline or the
  rule-based detector measured in the SAME run, which every script prints beside it.
