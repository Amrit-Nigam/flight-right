"""Plan 3.2, second half: what the controller is SHOWN, judged on labelled pairs.

    python ml_pipeline/utils/alert_prominence.py

Detection is settled (offsets_ab_test.py): with the safety net on the straight line, the
multi-path model no longer decides WHICH pairs are alerted. It still decides two things
the controller experiences directly:

  1. Tier. A pair outside the straight-line tier 1 becomes an AUDIBLE tier 1 alarm (with
     manoeuvres) if the WORST of its 25 path combinations closes inside 180 s -- however
     unlikely that combination is. That is worst-case propagation, which Kuchar & Yang
     (2000) identify as the source of "a high false alarm rate" when the manoeuvres it
     protects against are unlikely.
  2. Prominence. The alert feed collapses a tier 2 row into a counted group when the
     classifier's raw score is under 0.25, whatever the path model thinks.

This script records, for every validation and test pair, what the served system decides
and every probability both models give, so a likelihood-based rule for each can be CHOSEN
ON VALIDATION and CONFIRMED ONCE ON TEST. It writes
ml_pipeline/data/processed/alert_prominence_<split>.parquet and changes nothing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/utils"))

from offsets_ab_test import SAVED, breach, decide, gen, inputs  # noqa: E402
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    TIER_1_MAX_SECONDS, classify_conflict, compute_cpa_from_paths)

OUT = ROOT / "ml_pipeline/data/processed"


def table(split: str, model_path: Path | None = None, tag: str = "",
          callsigns: list | None = None) -> pd.DataFrame:
    """callsigns: one per row of X (A rows then B rows), for a model that uses destination inputs."""
    import xgboost
    from server.app.ml.inference import MultiPathPredictor

    frame, X, current = inputs(split)
    n = len(frame)
    card = json.loads((SAVED / "xgboost_conflict_model_card.json").read_text())
    booster = xgboost.Booster()
    booster.load_model(str(SAVED / "xgboost_conflict.json"))
    from train_xgboost import classifier_raw_scores
    raw = classifier_raw_scores(booster, frame)      # the inputs the saved file declares
    predictor = (MultiPathPredictor(offsets="per_mode") if model_path is None
                 else MultiPathPredictor(model_path, offsets="per_mode"))
    extra = predictor.route_inputs(X, callsigns if callsigns is not None else [None] * len(X))
    probabilities, positions, _ = predictor.predict(X, extra=extra)

    rows = []
    for i in range(n):
        rule = {"cpa_lateral_distance_nm": float(frame["predicted_cpa_lateral_nm"].iloc[i]),
                "cpa_vertical_separation_ft": float(frame["predicted_cpa_vertical_ft"].iloc[i]),
                "time_to_cpa_seconds": float(frame["predicted_time_to_cpa_seconds"].iloc[i]),
                "is_converging": True}
        mp = compute_cpa_from_paths(predictor.paths_for_cpa(X, i, probabilities, positions),
                                    predictor.paths_for_cpa(X, n + i, probabilities, positions),
                                    tuple(current[i]), tuple(current[n + i]))
        combos = mp["combinations"]
        alert = bool(raw[i] >= card["decision_threshold"])
        fired, tier, route = decide("rule_only", rule, combos, probabilities[i], probabilities[n + i], alert)
        rule_class = classify_conflict(rule)
        w = np.array([c["joint_probability"] for c in combos])
        av = np.array([c["breaches_alert_volume"] for c in combos])
        soon = np.array([c["cpa"]["time_to_cpa_seconds"] <= TIER_1_MAX_SECONDS for c in combos])
        legal = np.array([breach(c["cpa"]) for c in combos])
        rows.append({
            "y": int(frame["is_conflict"].iloc[i]),
            "in_time": bool(frame["actual_time_to_cpa_seconds"].iloc[i] >= 180),
            "fired": fired, "tier": tier, "route": route,
            "rule_tier1": rule["time_to_cpa_seconds"] <= TIER_1_MAX_SECONDS,
            "rule_is_conflict": bool(rule_class["is_conflict"]), "severity": str(rule_class["severity"]),
            "classifier_raw": float(raw[i]), "classifier_alert": alert,
            "mp_p_alert_volume": float(w[av].sum()),
            "mp_p_legal_minimum": float(w[legal].sum()),
            "mp_p_alert_volume_within_180s": float(w[av & soon].sum()),
            "mp_worst_time_s": float(mp["time_to_cpa_seconds"]),
        })
    out = pd.DataFrame(rows)
    suffix = f"_{tag}" if tag else ""
    out.to_parquet(OUT / f"alert_prominence_{split}{suffix}.parquet")
    print(f"{split}: {n:,} pairs, {int(out['y'].sum())} real, {int(out['fired'].sum())} alerted "
          f"-> {OUT.name}/alert_prominence_{split}{suffix}.parquet")
    return out


SEVERITY = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def tier_breaching_only(t: pd.DataFrame) -> pd.Series:
    """Change A: a model path may raise a pair to tier 1 only if it actually CONFLICTS.

    Served before: outside the straight-line tier 1, the tier came from the multi-path
    representative, which is the likeliest combination when NO combination breaches the
    alert volume -- so a pair whose model paths all stay clear was still promoted to an
    audible alarm if that clear path's closest point fell inside 180 s. Now: with no
    breaching combination, the straight line sets the tier. No threshold is involved.
    """
    promoted = (t["tier"] == 1) & ~t["rule_tier1"]
    return t["tier"].where(~(promoted & (t["mp_p_alert_volume"] == 0.0)), 2)


def collapsed(t: pd.DataFrame, raw_below: float, mp_below: float | None) -> pd.Series:
    """The alert feed's collapse rule on this table; mp_below=None is the served rule."""
    rule = (t["fired"] & (t["tier"] == 2) & ~t["rule_is_conflict"]
            & (t["severity"].map(SEVERITY) < SEVERITY["high"]) & (t["classifier_raw"] < raw_below))
    return rule if mp_below is None else rule & (t["mp_p_alert_volume"] < mp_below)


