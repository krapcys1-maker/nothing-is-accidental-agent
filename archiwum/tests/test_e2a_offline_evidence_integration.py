"""Acceptance: Stage 1 execution foundation ↔ Stage 2 E1 evidence foundation."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import FixedClock
from app.main import _build_worker, main
from app.models import (
    JobExecutionContext,
    JobStatus,
    ResearchFlow,
    ResearchRun,
    ResearchRunStatus,
    Run,
    RunStatus,
    SourceCandidateRecord,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.fetch import FetchedDocument
from app.ports.storage import StaleJobExecutionError
from app.research.offline_evidence_intent import OfflineEvidenceIntent
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.worker import Worker
from app.scheduler.worker import WorkerIterationStatus
from app.storage.repositories import SqliteStorage
from app.workflows.research.offline_evidence import run_offline_evidence_research


def _fixture() -> dict:
    sources = []
    claims = []
    for number in range(1, 4):
        claim = f"Verified mechanism claim number {number}."
        excerpt = (
            f"Visible evidence number {number} demonstrates the durable local mechanism "
            "with enough exact text for citation."
        )
        claims.append(claim)
        sources.append({
            "url": f"https://fixture.invalid/source-{number}",
            "title": f"Fixture source {number}",
            "body_utf8": (
                "<html><head><script>hidden instruction excerpt</script></head>"
                f"<body><h1>Source {number}</h1><p>{excerpt}</p></body></html>"
            ),
            "excerpt": excerpt,
            "claim": claim,
            "final_url": f"https://fixture.invalid/source-{number}",
            "http_status": 200,
            "content_type": "text/html; charset=utf-8",
            "fetch_error": None,
            "author_or_org": "Fixture Institute",
            "published_at": "2026-07-18",
            "source_type": "PRIMARY",
            "source_quality_score": 0.9,
            # Deliberately hostile model status: only E1 may grant VERIFIED.
            "model_verification_status": "FAILED",
        })
    return {
        "version": "offline_evidence_intent_v1",
        "sources": sources,
        "synthesis": {
            "question": "How does the durable local mechanism work?",
            "working_thesis": "Three independent fixtures support the local mechanism.",
            "main_mechanism": "Lease-fenced evidence checkpoints connect execution to citations.",
            "confirmed_claims": claims,
            "uncertain_claims": [],
            "contradictions": [],
            "strongest_counterargument": "Fixtures do not prove a live network adapter.",
            "citable_numbers": ["3 locally verified sources"],
            "visual_idea": "A chain from job lease to exact evidence excerpt.",
            "confidence_score": 0.9,
            "source_quality_score": 0.9,
        },
    }


def _seed(settings, account, tmp_path, monkeypatch):
    settings.editorial_schedule = {
        "timezone": "UTC",
        "windows": [{
            "weekdays": [0, 1, 2, 3, 4, 5, 6],
            "start": "00:00", "end": "23:59",
        }],
    }
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title="Offline evidence integration",
        question="How does the durable local mechanism work?",
        status=TopicStatus.SELECTED,
    ))
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", False),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="E2-A acceptance")
    storage.close()
    fixture_path = tmp_path / "offline-evidence.json"
    fixture_path.write_text(json.dumps(_fixture()), encoding="utf-8")
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main([
        "enqueue-offline-evidence-research",
        "--account-id", account.id,
        "--topic-id", str(topic.id),
        "--fixture-path", str(fixture_path),
    ]) == 0
    return topic


def test_stage1_execution_foundation_to_stage2_e1_evidence_foundation(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, tmp_path, monkeypatch)
    queued = SqliteStorage.open(settings.db_path)
    job = queued.conn.execute("SELECT * FROM jobs").fetchone()
    moment = job["earliest_run_at"]
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment).replace(tzinfo=timezone.utc)
    elif moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    queued.close()

    worker, storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=1)),
        lease_owner="e2a-worker-one",
    )
    try:
        result = worker.run_once()
        assert result.status is WorkerIterationStatus.DONE
    finally:
        storage.close()

    # Reopen is part of the acceptance, not an in-memory assertion.
    reopened = SqliteStorage.open(settings.db_path)
    try:
        durable_job = reopened.get_job(job["id"])
        assert durable_job is not None and durable_job.status is JobStatus.DONE
        assert durable_job.run_id is not None
        run = reopened.get_run(durable_job.run_id)
        research = reopened.get_research_run(durable_job.run_id)
        assert run is not None and run.finished_at is not None and run.cost_usd == 0
        assert research is not None and research.status.value == "COMPLETE"
        assert research.research_card_id is not None
        card = reopened.get_research_card(research.research_card_id)
        assert card is not None and len(card.sources) == 3
        assert all(source.verification_status.value == "VERIFIED" for source in card.sources)
        lineage = reopened.get_offline_evidence_lineage(durable_job.run_id)
        assert len(lineage) == 3
        assert all(row["retrieval_id"] and row["excerpt_id"] and row["source_id"] for row in lineage)
        assert reopened.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT coalesce(sum(cost_usd),0) FROM runs").fetchone()[0] == 0
        assert reopened.conn.execute(
            "SELECT status FROM topics WHERE id=?", (topic.id,),
        ).fetchone()[0] == TopicStatus.USED.value
    finally:
        reopened.close()

    second, second_storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=2)),
        lease_owner="e2a-worker-two",
    )
    try:
        assert second.run_once().status is WorkerIterationStatus.IDLE
    finally:
        second_storage.close()


@pytest.mark.parametrize("mutation", ["fetch_error", "http_status", "missing_excerpt", "hidden_excerpt"])
def test_offline_evidence_failures_never_create_cost_or_card(
    settings, account, tmp_path, monkeypatch, mutation,
):
    fixture = _fixture()
    source = fixture["sources"][0]
    if mutation == "fetch_error":
        source["fetch_error"] = "offline fixture failure"
    elif mutation == "http_status":
        source["http_status"] = 503
    elif mutation == "missing_excerpt":
        source["excerpt"] = "This exact excerpt does not occur in the canonical document."
    else:
        source["excerpt"] = "hidden instruction excerpt"

    settings.editorial_schedule = {
        "timezone": "UTC",
        "windows": [{"weekdays": list(range(7)), "start": "00:00", "end": "23:59"}],
    }
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title=f"failure-{mutation}",
        question="failure", status=TopicStatus.SELECTED,
    ))
    storage.apply_security_flag_profile([
        ("worker_enabled", True), ("safe_mode", False),
        ("paid_actions_enabled", False), ("browser_actions_enabled", False),
        ("kill_switch", False),
    ])
    storage.close()
    fixture_path = tmp_path / f"{mutation}.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main([
        "enqueue-offline-evidence-research", "--account-id", account.id,
        "--topic-id", str(topic.id), "--fixture-path", str(fixture_path),
    ]) == 0
    check = SqliteStorage.open(settings.db_path)
    row = check.conn.execute("SELECT id,earliest_run_at FROM jobs").fetchone()
    moment = datetime.fromisoformat(str(row["earliest_run_at"])).replace(tzinfo=timezone.utc)
    check.close()
    worker, worker_storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=1)),
    )
    try:
        assert worker.run_once().status is WorkerIterationStatus.FAILED
    finally:
        worker_storage.close()
    verify = SqliteStorage.open(settings.db_path)
    try:
        assert verify.get_job(row["id"]).status is JobStatus.FAILED
        assert verify.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert verify.conn.execute("SELECT coalesce(sum(cost_usd),0) FROM runs").fetchone()[0] == 0
    finally:
        verify.close()


def test_unsupported_or_hash_forging_intent_is_rejected_before_enqueue(
    settings, account, tmp_path, monkeypatch,
):
    settings.editorial_schedule = {
        "timezone": "UTC",
        "windows": [{"weekdays": list(range(7)), "start": "00:00", "end": "23:59"}],
    }
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id, title="invalid intent", status=TopicStatus.SELECTED,
    ))
    storage.close()
    fixture = _fixture()
    fixture["version"] = "offline_evidence_intent_v999"
    fixture["sources"][0]["canonical_sha256"] = "0" * 64
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main([
        "enqueue-offline-evidence-research", "--account-id", account.id,
        "--topic-id", str(topic.id), "--fixture-path", str(path),
    ]) == 2
    verify = SqliteStorage.open(settings.db_path)
    try:
        assert verify.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    finally:
        verify.close()


def test_offline_evidence_execution_cannot_be_changed_to_paid(
    settings, account, tmp_path, monkeypatch,
):
    _seed(settings, account, tmp_path, monkeypatch)
    mutate = SqliteStorage.open(settings.db_path)
    job = mutate.conn.execute("SELECT id,payload_json,earliest_run_at FROM jobs").fetchone()
    payload = json.loads(job["payload_json"])
    payload["dry_run"] = False
    mutate.conn.execute(
        "UPDATE jobs SET payload_json=? WHERE id=?",
        (json.dumps(payload, sort_keys=True, separators=(",", ":")), job["id"]),
    )
    mutate.conn.commit()
    moment = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    mutate.close()
    worker, storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=1)),
    )
    try:
        assert worker.run_once().status is WorkerIterationStatus.FAILED
    finally:
        storage.close()
    verify = SqliteStorage.open(settings.db_path)
    try:
        assert verify.get_job(job["id"]).status is JobStatus.FAILED
        assert verify.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    finally:
        verify.close()


def test_stale_lease_cannot_write_retrieval(
    settings, account, tmp_path, monkeypatch,
):
    _seed(settings, account, tmp_path, monkeypatch)
    storage = SqliteStorage.open(settings.db_path)
    job = storage.conn.execute("SELECT * FROM jobs").fetchone()
    start = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    active = FixedClock(start + timedelta(seconds=1))
    lease = storage.claim_next_job("stale-worker", 60, clock=active)
    storage.mark_job_running(job["id"], "stale-worker", clock=active)
    initialized = storage.initialize_offline_evidence_run_for_job(
        job["id"], "stale-worker", "stale-e2a-run", clock=active,
    )
    execution = JobExecutionContext(
        job_id=job["id"], lease_owner="stale-worker",
        run_id=initialized.run.id, clock=active,
    )
    intent = OfflineEvidenceIntent.from_payload(json.loads(job["payload_json"])["execution_intent"])
    storage.persist_offline_evidence_discovery(
        execution,
        [
            SourceCandidateRecord(
                research_run_id=execution.run_id, url=source.url, title=source.title,
            )
            for source in intent.sources
        ],
    )
    candidate = storage.list_source_candidates(execution.run_id)[0]
    stale = JobExecutionContext(
        job_id=job["id"], lease_owner="stale-worker", run_id=execution.run_id,
        clock=FixedClock(start + timedelta(seconds=62)),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.persist_offline_evidence_retrieval(
            stale, int(candidate.id), intent.fake_fetch(active.now()).fetch(candidate.url),
        )
    assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
    storage.close()


@pytest.mark.parametrize(
    ("method", "expected_retrievals", "expected_excerpts"),
    [
        ("persist_offline_evidence_retrieval", 0, 0),
        ("persist_offline_verified_excerpt", 1, 0),
        ("finalize_offline_evidence_execution", 3, 3),
    ],
)
def test_storage_faults_never_leave_false_success(
    settings, account, tmp_path, monkeypatch,
    method, expected_retrievals, expected_excerpts,
):
    _seed(settings, account, tmp_path, monkeypatch)
    original = getattr(SqliteStorage, method)

    def fail(*args, **kwargs):
        raise RuntimeError(f"controlled {method} failure")

    monkeypatch.setattr(SqliteStorage, method, fail)
    queued = SqliteStorage.open(settings.db_path)
    job = queued.conn.execute("SELECT id,earliest_run_at FROM jobs").fetchone()
    moment = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    queued.close()
    worker, storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=1)),
    )
    try:
        assert worker.run_once().status is WorkerIterationStatus.FAILED
    finally:
        storage.close()
    monkeypatch.setattr(SqliteStorage, method, original)
    verify = SqliteStorage.open(settings.db_path)
    try:
        assert verify.get_job(job["id"]).status is JobStatus.FAILED
        assert verify.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == expected_retrievals
        assert verify.conn.execute("SELECT count(*) FROM evidence_excerpts").fetchone()[0] == expected_excerpts
        assert verify.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    finally:
        verify.close()


def test_second_worker_cannot_claim_the_same_offline_job(
    settings, account, tmp_path, monkeypatch,
):
    _seed(settings, account, tmp_path, monkeypatch)
    first = SqliteStorage.open(settings.db_path)
    second = SqliteStorage.open(settings.db_path)
    row = first.conn.execute("SELECT earliest_run_at FROM jobs").fetchone()
    moment = datetime.fromisoformat(str(row["earliest_run_at"])).replace(tzinfo=timezone.utc)
    clock = FixedClock(moment + timedelta(seconds=1))
    lease = first.claim_next_job("worker-one", 60, clock=clock)
    assert lease is not None
    assert second.claim_next_job("worker-two", 60, clock=clock) is None
    first.close()
    second.close()


def test_raw_sqlite_blocks_foreign_account_run_and_topic_lineage_after_success(
    settings, account, tmp_path, monkeypatch,
):
    _seed(settings, account, tmp_path, monkeypatch)
    queued = SqliteStorage.open(settings.db_path)
    job = queued.conn.execute("SELECT id,earliest_run_at FROM jobs").fetchone()
    moment = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    queued.close()
    worker, worker_storage = _build_worker(
        settings, True, clock=FixedClock(moment + timedelta(seconds=1)),
    )
    try:
        assert worker.run_once().status is WorkerIterationStatus.DONE
    finally:
        worker_storage.close()

    storage = SqliteStorage.open(settings.db_path)
    durable = storage.get_job(job["id"])
    other = account.model_copy(update={"id": "foreign-account", "display_name": "Foreign"})
    storage.ensure_account(other)
    other_topic = storage.add_topic(other.id, Topic(
        account_id=other.id, title="foreign topic", status=TopicStatus.SELECTED,
    ))
    storage.create_run(Run(
        id="foreign-run", account_id=other.id, workflow=WorkflowType.RESEARCH,
        status=RunStatus.DRY_RUN, started_at=moment,
    ))
    storage.create_research_run(ResearchRun(
        id="foreign-run", account_id=other.id, topic_id=int(other_topic.id),
        flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_PENDING,
        created_at=moment, updated_at=moment,
    ))
    storage.conn.execute(
        "INSERT INTO research_source_candidates (research_run_id,url,title,status)"
        " VALUES (?,?,?,'PENDING_EXTRACTION')",
        ("foreign-run", "https://fixture.invalid/foreign", "foreign"),
    )
    foreign_candidate = int(storage.conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    retrieval = storage.record_evidence_retrieval(FetchedDocument(
        requested_url="https://fixture.invalid/foreign",
        final_url="https://fixture.invalid/foreign", fetched_at=moment,
        http_status=200, content_type="text/plain",
        body=b"Visible foreign lineage evidence with a valid exact local body.",
    ), account_id=account.id, now=moment)
    storage.conn.execute("PRAGMA foreign_keys=OFF")
    probes = [
        (foreign_candidate, "foreign-run", account.id, retrieval.id),  # foreign account/run
        (foreign_candidate, durable.run_id, account.id, retrieval.id),  # candidate other topic
        (foreign_candidate, "missing-run", account.id, retrieval.id),  # retrieval/run mismatch
    ]
    for values in probes:
        with pytest.raises(sqlite3.IntegrityError, match="lineage"):
            storage.conn.execute(
                "INSERT INTO evidence_candidate_retrievals "
                "(candidate_id,research_run_id,account_id,retrieval_id,created_at)"
                " VALUES (?,?,?,?,?)",
                (*values, moment.isoformat()),
            )
        storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT count(*) FROM evidence_candidate_retrievals WHERE candidate_id=?",
        (foreign_candidate,),
    ).fetchone()[0] == 0
    storage.close()


def test_lease_loss_after_validation_rolls_back_retrieval_write(
    settings, account, tmp_path, monkeypatch,
):
    _seed(settings, account, tmp_path, monkeypatch)
    storage = SqliteStorage.open(settings.db_path)
    job = storage.conn.execute("SELECT * FROM jobs").fetchone()
    start = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    clock = FixedClock(start + timedelta(seconds=1))
    storage.claim_next_job("race-worker", 60, clock=clock)
    storage.mark_job_running(job["id"], "race-worker", clock=clock)
    initialized = storage.initialize_offline_evidence_run_for_job(
        job["id"], "race-worker", "race-e2a-run", clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job["id"], lease_owner="race-worker",
        run_id=initialized.run.id, clock=clock,
    )
    intent = OfflineEvidenceIntent.from_payload(json.loads(job["payload_json"])["execution_intent"])
    storage.persist_offline_evidence_discovery(
        execution,
        [
            SourceCandidateRecord(
                research_run_id=execution.run_id, url=source.url, title=source.title,
            )
            for source in intent.sources
        ],
    )
    candidate = storage.list_source_candidates(execution.run_id)[0]
    original_fence = storage._require_job_execution_fence

    def lose_after_validation(*args, **kwargs):
        original_fence(*args, **kwargs)
        raise StaleJobExecutionError(job["id"], "controlled loss after validation")

    monkeypatch.setattr(storage, "_require_job_execution_fence", lose_after_validation)
    with pytest.raises(StaleJobExecutionError):
        storage.persist_offline_evidence_retrieval(
            execution, int(candidate.id),
            intent.fake_fetch(clock.now()).fetch(candidate.url),
        )
    assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
    storage.close()


class _ProcessCrash(BaseException):
    pass


@pytest.mark.parametrize("crash_point", ["after_retrieval", "after_all_excerpts"])
def test_offline_evidence_resumes_from_durable_checkpoint_without_duplicate_effects(
    settings, account, tmp_path, monkeypatch, crash_point,
):
    _seed(settings, account, tmp_path, monkeypatch)
    first_storage = SqliteStorage.open(settings.db_path)
    job = first_storage.conn.execute("SELECT * FROM jobs").fetchone()
    start = datetime.fromisoformat(str(job["earliest_run_at"])).replace(tzinfo=timezone.utc)
    first_clock = FixedClock(start + timedelta(seconds=1))
    first_policy = PolicyEngine(settings, first_storage, first_clock)

    def crashing_runner(*args, **kwargs):
        def hook(point: str) -> None:
            if crash_point == "after_retrieval" and point == "after_retrieval":
                raise _ProcessCrash()
            if crash_point == "after_all_excerpts" and point == "after_excerpt":
                run_id = first_storage.get_job(job["id"]).run_id
                rows = first_storage.get_offline_evidence_lineage(run_id)
                if len(rows) == 3 and all(row["excerpt_id"] is not None for row in rows):
                    raise _ProcessCrash()
        return run_offline_evidence_research(*args, **kwargs, checkpoint_hook=hook)

    dispatcher = JobDispatcher(
        settings=settings, storage=first_storage, policy=first_policy,
        clock=first_clock, allow_real_research=False,
        research_offline_evidence=crashing_runner,
    )
    worker = Worker(
        storage=first_storage, policy=first_policy, dispatcher=dispatcher,
        lease_owner="crashing-worker", lease_seconds=60,
        heartbeat_interval_seconds=20,
        heartbeat_startup_timeout_seconds=5,
        heartbeat_shutdown_timeout_seconds=5,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=first_clock,
    )
    with pytest.raises(_ProcessCrash):
        worker.run_once()
    partial_job = first_storage.get_job(job["id"])
    assert partial_job.status is JobStatus.RUNNING
    partial = first_storage.get_offline_evidence_lineage(partial_job.run_id)
    if crash_point == "after_retrieval":
        assert sum(row["retrieval_id"] is not None for row in partial) == 1
        assert sum(row["excerpt_id"] is not None for row in partial) == 0
    else:
        assert all(row["retrieval_id"] and row["excerpt_id"] for row in partial)
    first_storage.close()

    recovery_time = start + timedelta(seconds=122)
    recovery = SqliteStorage.open(settings.db_path)
    recovered = recovery.release_or_requeue_expired_leases(
        clock=FixedClock(recovery_time),
    )
    assert recovered.requeued_count == 1
    recovery.close()

    resumed, resumed_storage = _build_worker(
        settings, True, clock=FixedClock(recovery_time),
        lease_owner="resuming-worker",
    )
    try:
        assert resumed.run_once().status is WorkerIterationStatus.DONE
    finally:
        resumed_storage.close()
    verify = SqliteStorage.open(settings.db_path)
    try:
        durable = verify.get_job(job["id"])
        assert durable.status is JobStatus.DONE
        assert verify.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 3
        assert verify.conn.execute("SELECT count(*) FROM evidence_excerpts").fetchone()[0] == 3
        assert verify.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 1
        assert verify.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert verify.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    finally:
        verify.close()
