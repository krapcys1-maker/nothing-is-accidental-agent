"""Jedna trwała doba redakcyjna i atomowy budżet mutacji V3."""

from __future__ import annotations

import calendar
import hashlib
import json
import random
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import config


POLICY_VERSION = 1
COUNTING_STATES = frozenset({"RESERVED", "CONSUMED", "QUARANTINED"})

KIND_TO_CATEGORY: dict[str, str | None] = {
    "article": "artykuly",
    "article_publish": "artykuly",
    # Zapis szkicu i publikacja są dwiema mutacjami, ale jedną jednostką
    # wolumenu redakcyjnego. Szkic ma własny ledger bezpieczeństwa; limit
    # artykułów zużywa dopiero potwierdzona/niepewna próba publikacji.
    "draft_write": None,
    "note": "notki",
    "comment": "komentarze",
    "discussion_reply": "komentarze",
    "reply": "odpowiedzi",
    "article_reply": "odpowiedzi",
    "like": "lajki",
    "restack": "restacki",
    "obserwacja": "follow",
    "subskrypcja": "subskrypcje",
    "settings": "ustawienia",
}


class BudgetPolicyError(RuntimeError):
    """Rodzaj mutacji lub zapis budżetu nie spełnia kontraktu."""


class BudgetExhausted(RuntimeError):
    """Twardy limit kategorii został już zarezerwowany lub zużyty."""

    def __init__(
        self, *, day_id: str, category: str, limit: int, accounted: int,
        requested: int,
    ) -> None:
        self.day_id = day_id
        self.category = category
        self.limit = limit
        self.accounted = accounted
        self.requested = requested
        super().__init__(
            f"budżet {category} wyczerpany: {accounted}+{requested}>{limit} "
            f"w {day_id}"
        )


def _aware(at: datetime | None = None) -> datetime:
    value = at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("OperationalDay wymaga czasu ze strefą")
    return value


def editorial_date(at: datetime | None = None) -> date:
    return _aware(at).astimezone(ZoneInfo(config.EDITORIAL_TIMEZONE)).date()


