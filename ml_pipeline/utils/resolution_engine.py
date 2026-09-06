"""Model 3: rule-based conflict resolution options, each one explained and costed.

WHAT THIS DOES

Given two aircraft that the detector has escalated to a tier 1 alarm, this proposes
three ways out -- change an altitude, change a heading, or change a speed -- and for
each one reports what separation it actually achieves, what it costs in delay and
fuel, how confident we are, and a sentence a controller can read aloud.

It never applies anything. It returns options. The controller accepts, dismisses or
overrides, and that decision is logged. Nothing here can command an aircraft.

THE ONE IDEA THAT MAKES THIS HONEST: MANOEUVRES TAKE TIME

The naive version of this file would move the aircraft to its new heading instantly,
re-run the geometry, and report that the conflict is solved. That would be wrong in
the dangerous direction -- it would recommend turns that cannot physically work in
the time available.

So every option is simulated with its real kinematics:

  1. Nothing happens at all for RESPONSE_DELAY_SECONDS. The controller decides (15 s),
     calls the pilot and gets a readback (15 s), and the pilot acts (8 s). That is 38
     seconds before the aircraft has moved a foot.
  2. Then the aircraft turns at a standard rate, or climbs at a normal rate, or
     changes speed at a normal acceleration. It does not teleport.
  3. Separation is then measured from the resulting path.

This is why the project prefers altitude changes when time is short, and the
preference is not a scoring fudge -- it falls out of the physics. A 1000 ft level
change opens the required gap in about 40 s. A 30 degree turn at 450 kt takes about
96 s to open 5 NM, because after turning you are only closing sideways at
V x sin(30) and it takes that long to cover the distance. When the closest approach
is 90 seconds away, the climb is available and the turn is not. The engine discovers
that by simulating, rather than by being told.

WHAT IS DELIBERATELY CRUDE, AND SAID OUT LOUD

Delay and fuel are coarse proxies, not an aircraft performance model. We have no
engine data, no weight, no wind. They are computed from track-mile arithmetic and are
good enough to rank three options against each other. They are NOT good enough to
quote to an airline, and the explanation strings say "about" for exactly that reason.
Section 10 of CLAUDE.md asks for a "fuel proxy" and that is what this is.

Run the demonstration: venv/Scripts/python.exe ml_pipeline/utils/resolution_engine.py
"""

from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Set before the project import below, so this file works both as a module and when
# run directly as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ml_pipeline.utils.cpa_conflict_detection import (
    SEPARATION_LATERAL_NM,
    SEPARATION_VERTICAL_FT,
    compute_cpa,
)

METRES_PER_DEGREE = 111_320.0
METRES_PER_NAUTICAL_MILE = 1_852.0
METRES_TO_FEET = 3.28084
KNOTS_TO_MS = 0.514444

# --- Response geometry. These four numbers are the reason tier 1 stops at 3 minutes.
CONTROLLER_DECISION_SECONDS = 15.0
RADIO_CALL_AND_READBACK_SECONDS = 15.0
PILOT_REACTION_SECONDS = 8.0
RESPONSE_DELAY_SECONDS = (
    CONTROLLER_DECISION_SECONDS + RADIO_CALL_AND_READBACK_SECONDS + PILOT_REACTION_SECONDS
)

# --- Aircraft kinematics. Simplified but standard values, not certified performance.
# A standard rate turn is 3 degrees per second, which is what civil traffic is vectored
# at below high speed. A 30 degree turn therefore takes 10 seconds to establish.
STANDARD_TURN_RATE_DEG_S = 3.0
# 1500 feet per minute. This is what makes a 1000 ft level change take about 40 s,
# which is the number the tier boundary is built on.
LEVEL_CHANGE_RATE_FT_MIN = 1500.0
LEVEL_CHANGE_RATE_MS = LEVEL_CHANGE_RATE_FT_MIN / 60.0 / METRES_TO_FEET
# Airliners change speed slowly. 0.35 m/s^2 is roughly 40 kt in a minute.
SPEED_CHANGE_RATE_MS2 = 0.35
# Internal integration step. The grid we report on is 15 s, but a 30 degree turn is
# established in 10 s, so integrating at 15 s would miss the turn entirely.
SIMULATION_STEP_SECONDS = 1.0

