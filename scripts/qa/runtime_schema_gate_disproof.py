"""Independent offline disproof for PR1-MAJ-005 using one throwaway SQLite file."""
from __future__ import annotations

import hashlib
from pathlib import Path
from shutil import copy2
import sqlite3
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.testing.safety_kernel import activate as _activate_safety_kernel  # noqa: E402

_activate_safety_kernel()

from app.storage.db import (  # noqa: E402
    CONTROLLED_FETCH_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    ExplicitMigrationError,
    RUNTIME_SCHEMA_VERSION,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    SchemaVersionInvalid,
    SchemaVersionTooOld,
    SchemaVersionUnavailable,
    database_schema_versions,
    initialize_database,
    migrate_0014_to_0015,
    migrate_0015_to_0016,
    migrate_0016_to_0017,
    migrate_0017_to_0018,
)
import app.storage.repositories as repositories_module  # noqa: E402
from app.storage.repositories import SqliteStorage  # noqa: E402


def _fingerprint(path: Path):
    stat = path.stat()
    return (
        hashlib.sha256(path.read_bytes()).hexdigest().upper(),
        stat.st_size,
        stat.st_mtime_ns,
        tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal")),
        database_schema_versions(path),
    )


def _sidecars(path: Path) -> tuple[bool, bool, bool]:
    return tuple(Path(f"{path}{suffix}").exists() for suffix in ("-wal", "-shm", "-journal"))


def _force_delete_journal_mode(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        assert conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0].lower() == "delete"
    finally:
        conn.close()


def main() -> int:
    checks: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="nia-runtime-schema-gate-") as tmp:
        root = Path(tmp)
        path = root / "schema-gate.db"
        initialize_database(path, through=STAGE1_SCHEMA_VERSION)
        _force_delete_journal_mode(path)
        before = _fingerprint(path)
        checks.append(before[3] == (False, False, False))
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        checks.append(_fingerprint(path) == before)
        checks.append(len(before[4]) == 14 and before[4][-1] == STAGE1_SCHEMA_VERSION)

        deleted = root / "deleted-after-preflight.db"
        initialize_database(deleted)
        original_preflight = repositories_module.require_database_schema
        original_prepare = repositories_module.prepare_writable_connection
        deletion_prepared: list[bool] = []

        def delete_after_preflight(db_path, **kwargs):
            versions = original_preflight(db_path, **kwargs)
            Path(db_path).unlink()
            return versions

        repositories_module.require_database_schema = delete_after_preflight
        repositories_module.prepare_writable_connection = (
            lambda *_args, **_kwargs: deletion_prepared.append(True)
        )
        try:
            SqliteStorage.open(deleted)
        except SchemaVersionUnavailable:
            checks.append(True)
        else:
            checks.append(False)
        finally:
            repositories_module.require_database_schema = original_preflight
            repositories_module.prepare_writable_connection = original_prepare
        checks.append(not deleted.exists())
        checks.append(_sidecars(deleted) == (False, False, False))
        checks.append(deletion_prepared == [])

        replaced = root / "replaced-after-preflight.db"
        replacement = root / "replacement-0014.db"
        initialize_database(replaced)
        initialize_database(replacement, through=STAGE1_SCHEMA_VERSION)
        _force_delete_journal_mode(replacement)
        replacement_before: list[tuple[object, ...]] = []
        replacement_prepared: list[bool] = []

        def replace_after_preflight(db_path, **kwargs):
            versions = original_preflight(db_path, **kwargs)
            copy2(replacement, db_path)
            replacement_before.append(_fingerprint(Path(db_path)))
            return versions

        repositories_module.require_database_schema = replace_after_preflight
        repositories_module.prepare_writable_connection = (
            lambda *_args, **_kwargs: replacement_prepared.append(True)
        )
        try:
            SqliteStorage.open(replaced)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        finally:
            repositories_module.require_database_schema = original_preflight
            repositories_module.prepare_writable_connection = original_prepare
        checks.append(len(replacement_before) == 1 and _fingerprint(replaced) == replacement_before[0])
        checks.append(replacement_prepared == [])

        migrated = migrate_0014_to_0015(path)
        checks.append(migrated.applied_migrations == (SETTLED_RECOVERY_SCHEMA_VERSION,))
        checks.append(len(database_schema_versions(path)) == 15)
        # 0015 is an intermediate rung now: runtime must still refuse it.
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        evidence = migrate_0015_to_0016(path)
        checks.append(evidence.applied_migrations == (EVIDENCE_SCHEMA_VERSION,))
        checks.append(len(database_schema_versions(path)) == 16)
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        lineage = migrate_0016_to_0017(path)
        checks.append(lineage.applied_migrations == (EVIDENCE_PIPELINE_SCHEMA_VERSION,))
        checks.append(len(database_schema_versions(path)) == 17)
        before_0017_refusal = _fingerprint(path)
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            checks.append(True)
        else:
            checks.append(False)
        checks.append(_fingerprint(path) == before_0017_refusal)
        controlled_fetch = migrate_0017_to_0018(path)
        checks.append(
            controlled_fetch.applied_migrations == (CONTROLLED_FETCH_SCHEMA_VERSION,)
        )
        checks.append(len(database_schema_versions(path)) == 18)
        runtime = SqliteStorage.open(path)
        runtime.close()
        checks.append(True)
        # The superseded rung must fail closed on a fully migrated database.
        try:
            migrate_0014_to_0015(path)
        except ExplicitMigrationError:
            checks.append(True)
        else:
            checks.append(False)
        repeated_controlled_fetch = migrate_0017_to_0018(path)
        checks.append(
            repeated_controlled_fetch.idempotent
            and repeated_controlled_fetch.applied_migrations == ()
        )

        future_before_refusal: tuple[object, ...]
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "INSERT INTO schema_migrations(version) "
                "VALUES ('0019_not_supported_by_runtime')"
            )
            conn.commit()
        finally:
            conn.close()
        future_before_refusal = _fingerprint(path)
        try:
            SqliteStorage.open(path)
        except SchemaVersionInvalid:
            checks.append(True)
        else:
            checks.append(False)
        checks.append(_fingerprint(path) == future_before_refusal)

        missing = root / "missing" / "runtime.db"
        try:
            SqliteStorage.open(missing)
        except SchemaVersionUnavailable:
            checks.append(True)
        else:
            checks.append(False)
        checks.append(not missing.exists() and not missing.parent.exists())

    passed = sum(checks)
    print(f"[BLOCKED] runtime schema-gate disproof: {passed}/{len(checks)}")
    return 0 if passed == len(checks) == 30 else 1


if __name__ == "__main__":
    raise SystemExit(main())
