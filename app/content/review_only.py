"""One owner-approved REVIEW-ONLY chain over an existing terminal draft.

The initial reviewer is independent of the closed job.  When it requests one
rewrite, a narrowly authorised session reopens that exact CONTENT lifecycle and
hands control to the canonical writer pipeline at attempt 2.  No code in this
module can construct topic, research, fetch, writer attempt 1, publication or
Substack work.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Callable

from app.content.contracts import ArticleBrief, FakeDraft, PipelineDecision, WriterLimits
from app.content.cost_estimate import (
    ARTICLE_WRITER_MAX_CONTEXT_TOKENS,
    ARTICLE_WRITER_MAX_INPUT_TOKENS,
    ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
)
from app.content.foundation import ContentStatus, ContentType
from app.content.pipeline import run_offline_content_pipeline
from app.content.quality_gate import (
    ClaimAccountingEntry,
    ClaimAccountingReviewPort,
    ClaimReviewOutcome,
    DraftClaimSegment,
    build_claim_segments,
)
from app.content.reviewer import (
    ProductionArticleReviewer,
    REVIEWER_VERSION,
    ReviewerRequestIntent,
    assemble_reviewer_prompt,
    parse_reviewer_response,
)
from app.content.writer import ProductionArticleWriter
from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.money import decimal_from, quantize_usd
from app.llm.anthropic_controlled_adapter import (
    ControlledSdkFactory,
    ControlledTechnicalCaller,
)
from app.llm.anthropic_provider_contract import OPUS_5_MODEL_ID
from app.model_routing.contracts import LogicalModelRole, ModelFamily
from app.models import JobExecutionContext, JobKind
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import BudgetReservationError
from app.storage.db import RUNTIME_SCHEMA_VERSION, connection_schema_versions
from app.storage.repositories import SqliteStorage


class ReviewOnlyError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReviewOnlyAuthority:
    job_id: str
    content_id: int
    draft_fingerprint: str
    approval_ref: str
    initial_review_execution_ref: str
    writer_execution_ref: str
    post_review_execution_ref: str
    approved_by: str
    approved_at: str
    expires_at: str
    cost_ceiling_usd: Decimal | str


@dataclass(frozen=True)
class ReviewOnlyResult:
    job_id: str
    run_id: str
    content_id: int
    final_status: ContentStatus
    decision: PipelineDecision
    approval_ref: str
    initial_review_execution_ref: str
    writer_execution_ref: str
    post_review_execution_ref: str
    writer_attempt_no: int
    review_no: int
    draft_fingerprint: str
    writer_attempts: int
    reviews: int


def _authority_from_approval_row(row: dict[str, object]) -> ReviewOnlyAuthority:
    """Reconstruct the exact operator authority from its immutable SQLite row."""
    return ReviewOnlyAuthority(
        job_id=str(row["job_id"]),
        content_id=int(row["content_id"]),
        draft_fingerprint=str(row["source_draft_fingerprint"]),
        approval_ref=str(row["approval_ref"]),
        initial_review_execution_ref=str(row["initial_review_execution_ref"]),
        writer_execution_ref=str(row["writer_execution_ref"]),
        post_review_execution_ref=str(row["post_review_execution_ref"]),
        approved_by=str(row["approved_by"]),
        approved_at=str(row["approved_at"]),
        expires_at=str(row["expires_at"]),
        cost_ceiling_usd=str(row["chain_cap_usd"]),
    )


def load_review_only_authority(
    *, settings: Settings, approval_ref: str,
) -> ReviewOnlyAuthority | None:
    """Load one existing approval without deriving new timestamps or fields."""
    storage = SqliteStorage.open(settings.db_path)
    try:
        row = storage.get_content_review_resume_approval(approval_ref=approval_ref)
        return None if row is None else _authority_from_approval_row(row)
    finally:
        storage.close()


def _assert_authority_matches_persisted(
    supplied: ReviewOnlyAuthority, persisted: ReviewOnlyAuthority,
) -> None:
    """Refuse any attempt to retarget or extend an existing approval."""
    supplied_payload = {
        **supplied.__dict__,
        "cost_ceiling_usd": format(
            decimal_from(supplied.cost_ceiling_usd, label="REVIEW-ONLY chain ceiling"),
            ".6f",
        ),
    }
    persisted_payload = {
        **persisted.__dict__,
        "cost_ceiling_usd": format(
            decimal_from(persisted.cost_ceiling_usd, label="REVIEW-ONLY chain ceiling"),
            ".6f",
        ),
    }
    if supplied_payload != persisted_payload:
        raise ReviewOnlyError(
            "REVIEW_ONLY_APPROVAL_CONTRACT_MISMATCH",
            "Resume arguments differ from the immutable SQLite approval.",
        )


def _review_intent(
    *,
    execution_ref: str,
    job_id: str,
    run_id: str,
    content_id: int,
    draft: FakeDraft,
    review_no: int,
    brief: ArticleBrief,
    evidence: tuple[object, ...],
    segments: tuple[DraftClaimSegment, ...],
) -> ReviewerRequestIntent:
    prompt = assemble_reviewer_prompt(
        draft_fingerprint=draft.fingerprint(),
        brief=brief,
        evidence=evidence,
        segments=segments,
        lineage={"job_id": job_id, "run_id": run_id, "content_id": content_id},
    )
    return ReviewerRequestIntent(
        execution_ref=execution_ref,
        job_id=job_id,
        run_id=run_id,
        content_id=content_id,
        draft_fingerprint=draft.fingerprint(),
        writer_attempt_no=draft.attempt_no,
        review_no=review_no,
        prompt_fingerprint=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


def _entries_from_execution(
    row: dict[str, object], *, segments: tuple[DraftClaimSegment, ...],
    evidence_ids: frozenset[str], expected_intent: ReviewerRequestIntent,
) -> tuple[ClaimAccountingEntry, ...]:
    if row["request_intent_fingerprint"] != expected_intent.fingerprint():
        raise ReviewOnlyError(
            "REVIEW_ONLY_DURABLE_INTENT_MISMATCH",
            "Persisted reviewer intent differs from the exact resumed draft.",
        )
    if row["outcome"] != "SUCCESS":
        code = (
            "REVIEW_ONLY_REVIEW_RESULT_UNCERTAIN"
            if row["outcome"] in {"IN_FLIGHT", "NEEDS_VERIFICATION"}
            else "REVIEW_ONLY_REVIEW_FAILED"
        )
        raise ReviewOnlyError(code, f"Reviewer stage is {row['outcome']} and is not replayable.")
    payload = json.loads(str(row["result_json"]))
    entries = payload.get("entries")
    return parse_reviewer_response(
        json.dumps({"reviewer_version": REVIEWER_VERSION, "entries": entries}),
        segments=segments,
        allowed_evidence_ids=evidence_ids,
    )


def _review_once_or_resume(
    *,
    storage: SqliteStorage,
    settings: Settings,
    approval_ref: str,
    intent: ReviewerRequestIntent,
    draft: FakeDraft,
    brief: ArticleBrief,
    evidence: tuple[object, ...],
    segments: tuple[DraftClaimSegment, ...],
    api_key_provider: Callable[[], str | None],
    sdk_factory: ControlledSdkFactory | None,
    caller: ControlledTechnicalCaller | None,
    clock: Clock,
) -> tuple[ClaimAccountingEntry, ...]:
    existing = storage.get_content_review_resume_execution(
        execution_ref=intent.execution_ref,
    )
    if existing is not None:
        return _entries_from_execution(
            existing,
            segments=segments,
            evidence_ids=frozenset(item.confirmed_claim_id for item in evidence),
            expected_intent=intent,
        )
    reviewer = ProductionArticleReviewer(
        storage=storage,
        job_id=intent.job_id,
        api_key_provider=api_key_provider,
        sdk_factory=sdk_factory,
        caller=caller,
        timeout_seconds=300.0,
        daily_limit_usd=settings.max_daily_cost_usd,
        monthly_limit_usd=settings.max_monthly_cost_usd,
        resume_approval_ref=approval_ref,
        resume_intent=intent,
        clock=clock,
    )
    return reviewer.review(
        draft=draft, brief=brief, evidence=evidence, segments=segments,
    )


class _PostRewriteReview(ClaimAccountingReviewPort):
    reviewer_version = REVIEWER_VERSION

    def __init__(self, **kwargs: object) -> None:
        self._kwargs = kwargs

    def review(
        self, *, draft: FakeDraft, brief: ArticleBrief,
        evidence: tuple[object, ...], segments: tuple[DraftClaimSegment, ...],
    ) -> tuple[ClaimAccountingEntry, ...]:
        if draft.attempt_no != 2:
            raise ReviewOnlyError(
                "REVIEW_ONLY_POST_REVIEW_DRAFT_INVALID",
                "Post-rewrite reviewer accepts only canonical writer attempt 2.",
            )
        intent = _review_intent(
            execution_ref=str(self._kwargs["execution_ref"]),
            job_id=str(self._kwargs["job_id"]),
            run_id=str(self._kwargs["run_id"]),
            content_id=int(self._kwargs["content_id"]),
            draft=draft,
            review_no=2,
            brief=brief,
            evidence=evidence,
            segments=segments,
        )
        return _review_once_or_resume(
            storage=self._kwargs["storage"],
            settings=self._kwargs["settings"],
            approval_ref=str(self._kwargs["approval_ref"]),
            intent=intent,
            draft=draft,
            brief=brief,
            evidence=evidence,
            segments=segments,
            api_key_provider=self._kwargs["api_key_provider"],
            sdk_factory=self._kwargs["sdk_factory"],
            caller=self._kwargs["caller"],
            clock=self._kwargs["clock"],
        )


def _execution_context(
    storage: SqliteStorage, *, approval_ref: str, clock: Clock,
) -> JobExecutionContext:
    session = storage.get_content_review_resume_session(approval_ref=approval_ref)
    if session is None or session["status"] != "ACTIVE":
        raise ReviewOnlyError(
            "REVIEW_ONLY_SESSION_NOT_ACTIVE", "Canonical rewrite session is not active.",
        )
    return JobExecutionContext(
        job_id=str(session["job_id"]),
        lease_owner=str(session["lease_owner"]),
        run_id=str(session["run_id"]),
        clock=clock,
        fence_token=int(session["execution_generation"]),
        kind=JobKind.CONTENT,
        workflow=ContentType.ARTICLE,
    )


def _result_from_state(
    storage: SqliteStorage, authority: ReviewOnlyAuthority,
) -> ReviewOnlyResult:
    state = storage.get_content_pipeline_state(authority.job_id)
    content = state["content"]
    job = state["job"]
    assert isinstance(content, dict) and isinstance(job, dict)
    status = ContentStatus(str(content["status"]))
    drafts = [row for row in state["drafts"] if isinstance(row, dict)]
    if not drafts:
        raise ReviewOnlyError(
            "REVIEW_ONLY_RESULT_DRAFT_MISSING",
            "The durable result has no writer draft.",
        )
    latest_draft = max(drafts, key=lambda row: int(row["attempt_no"]))
    review_summary = storage.conn.execute(
        "SELECT count(*) AS review_count,MAX(review_no) AS latest_review "
        "FROM content_review_resume_executions WHERE content_id=?",
        (authority.content_id,),
    ).fetchone()
    assert review_summary is not None and review_summary["latest_review"] is not None
    return ReviewOnlyResult(
        job_id=authority.job_id,
        run_id=str(job["run_id"]),
        content_id=authority.content_id,
        final_status=status,
        decision=(PipelineDecision.PASS if status is ContentStatus.PENDING_APPROVAL
                  else PipelineDecision.BLOCK),
        approval_ref=authority.approval_ref,
        initial_review_execution_ref=authority.initial_review_execution_ref,
        writer_execution_ref=authority.writer_execution_ref,
        post_review_execution_ref=authority.post_review_execution_ref,
        writer_attempt_no=int(latest_draft["attempt_no"]),
        review_no=int(review_summary["latest_review"]),
        draft_fingerprint=str(latest_draft["draft_fingerprint"]),
        writer_attempts=len(state["attempts"]),
        reviews=int(review_summary["review_count"]),
    )


def run_controlled_article_review_only(
    *,
    settings: Settings,
    authority: ReviewOnlyAuthority,
    api_key_provider: Callable[[], str | None] | None = None,
    initial_reviewer_sdk_factory: ControlledSdkFactory | None = None,
    initial_reviewer_caller: ControlledTechnicalCaller | None = None,
    writer_sdk_factory: ControlledSdkFactory | None = None,
    writer_caller: ControlledTechnicalCaller | None = None,
    post_reviewer_sdk_factory: ControlledSdkFactory | None = None,
    post_reviewer_caller: ControlledTechnicalCaller | None = None,
    clock: Clock | None = None,
) -> ReviewOnlyResult:
    """Run or resume reviewer1 -> optional writer2 -> reviewer2 exactly once."""
    clock = clock or SystemClock()
    cap = decimal_from(authority.cost_ceiling_usd, label="REVIEW-ONLY chain ceiling")
    secret = api_key_provider or (lambda: settings.anthropic_api_key)
    storage = SqliteStorage.open(settings.db_path)
    try:
        versions = connection_schema_versions(storage.conn)
        if not versions or versions[-1] != RUNTIME_SCHEMA_VERSION:
            raise ReviewOnlyError(
                "REVIEW_ONLY_SCHEMA_NOT_READY",
                f"REVIEW-ONLY requires {RUNTIME_SCHEMA_VERSION}; observed "
                f"{versions[-1] if versions else 'none'}.",
            )
        session = storage.get_content_review_resume_session(
            approval_ref=authority.approval_ref,
        )
        persisted_approval = storage.get_content_review_resume_approval(
            approval_ref=authority.approval_ref,
        )
        if persisted_approval is not None:
            _assert_authority_matches_persisted(
                authority, _authority_from_approval_row(persisted_approval),
            )
        if session is not None and session["status"] != "ACTIVE":
            return _result_from_state(storage, authority)
        exposure = storage.unresolved_provider_exposure()
        if exposure > Decimal("0"):
            raise ReviewOnlyError(
                "REVIEW_ONLY_RECONCILIATION_REQUIRED",
                f"Unresolved provider exposure is {exposure:.6f} USD; external "
                "provider reconciliation by a human is required before review.",
            )
        state = storage.get_content_pipeline_state(authority.job_id)
        job = state["job"]
        content = state["content"]
        if not isinstance(job, dict) or not isinstance(content, dict):
            raise ReviewOnlyError("REVIEW_ONLY_LINEAGE_INVALID", "Job/content is missing.")
        if int(content["id"]) != authority.content_id:
            raise ReviewOnlyError("REVIEW_ONLY_CONTENT_MISMATCH", "Explicit content ID differs.")
        if session is None and str(content["status"]) not in {"FAILED", "NEEDS_VERIFICATION"}:
            raise ReviewOnlyError(
                "REVIEW_ONLY_DRAFT_NOT_TERMINAL", "Initial resume requires terminal content.",
            )
        if content.get("published_at") is not None or content.get("external_url") is not None:
            raise ReviewOnlyError("REVIEW_ONLY_PUBLICATION_FORBIDDEN", "Published content is out of scope.")
        active_other = storage.conn.execute(
            "SELECT count(*) FROM jobs WHERE status IN ('QUEUED','LEASED','RUNNING') AND id!=?",
            (authority.job_id,),
        ).fetchone()[0]
        if active_other:
            raise ReviewOnlyError("REVIEW_ONLY_ACTIVE_WORK_PRESENT", "Another active job exists.")
        drafts = [row for row in state["drafts"] if isinstance(row, dict)]
        first = next((row for row in drafts if int(row["attempt_no"]) == 1), None)
        if first is None or first["draft_fingerprint"] != authority.draft_fingerprint:
            raise ReviewOnlyError("REVIEW_ONLY_DRAFT_MISMATCH", "Exact attempt-1 draft is absent.")
        draft1 = FakeDraft.model_validate(json.loads(str(first["draft_json"])))
        if draft1.fingerprint() != authority.draft_fingerprint:
            raise ReviewOnlyError("REVIEW_ONLY_DRAFT_HASH_INVALID", "Stored draft preimage drifted.")
        if authority.writer_execution_ref != f"{authority.job_id}:content_draft:2":
            raise ReviewOnlyError(
                "REVIEW_ONLY_WRITER_IDENTITY_INVALID",
                "Writer execution ref must be the canonical attempt-2 request identity.",
            )
        brief_row = state["brief"]
        if not isinstance(brief_row, dict):
            raise ReviewOnlyError("REVIEW_ONLY_BRIEF_MISSING", "Article brief is missing.")
        brief = ArticleBrief.model_validate(json.loads(str(brief_row["brief_json"])))
        frozen = storage.assert_content_snapshot(str(content["account_id"]), authority.content_id)
        research_card = json.loads(frozen.research_card_snapshot_json)

        writer_binding = storage.freeze_content_writer_model_binding(
            job_id=authority.job_id, content_type=ContentType.ARTICLE, now=clock.now(),
        )
        reviewer_binding = storage.freeze_content_role_model_binding(
            job_id=authority.job_id, role=LogicalModelRole.ARTICLE_REVIEWER, now=clock.now(),
        )
        if (
            writer_binding.family is not ModelFamily.OPUS
            or reviewer_binding.family is not ModelFamily.OPUS
            or writer_binding.technical_model_id != OPUS_5_MODEL_ID
            or reviewer_binding.technical_model_id != OPUS_5_MODEL_ID
        ):
            raise ReviewOnlyError("REVIEW_ONLY_MODEL_BINDING_INVALID", "Exact Opus bindings are required.")
        provenance = storage.load_controlled_provider_provenance(job_id=authority.job_id)
        if provenance.pricing is None or provenance.pricing.prices is None:
            raise ReviewOnlyError("REVIEW_ONLY_WRITER_PRICING_MISSING", "Writer pricing is missing.")
        prices = provenance.pricing.prices.as_decimal_mapping()
        writer_envelope = quantize_usd(
            Decimal(ARTICLE_WRITER_MAX_INPUT_TOKENS) / Decimal("1000000") * prices["input_per_mtok"]
            + Decimal(ARTICLE_WRITER_MAX_OUTPUT_TOKENS) / Decimal("1000000") * prices["output_per_mtok"],
            label="Review-only writer envelope",
        )
        writer = ProductionArticleWriter(
            api_key_provider=secret,
            article_limits=WriterLimits(
                max_input_tokens=ARTICLE_WRITER_MAX_INPUT_TOKENS,
                max_context_tokens=ARTICLE_WRITER_MAX_CONTEXT_TOKENS,
                max_output_tokens=ARTICLE_WRITER_MAX_OUTPUT_TOKENS,
                max_cost_usd=float(writer_envelope),
                timeout_seconds=300.0,
            ),
            sdk_factory=writer_sdk_factory,
            caller=writer_caller,
        )
        probe_reviewer = ProductionArticleReviewer(
            storage=storage, job_id=authority.job_id, api_key_provider=secret,
            sdk_factory=initial_reviewer_sdk_factory, caller=initial_reviewer_caller,
            timeout_seconds=300.0, daily_limit_usd=settings.max_daily_cost_usd,
            monthly_limit_usd=settings.max_monthly_cost_usd, clock=clock,
        )
        reviewer_envelope = probe_reviewer.max_legal_cost(probe_reviewer._authority()[0])
        required_cap = quantize_usd(
            reviewer_envelope * 2 + writer_envelope, label="Review-only full chain",
        )
        if cap < required_cap:
            raise ReviewOnlyError(
                "REVIEW_ONLY_CHAIN_CAP_TOO_LOW",
                f"Full conditional chain requires {required_cap:.6f} USD.",
            )
        storage.record_content_review_resume_approval(
            approval_ref=authority.approval_ref,
            job_id=authority.job_id,
            run_id=str(content["run_id"]),
            content_id=authority.content_id,
            source_draft_fingerprint=authority.draft_fingerprint,
            initial_review_execution_ref=authority.initial_review_execution_ref,
            writer_execution_ref=authority.writer_execution_ref,
            post_review_execution_ref=authority.post_review_execution_ref,
            reviewer_provider=reviewer_binding.provider,
            reviewer_model_id=reviewer_binding.technical_model_id,
            writer_provider=writer_binding.provider,
            writer_model_id=writer_binding.technical_model_id,
            reviewer_max_output_tokens=8192,
            writer_max_output_tokens=8192,
            reviewer_max_cost_usd=reviewer_envelope,
            writer_max_cost_usd=writer_envelope,
            chain_cap_usd=cap,
            daily_limit_usd=settings.max_daily_cost_usd,
            monthly_limit_usd=settings.max_monthly_cost_usd,
            approved_by=authority.approved_by,
            approved_at=authority.approved_at,
            expires_at=authority.expires_at,
        )

        segments1 = build_claim_segments(draft1)
        initial_intent = _review_intent(
            execution_ref=authority.initial_review_execution_ref,
            job_id=authority.job_id,
            run_id=str(content["run_id"]),
            content_id=authority.content_id,
            draft=draft1,
            review_no=1,
            brief=brief,
            evidence=frozen.evidence_items,
            segments=segments1,
        )
        initial_entries = _review_once_or_resume(
            storage=storage, settings=settings, approval_ref=authority.approval_ref,
            intent=initial_intent, draft=draft1, brief=brief,
            evidence=frozen.evidence_items, segments=segments1,
            api_key_provider=secret, sdk_factory=initial_reviewer_sdk_factory,
            caller=initial_reviewer_caller, clock=clock,
        )

        session = storage.begin_content_review_resume_session(
            approval_ref=authority.approval_ref,
            lease_owner=f"review-only:{authority.approval_ref}",
            lease_seconds=1800,
            now=clock.now(),
        )
        execution = _execution_context(storage, approval_ref=authority.approval_ref, clock=clock)
        policy = PolicyEngine(settings, storage, clock)
        initial_approved = all(
            entry.outcome is ClaimReviewOutcome.PASS for entry in initial_entries
        )
        if initial_approved:
            storage.finalize_content_review_resume_approval(
                execution,
                approval_ref=authority.approval_ref,
                draft_fingerprint=draft1.fingerprint(),
            )
            storage.settle_content_review_resume_session(
                approval_ref=authority.approval_ref, now=clock.now(),
            )
            return _result_from_state(storage, authority)
        storage.transition_content_execution(
            execution, ContentStatus.REVISE,
            reason_code="CONTENT_REWRITE_REQUIRED",
            final_result={"attempt_no": 1, "draft_fingerprint": draft1.fingerprint()},
        )
        post_reviewer = _PostRewriteReview(
            storage=storage, settings=settings, approval_ref=authority.approval_ref,
            execution_ref=authority.post_review_execution_ref,
            job_id=authority.job_id, run_id=str(content["run_id"]),
            content_id=authority.content_id, api_key_provider=secret,
            sdk_factory=post_reviewer_sdk_factory, caller=post_reviewer_caller,
            clock=clock,
        )
        resumed_job = storage.get_job(authority.job_id)
        assert resumed_job is not None
        try:
            run_offline_content_pipeline(
                resumed_job,
                storage=storage,
                clock=clock,
                lease_owner=str(session["lease_owner"]),
                project_root=settings.project_root,
                policy=policy,
                writer=writer,
                claim_reviewer=post_reviewer,
                lease_seconds=1800,
                resume_writer_attempt_two_only=True,
                resume_rewrite_of_draft_fingerprint=draft1.fingerprint(),
                resume_rewrite_feedback=tuple({
                    "segment_id": entry.segment_id,
                    "segment_fingerprint": entry.segment_fingerprint,
                    "classification": entry.classification.value,
                    "evidence_ids": list(entry.evidence_ids),
                    "reason": entry.reason,
                    "outcome": entry.outcome.value,
                    "contains_external_fact": entry.contains_external_fact,
                } for entry in initial_entries),
                propagate_claim_reviewer_errors=True,
            )
        except BaseException as exc:
            failed_state = storage.get_content_pipeline_state(authority.job_id)
            current = failed_state["content"]
            if isinstance(current, dict) and current["status"] in {"RUNNING", "REVISE"}:
                review2 = storage.get_content_review_resume_execution(
                    execution_ref=authority.post_review_execution_ref,
                )
                unknown = review2 is not None and review2["outcome"] in {
                    "IN_FLIGHT", "NEEDS_VERIFICATION",
                }
                draft2_saved = any(
                    isinstance(row, dict) and int(row["attempt_no"]) == 2
                    for row in failed_state["drafts"]
                )
                safe_checkpoint = (
                    draft2_saved
                    and (review2 is None or review2["outcome"] == "SUCCESS")
                    and not isinstance(exc, BudgetReservationError)
                )
                if not safe_checkpoint:
                    storage.transition_content_execution(
                        execution,
                        ContentStatus.NEEDS_VERIFICATION if unknown else ContentStatus.FAILED,
                        reason_code=(
                            "REVIEW_ONLY_POST_REVIEW_UNKNOWN"
                            if unknown else "REVIEW_ONLY_CHAIN_FAILED"
                        ),
                        final_result={"error_type": type(exc).__name__, "retry": 0},
                    )
            terminal = storage.get_content_pipeline_state(authority.job_id)["content"]
            if isinstance(terminal, dict) and terminal["status"] in {
                "PENDING_APPROVAL", "FAILED", "NEEDS_VERIFICATION",
            }:
                storage.settle_content_review_resume_session(
                    approval_ref=authority.approval_ref, now=clock.now(),
                )
            raise
        storage.settle_content_review_resume_session(
            approval_ref=authority.approval_ref, now=clock.now(),
        )
        return _result_from_state(storage, authority)
    finally:
        storage.close()


__all__ = [
    "ReviewOnlyAuthority", "ReviewOnlyError", "ReviewOnlyResult",
    "load_review_only_authority", "run_controlled_article_review_only",
]
