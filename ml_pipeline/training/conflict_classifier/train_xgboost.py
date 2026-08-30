"""Train the baseline XGBoost CPA conflict classifier from the latest synthetic set."""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd
from sklearn.metrics import confusion_matrix, fbeta_score, precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


RANDOM_SEED = 42
TEST_SIZE = 0.20
FEATURE_COLUMNS = [
    "relative_distance_nm", "relative_altitude_ft", "relative_speed_ms", "relative_heading_deg",
    "closing_speed_ms", "time_to_cpa_seconds", "predicted_min_lateral_separation_nm",
    "predicted_min_vertical_separation_ft", "vertical_convergence_rate_ms",
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SYNTHETIC_DIRECTORY = PROJECT_ROOT / "ml_pipeline" / "data" / "synthetic"
MODEL_PATH = PROJECT_ROOT / "server" / "app" / "ml" / "saved_models" / "xgboost_conflict.json"


def latest_dataset_path() -> Path:
    """Use the newest timestamped synthetic dataset, rather than a stale hard-coded file."""
    paths = [Path(path) for path in glob.glob(str(SYNTHETIC_DIRECTORY / "conflict_scenarios_*.parquet"))]
    if not paths:
        raise FileNotFoundError(f"No conflict_scenarios_*.parquet files found in {SYNTHETIC_DIRECTORY}")
    return max(paths, key=lambda path: path.stat().st_mtime)


def main() -> None:
    dataset_path = latest_dataset_path()
    dataset = pd.read_parquet(dataset_path)
    required = set(FEATURE_COLUMNS + ["is_conflict"])
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    dataset = dataset.dropna(subset=FEATURE_COLUMNS + ["is_conflict"])
    x, y = dataset[FEATURE_COLUMNS], dataset["is_conflict"].astype(int)
    if y.nunique() != 2:
        raise ValueError("Training requires both conflict and non-conflict examples.")
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=TEST_SIZE, random_state=RANDOM_SEED, stratify=y)
    positives, negatives = int((y_train == 1).sum()), int((y_train == 0).sum())
    scale_pos_weight = negatives / positives
    print(f"Dataset: {dataset_path}\nTraining scale_pos_weight: {scale_pos_weight:.4f} ({negatives} negative / {positives} positive)")

    model = XGBClassifier(
        objective="binary:logistic", n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.7, scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_SEED, eval_metric="logloss",
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    print(f"Recall: {recall_score(y_test, predictions, zero_division=0):.4f}")
    print(f"Precision: {precision_score(y_test, predictions, zero_division=0):.4f}")
    print(f"F1: {f1_score(y_test, predictions, zero_division=0):.4f}")
    print(f"F-beta (beta=2): {fbeta_score(y_test, predictions, beta=2, zero_division=0):.4f}")
    print("Confusion matrix [[TN, FP], [FN, TP]]:")
    print(confusion_matrix(y_test, predictions, labels=[0, 1]))
    print("Feature importances:")
    for feature, importance in sorted(zip(FEATURE_COLUMNS, model.feature_importances_), key=lambda item: item[1], reverse=True):
        print(f"  {feature}: {importance:.6f}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(MODEL_PATH)
    print(f"Saved XGBoost model: {MODEL_PATH}")


if __name__ == "__main__":
    main()
