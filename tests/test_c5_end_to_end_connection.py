from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from datetime import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.clock import FixedClock
from app.content.controlled_entrypoint import (
    ControlledArticleAuthority,
    run_controlled_article,
)
from app.content.foundation import ContentStatus
from app.llm.base import Usage
from app.llm.base import TOPIC_CRITERIA
from app.llm.anthropic_client import AnthropicLLMClient
from app.model_routing.catalogue import OPUS_5
from app.model_routing.contracts import (
    LogicalModelRole,
    ModelFamily,
    RoutingError,
    candidate_eligibility_reasons,
)
from app.model_routing.qualification import (
    QualificationApproval,
    QualificationProbeResponse,
    QualificationProbeUsage,
)
from app.model_routing.role_activation import (
    ExactRoleActivationRequest,
    activate_and_bind_exact_role,
)
from app.model_routing.role_bootstrap import owner_approved_role_policy
from app.models import (
    Job,
    JobKind,
    JobStatus,
    ExecutionResolution,
    FinancialResolution,
    ProviderAttemptStatus,
    ResearchRunStatus,
    RunStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.controlled_fetch import UrlPolicyDecision
from app.ports.fetch import FetchedDocument
from app.ports.source_discovery import (
    SourceDiscoveryCandidate,
    SourceDiscoveryRequest,
    SourceDiscoveryResponse,
)
from app.research.corpus_packer import CorpusDocument, CorpusPackingError, pack_research_corpus
from app.research.anthropic_source_discovery import (
    AnthropicSourceDiscoveryPort,
    is_controlled_fetch_candidate,
)
from app.research.source_discovery_intent import (
    SOURCE_DISCOVERY_EXECUTION,
    SourceDiscoveryIntent,
)
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.scheduling import EditorialWindow, SchedulingPolicy
import app.scheduler.dispatcher as dispatcher_module
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from app.topics.durable_intent import (
    TOPIC_GENERATION_EXECUTION,
    DurableTopicGenerationIntent,
    topic_generation_idempotency_key,
    topic_generation_job_id,
)
from app.workflows.research.controlled_fetch import run_controlled_fetch
from tests.test_b3_production_reviewer import ReviewerTransport, WriterTransport
from tests.test_prec5_verified_catalogue_live_root import _activate_article_roles

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _open_flags(storage):
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", True),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="c5 connection", now=NOW)


def _official_research_authority(storage):
    storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_RESEARCH), now=NOW,
    )
    registered = storage.register_owner_verified_catalogue(
        (OPUS_5,), verified_by="owner:test", now=NOW,
    )[0]
    approval = QualificationApproval(
        approval_ref="qual-approval-research-32k",
        request_id="qual-research-32k",
        logical_role=LogicalModelRole.ARTICLE_RESEARCH,
        model_registry_id=registered.registry_id,
        provider="ANTHROPIC",
        technical_model_id="claude-opus-5",
        pricing_ref=OPUS_5.default_pricing_ref,
        max_input_tokens=23_808,
        max_output_tokens=8_192,
        cap_usd=Decimal("1.000000"),
        approved_by="owner:test",
        approved_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        require_source_discovery=True,
    )
    storage.record_model_qualification_approval(approval, now=NOW)
    outcome = storage.execute_controlled_qualification(
        approval,
        caller=lambda _approval: QualificationProbeResponse(
            returned_model_id="claude-opus-5",
            structured_response_ok=True,
            source_discovery_ok=True,
            usage=QualificationProbeUsage(
                input_tokens=100, output_tokens=100, web_search_requests=1,
            ),
        ),
        now=NOW,
    )
    assert outcome.outcome == "PASS"
    return activate_and_bind_exact_role(
        storage,
        ExactRoleActivationRequest(
            role=LogicalModelRole.ARTICLE_RESEARCH,
            intent_kind="test-research-authority",
            intent_id="test-research-authority-1",
        ),
        now=NOW,
    )


