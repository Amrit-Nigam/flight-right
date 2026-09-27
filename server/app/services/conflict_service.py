"""Run the full model chain over the current airspace and decide what the controller sees.

For every pair of aircraft that could plausibly conflict, this runs
`ConflictEngine.assess_pair` - the deterministic CPA rule always, then the multi-path
probability, the calibrated XGBoost classifier with its SHAP explanation, the tier and
anti-flicker escalation, and Model 3's ranked resolutions - and then passes the results
through `AlertFeed`, which decides what interrupts and what is merely listed.

Three things here are load-bearing and easy to get wrong:

  * **The en-route floor is applied here.** Conflict detection is en-route only
    (CLAUDE.md, 30 Aug 2026): applying the 5 NM rule to approach traffic flagged
    something in 91-94% of all snapshots, because landing aircraft are legitimately
    close together. The training data was filtered this way; until now inference was
    not, which was a real gap.
  * **Pairs are pre-filtered geometrically before any model runs.** Two aircraft 200 NM
    apart cannot reach the alert volume within ten minutes, and assessing every possible
    pair is quadratic.
  * **Pair history is kept across updates**, because the three-consecutive-updates rule
    that stops a single bad position report raising an alarm needs it.
"""

from __future__ import annotations

import logging
import math
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import (CONFLICT_MIN_ALTITUDE_FT, CONFLICT_MIN_VELOCITY_MS,
                      MAX_PAIRS_PER_UPDATE, PAIR_PREFILTER_FT, PAIR_PREFILTER_NM,
                      PROJECT_ROOT)
from .clearance_service import clearance_service
from .intent_service import intent_service
from .normalizer import to_engine_state

sys.path.insert(0, str(PROJECT_ROOT))
from ml_pipeline.utils.alert_feed import AlertFeed          # noqa: E402
from ..ml.inference import ConflictEngine                   # noqa: E402

log = logging.getLogger("flightright.conflicts")

NM_PER_DEGREE = 60.0
METRES_PER_DEGREE = 111_320.0
PAIR_HISTORY_LENGTH = 12


def _separation_nm(a: dict, b: dict) -> float:
    north = (a["lat"] - b["lat"]) * METRES_PER_DEGREE
    east = (a["lng"] - b["lng"]) * METRES_PER_DEGREE * math.cos(math.radians(a["lat"]))
    return math.hypot(north, east) / 1852.0


