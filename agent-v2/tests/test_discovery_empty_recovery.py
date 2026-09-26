"""Recover empty live search replies without buying the searches again."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config, db, llm, stages

A='https://example.org/reports/incident'
B='https://example.org/invented'

class RecoveryTests(unittest.TestCase):
    def discovery(self, text='', urls=(A,), recovery=None, error=None):
        self.calls=[]
        def call(purpose, system, user, **kw):
            self.calls.append((purpose,kw,user,db.AKCJA))
            if purpose=='discovery':
                kw['collect_urls'].extend(urls)
                return text
            if error: raise error
            return json.dumps(recovery if recovery is not None else {'sources':[{'url':A,'class':'SUPPORTING'}]})
        with patch.object(llm,'call',side_effect=call), patch.object(stages,'hosty_ktore_nigdy_nie_dzialaly',return_value=[]):
            return stages.discovery(None,1,'Why did notification take weeks?',[])

    def test_empty_reply_recovers_once_without_searching_again(self):
        result=self.discovery()
        self.assertEqual([s['url'] for s in result],[A])
        self.assertEqual([c[0] for c in self.calls],['discovery','discovery_recovery'])
        self.assertIs(self.calls[1][1]['web_search'],False)
        self.assertIn(A,self.calls[1][2])
        self.assertEqual([c[3] for c in self.calls],['artykul','artykul'])

    def test_no_actual_results_does_not_buy_a_recovery(self):
        with self.assertRaisesRegex(ValueError,'brak wynikow'):
            self.discovery(urls=())
        self.assertEqual(len(self.calls),1)

    def test_invented_path_on_real_domain_cannot_pass_recovery(self):
        result=self.discovery(recovery={'sources':[{'url':B},{'url':A}]})
        self.assertEqual([s['url'] for s in result],[A])

    def test_good_json_does_not_add_paid_call(self):
        self.discovery(text=json.dumps({'sources':[{'url':A}]}))
        self.assertEqual(len(self.calls),1)

    def test_global_budget_failure_still_propagates(self):
        with self.assertRaises(llm.BudgetExceeded):
            self.discovery(error=llm.BudgetExceeded('stop'))

    def test_empty_recovery_fails_without_a_loop(self):
        with self.assertRaises(ValueError):
            self.discovery(recovery={'sources':[]})
        self.assertEqual(len(self.calls),2)

    def test_recovery_keeps_flash_and_small_token_ceiling(self):
        self.assertEqual(config.MODEL_FOR['discovery_recovery'],config.DEEPSEEK)
        self.assertEqual(config.myslenie_deepseek('discovery_recovery'),{'type':'disabled'})
        self.assertEqual(config.MAX_TOKENS['discovery_recovery'],6000)

if __name__=='__main__': unittest.main(verbosity=2)
