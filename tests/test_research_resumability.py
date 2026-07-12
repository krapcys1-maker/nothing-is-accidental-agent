"""Testy odporności/wznawialności dwuetapowego researchu (stabilizacja Research Pipeline,
2026-07-12). Powód: pierwszy realny research (jednoetapowy, 2026-07-11) tracił WSZYSTKO
przy błędzie finalnego JSON-a — łącznie z realnie opłaconymi wynikami wyszukiwania.
Te testy dowodzą, że po zapisaniu etapu 1 (`research_sources`) źródła przeżywają:
- błąd/ucięcie JSON-a w etapie 2,
- konieczność ponowienia WYŁĄCZNIE etapu 2 (bez nowego web search),
- pełny restart procesu (nowe instancje PolicyEngine/UsageTracker/notifiera).
"""
from __future__ import annotations

from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import (
    ModelUsage,
    ResearchFlow,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.base import ResearchParseError, ResearchPlan, SourceGatheringResult
from app.research.fake_client import FakeResearchClient
from app.workflows.research.pipeline import (
    resume_research_stage_b,
    run_two_stage_research_pipeline,
)


def _selected_topic(storage, account) -> Topic:
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Why airline ticket prices change every few hours",
        question="What pricing system makes fares move so often?",
        score=89.5, status=TopicStatus.SELECTED,
    ))


