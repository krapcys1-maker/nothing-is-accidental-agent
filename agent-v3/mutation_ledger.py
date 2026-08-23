"""Trwały, fail-closed ledger prób mutujących.

Rezerwacja jest commitowana przed kliknięciem. Stan po dispatch bez dokładnego
zewnętrznego ID nigdy nie staje się sukcesem i blokuje automatyczne ponowienie.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import db
import operational_day


BLOCKING_STATES = frozenset({"PENDING", "UNKNOWN", "CONFIRMED"})
FINAL_STATES = frozenset({"UNKNOWN", "CONFIRMED", "FAILED"})
KEY_VERSION = 1


class MutationBlocked(RuntimeError):
    """Istniejąca próba zabrania automatycznego ponowienia."""

    def __init__(self, status: str, attempt_id: str) -> None:
        self.status = status
        self.attempt_id = attempt_id
        super().__init__(
            f"mutacja zablokowana przez {status} próby {attempt_id}"
        )


class InvalidTransition(RuntimeError):
    """Próba przejścia niezgodnego z maszyną stanów."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _canonical(value: str) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def identity(
    *, account: str, kind: str, target: str, payload: str
) -> tuple[str, str]:
    payload_hash = hashlib.sha256(
        _canonical(payload).encode("utf-8")
    ).hexdigest()
    envelope = {
        "version": KEY_VERSION,
        "account": _canonical(account).lower(),
        "kind": _canonical(kind).lower(),
        "target": _canonical(target),
        "payload_sha256": payload_hash,
    }
    raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), payload_hash


@dataclass
class Attempt:
    db_path: Path
    id: str
    idempotency_key: str
    sequence: int
    status: str = "PENDING"
    dispatched: bool = False

    def _connect(self) -> sqlite3.Connection:
        return db.connect(self.db_path)

    def dispatch(self) -> None:
        if self.status != "PENDING" or self.dispatched:
            raise InvalidTransition("dispatch wymaga niewysłanego PENDING")
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE mutation_attempts SET dispatched_at = ? "
                "WHERE id = ? AND status = 'PENDING' AND dispatched_at IS NULL",
                (_now(), self.id),
            )
            if cur.rowcount != 1:
                raise InvalidTransition("nie udało się utrwalić dispatch")
            conn.commit()
            self.dispatched = True
        finally:
            conn.close()

    def confirm(self, source_ref: str, metadata: dict[str, Any] | None = None) -> None:
        reference = _canonical(str(source_ref or ""))
        if self.status != "PENDING" or not self.dispatched:
            raise InvalidTransition("confirm wymaga PENDING po dispatch")
        if not reference:
            raise InvalidTransition("CONFIRMED wymaga source_ref")
        self._finish("CONFIRMED", source_ref=reference, metadata=metadata)

    def unknown(self, error: str = "",
                metadata: dict[str, Any] | None = None) -> None:
        if self.status != "PENDING" or not self.dispatched:
            raise InvalidTransition("UNKNOWN wymaga PENDING po dispatch")
        self._finish("UNKNOWN", error=error, metadata=metadata)

    def fail(self, error: str = "",
             metadata: dict[str, Any] | None = None) -> None:
        if self.status != "PENDING" or self.dispatched:
            raise InvalidTransition("FAILED jest dozwolone tylko przed dispatch")
        self._finish("FAILED", error=error, metadata=metadata)

    def _finish(
        self, status: str, *, source_ref: str = "", error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if status not in FINAL_STATES:
            raise InvalidTransition(f"nieznany stan końcowy {status!r}")
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE mutation_attempts SET status = ?, finished_at = ?, "
                "source_ref = ?, error = ?, result_json = ? "
                "WHERE id = ? AND status = 'PENDING'",
                (
                    status, _now(), source_ref or None, error[:1000] or None,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    self.id,
                ),
            )
            if cur.rowcount != 1:
                raise InvalidTransition("próba nie jest już PENDING")
            operational_day.finish_reservation(
                conn, attempt_id=self.id, attempt_status=status)
            conn.commit()
            self.status = status
        finally:
            conn.close()

    def __enter__(self) -> "Attempt":
        return self

    def __exit__(self, exc_type, exc, _traceback) -> bool:
        if self.status != "PENDING":
            return False
        reason = (
            f"{exc_type.__name__}: {exc}" if exc_type is not None
            else "blok zakończony bez jawnego stanu"
        )
        if self.dispatched:
            self.unknown(reason)
        else:
            self.fail(reason)
        return False


