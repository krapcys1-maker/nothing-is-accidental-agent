"""Explicit 0041 -> 0042 migrator; never imported by runtime roots."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.storage.db import ExplicitMigrationError, SchemaVersionError, migrate_0041_to_0042


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate one explicitly named SQLite database from exact schema "
            "0041 to research conservative adjudication schema 0042."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--confirm-0041-to-0042", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_0041_to_0042:
        print(
            "SCHEMA MIGRATION: failed closed: --confirm-0041-to-0042 is required.",
            file=sys.stderr,
        )
        return 2
    try:
        result = migrate_0041_to_0042(args.db_path)
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