def _run_fresh(settings, storage, account, topic, client):
    return run_two_stage_research_pipeline(
        account, topic,
        settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def _resume(settings, storage, account, research_run_id, client):
    """Wywołanie z CAŁKOWICIE NOWYMI instancjami PolicyEngine/UsageTracker/notifiera —
    symuluje prawdziwy restart procesu, nie tylko drugie wywołanie w tym samym teście."""
    return resume_research_stage_b(
        research_run_id, account,
        settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def _seed_real_cost(storage, account, cost: float) -> None:
    storage.ensure_account(account)
    storage.create_run(Run(id="seed", account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING))
    storage.add_model_usage(ModelUsage(run_id="seed", model="m",
                                       estimated_cost_usd=cost, dry_run=False))


class _BrokenSynthesizeOnceClient(FakeResearchClient):
    """Etap 1 zawsze udany (dziedziczy dobre gather_sources). Etap 2 pada za KAŻDYM
    razem, dopóki `should_fail=False` nie zostanie ustawione z zewnątrz — pozwala
    zbudować scenariusz PARTIAL do testów wznowienia."""

    def __init__(self, scenario: str = "good") -> None:
        super().__init__(scenario)
        self.should_fail = True
        self.synthesize_calls = 0

    def synthesize_card(self, plan, gathered):
        self.synthesize_calls += 1
        if self.should_fail:
            raise ResearchParseError(
                "Unterminated string in stage B...",
                usage=Usage(input_tokens=1500, output_tokens=2200, web_search_requests=0),
                model="sonnet-real",
            )
        return super().synthesize_card(plan, gathered)


class _GatherForbiddenClient(FakeResearchClient):
    """Jeśli gather_sources zostanie wywołany, test MUSI polec — dowód, że wznowienie
    nigdy nie robi ponownego web search. Liczy też wywołania synthesize_card, żeby
    testy mogły potwierdzić, że NIE zapłaciliśmy za etap 2, gdy nie powinniśmy."""

    def __init__(self, scenario: str = "good") -> None:
        super().__init__(scenario)
        self.synthesize_calls = 0

    def gather_sources(self, plan):
        raise AssertionError("gather_sources NIE POWINIEN być wołany podczas wznowienia etapu 2!")

    def synthesize_card(self, plan, gathered):
        self.synthesize_calls += 1
        return super().synthesize_card(plan, gathered)


# --- 1. Poprawny etap A: research_runs + research_sources trwałe po samym etapie 1 ---

def test_stage_a_success_persists_research_run_and_sources(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = _BrokenSynthesizeOnceClient("good")  # etap 1 dobry, etap 2 celowo padnie
    summary = _run_fresh(settings, storage, account, topic, client)

    research_run = storage.get_research_run(summary.run_id)
    assert research_run is not None
    assert research_run.flow == ResearchFlow.TWO_STAGE
    assert research_run.status == ResearchRunStatus.PARTIAL  # etap 2 padł, ale etap 1 trwały
    assert research_run.stage_a_completed_at is not None
    assert research_run.stage_b_completed_at is None

    sources = storage.list_research_sources(summary.run_id)
    assert len(sources) == 3  # tyle daje FakeResearchClient("good")


# --- 2. Poprawny etap B: COMPLETE + research_card_id ---

def test_stage_b_success_reaches_complete(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = FakeResearchClient("good")
    summary = _run_fresh(settings, storage, account, topic, client)

    research_run = storage.get_research_run(summary.run_id)
    assert research_run is not None
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.stage_a_completed_at is not None
    assert research_run.stage_b_completed_at is not None
    assert research_run.research_card_id == summary.card.id
    assert research_run.total_cost_usd == summary.cost_usd > 0


# --- 3 + 4. Ucięty JSON w etapie B: PARTIAL + źródła zachowane ---

def test_truncated_json_stage_b_sets_partial_and_keeps_sources(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = _BrokenSynthesizeOnceClient("good")
    summary = _run_fresh(settings, storage, account, topic, client)

    assert summary.error is not None
    research_run = storage.get_research_run(summary.run_id)
    assert research_run.status == ResearchRunStatus.PARTIAL
    assert research_run.error is not None and "synthesize_card" in research_run.error

    # Źródła NIETKNIĘTE mimo błędu etapu 2 — to jest sedno odporności.
    sources = storage.list_research_sources(summary.run_id)
    assert len(sources) == 3
    assert all(s.url for s in sources)


# --- 5 + 10. Wznowienie WYŁĄCZNIE etapu 2, bez web search, po symulowanym restarcie ---

def test_resume_stage_b_never_calls_gather_sources_and_survives_restart(settings, storage, account):
    topic = _selected_topic(storage, account)
    broken = _BrokenSynthesizeOnceClient("good")
    summary1 = _run_fresh(settings, storage, account, topic, broken)
    assert storage.get_research_run(summary1.run_id).status == ResearchRunStatus.PARTIAL

    # "Restart": nowy klient (gather_sources rzuca, jeśli wywołany), nowe instancje
    # Policy/UsageTracker/notifiera (patrz _resume) — research_run_id to JEDYNA łączność
    # ze starym procesem, cała reszta stanu wraca z bazy.
    resume_client = _GatherForbiddenClient("good")
    summary2 = _resume(settings, storage, account, summary1.run_id, resume_client)

    assert summary2.error is None
    assert summary2.card is not None
    assert summary2.sources_count == 3

    research_run = storage.get_research_run(summary1.run_id)
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.research_card_id is not None


# --- 6. Realny usage zachowany przy błędzie (już etap 2, ale w nowej ścieżce) ---

def test_real_usage_recorded_when_stage_b_fails_during_fresh_run(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = _BrokenSynthesizeOnceClient("good")
    summary = _run_fresh(settings, storage, account, topic, client)

    assert summary.cost_usd > 0  # koszt etapu 1 (fake) + etapu 2 (1500/2200 tokenów)
    usage_rows = storage.get_research_usage(summary.run_id)
    tasks = {u.task for u in usage_rows}
    assert "research_gather" in tasks
    assert "research_synthesize" in tasks


# --- 7. Poprawne łączenie kosztów obu etapów (świeży run + wznowienie) ---

def test_total_cost_combines_stage_a_and_stage_b_across_resume(settings, storage, account):
    topic = _selected_topic(storage, account)
    broken = _BrokenSynthesizeOnceClient("good")
    summary1 = _run_fresh(settings, storage, account, topic, broken)
    cost_after_stage_a_and_failed_b = summary1.cost_usd
    assert cost_after_stage_a_and_failed_b > 0

    resume_client = FakeResearchClient("good")
    summary2 = _resume(settings, storage, account, summary1.run_id, resume_client)

    # Koszt końcowy = etap1 + nieudana próba etapu2 (summary1) + udana próba etapu2 (summary2's own stage B).
    research_run = storage.get_research_run(summary1.run_id)
    usage_rows = storage.get_research_usage(summary1.run_id)
    assert sum(u.estimated_cost_usd for u in usage_rows) == research_run.total_cost_usd
    assert research_run.total_cost_usd > cost_after_stage_a_and_failed_b
    assert summary2.cost_usd == research_run.total_cost_usd


# --- 8. Blokada budżetowa: przed etapem A i przed wznowieniem etapu B ---

def test_budget_blocks_before_stage_a_no_sources_created(settings, storage, account):
    topic = _selected_topic(storage, account)
    _seed_real_cost(storage, account, cost=40.0)  # == limit miesięczny

    client = FakeResearchClient("good")
    summary = _run_fresh(settings, storage, account, topic, client)

    assert summary.blocked
    assert summary.block_code == "BUDGET_MONTHLY_REACHED"
    # research_runs nawet nie powstał — blokada jest PRZED create_run.
    assert storage.list_research_sources(summary.run_id or "brak") == []


def test_budget_blocks_before_resume_stage_b(settings, storage, account):
    topic = _selected_topic(storage, account)
    broken = _BrokenSynthesizeOnceClient("good")
    summary1 = _run_fresh(settings, storage, account, topic, broken)
    assert storage.get_research_run(summary1.run_id).status == ResearchRunStatus.PARTIAL

    _seed_real_cost(storage, account, cost=40.0)  # wyczerpujemy budżet PO etapie 1

    resume_client = _GatherForbiddenClient("good")  # nie powinien być wołany w ogóle
    summary2 = _resume(settings, storage, account, summary1.run_id, resume_client)

    assert summary2.blocked
    assert summary2.block_code == "BUDGET_MONTHLY_REACHED"
    # Status zostaje PARTIAL — blokada budżetowa nie psuje ani nie zmienia zapisanych źródeł.
    assert storage.get_research_run(summary1.run_id).status == ResearchRunStatus.PARTIAL
    assert len(storage.list_research_sources(summary1.run_id)) == 3


# --- 9. Za mało źródeł: etap 2 odmawia (bo i tak nic by nie naprawił), bez wołania API ---

def test_resume_refuses_when_still_too_few_sources(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = FakeResearchClient("few_sources")  # tylko 2 źródła < research_min_sources (3)
    summary = _run_fresh(settings, storage, account, topic, client)

    research_run = storage.get_research_run(summary.run_id)
    assert research_run.status == ResearchRunStatus.PARTIAL
    assert len(storage.list_research_sources(summary.run_id)) == 2

    resume_client = _GatherForbiddenClient("good")
    summary2 = _resume(settings, storage, account, summary.run_id, resume_client)

    assert summary2.error is None and summary2.card is None
    assert "TOO_FEW_SOURCES" in summary2.reasons
    assert resume_client.synthesize_calls == 0  # nigdy nie zapłaciliśmy za etap 2


def test_resume_raises_for_unknown_or_wrong_status_run(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = FakeResearchClient("good")
    summary = _run_fresh(settings, storage, account, topic, client)  # -> COMPLETE

    import pytest
    with pytest.raises(ValueError):
        _resume(settings, storage, account, "nieistniejacy-run-id", client)
    with pytest.raises(ValueError):
        # COMPLETE nie jest wznawialne (nie ma czego wznawiać — już gotowe).
        _resume(settings, storage, account, summary.run_id, client)
