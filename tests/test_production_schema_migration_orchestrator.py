"""Offline contract tests for the sole production 0014->0018 orchestrator.

Every writable operation targets a fresh pytest database.  The project
``data/agent.db`` is never passed to the orchestrator.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

import app.operations.production_schema_migration as migration_module
import scripts.migrate_production_schema_0014_to_0018 as migration_cli
from app.operations.production_schema_migration import (
    MIGRATION_SEQUENCE,
    SUPPORTED_FROM_VERSION,
    SUPPORTED_TARGET_VERSION,
    ProductionMigrationError,
    ProductionMigrationRequest,
    run_production_schema_migration,
)
from app.storage.db import (
    CONTROLLED_FETCH_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0014_to_0015,
)


QUIESCENT = lambda _path: ()  # noqa: E731


@pytest.fixture(autouse=True)
def _frozen_supported_0018_ladder(monkeypatch):
    """Pin the CLOSED 0014->0018 orchestrator to its frozen 18-step ladder.

    Wykonana i zamknięta produkcyjna migracja 0014->0018 była zwalidowana na
    dokładnej drabinie 0001..0018.  Repo zawiera już 0019 (E3), więc w realnym
    repozytorium orchestrator odmawia trwale fail-closed
    (MIGRATION_CONTRACT_INVALID — pinowane osobnym testem w
    test_e3_migration_0019.py).  Te historyczne testy nadal dowodzą pełnego
    zachowania narzędzia względem JEGO zamrożonego kontraktu.
    """
    from app.storage.db import MIGRATIONS_DIR, canonical_migration_versions

    real = canonical_migration_versions()
    frozen = tuple(
        version for version in real
        if version <= CONTROLLED_FETCH_SCHEMA_VERSION
    )
    assert len(frozen) == 18 and frozen[-1] == CONTROLLED_FETCH_SCHEMA_VERSION

    def frozen_ladder(migrations_dir=MIGRATIONS_DIR):
        del migrations_dir
        return frozen

    monkeypatch.setattr(
        migration_module, "canonical_migration_versions", frozen_ladder,
    )


def _force_delete_journal_mode(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "PRAGMA journal_mode=DELETE"
        ).fetchone()[0].lower() == "delete"
    finally:
        connection.close()


def _fingerprint(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper(), path.stat().st_size


def _sidecars(path: Path) -> tuple[bool, bool, bool]:
    return tuple(
        Path(f"{path}{suffix}").exists()
        for suffix in ("-wal", "-shm", "-journal")
    )


def _case(
    tmp_path: Path,
    *,
    version: str = STAGE1_SCHEMA_VERSION,
) -> tuple[Path, Path]:
    source_dir = tmp_path / "database"
    snapshot_dir = tmp_path / "snapshots"
    source_dir.mkdir()
    snapshot_dir.mkdir()
    source = source_dir / "candidate.db"
    snapshot = snapshot_dir / "candidate-before-migration.db"
    initialize_database(source, through=version)
    _force_delete_journal_mode(source)
    assert _sidecars(source) == (False, False, False)
    return source.resolve(), snapshot.resolve()


def _request(
    source: Path,
    snapshot: Path,
    *,
    confirmed: bool = True,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    expected_from_version: str = SUPPORTED_FROM_VERSION,
    target_version: str = SUPPORTED_TARGET_VERSION,
) -> ProductionMigrationRequest:
    sha256, size = _fingerprint(source)
    return ProductionMigrationRequest(
        db_path=source,
        expected_sha256=expected_sha256 or sha256,
        expected_size=size if expected_size is None else expected_size,
        expected_from_version=expected_from_version,
        target_version=target_version,
        snapshot_path=snapshot,
        confirmed_0014_to_0018=confirmed,
    )


def _run(
    request: ProductionMigrationRequest,
    *,
    failpoint=None,
    quiescence_probe=QUIESCENT,
):
    return run_production_schema_migration(
        request,
        quiescence_probe=quiescence_probe,
        failpoint=failpoint,
    )


def _assert_refusal_without_source_mutation(
    source: Path,
    snapshot: Path,
    request: ProductionMigrationRequest,
    expected_code: str,
    **run_kwargs,
) -> ProductionMigrationError:
    before = _fingerprint(source)
    with pytest.raises(ProductionMigrationError) as caught:
        _run(request, **run_kwargs)
    assert caught.value.code == expected_code
    assert _fingerprint(source) == before
    assert not snapshot.exists()
    return caught.value


def test_preflight_accepts_exact_path_sha_size_and_0014(tmp_path):
    source, snapshot = _case(tmp_path)
    result = _run(_request(source, snapshot))
    assert result.status == "MIGRATION_COMPLETE"
    assert result.source_version == STAGE1_SCHEMA_VERSION
    assert result.applied_migrations == MIGRATION_SEQUENCE
    assert snapshot.read_bytes() != source.read_bytes()
    assert result.snapshot is not None
    assert result.snapshot.sha256 == result.database_before.sha256
    assert result.snapshot.size == result.database_before.size
    assert database_schema_versions(source)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("sha", "DATABASE_SHA256_MISMATCH"),
        ("size", "DATABASE_SIZE_MISMATCH"),
        ("path", "DATABASE_SHA256_MISMATCH"),
    ),
)
def test_preflight_rejects_wrong_identity_fields(tmp_path, mutation, expected_code):
    source, snapshot = _case(tmp_path)
    request = _request(source, snapshot)
    if mutation == "sha":
        request = _request(source, snapshot, expected_sha256="00" * 32)
    elif mutation == "size":
        request = _request(source, snapshot, expected_size=source.stat().st_size + 1)
    else:
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        other = other_dir / "other.db"
        initialize_database(other, through=STAGE1_SCHEMA_VERSION)
        _force_delete_journal_mode(other)
        connection = sqlite3.connect(other)
        try:
            connection.execute("PRAGMA user_version=77")
            connection.commit()
        finally:
            connection.close()
        _force_delete_journal_mode(other)
        request = ProductionMigrationRequest(
            **{**request.__dict__, "db_path": other.resolve()}
        )
        source = other.resolve()
    _assert_refusal_without_source_mutation(
        source, snapshot, request, expected_code,
    )


def test_preflight_rejects_noncanonical_relative_path(tmp_path):
    source, snapshot = _case(tmp_path)
    request = ProductionMigrationRequest(
        **{**_request(source, snapshot).__dict__, "db_path": Path("relative.db")}
    )
    with pytest.raises(ProductionMigrationError, match="DATABASE_PATH_NOT_CANONICAL"):
        _run(request)
    assert not snapshot.exists()


def test_preflight_rejects_hardlink_alias_when_supported(tmp_path):
    source, snapshot = _case(tmp_path)
    alias = source.with_name("alias.db")
    try:
        os.link(source, alias)
    except OSError as exc:
        pytest.skip(f"filesystem does not support hard links: {exc}")
    _assert_refusal_without_source_mutation(
        source,
        snapshot,
        _request(source, snapshot),
        "DATABASE_PATH_ALIAS_DETECTED",
    )


def test_preflight_rejects_schema_before_supported_start(tmp_path):
    source, snapshot = _case(tmp_path, version="0013_provider_attempt_usage_integrity")
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "UNSUPPORTED_SCHEMA_STATE",
    )


def test_preflight_rejects_future_schema_without_mutation(tmp_path):
    source, snapshot = _case(tmp_path, version=CONTROLLED_FETCH_SCHEMA_VERSION)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES ('0019_future_schema')"
        )
        connection.commit()
    finally:
        connection.close()
    _force_delete_journal_mode(source)
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "FUTURE_SCHEMA_VERSION",
    )


def test_preflight_rejects_missing_ledger(tmp_path):
    source, snapshot = _case(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("ALTER TABLE schema_migrations RENAME TO hidden_ledger")
        connection.commit()
    finally:
        connection.close()
    _force_delete_journal_mode(source)
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "MIGRATION_LEDGER_MISSING",
    )


def test_preflight_rejects_duplicate_ledger(tmp_path):
    source, snapshot = _case(tmp_path)
    connection = sqlite3.connect(source)
    try:
        rows = connection.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        connection.execute("ALTER TABLE schema_migrations RENAME TO original_ledger")
        connection.execute(
            "CREATE TABLE schema_migrations(version TEXT, applied_at TEXT)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?,?)",
            rows + [rows[-1]],
        )
        connection.commit()
    finally:
        connection.close()
    _force_delete_journal_mode(source)
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "MIGRATION_LEDGER_DUPLICATE",
    )


def test_preflight_rejects_integrity_failure_on_throwaway_copy(tmp_path):
    source, snapshot = _case(tmp_path)
    connection = sqlite3.connect(source)
    try:
        index_name = connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type='index' AND rootpage>0 LIMIT 1"
        ).fetchone()[0]
        connection.execute("PRAGMA writable_schema=ON")
        connection.execute(
            "UPDATE sqlite_master SET rootpage=999999 WHERE name=?",
            (index_name,),
        )
        connection.execute("PRAGMA writable_schema=OFF")
        connection.commit()
    finally:
        connection.close()
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "DATABASE_INTEGRITY_FAILED",
    )


def test_preflight_rejects_foreign_key_violation_on_throwaway_copy(tmp_path):
    source, snapshot = _case(tmp_path)
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO topics(account_id, title) VALUES ('missing-account','orphan')"
        )
        connection.commit()
    finally:
        connection.close()
    _force_delete_journal_mode(source)
    _assert_refusal_without_source_mutation(
        source,
        snapshot,
        _request(source, snapshot),
        "DATABASE_FOREIGN_KEY_FAILED",
    )


@pytest.mark.parametrize(
    ("confirmed", "from_version", "target_version", "expected_code"),
    (
        (False, SUPPORTED_FROM_VERSION, SUPPORTED_TARGET_VERSION, "OWNER_CONFIRMATION_REQUIRED"),
        (True, SETTLED_RECOVERY_SCHEMA_VERSION, SUPPORTED_TARGET_VERSION, "UNSUPPORTED_FROM_VERSION"),
        (True, SUPPORTED_FROM_VERSION, EVIDENCE_PIPELINE_SCHEMA_VERSION, "UNSUPPORTED_TARGET_VERSION"),
    ),
)
def test_contract_arguments_fail_before_snapshot(
    tmp_path, confirmed, from_version, target_version, expected_code,
):
    source, snapshot = _case(tmp_path)
    request = _request(
        source,
        snapshot,
        confirmed=confirmed,
        expected_from_version=from_version,
        target_version=target_version,
    )
    _assert_refusal_without_source_mutation(
        source, snapshot, request, expected_code,
    )


def test_database_not_quiescent_has_distinct_reason(tmp_path):
    source, snapshot = _case(tmp_path)
    error = _assert_refusal_without_source_mutation(
        source,
        snapshot,
        _request(source, snapshot),
        "DATABASE_NOT_QUIESCENT",
        quiescence_probe=lambda path: (str(path),),
    )
    assert error.reason_codes == ("DATABASE_NOT_QUIESCENT",)


@pytest.mark.parametrize(
    ("suffixes", "code", "reasons"),
    (
        (("-wal",), "WAL_PRESENT", ("WAL_PRESENT",)),
        (("-shm",), "SHM_PRESENT", ("SHM_PRESENT",)),
        (("-journal",), "JOURNAL_PRESENT", ("JOURNAL_PRESENT",)),
        (("-wal", "-shm"), "WAL_PRESENT", ("WAL_PRESENT", "SHM_PRESENT")),
    ),
)
def test_sidecars_stop_before_snapshot_and_are_not_removed(
    tmp_path, suffixes, code, reasons,
):
    source, snapshot = _case(tmp_path)
    sidecars = [Path(f"{source}{suffix}") for suffix in suffixes]
    for sidecar in sidecars:
        sidecar.write_bytes(b"synthetic")
    error = _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), code,
    )
    assert error.reason_codes == reasons
    assert all(sidecar.read_bytes() == b"synthetic" for sidecar in sidecars)


@pytest.mark.parametrize(
    "state_change",
    ("replace_same_ledger", "size", "sha_same_size", "ledger", "sidecar"),
)
def test_revalidation_rejects_state_changed_after_snapshot(
    tmp_path, state_change,
):
    source, snapshot = _case(tmp_path)
    original = _fingerprint(source)
    replacement_dir = tmp_path / "replacement"
    replacement_dir.mkdir()
    replacement = replacement_dir / "replacement.db"
    initialize_database(replacement, through=STAGE1_SCHEMA_VERSION)
    _force_delete_journal_mode(replacement)
    connection = sqlite3.connect(replacement)
    try:
        connection.execute("PRAGMA user_version=7")
        connection.execute(
            "INSERT INTO accounts(id,name,mode,autonomy_level,active,"
            "browser_profile_path,writing_profile_path) "
            "VALUES ('replacement','replacement','full_publication','L1',0,'x','y')"
        )
        connection.commit()
    finally:
        connection.close()
    _force_delete_journal_mode(replacement)

    def mutate(phase: str) -> None:
        if phase != "after_snapshot":
            return
        if state_change == "replace_same_ledger":
            shutil.copy2(replacement, source)
        elif state_change == "size":
            with source.open("ab") as handle:
                handle.write(b"x")
        elif state_change == "sha_same_size":
            connection = sqlite3.connect(source)
            try:
                connection.execute("PRAGMA user_version=9")
                connection.commit()
            finally:
                connection.close()
            _force_delete_journal_mode(source)
            assert source.stat().st_size == original[1]
        elif state_change == "ledger":
            migrate_0014_to_0015(source)
            _force_delete_journal_mode(source)
        else:
            Path(f"{source}-wal").write_bytes(b"appeared-between-gates")

    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot), failpoint=mutate)
    assert caught.value.code == "STALE_DATABASE_STATE"
    assert snapshot.exists()
    if state_change == "sidecar":
        assert "WAL_PRESENT" in caught.value.reason_codes
        assert Path(f"{source}-wal").exists()
    assert database_schema_versions(snapshot)[-1] == STAGE1_SCHEMA_VERSION


def test_sidecar_appearing_immediately_before_writable_open_is_refused(tmp_path):
    source, snapshot = _case(tmp_path)

    def appear(phase: str) -> None:
        if phase == "before_writable_open":
            Path(f"{source}-journal").write_bytes(b"late")

    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot), failpoint=appear)
    assert caught.value.code == "STALE_DATABASE_STATE"
    assert caught.value.reason_codes == ("JOURNAL_PRESENT",)
    assert database_schema_versions(source)[-1] == STAGE1_SCHEMA_VERSION
    assert Path(f"{source}-journal").read_bytes() == b"late"


def test_snapshot_target_existing_is_never_overwritten(tmp_path):
    source, snapshot = _case(tmp_path)
    snapshot.write_bytes(b"prior-backup")
    before = _fingerprint(source)
    with pytest.raises(ProductionMigrationError, match="SNAPSHOT_TARGET_EXISTS"):
        _run(_request(source, snapshot))
    assert snapshot.read_bytes() == b"prior-backup"
    assert _fingerprint(source) == before


def test_snapshot_mismatch_stops_before_migration(monkeypatch, tmp_path):
    source, snapshot = _case(tmp_path)
    original_copy = migration_module._copy_snapshot

    def mismatching_copy(source_path: Path, target_path: Path) -> None:
        original_copy(source_path, target_path)
        connection = sqlite3.connect(target_path)
        try:
            connection.execute("PRAGMA user_version=123")
            connection.commit()
        finally:
            connection.close()
        _force_delete_journal_mode(target_path)

    monkeypatch.setattr(migration_module, "_copy_snapshot", mismatching_copy)
    before = _fingerprint(source)
    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot))
    assert caught.value.code == "SNAPSHOT_MISMATCH"
    assert _fingerprint(source) == before
    assert database_schema_versions(source)[-1] == STAGE1_SCHEMA_VERSION


def test_snapshot_copy_failure_stops_before_migration(monkeypatch, tmp_path):
    source, snapshot = _case(tmp_path)

    def fail_copy(_source: Path, _target: Path) -> None:
        raise ProductionMigrationError(
            "SNAPSHOT_COPY_FAILED", "controlled copy failure", phase="snapshot_copy",
        )

    monkeypatch.setattr(migration_module, "_copy_snapshot", fail_copy)
    _assert_refusal_without_source_mutation(
        source, snapshot, _request(source, snapshot), "SNAPSHOT_COPY_FAILED",
    )


def test_snapshot_validation_failure_stops_before_migration(monkeypatch, tmp_path):
    source, snapshot = _case(tmp_path)
    original_inspect = migration_module._inspect_database

    def fail_snapshot_validation(path: Path):
        if path == snapshot:
            raise ProductionMigrationError(
                "DATABASE_INTEGRITY_FAILED",
                "controlled snapshot validation failure",
                phase="database_preflight",
            )
        return original_inspect(path)

    monkeypatch.setattr(
        migration_module, "_inspect_database", fail_snapshot_validation,
    )
    before = _fingerprint(source)
    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot))
    assert caught.value.code == "SNAPSHOT_VALIDATION_FAILED"
    assert _fingerprint(source) == before
    assert database_schema_versions(source)[-1] == STAGE1_SCHEMA_VERSION


@pytest.mark.parametrize(
    ("version", "expected_applied"),
    (
        (STAGE1_SCHEMA_VERSION, MIGRATION_SEQUENCE),
        (SETTLED_RECOVERY_SCHEMA_VERSION, MIGRATION_SEQUENCE[1:]),
        (EVIDENCE_SCHEMA_VERSION, MIGRATION_SEQUENCE[2:]),
        (EVIDENCE_PIPELINE_SCHEMA_VERSION, MIGRATION_SEQUENCE[3:]),
    ),
)
def test_start_and_supported_resume_states_reach_0018_once(
    tmp_path, version, expected_applied,
):
    source, snapshot = _case(tmp_path, version=version)
    result = _run(_request(source, snapshot))
    assert result.status == "MIGRATION_COMPLETE"
    assert result.source_version == version
    assert result.applied_migrations == expected_applied
    versions = database_schema_versions(source)
    assert len(versions) == 18
    assert len(set(versions)) == 18
    assert versions[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    for migration in MIGRATION_SEQUENCE:
        assert versions.count(migration) == 1


def test_0018_returns_already_at_target_without_snapshot_or_mutation(tmp_path):
    source, snapshot = _case(tmp_path, version=CONTROLLED_FETCH_SCHEMA_VERSION)
    before = _fingerprint(source)
    result = _run(_request(source, snapshot))
    assert result.status == "ALREADY_AT_TARGET"
    assert result.applied_migrations == ()
    assert result.snapshot_path is None
    assert not snapshot.exists()
    assert _fingerprint(source) == before
    assert result.runtime_gate_sha_unchanged is True


_FAILPOINT_DURABLE_VERSION = {
    "before_snapshot": STAGE1_SCHEMA_VERSION,
    "after_snapshot": STAGE1_SCHEMA_VERSION,
    "after_second_preflight": STAGE1_SCHEMA_VERSION,
    "before_writable_open": STAGE1_SCHEMA_VERSION,
    "before_0015": STAGE1_SCHEMA_VERSION,
    "during_0015": STAGE1_SCHEMA_VERSION,
    "after_0015": SETTLED_RECOVERY_SCHEMA_VERSION,
    "before_0016": SETTLED_RECOVERY_SCHEMA_VERSION,
    "during_0016": SETTLED_RECOVERY_SCHEMA_VERSION,
    "after_0016": EVIDENCE_SCHEMA_VERSION,
    "before_0017": EVIDENCE_SCHEMA_VERSION,
    "during_0017": EVIDENCE_SCHEMA_VERSION,
    "after_0017": EVIDENCE_PIPELINE_SCHEMA_VERSION,
    "before_0018": EVIDENCE_PIPELINE_SCHEMA_VERSION,
    "during_0018": EVIDENCE_PIPELINE_SCHEMA_VERSION,
    "after_0018": CONTROLLED_FETCH_SCHEMA_VERSION,
    "before_final_validation": CONTROLLED_FETCH_SCHEMA_VERSION,
}


@pytest.mark.parametrize("phase", tuple(_FAILPOINT_DURABLE_VERSION))
def test_controlled_failpoints_leave_a_consistent_durable_resume_state(
    tmp_path, phase,
):
    source, snapshot = _case(tmp_path)
    calls: list[str] = []

    def stop(current: str) -> None:
        calls.append(current)
        if current == phase:
            raise RuntimeError(f"controlled {phase}")

    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot), failpoint=stop)
    error = caught.value
    expected = _FAILPOINT_DURABLE_VERSION[phase]
    assert error.code == "CONTROLLED_FAILPOINT"
    assert error.durable_version == expected
    versions = database_schema_versions(source)
    assert versions[-1] == expected
    assert len(versions) == len(set(versions))
    assert _sidecars(source) == (False, False, False)
    assert calls.count(phase) == 1
    if phase == "before_snapshot":
        assert not snapshot.exists()
    else:
        assert snapshot.exists()
        assert database_schema_versions(snapshot)[-1] == STAGE1_SCHEMA_VERSION

    if expected != CONTROLLED_FETCH_SCHEMA_VERSION:
        resume_dir = tmp_path / "resume-snapshots"
        resume_dir.mkdir()
        resume_snapshot = resume_dir / f"resume-{phase}.db"
        resumed = _run(_request(source, resume_snapshot))
        assert resumed.status == "MIGRATION_COMPLETE"
        assert database_schema_versions(source)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    else:
        rerun_dir = tmp_path / "rerun-snapshots"
        rerun_dir.mkdir()
        rerun_snapshot = rerun_dir / f"rerun-{phase}.db"
        rerun = _run(_request(source, rerun_snapshot))
        assert rerun.status == "ALREADY_AT_TARGET"
        assert not rerun_snapshot.exists()


def test_failpoint_during_final_validation_needs_operator_assessment(tmp_path):
    source, snapshot = _case(tmp_path)

    def stop(phase: str) -> None:
        if phase == "during_final_validation":
            raise RuntimeError("controlled final validation failure")

    with pytest.raises(ProductionMigrationError) as caught:
        _run(_request(source, snapshot), failpoint=stop)
    assert caught.value.code == "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT"
    assert caught.value.durable_version == CONTROLLED_FETCH_SCHEMA_VERSION
    assert database_schema_versions(source)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    assert snapshot.exists()
    assert _sidecars(source) == (False, False, False)


def _cli_args(source: Path, snapshot: Path) -> list[str]:
    sha256, size = _fingerprint(source)
    return [
        "--db-path", str(source),
        "--expected-sha256", sha256,
        "--expected-size", str(size),
        "--expected-from-version", STAGE1_SCHEMA_VERSION,
        "--target-version", CONTROLLED_FETCH_SCHEMA_VERSION,
        "--snapshot-path", str(snapshot),
    ]


def test_cli_missing_confirmation_stops_without_mutation(tmp_path, capsys):
    source, snapshot = _case(tmp_path)
    before = _fingerprint(source)
    assert migration_cli.main(_cli_args(source, snapshot)) == 2
    report = capsys.readouterr().err
    assert "OWNER_CONFIRMATION_REQUIRED" in report
    assert _fingerprint(source) == before
    assert not snapshot.exists()


@pytest.mark.parametrize(
    "args_mutation",
    ("missing_required", "invalid_confirmation", "wrong_contract_value"),
)
def test_cli_parser_refuses_invalid_contract_without_mutation(
    tmp_path, args_mutation,
):
    source, snapshot = _case(tmp_path)
    args = _cli_args(source, snapshot)
    if args_mutation == "missing_required":
        index = args.index("--expected-sha256")
        del args[index:index + 2]
    elif args_mutation == "invalid_confirmation":
        args.append("--confirm-production-schema-migration-0014-to-0017")
    else:
        index = args.index("--target-version")
        args[index + 1] = EVIDENCE_PIPELINE_SCHEMA_VERSION
    before = _fingerprint(source)
    with pytest.raises(SystemExit) as caught:
        migration_cli.main(args)
    assert caught.value.code == 2
    assert _fingerprint(source) == before
    assert not snapshot.exists()


def test_cli_success_prints_terminal_report(monkeypatch, tmp_path, capsys):
    source, snapshot = _case(tmp_path)
    monkeypatch.setattr(
        migration_module, "_default_quiescence_probe", QUIESCENT,
    )
    args = _cli_args(source, snapshot)
    args.append("--confirm-production-schema-migration-0014-to-0018")
    assert migration_cli.main(args) == 0
    report = capsys.readouterr().out
    assert '"status": "MIGRATION_COMPLETE"' in report
    assert '"no_auto_retry": true' in report
    assert database_schema_versions(source)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    assert snapshot.exists()
