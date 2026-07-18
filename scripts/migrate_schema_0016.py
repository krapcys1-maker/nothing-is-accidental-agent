"""Explicit 0015 -> 0016 migrator; never imported or called by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.db import (  # noqa: E402
    ExplicitMigrationError,
    SchemaVersionError,
    migrate_0015_to_0016,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Explicitly migrate one named SQLite database from exact schema 0015 "
            "to exact schema 0016. This command never starts runtime."
        )
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument(
        "--confirm-0015-to-0016",
        action="store_true",
        help="Required explicit confirmation; owner authorization is still external.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.confirm_0015_to_0016:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0015-to-0016 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0015_to_0016(args.db_path)
    except (ExplicitMigrationError, SchemaVersionError, OSError) as exc:
        print(f"SCHEMA MIGRATION: failed closed: {exc}", file=sys.stderr)
        return 2
    applied = ",".join(result.applied_migrations) or "none"
    print(
        "SCHEMA MIGRATION: OK "
        f"source={result.source_version} target={result.target_version} "
        f"applied={applied} idempotent={str(result.idempotent).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
