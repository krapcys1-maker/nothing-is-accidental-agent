"""Offline contracts for streamed DeepSeek /responses discovery."""

from __future__ import annotations

import json
import pathlib
import sys
import unittest
from contextlib import nullcontext
from unittest import mock

import httpx


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
import llm  # noqa: E402


def _response(lines: list[str]) -> httpx.Response:
    request = httpx.Request("POST", "https://api.deepseek.com/responses")
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=("\n\n".join(lines) + "\n\n").encode("utf-8"),
        request=request,
    )


def _event(name: str, value: dict) -> str:
    return "event: " + name + "\n" + "data: " + json.dumps(
        value, separators=(",", ":")
    )


def _completed(*, status: str = "completed", usage: bool = True) -> dict:
    response = {
        "id": "resp-search-live-1",
        "status": status,
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [{
                        "url": "https://records.example/rule#ws_call_id=abc"
                    }]
                },
            },
            {
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": "{\"sources\":[{\"url\":\"https://records.example/rule\"}]}",
                    "annotations": [],
                }],
            },
        ],
    }
    if usage:
        response["usage"] = {"input_tokens": 120, "output_tokens": 80}
    if status != "completed":
        response["incomplete_details"] = {"reason": "max_output_tokens"}
    return {"type": "response.completed", "response": response}


class DeepSeekResponsesStreamTests(unittest.TestCase):
    def complete_lines(self) -> list[str]:
        return [
            ": keep-alive",
            _event("response.created", {
                "type": "response.created",
                "response": {"id": "resp-search-live-1"},
            }),
            _event("response.output_text.delta", {
                "type": "response.output_text.delta", "delta": "{\"sources\":"
            }),
            _event("response.completed", _completed()),
            "data: [DONE]",
        ]

    def test_completed_stream_returns_text_usage_searches_and_exact_urls(self) -> None:
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(self.complete_lines()))
        ) as stream:
            result = llm._call_deepseek_responses("discovery", "system", "user")
        self.assertEqual(
            result,
            (
                '{"sources":[{"url":"https://records.example/rule"}]}',
                120,
                80,
                1,
                ["https://records.example/rule"],
            ),
        )
        request_json = stream.call_args.kwargs["json"]
        self.assertIs(request_json["stream"], True)
        self.assertEqual(request_json["model"], config.MODEL_FOR["discovery"])
        self.assertEqual(request_json["tools"], [{"type": "web_search"}])

    def test_stream_end_without_completed_preserves_partial_diagnostic(self) -> None:
        lines = self.complete_lines()[0:3]
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaisesRegex(
                httpx.RemoteProtocolError, "without response.completed.*partial_content_chars=11"
            ):
                llm._call_deepseek_responses("discovery", "system", "user")

    def test_completed_without_usage_is_protocol_failure(self) -> None:
        lines = [
            _event("response.completed", _completed(usage=False)),
            "data: [DONE]",
        ]
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaisesRegex(httpx.RemoteProtocolError, "lacks usage"):
                llm._call_deepseek_responses("discovery", "system", "user")

    def test_incomplete_terminal_status_is_truncated(self) -> None:
        lines = [
            _event("response.completed", _completed(status="incomplete")),
            "data: [DONE]",
        ]
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaises(llm.Truncated):
                llm._call_deepseek_responses("discovery", "system", "user")


if __name__ == "__main__":
    unittest.main(verbosity=2)