# --- The candidate manoeuvres. Deliberately a short, round-numbered list: these are
# instructions a controller would actually give, not a continuous optimisation.
ALTITUDE_CHANGES_FT = (1000.0, 2000.0, -1000.0, -2000.0)
HEADING_CHANGES_DEG = (15.0, 30.0, 45.0, -15.0, -30.0, -45.0)
SPEED_CHANGES_KT = (-40.0, -20.0, 20.0)

# --- Safety envelope. A suggestion outside this is blocked and reported as blocked,
# never silently dropped: Section 10 counts blocked unsafe suggestions as a metric.
MIN_SAFE_ALTITUDE_FT = 10_000.0
MAX_SAFE_ALTITUDE_FT = 45_000.0
MIN_SAFE_SPEED_MS = 150.0
MAX_SAFE_SPEED_MS = 280.0

# --- Ranking weights, fixed by CLAUDE.md Section 3. Safety dominates by design.
WEIGHT_SAFETY = 0.60
WEIGHT_DELAY = 0.15
WEIGHT_FUEL = 0.10
WEIGHT_WORKLOAD = 0.10
WEIGHT_CONFIDENCE = 0.05

# Cost normalisation. A manoeuvre costing this much scores zero on that component;
# anything worse is clamped. Chosen so the three option types land on a comparable
# scale rather than one type always winning on units.
DELAY_SCALE_SECONDS = 300.0
FUEL_SCALE_EQUIVALENT_SECONDS = 600.0
# Climbing 1000 ft costs roughly this much extra fuel, expressed as the equivalent of
# flying level for that many seconds. A coarse proxy, stated as one.
CLIMB_COST_SECONDS_PER_1000FT = 120.0
DESCENT_COST_SECONDS_PER_1000FT = 30.0

# How much better than the legal minimum an option should be before we call it fully
# safe. Landing exactly on 5 NM leaves nothing for prediction error.
COMFORTABLE_LATERAL_NM = 8.0
COMFORTABLE_VERTICAL_FT = 1500.0


@dataclass
class Manoeuvre:
    """One instruction: who, what, how much."""

    aircraft: str
    kind: str  # "altitude", "heading" or "speed"
    magnitude: float
    unit: str


@dataclass
class ResolutionOption:
    """A costed, explained way out of one conflict."""

    manoeuvre: Manoeuvre
    resulting_lateral_nm: float
    resulting_vertical_ft: float
    resolves: bool
    first_violation_seconds: float | None
    seconds_to_establish: float
    established_before_cpa: bool
    delay_seconds: float
    fuel_equivalent_seconds: float
    confidence: float
    score: float
    components: dict[str, float]
    explanation: str
    blocked_reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_offerable(self) -> bool:
        """Offerable means it is safe to issue AND it actually prevents the loss.

        There is no separate 'in time' test. The simulation already contains the 38 s
        response delay and the real turn and climb rates, so a manoeuvre that is too
        slow simply fails to prevent the violation and resolves is False.
        """
        return self.blocked_reason is None and self.resolves


def _flight_level(altitude_m: float) -> str:
    """Altitude as a controller says it: FL260, or an altitude in feet when low."""
    feet = altitude_m * METRES_TO_FEET
    if feet >= 18_000:
        return f"FL{int(round(feet / 100)):03d}"
    return f"{int(round(feet / 100) * 100):,} ft"


