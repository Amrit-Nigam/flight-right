"""A heard (or known) ATC clearance, and what it rules out among the candidate paths.

This is the seam between the voice chain and the trajectory chain (plan Phase 7.2).
Everything upstream of it -- speech-to-text, extraction, callsign matching (plan Phases
4-6) -- has one job: produce a `Clearance`. Everything downstream consumes a `Clearance`
and never needs to know where it came from. So the voice chain can be added later
without touching the trajectory, conflict or display code, and in the meantime a
`Clearance` can come from:

  * "oracle"  -- read out of the truth, for the upper-bound measurement (Phase 7.1)
  * "manual"  -- typed in through the API, for the demo and for testing
  * "asr:<model id>" -- the speech chain, once it exists

WHAT A CLEARANCE DOES. It never picks a path. It ELIMINATES candidate paths that
contradict it and renormalises the rest (plan 7.2: "voice does not pick the right path,
it eliminates the wrong ones"). If it would eliminate every candidate, it eliminates
none and says so. An empty fan would silently switch off every model-based check for
that aircraft, which is the dangerous direction.

THE TOLERANCES ARE OUR OWN DESIGN, not taken from a standard. We checked for one: ICAO
does not mandate a universal minimum climb or descent rate. Some states define a
"standard rate" (Australia's AIP: at least 500 ft/min), and EASA SERA.8015 limits the
rate in the last 1,000 ft before the cleared level. So the values below are justified by
measurement instead. `ml_pipeline/utils/oracle_clearance.py` applies each rule to the
aircraft's TRUE future, derived from its own truth, and reports how often the truth itself
would have been eliminated. That rate must stay near zero.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

FT_PER_M = 3.28084

# Actions the extractor (Phase 6) will emit. DIRECT needs a fix position and SPEED needs
# the wind to turn an airspeed into a ground track, so the filter accepts both but
# eliminates nothing for them yet. They are recorded, not acted on.
ACTIONS = ("CLIMB", "DESCEND", "TURN", "DIRECT", "SPEED")
FILTERED_ACTIONS = ("CLIMB", "DESCEND", "TURN")

# A candidate cleared to change level must have moved at least this far toward the
# cleared level by ten minutes, or be within LEVEL_TOLERANCE_FT of it. 1,000 ft is the
# vertical separation standard, so "has not moved even one separation step toward the
# level in ten minutes" is what counts as not obeying the clearance.
MIN_PROGRESS_FT = 1_000.0
# How far past the cleared level a candidate may finish, and how far the wrong way it may
# drift, before it counts as contradicting the clearance.
LEVEL_TOLERANCE_FT = 1_000.0
# A heading clearance keeps candidates whose final track (five to ten minutes) lies within
# this many degrees of the cleared heading. Wide, because a track over the ground is not a
# heading (wind), and because the model's candidates are route shapes, not exact tracks.
HEADING_TOLERANCE_DEG = 45.0
# Plausibility checks on the value itself, so a mis-heard "descend flight level 3100"
# cannot eliminate anything.
LEVEL_RANGE_FT = (1_000.0, 60_000.0)
SPEED_RANGE_KT = (100.0, 600.0)
DEFAULT_VALID_SECONDS = 600.0


@dataclass(frozen=True)
class Clearance:
    """One instruction to one aircraft, from whatever source.

    `value` is feet for CLIMB/DESCEND, degrees for TURN, knots for SPEED, and a fix name
    for DIRECT (carried in `fix`). `confidence` is 0-1 and comes from the source: 1.0 for
    oracle and manual entries, and the extractor's own uncertainty-based score for ASR.
    """

    icao24: str
    action: str
    value: float | None = None
    callsign: str | None = None
    fix: str | None = None
    confidence: float = 1.0
    source: str = "manual"
    issued_at: float = 0.0
    valid_seconds: float = DEFAULT_VALID_SECONDS
    transcription_id: int | None = None
    notes: dict[str, Any] = field(default_factory=dict)

    def problems(self) -> list[str]:
        """Why this clearance must not be used, or [] if it may."""
        issues = []
        if self.action not in ACTIONS:
            issues.append(f"unknown action {self.action!r}")
        if not self.icao24:
            issues.append("no matched aircraft (icao24)")
        if not 0.0 <= float(self.confidence) <= 1.0:
            issues.append("confidence outside 0-1")
        if self.action in ("CLIMB", "DESCEND"):
            if self.value is None or not LEVEL_RANGE_FT[0] <= float(self.value) <= LEVEL_RANGE_FT[1]:
                issues.append(f"level {self.value} ft outside {LEVEL_RANGE_FT}")
        if self.action == "TURN" and (self.value is None or not 0.0 <= float(self.value) <= 360.0):
            issues.append(f"heading {self.value} outside 0-360")
        if self.action == "SPEED" and (self.value is None or not SPEED_RANGE_KT[0] <= float(self.value) <= SPEED_RANGE_KT[1]):
            issues.append(f"speed {self.value} kt outside {SPEED_RANGE_KT}")
        if self.action == "DIRECT" and not self.fix:
            issues.append("DIRECT without a fix")
        return issues

    def active(self, now: float) -> bool:
        return self.issued_at <= now <= self.issued_at + self.valid_seconds

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bearing_deg(start: np.ndarray, end: np.ndarray) -> float:
    """Initial bearing from start to end (lat, lon, ...), degrees clockwise from north."""
    lat1, lat2 = math.radians(float(start[0])), math.radians(float(end[0]))
    d_lon = math.radians(float(end[1]) - float(start[1]))
    y = math.sin(d_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return math.degrees(math.atan2(y, x)) % 360.0


def _angle_between(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def path_obeys(path: np.ndarray, current_altitude_m: float, clearance: Clearance) -> bool | None:
    """Does one path (4 horizons x lat/lon/alt_m) obey the clearance? None = cannot judge.

    Judged at the ten-minute horizon (index 3), with the five-minute point (index 2) for
    the final track. The same function is applied to candidate paths and, in the oracle
    self-check, to the aircraft's true path.
    """
    if clearance.action in ("CLIMB", "DESCEND"):
        now_ft, final_ft = current_altitude_m * FT_PER_M, float(path[3, 2]) * FT_PER_M
        target_ft = float(clearance.value)
        direction = 1.0 if clearance.action == "CLIMB" else -1.0
        if (target_ft - now_ft) * direction <= 0:
            return None  # already at or past the level: the clearance says nothing new
        needed = min(abs(target_ft - now_ft), MIN_PROGRESS_FT)
        progressed = (final_ft - now_ft) * direction
        overshoot = (final_ft - target_ft) * direction
        return progressed >= needed - 1e-9 and overshoot <= LEVEL_TOLERANCE_FT
    if clearance.action == "TURN":
        track = _bearing_deg(path[2], path[3])
        return _angle_between(track, float(clearance.value)) <= HEADING_TOLERANCE_DEG
    return None  # DIRECT / SPEED: recorded, not yet filterable


def cap_at_level(positions: np.ndarray, current_altitude_m: float, clearance: Clearance) -> tuple[np.ndarray, dict[str, Any]]:
    """Use a level clearance the way EUROCONTROL STCA Option E uses a cleared flight level.

    Source: EUROCONTROL Guidelines for STCA, Part III, Option E -- "Cleared and/or
    Selected Flight Level used for Vertical Prediction". No candidate is eliminated.
    Each candidate's predicted altitude is simply not allowed to pass through the level
    the aircraft was cleared to. An aircraft cleared to FL130 does not descend through it.

    Measured 25 Sep 2026 (oracle_clearance.py): ELIMINATING candidates by a level
    clearance lost the candidate closest to the truth for 9.2% of arrivals, because a
    candidate's horizontal and vertical parts come as one route shape. Capping keeps the
    horizontal guess and corrects only the height.
    """
    report: dict[str, Any] = {"clearance": clearance.to_dict()}
    issues = clearance.problems()
    if issues or clearance.action not in ("CLIMB", "DESCEND"):
        report.update(applied=False, reason="; ".join(issues) or f"{clearance.action} is not a level clearance")
        return positions, report
    target_m = float(clearance.value) / FT_PER_M
    direction = 1.0 if clearance.action == "CLIMB" else -1.0
    if (target_m - current_altitude_m) * direction <= 0:
        report.update(applied=False, reason="the aircraft is already at or past the cleared level")
        return positions, report
    capped = positions.copy()
    altitude = capped[..., 2]
    capped[..., 2] = np.minimum(altitude, target_m) if direction > 0 else np.maximum(altitude, target_m)
    changed = int(np.any(np.abs(capped[..., 2] - positions[..., 2]) > 1e-6, axis=-1).sum())
    report.update(applied=True, candidates_capped=changed,
                  reason=f"{changed} of {len(positions)} candidate paths were predicted to pass the cleared level")
    return capped, report


def constrain(probabilities: np.ndarray, positions: np.ndarray, current_altitude_m: float,
              clearance: Clearance) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Eliminate the candidate paths that contradict `clearance`.

    probabilities (K,), positions (K, 4, 3) for ONE aircraft. Returns the surviving
    probabilities (renormalised), their positions, and a report saying what happened and
    why. Never returns an empty fan.
    """
    report: dict[str, Any] = {"clearance": clearance.to_dict(), "candidates_before": int(len(probabilities))}
    issues = clearance.problems()
    if issues:
        report.update(applied=False, reason="clearance rejected: " + "; ".join(issues))
        return probabilities, positions, report
    if clearance.action not in FILTERED_ACTIONS:
        report.update(applied=False, reason=f"{clearance.action} is recorded but not yet used to filter paths")
        return probabilities, positions, report
    verdicts = [path_obeys(positions[k], current_altitude_m, clearance) for k in range(len(probabilities))]
    if all(v is None for v in verdicts):
        report.update(applied=False, reason="the aircraft is already at or past the cleared level")
        return probabilities, positions, report
    keep = np.array([v is not False for v in verdicts])
    if not keep.any():
        report.update(applied=False, reason="the clearance contradicts every candidate path; fan left unchanged")
        return probabilities, positions, report
    kept = probabilities[keep] / probabilities[keep].sum()
    report.update(applied=True, candidates_after=int(keep.sum()), kept_indices=np.flatnonzero(keep).tolist(),
                  probability_eliminated=float(probabilities[~keep].sum()),
                  reason=f"{int((~keep).sum())} of {len(keep)} candidate paths contradict the clearance")
    return kept, positions[keep], report


