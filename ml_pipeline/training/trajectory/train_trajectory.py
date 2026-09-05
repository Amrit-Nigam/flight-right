"""Train the multi-horizon trajectory model as a residual on constant velocity.

Why this is not the previous Bi-LSTM. That model normalised its targets with
    y_std = train_y.std(axis=(0, 1))
which collapses the horizon axis and divides absolute latitude/longitude by the
spatial spread of the whole collection region (measured: 1.867 degrees of latitude).
5 NM is 0.083 degrees, i.e. 0.045 standard deviations, so the entire range from a
perfect prediction to a useless one occupied 0 to 0.045 of the space the loss
function could see. The same normalisation applied to the inputs shrank the
aircraft's motion within its ten-step window to 1.9% of one standard deviation of
the latitude feature: the network could see WHERE an aircraft was but not WHICH WAY
it was going.

This model predicts the residual from the constant-velocity extrapolation, in metres,
in a frame rotated onto the aircraft's own heading. Zero output reproduces the
baseline exactly, so the model starts at the baseline and can only be pushed off it
by evidence.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch import nn

import evaluate
import framing


NUM_EPOCHS = 60
EARLY_STOPPING_PATIENCE = 10
BATCH_SIZE = 64
LEARNING_RATE = 0.001
HIDDEN_SIZE = 128
NUM_LAYERS = 2
DROPOUT = 0.3
# SmoothL1 is quadratic below beta and absolute above it, and beta is measured in
# NORMALISED residual units -- so it interacts with the per-horizon normalisation.
# At beta = 1.0 the quadratic region reaches one standard deviation of the residual,
# which at the 10-minute horizon is 11.5 NM: measured, 86% of along-track and 81% of
# cross-track targets fell inside it, making the loss effectively MSE for the bulk of
# the data and reproducing the failure this loss was chosen to avoid (a run at 1.0
# improved the 10-minute mean to 6.84 NM while dropping within-1-NM from the
# baseline's 32.6% to 12.9%). At 0.05 the quadratic region is ~0.5 NM at ten minutes
# and ~0.02 NM at one, so it only smooths the gradient near zero and the loss is
# absolute error everywhere that matters.
SMOOTH_L1_BETA = 0.05
PROGRESS_EVERY_EPOCHS = 5
RANDOM_SEED = 42

SEQUENCE_FEATURES = len(framing.SEQUENCE_FEATURE_NAMES)
SCALAR_FEATURES = len(framing.SCALAR_FEATURE_NAMES)
NUM_HORIZONS = len(framing.HORIZONS_SECONDS)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "processed"
MODEL_PATH = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models" / "trajectory_residual.pt"


class ResidualTrajectoryModel(nn.Module):
    """Local-frame window + window scalars -> four (along, cross, altitude) residual heads."""

    def __init__(self) -> None:
        super().__init__()
        # Unidirectional: at inference time there is no future to read backwards from,
        # so a bidirectional encoder would train on information it cannot be given.
        self.lstm = nn.LSTM(SEQUENCE_FEATURES, HIDDEN_SIZE, num_layers=NUM_LAYERS, batch_first=True, dropout=DROPOUT)
        self.shared = nn.Sequential(nn.Linear(HIDDEN_SIZE + SCALAR_FEATURES, HIDDEN_SIZE), nn.ReLU())
        self.heads = nn.ModuleList(nn.Linear(HIDDEN_SIZE, 3) for _ in range(NUM_HORIZONS))

    def forward(self, sequence: torch.Tensor, scalars: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.lstm(sequence)
        summary = torch.cat([hidden[-1], scalars], dim=1)
        shared = self.shared(summary)
        return torch.stack([head(shared) for head in self.heads], dim=1)


def load_split(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = DATA_DIRECTORY / f"trajectory_{name}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run preprocess_sequences.py first.")
    with np.load(path) as data:
        if "mask" not in data:
            raise KeyError(f"{path} predates per-horizon masking. Re-run preprocess_sequences.py.")
        return data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)


def fit_feature_statistics(sequence: np.ndarray, scalars: np.ndarray) -> dict[str, np.ndarray]:
    """Standardise each feature using training data only, to avoid leaking val/test."""
    statistics = {
        "sequence_mean": sequence.mean(axis=(0, 1)),
        "sequence_std": sequence.std(axis=(0, 1)),
        "scalar_mean": scalars.mean(axis=0),
        "scalar_std": scalars.std(axis=0),
    }
    statistics["sequence_std"][statistics["sequence_std"] < 1e-6] = 1.0
    statistics["scalar_std"][statistics["scalar_std"] < 1e-6] = 1.0
    return statistics


def fit_residual_statistics(residual: np.ndarray, mask: np.ndarray) -> dict[str, np.ndarray]:
    """Per-horizon, per-axis residual scaling over mask-valid entries only.

    This is load-bearing now that the targets are residuals: their magnitude grows
    roughly ninefold from the 1-minute to the 10-minute horizon, so a single shared
    scale would let the 10-minute head dominate the loss. On the old absolute-position
    targets the equivalent weighting was a no-op -- the four per-horizon standard
    deviations measured 1.873 / 1.865 / 1.861 / 1.869, identical by construction.
    """
    mean = np.zeros((NUM_HORIZONS, 3), dtype=np.float64)
    std = np.ones((NUM_HORIZONS, 3), dtype=np.float64)
    for horizon_index in range(NUM_HORIZONS):
        valid = residual[mask[:, horizon_index], horizon_index, :]
        mean[horizon_index] = valid.mean(axis=0)
        std[horizon_index] = np.where(valid.std(axis=0) < 1e-6, 1.0, valid.std(axis=0))
    return {"residual_mean": mean, "residual_std": std}


def prepare(X: np.ndarray, y: np.ndarray, mask: np.ndarray, feature_statistics: dict, residual_statistics: dict):
    """Turn a raw split into the standardised tensors the model consumes."""
    cv = framing.constant_velocity_predict(X)
    sequence, scalars = framing.to_local_features(X)
    residual = framing.residual_targets(X, y, cv)
    normalized_sequence = (sequence - feature_statistics["sequence_mean"]) / feature_statistics["sequence_std"]
    normalized_scalars = (scalars - feature_statistics["scalar_mean"]) / feature_statistics["scalar_std"]
    normalized_residual = (residual - residual_statistics["residual_mean"]) / residual_statistics["residual_std"]
    return (
        torch.from_numpy(normalized_sequence.astype(np.float32)),
        torch.from_numpy(normalized_scalars.astype(np.float32)),
        torch.from_numpy(normalized_residual.astype(np.float32)),
        torch.from_numpy(mask.astype(np.float32)),
        cv,
    )


def masked_loss(predicted: torch.Tensor, target: torch.Tensor, mask: torch.Tensor, criterion: nn.Module) -> torch.Tensor:
    """Average SmoothL1 over valid horizons only; invalid ones contribute no gradient."""
    element_loss = criterion(predicted, target) * mask[:, :, None]
    return element_loss.sum() / mask.sum().clamp(min=1.0) / 3.0


def iterate_batches(tensors: tuple[torch.Tensor, ...], shuffle: bool):
    """Batch by indexing tensors that already live on the device.

    The whole split is about 30 MB, so keeping it resident and slicing it is far
    cheaper than a DataLoader copying every 64-row batch across the bus -- on this
    laptop GPU the transfer, not the arithmetic, was setting the epoch time.
    """
    count = len(tensors[0])
    device = tensors[0].device
    order = torch.randperm(count, device=device) if shuffle else torch.arange(count, device=device)
    for start in range(0, count, BATCH_SIZE):
        index = order[start:start + BATCH_SIZE]
        yield tuple(tensor[index] for tensor in tensors)


def run_epoch(model, tensors, criterion, optimizer=None) -> float:
    model.train() if optimizer is not None else model.eval()
    total, count = 0.0, 0
    with torch.set_grad_enabled(optimizer is not None):
        for sequence, scalars, residual, mask in iterate_batches(tensors, shuffle=optimizer is not None):
            loss = masked_loss(model(sequence, scalars), residual, mask, criterion)
            if optimizer is not None:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total += loss.item() * len(sequence)
            count += len(sequence)
    return total / count


def predict_absolute(model, sequence: torch.Tensor, scalars: torch.Tensor, X: np.ndarray, cv: np.ndarray,
                     residual_statistics: dict, device: torch.device) -> np.ndarray:
    """Run the model and undo both the residual scaling and the residual framing."""
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(sequence), 1024):
            batch = model(sequence[start:start + 1024].to(device), scalars[start:start + 1024].to(device))
            outputs.append(batch.cpu().numpy())
    normalized = np.concatenate(outputs).astype(np.float64)
    residual = normalized * residual_statistics["residual_std"] + residual_statistics["residual_mean"]
    return framing.apply_residual(X, cv, residual)


def print_within_five(predictions: np.ndarray, cv: np.ndarray, y: np.ndarray, mask: np.ndarray, prefix: str) -> None:
    """The check that a training run must never again finish without showing."""
    model_error = framing.error_nm(predictions, y)
    baseline_error = framing.error_nm(cv, y)
    parts = []
    for horizon_index, horizon in enumerate(framing.HORIZONS_SECONDS):
        rows = mask[:, horizon_index]
        model_rate = (model_error[rows, horizon_index] < 5.0).mean() * 100
        baseline_rate = (baseline_error[rows, horizon_index] < 5.0).mean() * 100
        parts.append(f"{int(horizon) // 60:>2}min {model_rate:5.1f}% vs CV {baseline_rate:5.1f}%")
    print(f"{prefix} within 5 NM | " + " | ".join(parts))


def main() -> None:
    torch.manual_seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    train_x, train_y, train_mask = load_split("train")
    val_x, val_y, val_mask = load_split("val")
    test_x, test_y, test_mask = load_split("test")

    train_cv = framing.constant_velocity_predict(train_x)
    train_sequence_raw, train_scalars_raw = framing.to_local_features(train_x)
    feature_statistics = fit_feature_statistics(train_sequence_raw, train_scalars_raw)
    residual_statistics = fit_residual_statistics(framing.residual_targets(train_x, train_y, train_cv), train_mask)

    train_tensors = prepare(train_x, train_y, train_mask, feature_statistics, residual_statistics)
    val_tensors = prepare(val_x, val_y, val_mask, feature_statistics, residual_statistics)
    test_tensors = prepare(test_x, test_y, test_mask, feature_statistics, residual_statistics)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {torch.cuda.get_device_name(0) if device.type == 'cuda' else 'CPU'}")
    print(f"Samples: {len(train_x)} train / {len(val_x)} val / {len(test_x)} test")
    print("Residual std used for normalisation (m), per horizon [along, cross, altitude]:")
    for horizon_index, horizon in enumerate(framing.HORIZONS_SECONDS):
        print(f"  {int(horizon) // 60:>2} min: " + "  ".join(f"{value:8.1f}" for value in residual_statistics["residual_std"][horizon_index]))

    train_batches = tuple(tensor.to(device) for tensor in train_tensors[:4])
    val_batches = tuple(tensor.to(device) for tensor in val_tensors[:4])

    model = ResidualTrajectoryModel().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    # SmoothL1, not MSE. Measured: squared error improves the mean while collapsing
    # the 10-minute within-1-NM rate from 22.4% to 2.5%, because it is dominated by
    # the small manoeuvring tail and trades away thousands of near-perfect
    # predictions to shrink a few large errors.
    criterion = nn.SmoothL1Loss(beta=SMOOTH_L1_BETA, reduction="none")

    best_validation_loss = float("inf")
    best_state, best_epoch, epochs_without_improvement = None, 0, 0
    history: list[tuple[int, float, float]] = []

    for epoch in range(1, NUM_EPOCHS + 1):
        train_loss = run_epoch(model, train_batches, criterion, optimizer)
        validation_loss = run_epoch(model, val_batches, criterion)
        history.append((epoch, train_loss, validation_loss))

        marker = ""
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            best_epoch, epochs_without_improvement = epoch, 0
            marker = "  <- best"
        else:
            epochs_without_improvement += 1
        print(f"Epoch {epoch:02d}/{NUM_EPOCHS} | train loss: {train_loss:.6f} | val loss: {validation_loss:.6f}{marker}")

        if epoch % PROGRESS_EVERY_EPOCHS == 0:
            validation_predictions = predict_absolute(model, val_tensors[0], val_tensors[1], val_x, val_tensors[4], residual_statistics, device)
            print_within_five(validation_predictions, val_tensors[4], val_y, val_mask, f"  val @ epoch {epoch:02d}")

        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print(f"Stopping early: validation loss has not improved for {EARLY_STOPPING_PATIENCE} epochs.")
            break

    # Early stopping only decides WHEN to stop. The weights that get evaluated and
    # saved must be the best-validation-loss ones, never whatever the final epoch
    # happened to leave behind -- the last EARLY_STOPPING_PATIENCE epochs are by
    # definition the ones that got worse. Verified rather than assumed: the restored
    # weights are re-scored on the validation split and must reproduce the recorded
    # best loss (evaluation is deterministic, so this is an exact check).
    if best_state is None:
        raise RuntimeError("No checkpoint was recorded; training produced no usable weights.")
    model.load_state_dict(best_state)
    restored_validation_loss = run_epoch(model, val_batches, criterion)
    if abs(restored_validation_loss - best_validation_loss) > 1e-9:
        raise RuntimeError(
            f"Restored weights score {restored_validation_loss:.9f} on validation but the best "
            f"checkpoint recorded {best_validation_loss:.9f}: the best epoch was not restored."
        )
    print("")
    print(f"Best checkpoint: epoch {best_epoch}, val loss {best_validation_loss:.6f} (ran {len(history)} epochs).")
    print(f"Restored best weights and re-scored validation: {restored_validation_loss:.6f} (matches).")
    validation_predictions = predict_absolute(model, val_tensors[0], val_tensors[1], val_x, val_tensors[4], residual_statistics, device)
    print_within_five(validation_predictions, val_tensors[4], val_y, val_mask, "  final val")

    print("")
    print("Loss curve (epoch, train, validation):")
    for epoch, train_loss, validation_loss in history:
        print(f"  {epoch:02d}  {train_loss:.6f}  {validation_loss:.6f}")

    test_predictions = predict_absolute(model, test_tensors[0], test_tensors[1], test_x, test_tensors[4], residual_statistics, device)
    results, _, passed = evaluate.compare(
        test_predictions, test_tensors[4], test_y, test_mask, test_x, "residual LSTM", "constant velocity"
    )
    evaluate.print_report(results)
    evaluate.write_results(results)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "feature_normalization": {key: value.astype(np.float32) for key, value in feature_statistics.items()},
        "residual_normalization": {key: value.astype(np.float32) for key, value in residual_statistics.items()},
        "config": {
            "sequence_features": SEQUENCE_FEATURES,
            "scalar_features": SCALAR_FEATURES,
            "hidden_size": HIDDEN_SIZE,
            "num_layers": NUM_LAYERS,
            "dropout": DROPOUT,
            "num_horizons": NUM_HORIZONS,
            "horizons_seconds": framing.HORIZONS_SECONDS.tolist(),
            "input_steps": train_x.shape[1],
        },
    }, MODEL_PATH)
    print("")
    print(f"Saved model weights: {MODEL_PATH}")
    print(f"Gate 1 (beats constant velocity at every horizon on within-5-NM): {'PASS' if passed else 'FAIL'}")


if __name__ == "__main__":
    main()
