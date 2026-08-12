"""Explicit 0034 -> 0035 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0034_to_0035


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate one explicitly named SQLite database from exact schema 0034 to 0035."
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0034-to-0035", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0034_to_0035:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0034-to-0035 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0034_to_0035(args.db_path)
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
