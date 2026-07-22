"""One-shot controlled-live executor for one existing TOPIC_GENERATION job.

This module is deliberately a narrow composition root.  It creates neither a
job nor an approval, never selects from the queue, never retries, and never
runs maintenance.  The only external-effect-capable object it constructs is a
topic-generation client for the exact job named by the operator.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping
from uuid import uuid4

from app.core.clock import Clock
from app.core.config import Settings
from app.core.money import quantize_usd
from app.models import JobKind, JobStatus, WorkflowType
from app.operations.controlled_live import (
    OPEN_PROFILE,
    DbFingerprint,
    acquire_session_marker,
    clear_session_marker,
    confirm_flags,
    default_db_fingerprint,
    is_fail_closed,
    open_minimal_profile,
    read_session_marker,
    restore_fail_closed,
    write_operator_report,
    write_session_marker,
)
from app.operations.stage1_migration import _git_identity
from app.ports.storage import StoragePort
from app.topics.durable_intent import frozen_topic_generation_contract


EXIT_SUCCESS = 0
EXIT_TERMINAL_FAILURE = 1
EXIT_PREFLIGHT_REFUSED = 2
EXIT_RECONCILIATION_REQUIRED = 3
EXIT_POLICY_RESTORE_FAILED = 4
EXIT_RECOVERY_BARRIER_FAILED = 5

_OPERATION = "controlled-live-topic-generation"
_UPDATED_BY = _OPERATION
_LEASE_SECONDS = 60
_ATTEMPT_STAGE = "topics"
_ATTEMPT_NO = 1


@dataclass(frozen=True)
class TopicGenerationLiveRequest:
    job_id: str
    account_id: str
    expected_intent_fingerprint: str
    expected_model: str
    expected_max_tokens: int
    expected_cap_usd: str
    expected_candidate_count: int
    expected_db_sha256: str
    expected_schema: str
    expected_branch: str
    expected_head: str
    confirmed: bool

    @property
    def request_id(self) -> str:
        return f"{self.job_id}:{_ATTEMPT_STAGE}:{_ATTEMPT_NO}"


@dataclass(frozen=True)
class TopicGenerationCheckpoint:
    status: str
    reason_code: str
    exit_code: int
    job_id: str
    account_id: str
    intent_fingerprint: str
    request_id: str
    attempt_status: str | None = None
    job_status: str | None = None
    run_status: str | None = None
    approval_status: str = "missing"
    usage_count: int = 0
    actual_cost_usd: str | None = None
    topics_count: int = 0
    generated_topics_count: int = 0
    selected_topic_id: int | None = None
    reconciliation_required: bool = False
    policy_flags_restored: bool = False
    attempt_count: int = 0
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "exit_code": self.exit_code,
            "job_id": self.job_id,
            "account_id": self.account_id,
            "intent_fingerprint": self.intent_fingerprint,
            "request_id": self.request_id,
            "attempt_status": self.attempt_status,
            "attempt_count": self.attempt_count,
            "job_status": self.job_status,
            "run_status": self.run_status,
            "approval_status": self.approval_status,
            "usage_count": self.usage_count,
            "actual_cost_usd": self.actual_cost_usd,
            "topics_count": self.topics_count,
            "generated_topics_count": self.generated_topics_count,
            "selected_topic_id": self.selected_topic_id,
            "reconciliation_required": self.reconciliation_required,
            "policy_flags_restored": self.policy_flags_restored,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TopicGenerationLiveOutcome:
    checkpoint: TopicGenerationCheckpoint
    flags_before: dict[str, bool] = field(default_factory=dict)
    flags_during: dict[str, bool] = field(default_factory=dict)
    flags_after: dict[str, bool] = field(default_factory=dict)
    report_path: Path | None = None

    @property
    def exit_code(self) -> int:
        return self.checkpoint.exit_code


class TopicGenerationLiveError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise TopicGenerationLiveError(
            "CLOCK_NOT_TIMEZONE_AWARE", "controlled-live clock must be timezone-aware",
        )
    return moment.astimezone(timezone.utc)


def _durable_utc(moment: datetime) -> datetime:
    """SQLite timestamps without an offset are the project's persisted UTC."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _persisted(moment: datetime) -> str:
    value = _utc(moment).replace(tzinfo=None)
    return (
        value.strftime("%Y-%m-%d %H:%M:%S.%f")
        if value.microsecond
        else value.strftime("%Y-%m-%d %H:%M:%S")
    )


