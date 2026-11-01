"""Local false-alert study. Never writes served artifacts or changes runtime gates.

Frozen trajectory/classifier stacking uses early validation sessions for fitting,
late validation sessions for selection, and the existing historical test for audit.
"""
from __future__ import annotations
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '4')
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ml_pipeline/training/conflict_classifier'))
import train_xgboost as tx

REPORT = ROOT / 'ml_pipeline/reports/conflict_false_alerts_20261101'
WORK = ROOT / 'ml_pipeline/data/processed/conflict_experiments/20261101'
TABLES = ROOT / 'ml_pipeline/data/processed/multipath_experiments/20261101/alert_tables'
SAVED = ROOT / 'server/app/ml/saved_models'
MP = ['mp_p_alert_volume', 'mp_p_legal_minimum',
      'mp_p_alert_volume_within_180s', 'mp_worst_time_s']
CONFIGS = [dict(name='depth2', max_depth=2, n_estimators=150, min_child_weight=10, reg_lambda=10),
           dict(name='depth3', max_depth=3, n_estimators=250, min_child_weight=10, reg_lambda=10),
           dict(name='depth4', max_depth=4, n_estimators=300, min_child_weight=20, reg_lambda=20)]


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def floor_threshold(scores, protected):
    """Largest inclusive threshold preserving every protected row; never uses test."""
    if not np.any(protected):
        raise ValueError('No protected true positives; threshold is unidentified')
    return float(np.min(scores[protected]))


def counts(y, p):
    y, p = np.asarray(y, bool), np.asarray(p, bool)
    tp, fp, fn, tn = (int((y & p).sum()), int((~y & p).sum()),
                      int((y & ~p).sum()), int((~y & ~p).sum()))
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=precision, recall=recall,
                f1=2 * tp / max(2 * tp + fp + fn, 1), confusion_matrix=[[tn, fp], [fn, tp]])


def load(split):
    f = tx.attach_intent_columns(tx.split_by_session(pd.read_parquet(tx.latest_dataset_path()))[split]).reset_index(drop=True)
    t = pd.read_parquet(TABLES / f'alert_prominence_{split}_baseline.parquet')
    assert np.array_equal(f.is_conflict, t.y)
    raw = tx.classifier_raw_scores(booster, f)
    assert np.array_equal(raw, t.classifier_raw.to_numpy(dtype=np.float32))
    hard = ((f.predicted_cpa_lateral_nm < 5) & (f.predicted_cpa_vertical_ft < 1000)).to_numpy()
    eligible = t.tier.to_numpy() > 0
    baseline = (hard | (raw >= original_threshold)) & eligible
    assert np.array_equal(baseline, t.fired)
    features = f[original_columns].assign(classifier_raw=raw)
    for c in MP:
        features[c] = t[c].to_numpy()
    return dict(frame=f, table=t, features=features, raw=raw, hard=hard,
                eligible=eligible, baseline=baseline, y=f.is_conflict.to_numpy().astype(bool))


def evaluate(d, alert, probabilities=None):
    fired = (d['hard'] | alert) & d['eligible']
    y, base, t = d['y'], d['baseline'], d['table']
    result = dict(classifier=counts(y, alert), system=counts(y, fired),
                  lost_true_pair_rows=np.flatnonzero(y & base & ~fired).tolist(),
                  gained_true_pair_rows=np.flatnonzero(y & ~base & fired).tolist(),
                  lost_classifier_true_rows=np.flatnonzero(y & (d['raw'] >= original_threshold) & ~alert).tolist(),
                  early_true=int((fired & y & t.in_time.to_numpy()).sum()),
                  early_total=int((y & t.in_time.to_numpy()).sum()),
                  tier1_true=int((fired & y & (t.tier.to_numpy() == 1)).sum()),
                  tier1_false=int((fired & ~y & (t.tier.to_numpy() == 1)).sum()))
    if probabilities is not None:
        result['ranking'] = dict(pr_auc=float(average_precision_score(y, probabilities)),
                                 roc_auc=float(roc_auc_score(y, probabilities)),
                                 raw_brier=float(brier_score_loss(y, probabilities)))
    result['passes_true_preservation'] = not result['lost_true_pair_rows']
    return result


def subset(d, mask):
    return {k: (v.loc[mask].reset_index(drop=True) if isinstance(v, pd.DataFrame) else v[mask]) for k, v in d.items()}


