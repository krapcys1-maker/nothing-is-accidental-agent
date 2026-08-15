"""Baza: cztery tabele, zero migracji, zero triggerów, zero CHECK-ów z limitami.

Schemat powstaje z `CREATE TABLE IF NOT EXISTS` przy starcie. Zmiana schematu to
zmiana tego pliku — nie ma drabiny wersji, bo poprzedni agent miał 42 migracje
i to one blokowały produkcję, nie brak funkcji.

Limitów nie ma w `CHECK`-ach celowo: limit przypięty w schemacie to drugie
miejsce, w którym żyje ta sama liczba, a wtedy podniesienie jej w kodzie wywala
produkcję (stary agent: `attempt_no IN (1,2)` w ośmiu tabelach, 1,84 USD do kosza).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,          -- RUNNING / DONE / FAILED
    stage       TEXT,                   -- na czym stanęło
    cost_usd    REAL NOT NULL DEFAULT 0,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER,
    at             TEXT NOT NULL,
    provider       TEXT NOT NULL,       -- anthropic / deepseek
    model          TEXT NOT NULL,
    purpose        TEXT NOT NULL,       -- scout / discovery / write / ...
    tokens_in      INTEGER NOT NULL DEFAULT 0,
    tokens_out     INTEGER NOT NULL DEFAULT 0,
    web_searches   INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0,
    price_verified INTEGER NOT NULL DEFAULT 1,  -- 0 = stawka niepotwierdzona
    ok             INTEGER NOT NULL DEFAULT 1,
    note           TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    created_at   TEXT NOT NULL,
    topic        TEXT,
    title        TEXT,
    body         TEXT,
    evidence     TEXT,                  -- karta dowodowa, JSON
    status       TEXT NOT NULL,         -- SAVED / BLOCKED
    blocked_by   TEXT,                  -- która z czterech bramek
    notes        TEXT                   -- niesblokujące uwagi, JSON
);

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER,
    at           TEXT NOT NULL,
    url          TEXT NOT NULL,
    domain       TEXT NOT NULL,         -- do reguły różnorodności
    title        TEXT,
    source_class TEXT,                  -- PRIMARY / SUPPORTING / ODPAD
    fetched_ok   INTEGER NOT NULL DEFAULT 0,
    fail_reason  TEXT                   -- np. blokada botów
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Otwiera bazę i zakłada schemat, jeśli go nie ma."""
    db_path = path or config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def start_run(conn: sqlite3.Connection, stage: str = "start") -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at, status, stage) VALUES (?, 'RUNNING', ?)",
        (now(), stage),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection, run_id: int, status: str, stage: str, note: str = ""
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, stage = ?, note = ?,"
        " cost_usd = (SELECT COALESCE(SUM(cost_usd), 0) FROM calls WHERE run_id = ?)"
        " WHERE id = ?",
        (now(), status, stage, note, run_id, run_id),
    )
    conn.commit()


def record_call(conn: sqlite3.Connection, **fields: Any) -> None:
    keys = (
        "run_id", "provider", "model", "purpose", "tokens_in", "tokens_out",
        "web_searches", "cost_usd", "price_verified", "ok", "note",
    )
    values = [fields.get(k) for k in keys]
    conn.execute(
        f"INSERT INTO calls (at, {', '.join(keys)})"
        f" VALUES (?, {', '.join('?' * len(keys))})",
        [now(), *values],
    )
    conn.commit()


def spent_usd(conn: sqlite3.Connection, since_prefix: str) -> float:
    """Suma kosztów od znacznika czasu zaczynającego się danym prefiksem.

    `since_prefix` to `YYYY-MM-DD` dla doby albo `YYYY-MM` dla miesiąca — daty są
    zapisane w ISO 8601 UTC, więc porównanie prefiksem wystarczy i nie wymaga
    drugiej reprezentacji czasu w bazie.
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) AS total FROM calls WHERE at LIKE ?",
        (f"{since_prefix}%",),
    ).fetchone()
    return float(row["total"])


def recent_domains(conn: sqlite3.Connection, limit: int) -> list[str]:
    """Domeny z ostatnich N artykułów — wejście do reguły różnorodności."""
    rows = conn.execute(
        "SELECT DISTINCT s.domain FROM sources s"
        " JOIN articles a ON a.run_id = s.run_id"
        " WHERE a.status = 'SAVED'"
        " AND a.run_id IN (SELECT run_id FROM articles WHERE status = 'SAVED'"
        "                  ORDER BY id DESC LIMIT ?)",
        (limit,),
    ).fetchall()
    return [r["domain"] for r in rows]