def _parse_timestamp(value: object) -> datetime:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TopicGenerationLiveError(
            "TIMESTAMP_INVALID", "a durable timestamp is not parseable",
        ) from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _validate_request(request: TopicGenerationLiveRequest) -> None:
    for name in (
        "job_id", "account_id", "expected_intent_fingerprint", "expected_model",
        "expected_cap_usd", "expected_db_sha256", "expected_schema",
        "expected_branch", "expected_head",
    ):
        value = getattr(request, name)
        if not isinstance(value, str) or not value.strip():
            raise TopicGenerationLiveError(
                "CLI_CONTRACT_INVALID", f"{name} must be explicit and non-empty",
            )
    fingerprint = request.expected_intent_fingerprint
    if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
        raise TopicGenerationLiveError(
            "INTENT_FINGERPRINT_INVALID", "expected fingerprint must be lowercase SHA-256",
        )
    if request.expected_max_tokens <= 0 or request.expected_candidate_count <= 0:
        raise TopicGenerationLiveError(
            "CLI_CONTRACT_INVALID", "expected numeric limits must be positive",
        )
    try:
        cap = quantize_usd(request.expected_cap_usd, label="expected cap")
    except ValueError as exc:
        raise TopicGenerationLiveError("EXPECTED_CAP_INVALID", str(exc)) from exc
    if cap <= 0:
        raise TopicGenerationLiveError("EXPECTED_CAP_INVALID", "expected cap must be positive")
    if not request.confirmed:
        raise TopicGenerationLiveError(
            "CONFIRMATION_MISSING", "controlled-live confirmation is required",
        )


