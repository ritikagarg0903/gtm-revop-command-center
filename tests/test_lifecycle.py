import unittest
import pandas as pd
from src.generate_data import generate_prospects, generate_rep_capacity
from src.gtm_operations import score_prospects, route_leads
from src.lifecycle import simulate_lifecycle, lifecycle_metrics

class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prospects = generate_prospects()
        cls.reps = generate_rep_capacity()
        cls.scored = score_prospects(cls.prospects, {'fit': 4, 'intent': 3})
        cls.routed = route_leads(cls.scored[cls.scored.review_status.eq('Approved')], cls.reps)
        cls.result = simulate_lifecycle(cls.prospects, cls.scored, cls.routed, cls.reps, '2026-09-21')

    def test_outreach_gate(self):
        bad = self.result[~self.result.email_valid | ~self.result.domain_valid | self.result.is_duplicate]
        self.assertTrue(bad.nurture_entry_date.isna().all())
        self.assertTrue(bad.cadence_start_date.isna().all())
        self.assertTrue(bad.next_action.str.contains('Repair').all())

    def test_nurture_recovery_and_dormancy(self):
        recovered = self.result[self.result.re_engagement_date.notna()]
        self.assertGreater(len(recovered), 0)
        self.assertTrue(recovered.engagement_score.ge(20).all())
        self.assertTrue(recovered.lifecycle_stage.eq('SQL').all())
        dormant = self.result[self.result.status.eq('dormant')]
        self.assertGreater(len(dormant), 0)
        self.assertTrue(dormant.engagement_score.eq(0).all())
        self.assertTrue((pd.Timestamp('2026-09-21') - dormant.nurture_entry_date).dt.days.ge(90).all())
        self.assertTrue(self.result.nurture_touch_count.le(4).all())

    def test_cadence_history_and_metrics(self):
        enrolled = self.result[self.result.cadence_start_date.notna()]
        self.assertGreater(len(enrolled), 0)
        self.assertTrue(enrolled.assigned_rep.ne('').all())
        completed = enrolled[enrolled.cadence_status.eq('completed-no response')]
        self.assertTrue(completed.nurture_entry_date.notna().all())
        self.assertTrue(completed.cadence_step.eq(5).all())
        responded = enrolled[enrolled.response_date.notna()]
        self.assertTrue((responded.last_touch_date <= responded.response_date).all())
        metrics = lifecycle_metrics(self.result)
        self.assertEqual(metrics['unassigned_before'] - metrics['unassigned_after'], len(enrolled))
        self.assertAlmostEqual(metrics['response_rate'], 100 * len(responded) / len(enrolled))
        for _, r in enrolled.iterrows():
            rep = self.reps.set_index('rep_name').loc[r.assigned_rep]
            self.assertIn(r.territory, rep.territories.split('|'))
            self.assertIn(r.segment, rep.segments.split('|'))
            self.assertTrue(rep.available)

    def test_empty_and_deterministic(self):
        empty_route = route_leads(self.scored.iloc[:0], self.reps)
        empty = simulate_lifecycle(self.prospects.iloc[:0], self.scored.iloc[:0], empty_route, self.reps)
        self.assertEqual(lifecycle_metrics(empty)['cadence_total'], 0)
        pd.testing.assert_frame_equal(self.result, simulate_lifecycle(self.prospects, self.scored, self.routed, self.reps, '2026-09-21'))

    def test_no_available_owners(self):
        reps = self.reps.assign(available=False)
        routes = route_leads(self.scored[self.scored.review_status.eq('Approved')], reps)
        result = simulate_lifecycle(self.prospects, self.scored, routes, reps)
        m = lifecycle_metrics(result)
        self.assertEqual(m['unassigned_before'], m['unassigned_after'])
        self.assertEqual(m['cadence_total'], 0)

if __name__ == '__main__':
    unittest.main()
