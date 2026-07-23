"""Resumable WAVE C2 pipeline: frozen Research Card -> PENDING_APPROVAL."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.content.contracts import (
    ArticleBrief,
    ContentBrief,
    ContentPlan,
    DraftEvaluation,
    FakeDraft,
    NoteBrief,
    PipelineDecision,
    WriterIntent,
)
from app.content.evaluations import aggregate_decision, evaluate_draft
from app.content.foundation import (
    CONTENT_PROVIDER_STAGE,
    ContentExecutionMode,
    ContentStatus,
    ContentType,
    canonicalize_content_job_payload,
)
from app.content.planner import ContentPlanningBlocked, plan_content
from app.content.routing import ContentRoutingError, default_content_routing_path, load_content_route
from app.content.writer import FakeContentWriter, WriterPort, WriterRequest
from app.core.clock import Clock
from app.models import (
    Job,
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    ProviderAttemptStatus,
)
from app.ports.storage import StoragePort


@dataclass(frozen=True)
class ContentPipelineSummary:
    job_id: str
    run_id: str
    content_id: int
    status: ContentStatus
    attempts: int
    evaluation_count: int
    cost_usd: float
    block_code: str | None = None


def _profile_text(project_root: Path, name: str) -> str:
    path = project_root / "instrukcja dla pisania artykulow" / name
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ContentRoutingError(f"Derived style profile is empty: {name}.")
    return text


def _brief_from_json(content_type: ContentType, value: str) -> ContentBrief:
    raw = json.loads(value)
    if content_type is ContentType.ARTICLE:
        return ArticleBrief.model_validate(raw)
    return NoteBrief.model_validate(raw)


def _draft_from_row(row: dict[str, object]) -> FakeDraft:
    return FakeDraft.model_validate(json.loads(str(row["draft_json"])))


def _evaluation_from_row(row: dict[str, object]) -> DraftEvaluation:
    return DraftEvaluation(
        evaluation_type=str(row["evaluation_type"]),
        evaluator_version=str(row["evaluator_version"]),
        result=str(row["result"]),
        score=row["score"],
        findings=tuple(json.loads(str(row["findings_json"]))),
        draft_fingerprint=str(row["draft_fingerprint"]),
        decision=str(row["decision"]),
    )


def _summary(storage: StoragePort, job_id: str, block_code: str | None = None) -> ContentPipelineSummary:
    state = storage.get_content_pipeline_state(job_id)
    job = state["job"]
    content = state["content"]
    assert isinstance(job, dict) and isinstance(content, dict)
    run_id = str(job["run_id"])
    run = storage.get_run(run_id)
    return ContentPipelineSummary(
        job_id=job_id,
        run_id=run_id,
        content_id=int(content["id"]),
        status=ContentStatus(str(content["status"])),
        attempts=len(state["attempts"]),
        evaluation_count=len(state["evaluations"]),
        cost_usd=0.0 if run is None else float(run.cost_usd),
        block_code=block_code,
    )


def run_offline_content_pipeline(
    job: Job,
    *,
    storage: StoragePort,
    clock: Clock,
    lease_owner: str,
    project_root: Path,
    writer: WriterPort | None = None,
    fault_point: Callable[[str], None] | None = None,
) -> ContentPipelineSummary:
    """Resume from durable checkpoints and perform no network/API operation."""
    if job.kind is not JobKind.CONTENT:
        raise ValueError("Offline content pipeline requires a CONTENT job.")
    payload = canonicalize_content_job_payload(job.payload)
    if payload["execution_mode"] != ContentExecutionMode.OFFLINE_PIPELINE.value:
        raise ValueError("Dispatcher admits only OFFLINE_PIPELINE content jobs.")
    if job.status not in (JobStatus.LEASED, JobStatus.RUNNING):
        raise ValueError("Content job must be leased before pipeline execution.")
    run_id = job.run_id or f"content-run:{job.id}"
    initialized = storage.initialize_content_run_for_job(
        job.id,
        lease_owner,
        job.execution_generation,
        run_id,
        clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job.id,
        lease_owner=lease_owner,
        run_id=run_id,
        clock=clock,
        fence_token=job.execution_generation,
        kind=JobKind.CONTENT,
        workflow=job.workflow,
    )
    frozen = initialized.frozen_input
    writer = writer or FakeContentWriter()

    try:
        route = load_content_route(
            default_content_routing_path(project_root), frozen.content_type,
        )
        planned = plan_content(frozen, route)
    except (ContentPlanningBlocked, ContentRoutingError, OSError) as exc:
        code = getattr(exc, "code", "CONTENT_CONFIGURATION_BLOCKED")
        storage.transition_content_execution(
            execution, ContentStatus.FAILED, reason_code=str(code),
            final_result={"mode": "FAKE_OFFLINE_C2", "blocked": True},
        )
        return _summary(storage, job.id, str(code))

    plan_fingerprint = storage.record_content_plan(execution, planned.plan)
    brief_payload = planned.brief.model_dump(mode="json")
    brief_sha256 = storage.record_content_article_brief(
        execution,
        brief_schema_version=planned.brief.schema_version,
        brief=brief_payload,
    )
    if fault_point is not None:
        fault_point("BRIEF_PERSISTED")
    state = storage.get_content_pipeline_state(job.id)
    plan_row = state["plan"]
    brief_row = state["brief"]
    assert isinstance(plan_row, dict) and isinstance(brief_row, dict)
    persisted_plan = ContentPlan.model_validate(json.loads(str(plan_row["plan_json"])))
    if persisted_plan.fingerprint() != plan_fingerprint:
        raise RuntimeError("Persisted content plan fingerprint drifted.")
    brief = _brief_from_json(frozen.content_type, str(brief_row["brief_json"]))

    style_name = (
        "ARTICLE_STYLE_PROFILE_V1.md"
        if frozen.content_type is ContentType.ARTICLE
        else "NOTES_STYLE_PROFILE_V1.md"
    )
    style_profile = _profile_text(project_root, style_name)
    negative_profile = _profile_text(
        project_root, "ARTICLE_NEGATIVE_STYLE_PROFILE_V1.md",
    )

    prior_draft: FakeDraft | None = None
    prior_feedback: tuple[dict[str, object], ...] = ()
    for attempt_no in (1, 2):
        state = storage.get_content_pipeline_state(job.id)
        content_row = state["content"]
        assert isinstance(content_row, dict)
        if ContentStatus(str(content_row["status"])) in (
            ContentStatus.PENDING_APPROVAL,
            ContentStatus.FAILED,
            ContentStatus.NEEDS_VERIFICATION,
        ):
            return _summary(storage, job.id)

        persisted_drafts = {
            int(row["attempt_no"]): row
            for row in state["drafts"]
            if isinstance(row, dict)
        }
        persisted_evaluations = {
            int(row["attempt_no"]): []
            for row in state["evaluations"]
            if isinstance(row, dict)
        }
        for row in state["evaluations"]:
            if isinstance(row, dict):
                persisted_evaluations.setdefault(int(row["attempt_no"]), []).append(row)

        if attempt_no == 2 and prior_draft is None:
            first = persisted_drafts.get(1)
            if first is None:
                raise RuntimeError("Second writer attempt lacks durable first draft.")
            prior_draft = _draft_from_row(first)
            first_evals = tuple(
                _evaluation_from_row(row)
                for row in persisted_evaluations.get(1, [])
            )
            if len(first_evals) != 9 or aggregate_decision(first_evals) is not PipelineDecision.REWRITE_ONCE:
                raise RuntimeError("Second writer attempt lacks a durable rewrite decision.")
            prior_feedback = tuple(
                finding
                for evaluation in first_evals
                if evaluation.decision is PipelineDecision.REWRITE_ONCE
                for finding in evaluation.findings
            )

        intent = WriterIntent(
            intent_id=f"{job.id}:writer:{attempt_no}",
            job_id=job.id,
            run_id=run_id,
            content_id=frozen.content_id,
            account_id=frozen.account_id,
            content_type=frozen.content_type,
            attempt_no=attempt_no,
            route=route,
            plan_fingerprint=plan_fingerprint,
            brief_sha256=brief_sha256,
            frozen_input_sha256=frozen.input_sha256,
            evidence_manifest_sha256=frozen.evidence_manifest_sha256,
            style_profile_id=brief.style_profile_id,
            negative_style_profile_id=brief.negative_style_profile_id,
            rewrite_of_draft_fingerprint=(
                None if prior_draft is None else prior_draft.fingerprint()
            ),
            rewrite_feedback=prior_feedback,
        )
        storage.record_content_writer_intent(execution, intent)
        attempt = storage.begin_fake_content_writer_attempt(execution, attempt_no)
        request_id = attempt.request_id

        draft_row = persisted_drafts.get(attempt_no)
        if draft_row is None:
            attempt = storage.mark_fake_content_writer_started(execution, request_id)
            if fault_point is not None:
                fault_point("WRITER_ATTEMPT_STARTED")
            request = WriterRequest(
                intent=intent,
                brief=brief,
                frozen_evidence=frozen.evidence_items,
                style_profile=style_profile,
                negative_style_profile=negative_profile,
                brand_policy=brief.brand_topic_policy,
                max_words=brief.max_words,
            )
            draft = writer.write(request)
            if attempt.status is not ProviderAttemptStatus.SETTLED:
                storage.add_job_model_usage(
                    execution,
                    ModelUsage(
                        run_id=run_id,
                        provider="fake-content-writer",
                        model=route.route_key,
                        task=CONTENT_PROVIDER_STAGE,
                        input_tokens=0,
                        output_tokens=0,
                        estimated_cost_usd=0.0,
                        dry_run=True,
                        request_id=request_id,
                        created_at=clock.now(),
                    ),
                )
            draft_id = storage.record_content_draft(execution, intent, draft)
            if fault_point is not None:
                fault_point("DRAFT_PERSISTED")
        else:
            draft = _draft_from_row(draft_row)
            draft_id = int(draft_row["id"])

        evaluation_rows = persisted_evaluations.get(attempt_no, [])
        if len(evaluation_rows) == 9:
            evaluations = tuple(_evaluation_from_row(row) for row in evaluation_rows)
        else:
            evaluations = evaluate_draft(draft, brief)
            for evaluation in evaluations:
                storage.record_content_draft_evaluation(
                    execution,
                    draft_id=draft_id,
                    attempt_no=attempt_no,
                    evaluation=evaluation,
                )
        decision = aggregate_decision(evaluations)
        if decision is PipelineDecision.PASS:
            state = storage.get_content_pipeline_state(job.id)
            current_content = state["content"]
            assert isinstance(current_content, dict)
            if current_content["status"] == ContentStatus.REVISE.value:
                storage.transition_content_execution(execution, ContentStatus.RUNNING)
            storage.finalize_content_draft(
                execution, draft_fingerprint=draft.fingerprint(),
            )
            return _summary(storage, job.id)
        if decision is PipelineDecision.BLOCK:
            storage.transition_content_execution(
                execution,
                ContentStatus.FAILED,
                reason_code="CONTENT_EVALUATION_BLOCKED",
                final_result={
                    "attempt_no": attempt_no,
                    "draft_fingerprint": draft.fingerprint(),
                    "mode": "FAKE_OFFLINE_C2",
                },
            )
            return _summary(storage, job.id, "CONTENT_EVALUATION_BLOCKED")
        if attempt_no == 2:
            storage.transition_content_execution(
                execution,
                ContentStatus.FAILED,
                reason_code="CONTENT_REWRITE_LIMIT_EXHAUSTED",
                final_result={
                    "attempt_no": 2,
                    "draft_fingerprint": draft.fingerprint(),
                    "mode": "FAKE_OFFLINE_C2",
                },
            )
            return _summary(storage, job.id, "CONTENT_REWRITE_LIMIT_EXHAUSTED")
        state = storage.get_content_pipeline_state(job.id)
        current_content = state["content"]
        assert isinstance(current_content, dict)
        if current_content["status"] == ContentStatus.RUNNING.value:
            storage.transition_content_execution(
                execution,
                ContentStatus.REVISE,
                reason_code="CONTENT_REWRITE_REQUIRED",
                final_result={
                    "attempt_no": 1,
                    "draft_fingerprint": draft.fingerprint(),
                    "mode": "FAKE_OFFLINE_C2",
                },
            )
            if fault_point is not None:
                fault_point("REWRITE_DECISION_PERSISTED")
        prior_draft = draft
        prior_feedback = tuple(
            finding
            for evaluation in evaluations
            if evaluation.decision is PipelineDecision.REWRITE_ONCE
            for finding in evaluation.findings
        )

    raise AssertionError("Closed C2 attempt loop exhausted without terminalization.")
