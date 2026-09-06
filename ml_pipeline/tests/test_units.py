"""Unit tests for the pieces added on 6 Sep 2026. Run: python -m unittest ml_pipeline.tests.test_units

No data files are needed. These are the first automated tests in the project.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for extra in (PROJECT_ROOT, PROJECT_ROOT / "ml_pipeline" / "training" / "trajectory",
              PROJECT_ROOT / "ml_pipeline" / "training" / "conflict_classifier"):
    sys.path.insert(0, str(extra))

from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    compute_cpa,
    compute_cpa_from_paths,
    cpa_grid_times,
    densify_path,
    predict_dense_grid,
)


class DensifyPathTests(unittest.TestCase):
    def test_grid_has_every_15s_point_and_matches_known_points(self):
        current = (19.0, 72.0, 10_000.0)
        predictions = {"1min": (19.05, 72.0, 10_000.0), "3min": (19.15, 72.0, 10_000.0),
                       "5min": (19.25, 72.0, 10_000.0), "10min": (19.5, 72.0, 10_000.0)}
        dense = densify_path(current, predictions)
        self.assertEqual(sorted(dense), cpa_grid_times())
        self.assertEqual(dense[0], current)
        self.assertEqual(dense[600], predictions["10min"])
        # 240 s lies halfway from 180 s to 300 s; 210 s a quarter of the way.
        self.assertAlmostEqual(dense[240][0], 19.20, places=9)
        self.assertAlmostEqual(dense[210][0], 19.15 + 0.25 * (19.25 - 19.15), places=9)

    def test_never_extrapolates_past_last_prediction(self):
        dense = densify_path((0.0, 0.0, 0.0), {"1min": (0.1, 0.0, 0.0), "3min": (0.3, 0.0, 0.0)})
        self.assertEqual(max(dense), 180)

    def test_finds_conflict_between_horizons_that_four_points_miss(self):
        # Two aircraft whose paths cross at t = 240 s and are far apart at 180 s and 300 s.
        state_a = {"latitude": 19.0, "longitude": 72.0, "altitude_m": 10_000.0, "velocity_ms": 240.0,
                   "heading_deg": 90.0, "vertical_rate_ms": 0.0}
        # B approaches from the south, aimed to reach A's 240 s point at 240 s.
        east_240 = 240.0 * 240.0  # metres A travels in 240 s
        meet_lon = 72.0 + east_240 / (111_320.0 * np.cos(np.radians(19.0)))
        state_b = {"latitude": 19.0 - east_240 / 111_320.0, "longitude": meet_lon, "altitude_m": 10_000.0,
                   "velocity_ms": 240.0, "heading_deg": 0.0, "vertical_rate_ms": 0.0}
        dense_a, dense_b = predict_dense_grid(state_a), predict_dense_grid(state_b)
        sparse_a = {h: dense_a[h] for h in (60, 180, 300, 600)}
        sparse_b = {h: dense_b[h] for h in (60, 180, 300, 600)}
        current_a = (state_a["latitude"], state_a["longitude"], state_a["altitude_m"])
        current_b = (state_b["latitude"], state_b["longitude"], state_b["altitude_m"])

        sparse = compute_cpa_from_paths([(1.0, sparse_a)], [(1.0, sparse_b)])
        dense = compute_cpa_from_paths([(1.0, sparse_a)], [(1.0, sparse_b)], current_a, current_b)
        self.assertGreater(sparse["cpa_lateral_distance_nm"], 8.0, "four-point check should miss it")
        self.assertLess(dense["cpa_lateral_distance_nm"], 1.0, "dense check should find the crossing")
        self.assertEqual(dense["time_to_cpa_seconds"], 240)
        self.assertEqual(sparse["conflict_probability"], 0.0)
        self.assertEqual(dense["conflict_probability"], 1.0)


class PlattCalibratorTests(unittest.TestCase):
    def test_monotone_and_fits_overconfident_scores(self):
        from train_xgboost import PlattCalibrator

        rng = np.random.default_rng(0)
        true_logit = rng.normal(0, 1.5, 20000)
        truth = (rng.uniform(size=20000) < 1 / (1 + np.exp(-true_logit))).astype(int)
        # Over-confident: the model reports logits three times too large.
        raw = 1 / (1 + np.exp(-3 * true_logit))
        calibrator = PlattCalibrator().fit(raw, truth)
        self.assertAlmostEqual(calibrator.a, 1 / 3, delta=0.05, msg="over-confident scores need a slope near 1/3")
        calibrated = calibrator.transform(raw)
        order = np.argsort(raw)
        self.assertTrue(np.all(np.diff(calibrated[order]) >= -1e-12), "must not change the ranking")
        threshold = 0.3
        mapped = calibrator.transform(np.array([threshold]))[0]
        np.testing.assert_array_equal(raw >= threshold, calibrated >= mapped)


class TemperatureScalingTests(unittest.TestCase):
    def test_temperature_reduces_nll_and_keeps_ranking(self):
        import multipath
        from sklearn.ensemble import HistGradientBoostingClassifier

        rng = np.random.default_rng(1)
        X = rng.normal(size=(3000, 6))
        y = (X[:, 0] + 0.5 * X[:, 1] + rng.normal(scale=1.5, size=3000) > 0).astype(int) \
            + 2 * (X[:, 2] > 0.5).astype(int)  # 4 classes
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.3, random_state=0).fit(X[:2000], y[:2000])
        val_X, val_y = X[2000:], y[2000:]
        temperature = multipath.fit_temperature(clf, val_X, val_y)
        before = multipath.pattern_probabilities(clf, val_X, 1.0)
        after = multipath.pattern_probabilities(clf, val_X, temperature)
        np.testing.assert_allclose(before, clf.predict_proba(val_X), atol=1e-9)
        idx = np.searchsorted(clf.classes_, val_y)
        nll = lambda p: -np.log(p[np.arange(len(idx)), idx]).mean()  # noqa: E731
        self.assertLessEqual(nll(after), nll(before) + 1e-9)
        np.testing.assert_array_equal(np.argsort(-before, axis=1), np.argsort(-after, axis=1))

    def test_ece_zero_for_perfect_and_positive_for_overconfident(self):
        import multipath
        stated = np.array([0.9] * 100)
        self.assertAlmostEqual(multipath.expected_calibration_error(stated, np.array([1.0] * 90 + [0.0] * 10)), 0.0, places=9)
        self.assertGreater(multipath.expected_calibration_error(stated, np.array([1.0] * 50 + [0.0] * 50)), 0.3)


class EncounterFeatureTests(unittest.TestCase):
    def test_feature_order_matches_feature_columns(self):
        from generate_synthetic_scenarios import FEATURE_COLUMNS, encounter_features, manoeuvre_summary

        a = {"latitude": 19.0, "longitude": 72.0, "altitude_m": 10_000.0, "velocity_ms": 240.0, "heading_deg": 90.0,
             "vertical_rate_ms": 0.0}
        b = {"latitude": 19.1, "longitude": 72.4, "altitude_m": 10_100.0, "velocity_ms": 230.0, "heading_deg": 270.0,
             "vertical_rate_ms": -3.0}
        summary = manoeuvre_summary(np.array([0, 10, 20, 30]), np.array([240, 241, 242, 243]),
                                    np.array([359.0, 0.0, 1.0, 2.0]), np.array([0.0, 0.0, 0.5, 1.0]))
        self.assertAlmostEqual(summary["turn_rate_deg_s"], 3.0 / 30.0, places=9, msg="359->2 is a 3 degree turn")
        features = encounter_features(a, b, summary, summary)
        self.assertEqual(list(features), FEATURE_COLUMNS)
        self.assertTrue(all(np.isfinite(v) for v in features.values()))


class InferenceWindowTests(unittest.TestCase):
    def test_window_from_states_matches_preprocess_layout(self):
        from server.app.ml.inference import window_from_states
        import framing

        states = [{"latitude": 19.0 + 0.001 * k, "longitude": 72.0, "altitude_m": 9000.0, "velocity_ms": 200.0,
                   "heading_deg": 0.0, "vertical_rate_ms": 0.0, "time_position": 1000 + 10 * k} for k in range(12)]
        X = window_from_states(states)
        self.assertEqual(X.shape, (1, 10, 8))
        self.assertAlmostEqual(float(X[0, -1, framing.LATITUDE]), 19.011, places=5)
        self.assertEqual(float(X[0, 0, framing.TIME_GAP]), 0.0)
        self.assertEqual(float(X[0, 1, framing.TIME_GAP]), 10.0)
        cv = framing.constant_velocity_predict(X)
        self.assertEqual(cv.shape, (1, 4, 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
