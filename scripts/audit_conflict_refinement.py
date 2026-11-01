"""Actual served-trajectory and escalation audit for validation-frozen refinement winner."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '4')
import json
import sys
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'ml_pipeline/utils'))
import experiment_conflict_refinement as study
from offsets_ab_test import inputs
from destination_row import a_callsigns
from server.app.ml.inference import MultiPathPredictor
from ml_pipeline.utils.cpa_conflict_detection import (
    CLASSIFIER_ALERT_KEY, RULE_GEOMETRY_KEY, assign_tier, compute_cpa_from_paths, escalate_pair)


def main():
    study.setup()
    r = json.loads((study.REPORT / 'results.json').read_text())
    chosen_name = r['winners']['classifier_training']
    c = next(c for c in r['candidates'] if c['name'] == chosen_name)
    assert c['eligible_for_further_audit']
    predictor = MultiPathPredictor(offsets='per_mode')
    audit = dict(candidate=chosen_name, splits={})
    for split, key in [('val', 'validation'), ('test', 'test')]:
        d = study.first.load(split)
        frame, X, current = inputs(split)
        n = len(frame)
        calls = a_callsigns(frame, current[:n]) + [None] * n
        p, positions, _ = predictor.predict(X, extra=predictor.route_inputs(X, calls))
        alert = study.alert_for(c, d, r['protocol']['base_threshold'])
        fired, tiers = np.zeros(n, bool), np.zeros(n, int)
        for i in range(n):
            rule = dict(cpa_lateral_distance_nm=float(frame.predicted_cpa_lateral_nm.iloc[i]),
                        cpa_vertical_separation_ft=float(frame.predicted_cpa_vertical_ft.iloc[i]),
                        time_to_cpa_seconds=float(frame.predicted_time_to_cpa_seconds.iloc[i]), is_converging=True)
            chosen = dict(rule) if assign_tier(rule)['tier'] == 1 else {
                **compute_cpa_from_paths(predictor.paths_for_cpa(X, i, p, positions),
                                         predictor.paths_for_cpa(X, n+i, p, positions),
                                         tuple(current[i]), tuple(current[n+i])), RULE_GEOMETRY_KEY: rule}
            chosen[CLASSIFIER_ALERT_KEY] = bool(alert[i])
            actual = escalate_pair(chosen, [chosen, chosen])
            fired[i], tiers[i] = actual['notify'], actual['tier']
        assert np.array_equal(tiers, d['table'].tier)
        assert np.array_equal(fired, (d['hard'] | alert) & d['eligible'])
        assert study.first.counts(d['y'], fired) == c[key]['system']
        lost = d['y'] & d['baseline'] & ~fired
        assert not lost.any()
        audit['splits'][split] = dict(pairs=n, notifications_match=True, tiers_match=True,
                                      no_lost_real_pairs=True, lost_pair_rows=np.flatnonzero(lost).tolist(),
                                      persistence='Same geometry for three updates, not live transition replay')
        print(split, audit['splits'][split], flush=True)
    study.write('production_gate_audit.json', audit)


if __name__ == '__main__':
    with threadpool_limits(4):
        main()
