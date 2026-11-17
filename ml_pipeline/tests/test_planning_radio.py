"""Deterministic transcript consumer checks; no ASR or ML accuracy measurements."""
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.app.services.planning_radio import PlanningRadio, interpret
from server.app.services.planning_service import PlanningService
from server.app.services.traffic_context import display_context, traffic_scope
from server.app.api.planning import router

class PlanningRadioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.service=PlanningService(Path(self.temp.name)/'plan.db')
        self.radio=PlanningRadio()
        self.feed={'source':'replay','dataTimeUtc':'2026-09-04T12:00:00+00:00','replay':{'session':'test','cycle':0},
                   'flights':[{'callsign':'A1','icao24':'abc','onGround':False,'etaMinutes':5},{'callsign':'B2','icao24':'def','onGround':True}]}
        self.scope=traffic_scope(self.feed);self.n=0

    def process(self,text,role='atco',trusted=True,**kw):
        self.n+=1
        return self.radio.process(self.service,self.feed,text,role,kw.pop('event_id',str(self.n)),display_context(self.feed),trusted,**kw)

    def test_reviewed_arrival_uses_eta_and_never_sends_advisory(self):
        state=self.process('A1 cleared to land')
        self.assertEqual(state['rows'][0]['earliest'],300)
        self.assertEqual(state['radioEvents'][0]['status'],'applied')
        self.assertTrue(all(m['status']=='draft' for m in state['messages']))

    def test_number_and_follow_ordering_with_persistent_dedup(self):
        self.process('A1 cleared to land')
        state=self.process('B2 number one for departure',event_id='same')
        self.assertEqual([r['id'] for r in state['rows']],['B2','A1'])
        duplicate=self.process('B2 number one for departure',event_id='same')
        self.assertEqual(state,duplicate)
        self.assertEqual(PlanningService(self.service.path).snapshot(self.scope),state)
        state=self.process('B2 follow A1 for departure')
        self.assertEqual([r['id'] for r in state['rows']],['A1','B2'])

    def test_pilot_and_unidentified_tower_require_review(self):
        for role,trusted in [('pilot',True),('unknown',False),('atco',False)]:
            with self.subTest(role=role,trusted=trusted):
                state=self.process('A1 number one for landing',role,trusted)
                self.assertEqual(state['rows'],[])
                self.assertEqual(state['radioEvents'][-1]['status'],'review')
        state=self.service.apply(state['version'],'radio_accept',self.scope,event_id=state['radioEvents'][-1]['id'])
        self.assertEqual(state['rows'][0]['id'],'A1')

    def test_negative_conditional_ambiguous_and_unsupported_do_not_queue(self):
        for text in ['A1 not number one for landing','A1 request landing','A1 after B2 cleared to land',
                     'A1 expect landing number one','A1 cancel landing','A1 if ready cleared to land',
                     'A1 and B2 cleared to land','A1 number one number two for landing','A1 number one thousand for landing',
                     'A1 number zero for landing','A1 number 101 for landing','A1 number 1000 for landing',
                     'A1 number eleven for landing','A1 number two and follow B2 for landing',
                     'A1 descend 5000','unknown cleared to land','A1 go around number one for landing']:
            with self.subTest(text=text):
                state=self.process(text)
                self.assertFalse(state['rows'])
                self.assertEqual(state['radioEvents'][-1]['status'],'ignored')

    def test_unfillable_position_is_recorded_without_partial_add(self):
        state=self.process('A1 number two for landing')
        self.assertFalse(state['rows']);self.assertEqual(state['radioEvents'][-1]['status'],'blocked')

    def test_takeover_auto_off_and_session_isolation(self):
        state=self.service.apply(0,'radio_auto',self.scope,enabled=False)
        state=self.process('A1 cleared to land');self.assertFalse(state['rows'])
        self.service.apply(state['version'],'radio_auto',self.scope,enabled=True)
        state=self.service.snapshot(self.scope)
        self.service.apply(state['version'],'takeover',self.scope)
        state=self.process('A1 cleared to land');self.assertFalse(state['rows'])
        changed={**self.feed,'replay':{'session':'test','cycle':1}}
        self.assertFalse(self.service.snapshot(traffic_scope(changed))['radioEvents'])
        state=self.radio.process(self.service,changed,'A1 cleared to land','atco','wrong',display_context(self.feed),True)
        self.assertFalse(state['rows'])

    def test_pinned_movement_type_and_airborne_departure_cannot_be_overridden(self):
        state=self.process('A1 cleared to land')
        self.service.apply(state['version'],'pin',self.scope,flight='A1')
        self.feed['dataTimeUtc']='2026-09-04T12:05:00+00:00'
        state=self.process('B2 number one for departure')
        self.assertEqual([r['id'] for r in state['rows']],['A1'])
        self.assertEqual(state['radioEvents'][-1]['status'],'blocked')
        state=self.process('A1 cleared for takeoff')
        self.assertEqual(len(state['rows']),1)
        self.assertEqual(state['radioEvents'][-1]['status'],'ignored')

    def test_speech_sync_gates_role_confidence_and_live_replay(self):
        original={'transcriptionId':1,'transcript':'A1 cleared to land','role':'atco','roleSource':'phrase-hint',
                  'callsignMatch':{'code':'A1','score':100},'asrConfidence':.95,'displayContext':display_context(self.feed)}
        conv={'messages':[original],'supported':{'minConfidence':.8}}
        state=self.radio.sync(self.service,self.feed,conv)
        self.assertFalse(state['rows'])
        msg={**original,'transcriptionId':2,'roleSource':'labelled-channel','asrConfidence':.5}
        state=self.radio.sync(self.service,self.feed,{**conv,'messages':[msg]});self.assertFalse(state['rows'])
        msg={**msg,'transcriptionId':3,'asrConfidence':.95,'liveRadio':True}
        state=self.radio.sync(self.service,self.feed,{**conv,'messages':[msg]});self.assertFalse(state['rows'])
        msg={**msg,'transcriptionId':4,'liveRadio':False,'roleSource':'reviewed'}
        state=self.radio.sync(self.service,self.feed,{**conv,'messages':[msg]});self.assertEqual(len(state['rows']),1)
        self.assertEqual(state,self.radio.sync(self.service,self.feed,{**conv,'messages':[msg]}))

    def test_spoken_callsign_uses_existing_match_and_ignores_unscoped(self):
        msg={'transcriptionId':1,'transcript':'indigo one cleared to land','role':'atco','roleSource':'labelled-channel',
             'callsignMatch':{'code':'A1','score':100,'heard':'indigo one'},'asrConfidence':.95}
        self.assertFalse(self.radio.sync(self.service,self.feed,{'messages':[msg]})['rows'])
        msg['displayContext']=display_context(self.feed)
        state=self.radio.sync(self.service,self.feed,{'messages':[msg],'supported':{'minConfidence':.8}})
        self.assertEqual(state['rows'][0]['id'],'A1')

    def test_http_scope_review_and_auto_toggle(self):
        app=FastAPI();app.include_router(router)
        with patch('server.app.api.planning.planning_service',self.service),patch('server.app.api.planning.aircraft_service') as aircraft,TestClient(app) as client:
            aircraft.snapshot.return_value=self.feed
            self.assertEqual(client.post('/api/planning/communication',json={'scope':'other','role':'atco','text':'A1 cleared to land'}).status_code,409)
            state=client.post('/api/planning/communication',json={'scope':self.scope,'role':'pilot','text':'A1 cleared to land'}).json()
            self.assertFalse(state['rows'])
            r=client.post('/api/planning/event',json={'scope':self.scope,'version':state['version'],'action':'radio_accept','event_id':state['radioEvents'][0]['id']})
            self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['rows']),1)
            self.assertEqual(client.post('/api/planning/communication',json={'scope':self.scope,'role':'bogus','text':'A1'}).status_code,422)

    def test_maximum_supported_number_and_unknown_follow(self):
        proposal,_=interpret('A1 number 100 for landing',self.feed['flights'],[])
        self.assertEqual(proposal['position'],100)
        self.assertIsNone(interpret('A1 follow B2 for landing',self.feed['flights'],[])[0])

    def test_old_and_future_transcripts_wait_for_review(self):
        for at in [time.time()-121,time.time()+60]:
            state=self.process('A1 cleared to land',at=at)
            self.assertFalse(state['rows'])
            self.assertEqual(state['radioEvents'][-1]['status'],'review')

if __name__=='__main__':unittest.main()