def apply_clearance(probabilities: np.ndarray, positions: np.ndarray, current_altitude_m: float,
                    clearance: Clearance) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """What the running system does with a clearance. Returns (probabilities, positions,
    kept_indices, report).

    Chosen by the Phase 7.1 oracle measurement (oracle_clearance.py, 25 Sep 2026, test
    arrivals at ten minutes, UPPER BOUND with perfect recognition):
      * a LEVEL clearance CAPS altitude (STCA Option E): best-of-5 within 5 NM AND
        1,000 ft 43.4% -> 53.9%, nothing eliminated. Eliminating by level instead
        cost 5.6 points of horizontal best-of-5 and lost the closest candidate 9.2% of
        the time, so level clearances are never used to eliminate.
      * a HEADING clearance ELIMINATES contradicting candidates: top-1 within 5 NM
        42.8% -> 45.1%, best-of-5 unchanged, closest candidate lost 1.7%.
      * DIRECT and SPEED are recorded but change nothing yet.
    """
    everything = np.arange(len(probabilities))
    if clearance.action in ("CLIMB", "DESCEND"):
        capped, report = cap_at_level(positions, current_altitude_m, clearance)
        return probabilities, capped, everything, report
    kept_probabilities, kept_positions, report = constrain(probabilities, positions, current_altitude_m, clearance)
    kept = np.array(report.get("kept_indices", everything), dtype=int)
    return kept_probabilities, kept_positions, kept, report
