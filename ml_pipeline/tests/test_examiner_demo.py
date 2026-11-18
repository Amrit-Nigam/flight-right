"""Synthetic mode isolation, approval and presentation-budget contracts."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from server.app.api import examiner as api
from server.app.services.aircraft_service import AircraftService
from server.app.services.examiner_service import ExaminerService
from server.app.services.planning_service import PlanningService


class ExaminerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.demo=ExaminerService()
        self.demo.playing=False
        self.aircraft=AircraftService(mode='examiner')
        self.plans=PlanningService(Path(self.temp.name)/'plans.sqlite3')
        for obj,key,value in [(api,'demo',self.demo),(api,'aircraft_service',self.aircraft),
                              (api,'planning_service',self.plans)]:
            self.enterContext(patch.object(obj,key,value))
        self.enterContext(patch('server.app.services.examiner_service.examiner_service',self.demo))
        self.enterContext(patch.object(api,'assess',lambda:self.aircraft.refresh()))
        self.enterContext(patch.object(api.database,'record',return_value={'id':1}))
        self.aircraft.refresh()
        self.state=api.status()

    def act(self,action,**extra):
        return api.control(api.Control(action=action,revision=self.demo.revision,session=self.demo.session,
                                       token=api.snapshot()['token'],**extra))

    def test_live_isolation(self):
        self.aircraft.mode='live'
        self.assertFalse(api.status()['enabled'])
        with self.assertRaises(HTTPException):self.act('start')

    def test_dense_traffic_moves_on_each_report_and_has_mixed_queue(self):
        initial=self.aircraft.snapshot()['flights']
        self.assertEqual(len(initial),16)
        self.assertEqual(sum(not f['onGround'] for f in initial),10)
        self.assertEqual(len(self.plans.snapshot(api.traffic_scope(self.aircraft.snapshot()))['rows']),11)
        self.assertTrue(all('synthetic' not in (f['route'] or '').lower() for f in initial))
        positions={f['callsign']:(f['lat'],f['lng']) for f in initial if not f['onGround']}
        self.act('step')
        for f in self.aircraft.flights:
            if f['callsign'] in positions:self.assertNotEqual(positions[f['callsign']],(f['lat'],f['lng']))

    def test_playback_keeps_moving_past_a_chapter_pause_point(self):
        self.demo.chapter=1
        self.demo.playing=True
        before=self.demo.timestamp()
        self.aircraft.refresh();self.aircraft.refresh()
        self.assertTrue(self.demo.playing)
        self.assertEqual(self.demo.timestamp()-before,20)

    def test_live_refresh_still_uses_opensky_without_synthetic_traffic(self):
        live=AircraftService(mode='live')
        row=['abc123','LIVE123','India',time.time(),None,72.8,19.2,9000,False,230,90,0,None,9000,None]
        with patch.object(live.opensky,'fetch_states',return_value=[row]), \
             patch('server.app.services.aircraft_service.aircraft_info.enrich',side_effect=lambda f:f), \
             patch('server.app.services.aircraft_service.airport_service.observe'), \
             patch('server.app.services.aircraft_service.track_store.record'):
            snapshot=live.refresh()
        self.assertEqual(snapshot['source'],'live')
        self.assertIsNone(snapshot['replay'])
        self.assertEqual([f['callsign'] for f in snapshot['flights']],['LIVE123'])

    def test_stale_session_rejected(self):
        with self.assertRaises(HTTPException):
            api.control(api.Control(action='next',revision=0,session='older'))

    def test_pause_succeeds_when_a_new_traffic_tick_arrives(self):
        self.demo.playing=True
        revision=self.demo.revision
        self.aircraft.refresh()
        result=api.control(api.Control(action='pause',revision=revision,session=self.demo.session))
        self.assertFalse(result['playing'])

    def test_reset_changes_workspace_scope(self):
        from server.app.services.workspace_service import WorkspaceService
        before=WorkspaceService.scope(self.aircraft.snapshot())
        self.act('reset')
        self.demo.playing=False
        self.assertNotEqual(before,WorkspaceService.scope(self.aircraft.snapshot()))

    def test_clearance_required_and_duplicate_approval_rejected(self):
        self.act('next')
        with self.assertRaises(HTTPException):self.act('next')
        payload=api.Control(action='approve',revision=self.demo.revision,session=self.demo.session,
                            token=api.snapshot()['token'],option='takeoff')
        api.control(payload)
        self.assertEqual(self.demo.chapter,2)
        with self.assertRaises(HTTPException):api.control(payload)
        self.assertEqual(len(self.demo.approvals),1)

    def test_timed_presentation_freezes_at_nine_minutes(self):
        self.act('start')
        self.assertAlmostEqual(self.demo.deadline-time.time(),540,delta=2)
        self.demo.playing=False
        self.demo.deadline=time.time()-1
        with self.assertRaises(HTTPException):self.act('next')
        self.assertEqual(self.demo.chapter,0)

    def test_advance_preserves_ten_second_reports_and_caps_chapter(self):
        self.act('advance')
        history=self.aircraft.history('de0101')
        self.assertTrue(all(b['timePosition']-a['timePosition']==10 for a,b in zip(history,history[1:])))
        self.act('advance')
        self.assertEqual(self.demo.elapsed,120)
        self.act('step')
        self.assertEqual(self.demo.elapsed,130)

    def test_departure_stays_airborne_in_later_chapters(self):
        for chapter in (3,4,5,7):
            self.demo.chapter=chapter
            flight=next(f for f in self.demo.states() if f['callsign']=='IGO101')
            self.assertEqual(flight['altitudeFt'],5000)
            self.assertFalse(flight['onGround'])

    def test_goaround_reorders_real_planner_and_preserves_history(self):
        self.act('next');self.act('approve',option='takeoff')
        self.act('next')
        self.act('approve',option='goaround')
        p=self.plans.snapshot(api.traffic_scope(self.aircraft.snapshot()))
        self.assertEqual(len(p['rows']),10)
        order=[r['id'] for r in p['rows']]
        self.assertLess(order.index('IGO303'),order.index('AIC202'))
        self.assertEqual(p['closedMovements'][0]['id'],'IGO101')
        self.assertTrue(any(e['action']=='goaround' for e in p['events']))

    def test_unapproved_or_previous_session_audio_unavailable(self):
        for session in (self.demo.session,'older'):
            with self.assertRaises(HTTPException):api.audio(session,99)

    def test_resolution_preview_only_reads_current_command_in_current_session(self):
        command = {'id': 'IGO918-AIC119:0', 'text': 'IGO918, turn right heading 120.'}
        with patch.object(api, 'model_options', return_value=[command]), \
             patch.object(api, 'command_audio', return_value=Path('preview.wav')) as synthesize:
            preview = api.resolution_preview('IGO918-AIC119')
            self.assertEqual(preview['options'], [command])
            for session, pair, text in [('older', 'IGO918-AIC119', command['text']),
                                        (self.demo.session, 'another-pair', command['text']),
                                        (self.demo.session, 'IGO918-AIC119', 'arbitrary text')]:
                with self.assertRaises(HTTPException):
                    api.resolution_preview_audio(session, pair, text)
            synthesize.assert_not_called()
            response = api.resolution_preview_audio(self.demo.session, 'IGO918-AIC119', command['text'])
            self.assertEqual(response.media_type, 'audio/wav')
            synthesize.assert_called_once_with(command['text'])
            self.assertEqual(self.demo.approvals, [])


if __name__=='__main__':unittest.main()
