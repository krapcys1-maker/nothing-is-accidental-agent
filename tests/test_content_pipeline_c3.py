"""WAVE C3 provider-ready writer tests; all callers and SDKs are fake."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from app.content.contracts import (
    RouteContract,
    WriterFailureKind,
    WriterLimits,
    WriterUsage,
)
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline as _run_offline_content_pipeline
from app.content.routing import (
    MissingContentWriterConfiguration,
    default_content_routing_path,
    load_content_route,
    resolve_provider_route,
)
from app.content.writer import (
    FakeContentWriter,
    FakeWriterScenario,
    ProviderRawResponse,
    ProviderReadyContentWriter,
)
from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import JobStatus, ModelUsage, ProviderAttemptStatus
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import StaleJobExecutionError
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.db import (
    CONTENT_PIPELINE_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    CONTENT_DECISION_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    VERIFIED_CATALOGUE_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    apply_migrations,
    connect,
    database_schema_versions,
    initialize_database,
    migrate_0022_to_0023,
    migrate_0023_to_0024,
    migrate_0024_to_0025,
    migrate_0025_to_0026,
    migrate_0026_to_0027,
    migrate_0027_to_0028,
    migrate_0028_to_0029,
    migrate_0029_to_0030,
    migrate_0030_to_0031,
    migrate_0031_to_0032,
    migrate_0032_to_0033,
    migrate_0033_to_0034,
    migrate_0034_to_0035,
    migrate_0035_to_0036,
    migrate_0036_to_0037,
    migrate_0037_to_0038,
)
from app.storage.repositories import SqliteStorage
from tests.c2_fixtures import seed_c2_research
from tests.claim_accounting_fakes import (
    FakeClaimAccountingReviewer,
    ground_every_segment_in_package,
)


NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def run_offline_content_pipeline(*args, **kwargs):
    """C3 regression adapter supplies the now-mandatory C4 PolicyEngine."""
    storage = kwargs["storage"]
    kwargs.setdefault(
        "policy",
        PolicyEngine(
            Settings(
                project_root=ROOT,
                data_dir=ROOT,
                db_path=ROOT / "unused-test.db",
                costs_csv_path=ROOT / "unused-test-costs.csv",
            ),
            storage,
            kwargs["clock"],
        ),
    )
    kwargs.setdefault(
        "claim_reviewer",
        FakeClaimAccountingReviewer(decide=ground_every_segment_in_package),
    )
    return _run_offline_content_pipeline(*args, **kwargs)


def configured_route(
    content_type: ContentType,
    *,
    provider: str = "anthropic",
    model: str | None = None,
    pricing: str = "test-zero-pricing",
    availability: str = "CONFIGURED",
) -> RouteContract:
    return RouteContract(
        content_type=content_type,
        route_key=(
            "FABLE_5_ARTICLE"
            if content_type is ContentType.ARTICLE else "SONNET_5_NOTE"
        ),
        logical_model_name=(
            "Fable 5" if content_type is ContentType.ARTICLE else "Sonnet 5"
        ),
        config_version="c3-test-v1",
        config_fingerprint=("a" if content_type is ContentType.ARTICLE else "b") * 64,
        provider=provider,
        api_model_id=model or f"test-{content_type.value.lower()}-model",
        availability=availability,
        pricing_profile=pricing,
    )


def provider_limits() -> dict[ContentType, WriterLimits]:
    return {
        ContentType.ARTICLE: WriterLimits(
            max_input_tokens=8_000,
            max_context_tokens=16_000,
            max_output_tokens=2_048,
            max_cost_usd=0.0,
            timeout_seconds=5.0,
        ),
        ContentType.NOTE: WriterLimits(
            max_input_tokens=4_000,
            max_context_tokens=8_000,
            max_output_tokens=512,
            max_cost_usd=0.0,
            timeout_seconds=5.0,
        ),
    }


class FakeSdkFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return object()


class ScriptedCaller:
    def __init__(
        self,
        scenario: FakeWriterScenario = FakeWriterScenario.PASS,
        *,
        raw_text: str | None = None,
        stop_reason: str = "end_turn",
        error: Exception | None = None,
    ) -> None:
        self.fake = FakeContentWriter(scenario)
        self.raw_text = raw_text
        self.stop_reason = stop_reason
        self.error = error
        self.calls = 0

    def __call__(self, _client, _prompt, request):
        self.calls += 1
        if self.error is not None:
            raise self.error
        draft = self.fake.write(request).draft
        text = self.raw_text
        if text is None:
            text = json.dumps({
                "title": draft.title,
                "body": draft.body,
                "evidence_ids_used": list(draft.evidence_ids_used),
                "unsupported_claims": list(draft.unsupported_claims),
                "personal_experience": draft.personal_experience,
                "style_ok": draft.style_ok,
                "brief_compliant": draft.brief_compliant,
            })
        return ProviderRawResponse(
            text=text,
            usage=WriterUsage(
                input_tokens=100,
                output_tokens=200,
                estimated_cost_usd=0.0,
            ),
            stop_reason=self.stop_reason,
            provider_request_id=f"fake-provider-request-{self.calls}",
            api_model_id=request.intent.route.api_model_id,
        )


def provider_writer(
    caller: ScriptedCaller,
    *,
    factory: FakeSdkFactory | None = None,
    secret: str | None = "test-secret",
):
    resolved_factory = factory or FakeSdkFactory()
    writer = ProviderReadyContentWriter(
        api_key_provider=lambda: secret,
        limits_by_type=provider_limits(),
        sdk_factory=resolved_factory,
        caller=caller,
    )
    return writer, resolved_factory


def prepare_and_claim(
    storage: SqliteStorage,
    seed: dict[str, object],
    content_type: ContentType,
    suffix: str,
):
    request = ContentPreparationRequest(
        job_id=f"c3-job-{suffix}",
        idempotency_key=f"c3-intent-{suffix}",
        account_id=str(seed["account_id"]),
        research_card_id=int(seed["card_id"]),
        content_type=content_type,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version=(
            "ARTICLE_STYLE_PROFILE_V1"
            if content_type is ContentType.ARTICLE
            else "NOTES_STYLE_PROFILE_V1_PROVISIONAL"
        ),
    )
    prepared = storage.prepare_content_job(request, clock=FixedClock(NOW))
    owner = f"owner-{suffix}"
    lease = storage.claim_specific_job(
        request.job_id, owner, 60, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, prepared, lease, owner


def run_provider(
    storage: SqliteStorage,
    account,
    content_type: ContentType,
    *,
    suffix: str,
    caller: ScriptedCaller | None = None,
    route: RouteContract | None = None,
    secret: str | None = "test-secret",
    fault_point=None,
):
    seed = seed_c2_research(storage, account)
    request, prepared, lease, owner = prepare_and_claim(
        storage, seed, content_type, suffix,
    )
    scripted = caller or ScriptedCaller()
    writer, factory = provider_writer(scripted, secret=secret)
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        writer=writer,
        route_override=route or configured_route(content_type),
        fault_point=fault_point,
    )
    return request, prepared, lease, summary, writer, factory, scripted


@pytest.mark.parametrize(
    ("content_type", "route_key"),
    [
        (ContentType.ARTICLE, "FABLE_5_ARTICLE"),
        (ContentType.NOTE, "SONNET_5_NOTE"),
    ],
)
def test_provider_ready_full_flows_end_at_pending_approval(
    storage, account, content_type, route_key,
):
    request, _, _, summary, writer, factory, caller = run_provider(
        storage, account, content_type, suffix=f"happy-{content_type.value}",
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.cost_usd == 0.0
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["intents"][0]["route_key"] == route_key
    assert state["intents"][0]["api_model_id"] != route_key
    assert state["attempts"][0]["provider"] == "anthropic"
    assert state["attempts"][0]["model"] != route_key
    assert state["attempts"][0]["status"] == "SETTLED"
    assert state["attempts"][0]["actual_cost_usd"] == 0.0
    assert len(state["results"]) == len(state["usages"]) == len(state["drafts"]) == 1
    assert state["results"][0]["provider_request_id"] == "fake-provider-request-1"
    assert caller.calls == writer.caller_calls == len(factory.calls) == 1
    assert factory.calls[0]["max_retries"] == 0
    assert factory.calls[0]["timeout"] == 5.0


def test_logical_routes_have_no_fallback_and_default_is_unverified():
    for content_type, key in (
        (ContentType.ARTICLE, "FABLE_5_ARTICLE"),
        (ContentType.NOTE, "SONNET_5_NOTE"),
    ):
        route = load_content_route(
            default_content_routing_path(ROOT), content_type,
        )
        assert route.route_key == key
        assert route.fallback == "FORBIDDEN"
        assert route.configuration_status == "UNVERIFIED"
        with pytest.raises(MissingContentWriterConfiguration):
            resolve_provider_route(route)


@pytest.mark.parametrize(
    ("case", "route", "secret", "expected"),
    [
        (
            "missing-model",
            configured_route(
                ContentType.ARTICLE,
                provider="anthropic",
                model="UNVERIFIED",
                availability="CONFIGURED",
            ),
            "test-secret",
            WriterFailureKind.MISSING_CONFIGURATION,
        ),
        (
            "missing-pricing",
            configured_route(ContentType.ARTICLE, pricing="UNVERIFIED"),
            "test-secret",
            WriterFailureKind.MISSING_PRICING,
        ),
        (
            "missing-secret",
            configured_route(ContentType.ARTICLE),
            None,
            WriterFailureKind.MISSING_CONFIGURATION,
        ),
        (
            "unavailable",
            configured_route(ContentType.ARTICLE, availability="UNVERIFIED"),
            "test-secret",
            WriterFailureKind.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_fail_closed_configuration_blocks_before_sdk_and_caller(
    storage, account, case, route, secret, expected,
):
    caller = ScriptedCaller()
    request, _, _, summary, _, factory, _ = run_provider(
        storage,
        account,
        ContentType.ARTICLE,
        suffix=f"config-{case}",
        caller=caller,
        route=route,
        secret=secret,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == expected.value
    assert caller.calls == 0
    assert factory.calls == []
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["attempts"] == state["results"] == state["usages"] == []


@pytest.mark.parametrize(
    ("raw_text", "stop_reason", "expected"),
    [
        ("not-json", "end_turn", WriterFailureKind.PARSE_ERROR),
        ("{}", "max_tokens", WriterFailureKind.TRUNCATION),
        ("{}", "end_turn", WriterFailureKind.SCHEMA_VALIDATION),
    ],
)
def test_parse_truncation_and_schema_failures_settle_returned_usage(
    storage, account, raw_text, stop_reason, expected,
):
    caller = ScriptedCaller(raw_text=raw_text, stop_reason=stop_reason)
    request, _, _, summary, _, _, _ = run_provider(
        storage,
        account,
        ContentType.NOTE,
        suffix=f"bad-output-{expected.value.lower()}",
        caller=caller,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == expected.value
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["attempts"][0]["status"] == "SETTLED"
    assert state["attempts"][0]["actual_cost_usd"] == 0.0
    assert len(state["results"]) == len(state["usages"]) == 1
    assert state["results"][0]["failure_kind"] == expected.value
    assert state["drafts"] == []


def test_timeout_has_no_hidden_retry_and_becomes_uncertain(storage, account):
    timeout_error = type("APITimeoutError", (Exception,), {})()
    caller = ScriptedCaller(error=timeout_error)
    request, _, _, summary, writer, factory, _ = run_provider(
        storage,
        account,
        ContentType.ARTICLE,
        suffix="timeout",
        caller=caller,
    )
    assert summary.status is ContentStatus.NEEDS_VERIFICATION
    assert summary.block_code == WriterFailureKind.TIMEOUT.value
    assert caller.calls == writer.caller_calls == len(factory.calls) == 1
    assert factory.calls[0]["max_retries"] == 0
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["attempts"][0]["status"] == "NEEDS_RECONCILIATION"
    assert state["usages"] == []


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (429, WriterFailureKind.RATE_LIMIT),
        (503, WriterFailureKind.PROVIDER_5XX),
        (401, WriterFailureKind.AUTH_PERMISSION),
        (400, WriterFailureKind.INVALID_REQUEST),
    ],
)
def test_provider_errors_are_typed_and_never_retried(
    storage, account, status_code, expected,
):
    error_type = type(f"FakeStatus{status_code}", (Exception,), {})
    error = error_type()
    error.status_code = status_code
    caller = ScriptedCaller(error=error)
    request, _, _, summary, writer, factory, _ = run_provider(
        storage,
        account,
        ContentType.NOTE,
        suffix=f"status-{status_code}",
        caller=caller,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == expected.value
    assert caller.calls == writer.caller_calls == len(factory.calls) == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["attempts"][0]["status"] == "SETTLED"
    assert state["attempts"][0]["actual_cost_usd"] == 0.0


class SimulatedCrash(RuntimeError):
    pass


def test_restart_before_caller_calls_provider_once(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, lease, owner = prepare_and_claim(
        storage, seed, ContentType.ARTICLE, "restart-before",
    )
    caller = ScriptedCaller()
    writer, _ = provider_writer(caller)

    def crash(point: str) -> None:
        if point == "BRIEF_PERSISTED":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            writer=writer,
            route_override=configured_route(ContentType.ARTICLE),
            fault_point=crash,
        )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        writer=writer,
        route_override=configured_route(ContentType.ARTICLE),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert caller.calls == 1
    assert len(storage.get_content_pipeline_state(request.job_id)["attempts"]) == 1


def test_restart_after_caller_before_result_never_calls_again(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, lease, owner = prepare_and_claim(
        storage, seed, ContentType.NOTE, "restart-after-call",
    )
    caller = ScriptedCaller()
    writer, _ = provider_writer(caller)

    def crash(point: str) -> None:
        if point == "WRITER_CALL_RETURNED":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            writer=writer,
            route_override=configured_route(ContentType.NOTE),
            fault_point=crash,
        )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        writer=writer,
        route_override=configured_route(ContentType.NOTE),
    )
    assert summary.status is ContentStatus.NEEDS_VERIFICATION
    assert summary.block_code == "CONTENT_WRITER_RESULT_UNCERTAIN"
    assert caller.calls == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["attempts"][0]["status"] == "NEEDS_RECONCILIATION"
    assert state["results"] == state["usages"] == state["drafts"] == []


def test_restart_after_result_resumes_settlement_without_second_call(
    storage, account,
):
    seed = seed_c2_research(storage, account)
    request, _, lease, owner = prepare_and_claim(
        storage, seed, ContentType.ARTICLE, "restart-after-result",
    )
    caller = ScriptedCaller()
    writer, _ = provider_writer(caller)

    def crash(point: str) -> None:
        if point == "WRITER_RESULT_PERSISTED":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=owner,
            project_root=ROOT,
            writer=writer,
            route_override=configured_route(ContentType.ARTICLE),
            fault_point=crash,
        )
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=owner,
        project_root=ROOT,
        writer=writer,
        route_override=configured_route(ContentType.ARTICLE),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert caller.calls == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["results"]) == len(state["usages"]) == 1


def test_provider_writer_allows_exactly_one_durable_rewrite(storage, account):
    caller = ScriptedCaller(FakeWriterScenario.REWRITE_THEN_PASS)
    request, _, _, summary, _, _, _ = run_provider(
        storage,
        account,
        ContentType.ARTICLE,
        suffix="rewrite-once",
        caller=caller,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert caller.calls == 2
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["attempts"]) == len(state["results"]) == 2
    assert {row["attempt_no"] for row in state["attempts"]} == {1, 2}


def test_canonical_attempt_cannot_be_settled_twice(storage, account):
    request, _, lease, summary, _, _, _ = run_provider(
        storage, account, ContentType.NOTE, suffix="double-settlement",
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    state = storage.get_content_pipeline_state(request.job_id)
    attempt = state["attempts"][0]
    with pytest.raises(StaleJobExecutionError):
        storage.add_job_model_usage(
            # The original execution is still identifiable, but the parent is settled.
            execution=type("Execution", (), {
                "run_id": summary.run_id,
                "job_id": request.job_id,
                "lease_owner": "owner-double-settlement",
                "fence_token": lease.job.execution_generation,
                "kind": lease.job.kind,
                "workflow": lease.job.workflow,
                "now": lambda self: NOW,
            })(),
            usage=ModelUsage(
                run_id=summary.run_id,
                provider=attempt["provider"],
                model=attempt["model"],
                task="content_draft",
                input_tokens=1,
                output_tokens=1,
                estimated_cost_usd=0.0,
                dry_run=True,
                request_id=attempt["request_id"],
            ),
        )
    assert len(storage.get_content_pipeline_state(request.job_id)["usages"]) == 1


def test_old_owner_cannot_write_after_takeover(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, old_lease, old_owner = prepare_and_claim(
        storage, seed, ContentType.NOTE, "old-owner",
    )
    caller = ScriptedCaller()
    writer, _ = provider_writer(caller)

    def crash(point: str) -> None:
        if point == "BRIEF_PERSISTED":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        run_offline_content_pipeline(
            old_lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=old_owner,
            project_root=ROOT,
            writer=writer,
            route_override=configured_route(ContentType.NOTE),
            fault_point=crash,
        )
    later = FixedClock(NOW + timedelta(minutes=2))
    recovery = storage.release_or_requeue_expired_leases(clock=later)
    assert recovery.requeued_count == 1
    new_lease = storage.claim_specific_job(
        request.job_id, "new-owner", 60, clock=later,
    )
    assert new_lease is not None
    with pytest.raises(StaleJobExecutionError):
        run_offline_content_pipeline(
            old_lease.job,
            storage=storage,
            clock=later,
            lease_owner=old_owner,
            project_root=ROOT,
            writer=writer,
            route_override=configured_route(ContentType.NOTE),
        )


def test_two_workers_claim_one_provider_writer_execution(
    storage, settings, account,
):
    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id="c3-concurrent",
        idempotency_key="c3-concurrent-intent",
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=ContentType.NOTE,
        execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        prompt_version="offline_content_prompt_v1",
        style_guide_version="NOTES_STYLE_PROFILE_V1_PROVISIONAL",
    )
    storage.prepare_content_job(request, clock=FixedClock(NOW))
    storage.apply_security_flag_profile(
        [
            ("worker_enabled", True),
            ("safe_mode", False),
            ("paid_actions_enabled", False),
            ("browser_actions_enabled", False),
            ("kill_switch", False),
        ],
        updated_by="test",
        reason="offline C3 concurrency",
        now=NOW,
    )
    active = replace(settings, project_root=ROOT)
    shared_caller = ScriptedCaller()
    shared_writer, _ = provider_writer(shared_caller)

    def run_one(owner: str):
        worker_storage = SqliteStorage.open(settings.db_path)
        try:
            clock = FixedClock(NOW)
            policy = PolicyEngine(active, worker_storage, clock)
            dispatcher = JobDispatcher(
                settings=active,
                storage=worker_storage,
                policy=policy,
                clock=clock,
                allow_real_research=False,
                allow_real_topic_generation=False,
                content_writer=shared_writer,
                content_route_override=configured_route(ContentType.NOTE),
            )
            worker = Worker(
                storage=worker_storage,
                policy=policy,
                dispatcher=dispatcher,
                lease_owner=owner,
                target_job_id=request.job_id,
                lease_seconds=60,
                heartbeat_interval_seconds=20,
                heartbeat_startup_timeout_seconds=5,
                heartbeat_shutdown_timeout_seconds=5,
                heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
                clock=clock,
            )
            return worker.run_once()
        finally:
            worker_storage.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_one, ("c3-worker-1", "c3-worker-2")))
    assert sorted(item.status for item in results) == [
        WorkerIterationStatus.DONE,
        WorkerIterationStatus.IDLE,
    ]
    assert shared_caller.calls == 1
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["attempts"]) == len(state["results"]) == 1


def test_production_composition_remains_fake_and_provider_resolver_fails_closed():
    route = load_content_route(
        default_content_routing_path(ROOT), ContentType.ARTICLE,
    )
    with pytest.raises(MissingContentWriterConfiguration):
        resolve_provider_route(route)
    assert FakeContentWriter().call_mode.value == "FAKE"


def test_private_style_source_never_enters_prompt_or_durable_result(
    storage, account,
):
    request, _, _, summary, writer, _, _ = run_provider(
        storage, account, ContentType.ARTICLE, suffix="private-style",
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    prompt = writer._caller.fake.requests[0].prompt
    assert "article_style_samples_v1.txt" not in prompt.canonical_preimage()
    state = storage.get_content_pipeline_state(request.job_id)
    combined = json.dumps(state, ensure_ascii=False, default=str)
    assert "article_style_samples_v1.txt" not in combined


def test_explicit_0022_to_0023_migration_is_temp_only_and_idempotent(tmp_path):
    path = tmp_path / "c3-upgrade.db"
    initialize_database(path, through=CONTENT_PIPELINE_SCHEMA_VERSION)
    result = migrate_0022_to_0023(path)
    assert result.applied_migrations == (CONTENT_WRITER_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == CONTENT_WRITER_SCHEMA_VERSION
    repeated = migrate_0022_to_0023(path)
    assert repeated.idempotent is True
    c4 = migrate_0023_to_0024(path)
    assert c4.applied_migrations == (CONTENT_DECISION_SCHEMA_VERSION,)
    lineage = migrate_0024_to_0025(path)
    assert lineage.applied_migrations == (
        EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    )
    paid = migrate_0025_to_0026(path)
    assert paid.applied_migrations == (
        CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    )
    routing = migrate_0026_to_0027(path)
    assert routing.applied_migrations == (MODEL_FAMILY_ROUTING_SCHEMA_VERSION,)
    provenance = migrate_0027_to_0028(path)
    assert provenance.applied_migrations == (
        CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    )
    catalogue = migrate_0028_to_0029(path)
    assert catalogue.applied_migrations == (VERIFIED_CATALOGUE_SCHEMA_VERSION,)
    migrate_0029_to_0030(path)
    migrate_0030_to_0031(path)
    migrate_0031_to_0032(path)
    migrate_0032_to_0033(path)
    migrate_0033_to_0034(path)
    migrate_0034_to_0035(path)
    migrate_0035_to_0036(path)
    migrate_0036_to_0037(path)
    migrate_0037_to_0038(path)
    from app.storage.db import migrate_0038_to_0039
    migrate_0038_to_0039(path)
    from app.storage.db import migrate_0039_to_0040
    migrate_0039_to_0040(path)
    opened = SqliteStorage.open(path)
    opened.close()


def test_0023_failpoint_rolls_back_schema_and_ledger_together(tmp_path):
    path = tmp_path / "c3-upgrade-fault.db"
    initialize_database(path, through=CONTENT_PIPELINE_SCHEMA_VERSION)
    conn = connect(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="user-defined function"):
            apply_migrations(
                conn,
                through=CONTENT_WRITER_SCHEMA_VERSION,
                transaction_failpoint=lambda version: (
                    (_ for _ in ()).throw(RuntimeError("forced 0023 failure"))
                    if version == CONTENT_WRITER_SCHEMA_VERSION else None
                ),
            )
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA legacy_alter_table").fetchone()[0] == 0
    finally:
        conn.close()

    assert database_schema_versions(path)[-1] == CONTENT_PIPELINE_SCHEMA_VERSION
    conn = connect(path)
    try:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(content_writer_intents)")
        }
        objects = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','trigger')"
            )
        }
        assert "provider_status" in columns
        assert "provider" not in columns
        assert "content_writer_results" not in objects
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
