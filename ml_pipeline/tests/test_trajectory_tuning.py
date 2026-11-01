"""Check that the experiment rejects material regressions despite an improved average."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training/trajectory"))
from tune_trajectory import compare


def baseline():
    row = {"horizon": "10 min", "mean_nm": 5., "rmse_nm": 8., "median_nm": 2.,
           "p90_nm": 12., "altitude_mae_ft": 1000., "cross_mae_nm": 3.,
           "within_1_nm": 30., "within_5_nm": 65., "within_3d": 45.}
    bucket = {"family": "turn", "bucket": "sharp", "horizon": "10 min", "n": 200,
              "mean_nm": 10., "within_5_nm": 25.}
    return {"per_horizon": [row], "per_bucket": [bucket]}


class TuningGuardTests(unittest.TestCase):
    def test_identical_model_is_not_an_improvement(self):
        b = baseline()
        c = compare(copy.deepcopy(b), b)
        self.assertEqual(c["objective"], 0.)
        self.assertTrue(c["passes_guardrails"])
        self.assertFalse(c["improves_objective"])

    def test_better_mean_does_not_hide_lost_close_hits(self):
        b, c = baseline(), baseline()
        c["per_horizon"][0]["mean_nm"] = 3.
        c["per_horizon"][0]["within_1_nm"] = 28.
        result = compare(c, b)
        self.assertTrue(result["improves_objective"])
        self.assertFalse(result["passes_guardrails"])

    def test_better_global_score_does_not_hide_sharp_turn_regression(self):
        b, c = baseline(), baseline()
        c["per_horizon"][0]["mean_nm"] = 4.
        c["per_bucket"][0]["mean_nm"] = 11.
        result = compare(c, b)
        self.assertTrue(result["improves_objective"])
        self.assertFalse(result["passes_guardrails"])

    def test_improvements_across_errors_and_rates_pass(self):
        b, c = baseline(), baseline()
        c["per_horizon"][0]["mean_nm"] = 4.5
        c["per_horizon"][0]["altitude_mae_ft"] = 950.
        c["per_horizon"][0]["within_3d"] = 46.
        result = compare(c, b)
        self.assertTrue(result["passes_guardrails"])
        self.assertTrue(result["improves_objective"])


if __name__ == "__main__":
    unittest.main()
