"""Controlled Stage 1 migration rehearsal on copies; never replaces the source DB."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
from typing import Callable

from app.core.money import sum_usd
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect


EXPECTED_MIGRATIONS = tuple(
    path.stem for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
)
SOURCE_MIGRATIONS = EXPECTED_MIGRATIONS[:9]
TARGET_MIGRATIONS = EXPECTED_MIGRATIONS[:14]
MIGRATIONS_0010_TO_0014 = EXPECTED_MIGRATIONS[9:14]

STAGE1_BLOCKED_FLAGS = {
    "kill_switch": False,
    "worker_enabled": False,
    "safe_mode": False,
    "paid_actions_enabled": False,
    "browser_actions_enabled": False,
}

# Closed defense-in-depth set after 0009 -> 0014. Extra future triggers are
# allowed, but every trigger in this set must exist before a candidate passes.
REQUIRED_STAGE1_TRIGGERS = frozenset({
    "provider_attempts_initial_state",
    "provider_attempts_request_id_matches_identity",
    "provider_attempts_no_retry_without_resolver",
    "provider_attempts_identity_is_immutable",
    "provider_attempts_execution_intent_fingerprint_is_immutable",
    "provider_attempts_durable_v2_requires_execution_intent_fingerprint",
    "provider_attempts_controlled_transition",
    "jobs_terminal_requires_provider_attempt_normalized",
    "runs_terminal_requires_provider_attempt_normalized",
    "research_runs_terminal_requires_provider_attempt_normalized",
    "provider_attempts_reconciled_terminal_is_immutable",
    "provider_attempts_reconciled_terminal_no_delete",
    "provider_attempts_no_delete_with_nonlegacy_usage",
    "provider_attempts_reconciled_settled_requires_canonical_usage",
    "provider_attempts_reconciled_released_forbids_canonical_usage",
    "provider_attempts_terminal_requires_final_event",
    "provider_attempts_terminal_requires_terminal_lifecycle",
    "provider_attempts_terminal_requires_consistent_cost_cache",
    "provider_attempts_reconcile_requires_consistent_lineage",
    "legacy_model_usage_proofs_no_runtime_insert",
    "legacy_model_usage_proofs_immutable",
    "legacy_model_usage_proofs_no_delete",
    "model_usage_legacy_proof_required",
    "model_usage_legacy_row_no_delete",
    "model_usage_durable_identity_is_immutable",
    "model_usage_requires_request_job_run_relation",
    "model_usage_request_job_run_relation_on_update",
    "model_usage_reconciled_attempt_is_immutable",
    "model_usage_reconciled_attempt_no_delete",
    "runs_cost_cache_frozen_after_reconciliation",
    "research_runs_cost_cache_frozen_after_reconciliation",
    "reconciliation_events_sequence_is_monotonic",
    "reconciliation_events_require_active_attempt",
    "reconciliation_events_no_update",
    "reconciliation_events_no_delete",
})


class Stage1MigrationPreflightError(RuntimeError):
    pass


@dataclass(frozen=True)
class FileFingerprint:
    sha256: str
    size: int
    mtime_ns: int
    mtime_utc: str


@dataclass(frozen=True)
class Stage1MigrationRequest:
    project_root: Path
    source_db: Path
    workspace: Path
    expected_branch: str
    expected_head: str
    expected_source_sha256: str
    expected_source_size: int
    expected_source_mtime_utc: str
    expected_legacy_usage_count: int = 13
    expected_real_cost_usd: str = "0.684580"


@dataclass(frozen=True)
class Stage1MigrationResult:
    report_path: Path
    backup_path: Path
    candidate_path: Path
    source: FileFingerprint
    backup: FileFingerprint
    candidate: FileFingerprint
    applied_migrations: tuple[str, ...]
    trigger_count: int
    legacy_proof_count: int
    real_cost_usd: str


GitIdentityProvider = Callable[[Path], tuple[str, str]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _format_mtime_utc(mtime_ns: int) -> str:
    seconds, fraction = divmod(mtime_ns, 1_000_000_000)
    prefix = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    digits = f"{fraction:09d}"
    if fraction % 100 == 0:
        digits = digits[:7]
    return f"{prefix}.{digits}Z"


_UTC_MTIME = re.compile(
    r"^(?P<base>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d{1,9}))?Z$"
)


def parse_mtime_utc_ns(value: str) -> int:
    match = _UTC_MTIME.fullmatch(value)
    if match is None:
        raise ValueError("mtime must be UTC ISO-8601 ending in Z with up to 9 fractional digits.")
    base = datetime.fromisoformat(match.group("base")).replace(tzinfo=timezone.utc)
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return calendar.timegm(base.utctimetuple()) * 1_000_000_000 + int(fraction or "0")


def fingerprint(path: Path | str) -> FileFingerprint:
    resolved = Path(path).resolve()
    stat = resolved.stat()
    return FileFingerprint(
        sha256=_sha256(resolved),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        mtime_utc=_format_mtime_utc(stat.st_mtime_ns),
    )


def _git_identity(project_root: Path) -> tuple[str, str]:
    branch = subprocess.run(
        ["git", "branch", "--show-current"], cwd=project_root,
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root,
        check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()
    return branch, head


def _read_only_checks(path: Path) -> tuple[list[str], list[tuple[object, ...]]]:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        integrity = [str(row[0]) for row in conn.execute("PRAGMA integrity_check")]
        foreign_keys = [tuple(row) for row in conn.execute("PRAGMA foreign_key_check")]
        return integrity, foreign_keys
    finally:
        conn.close()


def _migration_versions(conn: sqlite3.Connection) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    )


def _real_cost(conn: sqlite3.Connection) -> Decimal:
    values = [
        row[0]
        for row in conn.execute(
            "SELECT estimated_cost_usd FROM model_usage WHERE dry_run=0 ORDER BY id"
        )
    ]
    return sum_usd(values, label="Stage 1 migration real cost")


def _initialize_blocked_flags(conn: sqlite3.Connection, *, timestamp: str) -> None:
    existing = int(conn.execute("SELECT COUNT(*) FROM system_flags").fetchone()[0])
    if existing != 0:
        raise Stage1MigrationPreflightError(
            "system_flags is not empty; explicit owner resolution is required before initialization."
        )
    conn.execute("BEGIN IMMEDIATE")
    try:
        for key, value in STAGE1_BLOCKED_FLAGS.items():
            conn.execute(
                "INSERT INTO system_flags(key,value_json,updated_at,updated_by,reason) "
                "VALUES (?,?,?,?,?)",
                (
                    key,
                    json.dumps(value),
                    timestamp,
                    "stage1-copy-preflight",
                    "Stage 1 controlled migration candidate; paid/browser remain disabled.",
                ),
            )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def run_stage1_copy_preflight(
    request: Stage1MigrationRequest,
    *,
    git_identity_provider: GitIdentityProvider = _git_identity,
    now: datetime | None = None,
) -> Stage1MigrationResult:
    """Create exact backup + candidate and migrate only the candidate to 0014."""
    if len(EXPECTED_MIGRATIONS) != 14:
        raise Stage1MigrationPreflightError(
            f"Current code exposes {len(EXPECTED_MIGRATIONS)} migrations, expected 14."
        )
    project_root = request.project_root.resolve()
    source = request.source_db.resolve()
    workspace = request.workspace.resolve()
    if not source.is_file():
        raise Stage1MigrationPreflightError(f"Source database does not exist: {source}")
    if (
        workspace == source.parent
        or source in workspace.parents
        or source.parent in workspace.parents
    ):
        raise Stage1MigrationPreflightError("Workspace must be separate from the source database path.")
    if workspace.exists() and any(workspace.iterdir()):
        raise Stage1MigrationPreflightError("Workspace must be absent or empty.")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{source}{suffix}")
        if sidecar.exists():
            raise Stage1MigrationPreflightError(
                f"Source SQLite sidecar exists ({sidecar.name}); stop all processes and checkpoint first."
            )

    try:
        branch, head = git_identity_provider(project_root)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stage1MigrationPreflightError(f"Cannot verify Git branch/HEAD: {exc}") from exc
    if branch != request.expected_branch or head != request.expected_head:
        raise Stage1MigrationPreflightError(
            f"Git identity mismatch: branch={branch!r}, HEAD={head!r}."
        )

    source_before = fingerprint(source)
    expected_mtime_ns = parse_mtime_utc_ns(request.expected_source_mtime_utc)
    if (
        source_before.sha256 != request.expected_source_sha256.upper()
        or source_before.size != request.expected_source_size
        or source_before.mtime_ns != expected_mtime_ns
    ):
        raise Stage1MigrationPreflightError(
            "Source SHA-256, size, or mtime does not match the approved baseline."
        )

    workspace.mkdir(parents=True, exist_ok=True)
    backup = workspace / "agent.schema-0009.full-backup.db"
    candidate = workspace / "agent.schema-0014.candidate.db"
    shutil.copy2(source, backup)
    backup_fingerprint = fingerprint(backup)
    if backup_fingerprint != source_before:
        raise Stage1MigrationPreflightError("Full backup is not byte/metadata-identical to source.")
    shutil.copy2(backup, candidate)

    integrity_before, foreign_before = _read_only_checks(backup)
    if integrity_before != ["ok"] or foreign_before:
        raise Stage1MigrationPreflightError(
            f"Backup integrity failed: integrity={integrity_before}, foreign_keys={foreign_before}."
        )

    candidate_conn = connect(candidate)
    try:
        source_versions = _migration_versions(candidate_conn)
        if source_versions != SOURCE_MIGRATIONS:
            raise Stage1MigrationPreflightError(
                f"Candidate source schema is {source_versions!r}, expected exact 0001..0009."
            )
        cost_before = _real_cost(candidate_conn)
        expected_cost = Decimal(request.expected_real_cost_usd).quantize(Decimal("0.000001"))
        if cost_before != expected_cost:
            raise Stage1MigrationPreflightError(
                f"Pre-migration real cost is {cost_before:.6f}, expected {expected_cost:.6f}."
            )
        applied = tuple(apply_migrations(candidate_conn))
        if applied != MIGRATIONS_0010_TO_0014:
            raise Stage1MigrationPreflightError(
                f"Applied migration set is {applied!r}, expected 0010..0014."
            )
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        _initialize_blocked_flags(candidate_conn, timestamp=timestamp)
        second_pass = tuple(apply_migrations(candidate_conn))
        if second_pass:
            raise Stage1MigrationPreflightError(
                f"Migration runner is not idempotent; second pass applied {second_pass!r}."
            )
        if _migration_versions(candidate_conn) != TARGET_MIGRATIONS:
            raise Stage1MigrationPreflightError("Candidate does not contain exact 0001..0014 ledger entries.")

        triggers = {
            str(row[0])
            for row in candidate_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        missing_triggers = sorted(REQUIRED_STAGE1_TRIGGERS - triggers)
        if missing_triggers:
            raise Stage1MigrationPreflightError(
                "Candidate is missing required triggers: " + ", ".join(missing_triggers)
            )

        legacy_proofs = int(
            candidate_conn.execute(
                "SELECT COUNT(*) FROM legacy_model_usage_proofs p "
                "JOIN model_usage u ON u.id=p.usage_id "
                "WHERE p.migration_version='0012_provider_ledger_hardening' "
                "AND u.dry_run=0 AND u.is_legacy_usage=1 AND u.request_id IS NULL"
            ).fetchone()[0]
        )
        if legacy_proofs != request.expected_legacy_usage_count:
            raise Stage1MigrationPreflightError(
                f"Legacy proof count is {legacy_proofs}, expected {request.expected_legacy_usage_count}."
            )
        cost_after = _real_cost(candidate_conn)
        if cost_after != cost_before:
            raise Stage1MigrationPreflightError(
                f"Migration changed real cost from {cost_before:.6f} to {cost_after:.6f}."
            )
        flag_rows = {
            str(row[0]): json.loads(str(row[1]))
            for row in candidate_conn.execute(
                "SELECT key,value_json FROM system_flags ORDER BY key"
            )
        }
        if flag_rows != STAGE1_BLOCKED_FLAGS:
            raise Stage1MigrationPreflightError(
                f"Candidate system_flags are not the approved blocked profile: {flag_rows!r}."
            )
        candidate_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        candidate_conn.close()

    integrity_after, foreign_after = _read_only_checks(candidate)
    if integrity_after != ["ok"] or foreign_after:
        raise Stage1MigrationPreflightError(
            f"Candidate integrity failed: integrity={integrity_after}, foreign_keys={foreign_after}."
        )
    source_after = fingerprint(source)
    if source_after != source_before:
        raise Stage1MigrationPreflightError("Source database changed during copy preflight.")
    if fingerprint(backup) != backup_fingerprint:
        raise Stage1MigrationPreflightError("Full backup changed during candidate migration.")
    candidate_fingerprint = fingerprint(candidate)

    report = {
        "status": "COPY_PREFLIGHT_PASSED_NOT_PRODUCTION_MIGRATION",
        "git": {"branch": branch, "head": head},
        "source": source_before.__dict__,
        "backup": backup_fingerprint.__dict__,
        "candidate": candidate_fingerprint.__dict__,
        "migrations_before": list(SOURCE_MIGRATIONS),
        "migrations_applied": list(MIGRATIONS_0010_TO_0014),
        "migrations_after": list(TARGET_MIGRATIONS),
        "required_trigger_count": len(REQUIRED_STAGE1_TRIGGERS),
        "observed_trigger_count": len(triggers),
        "legacy_proof_count": legacy_proofs,
        "real_cost_usd_before": f"{cost_before:.6f}",
        "real_cost_usd_after": f"{cost_after:.6f}",
        "system_flags": STAGE1_BLOCKED_FLAGS,
        "source_unchanged": True,
        "production_database_migrated": False,
        "new_baseline_candidate_sha256": candidate_fingerprint.sha256,
        "rollback": {
            "method": "full_file_restore",
            "source": str(backup),
            "constraint": "VERIFIED BACKUP ONLY; NO REVERSE SQL MUTATION",
        },
    }
    report_path = workspace / "stage1-copy-preflight-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return Stage1MigrationResult(
        report_path=report_path,
        backup_path=backup,
        candidate_path=candidate,
        source=source_before,
        backup=backup_fingerprint,
        candidate=candidate_fingerprint,
        applied_migrations=MIGRATIONS_0010_TO_0014,
        trigger_count=len(triggers),
        legacy_proof_count=legacy_proofs,
        real_cost_usd=f"{cost_after:.6f}",
    )
