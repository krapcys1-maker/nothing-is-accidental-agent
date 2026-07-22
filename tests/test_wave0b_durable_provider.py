"""Offline WAVE 0B contract tests for durable real-provider attempts."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
import shutil
import sys
import importlib

import pytest

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.llm.base import Usage
from app.llm.anthropic_client import AnthropicLLMClient
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    DurableProviderAttemptContext,
    ProviderAttempt,
    ProviderAttemptStatus,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    AmountBelowMinimumPrecisionError,
    BudgetReservationError,
    JobConflictError,
    JobPayloadValidationError,
    ModelUsageRequestIdError,
    ProviderAttemptOverReservationError,
    ProviderAttemptReconciliationRequired,
    StaleJobExecutionError,
)
from app.research.anthropic_client import AnthropicResearchClient, OfflineAnthropicResearchClient
from app.research.base import (
    DurableProviderAttemptContextError,
    ProviderRequestIdentityMismatch,
    ResearchPlan,
    expected_provider_request_id,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.research.fake_client import FakeResearchClient
from app.storage.db import MIGRATIONS_DIR, apply_migrations
from app.storage.repositories import SqliteStorage
from app.policies.policy_engine import PolicyEngine
from app.ports.notification import LogNotification
from app.llm.usage_tracker import UsageTracker
from app.workflows.research.pipeline import (
    ResearchExecutionNeedsReconciliation,
    ResearchExecutionRequiresDurableJob,
    run_research_pipeline,
    run_staged_research_pipeline,
    run_two_stage_research_pipeline,
)
from app.models import ResearchJobExecution
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationStatus
from tests.conftest import write_approved_pricing_profile


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def now(self) -> datetime:
        return self.moment


def _topic(storage, account, suffix: str):
    storage.ensure_account(account)
    return storage.add_topic(account.id, Topic(
        account_id=account.id, title=f"Durable topic {suffix}", question="Why?",
        score=90.0, status=TopicStatus.SELECTED,
    ))


def _real_job(account, topic, key: str, cap: float, *, max_tokens: object = 3000) -> Job:
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="durable-test-model",
            research_timeout_seconds=60,
        ),
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd=cap,
        max_web_searches=3,
        question=topic.question or topic.title,
        niche=account.niche,
        max_tokens=max_tokens,
    )
    return Job(
        id=f"job-{key}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"idempotency-{key}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v2",
            "mode": "single",
            "max_cost_usd": intent.cap_usd,
            "execution_intent": intent.as_payload(),
        },
    )


def _execution(storage, account, topic, key: str, cap: float) -> JobExecutionContext:
    job = storage.enqueue_job(_real_job(account, topic, key, cap))
    lease = storage.claim_next_job(f"worker-{key}", 120, now=NOW)
    assert lease is not None and lease.job.id == job.id
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(
        job.id, lease.lease_owner, f"run-{key}", now=NOW,
    )
    assert initialized.created
    return JobExecutionContext(
        job_id=job.id, lease_owner=lease.lease_owner, run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )


class _CallerCounter(FakeResearchClient):
    """A fake whose methods prove that the provider boundary was never reached."""

    requires_durable_provider_context = True

    def __init__(self) -> None:
        super().__init__("good")
        self.calls = 0

    def gather_sources(self, plan):
        self.calls += 1
        return super().gather_sources(plan)

    def discover_sources(self, plan, max_searches=3):
        self.calls += 1
        return super().discover_sources(plan, max_searches)


def _raw_provider_attempt(storage, execution, **changes) -> None:
    values = {
        "job_id": execution.job_id,
        "stage": "research",
        "attempt_no": 1,
        "request_id": f"{execution.job_id}:research:1",
        "status": "RESERVED",
        "reserved_amount_usd": 0.1,
        "reserved_at": "2026-07-14 12:00:00",
        "request_started_at": None,
        "settled_at": None,
        "released_at": None,
        "actual_cost_usd": None,
        "error_code": None,
    }
    values.update(changes)
    columns = ",".join(values)
    placeholders = ",".join("?" for _ in values)
    storage.conn.execute(
        f"INSERT INTO provider_attempts ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _operation_job(account, topic, job_id: str, operation_key: str, *, cap: float = 0.2,
                   payload: dict | None = None, workflow: WorkflowType = WorkflowType.RESEARCH) -> Job:
    durable_payload = payload or _real_job(account, topic, job_id, cap).payload
    return Job(
        id=job_id, account_id=account.id, kind=JobKind.RESEARCH,
        workflow=workflow, idempotency_key=f"real-research:{operation_key}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1, payload=durable_payload,
    )


def _valid_research_response() -> str:
    return json.dumps({
        "question": "Why?",
        "working_thesis": "A mechanism.",
        "main_mechanism": "A durable mechanism.",
        "confirmed_claims": ["A", "B", "C"],
        "uncertain_claims": [],
        "contradictions": [],
        "strongest_counterargument": "A counterargument.",
        "citable_numbers": [],
        "visual_idea": "A diagram.",
        "confidence_score": 0.9,
        "source_quality_score": 0.9,
        "sources": [
            {
                "url": f"https://{name.lower()}.example",
                "title": name,
                "author_or_org": None,
                "published_at": None,
                "source_type": "PRIMARY",
                "supports_claim": name,
            }
            for name in ("A", "B", "C")
        ],
    })


def _research_response_with_score(value: object) -> str:
    payload = json.loads(_valid_research_response())
    payload["confidence_score"] = value
    return json.dumps(payload)


def _research_response_with_score_literal(value: str) -> str:
    return _valid_research_response().replace(
        '"confidence_score": 0.9',
        f'"confidence_score": {value}',
        1,
    )


def test_real_attempt_has_stable_request_id_and_settles_once(storage, account):
    topic = _topic(storage, account, "stable")
    execution = _execution(storage, account, topic, "stable", 0.20)

    reserved = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.20,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    assert reserved.request_id == "job-stable:research:1"
    same = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.20,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    assert same.request_id == reserved.request_id
    started = storage.mark_provider_attempt_request_started(execution, reserved.request_id)
    assert started.status is ProviderAttemptStatus.REQUEST_STARTED
    with pytest.raises(StaleJobExecutionError):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=1, max_cost_usd=0.20,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )

    usage = storage.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, provider="anthropic", model="test", task="research",
        input_tokens=1, output_tokens=1, estimated_cost_usd=0.01, dry_run=False,
        request_id=reserved.request_id,
    ))
    assert usage.request_id == reserved.request_id
    row = storage.conn.execute(
        "SELECT status,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (reserved.request_id,),
    ).fetchone()
    assert dict(row) == {"status": "SETTLED", "actual_cost_usd": 0.01}
    with pytest.raises(Exception):
        storage.add_job_model_usage(execution, ModelUsage(
            run_id=execution.run_id, provider="anthropic", model="test", task="research",
            estimated_cost_usd=0.01, dry_run=False, request_id=reserved.request_id,
        ))


def test_actual_cost_above_reservation_is_preserved_and_requires_reconciliation(
        storage, account):
    """Rounding is canonical before comparison; no second provider attempt is legal."""
    topic = _topic(storage, account, "over-reservation")
    execution = _execution(storage, account, topic, "over-reservation", 0.20)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.0000005,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    assert attempt.reserved_amount_usd == 0.000001
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    with pytest.raises(ProviderAttemptOverReservationError) as raised:
        storage.add_job_model_usage(execution, ModelUsage(
            run_id=execution.run_id, provider="anthropic", model="test", task="research",
            estimated_cost_usd=0.0000015, dry_run=False, request_id=attempt.request_id,
        ))
    assert raised.value.reserved_amount_usd == 0.000001
    assert raised.value.actual_cost_usd == 0.000002
    usage = storage.conn.execute(
        "SELECT estimated_cost_usd,request_id FROM model_usage WHERE run_id=?", (execution.run_id,),
    ).fetchall()
    assert [tuple(row) for row in usage] == [(0.000002, attempt.request_id)]
    state = storage.conn.execute(
        "SELECT status,error_code,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert tuple(state) == (
        "NEEDS_RECONCILIATION", "PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION", None,
    )
    assert storage.get_run(execution.run_id).cost_usd == 0.000002
    with pytest.raises(ProviderAttemptReconciliationRequired):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=2, max_cost_usd=0.000001,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (execution.job_id,),
    ).fetchone()[0] == 1


def test_actual_cost_at_rounded_reservation_settles_normally(storage, account):
    topic = _topic(storage, account, "rounded-settlement")
    execution = _execution(storage, account, topic, "rounded-settlement", 0.20)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.0000005,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    usage = storage.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, provider="anthropic", model="test", task="research",
        estimated_cost_usd=0.0000014, dry_run=False, request_id=attempt.request_id,
    ))
    assert usage.request_id == attempt.request_id
    assert tuple(storage.conn.execute(
        "SELECT status,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()) == ("SETTLED", 0.000001)


@pytest.mark.parametrize(
    ("actual_cost", "expected_status"),
    [
        (0.000002, "SETTLED"),
        (0.000001, "SETTLED"),
        (0.000003, "NEEDS_RECONCILIATION"),
    ],
)
def test_storage_compares_actual_cost_to_reservation_at_one_micro_usd(
        storage, account, actual_cost, expected_status):
    topic = _topic(storage, account, f"one-micro-{actual_cost}")
    execution = _execution(storage, account, topic, f"one-micro-{actual_cost}", 0.20)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.000002,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)

    usage = ModelUsage(
        run_id=execution.run_id, provider="anthropic", model="test", task="research",
        estimated_cost_usd=actual_cost, dry_run=False, request_id=attempt.request_id,
    )
    if expected_status == "NEEDS_RECONCILIATION":
        with pytest.raises(ProviderAttemptOverReservationError):
            storage.add_job_model_usage(execution, usage)
    else:
        storage.add_job_model_usage(execution, usage)

    state = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE request_id=?", (attempt.request_id,),
    ).fetchone()[0]
    assert state == expected_status
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (execution.run_id,),
    ).fetchone()[0] == 1


def test_atomic_reservation_blocks_shared_budget_race(storage, account):
    first = _execution(storage, account, _topic(storage, account, "budget-a"), "budget-a", 0.20)
    second = _execution(storage, account, _topic(storage, account, "budget-b"), "budget-b", 0.20)
    storage.begin_provider_attempt(
        first, stage="research", attempt_no=1, max_cost_usd=0.20,
        daily_limit_usd=0.30, monthly_limit_usd=0.30,
    )
    with pytest.raises(BudgetReservationError):
        storage.begin_provider_attempt(
            second, stage="research", attempt_no=1, max_cost_usd=0.20,
            daily_limit_usd=0.30, monthly_limit_usd=0.30,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"reserved_amount_usd": 0.0},
        {"reserved_amount_usd": -0.1},
        {"reserved_amount_usd": float("inf")},
        {"attempt_no": 0, "request_id": "job:research:0"},
        {"stage": "BAD STAGE", "request_id": "job:BAD STAGE:1"},
        {"request_id": "arbitrary-request-id"},
        {
            "status": "SETTLED", "request_started_at": "2026-07-14 12:00:00",
            "settled_at": "2026-07-14 12:00:01", "actual_cost_usd": None,
        },
        {
            "status": "RELEASED", "released_at": "2026-07-14 12:00:01",
            "actual_cost_usd": 0.01,
        },
    ],
)
def test_provider_attempt_schema_rejects_inconsistent_direct_inserts(
        storage, account, changes):
    topic = _topic(storage, account, f"raw-{len(changes)}")
    execution = _execution(storage, account, topic, f"raw-{topic.id}", 0.2)
    with pytest.raises(sqlite3.IntegrityError):
        _raw_provider_attempt(storage, execution, **changes)


def test_provider_attempt_identity_and_transitions_are_immutable(storage, account):
    topic = _topic(storage, account, "transition")
    execution = _execution(storage, account, topic, "transition", 0.2)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET request_id='changed' WHERE request_id=?",
            (attempt.request_id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='SETTLED',actual_cost_usd=0.01,"
            "request_started_at='2026-07-14 12:00:00',settled_at='2026-07-14 12:00:01' "
            "WHERE request_id=?",
            (attempt.request_id,),
        )
    storage.conn.rollback()
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.settle_provider_attempt_without_usage(
        execution, attempt.request_id, error_code="ConfirmedNoUsage",
    )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE provider_attempts SET status='REQUEST_STARTED' WHERE request_id=?",
            (attempt.request_id,),
        )


def test_real_model_usage_requires_active_attempt_and_dry_run_history_remains_valid(
        storage, account):
    topic = _topic(storage, account, "usage")
    execution = _execution(storage, account, topic, "usage", 0.2)
    with pytest.raises(ModelUsageRequestIdError):
        storage.add_model_usage(ModelUsage(
            run_id=execution.run_id, model="test", dry_run=False,
        ))
    storage.add_model_usage(ModelUsage(
        run_id=execution.run_id, model="test", dry_run=True,
    ))
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,model,dry_run,request_id) VALUES (?,?,0,?)",
            (execution.run_id, "test", "missing:research:1"),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="self-declare legacy"):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,model,dry_run,is_legacy_usage) VALUES (?,?,0,1)",
            (execution.run_id, "test"),
        )
    storage.conn.rollback()

    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, model="test", task="research", dry_run=False,
        estimated_cost_usd=0.01, request_id=attempt.request_id,
    ))
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,model,dry_run,request_id) VALUES (?,?,0,?)",
            (execution.run_id, "test", attempt.request_id),
        )
    storage.conn.rollback()

    other = _execution(storage, account, _topic(storage, account, "usage-other"), "usage-other", 0.2)
    with pytest.raises(sqlite3.IntegrityError, match="request->job->run"):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,model,dry_run,request_id) VALUES (?,?,0,?)",
            (other.run_id, "test", attempt.request_id),
        )
    storage.conn.rollback()


def test_budget_reservation_accepts_decimal_boundary_and_rejects_excess(storage, account):
    first = _execution(storage, account, _topic(storage, account, "decimal-a"), "decimal-a", 0.1)
    second = _execution(storage, account, _topic(storage, account, "decimal-b"), "decimal-b", 0.2)
    third = _execution(storage, account, _topic(storage, account, "decimal-c"), "decimal-c", 0.000001)
    storage.begin_provider_attempt(
        first, stage="research", attempt_no=1, max_cost_usd=0.10,
        daily_limit_usd=0.30, monthly_limit_usd=0.30,
    )
    storage.begin_provider_attempt(
        second, stage="research", attempt_no=1, max_cost_usd=0.20,
        daily_limit_usd=0.30, monthly_limit_usd=0.30,
    )
    with pytest.raises(BudgetReservationError):
        storage.begin_provider_attempt(
            third, stage="research", attempt_no=1, max_cost_usd=0.000001,
            daily_limit_usd=0.30, monthly_limit_usd=0.30,
        )


def test_operation_key_is_global_and_payload_is_canonical(storage, account):
    first_topic = _topic(storage, account, "operation-first")
    second_topic = _topic(storage, account, "operation-second")
    first = _operation_job(
        account, first_topic, "operation-first", "operation-key",
        payload={
            "account_id": account.id, "topic_id": int(first_topic.id), "dry_run": False,
            "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": "0.200000",
            "execution_intent": DurableResearchExecutionIntent.from_settings(
                settings=SimpleNamespace(
                    pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
                    model_quality="durable-test-model", research_timeout_seconds=60,
                 ), account_id=account.id, topic_id=int(first_topic.id), cap_usd=0.2,
                 max_web_searches=3, question=first_topic.question or first_topic.title,
                 niche=account.niche,
            ).as_payload(),
        },
    )
    created = storage.enqueue_job_result(first)
    assert created.created is True
    reordered = _operation_job(
        account, first_topic, "operation-reordered", "operation-key",
        payload={
            "max_cost_usd": 0.2, "mode": "single",
            "execution": "durable_provider_v2", "dry_run": False,
            "topic_id": int(first_topic.id), "account_id": account.id,
            "execution_intent": DurableResearchExecutionIntent.from_settings(
                settings=SimpleNamespace(
                    pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
                    model_quality="durable-test-model", research_timeout_seconds=60,
                 ), account_id=account.id, topic_id=int(first_topic.id), cap_usd=0.2,
                 max_web_searches=3, question=first_topic.question or first_topic.title,
                 niche=account.niche,
            ).as_payload(),
        },
    )
    existing = storage.enqueue_job_result(reordered)
    assert existing.created is False and existing.job.id == created.job.id

    other_account = account.model_copy(update={"id": "other-account"})
    storage.ensure_account(other_account)
    other_topic = _topic(storage, other_account, "operation-other-account")
    for changed in (
        _operation_job(account, second_topic, "operation-topic", "operation-key"),
        _operation_job(other_account, other_topic, "operation-account", "operation-key"),
        _operation_job(account, first_topic, "operation-cap", "operation-key", cap=0.3),
        _operation_job(
            account, first_topic, "operation-workflow", "operation-key",
            workflow=WorkflowType.TOPIC,
        ),
    ):
        with pytest.raises(JobConflictError, match="different job context"):
            storage.enqueue_job_result(changed)


def test_operation_key_races_are_atomic(settings, storage, account):
    first_topic = _topic(storage, account, "race-first")
    same_job = _operation_job(account, first_topic, "race-same", "race-same")
    barrier = threading.Barrier(2)

    def enqueue_same():
        connection = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            return connection.enqueue_job_result(same_job)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same_results = list(pool.map(lambda _value: enqueue_same(), range(2)))
    assert sum(result.created for result in same_results) == 1
    assert {result.job.id for result in same_results} == {same_job.id}

    conflict_first_topic = _topic(storage, account, "race-conflict-first")
    second_topic = _topic(storage, account, "race-second")
    first = _operation_job(account, conflict_first_topic, "race-conflict-a", "race-conflict")
    second = _operation_job(account, second_topic, "race-conflict-b", "race-conflict")
    conflict_barrier = threading.Barrier(2)

    def enqueue(job):
        connection = SqliteStorage.open(settings.db_path)
        try:
            conflict_barrier.wait()
            return connection.enqueue_job_result(job)
        except JobConflictError:
            return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        conflict_results = list(pool.map(enqueue, (first, second)))
    assert sum(result == "conflict" for result in conflict_results) == 1
    assert sum(getattr(result, "created", False) for result in conflict_results) == 1


def test_budget_reservation_real_thread_race_allows_only_one(settings, storage, account):
    first = _execution(storage, account, _topic(storage, account, "thread-budget-a"), "thread-budget-a", 0.2)
    second = _execution(storage, account, _topic(storage, account, "thread-budget-b"), "thread-budget-b", 0.2)
    barrier = threading.Barrier(2)

    def reserve(execution):
        connection = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            connection.begin_provider_attempt(
                execution, stage="research", attempt_no=1, max_cost_usd=0.2,
                daily_limit_usd=0.3, monthly_limit_usd=0.3,
            )
            return "reserved"
        except BudgetReservationError:
            return "blocked"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, (first, second)))
    assert sorted(results) == ["blocked", "reserved"]


def _database_at_0010(tmp_path: Path) -> sqlite3.Connection:
    legacy_migrations = tmp_path / "migrations-0010"
    legacy_migrations.mkdir()
    for source in MIGRATIONS_DIR.glob("*.sql"):
        if source.stem <= "0010_provider_attempts":
            shutil.copy2(source, legacy_migrations / source.name)
    conn = sqlite3.connect(tmp_path / "legacy-0010.db")
    conn.row_factory = sqlite3.Row
    assert apply_migrations(conn, legacy_migrations)[-1] == "0010_provider_attempts"
    return conn


def _seed_0010_provider_history(conn: sqlite3.Connection, *, valid: bool) -> None:
    conn.execute(
        "INSERT INTO accounts (id,name,mode,autonomy_level,active,browser_profile_path,writing_profile_path) "
        "VALUES ('a','A','RESEARCH_ONLY','LEVEL_1',1,'browser','writer')"
    )
    conn.execute("INSERT INTO topics (id,account_id,title,status) VALUES (1,'a','T','SELECTED')")
    conn.execute("INSERT INTO runs (id,account_id,workflow,status) VALUES ('run','a','RESEARCH','RUNNING')")
    conn.execute(
        "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,topic_id,"
        "payload_json,schedule_reason,earliest_run_at,lease_owner,lease_expires_at,"
        "max_attempts,created_at,updated_at) VALUES "
        "('job','a','RESEARCH','RESEARCH','RUNNING','key',1,'{}','WITHIN_EDITORIAL_WINDOW',"
        "'2026-07-14 12:00:00','worker','2026-07-14 12:05:00',1,"
        "'2026-07-14 12:00:00','2026-07-14 12:00:00')"
    )
    if valid:
        conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
            "reserved_amount_usd,reserved_at,request_started_at,settled_at,actual_cost_usd) "
            "VALUES ('job','research',1,'job:research:1','SETTLED',0.2,"
            "'2026-07-14 12:00:00','2026-07-14 12:00:01','2026-07-14 12:00:02',0.01)"
        )
    else:
        conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
            "reserved_amount_usd,reserved_at) VALUES "
            "('job','research',1,'job:research:1','RESERVED',0.0,'2026-07-14 12:00:00')"
        )
    # Historical real usage did not have provider identities before WAVE 0B.
    conn.execute(
        "INSERT INTO model_usage (run_id,model,dry_run,estimated_cost_usd) "
        "VALUES ('run','legacy',0,0.03)"
    )
    conn.commit()


def test_migration_0011_preserves_valid_0010_history_and_is_idempotent(tmp_path: Path):
    conn = _database_at_0010(tmp_path)
    _seed_0010_provider_history(conn, valid=True)
    assert apply_migrations(conn) == [
        "0011_provider_attempt_invariants", "0012_provider_ledger_hardening",
            "0013_provider_attempt_usage_integrity", "0014_provider_attempt_reconciliation",
            "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle", "0019_evidence_research_approvals",
            "0020_topic_generation_lifecycle",
    ]
    attempt = conn.execute(
        "SELECT status,actual_cost_usd,released_at FROM provider_attempts"
    ).fetchone()
    assert dict(attempt) == {"status": "SETTLED", "actual_cost_usd": 0.01, "released_at": None}
    history = conn.execute(
        "SELECT request_id,is_legacy_usage FROM model_usage WHERE model='legacy'"
    ).fetchone()
    assert dict(history) == {"request_id": None, "is_legacy_usage": 1}
    assert apply_migrations(conn) == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()


def test_migration_0011_rolls_back_invalid_0010_attempts(tmp_path: Path):
    conn = _database_at_0010(tmp_path)
    _seed_0010_provider_history(conn, valid=False)
    with pytest.raises(sqlite3.IntegrityError):
        apply_migrations(conn)
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0011_provider_attempt_invariants'"
    ).fetchone()[0] == 0
    assert "released_at" not in {
        row["name"] for row in conn.execute("PRAGMA table_info(provider_attempts)")
    }
    conn.close()


def test_restart_before_request_reuses_identity_but_unknown_blocks_retry(storage, settings, account):
    topic = _topic(storage, account, "restart")
    execution = _execution(storage, account, topic, "restart", 0.20)
    first = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.20,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        resumed = reopened.begin_provider_attempt(
            execution, stage="research", attempt_no=1, max_cost_usd=0.20,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
        assert resumed.request_id == first.request_id
        reopened.mark_provider_attempt_request_started(execution, resumed.request_id)
        reopened.mark_provider_attempt_needs_reconciliation(
            execution, resumed.request_id, error_code="ResearchTimeout",
        )
        with pytest.raises(ProviderAttemptReconciliationRequired):
            reopened.begin_provider_attempt(
                execution, stage="research", attempt_no=1, max_cost_usd=0.20,
                daily_limit_usd=2.0, monthly_limit_usd=40.0,
            )
    finally:
        reopened.close()


def test_client_receives_stable_request_id_without_network():
    captured = []

    def caller(_plan):
        captured.append("called")
        return (_valid_research_response(), Usage())

    client = OfflineAnthropicResearchClient("offline", "test", caller=caller)
    client.configure_attempt_control(
        budget_callback=lambda _context: SimpleNamespace(request_id="job-x:research:1"),
        retry_usage_callback=None, estimated_attempt_cost=0.1,
    )
    result = client.run_research(ResearchPlan(topic_id=1, account_id="a", question="Why?"))
    assert captured == ["called"]
    assert result.request_id == "job-x:research:1"


def test_fresh_real_pipeline_without_job_is_rejected(settings, storage, account):
    topic = _topic(storage, account, "no-bypass")
    real_settings = replace(settings, dry_run=False)
    with pytest.raises(ResearchExecutionRequiresDurableJob):
        run_research_pipeline(
            account, topic, settings=real_settings, storage=storage,
            research_client=AnthropicResearchClient("offline", "model"),
            usage_tracker=UsageTracker(real_settings, storage),
            policy=PolicyEngine(real_settings, storage), notifier=LogNotification(),
            run_cap_usd=1.0,
        )


@pytest.mark.parametrize("flow", ["two-stage", "staged"])
def test_fresh_real_legacy_pipeline_is_blocked_before_any_caller(
        settings, storage, account, flow):
    topic = _topic(storage, account, f"blocked-{flow}")
    real_settings = replace(settings, dry_run=False)
    client = _CallerCounter()
    common = dict(
        settings=real_settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage), notifier=LogNotification(),
        run_cap_usd=1.0,
    )
    with pytest.raises(ResearchExecutionRequiresDurableJob, match="WAVE 1A"):
        if flow == "two-stage":
            run_two_stage_research_pipeline(account, topic, **common)
        else:
            run_staged_research_pipeline(account, topic, **common)
    assert client.calls == 0


def test_fake_two_stage_and_staged_pipelines_remain_available(settings, storage, account):
    two_stage_topic = _topic(storage, account, "fake-two-stage")
    two_stage = run_two_stage_research_pipeline(
        account, two_stage_topic, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage), policy=PolicyEngine(settings, storage),
        notifier=LogNotification(), run_cap_usd=1.0,
    )
    assert two_stage.card is not None

    staged_topic = _topic(storage, account, "fake-staged")
    staged = run_staged_research_pipeline(
        account, staged_topic, settings=settings, storage=storage,
        research_client=FakeResearchClient("good"),
        usage_tracker=UsageTracker(settings, storage), policy=PolicyEngine(settings, storage),
        notifier=LogNotification(), run_cap_usd=1.0,
    )
    assert staged.card is not None


def test_real_single_pipeline_uses_attempt_ledger_before_injected_provider(
        storage, settings, account):
    topic = _topic(storage, account, "pipeline")
    job = storage.enqueue_job(_real_job(account, topic, "pipeline", 1.0))
    lease = storage.claim_next_job("worker-pipeline", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={
            "input_per_mtok": 1.0, "output_per_mtok": 1.0,
            "cache_read_per_mtok": 1.0, "cache_write_per_mtok": 1.0,
            "web_search_per_1k": 1.0,
        },
    )
    calls = []

    def caller(_plan):
        calls.append("provider")
        return _valid_research_response(), Usage(
            input_tokens=10, output_tokens=10, web_search_requests=1
        )

    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage,
        research_client=AnthropicResearchClient("offline", "model", caller=caller),
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)),
        notifier=LogNotification(), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=1.0,
    )
    assert calls == ["provider"]
    assert summary.run_id is not None
    attempt = storage.conn.execute(
        "SELECT request_id,status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert dict(attempt) == {"request_id": "job-pipeline:research:1", "status": "SETTLED"}


def test_durable_max_tokens_drives_estimate_reservation_and_fake_caller(
        monkeypatch, storage, settings, account):
    from app.workflows.research import pipeline as pipeline_module

    topic = _topic(storage, account, "max-tokens-flow")
    job = storage.enqueue_job(_real_job(account, topic, "max-tokens-flow", 1.0, max_tokens=3107))
    lease = storage.claim_next_job("worker-max-tokens-flow", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    intent = DurableResearchExecutionIntent.from_payload(job.payload["execution_intent"])
    observed: dict[str, object] = {}
    estimate = pipeline_module.estimate_worst_case_search_call_usd
    begin = storage.begin_provider_attempt

    def record_estimate(*args, **kwargs):
        observed["estimate_max_tokens"] = kwargs["max_output_tokens"]
        result = estimate(*args, **kwargs)
        observed["estimate_total"] = result.total_usd
        return result

    def record_reservation(*args, **kwargs):
        observed["reservation"] = kwargs["max_cost_usd"]
        return begin(*args, **kwargs)

    caller_limits: list[int] = []

    def caller(_plan):
        caller_limits.append(client._research_max_tokens)
        return _valid_research_response(), Usage(input_tokens=10, output_tokens=10, web_search_requests=1)

    monkeypatch.setattr(pipeline_module, "estimate_worst_case_search_call_usd", record_estimate)
    monkeypatch.setattr(storage, "begin_provider_attempt", record_reservation)
    client = AnthropicResearchClient(
        "offline", intent.model, caller=caller, max_web_searches=intent.max_web_searches,
        research_max_tokens=intent.max_tokens,
    )
    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)), notifier=LogNotification(),
        clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=float(intent.cap_usd), max_web_searches=intent.max_web_searches,
        request_max_tokens=intent.max_tokens, durable_plan=intent.as_research_plan(),
    )
    assert summary.run_id is not None
    assert summary.error is None
    assert intent.max_tokens == 3107
    assert observed["estimate_max_tokens"] == 3107
    assert observed["reservation"] == observed["estimate_total"]
    assert caller_limits == [3107]
    attempt = storage.conn.execute(
        "SELECT reserved_amount_usd,status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert tuple(attempt) == (observed["estimate_total"], "SETTLED")


def test_durable_pipeline_over_reservation_retains_usage_and_blocks_success(
        storage, settings, account):
    topic = _topic(storage, account, "pipeline-over-reservation")
    job = storage.enqueue_job(_real_job(account, topic, "pipeline-over-reservation", 10.0, max_tokens=3001))
    lease = storage.claim_next_job("worker-pipeline-over-reservation", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    intent = DurableResearchExecutionIntent.from_payload(job.payload["execution_intent"])
    client = AnthropicResearchClient(
        "offline", intent.model,
        caller=lambda _plan: (_valid_research_response(), Usage(output_tokens=1_000_000)),
        max_web_searches=intent.max_web_searches, research_max_tokens=intent.max_tokens,
    )
    with pytest.raises(ResearchExecutionNeedsReconciliation):
        run_research_pipeline(
            account, topic, settings=real_settings, storage=storage, research_client=client,
            usage_tracker=UsageTracker(real_settings, storage),
            policy=PolicyEngine(real_settings, storage, FixedClock(NOW)), notifier=LogNotification(),
            clock=FixedClock(NOW),
            job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
            run_cap_usd=float(intent.cap_usd), max_web_searches=intent.max_web_searches,
            request_max_tokens=intent.max_tokens, durable_plan=intent.as_research_plan(),
        )
    run_id = storage.get_job(job.id).run_id
    assert run_id is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (topic.id,),
    ).fetchone()[0] == 0
    usage = storage.conn.execute(
        "SELECT count(*),SUM(estimated_cost_usd) FROM model_usage WHERE run_id=?", (run_id,),
    ).fetchone()
    assert tuple(usage) == (1, 1.0)
    attempt = storage.conn.execute(
        "SELECT status,error_code FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert tuple(attempt) == ("NEEDS_RECONCILIATION", "PROVIDER_ATTEMPT_COST_EXCEEDS_RESERVATION")
    assert storage.get_run(run_id).status is RunStatus.RUNNING


@pytest.mark.parametrize(
    ("case", "response", "stop_reason", "classification"),
    [
        ("parse", "not valid json", "end_turn", "prose_outside_json"),
        (
            "schema",
            json.dumps({
                key: value
                for key, value in json.loads(_valid_research_response()).items()
                if key != "working_thesis"
            }),
            "end_turn",
            "classification=schema",
        ),
        ("truncation", '{"question":"cut', "max_tokens", "stop_reason=max_tokens"),
        (
            "score-400-digit",
            _research_response_with_score(int("9" * 400)),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-huge-exponent",
            _research_response_with_score_literal("1e400"),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-positive-infinity",
            _research_response_with_score_literal("Infinity"),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-negative-infinity",
            _research_response_with_score_literal("-Infinity"),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-nan",
            _research_response_with_score_literal("NaN"),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-out-of-range",
            _research_response_with_score(1.01),
            "end_turn",
            "classification=schema",
        ),
        (
            "score-text",
            _research_response_with_score("0.8"),
            "end_turn",
            "classification=schema",
        ),
    ],
)
def test_durable_parse_schema_and_truncation_settle_usage_once(
    storage, settings, account, case, response, stop_reason, classification,
):
    suffix = f"{case}-settlement"
    topic = _topic(storage, account, suffix)
    job = storage.enqueue_job(_real_job(account, topic, suffix, 1.0))
    lease = storage.claim_next_job(f"worker-{suffix}", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    calls: list[str] = []

    def caller(_plan):
        calls.append("provider")
        return (
            response,
            Usage(input_tokens=10, output_tokens=10, web_search_requests=1),
            stop_reason,
        )

    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage,
        research_client=AnthropicResearchClient("offline", "model", caller=caller),
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)),
        notifier=LogNotification(), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=1.0,
    )
    assert calls == ["provider"]
    assert summary.error and classification in summary.error
    usage = storage.conn.execute(
        "SELECT request_id,estimated_cost_usd FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchall()
    assert len(usage) == 1
    attempt = storage.conn.execute(
        "SELECT request_id,status,actual_cost_usd,request_started_at,settled_at "
        "FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()
    assert attempt["status"] == "SETTLED"
    assert attempt["request_started_at"] is not None
    assert attempt["settled_at"] is not None
    assert usage[0]["request_id"] == attempt["request_id"]
    assert usage[0]["estimated_cost_usd"] == attempt["actual_cost_usd"]
    with pytest.raises(StaleJobExecutionError):
        storage.settle_provider_attempt_without_usage(
            JobExecutionContext(
                job_id=job.id, lease_owner=lease.lease_owner, run_id=summary.run_id,
                clock=FixedClock(NOW),
            ),
            attempt["request_id"], error_code="must-not-settle-twice",
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1
    terminal_job = storage.get_job(job.id)
    assert terminal_job.status.value == "FAILED"
    assert terminal_job.status.value != "NEEDS_VERIFICATION"
    assert terminal_job.budget_reserved_at is None
    assert terminal_job.lease_owner is None
    assert summary.card is None
    assert storage.conn.execute(
        "SELECT count(*) FROM research_cards WHERE topic_id=?", (topic.id,),
    ).fetchone()[0] == 0
    diagnostic = (
        settings.data_dir / "debug" / "research" / summary.run_id
        / "SINGLE_raw_response.txt"
    )
    content = diagnostic.read_text(encoding="utf-8")
    assert f"stop_reason: {stop_reason}" in content
    assert response in content


def test_durable_boundary_score_succeeds_with_one_usage_and_settlement(
    storage, settings, account,
):
    topic = _topic(storage, account, "score-boundary")
    job = storage.enqueue_job(_real_job(account, topic, "score-boundary", 1.0))
    lease = storage.claim_next_job("worker-score-boundary", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    calls: list[str] = []

    def caller(_plan):
        calls.append("provider")
        return (
            _research_response_with_score(1),
            Usage(input_tokens=10, output_tokens=10, web_search_requests=1),
            "end_turn",
        )

    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage,
        research_client=AnthropicResearchClient("offline", "model", caller=caller),
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)),
        notifier=LogNotification(), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=1.0,
    )
    assert calls == ["provider"]
    assert summary.passed is True
    assert summary.card is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()[0] == 1
    attempt = storage.conn.execute(
        "SELECT status,request_started_at,settled_at FROM provider_attempts "
        "WHERE job_id=?", (job.id,),
    ).fetchone()
    assert tuple(attempt) == ("SETTLED", attempt["request_started_at"], attempt["settled_at"])
    assert attempt["request_started_at"] is not None
    assert attempt["settled_at"] is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1


_SECRET_RAW = """not valid json
sk-ant-test-secret
Authorization: Bearer test-secret
api_key=test-secret
nested_exception=RuntimeError(password=test-secret)
headers={"x-api-key":"test-secret"}
"""
_FORBIDDEN_SECRET_TEXT = (
    "sk-ant-test-secret", "Authorization", "Bearer", "api_key",
    "nested_exception", "headers", "test-secret",
)


def test_durable_secret_response_is_sanitized_in_all_persistent_surfaces(
    storage, settings, account, caplog, capsys, tmp_path,
):
    from app.operations.controlled_live import write_operator_report

    topic = _topic(storage, account, "secret-diagnostic")
    job = storage.enqueue_job(_real_job(account, topic, "secret-diagnostic", 1.0))
    lease = storage.claim_next_job("worker-secret-diagnostic", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    calls: list[str] = []

    def caller(_plan):
        calls.append("provider")
        return (
            _SECRET_RAW,
            Usage(input_tokens=10, output_tokens=10, web_search_requests=1),
            "end_turn",
        )

    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage,
        research_client=AnthropicResearchClient("offline", "model", caller=caller),
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)),
        notifier=LogNotification(), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=1.0,
    )
    report = write_operator_report(
        tmp_path / "reports", "secret-report", {"detail": _SECRET_RAW}
    )
    diagnostic = (
        settings.data_dir / "debug" / "research" / summary.run_id
        / "SINGLE_raw_response.txt"
    )
    persistent_text = diagnostic.read_text(encoding="utf-8")
    persistent_text += report.read_text(encoding="utf-8")
    persistent_text += " ".join(
        str(value or "")
        for value in storage.conn.execute(
            "SELECT jobs.last_error,runs.error,research_runs.error "
            "FROM jobs JOIN runs ON runs.id=jobs.run_id "
            "JOIN research_runs ON research_runs.id=runs.id WHERE jobs.id=?",
            (job.id,),
        ).fetchone()
    )
    captured = capsys.readouterr()
    persistent_text += caplog.text + captured.out + captured.err

    assert calls == ["provider"]
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == "SETTLED"
    for forbidden in _FORBIDDEN_SECRET_TEXT:
        assert forbidden not in persistent_text


@pytest.mark.parametrize(
    "failure_point",
    ("temp_write", "file_fsync", "replace", "directory_fsync"),
)
def test_diagnostic_failpoints_do_not_change_durable_failure_lifecycle(
    storage, settings, account, monkeypatch, failure_point,
):
    import app.research.diagnostics as diagnostics_module
    import app.workflows.research.pipeline as pipeline_module

    def fail(*_args):
        raise OSError(failure_point)

    replacement = {
        "temp_write": {"write_file": fail},
        "file_fsync": {"fsync_file": fail},
        "replace": {"replace_file": fail},
        "directory_fsync": {"fsync_directory": fail},
    }[failure_point]
    file_ops = replace(diagnostics_module._DEFAULT_FILE_OPS, **replacement)
    real_writer = diagnostics_module.write_diagnostics
    monkeypatch.setattr(
        pipeline_module,
        "write_diagnostics",
        lambda data_dir, diag: real_writer(data_dir, diag, _file_ops=file_ops),
    )

    topic = _topic(storage, account, f"diagnostic-{failure_point}")
    job = storage.enqueue_job(
        _real_job(account, topic, f"diagnostic-{failure_point}", 1.0)
    )
    lease = storage.claim_next_job(
        f"worker-diagnostic-{failure_point}", 120, now=NOW
    )
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    calls: list[str] = []

    def caller(_plan):
        calls.append("provider")
        return (
            "not valid json",
            Usage(input_tokens=10, output_tokens=10, web_search_requests=1),
            "end_turn",
        )

    summary = run_research_pipeline(
        account, topic, settings=real_settings, storage=storage,
        research_client=AnthropicResearchClient("offline", "model", caller=caller),
        usage_tracker=UsageTracker(real_settings, storage),
        policy=PolicyEngine(real_settings, storage, FixedClock(NOW)),
        notifier=LogNotification(), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        run_cap_usd=1.0,
    )
    assert calls == ["provider"]
    assert summary.error
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.get_job(job.id).budget_reserved_at is None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (summary.run_id,),
    ).fetchone()[0] == 1
    attempt = storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchall()
    assert [row["status"] for row in attempt] == ["SETTLED"]


def test_tests_cannot_open_project_database_for_writing():
    protected = Path(__file__).resolve().parents[1] / "data" / "agent.db"
    with pytest.raises(RuntimeError, match="must not open"):
        SqliteStorage.open(protected)


def test_real_cli_enqueues_only_and_operation_key_is_idempotent(
        monkeypatch, capsys, settings, storage, account):
    from scripts import run_capped_research

    from tests.conftest import write_approved_pricing_profile

    topic = _topic(storage, account, "cli")
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="test-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    profile_id, _ = write_approved_pricing_profile(
        real_settings.project_root, model=real_settings.model_quality,
    )
    monkeypatch.setattr(run_capped_research, "load_settings", lambda: real_settings)
    argv = [
        "--topic-id", str(topic.id), "--real", "--operation-key", "wave0b-cli",
        "--pricing-profile", profile_id,
    ]
    assert run_capped_research.main(argv) == 0
    assert "JOB_ENQUEUED" in capsys.readouterr().out
    assert run_capped_research.main(argv) == 0
    assert "JOB_ALREADY_EXISTS" in capsys.readouterr().out
    assert run_capped_research.main(argv + ["--max-cost-usd", "0.9"]) == 2
    assert "OPERATION_KEY_CONFLICT" in capsys.readouterr().out
    second = _topic(storage, account, "cli-second")
    assert run_capped_research.main([
        "--topic-id", str(second.id), "--real", "--operation-key", "wave0b-cli",
        "--pricing-profile", profile_id,
    ]) == 2
    assert "OPERATION_KEY_CONFLICT" in capsys.readouterr().out
    assert run_capped_research.main([
        "--topic-id", str(second.id), "--real", "--operation-key", "wave0b-cli-second",
        "--pricing-profile", profile_id,
    ]) == 0
    jobs = storage.conn.execute("SELECT id,payload_json FROM jobs WHERE id LIKE 'real-research-%'").fetchall()
    assert len(jobs) == 2
    assert '"dry_run":false' in jobs[0]["payload_json"]


def _started_provider_attempt(context: DurableProviderAttemptContext, *, request_id: str | None = None,
                              status: ProviderAttemptStatus = ProviderAttemptStatus.REQUEST_STARTED) -> ProviderAttempt:
    return ProviderAttempt(
        job_id=context.job_id, stage=context.stage, attempt_no=context.attempt_no,
        request_id=request_id or context.request_id, status=status,
        reserved_amount_usd=0.1, reserved_at=NOW,
        request_started_at=NOW if status is not ProviderAttemptStatus.RESERVED else None,
    )


def _direct_durable_context(request_id: str | None = "direct:research:1") -> DurableProviderAttemptContext:
    return DurableProviderAttemptContext(
        job_id="direct", run_id="run-direct", stage="research", attempt_no=1,
        request_id=request_id, lease_owner="worker-direct",  # type: ignore[arg-type]
        fence_token="direct:run-direct:worker-direct", checked_at=NOW,
    )


def test_real_client_requires_confirmed_durable_context_before_any_caller():
    calls: list[str] = []

    def caller(_plan):
        calls.append("caller")
        return (_valid_research_response(), Usage())

    plan = ResearchPlan(topic_id=1, account_id="a", question="Why?")
    client = AnthropicResearchClient("offline", "model", caller=caller)
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: None, activation_callback=lambda _context: None,
        assertion_callback=lambda _context: None,
        estimated_attempt_cost=0.1,
    )
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    context = _direct_durable_context()
    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context, activation_callback=None,
        assertion_callback=lambda _context: _started_provider_attempt(context),
        estimated_attempt_cost=0.1,
    )
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: _direct_durable_context(None),
        activation_callback=lambda _context: pytest.fail("activation must not run without request_id"),
        assertion_callback=lambda _context: pytest.fail("assertion must not run without request_id"),
        estimated_attempt_cost=0.1,
    )
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=lambda active: _started_provider_attempt(active, request_id="other:research:1"),
        assertion_callback=_started_provider_attempt,
        estimated_attempt_cost=0.1,
    )
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=lambda active: _started_provider_attempt(
            active, status=ProviderAttemptStatus.RESERVED,
        ),
        assertion_callback=_started_provider_attempt,
        estimated_attempt_cost=0.1,
    )
    with pytest.raises(DurableProviderAttemptContextError):
        client.run_research(plan)
    assert calls == []

    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=_started_provider_attempt,
        assertion_callback=_started_provider_attempt,
        estimated_attempt_cost=0.1,
    )
    result = client.run_research(plan)
    assert result.request_id == context.request_id
    assert calls == ["caller"]


@pytest.mark.parametrize(
    ("context_request_id", "confirmation_request_id", "caller_count"),
    [
        ("ARBITRARY-BUT-MATCHED", "ARBITRARY-BUT-MATCHED", 0),
        ("direct:research:1", "ARBITRARY-BUT-MATCHED", 0),
        ("ARBITRARY-BUT-MATCHED", "direct:research:1", 0),
        ("direct:research:2", "direct:research:1", 0),
        ("direct:other-stage:1", "direct:research:1", 0),
        ("other-job:research:1", "direct:research:1", 0),
        ("direct:research:1", "direct:research:1", 1),
    ],
    ids=[
        "arbitrary-matched", "callback-arbitrary", "context-arbitrary",
        "attempt-mismatch", "stage-mismatch", "job-mismatch", "valid",
    ],
)
def test_direct_client_derives_request_identity_before_caller(
        context_request_id, confirmation_request_id, caller_count):
    calls: list[str] = []
    context = _direct_durable_context(context_request_id)
    client = AnthropicResearchClient(
        "offline", "model",
        caller=lambda _plan: calls.append("caller") or (
            _valid_research_response(), Usage(),
        ),
    )
    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=lambda active: _started_provider_attempt(
            active, request_id=confirmation_request_id,
        ),
        assertion_callback=_started_provider_attempt,
        estimated_attempt_cost=0.1,
    )

    if caller_count:
        result = client.run_research(ResearchPlan(topic_id=1, account_id="a", question="Why?"))
        assert result.request_id == "direct:research:1"
    else:
        with pytest.raises(ProviderRequestIdentityMismatch):
            client.run_research(ResearchPlan(topic_id=1, account_id="a", question="Why?"))
    assert calls == ["caller"] * caller_count


def test_request_identity_rejects_stage_separator_without_normalization():
    with pytest.raises(ProviderRequestIdentityMismatch):
        expected_provider_request_id("direct", "research:collision", 1)
    assert expected_provider_request_id(" Direct ", "Research", 1) == " Direct :Research:1"


def test_direct_sdk_request_uses_exact_derived_idempotency_key(monkeypatch):
    captured: list[dict] = []
    context = _direct_durable_context()

    class Messages:
        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=_valid_research_response())],
                usage=SimpleNamespace(
                    input_tokens=1, output_tokens=1,
                    cache_read_input_tokens=0, cache_creation_input_tokens=0,
                ),
                stop_reason="end_turn",
            )

    class SDK:
        messages = Messages()

    client = AnthropicResearchClient("offline", "model")
    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=_started_provider_attempt,
        assertion_callback=_started_provider_attempt,
        estimated_attempt_cost=0.1,
    )
    monkeypatch.setattr(client, "_import_anthropic", lambda: object())
    monkeypatch.setattr(client, "_new_anthropic_client", lambda _sdk: SDK())

    result = client.run_research(
        ResearchPlan(topic_id=1, account_id="a", question="Why?")
    )

    assert len(captured) == 1
    assert captured[0]["extra_headers"] == {"Idempotency-Key": "direct:research:1"}
    assert "exactly ONE compact single-line JSON object" in captured[0]["messages"][0]["content"]
    assert result.stop_reason == "end_turn"
    assert result.raw_text == _valid_research_response()


def _storage_gated_direct_client(
    storage, execution: JobExecutionContext, context: DurableProviderAttemptContext,
    calls: list[str], *, after_context=None, before_sdk_assertion=None,
) -> AnthropicResearchClient:
    def context_callback(_attempt):
        if after_context is not None:
            after_context()
        return context

    def activation_callback(active):
        storage.mark_provider_attempt_request_started(execution, active.request_id)
        return storage.assert_durable_provider_attempt_active(
            active, clock=execution.clock,
        )

    def assertion_callback(active):
        if before_sdk_assertion is not None:
            before_sdk_assertion()
        return storage.assert_durable_provider_attempt_active(
            active, clock=execution.clock,
        )

    client = AnthropicResearchClient(
        "offline", "model",
        caller=lambda _plan: calls.append("caller") or (
            _valid_research_response(), Usage(),
        ),
    )
    client.configure_durable_attempt_control(
        context_callback=context_callback,
        activation_callback=activation_callback,
        assertion_callback=assertion_callback,
        estimated_attempt_cost=0.1,
    )
    return client


def _provider_context_for_execution(
    execution: JobExecutionContext, request_id: str, *, checked_at: datetime,
) -> DurableProviderAttemptContext:
    return DurableProviderAttemptContext(
        job_id=execution.job_id,
        run_id=execution.run_id,
        stage="research",
        attempt_no=1,
        request_id=request_id,
        lease_owner=execution.lease_owner,
        fence_token=(
            f"{execution.job_id}:{execution.run_id}:{execution.lease_owner}"
        ),
        checked_at=checked_at,
    )


@pytest.mark.parametrize(
    ("checked_at", "authoritative_now", "caller_count"),
    [
        (NOW + timedelta(seconds=119), NOW + timedelta(seconds=121), 0),
        (NOW, NOW + timedelta(seconds=119), 1),
        (NOW, NOW + timedelta(seconds=120), 1),
        (NOW, NOW + timedelta(seconds=120, microseconds=1), 0),
    ],
    ids=["expired-despite-old-context", "fresh-before-expiry", "exact-boundary", "microsecond-expired"],
)
def test_direct_client_uses_fresh_authoritative_clock_for_lease(
        storage, account, checked_at, authoritative_now, caller_count):
    seed = _execution(storage, account, _topic(storage, account, "fresh-clock"), "fresh-clock", 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    clock = MutableClock(authoritative_now)
    execution = replace(seed, clock=clock)
    context = _provider_context_for_execution(
        execution, attempt.request_id, checked_at=checked_at,
    )
    calls: list[str] = []
    client = _storage_gated_direct_client(storage, execution, context, calls)

    if caller_count:
        client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    else:
        with pytest.raises(StaleJobExecutionError):
            client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    assert calls == ["caller"] * caller_count


def test_fresh_assertion_observes_lease_renewal_after_context_creation(storage, account):
    seed = _execution(storage, account, _topic(storage, account, "renewed-lease"), "renewed-lease", 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    clock = MutableClock(NOW + timedelta(seconds=119))
    execution = replace(seed, clock=clock)
    context = _provider_context_for_execution(execution, attempt.request_id, checked_at=NOW)

    def renew_after_context():
        storage.heartbeat_job_lease(
            execution.job_id, execution.lease_owner, 120, clock=clock,
        )
        clock.moment = NOW + timedelta(seconds=121)

    calls: list[str] = []
    client = _storage_gated_direct_client(
        storage, execution, context, calls, after_context=renew_after_context,
    )
    client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    assert calls == ["caller"]


@pytest.mark.parametrize("mutation", ["lease-takeover", "run-fence-change", "needs-reconciliation"])
def test_fresh_assertion_blocks_state_changes_after_context_creation(
        storage, account, mutation):
    seed = _execution(storage, account, _topic(storage, account, mutation), mutation, 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    clock = MutableClock(NOW + timedelta(seconds=119))
    execution = replace(seed, clock=clock)
    context = _provider_context_for_execution(execution, attempt.request_id, checked_at=NOW)

    def mutate_after_context():
        if mutation == "lease-takeover":
            storage.conn.execute(
                "UPDATE jobs SET lease_owner='other-worker' WHERE id=?", (execution.job_id,),
            )
            storage.conn.commit()
        elif mutation == "run-fence-change":
            storage.conn.execute("UPDATE jobs SET run_id=NULL WHERE id=?", (execution.job_id,))
            storage.conn.commit()
        else:
            storage.mark_provider_attempt_request_started(execution, context.request_id)
            storage.mark_provider_attempt_needs_reconciliation(
                execution, context.request_id, error_code="ResearchTimeout",
            )

    calls: list[str] = []
    client = _storage_gated_direct_client(
        storage, execution, context, calls, after_context=mutate_after_context,
    )
    with pytest.raises(StaleJobExecutionError):
        client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    assert calls == []


@pytest.mark.parametrize("mutation", ["lease-expiry", "job-status", "fence-token"])
def test_research_final_boundary_blocks_late_state_changes_without_usage_or_cost(
        storage, account, mutation):
    seed = _execution(storage, account, _topic(storage, account, f"final-{mutation}"),
                      f"final-{mutation}", 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    context = _provider_context_for_execution(seed, attempt.request_id, checked_at=NOW)

    def mutate_before_provider():
        if mutation == "lease-expiry":
            storage.conn.execute(
                "UPDATE jobs SET lease_expires_at=? WHERE id=?",
                ("2026-07-14 11:59:59", seed.job_id),
            )
            storage.conn.commit()
        elif mutation == "job-status":
            storage.conn.execute(
                "UPDATE jobs SET status='DONE',lease_owner=NULL,lease_expires_at=NULL WHERE id=?",
                (seed.job_id,),
            )
            storage.conn.commit()
        else:
            object.__setattr__(context, "fence_token", "tampered-fence")

    calls: list[str] = []
    client = _storage_gated_direct_client(
        storage, seed, context, calls, before_sdk_assertion=mutate_before_provider,
    )
    expected_error = sqlite3.IntegrityError if mutation == "job-status" else StaleJobExecutionError
    with pytest.raises(expected_error) as raised:
        client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    if mutation == "job-status":
        assert "provider_attempt normalization" in str(raised.value)
        storage.conn.rollback()
        assert storage.get_job(seed.job_id).status is JobStatus.RUNNING
    assert calls == []
    assert storage.get_research_usage(seed.run_id) == []
    assert storage.get_run(seed.run_id).cost_usd == 0.0


@pytest.mark.parametrize("mutation", [
    "lease-owner", "lease-expiry", "run-id", "job-status", "attempt-status", "fence-token",
])
def test_topics_final_boundary_blocks_all_late_state_changes_without_usage_or_cost(
        monkeypatch, storage, account, mutation):
    seed = _execution(storage, account, _topic(storage, account, f"topics-{mutation}"),
                      f"topics-{mutation}", 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="topics", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    context = DurableProviderAttemptContext(
        job_id=seed.job_id, run_id=seed.run_id, stage="topics", attempt_no=1,
        request_id=attempt.request_id, lease_owner=seed.lease_owner,
        fence_token=f"{seed.job_id}:{seed.run_id}:{seed.lease_owner}", checked_at=NOW,
    )
    message_calls: list[dict] = []

    class Messages:
        def create(self, **kwargs):
            message_calls.append(kwargs)
            raise AssertionError("messages.create must not run after a rejected final assertion")

    class FakeAPIError(Exception):
        pass

    fake_sdk = SimpleNamespace(
        APIError=FakeAPIError,
        Anthropic=lambda **_kwargs: SimpleNamespace(messages=Messages()),
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_sdk)

    def activation_callback(active):
        storage.mark_provider_attempt_request_started(seed, active.request_id)
        return storage.assert_durable_provider_attempt_active(active, clock=seed.clock)

    def assertion_callback(active):
        if mutation == "lease-owner":
            storage.conn.execute("UPDATE jobs SET lease_owner='other' WHERE id=?", (seed.job_id,))
            storage.conn.commit()
        elif mutation == "lease-expiry":
            storage.conn.execute(
                "UPDATE jobs SET lease_expires_at=? WHERE id=?",
                ("2026-07-14 11:59:59", seed.job_id),
            )
            storage.conn.commit()
        elif mutation == "run-id":
            storage.conn.execute("UPDATE jobs SET run_id=NULL WHERE id=?", (seed.job_id,))
            storage.conn.commit()
        elif mutation == "job-status":
            storage.conn.execute(
                "UPDATE jobs SET status='DONE',lease_owner=NULL,lease_expires_at=NULL WHERE id=?",
                (seed.job_id,),
            )
            storage.conn.commit()
        elif mutation == "attempt-status":
            storage.mark_provider_attempt_needs_reconciliation(
                seed, active.request_id, error_code="test",
            )
        else:
            object.__setattr__(context, "fence_token", "tampered-fence")
        return storage.assert_durable_provider_attempt_active(active, clock=seed.clock)

    client = AnthropicLLMClient("test-key", "topics-model")
    client.configure_durable_attempt_control(
        context_callback=lambda _budget: context,
        activation_callback=activation_callback,
        assertion_callback=assertion_callback,
    )
    expected_error = sqlite3.IntegrityError if mutation == "job-status" else StaleJobExecutionError
    with pytest.raises(expected_error) as raised:
        client.generate_and_score_topics(account, 1)
    if mutation == "job-status":
        assert "provider_attempt normalization" in str(raised.value)
        storage.conn.rollback()
        assert storage.get_job(seed.job_id).status is JobStatus.RUNNING
    assert message_calls == []
    assert storage.get_research_usage(seed.run_id) == []
    assert storage.get_run(seed.run_id).cost_usd == 0.0


def test_fresh_sdk_assertion_blocks_lease_takeover_before_messages_create(
        monkeypatch, storage, account):
    seed = _execution(storage, account, _topic(storage, account, "sdk-reassert"), "sdk-reassert", 0.2)
    attempt = storage.begin_provider_attempt(
        seed, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    clock = MutableClock(NOW + timedelta(seconds=119))
    execution = replace(seed, clock=clock)
    context = _provider_context_for_execution(execution, attempt.request_id, checked_at=NOW)
    created: list[dict] = []

    class Messages:
        def create(self, **kwargs):
            created.append(kwargs)
            raise AssertionError("messages.create must not run after a lost lease")

    class SDK:
        messages = Messages()

    def activation_callback(active):
        storage.mark_provider_attempt_request_started(execution, active.request_id)
        return storage.assert_durable_provider_attempt_active(active, clock=clock)

    def assertion_callback(active):
        storage.conn.execute(
            "UPDATE jobs SET lease_owner='other-worker' WHERE id=?", (execution.job_id,),
        )
        storage.conn.commit()
        return storage.assert_durable_provider_attempt_active(active, clock=clock)

    client = AnthropicResearchClient("offline", "model")
    client.configure_durable_attempt_control(
        context_callback=lambda _attempt: context,
        activation_callback=activation_callback,
        assertion_callback=assertion_callback,
        estimated_attempt_cost=0.1,
    )
    monkeypatch.setattr(client, "_import_anthropic", lambda: object())
    monkeypatch.setattr(client, "_new_anthropic_client", lambda _sdk: SDK())

    with pytest.raises(StaleJobExecutionError):
        client.run_research(ResearchPlan(topic_id=1, account_id=account.id, question="Why?"))
    assert created == []


def test_direct_real_sdk_helper_cannot_reach_messages_create_without_context(monkeypatch):
    created: list[dict] = []

    class Messages:
        def create(self, **kwargs):
            created.append(kwargs)
            raise AssertionError("messages.create must not be reached")

    class SDK:
        messages = Messages()

    client = AnthropicResearchClient("offline", "model")
    monkeypatch.setattr(client, "_import_anthropic", lambda: object())
    monkeypatch.setattr(client, "_new_anthropic_client", lambda _sdk: SDK())
    with pytest.raises(DurableProviderAttemptContextError):
        client._default_caller(ResearchPlan(topic_id=1, account_id="a", question="Why?"))
    assert created == []


def _durable_payload(settings, account, topic, *, cap: object = 1.0,
                     max_tokens: object = 3000, intent_changes: dict | None = None,
                     pricing_profile=None) -> dict:
    pricing_kwargs = {}
    if pricing_profile is not None:
        pricing_kwargs = {
            "pricing_prices": pricing_profile.prices,
            "pricing_profile_id": pricing_profile.profile_id,
            "pricing_profile_version": pricing_profile.version,
            "pricing_currency": pricing_profile.currency,
            "pricing_unit": pricing_profile.unit,
        }
    intent = DurableResearchExecutionIntent.from_settings(
        settings=settings, account_id=account.id, topic_id=int(topic.id),
        cap_usd=cap, max_web_searches=3, question=topic.question or topic.title,
        niche=account.niche, max_tokens=max_tokens,
        **pricing_kwargs,
    ).as_payload()
    if intent_changes:
        intent.update(intent_changes)
    return {
        "account_id": account.id, "topic_id": int(topic.id), "dry_run": False,
        "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": cap,
        "execution_intent": intent,
    }


def test_operation_intent_is_schema_canonical_and_conflicts_on_execution_change(
        settings, storage, account):
    topic = _topic(storage, account, "intent")
    real = replace(
        settings, dry_run=False, anthropic_api_key="offline-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    base_payload = _durable_payload(real, account, topic, cap=1.0)
    first = storage.enqueue_job_result(_operation_job(
        account, topic, "intent-first", "intent-key", cap=1.0, payload=base_payload,
    ))
    assert first.created

    equivalent = _durable_payload(real, account, topic, cap=1)
    equivalent["execution_intent"]["max_tokens"] = 3000.0
    equivalent["execution_intent"]["pricing_profile"] = {
        key: 1 if key == "input_per_mtok" else value
        for key, value in equivalent["execution_intent"]["pricing_profile"].items()
    }
    assert storage.enqueue_job_result(_operation_job(
        account, topic, "intent-equivalent", "intent-key", cap=1, payload=equivalent,
    )).created is False

    changed_payloads = [
        _durable_payload(real, account, topic, intent_changes={"model": "other-model"}),
        _durable_payload(real, account, topic, intent_changes={"provider": "other-provider"}),
        _durable_payload(real, account, topic, intent_changes={"timeout_seconds": 61}),
        _durable_payload(real, account, topic, intent_changes={"max_tokens": 3001}),
        _durable_payload(real, account, topic, intent_changes={"pipeline_version": "single-research-v2"}),
        _durable_payload(real, account, topic, cap=1.000001),
    ]
    repriced = replace(real, pricing={**real.pricing, "input_per_mtok": 2.0})
    changed_payloads.append(_durable_payload(repriced, account, topic))
    for number, payload in enumerate(changed_payloads):
        with pytest.raises((JobConflictError, JobPayloadValidationError)):
            storage.enqueue_job_result(_operation_job(
                account, topic, f"intent-change-{number}", "intent-key", payload=payload,
            ))


def test_sub_quantum_provider_reservation_policy_is_typed(storage, account):
    topic = _topic(storage, account, "sub-quantum")
    execution = _execution(storage, account, topic, "sub-quantum", 1.0)
    for invalid in (0, -1, float("nan"), float("inf")):
        with pytest.raises(BudgetReservationError):
            storage.begin_provider_attempt(
                execution, stage="research", attempt_no=1, max_cost_usd=invalid,
                daily_limit_usd=2.0, monthly_limit_usd=40.0,
            )
    with pytest.raises(AmountBelowMinimumPrecisionError):
        storage.begin_provider_attempt(
            execution, stage="research", attempt_no=1, max_cost_usd=0.0000004,
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
    rounded = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.0000005,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    assert rounded.reserved_amount_usd == 0.000001


def test_attempt_two_is_atomically_blocked_after_needs_reconciliation(
        settings, storage, account):
    topic = _topic(storage, account, "reconciliation-race")
    execution = _execution(storage, account, topic, "reconciliation-race", 0.2)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.mark_provider_attempt_needs_reconciliation(
        execution, attempt.request_id, error_code="ResearchTimeout",
    )
    barrier = threading.Barrier(2)

    def retry() -> str:
        connection = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait()
            connection.begin_provider_attempt(
                execution, stage="research", attempt_no=2, max_cost_usd=0.2,
                daily_limit_usd=2.0, monthly_limit_usd=40.0,
            )
        except ProviderAttemptReconciliationRequired:
            return "blocked"
        finally:
            connection.close()
        return "unexpected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _value: retry(), range(2))) == ["blocked", "blocked"]
    rows = storage.conn.execute(
        "SELECT attempt_no,status FROM provider_attempts WHERE job_id=?", (execution.job_id,),
    ).fetchall()
    assert [tuple(row) for row in rows] == [(1, "NEEDS_RECONCILIATION")]


def test_worker_uses_persisted_intent_after_runtime_settings_change(
        monkeypatch, settings, storage, account):
    from app.scheduler import dispatcher

    topic = _topic(storage, account, "worker-intent")
    queued_settings = replace(
        settings, dry_run=False, anthropic_api_key="queued-key", model_quality="queued-model",
        research_timeout_seconds=37,
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    profile_id, pricing_path = write_approved_pricing_profile(
        queued_settings.project_root,
        model=queued_settings.model_quality,
        prices=dict(queued_settings.pricing),
    )
    pricing_profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=queued_settings.model_quality,
    )
    payload = _durable_payload(
        queued_settings,
        account,
        topic,
        cap=0.7,
        max_tokens=3107,
        pricing_profile=pricing_profile,
    )
    job = storage.enqueue_job(_operation_job(
        account, topic, "worker-intent", "worker-intent", cap=0.7, payload=payload,
    ))
    lease = storage.claim_next_job("worker-intent", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    changed_settings = replace(
        queued_settings, model_quality="changed-model", research_timeout_seconds=99,
        pricing={key: 2.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    captured = {}

    def fake_pipeline(_account, _topic, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(dispatcher, "run_research_pipeline", fake_pipeline)
    dispatcher._run_durable_real_research(
        account, topic, settings=changed_settings, storage=storage,
        policy=PolicyEngine(changed_settings, storage, FixedClock(NOW)), clock=FixedClock(NOW),
        job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
    )
    client = captured["research_client"]
    assert captured["settings"].model_quality == "queued-model"
    assert captured["settings"].research_timeout_seconds == 37
    assert captured["settings"].pricing == {key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS}
    assert client.model == "queued-model"
    assert client._timeout_seconds == 37
    assert client._research_max_tokens == 3107
    assert client._max_web_searches == 3
    assert captured["run_cap_usd"] == 0.7
    assert captured["request_max_tokens"] == 3107


def test_durable_provider_v1_is_rejected_at_enqueue_and_initialization(storage, account):
    topic = _topic(storage, account, "v1-rejected")
    legacy = _real_job(account, topic, "v1-rejected", 0.2).model_copy(update={
        "payload": {
            "account_id": account.id,
            "topic_id": int(topic.id),
            "dry_run": False,
            "execution": "durable_provider_v1",
            "mode": "single",
            "max_cost_usd": 0.2,
        },
    })
    with pytest.raises(JobConflictError) as raised:
        storage.enqueue_job(legacy)
    assert raised.value.code == "UNSUPPORTED_EXECUTION_CONTRACT"


def test_0013_blocks_direct_provider_attempt_or_job_delete_with_real_usage(storage, account):
    execution = _execution(storage, account, _topic(storage, account, "delete-integrity"),
                           "delete-integrity", 0.2)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    storage.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, provider="anthropic", model="test", task="research",
        input_tokens=1, output_tokens=1, estimated_cost_usd=0.01, dry_run=False,
        request_id=attempt.request_id,
    ))

    for statement, parameters in (
        ("DELETE FROM provider_attempts WHERE request_id=?", (attempt.request_id,)),
        ("DELETE FROM jobs WHERE id=?", (execution.job_id,)),
    ):
        with pytest.raises(sqlite3.IntegrityError, match="non-legacy model_usage"):
            storage.conn.execute(statement, parameters)
        storage.conn.rollback()

    assert storage.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert storage.conn.execute(
        "SELECT u.id FROM model_usage u LEFT JOIN provider_attempts p "
        "ON p.request_id=u.request_id WHERE u.dry_run=0 AND u.is_legacy_usage=0 "
        "AND p.request_id IS NULL"
    ).fetchall() == []


@pytest.mark.parametrize("api_key", [None, "", "sk-ant-looking-key"])
def test_offline_client_requires_fake_root_caller_before_sdk_construction(monkeypatch, api_key):
    """A missing root fake blocks construction, hence also every root call path."""
    constructed: list[object] = []

    class UnexpectedSDK:
        def __init__(self, *_args, **_kwargs):
            constructed.append(object())

    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=UnexpectedSDK))
    module = importlib.import_module("app.research.anthropic_client")

    with pytest.raises(ValueError, match="explicit fake caller"):
        module.OfflineAnthropicResearchClient(api_key, "test-model")

    # run_research cannot be reached either: root construction is intentionally
    # fail-fast, before a direct import could construct an SDK or call messages.create.
    assert constructed == []


def test_offline_client_requires_staged_fake_callers_and_never_constructs_sdk():

    client = OfflineAnthropicResearchClient(
        "sk-ant-looking-key", "test-model",
        caller=lambda _plan: (_valid_research_response(), Usage()),
    )
    with pytest.raises(RuntimeError, match="never constructs"):
        client._new_anthropic_client(object())
    with pytest.raises(RuntimeError, match="explicit fake caller for extract_source"):
        client.extract_source(
            ResearchPlan(topic_id=1, account_id="a", question="Why?"),
            SimpleNamespace(url="https://example.test", title="Test"),
        )
    with pytest.raises(RuntimeError, match="explicit fake caller for synthesize_from_cards"):
        client.synthesize_from_cards(
            ResearchPlan(topic_id=1, account_id="a", question="Why?"), [],
        )


def test_durable_v2_worker_flow_calls_fake_provider_once_and_terminalizes(
        monkeypatch, settings, storage, account):
    from app.scheduler import dispatcher as dispatcher_module

    topic = _topic(storage, account, "worker-v2-e2e")
    real_settings = replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-only-key",
        model_quality="persisted-v2-model",
        research_timeout_seconds=31,
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    profile_id, pricing_path = write_approved_pricing_profile(
        real_settings.project_root,
        model=real_settings.model_quality,
        prices=dict(real_settings.pricing),
    )
    pricing_profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real_settings.model_quality,
    )
    payload = _durable_payload(
        real_settings,
        account,
        topic,
        cap=1.0,
        pricing_profile=pricing_profile,
    )
    job = storage.enqueue_job(_operation_job(
        account, topic, "worker-v2-e2e", "worker-v2-e2e", cap=1.0, payload=payload,
    ))
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="v2-e2e", now=NOW)

    calls: list[str] = []

    def fake_provider(_plan):
        calls.append("provider")
        return _valid_research_response(), Usage(
            input_tokens=10, output_tokens=10, web_search_requests=1
        )

    def fake_client(*args, **kwargs):
        return AnthropicResearchClient(*args, caller=fake_provider, **kwargs)

    monkeypatch.setattr(dispatcher_module, "AnthropicResearchClient", fake_client)
    clock = FixedClock(NOW)
    policy = PolicyEngine(real_settings, storage, clock)
    dispatcher = JobDispatcher(settings=real_settings, storage=storage, policy=policy, clock=clock)
    worker = Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner="worker-v2-e2e",
        lease_seconds=120,
        heartbeat_interval_seconds=1,
        heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real_settings.db_path),
        clock=clock,
    )

    result = worker.run_once()
    assert result.status is WorkerIterationStatus.DONE
    assert result.job_id == job.id
    assert calls == ["provider"]
    assert storage.get_job(job.id).status is JobStatus.DONE
    run = storage.get_job(job.id).run_id
    assert run is not None
    assert storage.get_run(run).status is RunStatus.SUCCESS
    assert storage.get_research_run(run).status.value == "COMPLETE"
    assert next(t for t in storage.list_topics(account.id) if t.id == topic.id).status is TopicStatus.USED
    assert storage.conn.execute(
        "SELECT status FROM provider_attempts WHERE job_id=?", (job.id,)
    ).fetchone()["status"] == "SETTLED"
    assert storage.conn.execute("SELECT count(*) FROM model_usage WHERE run_id=?", (run,)).fetchone()[0] == 1


def _upgrade_0010_to_0011_only(conn: sqlite3.Connection, tmp_path: Path) -> None:
    migrations = tmp_path / "migrations-0011-only"
    migrations.mkdir()
    shutil.copy2(
        MIGRATIONS_DIR / "0011_provider_attempt_invariants.sql",
        migrations / "0011_provider_attempt_invariants.sql",
    )
    assert apply_migrations(conn, migrations) == ["0011_provider_attempt_invariants"]


def _add_linked_0011_usage(conn: sqlite3.Connection, *, usage_run_id: str = "run",
                           request_id: str = "job:linked:1") -> None:
    conn.execute("UPDATE jobs SET run_id='run' WHERE id='job'")
    conn.execute(
        "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,status,"
        "reserved_amount_usd,reserved_at) VALUES ('job','linked',1,?,'RESERVED',0.2,"
        "'2026-07-14 12:00:00')",
        (request_id,),
    )
    conn.execute(
        "UPDATE provider_attempts SET status='REQUEST_STARTED',request_started_at="
        "'2026-07-14 12:00:01' WHERE request_id=?", (request_id,),
    )
    conn.execute(
        "INSERT INTO model_usage (run_id,model,dry_run,request_id,estimated_cost_usd) "
        "VALUES (?, 'linked', 0, ?, 0.03)", (usage_run_id, request_id),
    )
    conn.commit()


def test_migration_0012_keeps_provable_usage_nonlegacy_and_reopens_cleanly(tmp_path: Path):
    conn = _database_at_0010(tmp_path)
    _seed_0010_provider_history(conn, valid=True)
    _upgrade_0010_to_0011_only(conn, tmp_path)
    _add_linked_0011_usage(conn)
    assert apply_migrations(conn) == [
            "0012_provider_ledger_hardening", "0013_provider_attempt_usage_integrity",
            "0014_provider_attempt_reconciliation", "0015_settled_execution_recovery", "0016_evidence_foundation", "0017_evidence_pipeline_lineage", "0018_controlled_fetch_lifecycle", "0019_evidence_research_approvals",
            "0020_topic_generation_lifecycle",
    ]
    states = {
        row["model"]: row["is_legacy_usage"]
        for row in conn.execute("SELECT model,is_legacy_usage FROM model_usage")
    }
    assert states == {"legacy": 1, "linked": 0}
    assert apply_migrations(conn) == []
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    triggers = {
        row["name"] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    assert {
        "provider_attempts_no_retry_without_resolver",
        "model_usage_requires_request_job_run_relation",
        "model_usage_legacy_proof_required",
    } <= triggers
    conn.close()


@pytest.mark.parametrize("kind", ["arbitrary_attempt", "foreign_run", "missing_request"])
def test_migration_0012_rolls_back_contradictory_ledger_history(tmp_path: Path, kind: str):
    conn = _database_at_0010(tmp_path)
    _seed_0010_provider_history(conn, valid=True)
    _upgrade_0010_to_0011_only(conn, tmp_path)
    if kind == "arbitrary_attempt":
        conn.execute("DROP TRIGGER provider_attempts_identity_is_immutable")
        conn.execute("DROP TRIGGER provider_attempts_controlled_transition")
        conn.execute("UPDATE provider_attempts SET request_id='arbitrary' WHERE stage='research'")
        conn.commit()
    elif kind == "foreign_run":
        conn.execute(
            "INSERT INTO runs (id,account_id,workflow,status) VALUES ('other','a','RESEARCH','RUNNING')"
        )
        _add_linked_0011_usage(conn, usage_run_id="other")
    else:
        conn.execute("DROP TRIGGER model_usage_requires_active_attempt")
        conn.execute(
            "INSERT INTO model_usage (run_id,model,dry_run,request_id,estimated_cost_usd) "
            "VALUES ('run','missing',0,'missing:research:1',0.03)"
        )
        conn.commit()

    before_attempts = [tuple(row) for row in conn.execute(
        "SELECT job_id,stage,attempt_no,request_id,status FROM provider_attempts ORDER BY stage"
    )]
    before_usage = [tuple(row) for row in conn.execute(
        "SELECT run_id,model,request_id,is_legacy_usage FROM model_usage ORDER BY id"
    )]
    with pytest.raises(sqlite3.IntegrityError):
        apply_migrations(conn)
    assert conn.execute(
        "SELECT count(*) FROM schema_migrations WHERE version='0012_provider_ledger_hardening'"
    ).fetchone()[0] == 0
    assert before_attempts == [tuple(row) for row in conn.execute(
        "SELECT job_id,stage,attempt_no,request_id,status FROM provider_attempts ORDER BY stage"
    )]
    assert before_usage == [tuple(row) for row in conn.execute(
        "SELECT run_id,model,request_id,is_legacy_usage FROM model_usage ORDER BY id"
    )]
    assert "legacy_model_usage_proofs" not in {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
