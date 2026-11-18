"""Exercise the synthetic narrative against actual served models in isolated stores.

Not an accuracy evaluation. Retains raw outputs including failed checks.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    output=ROOT/'checkpoints'/'examiner_20261118'
    output.mkdir(parents=True,exist_ok=True)
    evidence={'purpose':'Synthetic integration smoke; not accuracy/latency measurement','steps':[]}
    try:
        with tempfile.TemporaryDirectory(dir=output,ignore_cleanup_errors=True) as temp:
            os.environ.update(FLIGHT_RIGHT_DATA_MODE='examiner',FLIGHT_RIGHT_AUDIT_DB=str(Path(temp)/'audit.sqlite3'),
                DATABASE_URL='',FLIGHT_RIGHT_ROUTE_LOOKUP='off',HF_HUB_OFFLINE='1',
                OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',LOKY_MAX_CPU_COUNT='1')
            from server.app.services.database import database
            from server.app.api import examiner as api
            from server.app.services.aircraft_service import aircraft_service
            from server.app.services.conflict_service import conflict_service
            from server.app.services.speech_service import speech_service,decode_wav
            from fastapi import HTTPException
            database.initialise()
            api.demo.playing=False
            api.assess()
            state=api.status()
            def act(action,option=''):
                nonlocal state
                state=api.control(api.Control(action=action,revision=state['revision'],session=state['session'],
                                              token=state['token'],option=option))
                evidence['steps'].append({'action':action,'scenario':state,'conflicts':conflict_service.snapshot()})
                print(action,state['chapter'],state['elapsed'],len(state['options']),flush=True)
            assert len(aircraft_service.flights)==16
            assert aircraft_service.flights[0]['onGround']
            act('next')
            try:act('next');raise AssertionError('Approval bypass')
            except HTTPException as error:assert error.status_code==409
            act('approve','takeoff')
            for _ in range(18):act('step')
            dep=next(f for f in aircraft_service.flights if f['callsign']=='IGO101')
            assert dep['altitudeFt']==5000 and not dep['onGround']
            act('next');act('approve','goaround')
            p=api.plan('optimize')
            assert len(p['rows'])==10
            order=[r['callsign'] for r in p['rows']]
            assert order.index('IGO303')<order.index('AIC202')
            evidence['recoveryPlan']=p
            act('next')
            for _ in range(3):
                if state['options']:break
                act('step')
            assert state['options'],'No actual model resolution offered'
            evidence['modelVersions']=conflict_service.engine.status()
            act('approve',state['options'][0]['id'])
            for _ in range(18):act('step')
            evidence['postCompliance']=conflict_service.snapshot()
            assert not any(a['tier']==1 for a in conflict_service.snapshot()['active']), 'Urgent conflict persisted after compliance'
            act('next')
            for _ in range(10):act('step')
            arr=next(f for f in aircraft_service.flights if f['callsign']=='AIC202')
            assert arr['onGround'] and arr['speedKt']==0
            response=api.audio(state['session'],1)
            import wave
            with wave.open(str(response.path)) as wav:assert wav.getnframes()>0
            evidence['audio']={'path':str(response.path),'bytes':Path(response.path).stat().st_size}
            sample=api.sample()
            # Real recognition, no supplied/cached transcript. Pilot cannot issue intent.
            result=speech_service.hear(decode_wav(Path(sample.path).read_bytes()),'examiner-generated-pilot',
                aircraft_service.flights,role='pilot',allow_apply=False)
            evidence['speech']=result
            assert result.get('transcript'), 'No real ASR transcript'
            assert isinstance(result.get('transcriptionId'),int), 'Speech review requires a durable transcript ID'
            act('reset')
            assert not state['approvals'] and state['chapter']==0
            evidence['result']='passed'
    except Exception as error:
        evidence['result']='failed';evidence['error']=repr(error)
        raise
    finally:
        report=output/f'integration-{time.time_ns()}.json'
        report.write_text(json.dumps(evidence,indent=2,default=str),encoding='utf-8')
        print(evidence['result'],report)


if __name__=='__main__':main()
