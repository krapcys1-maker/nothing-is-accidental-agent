"""One-process durable worker using the queue's existing atomic lifecycle helpers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ResearchExecutionFailureOutcome,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import LifecycleTransitionError, StaleJobExecutionError, StoragePort
from app.scheduler.dispatcher import (
    DispatchContractError,
    DispatchError,
    DispatchResult,
    TerminalizationMode,
    UncertainExternalEffectError,
)
from app.scheduler.heartbeat import (
    EventHeartbeatWaiter,
    HeartbeatGuard,
    HeartbeatStorage,
    HeartbeatWaiter,
    ReadyWaiter,
    ThreadJoiner,
    _join_thread,
    _wait_for_ready,
)


def _is_topic_generation(job: Job) -> bool:
    """One predicate for the durable, paid, topic-free workflow."""
    return (
        job.kind is JobKind.TOPIC_GENERATION
        and job.workflow is WorkflowType.TOPIC_GENERATION
    )


class WorkerIterationStatus(str, Enum):
    IDLE = "IDLE"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    FAILED = "FAILED"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    LOST_LEASE = "LOST_LEASE"


@dataclass(frozen=True)
class WorkerIterationResult:
    status: WorkerIterationStatus
    job_id: str | None = None
    detail: str | None = None


class Dispatcher(Protocol):
    def dispatch(
        self, job: Job, *, lease_owner: str, heartbeat: Callable[[], None],
    ) -> DispatchResult: ...


class Worker:
    """Runs at most one claimed job per `run_once` call.

    The worker does not recover expired leases itself.  Recovery is an explicit
    storage operation today; the one-shot run reaper is a separate CLI command,
    not an automatic worker action.  During an active dispatch, a dedicated guard
    renews the job lease through a separately opened storage connection.
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        policy: PolicyEngine,
        dispatcher: Dispatcher,
        lease_owner: str,
        target_job_id: str | None = None,
        lease_seconds: int = 60,
        heartbeat_interval_seconds: float,
        heartbeat_startup_timeout_seconds: float,
        heartbeat_shutdown_timeout_seconds: float,
        heartbeat_storage_factory: Callable[[], HeartbeatStorage],
        heartbeat_waiter_factory: Callable[[], HeartbeatWaiter] = EventHeartbeatWaiter,
        heartbeat_ready_waiter: ReadyWaiter = _wait_for_ready,
        heartbeat_thread_joiner: ThreadJoiner = _join_thread,
        clock: Clock | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not lease_owner.strip() or lease_seconds <= 0:
            raise ValueError("lease_owner must be non-empty and lease_seconds must be positive.")
        if not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be finite and positive.")
        if heartbeat_interval_seconds >= lease_seconds:
            raise ValueError("heartbeat_interval_seconds must be shorter than lease_seconds.")
        for name, value in (
            ("heartbeat_startup_timeout_seconds", heartbeat_startup_timeout_seconds),
            ("heartbeat_shutdown_timeout_seconds", heartbeat_shutdown_timeout_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")
        self._storage = storage
        self._policy = policy
        self._dispatcher = dispatcher
        self._lease_owner = lease_owner
        self._target_job_id = target_job_id
        self._lease_seconds = lease_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_startup_timeout_seconds = heartbeat_startup_timeout_seconds
        self._heartbeat_shutdown_timeout_seconds = heartbeat_shutdown_timeout_seconds
        self._heartbeat_storage_factory = heartbeat_storage_factory
        self._heartbeat_waiter_factory = heartbeat_waiter_factory
        self._heartbeat_ready_waiter = heartbeat_ready_waiter
        self._heartbeat_thread_joiner = heartbeat_thread_joiner
        self._clock = clock or SystemClock()
        self._sleeper = sleeper

    def run_once(self) -> WorkerIterationResult:
        runtime = self._policy.check_worker_runtime()
        if not runtime.allowed:
            return WorkerIterationResult(WorkerIterationStatus.BLOCKED, detail=runtime.code)

        if self._target_job_id is None:
            lease = self._storage.claim_next_job(
                self._lease_owner, self._lease_seconds, clock=self._clock,
            )
        else:
            # One-shot single-job composition root: lease ONLY the named job so a
            # concurrently queued job can never be claimed or run by this worker.
            lease = self._storage.claim_specific_job(
                self._target_job_id, self._lease_owner, self._lease_seconds,
                clock=self._clock,
            )
        if lease is None:
            return WorkerIterationResult(WorkerIterationStatus.IDLE)
        job = lease.job

        # Flags are read once before claim and again after it.  This closes the
        # interval in which an operator could have disabled the worker.
        runtime = self._policy.check_worker_runtime()
        if not runtime.allowed:
            if job.kind is JobKind.CONTENT:
                # Generic job failure is forbidden for CONTENT. The untouched
                # leased job is recoverable after expiry under its C1 boundary.
                return WorkerIterationResult(
                    WorkerIterationStatus.LOST_LEASE, job.id,
                    f"Policy denied after claim: {runtime.code}",
                )
            return self._fail(job, f"Policy denied: {runtime.code}")

        # CONTENT is a targeted, offline-only composition root. C1 deliberately
        # forbids generic start/heartbeat/terminal mutators for this job class;
        # the C2 storage boundary initializes it with a generation fence and
        # owns the complete terminal transaction inside the bounded lease.
        if job.kind is JobKind.CONTENT:
            try:
                result = self._dispatcher.dispatch(
                    job, lease_owner=self._lease_owner, heartbeat=lambda: None,
                )
                terminalization = self._dispatch_terminalization(result)
                if terminalization is TerminalizationMode.WORKFLOW_TERMINALIZED:
                    return WorkerIterationResult(
                        WorkerIterationStatus.DONE, job.id, result.detail,
                    )
                if terminalization is TerminalizationMode.WORKFLOW_FAILED:
                    return WorkerIterationResult(
                        WorkerIterationStatus.FAILED, job.id, result.detail,
                    )
                raise DispatchContractError(
                    "CONTENT dispatcher must own its terminal transition."
                )
            except (LifecycleTransitionError, StaleJobExecutionError):
                return self._lost_lease(job)
            except DispatchContractError:
                raise
            except Exception as exc:
                # The generic failure path is intentionally unavailable for
                # CONTENT. Leave the lease for explicit fenced recovery.
                return WorkerIterationResult(
                    WorkerIterationStatus.LOST_LEASE,
                    job.id,
                    str(exc).replace("\n", " ")[:240],
                )

        guard: HeartbeatGuard | None = None
        try:
            self._storage.mark_job_running(job.id, self._lease_owner, clock=self._clock)
            self._heartbeat(job.id)
            guard = HeartbeatGuard(
                job_id=job.id,
                lease_owner=self._lease_owner,
                lease_seconds=self._lease_seconds,
                interval_seconds=self._heartbeat_interval_seconds,
                startup_timeout_seconds=self._heartbeat_startup_timeout_seconds,
                shutdown_timeout_seconds=self._heartbeat_shutdown_timeout_seconds,
                storage_factory=self._heartbeat_storage_factory,
                clock=self._clock,
                waiter=self._heartbeat_waiter_factory(),
                ready_waiter=self._heartbeat_ready_waiter,
                thread_joiner=self._heartbeat_thread_joiner,
            )
            guard.start()
            if guard.lost_lease is not None:
                return self._lost_lease(job)
            if guard.failure is not None:
                return self._heartbeat_guard_failure(job, guard)

            dispatch_error: Exception | None = None
            dispatch_result: object | None = None
            try:
                dispatch_result = self._dispatcher.dispatch(
                    job,
                    lease_owner=self._lease_owner,
                    heartbeat=lambda: self._dispatcher_heartbeat(job.id, guard),
                )
            except Exception as exc:
                dispatch_error = exc
            finally:
                guard.stop()

            if isinstance(dispatch_error, DispatchContractError):
                raise dispatch_error

            if dispatch_error is None:
                terminalization = self._dispatch_terminalization(dispatch_result)

                # A workflow that committed its own terminal transaction owns the
                # canonical outcome. Guard cleanup can observe the now-cleared lease,
                # but it must never overwrite that durable result.
                if terminalization is TerminalizationMode.WORKFLOW_TERMINALIZED:
                    assert isinstance(dispatch_result, DispatchResult)
                    return WorkerIterationResult(
                        WorkerIterationStatus.DONE, job.id, dispatch_result.detail,
                    )
                if terminalization is TerminalizationMode.WORKFLOW_FAILED:
                    assert isinstance(dispatch_result, DispatchResult)
                    return WorkerIterationResult(
                        WorkerIterationStatus.FAILED, job.id, dispatch_result.detail,
                    )
                if terminalization is not TerminalizationMode.WORKER_MUST_COMPLETE:
                    raise DispatchContractError(
                        f"Unsupported dispatch terminalization mode: {terminalization!r}."
                    )

            # Lost lease wins over every non-terminal dispatcher exception: the
            # original worker no longer owns the right to record any result.
            if guard.lost_lease is not None:
                return self._lost_lease(job)
            if guard.failure is not None:
                return self._heartbeat_guard_failure(job, guard)
            if dispatch_error is not None:
                return self._dispatch_failure(job, dispatch_error)

            # Only the explicit local/non-research ownership mode reaches generic
            # worker finalization.  Every workflow-owned terminal mode returned above.
            self._heartbeat(job.id)
            self._storage.complete_job(job.id, self._lease_owner, clock=self._clock)
            return WorkerIterationResult(WorkerIterationStatus.DONE, job.id)
        except DispatchContractError:
            raise
        except LifecycleTransitionError:
            return self._lost_lease(job)
        except Exception:
            if guard is not None and guard.lost_lease is not None:
                return self._lost_lease(job)
            if guard is not None and guard.failure is not None:
                return self._heartbeat_guard_failure(job, guard)
            return self._fail_unexpected_research_pipeline(
                job, "Worker execution failed before a confirmed external effect.",
            )
        finally:
            if guard is not None:
                guard.stop()

    def run_forever(
        self,
        *,
        poll_seconds: float,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive.")
        stopped = should_stop or (lambda: False)
        while not stopped():
            result = self.run_once()
            if stopped():
                break
            if result.status in {WorkerIterationStatus.IDLE, WorkerIterationStatus.BLOCKED}:
                self._sleeper(poll_seconds)

    def _heartbeat(self, job_id: str) -> None:
        self._storage.heartbeat_job_lease(
            job_id, self._lease_owner, self._lease_seconds, clock=self._clock,
        )

    def _dispatcher_heartbeat(self, job_id: str, guard: HeartbeatGuard) -> None:
        try:
            self._heartbeat(job_id)
        except LifecycleTransitionError as exc:
            guard.record_lost_lease(exc)
            raise

    @staticmethod
    def _dispatch_terminalization(result: object | None) -> TerminalizationMode:
        if not isinstance(result, DispatchResult):
            raise DispatchContractError("Dispatcher did not return a DispatchResult.")
        if not isinstance(result.terminalization, TerminalizationMode):
            raise DispatchContractError(
                "Dispatcher returned a DispatchResult with an invalid terminalization mode."
            )
        return result.terminalization

    def _dispatch_failure(self, job: Job, error: Exception) -> WorkerIterationResult:
        if isinstance(error, StaleJobExecutionError):
            return self._lost_lease(job)
        if isinstance(error, UncertainExternalEffectError):
            return self._needs_verification(job, "External effect outcome is uncertain.")
        if isinstance(error, LifecycleTransitionError):
            return self._lost_lease(job)
        if isinstance(error, DispatchError):
            return self._fail_unexpected_research_pipeline(
                job, self._safe_dispatch_error(error),
            )
        return self._fail_unexpected_research_pipeline(job)

    def _fail_unexpected_research_pipeline(
        self, job: Job, error: str = "UNEXPECTED_RESEARCH_PIPELINE_EXCEPTION",
    ) -> WorkerIterationResult:
        """Delegate every attached research failure decision to one storage transaction."""
        current = self._storage.get_job(job.id)
        if current is not None and current.run_id is not None and _is_topic_generation(
            current
        ):
            return self._fail_topic_generation_boundary(current, error)
        if (
            current is None
            or current.run_id is None
            or current.kind is not JobKind.RESEARCH
            or current.workflow is not WorkflowType.RESEARCH
        ):
            return self._fail(job, error)
        if current.payload.get("execution") == "controlled_fetch_v1":
            return self._fail_controlled_fetch_boundary(current, error)
        execution = JobExecutionContext(
            job_id=current.id,
            lease_owner=self._lease_owner,
            run_id=current.run_id,
            clock=self._clock,
        )
        try:
            outcome = self._storage.fail_or_escalate_job_research_execution(
                execution,
                None,
                error,
                terminalize_job=True,
            )
        except (LifecycleTransitionError, StaleJobExecutionError):
            return self._lost_lease(job)
        except Exception:
            # The failure boundary itself is unavailable; do not fall back to a
            # standalone job failure that could orphan the initialized run.
            return self._lost_lease(job)
        if outcome in {
            ResearchExecutionFailureOutcome.ESCALATED_RESERVED,
            ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED,
            ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION,
        }:
            return WorkerIterationResult(
                WorkerIterationStatus.NEEDS_VERIFICATION, job.id, error,
            )
        if outcome is ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED:
            durable = self._storage.get_job(job.id)
            status = (
                WorkerIterationStatus.DONE
                if durable is not None and durable.status is JobStatus.DONE
                else WorkerIterationStatus.FAILED
            )
            return WorkerIterationResult(status, job.id, error)
        return WorkerIterationResult(WorkerIterationStatus.FAILED, job.id, error)

    def _fail_topic_generation_boundary(
        self, current: Job, error: str, *, preserve_for_verification: bool = False,
    ) -> WorkerIterationResult:
        """Route an escaped topic-generation failure through its storage boundary.

        A TOPIC_GENERATION job whose attempt already crossed REQUEST_STARTED can
        only be escalated for review here — it is never requeued and never gains
        a second provider attempt.
        """
        assert current.run_id is not None
        execution = JobExecutionContext(
            job_id=current.id,
            lease_owner=self._lease_owner,
            run_id=current.run_id,
            clock=self._clock,
        )
        try:
            outcome = self._storage.fail_or_escalate_topic_generation_execution(
                execution,
                None,
                error,
                terminalize_job=not preserve_for_verification,
                preserve_for_verification=preserve_for_verification,
            )
        except (LifecycleTransitionError, StaleJobExecutionError):
            return self._lost_lease(current)
        except Exception:
            # The failure boundary itself is unavailable; never invent a
            # standalone terminal outcome around a possibly live attempt.
            return self._lost_lease(current)
        if outcome in {
            ResearchExecutionFailureOutcome.ESCALATED_RESERVED,
            ResearchExecutionFailureOutcome.ESCALATED_REQUEST_STARTED,
            ResearchExecutionFailureOutcome.ALREADY_NEEDS_RECONCILIATION,
            ResearchExecutionFailureOutcome.PRESERVED_NEEDS_VERIFICATION,
        }:
            return WorkerIterationResult(
                WorkerIterationStatus.NEEDS_VERIFICATION, current.id, error,
            )
        if outcome is ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED:
            durable = self._storage.get_job(current.id)
            status = (
                WorkerIterationStatus.DONE
                if durable is not None and durable.status is JobStatus.DONE
                else WorkerIterationStatus.FAILED
            )
            return WorkerIterationResult(status, current.id, error)
        return WorkerIterationResult(WorkerIterationStatus.FAILED, current.id, error)

    def _fail_controlled_fetch_boundary(
        self, current: Job, error: str,
    ) -> WorkerIterationResult:
        """Route an escaped controlled fetch failure through its storage boundary."""
        from app.models import ControlledFetchFailureOutcome

        execution = JobExecutionContext(
            job_id=current.id,
            lease_owner=self._lease_owner,
            run_id=current.run_id,
            clock=self._clock,
        )
        try:
            outcome = self._storage.fail_controlled_fetch_execution(execution, error)
        except (LifecycleTransitionError, StaleJobExecutionError):
            return self._lost_lease(current)
        except Exception:
            # The failure boundary itself is unavailable; never invent a
            # standalone terminal outcome around a possibly live attempt.
            return self._lost_lease(current)
        if outcome is ControlledFetchFailureOutcome.ESCALATED_NEEDS_VERIFICATION:
            return WorkerIterationResult(
                WorkerIterationStatus.NEEDS_VERIFICATION, current.id, error,
            )
        if outcome is ControlledFetchFailureOutcome.ALREADY_TERMINALIZED:
            durable = self._storage.get_job(current.id)
            status = (
                WorkerIterationStatus.DONE
                if durable is not None and durable.status is JobStatus.DONE
                else WorkerIterationStatus.FAILED
            )
            return WorkerIterationResult(status, current.id, error)
        return WorkerIterationResult(WorkerIterationStatus.FAILED, current.id, error)

    @staticmethod
    def _lost_lease(job: Job) -> WorkerIterationResult:
        return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)

    def _heartbeat_guard_failure(
        self, job: Job, guard: HeartbeatGuard,
    ) -> WorkerIterationResult:
        # A guard infrastructure failure is not proof that the lease was lost.
        # If research already has a run/attempt, the same centralized storage
        # boundary must inspect it before any terminal outcome is chosen.
        current = self._storage.get_job(job.id)
        if (
            current is None
            or current.run_id is None
            or (
                not _is_topic_generation(current)
                and (
                    current.kind is not JobKind.RESEARCH
                    or current.workflow is not WorkflowType.RESEARCH
                )
            )
        ):
            return WorkerIterationResult(
                WorkerIterationStatus.LOST_LEASE,
                job.id,
                guard.failure_code or "HEARTBEAT_GUARD_FAILURE",
            )
        return self._fail_unexpected_research_pipeline(
            job, guard.failure_code or "HEARTBEAT_GUARD_FAILURE",
        )

    @staticmethod
    def _safe_dispatch_error(exc: DispatchError) -> str:
        # All dispatcher messages are controlled strings.  Keep the persisted
        # audit compact even if a future subclass accidentally creates a long one.
        return str(exc).replace("\n", " ")[:240]

    def _fail(self, job: Job, error: str) -> WorkerIterationResult:
        try:
            self._storage.fail_job(job.id, self._lease_owner, error, clock=self._clock)
        except LifecycleTransitionError:
            return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
        return WorkerIterationResult(WorkerIterationStatus.FAILED, job.id, error)

    def _needs_verification(self, job: Job, error: str) -> WorkerIterationResult:
        current = self._storage.get_job(job.id)
        # A workflow that already escalated durably (e.g. controlled fetch)
        # cleared the lease and owns the canonical NEEDS_VERIFICATION outcome;
        # the worker must report it, never re-derive it.
        if current is not None and current.status is JobStatus.NEEDS_VERIFICATION:
            return WorkerIterationResult(
                WorkerIterationStatus.NEEDS_VERIFICATION, job.id, error,
            )
        if (
            current is not None
            and current.run_id is not None
            and _is_topic_generation(current)
        ):
            return self._fail_topic_generation_boundary(
                current, error, preserve_for_verification=True,
            )
        if (
            current is not None
            and current.run_id is not None
            and current.kind is JobKind.RESEARCH
            and current.workflow is WorkflowType.RESEARCH
        ):
            execution = JobExecutionContext(
                job_id=current.id,
                lease_owner=self._lease_owner,
                run_id=current.run_id,
                clock=self._clock,
            )
            try:
                outcome = self._storage.fail_or_escalate_job_research_execution(
                    execution,
                    None,
                    error,
                    preserve_for_verification=True,
                )
            except (LifecycleTransitionError, StaleJobExecutionError):
                return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
            except Exception:
                return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
            if outcome is ResearchExecutionFailureOutcome.ALREADY_TERMINALIZED:
                durable = self._storage.get_job(job.id)
                status = (
                    WorkerIterationStatus.DONE
                    if durable is not None and durable.status is JobStatus.DONE
                    else WorkerIterationStatus.FAILED
                )
                return WorkerIterationResult(status, job.id, error)
            return WorkerIterationResult(
                WorkerIterationStatus.NEEDS_VERIFICATION, job.id, error,
            )
        try:
            self._storage.mark_job_needs_verification(
                job.id, self._lease_owner, error, clock=self._clock,
            )
        except LifecycleTransitionError:
            return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
        return WorkerIterationResult(WorkerIterationStatus.NEEDS_VERIFICATION, job.id, error)
