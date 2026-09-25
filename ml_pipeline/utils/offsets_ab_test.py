"""Does switching the multi-path model to per-mode offsets make the ALERTS better?

    python ml_pipeline/utils/offsets_ab_test.py

Phase 3.1 showed per-mode offsets put the predicted paths closer to where aircraft went
(arrivals best-of-5 63.6% -> 71.5%). That is a trajectory measurement. The backend
serves the old table because switching changes which pairs the controller is alerted
about, and a replay cannot say whether those changes are right -- it has no labels.

This answers it on labelled data. The held-out encounter test split (4,690 pairs, each
labelled by where the two REAL aircraft actually went) is run through the same decision
the backend makes, for both offset modes (table = serving on 24 Sep, per_mode = Phase
3.1) and for every plan-3.2 variant of what the safety net may look at (see VARIANTS).
The 'none' variant must reproduce reevaluate_models.py's runtime number exactly.

The encounter file does not store each aircraft's 10-state history, which the
multi-path model needs, so the seeded generator is re-run with its RNG untouched and
every placement captured. The rebuild is checked row-for-row against the saved file
before anything is scored; if it differs the script stops.

Aircraft B's history gets the same rigid move-and-rotate its future got, so its real
past flying survives exactly as its real future does. Trains nothing, changes no
setting, writes ml_pipeline/reports/offsets_ab_<stamp>.json.

Persistence: each pair is scored as though its geometry held for three updates, the
same assumption reevaluate_models.escalation_run makes, so what is compared is the
gate, not the anti-flicker rule.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/trajectory"))
sys.path.insert(0, str(ROOT / "ml_pipeline/training/conflict_classifier"))

import generate_synthetic_scenarios as gen  # noqa: E402
from train_xgboost import (latest_dataset_path, split_by_session,  # noqa: E402
                           metrics_from_predictions, headline_metric)
from ml_pipeline.utils.cpa_conflict_detection import (  # noqa: E402
    CLASSIFIER_ALERT_KEY, CLASSIFIER_PROBABILITY_KEY, RULE_GEOMETRY_KEY, SEPARATION_LATERAL_NM,
    SEPARATION_VERTICAL_FT, assign_tier, compute_cpa_from_paths, escalate_pair)

SAVED = ROOT / "server/app/ml/saved_models"
REPORTS = ROOT / "ml_pipeline/reports"


# ------------------------------------------------------------------ rebuild with windows

def build_anchors_with_windows(states: pd.DataFrame) -> dict[str, np.ndarray]:
    """gen.build_anchors, line for line, plus each anchor's 10 past states.

    Consumes gen.RNG exactly as the original does, so the dataset that follows is the
    same dataset. Window columns: time, lat, lon, alt_m, velocity, heading, vrate.
    """
    anchor_rows, futures, windows, icaos = [], [], [], []
    for icao, whole_track in states.groupby("icao24", sort=False):
        whole_track = whole_track.drop_duplicates("time_position", keep="last")
        times_all = whole_track["time_position"].to_numpy(dtype=np.int64)
        cuts = np.flatnonzero(np.diff(times_all) > gen.MAX_TRACK_GAP_SECONDS) + 1
        for segment in np.split(np.arange(len(whole_track)), cuts):
            if len(segment) < gen.PAST_STEPS + 2:
                continue
            track = whole_track.iloc[segment]
            times = track["time_position"].to_numpy(dtype=np.int64)
            latitudes = track["latitude"].to_numpy(dtype=np.float64)
            longitudes = track["longitude"].to_numpy(dtype=np.float64)
            altitudes = track["baro_altitude"].to_numpy(dtype=np.float64)
            velocities = track["velocity"].to_numpy(dtype=np.float64)
            headings = track["true_track"].to_numpy(dtype=np.float64)
            vertical_rates = track["vertical_rate"].to_numpy(dtype=np.float64)
            unwrapped = np.unwrap(np.deg2rad(headings))
            for index in range(gen.PAST_STEPS - 1, len(track)):
                future = gen._dense_future(times, latitudes, longitudes, altitudes, index)
                if future is None:
                    continue
                span = max(float(times[index] - times[index - gen.PAST_STEPS + 1]), 1.0)
                turn_rate = math.degrees(unwrapped[index] - unwrapped[index - gen.PAST_STEPS + 1]) / span
                along_accel = (velocities[index] - velocities[index - gen.PAST_STEPS + 1]) / span
                vertical_accel = (vertical_rates[index] - vertical_rates[index - gen.PAST_STEPS + 1]) / span
                anchor_rows.append((int(times[index]), latitudes[index], longitudes[index], altitudes[index],
                                    velocities[index], headings[index] % 360.0, vertical_rates[index],
                                    turn_rate, along_accel, vertical_accel))
                futures.append(future)
                w = slice(index - gen.PAST_STEPS + 1, index + 1)
                windows.append(np.column_stack((times[w], latitudes[w], longitudes[w], altitudes[w],
                                                velocities[w], headings[w], vertical_rates[w])))
                icaos.append(str(icao))
    columns = ["time", "latitude", "longitude", "altitude_m", "velocity_ms", "heading_deg",
               "vertical_rate_ms", "turn_rate_deg_s", "along_accel_ms2", "vertical_accel_ms2"]
    table = {name: np.asarray([row[i] for row in anchor_rows], dtype=np.float64)
             for i, name in enumerate(columns)}
    table["time"] = table["time"].astype(np.int64)
    table["future"] = np.stack(futures)
    table["window"] = np.stack(windows)
    table["icao24"] = np.asarray(icaos)   # which real aircraft each anchor is (plan 9.0 joins)
    order = np.argsort(table["time"])
    table = {key: value[order] for key, value in table.items()}
    table["session_id"] = np.concatenate(([0], np.cumsum(np.diff(table["time"]) > gen.SESSION_BREAK_SECONDS)))
    if len(table["time"]) > gen.MAX_ANCHORS:
        keep = np.sort(gen.RNG.choice(len(table["time"]), size=gen.MAX_ANCHORS, replace=False))
        table = {key: value[keep] for key, value in table.items()}
    return table


def rebuild() -> tuple[pd.DataFrame, list[dict], dict[str, np.ndarray]]:
    """Re-run the seeded generator, capturing every kept row's placement."""
    captured: list[dict] = []
    last: dict = {}
    original_place, original_transform, original_try = (
        gen._place_second_aircraft, gen.transform_track, gen._try_build_row)

    def place(anchors, index_a, index_b, intended):
        out = original_place(anchors, index_a, index_b, intended)
        last["place"] = out
        return out

    def transform(future, anchor_latitude, anchor_longitude, rotation_deg, new_latitude,
                  new_longitude, altitude_offset_m):
        last["transform"] = (anchor_latitude, anchor_longitude, rotation_deg, new_latitude,
                             new_longitude, altitude_offset_m)
        return original_transform(future, anchor_latitude, anchor_longitude, rotation_deg,
                                  new_latitude, new_longitude, altitude_offset_m)

    def try_row(anchors, index_a, index_b, intended):
        last.clear()
        row = original_try(anchors, index_a, index_b, intended)
        if row is not None:
            captured.append({"index_a": index_a, "index_b": index_b, **dict(zip(
                ("anchor_lat", "anchor_lon", "rotation", "lat_b", "lon_b", "alt_offset_m"),
                last["transform"]))})
        return row

    gen._place_second_aircraft, gen.transform_track, gen._try_build_row = place, transform, try_row
    try:
        anchors = build_anchors_with_windows(gen.load_valid_states())
        dataset = gen.build_dataset(anchors)
    finally:
        gen._place_second_aircraft, gen.transform_track, gen._try_build_row = (
            original_place, original_transform, original_try)
    return dataset, captured, anchors


