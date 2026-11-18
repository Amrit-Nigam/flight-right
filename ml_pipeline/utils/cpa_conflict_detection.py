"""Closest-point-of-approach calculations and transparent rule-based labels."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ml_pipeline.utils.trajectory_baseline import predict_future_position


EARTH_RADIUS_M = 6_371_000.0
METRES_PER_NAUTICAL_MILE = 1_852.0
METRES_TO_FEET = 3.28084
HORIZON_SECONDS = {"1min": 60, "3min": 180, "5min": 300, "10min": 600}
# The true closest point of approach almost never lands on one of the four named
# horizons. Two aircraft passing at t = 240 s used to be recorded at whatever their
# separation happened to be at 180 s and at 300 s -- often well outside threshold --
# and the conflict was silently dropped, capping detection recall. Fifteen seconds
# at a 500 m/s closing speed moves the pair by ~4 NM, which is fine enough to resolve
# a 5 NM threshold.
CPA_GRID_STEP_SECONDS = 15
CPA_GRID_END_SECONDS = 600

# The legal separation minimum. This is what actually counts as a loss of
# separation, and it is what the evaluation reports against. Simplified academic
# en-route values, not certified regulatory standards.
SEPARATION_LATERAL_NM = 5.0
SEPARATION_VERTICAL_FT = 1000.0
# The alert volume, deliberately WIDER than the legal minimum. A prediction that is
# 1 NM out otherwise flips the decision from "safe" to "conflict" and back again.
# Measured on our own test pairs: triggering at the bare 5 NM / 1000 ft minimum
# catches only 46% of real conflicts, while 8 NM / 1500 ft catches 99% at one minute
# and 93% at three, costing 32-34 false alarms per 1000 pairs. Both pairs of numbers
# live here so the trade can be re-tuned in one place.
ALERT_LATERAL_NM = 8.0
ALERT_VERTICAL_FT = 1500.0

# Two tiers, because a ten-minute prediction is not accurate enough to justify
# telling an aircraft to change course. Tier 1 raises a real alert and earns a
# resolution suggestion; tier 2 is a watch-list entry only and never suggests a
# manoeuvre. The 180 s boundary is the geometry of the response, not a round number:
# alert to controller decision to readback to the pilot starting the manoeuvre is
# about 38 s, a 1000 ft level change then takes ~40 s and a 30 degree turn at 450 kt
# ~96 s, so the practical floor for a useful warning is around three minutes.
TIER_1_MAX_SECONDS = 180
TIER_2_MAX_SECONDS = 600
TIER_NAMES = {0: "background", 1: "alarm", 2: "advisory"}
# Tier 1 interrupts the controller, so it demands more confidence than tier 2, which
# only adds a row to a watch list.
TIER_1_PROBABILITY_THRESHOLD = 0.85
TIER_2_PROBABILITY_THRESHOLD = 0.60
# One noisy position report should not raise an alarm, and an alert that flickers on
# and off is worse than no alert. A pair must qualify on this many updates in a row.
CONSECUTIVE_UPDATES_TO_NOTIFY = 3

# When the XGBoost conflict classifier has given a verdict on a pair, it rides on the
# CPA result under these keys so that escalate_pair can use it AND so the
# three-consecutive-updates walk sees the same verdict for past updates that it saw
# when they were current. Absent, escalation behaves exactly as it did before, which
# is what keeps the rule-only path (and every existing test) working unchanged.
CLASSIFIER_ALERT_KEY = "classifier_alert"
CLASSIFIER_PROBABILITY_KEY = "classifier_probability"
# When the geometry a pair is tiered on came from a MODEL (the multi-path representative,
# used outside tier 1), the straight-line rule's own closest approach rides along under
# this key, and the safety net checks it instead. Section 13: the deterministic rule is
# the safety net. Letting the model's worst path combination stand in for it was measured
# on 24 Sep 2026 (offsets_ab_test.py, 4,690 labelled test pairs) to add 86-111 false alarms
# for 0-2 real conflicts, and to DROP a real conflict whose rule geometry breached.
RULE_GEOMETRY_KEY = "rule_geometry"
# Two consecutive increases in separation, so a single jittery reading cannot retire
# a pair that is still converging.
DIVERGING_UPDATES_TO_DROP = 2


def haversine_distance_nm(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    """Return great-circle lateral distance between latitude/longitude points in NM."""
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (latitude_a, longitude_a, latitude_b, longitude_b))
    delta_lat, delta_lon = lat_b - lat_a, lon_b - lon_a
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    return (2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))) / METRES_PER_NAUTICAL_MILE


def _position(prediction: Any) -> tuple[float, float, float]:
    """Accept the baseline tuple format, plus named dictionaries for convenience."""
    if isinstance(prediction, Mapping):
        return float(prediction["latitude"]), float(prediction["longitude"]), float(prediction["altitude_m"])
    latitude, longitude, altitude_m = prediction
    return float(latitude), float(longitude), float(altitude_m)


def cpa_grid_times(step_seconds: int = CPA_GRID_STEP_SECONDS, end_seconds: int = CPA_GRID_END_SECONDS) -> list[int]:
    """The default look-ahead grid: every step_seconds from now to end_seconds inclusive."""
    return list(range(0, int(end_seconds) + 1, int(step_seconds)))


def predict_dense_grid(
    state: Mapping[str, float],
    times_seconds: Sequence[int] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Constant-velocity positions on a dense time grid, keyed by seconds from now.

    This keeps the rule-based conflict path working without the neural model, which
    matters because the CPA rule is the deterministic safety net that stays in place
    alongside any learned detector.
    """
    times = cpa_grid_times() if times_seconds is None else [int(value) for value in times_seconds]
    return {
        seconds: predict_future_position(
            state["latitude"], state["longitude"], state["altitude_m"],
            state["velocity_ms"], state["heading_deg"], state["vertical_rate_ms"], seconds,
        )
        for seconds in times
    }


