"""Explicit 0035 -> 0036 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0035_to_0036


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate one explicitly named SQLite database from exact schema 0035 to 0036."
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0035-to-0036", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0035_to_0036:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0035-to-0036 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0035_to_0036(args.db_path)
    except (ExplicitMigrationError, SchemaVersionError) as exc:
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
