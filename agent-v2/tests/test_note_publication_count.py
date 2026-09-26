"""The real daily note block counts confirmed publications, not drafted attempts."""
import ast
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock


class NotePublicationCount(unittest.TestCase):
    def execute_block(self, outcome):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'run.py').read_text(encoding='utf-8'))
        daily = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dzien')
        block = next(n for n in daily.body if isinstance(n, ast.FunctionDef) and n.name == 'notki')
        stages = MagicMock()
        stages.notki_dnia.return_value = [{'candidates': [{'note': 'A checked note.', 'safe_to_post': True}],
                                         'type': 'CIEKAWOSTKA', 'fakt': 'A sourced fact.',
                                         'fakt_wpis': {'fact': 'A sourced fact.'}}]
        stages.zwroc_kandydatow.return_value = 1
        browser = MagicMock()
        browser.wystaw_notke.return_value = outcome
        env = {'conn': None, 'run_id': 1, 'wyslij': True, 'stages': stages,
               'browser': browser, 'config': SimpleNamespace(ZWLOKA_PRZED_NOTKAMI=(0, 0)),
               'time': MagicMock(), 'na_teraz': {'notki': 1}, 'juz': {'notki': 0},
               'zostal_czas': lambda *a: True, 'rytm': lambda *a: True,
               'rytm_stanu': {}, 'zrobione': {'notki': 0}}
        exec(compile(ast.Module(body=[block], type_ignores=[]), '<real daily note block>', 'exec'), env)
        with contextlib.redirect_stdout(io.StringIO()):
            env['notki']()
        return env['zrobione']['notki'], stages

    def test_rejected_publication_is_zero_and_fact_returns(self):
        count, stages = self.execute_block({'wyslane': False, 'pominiete': True})
        self.assertEqual(count, 0)
        stages.zwroc_kandydatow.assert_called_once()
        stages.zapisz_zuzyte.assert_not_called()

    def test_confirmed_publication_is_one(self):
        count, stages = self.execute_block({'wyslane': True, 'id': '123'})
        self.assertEqual(count, 1)
        stages.zapisz_zuzyte.assert_called_once()

    def test_existing_publication_is_not_new(self):
        count, _ = self.execute_block({'wyslane': True, 'pominiete': True})
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
