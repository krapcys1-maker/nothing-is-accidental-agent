"""Read-only and honest-UNKNOWN contracts for the Stage 1 operational report."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app import main as app_main
from app.models import OperationalFieldStatus
from app.operations.stage1_migration import fingerprint
from app.storage.db import MIGRATIONS_DIR, apply_migrations
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _create_schema_0009(path: Path, migration_dir: Path) -> None:
    migration_dir.mkdir()
    for source in sorted(MIGRATIONS_DIR.glob("*.sql"))[:9]:
        (migration_dir / source.name).write_bytes(source.read_bytes())
    conn = sqlite3.connect(path)
    try:
        assert len(apply_migrations(conn, migration_dir)) == 9
    finally:
        conn.close()


def test_report_connection_is_query_only_and_does_not_change_database(settings):
    writer = SqliteStorage.open(settings.db_path)
    writer.apply_security_flag_profile([
        ("worker_enabled", False),
        ("safe_mode", False),
        ("paid_actions_enabled", False),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", now=NOW)
    writer.close()
    before = fingerprint(settings.db_path)

    reader = SqliteStorage.open_read_only(settings.db_path)
    try:
        assert reader.conn.execute("PRAGMA query_only").fetchone()[0] == 1
        report = reader.read_operational_report(now=NOW)
        assert report.schema_migrations.value == 27
        assert report.job_counts is not None
        assert all(value == 0 for value in report.job_counts.values())
        assert report.needs_reconciliation_attempts.value == 0
        assert report.active_reserved_cost_usd.value == "0.000000"
        assert report.last_maintenance_at.status is OperationalFieldStatus.UNKNOWN
        assert "last maintenance-cycle timestamp" in " ".join(report.unknown_reasons)
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            reader.conn.execute("CREATE TABLE forbidden_write(id INTEGER)")
    finally:
        reader.close()
    assert fingerprint(settings.db_path) == before


def test_pre_0010_reconciliation_and_missing_flags_are_unknown_not_zero(tmp_path: Path):
    db_path = tmp_path / "schema-0009.db"
    _create_schema_0009(db_path, tmp_path / "migrations-0009")
    reader = SqliteStorage.open_read_only(db_path)
    try:
        report = reader.read_operational_report(now=NOW)
    finally:
        reader.close()
    assert report.schema_migrations.value == 9
    assert report.needs_reconciliation_attempts.status is OperationalFieldStatus.UNKNOWN
    assert report.needs_reconciliation_attempts.value is None
    assert all(
        flag.status is OperationalFieldStatus.UNKNOWN
        for flag in report.system_flags.values()
    )
    assert not report.complete


def test_operational_report_cli_is_read_only_and_has_controlled_degraded_exit(
    settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
):
    writer = SqliteStorage.open(settings.db_path)
    writer.close()
    before = fingerprint(settings.db_path)
    monkeypatch.setattr(app_main, "load_settings", lambda: replace(settings))
    assert app_main.main(["operational-report"]) == 2
    output = capsys.readouterr().out
    assert "READ ONLY" in output
    assert "UNKNOWN/BLOCKED" in output
    assert "REPORT_STATUS=DEGRADED_UNKNOWN" in output
    assert fingerprint(settings.db_path) == before


def test_importing_report_cli_does_not_load_provider_sdk():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; before=set(sys.modules); import app.main; "
                "loaded=set(sys.modules)-before; "
                "assert not any(x == 'anthropic' or x.startswith('anthropic.') for x in loaded)"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
