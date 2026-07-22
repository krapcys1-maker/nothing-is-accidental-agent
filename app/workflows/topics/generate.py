"""Autonomiczne generowanie tematów w istniejącym durable provider lifecycle.

Przepływ (jeden Worker, jeden Dispatcher, jeden Policy Engine, jedna tabela
`provider_attempts`, jedna tabela `model_usage`, jeden settlement):

    zamrożony intent -> [POLICY] runtime+budżet -> run TOPIC_GENERATION
    -> provider_attempt RESERVED (atomowo konsumuje zgodę L1)
    -> REQUEST_STARTED -> DOKŁADNIE jeden request -> istniejący parser
    -> walidacja wymiarów -> istniejący scoring -> istniejący TopicDeduplicator
    -> najwyżej jeden SELECTED tego runu -> usage dokładnie raz -> settlement
    -> run SUCCESS -> job DONE.

Człowiek nie wpisuje tematu i nie wybiera zwycięzcy. Zgoda L1 dotyczy WYŁĄCZNIE
uruchomienia jednego płatnego joba w bieżącej fazie budowy — nie jest docelową
logiką wyboru tematu ani wymogiem LEVEL_3.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from app.core.clock import Clock, SystemClock
from app.core.config import Settings
from app.core.ids import new_run_id
from app.llm.base import (
    LLMClientError,
    LLMProviderError,
    LLMResponseError,
    TopicIdea,
)
from app.models import (
    JobExecutionContext,
    ResearchJobExecution,
    Topic,
    TopicGenerationCandidate,
    TopicStatus,
)
from app.llm.usage_tracker import UsageTracker
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import (
    BudgetReservationError,
    ProviderAttemptOverReservationError,
    ProviderAttemptReconciliationRequired,
    StaleJobExecutionError,
    StoragePort,
    TopicGenerationAuthorizationError,
    TopicGenerationResultError,
)
from app.research.base import DurableProviderAttemptContext
from app.topics.durable_intent import DurableTopicGenerationIntent
from app.workflows.topics.dedup import TopicDeduplicator
from app.workflows.topics.discover import compute_weighted_score

TOPIC_GENERATION_USAGE_TASK = "topics"


class TopicGenerationNeedsVerification(RuntimeError):
    """The provider outcome is unknown; only explicit human review may continue."""


class TopicGenerationBlocked(RuntimeError):
    """A policy or budget gate refused before any provider request existed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass
class TopicGenerationSummary:
    run_id: str | None
    account_id: str
    model: str = ""
    request_id: str | None = None
    total: int = 0
    selected: int = 0
    scored: int = 0
    rejected: int = 0
    duplicates: int = 0
    cost_usd: float = 0.0
    blocked: bool = False
    block_code: str | None = None
    error: str | None = None
    selected_topic_id: int | None = None
    topic_ids: list[int] = field(default_factory=list)


