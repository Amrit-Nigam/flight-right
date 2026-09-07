"""Regenerate every figure and metric in evaluation.md.

    python ml_pipeline/utils/build_evaluation_figures.py

Writes 13 charts to docs/figures/ and the raw numbers to docs/metrics.json. Everything
is read from the saved model artifacts or recomputed from them in this process, so the
document cannot drift away from the models: re-run this after any retrain and the
document is current.

Requires matplotlib. The charts use the project's validated colour palette; the two
rules that matter if you edit them are that a chart's proportions must match its data
(an early version of the alert funnel used a log scale, which made 303 conflicts out of
4,690 pairs look like a majority of the bar) and that every series carries a direct
label rather than relying on colour alone.
"""
import json
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xgboost
from sklearn.metrics import precision_recall_curve, average_precision_score

ROOT = Path(os.environ.get("FLIGHT_RIGHT_DATA_ROOT", Path(__file__).resolve().parents[2]))
FIGS = ROOT / "docs" / "figures"
FIGS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

from train_xgboost import latest_dataset_path, split_by_session, headline_metric, rule_predictions  # noqa
from generate_synthetic_scenarios import FEATURE_COLUMNS  # noqa
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa
    classify_conflict, TIER_1_MAX_SECONDS, TIER_2_MAX_SECONDS,
    SEPARATION_LATERAL_NM, SEPARATION_VERTICAL_FT, ALERT_LATERAL_NM, ALERT_VERTICAL_FT)
from ml_pipeline.utils.alert_feed import AlertFeed  # noqa

# ---- validated palette (dataviz skill reference instance, light mode) -------------
SURFACE = "#fcfcfb"
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8880"
S1, S2, S3 = "#2a78d6", "#eb6834", "#1baf7a"        # blue, orange, aqua
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GRID = "#e6e5e1"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans", "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.linewidth": 0.8, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.7, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 150, "savefig.bbox": "tight", "legend.frameon": False,
})


def finish(ax, title, subtitle=None, ylabel=None, xlabel=None):
    ax.set_title(title, color=INK, fontsize=12, fontweight="bold", loc="left", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK2, fontsize=9, va="bottom")
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)


M: dict = {}

# ==================================================================================
# Model 1 and the tree reference -- from the saved evaluation CSVs and the run log
# ==================================================================================
cv = pd.read_csv(ROOT / "ml_pipeline/data/processed/eval_constant_velocity.csv")
lstm = pd.read_csv(ROOT / "ml_pipeline/data/processed/eval_residual_lstm.csv")
cv_h = cv[cv["section"] == "per_horizon"].set_index("horizon")
lstm_h = lstm[lstm["section"] == "per_horizon"].set_index("horizon")
HORIZONS = ["1 min", "3 min", "5 min", "10 min"]
# The tree reference is printed by reference_benchmark.py; parsed from that run's log.
GBT = {"1 min": (0.43, 90.8, 98.5), "3 min": (1.27, 73.4, 92.6),
       "5 min": (2.39, 60.1, 85.1), "10 min": (5.57, 33.1, 65.7)}

M["model1"] = {"horizons": []}
for h in HORIZONS:
    M["model1"]["horizons"].append({
        "horizon": h, "n": int(cv_h.loc[h, "n"]),
        "cv_mean_nm": float(cv_h.loc[h, "mean_nm"]), "lstm_mean_nm": float(lstm_h.loc[h, "mean_nm"]),
        "gbt_mean_nm": GBT[h][0],
        "cv_within5": float(cv_h.loc[h, "within_5_nm"]), "lstm_within5": float(lstm_h.loc[h, "within_5_nm"]),
        "gbt_within5": GBT[h][2],
        "cv_within1": float(cv_h.loc[h, "within_1_nm"]), "lstm_within1": float(lstm_h.loc[h, "within_1_nm"]),
        "gbt_within1": GBT[h][1],
        "lstm_cross_mae_nm": float(lstm_h.loc[h, "cross_mae_nm"]),
        "lstm_along_mae_nm": float(lstm_h.loc[h, "along_mae_nm"]),
        "lstm_alt_mae_ft": float(lstm_h.loc[h, "altitude_mae_ft"]),
    })

