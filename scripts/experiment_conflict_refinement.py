"""Second, explicitly exploratory batch: no served writes and no test-led selection."""
from __future__ import annotations
import os
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '4')
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import xgboost as xgb
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import experiment_conflict_false_alerts as first
REPORT = ROOT / 'ml_pipeline/reports/conflict_refinement_20261101'
WORK = ROOT / 'ml_pipeline/data/processed/conflict_experiments/20261101_refinement'
MASS_CUTS = [0., .01, .05, .1, .25, .5]
REFITS = [dict(name='continue_unweighted', continuation=True, depth=3, rounds=150, weighted=False),
          dict(name='continue_weighted', continuation=True, depth=3, rounds=150, weighted=True),
          dict(name='refit_depth2', continuation=False, depth=2, rounds=400, weighted=True),
          dict(name='refit_depth3', continuation=False, depth=3, rounds=400, weighted=True),
          dict(name='refit_depth4', continuation=False, depth=4, rounds=400, weighted=True),
          dict(name='refit_unweighted', continuation=False, depth=3, rounds=400, weighted=False)]


def write(name, data):
    (REPORT / name).write_text(json.dumps(data, indent=2), encoding='utf-8')


def setup():
    first.booster = xgb.Booster()
    first.booster.load_model(first.SAVED / 'xgboost_conflict.json')
    first.original_columns = json.loads(first.booster.attr('feature_columns'))
    first.original_threshold = json.loads((first.SAVED / 'xgboost_conflict_model_card.json').read_text())['decision_threshold']


def rule_ceiling(raw, protected, region, margin=.8, cap=.25):
    """Conservative strict raw-score veto; protected boundary is always retained."""
    applicable = protected & region
    return min(cap, float(raw[applicable].min()) * margin) if applicable.any() else cap


def raw_alert(d, cutoff):
    return d['raw'] >= cutoff


def result(d, alert):
    r = first.evaluate(d, alert)
    r['passes_strict_guard'] = not r['lost_true_pair_rows'] and not r['lost_classifier_true_rows']
    return r


def model_scores(path, d, columns):
    model = xgb.Booster()
    model.load_model(path)
    return model.predict(xgb.DMatrix(d['features'][columns], feature_names=columns))


def alert_for(c, d, cutoff):
    initial = raw_alert(d, cutoff)
    if c['kind'] == 'rule':
        region = d['features'][c['column']].to_numpy() <= c['mass_cut']
        return initial & ~(region & (d['raw'] < c['raw_ceiling']))
    if c['kind'] == 'ensemble':
        scores = np.stack([model_scores(first.WORK / f'{name}.json', d, c['columns']) for name in c['members']], axis=1)
        score = scores.max(axis=1) if c['aggregation'] == 'max' else scores.mean(axis=1)
    else:
        score = model_scores(WORK / f"{c['name']}.json", d, first.original_columns)
    return initial & (score >= c['score_floor'])


