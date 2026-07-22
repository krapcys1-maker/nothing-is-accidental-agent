"""Autonomiczne generowanie tematów w durable provider lifecycle (0020).

Całość offline na nowych tymczasowych bazach: fake caller tematów, zero SDK,
zero sieci, zero realnego API. Pokrycie: kontrakt durable intentu (brak
topic_id, fingerprint, cap, pricing, max_retries=0, max_web_searches=0), trwała
jednorazowa zgoda L1 (binding, expiry, exactly-once, replay, mismatch modelu /
capu / konta / intentu), atomowa konsumpcja + rezerwacja, fence
TOPIC_GENERATION, dokładnie jeden attempt, pełna macierz błędów, scoring +
dedup + najwyżej jeden SELECTED na generation run, lineage po reopen bazy,
concurrency, restart i recovery.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.llm.base import LLMProviderError, TopicIdea, Usage
from app.models import (
    ExecutionResolution,
    FinancialResolution,
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ProviderAttemptStatus,
    ReconciliationEventType,
    ReconciliationFaultPoint,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import (
    JobConflictError,
    ProviderAttemptReconciliationError,
    StaleJobExecutionError,
    TopicGenerationAuthorizationError,
    TopicGenerationResultError,
)
from app.research.durable_intent import DurableExecutionIntentError
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from app.topics.durable_intent import (
    TOPIC_GENERATION_EXECUTION,
    DurableTopicGenerationIntent,
    canonicalize_topic_generation_payload,
    frozen_topic_generation_intent_json,
    topic_generation_job_id,
)
from app.workflows.topics.generate import validate_score_breakdown
from tests.conftest import STANDARD_WEIGHTS, write_approved_pricing_profile

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
DIMENSIONS = sorted(STANDARD_WEIGHTS)


# --- wspólne przygotowanie ---------------------------------------------------

def _real_settings(settings, model="topics-test-model"):
    return replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-only-key",
        model_quality=model,
        research_timeout_seconds=31,
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )


def _pricing_profile(real_settings):
    profile_id, pricing_path = write_approved_pricing_profile(
        real_settings.project_root,
        model=real_settings.model_quality,
        prices=dict(real_settings.pricing),
    )
    return resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real_settings.model_quality,
    )


def _intent(real_settings, account, *, cap=1.0, count=3, max_tokens=1500,
            profile=None, model=None, dimensions=None):
    profile = profile or _pricing_profile(real_settings)
    return DurableTopicGenerationIntent.from_settings(
        settings=real_settings,
        account_id=account.id,
        cap_usd=cap,
        candidate_count=count,
        niche=account.niche,
        model=model or real_settings.model_quality,
        max_tokens=max_tokens,
        score_dimensions=dimensions or DIMENSIONS,
        pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )


def _payload(intent):
    return {
        "account_id": intent.account_id,
        "dry_run": False,
        "execution": TOPIC_GENERATION_EXECUTION,
        "mode": "single",
        "max_cost_usd": intent.cap_usd,
        "execution_intent": intent.as_payload(),
    }


def _job(account, key, payload):
    return Job(
        id=f"topicgen-job-{key}", account_id=account.id,
        kind=JobKind.TOPIC_GENERATION, workflow=WorkflowType.TOPIC_GENERATION,
        idempotency_key=f"topicgen-{key}", topic_id=None,
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW,
        max_attempts=1, payload=payload,
    )


def _open_flags(storage):
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="topic-generation", now=NOW)


def _approve(storage, job_id, account, *, hours=2, approved_by="owner-l1"):
    return storage.record_topic_generation_approval(
        job_id=job_id, account_id=account.id, approved_by=approved_by,
        expires_at=NOW + timedelta(hours=hours), clock=FixedClock(NOW),
    )


# Deliberately unrelated titles: the real TopicDeduplicator would otherwise
# collapse near-identical fixtures, which is its job but not what most of these
# tests are about.  The dedup tests below pass explicit colliding titles.
_DISTINCT_TITLES = [
    "Why supermarket queues form",
    "How postal codes shape insurance premiums",
    "The hidden economics of stadium parking",
    "Who decides where traffic lights go",
    "What airline overbooking really costs",
]


def _response(*scores, titles=None):
    """Build one topic response; each score is a uniform 0..1 breakdown value."""
    topics = []
    for index, value in enumerate(scores):
        title = titles[index] if titles else _DISTINCT_TITLES[index]
        topics.append({
            "title": title,
            "question": f"Why does '{title}' work that way?",
            "score_breakdown": {name: value for name in DIMENSIONS},
        })
    return json.dumps({"topics": topics})


class _FakeTopicCaller:
    """The single fake transport; everything else is the real durable path."""

    def __init__(self, response=None, usage=None, error=None):
        self.calls = []
        self._response = response if response is not None else _response(0.9)
        self._usage = usage or Usage(input_tokens=120, output_tokens=90)
        self._error = error

    def __call__(self, account, count):
        self.calls.append((account, count))
        if self._error is not None:
            raise self._error
        return self._response, self._usage


def _install_fake_caller(dispatcher_kwargs, caller):
    from app.llm.anthropic_client import AnthropicLLMClient

    def factory(settings, intent):
        return AnthropicLLMClient(
            settings.anthropic_api_key, intent.model,
            caller=caller, timeout_seconds=float(intent.timeout_seconds),
            topic_max_tokens=intent.max_tokens,
        )

    dispatcher_kwargs["topic_generation_client_factory"] = factory
    return dispatcher_kwargs


def _worker(real_settings, storage, caller, *, lease_owner="topicgen-worker",
            clock=None, lease_seconds=120):
    clock = clock or FixedClock(NOW)
    policy = PolicyEngine(real_settings, storage, clock)
    kwargs = _install_fake_caller({
        "settings": real_settings, "storage": storage, "policy": policy,
        "clock": clock,
    }, caller)
    dispatcher = JobDispatcher(**kwargs)
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner=lease_owner, lease_seconds=lease_seconds,
        heartbeat_interval_seconds=5.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real_settings.db_path),
        clock=clock,
    )


def _prepare(settings, storage, account, *, key="a", cap=1.0, count=3,
             approve=True, model=None):
    real = _real_settings(settings) if model is None else _real_settings(settings, model)
    profile = _pricing_profile(real)
    intent = _intent(real, account, cap=cap, count=count, profile=profile)
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, key, _payload(intent)))
    _open_flags(storage)
    if approve:
        _approve(storage, job.id, account)
    return real, intent, job


# --- kontrakt durable intentu ------------------------------------------------

def test_intent_has_no_topic_id_and_pins_the_paid_request_contract(settings, account):
    real = _real_settings(settings)
    intent = _intent(real, account, cap=0.5, count=4, max_tokens=1200)
    payload = intent.as_payload()

    assert "topic_id" not in payload
    assert payload["workflow"] == "TOPIC_GENERATION"
    assert payload["stage"] == "topics"
    assert payload["max_retries"] == 0
    assert payload["max_web_searches"] == 0
    assert payload["cap_usd"] == "0.500000"
    assert payload["candidate_count"] == 4
    assert payload["max_tokens"] == 1200
    assert payload["score_dimensions"] == DIMENSIONS
    assert set(payload["pricing_profile"]) == set(REAL_PROVIDER_PRICING_KEYS)
    assert intent.is_supported_by_current_worker()


def test_intent_round_trips_and_fingerprint_is_stable(settings, account):
    real = _real_settings(settings)
    intent = _intent(real, account)
    payload = _payload(intent)
    encoded, fingerprint = frozen_topic_generation_intent_json(payload)

    assert DurableTopicGenerationIntent.from_payload(intent.as_payload()) == intent
    # Key order and equivalent numeric forms must not change identity.
    shuffled = dict(reversed(list(payload.items())))
    assert frozen_topic_generation_intent_json(shuffled)[1] == fingerprint
    assert json.loads(encoded)["cap_usd"] == intent.cap_usd


def test_intent_rejects_topic_id_and_unknown_fields(settings, account):
    real = _real_settings(settings)
    raw = _intent(real, account).as_payload()

    with pytest.raises(DurableExecutionIntentError) as with_topic:
        DurableTopicGenerationIntent.from_payload({**raw, "topic_id": 7})
    assert with_topic.value.code == "TOPIC_GENERATION_FORBIDS_TOPIC_ID"

    with pytest.raises(DurableExecutionIntentError):
        DurableTopicGenerationIntent.from_payload({**raw, "surprise": 1})
    missing = {k: v for k, v in raw.items() if k != "cap_usd"}
    with pytest.raises(DurableExecutionIntentError):
        DurableTopicGenerationIntent.from_payload(missing)


@pytest.mark.parametrize("field,value,code", [
    ("max_web_searches", 1, "TOPIC_GENERATION_REQUIRES_ZERO_SEARCHES"),
    ("max_retries", 1, "TOPIC_GENERATION_REQUIRES_ZERO_RETRIES"),
    ("candidate_count", 0, "CANDIDATE_COUNT_OUT_OF_RANGE"),
    ("candidate_count", 99, "CANDIDATE_COUNT_OUT_OF_RANGE"),
    ("max_tokens", 12, "MAX_TOKENS_OUT_OF_RANGE"),
])
def test_intent_enforces_its_closed_numeric_bounds(settings, account, field, value, code):
    real = _real_settings(settings)
    raw = _intent(real, account).as_payload()
    with pytest.raises(DurableExecutionIntentError) as exc:
        DurableTopicGenerationIntent.from_payload({**raw, field: value})
    assert exc.value.code == code


def test_intent_rejects_tampered_pricing_and_projection(settings, account):
    real = _real_settings(settings)
    raw = _intent(real, account).as_payload()

    tampered_prices = dict(raw["pricing_profile"])
    tampered_prices["input_per_mtok"] = "0.000001"
    with pytest.raises(DurableExecutionIntentError):
        DurableTopicGenerationIntent.from_payload(
            {**raw, "pricing_profile": tampered_prices}
        )
    with pytest.raises(DurableExecutionIntentError):
        DurableTopicGenerationIntent.from_payload(
            {**raw, "projected_cost_usd": "0.000001"}
        )


def test_payload_canonicalization_rejects_dry_run_and_foreign_execution(settings, account):
    real = _real_settings(settings)
    payload = _payload(_intent(real, account))

    with pytest.raises(DurableExecutionIntentError):
        canonicalize_topic_generation_payload({**payload, "dry_run": True})
    with pytest.raises(DurableExecutionIntentError) as exc:
        canonicalize_topic_generation_payload(
            {**payload, "execution": "durable_provider_v2"}
        )
    assert exc.value.code == "UNSUPPORTED_EXECUTION_CONTRACT"
    with pytest.raises(DurableExecutionIntentError):
        canonicalize_topic_generation_payload({**payload, "topic_id": 3})


def test_job_id_is_deterministic_for_one_operation_key():
    assert topic_generation_job_id("wave-1") == topic_generation_job_id("wave-1")
    assert topic_generation_job_id("wave-1") != topic_generation_job_id("wave-2")


# --- trwała zgoda L1 ---------------------------------------------------------

def test_approval_binds_the_frozen_contract_and_is_born_unconsumed(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    approval = _approve(storage, job.id, account)

    _, fingerprint = frozen_topic_generation_intent_json(job.payload)
    assert approval.intent_fingerprint == fingerprint
    assert approval.model == intent.model
    assert approval.cap_usd == intent.cap_usd
    assert approval.max_tokens == intent.max_tokens
    assert approval.consumed_at is None
    assert json.loads(approval.execution_intent_json)["account_id"] == account.id
    assert storage.get_topic_generation_approval_for_job(job.id).id == approval.id


def test_approval_is_refused_twice_and_for_a_foreign_account(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=True)

    with pytest.raises(TopicGenerationAuthorizationError) as duplicate:
        _approve(storage, job.id, account)
    assert duplicate.value.code == "APPROVAL_ALREADY_EXISTS"

    # A second account may hold its own concurrent job; approving it under the
    # FIRST account's identity must be refused.
    other = account.model_copy(update={"id": "other_account"})
    storage.ensure_account(other)
    other_intent = _intent(real, other, profile=_pricing_profile(real))
    job2 = storage.enqueue_job(_job(other, "b", _payload(other_intent)))
    with pytest.raises(TopicGenerationAuthorizationError) as foreign:
        storage.record_topic_generation_approval(
            job_id=job2.id, account_id=account.id, approved_by="op",
            expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
        )
    assert foreign.value.code == "ACCOUNT_MISMATCH"


def test_only_one_active_topic_generation_job_per_account(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    with pytest.raises(Exception):
        storage.enqueue_job(_job(account, "second", _payload(intent)))
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM jobs WHERE account_id=? AND kind='TOPIC_GENERATION'",
        (account.id,),
    ).fetchone()["c"] == 1


def test_approval_requires_a_future_expiry_and_a_named_operator(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)

    with pytest.raises(TopicGenerationAuthorizationError) as blank:
        storage.record_topic_generation_approval(
            job_id=job.id, account_id=account.id, approved_by="   ",
            expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
        )
    assert blank.value.code == "APPROVER_MISSING"

    with pytest.raises(TopicGenerationAuthorizationError) as past:
        storage.record_topic_generation_approval(
            job_id=job.id, account_id=account.id, approved_by="op",
            expires_at=NOW - timedelta(seconds=1), clock=FixedClock(NOW),
        )
    assert past.value.code == "APPROVAL_EXPIRY_INVALID"


def test_approval_is_refused_after_the_job_left_queued(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    storage.claim_next_job("worker", 60, clock=FixedClock(NOW))
    with pytest.raises(TopicGenerationAuthorizationError) as exc:
        _approve(storage, job.id, account)
    assert exc.value.code == "JOB_NOT_APPROVABLE"


def test_approval_row_is_append_only_and_immutable(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, approve=True)

    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE topic_generation_approvals SET model='other' WHERE job_id=?",
            (job.id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "DELETE FROM topic_generation_approvals WHERE job_id=?", (job.id,),
        )
    storage.conn.rollback()


def test_approval_fingerprint_must_be_the_hash_of_its_stored_preimage(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO topic_generation_approvals (job_id,account_id,"
            "intent_fingerprint,execution_intent_json,model,cap_usd,max_tokens,"
            "approved_by,approved_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                job.id, account.id, "0" * 64, json.dumps({"a": 1}), intent.model,
                intent.cap_usd, intent.max_tokens, "op",
                "2026-07-21 12:00:00", "2026-07-21 14:00:00",
            ),
        )
    storage.conn.rollback()


def test_approval_cannot_bind_a_research_job(settings, storage, account):
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Research topic", question="Why?",
        score=90.0, status=TopicStatus.SELECTED,
    ))
    research = storage.enqueue_job(Job(
        id="research-job", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key="research-job",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={"account_id": account.id, "topic_id": int(topic.id), "dry_run": True},
    ))
    with pytest.raises(TopicGenerationAuthorizationError):
        _approve(storage, research.id, account)


# --- fence, rezerwacja i konsumpcja zgody ------------------------------------

def _run_once(real, storage, caller, **kwargs):
    return _worker(real, storage, caller, **kwargs).run_once()


def _needs_topic_reconciliation(settings, storage, account, *, key="reconcile"):
    real, intent, job = _prepare(
        settings, storage, account, key=key, count=1,
    )
    caller = _FakeTopicCaller(
        error=LLMProviderError("unknown provider outcome", model=intent.model),
    )
    result = _run_once(real, storage, caller)
    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert len(caller.calls) == 1
    request_id = f"{job.id}:topics:1"
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value
    return real, intent, job, request_id, caller


class _CrashAfterSettledTopicUsage(BaseException):
    """Test-only process death after durable usage, before topic scoring."""


def _settled_topic_generation_crash(
    settings, storage, account, monkeypatch, *, key="settled-crash",
):
    """Reach the real SETTLED + non-terminal crash window through a fake caller."""
    from app.workflows.topics import generate as topic_generate

    real, intent, job = _prepare(
        settings, storage, account, key=key, count=1,
    )
    caller = _FakeTopicCaller(_response(0.95))

    def crash_before_scoring(*args, **kwargs):
        del args, kwargs
        raise _CrashAfterSettledTopicUsage

    with monkeypatch.context() as crash:
        crash.setattr(topic_generate, "_score_and_select", crash_before_scoring)
        with pytest.raises(_CrashAfterSettledTopicUsage):
            _run_once(real, storage, caller)

    durable_job = storage.get_job(job.id)
    assert durable_job is not None and durable_job.run_id is not None
    request_id = f"{job.id}:topics:1"
    attempt = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()
    usage = storage.conn.execute(
        "SELECT * FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchall()
    assert attempt["status"] == ProviderAttemptStatus.SETTLED.value
    assert durable_job.status is JobStatus.RUNNING
    assert storage.get_run(durable_job.run_id).status is RunStatus.RUNNING
    assert len(usage) == 1 and usage[0]["task"] == "topics"
    assert len(caller.calls) == 1
    assert storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM generated_topics"
    ).fetchone()[0] == 0
    return real, intent, job, request_id, caller, float(usage[0]["estimated_cost_usd"])


def _settled_recovery_snapshot(storage, job_id, request_id):
    job = storage.get_job(job_id)
    assert job is not None and job.run_id is not None
    return {
        "attempt": tuple(storage.conn.execute(
            "SELECT status,actual_cost_usd,settled_at,error_code FROM provider_attempts "
            "WHERE request_id=?", (request_id,),
        ).fetchone()),
        "job": tuple(storage.conn.execute(
            "SELECT status,reserved_cost_usd,budget_reserved_at,lease_owner,"
            "lease_expires_at,external_effect_started_at,last_error,finished_at "
            "FROM jobs WHERE id=?", (job_id,),
        ).fetchone()),
        "run": tuple(storage.conn.execute(
            "SELECT status,cost_usd,error,finished_at FROM runs WHERE id=?",
            (job.run_id,),
        ).fetchone()),
        "usage": [tuple(row) for row in storage.conn.execute(
            "SELECT id,run_id,provider,model,task,estimated_cost_usd,request_id "
            "FROM model_usage WHERE run_id=? ORDER BY id", (job.run_id,),
        ).fetchall()],
        "events": [tuple(row) for row in storage.conn.execute(
            "SELECT event_type,financial_resolution,execution_resolution,operator,note "
            "FROM reconciliation_events WHERE request_id=? ORDER BY sequence_number",
            (request_id,),
        ).fetchall()],
        "topics": storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0],
        "generated": storage.conn.execute(
            "SELECT COUNT(*) FROM generated_topics"
        ).fetchone()[0],
    }


def test_settled_topic_generation_crash_has_automatic_terminal_recovery(
    settings, storage, account, monkeypatch,
):
    from app.scheduler.maintenance import MaintenanceRunner

    real, intent, job, request_id, caller, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch,
    )
    crashed = storage.get_job(job.id)
    assert crashed.lease_owner == "topicgen-worker"
    assert crashed.external_effect_started_at is not None
    assert crashed.budget_reserved_at is None
    assert storage.get_topic_generation_approval_for_job(job.id).consumed_at is not None
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1

    # A plain reopen observes the durable crash window and performs no recovery.
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    assert reopened.get_job(job.id).status is JobStatus.RUNNING
    assert reopened.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == ProviderAttemptStatus.SETTLED.value

    maintenance_clock = FixedClock(NOW + timedelta(minutes=5))
    runner = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=30,
        clock=maintenance_clock,
    )
    cycle = runner.run_once()
    recovery = cycle.recovery

    assert recovery.needs_verification_count == 1
    assert recovery.settled_execution_recovery_count == 1
    assert recovery.settled_execution_blocked_count == 0
    terminal_job = reopened.get_job(job.id)
    assert terminal_job.status is JobStatus.FAILED
    assert terminal_job.lease_owner is None and terminal_job.lease_expires_at is None
    assert terminal_job.external_effect_started_at is None
    assert terminal_job.reserved_cost_usd == 0.0
    assert terminal_job.budget_reserved_at is None
    assert terminal_job.last_error == (
        "SETTLED_TOPIC_EXECUTION_RECOVERED_BEFORE_RESULT_FINALIZATION"
    )
    assert reopened.get_run(terminal_job.run_id).status is RunStatus.FAILED
    assert reopened.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == ProviderAttemptStatus.SETTLED.value
    usage = reopened.conn.execute(
        "SELECT * FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchall()
    assert len(usage) == 1 and usage[0]["task"] == "topics"
    assert reopened.get_run(terminal_job.run_id).cost_usd == pytest.approx(actual_cost)
    assert reopened.sum_real_cost_usd("2026-07-21") == pytest.approx(actual_cost)
    assert reopened.sum_real_cost_usd("2026-07") == pytest.approx(actual_cost)
    assert reopened.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE status IN "
        "('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')"
    ).fetchone()[0] == 0
    event = reopened.conn.execute(
        "SELECT * FROM reconciliation_events WHERE request_id=? AND event_type="
        "'EXECUTION_RECOVERY'", (request_id,),
    ).fetchone()
    assert event["financial_resolution"] == FinancialResolution.CHARGED_KNOWN.value
    assert event["execution_resolution"] == ExecutionResolution.EXECUTION_FAILED.value
    assert "before topic result finalization" in event["note"].lower()
    assert reopened.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert reopened.conn.execute(
        "SELECT COUNT(*) FROM generated_topics"
    ).fetchone()[0] == 0

    # Replay is a durable no-op; a worker has nothing to retry.
    terminal_snapshot = _settled_recovery_snapshot(reopened, job.id, request_id)
    second = runner.run_once()
    assert second.recovery.settled_execution_recovery_count == 0
    assert _settled_recovery_snapshot(reopened, job.id, request_id) == terminal_snapshot
    resolver_replay = reopened.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=actual_cost,
        reconciled_by="owner-l1", note="maintenance already recovered this execution",
        now=NOW + timedelta(minutes=6),
    )
    assert resolver_replay.idempotent is True
    assert _settled_recovery_snapshot(reopened, job.id, request_id) == terminal_snapshot
    worker_result = _worker(
        real, reopened, caller, clock=maintenance_clock,
    ).run_once()
    assert worker_result.status is WorkerIterationStatus.IDLE
    assert len(caller.calls) == 1

    # The terminal job left the active-account unique index; the old consumed
    # approval cannot authorize the new job.
    next_job = reopened.enqueue_job(
        _job(account, "after-settled-recovery", _payload(intent)),
    )
    assert next_job.status is JobStatus.QUEUED
    assert reopened.get_topic_generation_approval_for_job(next_job.id) is None
    assert reopened.get_topic_generation_approval_for_job(job.id).consumed_at is not None
    reopened.close()


def test_settled_topic_generation_public_resolver_terminalizes_without_new_usage(
    settings, storage, account, monkeypatch,
):
    _, intent, job, request_id, caller, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="settled-public-resolver",
    )
    usage_id = storage.conn.execute(
        "SELECT id FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0]

    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=actual_cost,
        reconciled_by="owner-l1", note="settled topic result was not finalized",
        now=NOW + timedelta(minutes=5),
    )
    terminal_snapshot = _settled_recovery_snapshot(storage, job.id, request_id)
    replay = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=actual_cost,
        reconciled_by="owner-l1", note="settled topic result was not finalized",
        now=NOW + timedelta(minutes=6),
    )

    assert result.attempt.status is ProviderAttemptStatus.SETTLED
    assert result.usage_id == usage_id
    assert replay.idempotent is True and replay.usage_id == usage_id
    assert _settled_recovery_snapshot(storage, job.id, request_id) == terminal_snapshot
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.get_job(job.id).external_effect_started_at is None
    assert storage.get_run(storage.get_job(job.id).run_id).status is RunStatus.FAILED
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 1
    assert len(caller.calls) == 1
    assert storage.enqueue_job(
        _job(account, "after-settled-public-resolver", _payload(intent)),
    ).status is JobStatus.QUEUED


@pytest.mark.parametrize(
    ("financial", "execution", "cost"),
    [
        (FinancialResolution.CHARGED_KNOWN, ExecutionResolution.EXECUTION_FAILED, "different"),
        (FinancialResolution.NOT_CHARGED, ExecutionResolution.EXECUTION_FAILED, None),
        (
            FinancialResolution.CHARGE_UNKNOWN,
            ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
            None,
        ),
        (
            FinancialResolution.CHARGED_KNOWN,
            ExecutionResolution.RESULT_ALREADY_FINALIZED,
            "actual",
        ),
    ],
)
def test_settled_topic_resolver_rejects_conflicting_resolution_without_mutation(
    settings, storage, account, monkeypatch, financial, execution, cost,
):
    _, _, job, request_id, _, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch,
        key=f"settled-conflict-{financial.value.lower()}-{execution.value.lower()}",
    )
    before = _settled_recovery_snapshot(storage, job.id, request_id)
    supplied_cost = (
        actual_cost + 0.01 if cost == "different"
        else actual_cost if cost == "actual" else None
    )
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=financial, execution_resolution=execution,
            actual_cost_usd=supplied_cost,
            reconciled_by="owner-l1", note="conflicting settled resolution",
            now=NOW + timedelta(minutes=5),
        )
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before


@pytest.mark.parametrize(
    "tamper",
    [
        "wrong_task",
        "wrong_model",
        "missing_usage",
        "duplicate_usage",
        "extra_run_usage",
        "wrong_stage",
        "attempt_two",
        "approval_not_consumed",
    ],
)
def test_settled_topic_resolver_rejects_inconsistent_durable_state_without_mutation(
    settings, storage, account, monkeypatch, tamper,
):
    _, _, job, request_id, _, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key=f"settled-tamper-{tamper}",
    )
    if tamper == "wrong_task":
        storage.conn.execute(
            "UPDATE model_usage SET task='research' WHERE request_id=?", (request_id,),
        )
    elif tamper == "wrong_model":
        storage.conn.execute(
            "UPDATE model_usage SET model='foreign-model' WHERE request_id=?",
            (request_id,),
        )
    elif tamper == "missing_usage":
        storage.conn.execute(
            "DELETE FROM model_usage WHERE request_id=?", (request_id,),
        )
    elif tamper == "duplicate_usage":
        storage.conn.execute("DROP INDEX ux_model_usage_request_id")
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,"
            "output_tokens,cache_read_tokens,cache_write_tokens,web_search_requests,"
            "estimated_cost_usd,dry_run,request_id,is_legacy_usage,created_at) "
            "SELECT run_id,provider,model,task,input_tokens,output_tokens,"
            "cache_read_tokens,cache_write_tokens,web_search_requests,"
            "estimated_cost_usd,dry_run,request_id,is_legacy_usage,created_at "
            "FROM model_usage WHERE request_id=?",
            (request_id,),
        )
    elif tamper == "extra_run_usage":
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,"
            "output_tokens,cache_read_tokens,cache_write_tokens,web_search_requests,"
            "estimated_cost_usd,dry_run,request_id,is_legacy_usage,created_at) "
            "SELECT run_id,provider,model,'research',0,0,0,0,0,0.0,1,NULL,0,created_at "
            "FROM model_usage WHERE request_id=?",
            (request_id,),
        )
    elif tamper in {"wrong_stage", "attempt_two"}:
        storage.conn.execute("DROP TRIGGER provider_attempts_identity_is_immutable")
        storage.conn.execute("DROP TRIGGER provider_attempts_controlled_transition")
        column, value = (
            ("stage", "research") if tamper == "wrong_stage" else ("attempt_no", 2)
        )
        storage.conn.execute(
            f"UPDATE provider_attempts SET {column}=? WHERE request_id=?",
            (value, request_id),
        )
    else:
        storage.conn.execute(
            "DROP TRIGGER topic_generation_approvals_consume_exactly_once"
        )
        storage.conn.execute(
            "UPDATE topic_generation_approvals SET consumed_at=NULL WHERE job_id=?",
            (job.id,),
        )
    storage.conn.commit()

    before = _settled_recovery_snapshot(storage, job.id, request_id)
    with pytest.raises(ProviderAttemptReconciliationError):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=actual_cost,
            reconciled_by="owner-l1", note="inconsistent settled state",
            now=NOW + timedelta(minutes=5),
        )
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before


def test_settled_topic_resolver_rejects_foreign_account_and_request_without_mutation(
    settings, storage, account, monkeypatch,
):
    _, _, job, request_id, _, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="settled-foreign-identity",
    )
    before = _settled_recovery_snapshot(storage, job.id, request_id)
    for rejected_request, rejected_account in (
        (request_id, "foreign-account"),
        (request_id + "-foreign", account.id),
    ):
        with pytest.raises(ProviderAttemptReconciliationError):
            storage.resolve_provider_attempt_reconciliation(
                request_id=rejected_request, account_id=rejected_account,
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=actual_cost,
                reconciled_by="owner-l1", note="foreign identity",
                now=NOW + timedelta(minutes=5),
            )
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before


def test_invalid_settled_topic_state_stays_reviewable_without_maintenance_mutation(
    settings, storage, account, monkeypatch,
):
    _, _, job, request_id, _, _ = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="settled-maintenance-invalid",
    )
    storage.conn.execute(
        "UPDATE model_usage SET task='research' WHERE request_id=?", (request_id,),
    )
    storage.conn.commit()

    first = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=5)),
    )
    assert first.needs_verification_count == 1
    assert first.settled_execution_recovery_count == 0
    assert first.settled_execution_blocked_count == 1
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    reviewable = _settled_recovery_snapshot(storage, job.id, request_id)

    second = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=6)),
    )
    assert second.settled_execution_recovery_count == 0
    assert second.settled_execution_blocked_count == 1
    assert _settled_recovery_snapshot(storage, job.id, request_id) == reviewable


def test_generated_topic_lineage_blocks_settled_failure_recovery_and_is_unreachable_via_finalizer_crash(
    settings, storage, account, monkeypatch,
):
    _, _, job, request_id, _, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="settled-generated-lineage",
    )
    run_id = storage.get_job(job.id).run_id
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Raw partial topic", question="Why?",
        score=50.0, status=TopicStatus.SCORED,
    ))
    storage.conn.execute(
        "INSERT INTO generated_topics (topic_id,account_id,job_id,run_id,request_id,"
        "candidate_index,is_selected,created_at) VALUES (?,?,?,?,?,0,0,?)",
        (int(topic.id), account.id, job.id, run_id, request_id, NOW.isoformat()),
    )
    storage.conn.commit()

    recovery = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=5)),
    )
    assert recovery.settled_execution_blocked_count == 1
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    before = _settled_recovery_snapshot(storage, job.id, request_id)
    with pytest.raises(ProviderAttemptReconciliationError, match="generated topics"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=actual_cost,
            reconciled_by="owner-l1", note="partial topic must not be guessed",
            now=NOW + timedelta(minutes=6),
        )
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before


def test_topic_finalization_crash_rolls_back_topics_then_settled_recovery_closes(
    settings, storage, account, monkeypatch,
):
    real, _, job = _prepare(
        settings, storage, account, key="finalization-transaction-crash", count=1,
    )
    caller = _FakeTopicCaller(_response(0.95))
    original_insert = storage._insert_topic

    def crash_after_topic_insert(topic):
        original_insert(topic)
        raise _CrashAfterSettledTopicUsage

    with monkeypatch.context() as crash:
        crash.setattr(storage, "_insert_topic", crash_after_topic_insert)
        with pytest.raises(_CrashAfterSettledTopicUsage):
            _run_once(real, storage, caller)

    request_id = f"{job.id}:topics:1"
    assert storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM generated_topics"
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()[0] == ProviderAttemptStatus.SETTLED.value
    recovery = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=5)),
    )
    assert recovery.settled_execution_recovery_count == 1
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert len(caller.calls) == 1


def test_settled_topic_recovery_failpoint_rolls_back_the_whole_maintenance_transaction(
    settings, storage, account, monkeypatch,
):
    _, _, job, request_id, _, _ = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="settled-recovery-failpoint",
    )
    before = _settled_recovery_snapshot(storage, job.id, request_id)

    def interrupt(point):
        if point == "AFTER_SETTLED_EXECUTION_RECOVERY":
            raise RuntimeError("forced settled topic recovery crash")

    with monkeypatch.context() as fault:
        fault.setattr(storage, "_recovery_fault_point", interrupt)
        with pytest.raises(RuntimeError, match="forced settled topic recovery crash"):
            storage.release_or_requeue_expired_leases(
                clock=FixedClock(NOW + timedelta(minutes=5)),
            )
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before

    recovered = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=5)),
    )
    assert recovered.settled_execution_recovery_count == 1
    assert storage.get_job(job.id).status is JobStatus.FAILED


@pytest.mark.parametrize("invalid_ledger", ["missing", "duplicate", "wrong_task"])
def test_sqlite_floor_rejects_settled_topic_recovery_without_one_topics_usage(
    settings, storage, account, monkeypatch, invalid_ledger,
):
    _, _, job, request_id, _, _ = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key=f"sqlite-ledger-{invalid_ledger}",
    )
    if invalid_ledger == "missing":
        storage.conn.execute("DELETE FROM model_usage WHERE request_id=?", (request_id,))
    elif invalid_ledger == "wrong_task":
        storage.conn.execute(
            "UPDATE model_usage SET task='research' WHERE request_id=?", (request_id,),
        )
    else:
        storage.conn.execute("DROP INDEX ux_model_usage_request_id")
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,"
            "output_tokens,cache_read_tokens,cache_write_tokens,web_search_requests,"
            "estimated_cost_usd,dry_run,request_id,is_legacy_usage,created_at) "
            "SELECT run_id,provider,model,task,input_tokens,output_tokens,"
            "cache_read_tokens,cache_write_tokens,web_search_requests,"
            "estimated_cost_usd,dry_run,request_id,is_legacy_usage,created_at "
            "FROM model_usage WHERE request_id=?", (request_id,),
        )
    storage.conn.execute(
        "UPDATE jobs SET status='NEEDS_VERIFICATION',lease_owner=NULL,"
        "lease_expires_at=NULL,last_error='test prestate' WHERE id=?", (job.id,),
    )
    storage.conn.commit()
    before = _settled_recovery_snapshot(storage, job.id, request_id)

    with pytest.raises(sqlite3.IntegrityError, match="consistent settled supported prestate"):
        storage.conn.execute(
            "INSERT INTO reconciliation_events (request_id,sequence_number,event_type,"
            "financial_resolution,execution_resolution,operator,note,"
            "previous_attempt_status,resulting_attempt_status,created_at,idempotency_key) "
            "VALUES (?,1,'EXECUTION_RECOVERY','CHARGED_KNOWN','EXECUTION_FAILED',"
            "'raw-writer','invalid ledger','SETTLED','SETTLED',?,?)",
            (request_id, NOW.isoformat(), f"raw-{invalid_ledger}"),
        )
    storage.conn.rollback()
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before


def test_sqlite_floors_reject_partial_settled_topic_terminalization_and_financial_rewrite(
    settings, storage, account, monkeypatch,
):
    _, _, job, request_id, _, actual_cost = _settled_topic_generation_crash(
        settings, storage, account, monkeypatch, key="sqlite-partial-settled",
    )
    run_id = storage.get_job(job.id).run_id
    storage.conn.execute(
        "UPDATE jobs SET status='NEEDS_VERIFICATION',lease_owner=NULL,"
        "lease_expires_at=NULL,last_error='test prestate' WHERE id=?", (job.id,),
    )
    storage.conn.commit()
    before = _settled_recovery_snapshot(storage, job.id, request_id)

    with pytest.raises(sqlite3.IntegrityError, match="settled run terminalization"):
        storage.conn.execute(
            "UPDATE runs SET status='FAILED',finished_at=? WHERE id=?",
            (NOW.isoformat(), run_id),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="settled execution terminalization"):
        storage.conn.execute(
            "UPDATE jobs SET status='FAILED',finished_at=? WHERE id=?",
            (NOW.isoformat(), job.id),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='NEEDS_RECONCILIATION',"
            "actual_cost_usd=NULL,settled_at=NULL,error_code='financial rewrite' "
            "WHERE request_id=?", (request_id,),
        )
    storage.conn.rollback()
    assert _settled_recovery_snapshot(storage, job.id, request_id) == before

    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=actual_cost,
        reconciled_by="owner-l1", note="valid atomic settled recovery",
        now=NOW + timedelta(minutes=5),
    )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        storage.conn.execute(
            "UPDATE jobs SET external_effect_started_at=? WHERE id=?",
            (NOW.isoformat(), job.id),
        )
    storage.conn.rollback()


def test_success_path_produces_one_selected_topic_with_full_lineage(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=3)
    caller = _FakeTopicCaller(_response(0.95, 0.70, 0.2))

    result = _run_once(real, storage, caller)
    assert result.status is WorkerIterationStatus.DONE
    assert len(caller.calls) == 1
    # The prompt input comes from the frozen snapshot, never from mutable rows.
    assert caller.calls[0][0].niche == account.niche
    assert caller.calls[0][1] == intent.candidate_count

    done = storage.get_job(job.id)
    assert done.status is JobStatus.DONE
    run = storage.get_run(done.run_id)
    assert run.status is RunStatus.SUCCESS
    assert run.workflow is WorkflowType.TOPIC_GENERATION

    attempts = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchall()
    assert len(attempts) == 1
    assert attempts[0]["stage"] == "topics"
    assert attempts[0]["attempt_no"] == 1
    assert attempts[0]["request_id"] == f"{job.id}:topics:1"
    assert attempts[0]["status"] == ProviderAttemptStatus.SETTLED.value

    usage = storage.conn.execute(
        "SELECT * FROM model_usage WHERE request_id=?", (attempts[0]["request_id"],),
    ).fetchall()
    assert len(usage) == 1
    assert usage[0]["task"] == "topics"
    assert usage[0]["dry_run"] == 0
    assert abs(float(run.cost_usd) - float(usage[0]["estimated_cost_usd"])) < 1e-9

    lineage = storage.list_generated_topics_for_run(done.run_id)
    assert [row.candidate_index for row in lineage] == [0, 1, 2]
    assert sum(1 for row in lineage if row.is_selected) == 1
    assert {row.request_id for row in lineage} == {attempts[0]["request_id"]}
    assert {row.job_id for row in lineage} == {job.id}

    statuses = {
        row.topic_id: storage.conn.execute(
            "SELECT status FROM topics WHERE id=?", (row.topic_id,),
        ).fetchone()["status"]
        for row in lineage
    }
    selected = [row for row in lineage if row.is_selected][0]
    assert statuses[selected.topic_id] == TopicStatus.SELECTED.value
    assert sorted(statuses.values()) == ["REJECTED", "SCORED", "SELECTED"]


def test_lineage_survives_reopening_the_database(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, count=2)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95, 0.1)))
    run_id = storage.get_job(job.id).run_id
    storage.close()

    reopened = SqliteStorage.open(settings.db_path)
    try:
        rows = reopened.conn.execute(
            "SELECT g.*, p.request_id AS attempt_request, p.status AS attempt_status,"
            " u.id AS usage_id, u.task AS usage_task "
            "FROM generated_topics g "
            "JOIN provider_attempts p ON p.request_id=g.request_id "
            "JOIN model_usage u ON u.request_id=g.request_id "
            "WHERE g.run_id=? ORDER BY g.candidate_index",
            (run_id,),
        ).fetchall()
        assert len(rows) == 2
        assert {row["job_id"] for row in rows} == {job.id}
        assert {row["attempt_status"] for row in rows} == {"SETTLED"}
        assert {row["usage_task"] for row in rows} == {"topics"}
        assert len({row["usage_id"] for row in rows}) == 1
        assert sum(int(row["is_selected"]) for row in rows) == 1
    finally:
        reopened.close()


def test_at_most_one_selected_per_run_even_when_many_candidates_qualify(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=3)
    # All three clear article_min_score; only one may win this execution.
    _run_once(real, storage, _FakeTopicCaller(_response(0.95, 0.94, 0.93)))

    run_id = storage.get_job(job.id).run_id
    lineage = storage.list_generated_topics_for_run(run_id)
    assert sum(1 for row in lineage if row.is_selected) == 1
    statuses = [
        storage.conn.execute(
            "SELECT status FROM topics WHERE id=?", (row.topic_id,),
        ).fetchone()["status"] for row in lineage
    ]
    assert statuses.count("SELECTED") == 1
    assert statuses.count("SCORED") == 2


def test_tie_is_broken_deterministically_by_response_order(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, count=3)
    _run_once(real, storage, _FakeTopicCaller(
        _response(0.9, 0.9, 0.9, titles=["Alpha one", "Beta two", "Gamma three"]),
    ))
    run_id = storage.get_job(job.id).run_id
    winner = [r for r in storage.list_generated_topics_for_run(run_id) if r.is_selected][0]
    assert winner.candidate_index == 0


def test_database_floor_forbids_two_selected_rows_in_one_run(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=2)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95, 0.1)))
    run_id = storage.get_job(job.id).run_id
    row = storage.conn.execute(
        "SELECT * FROM generated_topics WHERE run_id=? AND is_selected=0", (run_id,),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO generated_topics (topic_id,account_id,job_id,run_id,"
            "request_id,candidate_index,is_selected,created_at) VALUES "
            "(?,?,?,?,?,?,1,'2026-07-21 12:00:00')",
            (
                row["topic_id"], row["account_id"], row["job_id"], run_id,
                row["request_id"], 99,
            ),
        )
    storage.conn.rollback()


def test_many_historical_selected_topics_per_account_stay_legal(
    settings, storage, account,
):
    storage.ensure_account(account)
    for index in range(3):
        storage.add_topic(account.id, Topic(
            account_id=account.id, title=f"Historical selected {index}",
            question="Why?", score=90.0, status=TopicStatus.SELECTED,
            source="owner",
        ))
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM topics WHERE account_id=? AND status='SELECTED'",
        (account.id,),
    ).fetchone()["c"] == 3

    real, intent, job = _prepare(settings, storage, account, count=1)
    result = _run_once(real, storage, _FakeTopicCaller(_response(0.95)))
    assert result.status is WorkerIterationStatus.DONE
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM topics WHERE account_id=? AND status='SELECTED'",
        (account.id,),
    ).fetchone()["c"] == 4


def test_zero_selected_is_a_legal_success_when_nothing_reaches_the_threshold(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=2)
    result = _run_once(real, storage, _FakeTopicCaller(_response(0.2, 0.1)))

    assert result.status is WorkerIterationStatus.DONE
    done = storage.get_job(job.id)
    assert done.status is JobStatus.DONE
    assert storage.get_run(done.run_id).status is RunStatus.SUCCESS
    lineage = storage.list_generated_topics_for_run(done.run_id)
    assert len(lineage) == 2
    assert not any(row.is_selected for row in lineage)


# --- dedup -------------------------------------------------------------------

def test_duplicate_of_an_existing_account_topic_is_marked_and_never_selected(
    settings, storage, account,
):
    storage.ensure_account(account)
    existing = storage.add_topic(account.id, Topic(
        account_id=account.id, title=_DISTINCT_TITLES[0], question="Why?",
        score=90.0, status=TopicStatus.SELECTED, source="owner",
    ))
    real, intent, job = _prepare(settings, storage, account, count=2)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95, 0.94)))

    run_id = storage.get_job(job.id).run_id
    lineage = storage.list_generated_topics_for_run(run_id)
    first = storage.conn.execute(
        "SELECT * FROM topics WHERE id=?", (lineage[0].topic_id,),
    ).fetchone()
    assert first["status"] == TopicStatus.DUPLICATE.value
    assert first["duplicate_of"] == int(existing.id)
    assert not lineage[0].is_selected
    # The winner is the non-duplicate runner-up.
    assert lineage[1].is_selected


def test_duplicate_inside_one_batch_is_detected(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, count=2)
    _run_once(real, storage, _FakeTopicCaller(
        _response(0.95, 0.94, titles=["Why queues form", "Why queues form"]),
    ))
    run_id = storage.get_job(job.id).run_id
    lineage = storage.list_generated_topics_for_run(run_id)
    statuses = [
        storage.conn.execute(
            "SELECT status FROM topics WHERE id=?", (row.topic_id,),
        ).fetchone()["status"] for row in lineage
    ]
    assert statuses == [TopicStatus.SELECTED.value, TopicStatus.DUPLICATE.value]
    assert sum(1 for row in lineage if row.is_selected) == 1


# --- walidacja wymiarów scoringu ---------------------------------------------

def test_score_breakdown_contract_is_exact():
    good = TopicIdea(
        title="T", question="Q",
        score_breakdown={name: 0.5 for name in DIMENSIONS},
    )
    assert validate_score_breakdown(good, dimensions=DIMENSIONS, label="t") == {
        name: 0.5 for name in DIMENSIONS
    }

    cases = [
        ({name: 0.5 for name in DIMENSIONS[:-1]}, "SCORE_DIMENSION_MISSING"),
        ({**{n: 0.5 for n in DIMENSIONS}, "extra": 0.5}, "SCORE_DIMENSION_UNKNOWN"),
        ({**{n: 0.5 for n in DIMENSIONS}, DIMENSIONS[0]: 2.0}, "SCORE_DIMENSION_OUT_OF_RANGE"),
        ({**{n: 0.5 for n in DIMENSIONS}, DIMENSIONS[0]: float("nan")}, "SCORE_DIMENSION_NOT_FINITE"),
        ({**{n: 0.5 for n in DIMENSIONS}, DIMENSIONS[0]: "x"}, "SCORE_DIMENSION_NOT_NUMERIC"),
    ]
    for breakdown, code in cases:
        with pytest.raises(TopicGenerationResultError) as exc:
            validate_score_breakdown(
                TopicIdea(title="T", question="Q", score_breakdown=breakdown),
                dimensions=DIMENSIONS, label="t",
            )
        assert exc.value.code == code

    with pytest.raises(TopicGenerationResultError) as empty:
        validate_score_breakdown(
            TopicIdea(title="  ", question="Q",
                      score_breakdown={n: 0.5 for n in DIMENSIONS}),
            dimensions=DIMENSIONS, label="t",
        )
    assert empty.value.code == "CANDIDATE_TITLE_EMPTY"


# --- macierz błędów ----------------------------------------------------------

def test_missing_approval_means_no_request_no_usage_no_topics(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    caller = _FakeTopicCaller()

    result = _run_once(real, storage, caller)
    assert result.status is WorkerIterationStatus.FAILED
    assert caller.calls == []
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()["c"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM model_usage").fetchone()["c"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM generated_topics"
    ).fetchone()["c"] == 0


def test_expired_approval_is_refused_before_any_request(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    _approve(storage, job.id, account, hours=1)
    caller = _FakeTopicCaller()
    later = FixedClock(NOW + timedelta(hours=3))

    result = _run_once(real, storage, caller, clock=later)
    assert result.status is WorkerIterationStatus.FAILED
    assert caller.calls == []
    approval = storage.get_topic_generation_approval_for_job(job.id)
    assert approval.consumed_at is None
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts"
    ).fetchone()["c"] == 0


def test_approval_is_consumed_exactly_once_and_replay_is_refused(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=1)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95)))

    approval = storage.get_topic_generation_approval_for_job(job.id)
    assert approval.consumed_at is not None
    # A consumed approval can never be reset, nor consumed a second time.
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE topic_generation_approvals SET consumed_at=NULL WHERE job_id=?",
            (job.id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE topic_generation_approvals SET consumed_at='2026-07-21 13:00:00' "
            "WHERE job_id=?", (job.id,),
        )
    storage.conn.rollback()


def test_mutating_the_payload_after_approval_blocks_the_reservation(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    # The 0020 floor freezes the payload of an enqueued topic-generation job.
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE jobs SET payload_json=? WHERE id=?",
            (json.dumps({**job.payload, "max_cost_usd": "9.000000"}), job.id),
        )
    storage.conn.rollback()


def test_approval_of_a_different_model_or_higher_cap_is_refused(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=False)
    _approve(storage, job.id, account)
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="w", run_id="r", clock=FixedClock(NOW),
    )
    _, fingerprint = frozen_topic_generation_intent_json(job.payload)
    canonical_json = json.loads(
        storage.get_topic_generation_approval_for_job(job.id).execution_intent_json
    )
    stored_json = storage.get_topic_generation_approval_for_job(
        job.id
    ).execution_intent_json

    for kwargs, code in [
        ({"model": "other-model"}, "APPROVAL_MODEL_MISMATCH"),
        ({"cap_usd": "9.000000"}, "APPROVAL_CAP_EXCEEDED"),
        ({"max_tokens": 4096}, "APPROVAL_MAX_TOKENS_MISMATCH"),
        ({"account_id": "someone_else"}, "APPROVAL_ACCOUNT_MISMATCH"),
        ({"intent_fingerprint": "f" * 64}, "INTENT_MISMATCH"),
    ]:
        base = {
            "account_id": account.id, "model": intent.model,
            "cap_usd": intent.cap_usd, "max_tokens": intent.max_tokens,
            "canonical_intent_json": stored_json,
            "intent_fingerprint": fingerprint,
            "current_ts": "2026-07-21 12:00:00",
        }
        base.update(kwargs)
        with pytest.raises(TopicGenerationAuthorizationError) as exc:
            storage._require_usable_topic_generation_approval(job.id, **base)
        assert exc.value.code == code
    assert canonical_json["account_id"] == account.id


def test_parse_failure_books_the_cost_but_writes_no_topic(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    caller = _FakeTopicCaller("this is not json at all")

    result = _run_once(real, storage, caller)
    assert result.status is WorkerIterationStatus.FAILED
    assert len(caller.calls) == 1

    attempt = storage.conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.SETTLED.value
    assert float(attempt["actual_cost_usd"]) > 0
    usage = storage.conn.execute("SELECT * FROM model_usage").fetchall()
    assert len(usage) == 1
    assert usage[0]["task"] == "topics" and usage[0]["dry_run"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM generated_topics"
    ).fetchone()["c"] == 0
    done = storage.get_job(job.id)
    assert done.status is JobStatus.FAILED
    assert storage.get_run(done.run_id).status is RunStatus.FAILED


def test_scoring_rejection_books_the_cost_but_writes_no_topic(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    # Schema-valid response whose breakdown misses a required dimension.
    bad = json.dumps({"topics": [{
        "title": "Partial", "question": "Why?",
        "score_breakdown": {DIMENSIONS[0]: 0.9},
    }]})
    result = _run_once(real, storage, _FakeTopicCaller(bad))

    assert result.status is WorkerIterationStatus.FAILED
    assert len(storage.conn.execute("SELECT * FROM model_usage").fetchall()) == 1
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.SETTLED.value


def test_provider_failure_without_usage_settles_no_cost_and_writes_nothing(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    caller = _FakeTopicCaller(error=LLMProviderError("boom", model="m"))

    result = _run_once(real, storage, caller)
    assert result.status in {
        WorkerIterationStatus.FAILED, WorkerIterationStatus.NEEDS_VERIFICATION,
    }
    assert storage.conn.execute("SELECT COUNT(*) c FROM model_usage").fetchone()["c"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    # The request crossed the boundary, so the outcome is explicitly reviewable.
    assert attempt["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value


def test_actual_cost_over_reservation_escalates_without_a_topic(
    settings, storage, account,
):
    # The reservation is the (small) pessimistic projection, which the cap
    # admits; the returned usage is then far larger, so the real cost exceeds
    # the reservation.  Usage is persisted, the attempt becomes
    # NEEDS_RECONCILIATION, and no topic is written.
    real, intent, job = _prepare(settings, storage, account, cap=1.0, count=1)
    tight = replace(real, max_daily_cost_usd=100.0, max_monthly_cost_usd=100.0)
    caller = _FakeTopicCaller(
        _response(0.95),
        usage=Usage(input_tokens=5_000_000, output_tokens=5_000_000),
    )
    result = _run_once(tight, storage, caller)

    assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
    assert len(storage.conn.execute("SELECT * FROM model_usage").fetchall()) == 1
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM generated_topics"
    ).fetchone()["c"] == 0
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value


def test_unknown_outcome_never_requeues_and_never_creates_a_second_attempt(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    caller = _FakeTopicCaller(error=LLMProviderError("timeout", model="m"))
    _run_once(real, storage, caller)

    escalated = storage.get_job(job.id)
    assert escalated.status is JobStatus.NEEDS_VERIFICATION
    assert escalated.lease_owner is None

    # A later worker pass must not pick it up again.
    second = _run_once(real, storage, _FakeTopicCaller())
    assert second.status is WorkerIterationStatus.IDLE
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()["c"] == 1
    assert len(caller.calls) == 1


def test_second_attempt_number_is_unrepresentable(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, count=1)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95)))
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
            "execution_intent_fingerprint,reserved_amount_usd,reserved_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                job.id, "topics", 2, f"{job.id}:topics:2", "RESERVED",
                "a" * 64, 0.5, "2026-07-21 12:30:00",
            ),
        )
    storage.conn.rollback()


def test_attempt_without_a_consumed_approval_is_unrepresentable(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, approve=True)
    _, fingerprint = frozen_topic_generation_intent_json(job.payload)
    # The approval exists but has not been consumed yet.
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
            "execution_intent_fingerprint,reserved_amount_usd,reserved_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                job.id, "topics", 1, f"{job.id}:topics:1", "RESERVED",
                fingerprint, 0.5, "2026-07-21 12:30:00",
            ),
        )
    storage.conn.rollback()


def test_kill_switch_blocks_before_any_request(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    storage.set_system_flag("kill_switch", True, updated_by="t", reason="stop")
    caller = _FakeTopicCaller()
    result = _run_once(real, storage, caller)

    assert result.status is WorkerIterationStatus.BLOCKED
    assert caller.calls == []
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts"
    ).fetchone()["c"] == 0
    assert storage.get_topic_generation_approval_for_job(job.id).consumed_at is None


def test_paid_actions_flag_is_still_required(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    storage.set_system_flag("paid_actions_enabled", False, updated_by="t", reason="stop")
    caller = _FakeTopicCaller()
    result = _run_once(real, storage, caller)

    assert result.status is WorkerIterationStatus.FAILED
    assert caller.calls == []
    assert storage.get_topic_generation_approval_for_job(job.id).consumed_at is None


@pytest.mark.parametrize("limit_field", ["max_daily_cost_usd", "max_monthly_cost_usd"])
def test_budget_limits_block_before_any_request(settings, storage, account, limit_field):
    real, intent, job = _prepare(settings, storage, account)
    tight = replace(real, **{limit_field: 0.000001})
    caller = _FakeTopicCaller()

    result = _run_once(tight, storage, caller)
    assert result.status is not WorkerIterationStatus.DONE
    assert caller.calls == []
    assert storage.conn.execute("SELECT COUNT(*) c FROM model_usage").fetchone()["c"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0


def test_offline_only_worker_refuses_paid_topic_generation(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    clock = FixedClock(NOW)
    policy = PolicyEngine(real, storage, clock)
    caller = _FakeTopicCaller()
    kwargs = _install_fake_caller({
        "settings": real, "storage": storage, "policy": policy, "clock": clock,
        "allow_real_topic_generation": False,
    }, caller)
    worker = Worker(
        storage=storage, policy=policy, dispatcher=JobDispatcher(**kwargs),
        lease_owner="offline-worker", lease_seconds=120,
        heartbeat_interval_seconds=5.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=clock,
    )
    result = worker.run_once()
    assert result.status is WorkerIterationStatus.FAILED
    assert caller.calls == []


# --- fence, concurrency, restart --------------------------------------------

def test_foreign_owner_and_stale_lease_cannot_finalize(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    lease = storage.claim_next_job("real-owner", 120, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "real-owner", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "real-owner", "topicgen-run", clock=FixedClock(NOW),
    )
    assert initialized.created

    foreign = JobExecutionContext(
        job_id=job.id, lease_owner="intruder", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.assert_topic_generation_execution_active(foreign)

    expired = JobExecutionContext(
        job_id=job.id, lease_owner="real-owner", run_id=initialized.run.id,
        clock=FixedClock(NOW + timedelta(hours=5)),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.assert_topic_generation_execution_active(expired)


def test_fence_refuses_a_research_job_and_a_wrong_run(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account)
    storage.claim_next_job("owner", 120, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "owner", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "owner", "topicgen-run", clock=FixedClock(NOW),
    )
    wrong_run = JobExecutionContext(
        job_id=job.id, lease_owner="owner", run_id="not-this-run",
        clock=FixedClock(NOW),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.assert_topic_generation_execution_active(wrong_run)
    assert initialized.run.workflow is WorkflowType.TOPIC_GENERATION


def test_two_workers_produce_exactly_one_request(settings, storage, account):
    real, intent, job = _prepare(settings, storage, account, count=1)
    caller = _FakeTopicCaller(_response(0.95))
    results = []
    barrier = threading.Barrier(2)

    def run(name):
        store = SqliteStorage.open(real.db_path)
        try:
            worker = _worker(real, store, caller, lease_owner=name)
            barrier.wait(timeout=10)
            results.append(worker.run_once())
        finally:
            store.close()

    threads = [threading.Thread(target=run, args=(f"w{i}",)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(caller.calls) == 1
    assert sum(1 for r in results if r.status is WorkerIterationStatus.DONE) == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()["c"] == 1
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM model_usage"
    ).fetchone()["c"] == 1


def test_restart_before_the_request_leaves_nothing_and_can_be_recovered(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    storage.claim_next_job("crashed", 1, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "crashed", clock=FixedClock(NOW))

    # The lease expires before any run or attempt existed.  A paid
    # topic-generation job is enqueued with max_attempts=1, so recovery
    # terminalizes it instead of retrying — and, crucially, the one-shot L1
    # approval is still unconsumed and no attempt was ever created.
    recovery = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(hours=1)),
    )
    assert recovery.requeued_count == 0
    assert recovery.failed_count == 1
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM provider_attempts"
    ).fetchone()["c"] == 0
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    assert storage.get_topic_generation_approval_for_job(job.id).consumed_at is None


def test_restart_after_request_started_never_returns_to_the_queue(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    storage.claim_next_job("crashed", 1, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "crashed", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "crashed", "topicgen-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="crashed", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    attempt = storage.begin_provider_attempt(
        execution, stage="topics", attempt_no=1, max_cost_usd=0.5,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    recovery = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(hours=1)),
    )
    assert recovery.requeued_count == 0
    assert recovery.needs_verification_count == 1
    recovered = storage.get_job(job.id)
    assert recovered.status is JobStatus.NEEDS_VERIFICATION
    assert recovered.lease_owner is None
    escalated = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert escalated["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value


def test_reserved_but_unstarted_attempt_escalates_without_a_second_request(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account)
    storage.claim_next_job("crashed", 1, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "crashed", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "crashed", "topicgen-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="crashed", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    storage.begin_provider_attempt(
        execution, stage="topics", attempt_no=1, max_cost_usd=0.5,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(hours=1)),
    )
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    row = storage.conn.execute(
        "SELECT status,error_code FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert row["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value
    assert row["error_code"] == "LEASE_EXPIRED_BEFORE_REQUEST_STARTED"


def test_finalization_is_refused_when_state_changed_after_validation(
    settings, storage, account,
):
    real, intent, job = _prepare(settings, storage, account, count=1)
    storage.claim_next_job("owner", 120, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "owner", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "owner", "topicgen-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="owner", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    attempt = storage.begin_provider_attempt(
        execution, stage="topics", attempt_no=1, max_cost_usd=0.5,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    from app.models import TopicGenerationCandidate

    candidate = TopicGenerationCandidate(
        topic=Topic(account_id=account.id, title="X", question="Q", score=90.0,
                    status=TopicStatus.SELECTED, source="anthropic"),
        candidate_index=0, is_selected=True,
    )
    # The attempt never settled, so finalization must refuse outright.
    with pytest.raises(StaleJobExecutionError):
        storage.finalize_topic_generation_success(
            execution, request_id=attempt.request_id, candidates=[candidate],
            total_cost_usd=0.0,
        )
    assert storage.conn.execute("SELECT COUNT(*) c FROM topics").fetchone()["c"] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM generated_topics"
    ).fetchone()["c"] == 0


def test_finalization_refuses_more_than_one_selected_candidate(
    settings, storage, account,
):
    from app.models import TopicGenerationCandidate

    real, intent, job = _prepare(settings, storage, account)
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="owner", run_id="r", clock=FixedClock(NOW),
    )
    candidates = [
        TopicGenerationCandidate(
            topic=Topic(account_id=account.id, title=f"T{i}", question="Q",
                        score=90.0, status=TopicStatus.SELECTED),
            candidate_index=i, is_selected=True,
        ) for i in range(2)
    ]
    with pytest.raises(TopicGenerationResultError) as exc:
        storage.finalize_topic_generation_success(
            execution, request_id="x", candidates=candidates, total_cost_usd=0.0,
        )
    assert exc.value.code == "MULTIPLE_SELECTED"


def test_repeating_a_successful_finalization_is_refused_without_mutation(
    settings, storage, account,
):
    from app.models import TopicGenerationCandidate

    real, intent, job = _prepare(settings, storage, account, count=1)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95)))
    done = storage.get_job(job.id)
    request_id = f"{job.id}:topics:1"
    before_topics = storage.conn.execute(
        "SELECT COUNT(*) c FROM topics"
    ).fetchone()["c"]

    execution = JobExecutionContext(
        job_id=job.id, lease_owner="topicgen-worker", run_id=done.run_id,
        clock=FixedClock(NOW),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.finalize_topic_generation_success(
            execution, request_id=request_id,
            candidates=[TopicGenerationCandidate(
                topic=Topic(account_id=account.id, title="Replay", question="Q",
                            score=90.0, status=TopicStatus.SELECTED),
                candidate_index=0, is_selected=True,
            )],
            total_cost_usd=0.0,
        )
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM topics"
    ).fetchone()["c"] == before_topics
    assert len(storage.list_generated_topics_for_run(done.run_id)) == 1


def test_not_charged_terminalizes_topic_generation_and_unblocks_account(
    settings, storage, account,
):
    real, intent, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key="not-charged",
    )
    queue = storage.list_provider_attempts_needing_reconciliation(
        account_id=account.id,
    )
    assert [a.request_id for a in queue] == [request_id]
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
    )
    assert preview.reservation_active is True
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="op", note="provider confirmed no charge",
        expected_version_token=preview.version_token,
    )

    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert result.usage_id is None
    terminal_job = storage.get_job(job.id)
    assert terminal_job.status is JobStatus.FAILED
    assert terminal_job.reserved_cost_usd == 0.0
    assert terminal_job.budget_reserved_at is None
    assert terminal_job.lease_owner is None
    assert terminal_job.external_effect_started_at is None
    assert storage.get_run(terminal_job.run_id).status is RunStatus.FAILED
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM research_runs WHERE id=?", (terminal_job.run_id,),
    ).fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM generated_topics").fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE status IN "
        "('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')"
    ).fetchone()[0] == 0
    assert len(caller.calls) == 1

    next_job = storage.enqueue_job(
        _job(account, "after-not-charged", _payload(intent)),
    )
    assert next_job.status is JobStatus.QUEUED
    assert storage.get_topic_generation_approval_for_job(job.id).consumed_at is not None
    assert storage.get_topic_generation_approval_for_job(next_job.id) is None


def test_terminal_reconciliation_of_topic_generation_is_explicitly_refused(
    settings, storage, account,
):
    """The historical node now pins the still-unsupported finalized-result arm."""
    _, _, _, request_id, _ = _needs_topic_reconciliation(
        settings, storage, account, key="finalized-result-refused",
    )
    with pytest.raises(
        ProviderAttemptReconciliationError,
        match="supports EXECUTION_FAILED only",
    ):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.RESULT_ALREADY_FINALIZED,
            actual_cost_usd=None, reconciled_by="op", note="not a finalized result",
        )
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
    ).fetchone()["status"] == ProviderAttemptStatus.NEEDS_RECONCILIATION.value


def test_charge_unknown_records_one_idempotent_observation_and_keeps_block(
    settings, storage, account,
):
    _, intent, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key="unknown-observation",
    )
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op", note="invoice is not available",
    )
    replay = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op", note="invoice is not available",
    )
    assert result.observed is True
    assert replay.idempotent is True
    events = storage.list_reconciliation_events(
        request_id=request_id, account_id=account.id,
    )
    observations = [
        event for event in events
        if event.event_type in (
            ReconciliationEventType.UNRESOLVED_OBSERVATION,
            ReconciliationEventType.FOLLOW_UP,
        )
    ]
    assert len(observations) == 1
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION
    preview = storage.preview_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
    )
    assert preview.attempt_status is ProviderAttemptStatus.NEEDS_RECONCILIATION
    assert preview.reservation_active is True
    assert storage.conn.execute(
        "SELECT reserved_amount_usd FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()[0] > 0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert len(caller.calls) == 1
    with pytest.raises(JobConflictError):
        storage.enqueue_job(_job(account, "blocked-by-unknown", _payload(intent)))


@pytest.mark.parametrize(
    ("financial", "actual_cost", "terminal_status", "usage_count"),
    [
        (FinancialResolution.NOT_CHARGED, None, ProviderAttemptStatus.RECONCILED_RELEASED, 0),
        (FinancialResolution.CHARGED_KNOWN, "0.0123455", ProviderAttemptStatus.RECONCILED_SETTLED, 1),
    ],
)
def test_charge_unknown_can_later_reach_each_terminal_financial_decision(
    settings, storage, account, financial, actual_cost, terminal_status, usage_count,
):
    _, intent, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key=f"unknown-then-{financial.value.lower()}",
    )
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGE_UNKNOWN,
        execution_resolution=ExecutionResolution.MANUAL_REVIEW_REMAINS_REQUIRED,
        actual_cost_usd=None, reconciled_by="op", note="waiting for invoice",
    )
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=financial,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=actual_cost, reconciled_by="op", note="invoice resolved",
    )
    assert result.attempt.status is terminal_status
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchone()[0] == usage_count
    assert storage.enqueue_job(
        _job(account, f"after-{financial.value.lower()}", _payload(intent))
    ).status is JobStatus.QUEUED
    assert len(caller.calls) == 1


def test_charged_known_writes_exactly_one_topics_usage_and_replay_is_idempotent(
    settings, storage, account,
):
    _, intent, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key="charged-known",
    )
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.0123455", reconciled_by="op", note="invoice verified",
    )
    replay = storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.012346", reconciled_by="op", note="invoice verified",
    )
    usage = storage.conn.execute(
        "SELECT * FROM model_usage WHERE request_id=?", (request_id,),
    ).fetchall()
    assert result.usage_id is not None
    assert replay.idempotent is True
    assert len(usage) == 1
    assert usage[0]["run_id"] == storage.get_job(job.id).run_id
    assert usage[0]["request_id"] == request_id
    assert usage[0]["task"] == "topics"
    assert usage[0]["provider"] == intent.provider
    assert usage[0]["model"] == intent.model
    assert usage[0]["estimated_cost_usd"] == pytest.approx(0.012346)
    assert storage.get_run(storage.get_job(job.id).run_id).cost_usd == pytest.approx(0.012346)
    assert storage.get_job(job.id).reserved_cost_usd == 0.0
    assert storage.conn.execute(
        "SELECT COUNT(*) FROM provider_attempts WHERE status IN "
        "('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION')"
    ).fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0
    assert storage.conn.execute("SELECT COUNT(*) FROM generated_topics").fetchone()[0] == 0
    assert len(caller.calls) == 1


@pytest.mark.parametrize("fault", list(ReconciliationFaultPoint))
def test_topic_generation_reconciliation_faults_roll_back_every_related_row(
    settings, storage, account, monkeypatch, fault,
):
    _, _, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key=f"rollback-{fault.value.lower()}",
    )
    run_id = storage.get_job(job.id).run_id
    before = {
        "attempt": tuple(storage.conn.execute(
            "SELECT status,reconciled_at,reconciliation_resolution FROM provider_attempts WHERE request_id=?",
            (request_id,),
        ).fetchone()),
        "job": tuple(storage.conn.execute(
            "SELECT status,reserved_cost_usd,budget_reserved_at,external_effect_started_at FROM jobs WHERE id=?",
            (job.id,),
        ).fetchone()),
        "run": tuple(storage.conn.execute(
            "SELECT status,cost_usd,finished_at FROM runs WHERE id=?", (run_id,),
        ).fetchone()),
        "usage": storage.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
        ).fetchone()[0],
        "events": storage.conn.execute(
            "SELECT COUNT(*) FROM reconciliation_events WHERE request_id=?", (request_id,),
        ).fetchone()[0],
    }

    def interrupt(point):
        if point is fault:
            raise RuntimeError(f"forced topic reconciliation fault: {point.value}")

    monkeypatch.setattr(storage, "_reconciliation_fault_point", interrupt)
    with pytest.raises(RuntimeError, match="forced topic reconciliation fault"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.CHARGED_KNOWN,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd="0.020000", reconciled_by="op", note="rollback proof",
        )
    after = {
        "attempt": tuple(storage.conn.execute(
            "SELECT status,reconciled_at,reconciliation_resolution FROM provider_attempts WHERE request_id=?",
            (request_id,),
        ).fetchone()),
        "job": tuple(storage.conn.execute(
            "SELECT status,reserved_cost_usd,budget_reserved_at,external_effect_started_at FROM jobs WHERE id=?",
            (job.id,),
        ).fetchone()),
        "run": tuple(storage.conn.execute(
            "SELECT status,cost_usd,finished_at FROM runs WHERE id=?", (run_id,),
        ).fetchone()),
        "usage": storage.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
        ).fetchone()[0],
        "events": storage.conn.execute(
            "SELECT COUNT(*) FROM reconciliation_events WHERE request_id=?", (request_id,),
        ).fetchone()[0],
    }
    assert after == before
    assert len(caller.calls) == 1


def test_topic_reconciliation_rejects_foreign_account_and_unknown_request(
    settings, storage, account,
):
    _, _, _, request_id, _ = _needs_topic_reconciliation(
        settings, storage, account, key="foreign-input",
    )
    for rejected_request, rejected_account in (
        (request_id, "foreign-account"),
        (request_id + "-wrong", account.id),
    ):
        with pytest.raises(ProviderAttemptReconciliationError):
            storage.resolve_provider_attempt_reconciliation(
                request_id=rejected_request, account_id=rejected_account,
                financial_resolution=FinancialResolution.NOT_CHARGED,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=None, reconciled_by="op", note="must reject",
            )


@pytest.mark.parametrize(("column", "value"), [("stage", "research"), ("attempt_no", 2)])
def test_topic_reconciliation_rejects_wrong_stage_or_attempt_number(
    settings, storage, account, column, value,
):
    _, _, _, request_id, _ = _needs_topic_reconciliation(
        settings, storage, account, key=f"wrong-{column}",
    )
    storage.conn.execute("DROP TRIGGER provider_attempts_identity_is_immutable")
    storage.conn.execute("DROP TRIGGER provider_attempts_controlled_transition")
    storage.conn.execute(
        f"UPDATE provider_attempts SET {column}=? WHERE request_id=?",
        (value, request_id),
    )
    storage.conn.commit()
    with pytest.raises(ProviderAttemptReconciliationError, match="lineage"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="op", note="must reject",
        )


def test_topic_reconciliation_rejects_a_research_run_in_its_lineage(
    settings, storage, account,
):
    _, _, job, request_id, _ = _needs_topic_reconciliation(
        settings, storage, account, key="foreign-research-lineage",
    )
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Foreign research lineage", question="Why?",
        score=50.0, status=TopicStatus.SELECTED,
    ))
    run_id = storage.get_job(job.id).run_id
    storage.conn.execute(
        "INSERT INTO research_runs (id,account_id,topic_id,flow,status,total_cost_usd) "
        "VALUES (?,?,?,?,?,?)",
        (run_id, account.id, int(topic.id), "single", "PENDING", 0.0),
    )
    storage.conn.commit()
    with pytest.raises(ProviderAttemptReconciliationError, match="lineage"):
        storage.resolve_provider_attempt_reconciliation(
            request_id=request_id, account_id=account.id,
            financial_resolution=FinancialResolution.NOT_CHARGED,
            execution_resolution=ExecutionResolution.EXECUTION_FAILED,
            actual_cost_usd=None, reconciled_by="op", note="must reject",
        )


def test_unstarted_release_failure_can_be_closed_by_public_resolver(
    settings, storage, account,
):
    _, _, job = _prepare(settings, storage, account, key="release-failure", count=1)
    storage.claim_next_job("owner", 120, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "owner", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "owner", "release-failure-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="owner", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    attempt = storage.begin_provider_attempt(
        execution, stage="topics", attempt_no=1, max_cost_usd=0.5,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.fail_or_escalate_topic_generation_execution(
        execution, None, "TOPIC_PROVIDER_FAILED", terminalize_job=True,
    )
    assert storage.conn.execute(
        "SELECT request_started_at,status FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()["request_started_at"] is None
    result = storage.resolve_provider_attempt_reconciliation(
        request_id=attempt.request_id, account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="op", note="release failure resolved",
    )
    assert result.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert storage.get_job(job.id).status is JobStatus.FAILED


def test_terminal_topic_reconciliation_survives_reopen_and_maintenance_without_retry(
    settings, storage, account,
):
    _, _, job, request_id, caller = _needs_topic_reconciliation(
        settings, storage, account, key="reopen-maintenance",
    )
    storage.resolve_provider_attempt_reconciliation(
        request_id=request_id, account_id=account.id,
        financial_resolution=FinancialResolution.CHARGED_KNOWN,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd="0.020000", reconciled_by="op", note="terminal before reopen",
    )
    reopened = SqliteStorage.open(settings.db_path)
    try:
        reopened.release_or_requeue_expired_leases(
            clock=FixedClock(NOW + timedelta(days=1)),
        )
        reopened.reap_orphaned_stale_runs(
            NOW, clock=FixedClock(NOW + timedelta(days=1)),
        )
        assert reopened.get_job(job.id).status is JobStatus.FAILED
        assert reopened.conn.execute(
            "SELECT status FROM provider_attempts WHERE request_id=?", (request_id,),
        ).fetchone()["status"] == ProviderAttemptStatus.RECONCILED_SETTLED.value
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (job.id,),
        ).fetchone()[0] == 1
        assert reopened.conn.execute(
            "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
        ).fetchone()[0] == 1
    finally:
        reopened.close()
    assert len(caller.calls) == 1


def test_sqlite_floor_rejects_partial_topic_generation_terminalization(
    settings, storage, account,
):
    _, _, job, request_id, _ = _needs_topic_reconciliation(
        settings, storage, account, key="sqlite-partial-terminal",
    )
    before = storage.conn.execute(
        "SELECT status,reconciled_at FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at=?,"
            "reconciled_at=?,reconciled_by=?,reconciliation_note=?,"
            "reconciliation_resolution='NOT_CHARGED:EXECUTION_FAILED' "
            "WHERE request_id=? AND status='NEEDS_RECONCILIATION'",
            (NOW.isoformat(), NOW.isoformat(), "raw-writer", "partial", request_id),
        )
    storage.conn.rollback()
    after = storage.conn.execute(
        "SELECT status,reconciled_at FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()
    assert tuple(after) == tuple(before)
    assert storage.get_job(job.id).status is JobStatus.NEEDS_VERIFICATION


# --- brak regresji ścieżki RESEARCH ------------------------------------------

def test_research_fence_and_usage_task_contract_are_unchanged(
    settings, storage, account,
):
    """A research job may not book topic usage and vice versa."""
    from app.models import ModelUsage

    real, intent, job = _prepare(settings, storage, account)
    storage.claim_next_job("owner", 120, clock=FixedClock(NOW))
    storage.mark_job_running(job.id, "owner", clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, "owner", "topicgen-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner="owner", run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.add_job_model_usage(execution, ModelUsage(
            run_id=initialized.run.id, model="m", task="research",
            input_tokens=1, output_tokens=1, estimated_cost_usd=0.1,
            dry_run=False, request_id=f"{job.id}:topics:1",
        ))


def test_account_isolation_of_generated_topics(settings, storage, account):
    other = account.model_copy(update={"id": "second_account"})
    storage.ensure_account(other)
    real, intent, job = _prepare(settings, storage, account, count=1)
    _run_once(real, storage, _FakeTopicCaller(_response(0.95)))

    run_id = storage.get_job(job.id).run_id
    lineage = storage.list_generated_topics_for_run(run_id)
    assert {row.account_id for row in lineage} == {account.id}
    assert storage.conn.execute(
        "SELECT COUNT(*) c FROM topics WHERE account_id=?", (other.id,),
    ).fetchone()["c"] == 0
    assert list(storage.list_topics(other.id)) == []
