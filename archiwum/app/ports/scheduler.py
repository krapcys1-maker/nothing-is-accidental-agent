"""SchedulerPort — harmonogram. STUB w walking skeleton (APScheduler dopiero w Etapie 6)."""
from __future__ import annotations

from typing import Any, Callable, Protocol


class SchedulerPort(Protocol):
    def schedule(self, job_id: str, cron: str, func: Callable[..., Any],
                 account_id: str | None = None) -> None: ...
    def remove(self, job_id: str) -> None: ...
    def list_jobs(self) -> list[dict]: ...
    def start(self) -> None: ...
    def shutdown(self) -> None: ...


class StubScheduler:
    """Nie planuje niczego — walking skeleton uruchamiamy ręcznie."""

    def schedule(self, job_id: str, cron: str, func, account_id=None) -> None:
        raise NotImplementedError("Scheduler nieaktywny w MVP-0 (uruchamianie ręczne).")

    def remove(self, job_id: str) -> None:
        raise NotImplementedError

    def list_jobs(self) -> list[dict]:
        return []

    def start(self) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        return None
