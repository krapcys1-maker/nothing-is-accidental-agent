"""Testy integracyjne pipeline researchu (FakeResearchClient, dry_run)."""
from __future__ import annotations

from dataclasses import replace

import pytest

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
from app.research.fake_client import FakeResearchClient
from app.research.base import ResearchError
from app.research.validation import TOO_FEW_SOURCES
from app.workflows.research.pipeline import (
    CompletedResearchExistsError,
    run_research_pipeline,
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
    return run_research_pipeline(
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


def test_good_research_proceeds_and_persists(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, FakeResearchClient("good"))

    assert summary.passed
    assert summary.recommendation == ResearchRecommendation.PROCEED.value
    assert summary.sources_count == 3
    assert summary.injection_flags == 0
    assert summary.cost_usd > 0
    assert not summary.blocked and summary.error is None

    cards = storage.list_research_cards(account.id)
    assert len(cards) == 1
    assert len(cards[0].sources) == 3
    assert cards[0].working_thesis
    run = storage.get_run(summary.run_id)
    assert run is not None and run.status == RunStatus.DRY_RUN
    research_run = storage.get_research_run(summary.run_id)
    assert research_run is not None
    assert research_run.flow == ResearchFlow.SINGLE
    assert research_run.status == ResearchRunStatus.COMPLETE
    assert research_run.stage_b_completed_at is None
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED


def test_completed_card_blocks_fresh_research_without_explicit_override(
        settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))

    class _ForbiddenClient(FakeResearchClient):
        def __init__(self):
            super().__init__("good")
            self.calls = 0

        def run_research(self, plan):
            self.calls += 1
            return super().run_research(plan)

    forbidden = _ForbiddenClient()
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage")
    }
    with pytest.raises(CompletedResearchExistsError, match="--force-re-research"):
        _run(settings, storage, account, topic, forbidden)

    assert forbidden.calls == 0
    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before
    assert len(storage.list_research_cards(account.id)) == 1
    assert len(storage.list_topics(account.id)) == 1


def test_explicit_override_allows_new_research_but_keeps_topic_used(settings, storage, account):
    topic = _selected_topic(storage, account)
    first = _run(settings, storage, account, topic, FakeResearchClient("good"))

    summary = _run(
        settings, storage, account, topic, FakeResearchClient("good"),
        force_re_research=True,
    )

    assert summary.passed
    assert summary.run_id != first.run_id
    assert storage.get_research_card(first.card.id) is not None
    assert len(storage.list_research_cards(account.id)) == 2
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED

    class _FailingSingleClient(FakeResearchClient):
        def run_research(self, plan):
            raise ResearchError("forced single failure")

    cards_before_failure = [card.id for card in storage.list_research_cards(account.id)]
    failed = _run(
        settings, storage, account, topic, _FailingSingleClient("good"),
        force_re_research=True,
    )
    assert failed.error == "forced single failure"
    assert storage.get_run(failed.run_id).status == RunStatus.FAILED
    assert storage.get_research_run(failed.run_id).status == ResearchRunStatus.FAILED
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED
    assert [card.id for card in storage.list_research_cards(account.id)] == cards_before_failure
    assert storage.get_research_run(first.run_id).research_card_id == first.card.id


def test_force_re_research_keeps_budget_gate_and_topic_used(settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))
    _seed_real_cost(storage, account, cost=40.0)

    class _Counting(FakeResearchClient):
        def __init__(self):
            super().__init__("good")
            self.calls = 0

        def run_research(self, plan):
            self.calls += 1
            return super().run_research(plan)

    client = _Counting()
    summary = _run(
        settings, storage, account, topic, client, force_re_research=True,
    )
    assert summary.blocked
    assert summary.block_code == "BUDGET_MONTHLY_REACHED"
    assert client.calls == 0
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED


def test_force_re_research_keeps_kill_switch_gate_and_topic_used(settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))

    class _ForbiddenClient(FakeResearchClient):
        def run_research(self, plan):
            raise AssertionError("kill switch must block before the model call")

    summary = _run(
        replace(settings, kill_switch=True), storage, account, topic, _ForbiddenClient("good"),
        force_re_research=True,
    )
    assert summary.blocked
    assert summary.block_code == "KILL_SWITCH"
    assert storage.list_topics(account.id)[0].status == TopicStatus.USED


def test_cost_and_sources_saved(settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))
    row = storage.conn.execute(
        "SELECT web_search_requests, dry_run FROM model_usage WHERE task='research'"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["web_search_requests"] == 4
    assert row["dry_run"] == 1
    card = storage.list_research_cards(account.id)[0]
    assert all(s.source_type is not None for s in card.sources)


def test_prompt_injection_is_neutralized_not_followed(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, FakeResearchClient("injection"))

    assert summary.injection_flags >= 1
    # decyzja NIE zmienia się pod wpływem wstrzykniętej instrukcji
    assert summary.recommendation == ResearchRecommendation.PROCEED.value
    assert summary.card.confidence_score == 0.78
    titles = [s.title for s in summary.card.sources]
    assert any("REDACTED-INSTRUCTION" in t for t in titles)
    assert not any("IGNORE ALL PREVIOUS INSTRUCTIONS" in t for t in titles)


def test_budget_blocks_before_client_call(settings, storage, account):
    topic = _selected_topic(storage, account)
    _seed_real_cost(storage, account, cost=40.0)  # == limit miesięczny

    class _Counting(FakeResearchClient):
        def __init__(self):
            super().__init__("good")
            self.calls = 0

        def run_research(self, plan):
            self.calls += 1
            return super().run_research(plan)

    client = _Counting()
    summary = _run(settings, storage, account, topic, client)
    assert summary.blocked
    assert summary.block_code == "BUDGET_MONTHLY_REACHED"
    assert client.calls == 0
    assert storage.list_research_cards(account.id) == []


def test_too_few_sources_rejected_but_persisted(settings, storage, account):
    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, FakeResearchClient("few_sources"))
    assert not summary.passed
    assert summary.recommendation == ResearchRecommendation.REJECT.value
    assert TOO_FEW_SOURCES in summary.reasons
    # karta zapisana mimo odrzucenia (audyt)
    assert len(storage.list_research_cards(account.id)) == 1


def test_research_card_isolated_per_account(settings, storage, account):
    topic = _selected_topic(storage, account)
    _run(settings, storage, account, topic, FakeResearchClient("good"))
    assert storage.list_research_cards("other_account") == []


def test_real_usage_recorded_even_when_parse_fails(settings, storage, account):
    """Regresja: znaleziono na pierwszym realnym runie (2026-07-11) — API odpowiedziało
    (realny, płatny koszt), ale JSON był ucięty; koszt NIE MOŻE zniknąć z księgowości."""
    from app.llm.base import Usage
    from app.research.base import ResearchParseError, ResearchPlan

    class _BrokenJsonClient:
        model = "sonnet-real"

        def run_research(self, plan: ResearchPlan):
            exc = ResearchParseError(
                "Unterminated string...",
                usage=Usage(input_tokens=4000, output_tokens=3000, web_search_requests=6),
                model=self.model,
            )
            raise exc

    topic = _selected_topic(storage, account)
    summary = _run(settings, storage, account, topic, _BrokenJsonClient())

    assert summary.error is not None
    assert summary.cost_usd > 0  # <- to jest sedno regresji: koszt NIE jest zerem
    assert summary.input_tokens == 4000
    assert summary.output_tokens == 3000
    assert summary.web_search_requests == 6
    assert summary.model == "sonnet-real"

    run = storage.get_run(summary.run_id)
    assert run is not None and run.cost_usd > 0

    row = storage.conn.execute(
        "SELECT estimated_cost_usd, dry_run FROM model_usage WHERE task='research'"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row["estimated_cost_usd"] > 0
