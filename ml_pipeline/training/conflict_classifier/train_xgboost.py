"""Train the XGBoost conflict classifier on predicted features and real outcomes.

WHAT THIS MODEL IS NOW BEING ASKED.

    Given what we can see now, and what the straight-line prediction says will
    happen, will these two aircraft ACTUALLY lose separation?

That is a different question from the one this script used to ask. The old dataset
labelled each pair by applying the separation rule to two of its own input features,
so the label was a function of the inputs and the model was rediscovering an
if-statement it had been handed. It scored a perfect PR-AUC of 1.0, which was
evidence of a broken setup rather than a good model. See the module docstring of
generate_synthetic_scenarios.py for the full account.

Now the features come from the constant-velocity PREDICTION and the label comes from
where the two real aircraft ACTUALLY went. The model can therefore learn something
the geometry cannot express on its own: WHERE OUR OWN PREDICTION IS UNRELIABLE. A
predicted 6 NM miss between two aircraft turning near the airport deserves less trust
than the same 6 NM between two cruising straight, and the trust features carry that
evidence.

THE BAR IT HAS TO CLEAR IS NOT ZERO. The straight-line rule already answers this
question correctly for about 95% of pairs. That rule is reported here at every step,
on the identical test split, exactly as constant velocity is reported alongside the
trajectory model. A classifier that cannot beat the rule has earned nothing, and the
honest response to that outcome is to say so and keep the rule.

Retained from the previous version, because both were real fixes:
  - The split is by time, on whole collection sessions. A random split puts scenarios
    seeded from the same 90-minute session on both sides of the boundary and measures
    memorisation of one afternoon of Mumbai traffic.
  - The decision threshold is chosen deliberately on the VALIDATION split from the
    precision-recall curve, never left at the library default of 0.5.
"""

from __future__ import annotations

import glob
import json
import sys
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    fbeta_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
)
import xgboost
from xgboost import XGBClassifier


PROJECT_ROOT = Path(__file__).resolve().parents[3]
# FLIGHT_RIGHT_DATA_ROOT relocates data and saved models (used by the smoke test so
# it can never touch real data). Unset, everything lives under the project root.
DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# The feature list lives with the generator that produces it, so the two cannot
# disagree about what the model is allowed to see.
from generate_synthetic_scenarios import FEATURE_COLUMNS  # noqa: E402
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    ALERT_LATERAL_NM,
    ALERT_VERTICAL_FT,
    SEPARATION_LATERAL_NM,
    SEPARATION_VERTICAL_FT,
)

RANDOM_SEED = 42
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
SESSION_BREAK_SECONDS = 1800
# A missed conflict is the failure that matters, so recall is the gate. The precision
# paid for it is reported next to it and never hidden.
TARGET_RECALL = 0.95
THRESHOLD_GRID = np.round(np.arange(0.05, 1.0, 0.05), 2)
# The project's headline metric: a conflict is only usefully caught if there is still
# time to act on it. 180 s is the response geometry, not a round number.
HEADLINE_WARNING_SECONDS = 180

MODEL_PATH = Path(os.environ.get("FLIGHT_RIGHT_CLASSIFIER_OUT",
                                  DATA_ROOT / "server" / "app" / "ml" / "saved_models" / "xgboost_conflict.json"))
MODEL_CARD_PATH = MODEL_PATH.with_name(MODEL_PATH.stem + "_model_card.json")

# Plan 9.0, served from 26 Sep at Archit's decision: the autopilot level each aircraft has
# dialled in (adsb.lol nav_altitude_mcp), as three extra inputs. FLIGHT_RIGHT_CLASSIFIER_INTENT=1
# turns them on. They come from encounters_with_intent.parquet, which classifier_intent_ablation.py
# built by re-running the seeded generator and verifying it row-for-row against the encounter file,
# then joining each real aircraft's dialled level BACKWARD in time (<= 300 s) -- nothing from after
# the decision moment. Unknown stays NaN; XGBoost treats NaN as "missing" natively.
from generate_synthetic_scenarios import INTENT_COLUMNS  # noqa: E402  (one definition, shared with inference)
INTENT_CACHE = DATA_ROOT / "ml_pipeline" / "data" / "processed" / "encounters_with_intent.parquet"
USE_INTENT = os.environ.get("FLIGHT_RIGHT_CLASSIFIER_INTENT", "") == "1"
MODEL_COLUMNS = FEATURE_COLUMNS + (INTENT_COLUMNS if USE_INTENT else [])
# Archit, 26 Sep: "same alarm rate". With this set to a saved model file, the threshold is chosen
# on VALIDATION as the lowest one whose false-alarm rate does not exceed that model's validation
# false-alarm rate -- so any gain goes to catching more real conflicts, not to fewer alarms.
MATCH_FALSE_ALARMS_OF = os.environ.get("FLIGHT_RIGHT_MATCH_FALSE_ALARMS_OF", "").strip()
SYNTHETIC_DIRECTORY = DATA_ROOT / "ml_pipeline" / "data" / "synthetic"
# Recall margins reported as WHAT-IF rows only. The selected threshold is unchanged --
# choosing a margin changes when a controller is alerted and needs Archit's sign-off
# (CLAUDE.md Part 4, item 3). This table gives him the numbers to decide with.
WHAT_IF_RECALL_MARGINS = (0.005, 0.01, 0.02)
# The margin ACTUALLY applied when choosing the threshold. Default 0.0 = the original
# rule. Set FLIGHT_RIGHT_RECALL_MARGIN (e.g. 0.01) only after Archit has decided, using
# the WHAT-IF table; the value used is written into the model card so the decision is
# on record. This is a decision knob, not a tuning knob: it changes when a controller is
# alerted, and the report says so.
APPLIED_RECALL_MARGIN = float(os.environ.get("FLIGHT_RIGHT_RECALL_MARGIN", "0.0"))
# Columns describing what actually happened. These produce the label and must never
# reach the model; the guard below fails the run if any of them appears in the features.
OUTCOME_ONLY_COLUMNS = [
    "actual_cpa_lateral_nm", "actual_cpa_vertical_ft", "actual_time_to_cpa_seconds",
    "is_conflict", "severity",
]