def verify_identical(rebuilt: pd.DataFrame, saved: pd.DataFrame) -> None:
    if rebuilt.shape != saved.shape or list(rebuilt.columns) != list(saved.columns):
        raise SystemExit(f"REBUILD DIFFERS in shape: {rebuilt.shape} vs {saved.shape}")
    for column in saved.columns:
        a, b = rebuilt[column].to_numpy(), saved[column].to_numpy()
        same = np.array_equal(a, b) if a.dtype.kind not in "f" else np.allclose(a, b, rtol=0, atol=1e-9)
        if not same:
            raise SystemExit(f"REBUILD DIFFERS in column {column!r}; cannot trust the windows.")
    print(f"rebuild verified: {len(saved):,} rows x {saved.shape[1]} columns identical to the saved file")


# ------------------------------------------------------------------ model inputs

def to_model_window(raw: np.ndarray) -> np.ndarray:
    """(10, 7) captured states -> the (10, 8) window inference.window_from_states builds."""
    times, heading = raw[:, 0].astype(float), np.deg2rad(raw[:, 5])
    return np.column_stack((raw[:, 1], raw[:, 2], raw[:, 3], raw[:, 4], np.sin(heading),
                            np.cos(heading), raw[:, 6], np.diff(times, prepend=times[0]))).astype(np.float32)