def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    before = {p.name: digest(p) for p in (SAVED / 'xgboost_conflict.json', SAVED / 'trajectory_multipath.pkl')}
    val = load('val')
    sessions = sorted(val['frame'].split_session.unique())
    fit_mask = val['frame'].split_session.isin(sessions[:3]).to_numpy()
    fit, select = subset(val, fit_mask), subset(val, ~fit_mask)
    assert select['frame'].seed_time_position.min() - fit['frame'].seed_time_position.max() > 600
    plan = dict(original_threshold=original_threshold, original_columns=original_columns,
                mp_columns=MP, fit_sessions=[int(x) for x in sessions[:3]],
                selection_sessions=[int(x) for x in sessions[3:]], fit_rows=int(fit_mask.sum()),
                selection_rows=int((~fit_mask).sum()), configs=CONFIGS,
                objective='fewest selection system false positives preserving each baseline true pair',
                test_policy='Freeze all settings and winner before loading historical test; no test-led retries',
                stacking='Frozen upstream models trained before validation. No validation fit rows used for threshold selection.',
                hashes_before=before)
    (REPORT / 'protocol.json').write_text(json.dumps(plan, indent=2))
    candidates = []
    # Threshold-only studies use full validation, no model fitting.
    for scope in ('classifier', 'system'):
        protected = val['y'] & ((val['raw'] >= original_threshold) if scope == 'classifier'
                                else (val['baseline'] & ~val['hard']))
        threshold = max(original_threshold, floor_threshold(val['raw'], protected))
        candidates.append(dict(name=f'threshold_{scope}', threshold=threshold, kind='threshold',
                               validation=evaluate(val, val['raw'] >= threshold, val['raw'])))
    # New learned veto models. Existing classifier must also alert; safety net always bypasses veto.
    for with_mp in (False, True):
        columns = original_columns + ['classifier_raw'] + (MP if with_mp else [])
        for cfg in CONFIGS:
            params = {k: v for k, v in cfg.items() if k != 'name'}
            name = ('multipath_' if with_mp else 'existing_inputs_') + cfg['name']
            model = XGBClassifier(**params, learning_rate=.04, subsample=.9,
                                  colsample_bytree=1., objective='binary:logistic',
                                  tree_method='hist', n_jobs=4, random_state=42,
                                  eval_metric='logloss')
            model.fit(fit['features'][columns], fit['y'].astype(int))
            p = model.predict_proba(select['features'][columns])[:, 1]
            protected = select['y'] & select['baseline'] & ~select['hard']
            threshold = floor_threshold(p, protected)
            alert = (select['raw'] >= original_threshold) & (p >= threshold)
            result = evaluate(select, alert, p)
            model.save_model(WORK / f'{name}.json')
            np.savez_compressed(WORK / f'{name}_selection_scores.npz', scores=p)
            candidates.append(dict(name=name, kind='veto', with_mp=with_mp,
                                   columns=columns, threshold=threshold, selection=result))
            print(name, threshold, result['system'], flush=True)
    veto = [c for c in candidates if c['kind'] == 'veto']
    winner = min(veto, key=lambda c: (c['selection']['system']['fp'], len(c['columns']), c['name']))['name']
    mp_winner = min([c for c in veto if c['with_mp']], key=lambda c: (c['selection']['system']['fp'], c['name']))['name']
    # Freeze selection before test is opened.
    (REPORT / 'selection.json').write_text(json.dumps(dict(winner=winner, multipath_winner=mp_winner, candidates=candidates), indent=2))
    test = load('test')
    result = dict(protocol=plan, selected_veto=winner, selected_multipath_veto=mp_winner, baselines={}, candidates=candidates)
    for split, d in [('validation', val), ('selection', select), ('test', test)]:
        result['baselines'][split] = evaluate(d, d['raw'] >= original_threshold, d['raw'])
    result['test_safety_net'] = counts(test['y'], test['hard'] & test['eligible'])
    for c in candidates:
        for split, d in [('validation', val), ('test', test)]:
            if c['kind'] == 'threshold':
                p, alert = d['raw'], d['raw'] >= c['threshold']
            else:
                model = XGBClassifier()
                model.load_model(WORK / f"{c['name']}.json")
                p = model.predict_proba(d['features'][c['columns']])[:, 1]
                alert = (d['raw'] >= original_threshold) & (p >= c['threshold'])
            c[split] = evaluate(d, alert, p)
            if split == 'test':
                np.savez_compressed(WORK / f"{c['name']}_test_predictions.npz", scores=p, alert=alert)
        c['passes_test_guard_only'] = c['test']['passes_true_preservation'] and c['test']['system']['fp'] < result['baselines']['test']['system']['fp']
        c['eligible_after_selection_and_audit'] = c['passes_test_guard_only'] and (c['kind'] == 'threshold' or c['name'] == winner)
        print(c['name'], 'TEST', c['test']['system'], 'lost', len(c['test']['lost_true_pair_rows']), flush=True)
    result['hashes_after'] = {p.name: digest(p) for p in (SAVED / 'xgboost_conflict.json', SAVED / 'trajectory_multipath.pkl')}
    assert before == result['hashes_after']
    (REPORT / 'results.json').write_text(json.dumps(result, indent=2))
    (REPORT / 'source_snapshot.txt').write_bytes(Path(__file__).read_bytes())


if __name__ == '__main__':
    import xgboost
    booster = xgboost.Booster()
    booster.load_model(SAVED / 'xgboost_conflict.json')
    original_columns = json.loads(booster.attr('feature_columns'))
    original_threshold = json.loads((SAVED / 'xgboost_conflict_model_card.json').read_text())['decision_threshold']
    with threadpool_limits(4):
        main()