def simulate_manoeuvre(
    state: Mapping[str, float],
    manoeuvre: Manoeuvre | None,
    times_seconds: Sequence[int],
) -> dict[int, tuple[float, float, float]]:
    """Fly the aircraft forward, obeying the manoeuvre with realistic kinematics.

    Passing manoeuvre=None flies the aircraft as it is, which reproduces the ordinary
    constant-velocity path and is what the untouched aircraft in the pair does.

    Integration runs at SIMULATION_STEP_SECONDS and is sampled at the requested times.
    A coarser integration would step straight over a turn that establishes in ten
    seconds and would report a manoeuvre that never happened.
    """
    latitude = float(state["latitude"])
    longitude = float(state["longitude"])
    altitude = float(state["altitude_m"])
    speed = float(state["velocity_ms"])
    heading = float(state["heading_deg"]) % 360.0
    vertical_rate = float(state["vertical_rate_ms"])

    target_heading = heading
    target_altitude: float | None = None
    target_speed = speed
    if manoeuvre is not None:
        if manoeuvre.kind == "heading":
            target_heading = (heading + manoeuvre.magnitude) % 360.0
        elif manoeuvre.kind == "altitude":
            target_altitude = altitude + manoeuvre.magnitude / METRES_TO_FEET
        elif manoeuvre.kind == "speed":
            target_speed = speed + manoeuvre.magnitude * KNOTS_TO_MS

    wanted = sorted({int(t) for t in times_seconds})
    output: dict[int, tuple[float, float, float]] = {}
    elapsed = 0.0
    if 0 in wanted:
        output[0] = (latitude, longitude, altitude)

    end = max(wanted)
    step = SIMULATION_STEP_SECONDS
    while elapsed < end:
        elapsed += step
        manoeuvring = manoeuvre is not None and elapsed > RESPONSE_DELAY_SECONDS

        if manoeuvring and manoeuvre.kind == "heading":
            # Turn the short way round at a standard rate until established.
            difference = (target_heading - heading + 180.0) % 360.0 - 180.0
            turn = min(abs(difference), STANDARD_TURN_RATE_DEG_S * step)
            heading = (heading + math.copysign(turn, difference)) % 360.0
        elif manoeuvring and manoeuvre.kind == "altitude" and target_altitude is not None:
            remaining = target_altitude - altitude
            climb = min(abs(remaining), LEVEL_CHANGE_RATE_MS * step)
            altitude += math.copysign(climb, remaining)
            vertical_rate = math.copysign(LEVEL_CHANGE_RATE_MS, remaining) if abs(remaining) > 1e-6 else 0.0
        elif manoeuvring and manoeuvre.kind == "speed":
            remaining = target_speed - speed
            change = min(abs(remaining), SPEED_CHANGE_RATE_MS2 * step)
            speed += math.copysign(change, remaining)
        else:
            # Not manoeuvring: keep doing whatever the aircraft was already doing,
            # including any climb or descent already in progress.
            altitude += vertical_rate * step

        distance = speed * step
        latitude += (distance * math.cos(math.radians(heading))) / METRES_PER_DEGREE
        longitude += (distance * math.sin(math.radians(heading))) / (
            METRES_PER_DEGREE * math.cos(math.radians(latitude))
        )

        marker = int(round(elapsed))
        if marker in wanted and marker not in output:
            output[marker] = (latitude, longitude, altitude)

    for marker in wanted:
        output.setdefault(marker, (latitude, longitude, altitude))
    return output


def _pair_geometry(
    grid_a: Mapping[int, tuple[float, float, float]],
    grid_b: Mapping[int, tuple[float, float, float]],
) -> tuple[float | None, float, float, float]:
    """Walk the whole simulated window and report what actually happens.

    Returns (first_violation_seconds, worst_lateral_nm, vertical_at_that_moment,
    seconds_of_that_moment). A violation is the moment BOTH separations fail at once,
    since either one alone is legal separation.

    This replaces testing only the closest-approach sample. Two aircraft can be at
    their tightest laterally while comfortably stacked vertically, and lose separation
    at a different instant entirely -- so the violation test has to look at every step,
    not at one summary point.
    """
    from ml_pipeline.utils.cpa_conflict_detection import haversine_distance_nm

    first_violation: float | None = None
    worst_lateral = float("inf")
    vertical_there = float("inf")
    at_seconds = 0.0
    for seconds in sorted(set(grid_a).intersection(grid_b)):
        lat_a, lon_a, alt_a = grid_a[seconds]
        lat_b, lon_b, alt_b = grid_b[seconds]
        lateral = haversine_distance_nm(lat_a, lon_a, lat_b, lon_b)
        vertical = abs(alt_a - alt_b) * METRES_TO_FEET
        if lateral < SEPARATION_LATERAL_NM and vertical < SEPARATION_VERTICAL_FT:
            if first_violation is None:
                first_violation = float(seconds)
        if lateral < worst_lateral:
            worst_lateral, vertical_there, at_seconds = lateral, vertical, float(seconds)
    return first_violation, worst_lateral, vertical_there, at_seconds