def _seconds_for_key(key: Any) -> int | None:
    """Resolve a prediction key to seconds, accepting both named horizons and a grid."""
    if key in HORIZON_SECONDS:
        return HORIZON_SECONDS[key]
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


def compute_cpa(aircraft_a_predictions: Mapping[Any, Any], aircraft_b_predictions: Mapping[Any, Any]) -> dict[str, Any]:
    """Find minimum predicted lateral separation over every time both aircraft share.

    Accepts either the four named horizons (as the dashboard still supplies) or a
    dense grid keyed by seconds from predict_dense_grid. Denser input gives a truer
    CPA; the code path is the same.
    """
    times_a = {seconds: key for key in aircraft_a_predictions if (seconds := _seconds_for_key(key)) is not None}
    times_b = {seconds: key for key in aircraft_b_predictions if (seconds := _seconds_for_key(key)) is not None}
    common_times = sorted(set(times_a).intersection(times_b))
    if not common_times:
        raise ValueError("Aircraft predictions have no matching look-ahead times.")

    samples: list[dict[str, float]] = []
    for seconds in common_times:
        lat_a, lon_a, altitude_a = _position(aircraft_a_predictions[times_a[seconds]])
        lat_b, lon_b, altitude_b = _position(aircraft_b_predictions[times_b[seconds]])
        samples.append({
            "horizon_seconds": int(seconds),
            "lateral_distance_nm": haversine_distance_nm(lat_a, lon_a, lat_b, lon_b),
            "vertical_separation_ft": abs(altitude_a - altitude_b) * METRES_TO_FEET,
        })

    cpa = min(samples, key=lambda sample: sample["lateral_distance_nm"])
    # Whether the pair is closing right now, rather than merely close at some point.
    # A pair already separating is a different operational picture from one converging.
    is_converging = len(samples) >= 2 and samples[1]["lateral_distance_nm"] < samples[0]["lateral_distance_nm"]

    # The four named horizons stay available for the dashboard, when they are present.
    per_horizon = {
        label: sample
        for label, seconds in HORIZON_SECONDS.items()
        for sample in samples
        if sample["horizon_seconds"] == seconds
    }
    return {
        "time_to_cpa_seconds": cpa["horizon_seconds"],
        # Retained under its old name so existing callers keep working.
        "cpa_horizon_seconds": cpa["horizon_seconds"],
        "cpa_lateral_distance_nm": cpa["lateral_distance_nm"],
        "cpa_vertical_separation_ft": cpa["vertical_separation_ft"],
        "is_converging": is_converging,
        "grid": samples,
        "per_horizon": per_horizon,
    }


