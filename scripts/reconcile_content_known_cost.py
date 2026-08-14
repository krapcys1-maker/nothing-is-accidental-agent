"""Operator known-cost reconciliation for ONE CONTENT provider attempt.

Preview first, confirm second.  The charge is never supplied by the operator: it
is read from the single canonical ``model_usage`` row that the failed writer
already recorded, and the operator only confirms that exact amount.  No provider
call, no retry, no second cost, no content approval.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys

from app.models import ExecutionResolution, FinancialResolution
from app.ports.storage import ProviderAttemptReconciliationError
from app.storage.repositories import SqliteStorage

RESOLUTION = "CHARGED_KNOWN:EXECUTION_FAILED"


def _print_preview(preview: object, known_cost: Decimal, reserved: Decimal) -> None:
    difference = known_cost - reserved
    print("CONTENT KNOWN-COST RECONCILIATION PLAN")
    print(f"request_id={preview.request_id}")
    print(f"account_id={preview.account_id}")
    print(f"attempt_status={preview.attempt_status.value}")
    print(f"job_status={preview.job_status}")
    print(f"run_status={preview.run_status}")
    print(f"canonical_usage_rows={preview.usage_count}")
    print(f"known_cost_usd={known_cost:.6f}   (source: existing model_usage)")
    print(f"reserved_amount_usd={reserved:.6f}")
    print(f"difference_usd={difference:+.6f}")
    print(f"financial_resolution={FinancialResolution.CHARGED_KNOWN.value}")
    print(f"execution_resolution={ExecutionResolution.EXECUTION_FAILED.value}")
    print(f"combined_resolution={RESOLUTION}")
    print("PLANNED TRANSITIONS")
    print("  provider_attempts: NEEDS_RECONCILIATION -> RECONCILED_SETTLED")
    print("  provider_attempts.actual_cost_usd: stays NULL (cost lives in model_usage)")
    print("  jobs.status: NEEDS_VERIFICATION -> FAILED")
    print("  runs.status: -> FAILED")
    print("  reconciliation_events: + one FINAL_RESOLUTION")
    print("  model_usage: UNCHANGED (no new row, no second charge)")
    print("  content_runs / content_items: UNCHANGED")
    print("  APPROVE / PENDING_APPROVAL: never produced by this path")
    print(f"version_token={preview.version_token}")
    print("provider_call=false inference=false retry=false publication=false")


def _known_cost(store: SqliteStorage, request_id: str) -> Decimal:
    """The single canonical charge; anything ambiguous fails closed."""
    rows = store.conn.execute(
        "SELECT estimated_cost_usd FROM model_usage "
        "WHERE request_id=? AND dry_run=0 AND is_legacy_usage=0",
        (request_id,),
    ).fetchall()
    if len(rows) != 1:
        raise ProviderAttemptReconciliationError(
            f"Known-cost reconciliation requires exactly one canonical usage row; "
            f"found {len(rows)}."
        )
    return Decimal(str(rows[0]["estimated_cost_usd"])).quantize(Decimal("0.000001"))


def _reserved(store: SqliteStorage, request_id: str) -> Decimal:
    row = store.conn.execute(
        "SELECT reserved_amount_usd FROM provider_attempts WHERE request_id=?",
        (request_id,),
    ).fetchone()
    if row is None:
        raise ProviderAttemptReconciliationError("No such provider attempt.")
    return Decimal(str(row["reserved_amount_usd"])).quantize(Decimal("0.000001"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve one CONTENT provider attempt as CHARGED_KNOWN using the "
            "cost already recorded in model_usage. Preview unless confirmed."
        )
    )
    parser.add_argument("--db-path", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--reconciled-by", required=True)
    parser.add_argument("--note", required=True)
    # No default resolution: the operator states the decision explicitly.
    parser.add_argument(
        "--financial-resolution", required=True,
        choices=[FinancialResolution.CHARGED_KNOWN.value],
    )
    parser.add_argument("--confirm-charged-known", action="store_true")
    args = parser.parse_args(argv)
    try:
        preview_store = SqliteStorage.open_read_only(args.db_path)
        try:
            preview = preview_store.preview_provider_attempt_reconciliation(
                request_id=args.request_id, account_id=args.account_id,
            )
            known_cost = _known_cost(preview_store, args.request_id)
            reserved = _reserved(preview_store, args.request_id)
        finally:
            preview_store.close()
        _print_preview(preview, known_cost, reserved)
        if not args.confirm_charged_known:
            print(
                "PREVIEW ONLY: pass --confirm-charged-known to persist this exact "
                "reconciliation."
            )
            return 0
        store = SqliteStorage.open(args.db_path)
        try:
            # Re-read the charge under the write connection and pin the preview
            # token, so a concurrent change cannot slip a different cost through.
            confirmed_cost = _known_cost(store, args.request_id)
            if confirmed_cost != known_cost:
                raise ProviderAttemptReconciliationError(
                    "Canonical usage changed between preview and confirmation."
                )
            result = store.resolve_provider_attempt_reconciliation(
                request_id=args.request_id, account_id=args.account_id,
                financial_resolution=FinancialResolution.CHARGED_KNOWN,
                execution_resolution=ExecutionResolution.EXECUTION_FAILED,
                actual_cost_usd=format(confirmed_cost, ".6f"),
                reconciled_by=args.reconciled_by, note=args.note,
                expected_version_token=preview.version_token,
            )
        finally:
            store.close()
        print(
            "CONTENT KNOWN-COST RECONCILIATION: "
            f"attempt_status={result.attempt.status.value} "
            f"resolution={RESOLUTION} "
            f"usage_id={result.usage_id} "
            f"charged_usd={confirmed_cost:.6f} "
            f"idempotent={str(result.idempotent).lower()}"
        )
        return 0
    except (
        ProviderAttemptReconciliationError, ValueError, sqlite3.Error, OSError,
    ) as exc:
        print(
            f"CONTENT KNOWN-COST RECONCILIATION: failed closed: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