@dataclass
class ConflictService:
    engine: ConflictEngine | None = None
    feed: AlertFeed = field(default_factory=AlertFeed)
    pair_histories: dict[tuple, list] = field(default_factory=dict)
    last_result: dict = field(default_factory=dict)
    last_duration_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def load(self) -> None:
        if self.engine is None:
            self.engine = ConflictEngine.load()
            log.info("Conflict engine loaded: %s", self.engine.status())

    # ------------------------------------------------------------------ eligibility
    @staticmethod
    def eligible(aircraft: dict) -> bool:
        """En-route traffic only. See the module docstring for the measurement."""
        return (aircraft.get("altitudeFt", 0) >= CONFLICT_MIN_ALTITUDE_FT
                and aircraft.get("velocityMs", 0) > CONFLICT_MIN_VELOCITY_MS
                and not aircraft.get("onGround"))

    def candidate_pairs(self, histories: dict[str, list[dict]]) -> list[tuple]:
        """Pairs close enough to be worth assessing, closest first."""
        current = {key: window[-1] for key, window in histories.items()
                   if window and self.eligible(window[-1])}
        keys = sorted(current)
        pairs = []
        for i, key_a in enumerate(keys):
            a = current[key_a]
            for key_b in keys[i + 1:]:
                b = current[key_b]
                if abs(a["altitudeFt"] - b["altitudeFt"]) >= PAIR_PREFILTER_FT:
                    continue
                separation = _separation_nm(a, b)
                if separation >= PAIR_PREFILTER_NM:
                    continue
                pairs.append((separation, key_a, key_b))
        pairs.sort()
        return pairs[:MAX_PAIRS_PER_UPDATE]

    # ------------------------------------------------------------------ assessment
    def assess(self, histories: dict[str, list[dict]]) -> dict:
        """One full pass: every candidate pair through the chain, then the alert feed."""
        self.load()
        started = time.perf_counter()
        pairs = self.candidate_pairs(histories)
        assessments: dict[tuple, dict] = {}
        skipped = 0

        # The multi-path model is asked once for the whole airspace rather than once per
        # pair. sklearn's HistGradientBoosting walks 40 patterns x 300 trees on every
        # call regardless of how many rows it is given, so per-pair prediction cost about
        # 3.0 s per pair here - over 45 s for a 30-pair update, against a ten-second
        # budget. One batched call produces the identical result.
        needed = {key for _, a, b in pairs for key in (a, b)}
        # Model 3's secondary-conflict ("domino") check needs every OTHER aircraft near
        # the pair, not just the two in it, so the eligible traffic is converted too.
        # Until 21 Sep this was never passed and the check ran on an empty list in
        # production -- it worked only inside verify_pipeline.py.
        eligible_keys = {key for key, window in histories.items()
                         if window and self.eligible(window[-1]) and len(window) >= 10}
        engine_histories = {key: [to_engine_state(state) for state in histories[key]]
                            for key in needed | eligible_keys}
        # Known clearances (manual today, heard by the speech chain later) adjust the
        # candidate paths of the aircraft they apply to. Keys are icao24, as here.
        in_force = {key: value for key, value in clearance_service.in_force().items() if key in engine_histories}
        candidates = self.engine.multipath_candidates(engine_histories, clearances=in_force)
        current_states = {key: window[-1] for key, window in histories.items()
                          if key in eligible_keys}

        for _, key_a, key_b in pairs:
            history_a = engine_histories[key_a]
            history_b = engine_histories[key_b]
            if len(history_a) < 10 or len(history_b) < 10:
                skipped += 1
                continue
            callsign_a = histories[key_a][-1]["callsign"]
            callsign_b = histories[key_b][-1]["callsign"]
            pair_key = tuple(sorted((callsign_a, callsign_b)))
            previous = self.pair_histories.get(pair_key, [])
            # Everything else eligible and near enough to either aircraft to be put at
            # risk by a manoeuvre aimed at resolving this pair.
            traffic = []
            for key in eligible_keys:
                if key in (key_a, key_b):
                    continue
                other = current_states[key]
                near = (_separation_nm(current_states.get(key_a, other), other) < PAIR_PREFILTER_NM
                        or _separation_nm(current_states.get(key_b, other), other) < PAIR_PREFILTER_NM)
                if near:
                    traffic.append({"callsign": histories[key][-1]["callsign"],
                                    "history": engine_histories[key],
                                    "candidates": candidates.get(key)})
            try:
                state_a, state_b = histories[key_a][-1], histories[key_b][-1]
                result = self.engine.assess_pair(
                    history_a, history_b, previous, traffic=traffic,
                    candidates_a=candidates.get(key_a), candidates_b=candidates.get(key_b),
                    selected_a_ft=intent_service.selected_altitude_ft(key_a, state_a.get("timePosition")),
                    selected_b_ft=intent_service.selected_altitude_ft(key_b, state_b.get("timePosition")))
            except Exception as failure:                     # noqa: BLE001
                log.exception("assess_pair failed for %s: %s", pair_key, failure)
                continue
            result["callsigns"] = [callsign_a, callsign_b]
            self.pair_histories[pair_key] = (previous + [result])[-PAIR_HISTORY_LENGTH:]
            assessments[pair_key] = result

        # Forget pairs that have stopped appearing, so state does not accumulate.
        live_keys = set(assessments)
        for key in [k for k in self.pair_histories if k not in live_keys]:
            self.pair_histories[key] = self.pair_histories[key][-2:]
            if not self.pair_histories[key]:
                del self.pair_histories[key]

        feed_output = self.feed.update(assessments, now=time.time())
        self.last_duration_ms = (time.perf_counter() - started) * 1000.0

        with self._lock:
            self.last_result = {
                "ok": True,
                "pairsConsidered": len(pairs),
                "pairsAssessed": len(assessments),
                "clearancesInForce": {key: [c.to_dict() for c in value] for key, value in in_force.items()},
                "pairsSkippedShortHistory": skipped,
                "eligibleAircraft": sum(1 for w in histories.values() if w and self.eligible(w[-1])),
                "durationMs": round(self.last_duration_ms, 1),
                "modelVersions": self.engine.status(),
                "counts": feed_output["counts"],
                "guarantee": feed_output["guarantee"],
                "active": [self._present(entry) for entry in feed_output["active"]],
                "notifications": [self._present(e) for e in feed_output["notifications"]],
                "lowConfidence": {
                    "count": feed_output["low_confidence"]["count"],
                    "reason": feed_output["low_confidence"]["reason"],
                },
            }
        return self.last_result

    # ------------------------------------------------------------------ presentation
    @staticmethod
    def _present(entry: dict) -> dict:
        """One alert row, flattened into plain JSON the dashboard can render.

        Everything surfaced carries its reason and its confidence, because CLAUDE.md
        Section 12 forbids an endpoint that returns a bare prediction with no rationale.
        """
        assessment = entry["assessment"]
        rule = assessment.get("rule", {})
        classifier = assessment.get("classifier", {})
        multipath = assessment.get("multipath", {})
        resolution = assessment.get("resolution", {})
        callsigns = assessment.get("callsigns") or list(entry["pair"])

        return {
            "id": "-".join(callsigns),
            "pair": callsigns,
            "tier": entry["tier"],
            "tierName": entry["tier_name"],
            "severity": entry["severity"],
            "display": entry["display"],
            "isNewNotification": entry["is_new_notification"],
            "notificationReason": entry["notification_reason"],
            "reason": entry["reason"],
            "timeToCpaSeconds": entry["time_to_cpa_seconds"],
            "cpaLateralNm": entry["cpa_lateral_distance_nm"],
            "cpaVerticalFt": entry["cpa_vertical_separation_ft"],
            "probability": entry["probability"],
            "classifierProbability": entry.get("classifier_conflict_probability"),
            "ruleIsConflict": entry["rule_is_conflict"],
            "isConverging": rule.get("is_converging"),
            "firstSeen": entry["first_seen"],
            "notificationsSoFar": entry["notifications_so_far"],
            "sources": assessment.get("sources", []),
            "multipathProbability": multipath.get("conflict_probability"),
            "clearanceEffect": [c for c in (multipath.get("clearance_a"), multipath.get("clearance_b")) if c],
            "combinationsBreaching": multipath.get("combinations_breaching"),
            "explanation": classifier.get("explanation", []),
            "resolution": {
                "offered": resolution.get("offered", False),
                "reason": resolution.get("reason"),
                "options": resolution.get("options", []),
                "candidatesEvaluated": resolution.get("candidates_evaluated"),
                "blockedUnsafe": resolution.get("blocked_unsafe"),
                "rejectedIneffective": resolution.get("rejected_ineffective"),
                "rejectedNewConflict": resolution.get("rejected_new_conflict"),
                "checkedAgainst": resolution.get("checked_against"),
            },
        }

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.last_result) if self.last_result else {
                "ok": True, "active": [], "notifications": [], "counts": {},
                "pairsAssessed": 0, "eligibleAircraft": 0,
                "lowConfidence": {"count": 0, "reason": ""},
            }


conflict_service = ConflictService()
