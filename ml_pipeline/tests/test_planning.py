import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.app.api.planning import router
from pathlib import Path
from server.app.services.planning_service import PlanningService, PlanConflict
from server.app.services.track_store import TrackStore


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = PlanningService(Path(self.temp.name)/'plan.db')
        self.state = self.service.snapshot()

    def act(self, action, **args):
        self.state = self.service.apply(self.state['version'], action, **args)
        return self.state

    def populate(self):
        self.act('add', callsign='A1', kind='arrival')
        self.act('add', callsign='B2', kind='departure')

    def test_normal_no_delivery_without_authorization(self):
        self.populate()
        self.assertFalse(any(m['status']=='simulated delivery' for m in self.state['messages']))
        with self.assertRaises(ValueError): self.act('issue')
        self.act('issue', authorized=True)
        self.assertTrue(any(m['status']=='simulated delivery' for m in self.state['messages']))

    def test_reorder_and_undo_are_persistent(self):
        self.populate()
        self.act('reorder', order=['B2','A1'])
        self.assertEqual([r['target'] for r in self.state['rows']], [0,120])
        self.act('undo')
        self.assertEqual(self.service.snapshot()['rows'][0]['id'], 'A1')

    def test_conflicting_time_is_atomic(self):
        self.populate()
        before = self.service.snapshot()
        with self.assertRaises(ValueError): self.act('time', flight='B2', target=60)
        self.assertEqual(before, self.service.snapshot())

    def test_stale_and_invalid_orders_rejected(self):
        self.populate()
        with self.assertRaises(PlanConflict): self.service.apply(0,'normal')
        with self.assertRaises(ValueError): self.act('reorder', order=['A1','A1'])

    def test_emergency_delivery_takeover_and_handback(self):
        self.populate()
        self.act('emergency', flight='B2')
        self.assertEqual(self.state['rows'][0]['id'], 'B2')
        self.assertTrue(all(m['status']!='draft' for m in self.state['messages']))
        self.act('takeover')
        self.act('add', callsign='C3', kind='arrival')
        self.assertTrue(any(m['status']=='draft' for m in self.state['messages']))
        self.act('normal')
        self.assertFalse(any(m['status']=='draft' for m in self.state['messages']))

    def test_pinned_and_multiple_emergency_blocks(self):
        self.populate()
        self.act('pin', flight='A1')
        with self.assertRaises(ValueError): self.act('emergency', flight='B2')
        self.act('pin', flight='A1')
        self.act('emergency', flight='A1')
        with self.assertRaises(ValueError): self.act('emergency', flight='B2')

    def test_restart_retains_issued_records(self):
        self.populate()
        self.act('issue', authorized=True)
        restored = PlanningService(self.service.path).snapshot()
        self.assertEqual(restored, self.state)

    def test_scopes_and_restart_emergency_authority(self):
        self.populate()
        self.act('emergency', flight='B2')
        restored = PlanningService(self.service.path).snapshot()
        self.assertEqual(restored['mode'],'takeover')
        self.assertTrue(restored['recoveryRequired'])
        self.assertEqual(self.service.snapshot('another-session')['rows'],[])

    def test_emergency_for_already_first_flight_still_issues_current_advisories(self):
        self.populate()
        self.act('emergency',flight='A1')
        messages = [m for m in self.state['messages'] if m['revision']==self.state['version']]
        self.assertEqual(len(messages),2)
        self.assertTrue(all(m['status']=='simulated delivery' for m in messages))

    def test_new_movement_ready_time_uses_current_feed_clock(self):
        self.state = self.service.apply(0,'add',scope='timed',base_time=1000,callsign='A1',kind='arrival',ready_at=1600)
        self.assertEqual(self.state['rows'][0]['target'],600)
        state = self.service.apply(1,'add',scope='timed',base_time=2200,callsign='B2',kind='departure')
        self.assertEqual(state['rows'][1]['target'],1200)

    def test_api_airborne_departure_and_estimated_arrival(self):
        app=FastAPI()
        app.include_router(router)
        with patch('server.app.api.planning.planning_service',self.service), patch('server.app.api.planning.context',return_value=('sandbox',1000)), patch('server.app.api.planning.aircraft_service') as aircraft, TestClient(app) as client:
            aircraft.snapshot.return_value={'flights':[{'callsign':'A1','onGround':False,'etaMinutes':5}]}
            r=client.post('/api/planning/event',json={'version':0,'action':'add','callsign':'A1','kind':'departure'})
            self.assertEqual(r.status_code,400)
            r=client.post('/api/planning/event',json={'version':0,'action':'add','callsign':'A1','kind':'arrival'})
            self.assertEqual(r.status_code,200)
            self.assertEqual(r.json()['rows'][0]['earliest'],300)
            self.assertIn('not ML',r.json()['rows'][0]['provenance'])

    def test_takeover_wins_even_when_plan_revision_is_stale(self):
        self.populate()
        self.act('emergency',flight='B2')
        state=self.service.apply(0,'takeover')
        self.assertEqual(state['mode'],'takeover')
        self.assertGreater(state['version'],self.state['version'])

    def test_remove_and_earliest_feasible_recalculation(self):
        self.populate()
        self.act('time',flight='B2',target=600)
        self.act('optimize')
        self.assertEqual(self.state['rows'][1]['target'],120)
        self.act('remove',flight='A1')
        self.assertEqual(self.state['rows'][0]['id'],'B2')
        self.assertEqual(self.state['rows'][0]['target'],0)

    def test_http_validation_authorization_and_stale_version(self):
        app = FastAPI()
        app.include_router(router)
        with patch('server.app.api.planning.planning_service', self.service), patch('server.app.api.planning.context', return_value=('sandbox',0)), TestClient(app) as client:
            self.assertEqual(client.get('/api/planning').json()['mode'], 'normal')
            self.assertEqual(client.post('/api/planning/event', json=dict(version=0, action='issue')).status_code, 400)
            response = client.post('/api/planning/event', json=dict(version=0, action='add', callsign='A1', kind='arrival'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(client.post('/api/planning/event', json=dict(version=0, action='normal')).status_code, 409)
            self.assertEqual(client.post('/api/planning/event', json=dict(version=1, action='bogus')).status_code, 422)
            self.assertEqual(client.post('/api/planning/event', json=dict(scope='other-feed',version=1,action='takeover')).status_code,409)


class TrackTests(unittest.TestCase):
    def test_persistence_dedup_source_future_and_visit_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'tracks.db'
            store = TrackStore(path)
            for at in (1,2,2,5000,5001):
                store.record('live', [dict(icao24='abc',timePosition=at,lat=19,lng=72)])
            store.record('replay', [dict(icao24='abc',timePosition=5000,lat=20,lng=73)])
            self.assertEqual([s['timePosition'] for s in TrackStore(path).history('live','abc',3)], [1,2])
            self.assertEqual([s['timePosition'] for s in store.history('live','abc',5000)], [5000])
            self.assertEqual(store.history('replay','abc',4999), [])
