"""Plan or execute a copy-only rehearsal of the future production DB migration."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.operations.stage1_migration import (
    Stage1MigrationPreflightError,
    Stage1MigrationRequest,
    run_stage1_copy_preflight,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 1 DB migration rehearsal. It never replaces or migrates --source-db.",
    )
    parser.add_argument("action", choices=("plan", "execute-copy-preflight"))
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--expected-branch", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-source-size", type=int, required=True)
    parser.add_argument("--expected-source-mtime-utc", required=True)
    parser.add_argument("--expected-legacy-usage-count", type=int, default=13)
    parser.add_argument("--expected-real-cost-usd", default="0.684580")
    parser.add_argument("--confirm-copy-preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "plan":
        print("PLAN ONLY — NO FILES CREATED, NO DATABASE OPENED")
        print("source -> exact full backup -> candidate copy -> migrate candidate 0009→0014")
        print("checks: SHA/size/mtime, integrity, FK, 14 migrations, required triggers")
        print("checks: 13 legacy proofs, cost 0.684580, five blocked system_flags")
        print("source replacement=false rollback=full verified backup only")
        return 0
    if not args.confirm_copy_preflight_only:
        print(
            "COPY PREFLIGHT: execution requires --confirm-copy-preflight-only. "
            "This is not permission to migrate or replace production data.",
            file=sys.stderr,
        )
        return 2
    request = Stage1MigrationRequest(
        project_root=args.project_root,
        source_db=args.source_db,
        workspace=args.workspace,
        expected_branch=args.expected_branch,
        expected_head=args.expected_head,
        expected_source_sha256=args.expected_source_sha256,
        expected_source_size=args.expected_source_size,
        expected_source_mtime_utc=args.expected_source_mtime_utc,
        expected_legacy_usage_count=args.expected_legacy_usage_count,
        expected_real_cost_usd=args.expected_real_cost_usd,
    )
    try:
        result = run_stage1_copy_preflight(request)
    except (Stage1MigrationPreflightError, OSError, ValueError) as exc:
        print(f"COPY PREFLIGHT: failed closed: {exc}", file=sys.stderr)
        return 2
    print("COPY PREFLIGHT: PASSED — PRODUCTION DATABASE NOT MIGRATED")
    print(f"backup={result.backup_path}")
    print(f"candidate={result.candidate_path}")
    print(f"candidate_sha256={result.candidate.sha256}")
    print(f"legacy_proofs={result.legacy_proof_count}")
    print(f"real_cost_usd={result.real_cost_usd}")
    print(f"report={result.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
