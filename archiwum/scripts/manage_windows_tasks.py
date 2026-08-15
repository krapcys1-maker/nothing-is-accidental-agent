"""Explicit Windows Task Scheduler management; plan is the default safe action."""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import subprocess
import sys

from app.scheduler.windows_tasks import (
    SystemTaskKind,
    build_windows_task_specs,
    registration_command,
    removal_command,
    render_windows_task_xml,
    verification_command,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _current_user() -> str:
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip() or getpass.getuser()
    return f"{domain}\\{username}" if domain else username


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan, register, verify or remove one NIA Windows scheduled task.",
    )
    parser.add_argument("action", choices=("plan", "install", "verify", "remove"))
    parser.add_argument("--task", required=True, choices=[item.value for item in SystemTaskKind])
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--user-id", default=_current_user())
    parser.add_argument("--confirm-register-system-task", action="store_true")
    parser.add_argument("--confirm-remove-system-task", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec = build_windows_task_specs(
            project_root=args.project_root,
            python_executable=args.python_executable,
            user_id=args.user_id,
        )[SystemTaskKind(args.task)]
    except (OSError, ValueError) as exc:
        print(f"TASK SCHEDULER: invalid configuration: {exc}", file=sys.stderr)
        return 3

    if args.action == "plan":
        print(f"task_name={spec.task_name}")
        print(f"python_executable={spec.python_executable}")
        print(f"working_directory={spec.project_root}")
        print(f"launcher={spec.launcher_path}")
        print(f"interval_minutes={spec.interval_minutes}")
        print("multiple_instances=IgnoreNew")
        print("scheduler_retry=false execution_time_limit=unlimited")
        print("SYSTEM TASK NOT REGISTERED")
        return 0

    try:
        if args.action == "verify":
            completed = subprocess.run(
                verification_command(spec), check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        elif args.action == "install":
            if not args.confirm_register_system_task:
                print(
                    "TASK SCHEDULER: install requires --confirm-register-system-task ",
                    "and separate owner approval for this one task.",
                    file=sys.stderr,
                )
                return 2
            runtime_dir = spec.project_root / "runtime" / "task-scheduler"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            xml_path = runtime_dir / f"{spec.task_name}.xml"
            xml_path.write_bytes(render_windows_task_xml(spec))
            completed = subprocess.run(
                registration_command(spec, xml_path), check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        else:
            if not args.confirm_remove_system_task:
                print(
                    "TASK SCHEDULER: remove requires --confirm-remove-system-task ",
                    "and separate owner approval for this one task.",
                    file=sys.stderr,
                )
                return 2
            completed = subprocess.run(
                removal_command(spec), check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
    except OSError as exc:
        print(f"TASK SCHEDULER: system command failed: {exc}", file=sys.stderr)
        return 6
    if completed.stdout:
        print(completed.stdout.rstrip())
    if completed.stderr:
        print(completed.stderr.rstrip(), file=sys.stderr)
    return 0 if completed.returncode == 0 else 6


if __name__ == "__main__":
    raise SystemExit(main())
