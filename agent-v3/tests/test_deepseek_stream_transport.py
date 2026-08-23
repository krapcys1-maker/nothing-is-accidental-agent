"""Offline parser contracts for the DeepSeek SSE transport."""

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
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    body = ("\n\n".join(lines) + "\n\n").encode("utf-8")
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=body,
        request=request,
    )


def _data(value) -> str:
    return "data: " + json.dumps(value, separators=(",", ":"))


class DeepSeekStreamTransportTests(unittest.TestCase):
    def complete_lines(self) -> list[str]:
        return [
            _data({
                "id": "resp-live-1",
                "choices": [{
                    "index": 0,
                    "delta": {
                        "reasoning_content": "private reasoning", "content": None,
                    },
                    "finish_reason": None,
                }],
                "usage": None,
            }),
            _data({
                "id": "resp-live-1",
                "choices": [{
                    "index": 0,
                    "delta": {"content": "{\"topics\":[]"},
                    "finish_reason": None,
                }],
                "usage": None,
            }),
            _data({
                "id": "resp-live-1",
                "choices": [{
                    "index": 0,
                    "delta": {"content": ",\"ranking\":{}}"},
                    "finish_reason": "stop",
                }],
                "usage": None,
            }),
            _data({
                "id": "resp-live-1",
                "choices": [],
                "usage": {
                    "prompt_tokens": 120,
                    "prompt_cache_hit_tokens": 20,
                    "prompt_cache_miss_tokens": 100,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            }),
            "data: [DONE]",
        ]

    def test_complete_stream_collects_content_usage_and_requests_usage_chunk(self) -> None:
        response = _response(self.complete_lines())
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(response)
        ) as stream:
            result = llm._call_deepseek("scout", "system", "user")
        self.assertEqual(result, ('{"topics":[],"ranking":{}}', 100, 80, 0, 20))
        request_json = stream.call_args.kwargs["json"]
        self.assertIs(request_json["stream"], True)
        self.assertEqual(request_json["stream_options"], {"include_usage": True})
        self.assertEqual(request_json["model"], config.MODEL_FOR["scout"])

    def test_clean_end_without_done_is_unknown_protocol_failure(self) -> None:
        lines = self.complete_lines()[:-1]
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaisesRegex(httpx.RemoteProtocolError, "without data"):
                llm._call_deepseek("scout", "system", "user")

    def test_done_without_usage_is_unknown_protocol_failure(self) -> None:
        lines = self.complete_lines()
        del lines[-2]
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaisesRegex(httpx.RemoteProtocolError, "without the requested"):
                llm._call_deepseek("scout", "system", "user")

    def test_length_finish_is_truncated_not_valid_json(self) -> None:
        lines = self.complete_lines()
        chunk = json.loads(lines[2][len("data: "):])
        chunk["choices"][0]["finish_reason"] = "length"
        lines[2] = _data(chunk)
        with mock.patch.object(
            llm.httpx, "stream", return_value=nullcontext(_response(lines))
        ):
            with self.assertRaises(llm.Truncated):
                llm._call_deepseek("scout", "system", "user")


if __name__ == "__main__":
    unittest.main()
