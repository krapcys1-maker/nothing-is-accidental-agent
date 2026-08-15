"""Controlled production-schema orchestrator for the sole 0014 -> 0018 ladder.

This module deliberately does not expose an arbitrary migration engine.  It
binds one owner-approved invocation to the exact database path, SHA-256, size,
0014->0018 contract and a new external snapshot.  Production runtime never
imports or calls this operation.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat as stat_module
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.storage.db import (
    CONTROLLED_FETCH_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    MIGRATIONS_DIR,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    STAGE1_SCHEMA_VERSION,
    apply_migrations,
    canonical_migration_versions,
    connection_schema_versions,
    register_evidence_hash_function,
    require_database_schema,
)


SUPPORTED_FROM_VERSION = STAGE1_SCHEMA_VERSION
SUPPORTED_TARGET_VERSION = CONTROLLED_FETCH_SCHEMA_VERSION
SUPPORTED_RESUME_VERSIONS = (
    STAGE1_SCHEMA_VERSION,
    SETTLED_RECOVERY_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
)
SUPPORTED_STATES = SUPPORTED_RESUME_VERSIONS + (SUPPORTED_TARGET_VERSION,)
MIGRATION_SEQUENCE = (
    SETTLED_RECOVERY_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_PIPELINE_SCHEMA_VERSION,
    CONTROLLED_FETCH_SCHEMA_VERSION,
)
CONFIRMATION_FLAG = "--confirm-production-schema-migration-0014-to-0018"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_SIDECAR_SUFFIXES = (
    ("-wal", "WAL_PRESENT"),
    ("-shm", "SHM_PRESENT"),
    ("-journal", "JOURNAL_PRESENT"),
)

# Objects introduced by each supported rung.  These named SQLite objects are
# the physical-schema half of the resume contract; the exact ordered ledger is
# the other half.
_VERSION_OBJECTS: dict[str, frozenset[tuple[str, str]]] = {
    SETTLED_RECOVERY_SCHEMA_VERSION: frozenset({
        ("index", "ux_reconciliation_events_execution_recovery"),
        ("trigger", "settled_execution_recovery_requires_consistent_prestate"),
        ("trigger", "jobs_settled_recovery_requires_event"),
        ("trigger", "runs_settled_recovery_requires_event"),
        ("trigger", "research_runs_settled_recovery_requires_event"),
        ("trigger", "settled_execution_recovery_terminalizes_lifecycle"),
        ("trigger", "model_usage_execution_recovery_is_immutable"),
        ("trigger", "model_usage_execution_recovery_no_delete"),
        ("trigger", "runs_execution_recovery_terminal_is_immutable"),
        ("trigger", "research_runs_execution_recovery_terminal_is_immutable"),
        ("trigger", "jobs_execution_recovery_terminal_is_immutable"),
    }),
    EVIDENCE_SCHEMA_VERSION: frozenset({
        ("table", "evidence_retrievals"),
        ("table", "evidence_excerpts"),
        ("index", "ix_evidence_retrievals_account_final_url"),
        ("index", "ix_evidence_excerpts_retrieval"),
        ("index", "ux_evidence_excerpts_claim_identity"),
        ("trigger", "evidence_retrievals_authoritative_canonical_hash"),
        ("trigger", "evidence_excerpts_authoritative_claim_hash"),
        ("trigger", "evidence_excerpts_same_account_lineage"),
        ("trigger", "evidence_excerpts_require_consistent_evidence"),
        ("trigger", "evidence_retrievals_no_update"),
        ("trigger", "evidence_retrievals_no_delete"),
        ("trigger", "evidence_excerpts_no_update"),
        ("trigger", "evidence_excerpts_no_delete"),
    }),
    EVIDENCE_PIPELINE_SCHEMA_VERSION: frozenset({
        ("table", "evidence_candidate_retrievals"),
        ("table", "evidence_candidate_excerpts"),
        ("table", "evidence_source_lineage"),
        ("trigger", "evidence_candidate_retrievals_integrity"),
        ("trigger", "evidence_candidate_excerpts_integrity"),
        ("trigger", "evidence_source_lineage_integrity"),
        ("trigger", "evidence_candidate_retrievals_no_update"),
        ("trigger", "evidence_candidate_retrievals_no_delete"),
        ("trigger", "evidence_candidate_excerpts_no_update"),
        ("trigger", "evidence_candidate_excerpts_no_delete"),
        ("trigger", "evidence_source_lineage_no_update"),
        ("trigger", "evidence_source_lineage_no_delete"),
    }),
    CONTROLLED_FETCH_SCHEMA_VERSION: frozenset({
        ("table", "controlled_fetch_approvals"),
        ("table", "controlled_fetch_attempts"),
        ("trigger", "controlled_fetch_approvals_bind_frozen_job"),
        ("trigger", "controlled_fetch_approvals_born_unconsumed"),
        ("trigger", "controlled_fetch_approvals_consume_exactly_once"),
        ("trigger", "controlled_fetch_approvals_consume_before_expiry"),
        ("trigger", "controlled_fetch_approvals_no_delete"),
        ("trigger", "jobs_controlled_fetch_payload_frozen"),
        ("trigger", "controlled_fetch_attempts_born_reserved"),
        ("trigger", "controlled_fetch_attempts_bind_consumed_approval"),
        ("trigger", "controlled_fetch_attempts_controlled_transition"),
        ("trigger", "controlled_fetch_attempts_success_requires_ok_retrieval"),
        ("trigger", "controlled_fetch_attempts_failed_retrieval_consistent"),
        ("trigger", "controlled_fetch_attempts_no_delete"),
        ("trigger", "jobs_controlled_fetch_terminal_requires_resolved_attempt"),
        ("trigger", "jobs_controlled_fetch_done_requires_succeeded_attempt"),
        ("trigger", "runs_controlled_fetch_terminal_requires_resolved_attempt"),
    }),
}

Failpoint = Callable[[str], None]
QuiescenceProbe = Callable[[Path], tuple[str, ...]]


class _ControlledFailpoint(RuntimeError):
    def __init__(self, name: str, cause: BaseException) -> None:
        super().__init__(f"{name}: {cause}")
        self.name = name
        self.cause = cause


@dataclass(frozen=True)
class DatabaseFileState:
    canonical_path: str
    sha256: str
    size: int
    mtime_ns: int
    ctime_ns: int
    device: int
    inode: int
    link_count: int


@dataclass(frozen=True)
class DatabaseInspection:
    file: DatabaseFileState
    versions: tuple[str, ...]
    integrity_check: tuple[str, ...]
    foreign_key_violations: tuple[tuple[Any, ...], ...]
    objects: frozenset[tuple[str, str]]

    @property
    def current_version(self) -> str:
        return self.versions[-1]


@dataclass(frozen=True)
class ProductionMigrationRequest:
    db_path: Path
    expected_sha256: str
    expected_size: int
    expected_from_version: str
    target_version: str
    snapshot_path: Path
    confirmed_0014_to_0018: bool


@dataclass(frozen=True)
class ProductionMigrationResult:
    status: str
    db_path: str
    snapshot_path: str | None
    source_version: str
    target_version: str
    applied_migrations: tuple[str, ...]
    durable_version: str
    database_before: DatabaseFileState
    database_after: DatabaseFileState
    snapshot: DatabaseFileState | None
    runtime_gate_sha_unchanged: bool
    no_auto_retry: bool = True
    snapshot_auto_restored: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductionMigrationError(RuntimeError):
    """Typed terminal STOP with enough state for an owner-directed resume."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        phase: str,
        reason_codes: tuple[str, ...] = (),
        durable_version: str | None = None,
        next_migration: str | None = None,
        snapshot_path: Path | None = None,
        database_state: DatabaseFileState | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.phase = phase
        self.reason_codes = reason_codes
        self.durable_version = durable_version
        self.next_migration = next_migration
        self.snapshot_path = snapshot_path
        self.database_state = database_state

    def as_dict(self) -> dict[str, Any]:
        resumable = self.durable_version in SUPPORTED_RESUME_VERSIONS
        return {
            "status": (
                "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT"
                if self.code == "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT"
                else "STOPPED"
            ),
            "reason_code": self.code,
            "reason_codes": list(self.reason_codes),
            "phase": self.phase,
            "detail": self.detail,
            "durable_version": self.durable_version,
            "next_migration": self.next_migration,
            "snapshot_path": str(self.snapshot_path) if self.snapshot_path else None,
            "database_state": (
                asdict(self.database_state) if self.database_state is not None else None
            ),
            "safe_owner_resume": resumable,
            "resume_requirements": (
                "new invocation, exact current SHA-256 and size, new snapshot, "
                "and explicit 0014-to-0018 confirmation"
                if resumable
                else None
            ),
            "no_auto_retry": True,
            "snapshot_auto_restored": False,
        }


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _is_within(path: Path, root: Path) -> bool:
    return _same_path(path, root) or root in path.parents