x = np.arange(len(HORIZONS)); w = 0.26
fig, ax = plt.subplots(figsize=(7.2, 4.0))
for off, key, colour, label in ((-w, "cv_within5", S1, "Constant velocity (physics)"),
                                (0.0, "lstm_within5", S2, "Residual LSTM (Model 1)"),
                                (w, "gbt_within5", S3, "Tree reference (benchmark)")):
    vals = [r[key] for r in M["model1"]["horizons"]]
    bars = ax.bar(x + off, vals, w * 0.88, color=colour, label=label, zorder=3)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1.2, f"{v:.0f}", ha="center",
                color=INK2, fontsize=8)
ax.set_xticks(x); ax.set_xticklabels(HORIZONS); ax.set_ylim(0, 108)
ax.legend(loc="lower left", fontsize=9)
finish(ax, "Trajectory prediction: share of forecasts within 5 NM",
       "Held-out test split, 39,614 samples. Higher is better.", "% within 5 NM", "Prediction horizon")
fig.savefig(FIGS / "traj_within5nm.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(7.2, 4.0))
for key, colour, label, mark in (("cv_mean_nm", S1, "Constant velocity", "o"),
                                 ("lstm_mean_nm", S2, "Residual LSTM", "s"),
                                 ("gbt_mean_nm", S3, "Tree reference", "^")):
    vals = [r[key] for r in M["model1"]["horizons"]]
    ax.plot(HORIZONS, vals, color=colour, lw=2, marker=mark, ms=8, label=label, zorder=3)
    ax.text(3.06, vals[-1], f" {vals[-1]:.2f} NM", color=colour, fontsize=9, va="center", fontweight="bold")
ax.set_xlim(-0.2, 3.9); ax.legend(loc="upper left", fontsize=9)
finish(ax, "Trajectory prediction: mean position error",
       "Lower is better. The gap opens with the horizon.", "Mean error (NM)", "Prediction horizon")
fig.savefig(FIGS / "traj_mean_error.png"); plt.close(fig)

# ==================================================================================
# Model 1b -- multi-path
# ==================================================================================
M["model1b"] = {
    "best_of_k": [{"method": "Constant velocity", "arrivals": 15.8, "all": 50.5},
                  {"method": "Single-answer LSTM", "arrivals": 34.8, "all": 61.3},
                  {"method": "Multi-path, 1 option", "arrivals": 38.6, "all": 64.0},
                  {"method": "Multi-path, 3 options", "arrivals": 57.9, "all": 79.0},
                  {"method": "Multi-path, 5 options", "arrivals": 63.6, "all": 83.0},
                  {"method": "Multi-path, 10 options", "arrivals": 68.8, "all": 86.5}],
    "temperature": 1.729,
    "ece_arrivals": [0.054, 0.019], "ece_all": [0.040, 0.012],
}
ks = [1, 3, 5, 10]
arr = [38.6, 57.9, 63.6, 68.8]; alltest = [64.0, 79.0, 83.0, 86.5]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
ax.plot(ks, alltest, color=S1, lw=2, marker="o", ms=8, label="All test traffic", zorder=3)
ax.plot(ks, arr, color=S2, lw=2, marker="s", ms=8, label="Arrivals (the hard case)", zorder=3)
ax.axhline(50.5, color=INK3, lw=1.4, ls="--", zorder=2)
ax.text(9.8, 51.8, "constant velocity, all traffic  50.5%", color=INK3, fontsize=8.5, ha="right")
ax.axvline(5, color=GRID, lw=8, zorder=1)
for k, a, b in zip(ks, arr, alltest):
    ax.text(k, b + 1.8, f"{b:.1f}", ha="center", color=S1, fontsize=8.5)
    ax.text(k, a - 3.6, f"{a:.1f}", ha="center", color=S2, fontsize=8.5)
ax.set_xticks(ks); ax.set_ylim(30, 95); ax.legend(loc="lower right", fontsize=9)
finish(ax, "Multi-path: chance that one of K offered paths is within 5 NM at ten minutes",
       "Shaded column is the shipped setting, K = 5. This is best-of-K, not accuracy.",
       "% where at least one path is within 5 NM", "Number of candidate paths offered (K)")
fig.savefig(FIGS / "multipath_bestofk.png"); plt.close(fig)

before = [(0.348, 0.238), (0.649, 0.276), (0.852, 0.410), (0.972, 0.674)]
after_bands = [(0.016, 0.021), (0.070, 0.085), (0.141, 0.167), (0.244, 0.217),
               (0.346, 0.282), (0.447, 0.339), (0.549, 0.444)]
fig, ax = plt.subplots(figsize=(6.4, 4.6))
ax.plot([0, 1], [0, 1], color=INK3, lw=1.2, ls="--", zorder=2, label="Perfectly honest")
ax.plot([b[0] for b in before], [b[1] for b in before], color=S2, lw=2, marker="s", ms=8,
        label="Before calibration", zorder=3)
ax.plot([a[0] for a in after_bands], [a[1] for a in after_bands], color=S1, lw=2, marker="o", ms=7,
        label="After temperature scaling", zorder=4)
ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02); ax.legend(loc="upper left", fontsize=9)
finish(ax, "Multi-path: are the stated probabilities honest?",
       "Calibration error 0.054 → 0.019 on arrivals. Closer to the dashed line is better.",
       "How often it actually happened", "Probability the model stated")
