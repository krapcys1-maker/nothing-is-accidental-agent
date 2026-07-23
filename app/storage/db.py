"""Połączenie SQLite, jawne migracje i fail-closed schema gate runtime."""
from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
STAGE1_SCHEMA_VERSION = "0014_provider_attempt_reconciliation"
SETTLED_RECOVERY_SCHEMA_VERSION = "0015_settled_execution_recovery"
EVIDENCE_SCHEMA_VERSION = "0016_evidence_foundation"
EVIDENCE_PIPELINE_SCHEMA_VERSION = "0017_evidence_pipeline_lineage"
CONTROLLED_FETCH_SCHEMA_VERSION = "0018_controlled_fetch_lifecycle"
EVIDENCE_RESEARCH_SCHEMA_VERSION = "0019_evidence_research_approvals"
TOPIC_GENERATION_SCHEMA_VERSION = "0020_topic_generation_lifecycle"
CONTENT_FOUNDATION_SCHEMA_VERSION = "0021_durable_content_foundation"
CONTENT_PIPELINE_SCHEMA_VERSION = "0022_offline_content_pipeline"
RUNTIME_SCHEMA_VERSION = CONTENT_PIPELINE_SCHEMA_VERSION
_SELF_LEDGERED_MIGRATIONS = frozenset({
    # 0021 rebuilds jobs under foreign_keys=OFF and therefore must own BEGIN.
    # Unlike historical self-managed rebuilds, it also writes schema_migrations
    # in that same transaction; the runner verifies rather than duplicates it.
    CONTENT_FOUNDATION_SCHEMA_VERSION,
})
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
    "0017_evidence_pipeline_lineage",
    "0018_controlled_fetch_lifecycle",
    CONTENT_PIPELINE_SCHEMA_VERSION,
    # 0019 is intentionally ABSENT: rebuilding controlled_fetch_approvals with
    # incoming foreign keys requires PRAGMA foreign_keys=OFF, which is a no-op
    # inside the runner transaction — the migration manages its own explicit
    # BEGIN IMMEDIATE/COMMIT (the same contract as 0006).
    # 0020 is ABSENT for the same reason: it rebuilds `jobs`, which carries
    # incoming foreign keys from provider_attempts, controlled_fetch_attempts
    # and controlled_fetch_approvals.
    # 0021 is self-ledgered and intentionally handled by
    # _SELF_LEDGERED_MIGRATIONS instead.
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


# Nazwa deterministycznej funkcji SQL wkompilowanej w triggery migracji 0016.
EVIDENCE_HASH_SQL_FUNCTION = "evidence_sha256_hex"


def _evidence_sha256_hex(value: str | bytes | None) -> str | None:
    if value is None:
        return None
    data = value.encode("utf-8") if isinstance(value, str) else bytes(value)
    return hashlib.sha256(data).hexdigest()


