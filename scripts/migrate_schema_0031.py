"""Explicit 0030 -> 0031 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, migrate_0030_to_0031


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named non-production SQLite database "
            "from exact schema 0030 to exact schema 0031."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument(
        "--confirm-0030-to-0031",
        action="store_true",
        help="Required explicit confirmation for this single schema step.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_0030_to_0031:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0030-to-0031 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0030_to_0031(args.db_path)
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