def _canonical_database_path(raw_path: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise ProductionMigrationError(
            "DATABASE_PATH_NOT_CANONICAL",
            "--db-path must be an absolute canonical path.",
            phase="argument_preflight",
        )
    lexical = Path(os.path.abspath(os.path.normpath(str(path))))
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ProductionMigrationError(
            "DATABASE_NOT_FOUND",
            f"database does not exist: {path}",
            phase="argument_preflight",
        ) from exc
    if stat_module.S_ISLNK(metadata.st_mode):
        raise ProductionMigrationError(
            "DATABASE_PATH_ALIAS_DETECTED",
            "symlink database paths are not supported.",
            phase="argument_preflight",
        )
    if not stat_module.S_ISREG(metadata.st_mode):
        raise ProductionMigrationError(
            "DATABASE_NOT_REGULAR_FILE",
            f"database path is not a regular file: {path}",
            phase="argument_preflight",
        )
    resolved = path.resolve(strict=True)
    if not _same_path(lexical, resolved):
        raise ProductionMigrationError(
            "DATABASE_PATH_ALIAS_DETECTED",
            f"database path resolves through an alias: {path} -> {resolved}",
            phase="argument_preflight",
        )
    if metadata.st_nlink != 1:
        raise ProductionMigrationError(
            "DATABASE_PATH_ALIAS_DETECTED",
            f"database has {metadata.st_nlink} hard links; exactly one is required.",
            phase="argument_preflight",
        )
    return resolved


def _canonical_snapshot_target(
    raw_path: Path,
    *,
    source: Path,
    project_root: Path,
) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        raise ProductionMigrationError(
            "SNAPSHOT_PATH_NOT_CANONICAL",
            "--snapshot-path must be an absolute path.",
            phase="argument_preflight",
        )
    if os.path.lexists(path):
        raise ProductionMigrationError(
            "SNAPSHOT_TARGET_EXISTS",
            f"snapshot target already exists and will not be overwritten: {path}",
            phase="argument_preflight",
        )
    parent = path.parent
    if not parent.is_dir():
        raise ProductionMigrationError(
            "SNAPSHOT_PARENT_UNAVAILABLE",
            f"snapshot parent must already exist as a directory: {parent}",
            phase="argument_preflight",
        )
    parent_lexical = Path(os.path.abspath(os.path.normpath(str(parent))))
    parent_resolved = parent.resolve(strict=True)
    if not _same_path(parent_lexical, parent_resolved):
        raise ProductionMigrationError(
            "SNAPSHOT_PATH_ALIAS_DETECTED",
            f"snapshot parent resolves through an alias: {parent}",
            phase="argument_preflight",
        )
    target = parent_resolved / path.name
    if _is_within(target, project_root.resolve()):
        raise ProductionMigrationError(
            "SNAPSHOT_INSIDE_REPOSITORY",
            "snapshot must be outside the project repository.",
            phase="argument_preflight",
        )
    if _same_path(target.parent, source.parent):
        raise ProductionMigrationError(
            "SNAPSHOT_NOT_ISOLATED",
            "snapshot must be placed in a directory distinct from the database.",
            phase="argument_preflight",
        )
    return target


def _hash_open_file(handle) -> tuple[str, os.stat_result, os.stat_result]:
    before = os.fstat(handle.fileno())
    digest = hashlib.sha256()
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    after = os.fstat(handle.fileno())
    return digest.hexdigest().upper(), before, after


def _capture_file_state(path: Path) -> DatabaseFileState:
    canonical = path.resolve(strict=True)
    try:
        with canonical.open("rb") as handle:
            sha256, before, after = _hash_open_file(handle)
        observed = canonical.stat()
    except OSError as exc:
        raise ProductionMigrationError(
            "DATABASE_IDENTITY_UNAVAILABLE",
            f"cannot establish stable database identity: {exc}",
            phase="file_identity",
        ) from exc
    identity_before = (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
        after.st_nlink,
    )
    identity_path = (
        observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns,
        observed.st_nlink,
    )
    if identity_before != identity_after or identity_after != identity_path:
        raise ProductionMigrationError(
            "DATABASE_STATE_UNSTABLE",
            "database identity changed while it was being fingerprinted.",
            phase="file_identity",
        )
    return DatabaseFileState(
        canonical_path=str(canonical),
        sha256=sha256,
        size=observed.st_size,
        mtime_ns=observed.st_mtime_ns,
        ctime_ns=observed.st_ctime_ns,
        device=observed.st_dev,
        inode=observed.st_ino,
        link_count=observed.st_nlink,
    )


def _sidecar_reason_codes(path: Path) -> tuple[str, ...]:
    return tuple(
        code for suffix, code in _SIDECAR_SUFFIXES
        if os.path.lexists(Path(f"{path}{suffix}"))
    )


def _assert_no_sidecars(path: Path, *, phase: str) -> None:
    reasons = _sidecar_reason_codes(path)
    if reasons:
        raise ProductionMigrationError(
            reasons[0],
            f"SQLite sidecars are present: {', '.join(reasons)}; none were removed.",
            phase=phase,
            reason_codes=reasons,
        )


def _default_quiescence_probe(path: Path) -> tuple[str, ...]:
    """Reuse the established production process/task/handle quiescence proof."""
    from app.operations.stage1_migration import (
        Stage1MigrationPreflightError,
        _default_quiesce_probe as full_quiesce_probe,
    )

    try:
        report = full_quiesce_probe(PROJECT_ROOT, path)
    except Stage1MigrationPreflightError as exc:
        raise RuntimeError(str(exc)) from exc
    blockers = (
        tuple(f"process:{pid}" for pid in report.project_process_ids)
        + tuple(f"handle:{value}" for value in report.locked_paths)
        + tuple(f"scheduled_task:{value}" for value in report.scheduled_tasks)
    )
    return blockers


def _assert_quiescent(
    path: Path,
    probe: QuiescenceProbe,
    *,
    phase: str,
) -> None:
    try:
        blocked = tuple(probe(path))
    except ProductionMigrationError:
        raise
    except Exception as exc:
        raise ProductionMigrationError(
            "DATABASE_NOT_QUIESCENT",
            f"quiescence could not be proven: {exc}",
            phase=phase,
            reason_codes=("DATABASE_NOT_QUIESCENT",),
        ) from exc
    if blocked:
        raise ProductionMigrationError(
            "DATABASE_NOT_QUIESCENT",
            f"database has active or unshareable handles: {blocked}",
            phase=phase,
            reason_codes=("DATABASE_NOT_QUIESCENT",),
        )


def _immutable_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.resolve(strict=True).as_uri()}?mode=ro&immutable=1",
        uri=True,
    )
    connection.execute("PRAGMA query_only=ON")
    return connection


