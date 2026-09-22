import tempfile, unittest
from pathlib import Path
import pandas as pd
from src.workflow import Workflow
from src.nurture_campaigns import campaign_records

class CampaignTests(unittest.TestCase):
 def test_marketing_owned_and_confirmed_tracking(self):
  with tempfile.TemporaryDirectory() as folder:
   w=Workflow(Path(folder)/'state.sqlite')
   try:
    records=pd.DataFrame([dict(prospect_id='n', account_name='N', segment='SMB', territory='West', email_valid=True, domain_valid=True, is_duplicate=False, total_score=50),dict(prospect_id='s', account_name='S', segment='SMB', territory='West', email_valid=True, domain_valid=True, is_duplicate=False, total_score=80)])
    reps=pd.DataFrame([dict(rep_name='Rep',available=True,territories='West',segments='SMB',current_load=0,max_capacity=5)])
    result=w.run(records,reps,now='2026-01-01')
    campaigns=campaign_records(result)
    self.assertEqual(campaigns.prospect_id.tolist(),['n'])
    self.assertNotIn('assigned_rep',campaigns)
    self.assertEqual(campaigns.iloc[0].sequence_progress,'0 / 4 sent')
    self.assertTrue(pd.isna(campaigns.iloc[0].last_email_sent))
    action=w.actions().query("kind == 'nurture_email'").iloc[0]
    w.acknowledge(action.id,now='2026-01-01T00:00:00+00:00')
    event=dict(event_id='e',prospect_id='n',type='click',occurred_at='2026-01-02T00:00:00+00:00')
    w.run(records,reps,[event],now='2026-01-02')
    result=w.run(records,reps,[event],now='2026-01-02')
    row=campaign_records(result,'marketing@company.example').iloc[0]
    self.assertEqual(row.clicks,1)
    self.assertEqual(row.email_type,'Customer use case')
    self.assertEqual(row.sequence_progress,'1 / 4 sent')
    self.assertEqual(row.sender_email,'marketing@company.example')
    self.assertEqual(result.set_index('prospect_id').loc['n','assigned_rep'],'')
   finally: w.close()
 def test_empty_campaign_schema(self):
  result=campaign_records(pd.DataFrame())
  self.assertTrue(result.empty)
  self.assertIn('email_theme',result)