def _preflight_snapshot(
    storage: StoragePort,
    request: TopicGenerationLiveRequest,
    *,
    moment: datetime,
    frozen_quiescence: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, bool]]:
    """Read-only durable preflight.  Every refusal happens before gates open."""
    _validate_request(request)
    if any(frozen_quiescence.get(key) for key in (
        "project_process_ids", "scheduled_tasks", "locked_paths",
    )):
        raise TopicGenerationLiveError(
            "RUNTIME_NOT_QUIESCENT", "worker, scheduler, process, task or DB handle is active",
        )

    flags_before = confirm_flags(storage)
    # A fail-closed baseline makes the full snapshot both safe and exactly
    # recoverable through the established crash marker contract.
    if not is_fail_closed(flags_before):
        raise TopicGenerationLiveError(
            "NOT_FAIL_CLOSED_BASELINE", "all five durable flags must already be fail-closed",
        )

    job = storage.get_job(request.job_id)
    if job is None:
        raise TopicGenerationLiveError("JOB_MISSING", "the named job does not exist")
    if job.kind is not JobKind.TOPIC_GENERATION or job.workflow is not (
        WorkflowType.TOPIC_GENERATION
    ):
        raise TopicGenerationLiveError(
            "JOB_TYPE_INVALID", "the named job is not TOPIC_GENERATION",
        )
    if job.account_id != request.account_id:
        raise TopicGenerationLiveError("JOB_ACCOUNT_MISMATCH", "job account differs")

    conn = getattr(storage, "conn", None)
    if conn is None:
        raise TopicGenerationLiveError("STORAGE_INSPECTION_UNAVAILABLE", "storage has no SQL view")
    attempt_count = int(conn.execute(
        "SELECT count(*) FROM provider_attempts WHERE job_id=?", (request.job_id,),
    ).fetchone()[0])
    usage_count = int(conn.execute(
        "SELECT count(*) FROM model_usage u JOIN provider_attempts p "
        "ON p.request_id=u.request_id WHERE p.job_id=?", (request.job_id,),
    ).fetchone()[0])
    # Report the strongest irreversible fact first.  A normal attempt also
    # changes the job state, but the public contract promises an explicit
    # refusal when usage or an attempt already exists.
    if usage_count:
        raise TopicGenerationLiveError("USAGE_ALREADY_EXISTS", "job already has usage")
    if attempt_count:
        raise TopicGenerationLiveError("ATTEMPT_ALREADY_EXISTS", "job already has an attempt")
    if job.status is not JobStatus.QUEUED:
        raise TopicGenerationLiveError(
            "JOB_NOT_FIRST_EXECUTION", f"job status is {job.status.value}, not QUEUED",
        )
    if (
        job.attempts != 0 or job.max_attempts != 1 or job.run_id is not None
        or job.topic_id is not None or job.lease_owner is not None
        or job.lease_expires_at is not None or job.external_effect_started_at is not None
    ):
        raise TopicGenerationLiveError(
            "JOB_LIFECYCLE_INVALID", "job is not a pristine max_attempts=1 execution",
        )
    now = _utc(moment)
    if _durable_utc(job.earliest_run_at) > now:
        raise TopicGenerationLiveError("JOB_NOT_YET_CLAIMABLE", "earliest_run_at is in the future")
    if job.deadline_at is not None and _durable_utc(job.deadline_at) < now:
        raise TopicGenerationLiveError("JOB_DEADLINE_ELAPSED", "job deadline elapsed")

    try:
        intent, intent_json, fingerprint = frozen_topic_generation_contract(job.payload)
    except Exception as exc:
        raise TopicGenerationLiveError(
            "INTENT_INVALID", "durable topic-generation intent is invalid",
        ) from exc
    comparisons = (
        (fingerprint, request.expected_intent_fingerprint, "INTENT_FINGERPRINT_MISMATCH"),
        (intent.model, request.expected_model, "MODEL_MISMATCH"),
        (intent.max_tokens, request.expected_max_tokens, "MAX_TOKENS_MISMATCH"),
        (intent.candidate_count, request.expected_candidate_count, "CANDIDATE_COUNT_MISMATCH"),
    )
    for observed, expected, code in comparisons:
        if observed != expected:
            raise TopicGenerationLiveError(code, f"observed {observed!r} differs from expected")
    if quantize_usd(intent.cap_usd, label="intent cap") != quantize_usd(
        request.expected_cap_usd, label="expected cap",
    ):
        raise TopicGenerationLiveError("CAP_MISMATCH", "intent cap differs from expected cap")

    approval = storage.get_topic_generation_approval_for_job(request.job_id)
    if approval is None:
        raise TopicGenerationLiveError("APPROVAL_MISSING", "one-shot approval is missing")
    if approval.account_id != request.account_id:
        raise TopicGenerationLiveError("APPROVAL_ACCOUNT_MISMATCH", "approval account differs")
    if approval.consumed_at is not None:
        raise TopicGenerationLiveError("APPROVAL_ALREADY_CONSUMED", "approval was consumed")
    if _parse_timestamp(approval.expires_at) <= now:
        raise TopicGenerationLiveError("APPROVAL_EXPIRED", "approval expired")
    if approval.intent_fingerprint != fingerprint:
        raise TopicGenerationLiveError(
            "APPROVAL_FINGERPRINT_MISMATCH", "approval fingerprint differs",
        )
    if approval.execution_intent_json != intent_json:
        raise TopicGenerationLiveError(
            "APPROVAL_PREIMAGE_MISMATCH", "approval does not preserve the exact intent preimage",
        )
    if approval.model != request.expected_model:
        raise TopicGenerationLiveError("APPROVAL_MODEL_MISMATCH", "approval model differs")
    if approval.max_tokens != request.expected_max_tokens:
        raise TopicGenerationLiveError(
            "APPROVAL_MAX_TOKENS_MISMATCH", "approval max_tokens differs",
        )
    if quantize_usd(approval.cap_usd, label="approval cap") != quantize_usd(
        request.expected_cap_usd, label="expected cap",
    ):
        raise TopicGenerationLiveError("APPROVAL_CAP_MISMATCH", "approval cap differs")

    current_ts = _persisted(now)
    checks = (
        (
            "OTHER_CLAIMABLE_PAID_JOB",
            "SELECT count(*) FROM jobs WHERE id<>? AND status='QUEUED' "
            "AND earliest_run_at<=? AND (deadline_at IS NULL OR deadline_at>=?) "
            "AND attempts<max_attempts AND (kind='TOPIC_GENERATION' OR "
            "(kind='RESEARCH' AND json_extract(payload_json,'$.dry_run')=0 "
            "AND coalesce(json_extract(payload_json,'$.execution'),'')<>'controlled_fetch_v1'))",
            (request.job_id, current_ts, current_ts),
        ),
        (
            "OTHER_ACTIVE_TOPIC_GENERATION",
            "SELECT count(*) FROM jobs WHERE id<>? AND kind='TOPIC_GENERATION' "
            "AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION')",
            (request.job_id,),
        ),
        (
            "ACTIVE_PROVIDER_ATTEMPT",
            "SELECT count(*) FROM provider_attempts WHERE status IN ('RESERVED','REQUEST_STARTED')",
            (),
        ),
        (
            "NEEDS_VERIFICATION_PRESENT",
            "SELECT count(*) FROM jobs WHERE status='NEEDS_VERIFICATION'",
            (),
        ),
        (
            "NEEDS_RECONCILIATION_PRESENT",
            "SELECT count(*) FROM provider_attempts WHERE status='NEEDS_RECONCILIATION'",
            (),
        ),
        (
            "OTHER_UNUSED_PAID_APPROVAL",
            "SELECT (SELECT count(*) FROM topic_generation_approvals "
            "WHERE job_id<>? AND consumed_at IS NULL) + "
            "(SELECT count(*) FROM controlled_fetch_approvals "
            "WHERE action_type='EVIDENCE_RESEARCH' AND consumed_at IS NULL)",
            (request.job_id,),
        ),
        (
            "OTHER_ACTIVE_JOB",
            "SELECT count(*) FROM jobs WHERE id<>? AND status IN ('LEASED','RUNNING')",
            (request.job_id,),
        ),
    )
    for code, sql, parameters in checks:
        if int(conn.execute(sql, parameters).fetchone()[0]):
            raise TopicGenerationLiveError(code, "concurrent durable state blocks controlled-live")

    snapshot: dict[str, object] = {
        "job_id": request.job_id,
        "account_id": request.account_id,
        "job_status": job.status.value,
        "job_attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "intent_fingerprint": fingerprint,
        "intent_preimage_sha256": hashlib.sha256(intent_json.encode("utf-8")).hexdigest(),
        "model": intent.model,
        "max_tokens": intent.max_tokens,
        "cap_usd": intent.cap_usd,
        "candidate_count": intent.candidate_count,
        "approval_id": approval.id,
        "approval_expires_at": str(approval.expires_at),
        "request_id": request.request_id,
        "flags_before": flags_before,
        "quiescence": {
            key: list(frozen_quiescence.get(key, ()))
            for key in ("project_process_ids", "scheduled_tasks", "locked_paths")
        },
    }
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    snapshot["preflight_fingerprint"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return snapshot, flags_before


def _checkpoint_from_storage(
    storage: StoragePort,
    request: TopicGenerationLiveRequest,
    *,
    status: str,
    reason_code: str,
    exit_code: int,
    policy_flags_restored: bool,
    detail: str = "",
) -> TopicGenerationCheckpoint:
    conn = getattr(storage, "conn", None)
    if conn is None:
        return TopicGenerationCheckpoint(
            status=status, reason_code=reason_code, exit_code=exit_code,
            job_id=request.job_id, account_id=request.account_id,
            intent_fingerprint=request.expected_intent_fingerprint,
            request_id=request.request_id,
            policy_flags_restored=policy_flags_restored, detail=detail,
        )
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (request.job_id,)).fetchone()
    attempt_rows = conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=? ORDER BY attempt_no",
        (request.job_id,),
    ).fetchall()
    attempt = attempt_rows[0] if len(attempt_rows) == 1 else None
    usage_count = int(conn.execute(
        "SELECT count(*) FROM model_usage WHERE request_id=?", (request.request_id,),
    ).fetchone()[0])
    approval = conn.execute(
        "SELECT consumed_at FROM topic_generation_approvals WHERE job_id=?",
        (request.job_id,),
    ).fetchone()
    run_status = None
    run_id = None if job is None else job["run_id"]
    if run_id is not None:
        run = conn.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
        run_status = None if run is None else str(run["status"])
    generated = conn.execute(
        "SELECT topic_id,is_selected FROM generated_topics WHERE job_id=? "
        "ORDER BY candidate_index", (request.job_id,),
    ).fetchall()
    selected = [int(row["topic_id"]) for row in generated if bool(row["is_selected"])]
    topics_count = int(conn.execute(
        "SELECT count(*) FROM topics WHERE account_id=?", (request.account_id,),
    ).fetchone()[0])
    attempt_status = None if attempt is None else str(attempt["status"])
    job_status = None if job is None else str(job["status"])
    reconciliation = (
        attempt_status in {"RESERVED", "REQUEST_STARTED", "NEEDS_RECONCILIATION"}
        or job_status == "NEEDS_VERIFICATION"
    )
    actual = None if attempt is None else attempt["actual_cost_usd"]
    actual_cost = None if actual is None else format(
        quantize_usd(actual, label="actual cost"), "f",
    )
    return TopicGenerationCheckpoint(
        status=status,
        reason_code=reason_code,
        exit_code=exit_code,
        job_id=request.job_id,
        account_id=request.account_id,
        intent_fingerprint=request.expected_intent_fingerprint,
        request_id=request.request_id,
        attempt_status=attempt_status,
        attempt_count=len(attempt_rows),
        job_status=job_status,
        run_status=run_status,
        approval_status=(
            "missing" if approval is None
            else "consumed" if approval["consumed_at"] is not None
            else "unconsumed"
        ),
        usage_count=usage_count,
        actual_cost_usd=actual_cost,
        topics_count=topics_count,
        generated_topics_count=len(generated),
        selected_topic_id=selected[0] if len(selected) == 1 else None,
        reconciliation_required=reconciliation,
        policy_flags_restored=policy_flags_restored,
        detail=detail[:240],
    )


