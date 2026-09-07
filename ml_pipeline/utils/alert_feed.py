"""What the controller actually sees, and how often they are interrupted.

The detection chain (server/app/ml/inference.py) answers one question per pair per
update: is this pair a confirmed conflict? It has no memory. Two consequences, both
measured on this project's own data:

  1. A pair that stays in conflict geometry re-alerts on every update. Measured on two
     real one-hour OpenSky sessions, the same encounter produced 9.7 and 9.9 alert
     messages for every one distinct encounter -- 297 messages an hour for 30 real
     encounters, and 145 for 15.
  2. Everything arrives at the same visual weight. On the held-out test split, alerts
     scoring below 0.25 were 275 rows containing 11 real conflicts (4% precision),
     competing for attention with 332 rows at 0.80+ that were 72% real.

This module sits between the detection chain and the dashboard and fixes both without
removing anything. CLAUDE.md Section 12 requires duplicate suppression and severity
ranking; nothing implemented them until now.

THE GUARANTEE, and it is structural rather than tested-for
----------------------------------------------------------
Every pair the escalation rule confirms appears in `active`, on every update, without
exception. This module has no code path that removes a pair from `active`.

What it changes is only:

  * `is_new_notification` -- whether the pair raises a NEW interruption this update. A
    repeat of something already on screen is not a new interruption. Anything that gets
    WORSE always re-fires; see `_notification_decision`, where every escalation test is
    ordered ahead of every suppression test.
  * `display` -- whether the row is rendered prominently or collapsed into a counted
    group the controller can expand. A collapsed row is still in `active` and still
    carries its full assessment.

So a false conflict can stop interrupting, which is the point. A real conflict cannot
stop being reported, because reporting is `active` and nothing filters `active`.

The frontend contract that makes the guarantee real: render `active` in full. Use
`attention` to decide what is prominent and `notifications` to decide what makes a
sound. Never render `notifications` alone -- that would turn a display rule into a
detection rule, which is exactly what this module exists to avoid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# Severity ranking, so "did this get worse" is a comparison rather than a table of
# special cases. The names come from classify_conflict().
SEVERITY_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# How long a confirmed pair may stay quiet before it is announced again. Not a filter:
# the row is on screen throughout. This exists so a long encounter refreshes rather
# than going stale, and so an acknowledged alert cannot be quietly forgotten.
REALERT_SECONDS = 120.0

# A pair that closes by this much since it was last announced is announced again, even
# if nothing else changed. One nautical mile is a fifth of the legal lateral minimum,
# so this fires well before the situation is critical.
REALERT_LATERAL_CLOSE_NM = 1.0

# The same idea applied to the stated probability.
REALERT_PROBABILITY_STEP = 0.15

# Crossing any of these times-to-closest-approach announces the pair again. These are
# the moments where the controller's options actually change: below 120 s a turn is
# marginal, and below 60 s nothing an airliner can fly opens 5 NM in time -- measured
# in resolution_engine.py, where at 90 s all 26 candidate instructions are rejected.
REALERT_TIME_BOUNDARIES_SECONDS = (120.0, 60.0, 30.0)

# A pair absent for this long is forgotten, so a genuinely new encounter between the
# same two aircraft later is announced as new rather than mistaken for a repeat.
FORGET_SECONDS = 300.0

# Below this RAW classifier probability a tier 2 pair is collapsed into a counted group
# instead of taking its own row. Raw rather than calibrated, to match the saved decision
# threshold, which is 0.0851 in raw space. Measured on the test split: the 0.085-0.25
# band is 275 alerts holding 11 real conflicts. Every one of those 11 is tier 2, and the
# guards in `_is_low_confidence` release a pair the moment it becomes tier 1, picks up a
# rule-path conflict, or reaches high severity.
LOW_CONFIDENCE_RAW_PROBABILITY = 0.25

# How many rows the dashboard highlights. Everything else is still rendered; this only
# decides what sits at the top. It is never a cut.
ATTENTION_ROWS = 8


def _severity_rank(name: str | None) -> int:
    return SEVERITY_ORDER.get(str(name or "none").lower(), 0)


@dataclass
class _Shown:
    """What was last announced for one pair, so a repeat can be recognised."""

    first_seen: float
    last_notified: float
    last_seen: float
    tier: int
    severity_rank: int
    lateral_nm: float
    probability: float
    time_to_cpa_seconds: float
    suggest_resolution: bool
    resolution_signature: tuple = ()
    notifications: int = 0
    updates_since_notified: int = 0


def _resolution_signature(assessment: Mapping[str, Any]) -> tuple:
    """The manoeuvre types currently offered, as a comparable value.

    If the set of available ways out changes -- and especially if it empties -- the
    controller needs telling, because their options have just changed.
    """
    resolution = assessment.get("resolution") or {}
    if not resolution.get("offered"):
        return ()
    return tuple(sorted(str(option.get("manoeuvre_type"))
                        for option in resolution.get("options", []) or []))


def _entry_from_assessment(pair: Any, assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten one assess_pair result into the row the dashboard renders.

    The whole assessment is carried through under "assessment", so nothing this module
    does can lose detail the detail drawer needs.
    """
    escalation = assessment.get("escalation") or {}
    rule = assessment.get("rule") or {}
    classifier = assessment.get("classifier") or {}
    resolution = assessment.get("resolution") or {}
    return {
        "pair": pair,
        "tier": int(escalation.get("tier", 0)),
        "tier_name": escalation.get("tier_name"),
        "severity": rule.get("severity", "none"),
        "rule_is_conflict": bool(rule.get("is_conflict", False)),
        "time_to_cpa_seconds": float(escalation.get("time_to_cpa_seconds", 0.0)),
        "cpa_lateral_distance_nm": float(rule.get("cpa_lateral_distance_nm", float("inf"))),
        "cpa_vertical_separation_ft": float(rule.get("cpa_vertical_separation_ft", float("inf"))),
        "probability": float(escalation.get("probability", 0.0)),
        "classifier_raw_probability": (float(classifier["raw_probability"])
                                       if "raw_probability" in classifier else None),
        "classifier_conflict_probability": (float(classifier["conflict_probability"])
                                            if "conflict_probability" in classifier else None),
        "suggest_resolution": bool(escalation.get("suggest_resolution", False)),
        "resolution_offered": bool(resolution.get("offered", False)),
        "resolution_option_count": len(resolution.get("options", []) or []),
        "reason": escalation.get("reason", ""),
        "assessment": assessment,
    }


