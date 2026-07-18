"""Testy AnthropicResearchClient bez sieci — wstrzyknięty caller (retry/timeout/parse)."""
from __future__ import annotations

import json

import pytest

from app.llm.base import Usage
from app.research.anthropic_client import AnthropicResearchClient as _RealAnthropicResearchClient
from app.research.base import (
    AttemptBudgetContext,
    ResearchAuthenticationError,
    ResearchBudgetError,
    ResearchConnectionError,
    ResearchError,
    ResearchInvalidRequestError,
    ResearchNotFoundError,
    ResearchParseError,
    ResearchPlan,
    ResearchPermissionError,
    ResearchRateLimitError,
    ResearchServerError,
    ResearchTimeout,
    ResearchTruncatedError,
    ResearchUnknownProviderError,
    SourceCandidate,
)


class AnthropicResearchClient(_RealAnthropicResearchClient):
    """Test-local SDK seam; global conftest blocks any real network access."""

    requires_durable_provider_context = False

    def configure_attempt_control(
        self, *, budget_callback, retry_usage_callback, estimated_attempt_cost: float,
    ) -> None:
        self._test_budget_callback = budget_callback
        self._test_retry_usage_callback = retry_usage_callback
        self._test_estimated_attempt_cost = estimated_attempt_cost

    def _before_attempt(self, attempt: int, *, stage: str) -> str | None:
        callback = getattr(self, "_test_budget_callback", None)
        if not callable(callback):
            return None
        prepared = callback(AttemptBudgetContext(
            attempt_number=attempt + 1,
            max_attempts=1,
            estimated_attempt_cost=self._test_estimated_attempt_cost,
            stage=stage,
        ))
        return getattr(prepared, "request_id", None)

_PLAN = ResearchPlan(topic_id=1, account_id="acc", question="Why?", niche=["x"])

_GOOD_JSON = json.dumps({
    "question": "Why?",
    "working_thesis": "Because dynamic pricing.",
    "main_mechanism": "revenue management",
    "confirmed_claims": ["A"],
    "uncertain_claims": [],
    "contradictions": [],
    "strongest_counterargument": "None",
    "citable_numbers": [],
    "visual_idea": "diagram",
    "confidence_score": 0.8,
    "source_quality_score": 0.7,
    "sources": [{"url": "https://x", "title": "T", "author_or_org": None,
                 "published_at": None, "source_type": "PRIMARY",
                 "supports_claim": "A"}],
})
_USAGE = Usage(input_tokens=100, output_tokens=50, web_search_requests=2)


class _SDKError(Exception):
    def __init__(self, message="sdk error", *, status_code=None, usage=None):
        super().__init__(message)
        self.status_code = status_code
        self.usage = usage


class _SDKConnectionError(_SDKError):
    pass


class _SDKTimeoutError(_SDKConnectionError):
    pass


class _SDKStatusError(_SDKError):
    pass


class _FakeAnthropicSDK:
    APIError = _SDKError
    APIStatusError = _SDKStatusError
    APITimeoutError = _SDKTimeoutError
    APIConnectionError = _SDKConnectionError
    RateLimitError = type("RateLimitError", (_SDKStatusError,), {})
    InternalServerError = type("InternalServerError", (_SDKStatusError,), {})
    AuthenticationError = type("AuthenticationError", (_SDKStatusError,), {})
    PermissionDeniedError = type("PermissionDeniedError", (_SDKStatusError,), {})
    BadRequestError = type("BadRequestError", (_SDKStatusError,), {})
    UnprocessableEntityError = type("UnprocessableEntityError", (_SDKStatusError,), {})
    NotFoundError = type("NotFoundError", (_SDKStatusError,), {})


def _raise_from_messages(exc):
    class _Messages:
        def create(self, **kwargs):
            raise exc

    return type("Provider", (), {"messages": _Messages()})()


def test_timeout_is_propagated_after_exactly_one_attempt():
    state = {"n": 0}

    def caller(plan):
        state["n"] += 1
        if state["n"] == 1:
            raise ResearchTimeout("boom")
        return _GOOD_JSON, _USAGE

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    with pytest.raises(ResearchTimeout):
        client.run_research(_PLAN)
    assert state["n"] == 1
    assert client.call_count == 1


