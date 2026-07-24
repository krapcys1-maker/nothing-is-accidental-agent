"""Acceptance E2-B: CLI → approval L1 → Worker → real FetchPort (fake transport)
→ retrieval → terminalizacja → reopen, plus lokalne testy negatywne inwariantów,
granicy zaufania, spójności transakcyjnej i odporności na awarie.

Całość offline: fake transport + fake resolver z jawnego fixture; safety kernel
blokuje sieć dla całego procesu. Prawdziwy transport pozostaje nieautoryzowany.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.core.clock import FixedClock, SystemClock
from app.main import _build_worker, main
from app.models import (
    ControlledFetchAttemptStatus,
    JobExecutionContext,
    JobKind,
    JobStatus,
    Topic,
    TopicStatus,
    WorkflowType,
)
from app.ports.storage import (
    ControlledFetchAuthorizationError,
    StaleJobExecutionError,
)
from app.scheduler.worker import WorkerIterationStatus
from app.storage.repositories import SqliteStorage

PUBLIC_IP = "93.184.216.34"
URL = "https://example.com/report"
BODY = (
    "<html><head><script>ignored instruction</script></head>"
    "<body><h1>Report</h1><p>Controlled fetch durable evidence body with "
    "enough exact text for later citation.</p></body></html>"
)


def _seed(settings, account, monkeypatch, *, topic_title="Controlled fetch source"):
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
        title=topic_title,
        question="What does the approved source document actually say?",
        status=TopicStatus.SELECTED,
    ))
    storage.apply_security_flag_profile([
        ("worker_enabled", True),
        ("safe_mode", False),
        ("paid_actions_enabled", False),
        ("browser_actions_enabled", False),
        ("kill_switch", False),
    ], updated_by="test", reason="E2-B acceptance")
    storage.close()
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    return topic


def _fixture_env(tmp_path, monkeypatch, *, responses=None, resolved=None):
    fixture = tmp_path / "controlled-fetch-fixture.json"
    fixture.write_text(json.dumps({
        "responses": responses if responses is not None else {URL: {
            "status": 200, "content_type": "text/html; charset=utf-8",
            "body_utf8": BODY,
        }},
        "resolved_addresses": resolved if resolved is not None else {
            "example.com": [PUBLIC_IP],
        },
    }), encoding="utf-8")
    monkeypatch.setenv("NIA_CONTROLLED_FETCH_FAKE", "1")
    monkeypatch.setenv("NIA_CONTROLLED_FETCH_FIXTURE", str(fixture))
    return fixture


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _enqueue(settings, account, topic, *, url=URL, timeout=10, max_bytes=200_000,
             max_redirects=2, expires_delta=timedelta(hours=6)) -> str:
    assert main([
        "enqueue-controlled-fetch",
        "--account-id", account.id,
        "--topic-id", str(topic.id),
        "--url", url,
        "--source-identity", "example-report",
        "--timeout-seconds", str(timeout),
        "--max-bytes", str(max_bytes),
        "--max-redirects", str(max_redirects),
        "--expires-at", _iso(datetime.now(timezone.utc) + expires_delta),
    ]) == 0
    storage = SqliteStorage.open(settings.db_path)
    try:
        row = storage.conn.execute(
            "SELECT id FROM jobs WHERE topic_id=? ORDER BY created_at DESC LIMIT 1",
            (topic.id,),
        ).fetchone()
        assert row is not None
        return row["id"]
    finally:
        storage.close()


def _approve(account, job_id, *, expires_delta=timedelta(hours=2)) -> None:
    assert main([
        "approve-controlled-fetch",
        "--job-id", job_id,
        "--account-id", account.id,
        "--approved-by", "test-owner-l1",
        "--expires-at", _iso(datetime.now(timezone.utc) + expires_delta),
    ]) == 0


def _claim_moment(settings, job_id) -> datetime:
    storage = SqliteStorage.open(settings.db_path)
    try:
        moment = storage.conn.execute(
            "SELECT earliest_run_at FROM jobs WHERE id=?", (job_id,),
        ).fetchone()[0]
    finally:
        storage.close()
    if isinstance(moment, str):
        moment = datetime.fromisoformat(moment)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(moment, datetime.now(timezone.utc)) + timedelta(seconds=1)


def _run_worker(settings, moment, lease_owner, *, offline_only=False):
    # Controlled fetch to akcja zewnętrzna: wykonuje ją zwykły worker CLI;
    # system-schedulerowy --offline-only pozostaje fail-closed (osobny test).
    worker, storage = _build_worker(
        settings, offline_only, clock=FixedClock(moment), lease_owner=lease_owner,
    )
    try:
        return worker.run_once()
    finally:
        storage.close()


# --- Obowiązkowy acceptance offline (sekcja 14) --------------------------------

def test_full_controlled_fetch_acceptance_cli_worker_retrieval_reopen(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    result = _run_worker(settings, moment, "e2b-worker-one")
    assert result.status is WorkerIterationStatus.DONE, result

    # Reopen jest częścią acceptance — wszystkie asercje z trwałej bazy.
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        job = reopened.get_job(job_id)
        assert job is not None and job.status is JobStatus.DONE
        assert job.run_id is not None
        assert job.external_effect_started_at is not None

        approvals = reopened.conn.execute(
            "SELECT * FROM controlled_fetch_approvals"
        ).fetchall()
        assert len(approvals) == 1
        approval = approvals[0]
        assert approval["job_id"] == job_id
        assert approval["consumed_at"] is not None
        assert approval["action_type"] == "CONTROLLED_FETCH"

        attempts = reopened.conn.execute(
            "SELECT * FROM controlled_fetch_attempts"
        ).fetchall()
        assert len(attempts) == 1
        attempt = attempts[0]
        assert attempt["status"] == "SUCCEEDED"
        assert attempt["job_id"] == job_id
        assert attempt["run_id"] == job.run_id
        assert attempt["account_id"] == account.id
        assert attempt["topic_id"] == topic.id
        assert attempt["approval_id"] == approval["id"]
        assert attempt["attempt_no"] == 1
        assert attempt["requested_url"] == URL
        assert attempt["request_started_at"] is not None

        intent = job.payload["execution_intent"]
        assert attempt["intent_fingerprint"] == intent["fingerprint"]
        assert approval["intent_fingerprint"] == intent["fingerprint"]
        assert approval["requested_url"] == intent["requested_url"] == URL

        retrievals = reopened.conn.execute(
            "SELECT * FROM evidence_retrievals"
        ).fetchall()
        assert len(retrievals) == 1
        retrieval = retrievals[0]
        assert retrieval["id"] == attempt["retrieval_id"]
        assert retrieval["status"] == "OK"
        assert retrieval["account_id"] == account.id
        assert retrieval["requested_url"] == URL
        assert "Controlled fetch durable evidence body" in retrieval["canonical_text"]
        assert "ignored instruction" not in retrieval["canonical_text"]

        run_row = reopened.conn.execute(
            "SELECT * FROM runs WHERE id=?", (job.run_id,),
        ).fetchone()
        assert run_row["status"] == "SUCCESS"
        assert run_row["finished_at"] is not None
        assert float(run_row["cost_usd"]) == 0

        assert reopened.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT coalesce(sum(cost_usd),0) FROM runs").fetchone()[0] == 0
        # Fetch nie jest researchem: nie tworzy research_runs ani kart.
        assert reopened.conn.execute("SELECT count(*) FROM research_runs").fetchone()[0] == 0
        assert reopened.conn.execute("SELECT count(*) FROM research_cards").fetchone()[0] == 0
        # Topic pozostaje nietknięty (fetch nie konsumuje tematu).
        assert reopened.conn.execute(
            "SELECT status FROM topics WHERE id=?", (topic.id,),
        ).fetchone()[0] == TopicStatus.SELECTED.value
    finally:
        reopened.close()

    second = _run_worker(
        settings, moment + timedelta(seconds=2), "e2b-worker-two",
    )
    assert second.status is WorkerIterationStatus.IDLE


# --- Zgoda L1: brak / wygaśnięcie / niezgodność / jednorazowość -----------------

def test_missing_approval_fails_closed_without_consuming_anything(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)

    result = _run_worker(settings, _claim_moment(settings, job_id), "e2b-w")
    assert result.status is WorkerIterationStatus.FAILED

    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        assert job.status is JobStatus.FAILED
        assert "APPROVAL_MISSING" in (job.last_error or "")
        assert storage.conn.execute("SELECT count(*) FROM controlled_fetch_attempts").fetchone()[0] == 0
        assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        storage.close()


def test_expired_approval_is_refused_and_never_consumed(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id, expires_delta=timedelta(seconds=60))

    moment = _claim_moment(settings, job_id) + timedelta(seconds=180)
    result = _run_worker(settings, moment, "e2b-w")
    assert result.status is WorkerIterationStatus.FAILED

    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        assert "APPROVAL_EXPIRED" in (job.last_error or "")
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval is not None and approval.consumed_at is None
        assert storage.conn.execute("SELECT count(*) FROM controlled_fetch_attempts").fetchone()[0] == 0
    finally:
        storage.close()


def test_approval_binds_to_exactly_one_job_and_cannot_be_retargeted(
    settings, account, tmp_path, monkeypatch,
):
    topic_a = _seed(settings, account, monkeypatch)
    storage = SqliteStorage.open(settings.db_path)
    topic_b = storage.add_topic(account.id, Topic(
        account_id=account.id, title="Second source", question="Q?",
        status=TopicStatus.SELECTED,
    ))
    storage.close()
    _fixture_env(tmp_path, monkeypatch)
    job_a = _enqueue(settings, account, topic_a)
    job_b = _enqueue(settings, account, topic_b)
    _approve(account, job_b)

    storage = SqliteStorage.open(settings.db_path)
    try:
        approval = storage.get_controlled_fetch_approval_for_job(job_b)
        # Trwała podłoga: zgody nie można przepiąć na inny job ani URL.
        with pytest.raises(sqlite3.IntegrityError, match="one immutable consumption"):
            storage.conn.execute(
                "UPDATE controlled_fetch_approvals SET job_id=? WHERE id=?",
                (job_a, approval.id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="one immutable consumption"):
            storage.conn.execute(
                "UPDATE controlled_fetch_approvals SET requested_url='https://evil.invalid/' "
                "WHERE id=?", (approval.id,),
            )
        # INSERT zgody dla joba A z fingerprint/URL joba B odpada na podłodze SQL.
        job_a_row = storage.get_job(job_a)
        with pytest.raises(sqlite3.IntegrityError, match="frozen controlled_fetch_v1"):
            storage.conn.execute(
                "INSERT INTO controlled_fetch_approvals (job_id,account_id,action_type,"
                "requested_url,intent_fingerprint,timeout_seconds,max_bytes,max_redirects,"
                "approved_by,approved_at,expires_at,consumed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                (
                    job_a, account.id, "CONTROLLED_FETCH",
                    "https://evil.invalid/", "0" * 64, 10, 1000, 1,
                    "attacker", "2026-07-18 00:00:00", "2027-01-01 00:00:00",
                ),
            )
        del job_a_row
    finally:
        storage.close()


def test_second_approval_for_the_same_job_is_rejected(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    assert main([
        "approve-controlled-fetch",
        "--job-id", job_id,
        "--account-id", account.id,
        "--approved-by", "second-operator",
        "--expires-at", _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
    ]) == 2


def test_approval_requires_the_owning_account_and_a_queued_job(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    storage = SqliteStorage.open(settings.db_path)
    try:
        with pytest.raises(ControlledFetchAuthorizationError, match="ACCOUNT_MISMATCH"):
            storage.record_controlled_fetch_approval(
                job_id=job_id, account_id="someone_else",
                approved_by="x", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                clock=SystemClock(),
            )
        with pytest.raises(ControlledFetchAuthorizationError, match="JOB_MISSING"):
            storage.record_controlled_fetch_approval(
                job_id="no-such-job", account_id=account.id,
                approved_by="x", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                clock=SystemClock(),
            )
    finally:
        storage.close()


def test_consumed_approval_cannot_be_reset_or_reused(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    assert _run_worker(
        settings, _claim_moment(settings, job_id), "e2b-w",
    ).status is WorkerIterationStatus.DONE

    storage = SqliteStorage.open(settings.db_path)
    try:
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is not None
        # Konsumpcji nie da się cofnąć (jednorazowość przetrwa restart).
        with pytest.raises(sqlite3.IntegrityError, match="one immutable consumption"):
            storage.conn.execute(
                "UPDATE controlled_fetch_approvals SET consumed_at=NULL WHERE id=?",
                (approval.id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            storage.conn.execute(
                "DELETE FROM controlled_fetch_approvals WHERE id=?", (approval.id,),
            )
        # Drugi attempt na tę samą zgodę odpada strukturalnie (UNIQUE + trigger).
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        with pytest.raises(sqlite3.IntegrityError):
            storage.conn.execute(
                "INSERT INTO controlled_fetch_attempts (job_id,run_id,account_id,"
                "topic_id,approval_id,attempt_no,source_identity,requested_url,"
                "intent_fingerprint,status,lease_owner,reserved_at) "
                "VALUES (?,?,?,?,?,1,?,?,?,'RESERVED',?,?)",
                (
                    job_id, attempt.run_id, account.id, topic.id, approval.id,
                    "example-report", URL, approval.intent_fingerprint,
                    "attacker", "2026-07-18 00:00:00",
                ),
            )
    finally:
        storage.close()


# --- P2-3: trwała niemutowalność payloadu controlled_fetch_v1 -------------------

def test_p2_3_controlled_fetch_payload_is_frozen_at_the_sql_floor(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    storage = SqliteStorage.open(settings.db_path)
    try:
        payload = storage.conn.execute(
            "SELECT payload_json FROM jobs WHERE id=?", (job_id,),
        ).fetchone()[0]
        tampered = payload.replace("example.com/report", "evil.invalid/steal")
        assert tampered != payload
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            storage.conn.execute(
                "UPDATE jobs SET payload_json=? WHERE id=?", (tampered, job_id),
            )
        # Kierunek odwrotny: zwykły payload nie może STAĆ SIĘ kontraktem fetchu.
        storage.conn.execute(
            "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
            "topic_id,payload_json,schedule_reason,earliest_run_at,attempts,"
            "max_attempts,reserved_cost_usd,created_at,updated_at) "
            "VALUES ('plain-job',?,?,?,'QUEUED','plain-key',?,"
            "'{\"dry_run\":true}','WITHIN_EDITORIAL_WINDOW','2026-07-18 00:00:00',0,1,0,"
            "'2026-07-18 00:00:00','2026-07-18 00:00:00')",
            (account.id, JobKind.LOCAL.value, WorkflowType.ANALYTICS.value, None),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            storage.conn.execute(
                "UPDATE jobs SET payload_json=? WHERE id='plain-job'", (payload,),
            )
        storage.conn.rollback()
    finally:
        storage.close()


# --- Walidacja intentu przy CLI, enqueue i dispatcherze -------------------------

def test_enqueue_cli_rejects_boundary_and_bound_violations(
    settings, account, tmp_path, monkeypatch, capsys,
):
    topic = _seed(settings, account, monkeypatch)

    def attempt(url="https://example.com/x", timeout="10", max_bytes="1000",
                redirects="1"):
        return main([
            "enqueue-controlled-fetch",
            "--account-id", account.id, "--topic-id", str(topic.id),
            "--url", url, "--source-identity", "s",
            "--timeout-seconds", timeout, "--max-bytes", max_bytes,
            "--max-redirects", redirects,
            "--expires-at", _iso(datetime.now(timezone.utc) + timedelta(hours=1)),
        ])

    assert attempt(url="https://localhost/doc") == 2
    assert attempt(url="ftp://example.com/doc") == 2
    assert attempt(url="https://user:pw@example.com/doc") == 2
    assert attempt(timeout="0") == 2
    assert attempt(timeout="500") == 2
    assert attempt(max_bytes="5000000") == 2
    assert attempt(redirects="9") == 2
    capsys.readouterr()
    storage = SqliteStorage.open(settings.db_path)
    try:
        assert storage.conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    finally:
        storage.close()


def test_dispatcher_rejects_tampered_or_extra_field_controlled_payloads(
    settings, account, tmp_path, monkeypatch,
):
    from app.scheduler.dispatcher import JobDispatcher, PayloadValidationError
    from app.models import Job
    from app.policies.policy_engine import PolicyEngine
    from app.research.controlled_fetch_intent import ControlledFetchIntent

    topic = _seed(settings, account, monkeypatch)
    intent = ControlledFetchIntent.build(
        account_id=account.id, topic_id=topic.id, source_identity="s",
        requested_url=URL, timeout_seconds=10, max_bytes=1000, max_redirects=1,
        allowed_content_types=["text/html"],
        requested_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    storage = SqliteStorage.open(settings.db_path)
    try:
        dispatcher = JobDispatcher(
            settings=settings, storage=storage,
            policy=PolicyEngine(settings, storage, SystemClock()),
        )

        def job_with(payload):
            return Job(
                id="j1", account_id=account.id, kind=JobKind.RESEARCH,
                workflow=WorkflowType.RESEARCH, idempotency_key="k1",
                topic_id=topic.id, payload=payload,
            )

        good = {
            "account_id": account.id, "topic_id": topic.id, "dry_run": False,
            "execution": "controlled_fetch_v1", "execution_intent": intent.as_payload(),
        }
        # dry_run=true nigdy nie jest kontraktem fetchu.
        with pytest.raises(PayloadValidationError):
            dispatcher._validate_research_payload(job_with({**good, "dry_run": True}))
        # Pole spoza zamkniętego zbioru odpada.
        with pytest.raises(PayloadValidationError):
            dispatcher._validate_research_payload(job_with({**good, "mode": "single"}))
        # Zmieniony URL bez przeliczenia fingerprintu odpada.
        tampered_intent = dict(intent.as_payload(), requested_url="https://evil.invalid/")
        with pytest.raises(PayloadValidationError):
            dispatcher._validate_research_payload(
                job_with({**good, "execution_intent": tampered_intent})
            )
    finally:
        storage.close()


def test_offline_and_paid_flows_never_reach_the_controlled_fetch_runner(
    settings, account, tmp_path, monkeypatch,
):
    """Dispatcher wybiera controlled fetch wyłącznie dla controlled_fetch_v1."""
    from app.scheduler.dispatcher import JobDispatcher
    from app.policies.policy_engine import PolicyEngine

    topic = _seed(settings, account, monkeypatch)
    calls = []

    def sentinel_runner(*args, **kwargs):
        calls.append("controlled_fetch")
        raise AssertionError("controlled fetch runner must not be selected")

    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = SystemClock()
        dispatcher = JobDispatcher(
            settings=settings, storage=storage,
            policy=PolicyEngine(settings, storage, clock), clock=clock,
            research_controlled_fetch=sentinel_runner,
        )
        # Dry-run research (legacy SINGLE) — nie dotyka controlled fetch.
        from app.models import Job

        dry = Job(
            id="dry-job", account_id=account.id, kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH, idempotency_key="dry-key",
            topic_id=topic.id,
            payload={"account_id": account.id, "topic_id": topic.id, "dry_run": True},
        )
        parsed_topic, is_real = dispatcher._validate_research_payload(dry)
        assert parsed_topic.id == topic.id and is_real is False
        assert calls == []
    finally:
        storage.close()


# --- Lokalna polityka adresów i limity w pełnym flow ----------------------------

def test_url_policy_rejection_consumes_approval_before_authorized_binding(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    # Capability transportu powstaje dopiero po zużyciu L1; prywatny adres
    # kończy RESERVED jako FAILED, nadal przed REQUEST_STARTED i transportem.
    _fixture_env(
        tmp_path, monkeypatch,
        resolved={"example.com": ["192.168.7.7"]},
    )
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    result = _run_worker(settings, _claim_moment(settings, job_id), "e2b-w")
    assert result.status is WorkerIterationStatus.FAILED

    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        assert "URL_POLICY_REJECTED:ADDRESS_PRIVATE" in (job.last_error or "")
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is not None
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert attempt.status is ControlledFetchAttemptStatus.FAILED
        assert attempt.request_started_at is None
        assert storage.conn.execute("SELECT count(*) FROM controlled_fetch_attempts").fetchone()[0] == 1
        assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
        assert job.external_effect_started_at is None
    finally:
        storage.close()


def test_storage_issues_transport_capability_only_for_consumed_reserved_attempt(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    moment = _claim_moment(settings, job_id)
    clock = FixedClock(moment)

    storage = SqliteStorage.open(settings.db_path)
    try:
        lease = storage.claim_next_job("e2c-capability-worker", 60, clock=clock)
        assert lease is not None and lease.job.id == job_id
        initialized = storage.initialize_controlled_fetch_run_for_job(
            job_id,
            "e2c-capability-worker",
            "run-e2c-capability",
            clock=clock,
        )
        execution = JobExecutionContext(
            job_id=job_id,
            lease_owner="e2c-capability-worker",
            run_id=initialized.run.id,
            clock=clock,
        )

        with pytest.raises(
            ControlledFetchAuthorizationError,
            match="ATTEMPT_NOT_TRANSPORT_AUTHORIZABLE",
        ):
            storage.authorize_controlled_fetch_transport(execution, 999)

        attempt = storage.begin_controlled_fetch_attempt(execution)
        authorization = storage.authorize_controlled_fetch_transport(
            execution,
            attempt.id,
        )
        authorization.assert_storage_issued()
        assert authorization.job_id == job_id
        assert authorization.run_id == initialized.run.id
        assert authorization.account_id == account.id
        assert authorization.topic_id == topic.id
        assert authorization.approval_id == attempt.approval_id
        assert authorization.attempt_id == attempt.id
        assert authorization.requested_url == URL
        assert authorization.intent_fingerprint == attempt.intent_fingerprint
        assert storage.get_controlled_fetch_approval_for_job(
            job_id,
        ).consumed_at is not None

        storage.mark_controlled_fetch_request_started(execution, attempt.id)
        with pytest.raises(
            ControlledFetchAuthorizationError,
            match="ATTEMPT_NOT_TRANSPORT_AUTHORIZABLE",
        ):
            storage.authorize_controlled_fetch_transport(execution, attempt.id)
    finally:
        storage.close()


@pytest.mark.parametrize("mutation,expected_error", [
    ("redirect_private", "REDIRECT_POLICY_REJECTED:ADDRESS_PRIVATE"),
    ("oversize", "RESPONSE_TOO_LARGE"),
    ("content_type", "CONTENT_TYPE_REJECTED:application/json"),
    ("http_500", "HTTP_STATUS_500"),
])
def test_definitive_fetch_failures_terminalize_with_failed_retrieval(
    settings, account, tmp_path, monkeypatch, mutation, expected_error,
):
    topic = _seed(settings, account, monkeypatch)
    responses = {URL: {
        "status": 200, "content_type": "text/html; charset=utf-8",
        "body_utf8": BODY,
    }}
    if mutation == "redirect_private":
        responses[URL] = {
            "status": 302, "content_type": None, "location": "http://10.9.9.9/x",
            "body_utf8": "",
        }
    elif mutation == "oversize":
        responses[URL]["body_utf8"] = "x" * 300_000
    elif mutation == "content_type":
        responses[URL]["content_type"] = "application/json"
    elif mutation == "http_500":
        responses[URL]["status"] = 500
    _fixture_env(tmp_path, monkeypatch, responses=responses)
    job_id = _enqueue(settings, account, topic, max_bytes=200_000)
    _approve(account, job_id)

    result = _run_worker(settings, _claim_moment(settings, job_id), "e2b-w")
    assert result.status is WorkerIterationStatus.FAILED

    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        assert job.status is JobStatus.FAILED
        assert expected_error in (job.last_error or "")
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert attempt.status is ControlledFetchAttemptStatus.FAILED
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is not None
        retrieval = storage.conn.execute(
            "SELECT * FROM evidence_retrievals WHERE id=?", (attempt.retrieval_id,),
        ).fetchone()
        assert retrieval is not None and retrieval["status"] == "FAILED"
        assert storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0] == 0
        assert storage.conn.execute("SELECT coalesce(sum(cost_usd),0) FROM runs").fetchone()[0] == 0
    finally:
        storage.close()


# --- Lease, fencing, spójność transakcyjna --------------------------------------

def test_stale_lease_cannot_consume_approval_or_start_request(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        lease = storage.claim_next_job("stale-worker", 60, clock=FixedClock(moment))
        assert lease is not None and lease.job.id == job_id
        init = storage.initialize_controlled_fetch_run_for_job(
            job_id, "stale-worker", "run-e2b-stale", clock=FixedClock(moment),
        )
        # Zegar przesuwa się poza lease: każda kolejna trwała mutacja odpada.
        late = FixedClock(moment + timedelta(seconds=120))
        execution = JobExecutionContext(
            job_id=job_id, lease_owner="stale-worker", run_id=init.run.id, clock=late,
        )
        with pytest.raises(StaleJobExecutionError):
            storage.begin_controlled_fetch_attempt(execution)
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is None
        assert storage.get_controlled_fetch_attempt_for_job(job_id) is None
    finally:
        storage.close()


def test_lease_loss_between_reservation_and_request_start_is_fenced(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = FixedClock(moment)
        lease = storage.claim_next_job("w1", 60, clock=clock)
        assert lease is not None
        init = storage.initialize_controlled_fetch_run_for_job(
            job_id, "w1", "run-e2b-fence", clock=clock,
        )
        execution = JobExecutionContext(
            job_id=job_id, lease_owner="w1", run_id=init.run.id, clock=clock,
        )
        attempt = storage.begin_controlled_fetch_attempt(execution)
        assert attempt.status is ControlledFetchAttemptStatus.RESERVED

        late_execution = JobExecutionContext(
            job_id=job_id, lease_owner="w1", run_id=init.run.id,
            clock=FixedClock(moment + timedelta(seconds=120)),
        )
        with pytest.raises(StaleJobExecutionError):
            storage.mark_controlled_fetch_request_started(late_execution, attempt.id)
        durable = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert durable.status is ControlledFetchAttemptStatus.RESERVED
        assert storage.get_job(job_id).external_effect_started_at is None
    finally:
        storage.close()


def test_second_worker_cannot_claim_a_leased_controlled_fetch_job(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        first = storage.claim_next_job("w1", 60, clock=FixedClock(moment))
        assert first is not None and first.job.id == job_id
        second = storage.claim_next_job("w2", 60, clock=FixedClock(moment))
        assert second is None
    finally:
        storage.close()


def test_terminalized_attempt_and_job_refuse_a_second_terminalization(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    assert _run_worker(
        settings, _claim_moment(settings, job_id), "e2b-w",
    ).status is WorkerIterationStatus.DONE

    storage = SqliteStorage.open(settings.db_path)
    try:
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        with pytest.raises(
            sqlite3.IntegrityError, match="closed lifecycle|FAILED may only link",
        ):
            storage.conn.execute(
                "UPDATE controlled_fetch_attempts SET status='FAILED',"
                "terminalized_at='2026-07-19 00:00:00' WHERE id=?",
                (attempt.id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="closed lifecycle"):
            storage.conn.execute(
                "UPDATE controlled_fetch_attempts SET status='REQUEST_STARTED',"
                "terminalized_at=NULL,retrieval_id=NULL WHERE id=?",
                (attempt.id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            storage.conn.execute(
                "DELETE FROM controlled_fetch_attempts WHERE id=?", (attempt.id,),
            )
    finally:
        storage.close()


# --- Recovery i restart ---------------------------------------------------------

def test_restart_before_consumption_requeues_and_completes_later(
    settings, account, tmp_path, monkeypatch,
):
    settings.worker_default_max_attempts = 3
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = FixedClock(moment)
        lease = storage.claim_next_job("crashed-worker", 60, clock=clock)
        assert lease is not None
        storage.initialize_controlled_fetch_run_for_job(
            job_id, "crashed-worker", "run-e2b-crash1", clock=clock,
        )
        # Symulowany crash: lease wygasa bez konsumpcji zgody.
        recovery = storage.release_or_requeue_expired_leases(
            clock=FixedClock(moment + timedelta(seconds=120)),
        )
        assert recovery.requeued_count == 1
        job = storage.get_job(job_id)
        assert job.status is JobStatus.QUEUED
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is None
    finally:
        storage.close()

    result = _run_worker(
        settings, moment + timedelta(seconds=180), "recovered-worker",
    )
    assert result.status is WorkerIterationStatus.DONE
    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.get_job(job_id).status is JobStatus.DONE
        attempt = reopened.get_controlled_fetch_attempt_for_job(job_id)
        assert attempt.status is ControlledFetchAttemptStatus.SUCCEEDED
        assert reopened.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 1
    finally:
        reopened.close()


def test_reserved_attempt_with_expired_lease_terminalizes_failed(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = FixedClock(moment)
        storage.claim_next_job("crashed-worker", 60, clock=clock)
        init = storage.initialize_controlled_fetch_run_for_job(
            job_id, "crashed-worker", "run-e2b-crash2", clock=clock,
        )
        execution = JobExecutionContext(
            job_id=job_id, lease_owner="crashed-worker", run_id=init.run.id, clock=clock,
        )
        storage.begin_controlled_fetch_attempt(execution)

        recovery = storage.release_or_requeue_expired_leases(
            clock=FixedClock(moment + timedelta(seconds=120)),
        )
        assert recovery.failed_count == 1 and recovery.requeued_count == 0
        job = storage.get_job(job_id)
        assert job.status is JobStatus.FAILED
        assert "LEASE_EXPIRED_BEFORE_REQUEST_STARTED" in (job.last_error or "")
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert attempt.status is ControlledFetchAttemptStatus.FAILED
        assert attempt.outcome_reason == "LEASE_EXPIRED_BEFORE_REQUEST_STARTED"
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is not None
        run = storage.conn.execute(
            "SELECT status FROM runs WHERE id=?", (attempt.run_id,),
        ).fetchone()
        assert run["status"] == "FAILED"
        assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        storage.close()


def test_request_started_with_expired_lease_escalates_needs_verification(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    moment = _claim_moment(settings, job_id)
    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = FixedClock(moment)
        storage.claim_next_job("crashed-worker", 60, clock=clock)
        init = storage.initialize_controlled_fetch_run_for_job(
            job_id, "crashed-worker", "run-e2b-crash3", clock=clock,
        )
        execution = JobExecutionContext(
            job_id=job_id, lease_owner="crashed-worker", run_id=init.run.id, clock=clock,
        )
        attempt = storage.begin_controlled_fetch_attempt(execution)
        storage.mark_controlled_fetch_request_started(execution, attempt.id)

        recovery = storage.release_or_requeue_expired_leases(
            clock=FixedClock(moment + timedelta(seconds=120)),
        )
        assert recovery.needs_verification_count == 1
        job = storage.get_job(job_id)
        assert job.status is JobStatus.NEEDS_VERIFICATION
        durable = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert durable.status is ControlledFetchAttemptStatus.NEEDS_VERIFICATION
        assert durable.outcome_reason == "LEASE_EXPIRED_AFTER_REQUEST_STARTED"

        # NEEDS_VERIFICATION nie jest claimowalne — brak automatycznego ponowienia.
        assert storage.claim_next_job(
            "next-worker", 60, clock=FixedClock(moment + timedelta(seconds=200)),
        ) is None
        assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
    finally:
        storage.close()


@pytest.mark.parametrize(
    "boundary",
    [
        "before_request_started",
        "after_request_started",
        "after_response_before_retrieval",
        "after_retrieval_before_terminalization",
    ],
)
def test_controlled_fetch_failpoint_windows_reopen_without_retry(
    settings, account, tmp_path, monkeypatch, boundary,
):
    """Every crash window preserves attempt #1 and refuses a second request."""
    from app.ports.controlled_fetch import ControlledHttpFetch

    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    if boundary == "before_request_started":
        def fail_preflight(_self):
            raise RuntimeError("failpoint before REQUEST_STARTED")

        monkeypatch.setattr(
            ControlledHttpFetch,
            "preflight_boundary",
            fail_preflight,
        )
    elif boundary == "after_request_started":
        def fail_fetch(_self, _url):
            raise RuntimeError("failpoint directly after REQUEST_STARTED")

        monkeypatch.setattr(ControlledHttpFetch, "fetch", fail_fetch)
    elif boundary == "after_response_before_retrieval":
        def fail_finalize(_self, _execution, _attempt_id, _document):
            raise RuntimeError("failpoint after fake response before retrieval")

        monkeypatch.setattr(
            SqliteStorage,
            "finalize_controlled_fetch_success",
            fail_finalize,
        )
    else:
        original_insert = SqliteStorage._insert_controlled_fetch_retrieval

        def insert_then_fail(self, retrieval):
            original_insert(self, retrieval)
            raise RuntimeError("failpoint after retrieval before terminalization")

        monkeypatch.setattr(
            SqliteStorage,
            "_insert_controlled_fetch_retrieval",
            insert_then_fail,
        )

    moment = _claim_moment(settings, job_id)
    result = _run_worker(settings, moment, f"e2c-fail-{boundary}")
    expected_worker = (
        WorkerIterationStatus.FAILED
        if boundary == "before_request_started"
        else WorkerIterationStatus.NEEDS_VERIFICATION
    )
    assert result.status is expected_worker

    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert attempt.attempt_no == 1
        assert approval.consumed_at is not None
        assert storage.conn.execute(
            "SELECT count(*) FROM controlled_fetch_attempts WHERE job_id=?",
            (job_id,),
        ).fetchone()[0] == 1
        assert storage.conn.execute(
            "SELECT count(*) FROM evidence_retrievals",
        ).fetchone()[0] == 0
        if boundary == "before_request_started":
            assert job.status is JobStatus.FAILED
            assert attempt.status is ControlledFetchAttemptStatus.FAILED
            assert attempt.request_started_at is None
        else:
            assert job.status is JobStatus.NEEDS_VERIFICATION
            assert (
                attempt.status
                is ControlledFetchAttemptStatus.NEEDS_VERIFICATION
            )
            assert attempt.request_started_at is not None
    finally:
        storage.close()

    second = _run_worker(
        settings,
        moment + timedelta(seconds=5),
        f"e2c-second-{boundary}",
    )
    assert second.status is WorkerIterationStatus.IDLE

    reopened = SqliteStorage.open(settings.db_path)
    try:
        assert reopened.conn.execute(
            "SELECT count(*) FROM controlled_fetch_attempts WHERE job_id=?",
            (job_id,),
        ).fetchone()[0] == 1
        assert reopened.conn.execute(
            "SELECT count(*) FROM evidence_retrievals",
        ).fetchone()[0] == 0
    finally:
        reopened.close()


