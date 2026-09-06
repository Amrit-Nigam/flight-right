"""Load the three trained models and run them on live aircraft states.

This is the bridge between the training pipeline and the FastAPI backend. Every
transform here is imported from the training code -- framing.py for the trajectory
frame, generate_synthetic_scenarios.encounter_features for the pair features, and
cpa_conflict_detection for the geometry -- so inference can never drift from what the
models were trained on. Nothing in this file re-implements a feature.

Three predictors, each usable on its own, plus a ConflictEngine that runs the whole
chain for a set of aircraft:

  TrajectoryPredictor   the residual LSTM: one path per aircraft at 1/3/5/10 min.
  MultiPathPredictor    the route-pattern model: top-K paths with CALIBRATED probabilities.
  ConflictClassifier    XGBoost over a pair's predicted features: calibrated conflict
                        probability, alert decision at the saved threshold, and the
                        per-feature SHAP explanation for that alert.

The deterministic rule path (constant velocity + dense-grid CPA) is always run first
and is what tier 1 uses; the learned models add on top, never replace (CLAUDE.md
Section 13). If a model file is missing the engine degrades to the rule path and says
so in every result, rather than failing.

A confirmed tier 1 alarm then goes on to Model 3, the rule-based resolution engine,
which returns up to three ranked and explained ways out. So the chain ends in "here is
what you could do about it" rather than in "there is a problem". Nothing is ever
applied: the options are returned for the controller to accept, dismiss or override
(CLAUDE.md Section 12).

State dictionaries use the field names the rest of the project uses:
    latitude, longitude, altitude_m, velocity_ms, heading_deg, vertical_rate_ms,
    time_position (unix seconds)
"""

from __future__ import annotations

import json
import os
import pickle
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
# Import order matters: xgboost and torch each bundle an OpenMP runtime, and on macOS
# loading torch first makes xgboost's Booster.load_model segfault (measured 6 Sep 2026,
# exit -11). Importing xgboost before anything that pulls in torch avoids it on every
# platform, so this import stays at the top even though it looks unused here.
import xgboost  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[3]
for extra in (PROJECT_ROOT, PROJECT_ROOT / "ml_pipeline" / "training" / "trajectory",
              PROJECT_ROOT / "ml_pipeline" / "training" / "conflict_classifier"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import framing  # noqa: E402  (ml_pipeline/training/trajectory)
from generate_synthetic_scenarios import (  # noqa: E402
    FEATURE_COLUMNS,
    encounter_features,
    manoeuvre_summary,
)
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    assign_tier,
    classify_conflict,
    compute_cpa_from_paths,
    compute_cpa_from_states,
    escalate_pair,
)
# Model 3. Pure rules and kinematics, no saved model file, so it is imported directly
# like the other project modules rather than loaded and version-checked.
from ml_pipeline.utils.resolution_engine import generate_resolutions  # noqa: E402

DATA_ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", PROJECT_ROOT))
SAVED_MODELS = DATA_ROOT / "server" / "app" / "ml" / "saved_models"
TRAJECTORY_PATH = SAVED_MODELS / "trajectory_residual.pt"
MULTIPATH_PATH = SAVED_MODELS / "trajectory_multipath.pkl"
CONFLICT_PATH = SAVED_MODELS / "xgboost_conflict.json"

INPUT_STEPS = 10
HORIZON_LABELS = {60: "1min", 180: "3min", 300: "5min", 600: "10min"}
METRES_TO_FEET = 3.28084


# --------------------------------------------------------------------------------------
# Turning a live track into the model's input window
# --------------------------------------------------------------------------------------

