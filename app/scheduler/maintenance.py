"""Offline maintenance loop for expired job leases and stale research runs.

The runner deliberately has no worker, dispatcher, or PolicyEngine dependency.
It only invokes the existing durable recovery and reaper operations through an
independently opened storage connection, so safety cleanup remains possible
while execution flags are disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
import re
import threading
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.models import JobRecoveryResult, RunReaperResult


_ERROR_SUMMARY_LIMIT = 80
_SECRET_PATTERNS = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]+\b"),
    re.compile(
        r"(?i)\b(x-api-key|api[_ -]?key|authorization|password|passwd|secret|token)\b"
        r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[^\s,;]+"),
)


def _safe_error_summary(error: BaseException) -> str:
    """Return one bounded, non-secret diagnostic fragment for CLI output."""
    message = " ".join(str(error).split())
    message = _SECRET_PATTERNS[0].sub("[REDACTED]", message)
    message = _SECRET_PATTERNS[1].sub(
        lambda match: f"{match.group(1)}=[REDACTED]", message,
    )
    message = _SECRET_PATTERNS[2].sub("Bearer [REDACTED]", message)
    summary = f"{type(error).__name__}: {message}" if message else type(error).__name__
    if len(summary) > _ERROR_SUMMARY_LIMIT:
        return f"{summary[:_ERROR_SUMMARY_LIMIT - 3]}..."
    return summary


class MaintenanceCycleError(RuntimeError):
    """Controlled failure that retains primary and storage-cleanup diagnostics."""

    def __init__(
        self,
        *,
        primary_error: Exception | None,
        cleanup_error: BaseException,
    ) -> None:
        self.primary_error = primary_error
        self.cleanup_error = cleanup_error
        cleanup = _safe_error_summary(cleanup_error)
        if primary_error is None:
            message = f"Maintenance cleanup failed; cleanup_error={cleanup}"
        else:
            primary = _safe_error_summary(primary_error)
            message = (
                "Maintenance cycle failed; "
                f"primary_error={primary}; cleanup_error={cleanup}"
            )
        super().__init__(message)


class MaintenanceStorage(Protocol):
    """The narrow storage contract needed by a single maintenance cycle."""

    def release_or_requeue_expired_leases(
        self, *, now: datetime | None = None,
    ) -> JobRecoveryResult: ...

    def reap_orphaned_stale_runs(
        self, stale_before: datetime, *, now: datetime | None = None,
    ) -> RunReaperResult: ...

    def close(self) -> None: ...


class MaintenanceWaiter(Protocol):
    """Injectable wait primitive so polling remains deterministic in tests."""

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool: ...


class EventMaintenanceWaiter:
    """Production waiter: returns when stopped or after the requested delay."""

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool:
        return stop_event.wait(timeout_seconds)


@dataclass(frozen=True)
class MaintenanceCycleResult:
    """Structured, audit-friendly result of one completed maintenance cycle."""

    now: datetime
    recovery: JobRecoveryResult
    reaper: RunReaperResult


class MaintenanceRunner:
    """Runs explicit offline recovery before stale-run reaping.

    This class never claims a job, dispatches work, starts a worker, or resumes
    research.  It intentionally does not consult worker runtime flags: expired
    lease recovery and stale-run reaping are safety cleanup and must still be
    available while a worker is disabled, in safe mode, or killed.
    """

    def __init__(
        self,
        *,
        storage_factory: Callable[[], MaintenanceStorage],
        stale_after_seconds: float,
        clock: Clock | None = None,
        waiter: MaintenanceWaiter | None = None,
    ) -> None:
        if not math.isfinite(stale_after_seconds) or stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be finite and positive.")
        self._storage_factory = storage_factory
        self._stale_after_seconds = stale_after_seconds
        self._clock = clock or SystemClock()
        self._waiter = waiter or EventMaintenanceWaiter()

    def run_once(self) -> MaintenanceCycleResult:
        """Open one storage connection and complete exactly one ordered cycle."""
        now = self._clock.now()
        storage = self._storage_factory()
        try:
            recovery = storage.release_or_requeue_expired_leases(now=now)
            reaper = storage.reap_orphaned_stale_runs(
                now - timedelta(seconds=self._stale_after_seconds), now=now,
            )
        except BaseException as primary_error:
            try:
                storage.close()
            except BaseException as cleanup_error:
                if not isinstance(primary_error, Exception):
                    # Process-control exceptions remain process-control
                    # exceptions, but keep the cleanup fault available to a
                    # controlled CLI handler without exposing raw secrets.
                    primary_error.add_note(
                        "Maintenance cleanup failed: "
                        f"{_safe_error_summary(cleanup_error)}"
                    )
                    raise primary_error
                raise MaintenanceCycleError(
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise

        result = MaintenanceCycleResult(now=now, recovery=recovery, reaper=reaper)
        try:
            storage.close()
        except BaseException as cleanup_error:
            # A completed operation is not a successful cycle until its owned
            # storage connection has also closed deterministically.
            raise MaintenanceCycleError(
                primary_error=None,
                cleanup_error=cleanup_error,
            ) from cleanup_error
        return result

    def run_forever(
        self,
        *,
        interval_seconds: float,
        stop_event: threading.Event | None = None,
    ) -> None:
        """Poll sequentially, with one fixed delay after each completed cycle."""
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("interval_seconds must be finite and positive.")
        stopped = stop_event or threading.Event()
        while not stopped.is_set():
            self.run_once()
            if stopped.is_set():
                return
            if self._waiter.wait(stopped, interval_seconds):
                return
