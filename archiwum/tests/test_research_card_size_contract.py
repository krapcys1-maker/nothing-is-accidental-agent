"""Jawny kontrakt rozmiaru Research Card (prompt v3 + deterministyczna walidacja).

Fala 2026-07-18 po trzech kontrolowanych realnych próbach (1500/3000/3000 max_tokens,
dwa ucięcia + jeden schema failure). Testowane bez sieci: payloady profilowe muszą
przechodzić PRAWDZIWY parser i schemę; każde przekroczenie budżetu musi być typowanym,
fail-closed błędem z zachowanym usage i zerowym retry.
"""
from __future__ import annotations

import json

import pytest

from app.llm.base import Usage
from app.research import output_contract as oc
from app.research.anthropic_client import (
    AnthropicResearchClient,
    _parse,
    build_single_research_prompt,
)
from app.research.base import (
    ResearchCardSizeContractError,
    ResearchPlan,
    ResearchSchemaError,
    ResearchTruncatedError,
)
from app.research.diagnostics import ResponseDiagnostics, write_diagnostics
from app.research.durable_intent import (
    MAX_REQUEST_MAX_TOKENS,
    MIN_REQUEST_MAX_TOKENS,
)


class _OfflineContractClient(AnthropicResearchClient):
    requires_durable_provider_context = False


PLAN = ResearchPlan(topic_id=1, account_id="account", question="Why?", niche=["systems"])
USAGE = Usage(input_tokens=17, output_tokens=23, web_search_requests=1)


