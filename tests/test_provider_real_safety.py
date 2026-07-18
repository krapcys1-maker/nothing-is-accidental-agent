"""WAVE 0A: brak ukrytych realnych wywołań i fail-closed pricing."""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import main as app_main
from app.core.config import (
    ConfigError,
    REAL_PROVIDER_PRICING_KEYS,
    require_valid_real_provider_pricing,
)
from app.llm.anthropic_client import AnthropicLLMClient, TOPIC_MAX_OUTPUT_TOKENS
from app.llm.base import Usage
from app.llm.fake_client import FakeLLMClient
from app.llm.usage_tracker import UsageTracker
from app.models import (
    DurableProviderAttemptContext,
    ProviderAttempt,
    ProviderAttemptStatus,
    Topic,
    TopicStatus,
)
from app.orchestrator import runner
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.research.anthropic_client import AnthropicResearchClient, OfflineAnthropicResearchClient
from app.research.base import (
    ResearchPlan,
    ResearchRateLimitError,
    ResearchServerError,
    ResearchTimeout,
)
from app.research.fake_client import FakeResearchClient
from app.storage.repositories import SqliteStorage
from app.workflows.topics.discover import run_topic_discovery


_PLAN = ResearchPlan(topic_id=1, account_id="acc", question="Why?", niche=["x"])


def _selected_topic(storage, account):
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Why queues form", question="Which system makes queues form?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _fully_priced(settings):
    return replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-real-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def test_every_real_sdk_client_disables_sdk_retry_and_sets_timeout(monkeypatch, account):
    constructed: list[dict] = []

    class FakeMessages:
        def create(self, **_kwargs):
            raise FakeAPIError("offline")

    class FakeAPIError(Exception):
        pass

    class FakeAnthropic:
        def __init__(self, **kwargs):
            constructed.append(kwargs)
            self.messages = FakeMessages()

    fake_sdk = SimpleNamespace(Anthropic=FakeAnthropic, APIError=FakeAPIError)
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)

    context = DurableProviderAttemptContext(
        job_id="topics-job",
        run_id="topics-run",
        stage="topics",
        attempt_no=1,
        request_id="topics-job:topics:1",
        lease_owner="test-worker",
        fence_token="topics-job:topics-run:test-worker",
        checked_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    topic_client = AnthropicLLMClient("key", "model")
    topic_client.configure_durable_attempt_control(
        context_callback=lambda _budget: context,
        activation_callback=lambda _context: ProviderAttempt(
            job_id=context.job_id,
            stage=context.stage,
            attempt_no=context.attempt_no,
            request_id=context.request_id,
            status=ProviderAttemptStatus.REQUEST_STARTED,
            reserved_amount_usd=0.1,
            reserved_at=context.checked_at,
            request_started_at=context.checked_at,
        ),
        assertion_callback=lambda _context: ProviderAttempt(
            job_id=context.job_id,
            stage=context.stage,
            attempt_no=context.attempt_no,
            request_id=context.request_id,
            status=ProviderAttemptStatus.REQUEST_STARTED,
            reserved_amount_usd=0.1,
            reserved_at=context.checked_at,
            request_started_at=context.checked_at,
        ),
    )
    with pytest.raises(Exception):
        topic_client.generate_and_score_topics(account, 1)
    AnthropicResearchClient("key", "model")._new_anthropic_client(fake_sdk)

    assert len(constructed) == 2
    assert all(item["max_retries"] == 0 for item in constructed)
    assert all(item["timeout"] > 0 for item in constructed)


@pytest.mark.parametrize(
    "error",
    [
        ResearchTimeout("timeout"),
        ResearchRateLimitError("rate", status_code=429),
        ResearchServerError("server", status_code=503, retryable=True),
    ],
    ids=["timeout", "429", "5xx"],
)
def test_typed_provider_failure_makes_exactly_one_sdk_attempt(error):
    calls = 0

    def caller(_plan):
        nonlocal calls
        calls += 1
        raise error

    client = OfflineAnthropicResearchClient("offline", "model", caller=caller, max_retries=99)
    with pytest.raises(type(error)):
        client.run_research(_PLAN)

    assert calls == 1
    assert client.call_count == 1


def test_normal_roots_ignore_real_environment_and_worker_is_offline(settings, account):
    real_environment = replace(settings, dry_run=False, anthropic_api_key="test-real-key")

    assert isinstance(runner._build_llm(real_environment, force_real=False), FakeLLMClient)
    assert isinstance(runner._build_research_client(real_environment, force_real=False), FakeResearchClient)

    worker, worker_storage = app_main._build_worker(real_environment)
    try:
        assert worker._dispatcher._settings.dry_run is True
        assert worker._dispatcher._settings.anthropic_api_key == "test-real-key"
    finally:
        worker_storage.close()


def test_normal_application_paths_use_fake_with_dry_run_false_and_real_key(settings, account):
    real_environment = replace(settings, dry_run=False, anthropic_api_key="test-real-key")
    (real_environment.project_root / "docs").mkdir(parents=True, exist_ok=True)

    storage = SqliteStorage.open(real_environment.db_path)
    try:
        topic = _selected_topic(storage, account)
    finally:
        storage.close()

    research = runner.run_research(
        topic_id=topic.id,
        settings=real_environment,
        force_re_research=True,
    )
    topics = runner.run_topics(count=1, settings=real_environment)

    assert research.dry_run is True
    assert topics.dry_run is True


def test_capped_runner_without_real_flag_never_constructs_provider_client(
        monkeypatch, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: settings)

    assert run_capped_research.main(["--topic-id", str(topic.id)]) == 0


@pytest.mark.parametrize("invalid", [None, 0.0, -1.0, float("nan"), float("inf")])
def test_invalid_price_values_fail_closed_before_real_client_construction(
        monkeypatch, settings, storage, account, invalid):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    broken_prices = {key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS}
    broken_prices["output_per_mtok"] = invalid
    broken = replace(
        settings, dry_run=False, anthropic_api_key="test-real-key", pricing=broken_prices,
    )
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: broken)

    assert run_capped_research.main(["--topic-id", str(topic.id), "--real"]) == 1


def test_missing_prices_block_real_mode_but_dry_run_remains_usable(
        monkeypatch, settings, storage, account):
    from scripts import run_capped_research

    topic = _selected_topic(storage, account)
    missing = replace(settings, dry_run=False, anthropic_api_key="test-real-key", pricing={})
    with pytest.raises(ConfigError):
        require_valid_real_provider_pricing(missing)

    monkeypatch.setattr(run_capped_research, "load_settings", lambda: missing)
    assert run_capped_research.main([
        "--topic-id", str(topic.id), "--real", "--estimate-only",
    ]) == 2
    assert run_capped_research.main(["--topic-id", str(topic.id), "--real"]) == 1

    summary = runner.run_topics(count=1, settings=missing)
    assert summary.dry_run is True


def test_topic_estimate_uses_the_same_max_output_limit_as_the_request(
        monkeypatch, settings, storage, account):
    captured: list[Usage] = []
    tracker = UsageTracker(settings, storage)
    storage.ensure_account(account)
    real_estimate = tracker.estimate_cost

    def capture(usage: Usage) -> float:
        captured.append(usage)
        return real_estimate(usage)

    monkeypatch.setattr(tracker, "estimate_cost", capture)
    run_topic_discovery(
        account, 1, settings=settings, storage=storage,
        llm=FakeLLMClient(), usage_tracker=tracker,
        policy=PolicyEngine(settings, storage), notifier=LogNotification(),
    )

    assert captured[0].output_tokens == TOPIC_MAX_OUTPUT_TOKENS == 1500
