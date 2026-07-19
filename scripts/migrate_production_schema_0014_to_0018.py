"""Owner-confirmed production schema migration orchestrator: exact 0014 -> 0018."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.operations.production_schema_migration import (  # noqa: E402
    CONFIRMATION_FLAG,
    SUPPORTED_FROM_VERSION,
    SUPPORTED_TARGET_VERSION,
    ProductionMigrationError,
    ProductionMigrationRequest,
    run_production_schema_migration,
)


def _non_negative_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected size must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected size must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Controlled production migration for the sole supported schema ladder "
            "0014 -> 0015 -> 0016 -> 0017 -> 0018. Runtime is not started."
        )
    )
    parser.add_argument("--db-path", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-size", type=_non_negative_size, required=True)
    parser.add_argument(
        "--expected-from-version",
        choices=(SUPPORTED_FROM_VERSION,),
        required=True,
    )
    parser.add_argument(
        "--target-version",
        choices=(SUPPORTED_TARGET_VERSION,),
        required=True,
    )
    parser.add_argument("--snapshot-path", type=Path, required=True)
    parser.add_argument(
        CONFIRMATION_FLAG,
        action="store_true",
        dest="confirmed_0014_to_0018",
        help="Exact owner confirmation for this invocation of the 0014-to-0018 ladder.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    request = ProductionMigrationRequest(
        db_path=args.db_path,
        expected_sha256=args.expected_sha256,
        expected_size=args.expected_size,
        expected_from_version=args.expected_from_version,
        target_version=args.target_version,
        snapshot_path=args.snapshot_path,
        confirmed_0014_to_0018=args.confirmed_0014_to_0018,
    )
    try:
        result = run_production_schema_migration(request)
    except ProductionMigrationError as exc:
        print(
            json.dumps(exc.as_dict(), ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
        )
        return 3 if exc.code == "MIGRATION_RESULT_NEEDS_OPERATOR_ASSESSMENT" else 2
    print(json.dumps(result.as_dict(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
