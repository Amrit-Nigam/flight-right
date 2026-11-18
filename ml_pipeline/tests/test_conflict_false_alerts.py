"""Critical checks for local recall-constrained threshold experiments."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from experiment_conflict_false_alerts import floor_threshold, counts


class RecallConstraintTests(unittest.TestCase):
    def test_inclusive_threshold_preserves_lowest_protected_score_and_ties(self):
        scores = np.array([.02, .08, .08, .35])
        protected = np.array([False, True, False, True])
        t = floor_threshold(scores, protected)
        self.assertTrue(np.all((scores >= t)[protected]))
        self.assertEqual((scores >= t).tolist(), [False, True, True, True])
        self.assertFalse(np.all((scores >= np.nextafter(t, np.inf))[protected]))


    def test_no_positive_constraint_must_not_silently_select_a_threshold(self):
        with self.assertRaises(ValueError):
            floor_threshold(np.array([.1, .2]), np.array([False, False]))


    def test_matrix_orientation_and_f1_for_missed_conflict_and_false_alert(self):
        result = counts([True, True, False, False, False], [True, False, True, False, False])
        self.assertEqual(result['confusion_matrix'], [[2, 1], [1, 1]])
        self.assertEqual(result['precision'], .5)
        self.assertEqual(result['recall'], .5)
        self.assertEqual(result['f1'], .5)
