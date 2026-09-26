"""Preflight avoids paid drafts; voice memory contains only successful publications."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "agent-v2")
import config
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp(prefix="nia-package-test-")))
import browser
import stages


class PreflightTest(unittest.TestCase):
    def check(self, api_result, fields=(), page_error=None):
        page = MagicMock()
        page.locator.return_value.count.return_value = len(fields)
        nodes = []
        for visible, editable in fields:
            node = MagicMock()
            node.is_visible.return_value = visible
            node.is_editable.return_value = editable
            nodes.append(node)
        page.locator.return_value.nth.side_effect = nodes
        if page_error:
            page.goto.side_effect = page_error
        context = MagicMock()
        context.new_page.return_value = page
        runtime, br = MagicMock(), MagicMock()
        with patch.object(browser, "podlacz_sie", return_value=(runtime, br, context)), \
             patch.object(browser, "wymagaj_sesji"), \
             patch.object(browser, "hosty_gdzie_komentarz_nie_wchodzi", return_value=set()), \
             patch.object(browser, "zapamietaj_platny_host") as remember, \
             patch.object(browser, "api_json", side_effect=api_result if isinstance(api_result, Exception) else None,
                          return_value=api_result):
            result = browser.mozna_komentowac("https://writer.substack.com/p/a-post")
        page.close.assert_called_once()
        br.close.assert_called_once()
        runtime.stop.assert_called_once()
        page.keyboard.type.assert_not_called()
        for node in nodes:
            node.click.assert_not_called()
        return result, page, remember

    def test_unknown_permissions_require_visible_editable_field(self):
        for api in ({"type": "post"}, {}, None, {"write_comment_permissions": "future_value"}):
            with self.subTest(api=api):
                self.assertTrue(self.check(api, [(False, True), (True, True)])[0])
                result, _, remember = self.check(api, [(False, True), (True, False)])
                self.assertFalse(result)
                remember.assert_not_called()

    def test_failed_api_can_use_working_ui(self):
        self.assertTrue(self.check(TimeoutError(), [(True, True)])[0])

    def test_failed_ui_skips_one_attempt_without_banning_host(self):
        result, _, remember = self.check({}, page_error=TimeoutError())
        self.assertFalse(result)
        remember.assert_not_called()

    def test_paid_permissions_stop_without_loading_editor(self):
        result, page, remember = self.check({"write_comment_permissions": "only_paid"})
        self.assertFalse(result)
        page.goto.assert_not_called()
        remember.assert_called_once_with("writer.substack.com", "only_paid")

    def test_explicit_public_permission_keeps_fast_path(self):
        result, page, _ = self.check({"write_comment_permissions": "everyone"})
        self.assertTrue(result)
        page.goto.assert_not_called()


class VoiceMemoryTest(unittest.TestCase):
    def setUp(self):
        self.path = config.DATA_DIR / "dziennik.jsonl"
        self.path.unlink(missing_ok=True)

    def record(self, text, kind="komentarz", success=True):
        return json.dumps({"rodzaj": kind, "udane": success, "tekst": text})

    def test_recent_successes_only_deduplicated_and_bounded(self):
        rows = [self.record("older " + str(i)) for i in range(8)]
        rows += [self.record("latest"), self.record("latest"), self.record("failed", success=False),
                 self.record("another kind", kind="notka"), "broken", "null",
                 self.record(None), self.record(12)]
        self.path.write_text("\n".join(rows), encoding="utf-8")
        memory = stages.pamiec_glosu("komentarz.md")
        self.assertIn('"latest"', memory)
        self.assertEqual(memory.count('"latest"'), 1)
        self.assertIn("older 5", memory)
        self.assertNotIn("older 4", memory)
        self.assertNotIn("failed", memory)
        self.assertNotIn("another kind", memory)
        self.assertIn("not this conversation", memory)

    def test_large_history_and_partial_last_record_do_not_break_prompt(self):
        self.path.write_text(self.record("x" * 150000) + "\n" + self.record("fresh") + '\n{"broken":', encoding="utf-8")
        self.assertIn("fresh", stages.pamiec_glosu("komentarz.md"))

    def test_clips_long_text_and_excludes_repairs_articles_and_existing_note_memory(self):
        self.path.write_text(self.record("word " * 1000), encoding="utf-8")
        self.assertLess(len(stages.pamiec_glosu("komentarz.md")), 600)
        for name in ("pisarz.md", "naprawa.md", "notka.md"):
            self.assertEqual(stages.pamiec_glosu(name), "")

    def test_missing_history_is_empty(self):
        self.assertEqual(stages.pamiec_glosu("komentarz.md"), "")

    def test_skip_after_full_text_does_not_pay_for_factchecking(self):
        answer = {"comment": None, "reason_if_silent": "no_addition", "pierwsze_slowa": "The answer is already supplied", "what_it_adds": "The proposed question is answered in the final paragraph."}
        with patch.object(stages.llm, "call", return_value=json.dumps(answer)) as call, \
             patch.object(stages, "zweryfikuj") as verify:
            result = stages.comment_on(None, 0, {"text": "The answer is already supplied", "co_dodamy": "Ask for the answer"})
        self.assertFalse(any(c.get("safe_to_post") for c in result["candidates"]))
        verify.assert_not_called()
        self.assertTrue(all(c.args[0] == "comment" for c in call.call_args_list))
        self.assertIn("no_addition", stages.POWODY_CISZY)


if __name__ == "__main__":
    unittest.main()