def main():
    if (REPORT / 'results.json').exists():
        raise RuntimeError('Completed study exists; preserve it instead of overwriting.')
    REPORT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    setup()
    proposal = json.loads((first.REPORT / 'threshold_proposal.json').read_text())
    cutoff = proposal['proposed_raw_threshold']
    val = first.load('val')
    protected = val['y'] & (val['raw'] >= first.original_threshold)
    protocol = dict(created_at_utc=datetime.now(timezone.utc).isoformat(),
                    base_threshold=cutoff, masses=MASS_CUTS, refits=REFITS,
                    raw_rule_margin=.8, raw_rule_cap=.25, learned_floor_margin=.5,
                    fit='Original 28746 training pairs for refits/continuation; previously saved early-validation filters for ensembles',
                    guard='No lost original classifier true pair AND no lost original full-chain true pair; unchanged safety net and tiers',
                    selection='One winner per family by validation false alerts, then simpler name; require no classifier/system true losses on validation',
                    test='Existing historical audit has already been inspected. Freeze all family winners before loading it. Never choose an unselected diagnostic using test outcomes.',
                    limitations='Exploratory repeated benchmark. No guarantee of no lost future conflicts.',
                    source='Conservative conjunctions, margins and veto design are our own design, not a published guarantee.',
                    reference='https://xgboost.readthedocs.io/en/stable/python/python_api.html',
                    hashes_before={p.name: first.digest(p) for p in [first.SAVED/'xgboost_conflict.json', first.SAVED/'trajectory_multipath.pkl']})
    write('protocol.json', protocol)
    candidates = []
    # Own-design rules: low raw score together with low mass of predicted conflict paths.
    for column in first.MP[:3]:
        for cut in MASS_CUTS:
            region = val['features'][column].to_numpy() <= cut
            ceiling = rule_ceiling(val['raw'], protected, region)
            c = dict(name=f'rule_{column}_{cut:g}', kind='rule', family='multipath_rules',
                     column=column, mass_cut=cut, raw_ceiling=ceiling)
            c['validation'] = result(val, alert_for(c, val, cutoff))
            candidates.append(c)
    # Existing early-validation filters are applied together. Max keeps an alert if
    # even one member remains concerned; mean pools scores, not calibrated risks.
    for with_mp in [False, True]:
        members = [('multipath_' if with_mp else 'existing_inputs_') + name for name in ['depth2', 'depth3', 'depth4']]
        columns = first.original_columns + ['classifier_raw'] + (first.MP if with_mp else [])
        scores = np.stack([model_scores(first.WORK / f'{name}.json', val, columns) for name in members], axis=1)
        for aggregation in ['max', 'mean']:
            p = scores.max(axis=1) if aggregation == 'max' else scores.mean(axis=1)
            # Include all validation real pairs, including earlier fit sessions,
            # to guard the operating floor. Only later sessions rank these stacks.
            floor = .5 * first.floor_threshold(p, protected)
            c = dict(name=f"ensemble_{'multipath' if with_mp else 'existing'}_{aggregation}",
                     kind='ensemble', family='conservative_ensembles', columns=columns,
                     members=members, aggregation=aggregation, score_floor=floor)
            c['validation'] = result(val, alert_for(c, val, cutoff))
            select = first.subset(val, val['frame'].split_session.isin([24,25]).to_numpy())
            c['selection'] = result(select, alert_for(c, select, cutoff))
            candidates.append(c)
    train = first.tx.add_intent_columns(pd.read_parquet(first.tx.latest_dataset_path()))
    train = first.tx.split_by_session(train)['train']
    matrix = xgb.DMatrix(train[first.original_columns], label=train.is_conflict, feature_names=first.original_columns)
    weight = float((train.is_conflict == 0).sum() / (train.is_conflict == 1).sum())
    for cfg in REFITS:
        params = dict(objective='binary:logistic', eval_metric='logloss', tree_method='hist',
                      nthread=4, eta=.025 if cfg['continuation'] else .04,
                      max_depth=cfg['depth'], min_child_weight=20, reg_lambda=20.,
                      subsample=.9, colsample_bytree=1., seed=42,
                      scale_pos_weight=weight if cfg['weighted'] else 1.)
        model = xgb.train(params, matrix, num_boost_round=cfg['rounds'],
                          xgb_model=first.booster if cfg['continuation'] else None)
        model.save_model(WORK / f"{cfg['name']}.json")
        p = model.predict(xgb.DMatrix(val['features'][first.original_columns], feature_names=first.original_columns))
        floor = .5 * first.floor_threshold(p, protected)
        c = dict(name=cfg['name'], family='classifier_training', kind='trained_veto',
                 config=cfg, score_floor=floor, rounds_actual=model.num_boosted_rounds())
        c['validation'] = result(val, alert_for(c, val, cutoff))
        candidates.append(c)
    winners = {}
    for family in sorted({c['family'] for c in candidates}):
        eligible = [c for c in candidates if c['family'] == family and c['validation']['passes_strict_guard']]
        winners[family] = min(eligible, key=lambda c: (c.get('selection', c['validation'])['system']['fp'], c['name']))['name']
    write('selection.json', dict(winners=winners, candidates=candidates))
    print('Frozen family selections:', winners, flush=True)
    # First test access for this batch; no settings or family winners change below.
    test = first.load('test')
    outputs = dict(protocol=protocol, winners=winners, candidates=candidates, baselines={})
    for split, d in [('validation', val), ('test', test)]:
        outputs['baselines'][split] = dict(served=result(d, raw_alert(d, first.original_threshold)),
                                           prior_proposal=result(d, raw_alert(d, cutoff)))
    for c in candidates:
        alert = alert_for(c, test, cutoff)
        c['test'] = result(test, alert)
        c['selected_before_test'] = c['name'] == winners[c['family']]
        c['eligible_for_further_audit'] = c['selected_before_test'] and c['test']['passes_strict_guard'] and c['test']['system']['fp'] < outputs['baselines']['test']['prior_proposal']['system']['fp']
        np.savez_compressed(WORK / f"{c['name']}_test.npz", alert=alert)
        print(c['name'], 'FP', c['test']['system']['fp'], 'lost system/classifier',
              len(c['test']['lost_true_pair_rows']), len(c['test']['lost_classifier_true_rows']),
              'SELECTED' if c['selected_before_test'] else '', flush=True)
    outputs['hashes_after'] = {p.name: first.digest(p) for p in [first.SAVED/'xgboost_conflict.json', first.SAVED/'trajectory_multipath.pkl']}
    assert outputs['hashes_after'] == protocol['hashes_before']
    write('results.json', outputs)
    (REPORT / 'source_snapshot.txt').write_bytes(Path(__file__).read_bytes())


if __name__ == '__main__':
    with threadpool_limits(4):
        main()