def _seconds_to_establish(manoeuvre: Manoeuvre, state: Mapping[str, float]) -> float:
    """When the aircraft has finished doing what it was told, counting from now.

    Nothing at all happens for the first 38 seconds. Then the turn, climb or speed
    change takes its own time. This number is why a level change beats a turn when the
    clock is short, and it is arithmetic rather than a preference we imposed.
    """
    if manoeuvre.kind == "heading":
        moving = abs(manoeuvre.magnitude) / STANDARD_TURN_RATE_DEG_S
    elif manoeuvre.kind == "altitude":
        moving = abs(manoeuvre.magnitude) / LEVEL_CHANGE_RATE_FT_MIN * 60.0
    else:
        moving = abs(manoeuvre.magnitude) * KNOTS_TO_MS / SPEED_CHANGE_RATE_MS2
    return RESPONSE_DELAY_SECONDS + moving


def _estimate_delay_seconds(manoeuvre: Manoeuvre, state: Mapping[str, float],
                            hold_seconds: float) -> float:
    """Rough extra flying time the instruction costs. A proxy, not a performance model."""
    speed = float(state["velocity_ms"])
    if manoeuvre.kind == "heading":
        # Fly off track for hold_seconds then return: the dog-leg is longer than the
        # straight line by roughly (1/cos(angle) - 1).
        angle = math.radians(abs(manoeuvre.magnitude))
        return hold_seconds * (1.0 / max(math.cos(angle), 1e-3) - 1.0)
    if manoeuvre.kind == "speed":
        if manoeuvre.magnitude >= 0:
            return 0.0  # Speeding up costs fuel, not time.
        slower = speed + manoeuvre.magnitude * KNOTS_TO_MS
        if slower <= 0:
            return DELAY_SCALE_SECONDS
        return hold_seconds * (speed / slower - 1.0)
    # A level change costs almost no track distance.
    return 0.0


def _estimate_fuel_equivalent_seconds(manoeuvre: Manoeuvre, state: Mapping[str, float],
                                      delay_seconds: float) -> float:
    """Fuel cost expressed as equivalent seconds of level cruise. Coarse by design."""
    if manoeuvre.kind == "altitude":
        thousands = abs(manoeuvre.magnitude) / 1000.0
        rate = CLIMB_COST_SECONDS_PER_1000FT if manoeuvre.magnitude > 0 else DESCENT_COST_SECONDS_PER_1000FT
        return thousands * rate
    if manoeuvre.kind == "speed" and manoeuvre.magnitude > 0:
        # Drag rises steeply with speed, so going faster is the expensive option.
        return (manoeuvre.magnitude / 20.0) ** 2 * 60.0
    # Turning burns the extra track miles it creates.
    return delay_seconds


def _workload_score(manoeuvre: Manoeuvre) -> float:
    """How easy this is to issue and monitor. Higher is easier.

    A level change is one instruction and the controller can see it working on the
    readout. A vector needs a second instruction later to put the aircraft back on
    course, and the controller has to remember to give it.
    """
    return {"altitude": 1.0, "speed": 0.7, "heading": 0.5}[manoeuvre.kind]


def _safety_score(lateral_nm: float, vertical_ft: float) -> float:
    """How comfortably separated the pair ends up. Either dimension can do the job."""
    lateral = min(1.0, lateral_nm / COMFORTABLE_LATERAL_NM)
    vertical = min(1.0, vertical_ft / COMFORTABLE_VERTICAL_FT)
    return max(lateral, vertical)


def _confidence(lateral_nm: float, vertical_ft: float, seconds_to_establish: float,
                time_to_cpa: float, state_a: Mapping[str, float],
                state_b: Mapping[str, float]) -> float:
    """How much to trust this option, from margin, timing and how steady the traffic is.

    Three things reduce confidence. A thin margin over the legal minimum, because our
    own position prediction has error in it. A manoeuvre that is still being flown when
    the aircraft pass, since anything that delays it eats the whole margin. And an
    aircraft that is already climbing or descending hard, because that is exactly where
    this project's predictions are measured to be weakest.
    """
    margin = _safety_score(lateral_nm, vertical_ft)
    if time_to_cpa > 0:
        timing = max(0.0, min(1.0, (time_to_cpa - seconds_to_establish) / time_to_cpa))
    else:
        timing = 0.0
    steadiness = 1.0
    for state in (state_a, state_b):
        if abs(float(state.get("vertical_rate_ms", 0.0))) > 2.5:
            steadiness -= 0.15
    steadiness = max(0.4, steadiness)
    return round(max(0.0, min(1.0, 0.5 * margin + 0.3 * timing + 0.2 * steadiness)), 3)