def window_from_states(states: Sequence[Mapping[str, float]]) -> np.ndarray:
    """The last ten states of one aircraft -> the (1, 10, 8) array the models consume.

    Column order is fixed by preprocess_sequences.py and framing.py:
    latitude, longitude, altitude_m, velocity_ms, sin(track), cos(track),
    vertical_rate_ms, time_gap_s. States must be oldest first.
    """
    if len(states) < INPUT_STEPS:
        raise ValueError(f"Need {INPUT_STEPS} states for a window, got {len(states)}.")
    recent = list(states)[-INPUT_STEPS:]
    times = np.array([float(s["time_position"]) for s in recent])
    headings = np.deg2rad(np.array([float(s["heading_deg"]) for s in recent]))
    time_gaps = np.diff(times, prepend=times[0])
    window = np.column_stack((
        [s["latitude"] for s in recent], [s["longitude"] for s in recent],
        [s["altitude_m"] for s in recent], [s["velocity_ms"] for s in recent],
        np.sin(headings), np.cos(headings),
        [s.get("vertical_rate_ms", 0.0) or 0.0 for s in recent], time_gaps,
    )).astype(np.float32)
    return window[None, :, :]


def _horizon_dict(positions: np.ndarray) -> dict[str, tuple[float, float, float]]:
    """(4, 3) lat/lon/alt at the four horizons -> {'1min': (...), ...}."""
    return {HORIZON_LABELS[int(h)]: (float(p[0]), float(p[1]), float(p[2]))
            for h, p in zip(framing.HORIZONS_SECONDS, positions)}


# --------------------------------------------------------------------------------------
# Model 1: single-answer residual LSTM
# --------------------------------------------------------------------------------------

