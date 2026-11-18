"""Before serving the dialled-level classifier: does its gain survive other random seeds?

    python ml_pipeline/utils/classifier_intent_seeds.py

The served decision (Archit, 26 Sep): add the three dialled-level inputs and choose the
threshold on VALIDATION at the served classifier's validation false-alarm rate ("same alarm
rate"), so any gain is spent on catching real conflicts. train_xgboost.py does exactly that for
seed 42. This repeats it for seeds 42, 1, 2, 3 with every other setting identical, scores each
ONCE on test, and compares conflict by conflict with the SERVED classifier (the 6 Sep model), so
a gain that one seed happened to find cannot be mistaken for a property of the inputs.
Trains nothing that is served. Writes ml_pipeline/reports/classifier_intent_seeds_<stamp>.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

import xgboost  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402
from generate_synthetic_scenarios import FEATURE_COLUMNS  # noqa: E402
from train_xgboost import (INTENT_COLUMNS, add_intent_columns, headline_metric, latest_dataset_path,  # noqa: E402
                           metrics_at_threshold, reference_false_alarm_rate, split_by_session,
                           threshold_at_false_alarm_rate)

SERVED = ROOT / "server/app/ml/saved_models/xgboost_conflict.json"
SEEDS = (42, 1, 2, 3)


def main() -> None:
    dataset = add_intent_columns(pd.read_parquet(latest_dataset_path()))
    dataset = dataset.dropna(subset=FEATURE_COLUMNS + ["is_conflict"])
    splits = split_by_session(dataset)
    y = {k: v["is_conflict"].astype(int).to_numpy() for k, v in splits.items()}
    target_fa, served_val_recall = reference_false_alarm_rate(str(SERVED), splits["val"])

    served = xgboost.Booster()
    served.load_model(str(SERVED))
    served_raw = served.predict(xgboost.DMatrix(splits["test"][FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS))
    served_alerts = served_raw >= float(json.loads(served.attr("decision_threshold")))
    served_metrics = metrics_at_threshold(y["test"], served_raw, float(json.loads(served.attr("decision_threshold"))))
    rate, caught, total = headline_metric(splits["test"], served_alerts.astype(int))
    served_metrics["headline"] = {"rate": rate, "caught": caught, "total": total}
    in_time = (y["test"] == 1) & (splits["test"]["actual_time_to_cpa_seconds"].to_numpy() >= 180)

    columns = FEATURE_COLUMNS + INTENT_COLUMNS
    per_seed = {}
    for seed in SEEDS:
        model = XGBClassifier(objective="binary:logistic", n_estimators=300, max_depth=6, learning_rate=0.05,
                              subsample=0.8, colsample_bytree=0.7,
                              scale_pos_weight=(y["train"] == 0).sum() / (y["train"] == 1).sum(),
                              random_state=seed, eval_metric="logloss", tree_method="hist", device="cpu")
        model.fit(splits["train"][columns], y["train"])
        p_val = model.predict_proba(splits["val"][columns])[:, 1]
        p_test = model.predict_proba(splits["test"][columns])[:, 1]
        threshold = threshold_at_false_alarm_rate(y["val"], p_val, target_fa)
        val = metrics_at_threshold(y["val"], p_val, threshold)
        test = metrics_at_threshold(y["test"], p_test, threshold)
        alerts = p_test >= threshold
        rate, caught, total = headline_metric(splits["test"], alerts.astype(int))
        per_seed[seed] = {"threshold": threshold, "validation": {"recall": val["recall"],
                                                                 "false_alarms_per_1000": val["false_alarms_per_1000"]},
                          "test": {k: test[k] for k in ("recall", "precision", "false_alarms_per_1000", "fbeta_2")},
                          "headline": {"rate": rate, "caught": caught, "total": total},
                          "vs_served_real_conflicts_with_3min": {
                              "gained": int((alerts & ~served_alerts & in_time).sum()),
                              "lost": int((~alerts & served_alerts & in_time).sum())},
                          "gate_1_recall_floor": bool(test["recall"] >= 0.95)}
        s = per_seed[seed]
        print(f"seed {seed:>2}: val recall {val['recall']:.4f} @ {val['false_alarms_per_1000']:.1f} FA | test recall "
              f"{test['recall']:.4f} FA {test['false_alarms_per_1000']:.1f} | 3-min {caught}/{total} | "
              f"vs served +{s['vs_served_real_conflicts_with_3min']['gained']} -{s['vs_served_real_conflicts_with_3min']['lost']}")
    print(f"served : val recall {served_val_recall:.4f} @ {target_fa:.1f} FA | test recall {served_metrics['recall']:.4f} "
          f"FA {served_metrics['false_alarms_per_1000']:.1f} | 3-min {served_metrics['headline']['caught']}/{total}")
    report = {"measured_at_utc": datetime.now().isoformat(), "rule": "threshold on validation at the served "
              "classifier's validation false-alarm rate", "served_validation_false_alarms_per_1000": target_fa,
              "served": {"validation_recall": served_val_recall, **{k: served_metrics[k] for k in
                         ("recall", "precision", "false_alarms_per_1000", "headline")}},
              "per_seed": per_seed,
              "summary": {k: {"mean": float(np.mean([per_seed[s]["test"][k] for s in SEEDS])),
                              "min": float(np.min([per_seed[s]["test"][k] for s in SEEDS])),
                              "max": float(np.max([per_seed[s]["test"][k] for s in SEEDS]))}
                          for k in ("recall", "precision", "false_alarms_per_1000")}}
    out = ROOT / "ml_pipeline/reports" / f"classifier_intent_seeds_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=float))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