def _forbidden_workflow(*_args: object, **_kwargs: object):
    raise TopicGenerationLiveError(
        "NON_TOPIC_WORKFLOW_FORBIDDEN",
        "controlled-live-topic-generation cannot dispatch research or controlled fetch",
    )


def _default_worker(
    request: TopicGenerationLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    clock: Clock,
    topic_generation_client_factory=None,
):
    from app.policies.policy_engine import PolicyEngine
    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker
    from app.storage.repositories import SqliteStorage

    policy = PolicyEngine(settings, storage, clock)
    dispatcher = JobDispatcher(
        settings=settings,
        storage=storage,
        policy=policy,
        clock=clock,
        research_dry_run=_forbidden_workflow,
        research_real=_forbidden_workflow,
        research_offline_evidence=_forbidden_workflow,
        research_controlled_fetch=_forbidden_workflow,
        topic_generation_client_factory=topic_generation_client_factory,
        allow_real_research=False,
        allow_real_topic_generation=True,
    )
    return Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner=f"{_OPERATION}:{request.job_id}:{uuid4().hex}",
        target_job_id=request.job_id,
        lease_seconds=_LEASE_SECONDS,
        heartbeat_interval_seconds=20.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
    )


def _finish_report_and_marker(
    *,
    runtime_dir: Path,
    session_id: str,
    checkpoint: TopicGenerationCheckpoint,
    flags_before: Mapping[str, bool],
    flags_during: Mapping[str, bool],
    flags_after: Mapping[str, bool],
) -> tuple[Path | None, str | None]:
    report_key = f"topic-generation-{session_id}-{uuid4().hex[:12]}"
    payload = {
        "operation": _OPERATION,
        "session_id": session_id,
        "checkpoint": checkpoint.as_dict(),
        "flags_before": dict(flags_before),
        "flags_during": dict(flags_during),
        "flags_after": dict(flags_after),
        "provider_retry_performed": False,
        "maintenance_performed": False,
    }
    try:
        report = write_operator_report(
            runtime_dir / "controlled_live_reports", report_key, payload,
        )
    except BaseException:
        return None, "REPORT_WRITE_FAILED"
    try:
        clear_session_marker(runtime_dir)
    except BaseException:
        return report, "MARKER_CLEAR_FAILED"
    return report, None