class _FakeDiscoveryPort:
    def __init__(self):
        self.calls: list[SourceDiscoveryRequest] = []

    def discover(self, request: SourceDiscoveryRequest) -> SourceDiscoveryResponse:
        self.calls.append(request)
        return SourceDiscoveryResponse(
            candidates=tuple(
                SourceDiscoveryCandidate(
                    canonical_url=f"https://source{index}.example/report",
                    canonical_source_identity=f"source:{index}",
                    title=f"Source {index}",
                    result_identity=f"fake-result:{index}",
                    observed_at=NOW.isoformat(),
                )
                for index in range(1, 4)
            ),
            returned_model_id="claude-opus-5",
            request_id="fake-provider-search-request",
            usage=Usage(input_tokens=100, output_tokens=100, web_search_requests=1),
            port_name="fake-structured-search-v1",
        )


class _FakeApprovedFetch:
    def __init__(self, url: str):
        self.url = url
        self.calls = 0

    def preflight_boundary(self):
        return UrlPolicyDecision.ok()

    def fetch(self, url: str):
        assert url == self.url
        self.calls += 1
        body = (
            "Independent source evidence says supermarket route design follows "
            "commercial placement agreements and measured shopper exposure. "
            f"This independently published record is identified by {url}."
        )
        return FetchedDocument(
            requested_url=url, final_url=url, fetched_at=NOW,
            http_status=200, content_type="text/plain",
            body=body.encode("utf-8"), error=None,
        )


def test_official_32k_qualification_activates_exact_research_and_persists(
    storage, settings,
):
    binding = _official_research_authority(storage)
    assert binding.technical_model_id == "claude-opus-5"
    assert binding.provider == "ANTHROPIC"
    reopened = SqliteStorage.open(settings.db_path)
    try:
        persisted = reopened.get_frozen_model_binding(
            intent_kind="test-research-authority",
            intent_id="test-research-authority-1",
        )
        assert persisted == binding
    finally:
        reopened.close()


def test_source_discovery_requires_32k_search_capability(storage):
    storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.ARTICLE_RESEARCH), now=NOW,
    )
    registered = storage.register_owner_verified_catalogue(
        (OPUS_5,), verified_by="owner:test", now=NOW,
    )[0]
    approval = QualificationApproval(
        approval_ref="qual-approval-no-search",
        request_id="qual-no-search",
        logical_role=LogicalModelRole.ARTICLE_RESEARCH,
        model_registry_id=registered.registry_id,
        provider="ANTHROPIC", technical_model_id="claude-opus-5",
        pricing_ref=OPUS_5.default_pricing_ref,
        max_input_tokens=23_808, max_output_tokens=8_192,
        cap_usd=Decimal("1.000000"), approved_by="owner:test",
        approved_at=NOW.isoformat(), expires_at=(NOW + timedelta(hours=1)).isoformat(),
        require_source_discovery=True,
    )
    storage.record_model_qualification_approval(approval, now=NOW)
    outcome = storage.execute_controlled_qualification(
        approval,
        caller=lambda _approval: QualificationProbeResponse(
            returned_model_id="claude-opus-5", structured_response_ok=True,
            source_discovery_ok=False,
            usage=QualificationProbeUsage(
                input_tokens=100, output_tokens=100, web_search_requests=1,
            ),
        ), now=NOW,
    )
    assert outcome.outcome == "FAIL"
    with pytest.raises(RoutingError, match="ROLE_ACTIVATION_BLOCKED"):
        activate_and_bind_exact_role(
            storage,
            ExactRoleActivationRequest(
                role=LogicalModelRole.ARTICLE_RESEARCH,
                intent_kind="blocked", intent_id="blocked",
            ), now=NOW,
        )


