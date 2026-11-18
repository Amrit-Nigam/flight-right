import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from ml_pipeline.utils.path_confidence_monitor import PathConfidenceMonitor, PathConfidenceWorker, summarize


def aircraft(weights=(.6,.4)):
    return dict(current=(19.,73.,4000.),patterns=[10,20],
                paths=[(w,{60:(19.,73.,4000.),600:(19.,73.,4000.)}) for w in weights])


class PathConfidenceTests(unittest.TestCase):
    def test_joint_products_sum_and_both_marginals(self):
        r=summarize(aircraft(),aircraft((.5,.5)))
        self.assertEqual(r['combinations_checked'],4)
        self.assertAlmostEqual(r['total_weight'],1.)
        self.assertAlmostEqual(r['max_joint_weight'],.3)
        self.assertAlmostEqual(r['both_path_weight'],.5)

    def test_all_pairs_and_three_updates_before_display(self):
        m=PathConfidenceMonitor(.5)
        snapshot={k:aircraft() for k in ['a','b','c']}
        r=m.update(snapshot,0)
        self.assertEqual(r['pairs_checked'],3)
        self.assertEqual(len(r['pending']),3)
        self.assertEqual(r['shadow_visible'],[])
        m.update(snapshot,10)
        r=m.update(snapshot,20)
        self.assertEqual(len(r['shadow_visible']),3)
        self.assertTrue(all(x['new_notification'] for x in r['shadow_visible']))
        self.assertFalse(any(x['new_notification'] for x in m.update(snapshot,30)['shadow_visible']))

    def test_combination_tracking_uses_pattern_not_rank(self):
        m=PathConfidenceMonitor(.5)
        a=aircraft()
        m.update({'a':a,'b':aircraft()},0)
        reordered=copy.deepcopy(a)
        reordered['patterns'].reverse()
        reordered['paths'].reverse()
        r=m.update({'a':reordered,'b':aircraft()},10)
        hits=r['pending'][0]['combinations']
        self.assertTrue(all(x['updates']==2 for x in hits))
        self.assertAlmostEqual(next(x for x in hits if x['pattern_a']==10 and x['pattern_b']==10)['joint_weight'],.36)

    def test_low_confidence_stays_pending_and_does_not_require_increasing_trend(self):
        m=PathConfidenceMonitor(.5,score='max_joint_weight',consecutive=1)
        s={'a':aircraft(),'b':aircraft()}
        self.assertEqual(len(m.update(s,0)['pending']),1)
        s={'a':aircraft((.9,.1)),'b':aircraft((.9,.1))}
        self.assertEqual(len(m.update(s,10)['shadow_visible']),1)
        # A decline .81 -> .64 remains above .5 and must still qualify.
        s={'a':aircraft((.8,.2)),'b':aircraft((.8,.2))}
        self.assertEqual(len(m.update(s,20)['shadow_visible']),1)

    def test_missing_snapshot_and_long_gap_reset_persistence(self):
        m=PathConfidenceMonitor(.5,consecutive=2)
        s={'a':aircraft(),'b':aircraft()}
        m.update(s,0)
        self.assertEqual(len(m.update(s,10)['shadow_visible']),1)
        m.update({},20)
        self.assertEqual(len(m.update(s,30)['pending']),1)
        self.assertEqual(len(m.update(s,70)['pending']),1)

    def test_absent_pairs_expire_and_stale_times_reject(self):
        m=PathConfidenceMonitor(.5)
        m.update({'a':aircraft(),'b':aircraft()},0)
        self.assertEqual(m.update({},121)['retained_pairs'],0)
        with self.assertRaises(ValueError):
            m.update({},121)

    def test_protected_pair_bypasses_confidence_only(self):
        m=PathConfidenceMonitor(.99,score='max_joint_weight',consecutive=1)
        r=m.update({'a':aircraft(),'b':aircraft()},0,protected_pairs={('b','a')})
        self.assertEqual(len(r['shadow_visible']),1)
        self.assertTrue(r['shadow_visible'][0]['protected'])

    def test_invalid_probabilities_are_not_silently_normalized(self):
        with self.assertRaises(ValueError):
            summarize(aircraft((0.,0.)),aircraft())
        with self.assertRaises(ValueError):
            summarize(aircraft((float('nan'),1.)),aircraft())

    def test_zero_score_without_conflicting_geometry_does_not_display_at_zero_threshold(self):
        far=aircraft()
        far['current']=(25.,78.,4000.)
        far['paths']=[(w,{60:(25.,78.,4000.),600:(25.,78.,4000.)}) for w in [.6,.4]]
        r=PathConfidenceMonitor(0.,consecutive=1).update({'a':aircraft(),'b':far},0)
        self.assertEqual(r['shadow_visible'],[])

    def test_worker_returns_shadow_results_without_changing_live_feed(self):
        worker=PathConfidenceWorker(PathConfidenceMonitor(.5,consecutive=1))
        try:
            result=worker.submit({'a':aircraft(),'b':aircraft()},0).result(timeout=5)
            self.assertEqual(len(result['shadow_visible']),1)
            self.assertFalse(result['live_notifications_changed'])
        finally:
            worker.close()
