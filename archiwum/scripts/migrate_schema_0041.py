"""Explicit 0040 -> 0041 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0040_to_0041


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named SQLite database from exact schema "
            "0040 to reviewer document quality gate schema 0041."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0040-to-0041", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0040_to_0041:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0040-to-0041 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0040_to_0041(args.db_path)
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
