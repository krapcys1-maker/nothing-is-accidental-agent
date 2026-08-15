"""Explicit 0031 -> 0032 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, migrate_0031_to_0032


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named SQLite database from exact schema "
            "0031 to exact schema 0032."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument(
        "--confirm-0031-to-0032",
        action="store_true",
        help="Required explicit confirmation for this single schema step.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_0031_to_0032:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0031-to-0032 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0031_to_0032(args.db_path)
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
