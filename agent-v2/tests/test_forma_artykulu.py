"""Article length follows depth; rhetoric is not randomly assigned."""
import pathlib
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config
import stages

class ArticleShapeTest(unittest.TestCase):
    def test_every_depth_reaches_writer_with_its_plan_and_no_rhetorical_lottery(self):
        for depth in ("THIN", "SINGLE", "RICH"):
            with self.subTest(depth=depth), \
                 patch.object(config, "losowy_ruch_koncowy", side_effect=AssertionError("random ending")), \
                 patch.object(config, "losowa_liczba_paraleli", side_effect=AssertionError("parallel quota")), \
                 patch.object(stages, "ostatnie_uwagi", return_value=""), \
                 patch.object(stages.llm, "call", return_value='{"body":"Readable text."}') as call:
                result = stages.write(None, 0, {"confirmed_claims": [], "parallel_mechanisms": []}, depth)
                prompt = call.call_args.args[2]
                plan = config.dlugosc_dla(depth)
                self.assertIn(str(plan["cel"]), prompt)
                self.assertIn(str(plan["min"]), prompt)
                self.assertIn(str(plan["max"]), prompt)
                self.assertEqual(result["body"], "Readable text.")

if __name__ == "__main__":
    unittest.main()