def _inspect_database(path: Path) -> DatabaseInspection:
    before = _capture_file_state(path)
    connection: sqlite3.Connection | None = None
    try:
        connection = _immutable_connection(path)
        ledger_exists = connection.execute(
            "SELECT 1 FROM sqlite_schema "
            "WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if ledger_exists is None:
            raise ProductionMigrationError(
                "MIGRATION_LEDGER_MISSING",
                "schema_migrations table is missing.",
                phase="database_preflight",
            )
        versions = tuple(
            str(row[0]) for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
        integrity = tuple(
            str(row[0]) for row in connection.execute("PRAGMA integrity_check")
        )
        foreign_keys = tuple(
            tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
        )
        objects = frozenset(
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                "SELECT type, name FROM sqlite_schema "
                "WHERE type IN ('table','trigger','index') AND name IS NOT NULL"
            )
        )
    except ProductionMigrationError:
        raise
    except sqlite3.Error as exc:
        raise ProductionMigrationError(
            "DATABASE_INTEGRITY_FAILED",
            f"immutable SQLite inspection failed: {exc}",
            phase="database_preflight",
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    after = _capture_file_state(path)
    if before != after:
        raise ProductionMigrationError(
            "DATABASE_STATE_UNSTABLE",
            "database changed during immutable inspection.",
            phase="database_preflight",
        )
    return DatabaseInspection(
        file=after,
        versions=versions,
        integrity_check=integrity,
        foreign_key_violations=foreign_keys,
        objects=objects,
    )


def _validate_migration_contract() -> tuple[str, ...]:
    canonical = canonical_migration_versions()
    if (
        len(canonical) != 18
        or canonical[13] != SUPPORTED_FROM_VERSION
        or canonical[14:] != MIGRATION_SEQUENCE
        or canonical[-1] != SUPPORTED_TARGET_VERSION
    ):
        raise ProductionMigrationError(
            "MIGRATION_CONTRACT_INVALID",
            "repository migration ledger is not the exact supported 0001..0018 ladder.",
            phase="contract_preflight",
        )
    return canonical


def _validate_ledger(
    versions: tuple[str, ...],
    *,
    canonical: tuple[str, ...],
) -> str:
    if not versions:
        raise ProductionMigrationError(
            "MIGRATION_LEDGER_MISSING",
            "schema_migrations contains no versions.",
            phase="database_preflight",
        )
    if len(versions) != len(set(versions)):
        raise ProductionMigrationError(
            "MIGRATION_LEDGER_DUPLICATE",
            "schema_migrations contains duplicate versions.",
            phase="database_preflight",
        )
    if any(version > SUPPORTED_TARGET_VERSION for version in versions):
        raise ProductionMigrationError(
            "FUTURE_SCHEMA_VERSION",
            f"unsupported future schema version observed: {versions[-1]}",
            phase="database_preflight",
        )
    if versions != canonical[:len(versions)]:
        raise ProductionMigrationError(
            "MIGRATION_LEDGER_INVALID",
            "schema_migrations is not an exact canonical prefix.",
            phase="database_preflight",
        )
    current = versions[-1]
    if current not in SUPPORTED_STATES:
        raise ProductionMigrationError(
            "UNSUPPORTED_SCHEMA_STATE",
            f"supported current states are 0014..0018; observed {current}.",
            phase="database_preflight",
        )
    expected_count = canonical.index(current) + 1
    if len(versions) != expected_count:
        raise ProductionMigrationError(
            "MIGRATION_LEDGER_INVALID",
            f"ledger count {len(versions)} disagrees with current version {current}.",
            phase="database_preflight",
        )
    return current


def _validate_physical_schema(
    current_version: str,
    objects: frozenset[tuple[str, str]],
) -> None:
    current_index = SUPPORTED_STATES.index(current_version)
    required: set[tuple[str, str]] = set()
    forbidden: set[tuple[str, str]] = set()
    for version_index, version in enumerate(MIGRATION_SEQUENCE, start=1):
        target = required if version_index <= current_index else forbidden
        target.update(_VERSION_OBJECTS[version])
    missing = sorted(required - objects)
    premature = sorted(forbidden & objects)
    if missing or premature:
        raise ProductionMigrationError(
            "SCHEMA_LEDGER_MISMATCH",
            f"physical schema disagrees with ledger; missing={missing}, premature={premature}",
            phase="database_preflight",
        )


def _validate_inspection(
    inspection: DatabaseInspection,
    *,
    canonical: tuple[str, ...],
) -> str:
    current = _validate_ledger(inspection.versions, canonical=canonical)
    if inspection.integrity_check != ("ok",):
        raise ProductionMigrationError(
            "DATABASE_INTEGRITY_FAILED",
            f"integrity_check returned {inspection.integrity_check!r}.",
            phase="database_preflight",
        )
    if inspection.foreign_key_violations:
        raise ProductionMigrationError(
            "DATABASE_FOREIGN_KEY_FAILED",
            f"foreign_key_check returned {len(inspection.foreign_key_violations)} rows.",
            phase="database_preflight",
        )
    _validate_physical_schema(current, inspection.objects)
    return current


def _validate_request_contract(request: ProductionMigrationRequest) -> None:
    if not request.confirmed_0014_to_0018:
        raise ProductionMigrationError(
            "OWNER_CONFIRMATION_REQUIRED",
            f"explicit {CONFIRMATION_FLAG} approval is required.",
            phase="argument_preflight",
        )
    if request.expected_from_version != SUPPORTED_FROM_VERSION:
        raise ProductionMigrationError(
            "UNSUPPORTED_FROM_VERSION",
            f"expected-from-version must be exactly {SUPPORTED_FROM_VERSION}.",
            phase="argument_preflight",
        )
    if request.target_version != SUPPORTED_TARGET_VERSION:
        raise ProductionMigrationError(
            "UNSUPPORTED_TARGET_VERSION",
            f"target-version must be exactly {SUPPORTED_TARGET_VERSION}.",
            phase="argument_preflight",
        )
    if not _SHA256_PATTERN.fullmatch(request.expected_sha256):
        raise ProductionMigrationError(
            "EXPECTED_SHA256_INVALID",
            "expected SHA-256 must contain exactly 64 hexadecimal characters.",
            phase="argument_preflight",
        )
    if isinstance(request.expected_size, bool) or request.expected_size < 0:
        raise ProductionMigrationError(
            "EXPECTED_SIZE_INVALID",
            "expected size must be a non-negative integer.",
            phase="argument_preflight",
        )


def _initial_preflight(
    request: ProductionMigrationRequest,
    *,
    project_root: Path,
    quiescence_probe: QuiescenceProbe,
) -> tuple[Path, Path, tuple[str, ...], DatabaseInspection]:
    _validate_request_contract(request)
    canonical = _validate_migration_contract()
    source = _canonical_database_path(request.db_path)
    snapshot = _canonical_snapshot_target(
        request.snapshot_path,
        source=source,
        project_root=project_root,
    )
    _assert_no_sidecars(source, phase="initial_preflight")
    _assert_quiescent(
        source, quiescence_probe, phase="initial_preflight",
    )
    inspection = _inspect_database(source)
    current = _validate_inspection(inspection, canonical=canonical)
    if inspection.file.canonical_path != str(source):
        raise ProductionMigrationError(
            "DATABASE_PATH_IDENTITY_MISMATCH",
            "observed canonical database path changed during preflight.",
            phase="initial_preflight",
        )
    if inspection.file.sha256 != request.expected_sha256.upper():
        raise ProductionMigrationError(
            "DATABASE_SHA256_MISMATCH",
            f"expected {request.expected_sha256.upper()}, observed {inspection.file.sha256}.",
            phase="initial_preflight",
        )
    if inspection.file.size != request.expected_size:
        raise ProductionMigrationError(
            "DATABASE_SIZE_MISMATCH",
            f"expected {request.expected_size} B, observed {inspection.file.size} B.",
            phase="initial_preflight",
        )
    _assert_no_sidecars(source, phase="initial_preflight")
    if current == SUPPORTED_FROM_VERSION and len(inspection.versions) != 14:
        raise ProductionMigrationError(
            "MIGRATION_LEDGER_INVALID",
            "0014 start must contain exactly 14 migration entries.",
            phase="initial_preflight",
        )
    return source, snapshot, canonical, inspection


def _copy_snapshot(source: Path, target: Path) -> None:
    created = False
    try:
        with source.open("rb") as source_handle, target.open("xb") as target_handle:
            created = True
            while chunk := source_handle.read(1024 * 1024):
                target_handle.write(chunk)
            target_handle.flush()
            os.fsync(target_handle.fileno())
    except Exception as exc:
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise ProductionMigrationError(
            "SNAPSHOT_COPY_FAILED",
            f"exclusive snapshot copy failed: {exc}",
            phase="snapshot_copy",
        ) from exc


def _verify_snapshot(
    snapshot: Path,
    *,
    source_inspection: DatabaseInspection,
    canonical: tuple[str, ...],
) -> DatabaseInspection:
    try:
        inspection = _inspect_database(snapshot)
        _validate_inspection(inspection, canonical=canonical)
    except ProductionMigrationError as exc:
        raise ProductionMigrationError(
            "SNAPSHOT_VALIDATION_FAILED",
            f"snapshot immutable validation failed: {exc}",
            phase="snapshot_validation",
            reason_codes=(exc.code,),
            snapshot_path=snapshot,
        ) from exc
    if (
        inspection.file.sha256 != source_inspection.file.sha256
        or inspection.file.size != source_inspection.file.size
        or inspection.versions != source_inspection.versions
    ):
        raise ProductionMigrationError(
            "SNAPSHOT_MISMATCH",
            "snapshot is not byte-identical to the approved current database.",
            phase="snapshot_validation",
            snapshot_path=snapshot,
        )
    _assert_no_sidecars(snapshot, phase="snapshot_validation")
    return inspection


def _run_failpoint(failpoint: Failpoint | None, name: str) -> None:
    if failpoint is None:
        return
    try:
        failpoint(name)
    except Exception as exc:
        raise _ControlledFailpoint(name, exc) from exc


def _stale_from(error: ProductionMigrationError, *, phase: str) -> ProductionMigrationError:
    reasons = error.reason_codes or (error.code,)
    return ProductionMigrationError(
        "STALE_DATABASE_STATE",
        f"database changed after initial preflight: {error}",
        phase=phase,
        reason_codes=reasons,
    )


def _revalidate_source(
    source: Path,
    *,
    initial: DatabaseInspection,
    canonical: tuple[str, ...],
    quiescence_probe: QuiescenceProbe,
    phase: str,
) -> DatabaseInspection:
    try:
        _assert_no_sidecars(source, phase=phase)
        _assert_quiescent(source, quiescence_probe, phase=phase)
        current = _inspect_database(source)
        _validate_inspection(current, canonical=canonical)
        _assert_no_sidecars(source, phase=phase)
    except ProductionMigrationError as exc:
        raise _stale_from(exc, phase=phase) from exc
    if current != initial:
        raise ProductionMigrationError(
            "STALE_DATABASE_STATE",
            "canonical path, file identity, size, SHA-256, ledger, or checks changed.",
            phase=phase,
        )
    return current


def _next_migration(current: str) -> str | None:
    if current == SUPPORTED_TARGET_VERSION:
        return None
    return SUPPORTED_STATES[SUPPORTED_STATES.index(current) + 1]


def _recovery_error(
    source: Path,
    *,
    canonical: tuple[str, ...],
    phase: str,
    detail: str,
    snapshot: Path | None,
    reason_code: str,
) -> ProductionMigrationError:
    try:
        _assert_no_sidecars(source, phase=phase)
        inspection = _inspect_database(source)
        current = _validate_inspection(inspection, canonical=canonical)
    except ProductionMigrationError as exc:
        return ProductionMigrationError(
            "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT",
            f"{detail}; durable state could not be proven: {exc}",
            phase=phase,
            reason_codes=(reason_code, exc.code),
            snapshot_path=snapshot,
        )
    return ProductionMigrationError(
        reason_code,
        detail,
        phase=phase,
        reason_codes=(reason_code,),
        durable_version=current,
        next_migration=_next_migration(current),
        snapshot_path=snapshot,
        database_state=inspection.file,
    )


def _open_verified_writable(
    source: Path,
    *,
    expected: DatabaseInspection,
) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(f"{source.as_uri()}?mode=rw", uri=True)
    except sqlite3.Error as exc:
        raise ProductionMigrationError(
            "WRITABLE_OPEN_FAILED",
            f"cannot open existing database with mode=rw: {exc}",
            phase="writable_open",
        ) from exc
    try:
        connection.row_factory = sqlite3.Row
        register_evidence_hash_function(connection)
        observed_versions = connection_schema_versions(connection)
        observed_file = _capture_file_state(source)
        if observed_versions != expected.versions or observed_file != expected.file:
            raise ProductionMigrationError(
                "STALE_DATABASE_STATE",
                "writable handle did not observe the exact revalidated database state.",
                phase="writable_open",
            )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection
    except Exception:
        connection.close()
        raise


def _validate_final_database(
    source: Path,
    *,
    canonical: tuple[str, ...],
    failpoint: Failpoint | None,
) -> DatabaseInspection:
    _assert_no_sidecars(source, phase="final_validation")
    before = _capture_file_state(source)
    try:
        _run_failpoint(failpoint, "during_final_validation")
        inspection = _inspect_database(source)
        current = _validate_inspection(inspection, canonical=canonical)
        if (
            current != SUPPORTED_TARGET_VERSION
            or len(inspection.versions) != 18
            or len(set(inspection.versions)) != 18
        ):
            raise ProductionMigrationError(
                "FINAL_SCHEMA_INVALID",
                "final ledger must contain each canonical version exactly once through 0018.",
                phase="final_validation",
            )
        require_database_schema(source, required_version=SUPPORTED_TARGET_VERSION)
        after_runtime_gate = _capture_file_state(source)
        if after_runtime_gate != before or inspection.file != before:
            raise ProductionMigrationError(
                "RUNTIME_GATE_MUTATED_DATABASE",
                "immutable runtime exact-schema gate changed the database file.",
                phase="final_validation",
            )
        _assert_no_sidecars(source, phase="final_validation")
        return inspection
    except _ControlledFailpoint as exc:
        raise ProductionMigrationError(
            "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT",
            f"controlled failpoint interrupted final validation: {exc}",
            phase="final_validation",
            reason_codes=("CONTROLLED_FAILPOINT",),
        ) from exc
    except ProductionMigrationError as exc:
        if exc.code == "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT":
            raise
        raise ProductionMigrationError(
            "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT",
            f"final immutable validation failed: {exc}",
            phase="final_validation",
            reason_codes=(exc.code,),
        ) from exc


def run_production_schema_migration(
    request: ProductionMigrationRequest,
    *,
    project_root: Path = PROJECT_ROOT,
    quiescence_probe: QuiescenceProbe | None = None,
    failpoint: Failpoint | None = None,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> ProductionMigrationResult:
    """Execute or resume only the controlled 0014->0018 production ladder."""
    effective_quiescence_probe = quiescence_probe or _default_quiescence_probe
    source, snapshot, canonical, initial = _initial_preflight(
        request,
        project_root=project_root,
        quiescence_probe=effective_quiescence_probe,
    )
    source_version = initial.current_version

    if source_version == SUPPORTED_TARGET_VERSION:
        final = _validate_final_database(
            source, canonical=canonical, failpoint=failpoint,
        )
        return ProductionMigrationResult(
            status="ALREADY_AT_TARGET",
            db_path=str(source),
            snapshot_path=None,
            source_version=source_version,
            target_version=SUPPORTED_TARGET_VERSION,
            applied_migrations=(),
            durable_version=SUPPORTED_TARGET_VERSION,
            database_before=initial.file,
            database_after=final.file,
            snapshot=None,
            runtime_gate_sha_unchanged=initial.file == final.file,
        )

    try:
        _run_failpoint(failpoint, "before_snapshot")
    except _ControlledFailpoint as exc:
        raise _recovery_error(
            source, canonical=canonical, phase=exc.name, detail=str(exc),
            snapshot=None, reason_code="CONTROLLED_FAILPOINT",
        ) from exc

    _copy_snapshot(source, snapshot)
    snapshot_inspection = _verify_snapshot(
        snapshot, source_inspection=initial, canonical=canonical,
    )
    try:
        _run_failpoint(failpoint, "after_snapshot")
        _revalidate_source(
            source,
            initial=initial,
            canonical=canonical,
            quiescence_probe=effective_quiescence_probe,
            phase="second_preflight",
        )
        _run_failpoint(failpoint, "after_second_preflight")
        _run_failpoint(failpoint, "before_writable_open")
        # A final independent read occurs after both interposition windows and
        # immediately before mode=rw.  A sidecar or byte change introduced by
        # either hook is therefore refused without writable open.
        pre_open = _revalidate_source(
            source,
            initial=initial,
            canonical=canonical,
            quiescence_probe=effective_quiescence_probe,
            phase="immediate_pre_writable_open",
        )
    except _ControlledFailpoint as exc:
        raise _recovery_error(
            source, canonical=canonical, phase=exc.name, detail=str(exc),
            snapshot=snapshot, reason_code="CONTROLLED_FAILPOINT",
        ) from exc

    connection: sqlite3.Connection | None = None
    applied: list[str] = []
    active_phase = "writable_open"
    transaction_failures: list[_ControlledFailpoint] = []
    try:
        connection = _open_verified_writable(source, expected=pre_open)
        current = source_version
        for target in MIGRATION_SEQUENCE:
            if SUPPORTED_STATES.index(target) <= SUPPORTED_STATES.index(current):
                continue
            active_phase = f"before_{target[:4]}"
            _run_failpoint(failpoint, active_phase)

            def transaction_failpoint(version: str) -> None:
                try:
                    _run_failpoint(failpoint, f"during_{version[:4]}")
                except _ControlledFailpoint as exc:
                    transaction_failures.append(exc)
                    raise

            active_phase = f"during_{target[:4]}"
            newly = apply_migrations(
                connection,
                migrations_dir,
                through=target,
                transaction_failpoint=transaction_failpoint,
            )
            if newly != [target]:
                raise ProductionMigrationError(
                    "MIGRATION_STEP_CONTRACT_VIOLATION",
                    f"expected exactly {target}, applied {newly!r}.",
                    phase=active_phase,
                )
            observed = connection_schema_versions(connection)
            if observed != canonical[:canonical.index(target) + 1]:
                raise ProductionMigrationError(
                    "MIGRATION_LEDGER_INVALID",
                    f"ledger after {target} is not the exact canonical prefix.",
                    phase=active_phase,
                )
            object_rows = frozenset(
                (str(row[0]), str(row[1]))
                for row in connection.execute(
                    "SELECT type, name FROM sqlite_schema "
                    "WHERE type IN ('table','trigger','index') AND name IS NOT NULL"
                )
            )
            _validate_physical_schema(target, object_rows)
            applied.append(target)
            current = target
            active_phase = f"after_{target[:4]}"
            _run_failpoint(failpoint, active_phase)
    except Exception as exc:
        if connection is not None:
            connection.close()
            connection = None
        controlled_failure = (
            exc if isinstance(exc, _ControlledFailpoint)
            else (transaction_failures[-1] if transaction_failures else None)
        )
        failpoint_name = (
            controlled_failure.name if controlled_failure is not None else active_phase
        )
        reason = (
            "CONTROLLED_FAILPOINT"
            if controlled_failure is not None
            else (
                exc.code if isinstance(exc, ProductionMigrationError)
                else "MIGRATION_STEP_FAILED"
            )
        )
        raise _recovery_error(
            source,
            canonical=canonical,
            phase=failpoint_name,
            detail=f"migration sequence stopped without retry: {exc}",
            snapshot=snapshot,
            reason_code=reason,
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    try:
        _run_failpoint(failpoint, "before_final_validation")
    except _ControlledFailpoint as exc:
        raise _recovery_error(
            source, canonical=canonical, phase=exc.name, detail=str(exc),
            snapshot=snapshot, reason_code="CONTROLLED_FAILPOINT",
        ) from exc

    try:
        final = _validate_final_database(
            source, canonical=canonical, failpoint=failpoint,
        )
    except ProductionMigrationError as exc:
        if exc.database_state is not None:
            raise
        try:
            state = _capture_file_state(source)
        except ProductionMigrationError:
            state = None
        raise ProductionMigrationError(
            "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT",
            exc.detail,
            phase=exc.phase,
            reason_codes=exc.reason_codes,
            durable_version=SUPPORTED_TARGET_VERSION,
            next_migration=None,
            snapshot_path=snapshot,
            database_state=state,
        ) from exc

    return ProductionMigrationResult(
        status="MIGRATION_COMPLETE",
        db_path=str(source),
        snapshot_path=str(snapshot),
        source_version=source_version,
        target_version=SUPPORTED_TARGET_VERSION,
        applied_migrations=tuple(applied),
        durable_version=final.current_version,
        database_before=initial.file,
        database_after=final.file,
        snapshot=snapshot_inspection.file,
        runtime_gate_sha_unchanged=True,
    )
