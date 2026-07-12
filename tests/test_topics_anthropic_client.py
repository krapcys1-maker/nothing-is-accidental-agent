"""Offline parser and client-contract tests for topic generation."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from app.llm.anthropic_client import AnthropicLLMClient, _parse_topic_response
from app.llm.base import (
    LLMParseError,
    LLMProviderError,
    LLMSchemaValidationError,
    Usage,
)


def _payload(*, title: str = "Why queues form") -> str:
    return json.dumps({
        "topics": [{
            "title": title,
            "question": "What system creates them?",
            "score_breakdown": {"curiosity": 0.8, "source_quality": 1},
        }],
    })


def test_parser_accepts_raw_json():
    ideas = _parse_topic_response(_payload())
    assert ideas[0].title == "Why queues form"
    assert ideas[0].score_breakdown == {"curiosity": 0.8, "source_quality": 1.0}


@pytest.mark.parametrize("opening", ["```json", "```"])
def test_parser_removes_one_complete_outer_fence(opening):
    ideas = _parse_topic_response(f"{opening}\n{_payload()}\n```")
    assert [idea.title for idea in ideas] == ["Why queues form"]


def test_parser_accepts_whitespace_around_fence():
    ideas = _parse_topic_response(f" \r\n  ```json\r\n{_payload()}\r\n```  \n")
    assert len(ideas) == 1


def test_parser_preserves_backticks_inside_json_string():
    title = "Why the literal ``` marker survives"
    ideas = _parse_topic_response(f"```json\n{_payload(title=title)}\n```")
    assert ideas[0].title == title


@pytest.mark.parametrize("text", ["```json\n\n```", "```\n   \n```"])
def test_parser_rejects_empty_fence(text):
    with pytest.raises(LLMParseError, match="Pusty"):
        _parse_topic_response(text)


def test_parser_rejects_missing_closing_fence():
    with pytest.raises(LLMParseError, match="Brak zamykającego"):
        _parse_topic_response(f"```json\n{_payload()}")


@pytest.mark.parametrize("text", [
    '{"topics": [{"title": "cut',
    "not-json",
    f"preface\n{_payload()}",
    f"{_payload()}\nafterword",
])
def test_parser_rejects_truncated_invalid_or_surrounded_json(text):
    with pytest.raises(LLMParseError):
        _parse_topic_response(text)


@pytest.mark.parametrize(("payload", "message"), [
    ({}, "nie zawiera pola 'topics'"),
    ({"topics": {}}, "musi być listą"),
    ({"topics": [{"question": "Missing title"}]}, "title"),
    ({"topics": [{"title": "Bad score", "score_breakdown": {"curiosity": 1.1}}]},
     "zakresie 0..1"),
])
def test_parser_rejects_invalid_schema(payload, message):
    with pytest.raises(LLMSchemaValidationError, match=message):
        _parse_topic_response(json.dumps(payload))


def test_client_success_preserves_usage_and_model(account):
    calls = []
    usage = Usage(input_tokens=123, output_tokens=45, cache_read_tokens=6)

    def caller(received_account, count):
        calls.append((received_account.id, count))
        return _payload(), usage

    result = AnthropicLLMClient("offline-key", "topics-model", caller=caller) \
        .generate_and_score_topics(account, 1)

    assert calls == [(account.id, 1)]
    assert result.usage is usage
    assert result.model == "topics-model"


def test_client_parse_error_preserves_usage_and_model_without_retry(account):
    calls = 0
    usage = Usage(input_tokens=321, output_tokens=54)

    def caller(_account, _count):
        nonlocal calls
        calls += 1
        return '{"topics": [', usage

    client = AnthropicLLMClient("offline-key", "topics-model", caller=caller)
    with pytest.raises(LLMParseError) as caught:
        client.generate_and_score_topics(account, 1)

    assert calls == 1
    assert caught.value.usage is usage
    assert caught.value.model == "topics-model"
    assert isinstance(caught.value.__cause__, LLMParseError)


def test_client_schema_error_preserves_usage_and_model(account):
    usage = Usage(input_tokens=10, output_tokens=5)
    client = AnthropicLLMClient(
        "offline-key", "topics-model", caller=lambda *_: ("{}", usage),
    )

    with pytest.raises(LLMSchemaValidationError) as caught:
        client.generate_and_score_topics(account, 1)

    assert caught.value.usage is usage
    assert caught.value.model == "topics-model"


def test_provider_error_before_response_has_no_usage_and_one_call(account):
    calls = 0

    def caller(_account, _count):
        nonlocal calls
        calls += 1
        raise LLMProviderError("provider unavailable", model="topics-model")

    client = AnthropicLLMClient("offline-key", "topics-model", caller=caller)
    with pytest.raises(LLMProviderError) as caught:
        client.generate_and_score_topics(account, 1)

    assert calls == 1
    assert caught.value.usage is None
    assert caught.value.model == "topics-model"


def test_default_adapter_preserves_provider_usage_before_parse_error(
        monkeypatch, account):
    calls = 0

    class FakeAPIError(Exception):
        pass

    message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"topics": [')],
        usage=SimpleNamespace(
            input_tokens=91,
            output_tokens=17,
            cache_read_input_tokens=4,
            cache_creation_input_tokens=2,
        ),
    )

    def create(**_kwargs):
        nonlocal calls
        calls += 1
        return message

    fake_module = SimpleNamespace(
        APIError=FakeAPIError,
        Anthropic=lambda **_kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    with pytest.raises(LLMParseError) as caught:
        AnthropicLLMClient("offline-key", "topics-model") \
            .generate_and_score_topics(account, 1)

    assert calls == 1
    assert caught.value.model == "topics-model"
    assert caught.value.usage == Usage(
        input_tokens=91,
        output_tokens=17,
        cache_read_tokens=4,
        cache_write_tokens=2,
    )


def test_default_adapter_types_provider_error_without_artificial_usage(
        monkeypatch, account):
    calls = 0

    class FakeAPIError(Exception):
        pass

    def create(**_kwargs):
        nonlocal calls
        calls += 1
        raise FakeAPIError("offline provider failure")

    fake_module = SimpleNamespace(
        APIError=FakeAPIError,
        Anthropic=lambda **_kwargs: SimpleNamespace(messages=SimpleNamespace(create=create)),
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    with pytest.raises(LLMProviderError) as caught:
        AnthropicLLMClient("offline-key", "topics-model") \
            .generate_and_score_topics(account, 1)

    assert calls == 1
    assert caught.value.usage is None
    assert caught.value.model == "topics-model"
