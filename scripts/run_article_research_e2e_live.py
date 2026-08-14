"""One controlled ARTICLE_RESEARCH E2E: A1 -> fetches -> corpus -> card."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from app.core.clock import SystemClock
from app.core.config import load_settings
from app.models import Job, JobKind, JobStatus, TopicStatus
from app.model_routing.contracts import LogicalModelRole
from app.operations.controlled_fetch_live import (
    ControlledFetchLiveRequest,
    run_controlled_fetch_live_once,
)
from app.operations.controlled_live import OPEN_PROFILE_ORDER, restore_fail_closed
from app.policies.policy_engine import PolicyEngine
from app.research.durable_intent import DurableResearchExecutionIntent
from app.research.source_discovery_intent import (
    SOURCE_DISCOVERY_EXECUTION,
    SourceDiscoveryIntent,
)
from app.scheduler.dispatcher import JobDispatcher, _run_durable_real_research
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.db import RUNTIME_SCHEMA_VERSION
from app.storage.repositories import SqliteStorage


MODEL_ID = "claude-opus-5"
PROVIDER = "ANTHROPIC"


def _git_identity(root: Path) -> tuple[str, str]:
    import subprocess

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True,
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True,
    ).strip()
    return branch, head


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkpointed_sha256(storage: SqliteStorage, path: Path) -> str:
    checkpoint = storage.conn.execute("PRAGMA wal_checkpoint(FULL)").fetchone()
    if checkpoint is None or int(checkpoint[0]) != 0:
        raise RuntimeError("database WAL checkpoint did not complete before live fetch")
    return _sha256(path)


def _run_model_job(
    storage: SqliteStorage,
    settings,
    job_id: str,
    *,
    updated_by: str,
) -> str:
    clock = SystemClock()
    # The daily limit comes from config/growth_policy.yaml, which is where the
    # owner sets budget policy.  This used to hardcode 10.0, which silently
    # overrode a deliberately configured higher limit and blocked healthy runs
    # for a reason no operator could see.  The per-run fences that actually
    # bound one execution -- --max-cost-usd here and the intent cap -- are
    # unchanged.
    real = replace(
        settings,
        dry_run=False,
        model_quality=MODEL_ID,
        research_timeout_seconds=max(settings.research_timeout_seconds, 120),
    )
    policy = PolicyEngine(real, storage, clock)
    def diagnostic_research_real(*args, **kwargs):
        try:
            return _run_durable_real_research(*args, **kwargs)
        except Exception as exc:
            print(json.dumps({
                "status": "RESEARCH_PIPELINE_EXCEPTION",
                "exception_type": type(exc).__name__,
                "detail": str(exc),
            }, sort_keys=True))
            raise

    dispatcher = JobDispatcher(
        settings=real,
        storage=storage,
        policy=policy,
        clock=clock,
        allow_real_research=True,
        research_real=diagnostic_research_real,
    )
    worker = Worker(
        storage=storage,
        policy=policy,
        dispatcher=dispatcher,
        lease_owner=f"article-research-e2e:{job_id}",
        target_job_id=job_id,
        lease_seconds=180,
        heartbeat_interval_seconds=30,
        heartbeat_startup_timeout_seconds=5,
        heartbeat_shutdown_timeout_seconds=5,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
    )
    try:
        storage.apply_security_flag_profile(
            OPEN_PROFILE_ORDER,
            updated_by=updated_by,
            reason=f"ARTICLE_RESEARCH E2E {job_id}",
            now=clock.now(),
        )
        result = worker.run_once()
        return result.status.value
    finally:
        restore_fail_closed(
            storage,
            reason=f"ARTICLE_RESEARCH E2E {job_id} restore",
            now=clock.now(),
        )


def _usage_total(storage: SqliteStorage, job_ids: list[str]) -> Decimal:
    if not job_ids:
        return Decimal("0")
    marks = ",".join("?" for _ in job_ids)
    row = storage.conn.execute(
        f"SELECT coalesce(sum(u.estimated_cost_usd),0) "
        f"FROM model_usage u JOIN runs r ON r.id=u.run_id "
        f"JOIN jobs j ON j.run_id=r.id WHERE j.id IN ({marks})",
        tuple(job_ids),
    ).fetchone()
    return Decimal(str(row[0]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--confirm-live", action="store_true")
    # Cumulative A1 + synthesis stop. A1 alone may now reserve up to 3.00, so a
    # 1.50 cumulative stop would abort a healthy run between its two paid calls.
    parser.add_argument("--max-cost-usd", type=Decimal, default=Decimal("3.000000"))
    parser.add_argument(
        "--topic-id",
        required=True,
        type=int,
        help="Use the exact SELECTED topic and queued A1 job produced by TOPIC_GENERATION.",
    )
    parser.add_argument(
        "--discovery-job-id",
        help="Exact queued A1 job for the selected topic; defaults to source-discovery-<topic_id>.",
    )
    parser.add_argument(
        "--evidence-job-id",
        help="Optional new synthesis job id reusing the already approved corpus.",
    )
    args = parser.parse_args(argv)
    if not args.confirm_live:
        print("BLOCKED: --confirm-live is required")
        return 2
    if args.max_cost_usd <= 0 or args.max_cost_usd > Decimal("4.000000"):
        print("BLOCKED: live cap must be in (0, 4.00]")
        return 2

    settings = load_settings()
    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()
    now = clock.now()
    branch, head = _git_identity(settings.project_root)
    job_ids: list[str] = []
    fetch_results: list[dict[str, object]] = []
    try:
        active = storage.get_active_model_for_role(LogicalModelRole.ARTICLE_RESEARCH)
        capability = None if active is None else storage._model_capability_for(active)
        if not (
            active is not None
            and active.provider == PROVIDER
            and active.technical_model_id == MODEL_ID
            and capability is not None
            and capability.max_context_tokens is not None
            and capability.max_context_tokens >= 32_000
            and capability.max_output_tokens is not None
            and capability.max_output_tokens >= 8_192
            and capability.source_discovery is True
        ):
            print("BLOCKED: ARTICLE_RESEARCH exact active capability is missing")
            return 2
        account = settings.get_account("nothing_is_accidental")
        storage.ensure_account(account)
        topic = next(
            (
                item
                for status in (TopicStatus.SELECTED, TopicStatus.USED)
                for item in storage.list_topics_by_status(account.id, status)
                if item.id == args.topic_id
            ),
            None,
        )
        discovery_job_id = args.discovery_job_id or f"source-discovery-{args.topic_id}"
        discovery_job = storage.get_job(discovery_job_id)
        if (
            topic is None
            or topic.account_id != account.id
            or topic.status not in (TopicStatus.SELECTED, TopicStatus.USED)
            or discovery_job is None
            or discovery_job.status not in (JobStatus.QUEUED, JobStatus.DONE)
            or discovery_job.topic_id != args.topic_id
            or discovery_job.payload.get("execution") != SOURCE_DISCOVERY_EXECUTION
        ):
            print("BLOCKED: selected topic/A1 job lineage is invalid")
            return 2
        foreign_active = storage.conn.execute(
            "SELECT count(*) FROM jobs WHERE status IN ('LEASED','RUNNING') "
            "AND id!=?",
            (discovery_job_id,),
        ).fetchone()[0]
        if foreign_active:
            print("BLOCKED: another active job exists")
            return 2
        job_ids.append(discovery_job.id)
        if discovery_job.status is JobStatus.QUEUED:
            discovery_approval = storage.record_source_discovery_approval(
                job_id=discovery_job.id,
                account_id=account.id,
                approved_by=args.approved_by,
                expires_at=now + timedelta(minutes=30),
                clock=clock,
            )
            discovery_status = _run_model_job(
                storage, settings, discovery_job.id, updated_by=args.approved_by,
            )
        else:
            approval_row = storage.conn.execute(
                "SELECT approval_ref FROM source_discovery_approvals WHERE job_id=?",
                (discovery_job.id,),
            ).fetchone()
            if approval_row is None:
                print("BLOCKED: terminal discovery job lacks its approval lineage")
                return 2
            discovery_approval = str(approval_row["approval_ref"])
            discovery_status = WorkerIterationStatus.DONE.value
        if discovery_status != WorkerIterationStatus.DONE.value:
            print(json.dumps({
                "status": "DISCOVERY_FAILED",
                "job_id": discovery_job.id,
                "approval_id": discovery_approval,
                "worker_status": discovery_status,
            }, sort_keys=True))
            return 3

        candidates = storage.conn.execute(
            "SELECT * FROM research_source_candidates WHERE discovery_job_id=? "
            "ORDER BY canonical_source_identity,id",
            (discovery_job.id,),
        ).fetchall()
        successes = int(storage.conn.execute(
            "SELECT count(DISTINCT fa.candidate_id) "
            "FROM source_candidate_fetch_approvals fa "
            "JOIN controlled_fetch_attempts a ON a.job_id=fa.fetch_job_id "
            "WHERE fa.account_id=? AND fa.topic_id=? AND a.status='SUCCEEDED'",
            (account.id, int(topic.id)),
        ).fetchone()[0])
        discovery_contract = SourceDiscoveryIntent.from_payload(
            discovery_job.payload["execution_intent"]
        )
        for candidate in candidates:
            if successes >= discovery_contract.max_results:
                break
            # The corpus packer enqueues the evidence-research job as soon as the
            # corpus is complete, and ux_jobs_active_research_topic permits only
            # ONE active RESEARCH job per (account, topic).  Approving a further
            # fetch after that point raises UNIQUE constraint failed, so stop:
            # the corpus already holds every source the synthesis will use.
            if int(storage.conn.execute(
                "SELECT count(*) FROM jobs WHERE account_id=? AND topic_id=? "
                "AND kind='RESEARCH' AND id<>? "
                "AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION')",
                (account.id, int(topic.id), discovery_job.id),
            ).fetchone()[0]):
                break
            existing_fetch = storage.conn.execute(
                "SELECT fetch_job_id FROM source_candidate_fetch_approvals "
                "WHERE candidate_id=?",
                (int(candidate["id"]),),
            ).fetchone()
            if existing_fetch is None:
                fetch_job_id = storage.approve_source_candidate_fetch(
                    candidate_id=int(candidate["id"]),
                    approved_by=args.approved_by,
                    expires_at=clock.now() + timedelta(minutes=30),
                    clock=clock,
                )
            else:
                fetch_job_id = str(existing_fetch["fetch_job_id"])
                existing_job = storage.get_job(fetch_job_id)
                if existing_job is None:
                    print("BLOCKED: fetch approval points to a missing job")
                    return 2
                if existing_job.status in (JobStatus.DONE, JobStatus.FAILED):
                    existing_attempt = storage.conn.execute(
                        "SELECT status,outcome_reason,retrieval_id FROM "
                        "controlled_fetch_attempts WHERE job_id=?",
                        (fetch_job_id,),
                    ).fetchone()
                    succeeded = (
                        existing_job.status is JobStatus.DONE
                        and existing_attempt is not None
                        and existing_attempt["status"] == "SUCCEEDED"
                    )
                    fetch_results.append({
                        "candidate_id": int(candidate["id"]),
                        "url": str(candidate["url"]),
                        "job_id": fetch_job_id,
                        "status": "SUCCEEDED" if succeeded else "FAILED",
                        "reason": (
                            None if existing_attempt is None
                            else existing_attempt["outcome_reason"]
                        ),
                        "retrieval_id": (
                            None if existing_attempt is None
                            else existing_attempt["retrieval_id"]
                        ),
                    })
                    successes += int(succeeded)
                    job_ids.append(fetch_job_id)
                    continue
                if existing_job.status is not JobStatus.QUEUED:
                    print("BLOCKED: existing fetch job is not resumable")
                    return 2
            job_ids.append(fetch_job_id)
            outcome = run_controlled_fetch_live_once(
                ControlledFetchLiveRequest(
                    job_id=fetch_job_id,
                    account_id=account.id,
                    expected_db_sha256=_checkpointed_sha256(
                        storage, settings.db_path
                    ),
                    expected_schema=RUNTIME_SCHEMA_VERSION,
                    expected_branch=branch,
                    expected_head=head,
                ),
                settings=settings,
                storage=storage,
                project_root=settings.project_root,
                clock=clock,
            )
            fetch_results.append({
                "candidate_id": int(candidate["id"]),
                "url": str(candidate["url"]),
                "job_id": fetch_job_id,
                "status": outcome.status,
                "reason": outcome.reason_code,
                "retrieval_id": outcome.retrieval_id,
            })
            if outcome.status == "SUCCEEDED":
                successes += 1
            elif outcome.status != "FAILED":
                print(json.dumps({
                    "status": "FETCH_NOT_TERMINAL",
                    "job_id": fetch_job_id,
                    "outcome": fetch_results[-1],
                }, sort_keys=True))
                return 3
            if _usage_total(storage, job_ids) > args.max_cost_usd:
                print("BLOCKED: cumulative E2E cost cap exceeded")
                return 3

        if successes < 3:
            print(json.dumps({
                "status": "INSUFFICIENT_COMPLETE_SOURCES",
                "topic_id": topic.id,
                "discovery_job_id": discovery_job.id,
                "fetches": fetch_results,
            }, sort_keys=True))
            return 3

        canonical_evidence_job_id = f"article-research-evidence-{int(topic.id)}"
        evidence_job_id = args.evidence_job_id or canonical_evidence_job_id
        evidence_job = storage.get_job(evidence_job_id)
        if evidence_job is None and args.evidence_job_id is not None:
            canonical_job = storage.get_job(canonical_evidence_job_id)
            if canonical_job is None or canonical_job.status is not JobStatus.DONE:
                print("FAILED: canonical evidence job is unavailable for synthesis reuse")
                return 3
            resynthesis_payload = dict(canonical_job.payload)
            execution_intent = dict(resynthesis_payload["execution_intent"])
            execution_intent["flags"] = {"force_re_research": True}
            DurableResearchExecutionIntent.from_payload(execution_intent)
            resynthesis_payload["execution_intent"] = execution_intent
            evidence_job = storage.enqueue_job(Job(
                id=evidence_job_id,
                account_id=canonical_job.account_id,
                kind=canonical_job.kind,
                workflow=canonical_job.workflow,
                idempotency_key=f"{canonical_job.idempotency_key}:resynthesis:{evidence_job_id}",
                topic_id=canonical_job.topic_id,
                payload=resynthesis_payload,
                schedule_reason="SAFETY_OPERATION_IMMEDIATE",
                earliest_run_at=clock.now(),
                max_attempts=1,
                created_at=clock.now(),
            ))
        if evidence_job is None:
            print("FAILED: corpus packer did not enqueue evidence research")
            return 3
        job_ids.append(evidence_job_id)
        evidence_approval = storage.record_evidence_research_approval(
            job_id=evidence_job_id,
            account_id=account.id,
            approved_by=args.approved_by,
            expires_at=clock.now() + timedelta(minutes=30),
            clock=clock,
        )
        evidence_status = _run_model_job(
            storage, settings, evidence_job_id, updated_by=args.approved_by,
        )
        final_job = storage.get_job(evidence_job_id)
        research_run = None
        card = None
        if final_job is not None and final_job.run_id:
            research_run = storage.get_research_run(final_job.run_id)
            if research_run is not None and research_run.research_card_id:
                card = storage.get_research_card(research_run.research_card_id)
        print(json.dumps({
            "status": "PASS" if evidence_status == "DONE" and card is not None else "FAIL",
            "operation": "ARTICLE_RESEARCH_E2E",
            "provider": PROVIDER,
            "model_id": MODEL_ID,
            "topic_id": topic.id,
            "topic": {
                "title": topic.title,
                "question": topic.question,
            },
            "source_discovery": {
                "job_id": discovery_job.id,
                "approval_id": discovery_approval,
                "run_id": storage.get_job(discovery_job.id).run_id,
                "candidate_count": len(candidates),
            },
            "fetches": fetch_results,
            "complete_sources": successes,
            "evidence_research": {
                "job_id": evidence_job_id,
                "approval_id": evidence_approval.id,
                "run_id": None if final_job is None else final_job.run_id,
                "worker_status": evidence_status,
                "research_status": None if research_run is None else research_run.status.value,
                "research_card_id": None if card is None else card.id,
                "recommendation": (
                    None if card is None else card.publication_recommendation.value
                ),
            },
            "job_ids": job_ids,
            "usage_cost_usd": format(_usage_total(storage, job_ids), ".6f"),
            "publication": False,
        }, sort_keys=True, default=str))
        return 0 if evidence_status == "DONE" and card is not None else 3
    finally:
        restore_fail_closed(
            storage,
            reason="ARTICLE_RESEARCH E2E final restore",
            now=clock.now(),
        )
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