def _is_low_confidence(entry: Mapping[str, Any], cut: float) -> bool:
    """Whether this row may be collapsed into the counted group.

    Every condition here is a release valve, not a filter: a pair leaves the group the
    moment any of them stops holding, and leaving the group announces it through
    `_notification_decision`. The rule-path guard is the important one -- the
    deterministic CPA check is the safety net (CLAUDE.md Section 13), so a pair it calls
    a conflict is never collapsed however low the classifier scores it.
    """
    probability = entry["classifier_raw_probability"]
    return (
        entry["tier"] == 2
        and not entry["rule_is_conflict"]
        and _severity_rank(entry["severity"]) < SEVERITY_ORDER["high"]
        and not entry["suggest_resolution"]
        and probability is not None
        and probability < cut
    )


def _notification_decision(entry: Mapping[str, Any], previous: _Shown | None,
                           now: float, realert_seconds: float) -> tuple[bool, str]:
    """Whether this pair raises a NEW interruption, and why.

    Ordered so every escalation test runs before any suppression test. Nothing below can
    veto a decision made above it, which is what stops a worsening situation from being
    mistaken for a repeat.
    """
    if previous is None:
        return True, "New conflict."

    if entry["tier"] < previous.tier:
        return True, (f"Escalated from tier {previous.tier} to tier {entry['tier']}: closest "
                      f"approach is now {entry['time_to_cpa_seconds']:.0f} s away.")

    if _severity_rank(entry["severity"]) > previous.severity_rank:
        return True, f"Severity rose to {entry['severity']}."

    if entry["suggest_resolution"] and not previous.suggest_resolution:
        return True, "Resolution options are now available for this pair."

    signature = _resolution_signature(entry["assessment"])
    if signature != previous.resolution_signature:
        if not signature and previous.resolution_signature:
            return True, "No manoeuvre now restores separation in the time available."
        return True, "The available resolution options changed."

    for boundary in REALERT_TIME_BOUNDARIES_SECONDS:
        if entry["time_to_cpa_seconds"] <= boundary < previous.time_to_cpa_seconds:
            return True, f"Now inside {boundary:.0f} s to closest approach."

    closed = previous.lateral_nm - entry["cpa_lateral_distance_nm"]
    if closed >= REALERT_LATERAL_CLOSE_NM:
        return True, (f"Predicted closest approach has closed by {closed:.1f} NM to "
                      f"{entry['cpa_lateral_distance_nm']:.2f} NM.")

    if entry["probability"] - previous.probability >= REALERT_PROBABILITY_STEP:
        return True, f"Conflict probability rose to {entry['probability']:.2f}."

    quiet = now - previous.last_notified
    if quiet >= realert_seconds:
        return True, f"Still active after {quiet / 60.0:.0f} min; announced again."

    return False, (f"Already shown {quiet:.0f} s ago and nothing has worsened; the pair "
                   f"stays on the active list.")


def _rank_key(entry: Mapping[str, Any]) -> tuple:
    """Most urgent first: alarms before the watch list, then severity, then time."""
    return (
        entry["tier"] if entry["tier"] > 0 else 99,
        -_severity_rank(entry["severity"]),
        entry["time_to_cpa_seconds"],
        -entry["probability"],
    )


