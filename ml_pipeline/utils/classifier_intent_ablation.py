"""Plan 9.0 on the CONFLICT CLASSIFIER: does the dialled altitude cut false alarms safely?

    python ml_pipeline/utils/classifier_intent_ablation.py

Background. 64.8% of the classifier's false alarms are pairs that pass close laterally but
stay stacked vertically. The 7 Sep level-flight filter cut 46% of them and lost 21 real
conflicts, because "level now" does not mean "level in ten minutes" and we could not see the
cleared level. EUROCONTROL STCA Option E uses the cleared/selected level for exactly this.
adsb.lol broadcasts the selected level for 94.8% of reports near VABB (plan 9.0). But on 25 Sep
it was also measured that 77.5% of level-changing aircraft are re-cleared past their dialled
level within ten minutes. So the level is an input to LEARN from, not a hard rule to apply.

What this does. The encounter dataset is rebuilt exactly (offsets_ab_test.rebuild, verified
row-for-row), recording which real aircraft and moment each side came from. Each aircraft's
dialled level is joined BACKWARD in time (<= 300 s, context_features.MAX_AGE_S), and three
features are added:

  a_sel_alt_delta_ft, b_sel_alt_delta_ft   dialled level - current altitude (NaN if unknown)
  sel_level_separation_ft                 |A's dialled level - B's dialled level| (both known)

B's future was moved by an altitude offset; its dialled level moves with it, so the DELTA is
invariant and B's dialled level is b_altitude_ft + delta.

Then two XGBoost models are trained with the project's fixed hyperparameters and seed:
BASELINE (the 24 features, retrained here so both rows share every setting) and + INTENT.
Each threshold is chosen on VALIDATION at the 0.95 recall floor (train_xgboost.select_threshold)
and scored ONCE on test. It also reports each model at the baseline's exact false-alarm rate,
so recall cannot be bought with alarms. Trains nothing that is served; writes
ml_pipeline/reports/classifier_intent_<stamp>.json.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/utils"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

from offsets_ab_test import rebuild, verify_identical  # noqa: E402
from context_features import MAX_AGE_S  # noqa: E402
from train_xgboost import (RANDOM_SEED, TARGET_RECALL, headline_metric, latest_dataset_path,  # noqa: E402
                           metrics_at_threshold, select_threshold, split_by_session)
from generate_synthetic_scenarios import FEATURE_COLUMNS  # noqa: E402

FT = 3.28084
INTENT_COLUMNS = ["a_sel_alt_delta_ft", "b_sel_alt_delta_ft", "sel_level_separation_ft"]


def dialled_delta(icao: np.ndarray, time: np.ndarray, altitude_ft: np.ndarray, intent: pd.DataFrame) -> np.ndarray:
    left = pd.DataFrame({"i": np.arange(len(icao)), "icao24": icao.astype(str), "time": time.astype(np.int64)}).sort_values("time")
    right = intent[["icao24", "time", "nav_altitude_mcp"]].sort_values("time")
    joined = pd.merge_asof(left, right, on="time", by="icao24", direction="backward",
                           tolerance=int(MAX_AGE_S), allow_exact_matches=True).sort_values("i")
    return joined["nav_altitude_mcp"].to_numpy(dtype=np.float64) - altitude_ft


def train_and_score(splits: dict, columns: list[str], seed: int = RANDOM_SEED) -> dict:
    from xgboost import XGBClassifier
    x = {k: v[columns] for k, v in splits.items()}
    y = {k: v["is_conflict"].astype(int).to_numpy() for k, v in splits.items()}
    model = XGBClassifier(objective="binary:logistic", n_estimators=300, max_depth=6, learning_rate=0.05,
                          subsample=0.8, colsample_bytree=0.7,
                          scale_pos_weight=(y["train"] == 0).sum() / (y["train"] == 1).sum(),
                          random_state=seed, eval_metric="logloss", tree_method="hist", device="cpu")
    model.fit(x["train"], y["train"])
    p_val, p_test = model.predict_proba(x["val"])[:, 1], model.predict_proba(x["test"])[:, 1]
    threshold, met = select_threshold(y["val"], p_val, TARGET_RECALL)
    out = metrics_at_threshold(y["test"], p_test, threshold)
    rate, caught, total = headline_metric(splits["test"], (p_test >= threshold).astype(int))
    out.update(threshold=threshold, validation_floor_met=met, headline={"rate": rate, "caught": caught, "total": total})
    return out, p_test


def main() -> None:
    cache = ROOT / "ml_pipeline/data/processed/encounters_with_intent.parquet"
    if cache.exists() and "--rebuild" not in sys.argv:
        saved = pd.read_parquet(cache)
        print(f"encounters with intent from cache {cache.name} (rebuild verified when written)")
    else:
        saved = build(cache)
    seeds = [int(a) for a in sys.argv[1:] if a.isdigit()] or [RANDOM_SEED]
    run(saved, seeds)


def build(cache: Path) -> pd.DataFrame:
    intent = pd.read_parquet(ROOT / "ml_pipeline/data/adsblol/intent.parquet")
    intent = intent[intent["nav_altitude_mcp"].notna()].copy()
    intent["time"] = intent["time"].astype(np.int64)
    saved = pd.read_parquet(latest_dataset_path())
    rebuilt, captured, anchors = rebuild()
    verify_identical(rebuilt, saved)
    ia = np.array([c["index_a"] for c in captured]); ib = np.array([c["index_b"] for c in captured])
    a_alt = anchors["altitude_m"][ia] * FT; b_alt_real = anchors["altitude_m"][ib] * FT
    saved["a_sel_alt_delta_ft"] = dialled_delta(anchors["icao24"][ia], anchors["time"][ia], a_alt, intent)
    saved["b_sel_alt_delta_ft"] = dialled_delta(anchors["icao24"][ib], anchors["time"][ib], b_alt_real, intent)
    level_a = saved["a_altitude_ft"] + saved["a_sel_alt_delta_ft"]
    level_b = saved["b_altitude_ft"] + saved["b_sel_alt_delta_ft"]
    saved["sel_level_separation_ft"] = (level_a - level_b).abs()
    saved.to_parquet(cache)
    return saved


def run(saved: pd.DataFrame, seeds: list[int]) -> None:
    coverage = {c: float(saved[c].notna().mean()) for c in INTENT_COLUMNS}
    print(f"coverage over 40,000 encounters: {coverage}")
    splits = split_by_session(saved)
    per_seed = {}
    for seed in seeds:
        per_seed[seed] = one_seed(splits, seed)
    result = {"coverage": coverage, "seeds": seeds, "per_seed": per_seed}
    if len(seeds) > 1:
        keys = ("recall", "precision", "false_alarms_per_1000")
        result["summary"] = {m: {k: {"mean": float(np.mean([per_seed[s][m][k] for s in seeds])),
                                     "min": float(np.min([per_seed[s][m][k] for s in seeds])),
                                     "max": float(np.max([per_seed[s][m][k] for s in seeds]))} for k in keys}
                             for m in ("baseline_retrained", "plus_intent")}
        result["summary"]["lost_real_per_seed"] = [per_seed[s]["real_conflicts_lost_vs_baseline"] for s in seeds]
        result["summary"]["gained_real_per_seed"] = [per_seed[s]["real_conflicts_gained_vs_baseline"] for s in seeds]
        result["summary"]["headline_caught"] = {m: [per_seed[s][m]["headline"]["caught"] for s in seeds]
                                                for m in ("baseline_retrained", "plus_intent")}
        print(json.dumps(result["summary"], indent=1))
    out = ROOT / "ml_pipeline/reports" / f"classifier_intent_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, indent=2, default=float))
    print(f"wrote {out.relative_to(ROOT)}")


def one_seed(splits: dict, seed: int) -> dict:
    base, p_base = train_and_score(splits, FEATURE_COLUMNS, seed)
    plus, p_plus = train_and_score(splits, FEATURE_COLUMNS + INTENT_COLUMNS, seed)
    y_test = splits["test"]["is_conflict"].astype(int).to_numpy()

    # Same false-alarm cost: the +intent model at the baseline's alarm rate.
    target_fa = base["false_alarms_per_1000"]
    matched = None
    for value in np.unique(np.round(p_plus, 6)):
        candidate = metrics_at_threshold(y_test, p_plus, float(value))
        if candidate["false_alarms_per_1000"] <= target_fa:
            matched = candidate
            rate, caught, total = headline_metric(splits["test"], (p_plus >= value).astype(int))
            matched["headline"] = {"rate": rate, "caught": caught, "total": total}
            break
    # Where do the removed false alarms come from? The stacked-vertically mode.
    stacked = (splits["test"]["predicted_cpa_lateral_nm"] < 8) & (splits["test"]["predicted_cpa_vertical_ft"] >= 1000)
    fa_base = (p_base >= base["threshold"]) & (y_test == 0)
    fa_plus = (p_plus >= plus["threshold"]) & (y_test == 0)
    result = {"baseline_retrained": base, "plus_intent": plus,
              "plus_intent_at_baseline_false_alarm_rate": matched,
              "false_alarms_in_stacked_mode": {"baseline": int((fa_base & stacked).sum()), "plus_intent": int((fa_plus & stacked).sum())},
              "real_conflicts_lost_vs_baseline": int(((p_base >= base["threshold"]) & ~(p_plus >= plus["threshold"]) & (y_test == 1)).sum()),
              "real_conflicts_gained_vs_baseline": int((~(p_base >= base["threshold"]) & (p_plus >= plus["threshold"]) & (y_test == 1)).sum())}
    for name in ("baseline_retrained", "plus_intent"):
        b = result[name]
        print(f"{name:<20} recall {b['recall']:.4f}  precision {b['precision']:.4f}  FA/1000 {b['false_alarms_per_1000']:.1f}  "
              f"headline {b['headline']['caught']}/{b['headline']['total']}  threshold {b['threshold']:.4f}")
    if matched:
        print(f"{'+intent @ base FA':<20} recall {matched['recall']:.4f}  FA/1000 {matched['false_alarms_per_1000']:.1f}  "
              f"headline {matched['headline']['caught']}/{matched['headline']['total']}")
    print(f"seed {seed}:", json.dumps({k: result[k] for k in ("false_alarms_in_stacked_mode", "real_conflicts_lost_vs_baseline",
                                                             "real_conflicts_gained_vs_baseline")}))
    return result


if __name__ == "__main__":
    main()
