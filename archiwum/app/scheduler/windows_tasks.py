"""Pure Windows Task Scheduler configuration for existing Stage 1 entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET


TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"
ET.register_namespace("", TASK_NAMESPACE)


class SystemTaskKind(str, Enum):
    WORKER = "worker"
    MAINTENANCE = "maintenance"


@dataclass(frozen=True)
class WindowsTaskSpec:
    kind: SystemTaskKind
    task_name: str
    description: str
    interval_minutes: int
    project_root: Path
    python_executable: Path
    launcher_path: Path
    powershell_executable: Path
    user_id: str
    start_boundary: datetime
    launcher_arguments: tuple[str, ...]


_UNSAFE_ARGUMENT_CHARACTERS = re.compile(r"[\"'`$;&|<>\r\n\x00]")


def _validated_existing_path(value: Path | str, *, label: str, directory: bool) -> Path:
    path = Path(value).resolve()
    if _UNSAFE_ARGUMENT_CHARACTERS.search(str(path)):
        raise ValueError(f"{label} contains characters unsafe for a Task Scheduler action.")
    if directory and not path.is_dir():
        raise ValueError(f"{label} must be an existing directory: {path}")
    if not directory and not path.is_file():
        raise ValueError(f"{label} must be an existing file: {path}")
    return path


def _quoted(value: Path | str) -> str:
    text = str(value)
    if _UNSAFE_ARGUMENT_CHARACTERS.search(text):
        raise ValueError("Task Scheduler argument contains unsafe characters.")
    return f'"{text}"'


def build_windows_task_specs(
    *,
    project_root: Path | str,
    python_executable: Path | str,
    user_id: str,
    start_boundary: datetime | None = None,
    powershell_executable: Path | str | None = None,
) -> dict[SystemTaskKind, WindowsTaskSpec]:
    """Build two deterministic specs without registering or running anything."""
    root = _validated_existing_path(project_root, label="project_root", directory=True)
    python = _validated_existing_path(
        python_executable, label="python_executable", directory=False,
    )
    if not user_id.strip() or _UNSAFE_ARGUMENT_CHARACTERS.search(user_id):
        raise ValueError("user_id must be non-empty and free of command metacharacters.")
    powershell = Path(powershell_executable) if powershell_executable else Path(
        os.environ.get("SystemRoot", r"C:\Windows")
    ) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    powershell = _validated_existing_path(
        powershell, label="powershell_executable", directory=False,
    )
    boundary = start_boundary or (datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1))
    if boundary.tzinfo is not None:
        boundary = boundary.astimezone().replace(tzinfo=None)

    worker_launcher = _validated_existing_path(
        root / "scripts" / "run_worker_task.ps1",
        label="worker launcher",
        directory=False,
    )
    maintenance_launcher = _validated_existing_path(
        root / "scripts" / "run_maintenance_task.ps1",
        label="maintenance launcher",
        directory=False,
    )
    shared = (
        "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
    )
    return {
        SystemTaskKind.WORKER: WindowsTaskSpec(
            kind=SystemTaskKind.WORKER,
            task_name="NothingIsAccidental-WorkerOffline",
            description=(
                "Runs the canonical Stage 1 worker once in offline-only mode. "
                "It cannot enable flags, paid actions, browser actions or publication."
            ),
            interval_minutes=1,
            project_root=root,
            python_executable=python,
            launcher_path=worker_launcher,
            powershell_executable=powershell,
            user_id=user_id,
            start_boundary=boundary,
            launcher_arguments=shared + (
                "-File", str(worker_launcher), "-PythonExe", str(python),
                "-ProjectRoot", str(root),
            ),
        ),
        SystemTaskKind.MAINTENANCE: WindowsTaskSpec(
            kind=SystemTaskKind.MAINTENANCE,
            task_name="NothingIsAccidental-Maintenance",
            description=(
                "Runs the canonical Stage 1 maintenance entrypoint once. "
                "It never claims or dispatches jobs and cannot call a provider or browser."
            ),
            interval_minutes=5,
            project_root=root,
            python_executable=python,
            launcher_path=maintenance_launcher,
            powershell_executable=powershell,
            user_id=user_id,
            start_boundary=boundary,
            launcher_arguments=shared + (
                "-File", str(maintenance_launcher), "-PythonExe", str(python),
                "-ProjectRoot", str(root), "-StaleAfterSeconds", "300",
            ),
        ),
    }


def _element(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
    child = ET.SubElement(parent, f"{{{TASK_NAMESPACE}}}{name}")
    if text is not None:
        child.text = text
    return child


def render_windows_task_xml(spec: WindowsTaskSpec) -> bytes:
    """Render a task with IgnoreNew, no scheduler retry and no execution kill timeout."""
    task = ET.Element(f"{{{TASK_NAMESPACE}}}Task", {"version": "1.4"})
    registration = _element(task, "RegistrationInfo")
    _element(registration, "Author", spec.user_id)
    _element(registration, "Description", spec.description)

    triggers = _element(task, "Triggers")
    trigger = _element(triggers, "CalendarTrigger")
    repetition = _element(trigger, "Repetition")
    _element(repetition, "Interval", f"PT{spec.interval_minutes}M")
    _element(repetition, "StopAtDurationEnd", "false")
    _element(trigger, "StartBoundary", spec.start_boundary.isoformat(timespec="seconds"))
    _element(trigger, "Enabled", "true")
    schedule = _element(trigger, "ScheduleByDay")
    _element(schedule, "DaysInterval", "1")

    principals = _element(task, "Principals")
    principal = ET.SubElement(
        principals, f"{{{TASK_NAMESPACE}}}Principal", {"id": "Author"},
    )
    _element(principal, "UserId", spec.user_id)
    _element(principal, "LogonType", "InteractiveToken")
    _element(principal, "RunLevel", "LeastPrivilege")

    settings = _element(task, "Settings")
    _element(settings, "MultipleInstancesPolicy", "IgnoreNew")
    _element(settings, "DisallowStartIfOnBatteries", "false")
    _element(settings, "StopIfGoingOnBatteries", "false")
    _element(settings, "AllowHardTerminate", "false")
    _element(settings, "StartWhenAvailable", "true")
    _element(settings, "RunOnlyIfNetworkAvailable", "false")
    idle = _element(settings, "IdleSettings")
    _element(idle, "StopOnIdleEnd", "false")
    _element(idle, "RestartOnIdle", "false")
    _element(settings, "AllowStartOnDemand", "true")
    _element(settings, "Enabled", "true")
    _element(settings, "Hidden", "false")
    _element(settings, "WakeToRun", "false")
    # PT0S prevents Task Scheduler from killing Python during a SQLite write.
    _element(settings, "ExecutionTimeLimit", "PT0S")
    _element(settings, "Priority", "7")

    actions = ET.SubElement(
        task, f"{{{TASK_NAMESPACE}}}Actions", {"Context": "Author"},
    )
    execute = _element(actions, "Exec")
    _element(execute, "Command", str(spec.powershell_executable))
    rendered_args = " ".join(
        _quoted(argument) if (" " in argument or "\\" in argument) else argument
        for argument in spec.launcher_arguments
    )
    _element(execute, "Arguments", rendered_args)
    _element(execute, "WorkingDirectory", str(spec.project_root))
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def registration_command(spec: WindowsTaskSpec, xml_path: Path | str) -> list[str]:
    return [
        "schtasks.exe", "/Create", "/TN", spec.task_name,
        "/XML", str(Path(xml_path).resolve()), "/F",
    ]


def verification_command(spec: WindowsTaskSpec) -> list[str]:
    return ["schtasks.exe", "/Query", "/TN", spec.task_name, "/XML"]


def removal_command(spec: WindowsTaskSpec) -> list[str]:
    return ["schtasks.exe", "/Delete", "/TN", spec.task_name, "/F"]