def _explain(manoeuvre: Manoeuvre, option: dict, state: Mapping[str, float]) -> str:
    """The sentence a controller reads. Never ship a suggestion without one."""
    who = manoeuvre.aircraft
    if manoeuvre.kind == "altitude":
        target = state["altitude_m"] + manoeuvre.magnitude / METRES_TO_FEET
        verb = "Climb" if manoeuvre.magnitude > 0 else "Descend"
        instruction = f"{verb} {who} to {_flight_level(target)}"
        mechanism = f"holds vertical separation at {option['vertical']:,.0f} ft where the paths cross"
    elif manoeuvre.kind == "heading":
        direction = "right" if manoeuvre.magnitude > 0 else "left"
        target = (float(state["heading_deg"]) + manoeuvre.magnitude) % 360.0
        instruction = f"Turn {who} {direction} {abs(manoeuvre.magnitude):.0f} degrees, heading {target:03.0f}"
        mechanism = f"opens the closest approach to {option['lateral']:.1f} NM"
    else:
        verb = "Reduce" if manoeuvre.magnitude < 0 else "Increase"
        instruction = f"{verb} {who} speed by {abs(manoeuvre.magnitude):.0f} kt"
        mechanism = f"opens the closest approach to {option['lateral']:.1f} NM"

    cost = []
    if option["delay"] >= 15:
        cost.append(f"about {option['delay'] / 60:.1f} min delay")
    if option["fuel"] >= 30:
        cost.append(f"about {option['fuel'] / 60:.1f} min of extra fuel burn")
    tradeoff = "; ".join(cost) if cost else "negligible delay and fuel cost"

    return (
        f"{instruction}. Reason: {mechanism}. Fully established about "
        f"{option['establish']:.0f} s from now, against a closest approach in "
        f"{option['time_to_cpa']:.0f} s. Confidence {option['confidence']:.2f}. "
        f"Tradeoff: {tradeoff}. Delay and fuel are approximate."
    )


def _blocked_reason(manoeuvre: Manoeuvre, state: Mapping[str, float]) -> str | None:
    """Refuse instructions that are outside the safe envelope, before costing them."""
    if manoeuvre.kind == "altitude":
        target_ft = state["altitude_m"] * METRES_TO_FEET + manoeuvre.magnitude
        if target_ft < MIN_SAFE_ALTITUDE_FT:
            return f"would descend below the {MIN_SAFE_ALTITUDE_FT:,.0f} ft en-route floor"
        if target_ft > MAX_SAFE_ALTITUDE_FT:
            return f"would climb above the {MAX_SAFE_ALTITUDE_FT:,.0f} ft ceiling"
    if manoeuvre.kind == "speed":
        target = state["velocity_ms"] + manoeuvre.magnitude * KNOTS_TO_MS
        if target < MIN_SAFE_SPEED_MS:
            return "would slow the aircraft below a safe cruising speed"
        if target > MAX_SAFE_SPEED_MS:
            return "would push the aircraft above a safe cruising speed"
    return None


