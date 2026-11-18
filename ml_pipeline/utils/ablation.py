"""Plan Phase 8.1-8.2: the ablation table and its variance, generated, never typed.

    python ml_pipeline/utils/ablation.py

Every row is recomputed from a saved artifact on the SAME held-out test split, one change
at a time, and a change that did not help stays in the table (plan 8.1). Columns are the
ten-minute horizon, arrivals (<40 NM from VABB, the "terminal" regime) and all traffic:
within 5 NM horizontally, and within 5 NM AND 1,000 ft (a conflict needs both; measured
from 25 Sep 2026, see multipath_3d_eval.py). Top-1 is the single likeliest path; best-of-5
is COVERAGE -- "one of five candidate paths was close" -- never accuracy (plan rule 6).

Rows
  constant velocity ............ the baseline every row is printed beside (Part 3 rule 4)
  single-answer LSTM ........... server/app/ml/saved_models/trajectory_residual.pt
  tree reference ............... reference_benchmark.py's saved test predictions
  multi-path, pattern table .... served until 24 Sep 2026
  + per-mode offsets ........... served since 24 Sep 2026
  + candidate pruning (90% mass)  plan 3.2; measured, not adopted
  + more data (archive) ........ seed-42 archive pickle; measured, not adopted
  + heard clearance (ORACLE) ... level cap + heading filter, UPPER BOUND, perfect recognition,
                                 on the windows with a 5- and 10-minute truth

Variance (8.2) comes from the saved seed reports, with a 95% t-interval (n = 4). The
conflict headline's interval is a Wilson score interval on the count it is made of.

Writes docs/ablation.json and docs/ablation.md (the markdown is generated from the JSON).
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
sys.path.insert(0, str(ROOT / "ml_pipeline/utils"))

import evaluate  # noqa: E402
import framing  # noqa: E402
import multipath as mp  # noqa: E402

PROCESSED = ROOT / "ml_pipeline/data/processed"
REPORTS = ROOT / "ml_pipeline/reports"
FT = 3.28084
T_95_DF3 = 3.182  # two-sided 95% Student t, 3 degrees of freedom (n = 4 seeds)


def ten_minute_scores(positions: np.ndarray, X, y, mask, rows: np.ndarray) -> dict:
    """positions (N, K, 4, 3); K = 1 for single answers. Scored at ten minutes on `rows`."""
    lat = np.stack([framing.error_nm(positions[:, k], y) for k in range(positions.shape[1])], 1)[:, :, 3]
    ver = np.abs(positions[:, :, 3, 2] - y[:, None, 3, 2]) * FT
    groups = {"arrivals": mp.arrival_rows(X), "all": np.ones(len(X), bool)}
    out = {}
    for name, sel in groups.items():
        r = rows & sel
        both = (lat[r] < 5) & (ver[r] < 1000)
        out[name] = {"n": int(r.sum()),
                     "top1_5nm": float((lat[r, 0] < 5).mean() * 100),
                     "top1_both": float(both[:, 0].mean() * 100)}
        if positions.shape[1] > 1:
            k = min(5, positions.shape[1])
            out[name]["best5_5nm"] = float((lat[r, :k] < 5).any(1).mean() * 100)
            out[name]["best5_both"] = float(both[:, :k].any(1).mean() * 100)
    return out


def per_regime(positions: np.ndarray, X, y, rows: np.ndarray) -> dict:
    """Ten-minute top-1 (and best-of-5) within 5 NM in every evaluate.py regime bucket."""
    lat = np.stack([framing.error_nm(positions[:, k], y) for k in range(positions.shape[1])], 1)[:, :, 3]
    out = {}
    for family, (values, buckets) in evaluate.bucket_assignments(X).items():
        for name, low, high in buckets:
            r = rows & (values >= low) & (values < high)
            cell = {"n": int(r.sum()), "top1_5nm": float((lat[r, 0] < 5).mean() * 100) if r.any() else None}
            if positions.shape[1] > 1 and r.any():
                cell["best5_5nm"] = float((lat[r, :5] < 5).any(1).mean() * 100)
            out[f"{family}: {name}"] = cell
    return out


def prune_mass(probabilities: np.ndarray, positions: np.ndarray, mass: float = 0.90) -> np.ndarray:
    """Plan 3.2 pruning: keep each aircraft's likeliest paths up to `mass`; drop the rest
    by replacing them with the likeliest path (so best-of-K cannot count them)."""
    pruned = positions.copy()
    keep = (np.cumsum(probabilities, 1) - probabilities) < mass
    for k in range(positions.shape[1]):
        pruned[~keep[:, k], k] = positions[~keep[:, k], 0]
    return pruned


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round((centre - half) * 100, 2), round((centre + half) * 100, 2)]


def seed_stats(report_glob: str) -> dict:
    paths = sorted(REPORTS.glob(report_glob))
    if not paths:
        return {}
    runs = json.loads(paths[-1].read_text())["runs"]
    cells = {"per_mode_best5_arrivals": [r["best_of_k"]["per_mode"]["5"]["arrivals"] for r in runs.values()],
             "per_mode_top1_arrivals": [r["best_of_k"]["per_mode"]["1"]["arrivals"] for r in runs.values()],
             "table_best5_arrivals": [r["best_of_k"]["table"]["5"]["arrivals"] for r in runs.values()],
             "table_top1_arrivals": [r["best_of_k"]["table"]["1"]["arrivals"] for r in runs.values()]}
    out = {"source": paths[-1].name, "seeds": list(runs)}
    for key, values in cells.items():
        v = np.array(values, float)
        sd = float(v.std(ddof=1))
        half = T_95_DF3 * sd / math.sqrt(len(v))
        out[key] = {"mean": float(v.mean()), "sd": sd, "min": float(v.min()), "max": float(v.max()),
                    "ci95": [float(v.mean() - half), float(v.mean() + half)], "n": len(v)}
    return out


def main() -> None:
    from server.app.ml.inference import MULTIPATH_PATH, MultiPathPredictor, TrajectoryPredictor
    from oracle_clearance import oracle_clearances
    from ml_pipeline.utils.clearance import apply_clearance

    data = np.load(PROCESSED / "trajectory_test.npz")
    X, y, mask = data["X"].astype(np.float32), data["y"].astype(np.float32), data["mask"].astype(bool)
    rows10 = mask[:, 3]
    cv = framing.constant_velocity_predict(X)[:, None]
    lstm = TrajectoryPredictor().predict(X)[0][:, None]
    tree = np.load(PROCESSED / "tree_reference_test_predictions.npy")[:, None]
    # Each historical row is scored from the pickle that was served at the time, so a row's label
    # stays true after the served file changes (it changed on 24, 26 and 27 Sep).
    saved = MULTIPATH_PATH.parent
    per_mode_2309 = saved / "trajectory_multipath_20260923_per_mode_backup.pkl"   # served 24-26 Sep
    archive_2609 = saved / "trajectory_multipath_20260926_archive_backup.pkl"      # served 26-27 Sep
    early = per_mode_2309 if per_mode_2309.exists() else MULTIPATH_PATH
    _, table_positions, _ = MultiPathPredictor(early, offsets="table").predict(X)
    probabilities_2309, positions_2309, _ = MultiPathPredictor(early, offsets="per_mode").predict(X)
    served = MultiPathPredictor(MULTIPATH_PATH, offsets="per_mode")
    probabilities, positions, _ = served.predict(X, extra=served.saved_split_inputs("test"))

    rows = [("constant velocity", cv, "baseline"),
            ("single-answer LSTM", lstm, "not served as a candidate source; the tree beats it"),
            ("tree reference (single answer)", tree, "reference only"),
            ("multi-path, pattern table", table_positions, "served until 24 Sep 2026"),
            ("+ per-mode offsets", positions_2309, "served 24-26 Sep 2026"),
            ("+ candidate pruning (90% mass)", prune_mass(probabilities_2309, positions_2309),
             "measured, not adopted (plan 3.2)")]
    if archive_2609.exists():
        rows.append(("+ more data (OpenSky archive)", MultiPathPredictor(archive_2609, offsets="per_mode").predict(X)[1],
                     "served 26-27 Sep 2026 (Archit accepted one real tier 1 alarm lost on validation)"))
    if served.extra_features:
        rows.append(("+ destination (adsbdb route)", positions, "SERVED since 27 Sep 2026 (all 11 pre-set checks passed)"))
    result = {"generated_utc": datetime.now(timezone.utc).isoformat(), "test_windows": int(len(X)), "rows": []}
    for name, pos, note in rows:
        result["rows"].append({"name": name, "note": note, "ten_minutes": ten_minute_scores(pos, X, y, mask, rows10),
                               "per_regime": per_regime(pos, X, y, rows10)})

    # The oracle row: level cap + heading filter on the served per-mode fan, UPPER BOUND.
    oracle_rows = np.flatnonzero(mask[:, 2] & mask[:, 3])
    subset = np.zeros(len(X), bool); subset[oracle_rows] = True
    oracle_positions = positions.copy()
    for i in oracle_rows:
        p, pos = probabilities[i], positions[i]
        kept_order = np.arange(len(p))
        for kind in ("turn", "level"):
            clearance = oracle_clearances(X, y, i)[kind]
            if clearance is not None:
                p, pos, kept, _ = apply_clearance(p, pos, float(X[i, -1, framing.ALTITUDE]), clearance)
        order = np.argsort(-p)
        filled = np.repeat(pos[order][:1], positions.shape[1], 0)
        filled[:len(order)] = pos[order]
        oracle_positions[i] = filled
    result["oracle"] = {"name": "+ heard clearance (ORACLE: level cap + heading filter)",
                        "label": "UPPER BOUND, assuming perfect clearance recognition",
                        "windows": "test windows with a 5- and 10-minute truth",
                        "baseline_same_windows": ten_minute_scores(positions, X, y, mask, subset),
                        "with_oracle": ten_minute_scores(oracle_positions, X, y, mask, subset)}

    result["variance"] = {"served_per_mode_and_table": seed_stats("multipath_seeds_*.json"),
                          "archive": seed_stats("multipath_archive_seeds_*.json")}
    # Both counts are READ from files (plan rule 8), never typed.
    classifier = json.loads((ROOT / "docs/metrics.json").read_text())["model2"]["headline_three_minute_warning"]["xgboost"]
    ab = json.loads(sorted(REPORTS.glob("offsets_ab_*.json"))[-1].read_text())
    served = ab["results"]["per_mode rule_only"]["headline"]
    result["headline_intervals"] = {
        "classifier_alone_94_0": {"caught": classifier["caught"], "total": classifier["total"],
                                  "wilson95": wilson(classifier["caught"], classifier["total"]),
                                  "source": "docs/metrics.json model2.headline_three_minute_warning.xgboost"},
        "running_system_94_7": {"caught": served["caught"], "total": served["total"],
                                "wilson95": wilson(served["caught"], served["total"]),
                                "source": f"{sorted(REPORTS.glob('offsets_ab_*.json'))[-1].name}, per_mode rule_only"}}
    # Plan 9.x rows, read from their own reports (never typed).
    # Each run adds rows (25 Sep: intent/wind/type/traffic/all; 26 Sep: route, route + intent), so
    # merge every report, a newer one overriding a row both contain.
    ctx = sorted(REPORTS.glob("context_ablation_*.json"))
    if ctx:
        merged: dict = {}
        for report in ctx:
            merged.update(json.loads(report.read_text()))
        result["context_rows"] = {"source": ", ".join(f"`ml_pipeline/reports/{r.name}`" for r in ctx), **merged}
    clf = sorted(REPORTS.glob("classifier_intent_2*.json"))   # the 25 Sep ablation, not the 26 Sep *_seeds_* check
    if clf:
        result["classifier_intent"] = {"source": clf[-1].name, **json.loads(clf[-1].read_text())}

    (ROOT / "docs/ablation.json").write_text(json.dumps(result, indent=2))
    (ROOT / "docs/ablation.md").write_text(render(result), encoding="utf-8")
    print(render(result))
    print("wrote docs/ablation.json and docs/ablation.md")


def _f(x) -> str:
    return "—" if x is None else f"{x:.1f}%"


def render(r: dict) -> str:
    lines = ["# Ablation table (generated)", "",
             f"Generated by `ml_pipeline/utils/ablation.py` from saved artifacts, {r['generated_utc'][:10]}. "
             "Do not edit by hand; re-run the script.", "",
             "Ten minutes ahead, held-out test split. **Top-1** = the single likeliest path. "
             "**Best-of-5** = one of five candidate paths was close (coverage, not accuracy). "
             "**3-D** = within 5 NM *and* 1,000 ft, which is what a conflict needs.", "",
             "| Configuration | Arrivals top-1 | Arrivals best-of-5 | Arrivals top-1 3-D | Arrivals best-of-5 3-D | All top-1 | All best-of-5 | Status |",
             "|---|---|---|---|---|---|---|---|"]
    for row in r["rows"]:
        a, al = row["ten_minutes"]["arrivals"], row["ten_minutes"]["all"]
        lines.append(f"| {row['name']} | {_f(a['top1_5nm'])} | {_f(a.get('best5_5nm'))} | {_f(a['top1_both'])} | "
                     f"{_f(a.get('best5_both'))} | {_f(al['top1_5nm'])} | {_f(al.get('best5_5nm'))} | {row['note']} |")
    o = r["oracle"]
    for label, block in (("per-mode, same windows", o["baseline_same_windows"]), (o["name"], o["with_oracle"])):
        a, al = block["arrivals"], block["all"]
        lines.append(f"| {label} | {_f(a['top1_5nm'])} | {_f(a.get('best5_5nm'))} | {_f(a['top1_both'])} | "
                     f"{_f(a.get('best5_both'))} | {_f(al['top1_5nm'])} | {_f(al.get('best5_5nm'))} | "
                     f"{'**' + o['label'] + '**' if label == o['name'] else 'comparison for the oracle row'} |")
    lines += ["", f"Arrivals n = {r['rows'][0]['ten_minutes']['arrivals']['n']:,}, all n = "
              f"{r['rows'][0]['ten_minutes']['all']['n']:,}. The oracle rows use the {o['windows']} "
              f"(arrivals n = {o['with_oracle']['arrivals']['n']:,}).", "",
              "## Per regime — ten-minute top-1 within 5 NM (best-of-5 in brackets)", ""]
    regimes = list(r["rows"][0]["per_regime"])
    lines.append("| Configuration | " + " | ".join(regimes) + " |")
    lines.append("|---" * (len(regimes) + 1) + "|")
    for row in r["rows"]:
        cells = []
        for k in regimes:
            c = row["per_regime"][k]
            cells.append(_f(c["top1_5nm"]) + (f" ({c['best5_5nm']:.1f}%)" if c.get("best5_5nm") is not None else ""))
        lines.append(f"| {row['name']} | " + " | ".join(cells) + " |")
    lines.append("| n | " + " | ".join(f"{r['rows'][0]['per_regime'][k]['n']:,}" for k in regimes) + " |")
    lines += ["", "## Variance across four seeds (arrivals, ten minutes, within 5 NM)", "",
              "| | mean | sd | range | 95% CI (t, n = 4) |", "|---|---|---|---|---|"]
    for group, stats in r["variance"].items():
        for key, s in stats.items():
            if isinstance(s, dict) and "mean" in s:
                lines.append(f"| {group}: {key} | {s['mean']:.1f}% | {s['sd']:.2f} | {s['min']:.1f}–{s['max']:.1f} | "
                             f"{s['ci95'][0]:.1f}–{s['ci95'][1]:.1f} |")
    if "context_rows" in r:
        c = r["context_rows"]
        lines += ["", "## Plan 9: context features for the offset regressors (seed 42, one change at a time)", "",
                  f"Sources: {c['source']}. Standard split (no archive data), so `none` is the 24-26 Sep model. "
                  "Features reach the offset regressors only, so candidate shapes and probabilities are identical "
                  "in every row. `route` = destination; the served model carries it on archive data (table above).", "",
                  "| Row | Arrivals best-of-5 | Arrivals top-1 | Arrivals best-of-5 3-D | Arrivals top-1 3-D | All: top-1 height error |",
                  "|---|---|---|---|---|---|"]
        for name in ("none", "intent", "wind", "type", "traffic", "all", "route", "route_intent"):
            if name in c:
                x = c[name]
                lines.append(f"| {name} | {x['arrivals_best5_5nm']:.1f}% | {x['arrivals_top1_5nm']:.1f}% | "
                             f"{x['three_d']['arrivals']['best5_both']:.1f}% | {x['three_d']['arrivals']['top1_both']:.1f}% | "
                             f"{x['three_d']['all']['top1_altitude_mean_ft']:.0f} ft |")
        cap = c.get("selected_level_cap")
        if cap:
            s0, s1 = cap["served"]["all"], cap["served + selected-level cap"]["all"]
            lines += ["", f"**Capping at the broadcast selected level (STCA Option E, no training):** top-1 height "
                      f"error {s0['top1_altitude_mean_ft']:.0f} ft -> {s1['top1_altitude_mean_ft']:.0f} ft; all-traffic "
                      f"3-D best-of-5 {s0['best5_both']:.1f}% -> {s1['best5_both']:.1f}%. Worse at ten minutes: the "
                      "dialled level is usually a step in a sequence of clearances (see the Section 14 log, 25 Sep)."]
    if "classifier_intent" in r:
        ci = r["classifier_intent"]
        lines += ["", "## Plan 9.0 on the conflict classifier: the dialled level as an input", "",
                  f"Source: `ml_pipeline/reports/{ci['source']}`. Thresholds chosen on validation at the 0.95 "
                  "recall floor and scored once on test; the baseline is retrained with identical settings and seed.", "",
                  "| Seed | Baseline recall / FA per 1,000 / caught ≥3 min | + dialled level | Real lost / gained | + dialled level at the baseline's FA rate: recall |",
                  "|---|---|---|---|---|"]
        for seed, run in ci.get("per_seed", {}).items():
            b0, b1, m = run["baseline_retrained"], run["plus_intent"], run.get("plus_intent_at_baseline_false_alarm_rate") or {}
            lines.append(f"| {seed} | {b0['recall']:.4f} / {b0['false_alarms_per_1000']:.1f} / {b0['headline']['caught']} | "
                         f"{b1['recall']:.4f} / {b1['false_alarms_per_1000']:.1f} / {b1['headline']['caught']} | "
                         f"{run['real_conflicts_lost_vs_baseline']} / {run['real_conflicts_gained_vs_baseline']} | "
                         f"{m.get('recall', float('nan')):.4f} |")
    h = r["headline_intervals"]
    lines += ["", "## Headline intervals (Wilson 95%)", "",
              f"* Classifier alone: {h['classifier_alone_94_0']['caught']} of {h['classifier_alone_94_0']['total']} "
              f"caught with ≥3 min warning; 95% interval {h['classifier_alone_94_0']['wilson95'][0]}–"
              f"{h['classifier_alone_94_0']['wilson95'][1]}%.",
              f"* Running system: {h['running_system_94_7']['caught']} of {h['running_system_94_7']['total']}; "
              f"95% interval {h['running_system_94_7']['wilson95'][0]}–{h['running_system_94_7']['wilson95'][1]}%.",
              "", f"The two intervals overlap almost entirely: on {h['classifier_alone_94_0']['total']} conflicts, a "
              f"{abs(h['running_system_94_7']['caught'] - h['classifier_alone_94_0']['caught'])}-conflict difference is "
              "not statistically distinguishable. Report both figures, never as a significant gain."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
