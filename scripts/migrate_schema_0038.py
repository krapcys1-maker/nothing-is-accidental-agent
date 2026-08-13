"""Explicit 0037 -> 0038 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0037_to_0038


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate one explicitly named SQLite database from exact schema 0037 to 0038."
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0037-to-0038", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0037_to_0038:
        print("SCHEMA MIGRATION: failed closed: --confirm-0037-to-0038 is required.", file=sys.stderr)
        return 2
    try:
        result = migrate_0037_to_0038(args.db_path)
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
