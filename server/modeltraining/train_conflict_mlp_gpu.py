import argparse
import json
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm


FEATURE_NAMES = [
    "currentDistanceNm",
    "verticalSeparationFt",
    "headingDiffDeg",
    "speedDiffKt",
    "relAltitudeFt",
    "relVerticalRateFpm",
    "closingSpeedKt",
    "minProjectedDistanceNm",
    "timeToMinMinutes",
    "speedA",
    "speedB",
    "altitudeA",
    "altitudeB",
]


class ConflictMLP(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.15),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.10),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_matrix(rows):
    x = []
    y = []
    for row in rows:
        features = row.get("features", {})
        x.append([float(features.get(name, 0.0) or 0.0) for name in FEATURE_NAMES])
        y.append(int(row.get("label", 0)))
    return np.asarray(x, dtype=np.float32), np.asarray(y, dtype=np.float32)


def evaluate(model, x, y, device):
    model.eval()
    with torch.no_grad():
        logits = model(torch.from_numpy(x).to(device)).cpu().numpy()
    probs = 1.0 / (1.0 + np.exp(-logits))
    preds = (probs >= 0.5).astype(np.int32)
    y_int = y.astype(np.int32)
    return {
        "accuracy": float(accuracy_score(y_int, preds)),
        "precision": float(precision_score(y_int, preds, zero_division=0)),
        "recall": float(recall_score(y_int, preds, zero_division=0)),
        "f1": float(f1_score(y_int, preds, zero_division=0)),
        "positives": int(y_int.sum()),
        "rows": int(len(y_int)),
    }


def main():
    parser = argparse.ArgumentParser(description="Train a small GPU-friendly conflict classifier on OpenSky-derived pairs.")
    parser.add_argument("--data", default="data/conflict-pairs.jsonl", help="Path to conflict-pairs JSONL")
    parser.add_argument("--out", default="artifacts/conflict-mlp-gpu.pt", help="Output PyTorch checkpoint")
    parser.add_argument("--meta", default="artifacts/conflict-mlp-gpu-meta.json", help="Output metadata JSON")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    data_path = (base_dir / args.data).resolve() if not Path(args.data).is_absolute() else Path(args.data)
    out_path = (base_dir / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    meta_path = (base_dir / args.meta).resolve() if not Path(args.meta).is_absolute() else Path(args.meta)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    rows = read_jsonl(data_path)
    if len(rows) < 20:
        raise SystemExit(f"Need at least 20 rows, found {len(rows)}. Run collect + dataset steps first.")

    x, y = build_matrix(rows)
    positives = int(y.sum())
    if positives == 0:
        raise SystemExit("Dataset has 0 positive labels. Collect longer or loosen conflict thresholds for MVP training.")

    stratify = y if positives > 1 and positives < len(y) - 1 else None
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=args.test_size, random_state=args.seed, stratify=stratify
    )

    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train).astype(np.float32)
    x_test = scaler.transform(x_test).astype(np.float32)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[gpu-train] device: {device}")
    if device.type == "cuda":
        print(f"[gpu-train] gpu: {torch.cuda.get_device_name(0)}")

    train_ds = TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train))
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)

    model = ConflictMLP(input_dim=len(FEATURE_NAMES)).to(device)
    pos_weight_value = max(1.0, float((len(y_train) - y_train.sum()) / max(1.0, y_train.sum())))
    criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight_value, device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    for epoch in tqdm(range(args.epochs), desc="training"):
        model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(xb)
        if (epoch + 1) % 20 == 0 or epoch == 0:
            print(f"[gpu-train] epoch {epoch + 1}/{args.epochs}, loss={total_loss / len(train_ds):.5f}")

    train_metrics = evaluate(model, x_train, y_train, device)
    test_metrics = evaluate(model, x_test, y_test, device)

    checkpoint = {
        "model_state_dict": model.state_dict(),
        "feature_names": FEATURE_NAMES,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "threshold": 0.5,
        "model_type": "pytorch_mlp_conflict_classifier",
    }
    torch.save(checkpoint, out_path)

    metadata = {
        "modelType": "pytorch_mlp_conflict_classifier",
        "createdAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "dataPath": str(data_path),
        "rows": int(len(rows)),
        "positives": positives,
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
        "featureNames": FEATURE_NAMES,
        "epochs": args.epochs,
        "batchSize": args.batch_size,
        "learningRate": args.lr,
        "trainMetrics": train_metrics,
        "testMetrics": test_metrics,
        "checkpoint": str(out_path),
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"[gpu-train] train metrics: {train_metrics}")
    print(f"[gpu-train] test metrics: {test_metrics}")
    print(f"[gpu-train] wrote {out_path}")
    print(f"[gpu-train] wrote {meta_path}")


if __name__ == "__main__":
    main()
