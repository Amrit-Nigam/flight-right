"""Does adding the destination to the SERVED (archive-trained) path model help? Decided by a rule
written down before the numbers were seen.

    python ml_pipeline/utils/destination_row.py build     # archive split with callsigns + routes
    python ml_pipeline/utils/destination_row.py train     # control and +destination, seed 42
    python ml_pipeline/utils/destination_row.py alerts    # both through the real alarm chain
    python ml_pipeline/utils/destination_row.py decide    # apply the rule, write the report

Archit, 26 Sep: "if adding destination gets us benefit then do that". Benefit, fixed before any
result was seen (and printed by `decide` exactly as written here):

  1. HEIGHT: top-1 ten-minute height error, all traffic, falls (the reason to add it).
  2. POSITION: arrivals best-of-5 within 5 NM does not drop more than 1.2 points and top-1 not more
     than 0.8 -- twice the four-seed standard deviation of the archive model (0.6 and 0.4).
  3. ALARMS, on validation AND test, through the real chain (alert_prominence.table with today's
     classifier): no fewer real tier 1 alarms, no more real conflicts collapsed, no fewer real
     conflicts shown prominently with >= 3 min warning, and no more false alarms shown
     (tier 1 false + prominent false).

All three must hold, or the destination stays measured and not served.

Why a CONTROL row: the archive training split was deleted on 25 Sep, and it was built before the
join-key fix, so it is rebuilt here with callsigns. The control (no destination) must reproduce the
served archive model's published figures (75.4 / 46.8, temperature 1.065) before its sibling is
compared with anything; if it does not, the rebuild differs and the script stops.

B-side windows in the alarm-chain test were moved and rotated to create the encounter, so a bearing
to B's real destination would be meaningless: B's destination is given as unknown (NaN). A's
callsign is recovered from the raw OpenSky report at A's decision time and exact position (all
40,000 match; ambiguous keys are left unknown). This makes the test conservative for destination.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/utils"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

import archive_row  # noqa: E402
from context_features import GROUPS  # noqa: E402
from ml_pipeline.utils.route_features import ROUTE_FEATURES, route, route_matrix, track_from_window  # noqa: E402

PROCESSED = ROOT / "ml_pipeline/data/processed"
RUNS = PROCESSED / "seed_runs"
COMBINED = archive_row.COMBINED_ROOT / "ml_pipeline/data/processed"
SERVED_SUMMARY = RUNS / "multipath_archive_seed42.summary.json"
ROWS = {"control": "", "destination": "route"}
POSITION_SLACK = {"best5": 1.2, "top1": 0.8}
REPORTS = ROOT / "ml_pipeline/reports"


def build() -> None:
    days = archive_row.choose_days()
    archive_row.preprocess(days)                          # writes ARCHIVE_ROOT splits with keys
    parts = [np.load(archive_row.ARCHIVE_ROOT / f"ml_pipeline/data/processed/trajectory_{s}.npz", allow_pickle=True)
             for s in ("train", "val", "test")]
    keys = ("X", "y", "mask", "timestamps", "icao24", "callsign")
    archive = {k: np.concatenate([p[k] for p in parts]) for k in keys}
    with np.load(PROCESSED / "trajectory_val.npz") as val:
        assert archive["timestamps"].max() < val["timestamps"].min(), "archive sample reaches into validation time"
    rng = np.random.default_rng(archive_row.SEED)          # the identical 400,000-window draw
    pick = np.sort(rng.choice(len(archive["X"]), size=min(archive_row.ARCHIVE_SAMPLES, len(archive["X"])), replace=False))
    COMBINED.mkdir(parents=True, exist_ok=True)
    train = np.load(PROCESSED / "trajectory_train.npz", allow_pickle=True)
    combined = {k: np.concatenate([train[k], archive[k][pick]]) for k in keys}
    np.savez_compressed(COMBINED / "trajectory_train.npz", **combined)
    for split in ("val", "test"):
        shutil.copy2(PROCESSED / f"trajectory_{split}.npz", COMBINED / f"trajectory_{split}.npz")
        shutil.copy2(PROCESSED / f"context_{split}.npz", COMBINED / f"context_{split}.npz")
    print(f"combined train: {len(train['X']):,} existing + {len(pick):,} archive = {len(combined['X']):,} windows")

    callsigns = sorted({str(c).strip() for c in combined["callsign"] if str(c).strip()})
    missing = [c for c in callsigns if not (ROOT / "ml_pipeline/data/routes/adsbdb" / f"{c}.json").exists()]
    print(f"{len(callsigns):,} callsigns; fetching {len(missing):,} routes from adsbdb at <= 2 per second", flush=True)
    for n, callsign in enumerate(missing, 1):
        route(callsign, fetch=True)
        if n % 250 == 0:
            print(f"  {n:,}/{len(missing):,}", flush=True)

    X = combined["X"]
    values = route_matrix(combined["callsign"], X[:, -1, 0].astype(np.float64), X[:, -1, 1].astype(np.float64),
                          track_from_window(X))
    np.savez_compressed(COMBINED / "context_train.npz", groups=np.array(GROUPS, dtype=object),
                        **{name: values[:, j] for j, name in enumerate(ROUTE_FEATURES)})
    coverage = float(np.isfinite(values[:, 0]).mean())
    print(f"destination known for {coverage:.1%} of combined training windows")
    (REPORTS / f"destination_build_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(
        {"combined_windows": int(len(X)), "archive_windows": int(len(pick)), "callsigns": len(callsigns),
         "routes_fetched": len(missing), "destination_known_share": coverage}, indent=2))


def train() -> None:
    for name, groups in ROWS.items():
        out = RUNS / f"multipath_archive_{name}_seed42.pkl"
        if not (out.exists() and out.with_suffix(".summary.json").exists()):
            env = {**os.environ, "FLIGHT_RIGHT_DATA_ROOT": str(archive_row.COMBINED_ROOT),
                   "FLIGHT_RIGHT_MULTIPATH_SEED": "42", "FLIGHT_RIGHT_OFFSET_SEED": "0",
                   "FLIGHT_RIGHT_MULTIPATH_OUT": str(out), "FLIGHT_RIGHT_MULTIPATH_EXTRA": groups}
            with (RUNS / f"multipath_archive_{name}_seed42.log").open("w") as log:
                subprocess.run([sys.executable, str(ROOT / "ml_pipeline/training/trajectory/multipath.py")],
                               env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
        s = json.loads(out.with_suffix(".summary.json").read_text())
        print(f"{name:<12} arrivals b5 {s['best_of_k']['per_mode']['5']['arrivals']:.1f} top1 "
              f"{s['best_of_k']['per_mode']['1']['arrivals']:.1f} | height err all "
              f"{s['three_d']['per_mode']['all']['top1_altitude_mean_ft']:.0f} ft | T {s.get('temperature')}", flush=True)
    control = json.loads((RUNS / "multipath_archive_control_seed42.summary.json").read_text())
    served = json.loads(SERVED_SUMMARY.read_text())
    same = (control["best_of_k"]["per_mode"]["5"]["arrivals"] == served["best_of_k"]["per_mode"]["5"]["arrivals"]
            and control["best_of_k"]["per_mode"]["1"]["arrivals"] == served["best_of_k"]["per_mode"]["1"]["arrivals"])
    print("control reproduces the served archive model:", same)
    if not same:
        raise SystemExit("the rebuilt archive split differs from the one the served model was trained on; stopping")


def a_callsigns(frame: pd.DataFrame, current_a: np.ndarray) -> list[str | None]:
    """Side A's callsign from the raw report at A's decision time and exact position."""
    import glob
    raw = pd.concat([pd.read_parquet(f, columns=["callsign", "time_position", "latitude", "longitude"])
                     for f in glob.glob(str(ROOT / "ml_pipeline/data/raw/*.parquet"))]).dropna()
    raw["key"] = list(zip(raw["time_position"].astype(np.int64), raw["latitude"].round(4), raw["longitude"].round(4)))
    ambiguous = set(raw.loc[raw.duplicated("key", keep=False) & ~raw.duplicated(["key", "callsign"], keep=False), "key"])
    lut = raw.drop_duplicates("key").set_index("key")["callsign"].str.strip()
    out = []
    for t, lat, lon in zip(frame["seed_time_position"].astype(np.int64), current_a[:, 0], current_a[:, 1]):
        key = (int(t), round(float(lat), 4), round(float(lon), 4))
        out.append(None if key in ambiguous else (lut.get(key) or None))
    return out


def alerts() -> None:
    import alert_prominence as ap
    results = {}
    for split in ("val", "test"):
        frame, X, current = ap.inputs(split)
        n = len(frame)
        calls = a_callsigns(frame, current[:n]) + [None] * n          # B relocated: destination unknown
        for tag in ROWS:
            table = ap.table(split, RUNS / f"multipath_archive_{tag}_seed42.pkl", f"dest_{tag}", callsigns=calls)
            results[f"{split}/{tag}"] = ap.summary(table)
        print(split, {tag: results[f"{split}/{tag}"] for tag in ROWS}, flush=True)
    (RUNS / "destination_alerts.json").write_text(json.dumps(results, indent=2))


def decide() -> None:
    control = json.loads((RUNS / "multipath_archive_control_seed42.summary.json").read_text())
    dest = json.loads((RUNS / "multipath_archive_destination_seed42.summary.json").read_text())
    alerts_ = json.loads((RUNS / "destination_alerts.json").read_text())

    def pos(s, k):
        return s["best_of_k"]["per_mode"][k]["arrivals"]

    def height(s, group):
        return s["three_d"]["per_mode"][group]["top1_altitude_mean_ft"]

    checks = {
        "1_height_improves": height(dest, "all") < height(control, "all"),
        "2_position_best5_within_slack": pos(dest, "5") >= pos(control, "5") - POSITION_SLACK["best5"],
        "2_position_top1_within_slack": pos(dest, "1") >= pos(control, "1") - POSITION_SLACK["top1"],
    }
    for split in ("val", "test"):
        c, d = alerts_[f"{split}/control"], alerts_[f"{split}/destination"]
        checks[f"3_{split}_tier1_real_not_fewer"] = d["tier1_real"] >= c["tier1_real"]
        checks[f"3_{split}_collapsed_real_not_more"] = d["collapsed_real"] <= c["collapsed_real"]
        checks[f"3_{split}_prominent_real_3min_not_fewer"] = d["prominent_real_with_3min"] >= c["prominent_real_with_3min"]
        checks[f"3_{split}_false_shown_not_more"] = (d["tier1_false"] + d["prominent_false"]
                                                    <= c["tier1_false"] + c["prominent_false"])
    adopt = all(checks.values())
    report = {"measured_at": datetime.now().isoformat(), "rule": __doc__.split("Benefit, fixed")[1].split("All three")[0],
              "control": {"arrivals_best5": pos(control, "5"), "arrivals_top1": pos(control, "1"),
                          "height_all_ft": height(control, "all"), "height_arrivals_ft": height(control, "arrivals"),
                          "three_d_arrivals_best5": control["three_d"]["per_mode"]["arrivals"]["best5_both"]},
              "destination": {"arrivals_best5": pos(dest, "5"), "arrivals_top1": pos(dest, "1"),
                              "height_all_ft": height(dest, "all"), "height_arrivals_ft": height(dest, "arrivals"),
                              "three_d_arrivals_best5": dest["three_d"]["per_mode"]["arrivals"]["best5_both"]},
              "alerts": alerts_, "checks": checks, "adopt": adopt}
    out = REPORTS / f"destination_row_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(report, indent=2, default=float))
    print(json.dumps({k: report[k] for k in ("control", "destination", "checks", "adopt")}, indent=1, default=float))
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    {"build": build, "train": train, "alerts": alerts, "decide": decide}[sys.argv[1]]()
