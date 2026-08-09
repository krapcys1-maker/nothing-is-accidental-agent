"""WAVE C4 acceptance and adversarial tests; all execution stays offline."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import Barrier

import pytest

from app.content.decision import ContentDecisionOutcome
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline
from app.content.writer import FakeContentWriter
from app.core.clock import FixedClock
from app.models import (
    AccountMode,
    AutonomyLevel,
    JobExecutionContext,
    JobKind,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import (
    ContentDecisionConflictError,
    StaleJobExecutionError,
)
from app.storage.db import (
    CONTENT_DECISION_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0023_to_0024,
    migrate_0024_to_0025,
    migrate_0025_to_0026,
    migrate_0026_to_0027,
)
from app.storage.repositories import SqliteStorage
from tests.c2_fixtures import seed_c2_research
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    ground_every_segment_in_package,
)


NOW = datetime(2026, 7, 24, 9, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


class C4Checkpoint(RuntimeError):
    pass


def _account(
    account,
    *,
    autonomy: AutonomyLevel,
    content_type: ContentType,
    require_approval: bool,
    mode: AccountMode = AccountMode.FULL_PUBLICATION,
):
    policy_field = (
        "require_article_approval"
        if content_type is ContentType.ARTICLE
        else "require_note_approval"
    )
    return account.model_copy(update={
        "autonomy_level": autonomy,
        "mode": mode,
        "policies": account.policies.model_copy(
            update={policy_field: require_approval}
        ),
    })


def _prepare(
    storage: SqliteStorage,
    settings,
    account,
    *,
    content_type: ContentType,
    suffix: str,
    stop_before_write: bool,
):
    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id=f"c4-job-{suffix}",
        idempotency_key=f"c4-intent-{suffix}",
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=content_type,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version=(
            "ARTICLE_STYLE_PROFILE_V1"
            if content_type is ContentType.ARTICLE
            else "NOTES_STYLE_PROFILE_V1_PROVISIONAL"
        ),
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"c4-owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, 60, clock=FixedClock(NOW),
    )
    assert lease is not None
    policy = PolicyEngine(settings, storage, FixedClock(NOW))

    def checkpoint(point: str) -> None:
        if stop_before_write and point == "C4_POLICY_VALIDATED":
            raise C4Checkpoint(point)

    if stop_before_write:
        with pytest.raises(C4Checkpoint, match="C4_POLICY_VALIDATED"):
            run_offline_content_pipeline(
                lease.job,
                storage=storage,
                clock=FixedClock(NOW),
                lease_owner=owner,
                project_root=ROOT,
                policy=policy,
                writer=FakeContentWriter(),
                claim_reviewer=FakeClaimAccountingReviewer(
                    decide=ground_every_segment_in_package
                ),
                fault_point=checkpoint,
            )
        summary = None
    else:
        summary = run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            policy=policy,
            writer=FakeContentWriter(),
            claim_reviewer=FakeClaimAccountingReviewer(
                decide=ground_every_segment_in_package
            ),
        )
    state = storage.get_content_pipeline_state(request.job_id)
    draft = state["drafts"][-1]
    execution = JobExecutionContext(
        job_id=request.job_id,
        lease_owner=owner,
        run_id=str(state["job"]["run_id"]),
        clock=FixedClock(NOW),
        fence_token=lease.job.execution_generation,
        kind=JobKind.CONTENT,
        workflow=WorkflowType(content_type.value),
    )
    return request, policy, state, draft, execution, summary


@pytest.mark.parametrize(
    ("autonomy", "content_type", "require_approval", "mode", "expected"),
    [
        (AutonomyLevel.LEVEL_0, ContentType.ARTICLE, False,
         AccountMode.FULL_PUBLICATION, ContentStatus.PENDING_APPROVAL),
        (AutonomyLevel.LEVEL_1, ContentType.NOTE, False,
         AccountMode.FULL_PUBLICATION, ContentStatus.PENDING_APPROVAL),
        (AutonomyLevel.LEVEL_2, ContentType.ARTICLE, False,
         AccountMode.FULL_PUBLICATION, ContentStatus.PENDING_APPROVAL),
        (AutonomyLevel.LEVEL_2, ContentType.NOTE, False,
         AccountMode.FULL_PUBLICATION, ContentStatus.APPROVED),
        (AutonomyLevel.LEVEL_3, ContentType.ARTICLE, False,
         AccountMode.FULL_PUBLICATION, ContentStatus.APPROVED),
        (AutonomyLevel.LEVEL_3, ContentType.NOTE, True,
         AccountMode.FULL_PUBLICATION, ContentStatus.PENDING_APPROVAL),
        (AutonomyLevel.LEVEL_3, ContentType.NOTE, False,
         AccountMode.DRAFT_ONLY, ContentStatus.PENDING_APPROVAL),
    ],
)
def test_autonomy_matrix_uses_durable_account_policy(
    storage, settings, account, autonomy, content_type, require_approval, mode, expected,
):
    durable_account = _account(
        account,
        autonomy=autonomy,
        content_type=content_type,
        require_approval=require_approval,
        mode=mode,
    )
    request, _, state, _, _, summary = _prepare(
        storage,
        settings,
        durable_account,
        content_type=content_type,
        suffix=f"{autonomy.value}-{content_type.value}-{mode.value}",
        stop_before_write=False,
    )
    assert summary.status is expected
    persisted = storage.get_content_pipeline_state(request.job_id)
    assert len(persisted["decisions"]) == 1
    decision = persisted["decisions"][0]
    assert decision["applied"] == 1
    assert decision["lifecycle_status"] == expected.value
    if expected is ContentStatus.PENDING_APPROVAL:
        assert decision["outcome"] == ContentDecisionOutcome.HUMAN_REQUIRED.value
        assert persisted["approval"]["decision"] == "PENDING"
    else:
        assert decision["outcome"] == ContentDecisionOutcome.APPROVED.value
        assert persisted["approval"] is None
    assert json.loads(decision["input_json"])["account"]["autonomy_level"] == autonomy.value


def test_level_1_never_auto_approves_even_above_threshold(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_1,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, _, _, _, _, summary = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="level1-never-auto",
        stop_before_write=False,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    decision = storage.get_content_pipeline_state(request.job_id)["decisions"][0]
    assert decision["score"] == 1.0
    assert decision["reason_code"] == "CONTENT_LEVEL_1_REQUIRES_HUMAN"


def test_level_3_below_threshold_is_durable_autonomous_rejection(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="below-threshold",
        stop_before_write=True,
    )
    storage.conn.execute("DROP TRIGGER content_draft_evaluations_no_update")
    storage.conn.execute(
        "UPDATE content_draft_evaluations SET score=0.8 WHERE draft_id=?",
        (draft["id"],),
    )
    storage.conn.commit()
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    decision = policy.decide_content(snapshot)
    assert decision.outcome is ContentDecisionOutcome.REJECTED
    assert decision.reason_code == "CONTENT_SCORE_BELOW_THRESHOLD"
    before = storage.conn.execute(
        "SELECT (SELECT count(*) FROM provider_attempts),"
        "(SELECT count(*) FROM model_usage),"
        "(SELECT count(*) FROM provider_attempts WHERE status='SETTLED'),"
        "(SELECT coalesce(sum(actual_cost_usd),0.0) FROM provider_attempts),"
        "(SELECT coalesce(sum(estimated_cost_usd),0.0) FROM model_usage)"
    ).fetchone()
    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
    )
    after = storage.conn.execute(
        "SELECT (SELECT count(*) FROM provider_attempts),"
        "(SELECT count(*) FROM model_usage),"
        "(SELECT count(*) FROM provider_attempts WHERE status='SETTLED'),"
        "(SELECT coalesce(sum(actual_cost_usd),0.0) FROM provider_attempts),"
        "(SELECT coalesce(sum(estimated_cost_usd),0.0) FROM model_usage)"
    ).fetchone()
    assert result.content.status is ContentStatus.REJECTED
    assert tuple(before) == tuple(after)


def test_hard_violation_overrides_high_score_and_is_durable(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="hard-violation",
        stop_before_write=True,
    )
    storage.conn.execute("DROP TRIGGER content_draft_evaluations_no_update")
    storage.conn.execute(
        "UPDATE content_draft_evaluations "
        "SET result='FAIL',decision='BLOCK',score=1.0,"
        "findings_json='[{\"code\":\"UNSUPPORTED_CLAIM\"}]' "
        "WHERE draft_id=? AND evaluation_type='UNSUPPORTED_CLAIMS'",
        (draft["id"],),
    )
    storage.conn.commit()
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    decision = policy.decide_content(snapshot)
    assert decision.score == 1.0
    assert decision.reason_code == "CONTENT_HARD_POLICY_VIOLATION"
    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
    )
    assert result.content.status is ContentStatus.REJECTED


def test_policy_fails_closed_for_incomplete_duplicate_unknown_and_contradictory_input(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, policy, _, draft, _, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="policy-counterproof",
        stop_before_write=True,
    )
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    variants = []
    variants.append({**snapshot, "evaluations": snapshot["evaluations"][:-1]})
    variants.append({
        **snapshot,
        "evaluations": snapshot["evaluations"] + [snapshot["evaluations"][0]],
    })
    unknown = [dict(row) for row in snapshot["evaluations"]]
    unknown[0]["evaluator_version"] = "unknown"
    variants.append({**snapshot, "evaluations": unknown})
    contradiction = [dict(row) for row in snapshot["evaluations"]]
    contradiction[0]["result"] = "FAIL"
    contradiction[0]["decision"] = "PASS"
    variants.append({**snapshot, "evaluations": contradiction})
    wrong_draft = [dict(row) for row in snapshot["evaluations"]]
    wrong_draft[0]["draft_fingerprint"] = "f" * 64
    variants.append({**snapshot, "evaluations": wrong_draft})
    replaced_draft = {
        **snapshot,
        "lineage": {**snapshot["lineage"], "draft_is_current": False},
    }
    variants.append(replaced_draft)
    unsupported_autonomy = {
        **snapshot,
        "account": {**snapshot["account"], "autonomy_level": "LEVEL_99"},
    }
    variants.append(unsupported_autonomy)
    terminal = {
        **snapshot,
        "content": {**snapshot["content"], "status": "PUBLISHED"},
    }
    variants.append(terminal)
    for variant in variants:
        decision = policy.decide_content(variant)
        assert decision.outcome is ContentDecisionOutcome.STALE_INPUT
        assert decision.lifecycle_status is ContentStatus.NEEDS_VERIFICATION


def test_autonomy_drift_between_validation_and_write_cannot_approve(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="autonomy-drift",
        stop_before_write=True,
    )
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    decision = policy.decide_content(snapshot)
    assert decision.outcome is ContentDecisionOutcome.APPROVED

    def drift(point: str) -> None:
        if point == "C4_DECISION_REVALIDATED":
            storage.conn.execute(
                "UPDATE accounts SET autonomy_level='LEVEL_1' WHERE id=?",
                (account.id,),
            )

    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
        fault_point=drift,
    )
    assert result.content.status is ContentStatus.NEEDS_VERIFICATION
    stored = storage.get_content_pipeline_state(request.job_id)["decisions"][0]
    assert stored["outcome"] == ContentDecisionOutcome.STALE_INPUT.value
    assert stored["reason_code"] == "CONTENT_DECISION_INPUT_DRIFT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("content_article_auto_approve_min_score", 1.0),
        ("content_decision_policy_version", "content_decision_policy_v2"),
    ],
)
def test_policy_configuration_drift_between_validation_and_write_is_stale(
    storage, settings, account, field, value,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix=f"config-drift-{field}",
        stop_before_write=True,
    )
    decision = policy.decide_content(storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    ))

    def drift(point: str) -> None:
        if point == "C4_DECISION_REVALIDATED":
            setattr(settings, field, value)

    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
        fault_point=drift,
    )
    assert result.content.status is ContentStatus.NEEDS_VERIFICATION
    assert storage.get_content_pipeline_state(request.job_id)["decisions"][0][
        "outcome"
    ] == ContentDecisionOutcome.STALE_INPUT.value


def test_evaluation_drift_between_validation_and_write_is_stale(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="evaluation-drift",
        stop_before_write=True,
    )
    decision = policy.decide_content(storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    ))
    storage.conn.execute("DROP TRIGGER content_draft_evaluations_no_update")
    storage.conn.commit()

    def drift(point: str) -> None:
        if point == "C4_DECISION_REVALIDATED":
            storage.conn.execute(
                "UPDATE content_draft_evaluations SET score=0.7 "
                "WHERE draft_id=? AND evaluation_type='STYLE_PROFILE'",
                (draft["id"],),
            )

    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
        fault_point=drift,
    )
    assert result.content.status is ContentStatus.NEEDS_VERIFICATION
    assert storage.get_content_pipeline_state(request.job_id)["decisions"][0][
        "reason_code"
    ] == "CONTENT_DECISION_INPUT_DRIFT"


def test_invalid_threshold_is_distinct_durable_technical_error(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="technical-error",
        stop_before_write=True,
    )
    settings.content_note_auto_approve_min_score = float("nan")
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    decision = policy.decide_content(snapshot)
    assert decision.outcome is ContentDecisionOutcome.TECHNICAL_ERROR
    result = storage.finalize_content_decision(
        execution,
        decision,
        revalidate=lambda current: policy.decide_content(
            current, expected_input_fingerprint=decision.input_fingerprint,
        ),
    )
    assert result.content.status is ContentStatus.FAILED
    assert storage.get_content_pipeline_state(request.job_id)["decisions"][0][
        "reason_code"
    ] == "CONTENT_DECISION_CONFIGURATION_ERROR"


def test_atomic_failure_rolls_back_decision_approval_and_lifecycle(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_1,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="atomic-rollback",
        stop_before_write=True,
    )
    snapshot = storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    )
    decision = policy.decide_content(snapshot)

    def fail_after_apply(point: str) -> None:
        if point == "C4_DECISION_APPLIED":
            raise C4Checkpoint(point)

    with pytest.raises(C4Checkpoint):
        storage.finalize_content_decision(
            execution,
            decision,
            revalidate=lambda current: policy.decide_content(
                current, expected_input_fingerprint=decision.input_fingerprint,
            ),
            fault_point=fail_after_apply,
        )
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["content"]["status"] == ContentStatus.RUNNING.value
    assert state["job"]["status"] in {"LEASED", "RUNNING"}
    assert state["decisions"] == []
    assert state["approval"] is None
    assert storage.conn.execute(
        "SELECT count(*) FROM approvals WHERE object_type='CONTENT_ITEM' "
        "AND object_id=?",
        (state["content"]["id"],),
    ).fetchone()[0] == 0


def test_restart_after_c4_validation_recovers_to_one_decision(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, _, _, _, _, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="restart",
        stop_before_write=True,
    )
    recovery_clock = FixedClock(NOW + timedelta(minutes=2))
    recovered = storage.release_or_requeue_expired_leases(clock=recovery_clock)
    assert recovered.requeued_count == 1
    takeover = storage.claim_specific_job(
        request.job_id, "c4-takeover", 60, clock=recovery_clock,
    )
    assert takeover is not None
    policy = PolicyEngine(settings, storage, recovery_clock)
    summary = run_offline_content_pipeline(
        takeover.job,
        storage=storage,
        clock=recovery_clock,
        lease_owner="c4-takeover",
        project_root=ROOT,
        policy=policy,
        writer=FakeContentWriter(),
        claim_reviewer=FakeClaimAccountingReviewer(
            decide=ground_every_segment_in_package
        ),
    )
    assert summary.status is ContentStatus.APPROVED
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["decisions"]) == 1
    assert len(state["drafts"]) == 1


def test_identical_replay_is_idempotent_and_conflicting_second_decision_is_blocked(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="replay",
        stop_before_write=True,
    )
    decision = policy.decide_content(storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    ))
    revalidate = lambda current: policy.decide_content(
        current, expected_input_fingerprint=decision.input_fingerprint,
    )
    first = storage.finalize_content_decision(
        execution, decision, revalidate=revalidate,
    )
    second = storage.finalize_content_decision(
        execution, decision, revalidate=revalidate,
    )
    assert first.idempotent is False
    assert second.idempotent is True
    assert storage.conn.execute(
        "SELECT count(*) FROM autonomous_decisions WHERE content_id=?",
        (decision.content_id,),
    ).fetchone()[0] == 1
    conflicting = replace(decision, decision_fingerprint="f" * 64)
    with pytest.raises(ContentDecisionConflictError):
        storage.finalize_content_decision(
            execution, conflicting, revalidate=revalidate,
        )


def test_concurrent_identical_decisions_create_one_terminal_audit(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="concurrent",
        stop_before_write=True,
    )
    decision = policy.decide_content(storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    ))
    db_path = settings.db_path
    barrier = Barrier(2)

    def apply_once() -> bool:
        local = SqliteStorage.open(db_path)
        try:
            local_policy = PolicyEngine(settings, local, FixedClock(NOW))
            barrier.wait()
            result = local.finalize_content_decision(
                execution,
                decision,
                revalidate=lambda current: local_policy.decide_content(
                    current,
                    expected_input_fingerprint=decision.input_fingerprint,
                ),
            )
            return result.idempotent
        finally:
            local.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: apply_once(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert storage.conn.execute(
        "SELECT count(*) FROM autonomous_decisions WHERE content_id=?",
        (decision.content_id,),
    ).fetchone()[0] == 1


def test_stale_fence_cannot_write_decision(storage, settings, account):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_3,
        content_type=ContentType.NOTE,
        require_approval=False,
    )
    request, policy, _, draft, execution, _ = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.NOTE,
        suffix="stale-fence",
        stop_before_write=True,
    )
    decision = policy.decide_content(storage.get_content_decision_snapshot(
        request.job_id, str(draft["draft_fingerprint"]),
    ))
    storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=2)),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.finalize_content_decision(
            execution,
            decision,
            revalidate=lambda current: policy.decide_content(
                current, expected_input_fingerprint=decision.input_fingerprint,
            ),
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM autonomous_decisions WHERE content_id=?",
        (decision.content_id,),
    ).fetchone()[0] == 0


def test_sqlite_guards_block_audit_mutation_and_uncommanded_approval(
    storage, settings, account,
):
    durable_account = _account(
        account,
        autonomy=AutonomyLevel.LEVEL_1,
        content_type=ContentType.ARTICLE,
        require_approval=False,
    )
    request, _, state, _, _, summary = _prepare(
        storage, settings, durable_account,
        content_type=ContentType.ARTICLE,
        suffix="sqlite-guards",
        stop_before_write=False,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    decision_id = state["decisions"][0]["id"]
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE autonomous_decisions SET outcome='APPROVED' WHERE id=?",
            (decision_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "DELETE FROM autonomous_decisions WHERE id=?", (decision_id,),
        )
    with pytest.raises(sqlite3.IntegrityError):
        storage.conn.execute(
            "UPDATE content_items SET status='APPROVED' WHERE job_id=?",
            (request.job_id,),
        )
    storage.conn.rollback()


def test_explicit_0023_to_0024_migration_is_fresh_upgrade_and_idempotent(tmp_path):
    fresh = tmp_path / "fresh-c4.db"
    applied = initialize_database(fresh)
    assert CONTENT_DECISION_SCHEMA_VERSION in applied
    assert EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION in applied
    assert applied[-1] == MODEL_FAMILY_ROUTING_SCHEMA_VERSION
    assert database_schema_versions(fresh)[-1] == (
        MODEL_FAMILY_ROUTING_SCHEMA_VERSION
    )

    upgrade = tmp_path / "upgrade-c4.db"
    initialize_database(upgrade, through=CONTENT_WRITER_SCHEMA_VERSION)
    result = migrate_0023_to_0024(upgrade)
    assert result.applied_migrations == (CONTENT_DECISION_SCHEMA_VERSION,)
    repeated = migrate_0023_to_0024(upgrade)
    assert repeated.idempotent is True
    lineage = migrate_0024_to_0025(upgrade)
    assert lineage.applied_migrations == (
        EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    )
    paid = migrate_0025_to_0026(upgrade)
    assert paid.applied_migrations == (
        CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    )
    routing = migrate_0026_to_0027(upgrade)
    assert routing.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)
    opened = SqliteStorage.open(upgrade)
    try:
        assert opened.conn.execute(
            "SELECT count(*) FROM autonomous_decisions"
        ).fetchone()[0] == 0
        assert opened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        opened.close()