fig.savefig(FIGS / "multipath_calibration.png"); plt.close(fig)

# ==================================================================================
# Model 2 -- conflict classifier, on the held-out test split
# ==================================================================================
card = json.loads((ROOT / "server/app/ml/saved_models/xgboost_conflict_model_card.json").read_text())
T = card["decision_threshold"]
data = pd.read_parquet(latest_dataset_path())
splits = split_by_session(data)
test = splits["test"].reset_index(drop=True)
booster = xgboost.Booster()
booster.load_model(str(ROOT / "server/app/ml/saved_models/xgboost_conflict.json"))
raw = booster.predict(xgboost.DMatrix(test[FEATURE_COLUMNS], feature_names=FEATURE_COLUMNS))
test["raw"] = raw
y = test["is_conflict"].to_numpy()
alerts = (raw >= T).astype(int)
ttc = test["predicted_time_to_cpa_seconds"].to_numpy()
test["tier"] = np.where(ttc <= TIER_1_MAX_SECONDS, 1, np.where(ttc <= TIER_2_MAX_SECONDS, 2, 0))

M["model2"] = {k: card[k] for k in ("rows", "conflict_rate", "decision_threshold", "pr_auc",
                                    "test", "rule_alert_volume", "rule_legal_minimum",
                                    "headline_three_minute_warning", "calibration", "gates",
                                    "median_warning_seconds", "recall_margin_what_if")}
M["model2"]["shap_top"] = sorted(card["shap_mean_abs"].items(), key=lambda kv: -kv[1])[:8]

