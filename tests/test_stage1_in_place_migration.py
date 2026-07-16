"""Independent countertests for the canonical Stage 1 in-place executor."""
from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import sqlite3

import pytest

from app.core.security_flags import SECURITY_FLAG_DEFAULTS
import app.operations.stage1_migration as migration
from app.operations.stage1_migration import (
    MIGRATIONS_0010_TO_0014,
    QuiesceReport,
    Stage1MigrationPreflightError,
    Stage1MigrationRequest,
    database_file_set_fingerprint,
    fingerprint,
    run_stage1_in_place_migration,
)
from app.storage import db as storage_db
from app.storage.db import MIGRATIONS_DIR, apply_migrations


BRANCH = "dev/first-successful-research-card"
HEAD = "0658e8b221b99bcdaa549cf538ee140a9dc02613"
NOW = datetime(2026, 7, 16, 16, 0, tzinfo=timezone.utc)


def _production_shape_0009(path: Path, migration_dir: Path) -> None:
    migration_dir.mkdir(parents=True)
    for source in sorted(MIGRATIONS_DIR.glob("*.sql"))[:9]:
        (migration_dir / source.name).write_bytes(source.read_bytes())
    conn = sqlite3.connect(path)
    try:
        assert len(apply_migrations(conn, migration_dir)) == 9
        conn.execute(
            "INSERT INTO accounts(id,name,mode,autonomy_level,active,browser_profile_path,"
            "writing_profile_path) VALUES (?,?,?,?,?,?,?)",
            ("acc", "Account", "RESEARCH_ONLY", "LEVEL_1", 1, "", ""),
        )
        costs = ["0.050000"] * 12 + ["0.084580"]
        for index, cost in enumerate(costs, start=1):
            run_id = f"legacy-run-{index:02d}"
            conn.execute(
                "INSERT INTO runs(id,account_id,workflow,status,cost_usd) VALUES (?,?,?,?,?)",
                (run_id, "acc", "ANALYTICS", "SUCCESS", float(cost)),
            )
            conn.execute(
                "INSERT INTO model_usage(run_id,model,task,estimated_cost_usd,dry_run) "
                "VALUES (?,?,?,?,0)",
                (run_id, "legacy-model", "legacy", float(cost)),
            )
        conn.commit()
    finally:
        conn.close()


def _case(tmp_path: Path) -> tuple[Path, Path, Stage1MigrationRequest]:
    project = tmp_path / "project"
    source = project / "data" / "agent.db"
    source.parent.mkdir(parents=True)
    _production_shape_0009(source, project / "migrations-0009")
    baseline = fingerprint(source)
    workspace = tmp_path / "migration-workspace"
    request = Stage1MigrationRequest(
        project_root=project,
        source_db=source,
        workspace=workspace,
        expected_branch=BRANCH,
        expected_head=HEAD,
        expected_source_sha256=baseline.sha256,
        expected_source_size=baseline.size,
        expected_source_mtime_utc=baseline.mtime_utc,
    )
    return source, workspace, request


def _run(request: Stage1MigrationRequest):
    return run_stage1_in_place_migration(
        request,
        confirm_in_place_production_migration=True,
        git_identity_provider=lambda root: (BRANCH, HEAD),
        quiesce_probe=lambda root, source: QuiesceReport(),
        now=NOW,
    )


def test_counter_01_wal_absent_passes(tmp_path: Path):
    source, _, request = _case(tmp_path)
    assert not Path(f"{source}-wal").exists()
    result = _run(request)
    assert result.applied_migrations == MIGRATIONS_0010_TO_0014


def test_counter_02_zero_byte_wal_passes(tmp_path: Path):
    source, _, request = _case(tmp_path)
    Path(f"{source}-wal").write_bytes(b"")
    result = _run(request)
    assert result.source_before.wal is not None
    assert result.source_before.wal.size == 0


