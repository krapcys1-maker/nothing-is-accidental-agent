"""Trwały, offline-only runtime workera Etapu 1."""

from app.scheduler.enqueue import ScheduledEnqueueResult, ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.scheduling import EditorialWindow, ScheduleDecision, ScheduleReason, SchedulingPolicy

__all__ = [
    "EditorialWindow", "JobDispatcher", "ScheduleDecision", "ScheduleReason", "ScheduledEnqueueResult",
    "ScheduledJobEnqueuer", "ScheduledJobRequest", "SchedulingPolicy", "Worker",
    "WorkerIterationResult", "WorkerIterationStatus",
]


def __getattr__(name: str):
    """Retain worker exports without eagerly importing the paid-provider graph."""
    if name == "JobDispatcher":
        from app.scheduler.dispatcher import JobDispatcher
        return JobDispatcher
    if name in {"Worker", "WorkerIterationResult", "WorkerIterationStatus"}:
        from app.scheduler.worker import Worker, WorkerIterationResult, WorkerIterationStatus
        return {
            "Worker": Worker,
            "WorkerIterationResult": WorkerIterationResult,
            "WorkerIterationStatus": WorkerIterationStatus,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