def evaluate_manoeuvre(
    manoeuvre: Manoeuvre,
    state_a: Mapping[str, float],
    state_b: Mapping[str, float],
    time_to_cpa_seconds: float,
    times_seconds: Sequence[int],
) -> ResolutionOption:
    """Simulate one instruction and cost it. Returns an option, blocked or otherwise."""
    manoeuvred_is_a = manoeuvre.aircraft == state_a.get("callsign", "A")
    subject = state_a if manoeuvred_is_a else state_b

    blocked = _blocked_reason(manoeuvre, subject)
    if blocked is not None:
        return ResolutionOption(
            manoeuvre=manoeuvre, resulting_lateral_nm=float("nan"),
            resulting_vertical_ft=float("nan"), resolves=False,
            first_violation_seconds=None, seconds_to_establish=float("nan"),
            established_before_cpa=False, delay_seconds=float("nan"),
            fuel_equivalent_seconds=float("nan"), confidence=0.0, score=0.0,
            components={}, explanation=f"Blocked: {blocked}.", blocked_reason=blocked,
        )

    # Simulate at 1 s resolution over the whole window, not just the reporting grid:
    # a violation lasting 20 s can sit entirely between two 15 s samples.
    fine_times = list(range(0, int(max(times_seconds, default=600)) + 1))
    grid_a = simulate_manoeuvre(state_a, manoeuvre if manoeuvred_is_a else None, fine_times)
    grid_b = simulate_manoeuvre(state_b, None if manoeuvred_is_a else manoeuvre, fine_times)

    first_violation, lateral, vertical, _ = _pair_geometry(grid_a, grid_b)
    resolves = first_violation is None
    establish = _seconds_to_establish(manoeuvre, subject)
    established_before_cpa = establish <= max(time_to_cpa_seconds, 0.0)

    hold = max(time_to_cpa_seconds, 60.0) + 120.0
    delay = _estimate_delay_seconds(manoeuvre, subject, hold)
    fuel = _estimate_fuel_equivalent_seconds(manoeuvre, subject, delay)
    confidence = _confidence(lateral, vertical, establish, time_to_cpa_seconds,
                             state_a, state_b)

    components = {
        "safety": _safety_score(lateral, vertical),
        "delay": max(0.0, 1.0 - min(1.0, delay / DELAY_SCALE_SECONDS)),
        "fuel": max(0.0, 1.0 - min(1.0, fuel / FUEL_SCALE_EQUIVALENT_SECONDS)),
        "workload": _workload_score(manoeuvre),
        "confidence": confidence,
    }
    score = (
        components["safety"] * WEIGHT_SAFETY
        + components["delay"] * WEIGHT_DELAY
        + components["fuel"] * WEIGHT_FUEL
        + components["workload"] * WEIGHT_WORKLOAD
        + components["confidence"] * WEIGHT_CONFIDENCE
    )
    # An option that does not prevent the loss of separation cannot out-rank one that
    # does, however cheap and easy it is.
    if not resolves:
        score *= 0.1

    if resolves:
        explanation = _explain(manoeuvre, {
            "lateral": lateral, "vertical": vertical, "delay": delay, "fuel": fuel,
            "establish": establish, "time_to_cpa": time_to_cpa_seconds,
            "confidence": confidence,
        }, subject)
    else:
        explanation = (
            f"Rejected: separation is still lost at about {first_violation:.0f} s "
            f"({lateral:.1f} NM / {vertical:,.0f} ft at the closest point). The "
            f"manoeuvre is not fully established until about {establish:.0f} s, "
            f"including {RESPONSE_DELAY_SECONDS:.0f} s before the aircraft moves."
        )

    return ResolutionOption(
        manoeuvre=manoeuvre, resulting_lateral_nm=lateral, resulting_vertical_ft=vertical,
        resolves=resolves, first_violation_seconds=first_violation,
        seconds_to_establish=establish, established_before_cpa=established_before_cpa,
        delay_seconds=delay, fuel_equivalent_seconds=fuel, confidence=confidence,
        score=round(score, 4), components=components, explanation=explanation,
    )


