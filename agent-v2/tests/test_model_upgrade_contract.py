"""Contract tests for candidate gates, all families and restart persistence."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import db
import llm
import nowe_modele as updater


class Upgrades(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = config.uzyj_katalogu_danych(self.root / 'data')
        self.conn = db.connect()
        self.saved = {k: copy.deepcopy(getattr(config, k)) for k in (
            *updater.ROLE, 'MODEL_FOR', 'MODEL_DO_SZUKANIA', 'MODEL_DO_SZUKANIA_DOMYSLNY',
            'WEB_SEARCH_TOOL', 'PROBY_WYSZUKIWANIA', 'WOLNO_WOLAC_MODEL', 'DRY_RUN',
            'KILL_SWITCH', 'ANTHROPIC_API_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY', '_writer')}
        config.WOLNO_WOLAC_MODEL = True
        config.DRY_RUN = config.KILL_SWITCH = False
        config.ANTHROPIC_API_KEY = config.DEEPSEEK_API_KEY = config.OPENAI_API_KEY = 'fake-key'
        config._writer = ''
        self.targets = {'CLAUDE': 'claude-opus-5-6', 'SONNET': 'claude-sonnet-5-1',
            'FABLE': 'claude-fable-5-2', 'DEEPSEEK': 'deepseek-v4.2-flash',
            'DEEPSEEK_PRO': 'deepseek-v4.2-pro', 'IMAGE_MODEL': 'gpt-image-3'}
        self.lists = {provider: {} for provider, _ in updater.ROLE.values()}
        for role, model in self.targets.items():
            self.lists[updater.ROLE[role][0]][model] = '2026-10-01'
        self.patches = [
            patch('httpx.get', side_effect=AssertionError('Unexpected real HTTP GET')),
            patch('httpx.post', side_effect=AssertionError('Unexpected real HTTP POST')),
            patch.object(updater, 'lista_modeli', return_value=self.lists),
            patch.object(updater, 'proba_odpowiedzi', return_value=(True, 'JSON OK', 20, 5)),
            patch.object(updater, 'proba_wyszukiwania', return_value=(True, 1, 30, 5, 'szuka (1 wyszukiwan)')),
            patch.object(updater, 'proba_obrazu', return_value=(True, 'PNG OK')),
        ]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        for k, value in self.saved.items():
            setattr(config, k, value)
        self.conn.close()
        config.przywroc_katalog_danych(self.paths)
        self.temp.cleanup()

    def run_check(self):
        return updater.sprawdz(conn=self.conn, wymus=True)

    def test_all_six_roles_upgrade_and_survive_fresh_process(self):
        result = self.run_check()
        self.assertEqual({d['rola'] for d in result['wykonane']}, set(self.targets))
        self.assertEqual(config.MODEL_FOR['write'], self.targets['FABLE'])
        self.assertEqual(config.MODEL_FOR['factcheck'], self.targets['DEEPSEEK'])
        self.assertEqual(config.MODEL_FOR['obraz'], self.targets['IMAGE_MODEL'])
        self.assertEqual(config.MODEL_DO_SZUKANIA_DOMYSLNY, self.targets['DEEPSEEK_PRO'])
        self.assertTrue(config.szuka_naprawde(self.targets['DEEPSEEK']))
        for name in ('config.py', 'model_registry.py'):
            shutil.copyfile(Path(config.__file__).parent / name, self.root / name)
        code = 'import config,json; print(json.dumps({"roles":{r:getattr(config,r) for r in config.ROLE_MODELI},"routing":config.MODEL_FOR}))'
        env = dict(os.environ, PYTHONPATH=str(self.root), AGENT_V2_WRITER='', AGENT_V2_CHEAP='0')
        child = subprocess.run([sys.executable, '-c', code], cwd=self.root, env=env,
                               capture_output=True, text=True, check=True)
        loaded = json.loads(child.stdout)
        self.assertEqual(loaded['roles'], self.targets)
        self.assertEqual(loaded['routing']['obraz'], self.targets['IMAGE_MODEL'])
        self.assertEqual(loaded['routing']['write'], self.targets['FABLE'])
        self.assertEqual(loaded['routing']['note'], self.targets['DEEPSEEK'])

    def test_failed_json_keeps_text_models(self):
        self.mocks[3].return_value = (False, 'HTTP 404', 0, 0)
        result = self.run_check()
        self.assertEqual([d['rola'] for d in result['wykonane']], ['IMAGE_MODEL'])
        self.assertEqual(config.FABLE, self.saved['FABLE'])
        self.assertEqual(config.DEEPSEEK, self.saved['DEEPSEEK'])

    def test_json_without_real_search_does_not_switch_deepseek(self):
        self.mocks[4].return_value = (False, 0, 10, 4, 'nie wywoluje wyszukiwarki')
        result = self.run_check()
        self.assertFalse(any(d['dostawca'] == 'deepseek' for d in result['wykonane']))
        self.assertEqual(config.DEEPSEEK, self.saved['DEEPSEEK'])
        self.assertEqual(config.MODEL_FOR['note'], self.saved['MODEL_FOR']['note'])
        self.assertNotIn('DEEPSEEK', updater.wczytaj()['zamiany'])

    def test_search_outage_does_not_erase_last_good_capability(self):
        self.mocks[4].return_value = (False, 0, 0, 0, 'HTTP 503: outage')
        proof = {'dziala': True, 'kiedy': '2026-09-24T10:00:00+00:00',
                 'droga': config.DROGA_WYSZUKIWANIA_DEEPSEEK}
        updater.zapisz({'wyszukiwanie': {config.DEEPSEEK: proof}})
        self.run_check()
        self.assertEqual(updater.wczytaj()['wyszukiwanie'][config.DEEPSEEK], proof)

    def test_failed_image_keeps_existing_generator(self):
        self.mocks[5].return_value = (False, 'invalid PNG')
        self.run_check()
        self.assertEqual(config.IMAGE_MODEL, self.saved['IMAGE_MODEL'])
        self.assertEqual(config.MODEL_FOR['obraz'], self.saved['MODEL_FOR']['obraz'])

    def test_failed_persistence_leaves_routing_unchanged(self):
        with patch.object(updater, 'zapisz', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.run_check()
        self.assertEqual(config.MODEL_FOR, self.saved['MODEL_FOR'])
        self.assertEqual(config.FABLE, self.saved['FABLE'])
        self.assertFalse((config.DATA_DIR / 'dziennik.jsonl').exists())

    def test_family_boundaries_and_malformed_state(self):
        self.assertEqual(config.zamiany_z_danych({'zamiany': []}), {})
        self.assertEqual(config.zamiany_z_danych({'zamiany': {
            'DEEPSEEK': {'na': 'deepseek-v4.2-pro'}, 'FABLE': {'na': 'claude-opus-6'},
            'IMAGE_MODEL': {'na': 'claude-fable-6'}}}), {})
        for model in ('deepseek-v4.2-flash-preview', 'claude-fable-6-beta', 'gpt-image-3-mini'):
            self.assertFalse(any(updater.w_rodzinie(model, *family) for family in updater.ROLE.values()))

    def test_dates_are_not_versions_and_stable_image_name_wins(self):
        self.assertEqual(updater.wersja('gpt-image-2.5-sunburst-2026-09-08'), (2, 5))
        self.assertEqual(updater.wersja('deepseek-v4-pro-0813'), (4,))
        models = {'gpt-image-2': 1, 'gpt-image-2.5-flare': 2,
                  'gpt-image-2.5-sunburst': 3, 'gpt-image-2.5-sunburst-2026-09-08': 4}
        self.assertEqual(updater.najlepszy_w_rodzinie('openai', 'gpt-image', models),
                         'gpt-image-2.5-sunburst')

    def test_repeated_check_costs_nothing_and_existing_alias_stays(self):
        self.run_check()
        calls = self.mocks[3].call_count
        self.assertIn('pominiete', updater.sprawdz(conn=self.conn))
        self.assertEqual(self.mocks[3].call_count, calls)
        self.assertEqual(updater.zdecyduj({'DEEPSEEK': 'deepseek-flash'},
            {'deepseek': {'deepseek-flash': None}}), [])

    def test_explicit_writer_override_remains_pinned(self):
        config._writer = config.FABLE
        self.run_check()
        self.assertEqual(config.MODEL_FOR['write'], self.saved['FABLE'])
        self.assertEqual(config.FABLE, self.targets['FABLE'])

    def test_anthropic_second_page_and_openai_catalog(self):
        import httpx
        self.patches[2].stop()
        pages = [
            {'data': [{'id':'claude-fable-5-1'}], 'has_more': True, 'last_id': 'cursor'},
            {'data': [{'id':'claude-fable-5-2'}], 'has_more': False},
            {'data': [{'id':'deepseek-flash'}]},
            {'data': [{'id':'gpt-image-3'}, {'id':'gpt-6'}, {'id':'gpt-image-4-preview'}]},
        ]
        self.mocks[0].side_effect = [httpx.Response(200, json=p,
            request=httpx.Request('GET','https://example.test')) for p in pages]
        catalogs = updater.lista_modeli()
        self.assertIn('claude-fable-5-2', catalogs['anthropic'])
        self.assertEqual(catalogs['openai'], {'gpt-image-3': None})
        self.assertEqual(self.mocks[0].call_args_list[1].kwargs['params']['after_id'], 'cursor')

    def test_new_image_uses_openai_key_before_switch(self):
        self.assertEqual(llm.dostawca('gpt-image-3'), 'openai')
        config.OPENAI_API_KEY = ''
        result = self.run_check()
        self.assertEqual(config.IMAGE_MODEL, self.saved['IMAGE_MODEL'])
        self.assertTrue(any(d['rola']=='IMAGE_MODEL' and 'OPENAI_API_KEY' in d['dlaczego']
                            for d in result['odrzucone']))

    def test_image_cost_uses_actual_usage(self):
        cost, note = llm.koszt_obrazu('gpt-image-2.5-sunburst',
            {'input_tokens': 100, 'output_tokens': 2000,
             'input_tokens_details': {'text_tokens': 100, 'image_tokens': 0}})
        self.assertAlmostEqual(cost, .0605)
        self.assertIn('nie faktura', note)


if __name__ == '__main__':
    unittest.main()
