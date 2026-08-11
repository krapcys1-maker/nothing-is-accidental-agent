"""One explicit production composition root for a controlled paid ARTICLE.

Nothing in the ordinary worker imports or enables this root. The caller must
name a durable job, a one-shot owner authority, an expiry and a positive cost
ceiling. The existing storage approval, dispatcher policy, writer lifecycle,
provenance and canonical settlement remain the only path to the transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from app.content.contracts import WriterLimits
from app.content.cost_estimate import (
    ARTICLE_WRITER_MAX_CONTEXT_TOKENS,
    ARTICLE_WRITER_MAX_INPUT_TOKENS,
    ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
)
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentType,
)
from app.content.reviewer import ProductionArticleReviewer
from app.content.writer import (
    ProductionArticleWriter,
)
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.money import decimal_from, quantize_usd
from app.llm.anthropic_controlled_adapter import (
    ControlledSdkFactory,
    ControlledTechnicalCaller,
)
from app.llm.anthropic_provider_contract import OPUS_5_MODEL_ID
from app.model_routing.contracts import LogicalModelRole, ModelFamily
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationResult
from app.storage.repositories import SqliteStorage


@dataclass(frozen=True)
class ControlledArticleAuthority:
    job_id: str
    approval_ref: str
    approved_by: str
    approved_at: str
    expires_at: str
    cost_ceiling_usd: Decimal | str


@dataclass(frozen=True)
class ControlledArticleEntrypointResult:
    content_id: int
    job_id: str
    worker: WorkerIterationResult


def run_controlled_article(
    *,
    settings: Settings,
    account_id: str,
    research_card_id: int,
    idempotency_key: str,
    authority: ControlledArticleAuthority,
    api_key_provider: Callable[[], str | None] | None = None,
    sdk_factory: ControlledSdkFactory | None = None,
    caller: ControlledTechnicalCaller | None = None,
    reviewer_sdk_factory: ControlledSdkFactory | None = None,
    reviewer_caller: ControlledTechnicalCaller | None = None,
    clock: Clock | None = None,
    lease_owner: str | None = None,
    timeout_seconds: float = 30.0,
) -> ControlledArticleEntrypointResult:
    """Execute one targeted controlled ARTICLE; never scan/unlock the queue."""
    clock = clock or SystemClock()
    cap = decimal_from(authority.cost_ceiling_usd, label="ARTICLE cost ceiling")
    if cap <= Decimal("0"):
        raise ValueError("Controlled ARTICLE requires a positive cost ceiling.")
    if not authority.job_id.strip() or not authority.approval_ref.strip():
        raise ValueError("Controlled ARTICLE authority requires job and approval refs.")
    storage = SqliteStorage.open(settings.db_path)
    try:
        prepared = storage.prepare_content_job(
            ContentPreparationRequest(
                job_id=authority.job_id,
                idempotency_key=idempotency_key,
                account_id=account_id,
                research_card_id=research_card_id,
                content_type=ContentType.ARTICLE,
                execution_mode=ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE,
                prompt_version="controlled_article_prompt_v1",
                style_guide_version="ARTICLE_STYLE_PROFILE_V1",
            ),
            clock=clock,
        )
        binding = storage.freeze_content_writer_model_binding(
            job_id=authority.job_id,
            content_type=ContentType.ARTICLE,
            now=clock.now(),
        )
        if (
            binding.role is not LogicalModelRole.ARTICLE_WRITER
            or binding.family is not ModelFamily.OPUS
            or binding.technical_model_id != OPUS_5_MODEL_ID
            or binding.fallback_policy != "FORBIDDEN"
        ):
            raise ValueError(
                "Controlled ARTICLE authority requires exact OPUS / claude-opus-5 "
                "with fallback FORBIDDEN."
            )
        storage.record_content_provider_approval(
            approval_ref=authority.approval_ref,
            job_id=authority.job_id,
            account_id=account_id,
            role=LogicalModelRole.ARTICLE_WRITER,
            model_registry_id=binding.model_registry_id,
            provider=binding.provider,
            technical_model_id=binding.technical_model_id,
            pricing_ref=binding.pricing_ref,
            max_output_tokens=ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
            cap_usd=cap,
            approved_by=authority.approved_by,
            approved_at=authority.approved_at,
            expires_at=authority.expires_at,
            retention_acceptance_ref=None,
        )
        provenance = storage.load_controlled_provider_provenance(
            job_id=authority.job_id,
        )
        pricing = provenance.pricing
        if pricing is None or pricing.prices is None:
            raise ValueError("Controlled ARTICLE writer has no verified pricing.")
        dimensions = pricing.prices.as_decimal_mapping()
        writer_attempt_envelope = quantize_usd(
            (
                Decimal(ARTICLE_WRITER_MAX_INPUT_TOKENS)
                / Decimal("1000000")
                * dimensions["input_per_mtok"]
                + Decimal(ARTICLE_WRITER_MAX_OUTPUT_TOKENS)
                / Decimal("1000000")
                * dimensions["output_per_mtok"]
            ),
            label="ARTICLE writer attempt envelope",
        )
        writer = ProductionArticleWriter(
            api_key_provider=(
                api_key_provider
                if api_key_provider is not None
                else lambda: settings.anthropic_api_key
            ),
            article_limits=WriterLimits(
                max_input_tokens=ARTICLE_WRITER_MAX_INPUT_TOKENS,
                max_context_tokens=ARTICLE_WRITER_MAX_CONTEXT_TOKENS,
                max_output_tokens=ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
                max_cost_usd=float(writer_attempt_envelope),
                timeout_seconds=timeout_seconds,
            ),
            sdk_factory=sdk_factory,
            caller=caller,
        )
        # The independent reviewer is composed here, from the same secret
        # boundary and the same frozen-authority rules as the writer.  It binds
        # ARTICLE_REVIEWER separately, so a paid review can never inherit the
        # writer's authority, and it draws down the one job-scoped ARTICLE cap.
        storage.freeze_content_role_model_binding(
            job_id=authority.job_id,
            role=LogicalModelRole.ARTICLE_REVIEWER,
            now=clock.now(),
        )
        reviewer = ProductionArticleReviewer(
            storage=storage,
            job_id=authority.job_id,
            api_key_provider=(
                api_key_provider
                if api_key_provider is not None
                else lambda: settings.anthropic_api_key
            ),
            sdk_factory=reviewer_sdk_factory,
            caller=reviewer_caller,
            timeout_seconds=timeout_seconds,
            daily_limit_usd=settings.max_daily_cost_usd,
            monthly_limit_usd=settings.max_monthly_cost_usd,
        )
        policy = PolicyEngine(settings, storage, clock)
        dispatcher = JobDispatcher(
            settings=settings,
            storage=storage,
            policy=policy,
            clock=clock,
            allow_real_research=False,
            allow_real_topic_generation=False,
            content_writer=writer,
            content_claim_reviewer=reviewer,
            allow_paid_content=True,
        )
        owner = lease_owner or f"controlled-article:{authority.job_id}"
        worker = Worker(
            storage=storage,
            policy=policy,
            dispatcher=dispatcher,
            lease_owner=owner,
            target_job_id=authority.job_id,
            lease_seconds=60,
            heartbeat_interval_seconds=20.0,
            heartbeat_startup_timeout_seconds=5.0,
            heartbeat_shutdown_timeout_seconds=5.0,
            heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
            clock=clock,
        )
        result = worker.run_once()
        return ControlledArticleEntrypointResult(
            content_id=prepared.content.id,
            job_id=authority.job_id,
            worker=result,
        )
    finally:
        storage.close()
