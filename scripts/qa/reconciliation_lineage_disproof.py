"""Persistent, reviewer-runnable self-disproof for W1A-VERIFY-02 (lineage).

Independent review found a fail-open where the reconciliation resolver accepted an
attempt whose ``runs.account_id`` was foreign and ``runs.workflow`` was ANALYTICS.
This script tries to force that class of defect on throwaway temporary SQLite
databases and asserts the resolver fails closed with zero mutation.

Safety: activates the inherited test safety kernel (blocks network, blocks the
project ``data/agent.db``, scrubs provider secrets) before opening any database.
No network, no SDK, no cost.  Exit code 0 means every attack was blocked; exit
code 1 means at least one leak (or an unexpected error).

Run from the repository root:

    python scripts/qa/reconciliation_lineage_disproof.py
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.testing.safety_kernel import activate as _activate_safety_kernel

_activate_safety_kernel()

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS, Settings
from app.models import (
    Account, AccountMode, AutonomyLevel, ExecutionResolution, FinancialResolution, Job,
    JobExecutionContext, JobKind, Topic, TopicStatus, WorkflowType,
)
from app.ports.storage import (
    ProviderAttemptReconciliationError, ReconciliationPreviewStaleError,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
_RESULTS: list[tuple[str, bool, str]] = []
# W1A-QA-01: every temporary database directory carries this prefix and is
# removed in run()'s finally block, even after an exception.  The final check
# fails the run if any directory with the prefix survives in the temp root.
_TMP_PREFIX = "nia-lineage-disproof-"
_TMPDIRS: list[str] = []


def _check(name: str, blocked: bool, evidence: str) -> None:
    _RESULTS.append((name, blocked, evidence))
    print(f"[{'BLOCKED' if blocked else 'LEAK'}] {name} :: {evidence}")


def _account(account_id: str) -> Account:
    return Account(
        id=account_id, display_name=account_id, mode=AccountMode.FULL_PUBLICATION,
        autonomy_level=AutonomyLevel.LEVEL_1, active=True, niche=["hidden systems"],
        languages=["en"], browser_profile_path="./p", writing_profile_path="./w.md",
        allowed_actions=["research"],
    )


def _settings(tmp: str) -> Settings:
    data = pathlib.Path(tmp) / "data"
    return Settings(
        project_root=pathlib.Path(tmp), data_dir=data, db_path=data / "agent.db",
        costs_csv_path=pathlib.Path(tmp) / "COSTS.csv", dry_run=True, kill_switch=False,
        max_daily_cost_usd=2.0, max_monthly_cost_usd=40.0, monthly_limit_has_priority=True,
        model_fast="dry", model_quality="reconciliation-model",
        pricing={"input_per_mtok": 3.0, "output_per_mtok": 15.0, "cache_read_per_mtok": 0.0,
                 "cache_write_per_mtok": 0.0, "web_search_per_1k": 0.0},
        article_min_score=75.0, note_min_score=65.0, topic_scoring_weights={"curiosity": 100.0},
        anthropic_api_key=None, accounts={"nothing_is_accidental": _account("nothing_is_accidental")},
    )


def _fresh_store() -> tuple[SqliteStorage, Account]:
    tmp = tempfile.mkdtemp(prefix=_TMP_PREFIX)
    _TMPDIRS.append(tmp)
    initialize_database(_settings(tmp).db_path)
    store = SqliteStorage.open(_settings(tmp).db_path)
    owner = _account("nothing_is_accidental")
    store.ensure_account(owner)
    store.ensure_account(_account("foreign_account"))
    return store, owner


def _cleanup_tmpdirs() -> list[str]:
    """Remove every created temp directory; return the paths that survived."""
    import shutil

    leftovers: list[str] = []
    for path in _TMPDIRS:
        shutil.rmtree(path, ignore_errors=True)
        if pathlib.Path(path).exists():
            leftovers.append(path)
    temp_root = pathlib.Path(tempfile.gettempdir())
    leftovers.extend(
        str(entry) for entry in temp_root.glob(f"{_TMP_PREFIX}*")
        if str(entry) not in leftovers
    )
    return leftovers


def _needs_reconciliation(store, account, suffix, *, topic_id=None):
    if topic_id is None:
        topic = store.add_topic(account.id, Topic(
            account_id=account.id, title=f"T{suffix}", question="Why?", score=90, status=TopicStatus.SELECTED))
        topic_id = int(topic.id)
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(pricing={k: 1.0 for k in REAL_PROVIDER_PRICING_KEYS},
                                 model_quality="reconciliation-model", research_timeout_seconds=60),
        account_id=account.id, topic_id=topic_id, cap_usd=0.2, max_web_searches=1,
        question="Why?", niche=account.niche)
    job = store.enqueue_job(Job(
        id=f"job-{suffix}", account_id=account.id, kind=JobKind.RESEARCH, workflow=WorkflowType.RESEARCH,
        idempotency_key=f"key-{suffix}", topic_id=topic_id, schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={"account_id": account.id, "topic_id": topic_id, "dry_run": False,
                 "execution": "durable_provider_v2", "mode": "single", "max_cost_usd": intent.cap_usd,
                 "execution_intent": intent.as_payload()}))
    lease = store.claim_next_job(f"owner-{suffix}", 120, now=NOW)
    store.mark_job_running(job.id, lease.lease_owner, now=NOW)
    init = store.initialize_research_run_for_job(job.id, lease.lease_owner, f"run-{suffix}", now=NOW)
    ex = JobExecutionContext(job_id=job.id, lease_owner=lease.lease_owner, run_id=init.run.id, clock=FixedClock(NOW))
    attempt = store.begin_provider_attempt(ex, stage="research", attempt_no=1, max_cost_usd=0.2,
                                           daily_limit_usd=2.0, monthly_limit_usd=40.0)
    store.mark_provider_attempt_request_started(ex, attempt.request_id)
    store.mark_provider_attempt_needs_reconciliation(ex, attempt.request_id, error_code="UNKNOWN")
    store.mark_job_needs_verification(ex.job_id, ex.lease_owner, "UNKNOWN", now=NOW)
    return ex, attempt.request_id


def _snap(store, ex, rid):
    return (
        store.conn.execute("SELECT status FROM provider_attempts WHERE request_id=?", (rid,)).fetchone()[0],
        store.conn.execute("SELECT COUNT(*) FROM provider_attempts WHERE job_id=?", (ex.job_id,)).fetchone()[0],
        store.conn.execute("SELECT status FROM jobs WHERE id=?", (ex.job_id,)).fetchone()[0],
        store.conn.execute("SELECT status FROM runs WHERE id=?", (ex.run_id,)).fetchone()[0],
        store.conn.execute("SELECT status FROM research_runs WHERE id=?", (ex.run_id,)).fetchone()[0],
        store.conn.execute("SELECT COUNT(*) FROM model_usage WHERE run_id=? AND dry_run=0 AND is_legacy_usage=0",
                           (ex.run_id,)).fetchone()[0],
        store.conn.execute("SELECT COUNT(*) FROM reconciliation_events WHERE request_id=?", (rid,)).fetchone()[0],
    )


def _resolve(store, rid, account_id, **kw):
    return store.resolve_provider_attempt_reconciliation(
        request_id=rid, account_id=account_id,
        financial_resolution=FinancialResolution.NOT_CHARGED,
        execution_resolution=ExecutionResolution.EXECUTION_FAILED,
        actual_cost_usd=None, reconciled_by="op", note="disproof", **kw)


def _expect_blocked(name, store, ex, rid, call, *, exc=ProviderAttemptReconciliationError):
    before = _snap(store, ex, rid)
    try:
        call()
        _check(name, False, "resolver accepted a divergent lineage")
    except exc as err:
        after = _snap(store, ex, rid)
        _check(name, before == after and after[0] == "NEEDS_RECONCILIATION", f"{type(err).__name__}; no_mutation={before == after}")


def _run_checks() -> int:
    # 1. Reviewer's exact scenario: foreign runs.account_id + ANALYTICS workflow.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d1")
    store.conn.execute("UPDATE runs SET account_id='foreign_account', workflow='ANALYTICS' WHERE id=?", (ex.run_id,))
    store.conn.commit()
    _expect_blocked("reviewer scenario: foreign run account + ANALYTICS workflow", store, ex, rid,
                    lambda: _resolve(store, rid, owner.id))
    store.close()

    # 2. Foreign research_runs.account_id only.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d2")
    store.conn.execute("UPDATE research_runs SET account_id='foreign_account' WHERE id=?", (ex.run_id,))
    store.conn.commit()
    _expect_blocked("foreign research_run account", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 3. runs.workflow = ANALYTICS alone.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d3")
    store.conn.execute("UPDATE runs SET workflow='ANALYTICS' WHERE id=?", (ex.run_id,))
    store.conn.commit()
    _expect_blocked("run workflow ANALYTICS", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 4. Wrong job kind.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d4")
    store.conn.execute("UPDATE jobs SET kind='LOCAL' WHERE id=?", (ex.job_id,))
    store.conn.commit()
    _expect_blocked("job kind not RESEARCH", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 5. jobs.run_id -> foreign full run.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d5")
    other, _ = _needs_reconciliation(store, _account("foreign_account"), "d5-foreign")
    store.conn.execute("UPDATE jobs SET run_id=? WHERE id=?", (other.run_id, ex.job_id))
    store.conn.commit()
    _expect_blocked("jobs.run_id points at a foreign run", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 6. research_run topic mismatch.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d6")
    other_topic = store.add_topic(owner.id, Topic(account_id=owner.id, title="Other", question="Why?",
                                                  score=90, status=TopicStatus.SELECTED))
    store.conn.execute("UPDATE research_runs SET topic_id=? WHERE id=?", (int(other_topic.id), ex.run_id))
    store.conn.commit()
    _expect_blocked("research_run topic mismatch", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 7. Tampered durable intent account.
    import json
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d7")
    payload = json.loads(store.conn.execute("SELECT payload_json FROM jobs WHERE id=?", (ex.job_id,)).fetchone()[0])
    payload["execution_intent"]["account_id"] = "foreign_account"
    store.conn.execute("UPDATE jobs SET payload_json=? WHERE id=?", (json.dumps(payload), ex.job_id))
    store.conn.commit()
    _expect_blocked("tampered durable intent account", store, ex, rid, lambda: _resolve(store, rid, owner.id))
    store.close()

    # 8. Stale token: runs.account_id changes between preview and confirm.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d8")
    token = store.preview_provider_attempt_reconciliation(request_id=rid, account_id=owner.id).version_token
    store.conn.execute("UPDATE runs SET account_id='foreign_account' WHERE id=?", (ex.run_id,))
    store.conn.commit()
    _expect_blocked("stale token after runs.account_id change", store, ex, rid,
                    lambda: _resolve(store, rid, owner.id, expected_version_token=token),
                    exc=ReconciliationPreviewStaleError)
    store.close()

    # 9. SQLite trigger: raw terminal UPDATE on a foreign-account run fails closed.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d9")
    store.conn.execute("UPDATE runs SET account_id='foreign_account' WHERE id=?", (ex.run_id,))
    store.conn.commit()
    before = _snap(store, ex, rid)
    try:
        store.conn.execute(
            "UPDATE provider_attempts SET status='RECONCILED_RELEASED',released_at=?,reconciled_at=?,"
            "reconciled_by=?,reconciliation_note=?,reconciliation_resolution=? "
            "WHERE request_id=? AND status='NEEDS_RECONCILIATION'",
            ("2026-07-15 12:00:00", "2026-07-15 12:00:00", "op", "n", "NOT_CHARGED:EXECUTION_FAILED", rid))
        store.conn.commit()
        _check("SQLite trigger blocks raw terminalization", False, "raw UPDATE terminalized a foreign-run attempt")
    except sqlite3.IntegrityError as err:
        store.conn.rollback()
        _check("SQLite trigger blocks raw terminalization", _snap(store, ex, rid) == before, f"IntegrityError: {err}")
    store.close()

    # 10. Positive control: a consistent lineage still reconciles cleanly.
    store, owner = _fresh_store()
    ex, rid = _needs_reconciliation(store, owner, "d10")
    _resolve(store, rid, owner.id)
    ok = (_snap(store, ex, rid)[0] == "RECONCILED_RELEASED"
          and store.conn.execute("SELECT status FROM runs WHERE id=?", (ex.run_id,)).fetchone()[0] == "FAILED")
    _check("positive control: consistent lineage reconciles", ok, "RECONCILED_RELEASED / run FAILED")
    store.close()

    print("\n==== SUMMARY ====")
    leaks = [name for name, blocked, _ in _RESULTS if not blocked]
    print(f"checks={len(_RESULTS)} blocked={len(_RESULTS) - len(leaks)} leaks={len(leaks)}")
    if leaks:
        print("LEAKS:", leaks)
        return 1
    print("ALL LINEAGE DISPROOF ATTEMPTS BLOCKED")
    return 0


def run() -> int:
    """Run all checks, then guarantee temp-directory cleanup (W1A-QA-01)."""
    try:
        outcome = _run_checks()
    finally:
        leftovers = _cleanup_tmpdirs()
    if leftovers:
        print(f"TEMP LEAK: leftover temporary directories: {leftovers}")
        return 1
    print("TEMP CLEANUP OK: no leftover temporary directories")
    return outcome


if __name__ == "__main__":
    raise SystemExit(run())