def compute_cpa_from_states(
    state_a: Mapping[str, float],
    state_b: Mapping[str, float],
    times_seconds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Convenience path: two raw aircraft states straight to a dense-grid CPA result."""
    return compute_cpa(predict_dense_grid(state_a, times_seconds), predict_dense_grid(state_b, times_seconds))


def classify_conflict(
    cpa_result: Mapping[str, Any],
    lateral_threshold_nm: float = SEPARATION_LATERAL_NM,
    vertical_threshold_ft: float = SEPARATION_VERTICAL_FT,
) -> dict[str, bool | str]:
    """Apply configurable separation thresholds and the project's severity rules."""
    lateral = float(cpa_result["cpa_lateral_distance_nm"])
    vertical = float(cpa_result["cpa_vertical_separation_ft"])
    cpa_seconds = float(cpa_result.get("time_to_cpa_seconds", cpa_result.get("cpa_horizon_seconds", 0.0)))
    is_conflict = lateral < lateral_threshold_nm and vertical < vertical_threshold_ft

    # Severity describes lateral encounter urgency. A high severity can therefore
    # still have is_conflict=False when vertical separation remains safe.
    if lateral < 3.0 and vertical < 700.0 and cpa_seconds <= 180:
        severity = "critical"
    elif lateral < 5.0 and cpa_seconds <= 300:
        severity = "high"
    elif lateral < lateral_threshold_nm and cpa_seconds <= 600:
        severity = "medium"
    else:
        # A decreasing range that never crossed the configured threshold is a
        # low-risk convergence; otherwise there is no meaningful convergence. The
        # dense grid answers this directly; the per-horizon fallback covers callers
        # still passing the four named horizons only.
        if "is_converging" in cpa_result:
            converging = bool(cpa_result["is_converging"])
        else:
            distances = [item["lateral_distance_nm"] for item in cpa_result.get("per_horizon", {}).values()]
            converging = len(distances) >= 2 and min(distances[1:]) < distances[0]
        severity = "low" if converging else "none"
    return {"is_conflict": is_conflict, "severity": severity}


def current_separation_nm(cpa_result: Mapping[str, Any]) -> float:
    """Lateral separation right now, rather than at the closest point of approach.

    The first sample on the dense grid is t = 0, so it is where the two aircraft
    actually are. That is the honest measure of "have they passed each other yet",
    which the CPA distance cannot answer on its own: a pair that has already passed
    still reports whatever their closest approach was.
    """
    grid = cpa_result.get("grid")
    if grid:
        return float(grid[0]["lateral_distance_nm"])
    return float(cpa_result["cpa_lateral_distance_nm"])


def is_inside_alert_volume(cpa_result: Mapping[str, Any]) -> bool:
    """Whether the predicted closest approach breaches the (wider) alert volume."""
    return (
        float(cpa_result["cpa_lateral_distance_nm"]) < ALERT_LATERAL_NM
        and float(cpa_result["cpa_vertical_separation_ft"]) < ALERT_VERTICAL_FT
    )


def breaches_separation_minimum(cpa_result: Mapping[str, Any]) -> bool:
    """Whether the predicted closest approach breaches the LEGAL minimum, 5 NM / 1000 ft.

    This is the deterministic safety net, and it is deliberately narrower than the
    8 NM / 1500 ft alert volume. Section 13 keeps the CPA rule in place alongside the
    classifier and never lets a model overrule it, so a predicted breach of the legal
    minimum raises an alert whatever the classifier says. Measured on the held-out
    test split (21 Sep): it rescues 2 real conflicts the classifier misses, which is
    what takes system recall from 0.9439 to 0.9505.
    """
    return (
        float(cpa_result["cpa_lateral_distance_nm"]) < SEPARATION_LATERAL_NM
        and float(cpa_result["cpa_vertical_separation_ft"]) < SEPARATION_VERTICAL_FT
    )


def conflict_probability(cpa_result: Mapping[str, Any]) -> float:
    """How likely this pair is to actually conflict, from 0.0 to 1.0.

    When the result came from compute_cpa_from_paths it already carries a real
    probability -- the summed weight of the candidate path combinations that violate
    separation -- and that value is used directly.

    Otherwise this falls back to the single-path rule: 1.0 inside the alert volume
    and 0.0 outside it. That fallback is deliberately blunt rather than an invented
    confidence, and it keeps the rule-based path working when the multi-path model is
    unavailable, exactly as the constant-velocity baseline does for trajectories.
    """
    if "conflict_probability" in cpa_result:
        return float(cpa_result["conflict_probability"])
    return 1.0 if is_inside_alert_volume(cpa_result) else 0.0


def densify_path(
    current_position: tuple[float, float, float] | Mapping[str, float],
    horizon_predictions: Mapping[Any, Any],
    times_seconds: Sequence[int] | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Interpolate a sparse predicted path onto the dense 15 s grid.

    The multi-path model predicts at the four named horizons only (60/180/300/600 s).
    Checking K x K path combinations on those four instants reintroduces exactly the
    blind spot the rule-based path fixed on 1 Sep: a pair closest at t = 240 s is
    measured at 180 s and 300 s and the conflict is missed. This puts the current
    position at t = 0 and linearly interpolates between the known points, so every
    candidate path is checked on the same grid the deterministic detector uses.

    Linear interpolation between predicted points is the honest choice: the model has
    said nothing about the shape of the path between horizons, and a straight segment
    adds no assumption the model did not make. Over 60-300 s segments the chord of an
    airliner's turn deviates from the arc by well under the 5 NM threshold.
    """
    times = cpa_grid_times() if times_seconds is None else sorted(int(value) for value in times_seconds)
    known: dict[int, tuple[float, float, float]] = {0: _position(current_position)}
    for key, prediction in horizon_predictions.items():
        seconds = _seconds_for_key(key)
        if seconds is not None and seconds > 0:
            known[seconds] = _position(prediction)
    known_times = sorted(known)
    if len(known_times) < 2:
        raise ValueError("A path needs the current position and at least one prediction to densify.")

    dense: dict[int, tuple[float, float, float]] = {}
    for seconds in times:
        if seconds in known:
            dense[seconds] = known[seconds]
            continue
        if seconds > known_times[-1]:
            break  # Never extrapolate past the last predicted point.
        # Locate the bracketing known points.
        upper = next(t for t in known_times if t > seconds)
        lower = max(t for t in known_times if t < seconds)
        fraction = (seconds - lower) / (upper - lower)
        start, end = known[lower], known[upper]
        dense[seconds] = tuple(start[i] + fraction * (end[i] - start[i]) for i in range(3))  # type: ignore[assignment]
    return dense


def compute_cpa_from_paths(
    paths_a: Sequence[tuple[float, Mapping[Any, Any]]],
    paths_b: Sequence[tuple[float, Mapping[Any, Any]]],
    current_a: tuple[float, float, float] | Mapping[str, float] | None = None,
    current_b: tuple[float, float, float] | Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Conflict probability over every combination of two aircraft's candidate paths.

    Each argument is a sequence of (probability, predictions) pairs, where predictions
    is whatever compute_cpa accepts -- a dense grid keyed by seconds, or the four
    named horizons. Every one of the K x K combinations is checked, and the
    probabilities of the combinations that breach the alert volume are summed. That
    sum is the conflict probability the escalation rule consumes.

    This is the point of predicting several paths. A single predicted path forces a
    yes/no answer to a question whose honest answer is a proportion: two aircraft in
    an identical situation finish an average of 7.9 NM apart ten minutes later, so
    "which of the plausible futures conflict, and how much weight do they carry" is
    the question that can actually be answered.

    The returned result is a normal CPA result so it drops straight into
    classify_conflict, assign_tier and escalate_pair, with the probability attached.
    The representative geometry is the WORST conflicting combination -- the smallest
    lateral separation -- because that is the encounter the controller needs to see;
    if nothing conflicts, the most likely combination is reported instead.

    When current_a and current_b (the aircraft's positions right now) are supplied,
    every candidate path is first interpolated onto the dense 15 s grid with
    densify_path, so the K x K check no longer inherits the four-horizon blind spot.
    """
    if not paths_a or not paths_b:
        raise ValueError("Both aircraft need at least one candidate path.")
    if current_a is not None and current_b is not None:
        paths_a = [(probability, densify_path(current_a, predictions)) for probability, predictions in paths_a]
        paths_b = [(probability, densify_path(current_b, predictions)) for probability, predictions in paths_b]

    # Renormalise defensively: a caller that trimmed to the top K without
    # renormalising would otherwise understate every probability below.
    weight_a = _normalised_weights([probability for probability, _ in paths_a])
    weight_b = _normalised_weights([probability for probability, _ in paths_b])

    combinations: list[dict[str, Any]] = []
    conflict_weight = 0.0
    for index_a, (_, predictions_a) in enumerate(paths_a):
        for index_b, (_, predictions_b) in enumerate(paths_b):
            cpa = compute_cpa(predictions_a, predictions_b)
            joint = weight_a[index_a] * weight_b[index_b]
            breaches = is_inside_alert_volume(cpa)
            if breaches:
                conflict_weight += joint
            combinations.append({
                "path_a": index_a, "path_b": index_b, "joint_probability": joint,
                "breaches_alert_volume": breaches, "cpa": cpa,
            })

    breaching = [item for item in combinations if item["breaches_alert_volume"]]
    if breaching:
        representative = min(breaching, key=lambda item: item["cpa"]["cpa_lateral_distance_nm"])
    else:
        representative = max(combinations, key=lambda item: item["joint_probability"])

    result = dict(representative["cpa"])
    result["conflict_probability"] = float(min(1.0, conflict_weight))
    result["combinations_checked"] = len(combinations)
    result["combinations_breaching"] = len(breaching)
    result["representative_paths"] = (representative["path_a"], representative["path_b"])
    result["combinations"] = combinations
    return result


def _normalised_weights(probabilities: Sequence[float]) -> list[float]:
    """Scale path probabilities to sum to 1, falling back to uniform if they cannot."""
    values = [max(0.0, float(value)) for value in probabilities]
    total = sum(values)
    if total <= 0.0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in values]


def assign_tier(cpa_result: Mapping[str, Any]) -> dict[str, Any]:
    """Place a pair in a tier from how soon its closest approach arrives."""
    seconds = float(cpa_result.get("time_to_cpa_seconds", cpa_result.get("cpa_horizon_seconds", 0.0)))
    if 0 <= seconds <= TIER_1_MAX_SECONDS:
        tier = 1
    elif TIER_1_MAX_SECONDS < seconds <= TIER_2_MAX_SECONDS:
        tier = 2
    else:
        tier = 0
    return {"tier": tier, "tier_name": TIER_NAMES[tier], "time_to_cpa_seconds": seconds}


def tier_probability_threshold(tier: int) -> float:
    """The confidence a pair needs before it is worth showing, per tier."""
    if tier == 1:
        return TIER_1_PROBABILITY_THRESHOLD
    if tier == 2:
        return TIER_2_PROBABILITY_THRESHOLD
    # Tier 0 is the background list, which is never shown, so nothing can clear it.
    return 1.1


def alert_gate(cpa_result: Mapping[str, Any]) -> tuple[bool, str]:
    """Whether this pair qualifies on its own, and which route decided it.

    Three routes, in strict priority order:

    1. **The deterministic safety net.** A predicted breach of the legal 5 NM /
       1000 ft minimum qualifies whatever any model says. The rule is never
       overruled by a model (Section 13). It is judged on the straight-line rule's
       geometry (RULE_GEOMETRY_KEY when the tiering geometry came from a model), so
       a low-probability model path can neither raise nor suppress it.
    2. **The conflict classifier**, when a verdict is attached. It is the model the
       94.0% headline is measured on, and it answers exactly this question. It
       carries its OWN calibrated threshold, applied before the verdict reaches
       here. It is emphatically NOT compared against TIER_1/TIER_2_PROBABILITY_
       THRESHOLD: those are 0.85 and 0.60, chosen for the multi-path joint
       probability, while the classifier's own conflict line sits at 0.0285
       calibrated -- roughly thirty times lower. Measured on the held-out split
       (21 Sep), comparing the classifier against 0.85 would drop test recall from
       0.9439 to 0.1881 and the headline metric from 94.0% to 19.0%.
    3. **The probability route**, unchanged: the multi-path joint probability where
       one exists, else the blunt 1.0/0.0 alert-volume rule. This is what runs when
       no classifier verdict is attached, so the rule-only path and every existing
       test behave exactly as before.
    """
    tier = assign_tier(cpa_result)["tier"]
    if tier == 0:
        return False, "tier-0"
    if breaches_separation_minimum(cpa_result.get(RULE_GEOMETRY_KEY, cpa_result)):
        return True, "separation-minimum"
    if CLASSIFIER_ALERT_KEY in cpa_result:
        return bool(cpa_result[CLASSIFIER_ALERT_KEY]), "classifier"
    return conflict_probability(cpa_result) >= tier_probability_threshold(tier), "probability"


def meets_alert_conditions(cpa_result: Mapping[str, Any]) -> bool:
    """Conditions 1 and 2 of the escalation rule, for one update on its own.

    Condition 3 -- persistence -- cannot be judged from a single update, so it is
    applied by escalate_pair over the history.
    """
    return alert_gate(cpa_result)[0]


def consecutive_alert_updates(cpa_result: Mapping[str, Any], history: Sequence[Mapping[str, Any]] = ()) -> int:
    """Count how many updates in a row, ending with this one, have qualified.

    history is the previous CPA results for this same pair, oldest first, so the
    walk runs backwards from the most recent and stops at the first update that
    did not qualify.
    """
    if not meets_alert_conditions(cpa_result):
        return 0
    count = 1
    for previous in reversed(list(history)):
        if not meets_alert_conditions(previous):
            break
        count += 1
    return count


def escalate_pair(cpa_result: Mapping[str, Any], history: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Decide whether this pair is shown to the controller, and in which tier.

    Notify only when all three conditions hold together: the conflict probability
    clears the tier's threshold, the closest approach falls inside that tier's time
    range, and the pair has held both of those for CONSECUTIVE_UPDATES_TO_NOTIFY
    updates in a row. Any one of the three on its own produces alerts that flicker,
    fire too early to act on, or fire on a single bad position report.
    """
    tier_result = assign_tier(cpa_result)
    tier = tier_result["tier"]
    probability = conflict_probability(cpa_result)
    threshold = tier_probability_threshold(tier)
    qualifies, gate = alert_gate(cpa_result)
    updates = consecutive_alert_updates(cpa_result, history)
    notify = updates >= CONSECUTIVE_UPDATES_TO_NOTIFY

    # Every item surfaced to the controller carries its reason with it, so the
    # dashboard never has to display an alert it cannot explain.
    if tier == 0:
        reason = f"Closest approach {tier_result['time_to_cpa_seconds']:.0f} s away is outside the {TIER_2_MAX_SECONDS} s look-ahead."
    elif not qualifies:
        if gate == "classifier":
            reason = (f"The conflict classifier puts this pair at "
                      f"{float(cpa_result.get(CLASSIFIER_PROBABILITY_KEY, 0.0)) * 100:.1f}%, "
                      f"below the level at which it calls a conflict, and the predicted closest "
                      f"approach stays outside {SEPARATION_LATERAL_NM:.0f} NM / {SEPARATION_VERTICAL_FT:.0f} ft.")
        else:
            reason = f"Predicted closest approach stays outside the {ALERT_LATERAL_NM:.0f} NM / {ALERT_VERTICAL_FT:.0f} ft alert volume."
    elif not notify:
        reason = f"Held for {updates} of {CONSECUTIVE_UPDATES_TO_NOTIFY} consecutive updates; waiting for confirmation."
    else:
        reason = (
            f"{tier_result['tier_name']}: closest approach {cpa_result['cpa_lateral_distance_nm']:.2f} NM / "
            f"{cpa_result['cpa_vertical_separation_ft']:.0f} ft in {tier_result['time_to_cpa_seconds']:.0f} s, "
            f"confirmed on {updates} consecutive updates."
        )
        # ISSUES.md C4: never present the classifier's explanation as the justification
        # for an alert the classifier did not raise. When the deterministic rule fired
        # and the classifier disagrees, say which one is speaking. The rule wins, but
        # the controller is told the models are not of one mind.
        # The geometry above may be the multi-path model's; the net fired on the
        # straight line, so quote the numbers that actually raised it.
        rule = cpa_result.get(RULE_GEOMETRY_KEY)
        if gate == "separation-minimum" and rule is not None:
            reason += (
                f" The straight-line prediction that raised it: {float(rule['cpa_lateral_distance_nm']):.2f} NM / "
                f"{float(rule['cpa_vertical_separation_ft']):.0f} ft in {float(rule['time_to_cpa_seconds']):.0f} s."
            )
        if gate == "separation-minimum" and cpa_result.get(CLASSIFIER_ALERT_KEY) is False:
            reason += (
                f" Raised by the separation rule, not by the classifier, which puts this pair at "
                f"{float(cpa_result.get(CLASSIFIER_PROBABILITY_KEY, 0.0)) * 100:.1f}% and would not "
                f"have alerted; the deterministic rule is never overruled by a model."
            )

    return {
        "tier": tier,
        "tier_name": tier_result["tier_name"],
        "time_to_cpa_seconds": tier_result["time_to_cpa_seconds"],
        "probability": probability,
        "probability_threshold": threshold,
        # Which of the three routes in alert_gate() decided this, so the dashboard and
        # the audit log can say WHY a pair qualified rather than only that it did.
        "gate": gate,
        "qualifies_this_update": qualifies,
        "classifier_probability": (float(cpa_result[CLASSIFIER_PROBABILITY_KEY])
                                   if CLASSIFIER_PROBABILITY_KEY in cpa_result else None),
        "consecutive_updates": updates,
        "notify": notify,
        # Tier 2 is a watch list. Suggesting a manoeuvre on a ten-minute prediction
        # would cost real fuel and delay on a conflict that may never happen.
        "suggest_resolution": notify and tier == 1,
        "reason": reason,
    }


def should_drop_from_tracking(cpa_result: Mapping[str, Any], history: Sequence[Mapping[str, Any]] = ()) -> bool:
    """Whether the aircraft have safely passed and the pair can be retired.

    Both conditions are required. Separation increasing on its own is not enough --
    two aircraft can be drifting apart and still be predicted to converge again --
    and being outside the alert volume on its own is just a pair that has not
    converged yet.
    """
    if is_inside_alert_volume(cpa_result):
        return False
    separations = [current_separation_nm(item) for item in list(history)] + [current_separation_nm(cpa_result)]
    if len(separations) < DIVERGING_UPDATES_TO_DROP + 1:
        return False
    recent = separations[-(DIVERGING_UPDATES_TO_DROP + 1):]
    return all(later > earlier for earlier, later in zip(recent, recent[1:]))
