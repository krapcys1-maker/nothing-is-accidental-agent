"""Trwały, offline-only runtime workera Etapu 1."""

from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationResult, WorkerIterationStatus

__all__ = ["JobDispatcher", "Worker", "WorkerIterationResult", "WorkerIterationStatus"]
