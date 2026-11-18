"""Examiner controls exist only in an explicitly started synthetic process."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..config import PROJECT_ROOT
from ..services.aircraft_service import aircraft_service
from ..services.conflict_service import conflict_service
from ..services.database import database
from ..services.examiner_service import examiner_service as demo, RUNWAY_MOVEMENTS
from ..services.planning_service import planning_service
from ..services.traffic_context import traffic_scope

router = APIRouter(prefix='/api/examiner')
command_audio_lock = Lock()


def require_demo():
    if aircraft_service.mode != 'examiner':
        raise HTTPException(409, 'Start with --mode examiner; these controls cannot affect live/replay traffic.')


def plan(action, **args):
    feed = aircraft_service.snapshot()
    scope = traffic_scope(feed)
    current = planning_service.snapshot(scope, aircraft_service.data_time())
    return planning_service.apply(current['version'], action, scope=scope,
                                  base_time=aircraft_service.data_time(), **args)


def seed_plan():
    scope = traffic_scope(aircraft_service.snapshot())
    if planning_service.snapshot(scope)['rows']:
        return
    for code,kind,delay in RUNWAY_MOVEMENTS:
        plan('add',callsign=code,kind=kind,ready_at=demo.base+delay,
             provenance='Scheduled runway movement')


def assess():
    aircraft_service.refresh()
    result = conflict_service.assess(aircraft_service.histories_for_models(),aircraft_service.histories_for_coverage())
    database.record_conflicts(result.get('active', []))


def model_options(background: bool | None = False):
    options=[]
    for alert in conflict_service.snapshot().get('active',[]):
        main=set(alert['pair']) == {'IGO401','AIC402'}
        if background is not None and main == background:
            continue
        for i,option in enumerate(alert.get('resolution',{}).get('options',[])):
            m=dict(aircraft=option['aircraft'],kind=option['manoeuvre_type'],magnitude=option['magnitude'],unit=option['unit']);code=m['aircraft']
            flight=next((f for f in aircraft_service.flights if f['callsign']==code),None)
            if flight is None:continue
            value=m['magnitude'];kind=m['kind']
            if kind=='altitude':text=f"{code}, {'climb' if value>0 else 'descend'} to flight level {round((flight['altitudeFt']+value)/100)}."
            elif kind=='heading':text=f"{code}, turn {'right' if value>0 else 'left'} heading {round((flight['heading']+value)%360):03d}."
            elif kind=='speed':text=f"{code}, {'increase' if value>0 else 'reduce'} speed to {round(flight['speedKt']+value)} knots."
            else:continue
            options.append(dict(id=f"{alert['id']}:{i}",pair=alert['pair'],text=text,manoeuvre=m,explanation=option.get('explanation'),score=option.get('score')))
    return options


def command_options():
    if demo.chapter == 1:
        return [dict(id='takeoff', text='IGO101, runway two seven, cleared for takeoff. Climb to five thousand feet.')]
    if demo.chapter == 3:
        return [dict(id='goaround', text='AIC202, go around. Climb to three thousand feet. Runway occupied.')]
    if demo.chapter == 5:
        return model_options()
    return []


def snapshot():
    options=command_options()
    background=model_options(background=True)
    token=hashlib.sha256(json.dumps([demo.session,demo.revision,options,background],sort_keys=True).encode()).hexdigest()
    p=planning_service.snapshot(traffic_scope(aircraft_service.snapshot()))
    flights=aircraft_service.flights
    return {**demo.status(), 'options':options,'backgroundOptions':background,'token':token,
            'traffic':dict(total=len(flights),airborne=sum(not f['onGround'] for f in flights),ground=sum(f['onGround'] for f in flights),queued=len(p['rows']))}


@router.get('')
def status():
    if aircraft_service.mode!='examiner':
        return dict(ok=True,enabled=False)
    with demo.lock:
        seed_plan()
        return dict(enabled=True,**snapshot())


class Control(BaseModel):
    action: str
    revision: int = Field(ge=0)
    session: str
    option: str = ''
    token: str = ''


@router.post('/control')
def control(payload: Control):
    require_demo()
    with demo.lock:
        if payload.session!=demo.session or (payload.revision!=demo.revision and payload.action not in ('pause','reset','start')):
            raise HTTPException(409,'Scenario changed. Refresh and review again.')
        if demo.deadline and time.time()>=demo.deadline and payload.action not in ('reset','start'):
            demo.playing=False
            raise HTTPException(409,'Nine-minute presentation finished. Reset for another rehearsal.')
        if payload.action in ('reset','start'):
            from ..services.clearance_service import clearance_service
            from ..services.speech_service import speech_service
            clearance_service.clear()
            speech_service.reset_demo_conversation()
            demo.reset()
            if payload.action=='start':
                demo.deadline=time.time()+540
            aircraft_service.histories.clear()
            conflict_service.pair_histories.clear()
            from ml_pipeline.utils.alert_feed import AlertFeed
            conflict_service.feed=AlertFeed()
            conflict_service.last_result={}
            demo.playing=False
            assess(); seed_plan()
            demo.playing=True
        elif payload.action in ('play','pause'):
            demo.playing=payload.action=='play'
            demo.revision+=1
        elif payload.action in ('step','advance'):
            if demo.playing:
                raise HTTPException(409,'Pause before stepping.')
            for _ in range(6 if payload.action=='advance' else 1):
                if demo.deadline and time.time()>=demo.deadline:
                    break
                demo.advance()
                assess()
        elif payload.action=='resolve':
            if demo.playing:raise HTTPException(409,'Pause traffic to review and approve this instruction.')
            current=snapshot();option=next((o for o in current['backgroundOptions'] if o['id']==payload.option),None)
            if current['token']!=payload.token or option is None:raise HTTPException(409,'Resolution changed; review the current options.')
            m=option['manoeuvre']
            if m['aircraft'] not in ('IGO918','AIC119'):raise HTTPException(409,'Use the chapter resolution for this aircraft.')
            from ..services.normalizer import to_engine_state
            flight=next(f for f in aircraft_service.flights if f['callsign']==m['aircraft'])
            record=dict(id=len(demo.approvals)+1,chapter=demo.chapter,text=option['text'],session=demo.session,at=demo.iso(demo.timestamp()))
            database.record(dict(level='audit',source='examiner',action='Controller approved traffic resolution',decision='accepted',callsign=m['aircraft'],detail={**record,'option':option}))
            demo.approvals.append(record)
            demo.background_commands[m['aircraft']]=dict(at=demo.traffic_elapsed,state=to_engine_state(flight),manoeuvre=m)
            from ..services.clearance_service import clearance_service
            from ..services.traffic_context import display_context
            kind=m['kind'];change=m['magnitude']
            action=('CLIMB' if change>0 else 'DESCEND') if kind=='altitude' else 'TURN' if kind=='heading' else 'SPEED'
            value=round(flight['altitudeFt']+change) if kind=='altitude' else round((flight['heading']+change)%360) if kind=='heading' else round(flight['speedKt']+change)
            clearance_service.submit(dict(callsign=m['aircraft'],action=action,value=value,confidence=1.),aircraft_service.flights,source='examiner-approved',display_context=display_context(aircraft_service.snapshot()))
            demo.revision+=1
        elif payload.action in ('next','approve'):
            if demo.playing:
                raise HTTPException(409,'Pause to change chapter or approve a command.')
            if demo.chapter==7:
                raise HTTPException(409,'Scenario complete. Reset to start a new session.')
            guarded=demo.chapter in (1,3,5)
            if guarded:
                if payload.action!='approve':
                    raise HTTPException(409,'Review and approve the command before continuing.')
                current=snapshot()
                option=next((o for o in current['options'] if o['id']==payload.option),None)
                if payload.token!=current['token'] or option is None:
                    raise HTTPException(409,'Command changed or no model option is available; review again.')
                p=planning_service.snapshot(traffic_scope(aircraft_service.snapshot()))
                if p['mode']!='normal':
                    raise HTTPException(409,'Return the runway planner to normal before scenario approval.')
                if demo.chapter==3:
                    row=next((r for r in p['rows'] if r['id']=='AIC202'),None)
                    if not row or row['pinned']:
                        raise HTTPException(409,'AIC202 must be scheduled and unpinned for go-around recovery.')
                record=dict(id=len(demo.approvals)+1,chapter=demo.chapter,text=option['text'],
                            session=demo.session,at=demo.iso(demo.timestamp()))
                database.record(dict(level='audit',source='examiner',action='Controller approved command',
                                     decision='accepted',detail={**record,'option':option}))
                demo.approvals.append(record)
                if demo.chapter==1:demo.departure_at=demo.traffic_elapsed
                if demo.chapter==3:demo.goaround_at=demo.traffic_elapsed
                if demo.chapter==5:
                    demo.manoeuvre=option['manoeuvre'];demo.resolution_start=demo.elapsed
                    from ..services.clearance_service import clearance_service
                    from ..services.traffic_context import display_context
                    m=option['manoeuvre']
                    flight=next(f for f in aircraft_service.flights if f['callsign']==m['aircraft'])
                    if m['kind']=='altitude':
                        action='CLIMB' if m['magnitude']>0 else 'DESCEND'
                        value=round(flight['altitudeFt']+m['magnitude'])
                    elif m['kind']=='heading':
                        action='TURN';value=round((flight['heading']+m['magnitude'])%360)
                    else:
                        action='SPEED';value=round(flight['speedKt']+m['magnitude'])
                    clearance_service.submit(dict(callsign=m['aircraft'],action=action,value=value,confidence=1.),
                        aircraft_service.flights,source='examiner-approved',display_context=display_context(aircraft_service.snapshot()))
            elif payload.action=='approve':
                raise HTTPException(409,'No command awaiting approval in this chapter.')
            previous=demo.chapter
            demo.clock+=demo.elapsed+10
            demo.traffic_elapsed+=10
            demo.chapter+=1;demo.elapsed=0;demo.revision+=1
            aircraft_service.histories.clear()
            assess()
            if previous==2:
                p=planning_service.snapshot(traffic_scope(aircraft_service.snapshot()))
                if any(r['id']=='IGO101' for r in p['rows']):
                    plan('close',flight='IGO101',outcome='completed')
            if previous==3:
                # A missed approach changes readiness, not just visual order.
                before=planning_service.snapshot(traffic_scope(aircraft_service.snapshot()))['rows']
                plan('goaround',flight='AIC202',ready_at=demo.timestamp()+360)
                after=plan('optimize')['rows']
                demo.resequence=dict(before=[dict(callsign=r['callsign'],target=r['target']) for r in before],after=[dict(callsign=r['callsign'],target=r['target']) for r in after])
        else:
            raise HTTPException(422,'Unknown scenario action')
        database.record(dict(level='audit',source='examiner',action=f'Presentation {payload.action}',detail=demo.status()))
        return dict(enabled=True,**snapshot())


@router.get('/resolution-preview')
def resolution_preview(pair: str = Query(max_length=80)):
    require_demo()
    with demo.lock:
        options = [option for option in model_options(background=None)
                   if option['id'].rsplit(':', 1)[0] == pair]
        return {'ok': True, 'session': demo.session, 'options': options}


@router.get('/resolution-preview/audio')
def resolution_preview_audio(session: str = Query(max_length=80), pair: str = Query(max_length=80),
                             command: str = Query(max_length=200)):
    require_demo()
    with demo.lock:
        if session != demo.session or not any(
            option['id'].rsplit(':', 1)[0] == pair and option['text'] == command
            for option in model_options(background=None)
        ):
            raise HTTPException(409, 'The resolution changed. Review the current option and try again.')
    path = command_audio(command)
    return FileResponse(path, media_type='audio/wav', filename='pilot-command-preview.wav')


def command_audio(command):
    digest = hashlib.sha256(command.encode()).hexdigest()
    path = PROJECT_ROOT/'demo'/'.runtime'/'examiner_audio'/f'{digest}.wav'
    with command_audio_lock:
        synthesize(command, path)
    return path


def synthesize(text, path):
    """Offline Windows voice; no network/service key. Never invokes a radio device."""
    import wave
    if path.exists():
        try:
            with wave.open(str(path)) as wav:
                if wav.getnframes()>0:
                    return
        except (wave.Error,EOFError):
            pass
    if os.name!='nt':
        raise HTTPException(503,'Offline WAV generation currently requires Windows System.Speech.')
    path.parent.mkdir(parents=True,exist_ok=True)
    text_path=path.with_suffix('.txt')
    text_path.write_text(text,encoding='utf-8-sig')
    script=PROJECT_ROOT/'scripts'/'examiner_voice.ps1'
    temporary=path.with_suffix('.partial.wav')
    try:
        subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),
                        '-TextPath',str(text_path),'-OutputPath',str(temporary)],
                       check=True,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        with wave.open(str(temporary)) as wav:
            if not wav.getnframes():
                raise OSError('Empty speech output')
        temporary.replace(path)
    except (subprocess.SubprocessError,OSError) as error:
        raise HTTPException(503,'Local speech synthesis failed; check Windows speech voice installation.') from error


@router.get('/audio/{session}/{command_id}')
def audio(session:str,command_id:int):
    require_demo()
    with demo.lock:
        if session!=demo.session:
            raise HTTPException(404,'Command belongs to an earlier session')
        record=next((r for r in demo.approvals if r['id']==command_id),None)
        if record is None:
            raise HTTPException(404,'No approved command')
        command=record['text']
    path=command_audio(command)
    return FileResponse(path,media_type='audio/wav',filename=f"demo-command-{command_id}.wav")


@router.get('/sample')
def sample():
    require_demo()
    path=PROJECT_ROOT/'demo'/'.runtime'/'examiner_audio'/'pilot-igo101.wav'
    synthesize('Indigo one zero one, request departure.',path)
    return FileResponse(path,media_type='audio/wav',filename='synthetic-pilot-request.wav')
