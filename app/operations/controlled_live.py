"""Kanoniczny, fail-closed wrapper jednego controlled live acceptance.

Moduł składa trwałą sesję, pełny pricing contract, dokładnie jeden fenced worker,
recovery bez retry, prawdziwy reopen oraz trwały i zanonimizowany raport. Realny
provider pozostaje wyłączony; testowy composition root używa wyłącznie fake workera
na tymczasowej bazie.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from types import MappingProxyType
from typing import Callable, Mapping
from uuid import uuid4

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.pricing import (
    PricingConfigError,
    PricingProfile,
    assert_frozen_pricing_contract,
    default_pricing_profiles_path,
    load_pricing_profiles,
    resolve_real_pricing_profile,
)
from app.core.security_flags import SECURITY_FLAG_DEFAULTS
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    OperationalFieldStatus,
    ResearchCard,
    ResearchRecommendation,
    RunStatus,
    Source,
    SourceType,
    SourceVerification,
    WorkflowType,
)
from app.ports.storage import JobConflictError, StoragePort
from app.research.durable_intent import (
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    canonicalize_durable_research_payload,
    controlled_research_job_id,
    controlled_session_contract,
    durable_execution_intent_fingerprint,
)

FLAG_KEYS = (
    "kill_switch",
    "safe_mode",
    "worker_enabled",
    "paid_actions_enabled",
    "browser_actions_enabled",
)
OPEN_PROFILE_ORDER: list[tuple[str, bool]] = [
    ("safe_mode", False),
    ("worker_enabled", True),
    ("paid_actions_enabled", True),
    ("browser_actions_enabled", False),
    ("kill_switch", False),
]
OPEN_PROFILE = MappingProxyType(dict(OPEN_PROFILE_ORDER))
FAIL_CLOSED_ORDER: list[tuple[str, bool]] = [
    ("kill_switch", True),
    ("safe_mode", True),
    ("worker_enabled", False),
    ("paid_actions_enabled", False),
    ("browser_actions_enabled", False),
]
FAIL_CLOSED_PROFILE = MappingProxyType(dict(SECURITY_FLAG_DEFAULTS))

REAL_CONTROLLED_LIVE_ENABLED = False
_MARKER_NAME = "controlled_live_session.json"
_UPDATED_BY = "controlled-live-once"
_ATTEMPT_STAGE = "research"
_ATTEMPT_NO = 1


class ControlledLiveError(RuntimeError):
    def __init__(self, detail: str, *, code: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ControlledLiveRequest:
    account_id: str
    topic_id: int
    operation_key: str
    model: str
    pricing_profile_id: str
    max_tokens: int
    max_web_searches: int
    max_cost_usd: str
    expected_db_sha256: str
    expected_schema: str
    expected_branch: str
    expected_head: str
    max_attempts: int = 1
    max_retries: int = 0

    def job_id(self) -> str:
        return controlled_research_job_id(self.operation_key)


@dataclass(frozen=True)
class DbFingerprint:
    sha256: str
    size: int
    schema_tail: str


@dataclass(frozen=True)
class ControlledWorkerContract:
    session_id: str
    operation_key: str
    expected_job_id: str
    expected_request_id: str
    expected_attempt_no: int
    worker_execution_token: str

    def as_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "operation_key": self.operation_key,
            "expected_job_id": self.expected_job_id,
            "expected_request_id": self.expected_request_id,
            "expected_attempt_no": self.expected_attempt_no,
            "worker_execution_token": self.worker_execution_token,
        }


@dataclass(frozen=True)
class WorkerOnceResult:
    status: str
    job_id: str | None = None
    request_id: str | None = None
    attempt_no: int | None = None
    worker_execution_token: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class FrozenPlan:
    session_id: str
    operation_key: str
    job_id: str
    request_id: str
    attempt_no: int
    worker_execution_token: str
    execution_intent_fingerprint: str
    model: str
    pricing_fingerprint: str
    pricing_profile_id: str
    pricing_profile_version: str
    pricing_currency: str
    pricing_unit: str
    pricing_profile: dict[str, str]
    max_tokens: int
    max_web_searches: int
    projected_cost_usd: str
    pessimistic_cost_usd: str
    cap_usd: str
    preflight_fingerprint: str
    flags_before: dict[str, bool]
    flags_during: dict[str, bool]
    flags_after: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "operation_key": self.operation_key,
            "job_id": self.job_id,
            "request_id": self.request_id,
            "attempt_no": self.attempt_no,
            "worker_execution_token_hash": _diagnostic_hash(
                self.worker_execution_token
            ),
            "execution_intent_fingerprint": self.execution_intent_fingerprint,
            "model": self.model,
            "pricing_fingerprint": self.pricing_fingerprint,
            "pricing_profile_id": self.pricing_profile_id,
            "pricing_profile_version": self.pricing_profile_version,
            "pricing_currency": self.pricing_currency,
            "pricing_unit": self.pricing_unit,
            "pricing_profile": dict(self.pricing_profile),
            "max_tokens": self.max_tokens,
            "max_web_searches": self.max_web_searches,
            "projected_cost_usd": self.projected_cost_usd,
            "pessimistic_cost_usd": self.pessimistic_cost_usd,
            "cap_usd": self.cap_usd,
            "preflight_fingerprint": self.preflight_fingerprint,
            "flags_before": dict(self.flags_before),
            "flags_during": dict(self.flags_during),
            "flags_after": dict(self.flags_after),
        }


@dataclass(frozen=True)
class ControlledLiveOutcome:
    status: str
    exit_code: int
    session_id: str
    report_path: Path | None = None
    plan: FrozenPlan | None = None
    flags_after: dict[str, bool] = field(default_factory=dict)
    worker_result: WorkerOnceResult | None = None
    recovery: dict[str, object] | None = None
    detail: str = ""


@dataclass(frozen=True)
class PreflightResult:
    job: Job
    intent: DurableResearchExecutionIntent
    profile: PricingProfile
    execution_intent_fingerprint: str
    preflight_fingerprint: str
    flags_before: dict[str, bool]


def marker_path(runtime_dir: Path) -> Path:
    return runtime_dir / _MARKER_NAME


def _diagnostic_hash(value: object) -> str:
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def _fsync_directory(directory: Path) -> None:
    """Durability barrier for directory metadata.

    POSIX supports fsync on a directory descriptor. Windows does not expose that
    through ``os.open``; a create+fsync+unlink barrier in the same directory is
    the closest available Python-level equivalent and forces its metadata volume.
    """
    if os.name != "nt":
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    barrier = directory / f".dirsync-{uuid4().hex}.tmp"
    fd = os.open(str(barrier), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(b"directory durability barrier\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    barrier.unlink()


def _durable_json_replace(path: Path, payload: Mapping[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    encoded = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    try:
        os.replace(tmp, path)
        _fsync_directory(path.parent)
    except BaseException:
        if tmp.exists():
            tmp.unlink()
        raise
    return path


def read_session_marker(runtime_dir: Path) -> dict[str, object] | None:
    path = marker_path(runtime_dir)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, ValueError):
        return {"session_id": "unreadable", "status": "UNKNOWN", "corrupt": True}
    if not isinstance(loaded, dict):
        return {"session_id": "unreadable", "status": "UNKNOWN", "corrupt": True}
    return loaded


def acquire_session_marker(
    runtime_dir: Path, marker: Mapping[str, object],
) -> bool:
    """Acquire the session identity with O_EXCL and fsync file + directory."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    path = marker_path(runtime_dir)
    encoded = (
        json.dumps(dict(marker), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(fd)
    _fsync_directory(runtime_dir)
    return True


def write_session_marker(
    runtime_dir: Path, marker: Mapping[str, object],
) -> None:
    _durable_json_replace(marker_path(runtime_dir), marker)


def clear_session_marker(runtime_dir: Path) -> None:
    """Unlink only after a durable report, then persist the directory mutation."""
    path = marker_path(runtime_dir)
    if not path.exists():
        raise ControlledLiveError(
            "owned session marker disappeared before durable clear.",
            code="MARKER_OWNERSHIP_LOST",
        )
    path.unlink()
    try:
        _fsync_directory(runtime_dir)
    except BaseException:
        # The unlink durability is unknown. Re-establish an explicit recovery
        # marker before surfacing the failure whenever the filesystem permits.
        try:
            acquire_session_marker(
                runtime_dir,
                {
                    "session_id": "marker-clear-uncertain",
                    "status": "MARKER_CLEAR_DURABILITY_UNKNOWN",
                    "operator_attention_required": True,
                },
            )
        except BaseException:
            pass
        raise


def confirm_flags(storage: StoragePort) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key in FLAG_KEYS:
        flag = storage.get_system_flag(key)
        if flag is None or not flag.is_valid:
            raise ControlledLiveError(
                f"security flag {key!r} is absent or invalid.",
                code="FLAG_CONFIRM_FAILED",
            )
        result[key] = flag.value
    return result


def is_fail_closed(flags: Mapping[str, bool]) -> bool:
    return all(
        flags.get(key) == value
        for key, value in SECURITY_FLAG_DEFAULTS.items()
    )


def open_minimal_profile(
    storage: StoragePort, *, reason: str, now: datetime | None = None,
) -> dict[str, bool]:
    storage.apply_security_flag_profile(
        OPEN_PROFILE_ORDER,
        updated_by=_UPDATED_BY,
        reason=reason,
        now=now,
    )
    return confirm_flags(storage)


def restore_fail_closed(
    storage: StoragePort, *, reason: str, now: datetime | None = None,
) -> dict[str, bool]:
    storage.apply_security_flag_profile(
        FAIL_CLOSED_ORDER,
        updated_by=_UPDATED_BY,
        reason=reason,
        now=now,
    )
    return confirm_flags(storage)


def default_db_fingerprint(db_path: Path) -> DbFingerprint:
    data = db_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest().upper()
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        versions = [
            str(row[0])
            for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
    finally:
        conn.close()
    return DbFingerprint(
        sha256=sha,
        size=len(data),
        schema_tail=versions[-1] if versions else "",
    )


def default_quiescence_probe(
    project_root: Path, db_path: Path,
) -> Mapping[str, tuple]:
    """Use the approved Windows process/task/handle inventory; never an empty stub."""
    from app.operations.stage1_migration import _default_quiesce_probe

    report = _default_quiesce_probe(project_root, db_path)
    return {
        "project_process_ids": tuple(report.project_process_ids),
        "scheduled_tasks": tuple(report.scheduled_tasks),
        "locked_paths": tuple(report.locked_paths),
    }


def _persisted_now(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ControlledLiveError(
            "controlled-live clock must be timezone-aware.",
            code="CLOCK_NOT_TIMEZONE_AWARE",
        )
    utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return (
        utc.strftime("%Y-%m-%d %H:%M:%S.%f")
        if utc.microsecond
        else utc.strftime("%Y-%m-%d %H:%M:%S")
    )


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None or moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _claimable_job_ids(storage: StoragePort, moment: datetime) -> tuple[str, ...]:
    conn = getattr(storage, "conn", None)
    if conn is None:
        raise ControlledLiveError(
            "storage does not expose the canonical claimability snapshot.",
            code="CLAIMABILITY_UNAVAILABLE",
        )
    current_ts = _persisted_now(moment)
    rows = conn.execute(
        "SELECT id FROM jobs WHERE status='QUEUED' AND earliest_run_at<=? "
        "AND (deadline_at IS NULL OR deadline_at>=?) AND attempts<max_attempts "
        "AND lease_owner IS NULL AND lease_expires_at IS NULL "
        "ORDER BY priority DESC,deadline_at IS NULL ASC,deadline_at ASC,created_at ASC,id ASC",
        (current_ts, current_ts),
    ).fetchall()
    return tuple(str(row["id"]) for row in rows)


def _compute_preflight_fingerprint(components: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(components),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _expected_session_payload(
    contract: ControlledWorkerContract,
) -> dict[str, object]:
    return contract.as_dict()


def _validate_expected_job(
    request: ControlledLiveRequest,
    job: Job,
    *,
    contract: ControlledWorkerContract,
    profile: PricingProfile,
    moment: datetime,
) -> tuple[Job, DurableResearchExecutionIntent]:
    if job.id != contract.expected_job_id:
        raise ControlledLiveError("foreign job identity.", code="JOB_OWNERSHIP_MISMATCH")
    if job.account_id != request.account_id or job.topic_id != request.topic_id:
        raise ControlledLiveError(
            "job account/topic identity differs from the request.",
            code="JOB_IDENTITY_MISMATCH",
        )
    if job.idempotency_key != f"real-research:{request.operation_key}":
        raise ControlledLiveError(
            "job operation key differs from the request.",
            code="OPERATION_KEY_MISMATCH",
        )
    if (
        job.payload.get("dry_run") is not False
        or job.payload.get("execution") != "durable_provider_v2"
    ):
        raise ControlledLiveError(
            "expected a durable real job.",
            code="JOB_NOT_DURABLE_REAL",
        )
    try:
        canonical = canonicalize_durable_research_payload(job.payload)
        intent_raw = canonical["execution_intent"]
        assert isinstance(intent_raw, dict)
        intent = DurableResearchExecutionIntent.from_payload(intent_raw)
    except (DurableExecutionIntentError, AssertionError) as exc:
        raise ControlledLiveError(
            "durable payload is invalid.",
            code="JOB_PAYLOAD_INVALID",
        ) from exc
    if canonical.get("controlled_session") != _expected_session_payload(contract):
        raise ControlledLiveError(
            "job is not fenced to this controlled session.",
            code="SESSION_FENCE_MISMATCH",
        )
    if job.max_attempts != 1 or request.max_attempts != 1:
        raise ControlledLiveError(
            "max_attempts must be exactly 1.",
            code="MAX_ATTEMPTS_NOT_ONE",
        )
    if intent.max_retries != 0 or request.max_retries != 0:
        raise ControlledLiveError(
            "max_retries must be exactly 0.",
            code="MAX_RETRIES_NOT_ZERO",
        )
    if intent.max_tokens != request.max_tokens:
        raise ControlledLiveError(
            "max_tokens mismatch.",
            code="MAX_TOKENS_MISMATCH",
        )
    if intent.max_web_searches != request.max_web_searches:
        raise ControlledLiveError(
            "max_web_searches mismatch.",
            code="MAX_WEB_SEARCHES_MISMATCH",
        )
    if intent.cap_usd != format(Decimal(request.max_cost_usd).quantize(Decimal("0.000001")), ".6f"):
        raise ControlledLiveError("cap mismatch.", code="CAP_MISMATCH")
    try:
        assert_frozen_pricing_contract(
            profile=profile,
            profile_id=intent.pricing_profile_id,
            version=intent.pricing_profile_version,
            model=intent.model,
            currency=intent.pricing_currency,
            unit=intent.pricing_unit,
            prices=intent.pricing_profile,
            fingerprint=intent.pricing_fingerprint,
        )
    except PricingConfigError as exc:
        raise ControlledLiveError(
            "frozen pricing contract differs from approved pricing.",
            code="FROZEN_PRICING_MISMATCH",
        ) from exc
    if (
        intent.pricing_profile_id != request.pricing_profile_id
        or intent.model != request.model
    ):
        raise ControlledLiveError(
            "request differs from frozen pricing/model identity.",
            code="PRICING_OR_MODEL_MISMATCH",
        )
    if not intent.is_supported_by_current_worker():
        raise ControlledLiveError(
            "intent is unsupported.",
            code="UNSUPPORTED_INTENT",
        )
    if (
        job.status is not JobStatus.QUEUED
        or job.lease_owner is not None
        or job.lease_expires_at is not None
        or job.attempts >= job.max_attempts
        or _as_utc(job.earliest_run_at) > _as_utc(moment)
        or (
            job.deadline_at is not None
            and _as_utc(job.deadline_at) < _as_utc(moment)
        )
    ):
        raise ControlledLiveError(
            "expected job is not currently claimable.",
            code="JOB_NOT_CLAIMABLE",
        )
    return job, intent


def _ensure_expected_claimable_job(
    request: ControlledLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    profile: PricingProfile,
    contract: ControlledWorkerContract,
    moment: datetime,
    allow_job_creation: bool,
) -> tuple[Job, DurableResearchExecutionIntent]:
    existing = storage.get_job(contract.expected_job_id)
    if existing is None:
        if not allow_job_creation:
            raise ControlledLiveError(
                "the controlled-live job must be durably enqueued before the real wrapper starts.",
                code="EXPECTED_JOB_MISSING",
            )
        account = settings.get_account(request.account_id)
        topic = next(
            (
                candidate
                for candidate in storage.list_topics(account.id)
                if candidate.id == request.topic_id
            ),
            None,
        )
        if topic is None:
            raise ControlledLiveError(
                "requested topic is unavailable.",
                code="TOPIC_MISSING",
            )
        intent = DurableResearchExecutionIntent.from_settings(
            settings=settings,
            account_id=account.id,
            topic_id=int(topic.id),
            cap_usd=request.max_cost_usd,
            max_web_searches=request.max_web_searches,
            question=topic.question
            or f"Why does '{topic.title}' work the way it does?",
            niche=account.niche,
            max_tokens=request.max_tokens,
            pricing_prices=profile.prices,
            pricing_profile_id=profile.profile_id,
            pricing_profile_version=profile.version,
            pricing_currency=profile.currency,
            pricing_unit=profile.unit,
        )
        storage.ensure_account(account)
        candidate = Job(
            id=contract.expected_job_id,
            account_id=account.id,
            kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH,
            idempotency_key=f"real-research:{request.operation_key}",
            topic_id=int(topic.id),
            payload={
                "account_id": account.id,
                "topic_id": int(topic.id),
                "dry_run": False,
                "execution": "durable_provider_v2",
                "mode": "single",
                "max_cost_usd": intent.cap_usd,
                "execution_intent": intent.as_payload(),
                "controlled_session": contract.as_dict(),
            },
            schedule_reason="WITHIN_EDITORIAL_WINDOW",
            earliest_run_at=moment,
            max_attempts=1,
        )
        try:
            existing = storage.enqueue_job_result(candidate).job
        except JobConflictError as exc:
            raise ControlledLiveError(
                "operation key conflicts with a different durable intent.",
                code="JOB_CONFLICT",
            ) from exc
    return _validate_expected_job(
        request,
        existing,
        contract=contract,
        profile=profile,
        moment=moment,
    )


def run_preflight(
    request: ControlledLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    project_root: Path,
    contract: ControlledWorkerContract,
    git_identity: Callable[[Path], tuple[str, str]],
    db_fingerprint: Callable[[Path], DbFingerprint],
    quiescence_probe: Callable[[], Mapping[str, tuple]],
    pricing_profiles_path: Path | None,
    clock: Clock,
    now: datetime | None = None,
    allow_job_creation: bool = False,
) -> PreflightResult:
    moment = now if now is not None else clock.now()
    flags_before = confirm_flags(storage)
    if not is_fail_closed(flags_before):
        raise ControlledLiveError(
            "system is not fail-closed at entry.",
            code="NOT_FAIL_CLOSED_AT_START",
        )
    branch, head = git_identity(project_root)
    if branch != request.expected_branch:
        raise ControlledLiveError("branch mismatch.", code="BRANCH_MISMATCH")
    if head != request.expected_head:
        raise ControlledLiveError("HEAD mismatch.", code="HEAD_MISMATCH")
    fingerprint = db_fingerprint(settings.db_path)
    if fingerprint.sha256.upper() != request.expected_db_sha256.upper():
        raise ControlledLiveError(
            "database fingerprint mismatch.",
            code="DB_SHA_MISMATCH",
        )
    if not fingerprint.schema_tail.startswith(request.expected_schema):
        raise ControlledLiveError("schema mismatch.", code="SCHEMA_MISMATCH")

    quiescence = quiescence_probe()
    if quiescence.get("project_process_ids"):
        raise ControlledLiveError(
            "project processes are active.",
            code="PROCESSES_PRESENT",
        )
    if quiescence.get("scheduled_tasks"):
        raise ControlledLiveError(
            "project Windows tasks are registered.",
            code="TASKS_PRESENT",
        )
    if quiescence.get("locked_paths"):
        raise ControlledLiveError(
            "database paths have active handles.",
            code="DB_HANDLES_PRESENT",
        )

    operational = storage.read_operational_report(clock=clock)
    if (
        operational.active_leases.status is not OperationalFieldStatus.OK
        or operational.active_leases.value != 0
    ):
        raise ControlledLiveError("active lease exists.", code="ACTIVE_LEASES")
    if (
        operational.active_reservations.status is not OperationalFieldStatus.OK
        or operational.active_reservations.value != 0
    ):
        raise ControlledLiveError(
            "active reservation exists.",
            code="ACTIVE_RESERVATIONS",
        )
    try:
        path = pricing_profiles_path or default_pricing_profiles_path(project_root)
        profile = resolve_real_pricing_profile(
            load_pricing_profiles(path),
            profile_id=request.pricing_profile_id,
            model=request.model,
        )
    except PricingConfigError as exc:
        raise ControlledLiveError(
            "pricing profile is not approved.",
            code="PRICING_NOT_APPROVED",
        ) from exc

    job, intent = _ensure_expected_claimable_job(
        request,
        settings=settings,
        storage=storage,
        profile=profile,
        contract=contract,
        moment=moment,
        allow_job_creation=allow_job_creation,
    )
    claimable = _claimable_job_ids(storage, moment)
    if claimable != (contract.expected_job_id,):
        raise ControlledLiveError(
            "the expected job is not the only currently claimable job.",
            code="NOT_SINGLE_EXPECTED_CLAIMABLE_JOB",
        )
    if Decimal(intent.pessimistic_cost_usd) > Decimal(intent.cap_usd):
        raise ControlledLiveError(
            "pessimistic frozen projection exceeds frozen cap.",
            code="COST_OVER_CAP",
        )
    canonical = canonicalize_durable_research_payload(job.payload)
    intent_fingerprint = durable_execution_intent_fingerprint(canonical)
    preflight_fingerprint = _compute_preflight_fingerprint(
        {
            "branch": branch,
            "head": head,
            "db_sha256": fingerprint.sha256.upper(),
            "schema_tail": fingerprint.schema_tail,
            "claimable": claimable,
            "session": contract.as_dict(),
            "execution_intent_fingerprint": intent_fingerprint,
            "pricing_fingerprint": intent.pricing_fingerprint,
            "projected_cost_usd": intent.projected_cost_usd,
            "pessimistic_cost_usd": intent.pessimistic_cost_usd,
            "cap_usd": intent.cap_usd,
            "flags_before": flags_before,
        }
    )
    return PreflightResult(
        job=job,
        intent=intent,
        profile=profile,
        execution_intent_fingerprint=intent_fingerprint,
        preflight_fingerprint=preflight_fingerprint,
        flags_before=flags_before,
    )


_SENSITIVE_KEY = re.compile(
    r"(authorization|api[_-]?key|secret|password|token|prompt|question|guidance|payload)",
    re.IGNORECASE,
)
_AUTH_VALUE = re.compile(r"(?i)\b(authorization\s*:\s*)(?:bearer\s+)?[^\s,;]+")
_KEY_VALUE = re.compile(
    r"(?i)\b(api[_ -]?key|secret|password|token)\s*[:=]\s*[^\s,;]+"
)
_PROVIDER_KEY = re.compile(r"\b(?:sk|ant|key)-[A-Za-z0-9_-]{8,}\b")


def sanitize_report_payload(value: object, *, key: str = "") -> object:
    """Redact secrets and private/provider payloads before durable serialization."""
    if _SENSITIVE_KEY.search(key) and key not in {
        "worker_execution_token_hash",
        "pricing_fingerprint",
        "execution_intent_fingerprint",
        "preflight_fingerprint",
        "diagnostic_fingerprint",
        "max_tokens",
    }:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize_report_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_report_payload(item, key=key) for item in value]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str):
        redacted = _AUTH_VALUE.sub(r"\1[REDACTED]", value)
        redacted = _KEY_VALUE.sub("[REDACTED]", redacted)
        redacted = _PROVIDER_KEY.sub("[REDACTED]", redacted)
        for env_key, env_value in os.environ.items():
            if (
                env_value
                and len(env_value) >= 8
                and _SENSITIVE_KEY.search(env_key)
            ):
                redacted = redacted.replace(env_value, "[REDACTED]")
        return redacted
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


_OPERATOR_MESSAGES = {
    "REAL_EXECUTION_DISABLED": "Real execution is disabled; no worker was run.",
    "PREFLIGHT_FAILED": "Preflight rejected the controlled session.",
    "STALE_PREFLIGHT": "State changed between preflight and profile opening.",
    "WORKER_FAILED": "The fenced worker did not produce a confirmed success.",
    "OWNERSHIP_FAILED": "Worker or durable state ownership could not be confirmed.",
    "VALIDATION_FAILED": "Durable terminal state did not satisfy success criteria.",
    "RESTORE_FAILED": "Fail-closed restoration could not be confirmed.",
    "REOPEN_FAILED": "A new storage connection could not confirm durable state.",
    "RECOVERY_REQUIRED": "An interrupted controlled session requires operator attention.",
    "REPORT_WRITE_FAILED": "The operator report was not durably written.",
    "MARKER_CLEAR_FAILED": "The recovery marker could not be durably removed.",
}


def _safe_error(exc: BaseException | None, reason_code: str) -> dict[str, object] | None:
    if exc is None:
        return None
    return {
        "error_class": type(exc).__name__,
        "reason_code": reason_code,
        "operator_message": _OPERATOR_MESSAGES.get(
            reason_code,
            "Controlled-live stopped fail-closed; inspect durable state.",
        ),
        "diagnostic_fingerprint": _diagnostic_hash(
            f"{type(exc).__name__}:{exc}"
        ),
    }


def write_operator_report(
    reports_dir: Path,
    session_id: str,
    payload: Mapping[str, object],
) -> Path:
    safe = sanitize_report_payload(payload)
    assert isinstance(safe, Mapping)
    return _durable_json_replace(
        reports_dir / f"{session_id}.json",
        safe,
    )


def _execution_evidence(
    storage: StoragePort,
    *,
    expected_job_id: str,
    expected_request_id: str,
) -> dict[str, object]:
    conn = getattr(storage, "conn", None)
    if conn is None:
        raise ControlledLiveError(
            "reopened storage cannot expose durable evidence.",
            code="EVIDENCE_UNAVAILABLE",
        )
    job = conn.execute(
        "SELECT * FROM jobs WHERE id=?",
        (expected_job_id,),
    ).fetchone()
    attempts = conn.execute(
        "SELECT * FROM provider_attempts WHERE job_id=? ORDER BY attempt_no",
        (expected_job_id,),
    ).fetchall()
    usage = conn.execute(
        "SELECT * FROM model_usage WHERE request_id=? ORDER BY id",
        (expected_request_id,),
    ).fetchall()
    run = None
    research_run = None
    if job is not None and job["run_id"] is not None:
        run = conn.execute(
            "SELECT * FROM runs WHERE id=?", (job["run_id"],)
        ).fetchone()
        research_run = conn.execute(
            "SELECT * FROM research_runs WHERE id=?", (job["run_id"],)
        ).fetchone()
    reconciliation_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM reconciliation_events WHERE request_id=?",
            (expected_request_id,),
        ).fetchone()[0]
    )
    return {
        "job": None if job is None else dict(job),
        "attempts": [dict(row) for row in attempts],
        "usage": [dict(row) for row in usage],
        "run": None if run is None else dict(run),
        "research_run": None if research_run is None else dict(research_run),
        "reconciliation_event_count": reconciliation_count,
    }


def _validate_success_evidence(
    *,
    evidence: Mapping[str, object],
    plan: FrozenPlan,
    worker_result: WorkerOnceResult | None,
    flags_after: Mapping[str, bool],
) -> None:
    if not is_fail_closed(flags_after):
        raise ControlledLiveError(
            "reopened flags are not fail-closed.",
            code="FAIL_CLOSED_NOT_CONFIRMED",
        )
    if worker_result is None or worker_result.status != "SUCCEEDED":
        raise ControlledLiveError(
            "worker did not report success.",
            code="WORKER_NOT_SUCCEEDED",
        )
    if (
        worker_result.job_id != plan.job_id
        or worker_result.request_id != plan.request_id
        or worker_result.attempt_no != plan.attempt_no
        or worker_result.worker_execution_token != plan.worker_execution_token
    ):
        raise ControlledLiveError(
            "worker result belongs to a foreign execution.",
            code="WORKER_RESULT_OWNERSHIP_MISMATCH",
        )
    job = evidence.get("job")
    attempts = evidence.get("attempts")
    usage = evidence.get("usage")
    run = evidence.get("run")
    research_run = evidence.get("research_run")
    if not isinstance(job, Mapping) or job.get("id") != plan.job_id:
        raise ControlledLiveError("expected job is absent.", code="EXPECTED_JOB_ABSENT")
    if not isinstance(attempts, list) or len(attempts) != 1:
        raise ControlledLiveError(
            "success requires exactly one provider attempt.",
            code="ATTEMPT_COUNT_NOT_ONE",
        )
    attempt = attempts[0]
    if not isinstance(attempt, Mapping) or (
        attempt.get("attempt_no") != 1
        or attempt.get("request_id") != plan.request_id
        or attempt.get("job_id") != plan.job_id
        or attempt.get("status") != "SETTLED"
        or attempt.get("request_started_at") is None
        or attempt.get("settled_at") is None
        or attempt.get("execution_intent_fingerprint")
        != plan.execution_intent_fingerprint
    ):
        raise ControlledLiveError(
            "provider attempt is not the expected settled attempt #1.",
            code="ATTEMPT_STATE_MISMATCH",
        )
    if not isinstance(usage, list) or len(usage) != 1:
        raise ControlledLiveError(
            "success requires exactly one canonical usage row.",
            code="USAGE_COUNT_NOT_ONE",
        )
    usage_row = usage[0]
    if not isinstance(usage_row, Mapping) or (
        usage_row.get("request_id") != plan.request_id
        or usage_row.get("run_id") != job.get("run_id")
        or int(usage_row.get("dry_run", 1)) != 0
    ):
        raise ControlledLiveError(
            "usage is not owned by the expected request/run.",
            code="USAGE_OWNERSHIP_MISMATCH",
        )
    settled = Decimal(str(attempt.get("actual_cost_usd"))).quantize(
        Decimal("0.000001")
    )
    usage_cost = Decimal(str(usage_row.get("estimated_cost_usd"))).quantize(
        Decimal("0.000001")
    )
    if settled != usage_cost:
        raise ControlledLiveError(
            "settlement differs from canonical usage.",
            code="SETTLEMENT_USAGE_MISMATCH",
        )
    if (
        job.get("status") != "DONE"
        or int(job.get("attempts", 0)) != 1
        or job.get("lease_owner") is not None
        or job.get("lease_expires_at") is not None
        or Decimal(str(job.get("reserved_cost_usd", 0))) != 0
        or job.get("budget_reserved_at") is not None
    ):
        raise ControlledLiveError(
            "job is not terminal and reservation-free.",
            code="JOB_TERMINAL_STATE_MISMATCH",
        )
    if not isinstance(run, Mapping) or (
        run.get("id") != job.get("run_id")
        or run.get("status") != "SUCCESS"
    ):
        raise ControlledLiveError(
            "run is not terminal SUCCESS.",
            code="RUN_TERMINAL_STATE_MISMATCH",
        )
    if not isinstance(research_run, Mapping) or (
        research_run.get("id") != job.get("run_id")
        or research_run.get("status") != "COMPLETE"
        or research_run.get("research_card_id") is None
    ):
        raise ControlledLiveError(
            "research_run is not terminal COMPLETE.",
            code="RESEARCH_RUN_TERMINAL_STATE_MISMATCH",
        )


def _report_evidence(evidence: Mapping[str, object] | None) -> dict[str, object]:
    if evidence is None:
        return {}
    job = evidence.get("job")
    attempts = evidence.get("attempts")
    usage = evidence.get("usage")
    run = evidence.get("run")
    research_run = evidence.get("research_run")
    attempt = attempts[0] if isinstance(attempts, list) and len(attempts) == 1 else None
    return {
        "job_status": job.get("status") if isinstance(job, Mapping) else None,
        "job_attempts": job.get("attempts") if isinstance(job, Mapping) else None,
        "run_status": run.get("status") if isinstance(run, Mapping) else None,
        "research_run_status": (
            research_run.get("status")
            if isinstance(research_run, Mapping)
            else None
        ),
        "provider_attempt_count": len(attempts) if isinstance(attempts, list) else None,
        "provider_attempt_status": (
            attempt.get("status") if isinstance(attempt, Mapping) else None
        ),
        "request_id": (
            attempt.get("request_id") if isinstance(attempt, Mapping) else None
        ),
        "usage_count": len(usage) if isinstance(usage, list) else None,
        "reconciliation_event_count": evidence.get(
            "reconciliation_event_count"
        ),
        "active_lease": bool(
            isinstance(job, Mapping) and job.get("lease_owner") is not None
        ),
        "active_job_reservation": bool(
            isinstance(job, Mapping)
            and job.get("budget_reserved_at") is not None
        ),
    }


def _write_then_clear_marker(
    *,
    reports_dir: Path,
    runtime_dir: Path,
    session_id: str,
    payload: Mapping[str, object],
    final_status: str,
    report_writer: Callable[[Path, str, Mapping[str, object]], Path],
    marker_clearer: Callable[[Path], None],
) -> tuple[Path | None, str | None]:
    """Persist provisional report, clear+fsync marker, then persist final status."""
    provisional = dict(payload)
    provisional["final_status"] = "REPORT_DURABLE_AWAITING_MARKER_CLEAR"
    provisional["candidate_status"] = final_status
    try:
        report_path = report_writer(reports_dir, session_id, provisional)
    except BaseException:
        return None, "REPORT_WRITE_FAILED"
    try:
        marker_clearer(runtime_dir)
    except BaseException:
        failed = dict(payload)
        failed["final_status"] = "MARKER_CLEAR_FAILED_RECOVERY_REQUIRED"
        failed["candidate_status"] = final_status
        try:
            report_writer(reports_dir, session_id, failed)
        except BaseException:
            pass
        return report_path, "MARKER_CLEAR_FAILED"
    final = dict(payload)
    final["final_status"] = final_status
    final["marker_cleared"] = True
    try:
        report_path = report_writer(reports_dir, session_id, final)
    except BaseException:
        # Recreate a durable recovery marker if final report promotion fails.
        try:
            acquire_session_marker(
                runtime_dir,
                {
                    "session_id": session_id,
                    "status": "REPORT_FINALIZATION_FAILED",
                    "operator_attention_required": True,
                },
            )
        except BaseException:
            pass
        return report_path, "REPORT_WRITE_FAILED"
    return report_path, None


def _close_and_reopen(
    storage: StoragePort,
    storage_reopener: Callable[[], StoragePort],
) -> StoragePort:
    close = getattr(storage, "close", None)
    if close is None:
        raise ControlledLiveError(
            "storage cannot be closed for reopen proof.",
            code="STORAGE_CLOSE_UNAVAILABLE",
        )
    close()
    reopened = storage_reopener()
    if reopened is storage:
        raise ControlledLiveError(
            "reopen returned the same storage object.",
            code="REOPEN_NOT_NEW_CONNECTION",
        )
    return reopened


def _recover_existing_session(
    *,
    marker: Mapping[str, object],
    settings: Settings,
    storage: StoragePort,
    storage_reopener: Callable[[], StoragePort],
    runtime_dir: Path,
    reports_dir: Path,
    clock: Clock,
    now: datetime | None,
    report_writer: Callable[[Path, str, Mapping[str, object]], Path],
    marker_clearer: Callable[[Path], None],
) -> ControlledLiveOutcome:
    session_id = uuid4().hex
    moment = now if now is not None else clock.now()
    flags_after: dict[str, bool] = {}
    recovery: dict[str, object] = {
        "recovered_session": marker.get("session_id"),
        "prior_status": marker.get("status"),
        "retry_performed": False,
    }
    error: BaseException | None = None
    reopened: StoragePort | None = None
    try:
        flags_after = restore_fail_closed(
            storage,
            reason="Interrupted controlled-live session recovery.",
            now=now,
        )
        expected_job_id = marker.get("expected_job_id") or marker.get("job_id")
        expected_request_id = marker.get("expected_request_id")
        if (
            not isinstance(expected_job_id, str)
            or not expected_job_id
            or not isinstance(expected_request_id, str)
            or not expected_request_id
        ):
            raise ControlledLiveError(
                "marker lacks the durable job/request ownership contract.",
                code="RECOVERY_MARKER_INCOMPLETE",
            )
        durable = storage.recover_controlled_live_session(
            expected_job_id=expected_job_id,
            expected_request_id=expected_request_id,
            now=now,
            clock=clock,
        )
        recovery.update(durable)
        reopened = _close_and_reopen(storage, storage_reopener)
        flags_after = confirm_flags(reopened)
        if not is_fail_closed(flags_after):
            raise ControlledLiveError(
                "reopened flags are not fail-closed.",
                code="RECOVERY_NOT_FAIL_CLOSED",
            )
        evidence = _execution_evidence(
            reopened,
            expected_job_id=expected_job_id,
            expected_request_id=expected_request_id,
        )
        recovery["durable_evidence"] = _report_evidence(evidence)
    except BaseException as exc:
        error = exc
    finally:
        if reopened is not None:
            try:
                reopened.close()  # type: ignore[attr-defined]
            except BaseException:
                pass
    if error is not None:
        payload = {
            "session_id": session_id,
            "timestamp": moment.isoformat(),
            "recovery": recovery,
            "flags_after": flags_after,
            "error": _safe_error(error, "RECOVERY_REQUIRED"),
            "operator_attention_required": True,
        }
        try:
            report_path = report_writer(reports_dir, session_id, payload)
        except BaseException:
            report_path = None
        return ControlledLiveOutcome(
            status="RECOVERY_REQUIRED",
            exit_code=3,
            session_id=session_id,
            report_path=report_path,
            flags_after=flags_after,
            recovery=recovery,
            detail=_OPERATOR_MESSAGES["RECOVERY_REQUIRED"],
        )

    payload = {
        "session_id": session_id,
        "timestamp": moment.isoformat(),
        "recovery": recovery,
        "flags_after": flags_after,
        "provider_request_started": recovery.get("provider_request_started"),
        "possible_unknown_provider_outcome": recovery.get(
            "possible_unknown_provider_outcome"
        ),
        "operator_attention_required": bool(
            recovery.get("reconciliation_required")
        ),
    }
    report_path, finalization_error = _write_then_clear_marker(
        reports_dir=reports_dir,
        runtime_dir=runtime_dir,
        session_id=session_id,
        payload=payload,
        final_status="RECOVERY_FORCED_FAIL_CLOSED",
        report_writer=report_writer,
        marker_clearer=marker_clearer,
    )
    if finalization_error is not None:
        return ControlledLiveOutcome(
            status=f"{finalization_error}_RECOVERY_REQUIRED",
            exit_code=5,
            session_id=session_id,
            report_path=report_path,
            flags_after=flags_after,
            recovery=recovery,
            detail=_OPERATOR_MESSAGES.get(
                finalization_error,
                _OPERATOR_MESSAGES["RECOVERY_REQUIRED"],
            ),
        )
    return ControlledLiveOutcome(
        status="RECOVERY_FORCED_FAIL_CLOSED",
        exit_code=3,
        session_id=session_id,
        report_path=report_path,
        flags_after=flags_after,
        recovery=recovery,
        detail="Prior session recovered locally; no provider retry was performed.",
    )


def run_controlled_live_once(
    request: ControlledLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    storage_reopener: Callable[[], StoragePort],
    project_root: Path,
    runtime_dir: Path,
    worker_runner: Callable[[ControlledWorkerContract], WorkerOnceResult],
    git_identity: Callable[[Path], tuple[str, str]] | None = None,
    db_fingerprint: Callable[[Path], DbFingerprint] = default_db_fingerprint,
    quiescence_probe: Callable[[], Mapping[str, tuple]] | None = None,
    pricing_profiles_path: Path | None = None,
    reports_dir: Path | None = None,
    clock: Clock | None = None,
    now: datetime | None = None,
    allow_execution: bool = False,
    allow_job_creation: bool = False,
    report_writer: Callable[
        [Path, str, Mapping[str, object]], Path
    ] = write_operator_report,
    marker_clearer: Callable[[Path], None] = clear_session_marker,
) -> ControlledLiveOutcome:
    """Run the sole controlled-live state machine; every exit is fail-closed."""
    clock = clock or SystemClock()
    moment = now if now is not None else clock.now()
    reports_dir = reports_dir or runtime_dir / "controlled_live_reports"
    if git_identity is None:
        from app.operations.stage1_migration import _git_identity

        git_identity = _git_identity
    if quiescence_probe is None:
        quiescence_probe = lambda: default_quiescence_probe(
            project_root, settings.db_path
        )

    existing_marker = read_session_marker(runtime_dir)
    if existing_marker is not None:
        return _recover_existing_session(
            marker=existing_marker,
            settings=settings,
            storage=storage,
            storage_reopener=storage_reopener,
            runtime_dir=runtime_dir,
            reports_dir=reports_dir,
            clock=clock,
            now=now,
            report_writer=report_writer,
            marker_clearer=marker_clearer,
        )
    if not allow_execution:
        session_id = uuid4().hex
        return ControlledLiveOutcome(
            status="REAL_EXECUTION_DISABLED",
            exit_code=2,
            session_id=session_id,
            flags_after=confirm_flags(storage),
            detail=_OPERATOR_MESSAGES["REAL_EXECUTION_DISABLED"],
        )

    contract_payload = controlled_session_contract(request.operation_key)
    contract = ControlledWorkerContract(**contract_payload)
    session_id = contract.session_id
    expected_job_id = contract.expected_job_id
    expected_request_id = contract.expected_request_id
    worker_execution_token = contract.worker_execution_token
    marker = {
        **contract.as_dict(),
        "status": "ACQUIRED",
        "opened_at": moment.isoformat(),
        "operator_attention_required": True,
    }
    if not acquire_session_marker(runtime_dir, marker):
        return ControlledLiveOutcome(
            status="SESSION_CONTENTION",
            exit_code=2,
            session_id=session_id,
            flags_after=confirm_flags(storage),
            detail="Another controlled-live session owns the marker.",
        )

    try:
        preflight = run_preflight(
            request,
            settings=settings,
            storage=storage,
            project_root=project_root,
            contract=contract,
            git_identity=git_identity,
            db_fingerprint=db_fingerprint,
            quiescence_probe=quiescence_probe,
            pricing_profiles_path=pricing_profiles_path,
            clock=clock,
            now=now,
            allow_job_creation=allow_job_creation,
        )
    except BaseException as exc:
        flags_after = confirm_flags(storage)
        payload = {
            "session_id": session_id,
            "timestamp": moment.isoformat(),
            "reason_code": "PREFLIGHT_FAILED",
            "error": _safe_error(exc, "PREFLIGHT_FAILED"),
            "flags_after": flags_after,
            "provider_request_started": False,
        }
        report_path, finalization_error = _write_then_clear_marker(
            reports_dir=reports_dir,
            runtime_dir=runtime_dir,
            session_id=session_id,
            payload=payload,
            final_status="PREFLIGHT_FAILED",
            report_writer=report_writer,
            marker_clearer=marker_clearer,
        )
        status = (
            f"{finalization_error}_RECOVERY_REQUIRED"
            if finalization_error
            else "PREFLIGHT_FAILED"
        )
        return ControlledLiveOutcome(
            status=status,
            exit_code=5 if finalization_error else 2,
            session_id=session_id,
            report_path=report_path,
            flags_after=flags_after,
            detail=_OPERATOR_MESSAGES[
                finalization_error or "PREFLIGHT_FAILED"
            ],
        )

    try:
        recheck = run_preflight(
            request,
            settings=settings,
            storage=storage,
            project_root=project_root,
            contract=contract,
            git_identity=git_identity,
            db_fingerprint=db_fingerprint,
            quiescence_probe=quiescence_probe,
            pricing_profiles_path=pricing_profiles_path,
            clock=clock,
            now=now,
            allow_job_creation=allow_job_creation,
        )
        if recheck.preflight_fingerprint != preflight.preflight_fingerprint:
            raise ControlledLiveError(
                "preflight fingerprint changed.",
                code="STALE_PREFLIGHT",
            )
    except BaseException as exc:
        flags_after = confirm_flags(storage)
        payload = {
            "session_id": session_id,
            "timestamp": moment.isoformat(),
            "reason_code": "STALE_PREFLIGHT",
            "error": _safe_error(exc, "STALE_PREFLIGHT"),
            "flags_after": flags_after,
            "provider_request_started": False,
        }
        report_path, finalization_error = _write_then_clear_marker(
            reports_dir=reports_dir,
            runtime_dir=runtime_dir,
            session_id=session_id,
            payload=payload,
            final_status="STALE_PREFLIGHT",
            report_writer=report_writer,
            marker_clearer=marker_clearer,
        )
        return ControlledLiveOutcome(
            status=(
                f"{finalization_error}_RECOVERY_REQUIRED"
                if finalization_error
                else "STALE_PREFLIGHT"
            ),
            exit_code=5 if finalization_error else 2,
            session_id=session_id,
            report_path=report_path,
            flags_after=flags_after,
            detail=_OPERATOR_MESSAGES[
                finalization_error or "STALE_PREFLIGHT"
            ],
        )

    plan = FrozenPlan(
        session_id=session_id,
        operation_key=request.operation_key,
        job_id=preflight.job.id,
        request_id=expected_request_id,
        attempt_no=1,
        worker_execution_token=worker_execution_token,
        execution_intent_fingerprint=preflight.execution_intent_fingerprint,
        model=preflight.intent.model,
        pricing_fingerprint=preflight.intent.pricing_fingerprint,
        pricing_profile_id=preflight.intent.pricing_profile_id,
        pricing_profile_version=preflight.intent.pricing_profile_version,
        pricing_currency=preflight.intent.pricing_currency,
        pricing_unit=preflight.intent.pricing_unit,
        pricing_profile=dict(preflight.intent.pricing_profile),
        max_tokens=preflight.intent.max_tokens,
        max_web_searches=preflight.intent.max_web_searches,
        projected_cost_usd=preflight.intent.projected_cost_usd,
        pessimistic_cost_usd=preflight.intent.pessimistic_cost_usd,
        cap_usd=preflight.intent.cap_usd,
        preflight_fingerprint=preflight.preflight_fingerprint,
        flags_before=preflight.flags_before,
        flags_during=dict(OPEN_PROFILE),
        flags_after=dict(FAIL_CLOSED_PROFILE),
    )
    write_session_marker(
        runtime_dir,
        {
            **marker,
            "status": "OPENING",
            "plan": plan.as_dict(),
        },
    )

    worker_result: WorkerOnceResult | None = None
    worker_error: BaseException | None = None
    restoration_error: BaseException | None = None
    reopen_error: BaseException | None = None
    validation_error: BaseException | None = None
    flags_during: dict[str, bool] = {}
    flags_after: dict[str, bool] = {}
    evidence: dict[str, object] | None = None
    post_execution_recovery: dict[str, object] | None = None
    reopened: StoragePort | None = None
    try:
        flags_during = open_minimal_profile(
            storage,
            reason=f"controlled-live session {session_id} open",
            now=now,
        )
        if flags_during != dict(OPEN_PROFILE):
            raise ControlledLiveError(
                "open profile mismatch.",
                code="OPEN_PROFILE_MISMATCH",
            )
        write_session_marker(
            runtime_dir,
            {
                **marker,
                "status": "WORKER_RUNNING",
                "plan": plan.as_dict(),
            },
        )
        worker_result = worker_runner(contract)
    except BaseException as exc:
        worker_error = exc
    finally:
        try:
            flags_after = restore_fail_closed(
                storage,
                reason=f"controlled-live session {session_id} restore",
                now=now,
            )
            if not is_fail_closed(flags_after):
                raise ControlledLiveError(
                    "restoration did not produce fail-closed flags.",
                    code="RESTORE_NOT_FAIL_CLOSED",
                )
        except BaseException as exc:
            restoration_error = exc
        if restoration_error is None:
            try:
                reopened = _close_and_reopen(storage, storage_reopener)
                flags_after = confirm_flags(reopened)
                evidence = _execution_evidence(
                    reopened,
                    expected_job_id=plan.job_id,
                    expected_request_id=plan.request_id,
                )
                active_attempt = next(
                    (
                        attempt
                        for attempt in evidence.get("attempts", [])
                        if isinstance(attempt, Mapping)
                        and attempt.get("status")
                        in ("RESERVED", "REQUEST_STARTED")
                    ),
                    None,
                )
                evidence_job = evidence.get("job")
                active_or_unowned_job = (
                    isinstance(evidence_job, Mapping)
                    and evidence_job.get("status")
                    in ("QUEUED", "LEASED", "RUNNING")
                )
                if active_attempt is not None or active_or_unowned_job:
                    post_execution_recovery = (
                        reopened.recover_controlled_live_session(
                            expected_job_id=plan.job_id,
                            expected_request_id=plan.request_id,
                            now=now,
                            clock=clock,
                        )
                    )
                    evidence = _execution_evidence(
                        reopened,
                        expected_job_id=plan.job_id,
                        expected_request_id=plan.request_id,
                    )
            except BaseException as exc:
                reopen_error = exc

    if restoration_error is None and reopen_error is None and reopened is not None:
        try:
            _validate_success_evidence(
                evidence=evidence or {},
                plan=plan,
                worker_result=worker_result,
                flags_after=flags_after,
            )
        except BaseException as exc:
            validation_error = exc
    if reopened is not None:
        try:
            reopened.close()  # type: ignore[attr-defined]
        except BaseException:
            pass

    if restoration_error is not None:
        candidate_status = "RESTORE_FAILED_RECOVERY_REQUIRED"
        exit_code = 4
        reason_code = "RESTORE_FAILED"
        error = restoration_error
    elif reopen_error is not None:
        candidate_status = "REOPEN_FAILED_RECOVERY_REQUIRED"
        exit_code = 4
        reason_code = "REOPEN_FAILED"
        error = reopen_error
    elif worker_error is not None:
        candidate_status = "WORKER_ERROR_FAIL_CLOSED"
        exit_code = 2
        reason_code = "WORKER_FAILED"
        error = worker_error
    elif validation_error is not None:
        candidate_status = "VALIDATION_FAILED_FAIL_CLOSED"
        exit_code = 2
        reason_code = "VALIDATION_FAILED"
        error = validation_error
    else:
        candidate_status = "COMPLETED_FAIL_CLOSED"
        exit_code = 0
        reason_code = "SUCCESS"
        error = None

    payload = {
        "session_id": session_id,
        "timestamp": moment.isoformat(),
        "plan": plan.as_dict(),
        "flags_before": preflight.flags_before,
        "flags_during": flags_during,
        "flags_after": flags_after,
        "worker_result": (
            None
            if worker_result is None
            else {
                "status": worker_result.status,
                "job_id": worker_result.job_id,
                "request_id": worker_result.request_id,
                "attempt_no": worker_result.attempt_no,
                "worker_execution_token_hash": (
                    _diagnostic_hash(worker_result.worker_execution_token)
                    if worker_result.worker_execution_token
                    else None
                ),
            }
        ),
        "durable_evidence": _report_evidence(evidence),
        "post_execution_recovery": post_execution_recovery,
        "reason_code": reason_code,
        "error": _safe_error(error, reason_code),
        "restoration_confirmed": restoration_error is None
        and is_fail_closed(flags_after),
        "reopen_confirmed": reopen_error is None,
        "operator_attention_required": exit_code != 0,
    }
    if restoration_error is not None or reopen_error is not None:
        retained = dict(payload)
        retained["final_status"] = candidate_status
        retained["marker_retained_for_recovery"] = True
        try:
            report_path = report_writer(reports_dir, session_id, retained)
            finalization_error = None
        except BaseException:
            report_path = None
            finalization_error = "REPORT_WRITE_FAILED"
    else:
        report_path, finalization_error = _write_then_clear_marker(
            reports_dir=reports_dir,
            runtime_dir=runtime_dir,
            session_id=session_id,
            payload=payload,
            final_status=candidate_status,
            report_writer=report_writer,
            marker_clearer=marker_clearer,
        )
    if finalization_error is not None:
        return ControlledLiveOutcome(
            status=f"{finalization_error}_RECOVERY_REQUIRED",
            exit_code=5,
            session_id=session_id,
            report_path=report_path,
            plan=plan,
            flags_after=flags_after,
            worker_result=worker_result,
            detail=_OPERATOR_MESSAGES[finalization_error],
        )
    return ControlledLiveOutcome(
        status=candidate_status,
        exit_code=exit_code,
        session_id=session_id,
        report_path=report_path,
        plan=plan,
        flags_after=flags_after,
        worker_result=worker_result,
        detail=(
            ""
            if exit_code == 0
            else _OPERATOR_MESSAGES.get(
                reason_code,
                "Controlled-live stopped fail-closed.",
            )
        ),
    )


class CanonicalControlledWorkerAdapter:
    """Map the canonical Worker result plus durable attempt identity to the wrapper."""

    def __init__(
        self,
        *,
        storage: StoragePort,
        worker_factory: Callable[[str], object],
    ) -> None:
        self._storage = storage
        self._worker_factory = worker_factory

    def __call__(self, contract: ControlledWorkerContract) -> WorkerOnceResult:
        worker = self._worker_factory(contract.worker_execution_token)
        result = worker.run_once()  # type: ignore[attr-defined]
        status_value = getattr(getattr(result, "status", None), "value", None)
        job_id = getattr(result, "job_id", None)
        conn = getattr(self._storage, "conn", None)
        attempt = None
        if conn is not None:
            attempt = conn.execute(
                "SELECT request_id,attempt_no FROM provider_attempts WHERE job_id=? "
                "ORDER BY attempt_no",
                (contract.expected_job_id,),
            ).fetchone()
        return WorkerOnceResult(
            status="SUCCEEDED" if status_value == "DONE" else str(status_value or "UNKNOWN"),
            job_id=job_id,
            request_id=None if attempt is None else str(attempt["request_id"]),
            attempt_no=None if attempt is None else int(attempt["attempt_no"]),
            worker_execution_token=contract.worker_execution_token,
        )


class DeterministicFakeControlledWorkerAdapter:
    """Offline fake worker for the subprocess composition-root test.

    It uses only storage methods and synthetic model usage. No SDK, network or
    provider client is imported or called.
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._clock = clock

    def __call__(self, contract: ControlledWorkerContract) -> WorkerOnceResult:
        lease = self._storage.claim_next_job(
            contract.worker_execution_token,
            60,
            clock=self._clock,
        )
        if lease is None:
            return WorkerOnceResult(
                "IDLE",
                worker_execution_token=contract.worker_execution_token,
            )
        if lease.job.id != contract.expected_job_id:
            return WorkerOnceResult(
                "FOREIGN_JOB",
                job_id=lease.job.id,
                worker_execution_token=contract.worker_execution_token,
            )
        job = lease.job
        self._storage.mark_job_running(
            job.id,
            contract.worker_execution_token,
            clock=self._clock,
        )
        run_id = f"controlled-fake-{uuid4().hex}"
        initialized = self._storage.initialize_research_run_for_job(
            job.id,
            contract.worker_execution_token,
            run_id,
            clock=self._clock,
        )
        execution = JobExecutionContext(
            job_id=job.id,
            lease_owner=contract.worker_execution_token,
            run_id=initialized.run.id,
            clock=self._clock,
        )
        intent = DurableResearchExecutionIntent.from_payload(
            canonicalize_durable_research_payload(job.payload)[
                "execution_intent"
            ]
        )
        attempt = self._storage.begin_provider_attempt(
            execution,
            stage=_ATTEMPT_STAGE,
            attempt_no=1,
            max_cost_usd=float(intent.cap_usd),
            daily_limit_usd=self._settings.max_daily_cost_usd,
            monthly_limit_usd=self._settings.max_monthly_cost_usd,
        )
        self._storage.mark_provider_attempt_request_started(
            execution,
            attempt.request_id,
        )
        usage = ModelUsage(
            run_id=execution.run_id,
            model=intent.model,
            task="research",
            input_tokens=1,
            output_tokens=1,
            web_search_requests=0,
            estimated_cost_usd=0.000001,
            dry_run=False,
            request_id=attempt.request_id,
        )
        self._storage.add_job_model_usage(execution, usage)
        card = ResearchCard(
            topic_id=int(job.topic_id),
            question="Synthetic offline controlled-live evidence.",
            working_thesis="The offline fake worker exercised the durable contract.",
            main_mechanism="Deterministic fake storage transitions.",
            confirmed_claims=["No network or provider SDK was used."],
            confidence_score=1.0,
            source_quality_score=1.0,
            publication_recommendation=ResearchRecommendation.PROCEED,
            sources=[
                Source(
                    url="https://example.invalid/offline-evidence",
                    title="Offline synthetic evidence",
                    source_type=SourceType.OTHER,
                    supports_claim="No network or provider SDK was used.",
                    verification_status=SourceVerification.VERIFIED,
                )
            ],
        )
        self._storage.finalize_job_research_execution(
            execution,
            card,
            usage.estimated_cost_usd,
            terminal_run_status=RunStatus.SUCCESS,
        )
        return WorkerOnceResult(
            status="SUCCEEDED",
            job_id=job.id,
            request_id=attempt.request_id,
            attempt_no=attempt.attempt_no,
            worker_execution_token=contract.worker_execution_token,
        )
