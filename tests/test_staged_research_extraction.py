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
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.anthropic_client import _parse_discovery_candidates_jsonl
from app.research.base import ResearchParseError
from app.research.diagnostics import diagnostics_dir
from app.research.fake_client import FakeResearchClient
from app.research.validation import TOO_FEW_VERIFIED_SOURCES
from app.workflows.research.pipeline import (
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
        status=ResearchRunStatus.DISCOVERY_PENDING,
    ))
    storage.create_source_candidates(run_id, [
        SourceCandidateRecord(research_run_id=run_id, url=f"https://example.org/source-{i}",
                              title=f"Candidate source {i}")
        for i in range(n)
    ])
    return run_id


def _run_discovery(settings, storage, account, topic, client, **kwargs):
    return run_source_discovery(
        account, topic, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _run_extraction(settings, storage, account, run_id, client, **kwargs):
    return run_source_extraction(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _run_synthesis(settings, storage, account, run_id, client, **kwargs):
    return run_synthesis_from_cards(
        run_id, account, settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs)


def _run_staged(settings, storage, account, topic, client, **kwargs):
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
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.research_card_id == summary.card.id

    extracted = storage.list_source_candidates(summary.run_id, SourceCandidateStatus.EXTRACTED)
    assert len(extracted) == 3


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


# --- 7. Ponowienie etapu B (synthesis) bez web search, przez pełny dispatcher wznowienia ---

def test_resume_synthesis_never_calls_discovery_or_extraction(settings, storage, account):
    topic = _selected_topic(storage, account)
    run_id = _seeded_run_with_candidates(storage, account, topic, n=3)
    _run_extraction(settings, storage, account, run_id, FakeResearchClient("good"))
    assert storage.get_research_run(run_id).status == ResearchRunStatus.SOURCES_COMPLETE

    broken = _BrokenSynthesizeFromCardsOnceClient("good")
    summary1 = _run_synthesis(settings, storage, account, run_id, broken)
    assert summary1.error is not None
    assert summary1.cost_usd > 0                          # 9. usage/koszt zachowane mimo błędu B
    research_run = storage.get_research_run(run_id)
    assert research_run.status == ResearchRunStatus.SOURCES_COMPLETE  # WRACA, nie PARTIAL/FAILED
    assert len(storage.list_source_candidates(run_id, SourceCandidateStatus.EXTRACTED)) == 3

    resume_client = _DiscoveryAndExtractionForbiddenClient("good")
    summary2 = _resume_staged(settings, storage, account, run_id, resume_client)

    assert summary2.error is None
    assert summary2.card is not None
    research_run2 = storage.get_research_run(run_id)
    assert research_run2.status == ResearchRunStatus.COMPLETE
    assert research_run2.research_card_id is not None


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
