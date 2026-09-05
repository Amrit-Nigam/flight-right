"""Manual check of two-tier conflict classification, escalation and drop-tracking.

Everything here is synthetic geometry rather than recorded traffic, because the
three behaviours being checked -- a closest approach that lands between the named
horizons, a one-update glitch, and a pair that safely passes -- have to be set up
deliberately. The aircraft motion itself is the same constant-velocity baseline the
rule-based path uses in production.

Run: venv/Scripts/python.exe ml_pipeline/utils/test_two_tier_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_pipeline.utils.cpa_conflict_detection import (
    ALERT_LATERAL_NM,
    ALERT_VERTICAL_FT,
    CONSECUTIVE_UPDATES_TO_NOTIFY,
    SEPARATION_LATERAL_NM,
    SEPARATION_VERTICAL_FT,
    classify_conflict,
    compute_cpa,
    compute_cpa_from_states,
    current_separation_nm,
    escalate_pair,
    should_drop_from_tracking,
)
from ml_pipeline.utils.trajectory_baseline import predict_future_position, predict_multiple_horizons


UPDATE_INTERVAL_SECONDS = 15
METRES_PER_DEGREE_LATITUDE = 111_320.0
METRES_PER_NAUTICAL_MILE = 1_852.0
CRUISE_SPEED_MS = 240.0
CRUISE_ALTITUDE_M = 10_000.0
TRUE_CPA_SECONDS = 240
MISS_DISTANCE_NM = 2.0
ALTITUDE_GAP_M = 200.0


def make_state(latitude, longitude, altitude_m, velocity_ms, heading_deg, vertical_rate_ms=0.0):
    """The aircraft state dictionary the baseline and CPA modules both expect."""
    return {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "altitude_m": float(altitude_m),
        "velocity_ms": float(velocity_ms),
        "heading_deg": float(heading_deg),
        "vertical_rate_ms": float(vertical_rate_ms),
    }


def advance_state(state, seconds):
    """Move an aircraft forward along its current vector, as the next report would show."""
    latitude, longitude, altitude_m = predict_future_position(
        state["latitude"], state["longitude"], state["altitude_m"],
        state["velocity_ms"], state["heading_deg"], state["vertical_rate_ms"], seconds,
    )
    return make_state(latitude, longitude, altitude_m, state["velocity_ms"], state["heading_deg"],
                      state["vertical_rate_ms"])


def print_update_table(rows):
    """One line per update: what the controller's screen would have shown."""
    print(f"  {'update':>6} {'CPA s':>6} {'CPA NM':>7} {'vert ft':>8} {'tier':>4} {'name':>10} "
          f"{'prob':>5} {'runs':>5} {'notify':>7} {'resolve':>8}")
    for index, (cpa, decision) in enumerate(rows, start=1):
        print(f"  {index:>6} {decision['time_to_cpa_seconds']:>6.0f} {cpa['cpa_lateral_distance_nm']:>7.2f} "
              f"{cpa['cpa_vertical_separation_ft']:>8.0f} {decision['tier']:>4} {decision['tier_name']:>10} "
              f"{decision['probability']:>5.2f} {decision['consecutive_updates']:>5} "
              f"{str(decision['notify']):>7} {str(decision['suggest_resolution']):>8}")


def run_updates(state_a, state_b, update_count, heading_overrides=None, interval_seconds=UPDATE_INTERVAL_SECONDS):
    """Step a pair forward, recomputing the CPA and the escalation decision each time.

    heading_overrides maps a 1-based update number to a bad heading for aircraft B,
    which is how the single noisy report in scenario 2 is produced.
    """
    heading_overrides = heading_overrides or {}
    history = []
    rows = []
    for update in range(1, update_count + 1):
        if update > 1:
            state_a = advance_state(state_a, interval_seconds)
            state_b = advance_state(state_b, interval_seconds)
        # The aircraft keeps flying its real track; only the heading in this one
        # report is wrong. Overriding the state itself would make the glitch stick,
        # which is a different (and easier) thing to detect.
        reported_b = state_b
        if update in heading_overrides:
            reported_b = dict(state_b, heading_deg=heading_overrides[update])
        cpa = compute_cpa_from_states(state_a, reported_b)
        rows.append((cpa, escalate_pair(cpa, history)))
        history.append(cpa)
    return rows, history