def test_article_research_rejects_sonnet_other_opus_and_16k_capability(storage):
    _official_research_authority(storage)
    active = storage.get_active_model_for_role(LogicalModelRole.ARTICLE_RESEARCH)
    assert active is not None and active.pricing_ref is not None
    policy = owner_approved_role_policy(LogicalModelRole.ARTICLE_RESEARCH)
    pricing = storage.get_model_pricing_profile(active.pricing_ref)
    capability = storage._model_capability_for(active)
    assert "FAMILY_NOT_ALLOWED" in candidate_eligibility_reasons(
        policy=policy,
        model=replace(active, family=ModelFamily.SONNET, technical_model_id="claude-sonnet-5"),
        pricing=pricing,
        capability=capability,
    )
    assert "TECHNICAL_MODEL_NOT_ALLOWED" in candidate_eligibility_reasons(
        policy=policy,
        model=replace(active, technical_model_id="claude-opus-4"),
        pricing=pricing,
        capability=capability,
    )

    # A real lifecycle result may PASS its own smaller probe and still be
    # ineligible for the owner-approved 32k/8192 role envelope.
    approval = QualificationApproval(
        approval_ref="qual-approval-research-16k",
        request_id="qual-research-16k",
        logical_role=LogicalModelRole.ARTICLE_RESEARCH,
        model_registry_id=active.registry_id,
        provider="ANTHROPIC",
        technical_model_id="claude-opus-5",
        pricing_ref=active.pricing_ref,
        max_input_tokens=13_952,
        max_output_tokens=2_048,
        cap_usd=Decimal("1.000000"),
        approved_by="owner:test",
        approved_at=NOW.isoformat(),
        expires_at=(NOW + timedelta(hours=1)).isoformat(),
        require_source_discovery=True,
    )
    storage.record_model_qualification_approval(approval, now=NOW)
    outcome = storage.execute_controlled_qualification(
        approval,
        caller=lambda _approval: QualificationProbeResponse(
            returned_model_id="claude-opus-5",
            structured_response_ok=True,
            source_discovery_ok=True,
            usage=QualificationProbeUsage(
                input_tokens=100, output_tokens=100, web_search_requests=1,
            ),
        ),
        now=NOW,
    )
    assert outcome.outcome == "PASS"
    with pytest.raises(RoutingError, match="ROLE_ACTIVATION_BLOCKED"):
        activate_and_bind_exact_role(
            storage,
            ExactRoleActivationRequest(
                role=LogicalModelRole.ARTICLE_RESEARCH,
                intent_kind="research-16k-blocked",
                intent_id="research-16k-blocked",
            ),
            now=NOW,
        )


def test_production_discovery_ignores_free_text_urls_and_accepts_structured_results():
    class Messages:
        response: object

        def create(self, **_kwargs):
            return self.response

    messages = Messages()
    client = SimpleNamespace(messages=messages)
    port = AnthropicSourceDiscoveryPort(
        api_key="fake", model="claude-opus-5",
        sdk_factory=lambda _api_key: client, now=lambda: NOW,
    )
    request = SourceDiscoveryRequest(
        account_id="account", topic_id=1, research_run_id="run",
        query="question", max_results=3,
    )
    messages.response = SimpleNamespace(
        id="provider-request-text-only", model="claude-opus-5",
        content=[{"type": "text", "text": "Use https://untrusted.example/from-text"}],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
    )
    with pytest.raises(ValueError, match="no controlled-fetch-compatible results"):
        port.discover(request)

    messages.response = SimpleNamespace(
        id="provider-request-structured", model="claude-opus-5",
        content=[{
            "type": "web_search_tool_result",
            "content": [{
                "type": "web_search_result",
                "url": "HTTPS://AUTHORITATIVE.EXAMPLE/report#fragment",
                "title": "Authoritative report",
            }],
        }],
        usage=SimpleNamespace(
            input_tokens=10, output_tokens=5,
            server_tool_use=SimpleNamespace(web_search_requests=1),
        ),
    )
    response = port.discover(request)
    assert len(response.candidates) == 1
    assert response.candidates[0].canonical_url == "https://authoritative.example/report"
    assert response.candidates[0].canonical_source_identity.startswith("url-sha256:")
    assert not is_controlled_fetch_candidate("https://www.sciencedirect.com/article/123")
    assert not is_controlled_fetch_candidate("https://arxiv.org/pdf/1234.5678")
    assert is_controlled_fetch_candidate("https://www.transit.dot.gov/research/bus-service")