def test_timeout_never_retries_even_when_legacy_metadata_is_nonzero():
    def caller(plan):
        raise ResearchTimeout("always")

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    with pytest.raises(ResearchTimeout):
        client.run_research(_PLAN)
    assert client.call_count == 1


def test_timeout_is_not_retried_when_max_retries_is_zero():
    client = AnthropicResearchClient(
        "key", "m", caller=lambda plan: (_ for _ in ()).throw(ResearchTimeout("timeout")),
        max_retries=0,
    )

    with pytest.raises(ResearchTimeout):
        client.run_research(_PLAN)

    assert client.call_count == 1


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: ResearchConnectionError("network"),
        lambda: ResearchRateLimitError("rate limit", status_code=429),
        lambda: ResearchServerError("500", status_code=500, retryable=True),
        lambda: ResearchServerError("502", status_code=502, retryable=True),
        lambda: ResearchServerError("503", status_code=503, retryable=True),
        lambda: ResearchServerError("504", status_code=504, retryable=True),
    ],
)
def test_typed_transient_provider_errors_are_not_retried(error_factory):
    state = {"calls": 0}

    def caller(plan):
        state["calls"] += 1
        if state["calls"] == 1:
            raise error_factory()
        return _GOOD_JSON, _USAGE

    error = error_factory()
    client = AnthropicResearchClient("key", "m", caller=lambda _plan: (_ for _ in ()).throw(error), max_retries=1)
    with pytest.raises(type(error)):
        client.run_research(_PLAN)
    assert client.call_count == 1


@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: ResearchInvalidRequestError("400", status_code=400),
        lambda: ResearchAuthenticationError("401", status_code=401),
        lambda: ResearchPermissionError("403", status_code=403),
        lambda: ResearchNotFoundError("404", status_code=404),
        lambda: ResearchInvalidRequestError("422", status_code=422),
        lambda: ResearchUnknownProviderError("unknown"),
        lambda: ResearchServerError("501", status_code=501, retryable=False),
    ],
)
def test_non_retryable_provider_errors_fail_closed(error_factory):
    error = error_factory()

    def caller(plan):
        raise error

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=3)
    with pytest.raises(type(error)) as excinfo:
        client.run_research(_PLAN)

    assert excinfo.value is error
    assert client.call_count == 1


def test_validation_error_is_not_retried():
    def caller(plan):
        raise ValueError("local validation failed")

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=3)
    with pytest.raises(ValueError, match="local validation failed"):
        client.run_research(_PLAN)
    assert client.call_count == 1


@pytest.mark.parametrize(
    ("sdk_error", "expected_type", "retryable", "expected_status"),
    [
        (_SDKTimeoutError("timeout"), ResearchTimeout, True, None),
        (_SDKConnectionError("network"), ResearchConnectionError, True, None),
        (_FakeAnthropicSDK.RateLimitError(status_code=429), ResearchRateLimitError, True, 429),
        (_FakeAnthropicSDK.InternalServerError(status_code=500), ResearchServerError, True, 500),
        (_FakeAnthropicSDK.InternalServerError(status_code=502), ResearchServerError, True, 502),
        (_FakeAnthropicSDK.InternalServerError(status_code=503), ResearchServerError, True, 503),
        (_FakeAnthropicSDK.InternalServerError(status_code=504), ResearchServerError, True, 504),
        (_FakeAnthropicSDK.BadRequestError(status_code=400), ResearchInvalidRequestError, False, 400),
        (_FakeAnthropicSDK.AuthenticationError(status_code=401), ResearchAuthenticationError, False, 401),
        (_FakeAnthropicSDK.PermissionDeniedError(status_code=403), ResearchPermissionError, False, 403),
        (_FakeAnthropicSDK.NotFoundError(status_code=404), ResearchNotFoundError, False, 404),
        (_FakeAnthropicSDK.UnprocessableEntityError(status_code=422), ResearchInvalidRequestError, False, 422),
        (_FakeAnthropicSDK.InternalServerError(status_code=501), ResearchServerError, False, 501),
        (RuntimeError("unknown"), ResearchUnknownProviderError, False, None),
    ],
)
def test_call_anthropic_maps_sdk_errors_without_network(
        monkeypatch, sdk_error, expected_type, retryable, expected_status):
    client = AnthropicResearchClient("offline", "m", max_retries=0)
    monkeypatch.setattr(client, "_import_anthropic", lambda: _FakeAnthropicSDK)

    with pytest.raises(expected_type) as excinfo:
        client._call_anthropic(
            _raise_from_messages(sdk_error), "prompt", tools=None, max_tokens=10)

    assert excinfo.value.retryable is retryable
    assert excinfo.value.status_code == expected_status
    assert excinfo.value.usage is None


