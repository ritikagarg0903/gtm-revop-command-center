import unittest
import pandas as pd
from src.demo_activity import demo_activity, email_metrics

class DemoTests(unittest.TestCase):
 def test_consistent_demo_and_no_input_mutation(self):
  leads=pd.DataFrame([dict(prospect_id=f'P-{i:05}',account_name=f'Company {i}',segment='SMB',blocked=False,assigned_rep='',nurture_entry_date=None,re_engagement_date=None,status='active',lifecycle_stage='MQL',engagement_score=0,nurture_touch_count=0,cadence_step=0) for i in range(500)])
  before=leads.copy(deep=True)
  mix,campaigns,emails=demo_activity(leads,'2026-09-22T00:00:00Z')
  pd.testing.assert_frame_equal(leads,before)
  self.assertTrue({'MQL','SQL','Opportunity','Customer','Nurture','Dormant'}.issubset(set(mix.lifecycle_stage)))
  self.assertTrue({'Active','Completed','Bounced','Unsubscribed','Recovered to SQL','Dormant'}.issubset(set(campaigns.campaign_status)))
  self.assertEqual(campaigns.emails_sent.sum(),len(emails))
  self.assertEqual(campaigns.emails_delivered.sum(),emails.delivered.sum())
  rates=email_metrics(emails)
  self.assertAlmostEqual(rates['open_rate'],100*emails.opened.sum()/emails.delivered.sum())
  self.assertTrue((emails.sent_at<=pd.Timestamp('2026-09-22T00:00:00Z')).all())
  stopped=campaigns[campaigns.campaign_status.isin(['Completed','Dormant','Unsubscribed','Bounced','Recovered to SQL'])]
  self.assertTrue(stopped.next_email_due.isna().all())
  self.assertTrue(mix.loc[mix.status.eq('nurture'),'assigned_rep'].eq('').all())
