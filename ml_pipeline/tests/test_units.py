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
    CLASSIFIER_ALERT_KEY,
    RULE_GEOMETRY_KEY,
    alert_gate,
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


class SafetyNetGeometryTests(unittest.TestCase):
    """The safety net judges the straight-line rule, never a model path (24 Sep 2026)."""

    @staticmethod
    def pair(model_nm, model_ft, rule_nm, rule_ft):
        return {"cpa_lateral_distance_nm": model_nm, "cpa_vertical_separation_ft": model_ft,
                "time_to_cpa_seconds": 300.0, CLASSIFIER_ALERT_KEY: False,
                RULE_GEOMETRY_KEY: {"cpa_lateral_distance_nm": rule_nm,
                                    "cpa_vertical_separation_ft": rule_ft, "time_to_cpa_seconds": 300.0}}

    def test_model_breach_alone_does_not_fire_the_net(self):
        self.assertEqual(alert_gate(self.pair(1.0, 200.0, 12.0, 3000.0)), (False, "classifier"))

    def test_rule_breach_fires_the_net_even_when_the_model_path_is_clear(self):
        self.assertEqual(alert_gate(self.pair(12.0, 3000.0, 1.0, 200.0)), (True, "separation-minimum"))

    def test_without_rule_geometry_the_result_itself_is_judged(self):
        plain = {"cpa_lateral_distance_nm": 1.0, "cpa_vertical_separation_ft": 200.0,
                 "time_to_cpa_seconds": 300.0, CLASSIFIER_ALERT_KEY: False}
        self.assertEqual(alert_gate(plain), (True, "separation-minimum"))


class ClearanceTests(unittest.TestCase):
    """Plan Phase 7: what a known clearance may and may not do to candidate paths."""

    @staticmethod
    def fan():
        from ml_pipeline.utils.clearance import FT_PER_M
        # Three candidates from 20,000 ft, heading north: level, descending to 12,000,
        # and descending through 8,000. Positions at 1/3/5/10 min.
        def path(final_ft, east_deg=0.0):
            alt = np.linspace(20_000, final_ft, 4) / FT_PER_M
            return np.column_stack([19.0 + np.array([0.05, 0.15, 0.25, 0.5]),
                                    72.8 + np.array([0, 0, 0, east_deg]), alt])
        return np.array([0.5, 0.3, 0.2]), np.stack([path(20_000), path(12_000), path(8_000, east_deg=0.4)]), 20_000 / FT_PER_M

    def test_level_clearance_caps_altitude_and_eliminates_nothing(self):
        from ml_pipeline.utils.clearance import FT_PER_M, Clearance, apply_clearance
        probs, pos, alt = self.fan()
        p, q, kept, report = apply_clearance(probs, pos, alt, Clearance("abc", "DESCEND", 10_000))
        self.assertTrue(report["applied"])
        self.assertEqual(len(p), 3)
        self.assertTrue(np.all(q[..., 2] * FT_PER_M >= 10_000 - 1e-6), "no candidate may pass the cleared level")
        self.assertAlmostEqual(float(q[1, 3, 2] * FT_PER_M), 12_000, delta=1e-3)

    def test_heading_clearance_eliminates_and_renormalises(self):
        from ml_pipeline.utils.clearance import Clearance, apply_clearance
        probs, pos, alt = self.fan()
        p, q, kept, report = apply_clearance(probs, pos, alt, Clearance("abc", "TURN", 0.0))
        self.assertEqual(kept.tolist(), [0, 1])
        self.assertAlmostEqual(float(p.sum()), 1.0)

    def test_never_returns_an_empty_fan(self):
        from ml_pipeline.utils.clearance import Clearance, apply_clearance
        probs, pos, alt = self.fan()
        p, q, kept, report = apply_clearance(probs, pos, alt, Clearance("abc", "TURN", 180.0))
        self.assertEqual(len(p), 3)
        self.assertFalse(report["applied"])

    def test_implausible_value_is_rejected_not_applied(self):
        from ml_pipeline.utils.clearance import Clearance, apply_clearance
        probs, pos, alt = self.fan()
        p, q, kept, report = apply_clearance(probs, pos, alt, Clearance("abc", "DESCEND", 310_000))
        self.assertFalse(report["applied"])
        self.assertTrue(np.array_equal(q, pos))


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