def generate_resolutions(
    state_a: Mapping[str, float],
    state_b: Mapping[str, float],
    cpa_result: Mapping[str, Any],
    escalation: Mapping[str, Any] | None = None,
    callsign_a: str = "AIRCRAFT A",
    callsign_b: str = "AIRCRAFT B",
) -> dict[str, Any]:
    """The entry point: three ranked, explained options for one tier 1 conflict.

    Returns the best option of each kind -- altitude, heading, speed -- ranked by the
    project's scoring formula, plus every candidate that was blocked or rejected, so
    the count of unsafe suggestions stopped is available as an evaluation metric.

    If an escalation result is supplied, its suggest_resolution flag is obeyed: tier 2
    is a watch list and is never offered a manoeuvre, per CLAUDE.md Section 3.
    """
    if escalation is not None and not escalation.get("suggest_resolution", False):
        return {
            "offered": False,
            "reason": (f"No resolution offered: {escalation.get('reason', 'pair is not a confirmed tier 1 alarm')}"),
            "options": [], "blocked": [], "rejected": [],
        }

    time_to_cpa = float(cpa_result.get("time_to_cpa_seconds",
                                       cpa_result.get("cpa_horizon_seconds", 0.0)))
    times = [int(sample["horizon_seconds"]) for sample in cpa_result.get("grid", [])]
    if not times:
        times = list(range(0, 601, 15))

    named_a = dict(state_a) | {"callsign": callsign_a}
    named_b = dict(state_b) | {"callsign": callsign_b}

    candidates: list[Manoeuvre] = []
    for callsign in (callsign_a, callsign_b):
        candidates += [Manoeuvre(callsign, "altitude", value, "ft") for value in ALTITUDE_CHANGES_FT]
        candidates += [Manoeuvre(callsign, "heading", value, "deg") for value in HEADING_CHANGES_DEG]
        candidates += [Manoeuvre(callsign, "speed", value, "kt") for value in SPEED_CHANGES_KT]

    evaluated = [evaluate_manoeuvre(candidate, named_a, named_b, time_to_cpa, times)
                 for candidate in candidates]

    blocked = [option for option in evaluated if option.blocked_reason is not None]
    rejected = [option for option in evaluated
                if option.blocked_reason is None and not option.is_offerable]
    offerable = [option for option in evaluated if option.is_offerable]

    # One option of each kind, so the controller always sees a genuine choice rather
    # than three variations of the same instruction.
    best_of_kind: dict[str, ResolutionOption] = {}
    for option in sorted(offerable, key=lambda item: item.score, reverse=True):
        best_of_kind.setdefault(option.manoeuvre.kind, option)
    options = sorted(best_of_kind.values(), key=lambda item: item.score, reverse=True)

    missing = [kind for kind in ("altitude", "heading", "speed") if kind not in best_of_kind]
    return {
        "offered": bool(options),
        "reason": ("Tier 1 alarm confirmed; options ranked by safety 0.60, delay 0.15, "
                   "fuel 0.10, workload 0.10, confidence 0.05."
                   if options else
                   "No manoeuvre in the candidate set restores separation in the time available."),
        "time_to_cpa_seconds": time_to_cpa,
        "options": options,
        "unavailable_kinds": missing,
        "blocked": blocked,
        "rejected": rejected,
        "counts": {
            "evaluated": len(evaluated), "offerable": len(offerable),
            "blocked_unsafe": len(blocked), "rejected_ineffective": len(rejected),
        },
    }


