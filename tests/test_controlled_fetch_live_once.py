"""Offline acceptance for the `controlled-fetch-live-once` one-shot executor.

Every test is fully offline: no network, no real API, no model provider, no real
transport. The controlled-fetch transport is exercised only through the in-memory
fake; every write lands in a per-test temporary SQLite database.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.clock import FixedClock
from app.main import main
from app.models import Topic, TopicStatus
from app.operations.controlled_fetch_live import (
    ControlledFetchLiveRequest,
    run_controlled_fetch_live_once,
)
from app.operations.controlled_live import (
    default_db_fingerprint,
    is_fail_closed,
    restore_fail_closed,
)
from app.ports.controlled_fetch import (
    ControlledFetchRequestContract,
    ControlledHttpFetch,
    FakeControlledHttpTransport,
    TransportResponse,
)
from app.storage.repositories import SqliteStorage

REPO_ROOT = Path(__file__).resolve().parents[1]
URL = "https://example.com/approved-source"
PUBLIC_IP = "93.184.216.34"
BODY = "The approved source documents the layout decision in plain readable HTML."
BRANCH = "test-branch"
HEAD = "test-head-sha"
TIMEOUT = 20
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 1


# --------------------------------------------------------------------------- #
# Setup helpers                                                               #
# --------------------------------------------------------------------------- #

def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _seed_topic(settings, account, *, title="Approved fetch source") -> Topic:
    storage = SqliteStorage.open(settings.db_path)
    try:
        storage.ensure_account(account)
        return storage.add_topic(account.id, Topic(
            account_id=account.id, title=title,
            question="What does the approved source document actually say?",
            status=TopicStatus.SELECTED,
        ))
    finally:
        storage.close()


def _enqueue(settings, account, topic, monkeypatch, *, url=URL, timeout=TIMEOUT,
             max_bytes=MAX_BYTES, max_redirects=MAX_REDIRECTS) -> str:
    settings.editorial_schedule = {
        "timezone": "UTC",
        "windows": [{"weekdays": [0, 1, 2, 3, 4, 5, 6], "start": "00:00", "end": "23:59"}],
    }
    monkeypatch.setattr("app.main.load_settings", lambda: settings)
    assert main([
        "enqueue-controlled-fetch",
        "--account-id", account.id, "--topic-id", str(topic.id),
        "--url", url, "--source-identity", "approved-source-en",
        "--timeout-seconds", str(timeout), "--max-bytes", str(max_bytes),
        "--max-redirects", str(max_redirects),
        "--expires-at", _iso(datetime.now(timezone.utc) + timedelta(hours=6)),
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


def _approve(account, job_id, *, hours=2) -> None:
    assert main([
        "approve-controlled-fetch", "--job-id", job_id, "--account-id", account.id,
        "--approved-by", "test-owner-l1",
        "--expires-at", _iso(datetime.now(timezone.utc) + timedelta(hours=hours)),
    ]) == 0


def _fail_closed_baseline(settings) -> None:
    storage = SqliteStorage.open(settings.db_path)
    try:
        restore_fail_closed(storage, reason="test baseline fail-closed")
    finally:
        storage.close()


def _prepare(settings, account, monkeypatch, **enqueue_kwargs) -> tuple[str, Topic]:
    topic = _seed_topic(settings, account)
    job_id = _enqueue(settings, account, topic, monkeypatch, **enqueue_kwargs)
    _approve(account, job_id)
    _fail_closed_baseline(settings)
    return job_id, topic


def _flags(db_path) -> dict[str, bool]:
    conn = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return {
            key: json.loads(value_json)
            for key, value_json in conn.execute(
                "SELECT key, value_json FROM system_flags"
            ).fetchall()
        }
    finally:
        conn.close()


def _request(settings, account, job_id, **overrides) -> ControlledFetchLiveRequest:
    fingerprint = default_db_fingerprint(settings.db_path)
    kwargs = dict(
        job_id=job_id, account_id=account.id,
        expected_db_sha256=fingerprint.sha256, expected_schema=fingerprint.schema_tail,
        expected_branch=BRANCH, expected_head=HEAD,
    )
    kwargs.update(overrides)
    return ControlledFetchLiveRequest(**kwargs)


class _FakeFactory:
    """Builds an in-memory controlled-fetch port; records every transport built."""

    def __init__(self, *, register_url=URL, db_path=None, flags_seen=None):
        self._register_url = register_url
        self._db_path = db_path
        self._flags_seen = flags_seen
        self.transports: list[FakeControlledHttpTransport] = []
        self.factory_calls = 0

    def __call__(self, authorization, *, settings, clock):
        self.factory_calls += 1
        if self._flags_seen is not None and self._db_path is not None:
            self._flags_seen.clear()
            self._flags_seen.update(_flags(self._db_path))
        contract = ControlledFetchRequestContract(
            requested_url=authorization.requested_url,
            timeout_seconds=authorization.timeout_seconds,
            max_bytes=authorization.max_bytes,
            max_redirects=authorization.max_redirects,
            allowed_content_types=authorization.allowed_content_types,
        )
        responses = {}
        if self._register_url is not None:
            responses[self._register_url] = TransportResponse(
                status=200, content_type="text/html", location=None,
                body=BODY.encode("utf-8"), body_complete=True,
            )
        transport = FakeControlledHttpTransport(responses)
        self.transports.append(transport)

        def resolver(hostname: str) -> tuple[str, ...]:
            return {"example.com": (PUBLIC_IP,)}.get(hostname, (PUBLIC_IP,))

        return ControlledHttpFetch(
            contract=contract, transport=transport, resolver=resolver, clock=clock,
        )

    @property
    def transport_calls(self) -> int:
        return sum(len(t.calls) for t in self.transports)


def _run(settings, request, factory, *, moment=None):
    moment = moment or (datetime.now(timezone.utc) + timedelta(seconds=5))
    storage = SqliteStorage.open(settings.db_path)
    try:
        return run_controlled_fetch_live_once(
            request, settings=settings, storage=storage,
            project_root=settings.project_root, clock=FixedClock(moment),
            git_identity=lambda _root: (BRANCH, HEAD),
            fetch_port_factory=factory,
        )
    finally:
        storage.close()


class _Overlay:
    """Read-only attribute overlay over any model object (dataclass or pydantic)."""

    def __init__(self, base, **overrides):
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_ov", overrides)

    def __getattr__(self, name):
        overrides = object.__getattribute__(self, "_ov")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self, "_base"), name)


class _StorageProxy:
    """Delegates every call to a real storage, optionally rewriting one lookup."""

    def __init__(self, real, *, job_mutator=None, approval_mutator=None):
        self._real = real
        self._job_mutator = job_mutator
        self._approval_mutator = approval_mutator

    def __getattr__(self, name):
        return getattr(self._real, name)

    def get_job(self, job_id):
        job = self._real.get_job(job_id)
        if job is not None and self._job_mutator is not None:
            return self._job_mutator(job)
        return job

    def get_controlled_fetch_approval_for_job(self, job_id):
        approval = self._real.get_controlled_fetch_approval_for_job(job_id)
        if approval is not None and self._approval_mutator is not None:
            return self._approval_mutator(approval)
        return approval


def _run_with_storage(settings, request, factory, storage, *, moment=None):
    moment = moment or (datetime.now(timezone.utc) + timedelta(seconds=5))
    return run_controlled_fetch_live_once(
        request, settings=settings, storage=storage,
        project_root=settings.project_root, clock=FixedClock(moment),
        git_identity=lambda _root: (BRANCH, HEAD), fetch_port_factory=factory,
    )


def _counts(settings, job_id):
    storage = SqliteStorage.open(settings.db_path)
    try:
        conn = storage.conn
        return {
            "retrievals": conn.execute("SELECT count(*) FROM evidence_retrievals").fetchone()[0],
            "attempts": conn.execute(
                "SELECT count(*) FROM controlled_fetch_attempts WHERE job_id=?", (job_id,),
            ).fetchone()[0],
            "request_started": conn.execute(
                "SELECT count(*) FROM controlled_fetch_attempts "
                "WHERE job_id=? AND request_started_at IS NOT NULL", (job_id,),
            ).fetchone()[0],
            "model_usage": conn.execute("SELECT count(*) FROM model_usage").fetchone()[0],
            "provider_attempts": conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0],
            "job_status": storage.get_job(job_id).status.value,
            "approval_consumed": conn.execute(
                "SELECT consumed_at FROM controlled_fetch_approvals WHERE job_id=?", (job_id,),
            ).fetchone()[0],
        }
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# 1, 14, 15, 16, 4, 12: happy path                                            #
# --------------------------------------------------------------------------- #

def test_approved_job_executes_one_transport_and_writes_retrieval(
        settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    factory = _FakeFactory()

    outcome = _run(settings, _request(settings, account, job_id), factory)

    assert outcome.status == "SUCCEEDED", outcome
    assert outcome.exit_code == 0
    assert outcome.retrieval_id is not None
    assert factory.factory_calls == 1          # exactly one transport built
    assert factory.transport_calls == 1        # exactly one transport request
    counts = _counts(settings, job_id)
    assert counts["attempts"] == 1             # exactly one attempt
    assert counts["request_started"] == 1      # exactly one REQUEST_STARTED
    assert counts["retrievals"] == 1           # retrieval written after OK
    assert counts["job_status"] == "DONE"
    assert counts["approval_consumed"] is not None  # approval consumed exactly once
    assert is_fail_closed(outcome.flags_after)      # restored after success


# --------------------------------------------------------------------------- #
# 2: only the named job runs when several are queued                          #
# --------------------------------------------------------------------------- #

def test_only_named_job_runs_when_multiple_queued(settings, account, monkeypatch):
    topic_a = _seed_topic(settings, account, title="Source A")
    topic_b = _seed_topic(settings, account, title="Source B")
    job_a = _enqueue(settings, account, topic_a, monkeypatch)
    job_b = _enqueue(settings, account, topic_b, monkeypatch)
    _approve(account, job_a)
    _approve(account, job_b)
    _fail_closed_baseline(settings)

    outcome = _run(settings, _request(settings, account, job_a), _FakeFactory())

    assert outcome.status == "SUCCEEDED", outcome
    storage = SqliteStorage.open(settings.db_path)
    try:
        assert storage.get_job(job_a).status.value == "DONE"
        # The other queued job is completely untouched: still QUEUED, never leased.
        other = storage.get_job(job_b)
        assert other.status.value == "QUEUED"
        assert other.lease_owner is None
        assert storage.get_controlled_fetch_attempt_for_job(job_b) is None
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# 3: URL and limits come from the frozen intent, never from execution args    #
# --------------------------------------------------------------------------- #

def test_url_and_limits_come_from_frozen_intent(settings, account, monkeypatch):
    job_id, _topic = _prepare(
        settings, account, monkeypatch, timeout=13, max_bytes=222_000, max_redirects=0,
    )
    factory = _FakeFactory()

    outcome = _run(settings, _request(settings, account, job_id), factory)

    assert outcome.status == "SUCCEEDED", outcome
    call = factory.transports[0].calls[0]
    # The command has no url/timeout/max-bytes/redirect arguments; these can only
    # originate from the frozen intent recorded at enqueue time.
    assert call["url"] == URL
    assert call["timeout_seconds"] == 13
    assert call["max_read_bytes"] == 222_000


# --------------------------------------------------------------------------- #
# 5, 17: re-running a consumed approval performs no transport                  #
# --------------------------------------------------------------------------- #

def test_rerun_after_success_does_no_transport(settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    assert _run(settings, _request(settings, account, job_id), _FakeFactory()).status == "SUCCEEDED"

    second_factory = _FakeFactory()
    # The job is now DONE and the approval consumed; the fingerprint no longer
    # matches a fresh request. Recompute the request against the post-run DB.
    outcome = _run(settings, _request(settings, account, job_id), second_factory)

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code in {"JOB_NOT_EXECUTABLE", "APPROVAL_ALREADY_CONSUMED"}
    assert second_factory.factory_calls == 0     # no second transport
    counts = _counts(settings, job_id)
    assert counts["attempts"] == 1               # still exactly one attempt
    assert counts["retrievals"] == 1
    assert is_fail_closed(_flags(settings.db_path))


# --------------------------------------------------------------------------- #
# 6, 7, 8: binding refusals — no transport, flags never open                   #
# --------------------------------------------------------------------------- #

def test_expired_approval_blocks_before_transport(settings, account, monkeypatch):
    topic = _seed_topic(settings, account)
    job_id = _enqueue(settings, account, topic, monkeypatch)
    _approve(account, job_id, hours=1)
    _fail_closed_baseline(settings)
    factory = _FakeFactory()

    # Clock five hours ahead: the one-hour approval has expired.
    outcome = _run(
        settings, _request(settings, account, job_id), factory,
        moment=datetime.now(timezone.utc) + timedelta(hours=5),
    )

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code in {"APPROVAL_EXPIRED", "INTENT_EXPIRED"}
    assert factory.factory_calls == 0
    assert _counts(settings, job_id)["attempts"] == 0
    assert is_fail_closed(_flags(settings.db_path))  # flags never opened


def test_fingerprint_mismatch_blocks_before_transport(settings, account, monkeypatch):
    # The durable job and approval are immutable, so an approval whose fingerprint
    # no longer binds the frozen intent is exercised through a storage proxy.
    job_id, _topic = _prepare(settings, account, monkeypatch)
    factory = _FakeFactory()
    storage = SqliteStorage.open(settings.db_path)
    proxy = _StorageProxy(
        storage,
        approval_mutator=lambda a: _Overlay(a, intent_fingerprint="mismatched-fingerprint"),
    )
    try:
        outcome = _run_with_storage(
            settings, _request(settings, account, job_id), factory, proxy,
        )
    finally:
        storage.close()

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code == "APPROVAL_FINGERPRINT_MISMATCH"
    assert factory.factory_calls == 0
    assert _counts(settings, job_id)["attempts"] == 0
    assert is_fail_closed(_flags(settings.db_path))


def test_wrong_account_blocks(settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    factory = _FakeFactory()

    outcome = _run(
        settings, _request(settings, account, job_id, account_id="someone_else"), factory,
    )

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code == "JOB_ACCOUNT_MISMATCH"
    assert factory.factory_calls == 0
    assert is_fail_closed(_flags(settings.db_path))


def test_non_controlled_fetch_job_blocks(settings, account, monkeypatch):
    # A durable job whose execution is not controlled_fetch_v1 must be refused
    # (exercised via a proxy that rewrites the frozen execution kind).
    job_id, _topic = _prepare(settings, account, monkeypatch)
    factory = _FakeFactory()
    storage = SqliteStorage.open(settings.db_path)
    proxy = _StorageProxy(
        storage,
        job_mutator=lambda j: _Overlay(
            j, payload=dict(j.payload, execution="offline_evidence_v1"),
        ),
    )
    try:
        outcome = _run_with_storage(
            settings, _request(settings, account, job_id), factory, proxy,
        )
    finally:
        storage.close()

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code == "JOB_NOT_CONTROLLED_FETCH"
    assert factory.factory_calls == 0
    assert is_fail_closed(_flags(settings.db_path))


# --------------------------------------------------------------------------- #
# 9: environment guard mismatches refuse execution                            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("override,reason", [
    ({"expected_db_sha256": "0" * 64}, "DB_SHA_MISMATCH"),
    ({"expected_schema": "9999_not_a_real_schema"}, "SCHEMA_MISMATCH"),
    ({"expected_branch": "wrong-branch"}, "BRANCH_MISMATCH"),
    ({"expected_head": "wrong-head"}, "HEAD_MISMATCH"),
])
def test_env_guard_mismatch_blocks(settings, account, monkeypatch, override, reason):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    factory = _FakeFactory()

    outcome = _run(settings, _request(settings, account, job_id, **override), factory)

    assert outcome.status == "BLOCKED"
    assert outcome.reason_code == reason
    assert factory.factory_calls == 0
    assert _counts(settings, job_id)["attempts"] == 0
    assert is_fail_closed(_flags(settings.db_path))


# --------------------------------------------------------------------------- #
# 10: the process-local real capability never persists                        #
# --------------------------------------------------------------------------- #

def test_process_local_capability_does_not_persist(settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    assert settings.controlled_fetch_real_enabled is False

    outcome = _run(settings, _request(settings, account, job_id), _FakeFactory())

    assert outcome.status == "SUCCEEDED", outcome
    # The passed-in settings object is untouched (the wrapper only used an
    # in-memory replace()) and a freshly constructed Settings still defaults off.
    assert settings.controlled_fetch_real_enabled is False
    from app.core.config import Settings
    assert Settings(
        project_root=Path("."), data_dir=Path("."), db_path=Path("x.db"),
        costs_csv_path=Path("c.csv"),
    ).controlled_fetch_real_enabled is False


# --------------------------------------------------------------------------- #
# 11, 12: flags open only inside the controlled window, restored afterwards    #
# --------------------------------------------------------------------------- #

def test_flags_open_only_during_window_then_restored(settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    assert is_fail_closed(_flags(settings.db_path))     # closed before
    flags_seen: dict[str, bool] = {}
    factory = _FakeFactory(db_path=settings.db_path, flags_seen=flags_seen)

    outcome = _run(settings, _request(settings, account, job_id), factory)

    assert outcome.status == "SUCCEEDED", outcome
    # Observed at the exact moment the transport was built (mid-execution):
    assert flags_seen["worker_enabled"] is True
    assert flags_seen["kill_switch"] is False
    assert flags_seen["safe_mode"] is False
    # Minimal profile: a zero-cost fetch never opens the paid-actions gate.
    assert flags_seen["paid_actions_enabled"] is False
    assert flags_seen["browser_actions_enabled"] is False
    # Closed again afterwards.
    assert is_fail_closed(_flags(settings.db_path))
    assert is_fail_closed(outcome.flags_after)


# --------------------------------------------------------------------------- #
# 13, 17: a failure after the possible request restores fail-closed safely     #
# --------------------------------------------------------------------------- #

def test_transport_failure_after_request_safely_terminalizes_and_restores(
        settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)
    # Register NO scripted response: the transport fails after REQUEST_STARTED.
    factory = _FakeFactory(register_url=None)

    outcome = _run(settings, _request(settings, account, job_id), factory)

    # A failure after the possible request must terminalize safely (FAILED or the
    # uncertain NEEDS_VERIFICATION) — never a silent success, never a 2nd transport.
    assert outcome.status in {"FAILED", "NEEDS_VERIFICATION"}, outcome
    assert outcome.exit_code in {2, 3}
    assert factory.factory_calls == 1           # transport built exactly once
    assert factory.transport_calls == 1         # exactly one transport request
    counts = _counts(settings, job_id)
    assert counts["attempts"] == 1
    assert counts["request_started"] == 1
    assert counts["job_status"] in {"FAILED", "NEEDS_VERIFICATION"}
    # No successful (OK) retrieval is ever written on the failure path; a FAILED
    # audit record may exist, but the source is never admitted as usable evidence.
    storage = SqliteStorage.open(settings.db_path)
    try:
        ok_retrievals = storage.conn.execute(
            "SELECT count(*) FROM evidence_retrievals WHERE status='OK'"
        ).fetchone()[0]
    finally:
        storage.close()
    assert ok_retrievals == 0
    assert is_fail_closed(outcome.flags_after)  # restored even on the error path
    assert is_fail_closed(_flags(settings.db_path))


# --------------------------------------------------------------------------- #
# 18: no model provider, usage, or cost is ever produced                       #
# --------------------------------------------------------------------------- #

def test_no_model_provider_usage_or_cost(settings, account, monkeypatch):
    job_id, _topic = _prepare(settings, account, monkeypatch)

    outcome = _run(settings, _request(settings, account, job_id), _FakeFactory())

    assert outcome.status == "SUCCEEDED", outcome
    counts = _counts(settings, job_id)
    assert counts["model_usage"] == 0
    assert counts["provider_attempts"] == 0
    storage = SqliteStorage.open(settings.db_path)
    try:
        run_row = storage.conn.execute(
            "SELECT cost_usd FROM runs WHERE id=(SELECT run_id FROM jobs WHERE id=?)",
            (job_id,),
        ).fetchone()
        assert float(run_row[0]) == 0.0
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# 19: full CLI entrypoint through a subprocess                                 #
# --------------------------------------------------------------------------- #

def test_subprocess_cli_full_entrypoint(settings, account, monkeypatch, tmp_path):
    job_id, _topic = _prepare(settings, account, monkeypatch)

    fixture = tmp_path / "fetch-fixture.json"
    fixture.write_text(json.dumps({
        "responses": {URL: {
            "status": 200, "content_type": "text/html; charset=utf-8", "body_utf8": BODY,
        }},
        "resolved_addresses": {"example.com": [PUBLIC_IP]},
    }), encoding="utf-8")

    from app.operations.stage1_migration import _git_identity
    branch, head = _git_identity(REPO_ROOT)
    fingerprint = default_db_fingerprint(settings.db_path)

    env = dict(os.environ)
    env.update({
        "NIA_TEST_MODE": "1",
        "NIA_CONTROLLED_FETCH_LIVE_FAKE": "1",
        "NIA_CONTROLLED_FETCH_LIVE_TEST_DB_PATH": str(settings.db_path),
        "NIA_CONTROLLED_FETCH_FAKE": "1",
        "NIA_CONTROLLED_FETCH_FIXTURE": str(fixture),
    })
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "controlled-fetch-live-once",
         "--job-id", job_id, "--account-id", account.id,
         "--expected-db-sha", fingerprint.sha256,
         "--expected-schema", fingerprint.schema_tail,
         "--expected-branch", branch, "--expected-head", head],
        cwd=REPO_ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CONTROLLED-FETCH-LIVE-ONCE: SUCCEEDED" in result.stdout
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "SUCCEEDED"
    assert payload["fail_closed"] is True
    assert payload["retrieval_id"] is not None
    # Durable state: exactly one retrieval, job DONE, flags fail-closed.
    assert _counts(settings, job_id)["retrievals"] == 1
    assert _counts(settings, job_id)["job_status"] == "DONE"
    assert is_fail_closed(_flags(settings.db_path))