def test_unexpected_exception_after_request_started_escalates_via_worker(
    settings, account, tmp_path, monkeypatch,
):
    """Transport rzuca nietypowany wyjątek → trwała eskalacja przez workera."""
    from app.policies.policy_engine import PolicyEngine
    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker
    from app.workflows.research.controlled_fetch import run_controlled_fetch

    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    class ExplodingPort:
        def preflight_boundary(self):
            from app.ports.controlled_fetch import UrlPolicyDecision

            return UrlPolicyDecision.ok()

        def fetch(self, url):
            raise RuntimeError("socket ripped mid-flight")

    def exploding_runner(account_, topic_, **kwargs):
        return run_controlled_fetch(
            account_, topic_,
            fetch_port_factory=lambda authorization, settings, clock: ExplodingPort(),
            **kwargs,
        )

    moment = _claim_moment(settings, job_id)
    clock = FixedClock(moment)
    storage = SqliteStorage.open(settings.db_path)
    try:
        policy = PolicyEngine(settings, storage, clock)
        dispatcher = JobDispatcher(
            settings=settings, storage=storage, policy=policy, clock=clock,
            research_controlled_fetch=exploding_runner,
        )
        worker = Worker(
            storage=storage, policy=policy, dispatcher=dispatcher,
            lease_owner="exploding-worker", lease_seconds=60,
            heartbeat_interval_seconds=20.0,
            heartbeat_startup_timeout_seconds=5.0,
            heartbeat_shutdown_timeout_seconds=5.0,
            heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
            clock=clock,
        )
        result = worker.run_once()
        assert result.status is WorkerIterationStatus.NEEDS_VERIFICATION
        job = storage.get_job(job_id)
        assert job.status is JobStatus.NEEDS_VERIFICATION
        attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
        assert attempt.status is ControlledFetchAttemptStatus.NEEDS_VERIFICATION
        assert "CONTROLLED_FETCH_OUTCOME_UNKNOWN" in (attempt.outcome_reason or "")
        assert storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0] == 0
        assert storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    finally:
        storage.close()