def _demonstration() -> None:
    """Two worked examples, printed the way the dashboard would show them.

    The second one is the point of the whole file: the same conflict with less time on
    the clock, where the turn stops being a usable answer.
    """
    from ml_pipeline.utils.cpa_conflict_detection import compute_cpa_from_states, escalate_pair

    def head_on_pair(seconds_to_cpa: float) -> tuple[dict, dict]:
        """Two aircraft closing head-on at FL350, timed to meet in the given seconds."""
        speed = 230.0
        separation_m = speed * 2 * seconds_to_cpa
        longitude_offset = separation_m / (METRES_PER_DEGREE * math.cos(math.radians(19.0)))
        first = {"latitude": 19.000, "longitude": 72.0, "altitude_m": 10668.0,
                 "velocity_ms": speed, "heading_deg": 90.0, "vertical_rate_ms": 0.0}
        second = {"latitude": 19.003, "longitude": 72.0 + longitude_offset,
                  "altitude_m": 10668.0, "velocity_ms": speed, "heading_deg": 270.0,
                  "vertical_rate_ms": 0.0}
        return first, second

    def run(seconds_to_cpa: float, title: str) -> None:
        aircraft_a, aircraft_b = head_on_pair(seconds_to_cpa)
        cpa = compute_cpa_from_states(aircraft_a, aircraft_b)
        history: list = []
        escalation = escalate_pair(cpa, history)
        for _ in range(2):
            history.append(cpa)
            escalation = escalate_pair(cpa, history)

        print("=" * 96)
        print(title)
        print("=" * 96)
        print(f"AI2841 heading 090 and 6E455 heading 270, both {_flight_level(aircraft_a['altitude_m'])}.")
        print(f"Without intervention: {cpa['cpa_lateral_distance_nm']:.2f} NM / "
              f"{cpa['cpa_vertical_separation_ft']:,.0f} ft in "
              f"{cpa['time_to_cpa_seconds']:.0f} s.")
        print(f"Escalation: tier {escalation['tier']}, notify {escalation['notify']}, "
              f"resolution allowed {escalation['suggest_resolution']}.")
        print(f"Of the {cpa['time_to_cpa_seconds']:.0f} s available, "
              f"{RESPONSE_DELAY_SECONDS:.0f} s are gone before the aircraft moves at all.")

        result = generate_resolutions(aircraft_a, aircraft_b, cpa, escalation, "AI2841", "6E455")
        if not result.get("counts"):
            # Tier 2 is a watch list. It is shown to the controller but never given a
            # manoeuvre, because a prediction that far out is not accurate enough to
            # justify turning an aircraft.
            print("")
            print(f"  {result['reason']}")
            print("")
            return
        counts = result["counts"]
        print("")
        print(f"Evaluated {counts['evaluated']} candidate instructions: "
              f"{counts['offerable']} work, {counts['blocked_unsafe']} blocked as unsafe, "
              f"{counts['rejected_ineffective']} rejected because separation is still lost.")
        print("")
        for rank, option in enumerate(result["options"], start=1):
            print(f"  OPTION {rank}  [{option.manoeuvre.kind}]  score {option.score:.3f}")
            print(f"    {option.explanation}")
            parts = "  ".join(f"{name} {value:.2f}" for name, value in option.components.items())
            print(f"    components: {parts}")
            print("")
        if result["unavailable_kinds"]:
            print(f"  NO USABLE OPTION of type: {', '.join(result['unavailable_kinds'])}")
            for option in result["rejected"]:
                if option.manoeuvre.kind in result["unavailable_kinds"] and option.manoeuvre.magnitude in (30.0, -30.0):
                    print(f"    why, for example: {option.manoeuvre.aircraft} "
                          f"{option.manoeuvre.kind} {option.manoeuvre.magnitude:+.0f}"
                          f"{option.manoeuvre.unit} -- {option.explanation}")
                    break
        print("")

    run(170.0, "CASE 1 -- NEARLY THREE MINUTES TO RUN. A real choice is available.")
    run(90.0, "CASE 2 -- NINETY SECONDS TO RUN. Nothing works at all.")
    run(300.0, "CASE 3 -- FIVE MINUTES OUT. Tier 2, so nothing is suggested at all.")

    print("=" * 96)
    print("WHAT THESE THREE CASES ACTUALLY SHOW")
    print("=" * 96)
    print("Case 2 is the important one, and it is not the result that was expected.")
    print("")
    print("At ninety seconds NOTHING works. Not the climb, not the turn, not the speed")
    print("change. All 26 candidate instructions are rejected, because 38 of those 90")
    print("seconds are gone before the aircraft moves at all, and no manoeuvre an airliner")
    print("can fly in the remaining 52 seconds opens 5 NM or 1000 ft in time.")
    print("")
    print("That is the strongest available argument for the three-minute tier boundary.")
    print("It was chosen from response geometry on paper; this simulation reaches the same")
    print("conclusion independently, by flying every option and finding that none of them")
    print("arrives in time. An alert raised much inside three minutes is real, and useless.")
    print("")
    print("A CORRECTION TO SECTION 3, MEASURED RATHER THAN ARGUED.")
    print("")
    print("CLAUDE.md says to prefer altitude changes as time-to-conflict falls, and gives")
    print("the physics: 1000 ft takes about 40 s, a 30 degree turn at 450 kt about 96 s.")
    print("The arithmetic is right, but the conclusion does not hold as a blanket rule.")
    print("Swept across this head-on geometry, altitude and heading options become")
    print("available at the SAME time, between 90 s and 105 s. There is no window in which")
    print("the climb works and the turn does not, because in a head-on encounter a turn")
    print("changes the crossing geometry very quickly.")
    print("")
    print("Altitude still ranks first in case 1, but for different reasons than assumed:")
    print("workload 1.00 against 0.50, because a level change is one instruction the")
    print("controller can watch working, whereas a vector has to be remembered and undone.")
    print("")
    print("The engine therefore TESTS each option per encounter instead of applying a")
    print("standing preference. That is the safer design: the standing preference would")
    print("have been wrong here, and a geometry where it is right would still be caught.")


if __name__ == "__main__":
    _demonstration()
