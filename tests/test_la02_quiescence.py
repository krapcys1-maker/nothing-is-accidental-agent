"""LA-02 ancestry, diagnostics and standalone quiescence countertests."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

import app.operations.controlled_live as controlled
import app.operations.stage1_migration as migration


CREATED_EARLY = "2026-07-17T10:00:00.0000000Z"
CREATED_LATE = "2026-07-17T10:00:01.0000000Z"
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows-only canonical probe")


def _snapshot(
    pid: int,
    parent_pid: int,
    *,
    executable: str = r"C:\Python\python.exe",
    command_line: str = "python.exe harmless.py",
    creation_time_utc: str = CREATED_EARLY,
):
    return migration._WindowsProcessSnapshot(
        pid=pid,
        parent_pid=parent_pid,
        executable=executable,
        command_line=command_line,
        creation_time_utc=creation_time_utc,
    )


def _classify(processes, root: Path, *, current: int = 100, parent: int = 90):
    return {
        item.pid: item
        for item in migration._classify_windows_processes(
            tuple(processes),
            project_root=root,
            current_pid=current,
            parent_pid=parent,
            helper_process_ids=frozenset({101}),
        )
    }


def _controlled_command(prefix: str = "python.exe") -> str:
    return f"{prefix} -m app.main controlled-live-once --topic-id 3"


@pytest.mark.parametrize(
    ("executable", "prefix"),
    (
        (r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "powershell.exe -Command python"),
        (r"C:\Program Files\PowerShell\7\pwsh.exe", "pwsh.exe -Command python"),
        (r"C:\Windows\System32\cmd.exe", "cmd.exe /c python"),
        (r"C:\Program Files\Git\bin\bash.exe", "bash.exe -lc python"),
    ),
    ids=("powershell", "pwsh", "cmd", "bash"),
)
def test_immediate_verified_shell_parent_is_nonblocking(
    tmp_path: Path,
    executable: str,
    prefix: str,
):
    root = tmp_path / "project"
    root.mkdir()
    diagnostics = _classify(
        (
            _snapshot(
                100,
                90,
                command_line=_controlled_command(),
                creation_time_utc=CREATED_LATE,
            ),
            _snapshot(
                90,
                80,
                executable=executable,
                command_line=_controlled_command(prefix),
            ),
            _snapshot(101, 100, command_line="powershell.exe registered helper"),
        ),
        root,
    )

    assert diagnostics[90].classification == "PROBE_ANCESTRY_LAUNCHER"
    assert diagnostics[90].belongs_to_probe_ancestry is True
    assert diagnostics[90].blocking is False
    assert diagnostics[100].classification == "PROBE_CURRENT"
    assert diagnostics[101].classification == "PROBE_HELPER"


@pytest.mark.parametrize(
    "grandparent_executable",
    (r"C:\Windows\System32\cmd.exe", r"C:\Program Files\Git\bin\bash.exe"),
    ids=("cmd-grandparent", "bash-grandparent"),
)
def test_multilevel_verified_ancestry_is_nonblocking(
    tmp_path: Path,
    grandparent_executable: str,
):
    root = tmp_path / "project"
    root.mkdir()
    processes = (
        _snapshot(
            100,
            90,
            command_line=_controlled_command(),
            creation_time_utc="2026-07-17T10:00:03.0000000Z",
        ),
        _snapshot(
            90,
            80,
            executable=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            command_line=_controlled_command("powershell.exe -Command python"),
            creation_time_utc="2026-07-17T10:00:02.0000000Z",
        ),
        _snapshot(
            80,
            70,
            executable=grandparent_executable,
            command_line=_controlled_command("launcher grandparent python"),
            creation_time_utc="2026-07-17T10:00:01.0000000Z",
        ),
        _snapshot(
            70,
            1,
            executable=r"C:\Tools\local-shell.exe",
            command_line=_controlled_command("local-shell python"),
        ),
    )

    ancestry = migration._verified_launcher_ancestry(
        processes,
        current_pid=100,
        parent_pid=90,
    )
    diagnostics = _classify(processes, root)

    assert ancestry == frozenset({70, 80, 90, 100})
    assert all(not diagnostics[pid].blocking for pid in ancestry)
    assert all(diagnostics[pid].belongs_to_probe_ancestry for pid in ancestry)


@pytest.mark.parametrize(
    ("command_line", "expected_reason"),
    (
        (_controlled_command(), "APP_ROLE_OPERATOR_CLI"),
        ("python.exe -m app.main worker --once", "APP_ROLE_WORKER"),
        ("python.exe -m app.main maintain --once", "APP_ROLE_MAINTENANCE"),
        ("python.exe -m app.main controlled-live-once --topic-id 4", "APP_ROLE_OPERATOR_CLI"),
        ("python.exe -m app.main enqueue-research --topic-id 3", "APP_ROLE_OPERATOR_CLI"),
    ),
    ids=(
        "identical-independent-operator",
        "independent-worker",
        "independent-maintenance",
        "second-controlled-live",
        "independent-scheduler-cli",
    ),
)
def test_independent_application_role_blocks(
    tmp_path: Path,
    command_line: str,
    expected_reason: str,
):
    root = tmp_path / "project"
    root.mkdir()
    diagnostics = _classify(
        (
            _snapshot(
                100,
                90,
                command_line=_controlled_command(),
                creation_time_utc=CREATED_LATE,
            ),
            _snapshot(90, 1, command_line=_controlled_command("cmd /c python")),
            _snapshot(200, 1, command_line=command_line),
        ),
        root,
    )

    assert diagnostics[200].blocking is True
    assert expected_reason in diagnostics[200].reason_codes
    assert diagnostics[200].belongs_to_probe_ancestry is False


def test_worker_descendant_of_verified_launcher_still_blocks(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    diagnostics = _classify(
        (
            _snapshot(
                100,
                90,
                command_line=_controlled_command(),
                creation_time_utc=CREATED_LATE,
            ),
            _snapshot(90, 1, command_line=_controlled_command("cmd /c python")),
            _snapshot(200, 90, command_line="python.exe -m app.main worker --once"),
        ),
        root,
    )

    assert diagnostics[90].blocking is False
    assert diagnostics[200].blocking is True
    assert "APP_ROLE_WORKER" in diagnostics[200].reason_codes


def test_launcher_that_also_names_worker_is_not_exempt(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    mixed = (
        _controlled_command("cmd /c python")
        + " && python.exe -m app.main worker --once"
    )
    diagnostics = _classify(
        (
            _snapshot(
                100,
                90,
                command_line=_controlled_command(),
                creation_time_utc=CREATED_LATE,
            ),
            _snapshot(90, 1, command_line=mixed),
        ),
        root,
    )

    assert diagnostics[90].blocking is True
    assert "APP_ROLE_WORKER" in diagnostics[90].reason_codes
    assert diagnostics[90].belongs_to_probe_ancestry is False


def test_parent_creation_after_child_fails_closed_as_pid_reuse():
    processes = (
        _snapshot(100, 90, command_line=_controlled_command()),
        _snapshot(
            90,
            1,
            command_line=_controlled_command("cmd /c python"),
            creation_time_utc=CREATED_LATE,
        ),
    )

    with pytest.raises(migration.Stage1MigrationPreflightError, match="creation time"):
        migration._verified_launcher_ancestry(
            processes,
            current_pid=100,
            parent_pid=90,
        )


def test_invalid_creation_time_fails_closed():
    processes = (
        _snapshot(
            100,
            90,
            command_line=_controlled_command(),
            creation_time_utc="changed-or-unreadable",
        ),
        _snapshot(90, 1, command_line=_controlled_command("cmd /c python")),
    )

    with pytest.raises(migration.Stage1MigrationPreflightError, match="creation time"):
        migration._verified_launcher_ancestry(
            processes,
            current_pid=100,
            parent_pid=90,
        )


def test_incomplete_launcher_identity_fails_closed():
    processes = (
        _snapshot(
            100,
            90,
            command_line=_controlled_command(),
            creation_time_utc=CREATED_LATE,
        ),
        _snapshot(
            90,
            1,
            executable="",
            command_line=_controlled_command("cmd /c python"),
        ),
    )

    with pytest.raises(migration.Stage1MigrationPreflightError, match="identity is incomplete"):
        migration._verified_launcher_ancestry(
            processes,
            current_pid=100,
            parent_pid=90,
        )


def test_pid_ppid_mismatch_fails_closed():
    processes = (
        _snapshot(100, 91, command_line=_controlled_command()),
        _snapshot(90, 1, command_line=_controlled_command("cmd /c python")),
    )

    with pytest.raises(migration.Stage1MigrationPreflightError, match="PID/PPID"):
        migration._verified_launcher_ancestry(
            processes,
            current_pid=100,
            parent_pid=90,
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_standalone_core_is_read_only_and_returns_full_pass_diagnostics(tmp_path: Path):
    db_path = tmp_path / "agent.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE system_flags(key TEXT PRIMARY KEY, value_json TEXT)")
        conn.execute("INSERT INTO system_flags VALUES ('kill_switch','true')")
        conn.commit()
    finally:
        conn.close()
    before_sha = _sha256(db_path)

    def clean_probe(_root: Path, _db: Path):
        return {
            "project_process_ids": (),
            "scheduled_tasks": (),
            "locked_paths": (),
            "probe_current_pid": 100,
            "probe_parent_pid": 90,
            "probe_ancestry_process_ids": (90, 100),
            "probe_helper_process_ids": (101,),
            "process_diagnostics": (
                {
                    "pid": 90,
                    "parent_pid": 1,
                    "executable": "cmd.exe",
                    "command_line": _controlled_command("cmd /c python"),
                    "creation_time_utc": CREATED_EARLY,
                    "classification": "PROBE_ANCESTRY_LAUNCHER",
                    "reason_codes": ("VERIFIED_PROBE_ANCESTRY",),
                    "blocking": False,
                    "belongs_to_probe_ancestry": True,
                },
            ),
        }

    exit_code, payload = controlled.run_controlled_live_quiescence_check(
        project_root=tmp_path,
        db_path=db_path,
        quiescence_probe=clean_probe,
    )

    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["database_unchanged"] is True
    assert payload["process_diagnostics"][0]["belongs_to_probe_ancestry"] is True
    assert payload["provider_constructed"] is False
    assert payload["provider_request_started"] is False
    assert payload["storage_opened"] is False
    assert payload["session_marker_created"] is False
    assert _sha256(db_path) == before_sha
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT * FROM system_flags").fetchall() == [
            ("kill_switch", "true")
        ]
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name IN "
            "('provider_attempts','model_usage')"
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert not (tmp_path / "controlled_live_session.json").exists()


def test_standalone_core_returns_stop_for_blocking_process(tmp_path: Path):
    db_path = tmp_path / "agent.db"
    db_path.write_bytes(b"temporary-db")

    def blocking_probe(_root: Path, _db: Path):
        return {
            "project_process_ids": (321,),
            "scheduled_tasks": (),
            "locked_paths": (),
            "process_diagnostics": (
                {
                    "pid": 321,
                    "parent_pid": 123,
                    "executable": "python.exe",
                    "command_line": "python.exe -m app.main worker --once",
                    "creation_time_utc": CREATED_EARLY,
                    "classification": "BLOCKING_APPLICATION_PROCESS",
                    "reason_codes": ("APP_ROLE_WORKER",),
                    "blocking": True,
                    "belongs_to_probe_ancestry": False,
                },
            ),
        }

    exit_code, payload = controlled.run_controlled_live_quiescence_check(
        project_root=tmp_path,
        db_path=db_path,
        quiescence_probe=blocking_probe,
    )

    assert exit_code == 2
    assert payload["status"] == "STOP"
    assert payload["reason_code"] == "PROCESSES_PRESENT"
    assert payload["project_process_ids"] == [321]


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


def _run_standalone_cli(db_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "app.main",
            "controlled-live-quiescence-check",
            "--db-path",
            str(db_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=45,
        check=False,
    )


@WINDOWS_ONLY
def test_full_standalone_entrypoint_passes_and_preserves_db(tmp_path: Path):
    db_path = tmp_path / "agent.db"
    db_path.write_bytes(b"standalone-read-only")
    before_sha = _sha256(db_path)

    result = _run_standalone_cli(db_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.splitlines()[0])
    assert payload["status"] == "PASS"
    assert payload["database_unchanged"] is True
    assert "CONTROLLED-LIVE-QUIESCENCE: PASS" in result.stdout
    assert _sha256(db_path) == before_sha


@WINDOWS_ONLY
def test_full_standalone_entrypoint_detects_real_worker_process(tmp_path: Path):
    db_path = tmp_path / "agent.db"
    db_path.write_bytes(b"standalone-blocking")
    sleeper = [
        sys.executable,
        "-c",
        "import time;print('READY',flush=True);time.sleep(60)",
        "-m",
        "app.main",
        "worker",
        "--once",
    ]
    with _ready_process(sleeper) as worker:
        result = _run_standalone_cli(db_path)

    assert result.returncode == 2, result.stderr
    payload = json.loads(result.stdout.splitlines()[0])
    assert payload["status"] == "STOP"
    assert payload["reason_code"] == "PROCESSES_PRESENT"
    assert worker.pid in payload["project_process_ids"]
    assert "CONTROLLED-LIVE-QUIESCENCE: STOP" in result.stdout