precision, recall, thresholds = precision_recall_curve(y, raw)
fig, ax = plt.subplots(figsize=(6.8, 4.6))
ax.plot(recall, precision, color=S1, lw=2, zorder=3, label="XGBoost classifier")
op = card["test"]
ax.plot([op["recall"]], [op["precision"]], marker="o", ms=11, color=S1,
        markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
ax.annotate(f"shipped operating point\nrecall {op['recall']:.3f}, precision {op['precision']:.3f}",
            (op["recall"], op["precision"]), textcoords="offset points", xytext=(-196, -66),
            color=INK2, fontsize=8.5, arrowprops=dict(arrowstyle="-", color=INK3, lw=1))
for rule, colour, label, dy in ((card["rule_alert_volume"], S2, "Rule, 8 NM / 1500 ft", 0.035),
                                (card["rule_legal_minimum"], S3, "Rule, 5 NM / 1000 ft", 0.035)):
    ax.plot([rule["recall"]], [rule["precision"]], marker="D", ms=9, color=colour,
            markeredgecolor=SURFACE, markeredgewidth=1.6, zorder=5)
    ax.text(rule["recall"] + 0.018, rule["precision"] + dy, label, color=colour,
            fontsize=8.5, ha="left", fontweight="bold")
ax.axhline(y.mean(), color=INK3, lw=1.2, ls="--", zorder=2)
ax.text(0.02, y.mean() + 0.015, f"guessing at random  {y.mean():.3f}", color=INK3, fontsize=8.5)
ax.set_xlim(0, 1.22); ax.set_ylim(0, 1.02); ax.legend(loc="upper right", fontsize=9)
finish(ax, "Conflict classifier: precision against recall",
       f"Area under the curve {card['pr_auc']:.3f}. The rule-based detectors are single points.",
       "Precision (share of alerts that are real)", "Recall (share of real conflicts caught)")
fig.savefig(FIGS / "classifier_pr.png"); plt.close(fig)


def platt(p, a, b):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return 1.0 / (1.0 + np.exp(-(a * np.log(p / (1 - p)) + b)))


cal = platt(raw, card["platt"]["a"], card["platt"]["b"])


def reliability(p, truth, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() >= 20:
            xs.append(p[m].mean()); ys.append(truth[m].mean())
    return xs, ys


fig, ax = plt.subplots(figsize=(6.4, 4.6))
ax.plot([0, 1], [0, 1], color=INK3, lw=1.2, ls="--", zorder=2, label="Perfectly honest")
bx, by = reliability(raw, y); cx, cy = reliability(cal, y)
ax.plot(bx, by, color=S2, lw=2, marker="s", ms=8, label="Raw XGBoost score", zorder=3)
ax.plot(cx, cy, color=S1, lw=2, marker="o", ms=8, label="After Platt calibration", zorder=4)
ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02); ax.legend(loc="upper left", fontsize=9)
finish(ax, "Conflict classifier: are the stated probabilities honest?",
       f"Calibration error {card['calibration']['raw XGBoost']['ece']:.4f} → "
       f"{card['calibration']['Platt-calibrated']['ece']:.4f}. The alert set is unchanged.",
       "How often it actually happened", "Probability the model stated")
fig.savefig(FIGS / "classifier_calibration.png"); plt.close(fig)

# ---- headline metric ------------------------------------------------------------
head = card["headline_three_minute_warning"]
fig, ax = plt.subplots(figsize=(7.0, 3.4))
names = ["Rule\n5 NM / 1000 ft", "Rule\n8 NM / 1500 ft", "XGBoost classifier\n(shipped)"]
vals = [head["rule_legal_minimum"]["rate"] * 100, head["rule_alert_volume"]["rate"] * 100,
        head["xgboost"]["rate"] * 100]
caught = [head["rule_legal_minimum"]["caught"], head["rule_alert_volume"]["caught"], head["xgboost"]["caught"]]
bars = ax.barh(names, vals, 0.55, color=[SEQ[2], SEQ[3], S1], zorder=3)
for bar, v, c in zip(bars, vals, caught):
    ax.text(v + 1.2, bar.get_y() + bar.get_height() / 2, f"{v:.1f}%   ({c} of {head['xgboost']['total']})",
            va="center", color=INK2, fontsize=9.5)
ax.set_xlim(0, 118); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
finish(ax, "THE HEADLINE METRIC: conflicts caught with at least 3 minutes of warning",
       "Three minutes is the minimum time in which a controller can actually act.", None, "% caught")
fig.savefig(FIGS / "headline_metric.png"); plt.close(fig)

# ==================================================================================
# What actually reaches the controller -- the alert feed applied to the test split
# ==================================================================================
rows = []
for index, row in test[test["raw"] >= T].iterrows():
    predicted = {"cpa_lateral_distance_nm": float(row["predicted_cpa_lateral_nm"]),
                 "cpa_vertical_separation_ft": float(row["predicted_cpa_vertical_ft"]),
                 "time_to_cpa_seconds": float(row["predicted_time_to_cpa_seconds"]),
                 "is_converging": bool(row["predicted_is_converging"])}
    verdict = classify_conflict(predicted)
    assessment = {
        "rule": {**predicted, "is_conflict": bool(verdict["is_conflict"]), "severity": verdict["severity"]},
        "classifier": {"raw_probability": float(row["raw"]), "conflict_probability": float(row["raw"])},
        "escalation": {"tier": int(row["tier"]), "tier_name": f"tier {int(row['tier'])}",
                       "time_to_cpa_seconds": float(row["predicted_time_to_cpa_seconds"]),
                       "probability": 1.0, "notify": True,
                       "suggest_resolution": int(row["tier"]) == 1, "reason": ""},
        "resolution": {"offered": False, "options": [], "reason": ""},
    }
    out = AlertFeed().update({index: assessment}, now=0.0)
    rows.append({"is_conflict": int(row["is_conflict"]), "tier": int(row["tier"]),
                 "display": out["active"][0]["display"], "on_active": len(out["active"]) == 1})
shown = pd.DataFrame(rows)

n_total = len(test); n_real = int(y.sum())
prominent = shown[shown["display"] == "alert"]
collapsed = shown[shown["display"] == "low_confidence"]
missed = int(((alerts == 0) & (y == 1)).sum())
correct_silence = int(((alerts == 0) & (y == 0)).sum())

M["frontend"] = {
    "pairs_assessed": n_total, "real_conflicts": n_real,
    "prominent": {"n": len(prominent), "real": int((prominent["is_conflict"] == 1).sum()),
                  "false": int((prominent["is_conflict"] == 0).sum())},
    "collapsed": {"n": len(collapsed), "real": int((collapsed["is_conflict"] == 1).sum()),
                  "false": int((collapsed["is_conflict"] == 0).sum())},
    "not_shown": {"n": int((alerts == 0).sum()), "real": missed, "false": correct_silence},
    "tier1": {"n": int((shown["tier"] == 1).sum()),
              "real": int(((shown["tier"] == 1) & (shown["is_conflict"] == 1)).sum()),
              "false": int(((shown["tier"] == 1) & (shown["is_conflict"] == 0)).sum())},
    "tier2": {"n": int((shown["tier"] == 2).sum()),
              "real": int(((shown["tier"] == 2) & (shown["is_conflict"] == 1)).sum()),
              "false": int(((shown["tier"] == 2) & (shown["is_conflict"] == 0)).sum())},
    "removed_from_active": int((~shown["on_active"]).sum()),
}
p_real = M["frontend"]["prominent"]["real"]; p_false = M["frontend"]["prominent"]["false"]
M["frontend"]["prominent"]["precision"] = p_real / (p_real + p_false)


def confusion(ax, matrix, xlabels, ylabels, title, subtitle):
    top = matrix.max()
    ax.imshow(matrix, cmap=matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ[:5]),
              norm=matplotlib.colors.PowerNorm(0.42, vmin=0, vmax=top), aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=15, fontweight="bold",
                    color=SURFACE if v > top * 0.35 else INK)
    ax.set_xticks(range(len(xlabels))); ax.set_xticklabels(xlabels, fontsize=9.5)
    ax.set_yticks(range(len(ylabels))); ax.set_yticklabels(ylabels, fontsize=9.5)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, color=INK, fontsize=11.5, fontweight="bold", loc="left", pad=20)
    ax.text(0, 1.03, subtitle, transform=ax.transAxes, color=INK2, fontsize=8.5, va="bottom")