def scenario_one_dense_grid_catches_a_240_second_cpa():
    """Two converging aircraft whose true closest approach is at 240 s."""
    print("=" * 100)
    print("SCENARIO 1 - converging pair, true CPA at 240 s (between the named horizons)")
    print("=" * 100)

    # Aircraft A cruises east. Aircraft B is placed due south of where A will be in
    # 240 s, flying north at the same speed, offset sideways by the miss distance --
    # so the two arrive at the same place at the same time, 2 NM apart.
    aircraft_a = make_state(19.0, 72.5, CRUISE_ALTITUDE_M, CRUISE_SPEED_MS, 90.0)
    meeting_lat, meeting_lon, _ = predict_future_position(
        aircraft_a["latitude"], aircraft_a["longitude"], aircraft_a["altitude_m"],
        aircraft_a["velocity_ms"], aircraft_a["heading_deg"], aircraft_a["vertical_rate_ms"], TRUE_CPA_SECONDS,
    )
    approach_degrees = (CRUISE_SPEED_MS * TRUE_CPA_SECONDS) / METRES_PER_DEGREE_LATITUDE
    offset_degrees = (MISS_DISTANCE_NM * METRES_PER_NAUTICAL_MILE) / METRES_PER_DEGREE_LATITUDE
    aircraft_b = make_state(
        meeting_lat - approach_degrees, meeting_lon + offset_degrees,
        CRUISE_ALTITUDE_M + ALTITUDE_GAP_M, CRUISE_SPEED_MS, 0.0,
    )

    print(f"  A: {aircraft_a['latitude']:.4f}, {aircraft_a['longitude']:.4f}  heading 090  "
          f"{aircraft_a['altitude_m']:.0f} m")
    print(f"  B: {aircraft_b['latitude']:.4f}, {aircraft_b['longitude']:.4f}  heading 000  "
          f"{aircraft_b['altitude_m']:.0f} m")

    sparse = compute_cpa(predict_multiple_horizons(aircraft_a), predict_multiple_horizons(aircraft_b))
    dense = compute_cpa_from_states(aircraft_a, aircraft_b)
    print("")
    print("  The blind spot the dense grid removes:")
    for label, values in sparse["per_horizon"].items():
        print(f"    named horizon {label:>5}: {values['lateral_distance_nm']:>6.2f} NM")
    print(f"    four named horizons only -> CPA {sparse['cpa_lateral_distance_nm']:.2f} NM "
          f"at {sparse['time_to_cpa_seconds']:.0f} s  (classified: "
          f"{'CONFLICT' if classify_conflict(sparse)['is_conflict'] else 'no conflict'})")
    print(f"    dense 15 s grid          -> CPA {dense['cpa_lateral_distance_nm']:.2f} NM "
          f"at {dense['time_to_cpa_seconds']:.0f} s  (classified: "
          f"{'CONFLICT' if classify_conflict(dense)['is_conflict'] else 'no conflict'}, "
          f"severity {classify_conflict(dense)['severity']})")
    print(f"    the true CPA at {TRUE_CPA_SECONDS} s is invisible to the four-point check: nothing looks at 240 s.")

    print("")
    print("  Escalation over consecutive updates (15 s apart):")
    rows, _ = run_updates(aircraft_a, aircraft_b, update_count=6)
    print_update_table(rows)
    first_notify = next((index for index, (_, decision) in enumerate(rows, start=1) if decision["notify"]), None)
    first_tier_one = next((index for index, (_, decision) in enumerate(rows, start=1) if decision["tier"] == 1), None)
    print(f"  -> notify becomes True on update {first_notify} (needs {CONSECUTIVE_UPDATES_TO_NOTIFY} in a row).")
    print(f"  -> the pair hands over from advisory to alarm on update {first_tier_one}, which is where a "
          f"resolution is first offered.")