def test_sdk_response_body_never_becomes_domain_error_or_audit_message():
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx")
    marker = "RAW_RESPONSE_MARKER"
    request = httpx.Request("POST", "https://api.anthropic.invalid/v1/messages")
    response = httpx.Response(422, request=request)
    body = {"error": {"message": marker}, "private_payload": marker}
    sdk_error = anthropic.UnprocessableEntityError(
        f"Error code: 422 - {body}", response=response, body=body)
    client = AnthropicResearchClient("offline", "m", max_retries=0)

    with pytest.raises(ResearchInvalidRequestError) as excinfo:
        client._call_anthropic(
            _raise_from_messages(sdk_error), "prompt", tools=None, max_tokens=10)

    error = excinfo.value
    assert marker not in str(error)
    assert error.status_code == 422
    assert error.retryable is False
    assert error.__cause__ is sdk_error


def test_504_is_propagated_once_without_retry_usage_callback():
    calls = []
    budget_attempts = []
    recorded_usage = []

    def caller(plan):
        calls.append(1)
        raise ResearchServerError(
            "gateway timeout", status_code=504, retryable=True,
            usage=_USAGE, model="m",
        )

    client = AnthropicResearchClient("offline", "m", caller=caller, max_retries=1)
    client.configure_attempt_control(
        budget_callback=lambda context: budget_attempts.append(context.attempt_number),
        retry_usage_callback=lambda usage, model: recorded_usage.append((usage, model)),
        estimated_attempt_cost=0.08,
    )

    with pytest.raises(ResearchServerError) as caught:
        client.run_research(_PLAN)

    assert caught.value.usage == _USAGE
    assert calls == [1]
    assert client.call_count == 1
    assert budget_attempts == [1]
    assert recorded_usage == []


def test_504_with_zero_retries_makes_one_attempt_and_preserves_usage():
    calls = []
    budget_attempts = []
    recorded_usage = []
    error = ResearchServerError(
        "gateway timeout", status_code=504, retryable=True,
        usage=_USAGE, model="m",
    )

    def caller(plan):
        calls.append(1)
        raise error

    client = AnthropicResearchClient("offline", "m", caller=caller, max_retries=0)
    client.configure_attempt_control(
        budget_callback=lambda context: budget_attempts.append(context.attempt_number),
        retry_usage_callback=lambda usage, model: recorded_usage.append((usage, model)),
        estimated_attempt_cost=0.08,
    )

    with pytest.raises(ResearchServerError) as excinfo:
        client.run_research(_PLAN)

    assert excinfo.value is error
    assert excinfo.value.status_code == 504
    assert excinfo.value.retryable is True
    assert excinfo.value.usage == _USAGE
    assert calls == [1]
    assert client.call_count == 1
    assert budget_attempts == [1]
    assert recorded_usage == []


def test_invalid_json_not_retried():
    def caller(plan):
        return "definitely not json", _USAGE

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    with pytest.raises(ResearchParseError):
        client.run_research(_PLAN)
    assert client.call_count == 1  # parse error nie jest ponawiany


def test_invalid_json_still_carries_real_usage():
    """Regresja: realne (płatne) wywołanie, którego JSON się nie sparsował, NIE MOŻE
    zgubić `usage` — inaczej rzeczywisty koszt znika z księgowości (znaleziono na
    pierwszym realnym runie 2026-07-11: ucięty JSON, koszt zgłoszony jako 0.00 USD)."""
    def caller(plan):
        return "{not valid json", _USAGE

    client = AnthropicResearchClient("key", "sonnet-x", caller=caller, max_retries=2)
    with pytest.raises(ResearchParseError) as excinfo:
        client.run_research(_PLAN)
    assert client.call_count == 1
    assert excinfo.value.usage == _USAGE
    assert excinfo.value.model == "sonnet-x"


