"""HTTP surface. The endpoint list is the one in CLAUDE.md Section 5.

The response envelope (`ok`, plus the payload) matches what the deleted Express backend
returned, so `client/src/lib/api.js` keeps working with only its base URL changed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, Query

from ..services.aircraft_service import aircraft_service
from ..services.audit_service import audit_service
from ..services.conflict_service import conflict_service

log = logging.getLogger("flightright.api")
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------- aircraft
@router.get("/aircraft/latest")
def latest_aircraft():
    """Every aircraft currently in the box, normalised for the dashboard."""
    return aircraft_service.snapshot()


@router.get("/aircraft/source")
def aircraft_source():
    """Which of the three data modes is actually feeding the screen right now.

    CLAUDE.md Section 8 item 7 asks for a live-vs-simulation indicator. This is what
    backs it: a dashboard that cannot say where its data came from is a dashboard that
    can quietly show yesterday's traffic as if it were live.
    """
    snapshot = aircraft_service.snapshot()
    return {"ok": True, **{k: snapshot[k] for k in
                           ("mode", "source", "provider", "error", "updatedAt", "updates",
                            "replay", "creditsRemaining", "count")}}


@router.post("/aircraft/mode")
def set_mode(mode: str = Body(..., embed=True)):
    try:
        aircraft_service.set_mode(mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    audit_service.record({"level": "audit", "source": "api:aircraft",
                          "action": f"Data mode switched to {mode}", "decision": mode})
    return aircraft_source()


@router.post("/aircraft/refresh")
def refresh_aircraft():
    snapshot = aircraft_service.refresh()
    conflict_service.assess(aircraft_service.histories_for_models())
    return snapshot


@router.get("/aircraft/history")
def aircraft_history(icao24: str = Query(..., description="ICAO24 address or callsign")):
    states = aircraft_service.history(icao24)
    return {"ok": True, "icao24": icao24, "count": len(states), "states": states}


# ---------------------------------------------------------------------- conflicts
@router.get("/conflicts/active")
def active_conflicts():
    """What the controller should see, after the alert feed has ranked and grouped it.

    `active` is the whole confirmed list and must be rendered in full; `notifications`
    is the subset that should interrupt. Rendering only `notifications` would turn a
    display rule into a detection rule, which the feed is written to prevent.
    """
    return conflict_service.snapshot()


@router.post("/predict/conflicts")
def predict_conflicts():
    """Force a fresh assessment rather than waiting for the next ingestion tick."""
    return conflict_service.assess(aircraft_service.histories_for_models())


@router.get("/recommend/resolution")
def resolution_for(pair: str = Query(..., description="Two callsigns joined by a hyphen")):
    """Model 3's ranked options for one confirmed tier 1 alarm."""
    snapshot = conflict_service.snapshot()
    for entry in snapshot.get("active", []):
        if entry["id"].upper() == pair.upper():
            return {"ok": True, "pair": entry["pair"], **entry["resolution"]}
    raise HTTPException(status_code=404, detail=f"No active conflict for pair {pair!r}")


# ---------------------------------------------------------------------- actions
@router.post("/actions/accept")
def accept_suggestion(payload: dict = Body(...)):
    """The controller accepted a suggestion. Nothing is transmitted to any aircraft.

    This records a decision. The system has no link to an aircraft and never will:
    CLAUDE.md Section 12 forbids any path that applies a manoeuvre without the
    controller, and there is no datalink here to apply one with.
    """
    return {"ok": True, "recorded": audit_service.record({
        "level": "audit", "source": "controller",
        "action": payload.get("action") or "Accepted AI suggestion",
        "decision": "accepted",
        "callsign": payload.get("callsign"),
        "conflictId": payload.get("conflictId"),
        "confidence": payload.get("confidence"),
        "modelVersion": payload.get("modelVersion"),
        "userId": payload.get("userId", "demo-controller"),
        "detail": payload.get("detail", payload),
    })}


@router.post("/actions/dismiss")
def dismiss_suggestion(payload: dict = Body(...)):
    return {"ok": True, "recorded": audit_service.record({
        "level": "audit", "source": "controller",
        "action": payload.get("action") or "Dismissed AI suggestion",
        "decision": "dismissed",
        "callsign": payload.get("callsign"),
        "conflictId": payload.get("conflictId"),
        "userId": payload.get("userId", "demo-controller"),
        "detail": payload.get("detail", payload),
    })}


# ---------------------------------------------------------------------- audit
@router.post("/audit")
def write_audit(entry: dict = Body(...)):
    return {"ok": True, "entry": audit_service.record(entry)}


@router.get("/audit")
def read_audit(limit: int = Query(200, ge=1, le=2000), level: str | None = None,
               conflictId: str | None = None, search: str | None = None):
    entries = audit_service.query(limit=limit, level=level, conflict_id=conflictId, search=search)
    return {"ok": True, "count": len(entries), "total": audit_service.count(), "entries": entries}


# ---------------------------------------------------------------------- health
@router.get("/health")
def health():
    snapshot = aircraft_service.snapshot()
    conflicts = conflict_service.snapshot()
    return {
        "ok": True,
        "aircraft": {"count": snapshot["count"], "source": snapshot["source"],
                     "mode": snapshot["mode"], "updatedAt": snapshot["updatedAt"],
                     "error": snapshot["error"]},
        "conflicts": {"active": len(conflicts.get("active", [])),
                      "assessed": conflicts.get("pairsAssessed", 0),
                      "durationMs": conflicts.get("durationMs")},
        "models": conflicts.get("modelVersions", {}),
        "auditEntries": audit_service.count(),
    }