def _write_report_keep_marker(
    *,
    runtime_dir: Path,
    session_id: str,
    checkpoint: TopicGenerationCheckpoint,
    flags_before: Mapping[str, bool],
    flags_during: Mapping[str, bool],
    flags_after: Mapping[str, bool],
) -> Path | None:
    """Persist evidence while retaining the crash fence for later recovery."""
    report_key = f"topic-generation-{session_id}-restore-failed-{uuid4().hex[:12]}"
    try:
        return write_operator_report(
            runtime_dir / "controlled_live_reports",
            report_key,
            {
                "operation": _OPERATION,
                "session_id": session_id,
                "checkpoint": checkpoint.as_dict(),
                "flags_before": dict(flags_before),
                "flags_during": dict(flags_during),
                "flags_after": dict(flags_after),
                "marker_retained_for_recovery": True,
                "provider_retry_performed": False,
                "maintenance_performed": False,
            },
        )
    except BaseException:
        return None


def _recover_topic_marker(
    *,
    marker: Mapping[str, object],
    request: TopicGenerationLiveRequest,
    storage: StoragePort,
    storage_reopener: Callable[[], StoragePort],
    runtime_dir: Path,
    moment: datetime,
) -> TopicGenerationLiveOutcome:
    if marker.get("operation") != _OPERATION:
        checkpoint = _checkpoint_from_storage(
            storage, request, status="PREFLIGHT_REFUSED",
            reason_code="FOREIGN_CONTROLLED_LIVE_SESSION",
            exit_code=EXIT_PREFLIGHT_REFUSED, policy_flags_restored=False,
            detail="another controlled-live workflow owns the durable marker",
        )
        return TopicGenerationLiveOutcome(checkpoint=checkpoint)
    baseline = marker.get("flags_before")
    if not isinstance(baseline, Mapping) or not is_fail_closed(baseline):
        checkpoint = _checkpoint_from_storage(
            storage, request, status="RESTORE_FAILED",
            reason_code="RECOVERY_MARKER_INVALID",
            exit_code=EXIT_POLICY_RESTORE_FAILED, policy_flags_restored=False,
            detail="topic-generation marker lacks a safe complete flag snapshot",
        )
        return TopicGenerationLiveOutcome(checkpoint=checkpoint)

    marker_job_id = marker.get("job_id")
    marker_account_id = marker.get("account_id")
    marker_request_id = marker.get("expected_request_id")
    marker_fingerprint = marker.get("intent_fingerprint")
    binding_matches = (
        marker_job_id == request.job_id
        and marker_account_id == request.account_id
        and marker_request_id == request.request_id
        and marker_fingerprint == request.expected_intent_fingerprint
    )

    flags_after: dict[str, bool] = {}
    error: BaseException | None = None
    reopened: StoragePort | None = None
    try:
        flags_after = restore_fail_closed(
            storage, reason=f"{_OPERATION} interrupted session recovery", now=moment,
        )
        if flags_after != dict(baseline):
            raise TopicGenerationLiveError(
                "RECOVERY_SNAPSHOT_MISMATCH", "restored flags differ from the saved snapshot",
            )
        storage.close()  # type: ignore[attr-defined]
        reopened = storage_reopener()
        flags_after = confirm_flags(reopened)
        if flags_after != dict(baseline):
            raise TopicGenerationLiveError(
                "RECOVERY_REOPEN_MISMATCH", "read-only reopen did not confirm the snapshot",
            )
    except BaseException as exc:
        error = exc
    target = reopened if reopened is not None else storage
    if error is not None:
        checkpoint = _checkpoint_from_storage(
            target, request, status="RESTORE_FAILED",
            reason_code="POLICY_RESTORE_FAILED",
            exit_code=EXIT_POLICY_RESTORE_FAILED, policy_flags_restored=False,
            detail=type(error).__name__,
        )
        return TopicGenerationLiveOutcome(
            checkpoint=checkpoint, flags_before=dict(baseline), flags_after=flags_after,
        )
    if not binding_matches:
        checkpoint = TopicGenerationCheckpoint(
            status="RECOVERY_BARRIER_FAILED",
            reason_code="RECOVERY_BINDING_MISMATCH",
            exit_code=EXIT_RECOVERY_BARRIER_FAILED,
            job_id=str(marker_job_id or "unknown"),
            account_id=str(marker_account_id or "unknown"),
            intent_fingerprint=str(marker_fingerprint or "unknown"),
            request_id=str(marker_request_id or "unknown"),
            policy_flags_restored=True,
            detail=(
                "Policy flags were restored, but the marker belongs to another exact "
                "job/account/request/intent binding. The marker was retained."
            ),
        )
        report = _write_report_keep_marker(
            runtime_dir=runtime_dir,
            session_id=str(marker.get("session_id") or uuid4().hex),
            checkpoint=checkpoint,
            flags_before=dict(baseline),
            flags_during={},
            flags_after=flags_after,
        )
        if reopened is not None:
            try:
                reopened.close()  # type: ignore[attr-defined]
            except BaseException:
                pass
        return TopicGenerationLiveOutcome(
            checkpoint=checkpoint,
            flags_before=dict(baseline),
            flags_after=flags_after,
            report_path=report,
        )
    observed = _checkpoint_from_storage(
        target, request, status="RECOVERY_INSPECTED",
        reason_code="RECOVERY_INSPECTED", exit_code=EXIT_PREFLIGHT_REFUSED,
        policy_flags_restored=True,
    )
    if observed.reconciliation_required:
        recovery_status = "RECONCILIATION_REQUIRED"
        recovery_reason = "INTERRUPTED_SESSION_REQUIRES_RECONCILIATION"
        recovery_exit = EXIT_RECONCILIATION_REQUIRED
    elif (
        observed.job_status == "DONE" and observed.run_status == "SUCCESS"
        and observed.attempt_status == "SETTLED" and observed.attempt_count == 1
        and observed.usage_count == 1 and observed.approval_status == "consumed"
    ):
        recovery_status = "SUCCESS"
        recovery_reason = "INTERRUPTED_SESSION_RECOVERED_TERMINAL_SUCCESS"
        recovery_exit = EXIT_SUCCESS
    elif observed.job_status == "FAILED" and observed.run_status == "FAILED":
        recovery_status = "TERMINAL_FAILURE"
        recovery_reason = "INTERRUPTED_SESSION_RECOVERED_TERMINAL_FAILURE"
        recovery_exit = EXIT_TERMINAL_FAILURE
    else:
        recovery_status = "PREFLIGHT_REFUSED"
        recovery_reason = "INTERRUPTED_SESSION_RECOVERED_BEFORE_REQUEST"
        recovery_exit = EXIT_PREFLIGHT_REFUSED
    checkpoint = _checkpoint_from_storage(
        target, request, status=recovery_status,
        reason_code=recovery_reason, exit_code=recovery_exit,
        policy_flags_restored=True,
        detail=(
            "No provider retry or maintenance was performed. Inspect durable state and use "
            "list-reconciliations/reconcile-attempt only when reconciliation_required=true."
        ),
    )
    report, barrier_error = _finish_report_and_marker(
        runtime_dir=runtime_dir,
        session_id=str(marker.get("session_id") or uuid4().hex),
        checkpoint=checkpoint,
        flags_before=dict(baseline), flags_during={}, flags_after=flags_after,
    )
    if barrier_error is not None:
        checkpoint = TopicGenerationCheckpoint(
            **{
                **checkpoint.__dict__,
                "status": "RECOVERY_BARRIER_FAILED",
                "reason_code": barrier_error,
                "exit_code": EXIT_RECOVERY_BARRIER_FAILED,
            }
        )
    if reopened is not None:
        try:
            reopened.close()  # type: ignore[attr-defined]
        except BaseException:
            pass
    return TopicGenerationLiveOutcome(
        checkpoint=checkpoint, flags_before=dict(baseline),
        flags_after=flags_after, report_path=report,
    )


