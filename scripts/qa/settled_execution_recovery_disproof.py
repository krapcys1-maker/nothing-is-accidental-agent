"""Independent offline disproof for PR1-MAJ-001.

The probe creates only throwaway SQLite databases, never imports a provider SDK,
and never performs network or production-database work.  Exit code 0 proves a
known SETTLED charge can be terminalized once, survives reopen, and cannot be
bypassed through raw SQLite when its canonical usage is missing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pathlib
import sqlite3
import sys
import tempfile
from types import SimpleNamespace


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.testing.safety_kernel import activate as _activate_safety_kernel

_activate_safety_kernel()

from app.core.clock import FixedClock
from app.core.config import REAL_PROVIDER_PRICING_KEYS
from app.models import (
    Account, AccountMode, AutonomyLevel, Job, JobExecutionContext, JobKind,
    ModelUsage, Topic, TopicStatus, WorkflowType,
)
from app.research.durable_intent import DurableResearchExecutionIntent
from app.storage.db import initialize_database
from app.storage.repositories import SqliteStorage


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
EXPIRED = NOW + timedelta(seconds=121)


def _account() -> Account:
    return Account(
        id="nothing_is_accidental", display_name="Nothing Is Accidental",
        mode=AccountMode.FULL_PUBLICATION, autonomy_level=AutonomyLevel.LEVEL_1,
        active=True, niche=["hidden systems"], languages=["en"],
        browser_profile_path="./blocked-browser", writing_profile_path="./blocked-writing",
        allowed_actions=["research"],
    )


def _crash(store: SqliteStorage, suffix: str) -> tuple[str, str, str, int]:
    owner = _account()
    store.ensure_account(owner)
    topic = store.add_topic(owner.id, Topic(
        account_id=owner.id, title=f"QA {suffix}", question="Why?", score=90,
        status=TopicStatus.SELECTED,
    ))
    intent = DurableResearchExecutionIntent.from_settings(
        settings=SimpleNamespace(
            pricing={key: 1.0 for key in REAL_PROVIDER_PRICING_KEYS},
            model_quality="qa-settled-model", research_timeout_seconds=60,
        ),
        account_id=owner.id, topic_id=int(topic.id), cap_usd=0.2,
        max_web_searches=1, question="Why?", niche=owner.niche,
    )
    job = store.enqueue_job(Job(
        id=f"qa-settled-{suffix}", account_id=owner.id, kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH, idempotency_key=f"qa-settled-key-{suffix}",
        topic_id=int(topic.id), schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=NOW, max_attempts=1,
        payload={
            "account_id": owner.id, "topic_id": int(topic.id), "dry_run": False,
            "execution": "durable_provider_v2", "mode": "single",
            "max_cost_usd": intent.cap_usd, "execution_intent": intent.as_payload(),
        },
    ))
    lease = store.claim_next_job(f"qa-owner-{suffix}", 120, now=NOW)
    assert lease is not None
    store.mark_job_running(job.id, lease.lease_owner, now=NOW)
    initialized = store.initialize_research_run_for_job(
        job.id, lease.lease_owner, f"qa-run-{suffix}", now=NOW,
    )
    execution = JobExecutionContext(
        job_id=job.id, lease_owner=lease.lease_owner, run_id=initialized.run.id,
        clock=FixedClock(NOW),
    )
    attempt = store.begin_provider_attempt(
        execution, stage="research", attempt_no=1, max_cost_usd=0.2,
        daily_limit_usd=2.0, monthly_limit_usd=40.0,
    )
    store.mark_provider_attempt_request_started(execution, attempt.request_id)
    usage = store.add_job_model_usage(execution, ModelUsage(
        run_id=execution.run_id, provider=intent.provider, model=intent.model,
        task="research", estimated_cost_usd=0.01, dry_run=False,
        request_id=attempt.request_id,
    ))
    assert usage.id is not None
    return job.id, execution.run_id, attempt.request_id, usage.id


def _row(store: SqliteStorage, table: str, identifier: str):
    column = "request_id" if table == "provider_attempts" else "id"
    return store.conn.execute(
        f"SELECT * FROM {table} WHERE {column}=?", (identifier,),
    ).fetchone()


def _run() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nia-settled-recovery-disproof-") as tmp:
        db_path = pathlib.Path(tmp) / "probe.db"
        initialize_database(db_path)
        store = SqliteStorage.open(db_path)
        job_id, run_id, request_id, _usage_id = _crash(store, "terminal")
        result = store.release_or_requeue_expired_leases(now=EXPIRED)
        if not (
            result.settled_execution_recovery_count == 1
            and _row(store, "jobs", job_id)["status"] == "FAILED"
            and _row(store, "runs", run_id)["status"] == "FAILED"
            and _row(store, "research_runs", run_id)["status"] == "FAILED"
            and _row(store, "provider_attempts", request_id)["status"] == "SETTLED"
            and store.conn.execute(
                "SELECT COUNT(*) FROM model_usage WHERE request_id=?", (request_id,),
            ).fetchone()[0] == 1
            and store.conn.execute(
                "SELECT COUNT(*) FROM reconciliation_events "
                "WHERE request_id=? AND event_type='EXECUTION_RECOVERY'", (request_id,),
            ).fetchone()[0] == 1
        ):
            failures.append("valid SETTLED crash did not converge to one audited failure")
        store.close()

        reopened = SqliteStorage.open(db_path)
        repeated = reopened.release_or_requeue_expired_leases(
            now=EXPIRED + timedelta(days=1),
        )
        if repeated.settled_execution_recovery_count != 0:
            failures.append("reopen created a duplicate execution recovery")

        blocked_job, _blocked_run, blocked_request, blocked_usage = _crash(
            reopened, "missing-usage",
        )
        reopened.conn.execute("DELETE FROM model_usage WHERE id=?", (blocked_usage,))
        reopened.conn.commit()
        blocked = reopened.release_or_requeue_expired_leases(now=EXPIRED)
        if not (
            blocked.settled_execution_blocked_count == 1
            and _row(reopened, "jobs", blocked_job)["status"] == "NEEDS_VERIFICATION"
            and store_event_count(reopened, blocked_request) == 0
        ):
            failures.append("missing canonical usage did not remain fail-closed")
        try:
            reopened.conn.execute(
                "UPDATE jobs SET status='FAILED' WHERE id=?", (blocked_job,),
            )
        except sqlite3.IntegrityError:
            reopened.conn.rollback()
        else:
            failures.append("raw SQLite bypassed EXECUTION_RECOVERY authorization")
            reopened.conn.rollback()
        integrity = reopened.conn.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = reopened.conn.execute("PRAGMA foreign_key_check").fetchall()
        reopened.close()
        if integrity != "ok" or foreign:
            failures.append("throwaway database failed integrity or foreign-key checks")

    if failures:
        for failure in failures:
            print(f"[LEAK] {failure}")
        return 1
    print("[BLOCKED] independent SETTLED execution recovery disproof: 4/4")
    return 0


def store_event_count(store: SqliteStorage, request_id: str) -> int:
    return int(store.conn.execute(
        "SELECT COUNT(*) FROM reconciliation_events "
        "WHERE request_id=? AND event_type='EXECUTION_RECOVERY'", (request_id,),
    ).fetchone()[0])


if __name__ == "__main__":
    raise SystemExit(_run())
