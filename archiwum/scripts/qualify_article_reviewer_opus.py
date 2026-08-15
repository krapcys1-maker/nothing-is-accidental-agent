"""One-shot production qualification for ARTICLE_REVIEWER at article length.

The reviewer inherited the ARTICLE_RESEARCH envelope, which was qualified for a
stage that answers in a short card. A reviewer answers with one accounting entry
per sentence, so its output grows with the article: a real 64-segment review
used 7,540 of 8,192 tokens, and a 65-segment one was truncated and thrown away
after the provider had been paid for it. This qualifies an envelope sized for
the work instead - 47,616 in, 16,384 out - so the ceiling stops being the thing
that decides whether an article survives.

It records a qualification approval, runs exactly one paid probe against the
already-audited provider boundary, and activates the role on PASS. It never
retries and never falls back.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from uuid import uuid4

from app.core.config import load_settings
from app.model_routing.contracts import LogicalModelRole
from app.model_routing.production_qualification import (
    OPUS_ARTICLE_REVIEWER_QUALIFICATION_CONTRACT as CONTRACT,
    execute_opus_article_reviewer_production_qualification,
)
from app.model_routing.qualification import QualificationApproval
from app.model_routing.role_activation import (
    ExactRoleActivationRequest,
    activate_and_bind_exact_role,
)
from app.storage.repositories import SqliteStorage


MODEL_ID = "claude-opus-5"
PROVIDER = "ANTHROPIC"
QUALIFICATION_CAP_USD = Decimal("0.350000")


def _monthly_spend(storage: SqliteStorage, moment: datetime) -> Decimal:
    month = moment.strftime("%Y-%m-01 00:00:00")
    usage = storage.conn.execute(
        "SELECT coalesce(sum(estimated_cost_usd),0) FROM model_usage WHERE created_at>=?",
        (month,),
    ).fetchone()[0]
    qualification = storage.conn.execute(
        "SELECT coalesce(sum(cast(cost_usd AS REAL)),0) FROM model_qualification_runs "
        "WHERE executed_at>=?",
        (month,),
    ).fetchone()[0]
    return Decimal(str(usage)) + Decimal(str(qualification))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--confirm-live", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_live:
        print("BLOCKED: --confirm-live is required")
        return 2

    settings = load_settings()
    storage = SqliteStorage.open(settings.db_path)
    now = datetime.now(timezone.utc)
    try:
        active = storage.get_active_model_for_role(LogicalModelRole.ARTICLE_REVIEWER)
        if active is not None:
            capability = storage._model_capability_for(active)
            if (
                active.provider == PROVIDER
                and active.technical_model_id == MODEL_ID
                and capability is not None
                and capability.max_context_tokens is not None
                and capability.max_context_tokens >= 64_000
                and capability.max_output_tokens is not None
                and capability.max_output_tokens >= 16_384
            ):
                print(json.dumps({
                    "status": "ALREADY_ACTIVE",
                    "role": LogicalModelRole.ARTICLE_REVIEWER.value,
                    "provider": active.provider,
                    "model_id": active.technical_model_id,
                    "capability_ref": active.capability_ref,
                }, sort_keys=True))
                return 0

        model = storage.conn.execute(
            "SELECT * FROM model_registry WHERE provider=? AND technical_model_id=?",
            (PROVIDER, MODEL_ID),
        ).fetchone()
        if model is None:
            print("BLOCKED: exact Opus registry entry is missing")
            return 2
        available = Decimal(str(settings.max_monthly_cost_usd)) - _monthly_spend(storage, now)
        if available < QUALIFICATION_CAP_USD:
            print("BLOCKED: monthly budget cannot cover the qualification cap")
            return 2

        suffix = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        approval = QualificationApproval(
            approval_ref=f"article-reviewer-qualification-approval-{suffix}",
            request_id=f"article-reviewer-qualification-request-{suffix}",
            logical_role=LogicalModelRole.ARTICLE_REVIEWER,
            model_registry_id=str(model["registry_id"]),
            provider=PROVIDER,
            technical_model_id=MODEL_ID,
            pricing_ref=str(model["pricing_ref"]),
            max_input_tokens=CONTRACT.max_input_tokens,
            max_output_tokens=CONTRACT.max_output_tokens,
            cap_usd=QUALIFICATION_CAP_USD,
            approved_by=args.approved_by,
            approved_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=30)).isoformat(),
        )
        storage.record_model_qualification_approval(approval, now=now)
        outcome = execute_opus_article_reviewer_production_qualification(
            storage,
            approval,
            api_key_provider=lambda: settings.anthropic_api_key,
            now=now,
        )
        payload = outcome.payload()
        payload["provider_request_id"] = storage.conn.execute(
            "SELECT json_extract(result_json,'$.provider_request_id') "
            "FROM model_qualification_runs WHERE request_id=?",
            (approval.request_id,),
        ).fetchone()[0]
        if outcome.outcome != "PASS":
            print(json.dumps({"status": "QUALIFICATION_FAILED", **payload}, sort_keys=True))
            return 3

        binding = activate_and_bind_exact_role(
            storage,
            ExactRoleActivationRequest(
                role=LogicalModelRole.ARTICLE_REVIEWER,
                intent_kind="article_reviewer_provider",
                intent_id=f"article-reviewer-activation-{suffix}",
                reason="owner-authorized ARTICLE_REVIEWER live qualification PASS at 64k/16k",
            ),
            now=now,
        )
        print(json.dumps({
            "status": "ACTIVE",
            "qualification": payload,
            "binding": asdict(binding),
        }, sort_keys=True, default=str))
        return 0
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
