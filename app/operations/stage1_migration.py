"""Canonical, fail-closed Stage 1 database migration tooling."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import time
from typing import Any, Callable

from app.core.money import sum_usd
from app.core.security_flags import SECURITY_FLAG_DEFAULTS
from app.storage.db import MIGRATIONS_DIR, apply_migrations, connect


EXPECTED_MIGRATIONS = tuple(
    path.stem for path in sorted(MIGRATIONS_DIR.glob("*.sql"))
)
SOURCE_MIGRATIONS = EXPECTED_MIGRATIONS[:9]
TARGET_MIGRATIONS = EXPECTED_MIGRATIONS[:14]
MIGRATIONS_0010_TO_0014 = EXPECTED_MIGRATIONS[9:14]

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


@dataclass(frozen=True)
class DatabaseFileSetFingerprint:
    database: FileFingerprint
    wal: FileFingerprint | None
    shm: FileFingerprint | None


@dataclass(frozen=True)
class QuiesceProcessIdentity:
    pid: int
    parent_pid: int
    executable: str
    command_line: str
    creation_time_utc: str
    classification: str
    reason_codes: tuple[str, ...]
    blocking: bool


@dataclass(frozen=True)
class QuiesceReport:
    project_process_ids: tuple[int, ...] = ()
    locked_paths: tuple[str, ...] = ()
    scheduled_tasks: tuple[str, ...] = ()
    probe_current_pid: int | None = None
    probe_parent_pid: int | None = None
    probe_helper_process_ids: tuple[int, ...] = ()
    process_diagnostics: tuple[QuiesceProcessIdentity, ...] = ()

    @property
    def is_quiescent(self) -> bool:
        return not (self.project_process_ids or self.locked_paths or self.scheduled_tasks)


@dataclass(frozen=True)
class Stage1InPlaceMigrationResult:
    report_path: Path
    backup_dir: Path
    rehearsal_path: Path
    baseline_path: Path
    source_before: DatabaseFileSetFingerprint
    source_after: DatabaseFileSetFingerprint
    applied_migrations: tuple[str, ...]
    trigger_count: int
    legacy_proof_count: int
    real_cost_usd: str


QuiesceProbe = Callable[[Path, Path], QuiesceReport]


GitIdentityProvider = Callable[[Path], tuple[str, str]]


@dataclass(frozen=True)
class _WindowsProcessSnapshot:
    pid: int
    parent_pid: int
    executable: str
    command_line: str
    creation_time_utc: str


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


def database_file_set_fingerprint(path: Path | str) -> DatabaseFileSetFingerprint:
    """Fingerprint the main DB and optional WAL/SHM without opening SQLite."""
    database = Path(path).resolve()
    return DatabaseFileSetFingerprint(
        database=fingerprint(database),
        wal=fingerprint(Path(f"{database}-wal")) if Path(f"{database}-wal").exists() else None,
        shm=fingerprint(Path(f"{database}-shm")) if Path(f"{database}-shm").exists() else None,
    )


def _file_set_as_dict(value: DatabaseFileSetFingerprint) -> dict[str, Any]:
    return {
        "database": value.database.__dict__,
        "wal": value.wal.__dict__ if value.wal is not None else None,
        "shm": value.shm.__dict__ if value.shm is not None else None,
    }


def _process_identity_as_dict(value: QuiesceProcessIdentity) -> dict[str, Any]:
    return {
        "pid": value.pid,
        "parent_pid": value.parent_pid,
        "executable": value.executable,
        "command_line": value.command_line,
        "creation_time_utc": value.creation_time_utc,
        "classification": value.classification,
        "reason_codes": list(value.reason_codes),
        "blocking": value.blocking,
    }


def _quiesce_report_as_dict(value: QuiesceReport) -> dict[str, Any]:
    return {
        "project_process_ids": list(value.project_process_ids),
        "locked_paths": list(value.locked_paths),
        "scheduled_tasks": list(value.scheduled_tasks),
        "probe_current_pid": value.probe_current_pid,
        "probe_parent_pid": value.probe_parent_pid,
        "probe_helper_process_ids": list(value.probe_helper_process_ids),
        "process_diagnostics": [
            _process_identity_as_dict(process)
            for process in value.process_diagnostics
        ],
    }


def _assert_sidecar_contract(path: Path, value: DatabaseFileSetFingerprint) -> None:
    journal = Path(f"{path}-journal")
    if journal.exists():
        raise Stage1MigrationPreflightError(
            f"SQLite rollback journal exists ({journal.name}); migration is blocked."
        )
    if value.wal is not None and value.wal.size != 0:
        raise Stage1MigrationPreflightError(
            f"SQLite WAL is non-empty ({value.wal.size} B); migration is blocked."
        )


def _assert_approved_baseline(
    request: Stage1MigrationRequest,
    value: DatabaseFileSetFingerprint,
) -> None:
    expected_mtime_ns = parse_mtime_utc_ns(request.expected_source_mtime_utc)
    database = value.database
    if (
        database.sha256 != request.expected_source_sha256.upper()
        or database.size != request.expected_source_size
        or database.mtime_ns != expected_mtime_ns
    ):
        raise Stage1MigrationPreflightError(
            "Source SHA-256, size, or mtime does not match the approved baseline."
        )


def _windows_locked_paths(source: Path) -> tuple[str, ...]:
    if os.name != "nt":
        raise Stage1MigrationPreflightError(
            "The packaged production quiesce probe is Windows-only and fails closed elsewhere."
        )
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = ctypes.windll.kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    locked: list[str] = []
    for candidate in (source, Path(f"{source}-wal"), Path(f"{source}-shm")):
        if not candidate.exists():
            continue
        handle = create_file(str(candidate), 0x80000000, 0, None, 3, 0x80, None)
        if handle == invalid:
            locked.append(str(candidate))
        else:
            close_handle(handle)
    return tuple(locked)


def _process_snapshot_from_payload(value: object) -> _WindowsProcessSnapshot:
    if not isinstance(value, dict):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: process inventory contains a non-object record."
        )
    try:
        pid = int(value["pid"])
        parent_pid = int(value["parent_pid"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: process inventory has an invalid PID relation."
        ) from exc
    if pid < 0 or parent_pid < 0:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: process inventory has a negative PID."
        )
    return _WindowsProcessSnapshot(
        pid=pid,
        parent_pid=parent_pid,
        executable=str(value.get("executable") or ""),
        command_line=str(value.get("command_line") or ""),
        creation_time_utc=str(value.get("creation_time_utc") or ""),
    )


def _parse_process_inventory(payload: object) -> tuple[_WindowsProcessSnapshot, ...]:
    if not isinstance(payload, dict):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: PowerShell returned a non-object payload."
        )
    raw_processes = payload.get("processes")
    if isinstance(raw_processes, dict):
        raw_processes = [raw_processes]
    if not isinstance(raw_processes, list):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: process inventory is missing."
        )
    processes = tuple(_process_snapshot_from_payload(value) for value in raw_processes)
    process_ids = [value.pid for value in processes]
    if len(process_ids) != len(set(process_ids)):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: process inventory contains duplicate PIDs."
        )
    return processes


def _string_tuple_from_payload(value: object, *, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, list):
        raise Stage1MigrationPreflightError(
            f"Cannot prove full quiescence: {label} is not a list."
        )
    if any(not isinstance(item, str) for item in value):
        raise Stage1MigrationPreflightError(
            f"Cannot prove full quiescence: {label} contains a non-string value."
        )
    return tuple(value)


def _process_role_reason(command_line: str) -> str | None:
    main_command = re.search(
        r"(?i)-m\s+app\.main\s+([a-z][a-z0-9-]*)",
        command_line,
    )
    if main_command is None:
        main_command = re.search(
            r"(?i)app[\\/]+main\.py[\"']?\s+([a-z][a-z0-9-]*)",
            command_line,
        )
    if main_command is not None:
        command = main_command.group(1).lower()
        if command == "worker":
            return "APP_ROLE_WORKER"
        if command == "maintain":
            return "APP_ROLE_MAINTENANCE"
        return "APP_ROLE_OPERATOR_CLI"

    normalized = command_line.replace("\\", "/").casefold()
    if "scripts/run_worker_task.ps1" in normalized:
        return "APP_ROLE_WORKER"
    if "scripts/run_maintenance_task.ps1" in normalized:
        return "APP_ROLE_MAINTENANCE"
    operator_entrypoints = (
        "scripts/prepare_stage1_db_migration.py",
        "scripts/manage_windows_tasks.py",
        "scripts/run_capped_research.py",
        "scripts/run_topics.py",
    )
    if any(entrypoint in normalized for entrypoint in operator_entrypoints):
        return "APP_ROLE_OPERATOR_CLI"
    return None


def _command_line_contains_root(command_line: str, project_root: Path) -> bool:
    normalized_command = command_line.replace("/", "\\").casefold()
    normalized_root = str(project_root.resolve()).replace("/", "\\").casefold()
    return normalized_root in normalized_command


def _identity_is_complete(process: _WindowsProcessSnapshot) -> bool:
    return bool(
        process.executable
        and process.command_line
        and process.creation_time_utc
    )


def _classify_windows_processes(
    processes: tuple[_WindowsProcessSnapshot, ...],
    *,
    project_root: Path,
    current_pid: int,
    parent_pid: int,
    helper_process_ids: frozenset[int],
) -> tuple[QuiesceProcessIdentity, ...]:
    diagnostics: list[QuiesceProcessIdentity] = []
    for process in processes:
        role_reason = _process_role_reason(process.command_line)
        contains_root = _command_line_contains_root(process.command_line, project_root)
        executable_name = Path(process.executable).name.casefold()
        blocking = False
        classification: str | None = None
        reasons: list[str] = []

        if process.pid == current_pid:
            classification = "PROBE_CURRENT"
            reasons.append("PROBE_CURRENT_PID")
        elif process.pid in helper_process_ids:
            classification = "PROBE_HELPER"
            reasons.append("PROBE_REGISTERED_HELPER_IDENTITY")
        elif (
            process.pid == parent_pid
            and executable_name in {"powershell.exe", "pwsh.exe"}
            and role_reason not in {"APP_ROLE_WORKER", "APP_ROLE_MAINTENANCE"}
        ):
            classification = "PROBE_PARENT_LAUNCHER"
            reasons.append("PROBE_PARENT_LAUNCHER")
            if role_reason == "APP_ROLE_OPERATOR_CLI":
                reasons.append("PARENT_COMMAND_REFERENCES_OPERATOR_ENTRYPOINT")
        elif process.pid == parent_pid and role_reason is None:
            classification = "PROBE_PARENT_LAUNCHER"
            reasons.append("PROBE_PARENT_LAUNCHER")
        elif role_reason is not None:
            classification = "BLOCKING_APPLICATION_PROCESS"
            reasons.append(role_reason)
            blocking = True
            if not _identity_is_complete(process):
                reasons.append("PROCESS_IDENTITY_INCOMPLETE")
        elif contains_root:
            if _identity_is_complete(process):
                classification = "OBSERVED_NONBLOCKING"
                reasons.append("PROJECT_ROOT_COMMAND_LINE_ONLY")
            else:
                classification = "BLOCKING_AMBIGUOUS_PROCESS"
                reasons.extend(
                    ("PROJECT_ROOT_COMMAND_LINE_ONLY", "PROCESS_IDENTITY_INCOMPLETE")
                )
                blocking = True
        elif (
            executable_name in {"python.exe", "pythonw.exe", "powershell.exe", "pwsh.exe"}
            and not process.command_line
        ):
            classification = "BLOCKING_AMBIGUOUS_PROCESS"
            reasons.append("APPLICATION_HOST_COMMAND_LINE_UNREADABLE")
            blocking = True

        if classification is None:
            continue
        diagnostics.append(
            QuiesceProcessIdentity(
                pid=process.pid,
                parent_pid=process.parent_pid,
                executable=process.executable,
                command_line=process.command_line,
                creation_time_utc=process.creation_time_utc,
                classification=classification,
                reason_codes=tuple(reasons),
                blocking=blocking,
            )
        )
    return tuple(sorted(diagnostics, key=lambda value: value.pid))


def _validate_probe_process_identities(
    *,
    payload: dict[str, object],
    processes: tuple[_WindowsProcessSnapshot, ...],
    nonce: str,
    current_pid: int,
    helper_pid: int,
    started_ns: int,
    completed_ns: int,
) -> None:
    if payload.get("probe_nonce") != nonce:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: probe nonce mismatch."
        )
    try:
        reported_helper_pid = int(payload["helper_pid"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper PID is missing."
        ) from exc
    if reported_helper_pid != helper_pid:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: spawned and reported helper PIDs differ."
        )

    by_pid = {value.pid: value for value in processes}
    current = by_pid.get(current_pid)
    helper = by_pid.get(helper_pid)
    if current is None or not _identity_is_complete(current):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: current Python process identity is incomplete."
        )
    if helper is None or not _identity_is_complete(helper):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper process identity is incomplete."
        )
    if helper.parent_pid != current_pid:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper parent PID does not match current PID."
        )
    if Path(helper.executable).name.casefold() not in {"powershell.exe", "pwsh.exe"}:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper executable is not PowerShell."
        )
    if nonce not in helper.command_line:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper command line does not contain its nonce."
        )
    try:
        helper_created_ns = parse_mtime_utc_ns(helper.creation_time_utc)
    except ValueError as exc:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper creation time is invalid."
        ) from exc
    tolerance_ns = 2_000_000_000
    if not (
        started_ns - tolerance_ns
        <= helper_created_ns
        <= completed_ns + tolerance_ns
    ):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: helper creation time does not match this probe."
        )


def _run_windows_process_inventory(
    project_root: Path,
) -> tuple[dict[str, object], tuple[_WindowsProcessSnapshot, ...], int]:
    escaped_root = str(project_root.resolve()).replace("'", "''")
    nonce = secrets.token_hex(16)
    script = (
        "$ErrorActionPreference='Stop';"
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        f"$root='{escaped_root}';$nonce='{nonce}';"
        "$processes=@(Get-CimInstance Win32_Process | ForEach-Object {"
        "$created=if ($null -eq $_.CreationDate) {$null} "
        "else {([datetime]$_.CreationDate).ToUniversalTime().ToString('o')};"
        "[pscustomobject]@{pid=[int]$_.ProcessId;parent_pid=[int]$_.ParentProcessId;"
        "executable=[string]$_.ExecutablePath;command_line=[string]$_.CommandLine;"
        "creation_time_utc=$created}"
        "});"
        "$tasks=@(Get-ScheduledTask | Where-Object {"
        "$text=(($_.Actions | ForEach-Object {\"$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)\"}) -join ' ');"
        "$text.Contains($root)"
        "} | ForEach-Object {\"$($_.TaskPath)$($_.TaskName)\"});"
        "[pscustomobject]@{probe_nonce=$nonce;helper_pid=[int]$PID;"
        "processes=$processes;scheduled_tasks=$tasks}"
        "|ConvertTo-Json -Depth 5 -Compress"
    )
    started_ns = time.time_ns()
    try:
        helper = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise Stage1MigrationPreflightError(
            f"Cannot prove full quiescence: cannot start PowerShell helper: {exc}"
        ) from exc

    try:
        try:
            stdout, stderr = helper.communicate(timeout=30)
        except subprocess.TimeoutExpired as exc:
            helper.terminate()
            try:
                helper.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                helper.kill()
                helper.communicate()
            raise Stage1MigrationPreflightError(
                "Cannot prove full quiescence: PowerShell helper timed out and was stopped."
            ) from exc
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.communicate()
    completed_ns = time.time_ns()
    if helper.returncode != 0:
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: PowerShell helper failed: "
            f"{stderr.strip() or f'exit code {helper.returncode}'}"
        )
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise Stage1MigrationPreflightError(
            f"Cannot prove full quiescence: invalid PowerShell JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise Stage1MigrationPreflightError(
            "Cannot prove full quiescence: PowerShell payload is not an object."
        )
    processes = _parse_process_inventory(payload)
    _validate_probe_process_identities(
        payload=payload,
        processes=processes,
        nonce=nonce,
        current_pid=os.getpid(),
        helper_pid=helper.pid,
        started_ns=started_ns,
        completed_ns=completed_ns,
    )
    return payload, processes, helper.pid


def _default_quiesce_probe(project_root: Path, source: Path) -> QuiesceReport:
    """Detect project processes/tasks and file handles without changing system state."""
    if os.name != "nt":
        raise Stage1MigrationPreflightError(
            "The packaged production quiesce probe is Windows-only and fails closed elsewhere."
        )
    current_pid = os.getpid()
    parent_pid = os.getppid()
    payload, processes, helper_pid = _run_windows_process_inventory(project_root)
    diagnostics = _classify_windows_processes(
        processes,
        project_root=project_root,
        current_pid=current_pid,
        parent_pid=parent_pid,
        helper_process_ids=frozenset({helper_pid}),
    )
    return QuiesceReport(
        project_process_ids=tuple(
            value.pid for value in diagnostics if value.blocking
        ),
        locked_paths=_windows_locked_paths(source),
        scheduled_tasks=_string_tuple_from_payload(
            payload.get("scheduled_tasks"),
            label="scheduled task inventory",
        ),
        probe_current_pid=current_pid,
        probe_parent_pid=parent_pid,
        probe_helper_process_ids=(helper_pid,),
        process_diagnostics=diagnostics,
    )


def _require_quiescence(
    project_root: Path,
    source: Path,
    probe: QuiesceProbe,
) -> QuiesceReport:
    snapshot = database_file_set_fingerprint(source)
    _assert_sidecar_contract(source, snapshot)
    report = probe(project_root, source)
    if not report.is_quiescent:
        blocking_processes = [
            _process_identity_as_dict(process)
            for process in report.process_diagnostics
            if process.blocking
        ]
        raise Stage1MigrationPreflightError(
            "Full quiescence was not proven: "
            f"processes={report.project_process_ids}, handles={report.locked_paths}, "
            f"tasks={report.scheduled_tasks}, "
            "process_details="
            f"{json.dumps(blocking_processes, ensure_ascii=False, sort_keys=True)}."
        )
    return report


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


def _initialize_blocked_flags(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    updated_by: str = "stage1-copy-preflight",
    reason: str = "Stage 1 controlled migration candidate; paid/browser remain disabled.",
) -> None:
    existing = int(conn.execute("SELECT COUNT(*) FROM system_flags").fetchone()[0])
    if existing != 0:
        raise Stage1MigrationPreflightError(
            "system_flags is not empty; explicit owner resolution is required before initialization."
        )
    conn.execute("BEGIN IMMEDIATE")
    try:
        for key, value in SECURITY_FLAG_DEFAULTS.items():
            conn.execute(
                "INSERT INTO system_flags(key,value_json,updated_at,updated_by,reason) "
                "VALUES (?,?,?,?,?)",
                (
                    key,
                    json.dumps(value),
                    timestamp,
                    updated_by,
                    reason,
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
    journal = Path(f"{source}-journal")
    if journal.exists():
        raise Stage1MigrationPreflightError(
            f"SQLite rollback journal exists ({journal.name}); source is not quiescent."
        )
    wal = Path(f"{source}-wal")
    if wal.exists() and wal.stat().st_size != 0:
        raise Stage1MigrationPreflightError(
            f"SQLite WAL is non-empty ({wal.stat().st_size} B); source is not safe to copy."
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
        if flag_rows != dict(SECURITY_FLAG_DEFAULTS):
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
        "system_flags": dict(SECURITY_FLAG_DEFAULTS),
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


def _copy_file_set(
    source: Path,
    destination_dir: Path,
    expected: DatabaseFileSetFingerprint,
) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=False)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    for suffix, value in (("-wal", expected.wal), ("-shm", expected.shm)):
        if value is not None:
            shutil.copy2(Path(f"{source}{suffix}"), Path(f"{destination}{suffix}"))
    copied = database_file_set_fingerprint(destination)
    if copied != expected:
        raise Stage1MigrationPreflightError(
            f"Copied database file set in {destination_dir} is not bitwise/metadata identical."
        )
    return destination


def _restore_file_set(
    source: Path,
    backup: Path,
    expected: DatabaseFileSetFingerprint,
) -> DatabaseFileSetFingerprint:
    """Restore DB/WAL/SHM as a unit; reverse SQL is intentionally unsupported."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = Path(f"{source}{suffix}")
        if candidate.exists():
            candidate.unlink()
    shutil.copy2(backup, source)
    for suffix, value in (("-wal", expected.wal), ("-shm", expected.shm)):
        if value is not None:
            shutil.copy2(Path(f"{backup}{suffix}"), Path(f"{source}{suffix}"))
    restored = database_file_set_fingerprint(source)
    if restored != expected or Path(f"{source}-journal").exists():
        raise Stage1MigrationPreflightError(
            "Full file restore did not reproduce the approved DB/WAL/SHM set exactly."
        )
    return restored


