"""Regression coverage for durable execution-intent immutability."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.core.pricing import load_pricing_profiles, resolve_real_pricing_profile
from app.llm.base import Usage
from app.model_routing import LogicalModelRole
from app.models import (
    DurableProviderAttemptContext,
    Job,
    JobExecutionContext,
    JobKind,
    ProviderAttemptStatus,
    Topic,
    TopicStatus,
    WorkflowType,
    ResearchJobExecution,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import JobPayloadValidationError, JobRunRelationError
from app.research.anthropic_client import AnthropicResearchClient
from app.research.base import ResearchPlan
from app.research.durable_intent import (
    DurableResearchExecutionIntent,
    durable_execution_intent_fingerprint,
)
from app.storage.repositories import SqliteStorage
from app.workflows.research.pipeline import ResearchExecutionNeedsReconciliation
from tests.conftest import write_approved_pricing_profile
from tests.controlled_provider_fixtures import seed_active_provider_role


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FixedClock:
    def now(self):
        return NOW


def _payload(
    settings,
    account,
    topic,
    *,
    cap: object = 1.0,
    max_tokens: object = 3000,
    pricing_profile=None,
) -> dict:
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
        cap_usd=cap, max_web_searches=3,
        question=topic.question or f"Why does '{topic.title}' work the way it does?",
        niche=account.niche,
        max_tokens=max_tokens,
        **pricing_kwargs,
    )
    return {
        "account_id": account.id,
        "topic_id": int(topic.id),
        "dry_run": False,
        "execution": "durable_provider_v2",
        "mode": "single",
        "max_cost_usd": intent.cap_usd,
        "execution_intent": intent.as_payload(),
    }


def _active_execution(storage, settings, account, *, max_tokens: object = 3000):
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Intent integrity", question="Why?",
        score=90.0, status=TopicStatus.SELECTED,
    ))
    payload = _payload(settings, account, topic, max_tokens=max_tokens)
    job = storage.enqueue_job(Job(
        id="intent-integrity-job", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key="intent-integrity-key",
        topic_id=int(topic.id), payload=payload, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
    ))
    lease = storage.claim_next_job("intent-integrity-worker", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = storage.initialize_research_run_for_job(
        job.id, lease.lease_owner, "intent-integrity-run", now=NOW,
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner=lease.lease_owner, run_id=initialized.run.id,
        clock=FixedClock(),
    )
    return topic, job, execution, payload


def _replace_payload(storage, job_id: str, payload: dict) -> None:
    storage.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False, separators=(",", ":")), job_id),
    )
    storage.conn.commit()


def _mutated_payload(kind: str, settings, account, topic, payload: dict) -> dict:
    changed = deepcopy(payload)
    intent = changed["execution_intent"]
    assert isinstance(intent, dict)
    if kind == "model":
        intent["model"] = "changed-model"
    elif kind == "provider":
        intent["provider"] = "changed-provider"
    elif kind == "prompt_question":
        intent["prompt_input"]["question"] = "Changed durable question?"
    elif kind == "prompt_niche":
        intent["prompt_input"]["niche"] = ["changed niche"]
    elif kind == "prompt_required_depth":
        intent["prompt_input"]["required_depth"] = "changed depth"
    elif kind == "prompt_guidance":
        intent["prompt_input"]["guidance"] = "changed guidance"
    elif kind == "stage":
        intent["stage"] = "other_stage"
    elif kind == "max_tokens":
        intent["max_tokens"] = 3001
    elif kind == "max_web_searches":
        intent["max_web_searches"] = 4
    elif kind == "timeout":
        intent["timeout_seconds"] = 61
    elif kind == "cap":
        changed["max_cost_usd"] = "1.100000"
        intent["cap_usd"] = "1.100000"
    elif kind == "pricing":
        repriced = replace(settings, pricing={
            **settings.pricing, "input_per_mtok": settings.pricing["input_per_mtok"] + 1,
        })
        changed["execution_intent"] = DurableResearchExecutionIntent.from_settings(
            settings=repriced, account_id=account.id, topic_id=int(topic.id),
            cap_usd=changed["max_cost_usd"], max_web_searches=3,
            question=topic.question or f"Why does '{topic.title}' work the way it does?",
            niche=account.niche,
        ).as_payload()
    elif kind == "pricing_fingerprint":
        intent["pricing_fingerprint"] = "0" * 64
    elif kind == "workflow":
        intent["workflow"] = "TOPICS"
    elif kind == "mode":
        intent["mode"] = "other"
    elif kind == "prompt_contract":
        intent["prompt_contract_version"] = "changed-contract"
    elif kind == "pipeline_version":
        intent["pipeline_version"] = "changed-pipeline"
    elif kind == "schema":
        intent["schema"] = "durable_research_intent_v999"
    elif kind == "retry":
        intent["max_retries"] = 1
    elif kind == "flags":
        intent["flags"] = {"force_re_research": True}
    elif kind == "missing_required_default":
        del intent["max_retries"]
    elif kind == "account_identity":
        changed["account_id"] = "other-account"
    elif kind == "topic_identity":
        changed["topic_id"] = int(topic.id) + 1
    else:  # pragma: no cover - exhaustive parametrization below
        raise AssertionError(kind)
    return changed


@pytest.mark.parametrize(
    ("kind", "expected_code"),
    [
        ("model", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("provider", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("prompt_question", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("prompt_niche", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("prompt_required_depth", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("prompt_guidance", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("stage", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("max_tokens", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("max_web_searches", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("timeout", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("cap", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("pricing", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("pricing_fingerprint", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("workflow", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("mode", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("prompt_contract", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("pipeline_version", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("schema", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("retry", "INVALID_EXECUTION_INTENT_FINGERPRINT"),
        ("flags", "FORCE_RE_RESEARCH_REQUIRES_EVIDENCE"),
        ("missing_required_default", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("account_identity", "MALFORMED_DURABLE_V2_PAYLOAD"),
        ("topic_identity", "MALFORMED_DURABLE_V2_PAYLOAD"),
    ],
)
def test_late_execution_intent_change_blocks_fake_caller_and_retains_attempt_for_reconciliation(
    storage, settings, account, kind, expected_code,
):
    topic, job, execution, payload = _active_execution(storage, settings, account)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    assert attempt.execution_intent_fingerprint == durable_execution_intent_fingerprint(payload)
    context = DurableProviderAttemptContext(
        job_id=job.id, run_id=execution.run_id, stage=attempt.stage,
        attempt_no=attempt.attempt_no, request_id=attempt.request_id,
        lease_owner=execution.lease_owner,
        fence_token=f"{job.id}:{execution.run_id}:{execution.lease_owner}", checked_at=NOW,
    )
    caller_count = 0

    def activation(_context):
        started = storage.mark_provider_attempt_request_started(execution, attempt.request_id)
        _replace_payload(storage, job.id, _mutated_payload(kind, settings, account, topic, payload))
        return started

    def caller(_plan):
        nonlocal caller_count
        caller_count += 1
        return ('{"question":"Why?","working_thesis":"No caller expected"}', Usage())

    client = AnthropicResearchClient("test-only", "model", caller=caller)
    client.configure_durable_attempt_control(
        context_callback=lambda _budget: context,
        activation_callback=activation,
        assertion_callback=lambda ctx: storage.assert_durable_provider_attempt_active(
            ctx, clock=execution.clock,
        ),
        estimated_attempt_cost=0.1,
    )

    with pytest.raises(JobRunRelationError) as raised:
        client.run_research(ResearchPlan(topic_id=int(topic.id), account_id=account.id, question="Why?"))
    assert raised.value.code == expected_code
    assert caller_count == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (execution.run_id,),
    ).fetchone()[0] == 0
    assert storage.get_run(execution.run_id).cost_usd == 0.0
    row = storage.conn.execute(
        "SELECT status,error_code,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert tuple(row) == (ProviderAttemptStatus.NEEDS_RECONCILIATION.value, expected_code, None)


def test_execution_intent_fingerprint_ignores_json_order_numeric_forms_and_whitespace(
    settings, account,
):
    topic = Topic(id=1, account_id=account.id, title="T", status=TopicStatus.SELECTED)
    payload = _payload(settings, account, topic, cap=1.0)
    equivalent = {
        key: deepcopy(payload[key])
        for key in reversed(list(payload))
    }
    intent = equivalent["execution_intent"]
    assert isinstance(intent, dict)
    intent["model"] = f"  {intent['model']}  "
    intent["max_tokens"] = float(intent["max_tokens"])
    intent["cap_usd"] = 1
    equivalent["max_cost_usd"] = 1
    pricing = intent["pricing_profile"]
    assert isinstance(pricing, dict)
    intent["pricing_profile"] = {
        key: int(float(value)) if float(value).is_integer() else value
        for key, value in reversed(list(pricing.items()))
    }

    assert durable_execution_intent_fingerprint(payload) == durable_execution_intent_fingerprint(equivalent)


@pytest.mark.parametrize("max_tokens", [2999, 3000, 3001])
def test_supported_max_tokens_survives_durable_enqueue_and_restart(
        storage, settings, account, max_tokens):
    """The persisted execution limit is reusable evidence after process restart."""
    topic, job, _execution, payload = _active_execution(
        storage, settings, account, max_tokens=max_tokens,
    )
    before = DurableResearchExecutionIntent.from_payload(payload["execution_intent"])
    assert before.max_tokens == max_tokens
    assert before.as_research_plan().topic_id == int(topic.id)

    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_job(job.id)
        assert persisted is not None
        after = DurableResearchExecutionIntent.from_payload(persisted.payload["execution_intent"])
        assert after.max_tokens == max_tokens
        assert durable_execution_intent_fingerprint(persisted.payload) == \
            durable_execution_intent_fingerprint(payload)
    finally:
        reopened.close()


def _assert_final_lifecycle_mutation_blocks_caller(
    storage, settings, account, mutation, expected_code: str,
) -> None:
    topic, job, execution, _payload_before = _active_execution(storage, settings, account)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    context = DurableProviderAttemptContext(
        job_id=job.id, run_id=execution.run_id, stage=attempt.stage,
        attempt_no=attempt.attempt_no, request_id=attempt.request_id,
        lease_owner=execution.lease_owner,
        fence_token=f"{job.id}:{execution.run_id}:{execution.lease_owner}", checked_at=NOW,
    )
    caller_count = 0

    def activation(_context):
        started = storage.mark_provider_attempt_request_started(execution, attempt.request_id)
        mutation(storage, execution, job, topic, account)
        storage.conn.commit()
        return started

    def caller(_plan):
        nonlocal caller_count
        caller_count += 1
        return ('{"question":"Why?","working_thesis":"No caller expected"}', Usage())

    client = AnthropicResearchClient("test-only", "model", caller=caller)
    client.configure_durable_attempt_control(
        context_callback=lambda _budget: context,
        activation_callback=activation,
        assertion_callback=lambda ctx: storage.assert_durable_provider_attempt_active(
            ctx, clock=execution.clock,
        ),
        estimated_attempt_cost=0.1,
    )
    with pytest.raises((JobRunRelationError, sqlite3.IntegrityError)) as raised:
        client.run_research(ResearchPlan(topic_id=int(topic.id), account_id=account.id, question="Why?"))
    sqlite_guarded = expected_code == "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"
    if sqlite_guarded:
        assert isinstance(raised.value, sqlite3.IntegrityError)
        assert "provider_attempt normalization" in str(raised.value)
        storage.conn.rollback()
    else:
        assert isinstance(raised.value, JobRunRelationError)
        assert raised.value.code == expected_code
    assert caller_count == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (execution.run_id,),
    ).fetchone()[0] == 0
    attempt_row = storage.conn.execute(
        "SELECT status,error_code,settled_at,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    if sqlite_guarded:
        assert tuple(attempt_row) == (
            ProviderAttemptStatus.REQUEST_STARTED.value, None, None, None,
        )
    else:
        assert tuple(attempt_row) == (
            ProviderAttemptStatus.NEEDS_RECONCILIATION.value, expected_code, None, None,
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1


def _set_run_status(status: str):
    return lambda storage, execution, _job, _topic, _account: storage.conn.execute(
        "UPDATE runs SET status=? WHERE id=?", (status, execution.run_id),
    )


def _set_run_finished(storage, execution, _job, _topic, _account):
    storage.conn.execute(
        "UPDATE runs SET finished_at='2026-07-15 12:00:01' WHERE id=?", (execution.run_id,),
    )


def _set_run_error(storage, execution, _job, _topic, _account):
    storage.conn.execute("UPDATE runs SET error='contradiction' WHERE id=?", (execution.run_id,))


def _invalidate_attempt_reservation(storage, execution, _job, _topic, _account):
    # Controlled corruption of a temporary test database.  The production
    # trigger makes reservation fields immutable; the final provider boundary
    # must nevertheless reject a damaged persisted row on its own evidence.
    storage.conn.execute("DROP TRIGGER provider_attempts_controlled_transition")
    storage.conn.execute(
        "UPDATE provider_attempts SET reserved_at='' WHERE job_id=? AND stage='research' AND attempt_no=1",
        (execution.job_id,),
    )


def _delete_run(storage, execution, _job, _topic, _account):
    # Controlled corruption of a temporary test database: normal foreign-key
    # constraints make this relation impossible, but the final gate must still
    # fail closed if a damaged persisted database reaches the worker.
    storage.conn.execute("PRAGMA foreign_keys=OFF")
    storage.conn.execute("DELETE FROM runs WHERE id=?", (execution.run_id,))
    storage.conn.commit()
    storage.conn.execute("PRAGMA foreign_keys=ON")


def _change_run_account(storage, execution, _job, _topic, account):
    other = account.model_copy(update={"id": "other-final-lifecycle-account"})
    storage.ensure_account(other)
    storage.conn.execute("UPDATE runs SET account_id=? WHERE id=?", (other.id, execution.run_id))


def _change_run_workflow(storage, execution, _job, _topic, _account):
    storage.conn.execute("UPDATE runs SET workflow='TOPIC' WHERE id=?", (execution.run_id,))


def _delete_research_run(storage, execution, _job, _topic, _account):
    storage.conn.execute("DELETE FROM research_runs WHERE id=?", (execution.run_id,))


def _set_research_status(status: str):
    return lambda storage, execution, _job, _topic, _account: storage.conn.execute(
        "UPDATE research_runs SET status=? WHERE id=?", (status, execution.run_id),
    )


def _change_research_flow(storage, execution, _job, _topic, _account):
    storage.conn.execute("UPDATE research_runs SET flow='staged' WHERE id=?", (execution.run_id,))


def _change_research_topic(storage, execution, _job, _topic, account):
    other_topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Other final lifecycle topic", question="Why other?",
        score=90.0, status=TopicStatus.SELECTED,
    ))
    storage.conn.execute(
        "UPDATE research_runs SET topic_id=? WHERE id=?", (other_topic.id, execution.run_id),
    )


def _set_research_timestamp(storage, execution, _job, _topic, _account):
    storage.conn.execute(
        "UPDATE research_runs SET stage_a_completed_at='2026-07-15 12:00:01' WHERE id=?",
        (execution.run_id,),
    )


def _attach_foreign_run(storage, execution, job, topic, account):
    foreign_id = "foreign-final-lifecycle-run"
    storage.conn.execute(
        "INSERT INTO runs (id,account_id,workflow,status,current_state,started_at) VALUES (?,?,?,?,?,?)",
        (foreign_id, account.id, "RESEARCH", "RUNNING", "research", "2026-07-15 12:00:00"),
    )
    storage.conn.execute(
        "INSERT INTO research_runs (id,account_id,topic_id,flow,status,total_cost_usd,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (foreign_id, account.id, topic.id, "single", "PENDING", 0.0,
         "2026-07-15 12:00:00", "2026-07-15 12:00:00"),
    )
    storage.conn.execute("UPDATE jobs SET run_id=? WHERE id=?", (foreign_id, job.id))


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (_invalidate_attempt_reservation, "FINAL_LIFECYCLE_ATTEMPT_STATE_INVALID"),
        (_set_run_status("SUCCESS"), "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"),
        (_set_run_status("FAILED"), "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"),
        (_set_run_status("STOPPED"), "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"),
        (_set_run_finished, "FINAL_LIFECYCLE_RUN_INVALID"),
        (_set_run_error, "FINAL_LIFECYCLE_RUN_INVALID"),
        (_delete_run, "FINAL_LIFECYCLE_RUN_MISSING"),
        (_change_run_account, "FINAL_LIFECYCLE_RUN_INVALID"),
        (_change_run_workflow, "FINAL_LIFECYCLE_RUN_INVALID"),
        (_delete_research_run, "FINAL_LIFECYCLE_RESEARCH_RUN_MISSING"),
        (_set_research_status("COMPLETE"), "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"),
        (_set_research_status("FAILED"), "SQLITE_PROVIDER_ATTEMPT_NORMALIZATION_REQUIRED"),
        (_set_research_status("SOURCES_COMPLETE"), "FINAL_LIFECYCLE_RESEARCH_RUN_INVALID"),
        (_change_research_flow, "FINAL_LIFECYCLE_RESEARCH_RUN_INVALID"),
        (_change_research_topic, "FINAL_LIFECYCLE_RESEARCH_RUN_INVALID"),
        (_set_research_timestamp, "FINAL_LIFECYCLE_RESEARCH_RUN_INVALID"),
        (_attach_foreign_run, "STALE_JOB_EXECUTION"),
    ],
)
def test_final_lifecycle_assertion_refuses_every_changed_run_or_research_relation(
    storage, settings, account, mutation, expected_code,
):
    _assert_final_lifecycle_mutation_blocks_caller(
        storage, settings, account, mutation, expected_code,
    )


def test_late_fingerprint_mismatch_remains_blocked_after_sqlite_reopen(storage, settings, account):
    topic, job, execution, payload = _active_execution(storage, settings, account)
    attempt = storage.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.1,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        context = DurableProviderAttemptContext(
            job_id=job.id, run_id=execution.run_id, stage=attempt.stage,
            attempt_no=attempt.attempt_no, request_id=attempt.request_id,
            lease_owner=execution.lease_owner,
            fence_token=f"{job.id}:{execution.run_id}:{execution.lease_owner}", checked_at=NOW,
        )
        caller_count = 0

        def activation(_context):
            started = reopened.mark_provider_attempt_request_started(execution, attempt.request_id)
            _replace_payload(
                reopened, job.id,
                _mutated_payload("prompt_question", settings, account, topic, payload),
            )
            return started

        def caller(_plan):
            nonlocal caller_count
            caller_count += 1
            return ('{"question":"Why?","working_thesis":"No caller expected"}', Usage())

        client = AnthropicResearchClient("test-only", "model", caller=caller)
        client.configure_durable_attempt_control(
            context_callback=lambda _budget: context,
            activation_callback=activation,
            assertion_callback=lambda ctx: reopened.assert_durable_provider_attempt_active(
                ctx, clock=execution.clock,
            ),
            estimated_attempt_cost=0.1,
        )
        with pytest.raises(JobRunRelationError) as raised:
            client.run_research(ResearchPlan(topic_id=int(topic.id), account_id=account.id, question="Why?"))
        assert raised.value.code == "INVALID_EXECUTION_INTENT_FINGERPRINT"
        assert caller_count == 0
        assert reopened.conn.execute(
            "SELECT count(*) FROM model_usage WHERE run_id=?", (execution.run_id,),
        ).fetchone()[0] == 0
        assert tuple(reopened.conn.execute(
            "SELECT status,error_code,settled_at FROM provider_attempts WHERE request_id=?",
            (attempt.request_id,),
        ).fetchone()) == ("NEEDS_RECONCILIATION", "INVALID_EXECUTION_INTENT_FINGERPRINT", None)
    finally:
        reopened.close()


@pytest.mark.parametrize("source", ["topic_question", "topic_fallback_title", "account_niche"])
def test_mutable_prompt_source_change_after_attempt_is_refused_before_fake_caller(
    monkeypatch, storage, settings, account, source,
):
    from app.scheduler import dispatcher

    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Snapshot source",
        question=None if source == "topic_fallback_title" else "Original question?",
        score=90.0, status=TopicStatus.SELECTED,
    ))
    real_settings = replace(
        settings, dry_run=False, anthropic_api_key="test-only-key",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    profile_id, pricing_path = write_approved_pricing_profile(
        settings.project_root,
        model=real_settings.model_quality,
        prices=dict(real_settings.pricing),
    )
    pricing_profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real_settings.model_quality,
    )
    payload = _payload(
        real_settings,
        account,
        topic,
        pricing_profile=pricing_profile,
    )
    job = storage.enqueue_job(Job(
        id=f"prompt-source-{source}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"prompt-source-{source}",
        topic_id=int(topic.id), payload=payload, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
    ))
    seed_active_provider_role(
        storage,
        role=LogicalModelRole.ARTICLE_RESEARCH,
        technical_model_id=real_settings.model_quality,
    )
    lease = storage.claim_next_job(f"prompt-source-{source}", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="prompt-source", now=NOW)

    original_begin = storage.begin_provider_attempt

    def mutate_after_reservation(*args, **kwargs):
        reserved = original_begin(*args, **kwargs)
        if source == "topic_question":
            topic.question = "Changed after enqueue?"
        elif source == "topic_fallback_title":
            topic.title = "Changed fallback title"
        else:
            account.niche = ["changed", "after enqueue"]
        return reserved

    caller_count = 0

    def fake_caller(_plan):
        nonlocal caller_count
        caller_count += 1
        return ('{"question":"Original question?","working_thesis":"No caller expected"}', Usage())

    monkeypatch.setattr(storage, "begin_provider_attempt", mutate_after_reservation)
    monkeypatch.setattr(
        dispatcher, "AnthropicResearchClient",
        lambda *args, **kwargs: AnthropicResearchClient(*args, caller=fake_caller, **kwargs),
    )
    clock = FixedClock()
    with pytest.raises(ResearchExecutionNeedsReconciliation):
        dispatcher._run_durable_real_research(
            account, topic, settings=real_settings, storage=storage,
            policy=PolicyEngine(real_settings, storage, clock), clock=clock,
            job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease.lease_owner),
        )
    assert caller_count == 0
    run_id = storage.get_job(job.id).run_id
    assert run_id is not None
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (run_id,),
    ).fetchone()[0] == 0
    assert tuple(storage.conn.execute(
        "SELECT status,error_code,settled_at,actual_cost_usd FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchone()) == ("NEEDS_RECONCILIATION", "PROMPT_SOURCE_SNAPSHOT_MISMATCH", None, None)
    assert storage.conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (job.id,),
    ).fetchone()[0] == 1


def test_dispatcher_rejects_changed_approved_pricing_before_client(
    monkeypatch, storage, settings, account,
):
    from app.scheduler import dispatcher

    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Pricing changed after enqueue",
        question="Why?",
        score=90.0,
        status=TopicStatus.SELECTED,
    ))
    real = replace(
        settings,
        dry_run=False,
        anthropic_api_key="offline-only",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    profile_id, pricing_path = write_approved_pricing_profile(
        real.project_root,
        model=real.model_quality,
        prices=dict(real.pricing),
    )
    profile = resolve_real_pricing_profile(
        load_pricing_profiles(pricing_path),
        profile_id=profile_id,
        model=real.model_quality,
    )
    job = storage.enqueue_job(Job(
        id="dispatcher-pricing-drift",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key="dispatcher-pricing-drift",
        topic_id=int(topic.id),
        payload=_payload(real, account, topic, pricing_profile=profile),
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
        max_attempts=1,
    ))
    lease = storage.claim_next_job("dispatcher-pricing-drift", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    write_approved_pricing_profile(
        real.project_root,
        model=real.model_quality,
        profile_id=profile_id,
        version="changed-after-enqueue",
        prices={key: 2.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    monkeypatch.setattr(
        dispatcher,
        "AnthropicResearchClient",
        lambda *_args, **_kwargs: pytest.fail(
            "provider client must not be constructed"
        ),
    )
    with pytest.raises(dispatcher.PayloadValidationError, match="not currently approved"):
        dispatcher._run_durable_real_research(
            account,
            topic,
            settings=real,
            storage=storage,
            policy=PolicyEngine(real, storage, FixedClock()),
            clock=FixedClock(),
            job_execution=ResearchJobExecution(
                job_id=job.id,
                lease_owner=lease.lease_owner,
            ),
        )


def test_direct_storage_enqueue_with_unapproved_contract_cannot_reach_provider(
    monkeypatch, storage, settings, account,
):
    from app.scheduler import dispatcher

    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Direct internal enqueue",
        question="Why?",
        score=90.0,
        status=TopicStatus.SELECTED,
    ))
    real = replace(
        settings,
        dry_run=False,
        anthropic_api_key="offline-only",
        pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
    )
    write_approved_pricing_profile(
        real.project_root,
        model=real.model_quality,
        profile_id="different-approved-profile",
        prices=dict(real.pricing),
    )
    job = storage.enqueue_job(Job(
        id="direct-unapproved-intent",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key="direct-unapproved-intent",
        topic_id=int(topic.id),
        payload=_payload(real, account, topic),
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
        max_attempts=1,
    ))
    lease = storage.claim_next_job("direct-unapproved-intent", 120, now=NOW)
    assert lease is not None
    storage.mark_job_running(job.id, lease.lease_owner, now=NOW)
    monkeypatch.setattr(
        dispatcher,
        "AnthropicResearchClient",
        lambda *_args, **_kwargs: pytest.fail(
            "provider client must not be constructed"
        ),
    )
    with pytest.raises(dispatcher.PayloadValidationError, match="not currently approved"):
        dispatcher._run_durable_real_research(
            account,
            topic,
            settings=real,
            storage=storage,
            policy=PolicyEngine(real, storage, FixedClock()),
            clock=FixedClock(),
            job_execution=ResearchJobExecution(
                job_id=job.id,
                lease_owner=lease.lease_owner,
            ),
        )


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        ({"execution": "durable_provider_v1"}, "UNSUPPORTED_EXECUTION_CONTRACT"),
        ({"execution": "durable_provider_v2"}, "MISSING_EXECUTION_INTENT"),
    ],
)
def test_durable_payload_rejections_expose_specific_error_codes(storage, account, payload, expected_code):
    job = Job(
        id=f"payload-error-{expected_code}", account_id=account.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"payload-error-{expected_code}",
        topic_id=1, payload=payload, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW,
    )
    with pytest.raises(JobPayloadValidationError) as raised:
        storage.enqueue_job(job)
    assert raised.value.code == expected_code


@pytest.mark.parametrize("resume_id", ["a2-resume", "b-resume"])
def test_real_resume_is_refused_before_any_sqlite_statement_or_runtime_construction(
    monkeypatch, storage, resume_id, capsys,
):
    module = importlib.import_module("scripts.run_capped_research")
    statements: list[str] = []
    storage.conn.set_trace_callback(statements.append)
    monkeypatch.setattr(module, "load_settings", lambda: pytest.fail("settings must not load"))
    monkeypatch.setattr(module.SqliteStorage, "open", lambda *_args, **_kwargs: pytest.fail("SQLite must not open"))

    assert module.main(["--resume", resume_id, "--real"]) == 2
    assert "real resume requires a durable job" in capsys.readouterr().out
    assert statements == []


def test_real_resume_subprocess_is_refused_before_loading_project_configuration():
    result = subprocess.run(
        [sys.executable, "scripts/run_capped_research.py", "--resume", "a2", "--real"],
        cwd=_PROJECT_ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "real resume requires a durable job" in result.stdout