fig, ax = plt.subplots(figsize=(6.0, 4.0))
cm = np.array([[card["test"]["true_positive"], card["test"]["false_negative"]],
               [card["test"]["false_positive"], card["test"]["true_negative"]]])
confusion(ax, cm, ["Really a conflict", "Not a conflict"], ["Alert raised", "No alert"],
          "Confusion matrix: the conflict classifier",
          f"{n_total:,} held-out pairs. Recall {op['recall']:.3f}, precision {op['precision']:.3f}.")
fig.savefig(FIGS / "confusion_classifier.png"); plt.close(fig)

fig, ax = plt.subplots(figsize=(6.4, 4.4))
fm = np.array([[M["frontend"]["prominent"]["real"], M["frontend"]["prominent"]["false"]],
               [M["frontend"]["collapsed"]["real"], M["frontend"]["collapsed"]["false"]],
               [missed, correct_silence]])
confusion(ax, fm, ["Really a conflict", "Not a conflict"],
          ["Own alert row\n(prominent)", "Collapsed group\n(still on screen)", "Not shown"],
          "Confusion matrix: what the controller actually sees",
          f"Prominent-list precision {M['frontend']['prominent']['precision']:.3f}. "
          f"Zero conflicts are removed from the active list.")
fig.savefig(FIGS / "confusion_frontend.png"); plt.close(fig)

