"""Centralna ścieżka tworzenia jobów z decyzją SchedulingPolicy."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.clock import Clock, SystemClock
from app.models import Job, JobKind, WorkflowType
from app.ports.storage import StoragePort
from app.scheduler.scheduling import (
    ImmediateSchedulingContract,
    ScheduleDecision,
    SchedulingPolicy,
    calculate_schedule,
)


@dataclass(frozen=True)
class ScheduledJobRequest:
    """Dane joba bez pól wyznaczanych wyłącznie przez politykę."""

    id: str
    account_id: str
    kind: JobKind
    workflow: WorkflowType
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    topic_id: int | None = None
    run_id: str | None = None
    priority: int = 0
    deadline_at: datetime | None = None
    max_attempts: int = 1
    requested_at: datetime | None = None
    immediate_contract: ImmediateSchedulingContract | None = None


@dataclass(frozen=True)
class ScheduledEnqueueResult:
    job: Job
    decision: ScheduleDecision


class ScheduledJobEnqueuer:
    """Builds a fresh job only after one deterministic schedule decision."""

    def __init__(
        self,
        *,
        storage: StoragePort,
        scheduling_policy: SchedulingPolicy,
        clock: Clock | None = None,
    ) -> None:
        self._storage = storage
        self._scheduling_policy = scheduling_policy
        self._clock = clock or SystemClock()

    def enqueue(self, request: ScheduledJobRequest) -> ScheduledEnqueueResult:
        decision = calculate_schedule(
            self._scheduling_policy,
            now=self._clock.now(),
            requested_at=request.requested_at,
            immediate_contract=request.immediate_contract,
        )
        job = Job(
            id=request.id,
            account_id=request.account_id,
            kind=request.kind,
            workflow=request.workflow,
            idempotency_key=request.idempotency_key,
            priority=request.priority,
            topic_id=request.topic_id,
            run_id=request.run_id,
            payload=request.payload,
            schedule_reason=decision.reason.value,
            earliest_run_at=decision.earliest_run_at,
            deadline_at=request.deadline_at,
            max_attempts=request.max_attempts,
            created_at=self._clock.now(),
        )
        return ScheduledEnqueueResult(job=self._storage.enqueue_job(job), decision=decision)