def validate_score_breakdown(
    idea: TopicIdea, *, dimensions: list[str], label: str,
) -> dict[str, float]:
    """Exact-dimension contract: no missing, no unknown, finite and in range."""
    if not idea.title.strip():
        raise TopicGenerationResultError(
            "CANDIDATE_TITLE_EMPTY", f"{label}.title must be a non-empty string.",
        )
    if not isinstance(idea.question, str) or not idea.question.strip():
        raise TopicGenerationResultError(
            "CANDIDATE_QUESTION_EMPTY",
            f"{label}.question must be a non-empty string.",
        )
    expected = set(dimensions)
    actual = set(idea.score_breakdown)
    missing = sorted(expected - actual)
    if missing:
        raise TopicGenerationResultError(
            "SCORE_DIMENSION_MISSING",
            f"{label}.score_breakdown is missing {','.join(missing)}.",
        )
    unknown = sorted(actual - expected)
    if unknown:
        raise TopicGenerationResultError(
            "SCORE_DIMENSION_UNKNOWN",
            f"{label}.score_breakdown carries unknown {','.join(unknown)}.",
        )
    breakdown: dict[str, float] = {}
    for name in dimensions:
        raw = idea.score_breakdown[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise TopicGenerationResultError(
                "SCORE_DIMENSION_NOT_NUMERIC",
                f"{label}.score_breakdown['{name}'] must be a finite number.",
            )
        value = float(raw)
        if not math.isfinite(value):
            raise TopicGenerationResultError(
                "SCORE_DIMENSION_NOT_FINITE",
                f"{label}.score_breakdown['{name}'] must be finite.",
            )
        if not 0.0 <= value <= 1.0:
            raise TopicGenerationResultError(
                "SCORE_DIMENSION_OUT_OF_RANGE",
                f"{label}.score_breakdown['{name}'] must lie in 0..1.",
            )
        breakdown[name] = value
    return breakdown


def _configure_durable_topic_attempt_control(
    *,
    llm,
    storage: StoragePort,
    policy: PolicyEngine,
    account,
    execution: JobExecutionContext,
    intent: DurableTopicGenerationIntent,
    intent_fingerprint: str,
    estimated_attempt_cost: float,
    state: dict[str, object],
) -> None:
    """Bind the shared durable boundary to storage-owned policy and persistence."""

    def context_callback(budget) -> DurableProviderAttemptContext:
        storage.assert_topic_generation_execution_active(execution)
        decision = policy.check_run_budget(
            estimated_attempt_cost,
            float(intent.cap_usd),
            current_run_cost=0.0,
            account=account,
        )
        if not decision.allowed:
            raise TopicGenerationBlocked(decision.code, decision.reason)
        try:
            attempt = storage.begin_provider_attempt(
                execution,
                stage=budget.stage,
                attempt_no=budget.attempt_number,
                max_cost_usd=budget.estimated_attempt_cost,
                daily_limit_usd=policy.daily_limit_usd,
                monthly_limit_usd=policy.monthly_limit_usd,
            )
        except BudgetReservationError as exc:
            raise TopicGenerationBlocked(
                "BUDGET_RESERVATION_DENIED",
                "Atomic provider reservation rejected the request.",
            ) from exc
        except ProviderAttemptReconciliationRequired as exc:
            raise TopicGenerationNeedsVerification(
                "Provider attempt requires explicit reconciliation before another request."
            ) from exc
        state["request_id"] = attempt.request_id
        return DurableProviderAttemptContext(
            job_id=execution.job_id,
            run_id=execution.run_id,
            stage=attempt.stage,
            attempt_no=attempt.attempt_no,
            request_id=attempt.request_id,
            lease_owner=execution.lease_owner,
            fence_token=(
                f"{execution.job_id}:{execution.run_id}:{execution.lease_owner}"
            ),
            checked_at=execution.now(),
        )

    def assert_frozen_intent_snapshot(context: DurableProviderAttemptContext) -> None:
        try:
            storage.assert_topic_generation_execution_active(
                execution, expected_intent_fingerprint=intent_fingerprint,
            )
        except TopicGenerationAuthorizationError:
            # REQUEST_STARTED is committed before this final gate.  Preserve the
            # attempt identity for explicit reconciliation; never auto-release
            # a possibly live request and never retry it.
            if state.get("request_started"):
                storage.mark_provider_attempt_needs_reconciliation(
                    execution, context.request_id,
                    error_code="TOPIC_INTENT_SNAPSHOT_MISMATCH",
                )
            raise

    def activation_callback(context: DurableProviderAttemptContext):
        if context.fence_token != (
            f"{execution.job_id}:{execution.run_id}:{execution.lease_owner}"
        ):
            raise StaleJobExecutionError(
                execution.job_id,
                "durable provider context fence token does not match the execution.",
            )
        attempt = storage.mark_provider_attempt_request_started(
            execution, context.request_id,
        )
        state["request_started"] = True
        assert_frozen_intent_snapshot(context)
        return attempt

    def assertion_callback(context: DurableProviderAttemptContext):
        assert_frozen_intent_snapshot(context)
        return storage.assert_durable_provider_attempt_active(
            context, clock=execution.clock,
        )

    llm.configure_durable_attempt_control(
        context_callback=context_callback,
        activation_callback=activation_callback,
        assertion_callback=assertion_callback,
        estimated_attempt_cost=estimated_attempt_cost,
    )


def run_topic_generation(
    account,
    *,
    settings: Settings,
    storage: StoragePort,
    llm,
    usage_tracker: UsageTracker,
    policy: PolicyEngine,
    clock: Clock | None = None,
    job_execution: ResearchJobExecution,
    intent: DurableTopicGenerationIntent,
    intent_fingerprint: str,
) -> TopicGenerationSummary:
    clock = clock or SystemClock()
    summary = TopicGenerationSummary(
        run_id=None, account_id=intent.account_id, model=intent.model,
    )

    initialized = storage.initialize_topic_generation_run_for_job(
        job_execution.job_id, job_execution.lease_owner, new_run_id(), clock=clock,
    )
    run_id = initialized.run.id
    summary.run_id = run_id
    execution = JobExecutionContext(
        job_id=job_execution.job_id,
        lease_owner=job_execution.lease_owner,
        run_id=run_id,
        clock=clock,
    )

    estimated_attempt_cost = float(intent.pessimistic_cost_usd)
    state: dict[str, object] = {"request_id": None, "request_started": False}
    _configure_durable_topic_attempt_control(
        llm=llm, storage=storage, policy=policy, account=account,
        execution=execution, intent=intent, intent_fingerprint=intent_fingerprint,
        estimated_attempt_cost=estimated_attempt_cost, state=state,
    )

    try:
        result = llm.generate_and_score_topics(
            intent.prompt_account(), intent.candidate_count,
        )
    except TopicGenerationBlocked as exc:
        # Refused BEFORE the request boundary: release the reservation if one
        # exists, then terminalize.  Zero usage, zero topics, zero cost.
        _release_unstarted_attempt(storage, execution, state, exc.code)
        storage.fail_or_escalate_topic_generation_execution(
            execution, None, f"{exc.code}", terminalize_job=True,
        )
        summary.blocked = True
        summary.block_code = exc.code
        summary.error = str(exc)
        return summary
    except LLMResponseError as exc:
        # The provider answered and billed; the body is unusable.  Book the real
        # usage exactly once, settle honestly, and persist NO partial topic.
        return _fail_with_known_usage(
            storage=storage, usage_tracker=usage_tracker, execution=execution,
            intent=intent, state=state, summary=summary, exc=exc,
            code="TOPIC_RESPONSE_REJECTED",
        )
    except LLMProviderError as exc:
        return _fail_provider_error(
            storage=storage, usage_tracker=usage_tracker, execution=execution,
            intent=intent, state=state, summary=summary, exc=exc,
        )
    except LLMClientError as exc:
        return _fail_provider_error(
            storage=storage, usage_tracker=usage_tracker, execution=execution,
            intent=intent, state=state, summary=summary, exc=exc,
        )

    request_id = state["request_id"]
    assert isinstance(request_id, str)
    summary.request_id = request_id

    # The real usage is booked BEFORE any scoring decision, so a response that
    # later fails validation can never disappear from the ledger.
    try:
        usage_row = usage_tracker.record_job(
            execution, result.model, result.usage,
            task=TOPIC_GENERATION_USAGE_TASK, dry_run=False, request_id=request_id,
        )
    except ProviderAttemptOverReservationError as exc:
        # Usage is persisted, but the real cost exceeded the reservation: the
        # attempt is already NEEDS_RECONCILIATION.  No topic is written and no
        # request is repeated; only a human may close this out.
        raise TopicGenerationNeedsVerification(
            "Actual topic generation cost exceeded its reservation."
        ) from exc
    summary.cost_usd = usage_row.estimated_cost_usd

    try:
        candidates = _score_and_select(
            result.ideas, settings=settings, storage=storage, policy=policy,
            intent=intent, summary=summary,
        )
    except TopicGenerationResultError as exc:
        storage.fail_or_escalate_topic_generation_execution(
            execution, usage_row.estimated_cost_usd, exc.code, terminalize_job=True,
        )
        summary.error = str(exc)
        summary.block_code = exc.code
        summary.total = 0
        summary.selected = summary.scored = summary.rejected = summary.duplicates = 0
        summary.topic_ids = []
        summary.selected_topic_id = None
        return summary

    lineage = storage.finalize_topic_generation_success(
        execution, request_id=request_id, candidates=candidates,
        total_cost_usd=usage_row.estimated_cost_usd,
    )
    summary.topic_ids = [row.topic_id for row in lineage]
    summary.selected_topic_id = next(
        (row.topic_id for row in lineage if row.is_selected), None,
    )
    return summary


def _release_unstarted_attempt(
    storage: StoragePort, execution: JobExecutionContext,
    state: dict[str, object], error_code: str,
) -> None:
    request_id = state.get("request_id")
    if not isinstance(request_id, str) or state.get("request_started"):
        return
    try:
        storage.release_provider_attempt_before_request(
            execution, request_id, error_code=error_code,
        )
    except Exception:
        # Never convert a release failure into a second provider request; the
        # centralized failure boundary below still normalizes the attempt.
        pass


def _fail_provider_error(
    *, storage: StoragePort, usage_tracker: UsageTracker,
    execution: JobExecutionContext, intent: DurableTopicGenerationIntent,
    state: dict[str, object], summary: TopicGenerationSummary,
    exc: LLMClientError,
) -> TopicGenerationSummary:
    """Provider failure: settle when usage is known, escalate when it is not."""
    if exc.usage is not None:
        return _fail_with_known_usage(
            storage=storage, usage_tracker=usage_tracker, execution=execution,
            intent=intent, state=state, summary=summary, exc=exc,
            code="TOPIC_PROVIDER_FAILED",
        )
    request_id = state.get("request_id")
    if isinstance(request_id, str) and state.get("request_started"):
        # The request crossed the boundary and returned no usage: the financial
        # outcome is UNKNOWN.  Never auto-retry, never invent a zero cost.
        raise TopicGenerationNeedsVerification(
            "Topic generation request outcome is unknown; explicit review required."
        ) from exc
    _release_unstarted_attempt(storage, execution, state, "TOPIC_PROVIDER_FAILED")
    storage.fail_or_escalate_topic_generation_execution(
        execution, None, "TOPIC_PROVIDER_FAILED", terminalize_job=True,
    )
    summary.error = str(exc)
    summary.block_code = "TOPIC_PROVIDER_FAILED"
    return summary


def _fail_with_known_usage(
    *, storage: StoragePort, usage_tracker: UsageTracker,
    execution: JobExecutionContext, intent: DurableTopicGenerationIntent,
    state: dict[str, object], summary: TopicGenerationSummary,
    exc: LLMClientError, code: str,
) -> TopicGenerationSummary:
    request_id = state.get("request_id")
    if exc.usage is None or not isinstance(request_id, str):
        raise TopicGenerationNeedsVerification(
            "Topic generation failure lacks the durable identity required to settle."
        ) from exc
    usage_row = usage_tracker.record_job(
        execution, exc.model or intent.model, exc.usage,
        task=TOPIC_GENERATION_USAGE_TASK, dry_run=False, request_id=request_id,
    )
    summary.request_id = request_id
    summary.cost_usd = usage_row.estimated_cost_usd
    storage.fail_or_escalate_topic_generation_execution(
        execution, usage_row.estimated_cost_usd, code, terminalize_job=True,
    )
    summary.error = str(exc)
    summary.block_code = code
    return summary


def _score_and_select(
    ideas: list[TopicIdea],
    *,
    settings: Settings,
    storage: StoragePort,
    policy: PolicyEngine,
    intent: DurableTopicGenerationIntent,
    summary: TopicGenerationSummary,
) -> list[TopicGenerationCandidate]:
    """Existing scoring + existing dedup + deterministic single-winner choice."""
    if not ideas:
        raise TopicGenerationResultError(
            "NO_CANDIDATES", "the response carried no topic candidates.",
        )
    if len(ideas) > intent.candidate_count:
        raise TopicGenerationResultError(
            "TOO_MANY_CANDIDATES",
            f"the response carried {len(ideas)} candidates, "
            f"more than the frozen {intent.candidate_count}.",
        )

    dedup = TopicDeduplicator(settings.topic_duplicate_threshold)
    # Existing account topics AND candidates accepted earlier in this very batch.
    existing: list[tuple[int, str]] = list(
        storage.list_topic_titles_for_dedup(intent.account_id)
    )
    # In-batch duplicates get negative synthetic ids: they are not persisted yet,
    # and a real topic id is never negative, so the two can never collide.
    next_batch_id = -1

    scored: list[tuple[int, float, Topic]] = []
    for index, idea in enumerate(ideas):
        breakdown = validate_score_breakdown(
            idea, dimensions=intent.score_dimensions, label=f"topics[{index}]",
        )
        score = compute_weighted_score(breakdown, settings.topic_scoring_weights)
        summary.total += 1
        match = dedup.find_duplicate(idea.title, existing)
        if match is not None:
            summary.duplicates += 1
            scored.append((index, score, Topic(
                account_id=intent.account_id, title=idea.title,
                question=idea.question, score=score, score_breakdown=breakdown,
                status=TopicStatus.DUPLICATE, source="anthropic",
                duplicate_of=match.existing_id if match.existing_id > 0 else None,
                rejection_reason=(
                    f"duplicate of topic #{match.existing_id} "
                    f"('{match.existing_title}') — {match.reason} "
                    f"(score={match.score})"
                ),
            )))
            continue
        scored.append((index, score, Topic(
            account_id=intent.account_id, title=idea.title, question=idea.question,
            score=score, score_breakdown=breakdown,
            status=TopicStatus.DISCOVERED, source="anthropic",
        )))
        existing.append((next_batch_id, idea.title))
        next_batch_id -= 1

    # Exactly one winner of THIS execution: highest weighted score among
    # non-duplicates that reach article_min_score; ties broken deterministically
    # by the earliest response index.
    eligible = [
        (index, score) for index, score, topic in scored
        if topic.status is not TopicStatus.DUPLICATE
        and score >= settings.article_min_score
    ]
    winner_index = (
        min(eligible, key=lambda pair: (-pair[1], pair[0]))[0] if eligible else None
    )

    candidates: list[TopicGenerationCandidate] = []
    for index, score, topic in scored:
        if topic.status is TopicStatus.DUPLICATE:
            candidates.append(TopicGenerationCandidate(
                topic=topic, candidate_index=index, is_selected=False,
            ))
            continue
        if index == winner_index:
            topic.status = TopicStatus.SELECTED
            summary.selected += 1
            candidates.append(TopicGenerationCandidate(
                topic=topic, candidate_index=index, is_selected=True,
            ))
            continue
        # Every remaining candidate keeps an existing legal status from the
        # existing thresholds; a runner-up that would also qualify for an
        # article is deliberately demoted to the Note tier, because this one
        # execution may promote at most one topic.
        status = policy.decide_topic_status(score)
        if status is TopicStatus.SELECTED:
            status = TopicStatus.SCORED
        topic.status = status
        if status is TopicStatus.SCORED:
            summary.scored += 1
        else:
            summary.rejected += 1
        candidates.append(TopicGenerationCandidate(
            topic=topic, candidate_index=index, is_selected=False,
        ))
    return candidates
