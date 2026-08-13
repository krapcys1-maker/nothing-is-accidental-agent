"""Operator CLI for one separately authorised REVIEW-ONLY request."""
from __future__ import annotations

import argparse
from datetime import timedelta
from decimal import Decimal
import json

from app.content.review_only import (
    ReviewOnlyAuthority,
    ReviewOnlyError,
    run_controlled_article_review_only,
)
from app.core.clock import SystemClock
from app.core.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--content-id", required=True, type=int)
    parser.add_argument("--draft-fingerprint", required=True)
    parser.add_argument("--initial-review-execution-ref", required=True)
    parser.add_argument("--writer-execution-ref", required=True)
    parser.add_argument("--post-review-execution-ref", required=True)
    parser.add_argument("--approval-ref", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--cost-ceiling-usd", required=True, type=Decimal)
    parser.add_argument("--confirm-review-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_review_only:
        print("BLOCKED: --confirm-review-only is required")
        return 2
    clock = SystemClock()
    now = clock.now()
    authority = ReviewOnlyAuthority(
        job_id=args.job_id,
        content_id=args.content_id,
        draft_fingerprint=args.draft_fingerprint,
        approval_ref=args.approval_ref,
        initial_review_execution_ref=args.initial_review_execution_ref,
        writer_execution_ref=args.writer_execution_ref,
        post_review_execution_ref=args.post_review_execution_ref,
        approved_by=args.approved_by,
        approved_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=30)).isoformat(),
        cost_ceiling_usd=args.cost_ceiling_usd,
    )
    try:
        result = run_controlled_article_review_only(
            settings=load_settings(), authority=authority, clock=clock,
        )
    except ReviewOnlyError as exc:
        print(json.dumps({"status": "BLOCKED", "code": exc.code,
                          "detail": exc.detail}, sort_keys=True))
        return 2
    print(json.dumps({
        "status": "REVIEW_ONLY_COMPLETE",
        "job_id": result.job_id,
        "run_id": result.run_id,
        "content_id": result.content_id,
        "writer_attempt_no": result.writer_attempt_no,
        "review_no": result.review_no,
        "draft_fingerprint": result.draft_fingerprint,
        "approval_ref": result.approval_ref,
        "initial_review_execution_ref": result.initial_review_execution_ref,
        "writer_execution_ref": result.writer_execution_ref,
        "post_review_execution_ref": result.post_review_execution_ref,
        "decision": result.decision.value,
        "final_status": result.final_status.value,
        "writer_attempts": result.writer_attempts,
        "reviews": result.reviews,
        "publication_reachable": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
