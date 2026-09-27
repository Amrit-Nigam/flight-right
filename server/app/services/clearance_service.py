"""Clearances in force, per aircraft, and the single door they come in through.

Plan Phase 7.3. A clearance ("descend FL130", "turn heading 090") adjusts that aircraft's
candidate paths before the conflict chain runs (ml_pipeline/utils/clearance.py). Today
clearances arrive from the manual API. The speech chain (plan Phases 4-6), once built,
calls `submit()` with `source="asr:<model id>"` and a transcription id, and nothing else in
the system has to change -- that is the reason this door exists before the voice chain does.

Every submission, accepted or not, is written to `extracted_clearances` (append-only) and
to the audit log. A clearance that is invalid, unmatched, or below the confidence floor is
recorded and not applied, with the reason.

Callsign matching here is EXACT (case-insensitive) against the aircraft visible right now.
Fuzzy matching of a mis-heard callsign is plan Phase 6.2 and belongs in the speech chain,
before `submit()` is called, so this stays the one place that decides what is applied.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import Any

from ..config import CLEARANCE_MIN_CONFIDENCE, CLEARANCE_VALID_SECONDS, PROJECT_ROOT
from .database import DEFAULT_USER, database

sys.path.insert(0, str(PROJECT_ROOT))
from ml_pipeline.utils.clearance import ACTIONS, Clearance  # noqa: E402

GROUP = {"CLIMB": "level", "DESCEND": "level", "TURN": "heading", "DIRECT": "route", "SPEED": "speed"}


class ClearanceService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_force: dict[str, dict[str, Clearance]] = {}

    def submit(self, payload: dict[str, Any], flights: list[dict], source: str = "manual") -> dict[str, Any]:
        """Validate, match to a visible aircraft, record, and (if acceptable) put in force."""
        action = str(payload.get("action", "")).strip().upper()
        wanted = str(payload.get("icao24") or payload.get("callsign") or "").strip()
        match = next((f for f in flights if wanted and wanted.lower() in
                      (str(f.get("icao24", "")).lower(), str(f.get("callsign", "")).strip().lower())), None)
        try:
            value = float(payload["value"]) if payload.get("value") not in (None, "") else None
            confidence = float(payload.get("confidence", 1.0))
        except (TypeError, ValueError):
            value, confidence = None, -1.0
        clearance = Clearance(
            icao24=str(match["icao24"]) if match else "",
            callsign=str(match["callsign"]).strip() if match else None,
            action=action, value=value, fix=payload.get("fix"), confidence=confidence,
            source=source, issued_at=time.time(),
            valid_seconds=float(payload.get("valid_seconds", CLEARANCE_VALID_SECONDS)),
            transcription_id=payload.get("transcription_id"),
            notes={"callsign_heard": wanted[:16], "requested_by": payload.get("user", DEFAULT_USER)})

        problems = clearance.problems()
        if not match:
            problems.insert(0, f"no aircraft {wanted!r} is visible right now")
        if confidence < CLEARANCE_MIN_CONFIDENCE and not problems:
            problems.append(f"confidence {confidence:.2f} below the {CLEARANCE_MIN_CONFIDENCE:.2f} floor")
        applied = not problems
        report = {"applied": applied, "problems": problems,
                  "effect": ("caps predicted altitude at the cleared level" if GROUP.get(action) == "level"
                             else "eliminates candidate paths whose track contradicts the heading" if action == "TURN"
                             else "recorded only; not yet used to adjust paths")}
        if applied:
            with self._lock:
                self._in_force.setdefault(clearance.icao24, {})[GROUP[action]] = clearance
        row_id = database.record_clearance(clearance.to_dict(), applied, report)
        database.record({
            "level": "audit", "source": "clearance_service",
            "action": f"clearance {action or '?'} {value if value is not None else ''} {'applied' if applied else 'rejected'}",
            "callsign": clearance.callsign, "decision": "applied" if applied else "rejected",
            "modelVersion": source, "confidence": confidence if confidence >= 0 else None,
            "detail": {"clearance_row": row_id, "clearance": clearance.to_dict(), "report": report},
        })
        return {"ok": applied, "id": row_id, "clearance": clearance.to_dict(), **report}

    def in_force(self, now: float | None = None) -> dict[str, list[Clearance]]:
        """icao24 -> clearances currently in force. Expired ones are dropped here."""
        now = time.time() if now is None else now
        with self._lock:
            for icao24 in list(self._in_force):
                live = {g: c for g, c in self._in_force[icao24].items() if c.active(now)}
                if live:
                    self._in_force[icao24] = live
                else:
                    del self._in_force[icao24]
            return {icao24: list(groups.values()) for icao24, groups in self._in_force.items()}

    def clear(self, icao24: str | None = None) -> int:
        """Withdraw clearances (all, or one aircraft's). The records stay in the database."""
        with self._lock:
            if icao24 is None:
                count = sum(len(v) for v in self._in_force.values())
                self._in_force.clear()
                return count
            return len(self._in_force.pop(icao24, {}))

    @staticmethod
    def supported() -> dict[str, Any]:
        return {"actions": list(ACTIONS), "minConfidence": CLEARANCE_MIN_CONFIDENCE,
                "validSeconds": CLEARANCE_VALID_SECONDS}


clearance_service = ClearanceService()
