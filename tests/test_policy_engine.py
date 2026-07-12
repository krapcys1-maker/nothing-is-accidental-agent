"""Testy Policy Engine: kill-switch, aktywność konta, budżet (miesięczny nadrzędny), progi."""
from __future__ import annotations

from dataclasses import replace

from app.models import ModelUsage, Run, RunStatus, TopicStatus, WorkflowType
from app.policies.policy_engine import PolicyEngine


def _seed_real_cost(storage, account, cost: float) -> None:
    storage.ensure_account(account)
    storage.create_run(Run(id="seed", account_id=account.id,
                           workflow=WorkflowType.TOPIC, status=RunStatus.RUNNING))
    storage.add_model_usage(ModelUsage(run_id="seed", model="m",
                                       estimated_cost_usd=cost, dry_run=False))


def test_kill_switch_blocks(settings, storage, account):
    engine = PolicyEngine(replace(settings, kill_switch=True), storage)
    decision = engine.check_can_run(account)
    assert not decision.allowed
    assert decision.code == "KILL_SWITCH"


def test_inactive_account_blocks(settings, storage, account):
    engine = PolicyEngine(settings, storage)
    decision = engine.check_can_run(account.model_copy(update={"active": False}))
    assert not decision.allowed
    assert decision.code == "ACCOUNT_INACTIVE"


def test_active_account_allowed(settings, storage, account):
    engine = PolicyEngine(settings, storage)
    assert engine.check_can_run(account).allowed


def test_monthly_limit_has_priority(settings, storage, account):
    _seed_real_cost(storage, account, cost=40.0)  # == limit miesięczny
    engine = PolicyEngine(settings, storage)
    decision = engine.check_budget(0.01)
    assert not decision.allowed
    assert decision.code == "BUDGET_MONTHLY_REACHED"


def test_daily_limit_blocks_within_month(settings, storage, account):
    _seed_real_cost(storage, account, cost=1.99)  # dziś, poniżej limitu miesięcznego
    engine = PolicyEngine(settings, storage)
    decision = engine.check_budget(0.05)  # 1.99 + 0.05 > 2.00
    assert not decision.allowed
    assert decision.code == "BUDGET_DAILY_EXCEEDED"


def test_budget_within_limits_allowed(settings, storage, account):
    _seed_real_cost(storage, account, cost=0.10)
    engine = PolicyEngine(settings, storage)
    assert engine.check_budget(0.05).allowed


def test_decide_topic_status_thresholds(settings, storage):
    engine = PolicyEngine(settings, storage)
    assert engine.decide_topic_status(80.0) == TopicStatus.SELECTED
    assert engine.decide_topic_status(70.0) == TopicStatus.SCORED
    assert engine.decide_topic_status(60.0) == TopicStatus.REJECTED