def reserve(
    db_path: Path, *, account: str, kind: str, target: str, payload: str,
    metadata: dict[str, Any] | None = None,
) -> Attempt:
    """Atomowo rezerwuje próbę albo odmawia dla blokującego poprzednika."""
    key, payload_hash = identity(
        account=account, kind=kind, target=target, payload=payload)
    budget_category = operational_day.category_for(kind)
    conn = db.connect(db_path)
    attempt_id = uuid.uuid4().hex
    try:
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute(
            "SELECT id, sequence, status FROM mutation_attempts "
            "WHERE idempotency_key = ? ORDER BY sequence DESC LIMIT 1",
            (key,),
        ).fetchone()
        if previous and previous["status"] in BLOCKING_STATES:
            conn.rollback()
            raise MutationBlocked(previous["status"], previous["id"])
        uncertain = conn.execute(
            "SELECT id, status FROM mutation_attempts "
            "WHERE status IN ('PENDING', 'UNKNOWN') "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if uncertain:
            conn.rollback()
            raise MutationBlocked(uncertain["status"], uncertain["id"])
        sequence = int(previous["sequence"]) + 1 if previous else 1
        if budget_category is not None:
            day = operational_day.get_or_create(conn, account=account)
            operational_day.reserve_units(
                conn, day=day, attempt_id=attempt_id,
                category=budget_category,
            )
        conn.execute(
            "INSERT INTO mutation_attempts "
            "(id, idempotency_key, sequence, account, kind, target, "
            "payload_sha256, created_at, status, request_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)",
            (
                attempt_id, key, sequence, _canonical(account).lower(),
                _canonical(kind).lower(), _canonical(target), payload_hash,
                _now(),
                json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return Attempt(Path(db_path), attempt_id, key, sequence)


def recover_pending(db_path: Path) -> dict[str, int]:
    """Domyka próby przerwane przez poprzedni proces.

    Funkcję wolno wywołać dopiero po zdobyciu wyłącznego zamka procesu. Jeżeli
    dispatch nie został trwale zapisany, mutacja nie mogła jeszcze nastąpić i
    próbę można oznaczyć FAILED. Zapisany dispatch bez wyniku staje się UNKNOWN
    i nadal blokuje ponowienie.
    """
    conn = db.connect(db_path)
    recovered = {"FAILED": 0, "UNKNOWN": 0}
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, dispatched_at FROM mutation_attempts "
            "WHERE status = 'PENDING'"
        ).fetchall()
        for row in rows:
            status = "UNKNOWN" if row["dispatched_at"] else "FAILED"
            error = (
                "restart po utrwalonym dispatch"
                if status == "UNKNOWN"
                else "restart przed dispatch"
            )
            conn.execute(
                "UPDATE mutation_attempts SET status = ?, finished_at = ?, "
                "error = ? WHERE id = ? AND status = 'PENDING'",
                (status, _now(), error, row["id"]),
            )
            operational_day.finish_reservation(
                conn, attempt_id=row["id"], attempt_status=status)
            recovered[status] += 1
        conn.commit()
        return recovered
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def get_attempt(db_path: Path, attempt_id: str) -> dict[str, Any] | None:
    conn = db.connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM mutation_attempts WHERE id = ?", (attempt_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