def _canonical_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest().upper(), "size": len(value)}
    return value


def _historical_snapshot(conn: sqlite3.Connection) -> dict[str, dict[str, object]]:
    """Digest every pre-existing application table using its pre-migration columns."""
    excluded = {"schema_migrations", "system_flags", "sqlite_sequence"}
    tables = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        if str(row[0]) not in excluded
    ]
    snapshot: dict[str, dict[str, object]] = {}
    for table in tables:
        quoted_table = '"' + table.replace('"', '""') + '"'
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({quoted_table})")]
        select_columns = ",".join('"' + value.replace('"', '""') + '"' for value in columns)
        canonical_rows = [
            json.dumps(
                [_canonical_value(value) for value in row],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in conn.execute(f"SELECT {select_columns} FROM {quoted_table}")
        ]
        canonical_rows.sort()
        payload = "\n".join(canonical_rows).encode("utf-8")
        snapshot[table] = {
            "columns": columns,
            "row_count": len(canonical_rows),
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
    return snapshot


def _historical_snapshot_using_columns(
    conn: sqlite3.Connection,
    expected: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    observed: dict[str, dict[str, object]] = {}
    for table, table_evidence in expected.items():
        columns = [str(value) for value in table_evidence["columns"]]
        quoted_table = '"' + table.replace('"', '""') + '"'
        select_columns = ",".join('"' + value.replace('"', '""') + '"' for value in columns)
        canonical_rows = [
            json.dumps(
                [_canonical_value(value) for value in row],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in conn.execute(f"SELECT {select_columns} FROM {quoted_table}")
        ]
        canonical_rows.sort()
        payload = "\n".join(canonical_rows).encode("utf-8")
        observed[table] = {
            "columns": columns,
            "row_count": len(canonical_rows),
            "sha256": hashlib.sha256(payload).hexdigest().upper(),
        }
    return observed


def _source_evidence(
    path: Path,
    request: Stage1MigrationRequest,
) -> tuple[dict[str, dict[str, object]], Decimal]:
    integrity, foreign_keys = _read_only_checks(path)
    if integrity != ["ok"] or foreign_keys:
        raise Stage1MigrationPreflightError(
            f"Schema-0009 rehearsal source failed integrity/FK checks: {integrity}, {foreign_keys}."
        )
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        if _migration_versions(conn) != SOURCE_MIGRATIONS:
            raise Stage1MigrationPreflightError("Rehearsal source is not exact schema 0001..0009.")
        existing_flags = int(conn.execute("SELECT COUNT(*) FROM system_flags").fetchone()[0])
        if existing_flags != 0:
            raise Stage1MigrationPreflightError(
                "Schema-0009 system_flags is not empty; owner resolution is required."
            )
        cost = _real_cost(conn)
        expected_cost = Decimal(request.expected_real_cost_usd).quantize(Decimal("0.000001"))
        if cost != expected_cost:
            raise Stage1MigrationPreflightError(
                f"Rehearsal source real cost is {cost:.6f}, expected {expected_cost:.6f}."
            )
        return _historical_snapshot(conn), cost
    finally:
        conn.close()


def _migrate_exact_0010_to_0014(
    path: Path,
    *,
    timestamp: str,
    updated_by: str,
    verify_runner_noop: bool,
) -> tuple[str, ...]:
    conn = connect(path)
    try:
        if _migration_versions(conn) != SOURCE_MIGRATIONS:
            raise Stage1MigrationPreflightError("Mutation target is not exact schema 0001..0009.")
        applied = tuple(apply_migrations(conn))
        if applied != MIGRATIONS_0010_TO_0014:
            raise Stage1MigrationPreflightError(
                f"Canonical runner applied {applied!r}, expected exact 0010..0014."
            )
        _initialize_blocked_flags(
            conn,
            timestamp=timestamp,
            updated_by=updated_by,
            reason=(
                "Stage 1 remains blocked pending controlled live acceptance; "
                "worker, paid, and browser actions remain disabled."
            ),
        )
        if verify_runner_noop:
            second_pass = tuple(apply_migrations(conn))
            if second_pass:
                raise Stage1MigrationPreflightError(
                    f"Canonical runner was not a no-op on its second pass: {second_pass!r}."
                )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return applied
    finally:
        conn.close()


def _verify_migrated_database(
    path: Path,
    request: Stage1MigrationRequest,
    expected_history: dict[str, dict[str, object]],
    expected_cost: Decimal,
) -> dict[str, object]:
    integrity, foreign_keys = _read_only_checks(path)
    if integrity != ["ok"] or foreign_keys:
        raise Stage1MigrationPreflightError(
            f"Migrated database failed integrity/FK checks: {integrity}, {foreign_keys}."
        )
    uri = f"{path.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON")
        versions = _migration_versions(conn)
        if versions != TARGET_MIGRATIONS:
            raise Stage1MigrationPreflightError("Migrated database is not exact schema 0001..0014.")
        observed_history = _historical_snapshot_using_columns(conn, expected_history)
        if observed_history != expected_history:
            raise Stage1MigrationPreflightError("Historical application rows changed during migration.")
        cost = _real_cost(conn)
        if cost != expected_cost:
            raise Stage1MigrationPreflightError(
                f"Migration changed real cost from {expected_cost:.6f} to {cost:.6f}."
            )
        flag_rows = {
            str(row[0]): json.loads(str(row[1]))
            for row in conn.execute("SELECT key,value_json FROM system_flags ORDER BY key")
        }
        if flag_rows != dict(SECURITY_FLAG_DEFAULTS):
            raise Stage1MigrationPreflightError(
                f"Migrated system_flags are not the canonical fail-closed profile: {flag_rows!r}."
            )
        triggers = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        missing_triggers = sorted(REQUIRED_STAGE1_TRIGGERS - triggers)
        if missing_triggers:
            raise Stage1MigrationPreflightError(
                "Migrated database is missing required triggers: " + ", ".join(missing_triggers)
            )
        legacy_proofs = int(
            conn.execute(
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
        provider_attempts = int(conn.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0])
        reconciliation_events = int(
            conn.execute("SELECT COUNT(*) FROM reconciliation_events").fetchone()[0]
        )
        if provider_attempts or reconciliation_events:
            raise Stage1MigrationPreflightError(
                "Migration unexpectedly created provider attempts or reconciliation events."
            )
        return {
            "migrations": list(versions),
            "system_flags": flag_rows,
            "trigger_count": len(triggers),
            "legacy_proof_count": legacy_proofs,
            "real_cost_usd": f"{cost:.6f}",
            "historical_tables": expected_history,
            "provider_attempt_count": provider_attempts,
            "reconciliation_event_count": reconciliation_events,
        }
    finally:
        conn.close()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_stage1_in_place_migration(
    request: Stage1MigrationRequest,
    *,
    confirm_in_place_production_migration: bool,
    git_identity_provider: GitIdentityProvider = _git_identity,
    quiesce_probe: QuiesceProbe = _default_quiesce_probe,
    now: datetime | None = None,
) -> Stage1InPlaceMigrationResult:
    """Run the sole packaged production 0009→0014 procedure, or restore fully."""
    if not confirm_in_place_production_migration:
        raise Stage1MigrationPreflightError(
            "Explicit --confirm-in-place-production-migration approval is required."
        )
    if len(EXPECTED_MIGRATIONS) != 14 or MIGRATIONS_0010_TO_0014 != TARGET_MIGRATIONS[9:14]:
        raise Stage1MigrationPreflightError("The canonical migration ledger is not exact 0001..0014.")
    project_root = request.project_root.resolve()
    source = request.source_db.resolve()
    workspace = request.workspace.resolve()
    if not source.is_file():
        raise Stage1MigrationPreflightError(f"Source database does not exist: {source}")
    if (
        workspace == source.parent
        or source in workspace.parents
        or source.parent in workspace.parents
        or workspace == project_root
        or project_root in workspace.parents
    ):
        raise Stage1MigrationPreflightError(
            "Migration workspace must be outside the source directory and project repository."
        )
    if workspace.exists() and any(workspace.iterdir()):
        raise Stage1MigrationPreflightError("Migration workspace must be absent or empty.")

    try:
        branch, head = git_identity_provider(project_root)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stage1MigrationPreflightError(f"Cannot verify Git branch/HEAD: {exc}") from exc
    if branch != request.expected_branch or head != request.expected_head:
        raise Stage1MigrationPreflightError(
            f"Git identity mismatch: branch={branch!r}, HEAD={head!r}."
        )

    source_before = database_file_set_fingerprint(source)
    _assert_approved_baseline(request, source_before)
    _assert_sidecar_contract(source, source_before)
    quiesce_initial = _require_quiescence(project_root, source, quiesce_probe)

    workspace.mkdir(parents=True, exist_ok=True)
    backup_dir = workspace / "verified-full-backup-schema-0009"
    rehearsal_dir = workspace / "rehearsal-schema-0014"
    report_path = workspace / "stage1-in-place-migration-report.json"
    baseline_path = workspace / "stage1-new-baseline.json"
    backup = _copy_file_set(source, backup_dir, source_before)
    source_after_backup = database_file_set_fingerprint(source)
    _assert_sidecar_contract(source, source_after_backup)
    if source_after_backup != source_before:
        raise Stage1MigrationPreflightError("DB/WAL/SHM drifted while the full backup was created.")
    quiesce_after_backup = _require_quiescence(project_root, source, quiesce_probe)

    rehearsal = _copy_file_set(backup, rehearsal_dir, source_before)
    expected_history, expected_cost = _source_evidence(rehearsal, request)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    rehearsal_applied = _migrate_exact_0010_to_0014(
        rehearsal,
        timestamp=timestamp,
        updated_by="stage1-production-migration-rehearsal",
        verify_runner_noop=True,
    )
    rehearsal_evidence = _verify_migrated_database(
        rehearsal, request, expected_history, expected_cost
    )
    if database_file_set_fingerprint(backup) != source_before:
        raise Stage1MigrationPreflightError("Verified full backup changed during rehearsal.")

    try:
        final_branch, final_head = git_identity_provider(project_root)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Stage1MigrationPreflightError(
            f"Cannot re-verify Git branch/HEAD immediately before mutation: {exc}"
        ) from exc
    if (final_branch, final_head) != (request.expected_branch, request.expected_head):
        raise Stage1MigrationPreflightError("Git branch/HEAD drifted before production mutation.")
    quiesce_pre_mutation = _require_quiescence(project_root, source, quiesce_probe)
    source_pre_mutation = database_file_set_fingerprint(source)
    _assert_sidecar_contract(source, source_pre_mutation)
    if source_pre_mutation != source_before:
        raise Stage1MigrationPreflightError(
            "DB/WAL/SHM drifted between approved fingerprint and production mutation."
        )

    production_opened = False
    try:
        production_opened = True
        applied = _migrate_exact_0010_to_0014(
            source,
            timestamp=timestamp,
            updated_by="stage1-controlled-production-migration",
            verify_runner_noop=False,
        )
        production_evidence = _verify_migrated_database(
            source, request, expected_history, expected_cost
        )
        source_after = database_file_set_fingerprint(source)
        _assert_sidecar_contract(source, source_after)
        if source_after.database.sha256 == source_before.database.sha256:
            raise Stage1MigrationPreflightError(
                "Production migration did not establish a distinct schema-0014 main DB baseline."
            )
        baseline = {
            "status": "NEW_SCHEMA_0014_BASELINE_ESTABLISHED",
            "database_file_set": _file_set_as_dict(source_after),
            "database_sha256_is_required_baseline": True,
            "wal_and_shm_are_metadata_only": True,
            "git": {"branch": final_branch, "head": final_head},
        }
        _write_json(baseline_path, baseline)
        report = {
            "status": "PRODUCTION_MIGRATION_PASSED",
            "git": {"branch": final_branch, "head": final_head},
            "source_before": _file_set_as_dict(source_before),
            "source_after_backup": _file_set_as_dict(source_after_backup),
            "source_pre_mutation": _file_set_as_dict(source_pre_mutation),
            "source_after": _file_set_as_dict(source_after),
            "quiesce": {
                "initial": _quiesce_report_as_dict(quiesce_initial),
                "after_backup": _quiesce_report_as_dict(quiesce_after_backup),
                "pre_mutation": _quiesce_report_as_dict(quiesce_pre_mutation),
            },
            "backup_dir": str(backup_dir),
            "backup_verified_unchanged": True,
            "rehearsal": rehearsal_evidence,
            "production": production_evidence,
            "migrations_applied": list(applied),
            "system_flags": dict(SECURITY_FLAG_DEFAULTS),
            "rollback_method": "full DB/WAL/SHM file-set restore only; no reverse SQL",
            "live_api_used": False,
            "worker_started": False,
            "windows_tasks_changed": False,
            "paid_actions": False,
            "browser_actions": False,
        }
        _write_json(report_path, report)
        return Stage1InPlaceMigrationResult(
            report_path=report_path,
            backup_dir=backup_dir,
            rehearsal_path=rehearsal,
            baseline_path=baseline_path,
            source_before=source_before,
            source_after=source_after,
            applied_migrations=applied,
            trigger_count=int(production_evidence["trigger_count"]),
            legacy_proof_count=int(production_evidence["legacy_proof_count"]),
            real_cost_usd=str(production_evidence["real_cost_usd"]),
        )
    except BaseException as migration_error:
        if not production_opened:
            raise
        try:
            restored = _restore_file_set(source, backup, source_before)
            baseline_path.unlink(missing_ok=True)
            failure_report: dict[str, object] = {
                "status": "PRODUCTION_MIGRATION_FAILED_FULL_RESTORE_VERIFIED",
                "error_type": type(migration_error).__name__,
                "error": str(migration_error),
                "source_before": _file_set_as_dict(source_before),
                "source_restored": _file_set_as_dict(restored),
                "restore_bitwise_and_metadata_identical": True,
                "rollback_method": "full DB/WAL/SHM file-set restore only; no reverse SQL",
                "live_api_used": False,
                "paid_actions": False,
                "browser_actions": False,
            }
            _write_json(report_path, failure_report)
        except BaseException as restore_error:
            raise Stage1MigrationPreflightError(
                "Production migration failed and the mandatory full file-set restore also failed: "
                f"migration={migration_error!r}; restore={restore_error!r}."
            ) from restore_error
        raise Stage1MigrationPreflightError(
            "Production migration failed; full DB/WAL/SHM restore was independently verified: "
            f"{migration_error}"
        ) from migration_error
