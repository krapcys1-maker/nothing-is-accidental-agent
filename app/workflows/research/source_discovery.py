"""Durable worker workflow for ARTICLE_RESEARCH A1."""
from __future__ import annotations

from uuid import uuid4

from app.core.clock import Clock
from app.core.config import Settings
from app.llm.usage_tracker import UsageTracker
from app.models import JobExecutionContext, ResearchJobExecution, Topic
from app.ports.source_discovery import SourceDiscoveryPort, SourceDiscoveryRequest
from app.research.source_discovery_intent import SourceDiscoveryIntent
from app.workflows.research.pipeline import ResearchRunSummary


def run_typed_source_discovery(
    account: object,
    topic: Topic,
    *,
    settings: Settings,
    storage: object,
    clock: Clock,
    job_execution: ResearchJobExecution,
    intent: SourceDiscoveryIntent,
    port: SourceDiscoveryPort,
) -> ResearchRunSummary:
    initialized = storage.initialize_source_discovery_run_for_job(
        job_execution.job_id, job_execution.lease_owner,
        f"source-discovery-run-{uuid4()}", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_execution.job_id,
        lease_owner=job_execution.lease_owner,
        run_id=initialized.run.id,
        clock=clock,
    )
    attempt = storage.begin_provider_attempt(
        execution,
        stage="research_discover",
        attempt_no=1,
        max_cost_usd=float(intent.cap_usd),
        daily_limit_usd=settings.max_daily_cost_usd,
        monthly_limit_usd=settings.max_monthly_cost_usd,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    response = port.discover(SourceDiscoveryRequest(
        account_id=intent.account_id,
        topic_id=intent.topic_id,
        research_run_id=initialized.run.id,
        query=topic.question or topic.title,
        max_results=intent.max_results,
    ))
    if response.returned_model_id != intent.model:
        storage.mark_provider_attempt_needs_reconciliation(
            execution, attempt.request_id, error_code="SOURCE_DISCOVERY_MODEL_MISMATCH",
        )
        raise ValueError("source-discovery provider returned a different model")
    # Provider metadata may use its own request id, but the financial ledger is
    # always keyed by the durable pre-call identity.
    UsageTracker(settings, storage).record_job(
        execution, intent.model, response.usage,
        task="research_discover", dry_run=False, request_id=attempt.request_id,
    )
    stored = storage.finalize_source_discovery_success(
        execution, candidates=response.candidates, port_name=response.port_name,
    )
    summary = ResearchRunSummary(
        run_id=initialized.run.id,
        account_id=intent.account_id,
        topic_id=intent.topic_id,
        dry_run=False,
    )
    summary.candidates_discovered = len(stored)
    summary.model = intent.model
    summary.input_tokens = response.usage.input_tokens
    summary.output_tokens = response.usage.output_tokens
    summary.web_search_requests = response.usage.web_search_requests
    row = storage.conn.execute(
        "SELECT cost_usd FROM runs WHERE id=?", (initialized.run.id,),
    ).fetchone()
    summary.cost_usd = float(row[0])
    return summary
