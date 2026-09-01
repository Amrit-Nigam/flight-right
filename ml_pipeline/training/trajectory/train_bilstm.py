"""Train the baseline multi-horizon Bi-LSTM trajectory model."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


NUM_EPOCHS = 60
EARLY_STOPPING_PATIENCE = 10
BATCH_SIZE = 64
LEARNING_RATE = 0.001
HIDDEN_SIZE = 128
NUM_LAYERS = 2
DROPOUT = 0.3
RANDOM_SEED = 42

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "processed"
MODEL_PATH = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models" / "bilstm_trajectory.pt"


class BiLSTMTrajectoryModel(nn.Module):
    """Ten steps of eight flight-state features -> four (lat, lon, altitude) heads."""

    def __init__(self) -> None:
        super().__init__()
        self.lstm = nn.LSTM(8, HIDDEN_SIZE, num_layers=NUM_LAYERS, batch_first=True, bidirectional=True, dropout=DROPOUT)
        self.heads = nn.ModuleList(nn.Linear(HIDDEN_SIZE * 2, 3) for _ in range(4))

    def forward(self, sequence: torch.Tensor) -> torch.Tensor:
        outputs, _ = self.lstm(sequence)
        # The forward direction summarises the window at its last step and the
        # backward direction at its first. Taking outputs[:, -1, :] would pair the
        # forward summary with a backward state that has seen only the final input,
        # wasting half the network.
        forward_summary = outputs[:, -1, :HIDDEN_SIZE]
        backward_summary = outputs[:, 0, HIDDEN_SIZE:]
        final_state = torch.cat([forward_summary, backward_summary], dim=1)
        return torch.stack([head(final_state) for head in self.heads], dim=1)


def load_split(name: str) -> tuple[np.ndarray, np.ndarray]:
    path = DATA_DIRECTORY / f"trajectory_{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run preprocess_sequences.py first.")
    with np.load(path) as data:
        return data["X"].astype(np.float32), data["y"].astype(np.float32)


def normalize_arrays(train_x: np.ndarray, train_y: np.ndarray, *arrays: np.ndarray) -> tuple[list[np.ndarray], dict[str, np.ndarray]]:
    """Fit scaling on train only; this prevents validation/test information leakage."""
    x_mean, x_std = train_x.mean(axis=(0, 1), keepdims=True), train_x.std(axis=(0, 1), keepdims=True)
    y_mean, y_std = train_y.mean(axis=(0, 1), keepdims=True), train_y.std(axis=(0, 1), keepdims=True)
    x_std[x_std < 1e-6] = 1.0
    y_std[y_std < 1e-6] = 1.0
    normalized = []
    for index, array in enumerate(arrays):
        normalized.append((array - (x_mean if index % 2 == 0 else y_mean)) / (x_std if index % 2 == 0 else y_std))
    return normalized, {"x_mean": x_mean, "x_std": x_std, "y_mean": y_mean, "y_std": y_std}


def make_loader(x: np.ndarray, y: np.ndarray, shuffle: bool) -> DataLoader:
    return DataLoader(TensorDataset(torch.from_numpy(x), torch.from_numpy(y)), batch_size=BATCH_SIZE, shuffle=shuffle)


def average_loss(model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device) -> float:
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for x_batch, y_batch in loader:
            loss = criterion(model(x_batch.to(device)), y_batch.to(device))
            total += loss.item() * len(x_batch)
            count += len(x_batch)
    return total / count


def evaluate_real_units(model: nn.Module, loader: DataLoader, y_mean: np.ndarray, y_std: np.ndarray, device: torch.device) -> None:
    """Report horizontal error in metres and altitude error in metres, not degrees."""
    model.eval()
    predictions, actuals = [], []
    with torch.no_grad():
        for x_batch, y_batch in loader:
            predictions.append(model(x_batch.to(device)).cpu().numpy())
            actuals.append(y_batch.numpy())
    predicted = np.concatenate(predictions) * y_std + y_mean
    actual = np.concatenate(actuals) * y_std + y_mean
    lat_error_m = (predicted[..., 0] - actual[..., 0]) * 111_320.0
    lon_error_m = (predicted[..., 1] - actual[..., 1]) * 111_320.0 * np.cos(np.deg2rad(actual[..., 0]))
    horizontal_error_m = np.hypot(lat_error_m, lon_error_m)
    altitude_error_m = predicted[..., 2] - actual[..., 2]
    print(f"Test horizontal MAE: {np.mean(np.abs(horizontal_error_m)):.2f} m ({np.mean(np.abs(horizontal_error_m)) / 1852:.4f} NM)")
    print(f"Test horizontal RMSE: {np.sqrt(np.mean(horizontal_error_m ** 2)):.2f} m")
    print(f"Test altitude MAE: {np.mean(np.abs(altitude_error_m)):.2f} m")
    print(f"Test altitude RMSE: {np.sqrt(np.mean(altitude_error_m ** 2)):.2f} m")


def main() -> None:
    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    train_x, train_y = load_split("train")
    val_x, val_y = load_split("val")
    test_x, test_y = load_split("test")
    if min(len(train_x), len(val_x), len(test_x)) == 0:
        raise ValueError("Each split needs at least one sample; collect more data before training.")
    (train_x, train_y, val_x, val_y, test_x, test_y), statistics = normalize_arrays(train_x, train_y, train_x, train_y, val_x, val_y, test_x, test_y)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'}")
    print(f"Samples: {len(train_x)} train / {len(val_x)} val / {len(test_x)} test")
    model = BiLSTMTrajectoryModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.MSELoss()  # Mean over all four heads: each horizon has equal weight.
    train_loader, val_loader, test_loader = make_loader(train_x, train_y, True), make_loader(val_x, val_y, False), make_loader(test_x, test_y, False)

    best_validation_loss = float("inf")
    best_state = None
    best_epoch = 0
    epochs_without_improvement = 0

    for epoch in range(1, NUM_EPOCHS + 1):
        model.train()
        total, count = 0.0, 0
        for x_batch, y_batch in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(x_batch.to(device)), y_batch.to(device))
            loss.backward()
            optimizer.step()
            total += loss.item() * len(x_batch)
            count += len(x_batch)
        validation_loss = average_loss(model, val_loader, criterion, device)

        # Keep the best weights rather than whatever the final epoch produced.
        marker = ""
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            best_epoch = epoch
            epochs_without_improvement = 0
            marker = "  <- best"
        else:
            epochs_without_improvement += 1
        print(f"Epoch {epoch:02d}/{NUM_EPOCHS} | train loss: {total / count:.6f} | val loss: {validation_loss:.6f}{marker}")

        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print(f"Stopping early: validation loss has not improved for {EARLY_STOPPING_PATIENCE} epochs.")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    print("")
    print(f"Evaluating the best checkpoint (epoch {best_epoch}, val loss {best_validation_loss:.6f}).")
    evaluate_real_units(model, test_loader, statistics["y_mean"], statistics["y_std"], device)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": model.state_dict(), "config": {"input_size": 8, "hidden_size": HIDDEN_SIZE, "num_layers": NUM_LAYERS, "dropout": DROPOUT}, "normalization": statistics}, MODEL_PATH)
    print(f"Saved model weights: {MODEL_PATH}")


if __name__ == "__main__":
    main()
