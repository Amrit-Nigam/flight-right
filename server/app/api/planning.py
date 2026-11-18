from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from ..services.aircraft_service import aircraft_service
from ..services.planning_service import planning_service, PlanConflict
from ..services.planning_radio import planning_radio, interpret
from ..services.speech_service import speech_service
from ..services.traffic_context import traffic_scope, display_context
import uuid

router = APIRouter(prefix='/api/planning')


class Change(BaseModel):
    version: int = Field(ge=0)
    scope: str = Field(default="sandbox", max_length=300)
    action: Literal['add', 'reorder', 'pin', 'time', 'undo', 'emergency', 'takeover', 'normal', 'issue', 'tick', 'remove', 'close', 'optimize', 'radio_auto', 'radio_accept']
    outcome: Literal['completed', 'cancelled'] = 'completed'
    flight: str = Field(default='', max_length=16)
    callsign: str = Field(default='', max_length=16)
    kind: Literal['arrival', 'departure'] = 'arrival'
    target: int | None = None
    order: list[str] = Field(default_factory=list, max_length=100)
    authorized: bool = False
    enabled: bool = False
    event_id: str = Field(default='',max_length=160)


def context():
    feed = aircraft_service.snapshot()
    at = feed.get('dataTimeUtc')
    base = datetime.fromisoformat(at).timestamp() if at else 0
    return traffic_scope(feed), base


@router.get('')
def snapshot():
    scope, base = context()
    return {'ok': True, **planning_service.snapshot(scope, base)}


@router.post('/event')
def change(payload: Change):
    scope, base = context()
    if payload.scope != scope:
        raise HTTPException(409, 'Traffic source/session changed. Refresh the plan.')
    args = payload.model_dump()
    if payload.action=='radio_accept':
        current=planning_service.snapshot(scope,base)
        event=next((e for e in current.get('radioEvents',[]) if e['id']==payload.event_id),None)
        if not event or not interpret(event['text'],aircraft_service.snapshot().get('flights',[]),current['rows'])[0]:
            raise HTTPException(400,'Transcript proposal no longer matches current traffic or sequence. Review it again.')
    if payload.action == 'add':
        feed = aircraft_service.snapshot()
        observed = next((f for f in feed.get('flights', []) if str(f.get('callsign','')).strip().upper() == payload.callsign.strip().upper()), None)
        if observed and payload.kind == 'departure' and observed.get('onGround') is False:
            raise HTTPException(400, 'Aircraft is already airborne; it cannot be queued for a future takeoff.')
        eta = observed.get('etaMinutes') if observed and payload.kind == 'arrival' else None
        if isinstance(eta, (int,float)) and 0 <= eta <= 1440:
            args.update(ready_at=base+eta*60, provenance='Earliest planning estimate: distance / ground speed, not ML landing clearance')
        else:
            args.update(provenance='Manually planned movement; readiness unverified')
    try:
        return {'ok': True, **planning_service.apply(**args, base_time=base)}
    except PlanConflict as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class RadioSync(BaseModel):
    scope: str = Field(max_length=300)

class Communication(RadioSync):
    text: str = Field(min_length=1,max_length=2000)
    role: Literal['atco','pilot','unknown']

@router.post('/radio/sync')
def sync_radio(payload:RadioSync):
    feed=aircraft_service.snapshot()
    if payload.scope!=traffic_scope(feed):raise HTTPException(409,'Traffic session changed. Refresh the plan.')
    try:return {'ok':True,**planning_radio.sync(planning_service,feed,speech_service.conversation())}
    except (ValueError,PlanConflict) as e:raise HTTPException(409,str(e)) from e

@router.post('/communication')
def communication(payload:Communication):
    feed=aircraft_service.snapshot()
    if payload.scope!=traffic_scope(feed):raise HTTPException(409,'Traffic session changed. Refresh the plan.')
    try:
        return {'ok':True,**planning_radio.process(planning_service,feed,payload.text,payload.role,
            'entered:'+uuid.uuid4().hex,display_context(feed),trusted=payload.role=='atco')}
    except (ValueError,PlanConflict) as e:raise HTTPException(409,str(e)) from e
