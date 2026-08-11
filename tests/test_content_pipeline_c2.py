"""WAVE C2 offline content pipeline acceptance tests."""
from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

import pytest

from app.content.contracts import EvaluationType
from app.content.entrypoint import run_content_offline
from app.content.foundation import (
    ContentExecutionMode,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.content.pipeline import run_offline_content_pipeline as _run_offline_content_pipeline
from app.content.planner import ContentPlanningBlocked, plan_content
from app.content.routing import (
    RealContentWriterUnavailable,
    default_content_routing_path,
    load_content_route,
    resolve_real_content_writer,
)
from app.content.writer import FakeContentWriter, FakeWriterScenario
from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import JobStatus
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker
from app.scheduler.worker import WorkerIterationStatus
from app.ports.storage import StaleJobExecutionError
from app.storage.db import (
    CONTENT_FOUNDATION_SCHEMA_VERSION,
    CONTENT_PIPELINE_SCHEMA_VERSION,
    CONTENT_WRITER_SCHEMA_VERSION,
    CONTENT_DECISION_SCHEMA_VERSION,
    EVIDENCE_RESEARCH_LINEAGE_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_CONTENT_SCHEMA_VERSION,
    CONTROLLED_PROVIDER_PROVENANCE_SCHEMA_VERSION,
    VERIFIED_CATALOGUE_SCHEMA_VERSION,
    MODEL_FAMILY_ROUTING_SCHEMA_VERSION,
    database_schema_versions,
    initialize_database,
    migrate_0021_to_0022,
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
    """C2 regression adapter supplies the now-mandatory C4 PolicyEngine."""
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


def prepare_and_claim(
    storage: SqliteStorage,
    seed: dict[str, object],
    content_type: ContentType,
    *,
    suffix: str,
):
    request = ContentPreparationRequest(
        job_id=f"c2-job-{suffix}",
        idempotency_key=f"c2-intent-{suffix}",
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
    lease = storage.claim_specific_job(
        request.job_id, f"owner-{suffix}", 60, clock=FixedClock(NOW),
    )
    assert lease is not None
    return request, prepared, lease


def run_direct(
    storage: SqliteStorage,
    seed: dict[str, object],
    content_type: ContentType,
    *,
    suffix: str,
    scenario: FakeWriterScenario = FakeWriterScenario.PASS,
):
    request, prepared, lease = prepare_and_claim(
        storage, seed, content_type, suffix=suffix,
    )
    writer = FakeContentWriter(scenario)
    summary = run_offline_content_pipeline(
        lease.job,
        storage=storage,
        clock=FixedClock(NOW),
        lease_owner=f"owner-{suffix}",
        project_root=ROOT,
        writer=writer,
    )
    return request, prepared, summary, writer


@pytest.mark.parametrize(
    ("content_type", "route_key"),
    [
        (ContentType.ARTICLE, "FABLE_5_ARTICLE"),
        (ContentType.NOTE, "SONNET_5_NOTE"),
    ],
)
def test_happy_paths_are_zero_cost_pending_approval(
    storage, account, content_type, route_key,
):
    seed = seed_c2_research(storage, account)
    request, prepared, summary, writer = run_direct(
        storage, seed, content_type, suffix=content_type.value.lower(),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.cost_usd == 0.0
    assert summary.attempts == 1
    assert summary.evaluation_count == 9
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["job"]["status"] == JobStatus.DONE.value
    assert state["content"]["title"]
    assert state["content"]["body"]
    assert state["plan"]["plan_schema_version"] == "content_plan_v1"
    assert state["brief"]["brief_schema_version"] in {
        "article_brief_v1", "note_brief_v1",
    }
    assert state["intents"][0]["route_key"] == route_key
    assert state["attempts"][0]["status"] == "SETTLED"
    assert state["attempts"][0]["actual_cost_usd"] == 0.0
    run = storage.get_run(summary.run_id)
    assert run is not None
    assert run.status.value == "SUCCESS"
    assert run.cost_usd == 0.0
    content_run = storage.conn.execute(
        "SELECT status,score,finished_at FROM content_runs WHERE run_id=?",
        (summary.run_id,),
    ).fetchone()
    assert content_run["status"] == "PENDING_APPROVAL"
    assert content_run["score"] == 1.0
    assert content_run["finished_at"] is not None
    usage = storage.conn.execute(
        "SELECT provider,model,task,dry_run,estimated_cost_usd,request_id "
        "FROM model_usage WHERE run_id=?",
        (summary.run_id,),
    ).fetchall()
    assert len(usage) == 1
    assert usage[0]["provider"] == "fake-content-writer"
    assert usage[0]["model"] == route_key
    assert usage[0]["task"] == "content_draft"
    assert usage[0]["dry_run"] == 1
    assert usage[0]["estimated_cost_usd"] == 0.0
    assert storage.conn.execute(
        "SELECT count(*) FROM approvals WHERE object_type='CONTENT' AND object_id=?",
        (prepared.content.id,),
    ).fetchone()[0] == 0
    assert len(writer.requests) == 1
    assert writer.requests[0].max_cost_usd == 0.0


def test_routing_is_logical_unverified_and_has_no_fallback():
    for content_type, key in (
        (ContentType.ARTICLE, "FABLE_5_ARTICLE"),
        (ContentType.NOTE, "SONNET_5_NOTE"),
    ):
        route = load_content_route(default_content_routing_path(ROOT), content_type)
        assert route.route_key == key
        assert route.fallback == "FORBIDDEN"
        assert {
            route.provider,
            route.api_model_id,
            route.availability,
            route.pricing_profile,
        } == {"UNVERIFIED"}
        with pytest.raises(RealContentWriterUnavailable):
            resolve_real_content_writer(route)


def test_one_rewrite_creates_two_distinct_canonical_attempts(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, summary, writer = run_direct(
        storage, seed, ContentType.ARTICLE, suffix="rewrite",
        scenario=FakeWriterScenario.REWRITE_THEN_PASS,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert summary.attempts == 2
    assert summary.evaluation_count == 18
    state = storage.get_content_pipeline_state(request.job_id)
    assert [row["attempt_no"] for row in state["attempts"]] == [1, 2]
    assert len({row["request_id"] for row in state["attempts"]}) == 2
    assert all(row["status"] == "SETTLED" for row in state["attempts"])
    assert all(row["actual_cost_usd"] == 0.0 for row in state["attempts"])
    assert len(writer.requests) == 2


def test_second_rewrite_is_terminal_failure_without_third_attempt(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, summary, _ = run_direct(
        storage, seed, ContentType.ARTICLE, suffix="rewrite-limit",
        scenario=FakeWriterScenario.ALWAYS_REWRITE,
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == "CONTENT_REWRITE_LIMIT_EXHAUSTED"
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["attempts"]) == 2
    assert len(state["drafts"]) == 2
    assert state["content"]["status"] == "FAILED"


@pytest.mark.parametrize(
    ("scenario", "evaluation_type"),
    [
        (FakeWriterScenario.UNSUPPORTED_CLAIM, "UNSUPPORTED_CLAIMS"),
        (FakeWriterScenario.PERSONAL_EXPERIENCE, "FAKE_PERSONAL_EXPERIENCE"),
    ],
)
def test_hard_evaluation_failures_block(storage, account, scenario, evaluation_type):
    seed = seed_c2_research(storage, account)
    request, _, summary, _ = run_direct(
        storage, seed, ContentType.NOTE, suffix=evaluation_type.lower(),
        scenario=scenario,
    )
    assert summary.status is ContentStatus.FAILED
    rows = storage.get_content_pipeline_state(request.job_id)["evaluations"]
    matching = [row for row in rows if row["evaluation_type"] == evaluation_type]
    assert len(matching) == 1
    assert matching[0]["decision"] == "BLOCK"


def test_brand_policy_blocks_ai_topic_before_writer_attempt(storage, account):
    seed = seed_c2_research(storage, account, topic_title="How AI builds this project")
    request, _, summary, writer = run_direct(
        storage, seed, ContentType.ARTICLE, suffix="brand-ai",
    )
    assert summary.status is ContentStatus.FAILED
    assert summary.block_code == "CONTENT_BRAND_TOPIC_BLOCKED"
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["plan"] is None
    assert state["attempts"] == []
    assert writer.requests == []


def test_writer_receives_only_derived_profiles_and_frozen_evidence(storage, account):
    seed = seed_c2_research(storage, account)
    _, _, _, writer = run_direct(
        storage, seed, ContentType.ARTICLE, suffix="writer-contract",
    )
    request = writer.requests[0]
    assert "ARTICLE_STYLE_PROFILE_V1" in request.style_profile
    assert "ARTICLE_NEGATIVE_STYLE_PROFILE_V1" in request.negative_style_profile
    assert len(request.frozen_evidence) == 1
    assert "article_style_samples_v1.txt" not in request.style_profile
    assert not hasattr(request, "raw_style_source")
    assert not hasattr(request, "secrets")


def test_profiles_and_private_source_boundaries():
    raw = ROOT / "data/style-references/articles/article_style_samples_v1.txt"
    assert raw.exists()
    profiles = [
        ROOT / "instrukcja dla pisania artykulow/ARTICLE_STYLE_PROFILE_V1.md",
        ROOT / "instrukcja dla pisania artykulow/ARTICLE_NEGATIVE_STYLE_PROFILE_V1.md",
        ROOT / "instrukcja dla pisania artykulow/NOTES_STYLE_PROFILE_V1.md",
    ]
    raw_text = raw.read_text(encoding="utf-8")
    for path in profiles:
        profile = path.read_text(encoding="utf-8")
        assert len(profile) < len(raw_text) // 3
        raw_segments = {
            raw_text[index:index + 200]
            for index in range(0, max(0, len(raw_text) - 200), 200)
        }
        assert not any(segment in profile for segment in raw_segments)
    assert "PROVISIONAL" in profiles[2].read_text(encoding="utf-8")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(raw.relative_to(ROOT))],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0


def test_planner_requires_proceed_and_frozen_evidence(storage, account):
    seed = seed_c2_research(storage, account)
    prepared = storage.prepare_content_job(
        ContentPreparationRequest(
            job_id="planner-preconditions-job",
            idempotency_key="planner-preconditions-intent",
            account_id=account.id,
            research_card_id=int(seed["card_id"]),
            content_type=ContentType.ARTICLE,
            execution_mode=ContentExecutionMode.OFFLINE_PIPELINE,
        ),
        clock=FixedClock(NOW),
    )
    frozen = prepared.frozen_input
    route = load_content_route(
        default_content_routing_path(ROOT), ContentType.ARTICLE,
    )
    card = json.loads(frozen.research_card_snapshot_json)
    card["publication_recommendation"] = "NEEDS_REVIEW"
    not_proceed = frozen.model_copy(update={
        "research_card_snapshot_json": json.dumps(
            card, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ),
    })
    with pytest.raises(ContentPlanningBlocked, match="CONTENT_CARD_NOT_PROCEED"):
        plan_content(not_proceed, route)
    without_evidence = frozen.model_copy(update={"evidence_items": ()})
    with pytest.raises(ContentPlanningBlocked, match="CONTENT_EVIDENCE_MISSING"):
        plan_content(without_evidence, route)


def test_full_entrypoint_claims_named_job_and_dispatches(
    storage, settings, account,
):
    seed = seed_c2_research(storage, account)
    storage.apply_security_flag_profile(
        [
            ("worker_enabled", True),
            ("safe_mode", False),
            ("paid_actions_enabled", False),
            ("browser_actions_enabled", False),
            ("kill_switch", False),
        ],
        updated_by="test", reason="offline C2", now=NOW,
    )
    result = run_content_offline(
        settings=replace(settings, project_root=ROOT),
        account_id=account.id,
        research_card_id=int(seed["card_id"]),
        content_type=ContentType.NOTE,
        idempotency_key="entrypoint-note",
        job_id="entrypoint-note-job",
        lease_owner="entrypoint-worker",
        clock=FixedClock(NOW),
    )
    assert result.worker.status is WorkerIterationStatus.DONE
    assert storage.get_content_item(account.id, result.content_id).status is ContentStatus.PENDING_APPROVAL
    assert storage.claim_next_job(
        "ordinary-worker", 60, clock=FixedClock(NOW),
    ) is None


def test_evaluation_set_is_exactly_nine(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, _, _ = run_direct(
        storage, seed, ContentType.ARTICLE, suffix="eval-types",
    )
    observed = {
        row["evaluation_type"]
        for row in storage.get_content_pipeline_state(request.job_id)["evaluations"]
    }
    assert observed == {kind.value for kind in EvaluationType}


def test_terminal_replay_creates_nothing(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, summary, _ = run_direct(
        storage, seed, ContentType.NOTE, suffix="terminal-replay",
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    assert storage.claim_specific_job(
        request.job_id, "second", 60, clock=FixedClock(NOW),
    ) is None
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["attempts"]) == 1
    assert len(state["drafts"]) == 1


def test_possible_external_effect_recovery_escalates(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, lease = prepare_and_claim(
        storage, seed, ContentType.ARTICLE, suffix="ambiguous-recovery",
    )
    storage.initialize_content_run_for_job(
        request.job_id, "owner-ambiguous-recovery",
        lease.job.execution_generation, f"content-run:{request.job_id}",
        clock=FixedClock(NOW),
    )
    storage.conn.execute(
        "UPDATE jobs SET external_effect_started_at=? WHERE id=?",
        ("2026-07-23 12:00:01", request.job_id),
    )
    storage.conn.commit()
    result = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=2)),
    )
    assert result.needs_verification_count == 1
    assert storage.get_job(request.job_id).status is JobStatus.NEEDS_VERIFICATION


class SimulatedCrash(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("checkpoint", "scenario", "attempts_before_recovery"),
    [
        ("BRIEF_PERSISTED", FakeWriterScenario.PASS, 0),
        ("WRITER_ATTEMPT_STARTED", FakeWriterScenario.PASS, 1),
        ("DRAFT_PERSISTED", FakeWriterScenario.PASS, 1),
        ("REWRITE_DECISION_PERSISTED", FakeWriterScenario.REWRITE_THEN_PASS, 1),
    ],
)
def test_restart_from_each_durable_checkpoint(
    storage, account, checkpoint, scenario, attempts_before_recovery,
):
    seed = seed_c2_research(storage, account)
    request, _, lease = prepare_and_claim(
        storage, seed, ContentType.ARTICLE, suffix=f"restart-{checkpoint.lower()}",
    )

    def crash(point: str) -> None:
        if point == checkpoint:
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash, match=checkpoint):
        run_offline_content_pipeline(
            lease.job,
            storage=storage,
            clock=FixedClock(NOW),
            lease_owner=f"owner-restart-{checkpoint.lower()}",
            project_root=ROOT,
            writer=FakeContentWriter(scenario),
            fault_point=crash,
        )
    before = storage.get_content_pipeline_state(request.job_id)
    assert len(before["attempts"]) == attempts_before_recovery
    recovery = storage.release_or_requeue_expired_leases(
        clock=FixedClock(NOW + timedelta(minutes=2)),
    )
    assert recovery.requeued_count == 1
    takeover_clock = FixedClock(NOW + timedelta(minutes=2))
    takeover = storage.claim_specific_job(
        request.job_id, "takeover", 60, clock=takeover_clock,
    )
    assert takeover is not None
    summary = run_offline_content_pipeline(
        takeover.job,
        storage=storage,
        clock=takeover_clock,
        lease_owner="takeover",
        project_root=ROOT,
        writer=FakeContentWriter(scenario),
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL
    state = storage.get_content_pipeline_state(request.job_id)
    assert len(state["attempts"]) <= 2
    assert len({row["request_id"] for row in state["attempts"]}) == len(state["attempts"])
    assert all(row["actual_cost_usd"] == 0.0 for row in state["attempts"])


def test_old_fence_is_rejected_after_takeover(storage, account):
    seed = seed_c2_research(storage, account)
    request, _, old_lease = prepare_and_claim(
        storage, seed, ContentType.NOTE, suffix="old-fence",
    )

    def crash(point: str) -> None:
        if point == "BRIEF_PERSISTED":
            raise SimulatedCrash(point)

    with pytest.raises(SimulatedCrash):
        run_offline_content_pipeline(
            old_lease.job, storage=storage, clock=FixedClock(NOW),
            lease_owner="owner-old-fence", project_root=ROOT,
            fault_point=crash,
        )
    later = FixedClock(NOW + timedelta(minutes=2))
    storage.release_or_requeue_expired_leases(clock=later)
    new_lease = storage.claim_specific_job(
        request.job_id, "new-owner", 60, clock=later,
    )
    assert new_lease is not None
    with pytest.raises(StaleJobExecutionError):
        run_offline_content_pipeline(
            old_lease.job, storage=storage, clock=later,
            lease_owner="owner-old-fence", project_root=ROOT,
        )
    summary = run_offline_content_pipeline(
        new_lease.job, storage=storage, clock=later,
        lease_owner="new-owner", project_root=ROOT,
    )
    assert summary.status is ContentStatus.PENDING_APPROVAL


def test_two_targeted_workers_create_one_execution(storage, settings, account):
    seed = seed_c2_research(storage, account)
    request = ContentPreparationRequest(
        job_id="c2-concurrent-worker-job",
        idempotency_key="c2-concurrent-worker-intent",
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
        updated_by="test", reason="offline concurrency", now=NOW,
    )
    active_settings = replace(settings, project_root=ROOT)

    def run_worker(owner: str):
        worker_storage = SqliteStorage.open(settings.db_path)
        try:
            clock = FixedClock(NOW)
            policy = PolicyEngine(active_settings, worker_storage, clock)
            dispatcher = JobDispatcher(
                settings=active_settings,
                storage=worker_storage,
                policy=policy,
                clock=clock,
                allow_real_research=False,
                allow_real_topic_generation=False,
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
        results = list(pool.map(run_worker, ("worker-one", "worker-two")))
    assert sorted(result.status.value for result in results) == ["DONE", "IDLE"]
    state = storage.get_content_pipeline_state(request.job_id)
    assert state["content"]["status"] == "PENDING_APPROVAL"
    assert len(state["attempts"]) == 1
    assert len(state["drafts"]) == 1
    assert len(state["evaluations"]) == 9


def test_explicit_0021_to_0022_migration_is_temp_only_and_idempotent(tmp_path):
    path = tmp_path / "c2-upgrade.db"
    initialize_database(path, through=CONTENT_FOUNDATION_SCHEMA_VERSION)
    result = migrate_0021_to_0022(path)
    assert result.applied_migrations == (CONTENT_PIPELINE_SCHEMA_VERSION,)
    assert database_schema_versions(path)[-1] == CONTENT_PIPELINE_SCHEMA_VERSION
    repeated = migrate_0021_to_0022(path)
    assert repeated.idempotent is True
    c3 = migrate_0022_to_0023(path)
    assert c3.applied_migrations == (CONTENT_WRITER_SCHEMA_VERSION,)
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
    conn = SqliteStorage.open(path)
    try:
        assert conn.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()