def test_staged_synthesis_success_below_limit_parses_normally():
    def caller(plan, cards):
        return _GOOD_JSON, _USAGE, "end_turn"

    client = AnthropicResearchClient(
        "key", "m", synthesize_from_cards_caller=caller, max_retries=0,
    )
    result = client.synthesize_from_cards(_PLAN, [])
    assert result.draft.working_thesis == "Because dynamic pricing."
    assert result.stop_reason == "end_turn"
    assert client.call_count == 1


def test_max_tokens_is_typed_truncation_with_usage_and_no_retry():
    calls = []

    def caller(plan, cards):
        calls.append(1)
        return '{"working_thesis": "cut', _USAGE, "max_tokens"

    client = AnthropicResearchClient(
        "key", "m", synthesize_from_cards_caller=caller,
        synthesize_max_tokens=3000, max_retries=3,
    )
    with pytest.raises(ResearchTruncatedError) as excinfo:
        client.synthesize_from_cards(_PLAN, [])

    assert calls == [1]
    assert client.call_count == 1
    assert excinfo.value.usage == _USAGE
    assert excinfo.value.model == "m"
    assert excinfo.value.raw_text == '{"working_thesis": "cut'
    assert excinfo.value.stop_reason == "max_tokens"
    assert "max_output_tokens=3000" in str(excinfo.value)


def test_a1_max_tokens_still_salvages_complete_jsonl_rows():
    """Truncation B is all-or-nothing, but A1 intentionally keeps complete
    JSONL candidates before a cut final row (ADR-020)."""
    raw = (
        '{"url":"https://a.example","title":"A"}\n'
        '{"url":"https://b.example","title":"B"}\n'
        '{"url":"https://cut.example","title":"'
    )

    def caller(plan, max_searches):
        return raw, _USAGE, "max_tokens"

    client = AnthropicResearchClient(
        "key", "m", discover_caller=caller, max_retries=0,
    )
    result = client.discover_sources(_PLAN, max_searches=3)

    assert [candidate.url for candidate in result.candidates] == [
        "https://a.example", "https://b.example",
    ]
    assert result.stop_reason == "max_tokens"


def test_invalid_json_without_max_tokens_remains_plain_parse_error():
    def caller(plan, cards):
        return "{invalid", _USAGE, "end_turn"

    client = AnthropicResearchClient(
        "key", "m", synthesize_from_cards_caller=caller, max_retries=2,
    )
    with pytest.raises(ResearchParseError) as excinfo:
        client.synthesize_from_cards(_PLAN, [])
    assert not isinstance(excinfo.value, ResearchTruncatedError)
    assert excinfo.value.usage == _USAGE
    assert client.call_count == 1


def test_provider_error_remains_separate_from_truncation():
    def caller(plan, cards):
        raise ResearchError("provider rejected request")

    client = AnthropicResearchClient(
        "key", "m", synthesize_from_cards_caller=caller, max_retries=2,
    )
    with pytest.raises(ResearchError) as excinfo:
        client.synthesize_from_cards(_PLAN, [])
    assert not isinstance(excinfo.value, (ResearchParseError, ResearchTruncatedError))
    assert client.call_count == 1