def test_worker_rerun_after_success_is_idle_and_changes_nothing(
    settings, account, tmp_path, monkeypatch,
):
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)
    moment = _claim_moment(settings, job_id)
    assert _run_worker(settings, moment, "w1").status is WorkerIterationStatus.DONE

    storage = SqliteStorage.open(settings.db_path)
    try:
        before = storage.conn.execute(
            "SELECT count(*) FROM evidence_retrievals"
        ).fetchone()[0]
    finally:
        storage.close()
    assert _run_worker(
        settings, moment + timedelta(seconds=5), "w2",
    ).status is WorkerIterationStatus.IDLE
    storage = SqliteStorage.open(settings.db_path)
    try:
        assert storage.conn.execute(
            "SELECT count(*) FROM evidence_retrievals"
        ).fetchone()[0] == before == 1
        assert storage.conn.execute(
            "SELECT count(*) FROM controlled_fetch_attempts"
        ).fetchone()[0] == 1
    finally:
        storage.close()


def test_offline_only_system_worker_refuses_controlled_fetch(
    settings, account, tmp_path, monkeypatch,
):
    """--offline-only (system scheduler) nigdy nie wykonuje akcji zewnętrznej."""
    topic = _seed(settings, account, monkeypatch)
    _fixture_env(tmp_path, monkeypatch)
    job_id = _enqueue(settings, account, topic)
    _approve(account, job_id)

    result = _run_worker(
        settings, _claim_moment(settings, job_id), "system-worker",
        offline_only=True,
    )
    assert result.status is WorkerIterationStatus.FAILED
    storage = SqliteStorage.open(settings.db_path)
    try:
        job = storage.get_job(job_id)
        assert "SYSTEM_SCHEDULER_OFFLINE_ONLY" in (job.last_error or "")
        approval = storage.get_controlled_fetch_approval_for_job(job_id)
        assert approval.consumed_at is None
        assert storage.conn.execute(
            "SELECT count(*) FROM controlled_fetch_attempts"
        ).fetchone()[0] == 0
        assert storage.conn.execute(
            "SELECT count(*) FROM evidence_retrievals"
        ).fetchone()[0] == 0
    finally:
        storage.close()


