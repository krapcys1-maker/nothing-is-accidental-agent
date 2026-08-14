"""Explicit 0042 -> 0043 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0042_to_0043


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named SQLite database from exact schema "
            "0042 to retryable frozen inputs schema 0043."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0042-to-0043", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0042_to_0043:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0042-to-0043 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0042_to_0043(args.db_path)
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
