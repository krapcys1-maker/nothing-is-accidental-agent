"""One controlled online ARTICLE: deterministic plan -> Opus writer/reviewer."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json

from app.content.controlled_entrypoint import (
    ControlledArticleAuthority,
    run_controlled_article,
)
from app.content.foundation import ContentStatus
from app.core.clock import SystemClock
from app.core.config import load_settings
from app.model_routing.contracts import LogicalModelRole
from app.operations.controlled_live import OPEN_PROFILE_ORDER, restore_fail_closed
from app.storage.db import RUNTIME_SCHEMA_VERSION, connection_schema_versions
from app.storage.repositories import SqliteStorage


PROVIDER = "ANTHROPIC"
MODEL_ID = "claude-opus-5"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--research-card-id", required=True, type=int)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--cost-ceiling-usd", type=Decimal, default=Decimal("1.000000"))
    args = parser.parse_args(argv)
    if not args.confirm_live:
        print("BLOCKED: --confirm-live is required")
        return 2
    if args.cost_ceiling_usd <= 0 or args.cost_ceiling_usd > Decimal("2.000000"):
        print("BLOCKED: ARTICLE ceiling must be in (0, 2.00]")
        return 2

    settings = load_settings()
    real = replace(
        settings,
        dry_run=False,
        max_daily_cost_usd=10.0,
    )
    clock = SystemClock()
    storage = SqliteStorage.open(settings.db_path)
    try:
        if connection_schema_versions(storage.conn)[-1] != RUNTIME_SCHEMA_VERSION:
            print("BLOCKED: runtime schema mismatch")
            return 2
        active_jobs = storage.conn.execute(
            "SELECT id,status FROM jobs WHERE status IN ('QUEUED','LEASED','RUNNING')"
        ).fetchall()
        if active_jobs and not (
            len(active_jobs) == 1
            and active_jobs[0]["id"] == args.job_id
            and active_jobs[0]["status"] == "QUEUED"
        ):
            print("BLOCKED: another active job exists")
            return 2
        card = storage.get_research_card(args.research_card_id)
        if card is None or card.publication_recommendation.value != "PROCEED":
            print("BLOCKED: ARTICLE requires one PROCEED Research Card")
            return 2
        lineage = storage.conn.execute(
            "SELECT count(*) AS total,count(DISTINCT retrieval_id) AS retrievals "
            "FROM evidence_source_lineage WHERE research_card_id=?",
            (args.research_card_id,),
        ).fetchone()
        if int(lineage["total"]) < 3 or int(lineage["retrievals"]) < 3:
            print("BLOCKED: Research Card lacks complete independent evidence lineage")
            return 2
        for role in (
            LogicalModelRole.ARTICLE_WRITER,
            LogicalModelRole.ARTICLE_REVIEWER,
        ):
            binding = storage.get_active_model_for_role(role)
            policy = storage.get_model_role_policy(role)
            if (
                binding is None
                or policy is None
                or binding.provider != PROVIDER
                or binding.technical_model_id != MODEL_ID
                or policy.fallback_policy != "FORBIDDEN"
            ):
                print(f"BLOCKED: exact {role.value} binding is unavailable")
                return 2
        now = clock.now()
        persisted_approval = storage.conn.execute(
            "SELECT * FROM content_provider_approvals WHERE job_id=?",
            (args.job_id,),
        ).fetchone()
        if persisted_approval is None:
            authority = ControlledArticleAuthority(
                job_id=args.job_id,
                approval_ref=f"approval:{args.job_id}",
                approved_by=args.approved_by,
                approved_at=now.isoformat(),
                expires_at=(now + timedelta(minutes=30)).isoformat(),
                cost_ceiling_usd=args.cost_ceiling_usd,
            )
        else:
            if (
                persisted_approval["approved_by"] != args.approved_by
                or Decimal(str(persisted_approval["cap_usd"])) != args.cost_ceiling_usd
                or persisted_approval["consumed_at"] is not None
            ):
                print("BLOCKED: queued job carries a different or consumed approval")
                return 2
            authority = ControlledArticleAuthority(
                job_id=args.job_id,
                approval_ref=str(persisted_approval["approval_ref"]),
                approved_by=str(persisted_approval["approved_by"]),
                approved_at=str(persisted_approval["approved_at"]),
                expires_at=str(persisted_approval["expires_at"]),
                cost_ceiling_usd=str(persisted_approval["cap_usd"]),
            )
        storage.apply_security_flag_profile(
            OPEN_PROFILE_ORDER,
            updated_by=args.approved_by,
            reason=f"controlled online ARTICLE {args.job_id}",
            now=now,
        )
    finally:
        storage.close()

    try:
        result = run_controlled_article(
            settings=real,
            account_id="nothing_is_accidental",
            research_card_id=args.research_card_id,
            idempotency_key=args.job_id,
            authority=authority,
            clock=clock,
            lease_owner=f"controlled-article:{args.job_id}",
            timeout_seconds=300.0,
        )
    finally:
        cleanup = SqliteStorage.open(settings.db_path)
        try:
            restore_fail_closed(
                cleanup,
                reason=f"controlled online ARTICLE {args.job_id} restore",
                now=clock.now(),
            )
        finally:
            cleanup.close()

    storage = SqliteStorage.open(settings.db_path)
    try:
        state = storage.get_content_pipeline_state(args.job_id)
        content = state["content"]
        run_id = str(content["run_id"])
        usage = [dict(row) for row in storage.conn.execute(
            "SELECT provider,model,task,input_tokens,output_tokens,"
            "cache_read_tokens,cache_write_tokens,estimated_cost_usd,request_id "
            "FROM model_usage WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()]
        roles = [dict(row) for row in storage.conn.execute(
            "SELECT logical_role,outcome,execution_ref,input_tokens,output_tokens,"
            "cost_usd,failure_kind FROM role_provider_executions "
            "WHERE job_id=? ORDER BY logical_role,attempt_no",
            (args.job_id,),
        ).fetchall()]
        publication = storage.conn.execute(
            "SELECT status,published_at,external_url FROM content_items WHERE id=?",
            (result.content_id,),
        ).fetchone()
        integrity = storage.conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(storage.conn.execute("PRAGMA foreign_key_check").fetchall())
        payload = {
            "status": (
                "PASS"
                if ContentStatus(str(content["status"])) is ContentStatus.PENDING_APPROVAL
                else "FAIL"
            ),
            "worker_status": result.worker.status.value,
            "worker_detail": result.worker.detail,
            "job_id": args.job_id,
            "content_id": result.content_id,
            "run_id": run_id,
            "research_card_id": args.research_card_id,
            "content_status": content["status"],
            "writer_attempts": len(state["attempts"]),
            "evaluations": len(state["evaluations"]),
            "provider": PROVIDER,
            "model": MODEL_ID,
            "usage": usage,
            "role_executions": roles,
            "total_cost_usd": format(
                sum((Decimal(str(row["estimated_cost_usd"])) for row in usage), Decimal("0")),
                ".6f",
            ),
            "published_at": publication["published_at"],
            "external_url": publication["external_url"],
            "schema": connection_schema_versions(storage.conn)[-1],
            "integrity_check": integrity,
            "foreign_key_check": foreign_keys,
        }
        print(json.dumps(payload, sort_keys=True, default=str))
        return 0 if payload["status"] == "PASS" else 3
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
