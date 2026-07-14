"""Jawny dispatcher bez dynamicznego wykonywania danych z kolejki."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.core.config import ConfigError, Settings
from app.models import Account, Job, JobKind, ResearchJobExecution, Topic, WorkflowType
from app.orchestrator.runner import run_research_dry_run
from app.policies.policy_engine import PolicyDecision, PolicyEngine
from app.ports.storage import StoragePort
from app.workflows.research.pipeline import (
    ResearchExecutionAlreadyInitialized,
    ResearchRunSummary,
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
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._policy = policy
        self._clock = clock or SystemClock()
        self._research_dry_run = research_dry_run

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
            return self._dispatch_research_dry_run(job, account, lease_owner, heartbeat)
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

    def _dispatch_research_dry_run(
        self,
        job: Job,
        account: Account,
        lease_owner: str,
        heartbeat: Callable[[], None],
    ) -> DispatchResult:
        topic = self._validate_research_payload(job)

        # A checkpoint before entering the existing pipeline keeps a long lease
        # alive without a second, competing heartbeat implementation.
        heartbeat()

        try:
            summary = self._research_dry_run(
                account, topic,
                settings=self._settings, storage=self._storage, policy=self._policy,
                clock=self._clock,
                job_execution=ResearchJobExecution(job_id=job.id, lease_owner=lease_owner),
            )
        except ResearchExecutionAlreadyInitialized as exc:
            raise UncertainExternalEffectError(
                "Research execution was already initialized; verification is required."
            ) from exc
        if summary.blocked:
            raise PolicyDeniedError(PolicyDecision.block(
                summary.block_code or "PIPELINE_BLOCKED",
                "Existing research pipeline rejected the dry-run.",
            ))
        if summary.error or summary.run_id is None:
            return DispatchResult.workflow_failed(
                run_id=summary.run_id,
                detail="Research dry-run failed.",
            )
        return DispatchResult.workflow_succeeded(
            run_id=summary.run_id,
        )

    def _validate_research_payload(self, job: Job) -> Topic:
        if job.workflow is not WorkflowType.RESEARCH:
            raise UnsupportedJobError("RESEARCH jobs support only the RESEARCH workflow.")
        if job.topic_id is None:
            raise PayloadValidationError("RESEARCH job requires topic_id.")
        if job.run_id is not None:
            raise PayloadValidationError("RESEARCH worker accepts only a job without a prior run_id.")
        required_keys = {"account_id", "topic_id", "dry_run"}
        if set(job.payload) != required_keys:
            raise PayloadValidationError("RESEARCH payload contains unsupported fields.")
        if job.payload["account_id"] != job.account_id or job.payload["topic_id"] != job.topic_id:
            raise PayloadValidationError("RESEARCH payload account_id/topic_id must match the job.")
        if job.payload["dry_run"] is not True:
            raise PayloadValidationError("RESEARCH worker accepts only dry_run=true.")
        topic = next(
            (candidate for candidate in self._storage.list_topics(job.account_id)
             if candidate.id == job.topic_id),
            None,
        )
        if topic is None:
            raise PayloadValidationError("RESEARCH job topic is unavailable for its account.")
        return topic
