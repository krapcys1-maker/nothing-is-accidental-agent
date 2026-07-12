"""Testy integracyjne DWUETAPOWEGO pipeline'u researchu (ADR-016, FakeResearchClient, dry_run).

Powód istnienia tej ścieżki: pierwszy realny, jednoetapowy research (2026-07-11,
temat #2 "suitcase") kosztował realnie 0.25 USD (przy szacunku 0.095 USD) i
zakończył się uciętym JSON-em. Dwuetapowy podział ma mniejsze ryzyko ucięcia i
pozwala TANIO odrzucić słaby research po etapie 1, zanim zapłacimy za etap 2.
"""
from __future__ import annotations

import pytest

from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import (
    ModelUsage,
    ResearchFlow,
    ResearchRecommendation,
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
from app.research.validation import TOO_FEW_SOURCES
from app.workflows.research.pipeline import (
    CompletedResearchExistsError,
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


def _run(settings, storage, account, topic, client, **kwargs):
    return run_two_stage_research_pipeline(
        account, topic,
        settings=settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(), **kwargs,
    )


def _seed_real_cost(storage, account, cost: float) -> None:
    storage.ensure_account(account)
    storage.create_run(Run(id="seed", account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=RunStatus.RUNNING))
    storage.add_model_usage(ModelUsage(run_id="seed", model="m",
                                       estimated_cost_usd=cost, dry_run=False))


class _CountingFake(FakeResearchClient):
    """Zlicza wywołania gather_sources/synthesize_card osobno — potrzebne do
    udowodnienia, że etap 2 jest POMIJANY przy tanim wczesnym wyjściu (bramka §7)."""

    def __init__(self, scenario: str = "good") -> None:
        super().__init__(scenario)
        self.gather_calls = 0
        self.synthesize_calls = 0

    def gather_sources(self, plan):
        self.gather_calls += 1
        return super().gather_sources(plan)

    def synthesize_card(self, plan, gathered):
        self.synthesize_calls += 1
        return super().synthesize_card(plan, gathered)


def test_good_research_proceeds_through_both_stages(settings, storage, account):
    topic = _selected_topic(storage, account)
    client = _CountingFake("good")
    summary = _run(settings, storage, account, topic, client)

    assert summary.passed
    assert summary.recommendation == ResearchRecommendation.PROCEED.value
    assert summary.sources_count == 3
    assert summary.injection_flags == 0
    assert summary.cost_usd > 0
    assert not summary.blocked and summary.error is None
    assert client.gather_calls == 1
    assert client.synthesize_calls == 1

    cards = storage.list_research_cards(account.id)
    assert len(cards) == 1
    assert len(cards[0].sources) == 3
    assert cards[0].working_thesis

    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.DRY_RUN
    assert storage.get_research_run(summary.run_id).flow == ResearchFlow.TWO_STAGE
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED


def test_two_stage_re_research_requires_force_and_force_keeps_history(settings, storage, account):
    topic = _selected_topic(storage, account)
    first = _run(settings, storage, account, topic, FakeResearchClient("good"))
    old_card_id = first.card.id
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage")
    }

    class _ForbiddenClient(FakeResearchClient):
        def gather_sources(self, plan):
            raise AssertionError("blocked re-research must not call gather_sources")

    with pytest.raises(CompletedResearchExistsError, match="--force-re-research"):
        _run(settings, storage, account, topic, _ForbiddenClient("good"))

    counts_after_block = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after_block == counts_before

    forced = _run(
        settings, storage, account, topic, FakeResearchClient("good"), force_re_research=True,
    )
    assert forced.run_id != first.run_id
    assert forced.card.id != old_card_id
    assert storage.get_research_card(old_card_id) is not None
    assert storage.get_research_run(forced.run_id).flow == ResearchFlow.TWO_STAGE
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED

    cards_before_failure = [card.id for card in storage.list_research_cards(account.id)]
    failed = _run(
        settings, storage, account, topic, FakeResearchClient("few_sources"),
        force_re_research=True,
    )
    assert not failed.passed
    assert storage.get_run(failed.run_id).status == RunStatus.FAILED
    assert storage.get_research_run(failed.run_id).status == ResearchRunStatus.PARTIAL
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED
    assert [card.id for card in storage.list_research_cards(account.id)] == cards_before_failure
    assert storage.get_research_run(first.run_id).research_card_id == old_card_id


def test_stops_after_stage_a_when_too_few_sources_and_skips_stage_b(settings, storage, account):
    """Sedno projektowe etapu 1: za mało źródeł -> REJECT natychmiast, BEZ płacenia
    za etap 2 (synthesize_card nigdy nie jest wołany — kluczowa asercja poniżej)."""
    topic = _selected_topic(storage, account)
    client = _CountingFake("few_sources")
    summary = _run(settings, storage, account, topic, client)

    assert not summary.passed
    assert summary.recommendation == ResearchRecommendation.REJECT.value
    assert TOO_FEW_SOURCES in summary.reasons
    assert client.gather_calls == 1
    assert client.synthesize_calls == 0                    # <- etap 2 pominięty
    assert summary.cost_usd > 0                             # etap 1 i tak kosztował
    assert storage.list_research_cards(account.id) == []    # brak karty — nic do syntezy

    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.FAILED


def test_prompt_injection_neutralized_in_stage_a(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, FakeResearchClient("injection"))

    assert summary.injection_flags >= 1
    assert summary.recommendation == ResearchRecommendation.PROCEED.value
    titles = [s.title for s in summary.card.sources]
    assert any("REDACTED-INSTRUCTION" in t for t in titles)
    assert not any("IGNORE ALL PREVIOUS INSTRUCTIONS" in t for t in titles)


def test_budget_blocks_before_stage_a_client_call(settings, storage, account):
    topic = _selected_topic(storage, account)
    _seed_real_cost(storage, account, cost=40.0)  # == limit miesięczny

    client = _CountingFake("good")
    summary = _run(settings, storage, account, topic, client)

    assert summary.blocked
    assert summary.block_code == "BUDGET_MONTHLY_REACHED"
    assert client.gather_calls == 0
    assert client.synthesize_calls == 0
    assert storage.list_research_cards(account.id) == []


def test_real_usage_recorded_when_stage_a_parse_fails(settings, storage, account):
    """Ta sama klasa błędu co w wersji jednoetapowej (docs/ERRORS_AND_FAILURES.md,
    2026-07-11) — musi być niemożliwa do powtórzenia w etapie 1: realny `usage`
    z udanego wywołania API nie może zniknąć z księgowości."""

    class _BrokenGatherClient:
        model = "sonnet-real"

        def gather_sources(self, plan: ResearchPlan):
            raise ResearchParseError(
                "Unterminated string in stage A...",
                usage=Usage(input_tokens=2000, output_tokens=1200, web_search_requests=4),
                model=self.model,
            )

        def synthesize_card(self, plan, gathered):  # pragma: no cover
            raise AssertionError("synthesize_card nie powinien być wołany po błędzie etapu 1")

    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, _BrokenGatherClient())

    assert summary.error is not None
    assert summary.cost_usd > 0
    assert summary.input_tokens == 2000
    assert summary.output_tokens == 1200
    assert summary.web_search_requests == 4

    run = storage.get_run(summary.run_id)
    assert run is not None and run.cost_usd > 0


def test_real_usage_recorded_when_stage_b_parse_fails(settings, storage, account):
    """Etap 1 się udaje (kosztuje), etap 2 pada z błędem parsowania — koszt OBU
    etapów musi zostać zaksięgowany (nie tylko etapu 1)."""

    class _BrokenSynthesizeClient(FakeResearchClient):
        def synthesize_card(self, plan, gathered: SourceGatheringResult):
            raise ResearchParseError(
                "Unterminated string in stage B...",
                usage=Usage(input_tokens=1500, output_tokens=2200, web_search_requests=0),
                model="sonnet-real",
            )

    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, _BrokenSynthesizeClient("good"))

    assert summary.error is not None
    assert summary.cost_usd > 0  # etap 1 (fake "good") + etap 2 (1500/2200 tokenów) razem
    assert storage.list_research_cards(account.id) == []

    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.FAILED and run.cost_usd > 0
    assert "[synthesize_card]" in (run.error or "")


def test_research_card_isolated_per_account(settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))
    assert storage.list_research_cards("other_account") == []