def test_typed_a1_timeout_is_fenced_for_reconciliation(
    settings, storage, account,
):
    storage.ensure_account(account)
    _official_research_authority(storage)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="A1 timeout boundary",
        question="Which dependencies fail first?",
        status=TopicStatus.SELECTED,
        source="TEST",
        created_at=NOW,
    ))
    assert topic.id is not None
    intent = SourceDiscoveryIntent.build(account_id=account.id, topic_id=topic.id)
    job = storage.enqueue_job(Job(
        id=f"source-discovery-timeout-{topic.id}",
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"source-discovery-timeout:{topic.id}",
        topic_id=topic.id,
        payload={
            "account_id": account.id,
            "topic_id": topic.id,
            "dry_run": False,
            "execution": SOURCE_DISCOVERY_EXECUTION,
            "execution_intent": intent.as_payload(),
        },
        schedule_reason="SAFETY_OPERATION_IMMEDIATE",
        earliest_run_at=NOW,
        max_attempts=1,
        created_at=NOW,
    ))
    storage.record_source_discovery_approval(
        job_id=job.id,
        account_id=account.id,
        approved_by="owner:test",
        expires_at=NOW + timedelta(hours=1),
        clock=FixedClock(NOW),
    )
    _open_flags(storage)

    class TimeoutPort:
        def discover(self, _request):
            raise TimeoutError("provider response exceeded the client timeout")

    real = replace(
        settings,
        dry_run=False,
        anthropic_api_key="test-only",
        model_quality="claude-opus-5",
    )
    policy = PolicyEngine(real, storage, FixedClock(NOW))
    dispatcher = JobDispatcher(
        settings=real,
        storage=storage,
        policy=policy,
        clock=FixedClock(NOW),
        source_discovery_port_factory=lambda _settings, _intent: TimeoutPort(),
    )
    worker = Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner="a1-timeout-worker",
        target_job_id=job.id,
        lease_seconds=120,
        heartbeat_interval_seconds=5,
        heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=FixedClock(NOW),
    )

    outcome = worker.run_once()

    assert outcome.status is WorkerIterationStatus.NEEDS_VERIFICATION
    durable = storage.get_job(job.id)
    assert durable is not None
    assert durable.status is JobStatus.NEEDS_VERIFICATION
    assert durable.lease_owner is None
    assert storage.get_run(durable.run_id).status is RunStatus.RUNNING
    assert (
        storage.get_research_run(durable.run_id).status
        is ResearchRunStatus.DISCOVERY_PENDING
    )
    attempt = storage.conn.execute(
        "SELECT status,error_code FROM provider_attempts WHERE job_id=?",
        (job.id,),
    ).fetchone()
    assert tuple(attempt) == (
        ProviderAttemptStatus.NEEDS_RECONCILIATION.value,
        "SOURCE_DISCOVERY_PROVIDER_OUTCOME_UNKNOWN",
    )
    assert storage.conn.execute(
        "SELECT count(*) FROM model_usage WHERE run_id=?", (durable.run_id,),
    ).fetchone()[0] == 0

    preview = storage.preview_provider_attempt_reconciliation(
        request_id=f"{job.id}:research_discover:1",
        account_id=account.id,
    )
    resolution = storage.resolve_provider_attempt_reconciliation(
        request_id=preview.request_id,
        account_id=account.id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None,
        reconciled_by="owner:test",
        note="Test provider evidence confirms that the timed-out request was not charged.",
        expected_version_token=preview.version_token,
    )
    assert resolution.attempt.status is ProviderAttemptStatus.RECONCILED_RELEASED
    assert storage.get_job(job.id).status is JobStatus.FAILED
    assert storage.get_run(durable.run_id).status is RunStatus.FAILED
    assert storage.get_research_run(durable.run_id).status is ResearchRunStatus.FAILED


