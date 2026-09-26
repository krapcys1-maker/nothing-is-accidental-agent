"""Feedback comes from successful publications, without another model call."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import config
import stages


class DeliveryMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = patch.object(config, "DATA_DIR", pathlib.Path(self.temp.name))
        self.directory.start()
        self.addCleanup(self.directory.stop)
        self.calls = patch.object(stages.llm, "call", side_effect=AssertionError("No API needed"))
        self.calls.start()
        self.addCleanup(self.calls.stop)

    def memory(self, rows, prompt="komentarz.md"):
        (config.DATA_DIR / "dziennik.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        return stages.pamiec_glosu(prompt)

    def row(self, text, kind="komentarz", ok=True):
        return dict(tekst=text, rodzaj=kind, udane=ok)

    def test_two_recent_questions_include_soft_feedback(self):
        out = self.memory([self.row("Who checks?"), self.row("Where is the record?")])
        self.assertIn("## Delivery feedback", out)
        self.assertIn("unless a real unanswered question is essential", out)
        self.assertIn("Do not invent", out)

    def test_question_after_excerpt_limit_is_counted(self):
        out = self.memory([self.row("One " * 100 + "why?"), self.row("Two " * 100 + "how?")])
        self.assertIn("## Delivery feedback", out)
        self.assertNotIn("why?", out)

    def test_failed_drafts_and_other_channels_cannot_trigger_feedback(self):
        for row in (self.row("Second?", ok=False), self.row("Second?", kind="odpowiedz")):
            with self.subTest(row=row):
                out = self.memory([self.row("First?"), row])
                self.assertNotIn("## Delivery feedback", out)

    def test_duplicate_journal_rows_do_not_count_twice(self):
        out = self.memory([self.row("Same?"), self.row("Same?")])
        self.assertNotIn("## Delivery feedback", out)

    def test_intervening_statement_resets_question_streak(self):
        out = self.memory([self.row("First?"), self.row("Second?"), self.row("A supported judgment.")])
        self.assertNotIn("## Delivery feedback", out)

    def test_replies_and_restacks_receive_their_own_feedback(self):
        for kind, template in (("odpowiedz", "odpowiedz.md"), ("restack", "restack.md")):
            with self.subTest(kind=kind):
                out = self.memory([self.row("First?", kind), self.row("Second?", kind)], template)
                self.assertIn("## Delivery feedback", out)

    def test_reply_opener_follows_reader_without_random_instruction(self):
        self.calls.stop()
        with patch.object(config, "COMMENT_CANDIDATES", 1), \
             patch.object(config, "losowe_otwarcie", side_effect=AssertionError("No random opener")), \
             patch.object(stages.llm, "call", return_value=json.dumps({"reply": "A fifth.", "kind": "answer"})) as call:
            stages.reply_to(None, 0, {"text": "What is six out of thirty?"}, {})
        self.assertIn("Start with the answer or the specific point this reader raises.", call.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
