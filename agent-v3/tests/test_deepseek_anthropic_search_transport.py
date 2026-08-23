"""A-123: bounded DeepSeek search through the official Anthropic interface."""

from __future__ import annotations

import pathlib
import sys
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import llm  # noqa: E402


class DeepSeekAnthropicSearchTransportTests(unittest.TestCase):
    @staticmethod
    def message(*, text: str = '{"sources":[]}', searches: int = 2):
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[
                SimpleNamespace(
                    type="web_search_tool_result",
                    content=[SimpleNamespace(url="https://records.example/a")],
                ),
                SimpleNamespace(type="text", text=text),
            ],
            usage=SimpleNamespace(
                input_tokens=120,
                output_tokens=80,
                server_tool_use=SimpleNamespace(web_search_requests=searches),
            ),
        )

    def test_same_deepseek_model_uses_official_base_and_hard_max_uses(self) -> None:
        stream = SimpleNamespace(get_final_message=lambda: self.message())
        client = SimpleNamespace(
            messages=SimpleNamespace(stream=mock.Mock(return_value=nullcontext(stream)))
        )
        trace = []
        with mock.patch.object(
            llm.anthropic, "Anthropic", return_value=client,
        ) as constructor, mock.patch.object(
            llm, "_deepseek_pick_from_urls",
            return_value=('{"sources":[]}', 20, 10, "selector user"),
        ) as picker:
            result = llm._call_deepseek_anthropic_search(
                "discovery", "system", "user", collect_trace=trace,
            )

        self.assertEqual(
            result,
            ('{"sources":[]}', 140, 90, 2, ["https://records.example/a"]),
        )
        picker.assert_called_once_with(
            "discovery", "system", "user", ["https://records.example/a"],
            draft='{"sources":[]}',
            collect_trace=trace,
        )
        # Picker jest w tym teście zamockowany; jego własny ślad ma osobny test.
        self.assertEqual([item["request_kind"] for item in trace], ["web_search"])
        self.assertEqual(trace[0]["search_result_urls"],
                         ["https://records.example/a"])
        self.assertEqual(
            constructor.call_args.kwargs["base_url"],
            config.DEEPSEEK_ANTHROPIC_BASE_URL,
        )
        request = client.messages.stream.call_args.kwargs
        self.assertEqual(request["model"], config.MODEL_FOR["discovery"])
        self.assertEqual(request["output_config"], {"effort": "low"})
        self.assertEqual(request["tools"], [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": config.DISCOVERY_MAX_SEARCHES,
        }])

    def test_missing_text_can_use_only_urls_already_returned(self) -> None:
        stream = SimpleNamespace(
            get_final_message=lambda: self.message(text="", searches=3)
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(stream=mock.Mock(return_value=nullcontext(stream)))
        )
        with mock.patch.object(
            llm.anthropic, "Anthropic", return_value=client,
        ), mock.patch.object(
            llm, "_deepseek_pick_from_urls",
            return_value=('{"sources":[]}', 20, 10, "selector user"),
        ) as picker:
            result = llm._call_deepseek_anthropic_search(
                "discovery", "system", "user",
            )
        self.assertEqual(result[0:4], ('{"sources":[]}', 140, 90, 3))
        picker.assert_called_once_with(
            "discovery", "system", "user", ["https://records.example/a"],
            draft="",
            collect_trace=None,
        )

    def test_selector_sees_draft_and_only_exact_result_urls(self) -> None:
        response = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "usage": {"prompt_tokens": 30, "completion_tokens": 12},
                "choices": [{"message": {"content": '{"sources":[]}'}}],
            },
        )
        trace = []
        with mock.patch.object(llm.httpx, "post", return_value=response) as post:
            picked, tin, tout, selector_user = llm._deepseek_pick_from_urls(
                "discovery", "system", "original",
                ["https://records.example/a", "https://records.example/a"],
                draft="first draft",
                collect_trace=trace,
            )
        self.assertEqual((picked, tin, tout), ('{"sources":[]}', 30, 12))
        self.assertIn("SEARCH DRAFT:\nfirst draft", selector_user)
        self.assertEqual(selector_user.count("https://records.example/a"), 1)
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], config.MODEL_FOR["discovery"])
        self.assertEqual(request["messages"][1]["content"], selector_user)
        self.assertEqual(trace[0]["state"], "COMPLETED_WITH_USAGE")
        self.assertEqual(trace[0]["response"], '{"sources":[]}')

    def test_broken_stream_still_records_dispatched_request(self) -> None:
        stream = SimpleNamespace(
            get_final_message=mock.Mock(side_effect=llm.httpx.RemoteProtocolError(
                "incomplete chunked read"
            ))
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(stream=mock.Mock(return_value=nullcontext(stream)))
        )
        trace = []
        with mock.patch.object(llm.anthropic, "Anthropic", return_value=client):
            with self.assertRaises(llm.httpx.RemoteProtocolError):
                llm._call_deepseek_anthropic_search(
                    "discovery", "system", "user", collect_trace=trace,
                )
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0]["request_kind"], "web_search")
        self.assertEqual(trace[0]["state"], "FAILED_WITHOUT_FINAL_USAGE")
        self.assertIn("incomplete chunked read", trace[0]["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
