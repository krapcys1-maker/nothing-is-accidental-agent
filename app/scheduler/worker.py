"""One-process durable worker using the queue's existing atomic lifecycle helpers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.models import Job
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import LifecycleTransitionError, StoragePort
from app.scheduler.dispatcher import (
    DispatchError,
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
    ) -> object: ...


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

        lease = self._storage.claim_next_job(
            self._lease_owner, self._lease_seconds, now=self._clock.now(),
        )
        if lease is None:
            return WorkerIterationResult(WorkerIterationStatus.IDLE)
        job = lease.job

        # Flags are read once before claim and again after it.  This closes the
        # interval in which an operator could have disabled the worker.
        runtime = self._policy.check_worker_runtime()
        if not runtime.allowed:
            return self._fail(job, f"Policy denied: {runtime.code}")

        guard: HeartbeatGuard | None = None
        try:
            self._storage.mark_job_running(job.id, self._lease_owner, now=self._clock.now())
            self._heartbeat(job.id)
            guard = HeartbeatGuard(
                job_id=job.id,
                lease_owner=self._lease_owner,
                lease_seconds=self._lease_seconds,
                interval_seconds=self._heartbeat_interval_seconds,
                startup_timeout_seconds=self._heartbeat_startup_timeout_seconds,
                shutdown_timeout_seconds=self._heartbeat_shutdown_timeout_seconds,
                storage_factory=self._heartbeat_storage_factory,
                now=self._clock.now,
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
            try:
                self._dispatcher.dispatch(
                    job,
                    lease_owner=self._lease_owner,
                    heartbeat=lambda: self._dispatcher_heartbeat(job.id, guard),
                )
            except Exception as exc:
                dispatch_error = exc
            finally:
                guard.stop()

            # Lost lease wins over every dispatcher exception: the original worker
            # no longer owns the right to record any terminal result.
            if guard.lost_lease is not None:
                return self._lost_lease(job)
            if guard.failure is not None:
                return self._heartbeat_guard_failure(job, guard)
            if dispatch_error is not None:
                return self._dispatch_failure(job, dispatch_error)

            self._heartbeat(job.id)
            self._storage.complete_job(job.id, self._lease_owner, now=self._clock.now())
            return WorkerIterationResult(WorkerIterationStatus.DONE, job.id)
        except LifecycleTransitionError:
            return self._lost_lease(job)
        except Exception:
            return self._fail(job, "Worker execution failed before a confirmed external effect.")
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
            job_id, self._lease_owner, self._lease_seconds, now=self._clock.now(),
        )

    def _dispatcher_heartbeat(self, job_id: str, guard: HeartbeatGuard) -> None:
        try:
            self._heartbeat(job_id)
        except LifecycleTransitionError as exc:
            guard.record_lost_lease(exc)
            raise

    def _dispatch_failure(self, job: Job, error: Exception) -> WorkerIterationResult:
        if isinstance(error, UncertainExternalEffectError):
            return self._needs_verification(job, "External effect outcome is uncertain.")
        if isinstance(error, LifecycleTransitionError):
            return self._lost_lease(job)
        if isinstance(error, DispatchError):
            return self._fail(job, self._safe_dispatch_error(error))
        return self._fail(job, "Worker execution failed before a confirmed external effect.")

    @staticmethod
    def _lost_lease(job: Job) -> WorkerIterationResult:
        return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)

    @staticmethod
    def _heartbeat_guard_failure(job: Job, guard: HeartbeatGuard) -> WorkerIterationResult:
        return WorkerIterationResult(
            WorkerIterationStatus.LOST_LEASE,
            job.id,
            guard.failure_code or "HEARTBEAT_GUARD_FAILURE",
        )

    @staticmethod
    def _safe_dispatch_error(exc: DispatchError) -> str:
        # All dispatcher messages are controlled strings.  Keep the persisted
        # audit compact even if a future subclass accidentally creates a long one.
        return str(exc).replace("\n", " ")[:240]

    def _fail(self, job: Job, error: str) -> WorkerIterationResult:
        try:
            self._storage.fail_job(job.id, self._lease_owner, error, now=self._clock.now())
        except LifecycleTransitionError:
            return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
        return WorkerIterationResult(WorkerIterationStatus.FAILED, job.id, error)

    def _needs_verification(self, job: Job, error: str) -> WorkerIterationResult:
        try:
            self._storage.mark_job_needs_verification(
                job.id, self._lease_owner, error, now=self._clock.now(),
            )
        except LifecycleTransitionError:
            return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
        return WorkerIterationResult(WorkerIterationStatus.NEEDS_VERIFICATION, job.id, error)