def relocated_window(raw: np.ndarray, cap: dict) -> np.ndarray:
    """B's past moved and rotated as the same rigid piece its future was."""
    moved = gen.transform_track(raw[:, 1:4].astype(np.float64), cap["anchor_lat"], cap["anchor_lon"],
                                cap["rotation"], cap["lat_b"], cap["lon_b"], cap["alt_offset_m"])
    out = raw.copy()
    out[:, 1:4] = moved
    out[:, 5] = (raw[:, 5] + cap["rotation"]) % 360.0
    return out


# ------------------------------------------------------------------ inputs, cached

CACHE = ROOT / "ml_pipeline/data/processed/offsets_ab_inputs.npz"


def inputs(split: str = "test") -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """One split, (2N, 10, 8) windows (A rows then B rows), (2N, 3) current positions.

    The rebuild takes ~10 minutes and is verified identical to the saved dataset before
    it is cached (gitignored) for ALL 40,000 rows, keyed on the dataset file name. Any
    split is then served from the cache. Delete the cache to force a rebuild.
    """
    dataset_name = latest_dataset_path().name
    saved = pd.read_parquet(latest_dataset_path())
    saved["_row"] = np.arange(len(saved))
    frame = split_by_session(saved)[split].reset_index(drop=True)
    cached = np.load(CACHE, allow_pickle=False) if CACHE.exists() else None
    if cached is None or str(cached["dataset"]) != dataset_name or "X_a" not in cached:
        print(f"dataset {dataset_name}: {len(saved):,} rows; rebuilding windows")
        rebuilt, captured, anchors = rebuild()
        verify_identical(rebuilt, saved.drop(columns="_row"))
        raw_a = [anchors["window"][c["index_a"]] for c in captured]
        raw_b = [relocated_window(anchors["window"][c["index_b"]], c) for c in captured]
        # The relocated current state must be the state the features were computed from.
        alt_b = np.array([anchors["altitude_m"][c["index_b"]] + c["alt_offset_m"] for c in captured])
        assert np.allclose([w[-1, 3] for w in raw_b], alt_b), "B's relocated altitude does not match"
        assert np.allclose([w[-1, 1] for w in raw_b], [c["lat_b"] for c in captured], atol=1e-9)
        np.savez_compressed(
            CACHE, dataset=dataset_name,
            X_a=np.stack([to_model_window(w) for w in raw_a]),
            X_b=np.stack([to_model_window(w) for w in raw_b]),
            current_a=np.stack([w[-1, 1:4] for w in raw_a]).astype(np.float64),
            current_b=np.stack([w[-1, 1:4] for w in raw_b]).astype(np.float64))
        cached = np.load(CACHE, allow_pickle=False)
    else:
        print(f"inputs from cache {CACHE.name} (rebuild was verified when it was written)")
    rows = frame["_row"].to_numpy()
    X = np.concatenate([cached["X_a"][rows], cached["X_b"][rows]])
    current = np.concatenate([cached["current_a"][rows], cached["current_b"][rows]])
    return frame, X, current


# ------------------------------------------------------------------ variants
#
# With a classifier verdict attached, a pair is alerted iff the safety net fires or the
# classifier alerts (alert_gate); the tier only decides alarm vs watch list. So the
# multi-path model changes WHO is alerted only through the safety net, and these
# variants differ only in what the safety net is allowed to look at.
#
#   none          no multi-path step at all; rule geometry for everything
#   current       the backend BEFORE 24 Sep: for pairs outside tier 1 the multi-path
#                 representative REPLACES the rule geometry, and the net checks it
#   rule_only     the net checks the straight-line rule geometry only; multi-path
#                 still supplies the tier for pairs outside tier 1. SHIPPED 24 Sep with
#                 per_mode, chosen by beneficial() below.
#   rule_or_mp:X  the net fires on the rule geometry OR on any admissible combination
#   replace:X     'current', with the candidate fan pruned to X first
#
# Pruning X (plan 3.2): mass90 keeps each aircraft's likeliest paths up to 90% of its
# probability; floor10 drops paths under 0.10 (likeliest always kept); joint05 drops
# combinations whose joint probability is under 0.05 (likeliest always kept).

PRUNINGS = ("all", "mass90", "floor10", "joint05")
VARIANTS = (["none", "current", "rule_only"] + [f"rule_or_mp:{p}" for p in PRUNINGS]
            + [f"replace:{p}" for p in PRUNINGS[1:]])