def latest_dataset_path() -> Path:
    """Newest real-outcome encounter file.

    The pattern deliberately does NOT match the old conflict_scenarios_*.parquet
    files. Those carry a circular label and training on one would silently undo this
    entire rewrite, so they are left unmatched rather than merely deprioritised.
    """
    paths = [Path(path) for path in glob.glob(str(SYNTHETIC_DIRECTORY / "encounters_real_outcome_*.parquet"))]
    if not paths:
        raise FileNotFoundError(
            f"No encounters_real_outcome_*.parquet in {SYNTHETIC_DIRECTORY}. "
            "Run generate_synthetic_scenarios.py first."
        )
    return max(paths, key=lambda path: path.stat().st_mtime)


def add_intent_columns(dataset: pd.DataFrame) -> pd.DataFrame:
    """Attach the dialled-level columns, refusing if the cache is not the same encounters."""
    cached = pd.read_parquet(INTENT_CACHE)
    same = (len(cached) == len(dataset)
            and np.allclose(cached[FEATURE_COLUMNS].to_numpy(dtype=float),
                            dataset[FEATURE_COLUMNS].to_numpy(dtype=float), equal_nan=True)
            and (cached["is_conflict"].to_numpy() == dataset["is_conflict"].to_numpy()).all())
    if not same:
        raise RuntimeError(f"{INTENT_CACHE.name} is not row-for-row the same encounters as the training file; "
                           "re-run classifier_intent_ablation.py --rebuild.")
    return dataset.assign(**{c: cached[c].to_numpy() for c in INTENT_COLUMNS})


def _row_keys(frame: pd.DataFrame) -> pd.Series:
    """An exact fingerprint of each encounter row (its 24 features and its time)."""
    return pd.util.hash_pandas_object(frame[FEATURE_COLUMNS + ["seed_time_position"]], index=False)


def attach_intent_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the dialled-level columns to ANY subset of encounter rows, in any order.

    Matched on each row's own contents, not its position, so a split or re-ordered frame
    cannot be paired with another row's dialled levels. Refuses on a missing or ambiguous row."""
    cached = pd.read_parquet(INTENT_CACHE)
    keys = _row_keys(cached)
    if keys.duplicated().any():
        raise RuntimeError("encounter fingerprints are not unique; cannot attach dialled levels safely")
    lookup = cached.assign(_key=keys.to_numpy()).set_index("_key")[INTENT_COLUMNS]
    wanted = _row_keys(frame)
    missing = ~wanted.isin(lookup.index)
    if missing.any():
        raise RuntimeError(f"{int(missing.sum())} encounter rows are not in {INTENT_CACHE.name}")
    return frame.assign(**{c: lookup.loc[wanted.to_numpy(), c].to_numpy() for c in INTENT_COLUMNS})


def classifier_raw_scores(booster: "xgboost.Booster", frame: pd.DataFrame) -> np.ndarray:
    """Raw scores from a saved classifier, fed exactly the inputs its file declares."""
    columns = json.loads(booster.attr("feature_columns"))
    if any(c not in frame.columns for c in columns):
        frame = attach_intent_columns(frame)
    return booster.predict(xgboost.DMatrix(frame[columns], feature_names=columns))


def threshold_at_false_alarm_rate(y_true: np.ndarray, probabilities: np.ndarray, target_per_1000: float) -> float:
    """Lowest threshold (so the most real conflicts caught) whose false alarms stay within target."""
    negatives = y_true == 0
    for value in np.unique(probabilities):                 # ascending
        if (probabilities[negatives] >= value).sum() / len(y_true) * 1000.0 <= target_per_1000:
            return float(value)
    return float(probabilities.max())


def reference_false_alarm_rate(path: str, frame: pd.DataFrame) -> tuple[float, float]:
    """Validation false alarms per 1000 and recall of an existing saved classifier."""
    reference = xgboost.Booster()
    reference.load_model(path)
    columns = json.loads(reference.attr("feature_columns"))
    raw = reference.predict(xgboost.DMatrix(frame[columns], feature_names=columns))
    metrics = metrics_at_threshold(frame["is_conflict"].astype(int).to_numpy(), raw,
                                   float(json.loads(reference.attr("decision_threshold"))))
    return metrics["false_alarms_per_1000"], metrics["recall"]


