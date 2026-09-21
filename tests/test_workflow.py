import tempfile
import unittest
from pathlib import Path
import pandas as pd
from src.workflow import Workflow

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = Workflow(Path(self.tmp.name) / 'workflow.sqlite')
        self.records = pd.DataFrame([dict(prospect_id='a',account_name='A',segment='SMB',territory='West',email_valid=True,domain_valid=True,is_duplicate=False,total_score=50)])
        self.reps = pd.DataFrame([dict(rep_name='Rep',available=True,territories='West',segments='SMB',current_load=0,max_capacity=1)])
    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()
    def event(self, key, kind, at='2026-01-02'):
        return dict(event_id=key,prospect_id='a',type=kind,occurred_at=at)
    def test_recovery_idempotency_and_outcomes(self):
        self.w.run(self.records,self.reps,now='2026-01-01')
        events=[self.event('1','reply'),self.event('2','reply')]
        out=self.w.run(self.records,self.reps,events,now='2026-01-02')
        self.assertEqual(out.iloc[0].lifecycle_stage,'SQL')
        self.w.run(self.records,self.reps,events,now='2026-01-02')
        self.assertEqual(len(self.w.movements()),2)
        self.assertEqual(self.w.actions().query("kind == 'nurture_email'").iloc[0].status,'cancelled')
        self.w.run(self.records,self.reps,[self.event('3','opportunity_created')],now='2026-01-02')
        out=self.w.run(self.records,self.reps,[self.event('4','customer_won')],now='2026-01-02')
        self.assertEqual(out.iloc[0].lifecycle_stage,'Customer')
    def test_no_fake_sends_and_dormancy(self):
        self.w.run(self.records,self.reps,now='2026-01-01')
        self.w.run(self.records,self.reps,now='2026-01-30')
        self.assertEqual(self.w.records().iloc[0].nurture_touch_count,0)
        self.assertEqual(len(self.w.actions().query("kind == 'nurture_email'")),1)
        out=self.w.run(self.records,self.reps,now='2026-04-02')
        self.assertEqual(out.iloc[0].lifecycle_stage,'Dormant')
    def test_cadence_ack_and_reply(self):
        self.records.total_score=80
        self.w.run(self.records,self.reps,now='2026-01-01')
        action=self.w.actions().query("kind == 'cadence_task'").iloc[0].id
        self.assertTrue(self.w.acknowledge(action,now='2026-01-01T00:00:00+00:00'))
        self.assertFalse(self.w.acknowledge(action))
        out=self.w.run(self.records,self.reps,[self.event('1','reply')],now='2026-01-02')
        self.assertEqual(out.iloc[0].lifecycle_stage,'SQL')
        self.assertEqual(out.iloc[0].cadence_step,1)
    def test_validation_and_capacity(self):
        self.records.total_score=80
        second=self.records.copy();second.prospect_id='b'
        out=self.w.run(pd.concat([self.records,second]),self.reps,now='2026-01-01')
        self.assertEqual(out.assigned_rep.ne('').sum(),1)
        self.records.email_valid=False
        self.w.run(self.records,self.reps,now='2026-01-02')
        self.assertTrue(self.w.actions().query("lead_id == 'a' and kind == 'cadence_task'").status.eq('cancelled').all())
    def test_completed_cadence_recycles_only_after_delivery(self):
        self.records.total_score=80
        for day in ['2026-01-01', '2026-01-05', '2026-01-07', '2026-01-12', '2026-01-15']:
            self.w.run(self.records,self.reps,now=day)
            for action in self.w.actions().query("kind == 'cadence_task' and status == 'pending'").id:
                self.w.acknowledge(action, now=day+'T00:00:00+00:00')
        out=self.w.run(self.records,self.reps,now='2026-01-17')
        self.assertEqual(out.iloc[0].lifecycle_stage,'Nurture')
        self.assertEqual(out.iloc[0].cadence_step,5)
        self.assertEqual(out.iloc[0].cadence_status,'completed-no response')

    def test_transaction_rolls_back(self):
        with self.assertRaises(ValueError):
            self.w.run(self.records,self.reps,[self.event('1','unsupported')],now='2026-01-02')
        self.assertTrue(self.w.records().empty)

if __name__=='__main__': unittest.main()
