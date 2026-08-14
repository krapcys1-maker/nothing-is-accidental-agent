"""Stage 3 / Wave C1 durable content foundation.

All writes target new temporary SQLite files.  No planner, writer, provider,
browser or publication adapter is constructed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from threading import Barrier

import pytest

from app.content.foundation import (
    ContentCallIntent,
    ContentEvaluation,
    ContentEvaluationKind,
    ContentEvaluationStatus,
    ContentInitializationFaultPoint,
    ContentPreparationRequest,
    ContentStatus,
    ContentType,
)
from app.core.clock import FixedClock
from app.models import (
    JobExecutionContext,
    JobKind,
    JobStatus,
    ModelUsage,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    ContentFoundationError,
    ContentSnapshotError,
    LifecycleTransitionError,
    StaleJobExecutionError,
)
from app.storage.repositories import SqliteStorage


_NOW = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
_CLAIM = "A hidden fee changes the apparent price."
_URL = "https://example.test/source"
_CANONICAL = (
    "A hidden fee changes the apparent price because the displayed amount "
    "excludes a mandatory charge."
)
_EXCERPT = "A hidden fee changes the apparent price"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _lineage_fingerprint(data: dict[str, object]) -> str:
    return _sha(json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ))


def build_content_seed(storage: SqliteStorage, account, *, suffix="content-seed"):
    """Create one complete PROCEED card with full evidence lineage.

    Exposed as a plain function (not only as the fixture) so the schema-0043
    migration test can build the same durable shape on a database that is still
    at 0042 and therefore cannot be opened through the runtime schema gate.
    ``suffix`` varies the topic and the card question, so two calls produce two
    genuinely different frozen inputs.
    """
    label = "The hidden fee" if suffix == "content-seed" else f"The hidden fee ({suffix})"
    question = (
        "Why does the price change?"
        if suffix == "content-seed"
        else f"Why does the price change ({suffix})?"
    )
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=label,
        question=question,
        status=TopicStatus.SELECTED,
    ))
    assert topic.id is not None
    cursor = storage.conn.execute(
        "INSERT INTO research_cards (topic_id,question,thesis,mechanism,facts_json,"
        "counterargument,citable_numbers,visual_idea,confidence,working_thesis,"
        "confirmed_claims,uncertain_claims,contradictions,source_quality_score,"
        "publication_recommendation,rejection_reason,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            topic.id, question, "Fees hide the mechanism.",
            "Mandatory charges are excluded.", "[]", "The fee is disclosed.",
            "[]", "A split receipt", 0.9, "Fees hide the mechanism.",
            json.dumps([_CLAIM]), "[]", "[]", 0.95, "PROCEED", None,
            "2026-07-23 11:00:00",
        ),
    )
    card_id = int(cursor.lastrowid)
    source = storage.conn.execute(
        "INSERT INTO sources (research_card_id,url,title,source_type,verified,"
        "author_or_org,supports_claim,verification_status) "
        "VALUES (?,?,?,'PRIMARY',1,'Example Org',?,'VERIFIED')",
        (card_id, _URL, "Source", _CLAIM),
    )
    source_id = int(source.lastrowid)
    retrieval = storage.conn.execute(
        "INSERT INTO evidence_retrievals (account_id,requested_url,final_url,"
        "fetched_at,status,http_status,content_type,fetch_error,raw_size_bytes,"
        "raw_sha256,extracted_chars,extracted_sha256,canonical_text,"
        "canonical_chars,canonical_sha256,truncated,created_at) "
        "VALUES (?,?,?,'2026-07-23 11:01:00','OK',200,'text/plain',NULL,"
        "?,?,?,?,?,?,?,0,'2026-07-23 11:01:00')",
        (
            account.id, _URL, _URL, len(_CANONICAL.encode()),
            _sha(_CANONICAL), len(_CANONICAL), _sha(_CANONICAL),
            _CANONICAL, len(_CANONICAL), _sha(_CANONICAL),
        ),
    )
    retrieval_id = int(retrieval.lastrowid)
    excerpt = storage.conn.execute(
        "INSERT INTO evidence_excerpts (account_id,retrieval_id,claim_text,"
        "claim_sha256,excerpt_text,start_offset,end_offset,created_at) "
        "VALUES (?,?,?,?,?,?,?,'2026-07-23 11:02:00')",
        (
            account.id, retrieval_id, _CLAIM, _sha(_CLAIM), _EXCERPT,
            0, len(_EXCERPT),
        ),
    )
    excerpt_id = int(excerpt.lastrowid)
    research_run_id = f"research-run-{suffix}"
    research_job_id = f"research-job-{suffix}"
    storage.conn.execute(
        "INSERT INTO runs (id,account_id,workflow,status,current_state,started_at,"
        "finished_at,cost_usd,human_intervention_count) "
        "VALUES (?,?,'RESEARCH','DRY_RUN','COMPLETE','2026-07-23 10:00:00',"
        "'2026-07-23 11:03:00',0,0)",
        (research_run_id, account.id),
    )
    storage.conn.execute(
        "INSERT INTO research_runs (id,account_id,topic_id,flow,status,"
        "research_card_id,total_cost_usd,created_at,updated_at) "
        "VALUES (?,?,?,'staged','COMPLETE',?,0,"
        "'2026-07-23 10:00:00','2026-07-23 11:03:00')",
        (research_run_id, account.id, topic.id, card_id),
    )
    storage.conn.execute(
        "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
        "topic_id,run_id,payload_json,schedule_reason,earliest_run_at,attempts,"
        "max_attempts,reserved_cost_usd,created_at,finished_at,updated_at) "
        "VALUES (?,?,'RESEARCH','RESEARCH','DONE',?,?,?,?,'WITHIN_EDITORIAL_WINDOW',"
        "'2026-07-23 10:00:00',1,1,0,'2026-07-23 10:00:00',"
        "'2026-07-23 11:03:00','2026-07-23 11:03:00')",
        (
            research_job_id, account.id, f"idem-{research_job_id}", topic.id,
            research_run_id,
            json.dumps({"execution": "offline_evidence_v1", "dry_run": 1}),
        ),
    )
    candidate = storage.conn.execute(
        "INSERT INTO research_source_candidates (research_run_id,url,title,"
        "verification_status,status,source_quality_score,attempts) "
        "VALUES (?,?,?,'VERIFIED','EXTRACTED',0.95,1)",
        (research_run_id, _URL, "Source"),
    )
    candidate_id = int(candidate.lastrowid)
    storage.conn.execute(
        "INSERT INTO evidence_candidate_retrievals (candidate_id,research_run_id,"
        "account_id,retrieval_id,created_at) VALUES (?,?,?,?,?)",
        (
            candidate_id, research_run_id, account.id, retrieval_id,
            "2026-07-23 11:01:00",
        ),
    )
    storage.conn.execute(
        "INSERT INTO evidence_candidate_excerpts (candidate_id,research_run_id,"
        "account_id,retrieval_id,excerpt_id,created_at) VALUES (?,?,?,?,?,?)",
        (
            candidate_id, research_run_id, account.id, retrieval_id, excerpt_id,
            "2026-07-23 11:02:00",
        ),
    )
    claim_id = f"research-card:{card_id}:confirmed-claim:0"
    lineage_data = {
        "account_id": account.id,
        "candidate_id": candidate_id,
        "confirmed_claim_id": claim_id,
        "confirmed_claim_ordinal": 0,
        "excerpt_id": excerpt_id,
        "research_card_id": card_id,
        "research_job_id": research_job_id,
        "research_run_id": research_run_id,
        "retrieval_id": retrieval_id,
        "source_id": source_id,
        "topic_id": int(topic.id),
    }
    storage.conn.execute(
        "INSERT INTO evidence_source_lineage (source_id,research_card_id,"
        "candidate_id,research_run_id,account_id,retrieval_id,excerpt_id,"
        "created_at,confirmed_claim_ordinal,confirmed_claim_id,"
        "confirmed_claim_sha256,research_job_id,topic_id,lineage_fingerprint) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            source_id, card_id, candidate_id, research_run_id, account.id,
            retrieval_id, excerpt_id, "2026-07-23 11:03:00", 0, claim_id,
            _sha(_CLAIM), research_job_id, topic.id,
            _lineage_fingerprint(lineage_data),
        ),
    )
    storage.conn.commit()
    return {
        "account_id": account.id,
        "topic_id": topic.id,
        "card_id": card_id,
        "source_id": source_id,
        "retrieval_id": retrieval_id,
        "excerpt_id": excerpt_id,
        "candidate_id": candidate_id,
        "research_run_id": research_run_id,
        "research_job_id": research_job_id,
    }


@pytest.fixture
def content_seed(storage: SqliteStorage, account):
    return build_content_seed(storage, account)


def _request(seed, suffix="one", content_type=ContentType.ARTICLE):
    return ContentPreparationRequest(
        job_id=f"content-job-{suffix}",
        idempotency_key=f"content-intent-{suffix}",
        account_id=seed["account_id"],
        research_card_id=seed["card_id"],
        content_type=content_type,
        max_attempts=3,
    )


def _start(storage, seed, suffix="one", content_type=ContentType.ARTICLE):
    request = _request(seed, suffix, content_type)
    prepared = storage.prepare_content_job(
        request, clock=FixedClock(_NOW),
    )
    lease = storage.claim_specific_job(
        request.job_id, "worker-a", 60, clock=FixedClock(_NOW),
    )
    assert lease is not None
    initialized = storage.initialize_content_run_for_job(
        request.job_id,
        "worker-a",
        lease.job.execution_generation,
        f"content-run-{suffix}",
        clock=FixedClock(_NOW),
    )
    execution = JobExecutionContext(
        job_id=request.job_id,
        lease_owner="worker-a",
        run_id=f"content-run-{suffix}",
        clock=FixedClock(_NOW),
        fence_token=lease.job.execution_generation,
        kind=JobKind.CONTENT,
        workflow=WorkflowType(content_type.value),
    )
    return request, prepared, initialized, execution


def _record_content_call_intent(
    storage,
    seed,
    suffix="provider",
    content_type=ContentType.ARTICLE,
):
    request, prepared, initialized, execution = _start(
        storage, seed, suffix, content_type,
    )
    brief_hash = storage.record_content_article_brief(
        execution,
        brief_schema_version="article_brief_v1",
        brief={
            "angle": "Follow the hidden fee",
            "format": "A1",
            "fixture_id": suffix,
        },
    )
    frozen = storage.get_frozen_content_input(
        seed["account_id"], initialized.content.id,
    )
    assert frozen is not None
    intent = ContentCallIntent(
        intent_id=f"call-intent-{suffix}",
        job_id=request.job_id,
        run_id=initialized.run.run_id,
        content_id=initialized.content.id,
        account_id=seed["account_id"],
        research_card_id=seed["card_id"],
        content_type=content_type,
        frozen_input_sha256=frozen.input_sha256,
        article_brief_sha256=brief_hash,
        evidence_manifest_sha256=frozen.evidence_manifest_sha256,
        provider="anthropic",
        model="test-model",
        pricing_profile_id="test-profile",
        pricing_profile_version="v1",
        pricing_fingerprint="a" * 64,
        max_input_tokens=20000,
        max_context_tokens=30000,
        max_output_tokens=6000,
        prompt_version=frozen.prompt_version,
        style_guide_version=frozen.style_guide_version,
        output_schema_version=frozen.output_schema_version,
        max_cost_usd=0.15,
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=15),
    )
    storage.record_content_call_intent(execution, intent)
    return request, prepared, initialized, execution, intent


_CONTENT_EXTENSION_INSERT = (
    "INSERT INTO content_provider_attempts (request_id,intent_id,job_id,run_id,"
    "content_id,account_id,stage,attempt_no,provider,model,created_at) "
    "VALUES (:request_id,:intent_id,:job_id,:run_id,:content_id,:account_id,"
    ":stage,:attempt_no,:provider,:model,:created_at)"
)


def _content_extension_values(intent, **overrides):
    values = {
        "request_id": f"{intent.job_id}:content_draft:1",
        "intent_id": intent.intent_id,
        "job_id": intent.job_id,
        "run_id": intent.run_id,
        "content_id": intent.content_id,
        "account_id": intent.account_id,
        "stage": intent.stage,
        "attempt_no": intent.attempt_no,
        "provider": intent.provider,
        "model": intent.model,
        "created_at": "2026-07-23 12:00:00",
    }
    values.update(overrides)
    return values


def _insert_foreign_provider_attempt(storage, seed, kind, suffix):
    if kind == "RESEARCH":
        job_id = seed["research_job_id"]
    else:
        job_id = f"foreign-{kind.lower()}-{suffix}"
        storage.conn.execute(
            "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
            "topic_id,payload_json,schedule_reason,earliest_run_at,attempts,"
            "max_attempts,reserved_cost_usd,created_at,finished_at,updated_at) "
            "VALUES (?,?,?,?, 'DONE', ?,?, '{}','TEST',?,0,1,0,?,?,?)",
            (
                job_id,
                seed["account_id"],
                kind,
                "ARTICLE" if kind == "LOCAL" else "TOPIC_GENERATION",
                f"foreign-idempotency-{kind.lower()}-{suffix}",
                None,
                "2026-07-23 11:00:00",
                "2026-07-23 11:00:00",
                "2026-07-23 11:00:00",
                "2026-07-23 11:00:00",
            ),
        )
    request_id = f"{job_id}:content_draft:1"
    storage.conn.execute(
        "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,"
        "status,reserved_amount_usd,reserved_at,execution_intent_fingerprint) "
        "VALUES (?,'content_draft',1,?,'RESERVED',0.15,?,?)",
        (job_id, request_id, "2026-07-23 12:00:00", "f" * 64),
    )
    storage.conn.commit()
    return request_id


def _clone_research_card(storage, seed, confirmed_claims):
    cursor = storage.conn.execute(
        "INSERT INTO research_cards (topic_id,question,thesis,mechanism,facts_json,"
        "counterargument,citable_numbers,visual_idea,confidence,working_thesis,"
        "confirmed_claims,uncertain_claims,contradictions,source_quality_score,"
        "publication_recommendation,rejection_reason,created_at) "
        "SELECT topic_id,question,thesis,mechanism,facts_json,counterargument,"
        "citable_numbers,visual_idea,confidence,working_thesis,?,uncertain_claims,"
        "contradictions,source_quality_score,publication_recommendation,"
        "rejection_reason,'2026-07-23 11:10:00' "
        "FROM research_cards WHERE id=?",
        (json.dumps(confirmed_claims), seed["card_id"]),
    )
    storage.conn.commit()
    return {**seed, "card_id": int(cursor.lastrowid)}


@pytest.mark.parametrize("content_type", [ContentType.ARTICLE, ContentType.NOTE])
def test_prepare_freezes_complete_lineage_and_holds_job_from_ordinary_queue(
    storage, content_seed, content_type,
):
    request = _request(content_seed, content_type.value.lower(), content_type)
    result = storage.prepare_content_job(request, clock=FixedClock(_NOW))
    assert result.job_created is True
    assert result.content.status is ContentStatus.PREPARED
    assert result.content.run_id is None
    assert len(result.frozen_input.evidence_items) == 1
    item = result.frozen_input.evidence_items[0]
    assert (
        item.source_id,
        item.excerpt_id,
        item.retrieval_id,
    ) == (
        content_seed["source_id"],
        content_seed["excerpt_id"],
        content_seed["retrieval_id"],
    )
    job = storage.get_job(request.job_id)
    assert job is not None
    assert job.kind is JobKind.CONTENT
    assert job.workflow is WorkflowType(content_type.value)
    assert job.payload["provider_enabled"] is False
    assert storage.claim_next_job("ordinary", 60, clock=FixedClock(_NOW)) is None
    assert storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM jobs WHERE kind='BROWSER'"
    ).fetchone()[0] == 0
    persisted = storage.conn.execute(
        "SELECT scheduled_at,published_at,external_url FROM content_items WHERE id=?",
        (result.content.id,),
    ).fetchone()
    assert tuple(persisted) == (None, None, None)


def test_content_models_reject_invalid_closed_contracts(content_seed):
    with pytest.raises(ValueError):
        ContentPreparationRequest(
            job_id=" content-job",
            idempotency_key="intent",
            account_id=content_seed["account_id"],
            research_card_id=content_seed["card_id"],
            content_type=ContentType.ARTICLE,
        )
    with pytest.raises(ValueError):
        ContentPreparationRequest(
            job_id="content-job",
            idempotency_key="intent",
            account_id=content_seed["account_id"],
            research_card_id=content_seed["card_id"],
            content_type=ContentType.ARTICLE,
            max_attempts=1,
        )


def test_preparation_is_idempotent_after_file_reopen(settings, content_seed):
    storage = SqliteStorage.open(settings.db_path)
    try:
        request = _request(content_seed)
        first = storage.prepare_content_job(request, clock=FixedClock(_NOW))
    finally:
        storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        second = reopened.prepare_content_job(request, clock=FixedClock(_NOW))
        assert second.job_created is False
        assert second.content.id == first.content.id
        assert second.frozen_input.input_sha256 == first.frozen_input.input_sha256
        assert reopened.conn.execute(
            "SELECT count(*) FROM content_items"
        ).fetchone()[0] == 1
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "point",
    [
        ContentInitializationFaultPoint.AFTER_CONTENT_INSERT,
        ContentInitializationFaultPoint.AFTER_FROZEN_INPUT_INSERT,
        ContentInitializationFaultPoint.AFTER_EVIDENCE_INSERTS,
        ContentInitializationFaultPoint.AFTER_JOB_INSERT,
        ContentInitializationFaultPoint.BEFORE_PREPARATION_COMMIT,
    ],
)
def test_preparation_failpoints_roll_back_every_row(storage, content_seed, point):
    request = _request(content_seed, point.value.lower())

    def fail(observed):
        if observed is point:
            raise RuntimeError(f"fault {point.value}")

    with pytest.raises(RuntimeError, match="fault"):
        storage.prepare_content_job(
            request, clock=FixedClock(_NOW), fault_point=fail,
        )
    for table in (
        "content_items",
        "content_frozen_inputs",
        "content_evidence_items",
        "jobs",
        "runs",
        "content_runs",
    ):
        if table == "jobs":
            count = storage.conn.execute(
                "SELECT count(*) FROM jobs WHERE kind='CONTENT'"
            ).fetchone()[0]
        elif table == "runs":
            count = storage.conn.execute(
                "SELECT count(*) FROM runs WHERE workflow IN ('ARTICLE','NOTE')"
            ).fetchone()[0]
        else:
            count = storage.conn.execute(
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0]
        assert count == 0


@pytest.mark.parametrize(
    "point",
    [
        ContentInitializationFaultPoint.AFTER_RUN_INSERT,
        ContentInitializationFaultPoint.AFTER_CONTENT_RUN_INSERT,
        ContentInitializationFaultPoint.AFTER_JOB_RUN_ATTACH,
        ContentInitializationFaultPoint.BEFORE_RUN_INITIALIZATION_COMMIT,
    ],
)
def test_run_initialization_failpoints_leave_prepared_job_recoverable(
    storage, content_seed, point,
):
    request = _request(content_seed, point.value.lower())
    prepared = storage.prepare_content_job(request, clock=FixedClock(_NOW))
    lease = storage.claim_specific_job(
        request.job_id, "worker-a", 60, clock=FixedClock(_NOW),
    )
    assert lease is not None

    def fail(observed):
        if observed is point:
            raise RuntimeError(f"fault {point.value}")

    with pytest.raises(RuntimeError, match="fault"):
        storage.initialize_content_run_for_job(
            request.job_id, "worker-a", lease.job.execution_generation,
            f"run-{point.value}",
            clock=FixedClock(_NOW), fault_point=fail,
        )
    job = storage.get_job(request.job_id)
    item = storage.get_content_item(content_seed["account_id"], prepared.content.id)
    assert job is not None and job.run_id is None and job.status is JobStatus.LEASED
    assert item is not None and item.run_id is None and item.status is ContentStatus.PREPARED
    assert storage.conn.execute(
        "SELECT count(*) FROM runs WHERE workflow IN ('ARTICLE','NOTE')"
    ).fetchone()[0] == 0
    assert storage.conn.execute("SELECT count(*) FROM content_runs").fetchone()[0] == 0


def test_run_initialization_is_atomic_and_idempotent(storage, content_seed):
    request, _, initialized, execution = _start(storage, content_seed)
    assert initialized.run is not None
    assert initialized.run.status is ContentStatus.RUNNING
    assert initialized.content.status is ContentStatus.RUNNING
    repeated = storage.initialize_content_run_for_job(
        request.job_id, "worker-a", execution.fence_token, "content-run-one",
        clock=FixedClock(_NOW),
    )
    assert repeated.run is not None
    assert repeated.run.run_id == "content-run-one"
    assert storage.conn.execute(
        "SELECT count(*) FROM runs WHERE workflow IN ('ARTICLE','NOTE')"
    ).fetchone()[0] == 1
    assert storage.conn.execute("SELECT count(*) FROM content_runs").fetchone()[0] == 1


def test_initialized_run_reopens_with_exact_durable_relations(settings, content_seed):
    storage = SqliteStorage.open(settings.db_path)
    try:
        request, prepared, initialized, _ = _start(storage, content_seed)
        assert initialized.run is not None
        content_id = prepared.content.id
        run_id = initialized.run.run_id
    finally:
        storage.close()
    reopened = SqliteStorage.open(settings.db_path)
    try:
        content = reopened.get_content_item(content_seed["account_id"], content_id)
        frozen = reopened.assert_content_snapshot(
            content_seed["account_id"], content_id,
        )
        job = reopened.get_job(request.job_id)
        run = reopened.get_run(run_id)
        assert content is not None and content.run_id == run_id
        assert job is not None and job.run_id == run_id
        assert run is not None and run.account_id == content_seed["account_id"]
        assert content.input_sha256 == frozen.input_sha256
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reopened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()


def test_snapshot_drift_between_prepare_and_start_fails_closed(storage, content_seed):
    request = _request(content_seed)
    prepared = storage.prepare_content_job(request, clock=FixedClock(_NOW))
    storage.conn.execute(
        "UPDATE research_cards SET working_thesis='Changed after validation' WHERE id=?",
        (content_seed["card_id"],),
    )
    storage.conn.commit()
    lease = storage.claim_specific_job(
        request.job_id, "worker-a", 60, clock=FixedClock(_NOW),
    )
    assert lease is not None
    with pytest.raises(ContentSnapshotError, match="FROZEN_INPUT_DRIFT"):
        storage.initialize_content_run_for_job(
            request.job_id, "worker-a", lease.job.execution_generation,
            "run-drift", clock=FixedClock(_NOW),
        )
    item = storage.get_content_item(content_seed["account_id"], prepared.content.id)
    assert item is not None and item.status is ContentStatus.PREPARED and item.run_id is None
    assert storage.conn.execute(
        "SELECT count(*) FROM runs WHERE workflow IN ('ARTICLE','NOTE')"
    ).fetchone()[0] == 0


def test_source_or_evidence_mismatch_is_rejected_without_mutation(storage, content_seed):
    request = _request(content_seed)
    prepared = storage.prepare_content_job(request, clock=FixedClock(_NOW))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE evidence_excerpts SET claim_sha256=? WHERE id=?",
            ("0" * 64, content_seed["excerpt_id"]),
        )
    storage.conn.rollback()
    storage.conn.execute(
        "UPDATE sources SET supports_claim='Changed source claim' WHERE id=?",
        (content_seed["source_id"],),
    )
    storage.conn.commit()
    with pytest.raises(
        ContentSnapshotError, match="CONTENT_LINEAGE_FINGERPRINT_INVALID"
    ):
        storage.assert_content_snapshot(
            content_seed["account_id"], prepared.content.id,
        )
    assert storage.get_frozen_content_input(
        content_seed["account_id"], prepared.content.id,
    ).input_sha256 == prepared.frozen_input.input_sha256


def test_frozen_content_rows_are_immutable_at_the_sql_floor(storage, content_seed):
    prepared = storage.prepare_content_job(
        _request(content_seed), clock=FixedClock(_NOW),
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE content_frozen_inputs SET prompt_version='tampered' "
            "WHERE content_id=?",
            (prepared.content.id,),
        )
    storage.conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        storage.conn.execute(
            "UPDATE content_evidence_items SET source_url='https://tampered.test' "
            "WHERE content_id=?",
            (prepared.content.id,),
        )
    storage.conn.rollback()
    frozen = storage.get_frozen_content_input(
        content_seed["account_id"], prepared.content.id,
    )
    assert frozen is not None
    assert frozen.input_sha256 == prepared.frozen_input.input_sha256


def test_account_card_mismatch_and_missing_evidence_fail_closed(
    storage, account, content_seed,
):
    other = account.model_copy(update={"id": "other"})
    storage.ensure_account(other)
    with pytest.raises(ContentSnapshotError, match="ACCOUNT_CARD_MISMATCH"):
        storage.prepare_content_job(ContentPreparationRequest(
            job_id="foreign", idempotency_key="foreign", account_id=other.id,
            research_card_id=content_seed["card_id"],
            content_type=ContentType.ARTICLE,
        ), clock=FixedClock(_NOW))
    cursor = storage.conn.execute(
        "INSERT INTO research_cards (topic_id,question,thesis,mechanism,facts_json,"
        "counterargument,citable_numbers,visual_idea,confidence,working_thesis,"
        "confirmed_claims,uncertain_claims,contradictions,source_quality_score,"
        "publication_recommendation,rejection_reason,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            content_seed["topic_id"], "No lineage?", "Missing lineage.",
            "No evidence relation.", "[]", "None.", "[]", "None.", 0.9,
            "Missing lineage.", json.dumps([_CLAIM]), "[]", "[]", 0.95,
            "PROCEED", None, "2026-07-23 11:10:00",
        ),
    )
    storage.conn.commit()
    seed_without_lineage = {
        **content_seed,
        "card_id": int(cursor.lastrowid),
    }
    with pytest.raises(ContentSnapshotError, match="EVIDENCE_INCOMPLETE"):
        storage.prepare_content_job(
            _request(seed_without_lineage, "no-evidence"), clock=FixedClock(_NOW),
        )
    assert storage.conn.execute("SELECT count(*) FROM content_items").fetchone()[0] == 0


def test_same_active_content_intent_cannot_be_created_twice(storage, content_seed):
    storage.prepare_content_job(_request(content_seed, "first"), clock=FixedClock(_NOW))
    with pytest.raises(ContentFoundationError, match="CONTENT_DURABLE_CONFLICT"):
        storage.prepare_content_job(
            _request(content_seed, "second"), clock=FixedClock(_NOW),
        )
    assert storage.conn.execute("SELECT count(*) FROM content_items").fetchone()[0] == 1


def test_legal_lifecycle_revise_resume_and_pending_approval(storage, content_seed):
    _, _, _, execution = _start(storage, content_seed)
    revise = storage.transition_content_execution(
        execution, ContentStatus.REVISE, reason_code="STYLE_BELOW_THRESHOLD",
    )
    assert revise.content.status is ContentStatus.REVISE
    prepared = storage.transition_content_execution(
        execution, ContentStatus.PREPARED,
    )
    assert prepared.content.status is ContentStatus.PREPARED
    running = storage.transition_content_execution(
        execution, ContentStatus.RUNNING,
    )
    assert running.content.status is ContentStatus.RUNNING
    done = storage.transition_content_execution(
        execution,
        ContentStatus.PENDING_APPROVAL,
        final_result={"audits": ["FACT", "STYLE", "GROWTH"]},
        score=0.91,
    )
    assert done.content.status is ContentStatus.PENDING_APPROVAL
    assert done.run.finished_at is not None
    assert storage.get_job(execution.job_id).status is JobStatus.DONE
    assert storage.get_run(execution.run_id).status.value == "SUCCESS"


def test_sql_floor_rejects_every_illegal_content_run_transition(
    storage, content_seed,
):
    _, _, initialized, _ = _start(storage, content_seed)
    assert initialized.run is not None
    run_id = initialized.run.run_id
    states = {
        ContentStatus.PREPARED,
        ContentStatus.RUNNING,
        ContentStatus.REVISE,
        ContentStatus.SKIPPED,
        ContentStatus.PENDING_APPROVAL,
        ContentStatus.FAILED,
        ContentStatus.NEEDS_VERIFICATION,
    }
    rejected = 0
    for target in states - {ContentStatus.RUNNING}:
        reason = (
            "TEST_REASON"
            if target in {
                ContentStatus.REVISE,
                ContentStatus.SKIPPED,
                ContentStatus.FAILED,
                ContentStatus.NEEDS_VERIFICATION,
            }
            else None
        )
        finished = (
            "2026-07-23 12:00:01.000000"
            if target in {
                ContentStatus.SKIPPED,
                ContentStatus.PENDING_APPROVAL,
                ContentStatus.FAILED,
                ContentStatus.NEEDS_VERIFICATION,
            }
            else None
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="content_runs may change only through a transition command",
        ):
            storage.conn.execute(
                "UPDATE content_runs SET status=?,reason_code=?,finished_at=? "
                "WHERE run_id=?",
                (target.value, reason, finished, run_id),
            )
        storage.conn.rollback()
        rejected += 1
    assert rejected == len(states) - 1


@pytest.mark.parametrize(
    ("target", "reason", "job_status", "run_status"),
    [
        (ContentStatus.SKIPPED, "NO_DEFENSIBLE_ANGLE", JobStatus.DONE, "SUCCESS"),
        (ContentStatus.FAILED, "CONTENT_PIPELINE_ERROR", JobStatus.FAILED, "FAILED"),
        (
            ContentStatus.NEEDS_VERIFICATION,
            "AMBIGUOUS_EXECUTION",
            JobStatus.NEEDS_VERIFICATION,
            "STOPPED",
        ),
    ],
)
def test_controlled_terminal_results_are_atomic(
    storage, content_seed, target, reason, job_status, run_status,
):
    _, _, _, execution = _start(storage, content_seed, target.value.lower())
    result = storage.transition_content_execution(
        execution, target, reason_code=reason,
        final_result={"result": target.value},
    )
    assert result.content.status is target
    assert result.run.status is target
    assert storage.get_job(execution.job_id).status is job_status
    assert storage.get_run(execution.run_id).status.value == run_status


def test_identical_terminalization_is_noop_and_conflict_does_not_mutate(
    storage, content_seed,
):
    _, _, _, execution = _start(storage, content_seed)
    first = storage.transition_content_execution(
        execution, ContentStatus.SKIPPED,
        reason_code="NO_DEFENSIBLE_ANGLE", final_result={"decision": "SKIP"},
    )
    second = storage.transition_content_execution(
        execution, ContentStatus.SKIPPED,
        reason_code="NO_DEFENSIBLE_ANGLE", final_result={"decision": "SKIP"},
    )
    assert first.idempotent is False and second.idempotent is True
    with pytest.raises(LifecycleTransitionError):
        storage.transition_content_execution(
            execution, ContentStatus.FAILED,
            reason_code="CONFLICTING_TERMINAL",
        )
    assert storage.get_content_item(
        content_seed["account_id"], first.content.id,
    ).status is ContentStatus.SKIPPED


def test_old_owner_write_is_rejected_after_safe_takeover(storage, content_seed):
    request, _, initialized, old_execution = _start(storage, content_seed)
    assert initialized.run is not None
    later = _NOW + timedelta(seconds=61)
    recovered = storage.release_or_requeue_expired_leases(clock=FixedClock(later))
    assert recovered.requeued_count == 1
    item = storage.get_content_item(
        content_seed["account_id"], initialized.content.id,
    )
    assert item is not None and item.status is ContentStatus.PREPARED
    takeover = storage.claim_specific_job(
        request.job_id, "worker-b", 60, clock=FixedClock(later),
    )
    assert takeover is not None
    resumed = storage.initialize_content_run_for_job(
        request.job_id, "worker-b", takeover.job.execution_generation,
        initialized.run.run_id,
        clock=FixedClock(later),
    )
    assert resumed.run is not None and resumed.run.status is ContentStatus.RUNNING
    with pytest.raises((StaleJobExecutionError, LifecycleTransitionError)):
        storage.transition_content_execution(
            old_execution, ContentStatus.SKIPPED,
            reason_code="STALE_OWNER",
        )


def test_ambiguous_boundary_never_requeues_or_retries(storage, content_seed):
    request, _, initialized, execution = _start(storage, content_seed)
    storage.conn.execute(
        "UPDATE jobs SET external_effect_started_at=? WHERE id=? "
        "AND lease_owner=? AND execution_generation=?",
        (
            _NOW.isoformat(), execution.job_id, execution.lease_owner,
            execution.fence_token,
        ),
    )
    storage.conn.commit()
    later = _NOW + timedelta(seconds=61)
    recovered = storage.release_or_requeue_expired_leases(clock=FixedClock(later))
    assert recovered.needs_verification_count == 1
    assert recovered.requeued_count == 0
    assert storage.get_job(request.job_id).status is JobStatus.NEEDS_VERIFICATION
    assert storage.get_content_item(
        content_seed["account_id"], initialized.content.id,
    ).status is ContentStatus.NEEDS_VERIFICATION
    assert storage.claim_specific_job(
        request.job_id, "worker-b", 60, clock=FixedClock(later),
    ) is None


def test_content_provider_attempt_creates_strict_canonical_and_extension_pair(
    storage, content_seed,
):
    request, _, initialized, execution = _start(storage, content_seed)
    assert initialized.run is not None
    brief_hash = storage.record_content_article_brief(
        execution,
        brief_schema_version="article_brief_v1",
        brief={"angle": "Follow the hidden fee", "format": "A1"},
    )
    frozen = storage.get_frozen_content_input(
        content_seed["account_id"], initialized.content.id,
    )
    assert frozen is not None
    intent = ContentCallIntent(
        intent_id="call-intent-one",
        job_id=request.job_id,
        run_id=initialized.run.run_id,
        content_id=initialized.content.id,
        account_id=content_seed["account_id"],
        research_card_id=content_seed["card_id"],
        content_type=ContentType.ARTICLE,
        frozen_input_sha256=frozen.input_sha256,
        article_brief_sha256=brief_hash,
        evidence_manifest_sha256=frozen.evidence_manifest_sha256,
        provider="anthropic",
        model="test-model",
        pricing_profile_id="test-profile",
        pricing_profile_version="v1",
        pricing_fingerprint="a" * 64,
        max_input_tokens=20000,
        max_context_tokens=30000,
        max_output_tokens=6000,
        prompt_version=frozen.prompt_version,
        style_guide_version=frozen.style_guide_version,
        output_schema_version=frozen.output_schema_version,
        max_cost_usd=0.15,
        created_at=_NOW,
        expires_at=_NOW + timedelta(minutes=15),
    )
    storage.record_content_call_intent(execution, intent)
    attempt = storage.begin_provider_attempt(
        execution,
        stage="content_draft",
        attempt_no=1,
        max_cost_usd=0.15,
        daily_limit_usd=2,
        monthly_limit_usd=40,
    )
    assert attempt.request_id == f"{request.job_id}:content_draft:1"
    pair = storage.conn.execute(
        "SELECT pa.request_id,pa.job_id,pa.stage,pa.attempt_no,"
        "cpa.intent_id,cpa.run_id,cpa.content_id,cpa.account_id,"
        "cpa.provider,cpa.model "
        "FROM provider_attempts pa JOIN content_provider_attempts cpa "
        "ON cpa.request_id=pa.request_id WHERE pa.request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert pair is not None
    assert dict(pair) == {
        "request_id": attempt.request_id,
        "job_id": request.job_id,
        "stage": "content_draft",
        "attempt_no": 1,
        "intent_id": intent.intent_id,
        "run_id": initialized.run.run_id,
        "content_id": initialized.content.id,
        "account_id": content_seed["account_id"],
        "provider": intent.provider,
        "model": intent.model,
    }
    with pytest.raises(sqlite3.IntegrityError, match="exact 1:1 extension"):
        storage.conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,"
            "status,reserved_amount_usd,reserved_at,execution_intent_fingerprint) "
            "VALUES (?,?,2,?,'RESERVED',0.15,?,?)",
            (
                request.job_id, "content_draft",
                f"{request.job_id}:content_draft:2",
                "2026-07-23 12:00:00", intent.fingerprint(),
            ),
        )
    storage.conn.rollback()
    assert storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 1
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_attempts"
    ).fetchone()[0] == 1


def test_c1_counterexample_01_content_without_authoritative_lineage_is_rejected(
    storage, content_seed,
):
    seed = _clone_research_card(storage, content_seed, [_CLAIM])
    with pytest.raises(ContentSnapshotError, match="EVIDENCE_INCOMPLETE"):
        storage.prepare_content_job(
            _request(seed, "counterexample-01"), clock=FixedClock(_NOW),
        )
    assert storage.conn.execute(
        "SELECT count(*) FROM jobs WHERE kind='CONTENT'"
    ).fetchone()[0] == 0


def test_c1_counterexample_02_equal_claim_texts_keep_distinct_claim_ids(
    storage, content_seed,
):
    storage.conn.execute(
        "UPDATE research_cards SET confirmed_claims=? WHERE id=?",
        (json.dumps([_CLAIM, _CLAIM]), content_seed["card_id"]),
    )
    storage.conn.commit()
    with pytest.raises(ContentSnapshotError, match="EVIDENCE_INCOMPLETE"):
        storage.prepare_content_job(
            _request(content_seed, "counterexample-02"), clock=FixedClock(_NOW),
        )


def test_c1_counterexample_03_same_url_with_different_source_id_is_not_lineage(
    storage, content_seed,
):
    other_claim = "A second claim shares the same public URL."
    storage.conn.execute(
        "UPDATE research_cards SET confirmed_claims=? WHERE id=?",
        (json.dumps([_CLAIM, other_claim]), content_seed["card_id"]),
    )
    other_source = storage.conn.execute(
        "INSERT INTO sources (research_card_id,url,title,source_type,verified,"
        "author_or_org,supports_claim,verification_status) "
        "VALUES (?,?,?,'PRIMARY',1,'Other Org',?,'VERIFIED')",
        (content_seed["card_id"], _URL, "Same URL, other source", other_claim),
    )
    storage.conn.commit()
    assert int(other_source.lastrowid) != content_seed["source_id"]
    with pytest.raises(ContentSnapshotError, match="EVIDENCE_INCOMPLETE"):
        storage.prepare_content_job(
            _request(content_seed, "counterexample-03"), clock=FixedClock(_NOW),
        )


def test_c1_counterexample_04_text_matching_excerpt_for_other_claim_is_rejected(
    storage, content_seed,
):
    other_claim = "A matching excerpt belongs to a different durable claim."
    storage.conn.execute(
        "UPDATE research_cards SET confirmed_claims=? WHERE id=?",
        (json.dumps([_CLAIM, other_claim]), content_seed["card_id"]),
    )
    storage.conn.execute(
        "INSERT INTO sources (research_card_id,url,title,source_type,verified,"
        "author_or_org,supports_claim,verification_status) "
        "VALUES (?,?,?,'PRIMARY',1,'Other Org',?,'VERIFIED')",
        (content_seed["card_id"], _URL, "Text-only source", other_claim),
    )
    storage.conn.execute(
        "INSERT INTO evidence_excerpts (account_id,retrieval_id,claim_text,"
        "claim_sha256,excerpt_text,start_offset,end_offset,created_at) "
        "VALUES (?,?,?,?,?,0,?,'2026-07-23 11:12:00')",
        (
            content_seed["account_id"], content_seed["retrieval_id"],
            other_claim, _sha(other_claim), _EXCERPT, len(_EXCERPT),
        ),
    )
    storage.conn.commit()
    with pytest.raises(ContentSnapshotError, match="EVIDENCE_INCOMPLETE"):
        storage.prepare_content_job(
            _request(content_seed, "counterexample-04"), clock=FixedClock(_NOW),
        )


def test_c1_counterexample_05_complete_job_rejects_content(storage, content_seed):
    request, _, initialized, _ = _start(
        storage, content_seed, "counterexample-05",
    )
    with pytest.raises(
        ContentFoundationError,
        match="CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
    ):
        storage.complete_job(
            request.job_id, "worker-a", clock=FixedClock(_NOW),
        )
    assert storage.get_job(request.job_id).status is JobStatus.RUNNING
    assert initialized.run.status is ContentStatus.RUNNING


def test_c1_counterexample_06_fail_job_rejects_content(storage, content_seed):
    request, _, initialized, _ = _start(
        storage, content_seed, "counterexample-06",
    )
    with pytest.raises(
        ContentFoundationError,
        match="CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
    ):
        storage.fail_job(
            request.job_id, "worker-a", "forced", clock=FixedClock(_NOW),
        )
    assert storage.get_job(request.job_id).status is JobStatus.RUNNING
    assert initialized.run.status is ContentStatus.RUNNING


def test_c1_counterexample_07_needs_verification_helper_rejects_content(
    storage, content_seed,
):
    request, _, initialized, _ = _start(
        storage, content_seed, "counterexample-07",
    )
    with pytest.raises(
        ContentFoundationError,
        match="CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
    ):
        storage.mark_job_needs_verification(
            request.job_id, "worker-a", "forced", clock=FixedClock(_NOW),
        )
    assert storage.get_job(request.job_id).status is JobStatus.RUNNING
    assert initialized.run.status is ContentStatus.RUNNING


def test_generic_cancel_job_rejects_prepared_content(storage, content_seed):
    request = _request(content_seed, "generic-cancel")
    storage.prepare_content_job(request, clock=FixedClock(_NOW))
    with pytest.raises(
        ContentFoundationError,
        match="CONTENT_GENERIC_JOB_TERMINALIZATION_FORBIDDEN",
    ):
        storage.cancel_job(request.job_id, clock=FixedClock(_NOW))
    assert storage.get_job(request.job_id).status is JobStatus.QUEUED


def test_sql_floor_rejects_terminal_content_job_before_run(storage, content_seed):
    request = _request(content_seed, "raw-terminal-before-run")
    storage.prepare_content_job(request, clock=FixedClock(_NOW))
    with pytest.raises(sqlite3.IntegrityError, match="content command"):
        storage.conn.execute(
            "UPDATE jobs SET status='DONE',finished_at=?,updated_at=? WHERE id=?",
            (
                "2026-07-23 12:00:00",
                "2026-07-23 12:00:00",
                request.job_id,
            ),
        )
    storage.conn.rollback()
    assert storage.get_job(request.job_id).status is JobStatus.QUEUED


def test_sql_floor_rejects_partial_general_run_terminal_fields(
    storage, content_seed,
):
    _, _, initialized, _ = _start(storage, content_seed, "raw-run-fields")
    with pytest.raises(sqlite3.IntegrityError, match="transition command"):
        storage.conn.execute(
            "UPDATE runs SET finished_at=?,current_state='SKIPPED' WHERE id=?",
            ("2026-07-23 12:00:00", initialized.run.run_id),
        )
    storage.conn.rollback()
    run = storage.get_run(initialized.run.run_id)
    assert run.status.value == "RUNNING"
    assert run.finished_at is None


def test_c1_counterexample_08_raw_content_run_terminalization_is_rejected(
    storage, content_seed,
):
    _, _, initialized, _ = _start(
        storage, content_seed, "counterexample-08",
    )
    with pytest.raises(sqlite3.IntegrityError, match="transition command"):
        storage.conn.execute(
            "UPDATE content_runs SET status='SKIPPED',"
            "reason_code='RAW_TERMINALIZATION',"
            "finished_at='2026-07-23 12:00:01' WHERE run_id=?",
            (initialized.run.run_id,),
        )
    storage.conn.rollback()
    assert storage.get_run(initialized.run.run_id).status.value == "RUNNING"


def test_c1_counterexample_09_terminal_content_with_running_job_run_is_rejected(
    storage, content_seed,
):
    request, _, initialized, _ = _start(
        storage, content_seed, "counterexample-09",
    )
    with pytest.raises(sqlite3.IntegrityError, match="transition command"):
        storage.conn.execute(
            "UPDATE content_items SET status='SKIPPED',"
            "reason_code='RAW_TERMINALIZATION' WHERE id=?",
            (initialized.content.id,),
        )
    storage.conn.rollback()
    assert storage.get_job(request.job_id).status is JobStatus.RUNNING
    assert storage.get_run(initialized.run.run_id).status.value == "RUNNING"


def test_c1_counterexample_10_old_owner_cannot_replay_new_owner_terminal_result(
    storage, content_seed,
):
    request, _, initialized, old_execution = _start(
        storage, content_seed, "counterexample-10",
    )
    later = _NOW + timedelta(seconds=61)
    storage.release_or_requeue_expired_leases(clock=FixedClock(later))
    takeover = storage.claim_specific_job(
        request.job_id, "worker-b", 60, clock=FixedClock(later),
    )
    assert takeover is not None
    storage.initialize_content_run_for_job(
        request.job_id,
        "worker-b",
        takeover.job.execution_generation,
        initialized.run.run_id,
        clock=FixedClock(later),
    )
    current_execution = JobExecutionContext(
        job_id=request.job_id,
        lease_owner="worker-b",
        run_id=initialized.run.run_id,
        clock=FixedClock(later),
        fence_token=takeover.job.execution_generation,
        kind=JobKind.CONTENT,
        workflow=WorkflowType.ARTICLE,
    )
    storage.transition_content_execution(
        current_execution,
        ContentStatus.SKIPPED,
        reason_code="SAME_TERMINAL_PAYLOAD",
    )
    with pytest.raises(StaleJobExecutionError):
        storage.transition_content_execution(
            old_execution,
            ContentStatus.SKIPPED,
            reason_code="SAME_TERMINAL_PAYLOAD",
        )


def test_c1_counterexample_11_terminal_replay_after_lease_expiry_is_rejected(
    storage, content_seed,
):
    request, _, initialized, execution = _start(
        storage, content_seed, "counterexample-11",
    )
    storage.transition_content_execution(
        execution,
        ContentStatus.SKIPPED,
        reason_code="EXPIRED_REPLAY",
    )
    expired_execution = JobExecutionContext(
        job_id=request.job_id,
        lease_owner=execution.lease_owner,
        run_id=initialized.run.run_id,
        clock=FixedClock(_NOW + timedelta(seconds=61)),
        fence_token=execution.fence_token,
        kind=JobKind.CONTENT,
        workflow=WorkflowType.ARTICLE,
    )
    with pytest.raises(StaleJobExecutionError):
        storage.transition_content_execution(
            expired_execution,
            ContentStatus.SKIPPED,
            reason_code="EXPIRED_REPLAY",
        )


def test_c1_counterexample_12_same_owner_string_with_old_fence_is_rejected(
    storage, content_seed,
):
    request, _, initialized, old_execution = _start(
        storage, content_seed, "counterexample-12",
    )
    later = _NOW + timedelta(seconds=61)
    storage.release_or_requeue_expired_leases(clock=FixedClock(later))
    takeover = storage.claim_specific_job(
        request.job_id, "worker-a", 60, clock=FixedClock(later),
    )
    assert takeover is not None
    assert takeover.job.execution_generation > old_execution.fence_token
    storage.initialize_content_run_for_job(
        request.job_id,
        "worker-a",
        takeover.job.execution_generation,
        initialized.run.run_id,
        clock=FixedClock(later),
    )
    with pytest.raises(StaleJobExecutionError):
        storage.transition_content_execution(
            old_execution,
            ContentStatus.SKIPPED,
            reason_code="ABA_REJECTED",
        )


def test_c1_counterexample_13_note_context_rejects_durable_article(
    storage, content_seed,
):
    request, _, initialized, execution = _start(
        storage, content_seed, "counterexample-13", ContentType.ARTICLE,
    )
    wrong = JobExecutionContext(
        job_id=request.job_id,
        lease_owner=execution.lease_owner,
        run_id=initialized.run.run_id,
        clock=execution.clock,
        fence_token=execution.fence_token,
        kind=JobKind.CONTENT,
        workflow=WorkflowType.NOTE,
    )
    with pytest.raises(
        ContentFoundationError, match="CONTENT_EXECUTION_RELATION_INVALID",
    ):
        storage.transition_content_execution(wrong, ContentStatus.REVISE, reason_code="WRONG_TYPE")
    assert storage.get_content_item(
        content_seed["account_id"], initialized.content.id,
    ).status is ContentStatus.RUNNING


def test_c1_counterexample_14_article_context_rejects_durable_note(
    storage, content_seed,
):
    request, _, initialized, execution = _start(
        storage, content_seed, "counterexample-14", ContentType.NOTE,
    )
    wrong = JobExecutionContext(
        job_id=request.job_id,
        lease_owner=execution.lease_owner,
        run_id=initialized.run.run_id,
        clock=execution.clock,
        fence_token=execution.fence_token,
        kind=JobKind.CONTENT,
        workflow=WorkflowType.ARTICLE,
    )
    with pytest.raises(
        ContentFoundationError, match="CONTENT_EXECUTION_RELATION_INVALID",
    ):
        storage.transition_content_execution(wrong, ContentStatus.REVISE, reason_code="WRONG_TYPE")
    assert storage.get_content_item(
        content_seed["account_id"], initialized.content.id,
    ).status is ContentStatus.RUNNING


@pytest.mark.parametrize(
    ("kind", "number"),
    [
        ("LOCAL", 15),
        ("RESEARCH", 16),
        ("TOPIC_GENERATION", 17),
    ],
    ids=["15-local", "16-research", "17-topic-generation"],
)
def test_c1_counterexamples_15_to_17_foreign_kind_attempt_is_rejected(
    storage, content_seed, kind, number,
):
    _, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, f"counterexample-{number}",
    )
    foreign_request = _insert_foreign_provider_attempt(
        storage, content_seed, kind, f"counterexample-{number}",
    )
    with pytest.raises(sqlite3.IntegrityError, match="call intent"):
        storage.conn.execute(
            _CONTENT_EXTENSION_INSERT,
            _content_extension_values(intent, request_id=foreign_request),
        )
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_attempts"
    ).fetchone()[0] == 0


def test_c1_counterexample_18_other_content_job_attempt_is_rejected(
    storage, content_seed,
):
    _, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-18-primary", ContentType.ARTICLE,
    )
    other = _record_content_call_intent(
        storage, content_seed, "counterexample-18-other", ContentType.NOTE,
    )
    other_execution, other_intent = other[3], other[4]
    other_attempt = storage.begin_provider_attempt(
        other_execution,
        stage=other_intent.stage,
        attempt_no=other_intent.attempt_no,
        max_cost_usd=other_intent.max_cost_usd,
        daily_limit_usd=2,
        monthly_limit_usd=40,
    )
    with pytest.raises(sqlite3.IntegrityError, match="call intent"):
        storage.conn.execute(
            _CONTENT_EXTENSION_INSERT,
            _content_extension_values(
                intent, request_id=other_attempt.request_id,
            ),
        )
    storage.conn.rollback()


def test_c1_counterexample_19_other_run_is_rejected(storage, content_seed):
    _, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-19",
    )
    with pytest.raises(sqlite3.IntegrityError, match="call intent"):
        storage.conn.execute(
            _CONTENT_EXTENSION_INSERT,
            _content_extension_values(
                intent, run_id=content_seed["research_run_id"],
            ),
        )
    storage.conn.rollback()


def test_c1_counterexample_20_other_account_is_rejected(
    storage, account, content_seed,
):
    _, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-20",
    )
    other = account.model_copy(update={"id": "counterexample-other-account"})
    storage.ensure_account(other)
    with pytest.raises(sqlite3.IntegrityError, match="call intent"):
        storage.conn.execute(
            _CONTENT_EXTENSION_INSERT,
            _content_extension_values(intent, account_id=other.id),
        )
    storage.conn.rollback()


def test_c1_counterexample_21_extension_without_parent_is_rejected_on_commit(
    storage, content_seed,
):
    _, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-21",
    )
    storage.conn.execute("BEGIN IMMEDIATE")
    storage.conn.execute(
        _CONTENT_EXTENSION_INSERT, _content_extension_values(intent),
    )
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        storage.conn.commit()
    storage.conn.rollback()
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_attempts"
    ).fetchone()[0] == 0


def test_c1_counterexample_22_content_parent_without_extension_is_rejected(
    storage, content_seed,
):
    request, _, _, _, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-22",
    )
    with pytest.raises(sqlite3.IntegrityError, match="exact 1:1 extension"):
        storage.conn.execute(
            "INSERT INTO provider_attempts (job_id,stage,attempt_no,request_id,"
            "status,reserved_amount_usd,reserved_at,execution_intent_fingerprint) "
            "VALUES (?,'content_draft',1,?,'RESERVED',0.15,?,?)",
            (
                request.job_id,
                f"{request.job_id}:content_draft:1",
                "2026-07-23 12:00:00",
                intent.fingerprint(),
            ),
        )
    storage.conn.rollback()


def test_c1_counterexample_23_incoherent_content_usage_is_rejected(
    storage, content_seed,
):
    _, _, _, execution, intent = _record_content_call_intent(
        storage, content_seed, "counterexample-23",
    )
    attempt = storage.begin_provider_attempt(
        execution,
        stage=intent.stage,
        attempt_no=intent.attempt_no,
        max_cost_usd=intent.max_cost_usd,
        daily_limit_usd=2,
        monthly_limit_usd=40,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    with pytest.raises(sqlite3.IntegrityError, match="canonical content attempt"):
        storage.conn.execute(
            "INSERT INTO model_usage (run_id,provider,model,task,input_tokens,"
            "output_tokens,estimated_cost_usd,dry_run,request_id,is_legacy_usage,"
            "created_at) VALUES (?,?,?,?,10,5,0.01,0,?,0,?)",
            (
                execution.run_id,
                "wrong-provider",
                intent.model,
                intent.stage,
                attempt.request_id,
                "2026-07-23 12:00:01",
            ),
        )
    storage.conn.rollback()
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0


def test_coherent_content_usage_settles_only_the_canonical_parent(
    storage, content_seed,
):
    _, _, _, execution, intent = _record_content_call_intent(
        storage, content_seed, "content-usage",
    )
    attempt = storage.begin_provider_attempt(
        execution,
        stage=intent.stage,
        attempt_no=intent.attempt_no,
        max_cost_usd=intent.max_cost_usd,
        daily_limit_usd=2,
        monthly_limit_usd=40,
    )
    storage.mark_provider_attempt_request_started(execution, attempt.request_id)
    usage = storage.add_job_model_usage(
        execution,
        ModelUsage(
            run_id=execution.run_id,
            provider=intent.provider,
            model=intent.model,
            task=intent.stage,
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.01,
            dry_run=False,
            request_id=attempt.request_id,
        ),
    )
    assert usage.id is not None
    parent = storage.conn.execute(
        "SELECT status,actual_cost_usd FROM provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()
    assert tuple(parent) == ("SETTLED", 0.01)
    assert storage.conn.execute(
        "SELECT request_id FROM model_usage WHERE id=?", (usage.id,),
    ).fetchone()[0] == attempt.request_id
    assert storage.conn.execute(
        "SELECT count(*) FROM content_provider_attempts WHERE request_id=?",
        (attempt.request_id,),
    ).fetchone()[0] == 1


def test_c1_counterexample_24_lineage_drift_at_start_recheck_rolls_back(
    storage, content_seed,
):
    request = _request(content_seed, "counterexample-24")
    storage.prepare_content_job(request, clock=FixedClock(_NOW))
    lease = storage.claim_specific_job(
        request.job_id, "worker-a", 60, clock=FixedClock(_NOW),
    )
    assert lease is not None

    def drift(point):
        if point is ContentInitializationFaultPoint.BEFORE_EXECUTION_SNAPSHOT_RECHECK:
            storage.conn.execute(
                "UPDATE sources SET supports_claim='Drift inside start transaction' "
                "WHERE id=?",
                (content_seed["source_id"],),
            )

    with pytest.raises(
        ContentSnapshotError, match="CONTENT_LINEAGE_FINGERPRINT_INVALID",
    ):
        storage.initialize_content_run_for_job(
            request.job_id,
            "worker-a",
            lease.job.execution_generation,
            "content-run-counterexample-24",
            clock=FixedClock(_NOW),
            fault_point=drift,
        )
    assert storage.conn.execute(
        "SELECT supports_claim FROM sources WHERE id=?",
        (content_seed["source_id"],),
    ).fetchone()[0] == _CLAIM
    assert storage.conn.execute(
        "SELECT count(*) FROM content_runs WHERE job_id=?", (request.job_id,),
    ).fetchone()[0] == 0


def test_c1_counterexample_25_concurrent_terminalizations_keep_four_rows_atomic(
    storage, settings, content_seed,
):
    request, _, initialized, execution = _start(
        storage, content_seed, "counterexample-25",
    )
    barrier = Barrier(2)

    def terminalize(target, reason):
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            try:
                result = store.transition_content_execution(
                    execution, target, reason_code=reason,
                )
                return ("ok", result.content.status.value)
            except Exception as exc:
                return ("error", type(exc).__name__)
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(
            lambda args: terminalize(*args),
            [
                (ContentStatus.SKIPPED, "CONCURRENT_SKIP"),
                (ContentStatus.FAILED, "CONCURRENT_FAIL"),
            ],
        ))
    assert [kind for kind, _ in outcomes].count("ok") == 1
    assert [kind for kind, _ in outcomes].count("error") == 1
    winner = next(value for kind, value in outcomes if kind == "ok")
    expected = {
        "SKIPPED": ("DONE", "SUCCESS"),
        "FAILED": ("FAILED", "FAILED"),
    }[winner]
    row = storage.conn.execute(
        "SELECT c.status AS content_status,cr.status AS content_run_status,"
        "j.status AS job_status,r.status AS run_status "
        "FROM content_items c JOIN content_runs cr ON cr.content_id=c.id "
        "JOIN jobs j ON j.id=c.job_id JOIN runs r ON r.id=c.run_id "
        "WHERE c.id=? AND c.job_id=? AND c.run_id=?",
        (initialized.content.id, request.job_id, initialized.run.run_id),
    ).fetchone()
    assert row is not None
    assert row["content_status"] == winner
    assert row["content_run_status"] == winner
    assert row["job_status"] == expected[0]
    assert row["run_status"] == expected[1]
    assert storage.conn.execute(
        "SELECT count(*) FROM content_transition_commands "
        "WHERE run_id=? AND target_content_status IN "
        "('SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION')",
        (initialized.run.run_id,),
    ).fetchone()[0] == 1


def test_generic_finish_run_rejects_content_run(storage, content_seed):
    _, _, initialized, _ = _start(storage, content_seed, "generic-run")
    with pytest.raises(
        ContentFoundationError,
        match="CONTENT_GENERIC_RUN_TERMINALIZATION_FORBIDDEN",
    ):
        storage.finish_run(initialized.run.run_id, "SUCCESS", 0)
    assert storage.get_run(initialized.run.run_id).status.value == "RUNNING"


def test_evaluation_storage_has_no_audit_execution_side_effect(storage, content_seed):
    _, _, initialized, execution = _start(storage, content_seed)
    evaluation = ContentEvaluation(
        content_id=initialized.content.id,
        account_id=content_seed["account_id"],
        job_id=execution.job_id,
        run_id=execution.run_id,
        kind=ContentEvaluationKind.FACT,
        audit_version="fact_v1",
        status=ContentEvaluationStatus.PENDING,
        created_at=_NOW,
        updated_at=_NOW,
    )
    stored = storage.record_content_evaluation(execution, evaluation)
    assert stored.id is not None
    assert storage.conn.execute("SELECT count(*) FROM evaluations").fetchone()[0] == 1
    assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0


def test_concurrent_same_idempotency_key_creates_exactly_one_intent(
    settings, content_seed,
):
    request = _request(content_seed, "race")
    barrier = Barrier(2)

    def prepare():
        store = SqliteStorage.open(settings.db_path)
        try:
            barrier.wait(timeout=5)
            return store.prepare_content_job(
                request, clock=FixedClock(_NOW),
            ).job_created
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: prepare(), range(2)))
    assert sorted(results) == [False, True]
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.conn.execute(
            "SELECT count(*) FROM content_items"
        ).fetchone()[0] == 1
        assert reopened.conn.execute(
            "SELECT count(*) FROM jobs WHERE kind='CONTENT'"
        ).fetchone()[0] == 1
        assert reopened.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert reopened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()
