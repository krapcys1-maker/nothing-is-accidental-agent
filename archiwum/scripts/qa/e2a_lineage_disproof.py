"""Independent raw-SQLite disproof harness for E2-A lineage floors."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models import (  # noqa: E402
    Account, AccountMode, AutonomyLevel, Job, JobKind, ResearchFlow,
    ResearchRun, ResearchRunStatus, Run, RunStatus, SourceCandidateRecord,
    Topic, TopicStatus, WorkflowType,
)
from app.ports.fetch import FetchedDocument  # noqa: E402
from app.research.offline_evidence_intent import (  # noqa: E402
    OFFLINE_EVIDENCE_EXECUTION, OFFLINE_EVIDENCE_INTENT_VERSION,
)
from app.storage.db import initialize_database  # noqa: E402
from app.storage.repositories import SqliteStorage  # noqa: E402


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def _account(identifier: str) -> Account:
    return Account(
        id=identifier, display_name=identifier, mode=AccountMode.DRAFT_ONLY,
        autonomy_level=AutonomyLevel.LEVEL_1, active=True,
    )


def _intent(account_id: str, topic_id: int) -> dict:
    source = {
        "url": "https://fixture.invalid/qa", "title": "QA",
        "body_utf8": "Visible deterministic evidence for lineage QA.",
        "excerpt": "Visible deterministic evidence for lineage QA.",
        "claim": "Lineage QA claim.", "final_url": "https://fixture.invalid/qa",
        "http_status": 200, "content_type": "text/plain", "fetch_error": None,
        "author_or_org": None, "published_at": None, "source_type": "PRIMARY",
        "source_quality_score": 1.0, "model_verification_status": "FAILED",
    }
    return {
        "account_id": account_id, "topic_id": topic_id, "dry_run": True,
        "execution": OFFLINE_EVIDENCE_EXECUTION,
        "execution_intent": {
            "version": OFFLINE_EVIDENCE_INTENT_VERSION, "sources": [source],
            "synthesis": {
                "question": "QA?", "working_thesis": "QA thesis.",
                "main_mechanism": "QA mechanism.", "confirmed_claims": ["Lineage QA claim."],
                "uncertain_claims": [], "contradictions": [],
                "strongest_counterargument": "QA counterargument.",
                "citable_numbers": [], "visual_idea": "QA chain.",
                "confidence_score": 1.0, "source_quality_score": 1.0,
            },
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nia-e2a-lineage-") as directory:
        path = Path(directory) / "qa.db"
        initialize_database(path)
        storage = SqliteStorage.open(path)
        a, b = _account("qa-a"), _account("qa-b")
        storage.ensure_account(a)
        storage.ensure_account(b)
        topic = storage.add_topic(a.id, Topic(
            account_id=a.id, title="QA", status=TopicStatus.SELECTED,
        ))
        run_id = "qa-e2a-run"
        storage.create_run(Run(
            id=run_id, account_id=a.id, workflow=WorkflowType.RESEARCH,
            status=RunStatus.DRY_RUN, started_at=NOW,
        ))
        storage.create_research_run(ResearchRun(
            id=run_id, account_id=a.id, topic_id=int(topic.id),
            flow=ResearchFlow.STAGED, status=ResearchRunStatus.DISCOVERY_PENDING,
            created_at=NOW, updated_at=NOW,
        ))
        storage.enqueue_job(Job(
            id="qa-e2a-job", account_id=a.id, kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH, idempotency_key="qa-e2a-job",
            topic_id=int(topic.id), run_id=run_id, payload=_intent(a.id, int(topic.id)),
            schedule_reason="WITHIN_EDITORIAL_WINDOW", earliest_run_at=NOW,
            created_at=NOW,
        ))
        candidates = storage.create_source_candidates(run_id, [
            SourceCandidateRecord(
                research_run_id=run_id, url="https://fixture.invalid/qa", title="QA",
            ),
        ])
        retrieval = storage.record_evidence_retrieval(FetchedDocument(
            requested_url="https://fixture.invalid/qa",
            final_url="https://fixture.invalid/qa", fetched_at=NOW,
            http_status=200, content_type="text/plain",
            body=b"Visible deterministic evidence for lineage QA.",
        ), account_id=a.id, now=NOW)
        storage.close()

        raw = sqlite3.connect(path)
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute(
            "INSERT INTO evidence_candidate_retrievals "
            "(candidate_id,research_run_id,account_id,retrieval_id,created_at)"
            " VALUES (?,?,?,?,?)",
            (candidates[0].id, run_id, a.id, retrieval.id, NOW.isoformat()),
        )
        probes = 0
        for sql, params in [
            (
                "UPDATE evidence_candidate_retrievals SET account_id=? WHERE candidate_id=?",
                (b.id, candidates[0].id),
            ),
            (
                "DELETE FROM evidence_candidate_retrievals WHERE candidate_id=?",
                (candidates[0].id,),
            ),
        ]:
            try:
                raw.execute(sql, params)
            except sqlite3.IntegrityError:
                probes += 1
            else:
                raise AssertionError("append-only lineage probe unexpectedly succeeded")
        raw.execute(
            "INSERT INTO research_source_candidates (research_run_id,url,title,status) "
            "VALUES (?,?,?,'PENDING_EXTRACTION')",
            (run_id, "https://fixture.invalid/foreign", "foreign"),
        )
        foreign_candidate = int(raw.execute("SELECT last_insert_rowid()").fetchone()[0])
        raw.commit()
        # A foreign account and a mismatched run are independently rejected by
        # the trigger even though FK enforcement is disabled.
        for account_id, research_run_id in [(b.id, run_id), (a.id, "foreign-run")]:
            try:
                raw.execute(
                    "INSERT INTO evidence_candidate_retrievals "
                    "(candidate_id,research_run_id,account_id,retrieval_id,created_at)"
                    " VALUES (?,?,?,?,?)",
                    (foreign_candidate, research_run_id, account_id, retrieval.id, NOW.isoformat()),
                )
            except sqlite3.IntegrityError:
                probes += 1
                raw.rollback()
            else:
                raise AssertionError("cross-account/run lineage probe unexpectedly succeeded")
        raw.close()
        print(f"E2A_LINEAGE_QA: PASS probes={probes}/4")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
