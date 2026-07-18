"""Controlled periodic lease renewal for one synchronously dispatched job."""
from __future__ import annotations

import math
import threading
from datetime import datetime
from typing import Callable, Protocol

from app.core.clock import Clock
from app.ports.storage import LifecycleTransitionError


class HeartbeatStorage(Protocol):
    """The narrow, independently opened storage contract used by the guard."""

    def heartbeat_job_lease(
        self, job_id: str, lease_owner: str, lease_seconds: int,
        *, now: datetime | None = None, clock: Clock | None = None,
    ) -> None: ...

    def close(self) -> None: ...


class HeartbeatWaiter(Protocol):
    """Injectable wait primitive; tests can trigger a heartbeat without sleeping."""

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool: ...

    def wake(self) -> None: ...


ReadyWaiter = Callable[[threading.Event, float], bool]
ThreadJoiner = Callable[[threading.Thread, float], None]


class HeartbeatGuardError(RuntimeError):
    """Controlled in-memory failure observed by the owning worker."""

    code = "HEARTBEAT_GUARD_FAILURE"


class HeartbeatGuardStartupError(HeartbeatGuardError):
    code = "HEARTBEAT_GUARD_START_FAILURE"


class HeartbeatGuardStartupTimeoutError(HeartbeatGuardStartupError):
    code = "HEARTBEAT_GUARD_START_TIMEOUT"


class HeartbeatGuardHeartbeatError(HeartbeatGuardError):
    code = "HEARTBEAT_GUARD_HEARTBEAT_FAILURE"


class HeartbeatGuardCleanupError(HeartbeatGuardError):
    code = "HEARTBEAT_GUARD_CLEANUP_FAILURE"


class HeartbeatGuardShutdownError(HeartbeatGuardError):
    code = "HEARTBEAT_GUARD_SHUTDOWN_FAILURE"


class HeartbeatGuardShutdownTimeoutError(HeartbeatGuardShutdownError):
    code = "HEARTBEAT_GUARD_SHUTDOWN_TIMEOUT"


def _wait_for_ready(event: threading.Event, timeout_seconds: float) -> bool:
    return event.wait(timeout_seconds)


def _join_thread(thread: threading.Thread, timeout_seconds: float) -> None:
    thread.join(timeout=timeout_seconds)


class EventHeartbeatWaiter:
    """Production waiter: wait for either the interval or the guard stop event."""

    def wait(self, stop_event: threading.Event, timeout_seconds: float) -> bool:
        return stop_event.wait(timeout_seconds)

    def wake(self) -> None:
        # ``Event.set`` already wakes ``Event.wait``.
        return None