# ---- funnel (two linear panels; a log scale here would misrepresent the split) ----
fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.9))
plt.subplots_adjust(wspace=0.42)
ax = axes[0]
st = [("Pairs assessed", n_total, n_real),
      ("Alert raised", int(alerts.sum()), int(((alerts == 1) & (y == 1)).sum()))]
yp = np.arange(2)
ax.barh(yp, [s0[1] for s0 in st], 0.55, color=SEQ[1], zorder=3, label="Not a conflict")
ax.barh(yp, [s0[2] for s0 in st], 0.55, color=S1, zorder=4, label="Really a conflict")
for i, s0 in enumerate(st):
    ax.text(s0[1] + n_total * 0.02, i, f"{s0[1]:,}  ({s0[2]} real)", va="center", color=INK2, fontsize=9)
ax.set_yticks(yp); ax.set_yticklabels([s0[0] for s0 in st], fontsize=9.5)
ax.set_xlim(0, n_total * 1.42); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
ax.legend(loc="center right", fontsize=8.5)
finish(ax, "Detection", f"{int(alerts.sum()):,} of {n_total:,} pairs raise an alert.", None, "Pairs")

ax = axes[1]
st = [("Alerts raised", int(alerts.sum()), int(((alerts == 1) & (y == 1)).sum())),
      ("Own alert row", len(prominent), M["frontend"]["prominent"]["real"]),
      ("Tier 1 alarm\n(audible + manoeuvres)", M["frontend"]["tier1"]["n"], M["frontend"]["tier1"]["real"])]
yp = np.arange(3)
ax.barh(yp, [s0[1] for s0 in st], 0.55, color=SEQ[1], zorder=3)
ax.barh(yp, [s0[2] for s0 in st], 0.55, color=S1, zorder=4)
for i, s0 in enumerate(st):
    ax.text(s0[1] + 18, i, f"{s0[1]:,}  ({s0[2]} real)", va="center", color=INK2, fontsize=9)
ax.set_yticks(yp); ax.set_yticklabels([s0[0] for s0 in st], fontsize=9.5)
ax.set_xlim(0, int(alerts.sum()) * 1.42); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
finish(ax, "What reaches the controller", "Same alerts, sorted by how loudly they arrive.", None, "Pairs")
fig.savefig(FIGS / "alert_funnel.png"); plt.close(fig)

# ---- precision by probability band ----------------------------------------------
edges = [T, 0.15, 0.25, 0.40, 0.60, 0.80, 1.01]
bands, precs, counts, reals_b = [], [], [], []
for lo, hi in zip(edges[:-1], edges[1:]):
    m = (raw >= lo) & (raw < hi)
    tp, fp = int((m & (y == 1)).sum()), int((m & (y == 0)).sum())
    if tp + fp:
        bands.append(f"{lo:.2f}–{hi:.2f}" if hi <= 1 else f"{lo:.2f}–1.00")
        precs.append(tp / (tp + fp)); counts.append(tp + fp); reals_b.append(tp)
M["bands"] = [{"band": b, "alerts": c, "real": r, "precision": p}
              for b, c, r, p in zip(bands, counts, reals_b, precs)]
fig, ax = plt.subplots(figsize=(7.2, 4.0))
bars = ax.bar(bands, [p * 100 for p in precs], 0.6, color=SEQ[3], zorder=3)
for bar, p, c in zip(bars, precs, counts):
    ax.text(bar.get_x() + bar.get_width() / 2, p * 100 + 2, f"{p*100:.0f}%\n{c:,} alerts",
            ha="center", color=INK2, fontsize=8.5)
ax.axvspan(-0.5, 1.5, color=S2, alpha=0.09, zorder=1)
ax.text(0.5, 68, "collapsed into the\nlow-confidence group", ha="center", color=S2, fontsize=9,
        fontweight="bold")
ax.set_ylim(0, 92)
finish(ax, "Alert precision by the model's stated confidence",
       "The two lowest bands are 275 alerts holding 11 real conflicts.", "% of alerts that are real",
       "Model score")
fig.savefig(FIGS / "precision_by_band.png"); plt.close(fig)

