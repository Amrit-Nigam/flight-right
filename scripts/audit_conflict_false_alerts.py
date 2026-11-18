"""Replay actual multi-path geometry and production escalation for the threshold study."""
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
sys.path.insert(0, str(ROOT / 'ml_pipeline/training/conflict_classifier'))
from offsets_ab_test import inputs
from destination_row import a_callsigns
from server.app.ml.inference import MultiPathPredictor
from ml_pipeline.utils.cpa_conflict_detection import (
    CLASSIFIER_ALERT_KEY, RULE_GEOMETRY_KEY, assign_tier, compute_cpa_from_paths, escalate_pair)
import experiment_conflict_false_alerts as study


def main():
    r = json.loads((study.REPORT / 'results.json').read_text())
    audit = {}
    predictor = MultiPathPredictor(offsets='per_mode')
    for split in ('val', 'test'):
        frame, X, current = inputs(split)
        n = len(frame)
        calls = a_callsigns(frame, current[:n]) + [None] * n
        p, positions, _ = predictor.predict(X, extra=predictor.route_inputs(X, calls))
        import pandas as pd
        t = pd.read_parquet(study.TABLES / f'alert_prominence_{split}_baseline.parquet')
        flags = {'baseline': t.classifier_alert.to_numpy()}
        flags['threshold_classifier'] = t.classifier_raw.to_numpy() >= r['candidates'][0]['threshold']
        fired = {name: np.zeros(n, bool) for name in flags}
        tier = np.zeros(n, int)
        for i in range(n):
            rule = dict(cpa_lateral_distance_nm=float(frame.predicted_cpa_lateral_nm.iloc[i]),
                        cpa_vertical_separation_ft=float(frame.predicted_cpa_vertical_ft.iloc[i]),
                        time_to_cpa_seconds=float(frame.predicted_time_to_cpa_seconds.iloc[i]),
                        is_converging=True)
            chosen = (dict(rule) if assign_tier(rule)['tier'] == 1 else
                      {**compute_cpa_from_paths(predictor.paths_for_cpa(X, i, p, positions),
                                                predictor.paths_for_cpa(X, n+i, p, positions),
                                                tuple(current[i]), tuple(current[n+i])), RULE_GEOMETRY_KEY: rule})
            for name, alerts in flags.items():
                chosen[CLASSIFIER_ALERT_KEY] = bool(alerts[i])
                actual = escalate_pair(chosen, [chosen, chosen])
                fired[name][i] = actual['notify']
                tier[i] = actual['tier']
        assert np.array_equal(fired['baseline'], t.fired)
        y = t.y.to_numpy().astype(bool)
        result = r['candidates'][0]['validation' if split == 'val' else 'test']
        assert study.counts(y, fired['threshold_classifier']) == result['system']
        assert not np.any(y & fired['baseline'] & ~fired['threshold_classifier'])
        assert np.array_equal(tier, t.tier)
        audit[split] = dict(pairs=n, all_notifications_match=True, all_tiers_match=True,
                           lost_true_pairs=0, persistence='same geometry repeated for three updates; not a live stream replay')
        print(split, audit[split], flush=True)
    (study.REPORT / 'production_gate_audit.json').write_text(json.dumps(audit, indent=2))


if __name__ == '__main__':
    with threadpool_limits(4):
        main()