def admissible(combinations: list[dict], prob_a: np.ndarray, prob_b: np.ndarray, pruning: str) -> list[dict]:
    if pruning == "all":
        return combinations
    if pruning == "mass90":
        keep_a = int(np.searchsorted(np.cumsum(prob_a), 0.90) + 1)
        keep_b = int(np.searchsorted(np.cumsum(prob_b), 0.90) + 1)
        return [c for c in combinations if c["path_a"] < keep_a and c["path_b"] < keep_b]
    if pruning == "floor10":
        return [c for c in combinations if (c["path_a"] == 0 or prob_a[c["path_a"]] >= 0.10)
                and (c["path_b"] == 0 or prob_b[c["path_b"]] >= 0.10)]
    if pruning == "joint05":
        kept = [c for c in combinations if c["joint_probability"] >= 0.05]
        return kept or [max(combinations, key=lambda c: c["joint_probability"])]
    raise ValueError(pruning)


def representative(combos: list[dict]) -> dict:
    """The same rule compute_cpa_from_paths uses: worst alert-volume breach, else likeliest."""
    breaching = [c for c in combos if c["breaches_alert_volume"]]
    if breaching:
        return min(breaching, key=lambda c: c["cpa"]["cpa_lateral_distance_nm"])["cpa"]
    return max(combos, key=lambda c: c["joint_probability"])["cpa"]


def breach(cpa: dict) -> bool:
    return bool(cpa["cpa_lateral_distance_nm"] < SEPARATION_LATERAL_NM
                and cpa["cpa_vertical_separation_ft"] < SEPARATION_VERTICAL_FT)


def decide(variant: str, rule: dict, combos, prob_a, prob_b, classifier_alert: bool) -> tuple[bool, int, str]:
    """(fired, tier, route) for one pair, assuming its geometry held for three updates."""
    if variant == "none" or combos is None or assign_tier(rule)["tier"] == 1:
        tier_cpa, net = rule, breach(rule)
    else:
        kind, _, pruning = variant.partition(":")
        pool = admissible(combos, prob_a, prob_b, pruning or "all")
        tier_cpa = representative(pool)
        if kind in ("current", "replace"):
            net = breach(tier_cpa)
        elif kind == "rule_only":
            net = breach(rule)
        else:  # rule_or_mp
            net = breach(rule) or any(breach(c["cpa"]) for c in pool)
    tier = assign_tier(tier_cpa)["tier"]
    if tier == 0:
        return False, 0, ""
    if net:
        return True, tier, "safety-net"
    return classifier_alert, tier, "classifier" if classifier_alert else ""


def score(test: pd.DataFrame, y: np.ndarray, fired: np.ndarray, tiers: np.ndarray, routes: np.ndarray) -> dict:
    block = metrics_from_predictions(y, fired.astype(int))
    rate, caught, total = headline_metric(test, fired.astype(int))
    block["headline"] = {"rate": rate, "caught": caught, "total": total}
    block["alerts"] = int(fired.sum())
    for tier in (1, 2):
        in_tier = fired & (tiers == tier)
        block[f"tier_{tier}"] = {"alerts": int(in_tier.sum()), "real": int((in_tier & (y == 1)).sum()),
                                 "false": int((in_tier & (y == 0)).sum())}
    block["by_route"] = {r: {"alerts": int((routes == r).sum()), "real": int(((routes == r) & (y == 1)).sum())}
                         for r in ("safety-net", "classifier")}
    return block


def beneficial(candidate: dict, served: dict) -> bool:
    """The adoption rule, fixed BEFORE the numbers were seen (24 Sep 2026): no loss in the
    three-minute catch, in recall, or in real tier 1 alarms. Fewest false alarms wins."""
    return (candidate["headline"]["caught"] >= served["headline"]["caught"]
            and candidate["recall"] >= served["recall"]
            and candidate["tier_1"]["real"] >= served["tier_1"]["real"])


