"""Offline regressions for PR1-MAJ-005 runtime/migration separation."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from shutil import copy2
import sqlite3

import pytest

import app.main as main_module
import app.orchestrator.runner as orchestrator_module
import app.storage.db as db_module
import app.storage.repositories as repositories_module
import scripts.migrate_schema_0015 as migration_cli
import scripts.run_capped_research as capped_module
from app.storage.db import (
    ExplicitMigrationError,
    MIGRATIONS_DIR,
    RUNTIME_SCHEMA_VERSION,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    SchemaVersionTooOld,
    SchemaVersionUnavailable,
    database_schema_versions,
    initialize_database,
    migrate_0014_to_0015,
)
from app.storage.repositories import SqliteStorage


def _fingerprint(path: Path) -> tuple[str, int, int, tuple[bool, bool, bool]]:
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        stat.st_size,
        stat.st_mtime_ns,
        tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")),
    )


def _old_database(path: Path) -> None:
    initialize_database(path, through=STAGE1_SCHEMA_VERSION)
    assert database_schema_versions(path)[-1] == STAGE1_SCHEMA_VERSION
    assert _fingerprint(path)[3] == (False, False, False)


def _force_delete_journal_mode(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() == "delete"
    finally:
        conn.close()
    assert _fingerprint(path)[3] == (False, False, False)


def _durable_counts(path: Path) -> tuple[int, int, int, int, int]:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        return tuple(int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in (
            "jobs", "provider_attempts", "model_usage", "reconciliation_events", "system_flags",
        ))
    finally:
        conn.close()


def test_runtime_open_refuses_0014_without_any_file_or_ledger_mutation(tmp_path):
    path = tmp_path / "runtime-old.db"
    _old_database(path)
    _force_delete_journal_mode(path)
    before = (_fingerprint(path), database_schema_versions(path), _durable_counts(path))

    with pytest.raises(SchemaVersionTooOld, match="SCHEMA_VERSION_TOO_OLD"):
        SqliteStorage.open(path)

    after = (_fingerprint(path), database_schema_versions(path), _durable_counts(path))
    assert after == before


def test_runtime_open_does_not_recreate_database_deleted_after_preflight(
    tmp_path, settings, monkeypatch, capsys,
):
    path = tmp_path / "deleted-after-preflight.db"
    initialize_database(path)
    runtime_settings = replace(settings, db_path=path)
    monkeypatch.setattr(main_module, "load_settings", lambda: runtime_settings)
    original_preflight = repositories_module.require_database_schema
    prepared: list[bool] = []
    runtime_calls: list[bool] = []
    provider_boundary_calls: list[bool] = []

    def delete_after_preflight(db_path, **kwargs):
        versions = original_preflight(db_path, **kwargs)
        Path(db_path).unlink()
        return versions

    def forbidden_prepare(*_args, **_kwargs):
        prepared.append(True)
        raise AssertionError("writable preparation ran before the second schema gate")

    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker

    monkeypatch.setattr(repositories_module, "require_database_schema", delete_after_preflight)
    monkeypatch.setattr(repositories_module, "prepare_writable_connection", forbidden_prepare)
    monkeypatch.setattr(
        JobDispatcher, "__init__",
        lambda _self, *_args, **_kwargs: provider_boundary_calls.append(True),
    )
    monkeypatch.setattr(Worker, "run_once", lambda _self: runtime_calls.append(True))

    assert main_module.main(["worker", "--once", "--offline-only"]) == 7

    assert "SCHEMA_VERSION_UNAVAILABLE" in capsys.readouterr().err
    assert prepared == []
    assert runtime_calls == []
    assert provider_boundary_calls == []
    assert not path.exists()
    assert tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")) == (
        False, False, False,
    )


def test_runtime_open_refuses_0014_replaced_after_preflight_without_mutation(
    tmp_path, settings, monkeypatch, capsys,
):
    path = tmp_path / "replaced-after-preflight.db"
    replacement = tmp_path / "replacement-0014.db"
    initialize_database(path)
    _old_database(replacement)
    _force_delete_journal_mode(replacement)
    runtime_settings = replace(settings, db_path=path)
    monkeypatch.setattr(main_module, "load_settings", lambda: runtime_settings)
    original_preflight = repositories_module.require_database_schema
    replaced_state: dict[str, object] = {}
    prepared: list[bool] = []
    runtime_calls: list[bool] = []
    provider_boundary_calls: list[bool] = []

    def replace_after_preflight(db_path, **kwargs):
        versions = original_preflight(db_path, **kwargs)
        copy2(replacement, db_path)
        replaced_state["value"] = (
            _fingerprint(Path(db_path)),
            database_schema_versions(db_path),
            _durable_counts(Path(db_path)),
        )
        return versions

    def forbidden_prepare(*_args, **_kwargs):
        prepared.append(True)
        raise AssertionError("writable preparation ran before the second schema gate")

    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker

    monkeypatch.setattr(repositories_module, "require_database_schema", replace_after_preflight)
    monkeypatch.setattr(repositories_module, "prepare_writable_connection", forbidden_prepare)
    monkeypatch.setattr(
        JobDispatcher, "__init__",
        lambda _self, *_args, **_kwargs: provider_boundary_calls.append(True),
    )
    monkeypatch.setattr(Worker, "run_once", lambda _self: runtime_calls.append(True))

    assert main_module.main(["worker", "--once", "--offline-only"]) == 7

    assert "SCHEMA_VERSION_TOO_OLD" in capsys.readouterr().err
    assert prepared == []
    assert runtime_calls == []
    assert provider_boundary_calls == []
    assert (
        _fingerprint(path), database_schema_versions(path), _durable_counts(path),
    ) == replaced_state["value"]


def test_runtime_open_never_creates_or_migrates_a_missing_database(tmp_path):
    path = tmp_path / "missing" / "runtime.db"
    with pytest.raises(SchemaVersionUnavailable, match="does not exist"):
        SqliteStorage.open(path)
    assert not path.exists()
    assert not path.parent.exists()


def test_explicit_fresh_initialization_then_runtime_open_does_not_reapply_migrations(tmp_path):
    path = tmp_path / "fresh.db"
    applied = initialize_database(path)
    assert applied[-1] == RUNTIME_SCHEMA_VERSION
    before = database_schema_versions(path)
    storage = SqliteStorage.open(path)
    storage.close()
    after = database_schema_versions(path)
    assert before == after
    assert after[-1] == RUNTIME_SCHEMA_VERSION
    assert len(after) == 30


def test_runtime_open_uses_mode_rw_and_gates_before_writable_preparation(
    tmp_path, monkeypatch,
):
    path = tmp_path / "runtime-mode-rw.db"
    initialize_database(path)
    sqlite_calls: list[tuple[str, bool]] = []
    order: list[str] = []
    original_sqlite_connect = db_module.sqlite3.connect
    original_gate = repositories_module.require_connection_schema
    original_prepare = repositories_module.prepare_writable_connection

    def record_sqlite_connect(database, *args, **kwargs):
        sqlite_calls.append((str(database), kwargs.get("uri", False)))
        return original_sqlite_connect(database, *args, **kwargs)

    def record_gate(conn, **kwargs):
        order.append("schema_gate")
        return original_gate(conn, **kwargs)

    def record_prepare(conn, db_path):
        order.append("writable_preparation")
        return original_prepare(conn, db_path)

    monkeypatch.setattr(db_module.sqlite3, "connect", record_sqlite_connect)
    monkeypatch.setattr(repositories_module, "require_connection_schema", record_gate)
    monkeypatch.setattr(repositories_module, "prepare_writable_connection", record_prepare)

    storage = SqliteStorage.open(path)
    storage.close()

    assert order == ["schema_gate", "writable_preparation"]
    assert sum(uri and database.endswith("?mode=rw") for database, uri in sqlite_calls) == 1


def test_explicit_0014_to_0015_is_exact_and_second_pass_is_idempotent(tmp_path):
    path = tmp_path / "upgrade.db"
    _old_database(path)
    first = migrate_0014_to_0015(path)
    assert first.source_version == STAGE1_SCHEMA_VERSION
    assert first.target_version == SETTLED_RECOVERY_SCHEMA_VERSION
    assert first.applied_migrations == (SETTLED_RECOVERY_SCHEMA_VERSION,)
    assert first.idempotent is False
    assert len(database_schema_versions(path)) == 15

    second_before = _fingerprint(path)
    second = migrate_0014_to_0015(path)
    assert second.applied_migrations == ()
    assert second.idempotent is True
    assert _fingerprint(path) == second_before


def test_explicit_0014_to_0015_fails_closed_for_wrong_source(tmp_path):
    path = tmp_path / "wrong-source.db"
    initialize_database(path, through="0009_jobs_system_flags")
    before = (_fingerprint(path), database_schema_versions(path))
    with pytest.raises(ExplicitMigrationError, match="requires exact"):
        migrate_0014_to_0015(path)
    assert (_fingerprint(path), database_schema_versions(path)) == before


def test_explicit_0015_rolls_back_ledger_and_partial_schema_on_fault(tmp_path):
    path = tmp_path / "rollback.db"
    _old_database(path)
    migration_dir = tmp_path / "faulty-migrations"
    migration_dir.mkdir()
    source = MIGRATIONS_DIR / f"{SETTLED_RECOVERY_SCHEMA_VERSION}.sql"
    target = migration_dir / source.name
    copy2(source, target)
    target.write_text(
        source.read_text(encoding="utf-8") + "\nTHIS IS A CONTROLLED INVALID STATEMENT;\n",
        encoding="utf-8",
    )
    before = (_fingerprint(path), database_schema_versions(path))

    with pytest.raises(Exception, match="syntax|near"):
        migrate_0014_to_0015(path, migrations_dir=migration_dir)

    assert database_schema_versions(path) == before[1]
    check = SqliteStorage.open_read_only(path)
    try:
        assert check.conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version=?",
            (SETTLED_RECOVERY_SCHEMA_VERSION,),
        ).fetchone()[0] == 0
        assert check.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='reconciliation_events_0014_old'"
        ).fetchone()[0] == 0
    finally:
        check.close()


def test_explicit_migration_cli_requires_confirmation_and_is_idempotent(tmp_path, capsys):
    path = tmp_path / "cli-upgrade.db"
    _old_database(path)
    assert migration_cli.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == STAGE1_SCHEMA_VERSION
    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0014-to-0015",
    ]) == 0
    assert migration_cli.main([
        "--db-path", str(path), "--confirm-0014-to-0015",
    ]) == 0
    output = capsys.readouterr()
    assert "idempotent=true" in output.out


_MAIN_RUNTIME_CASES = (
    ("run-topics", ["run-topics", "--count", "1"], 7),
    ("run-research", ["run-research"], 7),
    ("enqueue", ["enqueue-research", "--account-id", "nothing_is_accidental", "--topic-id", "1"], 7),
    ("worker", ["worker", "--once", "--offline-only"], 7),
    ("reaper", ["reap-runs", "--once", "--stale-after-seconds", "60"], 7),
    ("maintenance", ["maintain", "--once", "--stale-after-seconds", "60"], 1),
    ("controlled-live", [
        "controlled-live-once", "--topic-id", "1", "--operation-key", "schema-gate",
        "--model", "fake", "--pricing-profile", "fake", "--max-tokens", "6000",
        "--max-cost-usd", "0.20", "--expected-db-sha", "0" * 64,
        "--expected-schema", RUNTIME_SCHEMA_VERSION, "--expected-branch", "test",
        "--expected-head", "0" * 40,
    ], 7),
    ("reconcile", [
        "reconcile-attempt", "--request-id", "missing", "--account-id", "nothing_is_accidental",
        "--financial-resolution", "CHARGED_KNOWN", "--execution-resolution", "EXECUTION_FAILED",
        "--actual-cost-usd", "0.01", "--reconciled-by", "test", "--note", "schema gate",
    ], 6),
)


@pytest.mark.parametrize("_name,argv,expected_exit", _MAIN_RUNTIME_CASES)
def test_all_main_writable_composition_roots_fail_closed_on_0014(
    _name, argv, expected_exit, tmp_path, settings, monkeypatch, capsys,
):
    path = tmp_path / f"{_name}.db"
    _old_database(path)
    old_settings = replace(settings, db_path=path)
    old_settings.editorial_schedule = {
        "timezone": "Europe/Bucharest",
        "windows": [{
            "weekdays": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00",
        }],
    }
    monkeypatch.setattr(main_module, "load_settings", lambda: old_settings)
    monkeypatch.setattr(orchestrator_module, "load_settings", lambda: old_settings)
    before = (_fingerprint(path), database_schema_versions(path), _durable_counts(path))

    assert main_module.main(argv) == expected_exit

    captured = capsys.readouterr()
    assert "SCHEMA_VERSION_TOO_OLD" in captured.err
    assert (_fingerprint(path), database_schema_versions(path), _durable_counts(path)) == before


def test_capped_research_root_fails_closed_on_0014(tmp_path, settings, monkeypatch, capsys):
    path = tmp_path / "capped.db"
    _old_database(path)
    old_settings = replace(settings, db_path=path)
    monkeypatch.setattr(capped_module, "load_settings", lambda: old_settings)
    before = (_fingerprint(path), database_schema_versions(path), _durable_counts(path))

    assert capped_module.main(["--topic-id", "1", "--estimate-only"]) == 2

    assert "SCHEMA_VERSION_TOO_OLD" in capsys.readouterr().out
    assert (_fingerprint(path), database_schema_versions(path), _durable_counts(path)) == before


def test_read_only_operator_roots_remain_available_without_migrating_0014(
    tmp_path, settings, monkeypatch,
):
    path = tmp_path / "read-only.db"
    _old_database(path)
    old_settings = replace(settings, db_path=path)
    monkeypatch.setattr(main_module, "load_settings", lambda: old_settings)
    before = (_fingerprint(path), database_schema_versions(path), _durable_counts(path))

    assert main_module.main(["list-reconciliations"]) == 0
    assert main_module.main(["operational-report"]) in (0, 2)

    after = (_fingerprint(path)[:3], database_schema_versions(path), _durable_counts(path))
    assert after == (before[0][:3], before[1], before[2])