def assert_no_leakage(dataset: pd.DataFrame) -> float:
    """Refuse to train if the label can be recomputed from the features.

    This guard exists because the defect it checks for went undetected for weeks and
    produced a model that appeared perfect while having learned nothing. Two checks:
    no outcome column may be in the feature list, and the separation rule applied to
    the predicted closest approach must not reproduce the label.
    """
    overlap = sorted(set(MODEL_COLUMNS).intersection(OUTCOME_ONLY_COLUMNS))
    if overlap:
        raise RuntimeError(f"Outcome columns present in the feature list: {overlap}")

    rule = ((dataset["predicted_cpa_lateral_nm"] < SEPARATION_LATERAL_NM)
            & (dataset["predicted_cpa_vertical_ft"] < SEPARATION_VERTICAL_FT)).astype(int)
    agreement = float((rule == dataset["is_conflict"]).mean())
    print("Leakage guard")
    print(f"  separation rule on the PREDICTED closest approach reproduces the label for "
          f"{agreement:.2%} of rows")
    print(f"  (the old circular dataset: 100.00% -- anything above 99% is refused here)")
    if agreement > 0.99:
        raise RuntimeError(
            f"Label reproducible from features for {agreement:.4%} of rows. Refusing to train."
        )
    print(f"  PASS -- {int((rule != dataset['is_conflict']).sum()):,} rows where our own "
          f"prediction is wrong; that is what there is to learn.")
    return agreement