def run_topic_generation_live_once(
    request: TopicGenerationLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    storage_reopener: Callable[[], StoragePort],
    project_root: Path,
    runtime_dir: Path,
    frozen_quiescence: Mapping[str, object],
    clock: Clock,
    git_identity: Callable[[Path], tuple[str, str]] = _git_identity,
    db_fingerprint: Callable[[Path], DbFingerprint] = default_db_fingerprint,
    topic_generation_client_factory=None,
    worker_factory: Callable[[TopicGenerationLiveRequest], object] | None = None,
    failpoint_after_flags_open: Callable[[], None] | None = None,
    now: datetime | None = None,
) -> TopicGenerationLiveOutcome:
    """Execute exactly one Worker iteration for exactly one named job."""
    moment = _utc(now if now is not None else clock.now())
    existing = read_session_marker(runtime_dir)
    if existing is not None:
        return _recover_topic_marker(
            marker=existing, request=request, storage=storage,
            storage_reopener=storage_reopener, runtime_dir=runtime_dir, moment=moment,
        )

    try:
        branch, head = git_identity(project_root)
        if branch != request.expected_branch:
            raise TopicGenerationLiveError("BRANCH_MISMATCH", "Git branch differs")
        if head != request.expected_head:
            raise TopicGenerationLiveError("HEAD_MISMATCH", "Git HEAD differs")
        fingerprint = db_fingerprint(settings.db_path)
        if fingerprint.sha256.casefold() != request.expected_db_sha256.casefold():
            raise TopicGenerationLiveError("DB_SHA_MISMATCH", "database SHA differs")
        if fingerprint.schema_tail != request.expected_schema:
            raise TopicGenerationLiveError("SCHEMA_MISMATCH", "database schema differs")
        preflight, flags_before = _preflight_snapshot(
            storage, request, moment=moment, frozen_quiescence=frozen_quiescence,
        )
    except BaseException as exc:
        code = exc.code if isinstance(exc, TopicGenerationLiveError) else "PREFLIGHT_ERROR"
        checkpoint = _checkpoint_from_storage(
            storage, request, status="PREFLIGHT_REFUSED", reason_code=code,
            exit_code=EXIT_PREFLIGHT_REFUSED,
            policy_flags_restored=(
                isinstance(exc, TopicGenerationLiveError)
                and code != "NOT_FAIL_CLOSED_BASELINE"
            ),
            detail=exc.detail if isinstance(exc, TopicGenerationLiveError) else type(exc).__name__,
        )
        return TopicGenerationLiveOutcome(checkpoint=checkpoint)

    session_id = uuid4().hex
    marker = {
        "operation": _OPERATION,
        "session_id": session_id,
        "status": "ACQUIRED",
        "job_id": request.job_id,
        "account_id": request.account_id,
        "expected_request_id": request.request_id,
        "intent_fingerprint": request.expected_intent_fingerprint,
        "flags_before": flags_before,
        "preflight_fingerprint": preflight["preflight_fingerprint"],
        "opened_at": moment.isoformat(),
        "operator_attention_required": True,
    }
    if not acquire_session_marker(runtime_dir, marker):
        checkpoint = _checkpoint_from_storage(
            storage, request, status="PREFLIGHT_REFUSED",
            reason_code="SESSION_CONTENTION", exit_code=EXIT_PREFLIGHT_REFUSED,
            policy_flags_restored=True,
        )
        return TopicGenerationLiveOutcome(checkpoint=checkpoint, flags_before=flags_before)

    # Close the TOCTOU window between read-only validation and the filesystem
    # fence.  No flag has opened yet; any drift is a clean preflight refusal.
    try:
        repeated, repeated_flags = _preflight_snapshot(
            storage, request, moment=moment, frozen_quiescence=frozen_quiescence,
        )
        if repeated["preflight_fingerprint"] != preflight["preflight_fingerprint"]:
            raise TopicGenerationLiveError("STALE_PREFLIGHT", "durable state changed")
        if repeated_flags != flags_before:
            raise TopicGenerationLiveError("STALE_FLAG_SNAPSHOT", "flag snapshot changed")
    except BaseException as exc:
        checkpoint = _checkpoint_from_storage(
            storage, request, status="PREFLIGHT_REFUSED",
            reason_code=(exc.code if isinstance(exc, TopicGenerationLiveError) else "STALE_PREFLIGHT"),
            exit_code=EXIT_PREFLIGHT_REFUSED, policy_flags_restored=True,
            detail=type(exc).__name__,
        )
        report, barrier_error = _finish_report_and_marker(
            runtime_dir=runtime_dir, session_id=session_id, checkpoint=checkpoint,
            flags_before=flags_before, flags_during={}, flags_after=flags_before,
        )
        if barrier_error is not None:
            checkpoint = TopicGenerationCheckpoint(
                **{**checkpoint.__dict__, "status": "RECOVERY_BARRIER_FAILED",
                   "reason_code": barrier_error, "exit_code": EXIT_RECOVERY_BARRIER_FAILED}
            )
        return TopicGenerationLiveOutcome(
            checkpoint=checkpoint, flags_before=flags_before,
            flags_after=flags_before, report_path=report,
        )

    flags_during: dict[str, bool] = {}
    flags_after: dict[str, bool] = {}
    execution_error: BaseException | None = None
    restoration_error: BaseException | None = None
    worker_result: object | None = None
    reopened: StoragePort | None = None
    try:
        write_session_marker(runtime_dir, {**marker, "status": "OPENING"})
        flags_during = open_minimal_profile(
            storage, reason=f"{_OPERATION} {request.job_id} open", now=moment,
        )
        if flags_during != dict(OPEN_PROFILE):
            raise TopicGenerationLiveError("OPEN_PROFILE_MISMATCH", "open profile differs")
        write_session_marker(runtime_dir, {**marker, "status": "WORKER_RUNNING"})
        if failpoint_after_flags_open is not None:
            failpoint_after_flags_open()
        worker = (
            worker_factory(request)
            if worker_factory is not None
            else _default_worker(
                request, settings=settings, storage=storage, clock=clock,
                topic_generation_client_factory=topic_generation_client_factory,
            )
        )
        worker_result = worker.run_once()  # type: ignore[attr-defined]
    except BaseException as exc:
        execution_error = exc
    finally:
        try:
            flags_after = restore_fail_closed(
                storage, reason=f"{_OPERATION} {request.job_id} restore", now=moment,
            )
            if flags_after != flags_before:
                raise TopicGenerationLiveError(
                    "RESTORE_SNAPSHOT_MISMATCH", "restored flags differ from exact snapshot",
                )
        except BaseException as exc:
            restoration_error = exc
        if restoration_error is None:
            try:
                storage.close()  # type: ignore[attr-defined]
                reopened = storage_reopener()
                flags_after = confirm_flags(reopened)
                if flags_after != flags_before:
                    raise TopicGenerationLiveError(
                        "RESTORE_REOPEN_MISMATCH", "read-only reopen differs from snapshot",
                    )
            except BaseException as exc:
                restoration_error = exc

    inspected = reopened if reopened is not None else storage
    status_value = getattr(getattr(worker_result, "status", None), "value", None)
    if restoration_error is not None:
        status, reason, exit_code, restored = (
            "RESTORE_FAILED", "POLICY_RESTORE_FAILED", EXIT_POLICY_RESTORE_FAILED, False,
        )
        detail = type(restoration_error).__name__
    else:
        provisional = _checkpoint_from_storage(
            inspected, request, status="INSPECTING", reason_code="INSPECTING",
            exit_code=EXIT_TERMINAL_FAILURE, policy_flags_restored=True,
        )
        if provisional.reconciliation_required or status_value == "NEEDS_VERIFICATION":
            status, reason, exit_code = (
                "RECONCILIATION_REQUIRED", "RECONCILIATION_REQUIRED",
                EXIT_RECONCILIATION_REQUIRED,
            )
            detail = (
                "Do not rerun the provider. Use list-reconciliations and "
                "reconcile-attempt for the exact request_id."
            )
        elif (
            status_value == "DONE" and provisional.job_status == "DONE"
            and provisional.run_status == "SUCCESS"
            and provisional.attempt_status == "SETTLED"
            and provisional.attempt_count == 1 and provisional.usage_count == 1
            and provisional.approval_status == "consumed"
        ):
            status, reason, exit_code, detail = (
                "SUCCESS", "TERMINAL_SUCCESS", EXIT_SUCCESS, "",
            )
        elif (
            provisional.job_status == "FAILED" and provisional.run_status == "FAILED"
            and not provisional.reconciliation_required
        ):
            status, reason, exit_code, detail = (
                "TERMINAL_FAILURE", "TERMINAL_FAILURE", EXIT_TERMINAL_FAILURE, "",
            )
        elif (
            provisional.attempt_count == 0 and provisional.usage_count == 0
            and provisional.job_status == "QUEUED"
            and provisional.approval_status == "unconsumed"
        ):
            status, reason, exit_code = (
                "PREFLIGHT_REFUSED", "EXECUTION_ABORTED_BEFORE_REQUEST",
                EXIT_PREFLIGHT_REFUSED,
            )
            detail = (
                type(execution_error).__name__
                if execution_error is not None else f"worker_status={status_value or 'UNKNOWN'}"
            )
        else:
            status, reason, exit_code = (
                "TERMINAL_FAILURE", "EXECUTION_ERROR", EXIT_TERMINAL_FAILURE,
            )
            detail = (
                type(execution_error).__name__
                if execution_error is not None else f"worker_status={status_value or 'UNKNOWN'}"
            )
        restored = True

    checkpoint = _checkpoint_from_storage(
        inspected, request, status=status, reason_code=reason, exit_code=exit_code,
        policy_flags_restored=restored, detail=detail,
    )
    if restoration_error is not None:
        report = _write_report_keep_marker(
            runtime_dir=runtime_dir, session_id=session_id, checkpoint=checkpoint,
            flags_before=flags_before, flags_during=flags_during,
            flags_after=flags_after,
        )
        barrier_error = None
    else:
        report, barrier_error = _finish_report_and_marker(
            runtime_dir=runtime_dir, session_id=session_id, checkpoint=checkpoint,
            flags_before=flags_before, flags_during=flags_during,
            flags_after=flags_after,
        )
    if barrier_error is not None:
        checkpoint = TopicGenerationCheckpoint(
            **{**checkpoint.__dict__, "status": "RECOVERY_BARRIER_FAILED",
               "reason_code": barrier_error, "exit_code": EXIT_RECOVERY_BARRIER_FAILED}
        )
    if reopened is not None:
        try:
            reopened.close()  # type: ignore[attr-defined]
        except BaseException:
            pass
    return TopicGenerationLiveOutcome(
        checkpoint=checkpoint, flags_before=flags_before,
        flags_during=flags_during, flags_after=flags_after, report_path=report,
    )