def scenario_two_single_update_glitch():
    """A pair that enters the alert volume on one update only, from a bad heading report."""
    print("")
    print("=" * 100)
    print("SCENARIO 2 - one bad position report; persistence rule must suppress it")
    print("=" * 100)

    # Both aircraft cruise east on parallel tracks 12 NM apart, B ahead and to the
    # left: no conflict, and the gap never closes. On update 3 only, B's report
    # carries a heading of 180 instead of 090. Extrapolated, that turns B straight
    # down across A's track and -- because B is exactly 12 NM ahead as well as 12 NM
    # north -- the two arrive at the same point together, deep inside the volume.
    latitude_offset = (12.0 * METRES_PER_NAUTICAL_MILE) / METRES_PER_DEGREE_LATITUDE
    longitude_offset = (12.0 * METRES_PER_NAUTICAL_MILE) / (METRES_PER_DEGREE_LATITUDE * 0.9455)
    aircraft_a = make_state(19.0, 72.5, CRUISE_ALTITUDE_M, CRUISE_SPEED_MS, 90.0)
    aircraft_b = make_state(19.0 + latitude_offset, 72.5 + longitude_offset,
                            CRUISE_ALTITUDE_M, CRUISE_SPEED_MS, 90.0)

    print(f"  A and B cruise east on parallel tracks 12 NM apart, B ahead and to the left.")
    print(f"  On update 3 only, B reports heading 180 instead of 090 (a single noisy reading).")
    print("")
    rows, _ = run_updates(aircraft_a, aircraft_b, update_count=5, heading_overrides={3: 180.0})
    print_update_table(rows)
    inside = [index for index, (cpa, _) in enumerate(rows, start=1)
              if cpa["cpa_lateral_distance_nm"] < ALERT_LATERAL_NM and cpa["cpa_vertical_separation_ft"] < ALERT_VERTICAL_FT]
    notified = [index for index, (_, decision) in enumerate(rows, start=1) if decision["notify"]]
    print(f"  -> inside the {ALERT_LATERAL_NM:.0f} NM / {ALERT_VERTICAL_FT:.0f} ft alert volume on update(s): {inside}")
    print(f"  -> updates that notified the controller: {notified if notified else 'none'}")
    print(f"  -> the glitch reached {max(decision['consecutive_updates'] for _, decision in rows)} consecutive "
          f"update(s), short of the {CONSECUTIVE_UPDATES_TO_NOTIFY} required, so no alert was raised.")


def scenario_three_pair_safely_passes():
    """A pair that converges, passes, then diverges and should stop being tracked."""
    print("")
    print("=" * 100)
    print("SCENARIO 3 - pair converges, passes safely, and is dropped from tracking")
    print("=" * 100)

    # Same crossing geometry as scenario 1 but stepped in 60 s so the pair runs all
    # the way through its closest approach and out the other side.
    aircraft_a = make_state(19.0, 72.5, CRUISE_ALTITUDE_M, CRUISE_SPEED_MS, 90.0)
    meeting_lat, meeting_lon, _ = predict_future_position(
        aircraft_a["latitude"], aircraft_a["longitude"], aircraft_a["altitude_m"],
        aircraft_a["velocity_ms"], aircraft_a["heading_deg"], aircraft_a["vertical_rate_ms"], TRUE_CPA_SECONDS,
    )
    approach_degrees = (CRUISE_SPEED_MS * TRUE_CPA_SECONDS) / METRES_PER_DEGREE_LATITUDE
    offset_degrees = (4.0 * METRES_PER_NAUTICAL_MILE) / METRES_PER_DEGREE_LATITUDE
    aircraft_b = make_state(
        meeting_lat - approach_degrees, meeting_lon + offset_degrees,
        CRUISE_ALTITUDE_M + ALTITUDE_GAP_M, CRUISE_SPEED_MS, 0.0,
    )

    print(f"  {'update':>6} {'elapsed':>8} {'now NM':>7} {'CPA NM':>7} {'CPA s':>6} {'converging':>11} "
          f"{'tier':>4} {'notify':>7} {'drop':>6}")
    history = []
    state_a, state_b = aircraft_a, aircraft_b
    dropped_on = None
    for update in range(1, 9):
        if update > 1:
            state_a = advance_state(state_a, 60)
            state_b = advance_state(state_b, 60)
        cpa = compute_cpa_from_states(state_a, state_b)
        decision = escalate_pair(cpa, history)
        drop = should_drop_from_tracking(cpa, history)
        if drop and dropped_on is None:
            dropped_on = update
        print(f"  {update:>6} {(update - 1) * 60:>8} {current_separation_nm(cpa):>7.2f} "
              f"{cpa['cpa_lateral_distance_nm']:>7.2f} {cpa['time_to_cpa_seconds']:>6.0f} "
              f"{str(cpa['is_converging']):>11} {decision['tier']:>4} {str(decision['notify']):>7} "
              f"{str(drop):>6}")
        history.append(cpa)
    print(f"  -> dropped from tracking on update {dropped_on}: separation increasing on consecutive "
          f"updates AND outside the alert volume.")


def main() -> None:
    print("Thresholds in use")
    print(f"  legal separation minimum: {SEPARATION_LATERAL_NM:.0f} NM / {SEPARATION_VERTICAL_FT:.0f} ft")
    print(f"  alert volume (wider):     {ALERT_LATERAL_NM:.0f} NM / {ALERT_VERTICAL_FT:.0f} ft")
    print(f"  tier 1 alarm 0-180 s, tier 2 advisory 180-600 s, "
          f"{CONSECUTIVE_UPDATES_TO_NOTIFY} consecutive updates required to notify")
    print("")
    scenario_one_dense_grid_catches_a_240_second_cpa()
    scenario_two_single_update_glitch()
    scenario_three_pair_safely_passes()


if __name__ == "__main__":
    main()