def _ascii_text(n: int) -> str:
    """Deterministyczny ASCII o DOKŁADNIE n znakach, bez spacji na końcu."""
    base = "incentive structure margin retail logistics behavioral placement cost "
    s = (base * (n // len(base) + 1))[:n]
    return s[:-1] + "x" if s.endswith(" ") else s


def _minimal_payload() -> dict[str, object]:
    return {
        "question": "Why?",
        "working_thesis": "Because incentives shape the system.",
        "main_mechanism": None,
        "confirmed_claims": ["Claim A"],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": None,
        "citable_numbers": [],
        "visual_idea": None,
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


def _realistic_payload() -> dict[str, object]:
    """Skala realnej, kompletnej karty z live #2 (6 claims / 3+3 / 6 numbers / 6 sources)."""
    claims = [
        f"Retail consultants describe rear-of-store milk placement as claim {i} of a "
        "deliberate basket-building strategy exposing shoppers to more products."
        for i in range(6)
    ]
    return {
        "question": "What incentive puts milk and bread far from the entrance?",
        "working_thesis": (
            "Stores place staples at opposite ends primarily to maximize path length "
            "and impulse exposure, while refrigeration logistics reinforce the layout."
        ),
        "main_mechanism": (
            "Frequently purchased staples anchor opposite ends of the store, forcing "
            "nearly every customer to pass the maximum number of displays; back-wall "
            "coolers simultaneously minimize refrigeration and restocking costs, so "
            "psychology and engineering point at the same physical layout."
        ),
        "confirmed_claims": claims,
        "uncertain_claims": [
            "Whether impulse exposure or refrigeration economics dominates remains disputed.",
            "Bread placement may follow bakery workflow rather than the forced-path incentive.",
            "Layout choices may be inherited convention rather than measured optimization.",
        ],
        "contradictions": [
            "Economists argue competition would erase manipulative layouts; marketers disagree.",
            "Some sources call placement pure engineering, others a psychological tactic.",
            "A retail veteran denies any intent to trick shoppers, contradicting consultants.",
        ],
        "strongest_counterargument": (
            "If forced walks were the dominant profit lever, at least one major chain "
            "would differentiate with front-of-store milk, yet none does, suggesting "
            "shared cold-chain economics explain the near-universal layout."
        ),
        "citable_numbers": [
            "1 to 3 percent typical grocery profit margin",
            "40 degrees Fahrenheit minimum milk storage temperature",
            "2014 NPR Planet Money segment on milk placement",
            "2023 Tasting Table update citing the same debate",
            "2025 Reader's Digest interviews with three named sources",
            "2 competing named milk theorists featured by NPR",
        ],
        "visual_idea": (
            "Top-down store floor plan with a dotted forced-path line from entrance to "
            "rear dairy cooler, annotated with impulse-theory and logistics-theory callouts."
        ),
        "confidence_score": 0.55,
        "source_quality_score": 0.55,
        "sources": [
            {
                "url": f"https://example.test/articles/2026/milk-bread-layout-analysis-{i}",
                "title": f"Why Milk Sits At The Back Of The Store, Part {i}",
                "author_or_org": "Example Publication",
                "published_at": "2026-07-17",
                "source_type": "SECONDARY",
                "supports_claim": claims[i],
            }
            for i in range(6)
        ],
    }


def _max_payload() -> dict[str, object]:
    """Payload z KAŻDYM polem dokładnie na granicy kontraktu."""
    claims = [_ascii_text(oc.MAX_CLAIM_CHARS) for _ in range(oc.MAX_CONFIRMED_CLAIMS)]
    return {
        "question": _ascii_text(oc.MAX_QUESTION_CHARS),
        "working_thesis": _ascii_text(oc.MAX_WORKING_THESIS_CHARS),
        "main_mechanism": _ascii_text(oc.MAX_MAIN_MECHANISM_CHARS),
        "confirmed_claims": claims,
        "uncertain_claims": [
            _ascii_text(oc.MAX_CLAIM_CHARS) for _ in range(oc.MAX_UNCERTAIN_CLAIMS)
        ],
        "contradictions": [
            _ascii_text(oc.MAX_CONTRADICTION_CHARS) for _ in range(oc.MAX_CONTRADICTIONS)
        ],
        "strongest_counterargument": _ascii_text(oc.MAX_COUNTERARGUMENT_CHARS),
        "citable_numbers": [
            _ascii_text(oc.MAX_CITABLE_NUMBER_CHARS) for _ in range(oc.MAX_CITABLE_NUMBERS)
        ],
        "visual_idea": _ascii_text(oc.MAX_VISUAL_IDEA_CHARS),
        "confidence_score": 0.55,
        "source_quality_score": 0.55,
        "sources": [
            {
                "url": "https://example.test/" + "p" * (
                    oc.MAX_SOURCE_URL_CHARS - len("https://example.test/")
                ),
                "title": _ascii_text(oc.MAX_SOURCE_TITLE_CHARS),
                "author_or_org": _ascii_text(oc.MAX_SOURCE_AUTHOR_CHARS),
                "published_at": _ascii_text(oc.MAX_SOURCE_PUBLISHED_AT_CHARS),
                "source_type": "SECONDARY",
                "supports_claim": claims[i],
            }
            for i in range(oc.MAX_SOURCES)
        ],
    }


def _unicode_payload() -> dict[str, object]:
    """Unicode + długie URL-e + liczby — poprawny payload w granicach kontraktu."""
    payload = _realistic_payload()
    payload["working_thesis"] = (
        "Sklepy rozdzielają mleko i pieczywo — 27,5% dłuższa ścieżka → większy "
        "koszyk; chłodnictwo przy rampie załadunkowej wzmacnia ten sam układ."
    )
    payload["citable_numbers"] = [
        "27,5 % dłuższa ścieżka zakupowa (badanie 2026)",
        "3 × wyższa ekspozycja na produkty impulsowe",
        "40°F minimalna temperatura przechowywania mleka",
    ]
    payload["sources"][0]["url"] = (
        "https://przyklad.test/raporty/2026/układ-sklepu"
        "?utm_source=newsletter&utm_medium=email&utm_campaign=layout-incentives"
        "&section=chłodnictwo#metodologia-i-aneks-tabelaryczny"
    )
    payload["sources"][0]["title"] = "Dlaczego mleko stoi z tyłu sklepu? Analiza 2026"
    return payload


def _json(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"))


# --- payloady profilowe przechodzą PRAWDZIWY parser i schemę -----------------------


@pytest.mark.parametrize(
    "payload_builder",
    [
        pytest.param(_minimal_payload, id="minimal"),
        pytest.param(_realistic_payload, id="realistic"),
        pytest.param(_max_payload, id="max-at-every-cap"),
        pytest.param(_unicode_payload, id="unicode-long-urls-numbers"),
    ],
)
def test_correct_profile_payloads_pass_real_parser(payload_builder):
    draft = _parse(_json(payload_builder()))
    assert draft.question
    assert draft.working_thesis


def test_max_payload_serialized_size_matches_frozen_token_profile_input():
    """Zmiana budżetu pól bez ponownego wyznaczenia profilu tokenowego = błąd."""
    serialized = _json(_max_payload())
    assert len(serialized) == oc.MAX_CORRECT_PAYLOAD_CHARS
    assert len(serialized) <= oc.MAX_RESPONSE_CHARS


def test_token_profile_inequality_holds():
    import math

    assert oc.ESTIMATED_MAX_PAYLOAD_TOKENS == math.ceil(
        oc.MAX_CORRECT_PAYLOAD_CHARS / oc.CONSERVATIVE_CHARS_PER_TOKEN
    )
    assert (
        oc.RESEARCH_CARD_MAX_TOKENS
        >= oc.ESTIMATED_MAX_PAYLOAD_TOKENS + oc.HIDDEN_OUTPUT_OVERHEAD_TOKENS
    )
    assert oc.RESEARCH_CARD_TOKEN_SAFETY_MARGIN > 0
    assert MIN_REQUEST_MAX_TOKENS <= oc.RESEARCH_CARD_MAX_TOKENS <= MAX_REQUEST_MAX_TOKENS


def test_operational_profile_cap_covers_pessimistic_estimate():
    """Rekomendowany max_cost_usd pokrywa pesymistyczny sufit estymatora dla
    aktywnego, zatwierdzonego profilu cenowego. Zmiana cen lub limitów bez
    ponownego wyznaczenia profilu operacyjnego = jawny fail tego testu."""
    from decimal import Decimal
    from pathlib import Path
    from types import SimpleNamespace

    from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
    from app.research.cost_estimator import estimate_worst_case_search_call_usd

    profile = resolve_real_pricing_profile(
        load_pricing_profiles(
            Path(__file__).resolve().parents[1] / "config" / "pricing_profiles.yaml"
        ),
        profile_id="anthropic-sonnet-5-intro-2026-07",
        model="claude-sonnet-5",
    )
    estimate = estimate_worst_case_search_call_usd(
        SimpleNamespace(pricing={k: float(v) for k, v in profile.prices.items()}),
        max_web_searches=oc.RESEARCH_CARD_MAX_WEB_SEARCHES,
        max_output_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    assert Decimal(oc.RESEARCH_CARD_RECOMMENDED_MAX_COST_USD) >= Decimal(
        str(estimate.total_usd)
    )
    assert oc.RESEARCH_CARD_MAX_WEB_SEARCHES == 1


def test_stale_v2_prompt_contract_intent_is_fail_closed_unsupported():
    """Intent zamrożony pod starym promptem v2 nie może wykonać się pod v3."""
    from types import SimpleNamespace

    from app.core.config import REAL_PROVIDER_PRICING_KEYS
    from app.research.durable_intent import DurableResearchExecutionIntent

    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="stale-model",
            research_timeout_seconds=60,
        ),
        account_id="account", topic_id=1, cap_usd=0.2, max_web_searches=1,
        question="Why?", niche=["systems"], max_tokens=oc.RESEARCH_CARD_MAX_TOKENS,
    )
    assert intent.prompt_contract_version == "anthropic_research_single_v3"
    assert intent.is_supported_by_current_worker()

    stale = intent.as_payload()
    stale["prompt_contract_version"] = "anthropic_research_single_v2"
    reloaded = DurableResearchExecutionIntent.from_payload(stale)
    assert not reloaded.is_supported_by_current_worker()


# --- każde przekroczenie budżetu = typowany, fail-closed błąd ----------------------


def _oversize_cases():
    def with_field(field, value):
        payload = _realistic_payload()
        payload[field] = value
        return payload

    def with_source_field(field, value):
        payload = _realistic_payload()
        payload["sources"][0][field] = value
        return payload

    long_claim = _ascii_text(oc.MAX_CLAIM_CHARS + 1)
    yield pytest.param(
        with_field("question", _ascii_text(oc.MAX_QUESTION_CHARS + 1)),
        "question", id="question-over")
    yield pytest.param(
        with_field("working_thesis", _ascii_text(oc.MAX_WORKING_THESIS_CHARS + 1)),
        "working_thesis", id="thesis-over")
    yield pytest.param(
        with_field("main_mechanism", _ascii_text(oc.MAX_MAIN_MECHANISM_CHARS + 1)),
        "main_mechanism", id="mechanism-over")
    yield pytest.param(
        with_field("confirmed_claims",
                   [f"Claim number {i} stays short." for i in range(oc.MAX_CONFIRMED_CLAIMS + 1)]),
        "confirmed_claims", id="confirmed-count-over")
    yield pytest.param(
        with_field("confirmed_claims", ["Fine claim.", long_claim]),
        "confirmed_claims[1]", id="confirmed-elem-over")
    yield pytest.param(
        with_field("uncertain_claims",
                   [f"Uncertain {i}." for i in range(oc.MAX_UNCERTAIN_CLAIMS + 1)]),
        "uncertain_claims", id="uncertain-count-over")
    yield pytest.param(
        with_field("uncertain_claims", [long_claim]),
        "uncertain_claims[0]", id="uncertain-elem-over")
    yield pytest.param(
        with_field("contradictions",
                   [f"Contradiction {i}." for i in range(oc.MAX_CONTRADICTIONS + 1)]),
        "contradictions", id="contradictions-count-over")
    yield pytest.param(
        with_field("contradictions", [_ascii_text(oc.MAX_CONTRADICTION_CHARS + 1)]),
        "contradictions[0]", id="contradictions-elem-over")
    yield pytest.param(
        with_field("strongest_counterargument",
                   _ascii_text(oc.MAX_COUNTERARGUMENT_CHARS + 1)),
        "strongest_counterargument", id="counterargument-over")
    yield pytest.param(
        with_field("citable_numbers", [_ascii_text(oc.MAX_CITABLE_NUMBER_CHARS + 1)]),
        "citable_numbers[0]", id="citable-elem-over")
    yield pytest.param(
        with_field("visual_idea", _ascii_text(oc.MAX_VISUAL_IDEA_CHARS + 1)),
        "visual_idea", id="visual-over")

    base = _realistic_payload()
    extra_source = dict(base["sources"][0])
    extra_source["url"] = "https://example.test/extra"
    payload = _realistic_payload()
    payload["sources"] = payload["sources"] + [extra_source]
    yield pytest.param(payload, "sources", id="sources-count-over")

    yield pytest.param(
        with_source_field(
            "url",
            "https://example.test/" + "p" * (oc.MAX_SOURCE_URL_CHARS + 1 - len("https://example.test/")),
        ),
        "sources[0].url", id="source-url-over")
    yield pytest.param(
        with_source_field("title", _ascii_text(oc.MAX_SOURCE_TITLE_CHARS + 1)),
        "sources[0].title", id="source-title-over")
    yield pytest.param(
        with_source_field("author_or_org", _ascii_text(oc.MAX_SOURCE_AUTHOR_CHARS + 1)),
        "sources[0].author_or_org", id="source-author-over")
    yield pytest.param(
        with_source_field("published_at", _ascii_text(oc.MAX_SOURCE_PUBLISHED_AT_CHARS + 1)),
        "sources[0].published_at", id="source-published-over")
    yield pytest.param(
        with_source_field("supports_claim", _ascii_text(oc.MAX_SUPPORTS_CLAIM_CHARS + 1)),
        "sources[0].supports_claim", id="source-supports-over")


@pytest.mark.parametrize(("payload", "field"), list(_oversize_cases()))
def test_every_budget_excess_is_typed_size_contract_error(payload, field):
    with pytest.raises(ResearchCardSizeContractError) as excinfo:
        _parse(_json(payload))
    assert excinfo.value.classification == "size_contract"
    assert f"field={field};" in str(excinfo.value)
    # Podklasa ResearchSchemaError => dziedziczy udowodnioną ścieżkę settlement.
    assert isinstance(excinfo.value, ResearchSchemaError)


def test_oversized_raw_response_fails_before_decoding():
    """Sufit całej odpowiedzi działa PRZED dekodowaniem — nie parsujemy gigantów."""
    payload = _max_payload()
    # Nie-ASCII wypełnienie w granicach per-pole eksploduje po escapowaniu \uXXXX.
    payload["main_mechanism"] = "ż" * oc.MAX_MAIN_MECHANISM_CHARS
    payload["visual_idea"] = "ż" * oc.MAX_VISUAL_IDEA_CHARS
    payload["strongest_counterargument"] = "ż" * oc.MAX_COUNTERARGUMENT_CHARS
    payload["confirmed_claims"] = ["ż" * oc.MAX_CLAIM_CHARS] * oc.MAX_CONFIRMED_CLAIMS
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    assert len(raw) > oc.MAX_RESPONSE_CHARS
    with pytest.raises(ResearchCardSizeContractError) as excinfo:
        _parse(raw)
    assert "field=response;" in str(excinfo.value)


# --- klient: usage zachowane, zero retry, truncation ma pierwszeństwo --------------


def _client_with(raw: str, stop_reason: str | None):
    calls: list[int] = []

    def caller(_plan):
        calls.append(1)
        return raw, USAGE, stop_reason

    client = _OfflineContractClient(
        "offline", "model", caller=caller, research_max_tokens=6000,
    )
    return client, calls


def test_size_contract_error_preserves_usage_and_never_retries():
    payload = _realistic_payload()
    payload["visual_idea"] = _ascii_text(oc.MAX_VISUAL_IDEA_CHARS + 1)
    client, calls = _client_with(_json(payload), "end_turn")
    with pytest.raises(ResearchCardSizeContractError) as excinfo:
        client.run_research(PLAN)
    assert excinfo.value.usage == USAGE
    assert excinfo.value.raw_text == _json(payload)
    assert excinfo.value.stop_reason == "end_turn"
    assert calls == [1]
    assert client.call_count == 1


def test_truncation_takes_priority_over_size_contract():
    """stop_reason=max_tokens => ResearchTruncatedError, parser nie czyta JSON-a."""
    client, calls = _client_with(_json(_realistic_payload()), "max_tokens")
    with pytest.raises(ResearchTruncatedError) as excinfo:
        client.run_research(PLAN)
    assert excinfo.value.classification == "truncation"
    assert "per-segment cap" in str(excinfo.value)
    assert calls == [1]


# --- prompt v3: każdy limit jawny, spójny z egzekwowanym budżetem ------------------


def test_prompt_v3_states_every_limit_and_format_rule():
    prompt = build_single_research_prompt(PLAN)
    assert "Research question: Why?" in prompt
    for phrase in (
        "compact single-line JSON object",
        "no newlines or indentation inside the JSON",
        "question: string, at most 30 words",
        "working_thesis: string, at most 60 words",
        "main_mechanism: string or null, at most 100 words",
        "confirmed_claims: array of 4-6 strings, each at most 30 words",
        "uncertain_claims: array of at most 3 strings, each at most 30 words",
        "contradictions: array of at most 3 strings, each at most 35 words",
        "strongest_counterargument: string or null, at most 60 words",
        "citable_numbers: array of 3-6 short strings, each at most 15 words",
        "never a raw JSON number",
        "visual_idea: string or null, at most 50 words",
        "sources: array of 4-6 objects",
        "title (string, at most 15 words)",
        "author_or_org (string of at most 10 words, or null)",
        "supports_claim must be a JSON string equal to the exact text of the one "
        "confirmed claim this source supports, or JSON null",
        "never a boolean, array, object, or number",
        "short metadata only, never article summaries",
        "never repeat the same fact in more than one field",
        "completing valid JSON has priority over adding more detail",
    ):
        assert phrase in prompt, phrase


def test_prompt_counts_match_enforced_budget():
    """Liczności w prompcie odpowiadają deterministycznym stałym kontraktu."""
    prompt = build_single_research_prompt(PLAN)
    assert oc.MAX_CONFIRMED_CLAIMS == 6 and "array of 4-6 strings" in prompt
    assert oc.MAX_UNCERTAIN_CLAIMS == 3 and "at most 3 strings" in prompt
    assert oc.MAX_CONTRADICTIONS == 3
    assert oc.MAX_CITABLE_NUMBERS == 6 and "3-6 short strings" in prompt
    assert oc.MAX_SOURCES == 6 and "array of 4-6 objects" in prompt


# --- diagnostyka: niewidoczne tokeny rozumowania są mierzone, nie zgadywane --------


class _StubUsageDetails:
    def __init__(self, thinking_tokens):
        self.thinking_tokens = thinking_tokens


class _StubServerToolUse:
    web_search_requests = 1


class _StubSdkUsage:
    input_tokens = 100
    output_tokens = 3155
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0
    server_tool_use = _StubServerToolUse()
    output_tokens_details = _StubUsageDetails(1900)


class _StubMessage:
    model = "model"
    id = "fake-research-response"
    content = ()
    usage = _StubSdkUsage()
    stop_reason = "max_tokens"


class _StubMessages:
    def create(self, **_kwargs):
        return _StubMessage()


class _StubSdkClient:
    messages = _StubMessages()


def test_call_anthropic_captures_thinking_tokens_from_sdk_usage():
    client = _OfflineContractClient(
        "offline", "model", caller=lambda plan: ("{}", USAGE, None),
    )
    text, usage, stop_reason = client._call_anthropic(
        _StubSdkClient(), "prompt", tools=None, max_tokens=3000,
    )
    assert text == ""
    assert stop_reason == "max_tokens"
    assert usage.output_tokens == 3155
    assert usage.thinking_tokens == 1900


def test_diagnostics_header_records_thinking_tokens(tmp_path):
    path = write_diagnostics(tmp_path, ResponseDiagnostics(
        run_id="run", stage="SINGLE", stop_reason="max_tokens",
        input_tokens=10, output_tokens=3155, cache_read_tokens=0,
        cache_write_tokens=0, web_search_requests=1,
        raw_response="{\"question\": \"cut",
        thinking_tokens=1900,
    ))
    content = path.read_text(encoding="utf-8")
    assert "thinking_tokens: 1900" in content
    assert "output_tokens: 3155" in content


def test_surplus_citable_numbers_are_trimmed_not_fatal():
    """The one list whose length carries no meaning is trimmed, not refused.

    citable_numbers holds optional figures a writer may quote; the writer cites
    evidence ids, never this list. A live card carrying a seventh number was
    discarded whole, taking a complete corpus with it. Every other list still
    fails closed, because truncating uncertain_claims or contradictions would
    silently delete the caveats that become the writer's forbidden list.
    """
    payload = _realistic_payload()
    payload["citable_numbers"] = [
        f"{i} percent" for i in range(oc.MAX_CITABLE_NUMBERS + 3)
    ]
    draft = _parse(_json(payload))
    assert len(draft.citable_numbers) == oc.MAX_CITABLE_NUMBERS
    assert draft.citable_numbers[0] == "0 percent"

    for field, limit in (
        ("uncertain_claims", oc.MAX_UNCERTAIN_CLAIMS),
        ("contradictions", oc.MAX_CONTRADICTIONS),
    ):
        over = _realistic_payload()
        over[field] = ["a short claim"] * (limit + 1)
        with pytest.raises(ResearchCardSizeContractError) as excinfo:
            _parse(_json(over))
        assert f"field={field};" in str(excinfo.value)
