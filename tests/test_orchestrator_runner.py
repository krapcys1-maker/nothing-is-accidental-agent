"""Testy bezpieczeństwa app/orchestrator/runner.py (P0-3, docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.llm.usage_tracker import UsageTracker
from app.models import (
    ModelUsage,
    ResearchCard,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.orchestrator import runner
from app.orchestrator.runner import run_research
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.fake_client import FakeResearchClient
from app.ports.storage import ResearchTopicIntegrityError
from app.workflows.research.pipeline import CompletedResearchExistsError, run_research_pipeline


def test_run_research_force_real_is_blocked():
    """P0-3: 'python -m app.main run-research --real' (force_real=True) wołał
    przestarzały, jednoetapowy pipeline przez klienta zbudowanego BEZ max_web_searches
    (brak max_uses -> nieograniczona liczba web searchy w jednym wywołaniu) i bez capu
    kosztu per-run. Musi się zatrzymać PRZED zbudowaniem czegokolwiek (nawet przed
    load_settings()), nie tylko przed samym wywołaniem API."""
    with pytest.raises(RuntimeError, match="run_capped_research"):
        run_research(topic_id=1, force_real=True)


def _selected_topic(storage, account):
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title="Why fares move", question="Why?", score=90.0,
        status=TopicStatus.SELECTED,
    ))


def _complete_research(settings, storage, account, topic):
    return run_research_pipeline(
        account, topic, settings=settings, storage=storage, research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )


def test_runner_blocks_completed_topic_before_constructing_client(
        monkeypatch, settings, storage, account):
    topic = _selected_topic(storage, account)
    _complete_research(settings, storage, account, topic)
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage")
    }

    def forbidden_client(*args, **kwargs):
        raise AssertionError("runner must not construct a client before the re-research guard")

    monkeypatch.setattr(runner, "_build_research_client", forbidden_client)

    with pytest.raises(CompletedResearchExistsError, match="--force-re-research"):
        runner.run_research(topic_id=topic.id, settings=settings)

    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before


def test_runner_force_still_reaches_budget_gate_after_client_construction(
        monkeypatch, settings, storage, account):
    topic = _selected_topic(storage, account)
    _complete_research(settings, storage, account, topic)
    storage.create_run(Run(
        id="budget-seed", account_id=account.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.RUNNING,
    ))
    storage.add_model_usage(ModelUsage(
        run_id="budget-seed", model="fake", task="research", dry_run=False,
        estimated_cost_usd=settings.max_monthly_cost_usd,
    ))
    built = []

    def fake_client(*args, **kwargs):
        built.append(True)
        return FakeResearchClient("good")

    monkeypatch.setattr(runner, "_build_research_client", fake_client)

    summary = runner.run_research(
        topic_id=topic.id, settings=settings, force_re_research=True,
    )

    assert built == [True]
    assert summary.blocked
    assert summary.block_code == "BUDGET_MONTHLY_REACHED"


@pytest.mark.parametrize("corruption", ["used_without_complete", "missing_card", "wrong_topic", "wrong_account"])
def test_runner_force_cannot_bypass_corrupt_topic_state_before_client_or_mutation(
        monkeypatch, settings, storage, account, corruption):
    topic = _selected_topic(storage, account)
    if corruption == "used_without_complete":
        storage.conn.execute(
            "UPDATE topics SET status=? WHERE id=?", (TopicStatus.USED.value, topic.id),
        )
    else:
        run_id = "corrupt-complete"
        storage.create_run(Run(
            id=run_id, account_id=account.id, workflow=WorkflowType.RESEARCH,
            status=RunStatus.SUCCESS,
        ))
        storage.create_research_run(ResearchRun(
            id=run_id, account_id=account.id, topic_id=int(topic.id),
            flow=ResearchFlow.SINGLE,
        ))
        card_id = None
        if corruption in ("wrong_topic", "wrong_account"):
            card_account = account
            if corruption == "wrong_account":
                card_account = account.model_copy(
                    update={"id": "other-account", "display_name": "Other"},
                )
            wrong_topic = _selected_topic(storage, card_account)
            card = storage.add_research_card(ResearchCard(
                topic_id=int(wrong_topic.id), question="Wrong?", working_thesis="Wrong",
            ))
            card_id = card.id
        storage.conn.execute(
            "UPDATE research_runs SET status=?, research_card_id=? WHERE id=?",
            (ResearchRunStatus.COMPLETE.value, card_id, run_id),
        )
    storage.conn.commit()
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage", "research_cards")
    }

    def forbidden_client(*args, **kwargs):
        raise AssertionError("integrity failure must precede client construction")

    monkeypatch.setattr(runner, "_build_research_client", forbidden_client)
    with pytest.raises(ResearchTopicIntegrityError):
        runner.run_research(
            topic_id=topic.id, settings=settings, force_re_research=True,
        )

    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before


def test_runner_force_cannot_cross_account_before_client_or_mutation(
        monkeypatch, settings, storage, account):
    topic = _selected_topic(storage, account)
    other = account.model_copy(update={"id": "other-account", "display_name": "Other"})
    other_settings = replace(settings, accounts={account.id: account, other.id: other})
    counts_before = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in ("runs", "research_runs", "model_usage", "research_cards")
    }

    def forbidden_client(*args, **kwargs):
        raise AssertionError("account isolation must precede client construction")

    monkeypatch.setattr(runner, "_build_research_client", forbidden_client)
    with pytest.raises(RuntimeError, match="Nie znaleziono tematu"):
        runner.run_research(
            topic_id=topic.id, account_id=other.id, settings=other_settings,
            force_re_research=True,
        )
    counts_after = {
        table: storage.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in counts_before
    }
    assert counts_after == counts_before
