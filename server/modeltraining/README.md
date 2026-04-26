# Server Model Training

This folder is for model training using **real OpenSky data only**.

There are two training paths:

```text
Mac / low-power path:
OpenSky snapshots -> aircraft-pair features -> CPA labels -> pure Node logistic baseline

Windows NVIDIA path:
OpenSky snapshots -> aircraft-pair features -> CPA labels -> PyTorch MLP GPU model
```

For your RTX 4060 laptop with 16GB RAM, use the Windows NVIDIA path. The model is intentionally moderate: a small MLP classifier, not a huge deep learning model.

## Why This First

For a final-year MVP, the model needs to connect to the actual app pipeline. This folder creates the missing bridge:

- collect real OpenSky aircraft states
- transform them into aircraft-pair training rows
- label pairs with a CPA-style separation rule
- train a small baseline conflict-risk classifier
- save a model artifact that can later be loaded by the backend

## Files

| File | Purpose |
|---|---|
| `collect-opensky.js` | Collects live OpenSky snapshots into `data/opensky-snapshots.jsonl` |
| `build-conflict-dataset.js` | Builds pairwise aircraft features and labels into `data/conflict-pairs.jsonl` |
| `train-conflict-baseline.js` | Trains a pure Node logistic regression baseline |
| `train_conflict_mlp_gpu.py` | Trains a small PyTorch MLP conflict classifier, GPU-ready |
| `requirements-gpu.txt` | Windows/NVIDIA Python dependency list, excluding PyTorch |
| `lib/geo.js` | Distance, projection, CPA-style geometry helpers |
| `data/` | Local generated training data, ignored by git |
| `artifacts/` | Local generated model artifacts, ignored by git |

## Recommended Path for RTX 4060 Windows Laptop

Use this if you want a decent GPU-trained MVP model without making the project too heavy.

### 0. System Requirements

Recommended:

- Windows 10/11
- NVIDIA RTX 4060
- 16GB RAM
- Python 3.10 or 3.11
- Node.js 18+
- Git
- NVIDIA driver installed

You do **not** need to manually install the full CUDA Toolkit if you install the correct PyTorch CUDA wheel. PyTorch ships the CUDA runtime in the wheel.

Check GPU visibility:

```powershell
nvidia-smi
```

If this does not show your RTX 4060, update NVIDIA drivers first.

### 1. Create Python Virtual Environment

From:

```powershell
cd server\\modeltraining
```

Run:

```powershell
py -3.11 -m venv .venv
.\\.venv\\Scripts\\activate
python -m pip install --upgrade pip
```

If Python 3.11 is not installed, use:

```powershell
py -3.10 -m venv .venv
.\\.venv\\Scripts\\activate
python -m pip install --upgrade pip
```

### 2. Install PyTorch With CUDA

For most RTX 4060 laptops, use the official CUDA 12.1 wheel:

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify:

```powershell
python -c \"import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')\"
```

Expected:

```text
True
NVIDIA GeForce RTX 4060 Laptop GPU
```

If it prints `False`, the trainer will still run on CPU, but fix drivers/PyTorch before serious training.

### 3. Install Other Training Dependencies

```powershell
pip install -r requirements-gpu.txt
```

### 4. Collect Real OpenSky Training Data

Run this from `server/`, not inside `server/modeltraining`:

```powershell
cd ..
npm run collect:opensky
```

For more useful data, collect longer:

```powershell
$env:TRAINING_SAMPLES=\"60\"
$env:TRAINING_INTERVAL_MS=\"120000\"
npm run collect:opensky
```

This collects one snapshot every 2 minutes for about 2 hours.

Important:

- OpenSky may return `429` if rate-limited.
- Do not spam requests.
- More snapshots usually means better training rows.

### 5. Build Conflict Pair Dataset

Still from `server/`:

```powershell
npm run dataset:conflicts
```

If you get 0 positive conflict labels, that is normal with real traffic because actual conflicts are rare.

For MVP experimentation, temporarily loosen thresholds:

```powershell
$env:CONFLICT_LATERAL_NM=\"20\"
$env:CONFLICT_VERTICAL_FT=\"3000\"
npm run dataset:conflicts
```

