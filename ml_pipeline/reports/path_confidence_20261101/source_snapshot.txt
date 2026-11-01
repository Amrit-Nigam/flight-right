"""Threshold study for the all-pairs shadow monitor; no live policy changes."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '4')
import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'ml_pipeline/utils'))
import experiment_conflict_refinement as refine
from offsets_ab_test import inputs
from destination_row import a_callsigns
from server.app.ml.inference import MultiPathPredictor
from ml_pipeline.utils.path_confidence_monitor import summarize
REPORT = ROOT/'ml_pipeline/reports/path_confidence_20261101'
WORK = ROOT/'ml_pipeline/data/processed/path_confidence_experiments/20261101'
THRESHOLDS = [0., .01, .025, .05, .1, .2, .4, .6, .8]
SCORES = ['total_weight', 'max_joint_weight', 'both_path_weight']
MODES = ['path_only', 'safety_plus_paths', 'served_with_path_gate', 'refined_with_path_gate', 'served_plus_paths']


def write(name, value):
    (REPORT/name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def evidence(split):
    path = WORK/f'{split}_evidence.parquet'
    if path.exists():
        return pd.read_parquet(path)
    f, X, current = inputs(split)
    n = len(f)
    predictor = MultiPathPredictor(offsets='per_mode')
    calls = a_callsigns(f, current[:n]) + [None]*n
    p, positions, patterns = predictor.predict(X, extra=predictor.route_inputs(X, calls))
    rows = []
    for i in range(n):
        a = dict(paths=predictor.paths_for_cpa(X,i,p,positions),patterns=patterns[i],current=current[i])
        b = dict(paths=predictor.paths_for_cpa(X,n+i,p,positions),patterns=patterns[n+i],current=current[n+i])
        summary = summarize(a,b)
        rows.append({**{k:summary[k] for k in SCORES}, 'hits':len(summary['combinations']),
                     'checks':summary['combinations_checked'], 'y':int(f.is_conflict.iloc[i])})
    out = pd.DataFrame(rows)
    # Existing served audit tables establish correspondence with the previous geometry.
    table = pd.read_parquet(refine.first.TABLES/f'alert_prominence_{split}_baseline.parquet')
    np.testing.assert_allclose(out.total_weight, table.mp_p_alert_volume, atol=1e-12, rtol=1e-12)
    np.testing.assert_array_equal(out.y, table.y)
    out.to_parquet(path)
    print(split, 'evidence cached', len(out), flush=True)
    return out


def policy(d, ev, score, threshold, mode, refined):
    paths = (ev.hits.to_numpy()>0) & (ev[score].to_numpy()>=threshold)
    original = d['raw']>=refine.first.original_threshold
    if mode == 'path_only':
        flag = paths
    elif mode == 'safety_plus_paths':
        flag = d['hard'] | paths
    elif mode == 'served_with_path_gate':
        flag = d['hard'] | (original & paths)
    elif mode == 'refined_with_path_gate':
        flag = d['hard'] | (refined & paths)
    else:
        flag = d['hard'] | original | paths
    return flag & d['eligible']


def metrics(d, fired):
    y, table = d['y'], d['table']
    return dict(**refine.first.counts(y,fired), lost_original_true_rows=np.flatnonzero(y & d['baseline'] & ~fired).tolist(),
                gained_original_true_rows=np.flatnonzero(y & ~d['baseline'] & fired).tolist(),
                early_true=int((fired & y & table.in_time.to_numpy()).sum()),
                early_total=int((y & table.in_time.to_numpy()).sum()),
                tier1_true=int((fired & y & (table.tier.to_numpy()==1)).sum()),
                tier1_false=int((fired & ~y & (table.tier.to_numpy()==1)).sum()))


def main():
    if (REPORT/'results.json').exists():
        raise RuntimeError('Preserve completed study; use another experiment directory')
    REPORT.mkdir(parents=True,exist_ok=True)
    WORK.mkdir(parents=True,exist_ok=True)
    refine.setup()
    prior = json.loads((refine.REPORT/'results.json').read_text())
    candidate = next(c for c in prior['candidates'] if c['name']==prior['winners']['classifier_training'])
    protocol = dict(created_utc=datetime.now(timezone.utc).isoformat(), thresholds=THRESHOLDS, scores=SCORES, modes=MODES,
                    selection='For each score/policy, minimize validation FP preserving every originally detected real pair. If infeasible, record no candidate; best-F1 threshold is diagnostic only.',
                    caveat='Historical benchmark already examined. Static snapshots cannot measure warning delay or real stream persistence. No live threshold changes.',
                    checkpoint='checkpoints/20261101_pre_path_confidence',
                    threshold_zero='Still requires at least one predicted conflicting combination; no combination is not treated as a zero-threshold alert.',
                    probability='Top-five weights normalized per aircraft; products assume independent choices. Not calibrated conflict probabilities.',
                    own_design='All-pairs shadow state, threshold policies and persistence are our own experimental design.',
                    hashes={p.name:refine.first.digest(p) for p in [refine.first.SAVED/'trajectory_multipath.pkl',refine.first.SAVED/'xgboost_conflict.json']})
    write('protocol.json',protocol)
    val, ev = refine.first.load('val'), evidence('val')
    refined = refine.alert_for(candidate,val,prior['protocol']['base_threshold'])
    trials = []
    selections = {}
    for mode in MODES:
        for score in SCORES:
            group = []
            for threshold in THRESHOLDS:
                fired = policy(val,ev,score,threshold,mode,refined)
                c = dict(mode=mode,score=score,threshold=threshold,validation=metrics(val,fired))
                trials.append(c)
                group.append(c)
            feasible = [c for c in group if not c['validation']['lost_original_true_rows']]
            winner = min(feasible,key=lambda c:(c['validation']['fp'],-c['threshold'])) if feasible else None
            diagnostic = max(group,key=lambda c:(c['validation']['f1'],-c['validation']['fp']))
            selections[f'{mode}/{score}'] = dict(selected_threshold=winner['threshold'] if winner else None,
                                                  diagnostic_f1_threshold=diagnostic['threshold'])
    write('selection.json',dict(selections=selections,trials=trials))
    test, et = refine.first.load('test'), evidence('test')
    test_refined = refine.alert_for(candidate,test,prior['protocol']['base_threshold'])
    for c in trials:
        c['test'] = metrics(test,policy(test,et,c['score'],c['threshold'],c['mode'],test_refined))
    summary = dict(protocol=protocol,selections=selections,trials=trials,
                   baselines=dict(served=metrics(test,test['baseline']),refined=metrics(test,(test['hard']|test_refined)&test['eligible'])),
                   zero_path_evidence={})
    for split,d,e in [('val',val,ev),('test',test,et)]:
        missing = d['y'] & d['baseline'] & (e.hits.to_numpy()==0)
        missing_unprotected = missing & ~d['hard']
        summary['zero_path_evidence'][split] = dict(original_true_with_no_conflicting_path=int(missing.sum()),
                                                   not_rescued_by_safety_net=int(missing_unprotected.sum()),
                                                   row_indices=np.flatnonzero(missing_unprotected).tolist())
    assert protocol['hashes']=={p.name:refine.first.digest(p) for p in [refine.first.SAVED/'trajectory_multipath.pkl',refine.first.SAVED/'xgboost_conflict.json']}
    write('results.json',summary)
    (REPORT/'source_snapshot.txt').write_bytes(Path(__file__).read_bytes())
    print('No-path evidence:',summary['zero_path_evidence'],flush=True)
    for key,selection in selections.items():
        t = selection['selected_threshold']
        row = next((c for c in trials if f"{c['mode']}/{c['score']}"==key and c['threshold']==t),None)
        print(key, 'selected',t, 'test', {k:row['test'][k] for k in ['tp','fp','early_true']} if row else 'INFEASIBLE',flush=True)


if __name__ == '__main__':
    with threadpool_limits(4):
        main()