def test_typed_a1_worker_persists_only_structured_candidates(
    settings, storage, account, monkeypatch,
):
    storage.ensure_account(account)
    # ARTICLE_PLAN/WRITER/REVIEWER use their existing controlled lifecycle.
    # The new 32k qualification is deliberately last: it is the current model
    # capability used by both ARTICLE_RESEARCH and the exact TOPIC binding.
    _activate_article_roles(storage, now=NOW)
    _official_research_authority(storage)
    storage.upsert_model_role_policy(
        owner_approved_role_policy(LogicalModelRole.TOPIC_GENERATION), now=NOW,
    )
    topic_binding = activate_and_bind_exact_role(
        storage,
        ExactRoleActivationRequest(
            role=LogicalModelRole.TOPIC_GENERATION,
            intent_kind="topic_generation_provider",
            intent_id="c5-e2e-topic-generation",
        ),
        now=NOW,
    )
    assert topic_binding.provider == "ANTHROPIC"
    assert topic_binding.technical_model_id == "claude-opus-5"

    real = replace(
        settings, dry_run=False, anthropic_api_key="test-only",
        model_quality="claude-opus-5",
    )
    pricing = storage.get_model_pricing_profile(topic_binding.pricing_ref)
    assert pricing is not None and pricing.prices is not None
    topic_intent = DurableTopicGenerationIntent.from_settings(
        settings=replace(real, project_root=Path(__file__).resolve().parents[1]),
        account_id=account.id,
        cap_usd=Decimal("1.000000"),
        candidate_count=1,
        niche=account.niche or ["hidden everyday systems"],
        model="claude-opus-5",
        max_tokens=1500,
        score_dimensions=sorted(TOPIC_CRITERIA),
        pricing_prices=pricing.prices.as_decimal_mapping(),
        pricing_profile_id=pricing.pricing_ref,
        pricing_profile_version=pricing.contract_fingerprint(),
        pricing_currency=pricing.currency,
        pricing_unit=pricing.unit,
    )
    operation_key = "c5-e2e-topic-to-pending-approval"
    scheduled = ScheduledJobEnqueuer(
        storage=storage,
        scheduling_policy=SchedulingPolicy(
            timezone_name="UTC",
            windows=(EditorialWindow(
                weekdays=frozenset(range(7)), start=time(0, 0), end=time(23, 59),
            ),),
        ),
        clock=FixedClock(NOW),
    ).enqueue(ScheduledJobRequest(
        id=topic_generation_job_id(operation_key),
        account_id=account.id,
        kind=JobKind.TOPIC_GENERATION,
        workflow=WorkflowType.TOPIC_GENERATION,
        idempotency_key=topic_generation_idempotency_key(operation_key),
        payload={
            "account_id": account.id,
            "dry_run": False,
            "execution": TOPIC_GENERATION_EXECUTION,
            "mode": "single",
            "max_cost_usd": topic_intent.cap_usd,
            "execution_intent": topic_intent.as_payload(),
        },
        max_attempts=1,
    ))
    topic_job = scheduled.job
    storage.record_topic_generation_approval(
        job_id=topic_job.id, account_id=account.id, approved_by="owner:test",
        expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
    )
    _open_flags(storage)

    class FakeTopicCaller:
        calls = 0

        def __call__(self, _account, count):
            self.calls += 1
            assert count == 1
            return json.dumps({"topics": [{
                "title": "Who designed supermarket routes?",
                "question": "Who designed supermarket routes?",
                "score_breakdown": {
                    dimension: 0.95 for dimension in sorted(TOPIC_CRITERIA)
                },
            }]}), Usage(input_tokens=120, output_tokens=90)

    fake_topic = FakeTopicCaller()
    topic_dispatcher = JobDispatcher(
        settings=real,
        storage=storage,
        policy=PolicyEngine(real, storage, FixedClock(NOW)),
        clock=FixedClock(NOW),
        topic_generation_client_factory=lambda configured, intent: AnthropicLLMClient(
            configured.anthropic_api_key,
            intent.model,
            caller=fake_topic,
            timeout_seconds=float(intent.timeout_seconds),
            topic_max_tokens=intent.max_tokens,
        ),
    )
    topic_worker = Worker(
        storage=storage, policy=PolicyEngine(real, storage, FixedClock(NOW)),
        dispatcher=topic_dispatcher, lease_owner="topic-e2e-worker",
        target_job_id=topic_job.id, lease_seconds=120,
        heartbeat_interval_seconds=5, heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=FixedClock(NOW),
    )
    assert topic_worker.run_once().status is WorkerIterationStatus.DONE
    assert fake_topic.calls == 1
    selected = storage.conn.execute(
        "SELECT * FROM topics WHERE account_id=? AND status='SELECTED'",
        (account.id,),
    ).fetchall()
    assert len(selected) == 1
    topic = next(
        item for item in storage.list_topics_by_status(account.id, TopicStatus.SELECTED)
        if item.id == int(selected[0]["id"])
    )
    job = storage.get_job(f"source-discovery-{int(topic.id)}")
    assert job is not None
    storage.record_source_discovery_approval(
        job_id=job.id, account_id=account.id, approved_by="owner:test",
        expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
    )
    fake = _FakeDiscoveryPort()
    policy = PolicyEngine(real, storage, FixedClock(NOW))
    dispatcher = JobDispatcher(
        settings=real, storage=storage, policy=policy, clock=FixedClock(NOW),
        source_discovery_port_factory=lambda _settings, _intent: fake,
    )
    worker = Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner="a1-worker", target_job_id=job.id, lease_seconds=120,
        heartbeat_interval_seconds=5,
        heartbeat_startup_timeout_seconds=2,
        heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=FixedClock(NOW),
    )
    assert worker.run_once().status is WorkerIterationStatus.DONE
    assert len(fake.calls) == 1
    rows = storage.conn.execute(
        "SELECT * FROM research_source_candidates ORDER BY canonical_source_identity"
    ).fetchall()
    assert len(rows) == 3
    assert all(row["discovery_job_id"] == job.id for row in rows)
    assert all(row["discovery_result_identity"] for row in rows)
    usage = storage.conn.execute(
        "SELECT * FROM model_usage WHERE run_id=?", (storage.get_job(job.id).run_id,),
    ).fetchall()
    assert len(usage) == 1
    assert usage[0]["web_search_requests"] == 1
    assert storage.conn.execute(
        "SELECT cost_usd FROM runs WHERE id=?", (storage.get_job(job.id).run_id,),
    ).fetchone()[0] == usage[0]["estimated_cost_usd"]

    # Each typed candidate receives its own L1.  The approval atomically creates
    # exactly one controlled-fetch job; the existing worker/dispatcher and
    # producer path then create canonical retrievals.  The third success
    # automatically enqueues the packed ARTICLE_RESEARCH job.
    for index, row in enumerate(rows, start=1):
        fetch_job_id = storage.approve_source_candidate_fetch(
            candidate_id=int(row["id"]), approved_by="owner:test",
            expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
        )
        fake_fetch = _FakeApprovedFetch(str(row["url"]))

        def controlled_runner(account_obj, topic_obj, **kwargs):
            return run_controlled_fetch(
                account_obj, topic_obj, **kwargs,
                fetch_port_factory=lambda _authorization, **_ignored: fake_fetch,
            )

        fetch_dispatcher = JobDispatcher(
            settings=real, storage=storage, policy=policy, clock=FixedClock(NOW),
            research_controlled_fetch=controlled_runner,
        )
        fetch_worker = Worker(
            storage=storage, policy=policy, dispatcher=fetch_dispatcher,
            lease_owner=f"fetch-worker-{index}", target_job_id=fetch_job_id,
            lease_seconds=120, heartbeat_interval_seconds=5,
            heartbeat_startup_timeout_seconds=2, heartbeat_shutdown_timeout_seconds=2,
            heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
            clock=FixedClock(NOW),
        )
        assert fetch_worker.run_once().status is WorkerIterationStatus.DONE
        assert fake_fetch.calls == 1

    evidence_job = storage.get_job(f"article-research-evidence-{int(topic.id)}")
    assert evidence_job is not None
    assert evidence_job.payload["execution"] == "durable_provider_v2"
    frozen = evidence_job.payload["execution_intent"]
    assert frozen["max_tokens"] == 4096
    assert frozen["max_web_searches"] == 0
    assert len(frozen["evidence_input"]["retrievals"]) == 3

    storage.record_evidence_research_approval(
        job_id=evidence_job.id, account_id=account.id, approved_by="owner:test",
        expires_at=NOW + timedelta(hours=1), clock=FixedClock(NOW),
    )
    claim = "Commercial placement agreements shape the route shoppers follow."
    excerpt = (
        "supermarket route design follows commercial placement agreements and "
        "measured shopper exposure"
    )

    class FakeEvidenceCaller:
        calls = 0

        def __call__(self, _plan, contract):
            self.calls += 1
            return json.dumps({
                "question": topic.question,
                "working_thesis": "Commercial incentives shape the path.",
                "main_mechanism": "Placement agreements allocate exposure.",
                "confirmed_claims": [claim],
                "uncertain_claims": [],
                "contradictions": [],
                "strongest_counterargument": "Convenience also affects placement.",
                "citable_numbers": [],
                "visual_idea": "A store route map.",
                "confidence_score": 0.92,
                "source_quality_score": 0.91,
                "sources": [
                    {
                        "url": document.url,
                        "title": f"Evidence {idx}",
                        "author_or_org": f"Independent Org {idx}",
                        "published_at": None,
                        "source_type": "PRIMARY" if idx == 1 else "SECONDARY",
                        "supports_claim": claim,
                        "supporting_excerpt": excerpt,
                    }
                    for idx, document in enumerate(contract.documents, start=1)
                ],
            }), Usage(input_tokens=300, output_tokens=250), "end_turn"

    fake_research = FakeEvidenceCaller()
    from app.research.anthropic_client import AnthropicResearchClient

    monkeypatch.setattr(
        dispatcher_module, "AnthropicResearchClient",
        lambda *args, **kwargs: AnthropicResearchClient(
            *args, evidence_caller=fake_research, **kwargs,
        ),
    )
    research_dispatcher = JobDispatcher(
        settings=real, storage=storage, policy=policy, clock=FixedClock(NOW),
    )
    research_worker = Worker(
        storage=storage, policy=policy, dispatcher=research_dispatcher,
        lease_owner="evidence-research-worker", target_job_id=evidence_job.id,
        lease_seconds=120, heartbeat_interval_seconds=5,
        heartbeat_startup_timeout_seconds=2, heartbeat_shutdown_timeout_seconds=2,
        heartbeat_storage_factory=lambda: SqliteStorage.open(real.db_path),
        clock=FixedClock(NOW),
    )
    assert research_worker.run_once().status is WorkerIterationStatus.DONE
    assert fake_research.calls == 1
    research_run_id = storage.get_job(evidence_job.id).run_id
    research_row = storage.conn.execute(
        "SELECT research_card_id FROM research_runs WHERE id=?", (research_run_id,),
    ).fetchone()
    card_id = int(research_row["research_card_id"])
    card = storage.get_research_card(card_id)
    assert card.publication_recommendation.value == "PROCEED", card.rejection_reason
    lineage = storage.conn.execute(
        "SELECT * FROM evidence_source_lineage WHERE research_card_id=?", (card_id,),
    ).fetchall()
    assert len(lineage) == 3
    assert len({row["retrieval_id"] for row in lineage}) == 3
    research_usage = storage.conn.execute(
        "SELECT sum(estimated_cost_usd) AS total FROM model_usage WHERE run_id=?",
        (research_run_id,),
    ).fetchone()["total"]
    research_cost = storage.conn.execute(
        "SELECT cost_usd FROM runs WHERE id=?", (research_run_id,),
    ).fetchone()["cost_usd"]
    assert research_cost == research_usage

    # The actual controlled C5 composition root opens the same temporary DB,
    # prepares from this card, freezes independent Writer and Reviewer bindings,
    # consumes one job-scoped L1, then runs through worker + dispatcher + the
    # nine deterministic quality checks.  Only the two FINAL transports are fake.
    writer = WriterTransport()
    reviewer = ReviewerTransport()
    content_job_id = "c5-e2e-controlled-article"
    content_result = run_controlled_article(
        settings=replace(real, project_root=Path(__file__).resolve().parents[1]),
        account_id=account.id,
        research_card_id=card_id,
        idempotency_key=content_job_id,
        authority=ControlledArticleAuthority(
            job_id=content_job_id,
            approval_ref="approval-c5-e2e-controlled-article",
            approved_by="owner:test",
            approved_at=NOW.isoformat(),
            expires_at=(NOW + timedelta(hours=1)).isoformat(),
            cost_ceiling_usd=Decimal("1.000000"),
        ),
        api_key_provider=lambda: "fake-key-at-final-boundary",
        sdk_factory=lambda **_kwargs: object(),
        caller=writer,
        reviewer_sdk_factory=lambda **_kwargs: object(),
        reviewer_caller=reviewer,
        clock=FixedClock(NOW),
        lease_owner="c5-e2e-content-worker",
    )
    assert content_result.worker.status is WorkerIterationStatus.DONE
    assert writer.calls == 1
    assert reviewer.calls == 1
    content_state = storage.get_content_pipeline_state(content_job_id)
    assert ContentStatus(content_state["content"]["status"]) is ContentStatus.PENDING_APPROVAL
    assert len(content_state["evaluations"]) == 9
    assert {row["result"] for row in content_state["evaluations"]} == {"PASS"}
    assert len(content_state["attempts"]) == 1
    content_run_id = str(content_state["content"]["run_id"])
    content_usage = sum(
        Decimal(str(row["estimated_cost_usd"]))
        for row in storage.conn.execute(
            "SELECT estimated_cost_usd FROM model_usage WHERE run_id=?",
            (content_run_id,),
        ).fetchall()
    )
    assert Decimal(str(storage.get_run(content_run_id).cost_usd)) == content_usage
    publication = storage.conn.execute(
        "SELECT published_at,external_url FROM content_items WHERE id=?",
        (content_result.content_id,),
    ).fetchone()
    assert publication["published_at"] is None
    assert publication["external_url"] is None


def test_corpus_packer_is_stable_whole_document_and_fail_closed():
    documents = [
        CorpusDocument(index, f"source:{4-index}", f"{index:064x}", 1000, "x" * 1000)
        for index in range(1, 4)
    ]
    packed = pack_research_corpus(documents)
    assert [item.source_identity for item in packed.documents] == [
        "source:1", "source:2", "source:3",
    ]
    assert packed.estimated_input_tokens <= 23_808
    assert packed.context_tokens <= 32_000
    with pytest.raises(CorpusPackingError):
        pack_research_corpus(documents[:2])
    oversized = [
        CorpusDocument(
            index, f"oversized:{index}", f"{index + 10:064x}",
            100_000, "x" * 100_000,
        )
        for index in range(1, 4)
    ]
    with pytest.raises(CorpusPackingError):
        pack_research_corpus(oversized)