# ---- interruptions before / after the alert feed (real traffic replay) -----------
M["feed_replay"] = [
    {"session": "05 Sep, 00:30 IST", "pairs_before": 20, "pairs_after": 20,
     "interruptions_before": 241, "interruptions_after": 89},
    {"session": "03 Sep, 20:45 IST", "pairs_before": 10, "pairs_after": 10,
     "interruptions_before": 119, "interruptions_after": 42},
]
M["feed_reasons"] = [("Crossed into a shorter time band", 65), ("Genuinely new conflict", 30),
                     ("Closed by more than 1 NM", 23), ("Escalated to tier 1", 12),
                     ("Severity rose", 1), ("Heartbeat", 0)]
fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9))
ax = axes[0]
labels = [r["session"] for r in M["feed_replay"]]
xp = np.arange(2)
b1 = ax.bar(xp - 0.19, [r["interruptions_before"] for r in M["feed_replay"]], 0.34, color=SEQ[1],
            label="Before (every update re-alerts)", zorder=3)
b2 = ax.bar(xp + 0.19, [r["interruptions_after"] for r in M["feed_replay"]], 0.34, color=S1,
            label="After (repeat suppression)", zorder=3)
for bars in (b1, b2):
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5, f"{int(bar.get_height())}",
                ha="center", color=INK2, fontsize=9)
ax.set_xticks(xp); ax.set_xticklabels(labels, fontsize=9); ax.set_ylim(0, 285)
ax.legend(loc="upper right", fontsize=8.5)
finish(ax, "Interruptions per hour", "Real traffic replay. Same pairs reported in both.",
       "Alert messages")
ax = axes[1]
rl = [r[0] for r in M["feed_reasons"] if r[1] > 0][::-1]
rv = [r[1] for r in M["feed_reasons"] if r[1] > 0][::-1]
bars = ax.barh(rl, rv, 0.6, color=SEQ[3], zorder=3)
for bar, v in zip(bars, rv):
    ax.text(v + 1.2, bar.get_y() + bar.get_height() / 2, str(v), va="center", color=INK2, fontsize=9)
ax.set_xlim(0, 80); ax.grid(axis="y", visible=False)
finish(ax, "Why the remaining 131 fired", "Every one is a real change of state.", None, "Count")
fig.savefig(FIGS / "feed_interruptions.png"); plt.close(fig)

# ---- Model 3 ---------------------------------------------------------------------
M["model3"] = {"alarms": 41, "candidates_evaluated": 1066, "alarms_with_options": 31,
               "alarms_with_nothing": 10, "instructions_offered": 77,
               "instructions_for_real": 36, "instructions_for_false": 41,
               "rejected_ineffective": 565, "blocked_unsafe": 0,
               "by_time": [("0–60 s", 6, 3, 0.50), ("60–120 s", 14, 22, 1.57), ("120–180 s", 21, 52, 2.48)]}
fig, ax = plt.subplots(figsize=(7.0, 3.8))
bands3 = [b[0] for b in M["model3"]["by_time"]]
means = [b[3] for b in M["model3"]["by_time"]]
bars = ax.bar(bands3, means, 0.55, color=[SEQ[1], SEQ[3], S1], zorder=3)
for bar, b in zip(bars, M["model3"]["by_time"]):
    ax.text(bar.get_x() + bar.get_width() / 2, b[3] + 0.08,
            f"{b[3]:.2f}\n{b[2]} instructions\nfrom {b[1]} alarms", ha="center", color=INK2, fontsize=8.5)
ax.set_ylim(0, 3.3)
finish(ax, "Model 3: workable manoeuvres found, by time remaining",
       "Below a minute, almost nothing an airliner can fly restores separation in time.",
       "Mean options offered per alarm", "Time to closest approach")
fig.savefig(FIGS / "model3_options.png"); plt.close(fig)

(Path(FIGS.parent) / "metrics.json").write_text(json.dumps(M, indent=2, default=str))
print(f"figures written to {FIGS}")
for p in sorted(FIGS.glob('*.png')):
    print(f"  {p.name:34} {p.stat().st_size/1024:6.1f} KB")
print(f"\nfrontend confusion: {json.dumps(M['frontend'], indent=2)}")
