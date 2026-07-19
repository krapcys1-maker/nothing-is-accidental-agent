"""E2-B adversarial refutation harness (sekcja 19).

Niezależny od suity pytest. Każda hipoteza próbuje ZŁAMAĆ inwariant; wynik
PASS oznacza, że atak został ODParty (inwariant się utrzymał). Całość offline:
własny protected-DB env, fresh temp DB 0001→0018, fake transport + fake resolver.
"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["NIA_TEST_MODE"] = "1"
os.environ["NIA_TEST_PROTECTED_DB"] = str(Path("data/agent.db").resolve())
from app.testing.safety_kernel import activate
activate()

from app.core.clock import FixedClock
from app.core.config import Settings
from app.models import (
    Account, AccountMode, AutonomyLevel, ControlledFetchAttemptStatus,
    JobExecutionContext, JobKind, JobStatus, Topic, TopicStatus, WorkflowType,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import ControlledFetchAuthorizationError, StaleJobExecutionError
from app.research.controlled_fetch_intent import ControlledFetchIntent
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.scheduling import SchedulingPolicy
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage

PUBLIC_IP = "93.184.216.34"
URL = "https://example.com/report"
BODY = "<html><body><p>Durable controlled fetch evidence body for citation.</p></body></html>"
NOW = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)

RESULTS: list[tuple[str, bool, str]] = []


def record(name, refuted, detail=""):
    RESULTS.append((name, refuted, detail))


def account() -> Account:
    return Account(
        id="nothing_is_accidental", display_name="NIA",
        mode=AccountMode.FULL_PUBLICATION, autonomy_level=AutonomyLevel.LEVEL_1,
        active=True, niche=["x"], languages=["en"],
        browser_profile_path="./p", writing_profile_path="./w",
        allowed_actions=["research"],
    )


def make_settings(tmp: Path) -> Settings:
    data = tmp / "data"
    initialize_database(data / "agent.db")
    return Settings(
        project_root=tmp, data_dir=data, db_path=data / "agent.db",
        costs_csv_path=tmp / "c.csv", dry_run=True, kill_switch=False,
        max_daily_cost_usd=2.0, max_monthly_cost_usd=40.0,
        monthly_limit_has_priority=True, model_fast="f", model_quality="q",
        pricing={"input_per_mtok": 3.0, "output_per_mtok": 15.0,
                 "cache_read_per_mtok": 0.0, "cache_write_per_mtok": 0.0,
                 "web_search_per_1k": 0.0},
        article_min_score=75.0, note_min_score=65.0,
        topic_scoring_weights={"curiosity": 100.0},
        anthropic_api_key=None, accounts={account().id: account()},
        editorial_schedule={"timezone": "UTC", "windows": [
            {"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"}]},
    )


def fixture(tmp: Path, *, responses=None, resolved=None) -> Path:
    path = tmp / "fx.json"
    path.write_text(json.dumps({
        "responses": responses or {URL: {
            "status": 200, "content_type": "text/html; charset=utf-8",
            "body_utf8": BODY}},
        "resolved_addresses": resolved or {"example.com": [PUBLIC_IP]},
    }), encoding="utf-8")
    os.environ["NIA_CONTROLLED_FETCH_FAKE"] = "1"
    os.environ["NIA_CONTROLLED_FETCH_FIXTURE"] = str(path)
    return path


def build_intent(acc, topic, **ov):
    fields = dict(
        account_id=acc.id, topic_id=topic.id, source_identity="example-report",
        requested_url=URL, timeout_seconds=10, max_bytes=200_000, max_redirects=2,
        allowed_content_types=["text/html", "text/plain"],
        requested_at=NOW, expires_at=NOW + timedelta(hours=6),
    )
    fields.update(ov)
    return ControlledFetchIntent.build(**fields)


def seed(settings, acc, **intent_ov):
    storage = SqliteStorage.open(settings.db_path)
    storage.ensure_account(acc)
    topic = storage.add_topic(acc.id, Topic(
        account_id=acc.id, title="src", question="Q?", status=TopicStatus.SELECTED))
    storage.apply_security_flag_profile([
        ("worker_enabled", True), ("safe_mode", False),
        ("paid_actions_enabled", False), ("browser_actions_enabled", False),
        ("kill_switch", False)], updated_by="h", reason="harness")
    intent = build_intent(acc, topic, **intent_ov)
    payload = {"account_id": acc.id, "topic_id": topic.id, "dry_run": False,
               "execution": "controlled_fetch_v1", "execution_intent": intent.as_payload()}
    policy = SchedulingPolicy.from_config(settings.editorial_schedule)
    result = ScheduledJobEnqueuer(storage=storage, scheduling_policy=policy,
                                  clock=FixedClock(NOW)).enqueue(ScheduledJobRequest(
        id="cf-job", account_id=acc.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key="cf-key",
        topic_id=topic.id, payload=payload, requested_at=NOW, max_attempts=3))
    storage.close()
    return topic, result.job.id, intent


def approve(settings, acc, job_id, *, expires=timedelta(hours=2)):
    storage = SqliteStorage.open(settings.db_path)
    try:
        return storage.record_controlled_fetch_approval(
            job_id=job_id, account_id=acc.id, approved_by="l1",
            expires_at=NOW + expires, clock=FixedClock(NOW))
    finally:
        storage.close()


def run_worker(settings, moment, owner, *, offline_only=False):
    storage = SqliteStorage.open(settings.db_path)
    policy = PolicyEngine(settings, storage, FixedClock(moment))
    dispatcher = JobDispatcher(settings=settings, storage=storage, policy=policy,
                               clock=FixedClock(moment),
                               allow_real_research=not offline_only)
    worker = Worker(storage=storage, policy=policy, dispatcher=dispatcher,
                    lease_owner=owner, lease_seconds=60,
                    heartbeat_interval_seconds=20.0,
                    heartbeat_startup_timeout_seconds=5.0,
                    heartbeat_shutdown_timeout_seconds=5.0,
                    heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
                    clock=FixedClock(moment))
    try:
        return worker.run_once()
    finally:
        storage.close()


# --- H1: approval użyta dla innego joba/URL ---
def h1_approval_cross_job():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        _, job_id, intent = seed(settings, acc)
        approval = approve(settings, acc, job_id)
        storage = SqliteStorage.open(settings.db_path)
        try:
            # Utwórz drugi job.
            topic2 = storage.add_topic(acc.id, Topic(account_id=acc.id, title="t2",
                                       question="Q?", status=TopicStatus.SELECTED))
            intent2 = build_intent(acc, topic2)
            payload2 = {"account_id": acc.id, "topic_id": topic2.id, "dry_run": False,
                        "execution": "controlled_fetch_v1", "execution_intent": intent2.as_payload()}
            policy = SchedulingPolicy.from_config(settings.editorial_schedule)
            r2 = ScheduledJobEnqueuer(storage=storage, scheduling_policy=policy,
                clock=FixedClock(NOW)).enqueue(ScheduledJobRequest(
                id="cf-job2", account_id=acc.id, kind=JobKind.RESEARCH,
                workflow=WorkflowType.RESEARCH, idempotency_key="cf-key2",
                topic_id=topic2.id, payload=payload2, requested_at=NOW, max_attempts=3))
            job2 = r2.job.id
            blocked = False
            try:
                storage.conn.execute(
                    "UPDATE controlled_fetch_approvals SET job_id=? WHERE id=?",
                    (job2, approval.id))
            except sqlite3.IntegrityError:
                blocked = True
            record("H1 approval cannot be retargeted to another job", blocked)
        finally:
            storage.close()


# --- H2: approval użyta drugi raz ---
def h2_double_consume():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        fixture(tmp)
        moment = NOW + timedelta(seconds=1)
        run_worker(settings, moment, "w1")
        storage = SqliteStorage.open(settings.db_path)
        try:
            approval = storage.get_controlled_fetch_approval_for_job(job_id)
            blocked = False
            try:
                storage.conn.execute(
                    "UPDATE controlled_fetch_approvals SET consumed_at=NULL WHERE id=?",
                    (approval.id,))
            except sqlite3.IntegrityError:
                blocked = True
            record("H2 consumed approval cannot be reset for reuse",
                   blocked and approval.consumed_at is not None)
        finally:
            storage.close()


# --- H3: intent zmienia się po approval (P2-3) ---
def h3_payload_mutation():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        storage = SqliteStorage.open(settings.db_path)
        try:
            payload = storage.conn.execute("SELECT payload_json FROM jobs WHERE id=?",
                                           (job_id,)).fetchone()[0]
            tampered = payload.replace("example.com/report", "evil.invalid/x")
            blocked = False
            try:
                storage.conn.execute("UPDATE jobs SET payload_json=? WHERE id=?",
                                     (tampered, job_id))
            except sqlite3.IntegrityError:
                blocked = True
            record("H3 controlled_fetch_v1 payload is frozen after approval", blocked)
        finally:
            storage.close()


# --- H4: stary worker startuje transport po utracie lease ---
def h4_stale_worker_request():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        storage = SqliteStorage.open(settings.db_path)
        try:
            clock = FixedClock(NOW + timedelta(seconds=1))
            storage.claim_next_job("w1", 60, clock=clock)
            init = storage.initialize_controlled_fetch_run_for_job(
                job_id, "w1", "run-h4", clock=clock)
            execution = JobExecutionContext(job_id=job_id, lease_owner="w1",
                run_id=init.run.id, clock=clock)
            attempt = storage.begin_controlled_fetch_attempt(execution)
            late = JobExecutionContext(job_id=job_id, lease_owner="w1",
                run_id=init.run.id, clock=FixedClock(NOW + timedelta(seconds=200)))
            blocked = False
            try:
                storage.mark_controlled_fetch_request_started(late, attempt.id)
            except StaleJobExecutionError:
                blocked = True
            durable = storage.get_controlled_fetch_attempt_for_job(job_id)
            record("H4 stale worker cannot mark REQUEST_STARTED",
                   blocked and durable.status is ControlledFetchAttemptStatus.RESERVED)
        finally:
            storage.close()


# --- H5: adapter zbudowany w offline flow (composition gate) ---
def h5_gate_offline():
    from app.workflows.research.controlled_fetch import (
        ControlledFetchUnavailableError, resolve_controlled_fetch_port)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        for var in ("NIA_CONTROLLED_FETCH_FAKE", "NIA_CONTROLLED_FETCH_FIXTURE"):
            os.environ.pop(var, None)
        blocked = False
        try:
            resolve_controlled_fetch_port(intent, clock=FixedClock(NOW))
        except ControlledFetchUnavailableError:
            blocked = True
        record("H5 real adapter refuses to build without explicit fake fixture", blocked)


# --- H6: środowisko włącza proxy ---
def h6_proxy_scrubbed():
    from app.ports.controlled_fetch import RealControlledHttpTransport
    # Safety kernel scrubuje proxy env; realny transport i tak jawnie tnie proxy.
    import inspect
    src = inspect.getsource(RealControlledHttpTransport.request)
    scrubbed = all(k not in os.environ for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"))
    record("H6 proxy env is scrubbed and transport pins ProxyHandler({})",
           scrubbed and "ProxyHandler({})" in src)


# --- H7: odpowiedź przekracza limit ---
def h7_oversize():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc, max_bytes=1000)
        approve(settings, acc, job_id)
        fixture(tmp, responses={URL: {"status": 200,
            "content_type": "text/html; charset=utf-8", "body_utf8": "x" * 50_000}})
        run_worker(settings, NOW + timedelta(seconds=1), "w1")
        storage = SqliteStorage.open(settings.db_path)
        try:
            job = storage.get_job(job_id)
            attempt = storage.get_controlled_fetch_attempt_for_job(job_id)
            ok = (job.status is JobStatus.FAILED
                  and "RESPONSE_TOO_LARGE" in (job.last_error or "")
                  and attempt.status is ControlledFetchAttemptStatus.FAILED)
            record("H7 oversize response is a controlled FAILED, no OK retrieval",
                   ok and storage.conn.execute(
                       "SELECT count(*) FROM evidence_retrievals WHERE status='OK'"
                   ).fetchone()[0] == 0)
        finally:
            storage.close()


# --- H8: przekierowanie zmienia granicę adresu ---
def h8_redirect_boundary():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        fixture(tmp, responses={URL: {"status": 302, "content_type": None,
            "location": "http://169.254.1.1/x", "body_utf8": ""}})
        run_worker(settings, NOW + timedelta(seconds=1), "w1")
        storage = SqliteStorage.open(settings.db_path)
        try:
            job = storage.get_job(job_id)
            record("H8 redirect crossing address boundary is rejected",
                   "REDIRECT_POLICY_REJECTED:ADDRESS_LINK_LOCAL" in (job.last_error or ""))
        finally:
            storage.close()


# --- H9: REQUEST_STARTED wykonane dwukrotnie ---
def h9_double_request_started():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        storage = SqliteStorage.open(settings.db_path)
        try:
            clock = FixedClock(NOW + timedelta(seconds=1))
            storage.claim_next_job("w1", 60, clock=clock)
            init = storage.initialize_controlled_fetch_run_for_job(
                job_id, "w1", "run-h9", clock=clock)
            execution = JobExecutionContext(job_id=job_id, lease_owner="w1",
                run_id=init.run.id, clock=clock)
            attempt = storage.begin_controlled_fetch_attempt(execution)
            storage.mark_controlled_fetch_request_started(execution, attempt.id)
            blocked = False
            try:
                storage.mark_controlled_fetch_request_started(execution, attempt.id)
            except StaleJobExecutionError:
                blocked = True
            record("H9 REQUEST_STARTED cannot be applied twice", blocked)
        finally:
            storage.close()


# --- H10: restart tworzy drugi retrieval ---
def h10_restart_double_retrieval():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        fixture(tmp)
        moment = NOW + timedelta(seconds=1)
        run_worker(settings, moment, "w1")
        # Drugi worker po sukcesie: job DONE, nic nowego.
        r2 = run_worker(settings, moment + timedelta(seconds=5), "w2")
        storage = SqliteStorage.open(settings.db_path)
        try:
            n = storage.conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0]
            na = storage.conn.execute("SELECT count(*) FROM controlled_fetch_attempts").fetchone()[0]
            record("H10 restart after success creates no second retrieval/attempt",
                   r2.status is WorkerIterationStatus.IDLE and n == 1 and na == 1)
        finally:
            storage.close()


# --- H11: failure tworzy koszt lub provider attempt ---
def h11_failure_no_cost():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        approve(settings, acc, job_id)
        fixture(tmp, responses={URL: {"status": 500,
            "content_type": "text/html", "body_utf8": "err"}})
        run_worker(settings, NOW + timedelta(seconds=1), "w1")
        storage = SqliteStorage.open(settings.db_path)
        try:
            pa = storage.conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0]
            mu = storage.conn.execute("SELECT count(*) FROM model_usage").fetchone()[0]
            cost = storage.conn.execute("SELECT coalesce(sum(cost_usd),0) FROM runs").fetchone()[0]
            record("H11 fetch failure creates no cost, usage or provider attempt",
                   pa == 0 and mu == 0 and float(cost) == 0)
        finally:
            storage.close()


# --- H12: runtime działa na nieaktualnym schema gate ---
def h12_stale_schema_gate():
    from app.storage.db import (EVIDENCE_PIPELINE_SCHEMA_VERSION,
                                SchemaVersionTooOld, initialize_database)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "old.db"
        initialize_database(path, through=EVIDENCE_PIPELINE_SCHEMA_VERSION)
        blocked = False
        try:
            SqliteStorage.open(path)
        except SchemaVersionTooOld:
            blocked = True
        record("H12 runtime refuses to open a 0017 DB (gate requires 0018)", blocked)


# --- H13: approval INSERT dla obcego kontraktu (forge) ---
def h13_forged_approval_insert():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d); acc = account(); settings = make_settings(tmp)
        topic, job_id, intent = seed(settings, acc)
        storage = SqliteStorage.open(settings.db_path)
        try:
            blocked = False
            try:
                storage.conn.execute(
                    "INSERT INTO controlled_fetch_approvals (job_id,account_id,action_type,"
                    "requested_url,intent_fingerprint,timeout_seconds,max_bytes,max_redirects,"
                    "approved_by,approved_at,expires_at,consumed_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                    (job_id, acc.id, "CONTROLLED_FETCH", "https://evil.invalid/",
                     "0"*64, 10, 1000, 1, "atk", "2026-07-18 00:00:00",
                     "2027-01-01 00:00:00"))
                storage.conn.commit()
            except sqlite3.IntegrityError:
                blocked = True
            record("H13 forged approval with wrong URL/fingerprint is refused at SQL floor", blocked)
        finally:
            storage.close()


HYPOTHESES = [h1_approval_cross_job, h2_double_consume, h3_payload_mutation,
              h4_stale_worker_request, h5_gate_offline, h6_proxy_scrubbed,
              h7_oversize, h8_redirect_boundary, h9_double_request_started,
              h10_restart_double_retrieval, h11_failure_no_cost,
              h12_stale_schema_gate, h13_forged_approval_insert]


def main():
    for hypo in HYPOTHESES:
        try:
            hypo()
        except Exception:
            record(hypo.__name__, False, "HARNESS EXCEPTION:\n" + traceback.format_exc())
    print("=" * 78)
    print("E2-B REFUTATION HARNESS — PASS = atak odparty (inwariant się utrzymał)")
    print("=" * 78)
    passed = 0
    for name, refuted, detail in RESULTS:
        status = "PASS" if refuted else "FAIL"
        passed += int(refuted)
        print(f"[{status}] {name}")
        if detail:
            print("    " + detail.replace("\n", "\n    "))
    print("-" * 78)
    print(f"RESULT: {passed}/{len(RESULTS)} inwariantów obronionych")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
