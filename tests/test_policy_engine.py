"""Testy Policy Engine: kill-switch, aktywność konta, budżet (miesięczny nadrzędny), progi."""
from __future__ import annotations

from dataclasses import replace

import pytest

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


def test_run_budget_allows_below_and_exactly_at_cap(settings, storage, account):
    engine = PolicyEngine(settings, storage)
    assert engine.check_run_budget(0.49, 0.50, account=account).allowed
    assert engine.check_run_budget(0.50, 0.50, account=account).allowed


def test_run_budget_denies_above_cap(settings, storage, account):
    decision = PolicyEngine(settings, storage).check_run_budget(0.51, 0.50, account=account)
    assert not decision.allowed
    assert decision.code == "RUN_CAP_EXCEEDED"


def test_run_budget_rejects_negative_and_nonfinite_values(settings, storage, account):
    engine = PolicyEngine(settings, storage)
    for estimated, cap, current in [(-0.01, 1.0, 0.0), (0.1, -1.0, 0.0),
                                    (float("nan"), 1.0, 0.0), (0.1, 1.0, -0.1)]:
        decision = engine.check_run_budget(
            estimated, cap, current_run_cost=current, account=account)
        assert not decision.allowed


def test_zero_cap_allows_only_zero_projection(settings, storage, account):
    engine = PolicyEngine(settings, storage)
    assert engine.check_run_budget(0.0, 0.0, account=account).allowed
    assert engine.check_run_budget(0.001, 0.0, account=account).code == "RUN_CAP_EXCEEDED"


def test_current_run_usage_is_not_double_counted_globally(settings, storage, account):
    _seed_real_cost(storage, account, cost=1.90)
    engine = PolicyEngine(settings, storage)
    # Global spend already includes current=1.90; only upcoming 0.05 is added.
    decision = engine.check_run_budget(
        1.95, 2.00, current_run_cost=1.90, account=account)
    assert decision.allowed


def test_dry_run_usage_does_not_consume_real_budget(settings, storage, account):
    storage.ensure_account(account)
    storage.create_run(Run(id="dry", account_id=account.id,
                           workflow=WorkflowType.RESEARCH, status=RunStatus.DRY_RUN))
    storage.add_model_usage(ModelUsage(
        run_id="dry", model="m", estimated_cost_usd=100.0, dry_run=True))
    decision = PolicyEngine(settings, storage).check_run_budget(0.10, 0.50, account=account)
    assert decision.allowed


def test_run_budget_preserves_monthly_priority(settings, storage, account):
    _seed_real_cost(storage, account, cost=40.0)
    decision = PolicyEngine(settings, storage).check_run_budget(0.01, 0.0, account=account)
    assert decision.code == "BUDGET_MONTHLY_REACHED"


def test_run_budget_checks_kill_switch(settings, storage, account):
    decision = PolicyEngine(replace(settings, kill_switch=True), storage).check_run_budget(
        0.01, 1.0, account=account)
    assert decision.code == "KILL_SWITCH"


@pytest.mark.parametrize("bad_limit", [float("nan"), float("inf")])
def test_run_budget_rejects_nonfinite_configured_limits(
        settings, storage, account, bad_limit):
    broken = replace(
        settings, max_daily_cost_usd=bad_limit, max_monthly_cost_usd=bad_limit)
    decision = PolicyEngine(broken, storage).check_run_budget(0.10, 0.50, account=account)
    assert not decision.allowed
    assert decision.code == "BUDGET_INVALID_STATE"


@pytest.mark.parametrize("bad_spent", [float("nan"), float("inf"), -0.01])
def test_run_budget_rejects_invalid_storage_totals(
        settings, storage, account, monkeypatch, bad_spent):
    monkeypatch.setattr(storage, "sum_real_cost_usd", lambda prefix: bad_spent)
    decision = PolicyEngine(settings, storage).check_run_budget(0.10, 0.50, account=account)
    assert not decision.allowed
    assert decision.code == "BUDGET_INVALID_STATE"


def test_daily_and_monthly_exact_boundaries_are_allowed(settings, storage, account):
    _seed_real_cost(storage, account, cost=1.95)
    assert PolicyEngine(settings, storage).check_run_budget(0.05, 1.0, account=account).allowed

    monthly_settings = replace(settings, max_daily_cost_usd=100.0)
    storage.conn.execute("UPDATE model_usage SET estimated_cost_usd=39.95 WHERE run_id='seed'")
    storage.conn.commit()
    assert PolicyEngine(monthly_settings, storage).check_run_budget(
        0.05, 1.0, account=account).allowed
