"""Windows process-classification countertests for the Stage 1 quiesce probe."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

import app.operations.stage1_migration as migration
from app.operations.stage1_migration import Stage1MigrationPreflightError


WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows-only quiesce probe")
CREATED = "2026-07-16T18:59:17.5919140Z"


def _snapshot(
    pid: int,
    parent_pid: int,
    *,
    executable: str = r"C:\Python\python.exe",
    command_line: str = "python.exe harmless.py",
    creation_time_utc: str = CREATED,
):
    return migration._WindowsProcessSnapshot(
        pid=pid,
        parent_pid=parent_pid,
        executable=executable,
        command_line=command_line,
        creation_time_utc=creation_time_utc,
    )


def _diagnostics_by_pid(processes, root, *, current=100, parent=90, helpers=(101,)):
    return {
        value.pid: value
        for value in migration._classify_windows_processes(
            tuple(processes),
            project_root=root,
            current_pid=current,
            parent_pid=parent,
            helper_process_ids=frozenset(helpers),
        )
    }


def _temp_probe_paths(tmp_path: Path) -> tuple[Path, Path]:
    project_root = tmp_path / "probe-project"
    source = tmp_path / "probe-db" / "agent.db"
    project_root.mkdir()
    source.parent.mkdir()
    source.write_bytes(b"")
    return project_root, source


@contextmanager
def _ready_process(command: list[str]):
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "READY"
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def _sleeping_python(*arguments: str) -> list[str]:
    return [
        sys.executable,
        "-c",
        "import time; print('READY', flush=True); time.sleep(60)",
        *arguments,
    ]


def _windows_pid_is_running(pid: int) -> bool:
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == 259
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def test_classifier_tracks_current_parent_helper_and_root_only_process(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    root_text = str(root.resolve())
    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(
                100,
                90,
                command_line=(
                    "python "
                    f"{root_text}\\scripts\\prepare_stage1_db_migration.py plan"
                ),
            ),
            _snapshot(
                90,
                80,
                executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                command_line=(
                    "powershell.exe -Command python "
                    f"{root_text}\\scripts\\prepare_stage1_db_migration.py plan"
                ),
            ),
            _snapshot(
                101,
                100,
                executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                command_line=f"powershell.exe probe-helper {root_text}",
            ),
            _snapshot(
                102,
                80,
                executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                command_line=f"powershell.exe independent {root_text}",
            ),
        ),
        root,
    )

    assert diagnostics[100].reason_codes == ("PROBE_CURRENT_PID",)
    assert diagnostics[90].reason_codes == (
        "VERIFIED_PROBE_ANCESTRY",
        "PID_PPID_RELATION_VERIFIED",
        "CREATION_ORDER_VERIFIED",
        "ENTRYPOINT_SIGNATURE_MATCH",
    )
    assert diagnostics[90].belongs_to_probe_ancestry is True
    assert diagnostics[101].reason_codes == ("PROBE_REGISTERED_HELPER_IDENTITY",)
    assert diagnostics[102].reason_codes == ("PROJECT_ROOT_COMMAND_LINE_ONLY",)
    assert not any(value.blocking for value in diagnostics.values())


def test_registered_helper_does_not_hide_unregistered_worker_descendant(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(100, 90),
            _snapshot(101, 100, command_line="powershell.exe registered-helper"),
            _snapshot(102, 101, command_line="python.exe -m app.main worker --once"),
        ),
        root,
    )

    assert diagnostics[101].classification == "PROBE_HELPER"
    assert diagnostics[102].blocking is True
    assert "APP_ROLE_WORKER" in diagnostics[102].reason_codes


def test_parent_is_not_exempt_when_it_is_a_real_application_role(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(100, 90),
            _snapshot(90, 80, command_line="python.exe -m app.main maintain --once"),
            _snapshot(101, 100, command_line="powershell.exe registered-helper"),
        ),
        root,
    )

    assert diagnostics[90].blocking is True
    assert diagnostics[90].reason_codes == ("APP_ROLE_MAINTENANCE",)


def test_unreadable_application_host_fails_closed(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    live_pid = os.getpid()
    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(100, 90),
            _snapshot(101, 100, command_line="powershell.exe registered-helper"),
            _snapshot(live_pid, 1, command_line="", creation_time_utc=""),
        ),
        root,
    )

    assert diagnostics[live_pid].blocking is True
    assert diagnostics[live_pid].reason_codes == ("APPLICATION_HOST_COMMAND_LINE_UNREADABLE",)


@WINDOWS_ONLY
def test_unreadable_application_host_downgrades_when_confirmed_exited(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    exited = subprocess.Popen([sys.executable, "-c", "pass"])
    exited_pid = exited.pid
    exited.wait(timeout=10)
    del exited
    assert not _windows_pid_is_running(exited_pid)

    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(100, 90),
            _snapshot(101, 100, command_line="powershell.exe registered-helper"),
            _snapshot(exited_pid, 1, command_line="", creation_time_utc=""),
        ),
        root,
    )

    assert diagnostics[exited_pid].blocking is False
    assert diagnostics[exited_pid].classification == (
        "OBSERVED_HOST_PROCESS_EXITED_DURING_INVENTORY"
    )
    assert diagnostics[exited_pid].reason_codes == (
        "APPLICATION_HOST_COMMAND_LINE_UNREADABLE",
        "PROCESS_CONFIRMED_EXITED_AFTER_SNAPSHOT",
    )


@WINDOWS_ONLY
def test_unreadable_application_host_stays_blocking_while_genuinely_alive(
    tmp_path: Path,
):
    root = tmp_path / "project"
    root.mkdir()
    with _ready_process(_sleeping_python()) as alive:
        diagnostics = _diagnostics_by_pid(
            (
                _snapshot(100, 90),
                _snapshot(101, 100, command_line="powershell.exe registered-helper"),
                _snapshot(alive.pid, 1, command_line="", creation_time_utc=""),
            ),
            root,
        )

    assert diagnostics[alive.pid].blocking is True
    assert diagnostics[alive.pid].classification == "BLOCKING_AMBIGUOUS_PROCESS"
    assert diagnostics[alive.pid].reason_codes == (
        "APPLICATION_HOST_COMMAND_LINE_UNREADABLE",
    )


def test_unreadable_application_host_ignores_pid_that_never_existed(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    never_allocated_pid = 999_999_999
    diagnostics = _diagnostics_by_pid(
        (
            _snapshot(100, 90),
            _snapshot(101, 100, command_line="powershell.exe registered-helper"),
            _snapshot(never_allocated_pid, 1, command_line="", creation_time_utc=""),
        ),
        root,
    )

    detail = diagnostics[never_allocated_pid]
    if os.name == "nt":
        assert detail.blocking is False
        assert detail.classification == "OBSERVED_HOST_PROCESS_EXITED_DURING_INVENTORY"
    else:
        assert detail.blocking is True
        assert detail.classification == "BLOCKING_AMBIGUOUS_PROCESS"


def test_helper_creation_time_prevents_pid_reuse_acceptance():
    nonce = "fixed-probe-nonce"
    current_pid = 100
    helper_pid = 101
    now_ns = time.time_ns()
    processes = (
        _snapshot(current_pid, 90, command_line="python.exe executor.py"),
        _snapshot(
            helper_pid,
            current_pid,
            executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            command_line=f"powershell.exe helper {nonce}",
            creation_time_utc="2020-01-01T00:00:00.0000000Z",
        ),
    )

    with pytest.raises(Stage1MigrationPreflightError, match="creation time"):
        migration._validate_probe_process_identities(
            payload={"probe_nonce": nonce, "helper_pid": helper_pid},
            processes=processes,
            nonce=nonce,
            current_pid=current_pid,
            helper_pid=helper_pid,
            started_ns=now_ns,
            completed_ns=now_ns,
        )


@WINDOWS_ONLY
def test_real_probe_does_not_self_detect_child_powershell(tmp_path: Path):
    project_root, source = _temp_probe_paths(tmp_path)

    report = migration._default_quiesce_probe(project_root, source)

    assert report.is_quiescent
    assert report.probe_current_pid == os.getpid()
    assert report.probe_parent_pid == os.getppid()
    assert len(report.probe_helper_process_ids) == 1
    helper_pid = report.probe_helper_process_ids[0]
    helper = next(
        value for value in report.process_diagnostics if value.pid == helper_pid
    )
    assert helper.parent_pid == os.getpid()
    assert helper.classification == "PROBE_HELPER"
    assert helper.blocking is False
    assert str(project_root.resolve()) in helper.command_line
    assert helper.executable.lower().endswith("powershell.exe")
    assert helper.creation_time_utc
    assert not _windows_pid_is_running(helper_pid)


@WINDOWS_ONLY
def test_independent_root_only_powershell_is_reported_but_not_blocking(tmp_path: Path):
    project_root, source = _temp_probe_paths(tmp_path)
    escaped_root = str(project_root.resolve()).replace("'", "''")
    command = (
        "$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
        f"$root='{escaped_root}';Write-Output 'READY';Start-Sleep -Seconds 60"
    )
    with _ready_process(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
    ) as independent:
        report = migration._default_quiesce_probe(project_root, source)
        detail = next(
            value for value in report.process_diagnostics if value.pid == independent.pid
        )

    assert independent.pid not in report.project_process_ids
    assert detail.classification == "OBSERVED_NONBLOCKING"
    assert detail.reason_codes == ("PROJECT_ROOT_COMMAND_LINE_ONLY",)
    assert detail.command_line
    assert detail.creation_time_utc


@pytest.mark.parametrize(
    ("arguments", "reason"),
    (
        (("-m", "app.main", "worker", "--once"), "APP_ROLE_WORKER"),
        (("-m", "app.main", "maintain", "--once"), "APP_ROLE_MAINTENANCE"),
        (("-m", "app.main", "operational-report"), "APP_ROLE_OPERATOR_CLI"),
    ),
)
@WINDOWS_ONLY
def test_real_application_roles_still_block(
    tmp_path: Path,
    arguments: tuple[str, ...],
    reason: str,
):
    project_root, source = _temp_probe_paths(tmp_path)
    with _ready_process(_sleeping_python(*arguments)) as application:
        report = migration._default_quiesce_probe(project_root, source)
        detail = next(
            value for value in report.process_diagnostics if value.pid == application.pid
        )

    assert application.pid in report.project_process_ids
    assert detail.blocking is True
    assert reason in detail.reason_codes
    assert detail.parent_pid
    assert detail.executable
    assert detail.command_line
    assert detail.creation_time_utc
    assert not _windows_pid_is_running(application.pid)
    assert detail.pid == application.pid


@WINDOWS_ONLY
def test_process_without_project_root_but_with_temp_db_handle_blocks(tmp_path: Path):
    project_root, source = _temp_probe_paths(tmp_path)
    holder_code = (
        "import sqlite3,sys,time;"
        "connection=sqlite3.connect(sys.argv[1]);"
        "connection.execute('CREATE TABLE IF NOT EXISTS held(id INTEGER)');"
        "connection.commit();"
        "print('READY',flush=True);"
        "time.sleep(60)"
    )
    with _ready_process([sys.executable, "-c", holder_code, str(source)]) as holder:
        assert str(project_root.resolve()) not in " ".join(holder.args)
        report = migration._default_quiesce_probe(project_root, source)

    assert str(source) in report.locked_paths
    assert report.is_quiescent is False


@WINDOWS_ONLY
def test_two_parallel_probes_do_not_block_each_other(tmp_path: Path):
    project_root, source = _temp_probe_paths(tmp_path)
    barrier = threading.Barrier(2)

    def run_probe():
        barrier.wait(timeout=5)
        return migration._default_quiesce_probe(project_root, source)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = tuple(pool.map(lambda _: run_probe(), range(2)))

    assert all(report.is_quiescent for report in reports)
    assert all(not report.project_process_ids for report in reports)
    assert len({report.probe_helper_process_ids[0] for report in reports}) == 2


def test_quiesce_failure_includes_full_blocking_process_identity(tmp_path: Path):
    root = tmp_path / "project"
    source = tmp_path / "agent.db"
    root.mkdir()
    source.write_bytes(b"temporary")
    process = migration.QuiesceProcessIdentity(
        pid=321,
        parent_pid=123,
        executable=r"C:\Python\python.exe",
        command_line="python.exe -m app.main worker --once",
        creation_time_utc=CREATED,
        classification="BLOCKING_APPLICATION_PROCESS",
        reason_codes=("APP_ROLE_WORKER",),
        blocking=True,
    )

    with pytest.raises(Stage1MigrationPreflightError) as captured:
        migration._require_quiescence(
            root,
            source,
            lambda _root, _source: migration.QuiesceReport(
                project_process_ids=(321,),
                process_diagnostics=(process,),
            ),
        )

    message = str(captured.value)
    assert '"pid": 321' in message
    assert '"parent_pid": 123' in message
    assert "python.exe -m app.main worker --once" in message
    assert CREATED in message
    assert "APP_ROLE_WORKER" in message
