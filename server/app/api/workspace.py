from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..services.aircraft_service import aircraft_service
from ..services.workspace_service import workspace_service, WorkflowConflict

router = APIRouter(prefix="/api/workspace")


class StripChange(BaseModel):
    scope: str = Field(max_length=300)
    aircraft: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=0)
    position: Literal["tower", "ground", "clearance"]
    action: Literal["claim", "handoff", "acknowledge", "cancel handoff", "stage", "annotate"]
    target: str = Field(default="", max_length=20)
    value: str = Field(default="", max_length=100)
    note: str = Field(default="", max_length=1000)
    runway: str = Field(default="", max_length=30)
    taxiRoute: str = Field(default="", max_length=200)
    plannedRoute: str = Field(default="", max_length=500)


@router.get("")
def get_workspace():
    return workspace_service.snapshot(workspace_service.scope(aircraft_service.snapshot()))


@router.post("/event")
def update_strip(change: StripChange):
    snapshot = aircraft_service.snapshot()
    if change.scope != workspace_service.scope(snapshot):
        raise HTTPException(409, "Feed/session changed. Refresh the workspace.")
    flight = next((f for f in snapshot["flights"] if (f.get("icao24") or f["callsign"]) == change.aircraft), None)
    if not flight:
        raise HTTPException(404, "Aircraft is no longer in the current feed.")
    try:
        return workspace_service.apply(change.scope, change.aircraft, flight["callsign"], change)
    except WorkflowConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
