"""Jawny dispatcher bez dynamicznego wykonywania danych z kolejki."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Protocol

from app.core.clock import Clock, SystemClock
from app.core.config import ConfigError, Settings, require_valid_real_provider_pricing
from app.core.pricing import (
    PricingConfigError,
    assert_frozen_pricing_contract,
    default_pricing_profiles_path,
    load_pricing_profiles,
    resolve_real_pricing_profile,
)
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
from app.research.offline_evidence_intent import (
    OFFLINE_EVIDENCE_EXECUTION,
    OfflineEvidenceIntent,
    OfflineEvidenceIntentError,
    canonicalize_offline_evidence_payload,
)
from app.research.controlled_fetch_intent import (
    CONTROLLED_FETCH_EXECUTION,
    ControlledFetchIntent,
    ControlledFetchIntentError,
    canonicalize_controlled_fetch_payload,
)
from app.workflows.research.controlled_fetch import (
    ControlledFetchNeedsVerification,
    run_controlled_fetch,
)
from app.workflows.research.offline_evidence import run_offline_evidence_research
from app.workflows.research.pipeline import (
    ResearchExecutionAlreadyInitialized,
    ResearchExecutionNeedsReconciliation,
    ResearchRunSummary,
    run_research_pipeline,
)
from app.llm.anthropic_client import AnthropicLLMClient
from app.ports.storage import ProviderAttemptReconciliationRequired
from app.topics.durable_intent import (
    DurableTopicGenerationIntent,
    frozen_topic_generation_contract,
)
from app.workflows.topics.generate import (
    TopicGenerationNeedsVerification,
    TopicGenerationSummary,
    run_topic_generation,
)
from app.content.foundation import (
    ContentExecutionMode,
    ContentStatus,
    canonicalize_content_job_payload,
)
from app.content.pipeline import ContentPipelineSummary, run_offline_content_pipeline
from app.content.contracts import RouteContract
from app.content.writer import FakeContentWriter, WriterPort


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


class OfflineEvidenceCallable(Protocol):
    def __call__(
        self, account: Account, topic: Topic, *, settings: Settings,
        storage: StoragePort, policy: PolicyEngine, clock: Clock,
        job_execution: ResearchJobExecution, intent: OfflineEvidenceIntent,
    ) -> ResearchRunSummary: ...


class ControlledFetchCallable(Protocol):
    def __call__(
        self, account: Account, topic: Topic, *, settings: Settings,
        storage: StoragePort, policy: PolicyEngine, clock: Clock,
        job_execution: ResearchJobExecution, intent: ControlledFetchIntent,
    ) -> ResearchRunSummary: ...


class TopicGenerationCallable(Protocol):
    def __call__(
        self, account: Account, *, settings: Settings, storage: StoragePort,
        llm: object, usage_tracker: UsageTracker, policy: PolicyEngine,
        clock: Clock, job_execution: ResearchJobExecution,
        intent: DurableTopicGenerationIntent, intent_fingerprint: str,
    ) -> TopicGenerationSummary: ...


class TopicGenerationClientFactory(Protocol):
    def __call__(
        self, settings: Settings, intent: DurableTopicGenerationIntent,
    ) -> object: ...


class ContentPipelineCallable(Protocol):
    def __call__(
        self,
        job: Job,
        *,
        storage: StoragePort,
        clock: Clock,
        lease_owner: str,
        project_root: object,
        policy: PolicyEngine,
        writer: WriterPort | None = None,
        route_override: RouteContract | None = None,
    ) -> ContentPipelineSummary: ...


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
    try:
        profiles = load_pricing_profiles(
            default_pricing_profiles_path(settings.project_root)
        )
        approved = resolve_real_pricing_profile(
            profiles,
            profile_id=intent.pricing_profile_id,
            model=intent.model,
        )
        assert_frozen_pricing_contract(
            profile=approved,
            profile_id=intent.pricing_profile_id,
            version=intent.pricing_profile_version,
            model=intent.model,
            currency=intent.pricing_currency,
            unit=intent.pricing_unit,
            prices=intent.pricing_profile,
            fingerprint=intent.pricing_fingerprint,
        )
    except PricingConfigError as exc:
        raise PayloadValidationError(
            "Durable real research pricing contract is not currently approved."
        ) from exc
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
        force_re_research=intent.force_re_research,
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
        research_offline_evidence: OfflineEvidenceCallable = run_offline_evidence_research,
        research_controlled_fetch: ControlledFetchCallable = run_controlled_fetch,
        topic_generation: TopicGenerationCallable = run_topic_generation,
        topic_generation_client_factory: TopicGenerationClientFactory | None = None,
        allow_real_research: bool = True,
        allow_real_topic_generation: bool = True,
        content_pipeline: ContentPipelineCallable = run_offline_content_pipeline,
        content_writer: WriterPort | None = None,
        content_route_override: RouteContract | None = None,
        allow_paid_content: bool = False,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._policy = policy
        self._clock = clock or SystemClock()
        self._research_dry_run = research_dry_run
        self._research_real = research_real
        self._research_offline_evidence = research_offline_evidence
        self._research_controlled_fetch = research_controlled_fetch
        self._topic_generation = topic_generation
        self._topic_generation_client = (
            topic_generation_client_factory or self._default_topic_generation_client
        )
        self._allow_real_research = allow_real_research
        self._allow_real_topic_generation = allow_real_topic_generation
        self._content_pipeline = content_pipeline
        self._content_writer = content_writer or FakeContentWriter()
        self._content_route_override = content_route_override
        self._allow_paid_content = allow_paid_content

    def dispatch(
        self,
        job: Job,
        *,
        lease_owner: str,
        heartbeat: Callable[[], None],
    ) -> DispatchResult:
        """Runs one supported local operation after a fresh PolicyEngine check."""
        account = self._account_for(job)
        dry_run = job.payload.get("dry_run") is True or (
            job.kind is JobKind.CONTENT
            and job.payload.get("execution_mode")
            != ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE.value
        )
        controlled_fetch = (
            job.payload.get("execution") == CONTROLLED_FETCH_EXECUTION
        )
        decision = self._policy.check_worker_runtime(
            account, job_kind=job.kind, dry_run=dry_run,
            controlled_fetch=controlled_fetch,
        )
        if not decision.allowed:
            raise PolicyDeniedError(decision)

        if job.kind is JobKind.LOCAL:
            self._validate_local(job)
            heartbeat()
            return DispatchResult.worker_must_complete()
        if job.kind is JobKind.RESEARCH:
            return self._dispatch_research(job, account, lease_owner, heartbeat)
        if job.kind is JobKind.TOPIC_GENERATION:
            return self._dispatch_topic_generation(
                job, account, lease_owner, heartbeat,
            )
        if job.kind is JobKind.CONTENT:
            return self._dispatch_content(job, lease_owner, heartbeat)
        raise UnsupportedJobError("Unsupported job kind for the offline worker.")

    def _dispatch_content(
        self, job: Job, lease_owner: str, heartbeat: Callable[[], None],
    ) -> DispatchResult:
        """Run the held C3 offline root; no real provider is authorized."""
        if job.workflow not in (WorkflowType.ARTICLE, WorkflowType.NOTE):
            raise UnsupportedJobError("CONTENT jobs support only ARTICLE or NOTE.")
        try:
            payload = canonicalize_content_job_payload(job.payload)
        except Exception as exc:
            raise PayloadValidationError("CONTENT payload contract is invalid.") from exc
        paid = (
            payload["execution_mode"]
            == ContentExecutionMode.CONTROLLED_PROVIDER_PIPELINE.value
        )
        if not paid and (
            payload["execution_mode"] != ContentExecutionMode.OFFLINE_PIPELINE.value
        ):
            raise UnsupportedJobError(
                "Dispatcher accepts only executable content pipeline modes."
            )
        if paid and not self._allow_paid_content:
            # Declaring the mode is not authorization: this composition root
            # was not built with paid content enabled.
            raise PolicyDeniedError(PolicyDecision.block(
                "CONTENT_PAID_PROVIDER_NOT_AUTHORIZED",
                "This dispatcher is not composed with paid CONTENT enabled.",
            ))
        if not paid and payload["provider_enabled"] is not False:
            raise PolicyDeniedError(PolicyDecision.block(
                "CONTENT_REAL_PROVIDER_FORBIDDEN",
                "Offline content exposes only fake callers/SDKs.",
            ))
        summary = self._content_pipeline(
            job,
            storage=self._storage,
            clock=self._clock,
            lease_owner=lease_owner,
            project_root=self._settings.project_root,
            policy=self._policy,
            writer=self._content_writer,
            route_override=self._content_route_override,
            heartbeat=heartbeat,
        )
        if summary.status in {
            ContentStatus.PENDING_APPROVAL,
            ContentStatus.APPROVED,
            ContentStatus.REJECTED,
        }:
            return DispatchResult.workflow_succeeded(run_id=summary.run_id)
        return DispatchResult.workflow_failed(
            run_id=summary.run_id,
            detail=summary.block_code or "Offline content pipeline failed.",
        )

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
        topic, is_real = self._validate_research_payload(job, lease_owner=lease_owner)

        # A checkpoint before entering the existing pipeline keeps a long lease
        # alive without a second, competing heartbeat implementation.
        heartbeat()

        try:
            execution = ResearchJobExecution(job_id=job.id, lease_owner=lease_owner)
            if job.payload.get("execution") == OFFLINE_EVIDENCE_EXECUTION:
                intent = OfflineEvidenceIntent.from_payload(job.payload["execution_intent"])
                summary = self._research_offline_evidence(
                    account, topic, settings=self._settings, storage=self._storage,
                    policy=self._policy, clock=self._clock,
                    job_execution=execution, intent=intent,
                )
            elif job.payload.get("execution") == CONTROLLED_FETCH_EXECUTION:
                fetch_intent = ControlledFetchIntent.from_payload(
                    job.payload["execution_intent"]
                )
                summary = self._research_controlled_fetch(
                    account, topic, settings=self._settings, storage=self._storage,
                    policy=self._policy, clock=self._clock,
                    job_execution=execution, intent=fetch_intent,
                )
            else:
                runner = self._research_real if is_real else self._research_dry_run
                summary = runner(
                    account, topic,
                    settings=self._settings, storage=self._storage, policy=self._policy,
                    clock=self._clock, job_execution=execution,
                )
        except ControlledFetchNeedsVerification as exc:
            raise UncertainExternalEffectError(
                "Controlled fetch outcome requires verification; no automatic retry."
            ) from exc
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

    def _dispatch_topic_generation(
        self,
        job: Job,
        account: Account,
        lease_owner: str,
        heartbeat: Callable[[], None],
    ) -> DispatchResult:
        """Paid, durable topic generation — the only job kind without a topic."""
        if not self._allow_real_topic_generation:
            raise PolicyDeniedError(PolicyDecision.block(
                "SYSTEM_SCHEDULER_OFFLINE_ONLY",
                "The system-scheduled worker cannot execute paid topic generation.",
            ))
        if job.workflow is not WorkflowType.TOPIC_GENERATION:
            raise UnsupportedJobError(
                "TOPIC_GENERATION jobs support only the TOPIC_GENERATION workflow."
            )
        if job.topic_id is not None:
            raise PayloadValidationError(
                "TOPIC_GENERATION job must not carry a topic_id."
            )
        if job.run_id is not None:
            raise PayloadValidationError(
                "TOPIC_GENERATION worker accepts only a job without a prior run_id."
            )
        try:
            intent, _, intent_fingerprint = frozen_topic_generation_contract(
                job.payload,
            )
        except DurableExecutionIntentError as exc:
            raise PayloadValidationError(
                "TOPIC_GENERATION payload intent is invalid."
            ) from exc
        if intent.account_id != job.account_id:
            raise PayloadValidationError(
                "TOPIC_GENERATION intent does not match its durable job identity."
            )
        if not intent.is_supported_by_current_worker():
            raise PayloadValidationError(
                "TOPIC_GENERATION intent is not supported by this worker."
            )

        try:
            profiles = load_pricing_profiles(
                default_pricing_profiles_path(self._settings.project_root)
            )
            approved = resolve_real_pricing_profile(
                profiles, profile_id=intent.pricing_profile_id, model=intent.model,
            )
            assert_frozen_pricing_contract(
                profile=approved,
                profile_id=intent.pricing_profile_id,
                version=intent.pricing_profile_version,
                model=intent.model,
                currency=intent.pricing_currency,
                unit=intent.pricing_unit,
                prices=intent.pricing_profile,
                fingerprint=intent.pricing_fingerprint,
            )
        except PricingConfigError as exc:
            raise PayloadValidationError(
                "TOPIC_GENERATION pricing contract is not currently approved."
            ) from exc

        real_settings = replace(
            self._settings,
            dry_run=False,
            model_quality=intent.model,
            research_timeout_seconds=intent.timeout_seconds,
            pricing=intent.runtime_pricing(),
        )
        require_valid_real_provider_pricing(real_settings)

        # A checkpoint before entering the workflow keeps a long lease alive
        # without a second, competing heartbeat implementation.
        heartbeat()

        client = self._topic_generation_client(real_settings, intent)
        execution = ResearchJobExecution(job_id=job.id, lease_owner=lease_owner)
        try:
            summary = self._topic_generation(
                account,
                settings=real_settings, storage=self._storage, llm=client,
                usage_tracker=UsageTracker(real_settings, self._storage),
                policy=self._policy, clock=self._clock,
                job_execution=execution, intent=intent,
                intent_fingerprint=intent_fingerprint,
            )
        except TopicGenerationNeedsVerification as exc:
            raise UncertainExternalEffectError(
                "Topic generation outcome requires verification; no automatic retry."
            ) from exc
        except ProviderAttemptReconciliationRequired as exc:
            raise UncertainExternalEffectError(
                "Topic generation requires verification before any further provider request."
            ) from exc
        if summary.blocked:
            raise PolicyDeniedError(PolicyDecision.block(
                summary.block_code or "TOPIC_GENERATION_BLOCKED",
                "Topic generation was refused before any provider request.",
            ))
        if summary.error or summary.run_id is None:
            return DispatchResult.workflow_failed(
                run_id=summary.run_id, detail="Topic generation job failed.",
            )
        return DispatchResult.workflow_succeeded(run_id=summary.run_id)

    @staticmethod
    def _default_topic_generation_client(
        settings: Settings, intent: DurableTopicGenerationIntent,
    ) -> AnthropicLLMClient:
        return AnthropicLLMClient(
            settings.anthropic_api_key,
            intent.model,
            timeout_seconds=float(intent.timeout_seconds),
            topic_max_tokens=intent.max_tokens,
        )

    # Compatibility seam used by offline maintenance tests.  Dispatch itself
    # selects the payload-specific path above; this alias does not authorize a
    # real request and can be removed with the legacy dry-only test harness.
    _dispatch_research_dry_run = _dispatch_research

    def _validate_research_payload(
        self, job: Job, *, lease_owner: str | None = None,
    ) -> tuple[Topic, bool]:
        if job.workflow is not WorkflowType.RESEARCH:
            raise UnsupportedJobError("RESEARCH jobs support only the RESEARCH workflow.")
        if job.topic_id is None:
            raise PayloadValidationError("RESEARCH job requires topic_id.")
        is_offline_evidence = job.payload.get("execution") == OFFLINE_EVIDENCE_EXECUTION
        is_controlled_fetch = job.payload.get("execution") == CONTROLLED_FETCH_EXECUTION
        if job.run_id is not None and not (is_offline_evidence or is_controlled_fetch):
            raise PayloadValidationError("RESEARCH worker accepts only a job without a prior run_id.")
        dry_keys = {"account_id", "topic_id", "dry_run"}
        real_keys = {
            "account_id", "topic_id", "dry_run", "execution", "mode", "max_cost_usd",
            "execution_intent",
        }
        controlled_real_keys = real_keys | {"controlled_session"}
        offline_evidence_keys = {
            "account_id", "topic_id", "dry_run", "execution", "execution_intent",
        }
        controlled_fetch_keys = offline_evidence_keys
        if set(job.payload) not in (
            dry_keys, real_keys, controlled_real_keys, offline_evidence_keys,
            controlled_fetch_keys,
        ):
            raise PayloadValidationError("RESEARCH payload contains unsupported fields.")
        if job.payload["account_id"] != job.account_id or job.payload["topic_id"] != job.topic_id:
            raise PayloadValidationError("RESEARCH payload account_id/topic_id must match the job.")
        is_real = job.payload["dry_run"] is False
        if not is_real and job.payload["dry_run"] is not True:
            raise PayloadValidationError("RESEARCH payload dry_run must be boolean.")
        if is_controlled_fetch:
            try:
                normalized_fetch = canonicalize_controlled_fetch_payload(job.payload)
            except ControlledFetchIntentError as exc:
                raise PayloadValidationError("RESEARCH controlled fetch intent is invalid.") from exc
            if (
                normalized_fetch["account_id"] != job.account_id
                or normalized_fetch["topic_id"] != job.topic_id
                or not is_real
            ):
                raise PayloadValidationError(
                    "RESEARCH controlled fetch intent does not match job identity or mode."
                )
        if is_offline_evidence:
            try:
                normalized_offline = canonicalize_offline_evidence_payload(job.payload)
            except OfflineEvidenceIntentError as exc:
                raise PayloadValidationError("RESEARCH offline evidence intent is invalid.") from exc
            if (
                normalized_offline["account_id"] != job.account_id
                or normalized_offline["topic_id"] != job.topic_id
                or is_real
            ):
                raise PayloadValidationError(
                    "RESEARCH offline evidence intent does not match job identity or mode."
                )
        if is_real and not is_controlled_fetch and (
            job.payload.get("execution") != "durable_provider_v2"
        ):
            raise PayloadValidationError("RESEARCH real payload is not a durable single-attempt contract.")
        if is_real and not is_controlled_fetch:
            try:
                normalized = canonicalize_durable_research_payload(job.payload)
                intent_raw = normalized["execution_intent"]
                assert isinstance(intent_raw, dict)
                intent = DurableResearchExecutionIntent.from_payload(intent_raw)
            except DurableExecutionIntentError as exc:
                raise PayloadValidationError("RESEARCH real payload intent is invalid.") from exc
            if intent.account_id != job.account_id or intent.topic_id != job.topic_id:
                raise PayloadValidationError("RESEARCH real payload intent does not match job identity.")
            controlled = normalized.get("controlled_session")
            if controlled is not None:
                assert isinstance(controlled, dict)
                if (
                    controlled["expected_job_id"] != job.id
                    or controlled["worker_execution_token"] != lease_owner
                ):
                    raise PayloadValidationError(
                        "Controlled-live session fence does not own this worker execution."
                    )
        topic = next(
            (candidate for candidate in self._storage.list_topics(job.account_id)
             if candidate.id == job.topic_id),
            None,
        )
        if topic is None:
            raise PayloadValidationError("RESEARCH job topic is unavailable for its account.")
        return topic, is_real