def test_counter_03_present_shm_passes_and_is_reported(tmp_path: Path):
    source, _, request = _case(tmp_path)
    Path(f"{source}-shm").write_bytes(b"\0" * 32768)
    result = _run(request)
    assert result.source_before.shm is not None
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["source_before"]["shm"]["size"] == 32768


def test_counter_04_nonempty_wal_stops_before_workspace(tmp_path: Path):
    source, workspace, request = _case(tmp_path)
    Path(f"{source}-wal").write_bytes(b"uncheckpointed")
    with pytest.raises(Stage1MigrationPreflightError, match="WAL is non-empty"):
        _run(request)
    assert not workspace.exists()


def test_counter_05_rollback_journal_stops_before_workspace(tmp_path: Path):
    source, workspace, request = _case(tmp_path)
    Path(f"{source}-journal").write_bytes(b"journal")
    with pytest.raises(Stage1MigrationPreflightError, match="rollback journal"):
        _run(request)
    assert not workspace.exists()


def test_counter_06_active_writer_or_handle_stops(tmp_path: Path):
    source, workspace, request = _case(tmp_path)
    if os.name == "nt":
        writer = sqlite3.connect(source)
        try:
            writer.execute("BEGIN IMMEDIATE")
            assert str(source.resolve()) in migration._windows_locked_paths(source.resolve())
        finally:
            writer.rollback()
            writer.close()
    with pytest.raises(Stage1MigrationPreflightError, match="Full quiescence"):
        run_stage1_in_place_migration(
            request,
            confirm_in_place_production_migration=True,
            git_identity_provider=lambda root: (BRANCH, HEAD),
            quiesce_probe=lambda root, path: QuiesceReport(locked_paths=(str(source),)),
            now=NOW,
        )
    assert not workspace.exists()


def test_counter_07_database_drift_before_mutation_stops(monkeypatch, tmp_path: Path):
    source, _, request = _case(tmp_path)
    real_fingerprint = migration.database_file_set_fingerprint
    source_calls = 0

    def drifting_fingerprint(path):
        nonlocal source_calls
        resolved = Path(path).resolve()
        if resolved == source.resolve():
            source_calls += 1
            if source_calls == 6:
                stat = source.stat()
                os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        return real_fingerprint(path)

    monkeypatch.setattr(migration, "database_file_set_fingerprint", drifting_fingerprint)
    with pytest.raises(Stage1MigrationPreflightError, match="drifted"):
        _run(request)
    conn = sqlite3.connect(source)
    try:
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 9
    finally:
        conn.close()


def test_counter_08_wal_drift_between_gates_stops(monkeypatch, tmp_path: Path):
    source, _, request = _case(tmp_path)
    wal = Path(f"{source}-wal")
    wal.write_bytes(b"")
    real_fingerprint = migration.database_file_set_fingerprint
    source_calls = 0

    def drifting_fingerprint(path):
        nonlocal source_calls
        if Path(path).resolve() == source.resolve():
            source_calls += 1
            if source_calls == 6:
                wal.write_bytes(b"late-writer")
        return real_fingerprint(path)

    monkeypatch.setattr(migration, "database_file_set_fingerprint", drifting_fingerprint)
    with pytest.raises(Stage1MigrationPreflightError, match="WAL is non-empty"):
        _run(request)


def test_counter_09_confirmation_and_wrong_git_identity_stop(tmp_path: Path):
    source, workspace, request = _case(tmp_path)
    with pytest.raises(Stage1MigrationPreflightError, match="Explicit"):
        run_stage1_in_place_migration(
            request,
            confirm_in_place_production_migration=False,
            git_identity_provider=lambda root: (BRANCH, HEAD),
            quiesce_probe=lambda root, path: QuiesceReport(),
        )
    with pytest.raises(Stage1MigrationPreflightError, match="Git identity mismatch"):
        run_stage1_in_place_migration(
            request,
            confirm_in_place_production_migration=True,
            git_identity_provider=lambda root: ("main", "bad-head"),
            quiesce_probe=lambda root, path: QuiesceReport(),
        )
    assert fingerprint(source).sha256 == request.expected_source_sha256
    assert not workspace.exists()