Be honest in evaluation that this is a threshold-tuned academic label generator.

### 6. Train GPU MLP Model

From `server/modeltraining` with the Python environment activated:

```powershell
python train_conflict_mlp_gpu.py --epochs 80 --batch-size 256
```

Outputs:

```text
artifacts/conflict-mlp-gpu.pt
artifacts/conflict-mlp-gpu-meta.json
```

The `.pt` file is the model checkpoint. The `.json` file contains metrics and model metadata for your report.

### 7. Suggested RTX 4060 Settings

Good defaults:

```powershell
python train_conflict_mlp_gpu.py --epochs 80 --batch-size 256 --lr 0.001
```

If memory is fine and dataset is bigger:

```powershell
python train_conflict_mlp_gpu.py --epochs 120 --batch-size 512 --lr 0.001
```

If training is unstable:

```powershell
python train_conflict_mlp_gpu.py --epochs 100 --batch-size 128 --lr 0.0005
```

This is intentionally not a huge model. For this project, a clean data pipeline + explainable workflow matters more than a giant neural network.

### 8. What This Model Is

This is a conflict-risk classifier:

```text
input: pairwise aircraft features
output: probability of conflict-like CPA threshold breach
```

It is not a full 4D trajectory generative model. It is a practical MVP model that can later power:

```text
GET /api/conflicts/active
```

### 9. What To Say In Evaluation

Good answer:

> We used OpenSky snapshots to build pairwise aircraft features. Labels are generated using a CPA-based separation threshold. On a GPU laptop, we train a small PyTorch MLP classifier to estimate conflict risk. This is a practical MVP model. We also keep a deterministic CPA baseline because safety-critical systems should not depend only on a black-box model.

Do not claim:

- this is certified for ATC
- this model is enough for real aircraft control
- this replaces controller judgment
- this fully solves 4D trajectory prediction

Correct claim:

> This is a research-informed decision-support classifier for an academic MVP.

## Step 1: Collect Real OpenSky Data

From `server/`:

```bash
npm run collect:opensky
```

Defaults:

- `TRAINING_SAMPLES=12`
- `TRAINING_INTERVAL_MS=60000`
- Mumbai/BOM bounding box from `.env`

Important:

OpenSky can return `429` if rate-limited. The collector waits at least 60 seconds between attempts to keep this light.

Optional:

```bash
TRAINING_SAMPLES=30 TRAINING_INTERVAL_MS=120000 npm run collect:opensky
```

## Step 2: Build Conflict Dataset

```bash
npm run dataset:conflicts
```

This creates aircraft pairs from each snapshot and computes features like:

- current distance in NM
- vertical separation
- heading difference
- speed difference
- closing speed
- projected minimum distance
- time to projected minimum distance

Labels are rule-derived:

```text
label = 1 if projected lateral separation <= 5 NM
          and vertical separation <= 1000 ft
          within the lookahead window
```

This is not a certified ATC rule. It is an academic MVP label generator.

## Step 3: Train Lightweight Baseline

```bash
npm run train:conflicts
```

Output:

```text
modeltraining/artifacts/conflict-baseline-model.json
```

The artifact contains:

- feature names
- scaler means/stds
- logistic regression weights
- threshold
- training metrics

## One Command After Data Exists

```bash
npm run model:conflicts
```

This runs:

```text
dataset:conflicts -> train:conflicts
```

## If Training Fails With 0 Positives

That means real OpenSky data did not contain close conflict-like pairs in your collection window. This is normal because real conflicts are rare.

Options:

1. Collect longer.
2. Increase bounding box.
3. Temporarily loosen training thresholds for academic experimentation:

```bash
CONFLICT_LATERAL_NM=20 CONFLICT_VERTICAL_FT=3000 npm run dataset:conflicts
npm run train:conflicts
```

Be honest in evaluation:

> Real unsafe conflicts are rare, so initial labels are CPA-rule-derived and threshold-tunable for MVP experimentation.

## Next Step

After this baseline works, add backend inference:

```text
GET /api/conflicts/active
```

That endpoint should:

1. load `conflict-baseline-model.json`
2. build live aircraft-pair features
3. score conflict probability
4. return ranked conflicts to the dashboard