def boundaries(day: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(config.EDITORIAL_TIMEZONE)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def month_boundaries(day: date) -> tuple[datetime, datetime]:
    """Granice miesiąca kalendarzowego w tej samej strefie redakcyjnej."""
    zone = ZoneInfo(config.EDITORIAL_TIMEZONE)
    start_local = datetime(day.year, day.month, 1, tzinfo=zone)
    if day.month == 12:
        end_local = datetime(day.year + 1, 1, 1, tzinfo=zone)
    else:
        end_local = datetime(day.year, day.month + 1, 1, tzinfo=zone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _digest(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def day_id(account: str, day: date) -> str:
    return _digest(
        "operational-day", account.strip().lower(), config.EDITORIAL_TIMEZONE,
        day.isoformat(),
    )[:32]


def policy_fingerprint() -> str:
    policy = {
        "version": POLICY_VERSION,
        "timezone": config.EDITORIAL_TIMEZONE,
        "notes": len(config.NOTE_MIX_OTHER_DAY),
        "likes": config.LAJKI_DZIENNIE,
        "comments": config.KOMENTARZE_DZIENNIE,
        "follows_monthly": config.FOLLOW_MIESIECZNIE,
        "subscriptions_monthly": config.SUBSKRYPCJE_MIESIECZNIE,
        "restacks": config.RESTACK_DZIENNIE,
        "replies": config.ODPOWIEDZI_DZIENNIE,
        "articles": config.ARTYKULY_DZIENNIE,
        "settings": config.USTAWIENIA_DZIENNIE,
        "ramp_days": config.ROZBIEG_DNI,
    }
    raw = json.dumps(policy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _range_for_ramp(bounds: tuple[int, int], ramp_up: bool) -> tuple[int, int]:
    low, high = (int(bounds[0]), int(bounds[1]))
    if low < 0 or high < low:
        raise BudgetPolicyError(f"nieprawidłowe widełki {bounds!r}")
    if ramp_up:
        high = low + (high - low) // 2
    return low, high


def _daily_value(
    account: str, day: date, category: str, bounds: tuple[int, int],
    ramp_up: bool,
) -> int:
    low, high = _range_for_ramp(bounds, ramp_up)
    seed = int(_digest(
        "daily", POLICY_VERSION, account.lower(), day.isoformat(), category,
    )[:16], 16)
    return random.Random(seed).randint(low, high)


def _monthly_value(
    account: str, day: date, category: str, bounds: tuple[int, int],
    ramp_up: bool,
) -> int:
    """Wybiera dokładnie N dni miesiąca dla limitu mniejszego niż 31."""
    low, high = _range_for_ramp(bounds, ramp_up)
    month = day.strftime("%Y-%m")
    seed = int(_digest(
        "monthly-target", POLICY_VERSION, account.lower(), month, category,
    )[:16], 16)
    target = random.Random(seed).randint(low, high)
    days = calendar.monthrange(day.year, day.month)[1]
    target = min(target, days)
    ranked = sorted(
        range(1, days + 1),
        key=lambda number: _digest(
            "monthly-day", POLICY_VERSION, account.lower(), month, category,
            number,
        ),
    )
    return 1 if day.day in set(ranked[:target]) else 0


def build_budget(account: str, day: date, *, ramp_up: bool) -> dict[str, int]:
    account = account.strip().lower()
    if not account:
        raise BudgetPolicyError("budżet wymaga tożsamości konta")
    return {
        "artykuly": int(config.ARTYKULY_DZIENNIE),
        "notki": len(config.NOTE_MIX_OTHER_DAY),
        "komentarze": _daily_value(
            account, day, "komentarze", config.KOMENTARZE_DZIENNIE, ramp_up),
        "odpowiedzi": _daily_value(
            account, day, "odpowiedzi", config.ODPOWIEDZI_DZIENNIE, ramp_up),
        "lajki": _daily_value(
            account, day, "lajki", config.LAJKI_DZIENNIE, ramp_up),
        "restacki": _daily_value(
            account, day, "restacki", config.RESTACK_DZIENNIE, ramp_up),
        "follow": _monthly_value(
            account, day, "follow", config.FOLLOW_MIESIECZNIE, ramp_up),
        "subskrypcje": _monthly_value(
            account, day, "subskrypcje",
            config.SUBSKRYPCJE_MIESIECZNIE, ramp_up),
        "ustawienia": int(config.USTAWIENIA_DZIENNIE),
    }


def category_for(kind: str) -> str | None:
    normalized = str(kind or "").strip().lower()
    try:
        return KIND_TO_CATEGORY[normalized]
    except KeyError as exc:
        raise BudgetPolicyError(
            f"rodzaj mutacji {normalized!r} nie ma kategorii budżetu"
        ) from exc


def _account_age_days(
    conn: sqlite3.Connection, at: datetime,
) -> int:
    row = conn.execute("SELECT MIN(started_at) AS started FROM runs").fetchone()
    if not row or not row["started"]:
        return 0
    try:
        started = datetime.fromisoformat(
            str(row["started"]).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 0
    return max(0, (_aware(at) - started.astimezone(timezone.utc)).days)


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["budgets"] = json.loads(result.pop("budget_json"))
    result["ramp_up"] = bool(result["ramp_up"])
    result["quiet_day"] = bool(result["quiet_day"])
    return result


def get_or_create(
    conn: sqlite3.Connection, *, account: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Zwraca jeden zapisany plan; nigdy nie przelicza istniejącego dnia."""
    now = _aware(at).astimezone(timezone.utc)
    account = (account or config.TEST_ACCOUNT_HANDLE
               or "agent-v3-prototype").strip().lower()
    day = editorial_date(now)
    identifier = day_id(account, day)
    row = conn.execute(
        "SELECT * FROM operational_days WHERE id = ?", (identifier,)
    ).fetchone()
    if row:
        return _decode(row)

    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM operational_days WHERE id = ?", (identifier,)
        ).fetchone()
        if not row:
            ramp_up = _account_age_days(conn, now) < config.ROZBIEG_DNI
            start, end = boundaries(day)
            budgets = build_budget(account, day, ramp_up=ramp_up)
            conn.execute(
                "INSERT INTO operational_days "
                "(id, account, day_key, timezone, starts_at, ends_at, "
                "created_at, policy_version, policy_hash, ramp_up, quiet_day, "
                "budget_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier, account, day.isoformat(),
                    config.EDITORIAL_TIMEZONE,
                    start.isoformat(timespec="seconds"),
                    end.isoformat(timespec="seconds"),
                    now.isoformat(timespec="seconds"), POLICY_VERSION,
                    policy_fingerprint(), int(ramp_up),
                    int(config.cichy_dzien(now)),
                    json.dumps(budgets, sort_keys=True, separators=(",", ":")),
                ),
            )
            row = conn.execute(
                "SELECT * FROM operational_days WHERE id = ?", (identifier,)
            ).fetchone()
        if owns_transaction:
            conn.commit()
        return _decode(row)
    except Exception:
        if owns_transaction and conn.in_transaction:
            conn.rollback()
        raise


def accounted(conn: sqlite3.Connection, operational_day_id: str) -> dict[str, int]:
    row = conn.execute(
        "SELECT budget_json FROM operational_days WHERE id = ?",
        (operational_day_id,),
    ).fetchone()
    if not row:
        raise BudgetPolicyError(f"brak OperationalDay {operational_day_id}")
    budgets = json.loads(row["budget_json"])
    result = {str(key): 0 for key in budgets}
    placeholders = ",".join("?" for _ in COUNTING_STATES)
    rows = conn.execute(
        "SELECT category, COALESCE(SUM(units), 0) AS units "
        "FROM action_budget_reservations WHERE operational_day_id = ? "
        f"AND status IN ({placeholders}) GROUP BY category",
        (operational_day_id, *sorted(COUNTING_STATES)),
    ).fetchall()
    for item in rows:
        result[str(item["category"])] = int(item["units"])
    return result


def snapshot(
    conn: sqlite3.Connection, *, account: str | None = None,
    at: datetime | None = None,
) -> dict[str, Any]:
    day = get_or_create(conn, account=account, at=at)
    used = accounted(conn, day["id"])
    day["accounted"] = used
    day["remaining"] = {
        category: max(0, int(limit) - used.get(category, 0))
        for category, limit in day["budgets"].items()
    }
    return day


def reserve_units(
    conn: sqlite3.Connection, *, day: dict[str, Any], attempt_id: str,
    category: str, units: int = 1,
) -> None:
    if units <= 0:
        raise BudgetPolicyError("rezerwacja wymaga dodatniej liczby jednostek")
    budgets = day["budgets"]
    if category not in budgets:
        raise BudgetPolicyError(
            f"kategoria {category!r} nie istnieje w planie {day['id']}")
    used = accounted(conn, day["id"]).get(category, 0)
    limit = int(budgets[category])
    if used + units > limit:
        raise BudgetExhausted(
            day_id=day["id"], category=category, limit=limit,
            accounted=used, requested=units,
        )
    conn.execute(
        "INSERT INTO action_budget_reservations "
        "(attempt_id, operational_day_id, category, units, status, "
        "reserved_at) VALUES (?, ?, ?, ?, 'RESERVED', ?)",
        (
            attempt_id, day["id"], category, units,
            datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        ),
    )


def finish_reservation(
    conn: sqlite3.Connection, *, attempt_id: str, attempt_status: str,
) -> None:
    target = {
        "FAILED": "RELEASED",
        "UNKNOWN": "QUARANTINED",
        "CONFIRMED": "CONSUMED",
    }.get(attempt_status)
    if target is None:
        raise BudgetPolicyError(
            f"brak przejścia budżetu dla {attempt_status!r}")
    conn.execute(
        "UPDATE action_budget_reservations SET status = ?, finished_at = ? "
        "WHERE attempt_id = ? AND status = 'RESERVED'",
        (
            target,
            datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            attempt_id,
        ),
    )
