"""Jawny dispatcher bez dynamicznego wykonywania danych z kolejki."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.core.config import ConfigError, Settings, require_valid_real_provider_pricing
from app.llm.usage_tracker import UsageTracker
from app.models import Account, Job, JobKind, ResearchJobExecution, Topic, WorkflowType
from app.orchestrator.runner import run_research_dry_run
from app.policies.policy_engine import PolicyDecision, PolicyEngine
from app.ports.notification import LogNotification
from app.ports.storage import StoragePort
from app.research.anthropic_client import AnthropicResearchClient
from app.research.durable_intent import (
    DurableExecutionIntentError,
    DurableResearchExecutionIntent,
    canonicalize_durable_research_payload,
)
from app.workflows.research.pipeline import (
    ResearchExecutionAlreadyInitialized,
    ResearchExecutionNeedsReconciliation,
    ResearchRunSummary,
    run_research_pipeline,
)


class DispatchError(RuntimeError):
    """Controlled, safe-to-store failure while dispatching one job."""


class PayloadValidationError(DispatchError):
    pass


class UnsupportedJobError(DispatchError):
    pass


class PolicyDeniedError(DispatchError):
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        super().__init__(f"Policy denied: {decision.code}")


class UncertainExternalEffectError(DispatchError):
    """Durable execution state exists, but this worker cannot safely continue it."""


class DispatchContractError(TypeError):
    """Dispatcher returned a value outside the closed worker terminalization contract."""


class TerminalizationMode(str, Enum):
    """Explicitly assigns the durable terminalization owner for one dispatch."""

    WORKER_MUST_COMPLETE = "WORKER_MUST_COMPLETE"
    WORKFLOW_TERMINALIZED = "WORKFLOW_TERMINALIZED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"


@dataclass(frozen=True)
class DispatchResult:
    terminalization: TerminalizationMode
    run_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.terminalization, TerminalizationMode):
            raise DispatchContractError(
                "DispatchResult.terminalization must be a TerminalizationMode."
            )

    @classmethod
    def worker_must_complete(cls, *, run_id: str | None = None, detail: str | None = None) -> "DispatchResult":
        return cls(TerminalizationMode.WORKER_MUST_COMPLETE, run_id, detail)

    @classmethod
    def workflow_succeeded(cls, *, run_id: str | None = None, detail: str | None = None) -> "DispatchResult":
        return cls(TerminalizationMode.WORKFLOW_TERMINALIZED, run_id, detail)

    @classmethod
    def workflow_failed(cls, *, run_id: str | None = None, detail: str | None = None) -> "DispatchResult":
        return cls(TerminalizationMode.WORKFLOW_FAILED, run_id, detail)


class ResearchDryRunCallable(Protocol):
    def __call__(
        self,
        account: Account,
        topic: Topic,
        *,
        settings: Settings,
        storage: StoragePort,
        policy: PolicyEngine,
        clock: Clock,
        job_execution: ResearchJobExecution,
    ) -> ResearchRunSummary: ...


def _durable_job_intent(storage: StoragePort, job_id: str) -> DurableResearchExecutionIntent:
    """Read and validate the complete persisted execution contract, never ENV."""
    job = storage.get_job(job_id)
    if job is None:
        raise DispatchError("Durable real research job disappeared before execution.")
    try:
        normalized = canonicalize_durable_research_payload(job.payload)
        intent_raw = normalized["execution_intent"]
        assert isinstance(intent_raw, dict)
        intent = DurableResearchExecutionIntent.from_payload(intent_raw)
    except DurableExecutionIntentError as exc:
        raise PayloadValidationError("Real research job durable execution intent is invalid.") from exc
    if intent.account_id != job.account_id or intent.topic_id != job.topic_id:
        raise PayloadValidationError("Real research execution intent disagrees with its durable job identity.")
    if not intent.is_supported_by_current_worker():
        raise PayloadValidationError("Real research execution intent is not supported by this worker.")
    return intent


def _run_durable_real_research(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    policy: PolicyEngine,
    clock: Clock,
    job_execution: ResearchJobExecution,
) -> ResearchRunSummary:
    """The paid execution root accepts only an already leased durable job."""
    intent = _durable_job_intent(storage, job_execution.job_id)
    real_settings = replace(
        settings,
        dry_run=False,
        model_quality=intent.model,
        research_timeout_seconds=intent.timeout_seconds,
        pricing=intent.runtime_pricing(),
    )
    require_valid_real_provider_pricing(real_settings)
    client = AnthropicResearchClient(
        real_settings.anthropic_api_key, real_settings.model_quality,
        max_retries=0, timeout_seconds=real_settings.research_timeout_seconds,
        max_web_searches=intent.max_web_searches,
        research_max_tokens=intent.max_tokens,
    )
    return run_research_pipeline(
        account, topic, settings=real_settings, storage=storage, research_client=client,
        usage_tracker=UsageTracker(real_settings, storage), policy=policy,
        notifier=LogNotification(), clock=clock, job_execution=job_execution,
        run_cap_usd=float(intent.cap_usd),
        max_web_searches=intent.max_web_searches,
        request_max_tokens=intent.max_tokens,
        durable_plan=intent.as_research_plan(),
    )


class JobDispatcher:
    """Closed dispatch table for the two explicitly safe Stage 1 job types."""

    def __init__(
        self,
        *,
        settings: Settings,
        storage: StoragePort,
        policy: PolicyEngine,
        clock: Clock | None = None,
        research_dry_run: ResearchDryRunCallable = run_research_dry_run,
        research_real: ResearchDryRunCallable = _run_durable_real_research,
        allow_real_research: bool = True,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._policy = policy
        self._clock = clock or SystemClock()
        self._research_dry_run = research_dry_run
        self._research_real = research_real
        self._allow_real_research = allow_real_research

    def dispatch(
        self,
        job: Job,
        *,
        lease_owner: str,
        heartbeat: Callable[[], None],
    ) -> DispatchResult:
        """Runs one supported local operation after a fresh PolicyEngine check."""
        account = self._account_for(job)
        dry_run = job.payload.get("dry_run") is True
        decision = self._policy.check_worker_runtime(
            account, job_kind=job.kind, dry_run=dry_run,
        )
        if not decision.allowed:
            raise PolicyDeniedError(decision)

        if job.kind is JobKind.LOCAL:
            self._validate_local(job)
            heartbeat()
            return DispatchResult.worker_must_complete()
        if job.kind is JobKind.RESEARCH:
            return self._dispatch_research(job, account, lease_owner, heartbeat)
        raise UnsupportedJobError("Unsupported job kind for the offline worker.")

    def _account_for(self, job: Job) -> Account:
        try:
            return self._settings.get_account(job.account_id)
        except ConfigError as exc:
            raise DispatchError("Job account is unavailable in the active configuration.") from exc

    @staticmethod
    def _validate_local(job: Job) -> None:
        if job.workflow is not WorkflowType.ANALYTICS:
            raise UnsupportedJobError("LOCAL jobs support only the ANALYTICS workflow.")
        if job.topic_id is not None or job.run_id is not None:
            raise PayloadValidationError("LOCAL noop job may not contain topic_id or run_id.")
        if job.payload != {"dry_run": True, "action": "noop"}:
            raise PayloadValidationError("LOCAL job payload does not match the offline noop contract.")

    def _dispatch_research(
        self,
        job: Job,
        account: Account,
        lease_owner: str,
        heartbeat: Callable[[], None],
    ) -> DispatchResult:
        if job.payload.get("dry_run") is False and not self._allow_real_research:
            raise PolicyDeniedError(PolicyDecision.block(
                "SYSTEM_SCHEDULER_OFFLINE_ONLY",
                "The system-scheduled worker cannot execute paid research.",
            ))
        topic, is_real = self._validate_research_payload(job)

        # A checkpoint before entering the existing pipeline keeps a long lease
        # alive without a second, competing heartbeat implementation.
        heartbeat()

        try:
            runner = self._research_real if is_real else self._research_dry_run
            summary = runner(
                account, topic,
                settings=self._settings, storage=self._storage, policy=self._policy,
                clock=self._clock,
                job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease_owner),
            )
        except (ResearchExecutionAlreadyInitialized, ResearchExecutionNeedsReconciliation) as exc:
            raise UncertainExternalEffectError(
                "Research execution requires verification before any further provider request."
            ) from exc
        if summary.blocked:
            raise PolicyDeniedError(PolicyDecision.block(
                summary.block_code or "PIPELINE_BLOCKED",
                "Existing research pipeline rejected the dry-run.",
            ))
        if summary.error or summary.run_id is None:
            return DispatchResult.workflow_failed(
                run_id=summary.run_id,
                detail="Research dry-run failed." if not is_real else "Research real job failed.",
            )
        return DispatchResult.workflow_succeeded(
            run_id=summary.run_id,
        )

    # Compatibility seam used by offline maintenance tests.  Dispatch itself
    # selects the payload-specific path above; this alias does not authorize a
    # real request and can be removed with the legacy dry-only test harness.
    _dispatch_research_dry_run = _dispatch_research

    def _validate_research_payload(self, job: Job) -> tuple[Topic, bool]:
        if job.workflow is not WorkflowType.RESEARCH:
            raise UnsupportedJobError("RESEARCH jobs support only the RESEARCH workflow.")
        if job.topic_id is None:
            raise PayloadValidationError("RESEARCH job requires topic_id.")
        if job.run_id is not None:
            raise PayloadValidationError("RESEARCH worker accepts only a job without a prior run_id.")
        dry_keys = {"account_id", "topic_id", "dry_run"}
        real_keys = {
            "account_id", "topic_id", "dry_run", "execution", "mode", "max_cost_usd",
            "execution_intent",
        }
        if set(job.payload) not in (dry_keys, real_keys):
            raise PayloadValidationError("RESEARCH payload contains unsupported fields.")
        if job.payload["account_id"] != job.account_id or job.payload["topic_id"] != job.topic_id:
            raise PayloadValidationError("RESEARCH payload account_id/topic_id must match the job.")
        is_real = job.payload["dry_run"] is False
        if not is_real and job.payload["dry_run"] is not True:
            raise PayloadValidationError("RESEARCH payload dry_run must be boolean.")
        if is_real and (
            job.payload.get("execution") != "durable_provider_v2"
        ):
            raise PayloadValidationError("RESEARCH real payload is not a durable single-attempt contract.")
        if is_real:
            try:
                normalized = canonicalize_durable_research_payload(job.payload)
                intent_raw = normalized["execution_intent"]
                assert isinstance(intent_raw, dict)
                intent = DurableResearchExecutionIntent.from_payload(intent_raw)
            except DurableExecutionIntentError as exc:
                raise PayloadValidationError("RESEARCH real payload intent is invalid.") from exc
            if intent.account_id != job.account_id or intent.topic_id != job.topic_id:
                raise PayloadValidationError("RESEARCH real payload intent does not match job identity.")
        topic = next(
            (candidate for candidate in self._storage.list_topics(job.account_id)
             if candidate.id == job.topic_id),
            None,
        )
        if topic is None:
            raise PayloadValidationError("RESEARCH job topic is unavailable for its account.")
        return topic, is_real
