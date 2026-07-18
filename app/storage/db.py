"""Połączenie SQLite, jawne migracje i fail-closed schema gate runtime."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
STAGE1_SCHEMA_VERSION = "0014_provider_attempt_reconciliation"
SETTLED_RECOVERY_SCHEMA_VERSION = "0015_settled_execution_recovery"
EVIDENCE_SCHEMA_VERSION = "0016_evidence_foundation"
RUNTIME_SCHEMA_VERSION = EVIDENCE_SCHEMA_VERSION
_RUNNER_TRANSACTIONAL_MIGRATIONS = frozenset({
    "0007_candidate_attempts",
    "0008_staged_force_reresearch",
    "0009_jobs_system_flags",
    "0010_provider_attempts",
    "0011_provider_attempt_invariants",
    "0012_provider_ledger_hardening",
    "0013_provider_attempt_usage_integrity",
    "0014_provider_attempt_reconciliation",
    "0015_settled_execution_recovery",
    "0016_evidence_foundation",
})


class SchemaVersionError(RuntimeError):
    """Base class for a controlled schema-gate refusal."""

    code = "SCHEMA_VERSION_ERROR"

    def __init__(self, detail: str) -> None:
        super().__init__(f"{self.code}: {detail}")


class SchemaVersionUnavailable(SchemaVersionError):
    """The requested runtime database or its migration ledger is unavailable."""

    code = "SCHEMA_VERSION_UNAVAILABLE"


class SchemaVersionInvalid(SchemaVersionError):
    """The migration ledger is not an exact canonical prefix."""

    code = "SCHEMA_VERSION_INVALID"


class SchemaVersionTooOld(SchemaVersionError):
    """Runtime requires a newer, separately authorized schema."""

    code = "SCHEMA_VERSION_TOO_OLD"


class SchemaVersionTooNew(SchemaVersionError):
    """Runtime has not been approved against the observed newer schema."""

    code = "SCHEMA_VERSION_TOO_NEW"


class ExplicitMigrationError(RuntimeError):
    """A separately invoked migration failed its closed preflight."""


@dataclass(frozen=True)
class ExplicitMigrationResult:
    """Auditable result of one explicit single-step schema operation."""

    source_version: str
    target_version: str
    applied_migrations: tuple[str, ...]
    idempotent: bool


def _is_test_protected_database(db_path: Path | str) -> bool:
    """Reject the production DB for pytest collection, setup and subprocesses."""
    if not os.environ.get("NIA_TEST_MODE"):
        return False
    from app.testing.safety_kernel import is_protected_sqlite_database

    return is_protected_sqlite_database(db_path)


def connect(db_path: Path | str) -> sqlite3.Connection:
    if _is_test_protected_database(db_path):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        prepare_writable_connection(conn, db_path)
        return conn
    except Exception:
        conn.close()
        raise


def connect_existing_writable(db_path: Path | str) -> sqlite3.Connection:
    """Open one existing database with ``mode=rw`` and no mutating PRAGMA.

    Runtime must validate the schema on this exact handle before calling
    :func:`prepare_writable_connection`.
    """
    if _is_test_protected_database(db_path):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    path = Path(db_path).resolve()
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True)
    except sqlite3.Error as exc:
        raise SchemaVersionUnavailable(
            f"cannot open existing SQLite database for runtime: {path}"
        ) from exc
    conn.row_factory = sqlite3.Row
    return conn


def prepare_writable_connection(
    conn: sqlite3.Connection,
    db_path: Path | str,
) -> None:
    """Apply the established writable-connection settings after schema gates."""
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    if str(db_path) != ":memory:":
        journal_mode = conn.execute("PRAGMA journal_mode=WAL;").fetchone()[0].lower()
        if journal_mode != "wal":
            raise RuntimeError(
                f"SQLite database {db_path} did not enable WAL (active mode: {journal_mode})."
            )


def connect_read_only(db_path: Path | str) -> sqlite3.Connection:
    """Open an existing SQLite file without migrations or writable pragmas."""
    if _is_test_protected_database(db_path):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database does not exist: {path}")
    uri = f"{path.as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA query_only=ON;")
        return conn
    except Exception:
        conn.close()
        raise


def canonical_migration_versions(migrations_dir: Path = MIGRATIONS_DIR) -> tuple[str, ...]:
    """Return the canonical ordered ledger represented by migration filenames."""
    return tuple(path.stem for path in sorted(Path(migrations_dir).glob("*.sql")))


def _validate_schema_versions(
    versions: tuple[str, ...],
    *,
    required_version: str,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> None:
    canonical = canonical_migration_versions(migrations_dir)
    if required_version not in canonical:
        raise SchemaVersionInvalid(
            f"required version {required_version!r} is not present in the canonical ledger"
        )
    if not versions:
        raise SchemaVersionUnavailable("schema_migrations contains no applied versions")
    if versions != canonical[:len(versions)]:
        raise SchemaVersionInvalid(
            "schema_migrations is not an exact ordered prefix of canonical migrations"
        )
    required_count = canonical.index(required_version) + 1
    if len(versions) < required_count:
        raise SchemaVersionTooOld(
            f"runtime requires {required_version}; observed latest {versions[-1]}"
        )
    if len(versions) > required_count:
        raise SchemaVersionTooNew(
            f"runtime requires exact {required_version}; observed latest {versions[-1]}"
        )


def connection_schema_versions(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Read the durable migration ledger without creating or repairing it."""
    try:
        return tuple(
            row[0] for row in conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
    except sqlite3.Error as exc:
        raise SchemaVersionUnavailable(
            "schema_migrations cannot be read; explicit initialization is required"
        ) from exc


def require_connection_schema(
    conn: sqlite3.Connection,
    *,
    required_version: str = RUNTIME_SCHEMA_VERSION,
) -> tuple[str, ...]:
    """Require an exact canonical schema on an already-open connection."""
    versions = connection_schema_versions(conn)
    _validate_schema_versions(versions, required_version=required_version)
    return versions


def database_schema_versions(db_path: Path | str) -> tuple[str, ...]:
    """Inspect an existing database through mode=ro&immutable=1 only."""
    if _is_test_protected_database(db_path):
        raise RuntimeError("Tests must not open the project data/agent.db.")
    if str(db_path) == ":memory:":
        raise SchemaVersionUnavailable(":memory: has no durable schema to preflight")
    path = Path(db_path).resolve()
    if not path.is_file():
        raise SchemaVersionUnavailable(f"SQLite database does not exist: {path}")
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro&immutable=1", uri=True)
        conn.execute("PRAGMA query_only=ON")
        return connection_schema_versions(conn)
    except SchemaVersionError:
        raise
    except sqlite3.Error as exc:
        raise SchemaVersionUnavailable(f"cannot inspect SQLite schema at {path}") from exc
    finally:
        if conn is not None:
            conn.close()


def require_database_schema(
    db_path: Path | str,
    *,
    required_version: str = RUNTIME_SCHEMA_VERSION,
) -> tuple[str, ...]:
    """Fail closed before any writable SQLite connection or writable PRAGMA."""
    versions = database_schema_versions(db_path)
    _validate_schema_versions(versions, required_version=required_version)
    return versions


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version TEXT PRIMARY KEY,"
        " applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path = MIGRATIONS_DIR,
    *,
    through: str | None = None,
) -> list[str]:
    """Stosuje niezaaplikowane pliki .sql w kolejności nazw. Zwraca listę zastosowanych wersji."""
    _ensure_migrations_table(conn)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    for sql_file in sorted(Path(migrations_dir).glob("*.sql")):
        version = sql_file.stem
        if through is not None and version > through:
            continue
        if version in applied:
            continue
        sql = sql_file.read_text(encoding="utf-8")
        if version in _RUNNER_TRANSACTIONAL_MIGRATIONS:
            quoted_version = conn.execute("SELECT quote(?)", (version,)).fetchone()[0]
            try:
                conn.executescript(
                    "BEGIN IMMEDIATE;\n"
                    f"{sql}\n"
                    f"INSERT INTO schema_migrations(version) VALUES ({quoted_version});\n"
                    "COMMIT;"
                )
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
        else:
            # 0001-0006 retain their historical migration contract; 0006 has its
            # own BEGIN IMMEDIATE/COMMIT and must not be nested here.
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            conn.commit()
        newly.append(version)
    return newly