class SpeechTextTests(unittest.TestCase):
    """The speech chain's text side: normalising, numbers, clearance extraction."""

    def test_normalise_is_the_one_spelling(self):
        from ml_pipeline.voice.text_norm import normalise
        self.assertEqual(normalise("Oscar Kilo\xa0Alpha Juliet re- pekný deň"),
                         "oscar kilo alfa juliett re pekny den")
        self.assertEqual(normalise(float("nan")), "")

    def test_numbers_are_read_the_way_atc_speaks_them(self):
        from ml_pipeline.voice.extract import read_number
        self.assertEqual(read_number("one two zero".split(), 0)[0], 120)
        self.assertEqual(read_number("five thousand five hundred".split(), 0)[0], 5500)
        self.assertEqual(read_number("one zero thousand".split(), 0)[0], 10000)
        self.assertEqual(read_number("niner tree".split(), 0)[0], 93)

    def test_levels_headings_and_speeds(self):
        from ml_pipeline.voice.extract import extract
        cases = {
            "ifly five three two three descend flight level one two zero": ("DESCEND", 12000.0),
            "descend to five thousand feet": ("DESCEND", 5000.0),
            "air india one zero one climb three three zero": ("CLIMB", 33000.0),   # bare level = FL
            "turn left heading zero nine zero": ("TURN", 90.0),
            "reduce speed two five zero knots": ("SPEED", 250.0),
            "climb straight ahead four thousand feet": ("CLIMB", 4000.0),
            "five thousand five hundred feet climbing": ("CLIMB", 5500.0),           # readback order
        }
        for text, (action, value) in cases.items():
            got = extract(text)
            self.assertEqual((got.action, got.value), (action, value), text)

    def test_things_that_are_not_clearances(self):
        from ml_pipeline.voice.extract import extract
        self.assertIsNone(extract("runway two seven cleared to land wind two five zero degrees nine knots").action)
        self.assertIsNone(extract("squawk four five two one").action)
        # "passing X" is where the aircraft is, not where it is going
        self.assertEqual(extract("passing two thousand climbing five thousand").value, 5000.0)

    def test_annotation_tags_map_onto_our_actions(self):
        from ml_pipeline.voice.extract import gold_action
        self.assertEqual(gold_action("descend", "flight level one hundred"), ("DESCEND", 10000.0, None))
        self.assertEqual(gold_action("turn left heading", "three six zero"), ("TURN", 360.0, None))
        self.assertEqual(gold_action("proceed direct", "Baltu"), ("DIRECT", None, "baltu"))
        self.assertEqual(gold_action("cleared to land", "runway two four"), (None, None, None))


class CallsignTests(unittest.TestCase):
    """Spoken <-> written callsigns and snapping onto visible aircraft (plan 6.2)."""

    @classmethod
    def setUpClass(cls):
        from ml_pipeline.voice import callsigns
        try:
            cls.table = callsigns.telephony()
        except OSError as failure:          # first run offline: the FAA / OpenFlights tables are fetched once
            raise unittest.SkipTest(f"telephony tables unavailable: {failure}")
        cls.c = callsigns

    def test_indian_telephony_from_the_faa_list(self):
        self.assertEqual(self.table["IGO"], "ifly")
        self.assertEqual(self.table["AKJ"], "akasa air")     # missing from OpenFlights
        self.assertEqual(self.table["OMS"], "mazoon")        # OpenFlights has a defunct carrier

    def test_spoken_forms_and_back(self):
        self.assertEqual(self.c.spoken_forms("IGO5323"), ["ifly five three two three"])
        self.assertIn("oscar mike bravo", self.c.spoken_forms("OKPMB"))           # ICAO abbreviated form
        self.assertEqual(self.c.spoken_to_code("air india one zero one"), "AIC101")
        self.assertEqual(self.c.spoken_to_code("csa one delta zulu"), "CSA1DZ")    # shortened telephony

    def test_matching_snaps_a_misheard_callsign(self):
        got = self.c.match("ifly five tree two three descend flight level two four zero",
                           ["IGO5323", "IGO5232", "AIC101"])
        self.assertEqual(got["code"], "IGO5323")
        self.assertIsNone(self.c.match("speedbird eight five five climb", ["IGO5323", "AIC101"])["code"])


class RadioChannelTests(unittest.TestCase):
    def test_passband(self):
        from ml_pipeline.voice.radio_channel import radio
        t = np.arange(32_000) / 16_000
        x = (0.5 * np.sin(2 * np.pi * 1000 * t) + 0.5 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
        y = radio(x, None, np.random.default_rng(0))
        spectrum, freqs = np.abs(np.fft.rfft(y)), np.fft.rfftfreq(len(y), 1 / 16_000)
        at = lambda hz: spectrum[np.argmin(np.abs(freqs - hz))]  # noqa: E731
        self.assertGreater(at(1000), 100 * at(6000))
        self.assertLessEqual(float(np.max(np.abs(y))), 0.9 + 1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
