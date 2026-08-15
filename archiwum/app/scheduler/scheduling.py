"""Deterministyczna polityka okien redakcyjnych, bez SQLite i bez sieci."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from pathlib import Path
import sys
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_SCHEDULE_REASON_LENGTH = 64


class SchedulingValidationError(ValueError):
    """Konfiguracja albo wejście polityki nie pozwala na bezpieczny harmonogram."""


class ScheduleReason(str, Enum):
    """Zamknięte, trwałe kody decyzji harmonogramu."""

    WITHIN_EDITORIAL_WINDOW = "WITHIN_EDITORIAL_WINDOW"
    DEFERRED_TO_WINDOW_START = "DEFERRED_TO_WINDOW_START"
    REQUESTED_FUTURE_TIME = "REQUESTED_FUTURE_TIME"
    REQUESTED_TIME_DEFERRED_TO_WINDOW = "REQUESTED_TIME_DEFERRED_TO_WINDOW"
    SAFETY_OPERATION_IMMEDIATE = "SAFETY_OPERATION_IMMEDIATE"


class ImmediateSchedulingContract(str, Enum):
    """Jedyna wewnętrzna ścieżka, która może ominąć okno redakcyjne."""

    SAFETY_OPERATION = "SAFETY_OPERATION"


def validate_schedule_reason(value: str) -> ScheduleReason:
    """Odrzuca dowolny tekst zamiast kontrolowanego, krótkiego kodu."""
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise SchedulingValidationError("schedule_reason must be a non-empty single-line code.")
    if len(value) > MAX_SCHEDULE_REASON_LENGTH:
        raise SchedulingValidationError("schedule_reason exceeds the controlled length limit.")
    try:
        return ScheduleReason(value)
    except ValueError as exc:
        raise SchedulingValidationError("schedule_reason must be a controlled scheduling code.") from exc


def _utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise SchedulingValidationError(f"{name} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _load_iana_zone(timezone_name: str) -> ZoneInfo:
    """Loads IANA data through ``zoneinfo`` and fails closed when unavailable.

    ``tzdata`` is a runtime dependency on Windows. The local fallback only helps
    this project's virtual environment use the already-installed base interpreter
    data during offline development; it never guesses a Windows-local timezone.
    """
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as original_error:
        parts = timezone_name.split("/")
        if not parts or any(not part or part in {".", ".."} for part in parts):
            raise original_error
        fallback = Path(sys.base_prefix) / "Lib" / "site-packages" / "tzdata" / "zoneinfo"
        candidate = fallback.joinpath(*parts)
        if not candidate.is_file():
            raise original_error
        with candidate.open("rb") as stream:
            return ZoneInfo.from_file(stream, key=timezone_name)


@dataclass(frozen=True)
class EditorialWindow:
    """Jedno nieprzechodzące przez północ lokalne okno redakcyjne."""

    weekdays: frozenset[int]
    start: time
    end: time

    def __post_init__(self) -> None:
        weekdays = frozenset(self.weekdays)
        if not weekdays or any(isinstance(day, bool) or not isinstance(day, int) or day not in range(7)
                               for day in weekdays):
            raise SchedulingValidationError("EditorialWindow weekdays must be non-empty integers from 0 to 6.")
        if not isinstance(self.start, time) or not isinstance(self.end, time):
            raise SchedulingValidationError("EditorialWindow start and end must be time values.")
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise SchedulingValidationError("EditorialWindow times must be timezone-naive local wall times.")
        if any((self.start.second, self.start.microsecond, self.end.second, self.end.microsecond)):
            raise SchedulingValidationError("EditorialWindow supports deterministic HH:MM precision only.")
        if self.start >= self.end:
            raise SchedulingValidationError("EditorialWindow must satisfy start < end; cross-midnight windows are unsupported.")
        object.__setattr__(self, "weekdays", weekdays)

    @classmethod
    def from_config(cls, raw: Mapping[str, object]) -> "EditorialWindow":
        if not isinstance(raw, Mapping):
            raise SchedulingValidationError("Each editorial window must be a mapping.")
        weekdays = raw.get("weekdays")
        if isinstance(weekdays, (str, bytes)) or not isinstance(weekdays, Sequence):
            raise SchedulingValidationError("EditorialWindow weekdays must be a list.")
        return cls(
            weekdays=frozenset(weekdays),
            start=_parse_local_time(raw.get("start"), field_name="start"),
            end=_parse_local_time(raw.get("end"), field_name="end"),
        )


def _parse_local_time(value: object, *, field_name: str) -> time:
    if not isinstance(value, str):
        raise SchedulingValidationError(f"EditorialWindow {field_name} must be an HH:MM string.")
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise SchedulingValidationError(
            f"EditorialWindow {field_name} must be a valid HH:MM value."
        ) from exc


@dataclass(frozen=True)
class SchedulingPolicy:
    """Czysta polityka lokalnych okien; wynik zawsze zwraca jako UTC."""

    timezone_name: str
    windows: tuple[EditorialWindow, ...]
    timezone: ZoneInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.timezone_name, str) or not self.timezone_name.strip():
            raise SchedulingValidationError("An explicit IANA timezone is required.")
        try:
            zone = _load_iana_zone(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise SchedulingValidationError("Editorial timezone is unknown.") from exc
        windows = tuple(self.windows)
        if not windows:
            raise SchedulingValidationError("At least one editorial window is required.")
        if not all(isinstance(window, EditorialWindow) for window in windows):
            raise SchedulingValidationError("SchedulingPolicy windows must be EditorialWindow values.")
        for weekday in range(7):
            day_windows = sorted((window for window in windows if weekday in window.weekdays), key=lambda item: item.start)
            for previous, current in zip(day_windows, day_windows[1:]):
                if previous.end > current.start:
                    raise SchedulingValidationError("Editorial windows for the same weekday may not overlap.")
        object.__setattr__(self, "windows", windows)
        object.__setattr__(self, "timezone", zone)

    @classmethod
    def from_config(cls, raw: Mapping[str, object]) -> "SchedulingPolicy":
        if not isinstance(raw, Mapping):
            raise SchedulingValidationError("editorial_schedule must be a mapping.")
        timezone_name = raw.get("timezone")
        windows = raw.get("windows")
        if not isinstance(timezone_name, str):
            raise SchedulingValidationError("editorial_schedule.timezone must be an IANA timezone string.")
        if isinstance(windows, (str, bytes)) or not isinstance(windows, Sequence):
            raise SchedulingValidationError("editorial_schedule.windows must be a non-empty list.")
        return cls(timezone_name=timezone_name, windows=tuple(EditorialWindow.from_config(item) for item in windows))

    def is_within_window(self, moment: datetime) -> bool:
        local = _utc(moment, name="moment").astimezone(self.timezone)
        local_time = local.replace(tzinfo=None).time()
        return any(
            local.weekday() in window.weekdays and window.start <= local_time < window.end
            for window in self.windows
        )

    def next_window_start(self, moment: datetime) -> datetime:
        """Returns the first allowed local start not before ``moment``, as UTC.

        Ambiguous wall times choose fold=0. A nonexistent DST wall time is advanced
        minute by minute to the first valid local instant after the gap.
        """
        anchor = _utc(moment, name="moment")
        local_anchor = anchor.astimezone(self.timezone)
        for offset in range(8):
            candidate_date = local_anchor.date() + timedelta(days=offset)
            for window in sorted(
                (item for item in self.windows if candidate_date.weekday() in item.weekdays),
                key=lambda item: item.start,
            ):
                candidate = self._resolve_local_start(candidate_date, window.start)
                if candidate >= anchor:
                    return candidate
        raise SchedulingValidationError("No editorial window was found within one deterministic weekly cycle.")

    def _resolve_local_start(self, day: date, local_start: time) -> datetime:
        naive = datetime.combine(day, local_start)
        for minute_offset in range(0, (24 * 60) + 1):
            candidate = naive + timedelta(minutes=minute_offset)
            choices: list[datetime] = []
            for fold in (0, 1):
                local = candidate.replace(tzinfo=self.timezone, fold=fold)
                round_trip = local.astimezone(timezone.utc).astimezone(self.timezone)
                if round_trip.replace(tzinfo=None) == candidate and round_trip.fold == fold:
                    choices.append(local.astimezone(timezone.utc))
            if choices:
                return min(choices)
        raise SchedulingValidationError("Could not resolve the local editorial window after a DST transition.")


@dataclass(frozen=True)
class ScheduleDecision:
    earliest_run_at: datetime
    reason: ScheduleReason

    def __post_init__(self) -> None:
        object.__setattr__(self, "earliest_run_at", _utc(self.earliest_run_at, name="earliest_run_at"))


def calculate_schedule(
    policy: SchedulingPolicy,
    *,
    now: datetime,
    requested_at: datetime | None = None,
    immediate_contract: ImmediateSchedulingContract | None = None,
) -> ScheduleDecision:
    """Calculates one policy-controlled UTC schedule without touching storage.

    A requested time in the past is rejected fail-closed. Only the explicitly
    named safety contract may bypass editorial windows; no CLI exposes it.
    """
    current = _utc(now, name="now")
    if immediate_contract is not None:
        if immediate_contract is not ImmediateSchedulingContract.SAFETY_OPERATION:
            raise SchedulingValidationError("Immediate scheduling requires the safety-operation contract.")
        return ScheduleDecision(current, ScheduleReason.SAFETY_OPERATION_IMMEDIATE)

    if requested_at is not None:
        requested = _utc(requested_at, name="requested_at")
        if requested < current:
            raise SchedulingValidationError("requested_at may not be in the past.")
        if requested > current:
            if policy.is_within_window(requested):
                return ScheduleDecision(requested, ScheduleReason.REQUESTED_FUTURE_TIME)
            return ScheduleDecision(
                policy.next_window_start(requested),
                ScheduleReason.REQUESTED_TIME_DEFERRED_TO_WINDOW,
            )

    if policy.is_within_window(current):
        return ScheduleDecision(current, ScheduleReason.WITHIN_EDITORIAL_WINDOW)
    return ScheduleDecision(policy.next_window_start(current), ScheduleReason.DEFERRED_TO_WINDOW_START)
