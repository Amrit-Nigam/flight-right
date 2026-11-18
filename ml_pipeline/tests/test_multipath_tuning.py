"""Known-value scoring tests and regression checks for isolated multi-path experiments."""
import copy
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training/trajectory"))
from tune_multipath import energy_score, compare, alert_compare, split_validation


def baseline():
    group = {"n": 1000, "top1_mean_nm": 5., "top1_rmse_nm": 8., "top1_p90_nm": 12.,
             "top1_altitude_mae_ft": 1000., "energy_score": 1., "top1_within_1nm": 30.,
             "top1_within_5nm": 60., "best5_within_5nm": 80., "top1_both": 40., "best5_both": 60.}
    return {"groups": {"all": copy.deepcopy(group), "arrivals": copy.deepcopy(group)}, "regimes": []}


class MultiPathScoringTests(unittest.TestCase):
    def test_deterministic_energy_is_euclidean_error(self):
        value = energy_score(np.array([[[3., 4., 0.]]]), np.zeros((1, 3)), np.ones((1, 1)))
        self.assertEqual(value[0], 5.)

    def test_two_point_energy_known_value_and_permutation(self):
        points = np.array([[[0., 0., 0.], [2., 0., 0.]]])
        p = np.array([[.5, .5]])
        self.assertEqual(energy_score(points, np.zeros((1, 3)), p)[0], .5)
        np.testing.assert_array_equal(energy_score(points, np.zeros((1, 3)), p),
                                      energy_score(points[:, ::-1], np.zeros((1, 3)), p[:, ::-1]))

    def test_coverage_gain_cannot_hide_altitude_regression(self):
        b = baseline(); c = copy.deepcopy(b)
        c["groups"]["all"]["top1_altitude_mae_ft"] = 1050.
        c["groups"]["arrivals"]["best5_within_5nm"] = 85.
        self.assertFalse(compare(c, b)["passes_guardrails"])

    def test_identical_model_is_not_improvement(self):
        b = baseline(); r = compare(b, b)
        self.assertEqual(r["objective"], 0.)
        self.assertTrue(r["passes_guardrails"])
        self.assertFalse(r["improves_objective"])

    def test_alert_improvements_cannot_hide_a_lost_real_tier1(self):
        b = {"headline": {"caught": 270}, "true_positive": 290,
             "tier_1": {"real": 28, "false": 20}, "false_positive": 478,
             "display": {"prominent_real_with_3min": 250, "collapsed_real": 10,
                         "tier1_false": 20, "prominent_false": 100}}
        c = copy.deepcopy(b); c["tier_1"]["real"] = 27; c["false_positive"] = 470
        self.assertFalse(alert_compare(c, b)["passes_guardrails"])

    def test_chronological_partition_has_no_target_overlap(self):
        timestamps = np.concatenate([np.arange(0, 2000, 10), np.arange(5000, 7000, 10),
                                     np.arange(10000, 12000, 10), np.arange(15000, 17000, 10)])
        early, late = split_validation(timestamps)
        self.assertFalse(np.any(early & late))
        self.assertLess(timestamps[early].max() + 600, timestamps[late].min())


if __name__ == "__main__":
    unittest.main()