class TrajectoryPredictor:
    """Residual LSTM on top of constant velocity. Zero output == constant velocity."""

    def __init__(self, path: Path = TRAJECTORY_PATH) -> None:
        import torch
        import train_trajectory  # the module that defines the architecture

        if sys.platform == "darwin" and not torch.cuda.is_available():
            # torch, scikit-learn and xgboost each ship their own OpenMP runtime on
            # macOS. Once the other two have initialised theirs, torch's first parallel
            # region (the copy inside load_state_dict) deadlocks. Measured 6 Sep 2026.
            # Inference batches here are a few aircraft, so one thread costs nothing.
            torch.set_num_threads(1)
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        self.model = train_trajectory.ResidualTrajectoryModel()
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self.feature_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["feature_normalization"].items()}
        self.residual_stats = {k: np.asarray(v, dtype=np.float64) for k, v in checkpoint["residual_normalization"].items()}
        self.config = checkpoint["config"]
        self.training_summary = checkpoint.get("training_summary", {})
        self.version = f"trajectory_residual@{path.stat().st_mtime_ns}"

    def predict(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (model positions, constant-velocity positions), each (N, 4, 3)."""
        import torch

        cv = framing.constant_velocity_predict(X)
        sequence, scalars = framing.to_local_features(X)
        sequence = (sequence - self.feature_stats["sequence_mean"]) / self.feature_stats["sequence_std"]
        scalars = (scalars - self.feature_stats["scalar_mean"]) / self.feature_stats["scalar_std"]
        with torch.no_grad():
            normalised = self.model(torch.from_numpy(sequence.astype(np.float32)),
                                    torch.from_numpy(scalars.astype(np.float32))).numpy().astype(np.float64)
        residual = normalised * self.residual_stats["residual_std"] + self.residual_stats["residual_mean"]
        return framing.apply_residual(X, cv, residual), cv


# --------------------------------------------------------------------------------------
# Model 1b: multi-path with calibrated probabilities
# --------------------------------------------------------------------------------------

class MultiPathPredictor:
    """Top-K route patterns per aircraft, probabilities calibrated by temperature scaling."""

    def __init__(self, path: Path = MULTIPATH_PATH) -> None:
        import multipath

        with path.open("rb") as handle:
            bundle = pickle.load(handle)
        self._multipath = multipath
        self.classifier = bundle["classifier"]
        self.kmeans = bundle["kmeans"]
        self.pattern_residuals = bundle["pattern_residuals"]
        # Older pickles (before 6 Sep 2026) have no temperature: 1.0 reproduces them exactly.
        self.temperature = float(bundle.get("temperature", 1.0))
        self.calibration = bundle.get("calibration", {})
        self.config = bundle["config"]
        self.top_k = int(self.config.get("top_k", 5))
        self.version = f"trajectory_multipath@{path.stat().st_mtime_ns}"

    def predict(self, X: np.ndarray, top_k: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (probabilities (N, k), positions (N, k, 4, 3), pattern ids (N, k))."""
        probabilities, positions, patterns, _ = self._multipath.candidate_paths(
            self.classifier, self.kmeans, self.pattern_residuals, X, top_k or self.top_k, self.temperature
        )
        return probabilities, positions, patterns

    def paths_for_cpa(self, X: np.ndarray, index: int, probabilities: np.ndarray, positions: np.ndarray):
        """The (probability, predictions) list compute_cpa_from_paths expects, for one aircraft."""
        return [(float(probabilities[index, option]), _horizon_dict(positions[index, option]))
                for option in range(probabilities.shape[1])]


# --------------------------------------------------------------------------------------
# Model 2: conflict classifier with calibrated probability and SHAP explanation
# --------------------------------------------------------------------------------------

class ConflictClassifier:
    """XGBoost over a pair's t=0 features. Alerts at the threshold chosen in training."""

    def __init__(self, path: Path = CONFLICT_PATH) -> None:
        import xgboost

        self.booster = xgboost.Booster()
        self.booster.load_model(str(path))
        attributes = self.booster.attributes()
        self.feature_columns = json.loads(attributes["feature_columns"])
        if self.feature_columns != FEATURE_COLUMNS:
            raise RuntimeError("Saved model's feature list differs from generate_synthetic_scenarios.FEATURE_COLUMNS.")
        self.threshold = float(json.loads(attributes["decision_threshold"]))
        self.platt_a = float(json.loads(attributes.get("platt_a", "1.0")))
        self.platt_b = float(json.loads(attributes.get("platt_b", "0.0")))
        self.calibrated_threshold = float(json.loads(attributes.get("calibrated_decision_threshold",
                                                                    json.dumps(self.threshold))))
        self.version = f"xgboost_conflict@{path.stat().st_mtime_ns}"
        self._xgboost = xgboost

    def _calibrate(self, raw: np.ndarray) -> np.ndarray:
        clipped = np.clip(raw, 1e-7, 1 - 1e-7)
        logit = np.log(clipped / (1 - clipped))
        return 1.0 / (1.0 + np.exp(-(self.platt_a * logit + self.platt_b)))

    def predict(self, features: Sequence[Mapping[str, float]]) -> list[dict[str, Any]]:
        """One result per pair: raw and calibrated probability, alert flag, top SHAP reasons."""
        matrix = np.array([[float(row[column]) for column in self.feature_columns] for row in features])
        dmatrix = self._xgboost.DMatrix(matrix, feature_names=self.feature_columns)
        raw = self.booster.predict(dmatrix)
        calibrated = self._calibrate(raw)
        contributions = self.booster.predict(dmatrix, pred_contribs=True)[:, :-1]
        results = []
        for index in range(len(matrix)):
            order = np.argsort(-np.abs(contributions[index]))[:5]
            results.append({
                "raw_probability": float(raw[index]),
                "conflict_probability": float(calibrated[index]),
                "alert": bool(raw[index] >= self.threshold),
                "decision_threshold": self.threshold,
                "calibrated_decision_threshold": self.calibrated_threshold,
                # Positive contribution pushes towards "conflict", negative away from it.
                "explanation": [
                    {"feature": self.feature_columns[i], "value": float(matrix[index, i]),
                     "contribution": float(contributions[index, i])}
                    for i in order
                ],
                "model_version": self.version,
            })
        return results


# --------------------------------------------------------------------------------------
# The whole chain for a set of aircraft
# --------------------------------------------------------------------------------------

@dataclass
class ConflictEngine:
    """Rule path always; learned models when their files exist."""

    trajectory: TrajectoryPredictor | None = None
    multipath: MultiPathPredictor | None = None
    classifier: ConflictClassifier | None = None
    missing: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "ConflictEngine":
        engine = cls()
        for name, path, attribute, factory in (
            ("trajectory_residual", TRAJECTORY_PATH, "trajectory", TrajectoryPredictor),
            ("trajectory_multipath", MULTIPATH_PATH, "multipath", MultiPathPredictor),
            ("xgboost_conflict", CONFLICT_PATH, "classifier", ConflictClassifier),
        ):
            if path.exists():
                setattr(engine, attribute, factory(path))
            else:
                engine.missing.append(name)
        return engine

    def status(self) -> dict[str, Any]:
        return {
            "trajectory_residual": getattr(self.trajectory, "version", None),
            "trajectory_multipath": getattr(self.multipath, "version", None),
            "xgboost_conflict": getattr(self.classifier, "version", None),
            "multipath_temperature": getattr(self.multipath, "temperature", None),
            "missing_models": list(self.missing),
            "rule_path": "always on",
        }

    @staticmethod
    def _current(state: Mapping[str, float]) -> dict[str, float]:
        return {key: float(state[key]) for key in
                ("latitude", "longitude", "altitude_m", "velocity_ms", "heading_deg", "vertical_rate_ms")}

    def assess_pair(self, history_a: Sequence[Mapping[str, float]], history_b: Sequence[Mapping[str, float]],
                    pair_history: Sequence[Mapping[str, Any]] = (),
                    traffic: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        """Everything the dashboard needs for one pair, with a reason for each number.

        history_* are each aircraft's recent states, oldest first, at least ten. The
        rule path needs only the latest state; the models need the window.
        pair_history is the list of previous results for this pair (for the
        3-consecutive-updates rule).

        traffic is every OTHER aircraft nearby, each {"callsign", "history"}. Supplied,
        a suggested manoeuvre is also checked against those aircraft and rejected if it
        would create a new conflict with one of them. Omitted, resolutions consider only
        this pair, which is how a fix for one conflict becomes a conflict elsewhere.
        """
        state_a, state_b = self._current(history_a[-1]), self._current(history_b[-1])

        # 1. Deterministic path: constant velocity on the dense 15 s grid. Always.
        rule_cpa = compute_cpa_from_states(state_a, state_b)
        rule_class = classify_conflict(rule_cpa)
        result: dict[str, Any] = {
            "rule": {**{k: v for k, v in rule_cpa.items() if k != "grid"}, **rule_class},
            "sources": ["constant-velocity dense-grid CPA (rule path)"],
        }

        # 2. Multi-path conflict probability over K x K candidate combinations, densified.
        cpa_for_tiering = rule_cpa
        resolution_paths_a = resolution_paths_b = None
        if self.multipath is not None and len(history_a) >= INPUT_STEPS and len(history_b) >= INPUT_STEPS:
            X = np.concatenate([window_from_states(history_a), window_from_states(history_b)])
            probabilities, positions, patterns = self.multipath.predict(X)
            paths_a = self.multipath.paths_for_cpa(X, 0, probabilities, positions)
            paths_b = self.multipath.paths_for_cpa(X, 1, probabilities, positions)
            current_a = (state_a["latitude"], state_a["longitude"], state_a["altitude_m"])
            current_b = (state_b["latitude"], state_b["longitude"], state_b["altitude_m"])
            multipath_cpa = compute_cpa_from_paths(paths_a, paths_b, current_a, current_b)
            result["multipath"] = {
                "conflict_probability": multipath_cpa["conflict_probability"],
                "combinations_checked": multipath_cpa["combinations_checked"],
                "combinations_breaching": multipath_cpa["combinations_breaching"],
                "cpa_lateral_distance_nm": multipath_cpa["cpa_lateral_distance_nm"],
                "cpa_vertical_separation_ft": multipath_cpa["cpa_vertical_separation_ft"],
                "time_to_cpa_seconds": multipath_cpa["time_to_cpa_seconds"],
                "candidates_a": [{"probability": p, "pattern": int(patterns[0, i]), "positions": _horizon_dict(positions[0, i])}
                                 for i, p in enumerate(probabilities[0])],
                "candidates_b": [{"probability": p, "pattern": int(patterns[1, i]), "positions": _horizon_dict(positions[1, i])}
                                 for i, p in enumerate(probabilities[1])],
                "model_version": self.multipath.version,
                "probabilities_calibrated": self.multipath.temperature != 1.0,
            }
            result["sources"].append("multi-path K x K on the dense grid")
            # Kept for Model 3: the resolution check runs against these weighted futures
            # rather than a single straight line for the aircraft that is NOT moving.
            resolution_paths_a, resolution_paths_b = paths_a, paths_b
            # Tier 1 (<= 180 s) stays on the rule path by decision (CLAUDE.md Section 3);
            # the multi-path probability drives tier 2, where constant velocity degrades.
            if assign_tier(rule_cpa)["tier"] != 1:
                cpa_for_tiering = multipath_cpa

        # 3. XGBoost: will these two ACTUALLY lose separation, given the prediction?
        if self.classifier is not None:
            manoeuvre_a = _manoeuvre_from_history(history_a)
            manoeuvre_b = _manoeuvre_from_history(history_b)
            features = encounter_features(state_a, state_b, manoeuvre_a, manoeuvre_b, rule_cpa)
            result["classifier"] = self.classifier.predict([features])[0]
            result["sources"].append("XGBoost conflict classifier (calibrated, SHAP-explained)")

        # 4. Tiering and escalation with the anti-flicker rule.
        escalation = escalate_pair(cpa_for_tiering, [h.get("_cpa_for_tiering", h) for h in pair_history])
        result["escalation"] = escalation

        # 5. Model 3: what to actually do about it.
        #
        # Fed the RULE path, not the multi-path result, for two reasons. Tier 1 runs on
        # constant velocity by decision (Section 3), and resolutions are tier 1 only, so
        # the rule CPA is the geometry this alarm was raised on. The engine also flies
        # each candidate itself rather than trusting any predicted path.
        #
        # The engine obeys escalation["suggest_resolution"] internally, so a tier 2
        # advisory returns offered=False with a reason instead of a manoeuvre, and a
        # tier 1 pair that has not yet held for three consecutive updates gets nothing
        # either. Passing escalation through is what enforces that.
        callsign_a = str(history_a[-1].get("callsign") or "AIRCRAFT A").strip()
        callsign_b = str(history_b[-1].get("callsign") or "AIRCRAFT B").strip()
        # Every OTHER aircraft nearby, with its own predicted paths where the model can
        # supply them, so a manoeuvre is tested against the whole picture.
        neighbours = []
        for entry in traffic:
            neighbour_history = entry.get("history") or ()
            if not neighbour_history:
                continue
            neighbour_paths = None
            if self.multipath is not None and len(neighbour_history) >= INPUT_STEPS:
                nx = window_from_states(neighbour_history)
                np_prob, np_pos, _ = self.multipath.predict(nx)
                neighbour_paths = self.multipath.paths_for_cpa(nx, 0, np_prob, np_pos)
            neighbours.append({
                "callsign": str(entry.get("callsign")
                                or neighbour_history[-1].get("callsign") or "another aircraft").strip(),
                "state": self._current(neighbour_history[-1]),
                "paths": neighbour_paths,
            })
        resolutions = generate_resolutions(state_a, state_b, rule_cpa, escalation,
                                           callsign_a, callsign_b,
                                           paths_a=resolution_paths_a,
                                           paths_b=resolution_paths_b,
                                           traffic=neighbours)
        result["resolution"] = {
            "offered": resolutions["offered"],
            "reason": resolutions["reason"],
            "options": [_resolution_to_dict(option) for option in resolutions["options"]],
        }
        if resolutions["offered"]:
            # Counts only exist once the engine actually evaluated candidates. The
            # blocked count is Section 10's "unsafe suggestions blocked" metric.
            result["resolution"].update({
                "unavailable_manoeuvre_types": resolutions["unavailable_kinds"],
                "checked_against": resolutions.get("checked_against"),
                "candidates_evaluated": resolutions["counts"]["evaluated"],
                "blocked_unsafe": resolutions["counts"]["blocked_unsafe"],
                "rejected_ineffective": resolutions["counts"]["rejected_ineffective"],
                # The domino count: manoeuvres that fixed this pair but would have
                # caused a conflict with a third aircraft.
                "rejected_new_conflict": resolutions["counts"].get("rejected_domino", 0),
                "blocked_detail": [{"aircraft": o.manoeuvre.aircraft, "manoeuvre_type": o.manoeuvre.kind,
                                    "magnitude": o.manoeuvre.magnitude, "reason": o.blocked_reason}
                                   for o in resolutions["blocked"]],
                "new_conflict_detail": [{"aircraft": o.manoeuvre.aircraft,
                                         "manoeuvre_type": o.manoeuvre.kind,
                                         "magnitude": o.manoeuvre.magnitude,
                                         "would_conflict_with": o.creates_conflict_with,
                                         "risk": o.new_conflict_risk}
                                        for o in resolutions.get("would_create_new_conflict", [])],
            })
            result["sources"].append("rule-based resolution engine (Model 3)")

        result["_cpa_for_tiering"] = {k: v for k, v in cpa_for_tiering.items() if k not in ("grid", "combinations")}
        result["_cpa_for_tiering"]["grid"] = cpa_for_tiering.get("grid", [])
        result["model_versions"] = self.status()
        return result

    def predict_trajectory(self, history: Sequence[Mapping[str, float]]) -> dict[str, Any]:
        """Single aircraft: constant velocity always, LSTM and multi-path when available."""
        X = window_from_states(history)
        cv = framing.constant_velocity_predict(X)
        out: dict[str, Any] = {"constant_velocity": _horizon_dict(cv[0]), "confidence_note":
                               "constant velocity is exact for straight and level flight; see multipath for alternatives"}
        if self.trajectory is not None:
            predicted, _ = self.trajectory.predict(X)
            out["residual_lstm"] = _horizon_dict(predicted[0])
            out["residual_lstm_version"] = self.trajectory.version
        if self.multipath is not None:
            probabilities, positions, patterns = self.multipath.predict(X)
            out["multipath"] = [{"probability": float(p), "pattern": int(patterns[0, i]),
                                 "positions": _horizon_dict(positions[0, i])} for i, p in enumerate(probabilities[0])]
            out["multipath_version"] = self.multipath.version
        return out


def _resolution_to_dict(option: Any) -> dict[str, Any]:
    """Flatten one ResolutionOption into the JSON the dashboard consumes.

    The engine returns dataclasses; everything crossing this boundary has to be plain
    data. The explanation is carried through verbatim because Section 12 forbids
    surfacing a suggestion without one.
    """
    return {
        "aircraft": option.manoeuvre.aircraft,
        "manoeuvre_type": option.manoeuvre.kind,
        "magnitude": option.manoeuvre.magnitude,
        "unit": option.manoeuvre.unit,
        "resulting_lateral_separation_nm": option.resulting_lateral_nm,
        "resulting_vertical_separation_ft": option.resulting_vertical_ft,
        "resolves": option.resolves,
        "seconds_to_establish": option.seconds_to_establish,
        "established_before_cpa": option.established_before_cpa,
        "delay_seconds": option.delay_seconds,
        "fuel_equivalent_seconds": option.fuel_equivalent_seconds,
        "confidence": option.confidence,
        "score": option.score,
        "score_components": option.components,
        # How much of the other aircraft's predicted futures this still fails against,
        # and how much of a third aircraft's futures it would newly endanger.
        "residual_risk": option.residual_risk,
        "new_conflict_risk": option.new_conflict_risk,
        "explanation": option.explanation,
    }


def _manoeuvre_from_history(history: Sequence[Mapping[str, float]]) -> dict[str, float]:
    recent = list(history)[-INPUT_STEPS:]
    return manoeuvre_summary(
        np.array([float(s["time_position"]) for s in recent]),
        np.array([float(s["velocity_ms"]) for s in recent]),
        np.array([float(s["heading_deg"]) for s in recent]),
        np.array([float(s.get("vertical_rate_ms", 0.0) or 0.0) for s in recent]),
    )


if __name__ == "__main__":
    engine = ConflictEngine.load()
    print(json.dumps(engine.status(), indent=2))