class HeartbeatGuard:
    """Owns one daemon safety-net thread and its independently opened storage.

    The guard deliberately cannot interrupt arbitrary dispatcher code.  Instead it
    records failure only in this guard's in-memory state; the worker observes that
    state after dispatch and refuses to terminalize the job as DONE.  SQLite keeps
    the durable job state, which recovery/reconciliation resolves later.
    """

    def __init__(
        self,
        *,
        job_id: str,
        lease_owner: str,
        lease_seconds: int,
        interval_seconds: float,
        startup_timeout_seconds: float,
        shutdown_timeout_seconds: float,
        storage_factory: Callable[[], HeartbeatStorage],
        now: Callable[[], datetime] | None = None,
        clock: Clock | None = None,
        waiter: HeartbeatWaiter,
        ready_waiter: ReadyWaiter = _wait_for_ready,
        thread_joiner: ThreadJoiner = _join_thread,
    ) -> None:
        if not job_id.strip() or not lease_owner.strip():
            raise ValueError("job_id and lease_owner must be non-empty.")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive.")
        if not math.isfinite(interval_seconds) or interval_seconds <= 0:
            raise ValueError("interval_seconds must be finite and positive.")
        if interval_seconds >= lease_seconds:
            raise ValueError("interval_seconds must be shorter than lease_seconds.")
        for name, value in (
            ("startup_timeout_seconds", startup_timeout_seconds),
            ("shutdown_timeout_seconds", shutdown_timeout_seconds),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")

        self._job_id = job_id
        self._lease_owner = lease_owner
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._startup_timeout_seconds = startup_timeout_seconds
        self._shutdown_timeout_seconds = shutdown_timeout_seconds
        self._storage_factory = storage_factory
        if now is not None and clock is not None:
            raise ValueError("Pass either now or clock, not both.")
        self._now = now
        self._clock = clock
        self._waiter = waiter
        self._ready_waiter = ready_waiter
        self._thread_joiner = thread_joiner
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._state_lock = threading.Lock()
        self._lost_lease: LifecycleTransitionError | None = None
        self._failure: Exception | None = None
        self._thread: threading.Thread | None = None

    @property
    def lost_lease(self) -> LifecycleTransitionError | None:
        with self._state_lock:
            return self._lost_lease

    @property
    def failure(self) -> Exception | None:
        with self._state_lock:
            return self._failure

    @property
    def failure_code(self) -> str | None:
        failure = self.failure
        return None if failure is None else getattr(failure, "code", "HEARTBEAT_GUARD_FAILURE")

    @property
    def thread_is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Heartbeat guard may be started only once.")
        self._thread = threading.Thread(
            target=self._run,
            name=f"job-heartbeat-{self._job_id}",
            # A bounded stop/join is always attempted.  Daemon status is only the
            # last process-level safety net for a thread blocked inside arbitrary
            # storage code that Python cannot safely interrupt.
            daemon=True,
        )
        try:
            self._thread.start()
        except Exception as exc:
            self._record_failure(HeartbeatGuardStartupError(str(exc)))
            self._ready_event.set()
            return

        # Do not enter dispatcher code until the guard owns its separate SQLite
        # connection or has recorded a fail-closed startup failure.  The wait is
        # bounded so a blocked factory cannot hold the worker or process hostage.
        try:
            ready = self._ready_waiter(self._ready_event, self._startup_timeout_seconds)
        except Exception as exc:
            self._record_failure(HeartbeatGuardStartupError(str(exc)))
            self._request_stop()
            self._bounded_join(prefer_timeout=False)
            return
        if ready:
            return

        self._record_failure(HeartbeatGuardStartupTimeoutError(
            "Heartbeat guard did not become ready before its startup timeout."
        ), prefer_new=True)
        self._request_stop()
        self._bounded_join(prefer_timeout=False)

    def stop(self) -> None:
        self._request_stop()
        self._bounded_join()

    def record_lost_lease(self, error: LifecycleTransitionError) -> None:
        with self._state_lock:
            self._lost_lease = error

    def _record_failure(self, error: Exception, *, prefer_new: bool = False) -> None:
        with self._state_lock:
            if self._lost_lease is None and (self._failure is None or prefer_new):
                self._failure = error

    def _request_stop(self) -> None:
        self._stop_event.set()
        try:
            self._waiter.wake()
        except Exception as exc:
            self._record_failure(HeartbeatGuardCleanupError(str(exc)))

    def _bounded_join(self, *, prefer_timeout: bool = True) -> None:
        if self._thread is None:
            return
        try:
            self._thread_joiner(self._thread, self._shutdown_timeout_seconds)
        except Exception as exc:
            self._record_failure(HeartbeatGuardShutdownError(str(exc)))
        if self._thread.is_alive():
            self._record_failure(HeartbeatGuardShutdownTimeoutError(
                "Heartbeat guard did not stop before its shutdown timeout."
            ), prefer_new=prefer_timeout)

    def _run(self) -> None:
        storage: HeartbeatStorage | None = None
        try:
            storage = self._storage_factory()
            if self._stop_event.is_set():
                return
            self._ready_event.set()
            while True:
                if self._waiter.wait(self._stop_event, self._interval_seconds):
                    return
                if self._stop_event.is_set():
                    return
                try:
                    if self._clock is not None:
                        storage.heartbeat_job_lease(
                            self._job_id,
                            self._lease_owner,
                            self._lease_seconds,
                            clock=self._clock,
                        )
                    else:
                        assert self._now is not None
                        storage.heartbeat_job_lease(
                            self._job_id,
                            self._lease_owner,
                            self._lease_seconds,
                            now=self._now(),
                        )
                except LifecycleTransitionError as exc:
                    self.record_lost_lease(exc)
                    return
                except Exception as exc:
                    self._record_failure(HeartbeatGuardHeartbeatError(str(exc)))
                    return
        except Exception as exc:
            self._record_failure(HeartbeatGuardStartupError(str(exc)))
        finally:
            self._ready_event.set()
            if storage is not None:
                try:
                    storage.close()
                except Exception as exc:
                    self._record_failure(HeartbeatGuardCleanupError(str(exc)))