def register_evidence_hash_function(conn: sqlite3.Connection) -> None:
    """Rejestruje ``evidence_sha256_hex`` na jednym połączeniu SQLite.

    Triggery 0016 wiążą ``canonical_sha256``/``claim_sha256`` z rzeczywiście
    utrwalonym tekstem przez tę funkcję.  Kontrakt jest fail-closed: writer,
    który jej nie zarejestrował, nie może w ogóle INSERT-ować do tabel
    evidence ("no such function"), a writer z prawdziwą funkcją nie może
    utrwalić fałszywego hasha.  Granica zaufania: floor NIE broni przed
    autorem, który zmienia schemat, usuwa triggery albo celowo rejestruje
    pod tą nazwą fałszywą funkcję — taki autor jest poza modelem zagrożeń E1.
    """
    conn.create_function(
        EVIDENCE_HASH_SQL_FUNCTION, 1, _evidence_sha256_hex, deterministic=True,
    )


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
        register_evidence_hash_function(conn)
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
    register_evidence_hash_function(conn)
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
        register_evidence_hash_function(conn)
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
    transaction_failpoint: Callable[[str], None] | None = None,
) -> list[str]:
    """Stosuje niezaaplikowane pliki .sql w kolejności nazw.

    ``transaction_failpoint`` jest wyłącznie kontrolowanym hakiem testowym
    wykonywanym wewnątrz transakcji migracji 0007+ — po SQL schematu, lecz
    przed wpisem do ledgeru i COMMIT. Wyjątek z haka wycofuje zarówno schemat,
    jak i ledger danego kroku. Domyślna ścieżka produkcyjna nie instaluje haka.
    """
    _ensure_migrations_table(conn)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    newly: list[str] = []
    failpoint_function = "_nia_transactional_migration_failpoint"
    # 0021 always calls this function inside its own transaction.  Production
    # gets a deterministic no-op; tests may inject an exception immediately
    # before the atomic ledger write.
    conn.create_function(
        failpoint_function,
        1,
        transaction_failpoint if transaction_failpoint is not None else (lambda _version: None),
    )
    try:
        for sql_file in sorted(Path(migrations_dir).glob("*.sql")):
            version = sql_file.stem
            if through is not None and version > through:
                continue
            if version in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            if version in _SELF_LEDGERED_MIGRATIONS:
                try:
                    conn.executescript(sql)
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise
                finally:
                    # A fault before the migration's trailing PRAGMAs must not
                    # leak its temporary rebuild settings into a reused
                    # connection.
                    if not conn.in_transaction:
                        conn.execute("PRAGMA legacy_alter_table = OFF")
                        conn.execute("PRAGMA foreign_keys = ON")
                recorded = conn.execute(
                    "SELECT COUNT(*) FROM schema_migrations WHERE version=?",
                    (version,),
                ).fetchone()[0]
                if recorded != 1:
                    raise ExplicitMigrationError(
                        f"self-ledgered migration {version} did not record exactly one ledger row"
                    )
            elif version in _RUNNER_TRANSACTIONAL_MIGRATIONS:
                quoted_version = conn.execute("SELECT quote(?)", (version,)).fetchone()[0]
                failpoint_sql = (
                    f"SELECT {failpoint_function}({quoted_version});\n"
                    if transaction_failpoint is not None
                    else ""
                )
                try:
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        f"{sql}\n"
                        f"{failpoint_sql}"
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
    finally:
        conn.create_function(failpoint_function, 1, None)
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


def migrate_0016_to_0017(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized E2-A lineage migration."""
    return _migrate_single_step(
        db_path,
        source_version=EVIDENCE_SCHEMA_VERSION,
        target_version=EVIDENCE_PIPELINE_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0017_to_0018(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized E2-B controlled fetch migration."""
    return _migrate_single_step(
        db_path,
        source_version=EVIDENCE_PIPELINE_SCHEMA_VERSION,
        target_version=CONTROLLED_FETCH_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0018_to_0019(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized E3 evidence-approvals migration."""
    return _migrate_single_step(
        db_path,
        source_version=CONTROLLED_FETCH_SCHEMA_VERSION,
        target_version=EVIDENCE_RESEARCH_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0019_to_0020(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized topic-generation migration.

    Production is intentionally NOT migrated by this change; the step exists so
    that a later, separately authorized operation has the same explicit,
    idempotent, single-step contract as every rung below it.
    """
    return _migrate_single_step(
        db_path,
        source_version=EVIDENCE_RESEARCH_SCHEMA_VERSION,
        target_version=TOPIC_GENERATION_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0020_to_0021(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized durable-content foundation schema.

    This generic step is exercised exclusively on temporary databases in C1.
    It does not authorize or perform a production migration.
    """
    return _migrate_single_step(
        db_path,
        source_version=TOPIC_GENERATION_SCHEMA_VERSION,
        target_version=CONTENT_FOUNDATION_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )


def migrate_0021_to_0022(
    db_path: Path | str,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ExplicitMigrationResult:
    """Apply only the separately authorized offline C2 content schema.

    The function is intentionally not called by runtime and does not authorize
    migration of ``data/agent.db``.
    """
    return _migrate_single_step(
        db_path,
        source_version=CONTENT_FOUNDATION_SCHEMA_VERSION,
        target_version=CONTENT_PIPELINE_SCHEMA_VERSION,
        migrations_dir=migrations_dir,
    )
