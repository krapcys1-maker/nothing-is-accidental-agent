"""Zegar jako port — ułatwia testy deterministyczne."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Zegar testowy zwracający ustaloną chwilę."""

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def parse_authority_instant(value: object) -> datetime | None:
    """Parse one durable authority timestamp into an aware UTC instant.

    An owner writes an approval window as ``2026-08-10T18:00:00.000000+00:00``;
    the runtime persists its own clock as ``2026-08-10 16:55:12.345678``.  Both
    name the same canonical UTC timeline, but they do not sort against each
    other as text: within one date the ``T`` separator orders after the space,
    so an already-expired window compares as still open.  Freshness is therefore
    decided on the parsed instant, never on the two spellings.

    ``None`` means the value is not a timestamp at all.  Callers treat that as a
    refusal — an unreadable window is never an open one.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