# --- Migracja 0018 i runtime gate -----------------------------------------------

def test_migration_cli_0018_requires_confirmation_and_is_exact(tmp_path, capsys):
    import scripts.migrate_schema_0018 as migration_cli_0018
    from app.storage.db import (
        CONTROLLED_FETCH_SCHEMA_VERSION,
        EVIDENCE_PIPELINE_SCHEMA_VERSION,
        EVIDENCE_SCHEMA_VERSION,
        SchemaVersionTooOld,
        database_schema_versions,
        initialize_database,
    )

    path = tmp_path / "ladder-0018.db"
    initialize_database(path, through=EVIDENCE_PIPELINE_SCHEMA_VERSION)
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0018.main(["--db-path", str(path)]) == 2
    assert database_schema_versions(path)[-1] == EVIDENCE_PIPELINE_SCHEMA_VERSION
    assert migration_cli_0018.main([
        "--db-path", str(path), "--confirm-0017-to-0018",
    ]) == 0
    assert database_schema_versions(path)[-1] == CONTROLLED_FETCH_SCHEMA_VERSION
    assert migration_cli_0018.main([
        "--db-path", str(path), "--confirm-0017-to-0018",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out
    # E3: runtime gate wymaga teraz dokładnie 0019 — 0018 to o jeden krok za mało;
    # kolejny jawny szczebel drabiny otwiera runtime.
    import scripts.migrate_schema_0019 as migration_cli_0019

    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0019.main(["--db-path", str(path)]) == 2
    assert migration_cli_0019.main([
        "--db-path", str(path), "--confirm-0018-to-0019",
    ]) == 0
    assert migration_cli_0019.main([
        "--db-path", str(path), "--confirm-0018-to-0019",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out
    # 0020: runtime gate wymaga teraz dokładnie 0020 — kolejny jawny szczebel
    # drabiny (TOPIC_GENERATION) otwiera runtime.
    import scripts.migrate_schema_0020 as migration_cli_0020

    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0020.main(["--db-path", str(path)]) == 2
    assert migration_cli_0020.main([
        "--db-path", str(path), "--confirm-0019-to-0020",
    ]) == 0
    assert migration_cli_0020.main([
        "--db-path", str(path), "--confirm-0019-to-0020",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out
    # 0021: durable content foundation is the exact runtime gate.  This test
    # exercises only a temporary database and does not authorize production.
    import scripts.migrate_schema_0021 as migration_cli_0021

    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0021.main(["--db-path", str(path)]) == 2
    assert migration_cli_0021.main([
        "--db-path", str(path), "--confirm-0020-to-0021",
    ]) == 0
    # 0022: closed C2 floor; 0023: closed C3; 0024: current C4 runtime gate.
    import scripts.migrate_schema_0022 as migration_cli_0022
    import scripts.migrate_schema_0023 as migration_cli_0023
    import scripts.migrate_schema_0024 as migration_cli_0024

    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0022.main(["--db-path", str(path)]) == 2
    assert migration_cli_0022.main([
        "--db-path", str(path), "--confirm-0021-to-0022",
    ]) == 0
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0022.main([
        "--db-path", str(path), "--confirm-0021-to-0022",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out
    assert migration_cli_0023.main(["--db-path", str(path)]) == 2
    assert migration_cli_0023.main([
        "--db-path", str(path), "--confirm-0022-to-0023",
    ]) == 0
    with pytest.raises(SchemaVersionTooOld):
        SqliteStorage.open(path)
    assert migration_cli_0024.main(["--db-path", str(path)]) == 2
    assert migration_cli_0024.main([
        "--db-path", str(path), "--confirm-0023-to-0024",
    ]) == 0
    SqliteStorage.open(path).close()
    assert migration_cli_0024.main([
        "--db-path", str(path), "--confirm-0023-to-0024",
    ]) == 0
    assert "idempotent=true" in capsys.readouterr().out

    too_old = tmp_path / "too-old-0016.db"
    initialize_database(too_old, through=EVIDENCE_SCHEMA_VERSION)
    assert migration_cli_0018.main([
        "--db-path", str(too_old), "--confirm-0017-to-0018",
    ]) == 2
    assert database_schema_versions(too_old)[-1] == EVIDENCE_SCHEMA_VERSION
