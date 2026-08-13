"""One-record owner adjudication; no provider, worker or REVIEW-ONLY imports."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3
import sys

from app.content.conservative_reconciliation import (
    ConservativeReconciliationError,
    ConservativeSourceType,
)
from app.storage.repositories import SqliteStorage


def _source_identity(args: argparse.Namespace) -> str:
    if args.source_type == ConservativeSourceType.PROVIDER_ATTEMPT.value:
        if not args.request_id or args.execution_ref:
            raise ConservativeReconciliationError(
                "PROVIDER_ATTEMPT requires exactly --request-id."
            )
        return args.request_id
    if not args.execution_ref or args.request_id:
        raise ConservativeReconciliationError(
            "ROLE_EXECUTION requires exactly --execution-ref."
        )
    return args.execution_ref


def _print_plan(plan: object) -> None:
    record = plan.record
    print("CONSERVATIVE RECONCILIATION PLAN")
    print(f"source_type={record.source_type.value}")
    print(f"source_identity={record.source_identity}")
    print(f"job_id={record.job_id}")
    print(f"content_id={record.content_id}")
    print(f"run_id={record.run_id}")
    print(f"provider={record.provider}")
    print(f"model={record.model}")
    print(f"previous_status={record.previous_status}")
    print(f"resolution={record.resolution.value}")
    print(f"reserved_amount_usd={record.reserved_amount_usd:.6f}")
    print(f"conservative_cost_usd={record.conservative_cost_usd:.6f}")
    print("actual_cost_usd=<null>")
    print(f"approved_by={record.approved_by}")
    print(f"approved_at={record.approved_at}")
    print(f"approval_fingerprint={record.approval_fingerprint}")
    print(f"existing={str(plan.existing).lower()}")
    print("provider_call=false inference=false review_only=false publication=false")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Conservatively charge the exact full reservation of one ambiguous "
            "historical CONTENT/ARTICLE provider effect."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument(
        "--source-type", required=True,
        choices=[item.value for item in ConservativeSourceType],
        type=lambda value: value.upper().replace("-", "_"),
    )
    parser.add_argument("--request-id")
    parser.add_argument("--execution-ref")
    parser.add_argument("--expected-reserved-amount-usd", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm-conservative-max-charged", action="store_true")
    args = parser.parse_args(argv)
    try:
        identity = _source_identity(args)
        preview_store = SqliteStorage.open_read_only(args.db_path)
        try:
            preview = preview_store.preview_conservative_content_reconciliation(
                source_type=args.source_type, source_identity=identity,
                expected_reserved_amount_usd=args.expected_reserved_amount_usd,
                approved_by=args.approved_by, approved_at=args.approved_at,
                reason=args.reason,
            )
        finally:
            preview_store.close()
        _print_plan(preview)
        if not args.confirm_conservative_max_charged:
            print(
                "PREVIEW ONLY: pass --confirm-conservative-max-charged to persist "
                "this exact owner adjudication."
            )
            return 0
        store = SqliteStorage.open(args.db_path)
        try:
            result = store.resolve_conservative_content_reconciliation(
                source_type=args.source_type, source_identity=identity,
                expected_reserved_amount_usd=args.expected_reserved_amount_usd,
                approved_by=args.approved_by, approved_at=args.approved_at,
                reason=args.reason,
            )
            summary = store.conservative_cost_summary()
        finally:
            store.close()
        print(
            "CONSERVATIVE RECONCILIATION: "
            f"reconciliation_id={result.record.reconciliation_id} "
            f"idempotent={str(result.idempotent).lower()}"
        )
        print(
            "COST SUMMARY: "
            f"actual_known={summary.actual_known_cost_usd:.6f} "
            f"conservative={summary.conservative_adjudicated_cost_usd:.6f} "
            f"effective={summary.effective_budget_spend_usd:.6f} "
            f"unresolved={summary.unresolved_provider_exposure_usd:.6f}"
        )
        return 0
    except (ConservativeReconciliationError, ValueError, sqlite3.Error, OSError) as exc:
        print(f"CONSERVATIVE RECONCILIATION: failed closed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
