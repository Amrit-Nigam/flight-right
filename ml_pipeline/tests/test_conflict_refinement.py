"""Boundary and protection checks for the experimental raw-score veto rule."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from experiment_conflict_refinement import rule_ceiling


class ConservativeRuleTests(unittest.TestCase):
    def test_protected_rows_inside_region_are_kept_with_margin(self):
        raw = np.array([.1, .2, .4, .5])
        protected = np.array([False, True, True, False])
        region = np.array([True, True, False, True])
        ceiling = rule_ceiling(raw, protected, region)
        veto = region & (raw < ceiling)
        self.assertTrue(veto[0])
        self.assertFalse(np.any(veto & protected))
        self.assertFalse(veto[2])

    def test_empty_protected_region_is_capped(self):
        ceiling = rule_ceiling(np.array([.1, .7]), np.array([False, True]), np.array([True, False]))
        self.assertEqual(ceiling, .25)

    def test_strict_veto_keeps_exact_protected_boundary(self):
        raw = np.array([.1, .2])
        ceiling = rule_ceiling(raw, np.array([False, True]), np.array([True, True]), margin=1.)
        self.assertEqual(ceiling, .2)
        self.assertFalse(bool(raw[1] < ceiling))