def initialize_database(
    db_path: Path | str,
    *,
    through: str = RUNTIME_SCHEMA_VERSION,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> tuple[str, ...]:
    """Explicitly initialize one new database; ordinary runtime never calls this."""
    if str(db_path) == ":memory:":
        raise ExplicitMigrationError("durable explicit initialization requires a file path")
    path = Path(db_path).resolve()
    if path.exists():
        raise ExplicitMigrationError(f"initialization target already exists: {path}")
    canonical = canonical_migration_versions(migrations_dir)
    if through not in canonical:
        raise ExplicitMigrationError(f"unknown initialization target: {through}")
    conn = connect(path)
    try:
        applied = tuple(apply_migrations(conn, migrations_dir, through=through))
        versions = connection_schema_versions(conn)
        expected = canonical[:canonical.index(through) + 1]
        if versions != expected or applied != expected:
            raise ExplicitMigrationError(
                f"fresh initialization produced {versions!r}, expected {expected!r}"
            )
        return applied
    finally:
        conn.close()


def _migrate_single_step(
    db_path: Path | str,
    *,
    source_version: str,
    target_version: str,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Explicit, idempotent and transactional single-step migration only.

    The ladder is deliberately made of exact one-version steps: each step has
    its own confirmed CLI, preflight and authorization.  The caller must
    separately own operational authorization, quiescence and backup policy.
    This function is never reached by ``SqliteStorage.open``.
    """
    step = f"{source_version[:4]} -> {target_version[:4]}"
    before = database_schema_versions(db_path)
    if not before:
        raise ExplicitMigrationError(f"{step} preflight found an empty migration ledger")
    canonical = canonical_migration_versions()
    _validate_schema_versions(before, required_version=before[-1])
    if before[-1] == target_version:
        return ExplicitMigrationResult(
            source_version=target_version,
            target_version=target_version,
            applied_migrations=(),
            idempotent=True,
        )
    if before[-1] != source_version:
        raise ExplicitMigrationError(
            f"{step} preflight requires exact {source_version}; "
            f"observed {before[-1]}"
        )
    expected_before = canonical[:canonical.index(source_version) + 1]
    if before != expected_before:
        raise ExplicitMigrationError(
            f"{source_version[:4]} ledger is not the exact canonical prefix"
        )
    candidates = tuple(
        path.stem for path in sorted(Path(migrations_dir).glob("*.sql"))
        if path.stem not in before and path.stem <= target_version
    )
    if candidates != (target_version,):
        raise ExplicitMigrationError(
            f"explicit migration directory must offer only {target_version}; "
            f"observed {candidates!r}"
        )
    conn: sqlite3.Connection | None = None
    try:
        conn = connect(db_path)
        require_connection_schema(conn, required_version=source_version)
        applied = tuple(
            apply_migrations(conn, migrations_dir, through=target_version)
        )
        if applied != (target_version,):
            raise ExplicitMigrationError(
                f"explicit migration applied {applied!r}, expected only {target_version}"
            )
        require_connection_schema(conn, required_version=target_version)
    except (ExplicitMigrationError, SchemaVersionError):
        raise
    except sqlite3.Error as exc:
        raise ExplicitMigrationError(f"{step} migration failed: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()
    return ExplicitMigrationResult(
        source_version=source_version,
        target_version=target_version,
        applied_migrations=(target_version,),
        idempotent=False,
    )


def migrate_0014_to_0015(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Explicit, idempotent and transactional 0014 -> 0015 migration only."""
    return _migrate_single_step(
        db_path,
        source_version=STAGE1_SCHEMA_VERSION,
        target_version=SETTLED_RECOVERY_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0015_to_0016(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Explicit, idempotent and transactional 0015 -> 0016 migration only."""
    return _migrate_single_step(
        db_path,
        source_version=SETTLED_RECOVERY_SCHEMA_VERSION,
        target_version=EVIDENCE_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )
