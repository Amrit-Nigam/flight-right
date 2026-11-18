"""Presentation accounting and planning persistence only; no model evaluation."""
import tempfile
import unittest
from pathlib import Path
from server.app.services.planning_service import PlanningService, PlanConflict
from server.app.services.trajectory_service import TrajectoryService
from server.app.services.conflict_service import ConflictService


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = PlanningService(Path(self.temp.name)/'plan.db')

    def test_closeout_retains_original_target_history_and_other_slots_after_restart(self):
        state = self.service.apply(0, 'add', callsign='A1', kind='arrival')
        state = self.service.apply(1, 'add', callsign='B2', kind='departure')
        before = state['rows'][1]['target']
        state = self.service.apply(2, 'close', flight='A1', outcome='completed')
        self.assertEqual([r['id'] for r in state['rows']], ['B2'])
        self.assertEqual(state['rows'][0]['target'], before)
        self.assertIsNone(state['undo'])
        self.assertEqual(state['closedMovements'][0]['target'], 0)
        self.assertEqual(state['closedMovements'][0]['outcome'], 'completed')
        self.assertEqual(PlanningService(self.service.path).snapshot(), state)
        with self.assertRaises(ValueError):
            self.service.apply(3, 'undo')

    def test_closeout_validation_and_revision_rejection_leave_history_intact(self):
        initial=self.service.apply(0, 'add', callsign='A1', kind='arrival')
        with self.assertRaises(PlanConflict): self.service.apply(0,'close',flight='A1',outcome='completed')
        with self.assertRaises(ValueError): self.service.apply(1,'close',flight='A1',outcome='guess')
        self.assertEqual(self.service.snapshot(),initial)
        state=self.service.apply(1,'close',flight='A1',outcome='cancelled')
        self.assertEqual(state['closedMovements'][0]['outcome'],'cancelled')

    def test_emergency_must_be_closed_before_movement_closeout(self):
        self.service.apply(0,'add',callsign='A1',kind='arrival')
        self.service.apply(1,'emergency',flight='A1')
        with self.assertRaises(ValueError): self.service.apply(2,'close',flight='A1',outcome='completed')

    def test_forecast_progress_uses_distinct_history_without_calling_engine(self):
        result=TrajectoryService().predict(None,[{}]*3,[])
        self.assertEqual(result['reportsReceived'],3)
        self.assertEqual(result['requiredReports'],10)
        self.assertIsNone(result['fallback'])

    def test_coverage_accounts_once_for_each_existing_eligibility_exclusion(self):
        airborne=dict(onGround=False,altitudeFt=30000,velocityMs=200)
        histories={'ground':[{**airborne,'onGround':True,'altitudeFt':0}],
                   'low':[{**airborne,'altitudeFt':1000}],
                   'slow':[{**airborne,'velocityMs':0}],
                   'warm':[airborne]*3,'ready':[airborne]*10}
        result=ConflictService.coverage(histories,1,0,1)
        self.assertEqual([result[k] for k in ('ground','belowFloor','lowSpeed','eligible','warming')],[1,1,1,2,1])
        self.assertEqual(result['pairsFailed'],0)
        self.assertEqual(result['pairsNotShortlisted'],0)

    def test_alert_presentation_preserves_gate_and_separates_path_geometry(self):
        assessment={'rule':{'cpa_lateral_distance_nm':0.3,'cpa_vertical_separation_ft':1056,'time_to_cpa_seconds':75},
                    'multipath':{'conflict_probability':1,'combinations_breaching':25,
                                 'cpa_lateral_distance_nm':0.2,'cpa_vertical_separation_ft':800,'time_to_cpa_seconds':90},
                    'classifier':{'alert':True,'raw_probability':0.4,'decision_threshold':0.1,
                                  'calibrated_decision_threshold':0.2},
                    'escalation':{'gate':'classifier','consecutive_updates':11}}
        entry={'assessment':assessment,'pair':['A1','B2'],'tier':1,'tier_name':'alarm','severity':'high',
               'display':'alert','is_new_notification':False,'notification_reason':'','reason':'fixture',
               'time_to_cpa_seconds':90,'cpa_lateral_distance_nm':0.2,'cpa_vertical_separation_ft':800,
               'probability':1,'classifier_conflict_probability':0.39,'rule_is_conflict':False,
               'first_seen':1,'notifications_so_far':1}
        result=ConflictService._present(entry)
        self.assertEqual(result['triggerGate'],'classifier')
        self.assertEqual(result['nominalCpa']['verticalFt'],1056)
        self.assertEqual(result['alternativeCpa']['verticalFt'],800)
        self.assertEqual(result['classifierDecision']['rawThreshold'],0.1)
        self.assertEqual(result['classifierProbability'],0.39)
        self.assertEqual(result['confirmationUpdates'],11)
        self.assertEqual(entry['assessment'],assessment)


if __name__=='__main__': unittest.main()