def test_counter_10_two_security_profiles_are_impossible():
    import app.storage.repositories as repositories

    assert migration.SECURITY_FLAG_DEFAULTS is SECURITY_FLAG_DEFAULTS
    assert repositories.SECURITY_FLAG_DEFAULTS is SECURITY_FLAG_DEFAULTS
    assert dict(SECURITY_FLAG_DEFAULTS) == {
        "kill_switch": True,
        "safe_mode": True,
        "worker_enabled": False,
        "paid_actions_enabled": False,
        "browser_actions_enabled": False,
    }
    with pytest.raises(TypeError):
        SECURITY_FLAG_DEFAULTS["kill_switch"] = False  # type: ignore[index]
    assert not hasattr(migration, "STAGE1_BLOCKED_FLAGS")
    assert not hasattr(repositories, "_SECURITY_FLAG_DEFAULTS")


def test_counter_11_canonical_migration_runner_is_used(monkeypatch, tmp_path: Path):
    _, _, request = _case(tmp_path)
    calls: list[tuple[str, ...]] = []

    def recording_runner(conn):
        applied = tuple(storage_db.apply_migrations(conn))
        calls.append(applied)
        return list(applied)

    monkeypatch.setattr(migration, "apply_migrations", recording_runner)
    result = _run(request)
    assert result.applied_migrations == MIGRATIONS_0010_TO_0014
    assert calls == [MIGRATIONS_0010_TO_0014, (), MIGRATIONS_0010_TO_0014]


def test_counter_12_post_migration_failure_forces_full_restore(monkeypatch, tmp_path: Path):
    source, workspace, request = _case(tmp_path)
    before = database_file_set_fingerprint(source)
    real_verify = migration._verify_migrated_database
    calls = 0

    def failing_post_verify(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise Stage1MigrationPreflightError("injected post-migration failure")
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(migration, "_verify_migrated_database", failing_post_verify)
    with pytest.raises(Stage1MigrationPreflightError, match="restore was independently verified"):
        _run(request)
    assert database_file_set_fingerprint(source) == before
    report = json.loads(
        (workspace / "stage1-in-place-migration-report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "PRODUCTION_MIGRATION_FAILED_FULL_RESTORE_VERIFIED"
    assert not (workspace / "stage1-new-baseline.json").exists()


def test_counter_13_restore_reproduces_db_wal_shm_bitwise(tmp_path: Path):
    source, workspace, _ = _case(tmp_path)
    Path(f"{source}-wal").write_bytes(b"")
    Path(f"{source}-shm").write_bytes(b"valid-metadata" * 2048)
    expected = database_file_set_fingerprint(source)
    backup = migration._copy_file_set(source, workspace / "backup", expected)
    source.write_bytes(b"corrupt")
    Path(f"{source}-wal").write_bytes(b"dirty")
    Path(f"{source}-shm").unlink()
    restored = migration._restore_file_set(source, backup, expected)
    assert restored == expected


def test_counter_14_executor_has_no_live_api_or_cost_path(tmp_path: Path):
    source, _, request = _case(tmp_path)
    conn = sqlite3.connect(source)
    try:
        before_cost = conn.execute(
            "SELECT printf('%.6f',SUM(estimated_cost_usd)) FROM model_usage WHERE dry_run=0"
        ).fetchone()[0]
    finally:
        conn.close()
    result = _run(request)
    conn = sqlite3.connect(source)
    try:
        after_cost = conn.execute(
            "SELECT printf('%.6f',SUM(estimated_cost_usd)) FROM model_usage WHERE dry_run=0"
        ).fetchone()[0]
    finally:
        conn.close()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert before_cost == after_cost == "0.684580"
    assert report["live_api_used"] is False
    assert report["paid_actions"] is False
    assert report["browser_actions"] is False
    source_code = inspect.getsource(migration.run_stage1_in_place_migration)
    assert "requests." not in source_code
    assert "anthropic" not in source_code.lower()