@dataclass
class AlertFeed:
    """Per-pair memory across updates. One instance per controller session.

    Hold it for the life of the session and call `update` once per surveillance update,
    with every pair the detection chain assessed.
    """

    realert_seconds: float = REALERT_SECONDS
    low_confidence_probability: float = LOW_CONFIDENCE_RAW_PROBABILITY
    forget_seconds: float = FORGET_SECONDS
    attention_rows: int = ATTENTION_ROWS
    _shown: dict[Any, _Shown] = field(default_factory=dict)
    _clock: float = 0.0

    def update(self, assessments: Mapping[Any, Mapping[str, Any]],
               now: float | None = None) -> dict[str, Any]:
        """One surveillance update. Returns everything the dashboard needs.

        assessments maps a pair key -- anything hashable and stable; a sorted pair of
        callsigns works -- to that pair's assess_pair result.

        The returned dict:
          active         every confirmed pair, ranked, nothing removed. Render all of it.
          attention      the most urgent slice of active, for prominence only.
          notifications  the subset raising a new interruption now. Sound this and
                         nothing else. Never render this instead of active.
          low_confidence the collapsed group: a count plus the rows, every one of which
                         is also in active.
          suppressed     what was held back and why, for the audit log.
        """
        now = float(self._clock + 1.0 if now is None else now)
        self._clock = now

        active: list[dict[str, Any]] = []
        notifications: list[dict[str, Any]] = []
        suppressed: list[dict[str, Any]] = []
        waiting = 0

        for pair, assessment in assessments.items():
            escalation = assessment.get("escalation") or {}
            if not escalation.get("notify", False):
                # Not this module's decision. escalate_pair has not confirmed the pair
                # yet -- the three-consecutive-updates rule, or the tier probability
                # threshold. Left exactly as the detection chain left it.
                waiting += 1
                continue

            entry = _entry_from_assessment(pair, assessment)
            previous = self._shown.get(pair)
            if previous is not None and now - previous.last_seen > self.forget_seconds:
                previous = None

            low_confidence = _is_low_confidence(entry, self.low_confidence_probability)
            notify, reason = _notification_decision(entry, previous, now, self.realert_seconds)
            # A collapsed row does not interrupt. It cannot hide a real conflict: every
            # guard in _is_low_confidence releases the pair before it matters, and the
            # row is on the active list throughout either way.
            if low_confidence and notify:
                notify = False
                reason = ("Low confidence and still ten minutes out; listed in the collapsed "
                          "group rather than announced.")

            entry["display"] = "low_confidence" if low_confidence else "alert"
            entry["is_new_notification"] = notify
            entry["notification_reason"] = reason
            entry["first_seen"] = previous.first_seen if previous else now
            entry["notifications_so_far"] = ((previous.notifications if previous else 0)
                                             + (1 if notify else 0))
            entry["updates_since_notified"] = 0 if notify else (
                previous.updates_since_notified + 1 if previous else 0)
            active.append(entry)
            if notify:
                notifications.append(entry)
            else:
                suppressed.append({"pair": pair, "reason": reason, "display": entry["display"],
                                   "tier": entry["tier"], "severity": entry["severity"]})

            self._shown[pair] = _Shown(
                first_seen=entry["first_seen"],
                last_notified=now if notify else (previous.last_notified if previous else now),
                last_seen=now,
                tier=entry["tier"],
                severity_rank=_severity_rank(entry["severity"]),
                lateral_nm=entry["cpa_lateral_distance_nm"],
                probability=entry["probability"],
                time_to_cpa_seconds=entry["time_to_cpa_seconds"],
                suggest_resolution=entry["suggest_resolution"],
                resolution_signature=_resolution_signature(assessment),
                notifications=entry["notifications_so_far"],
                updates_since_notified=entry["updates_since_notified"],
            )

        retired = [pair for pair, state in self._shown.items()
                   if now - state.last_seen > self.forget_seconds]
        for pair in retired:
            del self._shown[pair]

        active.sort(key=_rank_key)
        notifications.sort(key=_rank_key)
        collapsed = [entry for entry in active if entry["display"] == "low_confidence"]

        return {
            "active": active,
            "attention": active[: self.attention_rows],
            "notifications": notifications,
            "low_confidence": {
                "count": len(collapsed),
                "pairs": [entry["pair"] for entry in collapsed],
                "rows": collapsed,
                "reason": (f"{len(collapsed)} lower-confidence watch-list pairs, collapsed to "
                           f"keep the urgent ones readable. All are on the active list."),
            },
            "suppressed": suppressed,
            "counts": {
                "assessed": len(assessments),
                "awaiting_confirmation": waiting,
                "active": len(active),
                "new_notifications": len(notifications),
                "repeats_suppressed": len(suppressed) - len(collapsed),
                "collapsed_low_confidence": len(collapsed),
                "tier_1": sum(1 for entry in active if entry["tier"] == 1),
                "tier_2": sum(1 for entry in active if entry["tier"] == 2),
                "retired": len(retired),
            },
            "retired": retired,
            "guarantee": ("Every confirmed pair is on the active list. Suppression only "
                          "affects whether a pair raises a new interruption, never whether "
                          "it is reported."),
        }
