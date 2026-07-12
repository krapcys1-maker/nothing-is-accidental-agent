"""Testy AnthropicResearchClient bez sieci — wstrzyknięty caller (retry/timeout/parse)."""
from __future__ import annotations

import json

import pytest

from app.llm.base import Usage
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import ResearchParseError, ResearchPlan, ResearchTimeout, SourceCandidate

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
    "sources": [{"url": "https://x", "title": "T", "source_type": "PRIMARY",
                 "supports_claim": "A"}],
})
_USAGE = Usage(input_tokens=100, output_tokens=50, web_search_requests=2)


def test_retry_then_success():
    state = {"n": 0}

    def caller(plan):
        state["n"] += 1
        if state["n"] == 1:
            raise ResearchTimeout("boom")
        return _GOOD_JSON, _USAGE

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    result = client.run_research(_PLAN)
    assert result.draft.working_thesis == "Because dynamic pricing."
    assert client.call_count == 2  # 1 timeout + 1 sukces


def test_timeout_exhausts_retries():
    def caller(plan):
        raise ResearchTimeout("always")

    client = AnthropicResearchClient("key", "m", caller=caller, max_retries=2)
    with pytest.raises(ResearchTimeout):
        client.run_research(_PLAN)
    assert client.call_count == 3  # max_retries + 1, bez nieskończonego retry


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
        def __init__(self, api_key):
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
        def __init__(self, api_key):
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
