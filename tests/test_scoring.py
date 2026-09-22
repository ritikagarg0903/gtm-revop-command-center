import unittest
import pandas as pd
from src.gtm_operations import score_prospects, DEFAULT_SCORING_WEIGHTS
class ScoringTests(unittest.TestCase):
 def test_fit_intent_only_and_gate(self):
  records=pd.DataFrame([dict(email_valid=True,domain_valid=True,is_duplicate=False,fit_score=80,intent_score=60),dict(email_valid=False,domain_valid=True,is_duplicate=False,fit_score=100,intent_score=100)])
  scored=score_prospects(records,DEFAULT_SCORING_WEIGHTS)
  self.assertEqual(len(scored),1)
  self.assertEqual(scored.iloc[0].total_score,71.4)
  for value in [0,100]:
   changed=records.assign(signal_quality_score=value,data_confidence_score=value)
   self.assertEqual(score_prospects(changed,DEFAULT_SCORING_WEIGHTS).iloc[0].total_score,71.4)
  self.assertNotIn('signal_data_confidence_score',scored)
