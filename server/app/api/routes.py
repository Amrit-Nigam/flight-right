"""HTTP surface. The endpoint list is the one in CLAUDE.md Section 5.

The response envelope (`ok`, plus the payload) matches what the deleted Express backend
returned, so `client/src/lib/api.js` keeps working with only its base URL changed.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..services.aircraft_service import aircraft_service
from ..services.database import DEFAULT_USER, database
from ..services.conflict_service import conflict_service
from ..services.clearance_service import clearance_service
from ..services.speech_service import decode_wav, speech_service
from ..services.intent_service import intent_service
from ..services.aircraft_info import aircraft_info
from ..services.airport_service import airport_service
from ..config import SPEECH_DEMO_DIR

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
        if mode in ("live", "auto"):
            intent_service.start_live()      # dialled levels, types and squawks come from this feed
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    database.record({"level": "audit", "source": "api:aircraft",
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
def _served_model_versions() -> dict | None:
    """The versions of the models actually running, from the server, never the client.

    ISSUES.md H2 (fixed 25 Sep 2026): modelVersion was null on every audit row. The
    resolve modal sent `conflict.sources` (names, not versions) and the suggestions panel
    sent nothing. Section 12 requires the model version on every entry, and the server is
    the only party that knows it for certain, so it stamps it here. Whatever the client
    sent is kept in the detail.
    """
    engine = conflict_service.engine
    if engine is None:
        return None
    status = engine.status()
    return {k: v for k, v in status.items() if k in ("trajectory_residual", "trajectory_multipath",
                                                      "xgboost_conflict", "rule_path")}


@router.post("/actions/accept")
def accept_suggestion(payload: dict = Body(...)):
    """The controller accepted a suggestion. Nothing is transmitted to any aircraft.

    This records a decision. The system has no link to an aircraft and never will:
    CLAUDE.md Section 12 forbids any path that applies a manoeuvre without the
    controller, and there is no datalink here to apply one with.
    """
    return {"ok": True, "recorded": database.record({
        "level": "audit", "source": "controller",
        "action": payload.get("action") or "Accepted AI suggestion",
        "decision": "accepted",
        "callsign": payload.get("callsign"),
        "conflictId": payload.get("conflictId"),
        "confidence": payload.get("confidence"),
        "modelVersion": _served_model_versions() or payload.get("modelVersion"),
        "userId": payload.get("userId", DEFAULT_USER),
        "detail": {**(payload.get("detail") or payload), "clientModelVersion": payload.get("modelVersion")},
    })}


@router.post("/actions/dismiss")
def dismiss_suggestion(payload: dict = Body(...)):
    return {"ok": True, "recorded": database.record({
        "level": "audit", "source": "controller",
        "action": payload.get("action") or "Dismissed AI suggestion",
        "decision": "dismissed",
        "callsign": payload.get("callsign"),
        "conflictId": payload.get("conflictId"),
        "modelVersion": _served_model_versions() or payload.get("modelVersion"),
        "userId": payload.get("userId", DEFAULT_USER),
        "detail": payload.get("detail", payload),
    })}


# ---------------------------------------------------------------------- audit
# ---------------------------------------------------------------------- clearances
@router.post("/clearances")
def submit_clearance(payload: dict = Body(...)):
    """A known instruction to one aircraft: {"callsign" or "icao24", "action", "value"}.

    Actions: CLIMB / DESCEND (value in feet), TURN (heading in degrees), DIRECT (fix), SPEED
    (knots). A level caps that aircraft's predicted altitude; a heading removes candidate
    paths that contradict it; the others are recorded only. Source is always "manual"
    here; the speech chain submits through the same service with its own source. The
    result says whether it was applied and why, and is recorded either way.
    """
    result = clearance_service.submit(payload, aircraft_service.snapshot()["flights"], source="manual")
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=result)
    return result


@router.get("/clearances")
def list_clearances(limit: int = Query(100, ge=1, le=1000)):
    return {"ok": True, "supported": clearance_service.supported(),
            "inForce": {k: [c.to_dict() for c in v] for k, v in clearance_service.in_force().items()},
            "history": database.clearance_history(limit)}


@router.delete("/clearances")
def withdraw_clearances(icao24: str | None = None):
    """Withdraw clearances from the model chain. The records in the database remain."""
    return {"ok": True, "withdrawn": clearance_service.clear(icao24)}


# ---------------------------------------------------------------------- speech
_CLIP_ID = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")


def _demo_clips() -> list[dict]:
    index = SPEECH_DEMO_DIR / "index.json"
    return json.loads(index.read_text(encoding="utf8")) if index.exists() else []


@router.get("/speech/status")
def speech_status():
    """Which speech model is installed (ASR_MODEL_ID), whether it is loaded, and the demo clips."""
    return {"ok": True, **speech_service.status(), "demoClips": len(_demo_clips())}


@router.get("/speech/clips")
def speech_clips():
    """Demo transmissions for the radio panel. Each says where its audio came from."""
    return {"ok": True, "clips": _demo_clips()}


@router.get("/speech/clips/{clip_id}/audio")
def speech_clip_audio(clip_id: str):
    if not _CLIP_ID.match(clip_id) or not (SPEECH_DEMO_DIR / f"{clip_id}.wav").exists():
        raise HTTPException(status_code=404, detail="no such clip")
    return FileResponse(SPEECH_DEMO_DIR / f"{clip_id}.wav", media_type="audio/wav")


@router.post("/speech/hear")
async def speech_hear(request: Request, clip: str | None = None, cached: bool = True):
    """Run the whole speech chain on one transmission and apply what it heard.

    Either ``?clip=<id>`` (a demo clip) or a raw audio body (Content-Type audio/*, any format
    soundfile reads). With a demo clip and ``cached=true`` the transcript pre-computed for the
    installed model is used (plan 7.3: zero inference at demo time); otherwise the model runs.
    The result shows every step: transcript, extraction, callsign match, and what the
    clearance door did with it.
    """
    flights = aircraft_service.snapshot()["flights"]
    if clip:
        entry = next((c for c in _demo_clips() if c.get("id") == clip), None)
        if entry is None or not _CLIP_ID.match(clip):
            raise HTTPException(status_code=404, detail="no such clip")
        transcript = (entry.get("transcripts") or {}).get(speech_service.status()["modelId"] or "") if cached else None
        audio = None if transcript is not None else decode_wav((SPEECH_DEMO_DIR / f"{clip}.wav").read_bytes())
        return speech_service.hear(audio, f"demo:{clip}", flights, transcript=transcript)
    body = await request.body()
    if not body or len(body) > 10_000_000:
        raise HTTPException(status_code=422, detail="send a clip id or up to 10 MB of audio")
    try:
        audio = decode_wav(body)
    except Exception as failure:                                            # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"could not read audio: {type(failure).__name__}")
    if len(audio) > 30 * 16_000:
        raise HTTPException(status_code=422, detail="one transmission at a time: 30 s at most")
    return speech_service.hear(audio, "upload", flights)


@router.get("/speech/transcriptions")
def speech_transcriptions(limit: int = Query(50, ge=1, le=1000)):
    return {"ok": True, "transcriptions": database.transcription_history(limit)}


@router.post("/audit")
def write_audit(entry: dict = Body(...)):
    if not entry.get("modelVersion"):
        entry = {**entry, "modelVersion": _served_model_versions()}
    return {"ok": True, "entry": database.record(entry)}


@router.get("/conflicts/history")
def conflict_history(limit: int = Query(100, ge=1, le=1000)):
    """Conflicts that have been raised, newest first. Survives a restart."""
    return {"ok": True, "conflicts": database.conflict_history(limit)}


@router.get("/audit")
def read_audit(limit: int = Query(200, ge=1, le=2000), level: str | None = None,
               conflictId: str | None = None, search: str | None = None):
    entries = database.query(limit=limit, level=level, conflict_id=conflictId, search=search)
    return {"ok": True, "count": len(entries), "total": database.count(), "entries": entries}


# ---------------------------------------------------------------------- airport
@router.get("/airport")
def airport():
    """VABB: real runways (OurAirports), the METAR for the time the picture describes (live:
    aviationweather.gov; replay: the archived report), runway in use and movements derived
    from the tracks, and upcoming arrivals with estimated times. See airport_service.py."""
    snapshot = aircraft_service.snapshot()
    return {"ok": True, **airport_service.summary(snapshot["flights"], snapshot["source"],
                                                  aircraft_service.data_time(), aircraft_info.destination)}


def _constants() -> dict:
    """The numbers the dashboard quotes, served from the modules that use them, so the UI can
    never drift from the backend (ISSUES.md: adapters.js used to hard-code 38 s and the weights)."""
    from ml_pipeline.utils import cpa_conflict_detection as cpa
    from ml_pipeline.utils import resolution_engine as re_
    return {"separationLateralNm": cpa.SEPARATION_LATERAL_NM, "separationVerticalFt": cpa.SEPARATION_VERTICAL_FT,
            "alertLateralNm": cpa.ALERT_LATERAL_NM, "alertVerticalFt": cpa.ALERT_VERTICAL_FT,
            "cpaGridStepSeconds": cpa.CPA_GRID_STEP_SECONDS, "lookAheadSeconds": cpa.CPA_GRID_END_SECONDS,
            "consecutiveUpdates": cpa.CONSECUTIVE_UPDATES_TO_NOTIFY,
            "responseDelaySeconds": re_.RESPONSE_DELAY_SECONDS,
            "weights": {"safety": re_.WEIGHT_SAFETY, "delay": re_.WEIGHT_DELAY, "fuel": re_.WEIGHT_FUEL,
                        "workload": re_.WEIGHT_WORKLOAD, "confidence": re_.WEIGHT_CONFIDENCE}}


# ---------------------------------------------------------------------- health
@router.get("/health")
def health():
    snapshot = aircraft_service.snapshot()
    conflicts = conflict_service.snapshot()
    return {
        "ok": True,
        "aircraft": {"count": snapshot["count"], "source": snapshot["source"],
                     "mode": snapshot["mode"], "updatedAt": snapshot["updatedAt"],
                     "dataTimeUtc": snapshot.get("dataTimeUtc"), "error": snapshot["error"]},
        # The identity every audit row is written under (no login: MVP security posture).
        "controller": DEFAULT_USER,
        "constants": _constants(),
        "conflicts": {"active": len(conflicts.get("active", [])),
                      "assessed": conflicts.get("pairsAssessed", 0),
                      "durationMs": conflicts.get("durationMs")},
        "models": conflicts.get("modelVersions", {}),
        "auditEntries": database.count(),
        # Which store is live, and whether the audit log's append-only guarantee is
        # enforced by the database or is only a convention of this code. The connection
        # string is deliberately not included: it carries a password.
        "store": database.backend(),
        # Where the classifier's dialled-level inputs come from, and the ODbL credit adsb.lol requires.
        "dialledLevels": intent_service.status(),
    }
