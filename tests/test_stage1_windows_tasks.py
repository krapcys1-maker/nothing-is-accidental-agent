"""Offline contract tests for the minimal Windows Task Scheduler boundary."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from app.models import Job, JobKind, WorkflowType
from app.policies.policy_engine import PolicyDecision
from app.scheduler.dispatcher import JobDispatcher, PolicyDeniedError
from app.scheduler.windows_tasks import (
    TASK_NAMESPACE,
    SystemTaskKind,
    build_windows_task_specs,
    registration_command,
    render_windows_task_xml,
)
from scripts import manage_windows_tasks


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(Path(sys.executable).anchor) / Path(
    "Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
)


def _specs():
    return build_windows_task_specs(
        project_root=PROJECT_ROOT,
        python_executable=sys.executable,
        powershell_executable=POWERSHELL,
        user_id="LOCAL\\stage1-review",
        start_boundary=datetime(2026, 7, 16, 12, 1, 0),
    )


def _text(root: ET.Element, path: str) -> str:
    value = root.findtext(path, namespaces={"t": TASK_NAMESPACE})
    assert value is not None
    return value


@pytest.mark.parametrize(
    ("kind", "interval", "launcher_name"),
    [
        (SystemTaskKind.WORKER, "PT1M", "run_worker_task.ps1"),
        (SystemTaskKind.MAINTENANCE, "PT5M", "run_maintenance_task.ps1"),
    ],
)
def test_task_xml_is_exact_non_overlapping_and_has_no_retry(
    kind: SystemTaskKind, interval: str, launcher_name: str,
):
    spec = _specs()[kind]
    root = ET.fromstring(render_windows_task_xml(spec))
    assert _text(root, ".//t:Repetition/t:Interval") == interval
    assert _text(root, ".//t:MultipleInstancesPolicy") == "IgnoreNew"
    assert _text(root, ".//t:ExecutionTimeLimit") == "PT0S"
    assert _text(root, ".//t:AllowHardTerminate") == "false"
    assert _text(root, ".//t:RunOnlyIfNetworkAvailable") == "false"
    assert _text(root, ".//t:RunLevel") == "LeastPrivilege"
    assert _text(root, ".//t:WorkingDirectory") == str(PROJECT_ROOT)
    assert _text(root, ".//t:Command") == str(POWERSHELL.resolve())
    assert launcher_name in _text(root, ".//t:Arguments")
    assert root.find(".//t:RestartOnFailure", {"t": TASK_NAMESPACE}) is None


def test_launchers_pin_exact_python_root_and_canonical_offline_commands():
    worker = (PROJECT_ROOT / "scripts" / "run_worker_task.ps1").read_text(encoding="utf-8")
    maintenance = (PROJECT_ROOT / "scripts" / "run_maintenance_task.ps1").read_text(encoding="utf-8")
    assert "'-m', 'app.main', 'worker', '--once', '--offline-only'" in worker
    assert "'-m', 'app.main', 'maintain', '--once', '--stale-after-seconds'" in maintenance
    assert "[string]$StaleAfterSeconds" in maintenance
    for source in (worker, maintenance):
        assert "-WorkingDirectory $resolvedRoot" in source
        assert "Start-Process" in source
        assert "-WindowStyle Hidden" in source
        assert "ExitCode" in source


def test_plan_is_pure_and_install_without_confirmation_never_calls_schtasks(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
):
    def forbidden(*args, **kwargs):
        raise AssertionError("schtasks must not run")

    monkeypatch.setattr(manage_windows_tasks.subprocess, "run", forbidden)
    common = [
        "--task", "worker", "--project-root", str(PROJECT_ROOT),
        "--python-executable", sys.executable, "--user-id", "LOCAL\\review",
    ]
    assert manage_windows_tasks.main(["plan", *common]) == 0
    assert "SYSTEM TASK NOT REGISTERED" in capsys.readouterr().out
    assert manage_windows_tasks.main(["install", *common]) == 2
    assert not (PROJECT_ROOT / "runtime" / "task-scheduler").exists()


def test_commands_are_argument_lists_and_path_metacharacters_fail_closed(tmp_path: Path):
    spec = _specs()[SystemTaskKind.WORKER]
    command = registration_command(spec, tmp_path / "worker.xml")
    assert command[:4] == ["schtasks.exe", "/Create", "/TN", spec.task_name]
    assert isinstance(command, list)
    with pytest.raises(ValueError, match="unsafe"):
        build_windows_task_specs(
            project_root=tmp_path / "bad;root",
            python_executable=sys.executable,
            powershell_executable=POWERSHELL,
            user_id="review",
        )


def test_system_scheduled_worker_blocks_real_research_before_runner(settings, account):
    calls = {"real": 0}

    class AllowingPolicy:
        @staticmethod
        def check_worker_runtime(*args, **kwargs):
            return PolicyDecision.ok()

    def forbidden_real(*args, **kwargs):
        calls["real"] += 1
        raise AssertionError("paid runner was reached")

    dispatcher = JobDispatcher(
        settings=settings,
        storage=object(),
        policy=AllowingPolicy(),
        research_real=forbidden_real,
        allow_real_research=False,
    )
    job = Job(
        id="paid-system-job",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key="paid-system-job",
        topic_id=1,
        payload={"dry_run": False},
    )
    with pytest.raises(PolicyDeniedError) as caught:
        dispatcher.dispatch(job, lease_owner="system-task", heartbeat=lambda: None)
    assert caught.value.decision.code == "SYSTEM_SCHEDULER_OFFLINE_ONLY"
    assert calls["real"] == 0
