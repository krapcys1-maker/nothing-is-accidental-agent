"""Oba transporty stosuja ustawienia etapu; selekcja zachowuje domyslne API.
Bez sieci i platnych wywolan. Uruchomic z korzenia repozytorium.
"""
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, "agent-v2")
import config
config.uzyj_katalogu_danych(pathlib.Path(tempfile.mkdtemp()))
import llm

class Response:
    def raise_for_status(self):
        pass
    def json(self):
        return {
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "content": [{"type": "text", "text": "{}"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }

class ThinkingTest(unittest.TestCase):
    def test_short_writers_disable_thinking_on_both_transports(self):
        for purpose in ("note", "note_tani", "restack"):
            for transport in (llm._call_deepseek, llm._call_deepseek_z_siecia):
                with self.subTest(purpose=purpose, transport=transport.__name__):
                    with patch.object(llm.httpx, "post", return_value=Response()) as post:
                        transport(purpose, "system", "source")
                    body = post.call_args.kwargs["json"]
                    self.assertEqual(body["model"], config.DEEPSEEK)
                    self.assertEqual(body["thinking"], {"type": "disabled"})
                    self.assertEqual(body["max_tokens"], config.MAX_TOKENS[purpose])
                    if transport is llm._call_deepseek_z_siecia:
                        self.assertEqual(body["tools"][0]["name"], "web_search")

    def test_selection_and_factchecking_keep_provider_defaults(self):
        for purpose in ("cele", "wybor", "factcheck", "bank", "classify", "discovery"):
            for transport in (llm._call_deepseek, llm._call_deepseek_z_siecia):
                with self.subTest(purpose=purpose, transport=transport.__name__):
                    with patch.object(llm.httpx, "post", return_value=Response()) as post:
                        transport(purpose, "system", "source")
                    self.assertNotIn("thinking", post.call_args.kwargs["json"])

    def test_target_effort_reaches_both_transports_without_changing_other_stages(self):
        for purpose in ("cele", "factcheck", "comment", "reply"):
            for transport in (llm._call_deepseek, llm._call_deepseek_z_siecia):
                with self.subTest(purpose=purpose, transport=transport.__name__):
                    with patch.object(llm.httpx, "post", return_value=Response()) as post:
                        transport(purpose, "system", "source")
                    body = post.call_args.kwargs["json"]
                    if purpose == "cele":
                        if transport is llm._call_deepseek:
                            self.assertEqual(body["reasoning_effort"], "low")
                            self.assertNotIn("output_config", body)
                        else:
                            self.assertEqual(body["output_config"], {"effort": "low"})
                            self.assertNotIn("reasoning_effort", body)
                    else:
                        self.assertNotIn("reasoning_effort", body)
                        self.assertNotIn("output_config", body)

    def test_analysis_conversations_and_corrections_still_think(self):
        for purpose in ("rozbior", "comment", "reply", "naprawa", "naprawa_komentarza"):
            for transport in (llm._call_deepseek, llm._call_deepseek_z_siecia):
                with self.subTest(purpose=purpose, transport=transport.__name__):
                    with patch.object(llm.httpx, "post", return_value=Response()) as post:
                        transport(purpose, "system", "source")
                    self.assertEqual(post.call_args.kwargs["json"]["thinking"], {"type": "enabled"})

    def test_config_is_copied_and_unknown_stages_have_no_override(self):
        settings = config.myslenie_deepseek("note")
        settings["type"] = "enabled"
        self.assertEqual(config.myslenie_deepseek("note"), {"type": "disabled"})
        self.assertIsNone(config.myslenie_deepseek("unknown"))
        with patch.dict(config.DEEPSEEK_MYSLENIE, {"cele": {}}):
            self.assertIsNone(config.myslenie_deepseek("cele"))

    def test_bank_judge_low_effort_and_scout_without_thinking_only_offline(self):
        # 27.09.2026, zywe testy A/B — patrz config.DEEPSEEK_EFFORT_FOR["bank"]
        # i config.DEEPSEEK_MYSLENIE_BEZ_SIECI. Sedzia banku rozumuje nisko,
        # skaut na spizarni nie rozumuje, a skaut SZUKAJACY w sieci zostaje przy
        # domyslnym ustawieniu dostawcy, bo tego nikt nie mierzyl.
        with patch.object(llm.httpx, "post", return_value=Response()) as post:
            llm._call_deepseek("bank", "system", "source")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertNotIn("thinking", body)
        with patch.object(llm.httpx, "post", return_value=Response()) as post:
            llm._call_deepseek("curiosity", "system", "source")
        self.assertEqual(post.call_args.kwargs["json"]["thinking"], {"type": "disabled"})
        with patch.object(llm.httpx, "post", return_value=Response()) as post:
            llm._call_deepseek_z_siecia("curiosity", "system", "source")
        self.assertNotIn("thinking", post.call_args.kwargs["json"])
        self.assertIsNone(config.myslenie_deepseek("curiosity"))
        self.assertEqual(config.myslenie_deepseek("curiosity", siec=False),
                         {"type": "disabled"})

if __name__ == "__main__":
    unittest.main()
