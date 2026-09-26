"""Preserved evidence boundaries and diagnostics, without obsolete word bans."""
import pathlib
import string
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config
import gates
import stages

class WriterIntegrityTest(unittest.TestCase):
    def test_current_prompt_leak_is_detected(self):
        instruction = "The article should leave them understanding both what happened and why."
        self.assertTrue(gates.frazy_z_instrukcji(instruction))
        self.assertFalse(gates.frazy_z_instrukcji("The company submitted a revised technical report."))

    def test_style_diagnostics_do_not_block_a_draft(self):
        self.assertEqual(gates.verdict([{"gate": "CZYTELNIK_NIEPRZYLAPANY", "detail": "no reader address"}]), ("SAVED", None))

    def test_evidence_and_legacy_feedback_are_preserved_as_data(self):
        template = (config.PROMPTS_DIR / "pisarz.md").read_text(encoding="utf8")
        fields = {f: "" for _,f,_,_ in string.Formatter().parse(template) if f and f != "marka"}
        fields.update(card_json='{"claim": "Literal {braces}", "not_fetched": true}', poprzednie_uwagi="HISTORICAL_FEEDBACK")
        prompt = stages._prompt("pisarz.md", **fields)
        self.assertIn(fields["card_json"], prompt)
        self.assertIn("HISTORICAL_FEEDBACK", prompt)
        self.assertIn("not_fetched", prompt)
        self.assertIn("numbers_used", prompt)
        self.assertIn("limits_paragraph_present", prompt)
        self.assertEqual(config.MODEL_FOR["write"], config.FABLE)

if __name__ == "__main__":
    unittest.main()
