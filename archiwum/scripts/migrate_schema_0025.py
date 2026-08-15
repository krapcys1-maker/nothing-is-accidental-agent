"""Explicit 0024 -> 0025 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, migrate_0024_to_0025


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named non-production SQLite database "
            "from exact schema 0024 to exact schema 0025."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument(
        "--confirm-0024-to-0025",
        action="store_true",
        help="Required explicit confirmation for this single schema step.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_0024_to_0025:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0024-to-0025 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0024_to_0025(args.db_path)
    except ExplicitMigrationError as exc:
        print(f"SCHEMA MIGRATION: failed closed: {exc}", file=sys.stderr)
        return 2
    print(
        "SCHEMA MIGRATION: "
        f"{result.source_version} -> {result.target_version}; "
        f"applied={list(result.applied_migrations)}; "
        f"idempotent={str(result.idempotent).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