def report(t: pd.DataFrame, name: str) -> dict:
    y, fired = t["y"] == 1, t["fired"]
    out = {"split": name}
    tier_a = tier_breaching_only(t)
    for label, tier in (("served", t["tier"]), ("A", tier_a)):
        out[f"tier1_real_{label}"] = int((fired & (tier == 1) & y).sum())
        out[f"tier1_false_{label}"] = int((fired & (tier == 1) & ~y).sum())
    demoted = fired & (t["tier"] == 1) & (tier_a == 2)
    out["A_demoted_real"], out["A_demoted_false"] = int((demoted & y).sum()), int((demoted & ~y).sum())
    # B1 is judged on the SERVED tiers: A was rejected on test (it demotes a real conflict).
    for label, mp_below in (("served", None), ("B1", 0.10)):
        c = collapsed(t, 0.25, mp_below)
        out[f"collapsed_real_{label}"] = int((c & y).sum())
        out[f"collapsed_false_{label}"] = int((c & ~y).sum())
        out[f"prominent_false_{label}"] = int((fired & ~c & ~y).sum())
        out[f"prominent_real_with_3min_{label}"] = int((fired & ~c & y & t["in_time"]).sum())
    return out


def main() -> None:
    tables = {}
    for split in ("val", "test"):
        path = OUT / f"alert_prominence_{split}.parquet"
        tables[split] = pd.read_parquet(path) if path.exists() else table(split)
    results = [report(tables[s], s) for s in ("val", "test")]
    frame = pd.DataFrame(results).set_index("split").T
    print(frame.to_string())
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    path = ROOT / "ml_pipeline/reports" / f"alert_prominence_{stamp}.json"
    path.write_text(json.dumps(results, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")


def summary(t: pd.DataFrame) -> dict:
    """What the controller experiences under one multi-path model, served display rules."""
    y, fired = t["y"] == 1, t["fired"]
    c = collapsed(t, 0.25, None)
    return {"alerts": int(fired.sum()), "real_alerted": int((fired & y).sum()),
            "tier1_real": int((fired & (t["tier"] == 1) & y).sum()),
            "tier1_false": int((fired & (t["tier"] == 1) & ~y).sum()),
            "collapsed_real": int((c & y).sum()), "collapsed_false": int((c & ~y).sum()),
            "prominent_false": int((fired & ~c & ~y).sum()),
            "prominent_real_with_3min": int((fired & ~c & y & t["in_time"]).sum())}


def compare(candidates: list[tuple[str, Path]]) -> None:
    """Served per_mode model vs each candidate pickle, on val and test."""
    results = {}
    for split in ("val", "test"):
        served = OUT / f"alert_prominence_{split}.parquet"
        results[(split, "served")] = summary(pd.read_parquet(served) if served.exists() else table(split))
        for tag, path in candidates:
            results[(split, tag)] = summary(table(split, path, tag))
    frame = pd.DataFrame(results)
    print(frame.to_string())
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%d_%H%M%S")
    out = ROOT / "ml_pipeline/reports" / f"alert_prominence_compare_{stamp}.json"
    out.write_text(json.dumps({f"{s}/{t}": v for (s, t), v in results.items()}, indent=2))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    # python alert_prominence.py                    -> the 3.2 tier / collapse study
    # python alert_prominence.py tag=model.pkl ...  -> served model vs candidate pickles
    if len(sys.argv) > 1:
        compare([(arg.split("=", 1)[0], Path(arg.split("=", 1)[1])) for arg in sys.argv[1:]])
    else:
        main()
