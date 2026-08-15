"""Controlled-live TOPIC_GENERATION acceptance; temp DBs and fake callers only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.clock import FixedClock, SystemClock
from app.core.config import load_settings
from app.core.pricing import (
    default_pricing_profiles_path,
    load_pricing_profiles,
    resolve_real_pricing_profile,
)
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.base import LLMProviderError, Usage
from app.model_routing import LogicalModelRole, ModelFamily
from app.models import (
    Job, JobExecutionContext, JobKind, JobStatus, WorkflowType,
)
from app.operations.controlled_live import (
    OPEN_PROFILE_ORDER,
    acquire_session_marker,
    confirm_flags,
    default_db_fingerprint,
    is_fail_closed,
    marker_path,
    restore_fail_closed,
)
from app.operations.stage1_migration import _git_identity
from app.operations.topic_generation_live import (
    EXIT_POLICY_RESTORE_FAILED,
    EXIT_PREFLIGHT_REFUSED,
    EXIT_RECONCILIATION_REQUIRED,
    EXIT_RECOVERY_BARRIER_FAILED,
    EXIT_SUCCESS,
    EXIT_TERMINAL_FAILURE,
    TopicGenerationLiveRequest,
    run_topic_generation_live_once,
)
from app.storage.db import RUNTIME_SCHEMA_VERSION, initialize_database
from app.storage.repositories import SqliteStorage
from app.topics.durable_intent import (
    DurableTopicGenerationIntent,
    frozen_topic_generation_contract,
)
from tests.test_topic_generation_runtime import (
    DIMENSIONS,
    NOW,
    _FakeTopicCaller,
    _job,
    _payload,
    _prepare,
    _pricing_profile,
    _real_settings,
    _response,
)
from tests.controlled_provider_fixtures import seed_model, seed_role_policy

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "controlled-live-test-branch"
HEAD = "controlled-live-test-head"
QUIESCENT = {
    "project_process_ids": (),
    "scheduled_tasks": (),
    "locked_paths": (),
}


def _factory(caller):
    def build(client_settings, intent):
        return AnthropicLLMClient(
            client_settings.anthropic_api_key,
            intent.model,
            caller=caller,
            timeout_seconds=float(intent.timeout_seconds),
            topic_max_tokens=intent.max_tokens,
        )

    return build


def _request(settings, account, job, intent, **overrides):
    fingerprint = default_db_fingerprint(settings.db_path)
    _, _, intent_fingerprint = frozen_topic_generation_contract(job.payload)
    values = {
        "job_id": job.id,
        "account_id": account.id,
        "expected_intent_fingerprint": intent_fingerprint,
        "expected_model": intent.model,
        "expected_max_tokens": intent.max_tokens,
        "expected_cap_usd": intent.cap_usd,
        "expected_candidate_count": intent.candidate_count,
        "expected_db_sha256": fingerprint.sha256,
        "expected_schema": fingerprint.schema_tail,
        "expected_branch": BRANCH,
        "expected_head": HEAD,
        "confirmed": True,
    }
    values.update(overrides)
    return TopicGenerationLiveRequest(**values)


def _prepare_live(settings, storage, account, *, key="live", count=3, approve=True):
    real, intent, job = _prepare(
        settings, storage, account, key=key, count=count, approve=approve,
    )
    real = replace(real, kill_switch=False)
    restore_fail_closed(storage, reason="controlled-live test baseline", now=NOW)
    return real, intent, job


def _other_topic_job(real, storage, account, *, key="other-state", approve=True):
    other_account = account.model_copy(update={
        "id": f"other-{key}",
        "display_name": f"Other {key}",
    })
    storage.ensure_account(other_account)
    profile = _pricing_profile(real)
    intent = DurableTopicGenerationIntent.from_settings(
        settings=real, account_id=other_account.id, cap_usd="1.000000",
        candidate_count=3, niche=other_account.niche, model=real.model_quality,
        max_tokens=1500, score_dimensions=DIMENSIONS,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency, pricing_unit=profile.unit,
    )
    job = storage.enqueue_job(_job(other_account, key, _payload(intent)))
    if approve:
        storage.record_topic_generation_approval(
            job_id=job.id, account_id=other_account.id, approved_by="other-owner",
            expires_at=NOW + timedelta(hours=2), clock=FixedClock(NOW),
        )
    return other_account, intent, job


def _run(
    settings, storage, account, intent, job, caller, tmp_path, *, request=None,
    quiescence=QUIESCENT, failpoint=None, clock=None, worker_factory=None,
):
    request = request or _request(settings, account, job, intent)
    try:
        return run_topic_generation_live_once(
            request,
            settings=settings,
            storage=storage,
            storage_reopener=lambda: SqliteStorage.open_read_only(settings.db_path),
            project_root=settings.project_root,
            runtime_dir=tmp_path / "runtime",
            frozen_quiescence=quiescence,
            clock=clock or FixedClock(NOW),
            git_identity=lambda _root: (BRANCH, HEAD),
            topic_generation_client_factory=_factory(caller),
            failpoint_after_flags_open=failpoint,
            worker_factory=worker_factory,
        )
    finally:
        try:
            storage.close()
        except Exception:
            pass


def _reopen(settings):
    return SqliteStorage.open(settings.db_path)


def test_exact_named_job_runs_one_request_and_replay_runs_zero(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller(_response(0.95, 0.70, 0.20))

    first = _run(real, storage, account, intent, job, caller, tmp_path)

    assert first.exit_code == EXIT_SUCCESS
    assert first.checkpoint.status == "SUCCESS"
    assert first.checkpoint.request_id == f"{job.id}:topics:1"
    assert first.checkpoint.attempt_count == 1
    assert first.checkpoint.usage_count == 1
    assert first.checkpoint.approval_status == "consumed"
    assert first.checkpoint.generated_topics_count == 3
    assert first.checkpoint.selected_topic_id is not None
    assert first.checkpoint.policy_flags_restored is True
    assert len(caller.calls) == 1

    reopened = _reopen(real)
    request = _request(real, account, reopened.get_job(job.id), intent)
    second = _run(real, reopened, account, intent, job, caller, tmp_path, request=request)
    assert second.exit_code == EXIT_PREFLIGHT_REFUSED
    assert len(caller.calls) == 1
    verify = _reopen(real)
    try:
        assert verify.conn.execute(
            "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
        ).fetchone()[0] == 1
        assert verify.conn.execute(
            "SELECT count(*) FROM model_usage WHERE request_id=?",
            (f"{job.id}:topics:1",),
        ).fetchone()[0] == 1
        assert is_fail_closed(confirm_flags(verify))
    finally:
        verify.close()


def test_unrelated_queued_local_job_is_never_claimed(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    other = storage.enqueue_job(Job(
        id="unrelated-local-job",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="unrelated-local-job",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
    ))
    caller = _FakeTopicCaller(_response(0.95))
    outcome = _run(real, storage, account, intent, job, caller, tmp_path)
    assert outcome.exit_code == EXIT_SUCCESS
    verify = _reopen(real)
    try:
        untouched = verify.get_job(other.id)
        assert untouched.status is JobStatus.QUEUED
        assert untouched.attempts == 0
    finally:
        verify.close()


def test_other_claimable_paid_job_refuses_before_request(
    settings, storage, account, tmp_path,
):
    real, intent, target = _prepare_live(settings, storage, account)
    other_account = account.model_copy(update={
        "id": "other-controlled-live-account",
        "display_name": "Other controlled-live account",
    })
    storage.ensure_account(other_account)
    profile = _pricing_profile(real)
    other_intent = DurableTopicGenerationIntent.from_settings(
        settings=real, account_id=other_account.id, cap_usd=intent.cap_usd,
        candidate_count=3, niche=other_account.niche, model=intent.model,
        max_tokens=intent.max_tokens, score_dimensions=DIMENSIONS,
        pricing_prices=profile.prices, pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency, pricing_unit=profile.unit,
    )
    other = storage.enqueue_job(_job(other_account, "competing", _payload(other_intent)))
    caller = _FakeTopicCaller(_response(0.95))
    outcome = _run(real, storage, account, intent, target, caller, tmp_path)
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == "OTHER_CLAIMABLE_PAID_JOB"
    assert caller.calls == []
    verify = _reopen(real)
    try:
        assert verify.get_job(other.id).status is JobStatus.QUEUED
        assert verify.get_job(other.id).attempts == 0
    finally:
        verify.close()


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"expected_intent_fingerprint": "f" * 64}, "INTENT_FINGERPRINT_MISMATCH"),
        ({"expected_model": "different-model"}, "MODEL_MISMATCH"),
        ({"expected_max_tokens": 4096}, "MAX_TOKENS_MISMATCH"),
        ({"expected_cap_usd": "9.000000"}, "CAP_MISMATCH"),
        ({"expected_candidate_count": 4}, "CANDIDATE_COUNT_MISMATCH"),
    ],
)
def test_cli_expected_binding_mismatch_refuses_before_request(
    settings, storage, account, tmp_path, override, reason,
):
    real, intent, job = _prepare_live(settings, storage, account)
    request = _request(real, account, job, intent, **override)
    caller = _FakeTopicCaller(_response(0.95))
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path, request=request,
    )
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == reason
    assert caller.calls == []


def test_missing_approval_refuses_before_request(settings, storage, account, tmp_path):
    real, intent, job = _prepare_live(
        settings, storage, account, approve=False,
    )
    caller = _FakeTopicCaller()
    outcome = _run(real, storage, account, intent, job, caller, tmp_path)
    assert outcome.checkpoint.reason_code == "APPROVAL_MISSING"
    assert caller.calls == []


def test_expired_approval_refuses_before_request(settings, storage, account, tmp_path):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path,
        clock=FixedClock(NOW + timedelta(hours=3)),
    )
    assert outcome.checkpoint.reason_code == "APPROVAL_EXPIRED"
    assert caller.calls == []


def test_consumed_approval_refuses_before_request(settings, storage, account, tmp_path):
    real, intent, job = _prepare_live(settings, storage, account)
    storage.conn.execute(
        "UPDATE topic_generation_approvals SET consumed_at=? WHERE job_id=?",
        ((NOW + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"), job.id),
    )
    storage.conn.commit()
    request = _request(real, account, job, intent)
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path, request=request,
    )
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == "APPROVAL_ALREADY_CONSUMED"
    assert caller.calls == []


def test_existing_attempt_refuses_before_request(settings, storage, account, tmp_path):
    real, intent, job = _prepare_live(settings, storage, account)
    owner = "existing-attempt-owner"
    assert storage.claim_specific_job(job.id, owner, 120, now=NOW) is not None
    storage.mark_job_running(job.id, owner, clock=FixedClock(NOW))
    initialized = storage.initialize_topic_generation_run_for_job(
        job.id, owner, "existing-attempt-run", clock=FixedClock(NOW),
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner=owner, run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    storage.begin_provider_attempt(
        execution, stage="topics", attempt_no=1,
        max_cost_usd=float(intent.pessimistic_cost_usd),
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    request = _request(real, account, storage.get_job(job.id), intent)
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path, request=request,
    )
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == "ATTEMPT_ALREADY_EXISTS"
    assert caller.calls == []


def test_existing_usage_refuses_before_request(settings, storage, account, tmp_path):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller(error=LLMProviderError(
        "known usage", model=intent.model,
        usage=Usage(input_tokens=120, output_tokens=90),
    ))
    first = _run(real, storage, account, intent, job, caller, tmp_path)
    assert first.checkpoint.usage_count == 1
    reopened = _reopen(real)
    request = _request(real, account, reopened.get_job(job.id), intent)
    second = _run(
        real, reopened, account, intent, job, caller, tmp_path, request=request,
    )
    assert second.exit_code == EXIT_PREFLIGHT_REFUSED
    assert second.checkpoint.reason_code == "USAGE_ALREADY_EXISTS"
    assert len(caller.calls) == 1


def test_unknown_job_and_wrong_account_refuse_before_request(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    unknown = _request(real, account, job, intent, job_id="missing-job")
    caller = _FakeTopicCaller()
    first = _run(
        real, storage, account, intent, job, caller, tmp_path, request=unknown,
    )
    assert first.checkpoint.reason_code == "JOB_MISSING"

    storage2 = _reopen(real)
    wrong = _request(real, account, job, intent, account_id="different-account")
    second = _run(
        real, storage2, account, intent, job, caller, tmp_path, request=wrong,
    )
    assert second.checkpoint.reason_code == "JOB_ACCOUNT_MISMATCH"
    assert caller.calls == []


def test_wrong_workflow_refuses_before_request(settings, storage, account, tmp_path):
    storage.ensure_account(account)
    local = storage.enqueue_job(Job(
        id="wrong-workflow",
        account_id=account.id,
        kind=JobKind.LOCAL,
        workflow=WorkflowType.ANALYTICS,
        idempotency_key="wrong-workflow",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
    ))
    restore_fail_closed(storage, reason="wrong workflow baseline", now=NOW)
    real = replace(_real_settings(settings), kill_switch=False)
    profile = _pricing_profile(real)
    intent = DurableTopicGenerationIntent.from_settings(
        settings=real, account_id=account.id, cap_usd="1.0", candidate_count=3,
        niche=account.niche, model=real.model_quality, max_tokens=1500,
        score_dimensions=DIMENSIONS, pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency, pricing_unit=profile.unit,
    )
    fake_job = _job(account, "shape", _payload(intent))
    fake_job.id = local.id
    outcome = _run(real, storage, account, intent, fake_job, _FakeTopicCaller(), tmp_path)
    assert outcome.checkpoint.reason_code == "JOB_TYPE_INVALID"


def test_runtime_quiescence_failure_refuses_before_request(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path,
        quiescence={**QUIESCENT, "project_process_ids": (123,)},
    )
    assert outcome.checkpoint.reason_code == "RUNTIME_NOT_QUIESCENT"
    assert caller.calls == []


@pytest.mark.parametrize(
    ("durable_state", "expected_reason"),
    [
        # Each of these states also keeps the other TOPIC_GENERATION lifecycle
        # active, which is intentionally the earlier and stronger refusal.
        ("active_attempt", "OTHER_ACTIVE_TOPIC_GENERATION"),
        ("needs_verification", "OTHER_ACTIVE_TOPIC_GENERATION"),
        ("needs_reconciliation", "OTHER_ACTIVE_TOPIC_GENERATION"),
        ("unused_paid_approval", "OTHER_UNUSED_PAID_APPROVAL"),
    ],
)
def test_concurrent_durable_state_refuses_without_consuming_it(
    settings, storage, account, tmp_path, durable_state, expected_reason,
):
    real, intent, target = _prepare_live(settings, storage, account)
    other_account, other_intent, other = _other_topic_job(
        real, storage, account, key=durable_state,
    )
    owner = f"owner-{durable_state}"
    lease = storage.claim_specific_job(other.id, owner, 120, now=NOW)
    assert lease is not None
    if durable_state == "unused_paid_approval":
        storage.fail_job(other.id, owner, "terminal other job", clock=FixedClock(NOW))
    else:
        storage.mark_job_running(other.id, owner, clock=FixedClock(NOW))
        initialized = storage.initialize_topic_generation_run_for_job(
            other.id, owner, f"run-{durable_state}", clock=FixedClock(NOW),
        )
        execution = JobExecutionContext(
            job_id=other.id, lease_owner=owner, run_id=initialized.run.id,
            clock=FixedClock(NOW),
        )
        attempt = storage.begin_provider_attempt(
            execution, stage="topics", attempt_no=1,
            max_cost_usd=float(other_intent.pessimistic_cost_usd),
            daily_limit_usd=2.0, monthly_limit_usd=40.0,
        )
        if durable_state in {"needs_verification", "needs_reconciliation"}:
            storage.mark_provider_attempt_request_started(execution, attempt.request_id)
        if durable_state == "needs_verification":
            storage.fail_or_escalate_topic_generation_execution(
                execution, None, "unknown", preserve_for_verification=True,
            )
        elif durable_state == "needs_reconciliation":
            storage.mark_provider_attempt_needs_reconciliation(
                execution, attempt.request_id, error_code="UNKNOWN",
            )
    request = _request(real, account, target, intent)
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, target, caller, tmp_path, request=request,
    )
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == expected_reason
    assert caller.calls == []
    verify = _reopen(real)
    try:
        assert verify.get_job(other.id).status is not JobStatus.DONE
        approval = verify.get_topic_generation_approval_for_job(other.id)
        if durable_state == "unused_paid_approval":
            assert approval.consumed_at is None
        else:
            assert verify.conn.execute(
                "SELECT count(*) FROM provider_attempts WHERE job_id=?", (other.id,),
            ).fetchone()[0] == 1
    finally:
        verify.close()


@pytest.mark.parametrize("kind", ["exception", "keyboard_interrupt"])
def test_flags_restore_after_failpoint_immediately_after_open(
    settings, storage, account, tmp_path, kind,
):
    real, intent, job = _prepare_live(settings, storage, account)
    error = RuntimeError("after-open") if kind == "exception" else KeyboardInterrupt()

    def failpoint():
        raise error

    outcome = _run(
        real, storage, account, intent, job, _FakeTopicCaller(), tmp_path,
        failpoint=failpoint,
    )
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.reason_code == "EXECUTION_ABORTED_BEFORE_REQUEST"
    assert outcome.checkpoint.policy_flags_restored is True
    verify = _reopen(real)
    try:
        assert is_fail_closed(confirm_flags(verify))
        assert verify.get_job(job.id).status is JobStatus.QUEUED
    finally:
        verify.close()


def test_policy_restore_failure_has_its_own_exit_code(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    request = _request(real, account, job, intent)
    original = storage.apply_security_flag_profile
    calls = 0

    def fail_second_profile(updates, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(updates, **kwargs)
        raise RuntimeError("simulated restore failure")

    storage.apply_security_flag_profile = fail_second_profile
    outcome = run_topic_generation_live_once(
        request, settings=real, storage=storage,
        storage_reopener=lambda: SqliteStorage.open_read_only(real.db_path),
        project_root=real.project_root, runtime_dir=tmp_path / "runtime",
        frozen_quiescence=QUIESCENT, clock=FixedClock(NOW),
        git_identity=lambda _root: (BRANCH, HEAD),
        topic_generation_client_factory=_factory(_FakeTopicCaller()),
        failpoint_after_flags_open=lambda: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    assert outcome.exit_code == EXIT_POLICY_RESTORE_FAILED
    assert outcome.checkpoint.policy_flags_restored is False
    assert marker_path(tmp_path / "runtime").exists()
    # Cleanup is test-only and uses the saved real method after the assertion.
    original(
        [("kill_switch", True), ("safe_mode", True), ("worker_enabled", False),
         ("paid_actions_enabled", False), ("browser_actions_enabled", False)],
        updated_by="test-cleanup", reason="restore failure cleanup", now=NOW,
    )
    storage.close()


def test_provider_failure_without_usage_requires_reconciliation_and_never_retries(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller(error=LLMProviderError("timeout", model=intent.model))
    first = _run(real, storage, account, intent, job, caller, tmp_path)
    assert first.exit_code == EXIT_RECONCILIATION_REQUIRED
    assert first.checkpoint.reconciliation_required is True
    assert first.checkpoint.usage_count == 0
    assert first.checkpoint.policy_flags_restored is True
    assert len(caller.calls) == 1

    second_storage = _reopen(real)
    second_request = _request(real, account, second_storage.get_job(job.id), intent)
    second = _run(
        real, second_storage, account, intent, job, caller, tmp_path,
        request=second_request,
    )
    assert second.exit_code == EXIT_PREFLIGHT_REFUSED
    assert len(caller.calls) == 1


def test_provider_failure_with_usage_is_terminal_and_restores_flags(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    caller = _FakeTopicCaller(error=LLMProviderError(
        "provider rejected", model=intent.model,
        usage=Usage(input_tokens=120, output_tokens=90),
    ))
    outcome = _run(real, storage, account, intent, job, caller, tmp_path)
    assert outcome.exit_code == EXIT_TERMINAL_FAILURE
    assert outcome.checkpoint.job_status == "FAILED"
    assert outcome.checkpoint.attempt_status == "SETTLED"
    assert outcome.checkpoint.usage_count == 1
    assert outcome.checkpoint.policy_flags_restored is True


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        json.dumps({"topics": [{
            "title": "Incomplete", "question": "Why?",
            "score_breakdown": {DIMENSIONS[0]: 0.9},
        }]}),
    ],
)
def test_parse_or_scoring_failure_is_terminal_and_restores_flags(
    settings, storage, account, tmp_path, response,
):
    real, intent, job = _prepare_live(settings, storage, account)
    outcome = _run(
        real, storage, account, intent, job,
        _FakeTopicCaller(response), tmp_path,
    )
    assert outcome.exit_code == EXIT_TERMINAL_FAILURE
    assert outcome.checkpoint.job_status == "FAILED"
    assert outcome.checkpoint.usage_count == 1
    assert outcome.checkpoint.policy_flags_restored is True


def test_worker_uses_specific_claim_and_never_queue_wide_claim(
    settings, storage, account, tmp_path, monkeypatch,
):
    real, intent, job = _prepare_live(settings, storage, account)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("queue-wide claim_next_job must be unreachable")

    monkeypatch.setattr(storage, "claim_next_job", forbidden)
    outcome = _run(
        real, storage, account, intent, job,
        _FakeTopicCaller(_response(0.95)), tmp_path,
    )
    assert outcome.exit_code == EXIT_SUCCESS


def test_no_research_fetch_browser_or_maintenance_root_is_called(
    settings, storage, account, tmp_path, monkeypatch,
):
    real, intent, job = _prepare_live(settings, storage, account)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("forbidden composition root was called")

    monkeypatch.setattr(
        "app.scheduler.maintenance.MaintenanceRunner.run_once", forbidden,
    )
    monkeypatch.setattr(
        "app.workflows.research.controlled_fetch.run_controlled_fetch", forbidden,
    )
    monkeypatch.setattr(
        "app.workflows.research.offline_evidence.run_offline_evidence_research", forbidden,
    )
    outcome = _run(
        real, storage, account, intent, job,
        _FakeTopicCaller(_response(0.95)), tmp_path,
    )
    assert outcome.exit_code == EXIT_SUCCESS


def test_interrupted_marker_restores_snapshot_without_worker_or_maintenance(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    request = _request(real, account, job, intent)
    runtime = tmp_path / "runtime"
    baseline = confirm_flags(storage)
    assert acquire_session_marker(runtime, {
        "operation": "controlled-live-topic-generation",
        "session_id": "interrupted-topic-session",
        "status": "WORKER_RUNNING",
        "job_id": job.id,
        "account_id": account.id,
        "expected_request_id": request.request_id,
        "intent_fingerprint": request.expected_intent_fingerprint,
        "flags_before": baseline,
    })
    storage.apply_security_flag_profile(
        OPEN_PROFILE_ORDER, updated_by="test", reason="simulated process death", now=NOW,
    )
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, account, intent, job, caller, tmp_path, request=request,
    )
    assert outcome.checkpoint.reason_code == "INTERRUPTED_SESSION_RECOVERED_BEFORE_REQUEST"
    assert outcome.exit_code == EXIT_PREFLIGHT_REFUSED
    assert outcome.checkpoint.policy_flags_restored is True
    assert caller.calls == []
    verify = _reopen(real)
    try:
        assert confirm_flags(verify) == baseline
        assert verify.get_job(job.id).status is JobStatus.QUEUED
    finally:
        verify.close()


def test_interrupted_marker_for_another_job_restores_flags_but_retains_marker(
    settings, storage, account, tmp_path,
):
    real, intent, job = _prepare_live(settings, storage, account)
    other_account, other_intent, other = _other_topic_job(
        real, storage, account, key="marker-mismatch",
    )
    original_request = _request(real, account, job, intent)
    other_request = _request(real, other_account, other, other_intent)
    runtime = tmp_path / "runtime"
    baseline = confirm_flags(storage)
    assert acquire_session_marker(runtime, {
        "operation": "controlled-live-topic-generation",
        "session_id": "interrupted-other-topic-session",
        "status": "WORKER_RUNNING",
        "job_id": job.id,
        "account_id": account.id,
        "expected_request_id": original_request.request_id,
        "intent_fingerprint": original_request.expected_intent_fingerprint,
        "flags_before": baseline,
    })
    storage.apply_security_flag_profile(
        OPEN_PROFILE_ORDER, updated_by="test", reason="simulated process death", now=NOW,
    )
    caller = _FakeTopicCaller()
    outcome = _run(
        real, storage, other_account, other_intent, other, caller, tmp_path,
        request=other_request,
    )
    assert outcome.exit_code == EXIT_RECOVERY_BARRIER_FAILED
    assert outcome.checkpoint.reason_code == "RECOVERY_BINDING_MISMATCH"
    assert outcome.checkpoint.policy_flags_restored is True
    assert marker_path(runtime).exists()
    assert caller.calls == []
    verify = _reopen(real)
    try:
        assert confirm_flags(verify) == baseline
        assert verify.get_job(job.id).status is JobStatus.QUEUED
        assert verify.get_job(other.id).status is JobStatus.QUEUED
    finally:
        verify.close()


def _seed_subprocess_job(tmp_path: Path):
    settings = replace(
        load_settings(),
        db_path=tmp_path / "agent.db",
        data_dir=tmp_path,
        dry_run=False,
        kill_switch=False,
    )
    initialize_database(settings.db_path)
    account = settings.get_account("nothing_is_accidental")
    profiles = load_pricing_profiles(default_pricing_profiles_path(settings.project_root))
    assert profiles, "repository must expose at least one approved pricing profile"
    profile = profiles[0]
    intent = DurableTopicGenerationIntent.from_settings(
        settings=settings,
        account_id=account.id,
        cap_usd="1.000000",
        candidate_count=3,
        niche=account.niche,
        model=profile.model,
        max_tokens=1500,
        score_dimensions=DIMENSIONS,
        pricing_prices=profile.prices,
        pricing_profile_id=profile.profile_id,
        pricing_profile_version=profile.version,
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    job = storage.enqueue_job(_job(account, "public-subprocess", _payload(intent)))
    seed_role_policy(storage, LogicalModelRole.TOPIC_GENERATION)
    seed_model(
        storage,
        family=ModelFamily.OPUS,
        provider="ANTHROPIC",
        technical_model_id_override=intent.model,
    )
    storage.promote_best_model(
        LogicalModelRole.TOPIC_GENERATION,
        reason="offline subprocess provider-contract fixture",
    )
    other = storage.enqueue_job(Job(
        id="subprocess-unapproved-local-job", account_id=account.id,
        kind=JobKind.LOCAL, workflow=WorkflowType.ANALYTICS,
        idempotency_key="subprocess-unapproved-local-job",
        payload={"dry_run": True, "action": "noop"},
        schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW,
    ))
    storage.record_topic_generation_approval(
        job_id=job.id,
        account_id=account.id,
        approved_by="subprocess-owner",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        clock=SystemClock(),
    )
    restore_fail_closed(storage, reason="subprocess baseline")
    storage.close()
    return settings, account, intent, job, other


def test_public_cli_subprocess_exact_job_exact_one_request_and_scrubbed_output(tmp_path):
    settings, account, intent, job, other = _seed_subprocess_job(tmp_path)
    _, _, intent_fingerprint = frozen_topic_generation_contract(job.payload)
    fingerprint = default_db_fingerprint(settings.db_path)
    branch, head = _git_identity(ROOT)
    call_log = tmp_path / "caller.log"
    fixture = tmp_path / "fake-topics.json"
    fixture.write_text(json.dumps({
        "response": json.loads(_response(0.95, 0.70, 0.20)),
        "usage": {"input_tokens": 120, "output_tokens": 90},
        "call_log_path": str(call_log),
    }), encoding="utf-8")
    runtime = tmp_path / "runtime-subprocess"
    env = dict(os.environ)
    env.update({
        "NIA_TEST_MODE": "1",
        "NIA_TEST_PROTECTED_DB": str(ROOT / "data" / "agent.db"),
        "NIA_TOPIC_GENERATION_LIVE_FAKE": "1",
        "NIA_TOPIC_GENERATION_LIVE_TEST_DB_PATH": str(settings.db_path),
        "NIA_TOPIC_GENERATION_LIVE_TEST_RUNTIME_DIR": str(runtime),
        "NIA_TOPIC_GENERATION_LIVE_FIXTURE": str(fixture),
        "PYTHONIOENCODING": "utf-8",
    })
    command = [
        sys.executable, "-m", "app.main", "controlled-live-topic-generation",
        "--job-id", job.id,
        "--account-id", account.id,
        "--expected-intent-fingerprint", intent_fingerprint,
        "--expected-model", intent.model,
        "--expected-max-tokens", str(intent.max_tokens),
        "--expected-cap-usd", intent.cap_usd,
        "--expected-candidate-count", str(intent.candidate_count),
        "--expected-db-sha", fingerprint.sha256,
        "--expected-schema", RUNTIME_SCHEMA_VERSION,
        "--expected-branch", branch,
        "--expected-head", head,
        "--confirm-controlled-live-topic-generation",
    ]
    first = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert first.returncode == EXIT_SUCCESS, first.stdout + first.stderr
    checkpoint = json.loads(first.stdout.strip().splitlines()[-1])
    assert checkpoint["status"] == "SUCCESS"
    assert checkpoint["attempt_count"] == 1
    assert checkpoint["usage_count"] == 1
    assert checkpoint["approval_status"] == "consumed"
    assert checkpoint["policy_flags_restored"] is True
    assert call_log.read_text(encoding="utf-8").splitlines() == [f"{account.id}:3"]
    scrubbed = (first.stdout + first.stderr).casefold()
    assert "api_key" not in scrubbed
    assert "prompt_input" not in scrubbed
    assert "anthropic_api_key" not in scrubbed
    inspect = SqliteStorage.open_read_only(settings.db_path)
    try:
        untouched = inspect.get_job(other.id)
        assert untouched.status is JobStatus.QUEUED
        assert untouched.attempts == 0
    finally:
        inspect.close()

    # DB hash is intentionally different after the first run; use the new
    # operator-observed hash so refusal is proved by durable job state, not by a
    # stale file fingerprint.  No second fake caller invocation may appear.
    second_fingerprint = default_db_fingerprint(settings.db_path)
    second_command = list(command)
    sha_index = second_command.index("--expected-db-sha") + 1
    second_command[sha_index] = second_fingerprint.sha256
    second = subprocess.run(
        second_command, cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert second.returncode == EXIT_PREFLIGHT_REFUSED, second.stdout + second.stderr
    assert call_log.read_text(encoding="utf-8").splitlines() == [f"{account.id}:3"]


def test_public_cli_missing_binding_argument_fails_in_argparse_before_runtime(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "controlled-live-topic-generation",
         "--job-id", "x"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "--account-id" in result.stderr
    assert "CONTROLLED-LIVE-TOPIC-GENERATION:" not in result.stdout
