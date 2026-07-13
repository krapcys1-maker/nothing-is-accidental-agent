"""One-process durable worker using the queue's existing atomic lifecycle helpers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
    storage operation today; the dedicated run reaper remains a later task.
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        policy: PolicyEngine,
        dispatcher: Dispatcher,
        lease_owner: str,
        lease_seconds: int = 60,
        clock: Clock | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not lease_owner.strip() or lease_seconds <= 0:
            raise ValueError("lease_owner must be non-empty and lease_seconds must be positive.")
        self._storage = storage
        self._policy = policy
        self._dispatcher = dispatcher
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
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

        try:
            self._storage.mark_job_running(job.id, self._lease_owner, now=self._clock.now())
            self._heartbeat(job.id)
            self._dispatcher.dispatch(
                job, lease_owner=self._lease_owner,
                heartbeat=lambda: self._heartbeat(job.id),
            )
            self._heartbeat(job.id)
            self._storage.complete_job(job.id, self._lease_owner, now=self._clock.now())
            return WorkerIterationResult(WorkerIterationStatus.DONE, job.id)
        except UncertainExternalEffectError:
            return self._needs_verification(job, "External effect outcome is uncertain.")
        except LifecycleTransitionError:
            return WorkerIterationResult(WorkerIterationStatus.LOST_LEASE, job.id)
        except DispatchError as exc:
            return self._fail(job, self._safe_dispatch_error(exc))
        except Exception:
            return self._fail(job, "Worker execution failed before a confirmed external effect.")

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
