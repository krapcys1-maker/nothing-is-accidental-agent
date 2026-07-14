"""Offline integration tests for single-attempt research budgets."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.llm.base import Usage
from app.llm.usage_tracker import UsageTracker
from app.models import RunStatus, Topic, TopicStatus
from app.policies.policy_engine import PolicyEngine
from app.policies.policy_engine import PolicyDecision
from app.ports.notification import LogNotification
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import ResearchRateLimitError, ResearchTimeout
from app.research.cost_estimator import (
    estimate_with_retries,
    estimate_worst_case_search_call_usd,
)
from app.research.fake_client import FakeResearchClient
from app.workflows.research.pipeline import (
    run_research_pipeline,
    run_two_stage_research_pipeline,
)
from scripts import run_capped_research


def _topic(storage, account):
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Retry budget",
        question="Why must retries be budgeted?",
        score=90.0,
        status=TopicStatus.SELECTED,
    ))


def _good_json():
    return json.dumps({
        "question": "Why must retries be budgeted?",
        "working_thesis": "Every technical attempt can be billable.",
        "main_mechanism": "retry accounting",
        "confirmed_claims": ["Retries can cost money."],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "Some timeouts are not billed.",
        "citable_numbers": [],
        "visual_idea": "attempt timeline",
        "confidence_score": 0.9,
        "source_quality_score": 0.9,
        "sources": [
            {"url": f"https://example.org/{i}", "title": f"Source {i}",
             "source_type": "PRIMARY", "supports_claim": "Retries can cost money."}
            for i in range(3)
        ],
    })


def _run(settings, storage, account, client, *, cap):
    return run_research_pipeline(
        account,
        _topic(storage, account),
        settings=settings,
        storage=storage,
        research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage),
        notifier=LogNotification(),
        max_retries=1,
        run_cap_usd=cap,
    )


def test_timeout_usage_is_persisted_without_automatic_retry(settings, storage, account):
    calls = []
    billed_timeout = Usage(output_tokens=40_000)  # 0.60 USD in fixture pricing

    def caller(plan):
        calls.append(1)
        raise ResearchTimeout("provider timeout", usage=billed_timeout, model="m")

    client = AnthropicResearchClient("offline", "m", caller=caller, max_retries=1)
    summary = _run(settings, storage, account, client, cap=1.0)

    assert len(calls) == 1
    assert client.call_count == 1
    assert not summary.blocked
    assert "timeout" in (summary.error or "").lower()
    usage = storage.get_research_usage(summary.run_id)
    assert len(usage) == 1
    assert usage[0].estimated_cost_usd == pytest.approx(0.60)
    assert storage.get_run(summary.run_id).cost_usd == pytest.approx(0.60)


def test_timeout_stops_before_a_second_billable_attempt(settings, storage, account):
    state = {"calls": 0}
    first_usage = Usage(input_tokens=100, output_tokens=50)
    success_usage = Usage(input_tokens=200, output_tokens=100)

    def caller(plan):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ResearchTimeout("provider timeout", usage=first_usage, model="m")
        return _good_json(), success_usage

    client = AnthropicResearchClient("offline", "m", caller=caller, max_retries=1)
    summary = _run(settings, storage, account, client, cap=2.0)

    assert state["calls"] == 1
    assert not summary.blocked
    assert "timeout" in (summary.error or "").lower()
    usage = storage.get_research_usage(summary.run_id)
    assert len(usage) == 1
    expected = sum(row.estimated_cost_usd for row in usage)
    assert summary.cost_usd == pytest.approx(expected)
    assert storage.get_run(summary.run_id).status == RunStatus.FAILED
    assert storage.get_run(summary.run_id).cost_usd == pytest.approx(expected)


def test_rate_limit_usage_is_persisted_exactly_once_without_retry(
        settings, storage, account):
    state = {"calls": 0}
    billed_rate_limit = Usage(input_tokens=100, output_tokens=50)
    success_usage = Usage(input_tokens=200, output_tokens=100)

    def caller(plan):
        state["calls"] += 1
        if state["calls"] == 1:
            raise ResearchRateLimitError(
                "rate limit", status_code=429, usage=billed_rate_limit, model="m")
        return _good_json(), success_usage

    client = AnthropicResearchClient("offline", "m", caller=caller, max_retries=1)
    summary = _run(settings, storage, account, client, cap=2.0)

    assert state["calls"] == 1
    assert not summary.blocked
    assert "rate limit" in (summary.error or "").lower()
    usage = storage.get_research_usage(summary.run_id)
    assert len(usage) == 1
    assert [(row.input_tokens, row.output_tokens) for row in usage] == [
        (100, 50),
    ]
    assert storage.get_run(summary.run_id).cost_usd == pytest.approx(
        sum(row.estimated_cost_usd for row in usage))


def test_cli_preflight_delegates_budget_decision_to_policy(settings, account, capsys):
    calls = []

    class _Policy:
        def check_run_budget(self, estimated_total, cap, *, current_run_cost, account):
            calls.append((estimated_total, cap, current_run_cost, account.id))
            return PolicyDecision.ok()

    configured = replace(settings, anthropic_api_key="offline-key", dry_run=False)
    result = run_capped_research._preflight_stop(
        configured, _Policy(), account, 0.30, 0.50, current_run_cost=0.10)
    assert result is None
    assert calls == [(0.30, 0.50, 0.10, account.id)]
    assert "OK:" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("code", "reason"),
    [("RUN_CAP_EXCEEDED", "run cap"),
     ("BUDGET_DAILY_EXCEEDED", "daily"),
     ("BUDGET_MONTHLY_EXCEEDED", "monthly")],
)
def test_cli_reports_exact_central_policy_denial(settings, account, capsys, code, reason):
    class _Policy:
        def check_run_budget(self, *args, **kwargs):
            return PolicyDecision.block(code, reason)

    configured = replace(settings, anthropic_api_key="offline-key", dry_run=False)
    result = run_capped_research._preflight_stop(
        configured, _Policy(), account, 0.30, 0.50, current_run_cost=0.10)
    assert result == 1
    output = capsys.readouterr().out
    assert code in output
    assert reason in output


def test_pipeline_infers_retry_count_from_anthropic_client(settings, storage, account):
    client = AnthropicResearchClient(
        "offline", "m", caller=lambda plan: (_good_json(), Usage()), max_retries=2)
    summary = run_research_pipeline(
        account, _topic(storage, account), settings=settings, storage=storage,
        research_client=client,
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
        run_cap_usd=2.0)
    assert summary.error is None
    assert client.call_count == 1


def test_pipeline_rejects_retry_configuration_mismatch_before_call(
        settings, storage, account):
    client = AnthropicResearchClient(
        "offline", "m", caller=lambda plan: (_good_json(), Usage()), max_retries=2)
    with pytest.raises(ValueError, match="zgodne z max_retries klienta"):
        run_research_pipeline(
            account, _topic(storage, account), settings=settings, storage=storage,
            research_client=client,
            usage_tracker=UsageTracker(
                settings, storage, costs_csv_path=settings.costs_csv_path),
            policy=PolicyEngine(settings, storage), notifier=LogNotification(),
            max_retries=1, run_cap_usd=2.0)
    assert client.call_count == 0


def test_real_pipeline_without_run_cap_fails_before_caller(settings, storage, account):
    calls = []
    real_settings = replace(settings, dry_run=False)
    client = AnthropicResearchClient(
        "offline", "m",
        caller=lambda plan: calls.append(1) or (_good_json(), Usage()),
        max_retries=0,
    )
    with pytest.raises(ValueError, match="wymaga jawnego run_cap_usd"):
        run_research_pipeline(
            account, _topic(storage, account), settings=real_settings, storage=storage,
            research_client=client,
            usage_tracker=UsageTracker(
                real_settings, storage, costs_csv_path=real_settings.costs_csv_path),
            policy=PolicyEngine(real_settings, storage), notifier=LogNotification())
    assert calls == []
    assert storage.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0


class _CaptureStageBudgetPolicy:
    def __init__(self):
        self.calls = []

    def check_can_run(self, account):
        return PolicyDecision.ok()

    def check_run_budget(self, estimated_total, cap, *, current_run_cost, account):
        self.calls.append((estimated_total, cap, current_run_cost))
        return PolicyDecision.block("RUN_CAP_EXCEEDED", "captured")


def test_legacy_single_applies_retry_multiplier_once(settings, storage, account):
    policy = _CaptureStageBudgetPolicy()
    summary = run_research_pipeline(
        account, _topic(storage, account), settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=policy, notifier=LogNotification(), max_retries=2, run_cap_usd=2.0)
    base = estimate_worst_case_search_call_usd(
        settings, max_web_searches=6, max_output_tokens=3000).total_usd
    assert policy.calls == [(estimate_with_retries(base, 2), 2.0, 0.0)]
    assert summary.blocked and summary.run_id is None


def test_legacy_two_stage_applies_retry_multiplier_once_to_stage_a(
        settings, storage, account):
    policy = _CaptureStageBudgetPolicy()
    summary = run_two_stage_research_pipeline(
        account, _topic(storage, account), settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage, costs_csv_path=settings.costs_csv_path),
        policy=policy, notifier=LogNotification(), max_web_searches=4,
        gather_max_tokens=1200, max_retries=2, run_cap_usd=2.0)
    base = estimate_worst_case_search_call_usd(
        settings, max_web_searches=4, max_output_tokens=1200).total_usd
    assert policy.calls == [(estimate_with_retries(base, 2), 2.0, 0.0)]
    assert summary.blocked and summary.run_id is None