@pytest.mark.parametrize("stage", ["A1", "A2", "B"])
@pytest.mark.parametrize(
    ("error_factory", "expected_type", "expected_status", "retryable"),
    [
        (lambda: ResearchTimeout("timeout"), ResearchTimeout, None, True),
        (lambda: ResearchRateLimitError("rate", status_code=429),
         ResearchRateLimitError, 429, True),
        (lambda: ResearchAuthenticationError("auth", status_code=401),
         ResearchAuthenticationError, 401, False),
        (lambda: ResearchInvalidRequestError("invalid", status_code=422),
         ResearchInvalidRequestError, 422, False),
        (lambda: ResearchUnknownProviderError("unknown"),
         ResearchUnknownProviderError, None, False),
    ],
    ids=["timeout", "rate-limit-429", "authentication-401", "invalid-422", "unknown"],
)
def test_staged_a1_a2_b_preserve_typed_provider_errors(
        stage, error_factory, expected_type, expected_status, retryable):
    caller_calls = []

    def fail(*args):
        caller_calls.append(1)
        raise error_factory()

    kwargs = {"max_retries": 3}
    if stage == "A1":
        kwargs["discover_caller"] = fail
    elif stage == "A2":
        kwargs["extract_caller"] = fail
    else:
        kwargs["synthesize_from_cards_caller"] = fail
    client = AnthropicResearchClient("offline", "m", **kwargs)

    with pytest.raises(expected_type) as excinfo:
        if stage == "A1":
            client.discover_sources(_PLAN, max_searches=1)
        elif stage == "A2":
            client.extract_source(
                _PLAN, SourceCandidate(url="https://example.org", title="Example"))
        else:
            client.synthesize_from_cards(_PLAN, [])

    assert excinfo.value.status_code == expected_status
    assert excinfo.value.retryable is retryable
    assert len(caller_calls) == 1
    assert client.call_count == 1


def test_budget_callback_runs_before_the_single_attempt():
    attempts = []
    def caller(plan):
        return _GOOD_JSON, _USAGE

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=1)
    client.configure_attempt_control(
        budget_callback=lambda context: attempts.append(context.attempt_number),
        retry_usage_callback=lambda usage, model: None,
        estimated_attempt_cost=0.08,
    )
    client.run_research(_PLAN)
    assert attempts == [1]


def test_budget_denial_before_first_attempt_makes_zero_calls():
    calls = []

    def caller(plan):
        calls.append(1)
        return _GOOD_JSON, _USAGE

    def deny(context):
        raise ResearchBudgetError("cap", code="RUN_CAP_EXCEEDED")

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    client.configure_attempt_control(
        budget_callback=deny, retry_usage_callback=None, estimated_attempt_cost=0.08)
    with pytest.raises(ResearchBudgetError):
        client.run_research(_PLAN)
    assert calls == []
    assert client.call_count == 0


def test_timeout_does_not_trigger_a_second_budget_check():
    calls = []

    def caller(plan):
        calls.append(1)
        raise ResearchTimeout("timeout")

    attempts = []

    def guard(context):
        attempts.append(context.attempt_number)

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=3)
    client.configure_attempt_control(
        budget_callback=guard, retry_usage_callback=None, estimated_attempt_cost=0.08)
    with pytest.raises(ResearchTimeout):
        client.run_research(_PLAN)
    assert len(calls) == 1
    assert client.call_count == 1
    assert attempts == [1]


def test_timeout_usage_is_preserved_without_retry_callback():
    recorded = []
    state = {"n": 0}

    def caller(plan):
        state["n"] += 1
        if state["n"] == 1:
            raise ResearchTimeout("timeout", usage=_USAGE, model="m")
        return _GOOD_JSON, _USAGE

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=1)
    client.configure_attempt_control(
        budget_callback=lambda context: None,
        retry_usage_callback=lambda usage, model: recorded.append((usage, model)),
        estimated_attempt_cost=0.08,
    )
    with pytest.raises(ResearchTimeout) as caught:
        client.run_research(_PLAN)
    assert caught.value.usage == _USAGE
    assert recorded == []


def test_negative_max_retries_is_rejected():
    with pytest.raises(ValueError):
        AnthropicResearchClient("key", "m", max_retries=-1)


def test_web_search_max_uses_passed_to_tool_spec(monkeypatch):
    """max_web_searches musi trafić do tools[].max_uses w realnym wywołaniu API.

    `anthropic` jest importowany leniwie wewnątrz `_default_caller`, więc podmieniamy
    sys.modules['anthropic'] zamiast atrybutu modułu.
    """
    import sys
    import types

    captured = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop-before-network")  # nie łączymy się z siecią w teście

    class _FakeAnthropicClient:
        def __init__(self, api_key, **_kwargs):
            self.messages = _FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _FakeAnthropicClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    client = AnthropicResearchClient("key", "m", max_web_searches=6)
    try:
        client._default_caller(_PLAN)
    except Exception:
        pass  # oczekiwane — przerywamy przed realną siecią; interesuje nas tylko `captured`
    assert captured.get("tools") == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 6}
    ]