def main() -> None:
    import xgboost
    from server.app.ml.inference import MultiPathPredictor

    test, X, current = inputs()
    n, y = len(test), test["is_conflict"].to_numpy()
    print(f"test: {n:,} pairs, {int(y.sum())} real conflicts")

    card = json.loads((SAVED / "xgboost_conflict_model_card.json").read_text())
    booster = xgboost.Booster()
    booster.load_model(str(SAVED / "xgboost_conflict.json"))
    raw = booster.predict(xgboost.DMatrix(test[gen.FEATURE_COLUMNS], feature_names=gen.FEATURE_COLUMNS))
    classifier_alert = raw >= card["decision_threshold"]

    rules = [{"cpa_lateral_distance_nm": float(test["predicted_cpa_lateral_nm"].iloc[i]),
              "cpa_vertical_separation_ft": float(test["predicted_cpa_vertical_ft"].iloc[i]),
              "time_to_cpa_seconds": float(test["predicted_time_to_cpa_seconds"].iloc[i]),
              "is_converging": True} for i in range(n)]

    # decide() re-implements alert_gate for speed; prove it agrees with the real thing.
    for i in range(n):
        row = {**rules[i], CLASSIFIER_ALERT_KEY: bool(classifier_alert[i]), CLASSIFIER_PROBABILITY_KEY: 0.5}
        assert escalate_pair(row, [row, row])["notify"] == decide(
            "none", rules[i], None, None, None, bool(classifier_alert[i]))[0], f"decide() disagrees on row {i}"

    results: dict = {}
    fired_sets: dict = {}
    for mode in ("table", "per_mode"):
        predictor = MultiPathPredictor(offsets=mode)
        probabilities, positions, _ = predictor.predict(X)
        pair_mp = [compute_cpa_from_paths(predictor.paths_for_cpa(X, i, probabilities, positions),
                                          predictor.paths_for_cpa(X, n + i, probabilities, positions),
                                          tuple(current[i]), tuple(current[n + i]))
                   for i in range(n)]
        pair_combos = [mp["combinations"] for mp in pair_mp]
        # 'rule_only' is what inference.assess_pair does since 24 Sep. Build its input the
        # way assess_pair does and run the REAL escalate_pair, so the measured variant and
        # the shipped code are proven to be the same decision, pair by pair.
        for i in range(n):
            chosen = rules[i] if assign_tier(rules[i])["tier"] == 1 else {
                **pair_mp[i], RULE_GEOMETRY_KEY: {k: rules[i][k] for k in
                                                  ("cpa_lateral_distance_nm", "cpa_vertical_separation_ft",
                                                   "time_to_cpa_seconds")}}
            row = {**chosen, CLASSIFIER_ALERT_KEY: bool(classifier_alert[i]), CLASSIFIER_PROBABILITY_KEY: 0.5}
            real = escalate_pair(row, [row, row])
            mine = decide("rule_only", rules[i], pair_combos[i], probabilities[i], probabilities[n + i],
                          bool(classifier_alert[i]))
            assert (real["notify"], real["tier"] if real["notify"] else 0) == (mine[0], mine[1] if mine[0] else 0), \
                f"{mode}: shipped escalate_pair disagrees with the measured rule_only variant on row {i}"
        print(f"{mode}: shipped decision path == measured 'rule_only' on all {n:,} pairs")
        for variant in VARIANTS:
            if variant == "none" and mode == "per_mode":
                continue
            out = [decide(variant, rules[i], pair_combos[i], probabilities[i], probabilities[n + i],
                          bool(classifier_alert[i])) for i in range(n)]
            key = "none" if variant == "none" else f"{mode} {variant}"
            fired = np.array([o[0] for o in out])
            results[key] = score(test, y, fired, np.array([o[1] for o in out]), np.array([o[2] for o in out]))
            fired_sets[key] = fired

    served = results["table current"]
    print(f"\n{'configuration':<28}{'alerts':>7}{'recall':>8}{'3-min':>10}{'FA/1000':>9}"
          f"{'t1 r/f':>10}{'t2 r/f':>10}{'net':>6}  beneficial")
    for key, b in results.items():
        b["beneficial_vs_served"] = beneficial(b, served)
        print(f"{key:<28}{b['alerts']:>7}{b['recall']:>8.4f}{b['headline']['caught']:>6}/{b['headline']['total']}"
              f"{b['false_alarms_per_1000']:>9.1f}{b['tier_1']['real']:>6}/{b['tier_1']['false']:<3}"
              f"{b['tier_2']['real']:>6}/{b['tier_2']['false']:<3}{b['by_route']['safety-net']['alerts']:>6}"
              f"  {'yes' if b['beneficial_vs_served'] else 'no'}")

    # What the multi-path safety net adds on top of the rule's own, per mode.
    in_time = test["actual_time_to_cpa_seconds"].to_numpy() >= 180
    added = {}
    for mode in ("table", "per_mode"):
        extra = fired_sets[f"{mode} rule_or_mp:all"] & ~fired_sets[f"{mode} rule_only"]
        added[mode] = {"real": int((extra & (y == 1)).sum()), "false": int((extra & (y == 0)).sum()),
                       "real_with_3min": int((extra & (y == 1) & in_time).sum())}
    print(f"\nalerts the multi-path safety net adds on top of the rule's: {added}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    REPORTS.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS / f"offsets_ab_{stamp}.json"
    out_path.write_text(json.dumps({"dataset": latest_dataset_path().name, "test_pairs": n,
                                    "served_configuration": "table current", "results": results,
                                    "multipath_net_adds": added}, indent=2, default=float))
    print(f"\nwrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()


