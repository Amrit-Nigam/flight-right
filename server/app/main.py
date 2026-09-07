"""Flight Right backend.

    python -m uvicorn server.app.main:app --reload --port 8000

Replaces the Express placeholder that was retired on 30 August 2026. Python rather than
Node because the four models are PyTorch and XGBoost and calling them from Node would
mean a second service or a subprocess bridge (CLAUDE.md Section 3).

Nothing here decides anything. It ingests aircraft states, calls the model chain, and
serves the result. Every judgement - what counts as a conflict, which tier it is in,
whether a manoeuvre is safe, whether an alert should interrupt - lives in ml_pipeline
and is unchanged by this being a web service.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import CORS_ORIGINS, DATA_MODE, POLL_SECONDS
from .services.aircraft_service import aircraft_service
from .services.audit_service import audit_service
from .services.conflict_service import conflict_service

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s  %(levelname)-7s %(name)-24s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("flightright")

app = FastAPI(
    title="Flight Right",
    version="0.1.0",
    description="AI-assisted ATC decision support. Prototype, human always in the loop.",
)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

_subscribers: set[WebSocket] = set()


async def _ingest_loop() -> None:
    """Poll, assess, broadcast. One tick per surveillance update."""
    while True:
        try:
            await asyncio.to_thread(aircraft_service.refresh)
            await asyncio.to_thread(conflict_service.assess,
                                    aircraft_service.histories_for_models())
            await _broadcast()
        except Exception as failure:                          # noqa: BLE001
            log.exception("Ingestion tick failed: %s", failure)
        await asyncio.sleep(POLL_SECONDS)


async def _broadcast() -> None:
    """Push the new picture to every connected dashboard."""
    if not _subscribers:
        return
    message = {"type": "update",
               "aircraft": aircraft_service.snapshot(),
               "conflicts": conflict_service.snapshot()}
    for socket in list(_subscribers):
        try:
            await socket.send_json(message)
        except Exception:                                     # noqa: BLE001
            _subscribers.discard(socket)


@app.websocket("/ws/stream")
async def stream(socket: WebSocket) -> None:
    """Aircraft states and conflict alerts on one socket.

    CLAUDE.md Section 5 lists /ws/aircraft and /ws/alerts separately. They are served
    together here because the dashboard needs them consistent with each other: an alert
    about two aircraft is meaningless if it arrives before the positions it refers to.
    """
    await socket.accept()
    _subscribers.add(socket)
    await socket.send_json({"type": "update",
                            "aircraft": aircraft_service.snapshot(),
                            "conflicts": conflict_service.snapshot()})
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _subscribers.discard(socket)


@app.on_event("startup")
async def startup() -> None:
    audit_service.initialise()
    log.info("Data mode: %s", DATA_MODE)
    await asyncio.to_thread(conflict_service.load)
    await asyncio.to_thread(aircraft_service.refresh)
    # Model loading and the first refresh take time; start the replay clock now so the
    # encounter it seeked to has not already gone past by the time anyone is watching.
    aircraft_service.replay.reset_clock()
    await asyncio.to_thread(aircraft_service.refresh)
    # Replay carries its own past, so the models can start assessing immediately rather
    # than waiting a hundred seconds for ten updates to accumulate.
    await asyncio.to_thread(aircraft_service.warm_up)
    await asyncio.to_thread(conflict_service.assess, aircraft_service.histories_for_models())
    audit_service.record({"level": "system", "source": "server",
                          "action": "Backend started",
                          "detail": {"mode": aircraft_service.mode,
                                     "source": aircraft_service.source,
                                     "models": conflict_service.engine.status()
                                     if conflict_service.engine else {}}})
    app.state.ingest = asyncio.create_task(_ingest_loop())
    log.info("Ready. %d aircraft from %s.", len(aircraft_service.flights), aircraft_service.source)


@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "ingest", None)
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@app.get("/")
def root():
    return {"service": "Flight Right backend", "docs": "/docs", "health": "/api/health"}