def _capture_extract_call_kwargs(monkeypatch, client: AnthropicResearchClient) -> dict:
    """Podmienia `anthropic.Anthropic` na fejka, który tylko zapisuje kwargs przekazane
    do `messages.create` i przerywa przed siecią — ten sam wzorzec co
    `test_web_search_max_uses_passed_to_tool_spec`, użyty dla `_default_extract_caller`."""
    import sys
    import types

    captured = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop-before-network")

    class _FakeAnthropicClient:
        def __init__(self, api_key, **_kwargs):
            self.messages = _FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _FakeAnthropicClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    candidate = SourceCandidate(url="https://example.org/x", title="X")
    try:
        client._default_extract_caller(_PLAN, candidate)
    except Exception:
        pass  # oczekiwane — przerywamy przed realną siecią; interesuje nas tylko `captured`
    return captured


def test_extract_default_max_tokens_is_1500(monkeypatch):
    """Regresja (2026-07-12, diagnostyka run 9bbeb020): stary domyślny 500 ucinał
    dwie realne ekstrakcje; późniejsza diagnostyka kandydata id=3 zakończyła się
    przy 915 tokenach — nowy produkcyjny domyślny to 1500, nie diagnostyczne 5000."""
    client = AnthropicResearchClient("key", "m")
    captured = _capture_extract_call_kwargs(monkeypatch, client)
    assert captured.get("max_tokens") == 1500


def test_extract_max_tokens_explicit_override_still_works(monkeypatch):
    client = AnthropicResearchClient("key", "m", extract_max_tokens=800)
    captured = _capture_extract_call_kwargs(monkeypatch, client)
    assert captured.get("max_tokens") == 800


def _capture_synthesis_call_kwargs(monkeypatch, client: AnthropicResearchClient) -> dict:
    import sys
    import types

    captured = {}

    class _FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("stop-before-network")

    class _FakeAnthropicClient:
        def __init__(self, api_key, **_kwargs):
            self.messages = _FakeMessages()

    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _FakeAnthropicClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)
    try:
        client._default_synthesize_from_cards_caller(_PLAN, [])
    except Exception:
        pass
    return captured


def test_synthesis_default_max_tokens_is_3000_and_override_works(monkeypatch):
    default = _capture_synthesis_call_kwargs(
        monkeypatch, AnthropicResearchClient("key", "m"),
    )
    override = _capture_synthesis_call_kwargs(
        monkeypatch, AnthropicResearchClient("key", "m", synthesize_max_tokens=2600),
    )
    assert default.get("max_tokens") == 3000
    assert override.get("max_tokens") == 2600


@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [([], 1500), (["--extraction-max-tokens", "800"], 800)],
)
def test_capped_research_cli_preserves_extraction_token_default_and_override(
        monkeypatch, extra_args, expected):
    """Parser CLI przekazuje zarówno produkcyjny default 1500, jak i jawny override;
    test zatrzymuje się przed konfiguracją, bazą i jakimkolwiek klientem API."""
    from scripts import run_capped_research

    captured = {}

    def fake_run_fresh(args):
        captured["extraction_max_tokens"] = args.extraction_max_tokens
        return 0

    monkeypatch.setattr(run_capped_research, "_run_fresh", fake_run_fresh)

    assert run_capped_research.main(["--topic-id", "1", *extra_args]) == 0
    assert captured["extraction_max_tokens"] == expected


@pytest.mark.parametrize(
    ("extra_args", "expected"),
    [([], 3000), (["--synthesize-max-tokens", "2600"], 2600)],
)
def test_capped_research_cli_preserves_synthesis_token_default_and_override(
        monkeypatch, extra_args, expected):
    from scripts import run_capped_research

    captured = {}

    def fake_run_fresh(args):
        captured["synthesize_max_tokens"] = args.synthesize_max_tokens
        return 0

    monkeypatch.setattr(run_capped_research, "_run_fresh", fake_run_fresh)
    assert run_capped_research.main(["--topic-id", "1", *extra_args]) == 0
    assert captured["synthesize_max_tokens"] == expected
