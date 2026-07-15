"""Deterministic, complete pytest partition runner for offline verification.

Each node id is assigned by interpreting its *entire* SHA-256 digest (of the
UTF-8 node id) as a big-endian integer and taking that value modulo ``parts``.
The runner collects once for each invocation, checks that the resulting node
ids are unique, and executes only the selected, sorted partition in bounded
command-line batches.  It never uses a digest prefix.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
from typing import Iterable, Sequence

import pytest


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MAX_COMMAND_CHARS = 24_000


def partition_index(node_id: str, parts: int) -> int:
    """Return a stable partition using the complete SHA-256 digest."""
    if parts < 1:
        raise ValueError("parts must be positive")
    digest = hashlib.sha256(node_id.encode("utf-8")).digest()
    return int.from_bytes(digest, byteorder="big", signed=False) % parts


def select_partition(node_ids: Iterable[str], *, parts: int, index: int) -> list[str]:
    """Return a sorted, duplicate-free partition of collected pytest node ids."""
    if not 0 <= index < parts:
        raise ValueError("index must be in [0, parts)")
    normalized = sorted(node_ids)
    if len(normalized) != len(set(normalized)):
        raise ValueError("pytest collection returned duplicate node ids")
    return [node_id for node_id in normalized if partition_index(node_id, parts) == index]


def verify_partition_cover(node_ids: Iterable[str], *, parts: int) -> None:
    """Prove that all partitions are disjoint and cover every collected node id once."""
    normalized = sorted(node_ids)
    selected = [select_partition(normalized, parts=parts, index=index) for index in range(parts)]
    flattened = [node_id for group in selected for node_id in group]
    if len(flattened) != len(set(flattened)) or sorted(flattened) != normalized:
        raise ValueError("partition coverage is not exactly-once")


class _NodeIdCollector:
    node_ids: list[str]

    def __init__(self) -> None:
        self.node_ids = []

    def pytest_collection_modifyitems(self, session, config, items) -> None:
        del session, config
        self.node_ids = [item.nodeid for item in items]


def collect_node_ids(project_root: Path = _PROJECT_ROOT) -> list[str]:
    """Collect pytest node ids without executing any test."""
    collector = _NodeIdCollector()
    previous_cwd = Path.cwd()
    try:
        if previous_cwd != project_root:
            # pytest resolves the project configuration from its current root.
            # The command-line runner always passes the repository root here.
            import os
            os.chdir(project_root)
        result = pytest.main(["--collect-only", "-q"], plugins=[collector])
    finally:
        if Path.cwd() != previous_cwd:
            import os
            os.chdir(previous_cwd)
    if result != 0:
        raise RuntimeError("pytest collection failed")
    if not collector.node_ids:
        raise RuntimeError("pytest collection returned no node ids")
    if len(collector.node_ids) != len(set(collector.node_ids)):
        raise RuntimeError("pytest collection returned duplicate node ids")
    return sorted(collector.node_ids)


def command_batches(node_ids: Sequence[str]) -> list[list[str]]:
    """Bound Windows command length while preserving node-id order and coverage."""
    prefix_size = len(sys.executable) + len(" -m pytest -q ")
    batches: list[list[str]] = []
    current: list[str] = []
    current_size = prefix_size
    for node_id in node_ids:
        next_size = current_size + len(node_id) + 1
        if current and next_size > _MAX_COMMAND_CHARS:
            batches.append(current)
            current = []
            current_size = prefix_size
        current.append(node_id)
        current_size += len(node_id) + 1
    if current:
        batches.append(current)
    return batches


def run_partition(node_ids: Sequence[str], project_root: Path = _PROJECT_ROOT) -> int:
    """Run exactly the supplied node ids, once each, in reproducible batches."""
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("partition contains duplicate node ids")
    for batch in command_batches(node_ids):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *batch], cwd=project_root, check=False,
        )
        if result.returncode != 0:
            return result.returncode
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parts", type=int, required=True, help="Total partition count (>= 1).")
    parser.add_argument("--index", type=int, help="Zero-based partition index to list or run.")
    parser.add_argument("--list", action="store_true", help="Print selected node ids; do not run them.")
    parser.add_argument("--verify", action="store_true", help="Verify exact-once coverage; do not run tests.")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.parts < 1:
        print("--parts must be positive", file=sys.stderr)
        return 2
    if args.verify and args.index is not None:
        print("--verify cannot be combined with --index", file=sys.stderr)
        return 2
    if not args.verify and args.index is None:
        print("--index is required unless --verify is used", file=sys.stderr)
        return 2
    try:
        node_ids = collect_node_ids()
        verify_partition_cover(node_ids, parts=args.parts)
        if args.verify:
            print(f"PARTITION COVERAGE OK: {len(node_ids)} node ids across {args.parts} partitions")
            return 0
        selected = select_partition(node_ids, parts=args.parts, index=args.index)
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.list:
        print("\n".join(selected))
        return 0
    print(
        f"Running partition {args.index}/{args.parts}: {len(selected)} of {len(node_ids)} node ids "
        "(full SHA-256 integer modulo parts)."
    )
    return run_partition(selected)


if __name__ == "__main__":
    raise SystemExit(main())
