"""Testy etapowego researchu A1 (discovery) / A2 (per-source extraction) / B (synthesis)
(stabilizacja Stage A, 2026-07-12, ADR-020). Powód: drugi realny test dwuetapowego
researchu (run 2a3b4bb9) pokazał, że nawet lekki schemat etapu A wciąż jest zbyt
kruchy — JEDEN duży JSON obejmujący WSZYSTKIE źródła naraz ucina się, i wtedy
WSZYSTKIE źródła giną razem. Te testy dowodzą, że po podziale na per-source wywołania:
- awaria źródła N nie ma wpływu na źródła 1..N-1 (zapisane niezależnie),
- surowa odpowiedź i stop_reason są zapisywane do diagnostyki przy KAŻDYM błędzie,
- wznowienie ekstrakcji kontynuuje dokładnie tam, gdzie się skończyło (nawet po
  symulowanym restarcie procesu),
- wznowienie syntezy NIGDY nie woła ponownie discovery/extraction,
- JSONL z uciętym ostatnim rekordem zachowuje wcześniejsze poprawne rekordy,
- realny koszt/usage nigdy nie znika, niezależnie od tego, w którym etapie padnie,
- pliki diagnostyczne nie zawierają sekretów.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.core.ids import new_run_id
from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import (
    ModelUsage,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    SourceCandidateRecord,
    SourceCandidateStatus,
    SourceVerification,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyDecision, PolicyEngine
from app.ports.notification import LogNotification
from app.ports.storage import ResearchTopicIntegrityError
from app.research.anthropic_client import AnthropicResearchClient, _parse_discovery_candidates_jsonl
from app.research.base import (
    ResearchAuthenticationError,
    ResearchError,
    ResearchInvalidRequestError,
    ResearchParseError,
    ResearchRateLimitError,
    ResearchTimeout,
    ResearchUnknownProviderError,
)
from app.research.diagnostics import diagnostics_dir
from app.research.cost_estimator import (
    estimate_discovery_cost_usd,
    estimate_extraction_cost_per_source_usd,
    estimate_synthesis_cost_usd,
    estimate_with_retries,
)
from app.research.fake_client import FakeResearchClient
from app.storage.repositories import SqliteStorage
from app.research.validation import TOO_FEW_VERIFIED_SOURCES
from app.workflows.research.pipeline import (
    CompletedResearchExistsError,
    _format_audit_error,
    resume_staged_research,
    run_source_discovery,
    run_source_extraction,
    run_staged_research_pipeline,
    run_synthesis_from_cards,
)


def _selected_topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Why airline ticket prices change every few hours",
        question="What pricing system makes fares move so often?",
        score=89.5, status=TopicStatus.SELECTED,
    ))


def _seeded_run_with_candidates(storage, account, topic, n: int = 3) -> str:
    """Ustawia research_run w stanie DISCOVERY_COMPLETE z N kandydatami — pozwala
    testować etap A2 (extraction) w izolacji, bez wołania A1 (discovery)."""
    run_id = new_run_id()
    storage.ensure_account(account)
    storage.create_run(Run(id=run_id, account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING))
    storage.create_research_run(ResearchRun(
        id=run_id, account_id=account.id, topic_id=int(topic.id),
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_PENDING,
    ))
    storage.create_source_candidates(run_id, [
        SourceCandidateRecord(research_run_id=run_id, url=f"https://example.org/source-{i}",
                              title=f"Candidate source {i}")
        for i in range(n)
    ])
    return run_id


def _run_discovery(settings, storage, account, topic, client, **kwargs):
    if not settings.dry_run and "run_cap_usd" not in kwargs:
        kwargs["run_cap_usd"] = 10.0
    return run_source_discovery(
        account, topic, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _run_extraction(settings, storage, account, run_id, client, **kwargs):
    if not settings.dry_run and "run_cap_usd" not in kwargs:
        kwargs["run_cap_usd"] = 10.0
    return run_source_extraction(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _run_synthesis(settings, storage, account, run_id, client, **kwargs):
    if not settings.dry_run and "run_cap_usd" not in kwargs:
        kwargs["run_cap_usd"] = 10.0
    return run_synthesis_from_cards(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


class _CaptureBudgetPolicy:
    def __init__(self):
        self.calls = []

    def check_can_run(self, account):
        return PolicyDecision.ok()

    def check_run_budget(self, estimated_total, cap, *, current_run_cost, account):
        self.calls.append((estimated_total, cap, current_run_cost))
        return PolicyDecision.block("RUN_CAP_EXCEEDED", "captured")


def test_a1_preflight_uses_retry_multiplier(settings, storage, account):
    topic = _selected_topic(storage, account)
    policy = _CaptureBudgetPolicy()
    summary = run_source_discovery(
        account, topic, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=policy, notifier=LogNotification(), max_searches=1,
        max_output_tokens=600, max_retries=2, run_cap_usd=2.0)
    base = estimate_discovery_cost_usd(settings, 1, 600).conservative_usd
    assert policy.calls == [(estimate_with_retries(base, 2), 2.0, 0.0)]
    assert summary.blocked
    assert summary.run_id is None


def test_a2_preflight_uses_retry_multiplier_per_source(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    policy = _CaptureBudgetPolicy()
    summary = run_source_extraction(
        run_id, account, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=policy, notifier=LogNotification(), max_sources=1,
        max_web_searches_per_source=1, max_output_tokens=1500,
        max_retries=2, run_cap_usd=2.0)
    base = estimate_extraction_cost_per_source_usd(settings, 1, 1500).conservative_usd
    assert policy.calls == [(estimate_with_retries(base, 2), 2.0, 0.0)]
    assert summary.blocked
    assert storage.get_research_usage(run_id) == []


def test_b_resume_includes_persisted_usage_and_retry_multiplier(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    extraction = _run_extraction(
        settings, storage, account, run_id, FakeResearchClient("good"), max_sources=3)
    assert extraction.sources_count == 3
    current = sum(row.estimated_cost_usd for row in storage.get_research_usage(run_id))
    policy = _CaptureBudgetPolicy()
    summary = run_synthesis_from_cards(
        run_id, account, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=policy, notifier=LogNotification(), synthesize_max_tokens=3000,
        forwarded_context_tokens=2500, max_retries=2, run_cap_usd=2.0)
    base = estimate_synthesis_cost_usd(settings, 3000, 2500).conservative_usd
    assert policy.calls == [(
        round(current + estimate_with_retries(base, 2), 6), 2.0, round(current, 6))]
    assert summary.blocked


def test_b_resume_is_blocked_before_client_when_3000_token_projection_exceeds_cap(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(
        settings, storage, account, run_id, FakeResearchClient("good"), max_sources=3)
    prior_usage = storage.get_research_usage(run_id)
    current = sum(row.estimated_cost_usd for row in prior_usage)
    projected_b = estimate_synthesis_cost_usd(
        settings, 3000, 2500).conservative_usd

    class ForbiddenSynthesisClient(FakeResearchClient):
        def synthesize_from_cards(self, plan, cards):
            raise AssertionError("budget guard must run before stage B client")

    summary = run_synthesis_from_cards(
        run_id, account, settings=settings, storage=storage,
        research_client=ForbiddenSynthesisClient("good"),
        usage_tracker=UsageTracker(
            settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        synthesize_max_tokens=3000, forwarded_context_tokens=2500,
        max_retries=0, run_cap_usd=current + projected_b - 0.000001,
    )

    assert summary.blocked and summary.block_code == "RUN_CAP_EXCEEDED"
    after_usage = storage.get_research_usage(run_id)
    assert len(after_usage) == len(prior_usage)
    assert [row.id for row in after_usage] == [row.id for row in prior_usage]
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE


def test_a1_timeout_usage_is_recorded_without_second_attempt(settings, storage, account):
    topic = _selected_topic(storage, account)
    calls = []

    def discover_caller(plan, max_searches):
        calls.append(1)
        raise ResearchTimeout(
            "A1 timeout", usage=Usage(output_tokens=40_000), model="m")

    client = AnthropicResearchClient(
        "offline", "m", discover_caller=discover_caller, max_retries=0)
    summary = run_source_discovery(
        account, topic, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        max_searches=1, max_output_tokens=600, max_retries=0, run_cap_usd=0.50)

    assert calls == [1]
    assert not summary.blocked
    assert "timeout" in (summary.error or "").lower()
    usage = storage.get_research_usage(summary.run_id)
    assert len(usage) == 1 and usage[0].task == "research_discover"


def test_a2_timeout_usage_is_recorded_without_second_attempt_for_one_source(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    calls = []

    def extract_caller(plan, candidate):
        calls.append(candidate.url)
        raise ResearchTimeout(
            "A2 timeout", usage=Usage(output_tokens=40_000), model="m")

    client = AnthropicResearchClient(
        "offline", "m", extract_caller=extract_caller, max_retries=0)
    summary = run_source_extraction(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        max_sources=1, max_web_searches_per_source=1, max_output_tokens=1500,
        max_retries=0, run_cap_usd=0.50)

    assert len(calls) == 1
    assert not summary.blocked
    assert summary.error is None
    assert summary.sources_failed == 1
    usage = storage.get_research_usage(run_id)
    assert len(usage) == 1 and usage[0].task == "research_extract"
    candidate = storage.list_source_candidates(run_id)[0]
    assert candidate.status == SourceCandidateStatus.EXTRACTION_FAILED


def test_b_timeout_usage_restores_sources_complete_without_retry(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(
        settings, storage, account, run_id, FakeResearchClient("good"), max_sources=3)
    prior_count = len(storage.get_research_usage(run_id))
    calls = []

    def synthesize_caller(plan, cards):
        calls.append(1)
        raise ResearchTimeout(
            "B timeout", usage=Usage(output_tokens=40_000), model="m")

    client = AnthropicResearchClient(
        "offline", "m", synthesize_from_cards_caller=synthesize_caller,
        max_retries=0)
    summary = run_synthesis_from_cards(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        synthesize_max_tokens=3000, forwarded_context_tokens=2500,
        max_retries=0, run_cap_usd=0.50)

    assert calls == [1]
    assert not summary.blocked
    assert "timeout" in (summary.error or "").lower()
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE
    usage = storage.get_research_usage(run_id)
    assert len(usage) == prior_count + 1
    assert usage[-1].task == "research_synthesize_cards"


def test_resume_rejects_other_account_before_cost_sync_or_client(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})

    class ForbiddenClient(FakeResearchClient):
        def extract_source(self, plan, candidate):
            raise AssertionError("account mismatch must stop before caller")

    before = storage.get_run(run_id).cost_usd
    with pytest.raises(ValueError, match="należy do konta"):
        run_source_extraction(
            run_id, other, settings=settings, storage=storage,
            research_client=ForbiddenClient("good"),
            usage_tracker=UsageTracker(
                settings, storage, costs_csv_path=settings.costs_csv_path),
            policy=PolicyEngine(settings, storage), notifier=LogNotification(),
            run_cap_usd=1.0)
    assert storage.get_run(run_id).cost_usd == before
    assert storage.get_research_usage(run_id) == []


def test_cli_resume_default_cap_is_absolute_not_prior_cost_plus_allowance(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    storage.add_model_usage(ModelUsage(
        run_id=run_id, model="m", task="research_extract",
        estimated_cost_usd=0.40, dry_run=False))
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: settings)

    assert run_capped_research.main(["--resume", run_id, "--estimate-only"]) == 0
    output = capsys.readouterr().out
    assert "koszt już poniesiony:          0.400000 USD" in output
    assert "cap tego wznowienia (--max-cost-usd): 0.20 USD" in output


def test_cli_resume_rejects_other_account_before_usage_or_client(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    configured = replace(settings, accounts={account.id: account, other.id: other})
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: configured)

    def forbidden_client(*args, **kwargs):
        raise AssertionError("account mismatch must stop before client")

    monkeypatch.setattr(run_capped_research, "AnthropicResearchClient", forbidden_client)
    before = storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0]
    assert run_capped_research.main([
        "--resume", run_id, "--account", other.id,
    ]) == 1
    assert "należy do konta" in capsys.readouterr().out
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == before


def _run_staged(settings, storage, account, topic, client, **kwargs):
    if not settings.dry_run and "run_cap_usd" not in kwargs:
        kwargs["run_cap_usd"] = 10.0
    return run_staged_research_pipeline(
        account, topic, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _resume_staged(settings, storage, account, run_id, client, **kwargs):
    """CAŁKOWICIE NOWE instancje PolicyEngine/UsageTracker/notifiera — symuluje
    prawdziwy restart procesu, tak jak w tests/test_research_resumability.py."""
    return resume_staged_research(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _assert_run_cost_matches_research_usage(storage, run_id: str) -> float:
    expected = sum(usage.estimated_cost_usd for usage in storage.get_research_usage(run_id))
    run = storage.get_run(run_id)
    assert run is not None
    assert run.cost_usd == pytest.approx(expected)
    return expected


class _AlwaysFailExtractClient(FakeResearchClient):
    """extract_source ZAWSZE pada, z realnym usage/raw_text/stop_reason dopiętym
    do wyjątku — jak prawdziwy incydent (2026-07-12, run 2a3b4bb9)."""

    def extract_source(self, plan, candidate):
        raise ResearchParseError(
            "Niepoprawny JSON z modelu (extract_source): Unterminated string at char 187",
            usage=Usage(input_tokens=18500, output_tokens=210, web_search_requests=1),
            model="sonnet-real",
            raw_text='{"url": "https://example.org/source-0", "title": "Candidate", "supported_claims": ["trunca',
            stop_reason="max_tokens",
        )


class _NthExtractionFailsClient(FakeResearchClient):
    """extract_source pada TYLKO dla kandydata o indeksie `fail_index` (0-based, wg
    kolejności wywołań) — pozostali kandydaci muszą zostać nietknięci."""

    def __init__(self, scenario: str = "good", fail_index: int = 0) -> None:
        super().__init__(scenario)
        self.fail_index = fail_index
        self.extract_calls = 0

    def extract_source(self, plan, candidate):
        idx = self.extract_calls
        self.extract_calls += 1
        if idx == self.fail_index:
            raise ResearchParseError(
                f"Niepoprawny JSON z modelu (extract_source, źródło #{idx}): "
                "Unterminated string at char 91",
                usage=Usage(input_tokens=17000, output_tokens=180, web_search_requests=1),
                model="sonnet-real", raw_text='{"url": "trunc', stop_reason="max_tokens",
            )
        return super().extract_source(plan, candidate)


class _BrokenSynthesizeFromCardsOnceClient(FakeResearchClient):
    """synthesize_from_cards pada za KAŻDYM razem, dopóki `should_fail=False` nie
    zostanie ustawione z zewnątrz — buduje scenariusz do testów wznowienia etapu B."""

    def __init__(self, scenario: str = "good") -> None:
        super().__init__(scenario)
        self.should_fail = True
        self.synthesize_calls = 0

    def synthesize_from_cards(self, plan, cards):
        self.synthesize_calls += 1
        if self.should_fail:
            raise ResearchParseError(
                "Niepoprawny JSON z modelu (synthesize_from_cards): "
                "Unterminated string at char 340",
                usage=Usage(input_tokens=2100, output_tokens=950, web_search_requests=0),
                model="sonnet-real", raw_text='{"question": "trunc', stop_reason="max_tokens",
            )
        return super().synthesize_from_cards(plan, cards)


class _DiscoveryAndExtractionForbiddenClient(FakeResearchClient):
    """Jeśli discover_sources LUB extract_source zostaną wywołane podczas wznowienia
    etapu B, test MUSI polec — dowód, że wznowienie syntezy nigdy nie robi ponownego
    web search."""

    def discover_sources(self, plan, max_searches):
        raise AssertionError("discover_sources NIE POWINIEN być wołany przy wznowieniu etapu B!")

    def extract_source(self, plan, candidate):
        raise AssertionError("extract_source NIE POWINIEN być wołany przy wznowieniu etapu B!")


class _BrokenDiscoveryClient:
    """Minimalny klient: discover_sources pada z realnym usage/raw_text dopiętym."""
    model = "sonnet-real"

    def discover_sources(self, plan, max_searches):
        raise ResearchParseError(
            "Niepoprawny JSON z modelu (discover_sources): Unterminated string at char 55",
            usage=Usage(input_tokens=19200, output_tokens=140, web_search_requests=2),
            model=self.model, raw_text='{"url": "https://example.org/a", "title": "trunc',
            stop_reason="max_tokens",
        )

    def extract_source(self, plan, candidate):  # pragma: no cover
        raise AssertionError("extract_source nie powinien być wołany po błędzie A1")

    def synthesize_from_cards(self, plan, cards):  # pragma: no cover
        raise AssertionError("synthesize_from_cards nie powinien być wołany po błędzie A1")


class _DiscoveryErrorWithoutUsageClient:
    """Błąd transportowy przed otrzymaniem usage od dostawcy."""

    def discover_sources(self, plan, max_searches):
        raise ResearchError("discovery failed before usage was available")


class _SynthesisErrorWithoutUsageClient(FakeResearchClient):
    """Błąd etapu B przed otrzymaniem usage od dostawcy."""

    def synthesize_from_cards(self, plan, cards):
        raise ResearchError("synthesis failed before usage was available")


class _TypedInvalidDiscoveryWithUsageClient:
    model = "typed-provider-model"

    def __init__(self) -> None:
        self.discover_calls = 0

    def discover_sources(self, plan, max_searches):
        self.discover_calls += 1
        raise ResearchInvalidRequestError(
            "provider rejected discovery request",
            status_code=422,
            usage=Usage(input_tokens=321, output_tokens=45, web_search_requests=0),
            model=self.model,
        )


class _MappedSdkBodyErrorClient:
    """Offline SDK-shaped 422 whose body must never enter persistent audit."""

    model = "typed-provider-model"
    marker = "RAW_RESPONSE_MARKER"

    def __init__(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        httpx = pytest.importorskip("httpx")
        request = httpx.Request("POST", "https://api.anthropic.invalid/v1/messages")
        response = httpx.Response(422, request=request)
        body = {"error": {"message": self.marker}, "private_payload": self.marker}
        self._anthropic = anthropic
        self._sdk_error = anthropic.UnprocessableEntityError(
            f"Error code: 422 - {body}", response=response, body=body)
        self._mapper = AnthropicResearchClient("offline", self.model, max_retries=0)

    def _raise_mapped(self) -> None:
        mapped = self._mapper._map_anthropic_error(self._sdk_error, self._anthropic)
        raise mapped from self._sdk_error

    def discover_sources(self, plan, max_searches):
        self._raise_mapped()

    def extract_source(self, plan, candidate):
        self._raise_mapped()


def _set_stale_run_cache(storage, run_id: str, cost_usd: float = 99.0) -> None:
    storage.conn.execute("UPDATE runs SET cost_usd=? WHERE id=?", (cost_usd, run_id))
    storage.conn.commit()


# --- 0. Sanity: pełny etapowy pipeline, dobra ścieżka (fundament dla reszty testów) ---

def test_staged_pipeline_happy_path_reaches_complete(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run_staged(settings, storage, account, topic, FakeResearchClient("good"))

    assert summary.passed
    assert summary.card is not None
    assert summary.candidates_discovered == 3
    assert summary.sources_extracted == 3
    assert summary.sources_failed == 0

    research_run = storage.get_research_run(summary.run_id)
    assert research_run.flow == ResearchFlow.STAGED
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.research_card_id == summary.card.id
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED
    _assert_run_cost_matches_research_usage(storage, summary.run_id)

    extracted = storage.list_source_candidates(summary.run_id, SourceCandidateStatus.EXTRACTED)
    assert len(extracted) == 3


def test_staged_re_research_requires_force_and_force_keeps_history(settings, storage, account):
    topic = _selected_topic(storage, account)
    first = _run_staged(settings, storage, account, topic, FakeResearchClient("good"))
    old_card_id = first.card.id
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage")
    }

    class _ForbiddenClient(FakeResearchClient):
        def discover_sources(self, plan, max_searches):
            raise AssertionError("blocked re-research must not call discovery")

    with pytest.raises(CompletedResearchExistsError, match="--force-re-research"):
        _run_staged(settings, storage, account, topic, _ForbiddenClient("good"))

    counts_after_block = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after_block == counts_before

    forced = _run_staged(
        settings, storage, account, topic, FakeResearchClient("good"), force_re_research=True,
    )
    assert forced.run_id != first.run_id
    assert forced.card.id != old_card_id
    assert storage.get_research_card(old_card_id) is not None
    assert storage.get_research_run(forced.run_id).flow == ResearchFlow.STAGED
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED

    cards_before_failure = [card.id for card in storage.list_research_cards(account.id)]
    failed = _run_staged(
        settings, storage, account, topic, _BrokenDiscoveryClient(),
        force_re_research=True,
    )
    assert failed.error is not None
    assert storage.get_run(failed.run_id).status == RunStatus.FAILED
    assert storage.get_research_run(failed.run_id).status == ResearchRunStatus.FAILED
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED
    assert [card.id for card in storage.list_research_cards(account.id)] == cards_before_failure
    assert storage.get_research_run(first.run_id).research_card_id == old_card_id


# --- 1 + 2. Raw response i stop_reason zapisywane przy błędzie (etap A2) ---

def test_raw_response_and_stop_reason_saved_on_extraction_error(settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)

    summary = _run_extraction(real_settings, storage, account, run_id, _AlwaysFailExtractClient("good"))

    candidate = storage.list_source_candidates(run_id)[0]
    assert candidate.status == SourceCandidateStatus.EXTRACTION_FAILED

    diag_path = diagnostics_dir(real_settings.data_dir, run_id) / f"A2_source_{candidate.id}_raw_response.txt"
    assert diag_path.exists()
    content = diag_path.read_text(encoding="utf-8")
    assert "stop_reason: max_tokens" in content
    assert "input_tokens: 18500" in content
    assert "web_search_requests: 1" in content
    assert "Unterminated string at char 187" in content   # parse_error_location
    assert '"supported_claims": ["trunca' in content        # fragment surowej odpowiedzi

    # 9. usage/koszt zachowane mimo błędu etapu A2.
    assert summary.model == "sonnet-real"
    assert summary.input_tokens == 18500
    assert summary.output_tokens == 210
    assert summary.web_search_requests == 1
    a2_usage = [u for u in storage.get_research_usage(run_id)
                if u.task == "research_extract"]
    assert summary.cost_usd == pytest.approx(
        sum(u.estimated_cost_usd for u in a2_usage))
    run = storage.get_run(run_id)
    assert run is not None and run.cost_usd > 0


# --- 3. Ucięty PIERWSZY Source Card — pozostałe nietknięte ---

def test_first_source_extraction_fails_others_unaffected(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=4)
    client = _NthExtractionFailsClient("good", fail_index=0)

    summary = _run_extraction(settings, storage, account, run_id, client)

    extracted = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)
    failed = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTION_FAILED)
    assert len(extracted) == 3
    assert len(failed) == 1
    assert summary.sources_extracted == 3
    assert summary.sources_failed == 1
    research_run = storage.get_research_run(run_id)
    assert research_run.status == ResearchRunStatus.SOURCES_COMPLETE  # 3 >= min_sources(3)


# --- 4 + 5. Ucięty CZWARTY Source Card — trzy wcześniejsze zachowane ---

def test_fourth_source_extraction_fails_first_three_preserved(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=4)
    client = _NthExtractionFailsClient("good", fail_index=3)

    summary = _run_extraction(settings, storage, account, run_id, client)

    extracted = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)
    failed = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTION_FAILED)
    assert len(extracted) == 3
    assert {c.url for c in extracted} == {
        "https://example.org/source-0", "https://example.org/source-1",
        "https://example.org/source-2",
    }
    assert len(failed) == 1
    assert failed[0].url == "https://example.org/source-3"
    assert summary.sources_extracted == 3
    assert summary.sources_failed == 1
    research_run = storage.get_research_run(run_id)
    assert research_run.status == ResearchRunStatus.SOURCES_COMPLETE


# --- 6. Restart i wznowienie etapu A2 (extraction) ---

def test_resume_extraction_after_restart_continues_remaining(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=4)

    # Pierwsze "uruchomienie" -- celowo ograniczone do 2 kandydatów (max_sources=2).
    summary1 = _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"),
                               max_sources=2)
    assert summary1.sources_extracted == 2
    research_run = storage.get_research_run(run_id)
    assert research_run.status == ResearchRunStatus.PARTIAL  # 2 < min_sources(3), dotąd

    # "Restart": nowy klient, nowe instancje Policy/UsageTracker/notifiera (patrz
    # _run_extraction -> buduje je od zera za każdym wywołaniem) -- jedyny łącznik
    # ze starym stanem to `run_id`, reszta wraca z bazy.
    summary2 = _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"),
                               max_sources=10)
    assert summary2.sources_extracted == 2  # dokładnie pozostali 2 kandydaci, nie 4

    all_extracted = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)
    assert len(all_extracted) == 4
    research_run2 = storage.get_research_run(run_id)
    assert research_run2.status == ResearchRunStatus.SOURCES_COMPLETE
    _assert_run_cost_matches_research_usage(storage, run_id)


# --- 7. Ponowienie etapu B (synthesis) bez web search, przez pełny dispatcher wznowienia ---

def test_resume_synthesis_never_calls_discovery_or_extraction(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE

    # RESUME_B is deliberately legal only after a durable B failure; the first
    # call is fresh B and records that failure before the dispatcher resumes it.
    broken = _BrokenSynthesizeFromCardsOnceClient("good")
    summary1 = _run_synthesis(settings, storage, account, run_id, broken)
    assert summary1.error is not None
    assert summary1.cost_usd > 0                          # 9. usage/koszt zachowane mimo błędu B
    research_run = storage.get_research_run(run_id)
    assert research_run.status == ResearchRunStatus.SOURCES_COMPLETE  # WRACA, nie PARTIAL/FAILED
    failed_resume_audit = storage.get_run(run_id)
    assert failed_resume_audit.status == RunStatus.FAILED
    assert failed_resume_audit.error.startswith("[synthesize_from_cards]")
    assert len(storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)) == 3
    _assert_run_cost_matches_research_usage(storage, run_id)

    resume_client = _DiscoveryAndExtractionForbiddenClient("good")
    summary2 = _resume_staged(settings, storage, account, run_id, resume_client)

    assert summary2.error is None
    assert summary2.card is not None
    research_run2 = storage.get_research_run(run_id)
    assert research_run2.status == ResearchRunStatus.COMPLETE
    assert research_run2.research_card_id is not None
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_force_reresearch_b_failure_then_resume_restores_durable_force_mode(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    original = _run_staged(settings, storage, account, topic, FakeResearchClient("good"))
    assert original.card is not None

    broken = _BrokenSynthesizeFromCardsOnceClient("good")
    failed = _run_staged(
        settings, storage, account, topic, broken, force_re_research=True,
    )
    assert failed.error is not None
    failed_run = storage.get_run(failed.run_id)
    failed_research_run = storage.get_research_run(failed.run_id)
    assert failed_run.status == RunStatus.FAILED
    assert failed_research_run.status == ResearchRunStatus.SOURCES_COMPLETE
    assert failed_research_run.is_force_reresearch is True

    # A separate connection simulates a restarted dispatcher: only the durable
    # marker, not Python process memory, may select the forced resume mode.
    resumed_storage = SqliteStorage.open(settings.db_path)
    resumed = _resume_staged(
        settings, resumed_storage, account, failed.run_id,
        _DiscoveryAndExtractionForbiddenClient("good"),
    )
    assert resumed.card is not None
    assert resumed_storage.get_run(failed.run_id).status == RunStatus.DRY_RUN
    assert resumed_storage.get_research_run(failed.run_id).status == ResearchRunStatus.COMPLETE
    assert resumed_storage.list_topics(account.id)[0].status == TopicStatus.USED
    resumed_storage.close()


def test_force_resume_preflight_rejects_before_provider_call_when_marker_is_invalid(
        settings, storage, account, monkeypatch):
    topic = _selected_topic(storage, account)
    _run_staged(settings, storage, account, topic, FakeResearchClient("good"))
    failed = _run_staged(
        settings, storage, account, topic,
        _BrokenSynthesizeFromCardsOnceClient("good"), force_re_research=True,
    )
    storage.conn.execute(
        "UPDATE research_runs SET is_force_reresearch=0 WHERE id=?", (failed.run_id,),
    )
    storage.conn.commit()
    client = FakeResearchClient("good")
    calls = 0

    def forbidden_synthesis(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("preflight must fail before provider call")

    monkeypatch.setattr(client, "synthesize_from_cards", forbidden_synthesis)
    usage_before = len(storage.get_research_usage(failed.run_id))
    with pytest.raises(ResearchTopicIntegrityError):
        _resume_staged(settings, storage, account, failed.run_id, client)
    assert calls == 0
    assert len(storage.get_research_usage(failed.run_id)) == usage_before
    assert storage.get_research_run(failed.run_id).status == ResearchRunStatus.SOURCES_COMPLETE


def test_synthesis_error_without_usage_preserves_canonical_cost(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))
    expected_cost = _assert_run_cost_matches_research_usage(storage, run_id)
    usage_count = len(storage.get_research_usage(run_id))
    _set_stale_run_cache(storage, run_id)

    summary = _run_synthesis(
        settings, storage, account, run_id, _SynthesisErrorWithoutUsageClient("good"),
    )

    assert summary.error == "synthesis failed before usage was available"
    assert len(storage.get_research_usage(run_id)) == usage_count
    run = storage.get_run(run_id)
    assert run is not None
    assert run.cost_usd == pytest.approx(expected_cost)
    assert run.status == RunStatus.FAILED
    assert run.finished_at is not None
    assert run.error == (
        "[synthesize_from_cards] ResearchError: "
        "synthesis failed before usage was available"
    )
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE


def test_fresh_b_max_tokens_records_usage_once_and_finishes_failed_after_reopen(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(real_settings, storage, account, run_id, FakeResearchClient("good"))
    prior_usage = len(storage.get_research_usage(run_id))
    prior_cards = storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0]
    calls = []
    billed = Usage(input_tokens=1904, output_tokens=3000, web_search_requests=0)

    def truncated_b(plan, cards):
        calls.append(1)
        return '{"question": "cut', billed, "max_tokens"

    client = AnthropicResearchClient(
        "offline", "m", synthesize_from_cards_caller=truncated_b,
        synthesize_max_tokens=3000, max_retries=0,
    )
    summary = _run_synthesis(
        real_settings, storage, account, run_id, client,
        synthesize_max_tokens=3000, max_retries=0,
    )

    assert calls == [1]
    assert summary.error is not None
    assert "stop_reason=max_tokens" in summary.error
    usage = storage.get_research_usage(run_id)
    assert len(usage) == prior_usage + 1
    assert usage[-1].task == "research_synthesize_cards"
    assert usage[-1].output_tokens == 3000
    assert storage.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == prior_cards
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE
    selected = storage.list_topics_by_status(account.id, TopicStatus.SELECTED)
    assert any(row.id == topic.id for row in selected)

    reopened = SqliteStorage.open(real_settings.db_path)
    try:
        persisted_run = reopened.get_run(run_id)
        persisted_research = reopened.get_research_run(run_id)
        assert persisted_run.status == RunStatus.FAILED
        assert persisted_run.finished_at is not None
        assert "stop_reason=max_tokens" in persisted_run.error
        assert persisted_research.status == ResearchRunStatus.SOURCES_COMPLETE
        assert persisted_research.research_card_id is None
        assert reopened.conn.execute(
            "SELECT count(*) FROM research_cards WHERE topic_id=?", (topic.id,),
        ).fetchone()[0] == 0
    finally:
        reopened.close()

    diagnostic = diagnostics_dir(real_settings.data_dir, run_id) / "B_raw_response.txt"
    content = diagnostic.read_text(encoding="utf-8")
    assert "stop_reason: max_tokens" in content
    assert "max_output_tokens=3000" in content


# --- 8. JSONL z uszkodzonym ostatnim rekordem — wcześniejsze rekordy zachowane ---

def test_jsonl_truncated_last_record_keeps_earlier_ones():
    text = (
        '{"url": "https://a.example/1", "title": "First"}\n'
        '{"url": "https://a.example/2", "title": "Second"}\n'
        '{"url": "https://a.example/3", "title": "Thi'   # ucięty ostatni rekord
    )
    candidates = _parse_discovery_candidates_jsonl(text)
    assert len(candidates) == 2
    assert [c.url for c in candidates] == ["https://a.example/1", "https://a.example/2"]


def test_jsonl_broken_middle_line_is_skipped_not_fatal():
    text = (
        '{"url": "https://a.example/1", "title": "First"}\n'
        'not even close to json\n'
        '{"url": "https://a.example/3", "title": "Third"}\n'
    )
    candidates = _parse_discovery_candidates_jsonl(text)
    assert [c.url for c in candidates] == ["https://a.example/1", "https://a.example/3"]


def test_jsonl_zero_valid_candidates_raises():
    with pytest.raises(ResearchParseError):
        _parse_discovery_candidates_jsonl("not json\nstill not json\n")


# --- 9. Usage i koszt zachowane przy KAŻDYM rodzaju błędu — tu: etap A1 (discovery) ---

def test_real_usage_preserved_when_discovery_fails(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run_discovery(settings, storage, account, topic, _BrokenDiscoveryClient())

    assert summary.error is not None
    assert summary.cost_usd > 0
    assert summary.input_tokens == 19200
    assert summary.output_tokens == 140
    assert summary.web_search_requests == 2

    research_run = storage.get_research_run(summary.run_id)
    assert research_run.status == ResearchRunStatus.FAILED   # nic do wznowienia — brak trwałych kandydatów
    assert storage.list_source_candidates(summary.run_id) == []

    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.FAILED and run.cost_usd > 0
    _assert_run_cost_matches_research_usage(storage, summary.run_id)


def test_discovery_error_without_usage_repairs_stale_cache(settings, storage, account, monkeypatch):
    topic = _selected_topic(storage, account)
    original_create_research_run = storage.create_research_run

    def create_research_run_with_stale_cache(research_run):
        original_create_research_run(research_run)
        _set_stale_run_cache(storage, research_run.id)
        return research_run

    monkeypatch.setattr(storage, "create_research_run", create_research_run_with_stale_cache)

    summary = _run_discovery(
        settings, storage, account, topic, _DiscoveryErrorWithoutUsageClient(),
    )

    assert summary.error == "discovery failed before usage was available"
    assert storage.get_research_usage(summary.run_id) == []
    run = storage.get_run(summary.run_id)
    assert run is not None
    assert run.cost_usd == 0.0
    assert run.status == RunStatus.FAILED
    assert storage.get_research_run(summary.run_id).status == ResearchRunStatus.FAILED


def test_typed_non_retryable_discovery_with_usage_is_recorded_once_after_reopen(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    client = _TypedInvalidDiscoveryWithUsageClient()

    summary = _run_discovery(
        real_settings, storage, account, topic, client,
        max_retries=0, run_cap_usd=10.0,
    )

    assert client.discover_calls == 1
    assert summary.error == "provider rejected discovery request"

    reopened = SqliteStorage.open(real_settings.db_path)
    try:
        usage = reopened.get_research_usage(summary.run_id)
        assert len(usage) == 1
        assert usage[0].model == "typed-provider-model"
        assert usage[0].input_tokens == 321
        assert usage[0].output_tokens == 45
        assert usage[0].web_search_requests == 0

        run = reopened.get_run(summary.run_id)
        assert run.status == RunStatus.FAILED
        assert run.finished_at is not None
        assert run.cost_usd == pytest.approx(
            sum(row.estimated_cost_usd for row in usage))
        assert "[discover_sources]" in run.error
        assert "ResearchInvalidRequestError" in run.error
        assert "status_code=422" in run.error
        assert "retryable=False" in run.error

        research_run = reopened.get_research_run(summary.run_id)
        assert research_run.status == ResearchRunStatus.FAILED
        assert research_run.research_card_id is None
        assert research_run.error == run.error
        stage_error = reopened.conn.execute(
            "SELECT error FROM research_stage_results "
            "WHERE research_run_id=? AND stage='A1' ORDER BY id DESC LIMIT 1",
            (summary.run_id,),
        ).fetchone()[0]
        assert stage_error == run.error
        assert reopened.list_topics(account.id)[0].status == TopicStatus.SELECTED
        assert reopened.conn.execute(
            "SELECT count(*) FROM research_cards WHERE topic_id=?", (topic.id,),
        ).fetchone()[0] == 0
    finally:
        reopened.close()


def test_sdk_response_body_marker_never_reaches_discovery_or_candidate_audit(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    client = _MappedSdkBodyErrorClient()

    discovery = _run_discovery(
        real_settings, storage, account, topic, client, run_cap_usd=10.0,
    )
    discovery_run = storage.get_run(discovery.run_id)
    discovery_research_run = storage.get_research_run(discovery.run_id)
    discovery_stage_error = storage.conn.execute(
        "SELECT error FROM research_stage_results "
        "WHERE research_run_id=? AND stage='A1' ORDER BY id DESC LIMIT 1",
        (discovery.run_id,),
    ).fetchone()[0]

    assert "ResearchInvalidRequestError(status_code=422, retryable=False)" in discovery_run.error
    assert discovery_research_run.error == discovery_run.error == discovery_stage_error
    assert client.marker not in discovery_run.error
    assert client.marker not in discovery_research_run.error
    assert client.marker not in discovery_stage_error

    extraction_run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    _run_extraction(
        real_settings, storage, account, extraction_run_id, client,
        max_attempts=1, run_cap_usd=10.0,
    )
    candidate = storage.list_source_candidates(extraction_run_id)[0]
    candidate_stage_error = storage.conn.execute(
        "SELECT error FROM research_stage_results "
        "WHERE research_run_id=? AND stage='A2' ORDER BY id DESC LIMIT 1",
        (extraction_run_id,),
    ).fetchone()[0]

    assert candidate.extraction_error is not None
    assert client.marker not in candidate.extraction_error
    assert client.marker not in candidate_stage_error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            ResearchAuthenticationError("bad credentials", status_code=401),
            "[discover_sources] ResearchAuthenticationError"
            "(status_code=401, retryable=False): bad credentials",
        ),
        (
            ResearchRateLimitError("rate limited", status_code=429),
            "[discover_sources] ResearchRateLimitError"
            "(status_code=429, retryable=True): rate limited",
        ),
        (
            ResearchUnknownProviderError("unknown provider failure"),
            "[discover_sources] ResearchUnknownProviderError"
            "(retryable=False): unknown provider failure",
        ),
        (
            ResearchError("plain domain failure"),
            "[discover_sources] ResearchError: plain domain failure",
        ),
        (
            ResearchError("truncated", stop_reason="max_tokens"),
            "[discover_sources] ResearchError(stop_reason=max_tokens): truncated",
        ),
    ],
)
def test_audit_error_formatter_preserves_safe_domain_metadata(error, expected):
    assert _format_audit_error("discover_sources", error) == expected


def test_audit_error_formatter_redacts_and_never_serializes_raw_response():
    raw_response = "PRIVATE_RAW_RESPONSE_SHOULD_NEVER_BE_PERSISTED"
    error = ResearchError(
        "authorization: Bearer secret-token; x-api-key=key-secret; "
        "api key: another-key-secret; sk-ant-example-secret " + "x" * 900,
        raw_text=raw_response,
    )

    formatted = _format_audit_error("discover_sources", error)

    assert formatted.startswith("[discover_sources] ResearchError: ")
    assert "authorization=[REDACTED]" in formatted
    assert "x-api-key=[REDACTED]" in formatted
    assert "api key=[REDACTED]" in formatted
    assert "[REDACTED]" in formatted
    assert "secret-token" not in formatted
    assert "key-secret" not in formatted
    assert "another-key-secret" not in formatted
    assert "sk-ant-example-secret" not in formatted
    assert raw_response not in formatted
    assert formatted.endswith("...")
    assert len(formatted) < 600


@pytest.mark.parametrize(
    "message",
    [
        "Bearer synthetic-secret-token",
        "bearer abc123",
        "BEARER eyJhbGciOiJIUzI1NiJ9.payload.signature",
    ],
)
def test_audit_error_formatter_redacts_standalone_bearer_tokens(message):
    formatted = _format_audit_error("discover_sources", ResearchError(message))

    assert message.split(maxsplit=1)[1] not in formatted
    assert "Bearer [REDACTED]" in formatted


def test_429_audit_keeps_type_and_records_the_single_attempt_after_reopen(
        settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    calls = []

    def rate_limited(plan, max_searches):
        calls.append(1)
        raise ResearchRateLimitError(
            "provider rate limit",
            status_code=429,
            usage=Usage(input_tokens=100, output_tokens=20),
            model="typed-provider-model",
        )

    client = AnthropicResearchClient(
        "offline", "typed-provider-model",
        discover_caller=rate_limited, max_retries=0,
    )
    summary = _run_discovery(
        real_settings, storage, account, topic, client,
        max_retries=0, run_cap_usd=10.0,
    )

    assert calls == [1]
    reopened = SqliteStorage.open(real_settings.db_path)
    try:
        usage = reopened.get_research_usage(summary.run_id)
        assert len(usage) == 1
        assert [(row.input_tokens, row.output_tokens) for row in usage] == [
            (100, 20),
        ]
        run = reopened.get_run(summary.run_id)
        research_run = reopened.get_research_run(summary.run_id)
        assert run.status == RunStatus.FAILED
        assert run.finished_at is not None
        assert run.cost_usd == pytest.approx(
            sum(row.estimated_cost_usd for row in usage))
        assert run.error == research_run.error
        assert "[discover_sources]" in run.error
        assert "ResearchRateLimitError" in run.error
        assert "status_code=429" in run.error
        assert "retryable=True" in run.error
        assert research_run.status == ResearchRunStatus.FAILED
        assert research_run.research_card_id is None
        assert reopened.list_topics(account.id)[0].status == TopicStatus.SELECTED
        assert reopened.conn.execute(
            "SELECT count(*) FROM research_cards WHERE topic_id=?", (topic.id,),
        ).fetchone()[0] == 0
    finally:
        reopened.close()


# --- 10. Brak sekretów w plikach diagnostycznych ---

def test_diagnostics_file_contains_no_secrets(settings, storage, account):
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)

    _run_extraction(real_settings, storage, account, run_id, _AlwaysFailExtractClient("good"))

    candidate = storage.list_source_candidates(run_id)[0]
    diag_path = diagnostics_dir(real_settings.data_dir, run_id) / f"A2_source_{candidate.id}_raw_response.txt"
    content = diag_path.read_text(encoding="utf-8")

    assert "ANTHROPIC_API_KEY" not in content
    assert "Authorization" not in content
    assert "Bearer" not in content
    assert "x-api-key" not in content.lower()
    assert "sk-ant" not in content


def test_no_diagnostics_written_in_dry_run(settings, storage, account):
    """dry_run=True (domyślne w fixture) -> FakeResearchClient i tak nie ma czego
    zapisać (raw_text puste w scenariuszach błędu ponad to, co jawnie ustawiono), ale
    jawnie potwierdzamy: katalog diagnostyczny w ogóle nie powstaje dla dry_run."""
    assert settings.dry_run is True
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)

    _run_extraction(settings, storage, account, run_id, _AlwaysFailExtractClient("good"))

    assert not diagnostics_dir(settings.data_dir, run_id).exists()


# --- Audyt 2026-07-12 (docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md) — testy sekcji 22, pozycje 1-2 ---

def test_real_mode_staged_pipeline_reaches_success_not_running(settings, storage, account):
    """P0-1: przed naprawą KAŻDY realny (dry_run=False) sukces — w tym cały etapowy
    przepływ A1/A2/B — kończył się terminalnym RUNNING zamiast SUCCESS."""
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    summary = _run_staged(real_settings, storage, account, topic, FakeResearchClient("good"))

    assert summary.passed
    run = storage.get_run(summary.run_id)
    assert run is not None
    assert run.status == RunStatus.SUCCESS
    assert run.status != RunStatus.RUNNING


def test_extraction_without_search_access_forces_unverified(settings, storage, account):
    """P0-2a: gdy max_web_searches_per_source<=0, karta MUSI zostać zapisana jako
    UNVERIFIED niezależnie od tego, co zwrócił model — FakeResearchClient("good") zawsze
    twierdzi VERIFIED, więc to dowodzi wymuszenia deterministycznego, nie promptowego."""
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)

    _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"),
                    max_web_searches_per_source=0)

    extracted = storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)
    assert len(extracted) == 3
    assert all(c.verification_status == SourceVerification.UNVERIFIED for c in extracted)


def test_real_mode_extraction_without_search_produces_rejected_card(settings, storage, account):
    """P0-2 end-to-end: dokładnie scenariusz, który audyt uznał za "nie dowodzący
    researchu" — ekstrakcja bez dostępu do wyszukiwania, w REALNYM trybie, musi
    zakończyć się REJECT (za mało zweryfikowanych źródeł), nawet gdy model przez całą
    drogę twierdzi VERIFIED i karta wygląda poprawnie pod każdym innym względem."""
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)

    _run_extraction(real_settings, storage, account, run_id, FakeResearchClient("good"),
                    max_web_searches_per_source=0)
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE

    summary = _run_synthesis(real_settings, storage, account, run_id, FakeResearchClient("good"))

    assert summary.card is not None       # karta i tak powstaje (zapisywana dla audytu)…
    assert not summary.passed             # …ale NIE przechodzi bramki jakości
    assert summary.recommendation == "REJECT"
    assert TOO_FEW_VERIFIED_SOURCES in summary.reasons
    _assert_run_cost_matches_research_usage(storage, run_id)


# --- Diagnostyka 2026-07-12 (run 9bbeb020) — naprawa błędu wyświetlania CLI etapu A2:
# run_source_extraction() nigdy nie ustawiał summary.model/.input_tokens/.output_tokens/
# .web_search_requests (baza była poprawna, tylko podsumowanie w pamięci/CLI było puste)
# + podniesienie domyślnego extraction_max_tokens 500 -> 1500.

def test_extraction_summary_aggregates_usage_across_sources(settings, storage, account):
    """FakeResearchClient("good").extract_source zwraca zawsze input=2500/output=180/
    web_search=1 na źródło — dla 3 źródeł suma musi być 3x, nie 0 (stary błąd)."""
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)

    summary = _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))

    assert summary.sources_extracted == 3
    assert summary.model == "dry-run-fake-research"
    assert summary.input_tokens == 2500 * 3
    assert summary.output_tokens == 180 * 3
    assert summary.web_search_requests == 1 * 3
    a2_usage = [u for u in storage.get_research_usage(run_id)
                if u.task == "research_extract"]
    assert summary.cost_usd == pytest.approx(
        sum(u.estimated_cost_usd for u in a2_usage))
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_extraction_summary_aggregation_unaffected_by_real_mode(settings, storage, account):
    """Ten sam scenariusz, ale dry_run=False — agregacja musi dać identyczne liczby
    (dry_run wpływa tylko na flagę w model_usage/budżet, nigdy na policzone tokeny)."""
    real_settings = replace(settings, dry_run=False)
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)

    summary = _run_extraction(real_settings, storage, account, run_id, FakeResearchClient("good"))

    assert summary.model == "dry-run-fake-research"
    assert summary.input_tokens == 2500 * 3
    assert summary.output_tokens == 180 * 3
    assert summary.web_search_requests == 1 * 3


def test_extraction_summary_aggregates_usage_including_failed_source(settings, storage, account):
    """Częściowa porażka (1 z 3 źródeł pada) — agregacja model/tokeny/web_search MUSI
    objąć również nieudane wywołanie, ta sama zasada co dla cost_usd (patrz
    test_raw_response_and_stop_reason_saved_on_extraction_error)."""
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    client = _NthExtractionFailsClient("good", fail_index=2)  # ostatnie wywołanie pada

    summary = _run_extraction(settings, storage, account, run_id, client)

    assert summary.sources_extracted == 2
    assert summary.sources_failed == 1
    # 2 sukcesy (input=2500/output=180/web_search=1 każdy) + 1 porażka
    # (input=17000/output=180/web_search=1, patrz _NthExtractionFailsClient).
    assert summary.input_tokens == 2500 * 2 + 17000
    assert summary.output_tokens == 180 * 3
    assert summary.web_search_requests == 3
    assert summary.model == "sonnet-real"  # ostatnie wywołanie (porażka) ustala model
    a2_usage = [u for u in storage.get_research_usage(run_id)
                if u.task == "research_extract"]
    assert summary.cost_usd == pytest.approx(
        sum(u.estimated_cost_usd for u in a2_usage))


def test_extraction_summary_partial_path_excludes_prior_stage_usage(
        settings, storage, account):
    """Podsumowanie A2 obejmuje wyłącznie wywołania A2 z bieżącej inwokacji,
    podczas gdy baza/runs zachowują kanoniczny koszt skumulowany całego runu."""
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=4)
    tracker = UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path)
    prior = tracker.record(
        run_id, "discovery-model",
        Usage(input_tokens=1000, output_tokens=100, web_search_requests=1),
        task="research_discover", dry_run=settings.dry_run,
    )

    summary = _run_extraction(
        settings, storage, account, run_id, FakeResearchClient("good"), max_sources=2)

    assert storage.get_research_run(run_id).status == ResearchRunStatus.PARTIAL
    assert summary.sources_extracted == 2
    assert summary.model == "dry-run-fake-research"
    assert summary.input_tokens == 2500 * 2
    assert summary.output_tokens == 180 * 2
    assert summary.web_search_requests == 2
    a2_usage = [u for u in storage.get_research_usage(run_id)
                if u.task == "research_extract"]
    a2_cost = sum(u.estimated_cost_usd for u in a2_usage)
    assert summary.cost_usd == pytest.approx(a2_cost)
    assert storage.get_run(run_id).cost_usd == pytest.approx(
        prior.estimated_cost_usd + a2_cost)
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_extraction_summary_keeps_existing_dry_run_accounting(
        settings, storage, account):
    """Agregacja podsumowania nie zmienia semantyki dry_run: usage jest zapisane
    jako estymacja, ale nie zwiększa realnego wydatku budżetowego."""
    assert settings.dry_run is True
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)

    summary = _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))

    a2_usage = [u for u in storage.get_research_usage(run_id)
                if u.task == "research_extract"]
    assert summary.dry_run is True
    assert summary.cost_usd > 0
    assert len(a2_usage) == 3
    assert all(u.dry_run for u in a2_usage)
    assert storage.sum_real_cost_usd("") == 0.0
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_extraction_resyncs_existing_usage_when_no_model_call_is_made(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)
    tracker = UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path)
    prior = tracker.record(
        run_id, "discovery-model",
        Usage(input_tokens=1000, output_tokens=100, web_search_requests=1),
        task="research_discover", dry_run=settings.dry_run,
    )
    storage.finish_run(run_id, RunStatus.FAILED.value, cost_usd=99.0, error="stale cache")

    summary = _run_extraction(
        settings, storage, account, run_id, FakeResearchClient("good"),
        max_sources=0, explicit_resume=True)
    resumed = _resume_staged(
        settings, storage, account, run_id, FakeResearchClient("good"), max_sources=0)

    assert summary.sources_extracted == 0
    assert resumed.sources_extracted == 0
    assert len(storage.get_research_usage(run_id)) == 1
    assert storage.get_run(run_id).cost_usd == pytest.approx(prior.estimated_cost_usd)
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_cost_is_synced_when_post_usage_stage_write_raises(
        settings, storage, account, monkeypatch):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=1)

    def fail_after_usage(*args, **kwargs):
        raise RuntimeError("stage-log write failed after usage")

    monkeypatch.setattr(storage, "add_research_stage_result", fail_after_usage)

    with pytest.raises(RuntimeError, match="stage-log write failed"):
        _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))

    assert len(storage.get_research_usage(run_id)) == 1
    _assert_run_cost_matches_research_usage(storage, run_id)


def test_extraction_and_client_defaults_use_1500_tokens():
    """Regresja: wszystkie realne źródła domyślnego limitu wyjścia etapu A2 muszą się
    zgadzać (500 -> 1500; diagnostyka kandydata id=3 zakończyła się przy 915 tokenach,
    a 500 ucinało wcześniejsze próby) — jeśli ktoś zmieni jedno miejsce i zapomni o
    pozostałych, ten test to złapie. Jednorazowe 5000 nie jest defaultem."""
    import inspect

    from app.research.anthropic_client import AnthropicResearchClient

    assert inspect.signature(AnthropicResearchClient.__init__).parameters[
        "extract_max_tokens"].default == 1500
    assert inspect.signature(run_source_extraction).parameters[
        "max_output_tokens"].default == 1500
    assert inspect.signature(run_staged_research_pipeline).parameters[
        "extraction_max_tokens"].default == 1500
    assert inspect.signature(resume_staged_research).parameters[
        "extraction_max_tokens"].default == 1500


def test_synthesis_defaults_use_measured_3000_token_limit():
    import inspect

    from app.research.anthropic_client import AnthropicResearchClient

    assert inspect.signature(AnthropicResearchClient.__init__).parameters[
        "synthesize_max_tokens"].default == 3000
    assert inspect.signature(run_synthesis_from_cards).parameters[
        "synthesize_max_tokens"].default == 3000
    assert inspect.signature(run_staged_research_pipeline).parameters[
        "synthesize_max_tokens"].default == 3000
    assert inspect.signature(resume_staged_research).parameters[
        "synthesize_max_tokens"].default == 3000
