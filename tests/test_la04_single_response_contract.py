"""LA-04: closed one-response parser contract for durable single research."""
from __future__ import annotations

import copy
import json

import pytest

from app.llm.base import Usage
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import (
    ResearchParseError,
    ResearchPlan,
    ResearchSchemaError,
    ResearchTruncatedError,
)


class _OfflineContractClient(AnthropicResearchClient):
    requires_durable_provider_context = False


PLAN = ResearchPlan(topic_id=1, account_id="account", question="Why?", niche=["systems"])
USAGE = Usage(input_tokens=17, output_tokens=23, web_search_requests=1)


def _payload() -> dict[str, object]:
    return {
        "question": "Why?",
        "working_thesis": "Because incentives shape the system.",
        "main_mechanism": "A bounded mechanism.",
        "confirmed_claims": ["Claim A"],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "Counterargument.",
        "citable_numbers": ["42 percent"],
        "visual_idea": "A compact flow.",
        "confidence_score": 0.8,
        "source_quality_score": 0.7,
        "sources": [{
            "url": "https://example.test/source",
            "title": "Source",
            "author_or_org": None,
            "published_at": None,
            "source_type": "PRIMARY",
            "supports_claim": "Claim A",
        }],
    }


def _json(payload: dict[str, object] | None = None) -> str:
    return json.dumps(_payload() if payload is None else payload)


def _missing(field: str) -> str:
    payload = _payload()
    del payload[field]
    return _json(payload)


def _changed(field: str, value: object) -> str:
    payload = copy.deepcopy(_payload())
    payload[field] = value
    return _json(payload)


def _score_literal(value: str) -> str:
    return _json().replace(
        '"confidence_score": 0.8',
        f'"confidence_score": {value}',
        1,
    )


CASES = [
    pytest.param(_json(), None, None, "good_json", id="01-good-json"),
    pytest.param(f"```json\n{_json()}\n```", None, None, "complete_fence",
                 id="02-one-complete-fence"),
    pytest.param(_json() + " \r\n\t", None, None, "trailing_whitespace",
                 id="03-trailing-whitespace"),
    pytest.param(f"```\n{_json()}\n```", None, ResearchParseError,
                 "incomplete_or_invalid_code_fence", id="04-bare-fence"),
    pytest.param("Here is the result: " + _json(), None, ResearchParseError,
                 "prose_outside_json", id="05-prose-before"),
    pytest.param(_json() + "\nDone.", None, ResearchParseError,
                 "prose_outside_json", id="06-prose-after"),
    pytest.param(_json() + _json(), None, ResearchParseError,
                 "multiple_json_values", id="07-object-plus-object"),
    pytest.param(_json() + "[]", None, ResearchParseError,
                 "multiple_json_values", id="08-object-plus-array"),
    pytest.param(_json() + "true", None, ResearchParseError,
                 "multiple_json_values", id="09-object-plus-true"),
    pytest.param(_json() + "123", None, ResearchParseError,
                 "multiple_json_values", id="10-object-plus-number"),
    pytest.param('{"question":"Why?"', None, ResearchParseError,
                 "incomplete_json", id="11-truncated-object"),
    pytest.param('{"question":"unterminated}', None, ResearchParseError,
                 "incomplete_json", id="12-unclosed-string"),
    pytest.param(_missing("working_thesis"), None, ResearchSchemaError,
                 "schema", id="13-missing-field"),
    pytest.param(_changed("confirmed_claims", "not-a-list"), None,
                 ResearchSchemaError, "schema", id="14-bad-list-type"),
    pytest.param(_changed("confidence_score", True), None, ResearchSchemaError,
                 "schema", id="15-bool-is-not-score"),
    pytest.param(
        _changed("sources", [{
            "url": "https://example.test/source", "title": "Source",
            "author_or_org": None, "published_at": None,
            "source_type": "UNKNOWN", "supports_claim": "Claim A",
        }]),
        None, ResearchSchemaError, "schema", id="16-invalid-source-enum",
    ),
    pytest.param("[]", None, ResearchSchemaError, "schema", id="17-root-array"),
    pytest.param("42", None, ResearchSchemaError, "schema", id="18-root-scalar"),
    pytest.param(f"```json\n{_json()}", None, ResearchParseError,
                 "incomplete_or_invalid_code_fence", id="19-incomplete-fence"),
    pytest.param('{"question":"cut', "max_tokens", ResearchTruncatedError,
                 "truncation", id="20-stop-reason-max-tokens"),
    pytest.param(_changed("confidence_score", int("9" * 400)), None,
                 ResearchSchemaError, "schema", id="21-score-400-digit-int"),
    pytest.param(_score_literal("1e400"), None, ResearchSchemaError, "schema",
                 id="22-score-huge-exponent"),
    pytest.param(_score_literal("Infinity"), None, ResearchSchemaError, "schema",
                 id="23-score-positive-infinity"),
    pytest.param(_score_literal("-Infinity"), None, ResearchSchemaError, "schema",
                 id="24-score-negative-infinity"),
    pytest.param(_score_literal("NaN"), None, ResearchSchemaError, "schema",
                 id="25-score-nan"),
    pytest.param(_changed("confidence_score", 1.01), None,
                 ResearchSchemaError, "schema", id="26-score-out-of-range"),
    pytest.param(_changed("confidence_score", "0.8"), None,
                 ResearchSchemaError, "schema", id="27-score-text"),
    pytest.param(_changed("confidence_score", 1), None, None,
                 "boundary_score", id="28-score-boundary-one"),
]


@pytest.mark.parametrize(("raw", "stop_reason", "error_type", "classification"), CASES)
def test_single_response_matrix_is_exact_once_and_fail_closed(
    raw, stop_reason, error_type, classification,
):
    calls: list[int] = []

    def caller(_plan):
        calls.append(1)
        return raw, USAGE, stop_reason

    client = _OfflineContractClient(
        "offline", "model", caller=caller, research_max_tokens=1500, max_retries=9,
    )

    if error_type is None:
        result = client.run_research(PLAN)
        assert result.usage == USAGE
        assert result.raw_text == raw
        assert result.stop_reason == stop_reason
        assert result.draft.working_thesis
    else:
        with pytest.raises(error_type) as excinfo:
            client.run_research(PLAN)
        assert excinfo.value.classification == classification
        assert excinfo.value.usage == USAGE
        assert excinfo.value.raw_text == raw
        assert excinfo.value.stop_reason == stop_reason

    assert calls == [1]
    assert client.call_count == 1