def split_by_session(dataset: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Assign whole collection sessions to train/validation/test in time order."""
    dataset = dataset.sort_values("seed_time_position").reset_index(drop=True)
    gaps = dataset["seed_time_position"].diff().fillna(0) > SESSION_BREAK_SECONDS
    dataset["split_session"] = gaps.cumsum()

    sizes = dataset.groupby("split_session").size()
    train_target = len(dataset) * TRAIN_FRACTION
    validation_target = len(dataset) * (TRAIN_FRACTION + VALIDATION_FRACTION)
    assignment: dict[int, str] = {}
    running = 0
    for session_id, size in sizes.items():
        assignment[session_id] = "train" if running < train_target else "val" if running < validation_target else "test"
        running += size

    dataset["split"] = dataset["split_session"].map(assignment)
    splits = {name: dataset.loc[dataset["split"] == name].copy() for name in ("train", "val", "test")}
    for name, frame in splits.items():
        if frame.empty:
            raise ValueError(f"The {name} split is empty.")
        if frame["is_conflict"].nunique() != 2:
            raise ValueError(f"The {name} split contains only one class.")
    return splits


def print_split_report(splits: dict[str, pd.DataFrame]) -> None:
    print("Time-based split (whole collection sessions, in order -- no random shuffling)")
    print(f"  {'split':<6} {'rows':>8} {'sessions':>9} {'conflicts':>10} {'rate':>7}   observation range (IST)")
    for name, frame in splits.items():
        span = pd.to_datetime(frame["seed_time_position"].agg(["min", "max"]), unit="s", utc=True) \
            + pd.Timedelta(hours=5, minutes=30)
        conflicts = int(frame["is_conflict"].sum())
        print(f"  {name:<6} {len(frame):>8,} {frame['split_session'].nunique():>9} {conflicts:>10,} "
              f"{conflicts / len(frame):>6.2%}   {span.iloc[0]:%d %b %H:%M} -> {span.iloc[1]:%d %b %H:%M}")


def metrics_at_threshold(y_true: np.ndarray, probabilities: np.ndarray, threshold: float) -> dict:
    predictions = (probabilities >= threshold).astype(int)
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        y_true, predictions, labels=[0, 1]
    ).ravel()
    return {
        "threshold": float(threshold),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
        "fbeta_2": float(fbeta_score(y_true, predictions, beta=2, zero_division=0)),
        "false_alarms_per_1000": float(false_positive / len(y_true) * 1000.0),
        "true_positive": int(true_positive), "false_positive": int(false_positive),
        "false_negative": int(false_negative), "true_negative": int(true_negative),
        "alert_rate": float(predictions.mean()),
    }


def metrics_from_predictions(y_true: np.ndarray, predictions: np.ndarray) -> dict:
    """Same headline numbers for a rule, which has no probability to threshold."""
    true_negative, false_positive, false_negative, true_positive = confusion_matrix(
        y_true, predictions, labels=[0, 1]
    ).ravel()
    return {
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "fbeta_2": float(fbeta_score(y_true, predictions, beta=2, zero_division=0)),
        "false_alarms_per_1000": float(false_positive / len(y_true) * 1000.0),
        "false_negative": int(false_negative), "alert_rate": float(predictions.mean()),
    }


def rule_predictions(frame: pd.DataFrame, lateral_nm: float, vertical_ft: float) -> np.ndarray:
    """The deterministic detector: alert when the predicted closest approach breaches."""
    return ((frame["predicted_cpa_lateral_nm"] < lateral_nm)
            & (frame["predicted_cpa_vertical_ft"] < vertical_ft)).astype(int).to_numpy()


def headline_metric(frame: pd.DataFrame, alerts: np.ndarray) -> tuple[float, int, int]:
    """THE project metric: share of real conflicts caught with >= 3 minutes of warning.

    Only conflicts that still had three minutes to run are counted, because a conflict
    detected with ninety seconds left is real but too late to act on: about 38 s to get
    an aircraft moving, then ~40 s for a 1000 ft level change.
    """
    conflicts = frame["is_conflict"].to_numpy() == 1
    in_time = frame["actual_time_to_cpa_seconds"].to_numpy() >= HEADLINE_WARNING_SECONDS
    eligible = conflicts & in_time
    total = int(eligible.sum())
    if total == 0:
        return float("nan"), 0, 0
    caught = int((eligible & (alerts == 1)).sum())
    return caught / total, caught, total


def select_threshold(y_true: np.ndarray, probabilities: np.ndarray,
                     target_recall: float = TARGET_RECALL) -> tuple[float, bool]:
    """Highest threshold on the validation split that still meets the recall floor."""
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    qualifying = [threshold for threshold, achieved in zip(thresholds, recall[:-1]) if achieved >= target_recall]
    if qualifying:
        return float(max(qualifying)), True
    return float(thresholds[int(np.argmax(recall[:-1]))]), False


def training_device() -> str:
    """'cuda' when XGBoost can see a GPU, otherwise 'cpu'. Same model either way.

    The RTX 4060 trains 300 trees on 30k rows in about a second; the point of using it
    is not speed here but confirming the GPU stack works before the trajectory model
    needs it. If the CUDA build is missing XGBoost falls back silently, so we probe.
    """
    if os.environ.get("FLIGHT_RIGHT_FORCE_CPU"):
        return "cpu"
    try:
        probe = xgboost.XGBClassifier(n_estimators=1, device="cuda", tree_method="hist")
        probe.fit(np.array([[0.0], [1.0], [0.0], [1.0]]), np.array([0, 1, 0, 1]))
        return "cuda"
    except Exception:
        return "cpu"


class PlattCalibrator:
    """Sigmoid (Platt) calibration: p_calibrated = 1 / (1 + exp(-(a * logit(p) + b))).

    Source: Platt, "Probabilistic Outputs for Support Vector Machines", 1999, and
    Niculescu-Mizil & Caruana, "Predicting Good Probabilities With Supervised
    Learning", ICML 2005, <https://www.cs.cornell.edu/~alexn/papers/calibration.icml05.crc.rev3.pdf>,
    which shows boosted trees are characteristically over-confident and that Platt
    scaling fixes it. Fitted on VALIDATION only.

    Why sigmoid and not isotonic: the map is strictly increasing, so it changes no
    ranking. The selected threshold is mapped through the same function and the set of
    alerts is IDENTICAL before and after -- calibration here changes what the
    probability number MEANS, never when a controller is alerted.
    """

    def __init__(self, a: float = 1.0, b: float = 0.0) -> None:
        self.a, self.b = float(a), float(b)

    @staticmethod
    def _logit(p: np.ndarray) -> np.ndarray:
        clipped = np.clip(np.asarray(p, dtype=np.float64), 1e-7, 1 - 1e-7)
        return np.log(clipped / (1 - clipped))

    def fit(self, probabilities: np.ndarray, y_true: np.ndarray) -> "PlattCalibrator":
        regression = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        regression.fit(self._logit(probabilities)[:, None], np.asarray(y_true).astype(int))
        self.a, self.b = float(regression.coef_[0, 0]), float(regression.intercept_[0])
        if self.a <= 0:
            raise RuntimeError(f"Platt slope {self.a:.4f} is not positive; calibration would reverse the ranking.")
        return self

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-(self.a * self._logit(probabilities) + self.b)))


def expected_calibration_error(stated: np.ndarray, y_true: np.ndarray, bins: int = 10) -> float:
    """Weighted mean gap between stated probability and observed conflict rate, per bin."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    error = 0.0
    for lower, upper in zip(edges[:-1], edges[1:]):
        in_bin = (stated >= lower) & ((stated < upper) if upper < 1.0 else (stated <= upper))
        if in_bin.any():
            error += in_bin.mean() * abs(stated[in_bin].mean() - y_true[in_bin].mean())
    return float(error)


def print_calibration(y_true: np.ndarray, raw: np.ndarray, calibrated: np.ndarray) -> dict:
    """Reliability of the conflict probability before and after Platt scaling, on TEST."""
    print("")
    print("=" * 96)
    print("CALIBRATION -- does 'probability 0.7' mean a 70% chance of a real conflict?")
    print("=" * 96)
    summary = {}
    for label, probabilities in (("raw XGBoost", raw), ("Platt-calibrated", calibrated)):
        brier = float(brier_score_loss(y_true, probabilities))
        ece = expected_calibration_error(probabilities, y_true)
        summary[label] = {"brier": brier, "ece": ece}
        print(f"  {label:<18} Brier {brier:.4f}   expected calibration error {ece:.4f}")
    print("  (Brier: mean squared gap between stated probability and outcome; both lower is better.)")
    print("")
    print(f"  {'stated band':>13} {'rows':>7} {'raw stated':>11} {'raw actual':>11} {'cal stated':>11} {'cal actual':>11}")
    edges = np.linspace(0.0, 1.0, 11)
    for lower, upper in zip(edges[:-1], edges[1:]):
        in_raw = (raw >= lower) & ((raw < upper) if upper < 1.0 else (raw <= upper))
        in_cal = (calibrated >= lower) & ((calibrated < upper) if upper < 1.0 else (calibrated <= upper))
        if not (in_raw.any() or in_cal.any()):
            continue
        raw_stated = f"{raw[in_raw].mean():>11.3f}" if in_raw.any() else f"{'-':>11}"
        raw_actual = f"{y_true[in_raw].mean():>11.3f}" if in_raw.any() else f"{'-':>11}"
        cal_stated = f"{calibrated[in_cal].mean():>11.3f}" if in_cal.any() else f"{'-':>11}"
        cal_actual = f"{y_true[in_cal].mean():>11.3f}" if in_cal.any() else f"{'-':>11}"
        print(f"  {lower:>5.1f} - {upper:<5.1f} {int(in_raw.sum()):>7,} {raw_stated} {raw_actual} {cal_stated} {cal_actual}")
    return summary


def print_margin_what_if(y_val: np.ndarray, val_probabilities: np.ndarray, test_frame: pd.DataFrame,
                         y_test: np.ndarray, test_probabilities: np.ndarray, selected: float) -> list[dict]:
    """What the gate WOULD show if the threshold were chosen with a margin above the floor.

    Reported, not applied. Every row here is information for a decision Archit has to
    make; the model saved by this script still uses the zero-margin threshold.
    """
    print("")
    print("=" * 96)
    print("WHAT-IF -- selecting the threshold with a recall margin above the 0.95 floor (NOT applied)")
    print("=" * 96)
    print("  The current rule picks the highest threshold reaching 0.95 on validation, which sits on")
    print("  the edge of the floor by construction and slips below it on a later test split. These")
    print("  rows show the cost, in false alarms, of buying a margin. Decision needed from Archit.")
    print("")
    print(f"  {'margin':>7} {'val target':>11} {'threshold':>10} {'test recall':>12} {'precision':>10} "
          f"{'FA/1000':>8} {'missed':>7} {'headline':>9} {'gate 1':>7}")
    rows = []
    for margin in (0.0,) + tuple(WHAT_IF_RECALL_MARGINS):
        threshold, met = select_threshold(y_val, val_probabilities, TARGET_RECALL + margin)
        metrics = metrics_at_threshold(y_test, test_probabilities, threshold)
        alerts = (test_probabilities >= threshold).astype(int)
        headline, _, _ = headline_metric(test_frame, alerts)
        gate = metrics["recall"] >= TARGET_RECALL
        marker = "  <- current, saved" if abs(threshold - selected) < 1e-12 else ""
        print(f"  {margin:>7.3f} {TARGET_RECALL + margin:>11.3f} {threshold:>10.4f} {metrics['recall']:>12.4f} "
              f"{metrics['precision']:>10.4f} {metrics['false_alarms_per_1000']:>8.1f} "
              f"{metrics['false_negative']:>7} {headline:>8.1%} {'PASS' if gate else 'FAIL':>7}{marker}")
        rows.append({"margin": margin, "threshold": threshold, "validation_target_met": met,
                     "test_recall": metrics["recall"], "test_precision": metrics["precision"],
                     "false_alarms_per_1000": metrics["false_alarms_per_1000"],
                     "missed": metrics["false_negative"], "headline": headline, "gate_1": bool(gate)})
    return rows


def shap_importance(booster: xgboost.Booster, x: pd.DataFrame) -> dict[str, float]:
    """Mean absolute SHAP contribution per feature, from XGBoost's built-in TreeSHAP.

    Section 3 asks for SHAP so a controller can be shown WHY an alert fired. XGBoost
    computes exact TreeSHAP values natively (Lundberg, Erion & Lee, "Consistent
    Individualized Feature Attribution for Tree Ensembles", arXiv:1802.03888), so no
    extra dependency is needed. The same call, per row, gives the per-alert explanation
    the backend will surface.
    """
    contributions = booster.predict(xgboost.DMatrix(x, feature_names=list(x.columns)), pred_contribs=True)
    mean_abs = np.abs(contributions[:, :-1]).mean(axis=0)  # last column is the bias term
    return {feature: float(value) for feature, value in zip(x.columns, mean_abs)}


def print_pr_table(y_true: np.ndarray, probabilities: np.ndarray, selected_threshold: float) -> None:
    print(f"  {'threshold':>9} {'recall':>8} {'precision':>10} {'F1':>7} {'F-beta2':>8} "
          f"{'FA/1000':>9} {'alerts':>8}")
    for threshold in sorted(THRESHOLD_GRID.tolist() + [selected_threshold]):
        row = metrics_at_threshold(y_true, probabilities, threshold)
        marker = "  <- selected" if abs(threshold - selected_threshold) < 1e-9 else ""
        meets = "*" if row["recall"] >= TARGET_RECALL else " "
        print(f"  {threshold:>9.4f} {row['recall']:>7.4f}{meets} {row['precision']:>10.4f} {row['f1']:>7.4f} "
              f"{row['fbeta_2']:>8.4f} {row['false_alarms_per_1000']:>9.1f} {row['alert_rate']:>7.1%}{marker}")
    print(f"  (* marks thresholds meeting the recall floor of {TARGET_RECALL:.2f})")


def print_warning_time(frame: pd.DataFrame, alerts: np.ndarray) -> float:
    """How much notice a caught conflict actually gets, from the REAL closest approach."""
    caught = (alerts == 1) & (frame["is_conflict"].to_numpy() == 1)
    warning = frame.loc[caught, "actual_time_to_cpa_seconds"].astype(float)
    if warning.empty:
        print("  no conflicts caught at this threshold.")
        return float("nan")
    print(f"  caught conflicts: {len(warning):,}")
    print(f"  min {warning.min():>5.0f} s   p10 {warning.quantile(0.10):>5.0f} s   "
          f"median {warning.median():>5.0f} s   p90 {warning.quantile(0.90):>5.0f} s   "
          f"max {warning.max():>5.0f} s")
    for lower, upper, label in ((0, 90, "under 90 s, too late"), (90, 180, "90-180 s, tier 1"),
                                (180, 300, "3-5 min, tier 2"), (300, 601, "5-10 min, tier 2")):
        count = int(((warning >= lower) & (warning < upper)).sum())
        print(f"    {label:<22} {count:>6,} ({count / len(warning):6.2%})")
    return float(warning.median())


def main() -> None:
    dataset_path = latest_dataset_path()
    dataset = pd.read_parquet(dataset_path)
    missing = set(FEATURE_COLUMNS + ["is_conflict", "seed_time_position",
                                     "actual_time_to_cpa_seconds"]).difference(dataset.columns)
    if missing:
        raise ValueError(f"Dataset is missing columns: {sorted(missing)}. Re-run the generator.")
    if USE_INTENT:
        dataset = add_intent_columns(dataset)
        print(f"Dialled-level inputs added from {INTENT_CACHE.name} (verified row-for-row): "
              + ", ".join(f"{c} {dataset[c].notna().mean():.1%} known" for c in INTENT_COLUMNS))
    dataset = dataset.dropna(subset=FEATURE_COLUMNS + ["is_conflict"])
    print(f"Dataset: {dataset_path.name}")
    print(f"Rows: {len(dataset):,}   real conflicts: {int(dataset['is_conflict'].sum()):,} "
          f"({dataset['is_conflict'].mean():.2%})   features: {len(MODEL_COLUMNS)}")
    print("")
    assert_no_leakage(dataset)
    print("")

    splits = split_by_session(dataset)
    print_split_report(splits)

    x_train, y_train = splits["train"][MODEL_COLUMNS], splits["train"]["is_conflict"].astype(int)
    x_val, y_val = splits["val"][MODEL_COLUMNS], splits["val"]["is_conflict"].astype(int)
    x_test, y_test = splits["test"][MODEL_COLUMNS], splits["test"]["is_conflict"].astype(int)

    positives, negatives = int((y_train == 1).sum()), int((y_train == 0).sum())
    scale_pos_weight = negatives / positives
    print("")
    print(f"scale_pos_weight from the training split: {scale_pos_weight:.3f} "
          f"({negatives:,} negative / {positives:,} positive)")

    device = training_device()
    print(f"XGBoost device: {device}  (xgboost {xgboost.__version__})")
    # Hyperparameters are the ones fixed in CLAUDE.md Section 3. They are not tuned
    # here: Gate 1's failure is a threshold-selection property, not a capacity one.
    model = XGBClassifier(
        objective="binary:logistic", n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.7, scale_pos_weight=scale_pos_weight,
        random_state=RANDOM_SEED, eval_metric="logloss", tree_method="hist", device=device,
    )
    model.fit(x_train, y_train)
    validation_probabilities = model.predict_proba(x_val)[:, 1]
    test_probabilities = model.predict_proba(x_test)[:, 1]

    selected_threshold, target_met = select_threshold(
        y_val.to_numpy(), validation_probabilities, TARGET_RECALL + APPLIED_RECALL_MARGIN
    )
    threshold_rule = "highest validation threshold still reaching the recall floor"
    if MATCH_FALSE_ALARMS_OF:
        target_fa, reference_recall = reference_false_alarm_rate(MATCH_FALSE_ALARMS_OF, splits["val"])
        selected_threshold = threshold_at_false_alarm_rate(y_val.to_numpy(), validation_probabilities, target_fa)
        achieved = metrics_at_threshold(y_val.to_numpy(), validation_probabilities, selected_threshold)
        target_met = achieved["recall"] >= TARGET_RECALL
        threshold_rule = (f"same validation false-alarm rate as {Path(MATCH_FALSE_ALARMS_OF).name} "
                          f"({target_fa:.1f} per 1000; its validation recall {reference_recall:.4f})")
        print("")
        print(f"DECISION APPLIED (Archit, 26 Sep, same alarm rate): threshold {selected_threshold:.4f} chosen on "
              f"VALIDATION so false alarms stay within {target_fa:.1f} per 1000, the rate of "
              f"{Path(MATCH_FALSE_ALARMS_OF).name}. Validation recall {achieved['recall']:.4f} against its "
              f"{reference_recall:.4f}; false alarms {achieved['false_alarms_per_1000']:.1f} per 1000.")
    if APPLIED_RECALL_MARGIN:
        print("")
        print(f"DECISION APPLIED: threshold selected for validation recall >= "
              f"{TARGET_RECALL + APPLIED_RECALL_MARGIN:.3f} (floor {TARGET_RECALL:.2f} + margin "
              f"{APPLIED_RECALL_MARGIN:.3f}), per FLIGHT_RIGHT_RECALL_MARGIN. This changes when a "
              f"controller is alerted and is recorded in the model card.")
    print("")
    print("=" * 96)
    print(f"PRECISION-RECALL ON VALIDATION ({len(y_val):,} rows) -- the threshold is chosen here")
    print("=" * 96)
    print_pr_table(y_val.to_numpy(), validation_probabilities, selected_threshold)
    validation_metrics = metrics_at_threshold(y_val.to_numpy(), validation_probabilities, selected_threshold)
    print("")
    if target_met:
        print(f"Selected threshold {selected_threshold:.4f}: highest threshold still reaching "
              f"recall >= {TARGET_RECALL:.2f} on validation "
              f"(recall {validation_metrics['recall']:.4f}, precision {validation_metrics['precision']:.4f}).")
    else:
        print(f"WARNING: no threshold reached recall {TARGET_RECALL:.2f} on validation. Using the "
              f"highest-recall point {selected_threshold:.4f} (recall {validation_metrics['recall']:.4f}). "
              f"The target was NOT met.")

    # ---- The comparison that decides whether this model has earned its place ----
    test_frame = splits["test"]
    test_metrics = metrics_at_threshold(y_test.to_numpy(), test_probabilities, selected_threshold)
    model_alerts = (test_probabilities >= selected_threshold).astype(int)
    legal_rule = rule_predictions(test_frame, SEPARATION_LATERAL_NM, SEPARATION_VERTICAL_FT)
    alert_rule = rule_predictions(test_frame, ALERT_LATERAL_NM, ALERT_VERTICAL_FT)
    legal_metrics = metrics_from_predictions(y_test.to_numpy(), legal_rule)
    alert_metrics = metrics_from_predictions(y_test.to_numpy(), alert_rule)

    print("")
    print("=" * 96)
    print(f"TEST SPLIT ({len(y_test):,} rows, all from later sessions than train and validation)")
    print("=" * 96)
    print("Every row answers the same question: will these two aircraft ACTUALLY lose separation?")
    print("")
    print(f"  {'method':<40} {'recall':>8} {'precision':>10} {'F-beta2':>9} {'FA/1000':>9} {'missed':>8}")
    print(f"  {'-' * 88}")
    print(f"  {'rule at legal minimum (5 NM/1000 ft)':<40} {legal_metrics['recall']:>8.4f} "
          f"{legal_metrics['precision']:>10.4f} {legal_metrics['fbeta_2']:>9.4f} "
          f"{legal_metrics['false_alarms_per_1000']:>9.1f} {legal_metrics['false_negative']:>8,}")
    print(f"  {'rule at alert volume (8 NM/1500 ft)':<40} {alert_metrics['recall']:>8.4f} "
          f"{alert_metrics['precision']:>10.4f} {alert_metrics['fbeta_2']:>9.4f} "
          f"{alert_metrics['false_alarms_per_1000']:>9.1f} {alert_metrics['false_negative']:>8,}")
    print(f"  {'XGBoost at the selected threshold':<40} {test_metrics['recall']:>8.4f} "
          f"{test_metrics['precision']:>10.4f} {test_metrics['fbeta_2']:>9.4f} "
          f"{test_metrics['false_alarms_per_1000']:>9.1f} {test_metrics['false_negative']:>8,}")

    pr_auc = float(average_precision_score(y_test, test_probabilities))
    print("")
    print(f"  PR-AUC (threshold-free): {pr_auc:.4f}   baseline = conflict rate {y_test.mean():.4f}")
    print(f"  A PR-AUC of 1.0 here would mean the leakage is back. It is not.")

    print("")
    print("=" * 96)
    print(f"HEADLINE METRIC -- conflicts caught with at least {HEADLINE_WARNING_SECONDS // 60} minutes of warning")
    print("=" * 96)
    for label, alerts in (("rule at legal minimum (5 NM/1000 ft)", legal_rule),
                          ("rule at alert volume (8 NM/1500 ft)", alert_rule),
                          ("XGBoost at the selected threshold", model_alerts)):
        rate, caught, total = headline_metric(test_frame, alerts)
        print(f"  {label:<40} {rate:>7.1%}   ({caught:,} of {total:,})")
    print(f"  Conflicts with less than {HEADLINE_WARNING_SECONDS} s of warning are excluded: they are")
    print(f"  real, but too late for a controller to act on.")

    print("")
    print("Warning time on the conflicts XGBoost caught (real closest approach):")
    median_warning = print_warning_time(test_frame, model_alerts)

    # ---- Calibration (rule 9: probabilities must be calibrated before a threshold means anything) ----
    calibrator = PlattCalibrator().fit(validation_probabilities, y_val.to_numpy())
    calibrated_test = calibrator.transform(test_probabilities)
    calibrated_threshold = float(calibrator.transform(np.array([selected_threshold]))[0])
    calibrated_alerts = (calibrated_test >= calibrated_threshold).astype(int)
    if not np.array_equal(calibrated_alerts, model_alerts):
        raise RuntimeError("Calibration changed the alert set; Platt scaling must be monotone. Refusing to save.")
    calibration_summary = print_calibration(y_test.to_numpy(), test_probabilities, calibrated_test)
    print("")
    print(f"  Platt parameters a={calibrator.a:.4f}, b={calibrator.b:.4f}. Raw threshold {selected_threshold:.4f} "
          f"maps to calibrated threshold {calibrated_threshold:.4f}.")
    print(f"  Verified: the set of alerts on test is identical before and after calibration "
          f"({int(model_alerts.sum()):,} alerts). Calibration changed the meaning of the number, not the decision.")

    what_if_rows = print_margin_what_if(y_val.to_numpy(), validation_probabilities, test_frame,
                                        y_test.to_numpy(), test_probabilities, selected_threshold)

    booster = model.get_booster()
    shap_values = shap_importance(booster, x_test)
    print("")
    print("Feature importance (gain-based) and mean |SHAP| contribution on the test split:")
    print(f"  {'feature':<34} {'gain':>10} {'mean |SHAP|':>12}")
    for feature, importance in sorted(zip(MODEL_COLUMNS, model.feature_importances_),
                                      key=lambda item: item[1], reverse=True):
        print(f"  {feature:<34} {importance:>10.6f} {shap_values[feature]:>12.4f}")

    booster.set_attr(
        decision_threshold=json.dumps(selected_threshold),
        calibrated_decision_threshold=json.dumps(calibrated_threshold),
        platt_a=json.dumps(calibrator.a),
        platt_b=json.dumps(calibrator.b),
        feature_columns=json.dumps(MODEL_COLUMNS),
        target_recall=json.dumps(TARGET_RECALL),
        test_recall=json.dumps(round(test_metrics["recall"], 6)),
        test_precision=json.dumps(round(test_metrics["precision"], 6)),
        test_pr_auc=json.dumps(round(pr_auc, 6)),
        rule_recall_alert_volume=json.dumps(round(alert_metrics["recall"], 6)),
        training_dataset=dataset_path.name,
        applied_recall_margin=json.dumps(APPLIED_RECALL_MARGIN),
        threshold_rule=threshold_rule,
    )
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(MODEL_PATH)
    print("")
    print(f"Saved model, threshold, calibration and feature list: {MODEL_PATH}")

    gate_passed = test_metrics["recall"] >= TARGET_RECALL
    beats_rule = test_metrics["fbeta_2"] > alert_metrics["fbeta_2"]
    print("")
    print("=" * 96)
    print(f"GATE 1 (test recall >= {TARGET_RECALL:.2f}): {'PASS' if gate_passed else 'FAIL'} "
          f"-- recall {test_metrics['recall']:.4f}, precision {test_metrics['precision']:.4f}, "
          f"{test_metrics['false_alarms_per_1000']:.1f} false alarms per 1000, "
          f"median warning {median_warning:.0f} s")
    print(f"GATE 2 (beats the rule-based detector on F-beta2): {'PASS' if beats_rule else 'FAIL'} "
          f"-- model {test_metrics['fbeta_2']:.4f} vs rule {alert_metrics['fbeta_2']:.4f}")
    if not (gate_passed and beats_rule):
        print("")
        print("A failing gate is reported, not tuned away. Do not move the threshold, the gate,")
        print("or a hyperparameter to make this pass -- find out why it failed first.")
    print("=" * 96)

    headline_rows = {}
    for label, alerts in (("rule_legal_minimum", legal_rule), ("rule_alert_volume", alert_rule), ("xgboost", model_alerts)):
        rate, caught, total = headline_metric(test_frame, alerts)
        headline_rows[label] = {"rate": rate, "caught": caught, "total": total}
    model_card = {
        "model": "xgboost_conflict", "trained_at_utc": pd.Timestamp.utcnow().isoformat(),
        "device": device, "xgboost_version": xgboost.__version__,
        "training_dataset": dataset_path.name,
        "rows": {name: int(len(frame)) for name, frame in splits.items()},
        "conflict_rate": {name: float(frame["is_conflict"].mean()) for name, frame in splits.items()},
        "features": MODEL_COLUMNS,
        "decision_threshold": selected_threshold, "calibrated_decision_threshold": calibrated_threshold,
        "applied_recall_margin": APPLIED_RECALL_MARGIN, "target_recall_floor": TARGET_RECALL,
        "threshold_rule": threshold_rule, "dialled_level_inputs": USE_INTENT,
        "platt": {"a": calibrator.a, "b": calibrator.b}, "calibration": calibration_summary,
        "test": test_metrics, "rule_alert_volume": alert_metrics, "rule_legal_minimum": legal_metrics,
        "pr_auc": pr_auc, "headline_three_minute_warning": headline_rows,
        "median_warning_seconds": median_warning,
        "gates": {"gate_1_recall_floor": bool(gate_passed), "gate_2_beats_rule": bool(beats_rule)},
        "recall_margin_what_if": what_if_rows, "shap_mean_abs": shap_values,
    }
    MODEL_CARD_PATH.write_text(json.dumps(model_card, indent=2, default=float), encoding="utf-8")
    print(f"Model card: {MODEL_CARD_PATH}")


if __name__ == "__main__":
    main()
