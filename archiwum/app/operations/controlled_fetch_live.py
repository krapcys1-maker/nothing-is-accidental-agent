"""controlled-fetch-live-once: kanoniczny jednorazowy executor DOKŁADNIE jednego
zatwierdzonego joba CONTROLLED_FETCH.

Command otwiera minimalny profil bezpieczeństwa WYŁĄCZNIE procesowo (bez edycji
YAML/.env/flag produkcyjnych), wykonuje wskazany job przez istniejący dispatcher
i runner, i ZAWSZE przywraca fail-closed w bloku ``finally``. Realny transport
jest aktywowany procesowo przez ``replace(settings, controlled_fetch_real_enabled
=True)`` przekazany tylko do dispatchera tej jednej egzekucji — nic nie jest
zapisywane do konfiguracji i nie przeżywa procesu.

Trwałą i JEDYNĄ zgodą na wykonanie pozostaje jednorazowy approval L1
CONTROLLED_FETCH w SQLite; ten wrapper NIE tworzy joba ani approvalu, nie
redefiniuje URL-a/timeoutu/max bytes/redirectów (pochodzą z zamrożonego intentu)
i nie dotyka architektury evidence research ani providera modelowego.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from app.core.clock import Clock
from app.core.config import Settings
from app.models import JobKind, JobStatus, WorkflowType
from app.operations.controlled_live import (
    DbFingerprint,
    confirm_flags,
    default_db_fingerprint,
    is_fail_closed,
    restore_fail_closed,
)
from app.operations.stage1_migration import _git_identity
from app.ports.storage import StoragePort
from app.research.controlled_fetch_intent import (
    CONTROLLED_FETCH_EXECUTION,
    ControlledFetchIntent,
    ControlledFetchIntentError,
    canonicalize_controlled_fetch_payload,
)

# Minimalny profil otwarcia dla BEZKOSZTOWEGO controlled fetch: włącza wyłącznie
# workera i zdejmuje kill_switch/safe_mode. paid_actions_enabled celowo pozostaje
# False (Policy Engine nie wymaga go dla controlled fetch — patrz
# app/policies/policy_engine.py check_worker_runtime). Profil musi wymieniać
# wszystkie pięć flag, a kill_switch jest zapisywany OSTATNI dla otwarcia.
FETCH_OPEN_PROFILE_ORDER: list[tuple[str, bool]] = [
    ("safe_mode", False),
    ("worker_enabled", True),
    ("paid_actions_enabled", False),
    ("browser_actions_enabled", False),
    ("kill_switch", False),
]
CONTROLLED_FETCH_ACTION_TYPE = "CONTROLLED_FETCH"
_UPDATED_BY = "controlled-fetch-live-once"
_LEASE_SECONDS = 60


@dataclass(frozen=True)
class ControlledFetchLiveRequest:
    job_id: str
    account_id: str
    expected_db_sha256: str
    expected_schema: str
    expected_branch: str
    expected_head: str


@dataclass(frozen=True)
class ControlledFetchLiveOutcome:
    status: str  # SUCCEEDED | FAILED | NEEDS_VERIFICATION | BLOCKED
    exit_code: int
    reason_code: str
    retrieval_id: int | None = None
    worker_status: str | None = None
    flags_after: dict[str, bool] = field(default_factory=dict)
    detail: str = ""


class ControlledFetchLiveError(RuntimeError):
    def __init__(self, detail: str, *, code: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _forbidden_research(*_args: object, **_kwargs: object):
    """Defence-in-depth: this wrapper never dispatches model research."""
    raise ControlledFetchLiveError(
        "controlled-fetch-live-once never dispatches model research.",
        code="MODEL_RESEARCH_FORBIDDEN",
    )


def _parse_persisted_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlledFetchLiveError(
            "approval expiry is unparseable.", code="APPROVAL_EXPIRY_INVALID",
        ) from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _verify_binding(
    storage: StoragePort, request: ControlledFetchLiveRequest, moment: datetime,
) -> str | None:
    """Read-only pre-gate: every inconsistency is refused BEFORE any flag opens."""
    job = storage.get_job(request.job_id)
    if job is None:
        return "JOB_MISSING"
    if job.kind is not JobKind.RESEARCH or job.workflow is not WorkflowType.RESEARCH:
        return "JOB_TYPE_INVALID"
    if job.payload.get("execution") != CONTROLLED_FETCH_EXECUTION:
        return "JOB_NOT_CONTROLLED_FETCH"
    if job.account_id != request.account_id:
        return "JOB_ACCOUNT_MISMATCH"
    if job.status is not JobStatus.QUEUED:
        return "JOB_NOT_EXECUTABLE"
    try:
        payload = canonicalize_controlled_fetch_payload(job.payload)
        intent = ControlledFetchIntent.from_payload(payload["execution_intent"])
    except ControlledFetchIntentError:
        return "INTENT_INVALID"
    if intent.account_id != request.account_id:
        return "INTENT_ACCOUNT_MISMATCH"
    if intent.topic_id != job.topic_id:
        return "TOPIC_MISMATCH"
    if moment >= intent.expires_at_datetime():
        return "INTENT_EXPIRED"

    approval = storage.get_controlled_fetch_approval_for_job(request.job_id)
    if approval is None:
        return "APPROVAL_MISSING"
    if approval.action_type != CONTROLLED_FETCH_ACTION_TYPE:
        return "APPROVAL_TYPE_INVALID"
    if approval.account_id != request.account_id:
        return "APPROVAL_ACCOUNT_MISMATCH"
    if approval.consumed_at is not None:
        return "APPROVAL_ALREADY_CONSUMED"
    if approval.intent_fingerprint != intent.fingerprint:
        return "APPROVAL_FINGERPRINT_MISMATCH"
    if approval.requested_url != intent.requested_url:
        return "APPROVAL_URL_MISMATCH"
    if moment >= _parse_persisted_ts(approval.expires_at):
        return "APPROVAL_EXPIRED"

    if storage.get_controlled_fetch_attempt_for_job(request.job_id) is not None:
        return "ATTEMPT_ALREADY_EXISTS"
    return None


def _no_other_active_work(storage: StoragePort, job_id: str) -> str | None:
    """Refuse if any other lease/worker is active; the target stays the only job."""
    conn = getattr(storage, "conn", None)
    if conn is None:  # pragma: no cover - defensive; SqliteStorage always exposes conn
        return None
    other_active = conn.execute(
        "SELECT count(*) FROM jobs WHERE status IN ('LEASED','RUNNING') AND id != ?",
        (job_id,),
    ).fetchone()[0]
    if other_active:
        return "OTHER_ACTIVE_JOB"
    return None


def _blocked(
    reason_code: str, storage: StoragePort, *, detail: str = "",
) -> ControlledFetchLiveOutcome:
    try:
        flags = confirm_flags(storage)
    except Exception:  # noqa: BLE001 - report is best-effort only
        flags = {}
    return ControlledFetchLiveOutcome(
        status="BLOCKED", exit_code=2, reason_code=reason_code,
        flags_after=flags, detail=detail or reason_code,
    )


def _default_worker(
    request: ControlledFetchLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    clock: Clock,
    fetch_port_factory,
):
    from dataclasses import replace

    from app.policies.policy_engine import PolicyEngine
    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker
    from app.storage.repositories import SqliteStorage
    from app.workflows.research.controlled_fetch import run_controlled_fetch

    # PROCESS-LOCAL real transport capability: only this dispatcher's settings copy
    # carries controlled_fetch_real_enabled=True. Nothing is persisted; the global
    # YAML emergency gate and every later process stay at their durable default.
    dispatch_settings = replace(settings, controlled_fetch_real_enabled=True)
    policy = PolicyEngine(dispatch_settings, storage, clock)

    if fetch_port_factory is None:
        controlled_fetch_runner = run_controlled_fetch
    else:
        def controlled_fetch_runner(account, topic, *, settings, storage, policy,
                                    clock, job_execution, intent):
            return run_controlled_fetch(
                account, topic, settings=settings, storage=storage, policy=policy,
                clock=clock, job_execution=job_execution, intent=intent,
                fetch_port_factory=fetch_port_factory,
            )

    dispatcher = JobDispatcher(
        settings=dispatch_settings, storage=storage, policy=policy, clock=clock,
        research_dry_run=_forbidden_research, research_real=_forbidden_research,
        research_controlled_fetch=controlled_fetch_runner,
        allow_real_research=True,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner=f"controlled-fetch-live-once:{request.job_id}",
        target_job_id=request.job_id, lease_seconds=_LEASE_SECONDS,
        heartbeat_interval_seconds=20.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
    )


def _map_outcome(
    worker_result: object,
    storage: StoragePort,
    request: ControlledFetchLiveRequest,
    flags_after: dict[str, bool],
) -> ControlledFetchLiveOutcome:
    status_value = getattr(getattr(worker_result, "status", None), "value", None)
    if status_value == "DONE":
        attempt = storage.get_controlled_fetch_attempt_for_job(request.job_id)
        retrieval_id = None if attempt is None else attempt.retrieval_id
        return ControlledFetchLiveOutcome(
            status="SUCCEEDED", exit_code=0, reason_code="SUCCEEDED",
            retrieval_id=retrieval_id, worker_status=status_value,
            flags_after=flags_after,
        )
    if status_value == "NEEDS_VERIFICATION":
        return ControlledFetchLiveOutcome(
            status="NEEDS_VERIFICATION", exit_code=3,
            reason_code="NEEDS_VERIFICATION", worker_status=status_value,
            flags_after=flags_after,
            detail="Controlled fetch outcome is uncertain; reconcile before retry.",
        )
    return ControlledFetchLiveOutcome(
        status="FAILED", exit_code=2,
        reason_code=f"WORKER_{status_value or 'UNKNOWN'}",
        worker_status=status_value, flags_after=flags_after,
    )


def run_controlled_fetch_live_once(
    request: ControlledFetchLiveRequest,
    *,
    settings: Settings,
    storage: StoragePort,
    project_root: Path,
    clock: Clock,
    git_identity: Callable[[Path], tuple[str, str]] = _git_identity,
    db_fingerprint: Callable[[Path], DbFingerprint] = default_db_fingerprint,
    fetch_port_factory=None,
    worker_factory: Callable[[ControlledFetchLiveRequest], object] | None = None,
    now: datetime | None = None,
) -> ControlledFetchLiveOutcome:
    """Execute exactly one approved CONTROLLED_FETCH job, always restoring fail-closed."""
    moment = now if now is not None else clock.now()

    # 1. Environment guards (read-only), refused before any flag opens.
    try:
        branch, head = git_identity(project_root)
    except Exception:  # noqa: BLE001 - a failed probe is a controlled fail-closed stop
        return _blocked("GIT_PROBE_FAILED", storage)
    if branch != request.expected_branch:
        return _blocked("BRANCH_MISMATCH", storage)
    if head != request.expected_head:
        return _blocked("HEAD_MISMATCH", storage)
    fingerprint = db_fingerprint(settings.db_path)
    if fingerprint.sha256.upper() != request.expected_db_sha256.upper():
        return _blocked("DB_SHA_MISMATCH", storage)
    if not fingerprint.schema_tail.startswith(request.expected_schema):
        return _blocked("SCHEMA_MISMATCH", storage)

    # 2. Job + approval binding and 3. no other active work (both read-only).
    binding = _verify_binding(storage, request, moment)
    if binding is not None:
        return _blocked(binding, storage)
    active = _no_other_active_work(storage, request.job_id)
    if active is not None:
        return _blocked(active, storage)

    # 4. Baseline must already be fail-closed before we open anything.
    try:
        baseline = confirm_flags(storage)
    except Exception:  # noqa: BLE001 - unreadable flags are not a safe baseline
        return _blocked("FLAGS_UNREADABLE", storage)
    if not is_fail_closed(baseline):
        return _blocked("NOT_FAIL_CLOSED_BASELINE", storage)

    # 5. Open the minimal profile, execute exactly one job, always restore.
    worker_result: object | None = None
    execute_error: BaseException | None = None
    try:
        storage.apply_security_flag_profile(
            FETCH_OPEN_PROFILE_ORDER, updated_by=_UPDATED_BY,
            reason=f"controlled-fetch-live-once {request.job_id}", now=moment,
        )
        worker = (
            worker_factory(request)
            if worker_factory is not None
            else _default_worker(
                request, settings=settings, storage=storage, clock=clock,
                fetch_port_factory=fetch_port_factory,
            )
        )
        worker_result = worker.run_once()
    except BaseException as exc:  # noqa: BLE001 - restoration must run for every path
        execute_error = exc
    finally:
        flags_after = restore_fail_closed(
            storage,
            reason=f"controlled-fetch-live-once {request.job_id} restore",
            now=moment,
        )

    # 6. Confirm the durable state is fail-closed again.
    if not is_fail_closed(flags_after):
        return ControlledFetchLiveOutcome(
            status="BLOCKED", exit_code=2, reason_code="RESTORE_FAILED",
            flags_after=flags_after,
            detail="Security profile did not return to fail-closed.",
        )
    if execute_error is not None:
        return ControlledFetchLiveOutcome(
            status="FAILED", exit_code=2, reason_code="EXECUTION_ERROR",
            flags_after=flags_after, detail=str(execute_error)[:240],
        )

    # 7. Map the canonical worker terminalization to the operator outcome.
    return _map_outcome(worker_result, storage, request, flags_after)
