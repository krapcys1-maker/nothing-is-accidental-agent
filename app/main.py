"""CLI walking skeleton.

Uruchomienie:
    python -m app.main run-topics --count 6

Domyślnie działa w dry_run (klient zastępczy, brak realnego kosztu, zero akcji na Substacku).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from app.core.clock import Clock, SystemClock
from app.core.config import ConfigError, Settings, load_settings
from app.models import (
    ExecutionResolution,
    FinancialResolution,
    JobKind,
    OperationalFieldStatus,
    OperationalScalar,
    WorkflowType,
)
from app.ports.storage import (
    ProviderAttemptReconciliationError,
    ReconciliationPreviewStaleError,
)
from app.orchestrator.runner import DEFAULT_ACCOUNT, run_research, run_topics
from app.policies.policy_engine import PolicyEngine
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.maintenance import MaintenanceRunner
from app.scheduler.scheduling import SchedulingPolicy, SchedulingValidationError
from app.storage.db import SchemaVersionError, require_database_schema
from app.storage.repositories import SqliteStorage
from app.research.offline_evidence_intent import (
    OFFLINE_EVIDENCE_EXECUTION,
    OfflineEvidenceIntent,
    OfflineEvidenceIntentError,
)
from app.research.controlled_fetch_intent import (
    CONTROLLED_FETCH_EXECUTION,
    ControlledFetchIntent,
    ControlledFetchIntentError,
    SUPPORTED_FETCH_CONTENT_TYPES,
    canonicalize_controlled_fetch_payload,
)


def _configure_output() -> None:
    # Wymuś UTF-8 na wyjściu, by polskie znaki nie były zniekształcane w konsoli Windows.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _cmd_run_topics(args: argparse.Namespace) -> int:
    if args.real:
        print("STOP: run-topics is offline-only. Real provider calls are not available here.")
        return 2
    summary = run_topics(count=args.count, account_id=args.account, force_real=args.real)

    print("\n=== WALKING SKELETON — TOPIC RUN ===")
    print(f"konto:    {summary.account_id}")
    print(f"run_id:   {summary.run_id}")
    print(f"dry_run:  {summary.dry_run}")
    print(f"model:    {summary.model}")
    if summary.blocked:
        print(f"STATUS:   ZABLOKOWANY przez Policy Engine [{summary.block_code}]")
        print(f"powód:    {summary.block_reason}")
        return 2
    print(f"tematy:   {summary.total}  (SELECTED={summary.selected}, "
          f"SCORED={summary.scored}, REJECTED={summary.rejected}, "
          f"DUPLICATE={summary.duplicates})")
    print(f"koszt~:   {summary.cost_usd:.6f} USD "
          f"({'szacunek dry_run' if summary.dry_run else 'realny'})")
    print("-" * 60)
    for t in summary.topics:
        print(f"  [{t.status.value:8}] {t.score:6.2f}  {t.title}")
    print("=" * 60)
    return 0


def _cmd_run_research(args: argparse.Namespace) -> int:
    if args.real:
        print("STOP: run-research is offline-only. Use scripts/run_capped_research.py --real.")
        return 2
    summary = run_research(
        topic_id=args.topic_id, account_id=args.account, force_real=args.real,
        force_re_research=args.force_re_research,
    )

    print("\n=== RESEARCH PIPELINE ===")
    print(f"konto:    {summary.account_id}")
    print(f"temat:    #{summary.topic_id}")
    print(f"run_id:   {summary.run_id}")
    print(f"dry_run:  {summary.dry_run}")
    print(f"model:    {summary.model}")
    if summary.blocked:
        print(f"STATUS:   ZABLOKOWANY przez Policy Engine [{summary.block_code}]")
        print(f"powód:    {summary.block_reason}")
        return 2
    if summary.error:
        print(f"STATUS:   BŁĄD — {summary.error}")
        return 3
    print(f"koszt~:   {summary.cost_usd:.6f} USD "
          f"({'szacunek dry_run' if summary.dry_run else 'realny'})")
    print(f"injection flags: {summary.injection_flags}")
    card = summary.card
    print("-" * 60)
    print(f"REKOMENDACJA: {summary.recommendation}"
          + (f"  (powody: {', '.join(summary.reasons)})" if summary.reasons else ""))
    if card is not None:
        print(f"question:          {card.question}")
        print(f"working_thesis:    {card.working_thesis}")
        print(f"main_mechanism:    {card.main_mechanism}")
        print(f"confirmed_claims:  {card.confirmed_claims}")
        print(f"uncertain_claims:  {card.uncertain_claims}")
        print(f"contradictions:    {card.contradictions}")
        print(f"counterargument:   {card.strongest_counterargument}")
        print(f"citable_numbers:   {card.citable_numbers}")
        print(f"visual_idea:       {card.visual_idea}")
        print(f"confidence_score:  {card.confidence_score}")
        print(f"source_quality:    {card.source_quality_score}")
        print(f"sources ({len(card.sources)}):")
        for s in card.sources:
            print(f"   - [{s.source_type.value}] {s.title} — {s.url} "
                  f"(verif={s.verification_status.value})")
    print("=" * 60)
    return 0


def _parse_requested_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("musi być datą ISO-8601 z jawną strefą czasową.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("musi zawierać jawną strefę czasową.")
    return parsed.astimezone(timezone.utc)


def _cmd_enqueue_research(args: argparse.Namespace) -> int:
    """Creates exactly one scheduled RESEARCH dry-run job; never starts a worker."""
    settings = load_settings()
    try:
        policy = SchedulingPolicy.from_config(settings.editorial_schedule)
        account = settings.get_account(args.account_id)
    except (ConfigError, SchedulingValidationError) as exc:
        # Missing/invalid schedule configuration is deliberately fail-closed.
        print(f"ENQUEUE: failed closed: {exc}", file=sys.stderr)
        return 2

    storage = SqliteStorage.open(settings.db_path)
    try:
        storage.ensure_account(account)
        result = ScheduledJobEnqueuer(
            storage=storage, scheduling_policy=policy, clock=SystemClock(),
        ).enqueue(ScheduledJobRequest(
            id=f"enqueue-research-{uuid4()}",
            account_id=account.id,
            kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH,
            idempotency_key=f"enqueue-research:{account.id}:{args.topic_id}:{uuid4()}",
            topic_id=args.topic_id,
            payload={"account_id": account.id, "topic_id": args.topic_id, "dry_run": True},
            requested_at=args.requested_at,
            max_attempts=settings.worker_default_max_attempts,
        ))
        local = result.decision.earliest_run_at.astimezone(policy.timezone)
        print(f"ENQUEUE: job_id={result.job.id}")
        print(f"earliest_run_at_utc={result.decision.earliest_run_at.isoformat()}")
        print(f"earliest_run_at_local={local.isoformat()}")
        print(f"schedule_reason={result.decision.reason.value}")
        print("dry_run=true")
        return 0
    except (SchedulingValidationError, ValueError) as exc:
        print(f"ENQUEUE: failed closed: {exc}", file=sys.stderr)
        return 2
    finally:
        storage.close()


def _cmd_enqueue_offline_evidence(args: argparse.Namespace) -> int:
    """Freeze one local fixture into a durable, versioned E2-A job intent."""
    settings = load_settings()
    try:
        policy = SchedulingPolicy.from_config(settings.editorial_schedule)
        account = settings.get_account(args.account_id)
        raw = json.loads(args.fixture_path.read_text(encoding="utf-8"))
        intent = OfflineEvidenceIntent.from_payload(raw)
    except (
        ConfigError, SchedulingValidationError, OfflineEvidenceIntentError,
        OSError, json.JSONDecodeError,
    ) as exc:
        print(f"ENQUEUE OFFLINE EVIDENCE: failed closed: {exc}", file=sys.stderr)
        return 2

    storage = SqliteStorage.open(settings.db_path)
    try:
        storage.ensure_account(account)
        payload = {
            "account_id": account.id,
            "topic_id": args.topic_id,
            "dry_run": True,
            "execution": OFFLINE_EVIDENCE_EXECUTION,
            "execution_intent": raw,
        }
        result = ScheduledJobEnqueuer(
            storage=storage, scheduling_policy=policy, clock=SystemClock(),
        ).enqueue(ScheduledJobRequest(
            id=f"offline-evidence-{uuid4()}",
            account_id=account.id,
            kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH,
            idempotency_key=f"offline-evidence:{account.id}:{args.topic_id}:{uuid4()}",
            topic_id=args.topic_id,
            payload=payload,
            requested_at=args.requested_at,
            # Three explicit crash checkpoints are safely resumable because the
            # path has no provider/external-effect boundary.
            max_attempts=max(settings.worker_default_max_attempts, 4),
        ))
        print(f"ENQUEUE OFFLINE EVIDENCE: job_id={result.job.id}")
        print(f"earliest_run_at_utc={result.decision.earliest_run_at.isoformat()}")
        print(f"intent_version={intent.version}")
        print("execution=offline_evidence_v1")
        print("dry_run=true")
        return 0
    except (SchedulingValidationError, ValueError) as exc:
        print(f"ENQUEUE OFFLINE EVIDENCE: failed closed: {exc}", file=sys.stderr)
        return 2
    finally:
        storage.close()


def _cmd_enqueue_controlled_fetch(args: argparse.Namespace) -> int:
    """Freeze exactly one approved-source fetch into a durable versioned intent.

    Enqueue nie wykonuje żadnego pobrania i nie uruchamia workera; wykonanie
    wymaga jeszcze jednorazowej zgody L1 (`approve-controlled-fetch`) oraz
    autoryzowanego transportu (w E2-B realny transport pozostaje wyłączony).
    """
    from app.ports.controlled_fetch import validate_url_syntax

    settings = load_settings()
    try:
        policy = SchedulingPolicy.from_config(settings.editorial_schedule)
        account = settings.get_account(args.account_id)
        boundary = validate_url_syntax(args.url)
        if not boundary.allowed:
            raise ControlledFetchIntentError(
                f"URL rejected by the local boundary policy: {boundary.code}."
            )
        intent = ControlledFetchIntent.build(
            account_id=account.id,
            topic_id=args.topic_id,
            source_identity=args.source_identity,
            requested_url=args.url,
            timeout_seconds=args.timeout_seconds,
            max_bytes=args.max_bytes,
            max_redirects=args.max_redirects,
            allowed_content_types=list(SUPPORTED_FETCH_CONTENT_TYPES),
            requested_at=datetime.now(timezone.utc),
            expires_at=args.expires_at,
        )
    except (ConfigError, SchedulingValidationError, ControlledFetchIntentError) as exc:
        print(f"ENQUEUE CONTROLLED FETCH: failed closed: {exc}", file=sys.stderr)
        return 2

    storage = SqliteStorage.open(settings.db_path)
    try:
        storage.ensure_account(account)
        payload = {
            "account_id": account.id,
            "topic_id": args.topic_id,
            "dry_run": False,
            "execution": CONTROLLED_FETCH_EXECUTION,
            "execution_intent": intent.as_payload(),
        }
        canonicalize_controlled_fetch_payload(payload)
        result = ScheduledJobEnqueuer(
            storage=storage, scheduling_policy=policy, clock=SystemClock(),
        ).enqueue(ScheduledJobRequest(
            id=f"controlled-fetch-{uuid4()}",
            account_id=account.id,
            kind=JobKind.RESEARCH,
            workflow=WorkflowType.RESEARCH,
            idempotency_key=f"controlled-fetch:{account.id}:{args.topic_id}:{uuid4()}",
            topic_id=args.topic_id,
            payload=payload,
            requested_at=args.requested_at,
            max_attempts=settings.worker_default_max_attempts,
        ))
        print(f"ENQUEUE CONTROLLED FETCH: job_id={result.job.id}")
        print(f"earliest_run_at_utc={result.decision.earliest_run_at.isoformat()}")
        print(f"intent_version={intent.version}")
        print(f"intent_fingerprint={intent.fingerprint}")
        print(f"requested_url={intent.requested_url}")
        print(f"intent_expires_at={intent.expires_at}")
        print("execution=controlled_fetch_v1")
        print(
            "dry_run=false approval_required=true "
            "real_transport_globally_enabled="
            f"{str(settings.controlled_fetch_real_enabled).lower()}"
        )
        return 0
    except (SchedulingValidationError, ControlledFetchIntentError, ValueError) as exc:
        print(f"ENQUEUE CONTROLLED FETCH: failed closed: {exc}", file=sys.stderr)
        return 2
    finally:
        storage.close()


def _cmd_approve_controlled_fetch(args: argparse.Namespace) -> int:
    """Record the one-shot human L1 approval bound to one frozen fetch job."""
    from app.ports.storage import ControlledFetchAuthorizationError

    try:
        settings = load_settings()
        settings.get_account(args.account_id)
    except ConfigError as exc:
        print(f"APPROVE CONTROLLED FETCH: failed closed: {exc}", file=sys.stderr)
        return 2
    storage = SqliteStorage.open(settings.db_path)
    try:
        approval = storage.record_controlled_fetch_approval(
            job_id=args.job_id,
            account_id=args.account_id,
            approved_by=args.approved_by,
            expires_at=args.expires_at,
            clock=SystemClock(),
        )
        print(f"APPROVE CONTROLLED FETCH: approval_id={approval.id}")
        print(f"job_id={approval.job_id}")
        print(f"requested_url={approval.requested_url}")
        print(f"intent_fingerprint={approval.intent_fingerprint}")
        print(f"expires_at={approval.expires_at}")
        print("action_type=CONTROLLED_FETCH single_use=true transferable=false")
        return 0
    except ControlledFetchAuthorizationError as exc:
        print(f"APPROVE CONTROLLED FETCH: failed closed: {exc}", file=sys.stderr)
        return 2
    except (ValueError, sqlite3.Error) as exc:
        print(f"APPROVE CONTROLLED FETCH: failed closed: {exc}", file=sys.stderr)
        return 2
    finally:
        storage.close()


def _cmd_approve_evidence_research(args: argparse.Namespace) -> int:
    """Record the one-shot human L1 approval bound to one frozen evidence job.

    E3: to jest właściwa, trwała zgoda właściciela na dokładnie jeden realny
    evidence research — audytowalna w SQLite, z expiry, konsumowana atomowo
    dokładnie raz w tej samej transakcji co rezerwacja provider attemptu.
    """
    from app.ports.storage import EvidenceResearchAuthorizationError

    storage = None
    try:
        settings = load_settings()
        settings.get_account(args.account_id)
        storage = SqliteStorage.open(settings.db_path)
        approval = storage.record_evidence_research_approval(
            job_id=args.job_id,
            account_id=args.account_id,
            approved_by=args.approved_by,
            expires_at=args.expires_at,
            clock=SystemClock(),
        )
        print(f"APPROVE EVIDENCE RESEARCH: approval_id={approval.id}")
        print(f"job_id={approval.job_id}")
        print(f"topic_id={approval.topic_id}")
        print(f"intent_fingerprint={approval.intent_fingerprint}")
        print(f"expires_at={approval.expires_at}")
        print("action_type=EVIDENCE_RESEARCH single_use=true transferable=false")
        return 0
    except SchemaVersionError:
        # The runtime schema gate keeps its dedicated exit code (main -> 7).
        raise
    except (
        ConfigError, EvidenceResearchAuthorizationError,
        ValueError, RuntimeError, OSError, sqlite3.Error,
    ) as exc:
        # Every refusal path (config, protected/unavailable storage,
        # authorization) is one controlled fail-closed exit.
        print(f"APPROVE EVIDENCE RESEARCH: failed closed: {exc}", file=sys.stderr)
        return 2
    finally:
        if storage is not None:
            try:
                storage.close()
            except (OSError, RuntimeError, sqlite3.Error):
                pass


def _cmd_controlled_fetch_live_once(args: argparse.Namespace) -> int:
    """One-shot executor for exactly one approved CONTROLLED_FETCH job.

    Opens the minimal security profile process-locally (no YAML/.env/flag edits),
    executes ONLY the named job through the existing dispatcher and runner, and
    always restores fail-closed.  The durable single-use L1 approval remains the
    only authorization; this command creates neither a job nor an approval.
    """
    from app.operations.controlled_fetch_live import (
        ControlledFetchLiveRequest,
        run_controlled_fetch_live_once,
    )
    from app.operations.controlled_live import is_fail_closed

    settings = load_settings()
    fake_mode = (
        os.environ.get("NIA_TEST_MODE") == "1"
        and os.environ.get("NIA_CONTROLLED_FETCH_LIVE_FAKE") == "1"
    )
    if fake_mode:
        test_db = os.environ.get("NIA_CONTROLLED_FETCH_LIVE_TEST_DB_PATH")
        if not test_db:
            print(
                "CONTROLLED-FETCH-LIVE-ONCE: fake gate requires a temporary DB path.",
                file=sys.stderr,
            )
            return 2
        protected = (settings.project_root / "data" / "agent.db").resolve()
        if Path(test_db).resolve() == protected:
            print(
                "CONTROLLED-FETCH-LIVE-ONCE: fake gate refuses the production database.",
                file=sys.stderr,
            )
            return 2
        settings = replace(settings, db_path=Path(test_db))

    # Schema authorization precedes any storage or gate work.
    require_database_schema(settings.db_path)

    request = ControlledFetchLiveRequest(
        job_id=args.job_id,
        account_id=args.account_id,
        expected_db_sha256=args.expected_db_sha,
        expected_schema=args.expected_schema,
        expected_branch=args.expected_branch,
        expected_head=args.expected_head,
    )
    storage = SqliteStorage.open(settings.db_path)
    try:
        outcome = run_controlled_fetch_live_once(
            request,
            settings=settings,
            storage=storage,
            project_root=settings.project_root,
            clock=SystemClock(),
        )
    finally:
        storage.close()

    print(
        f"CONTROLLED-FETCH-LIVE-ONCE: {outcome.status} reason={outcome.reason_code}"
        + (
            f" retrieval_id={outcome.retrieval_id}"
            if outcome.retrieval_id is not None
            else ""
        )
    )
    print(json.dumps(
        {
            "status": outcome.status,
            "reason_code": outcome.reason_code,
            "retrieval_id": outcome.retrieval_id,
            "worker_status": outcome.worker_status,
            "flags_after": outcome.flags_after,
            "fail_closed": bool(outcome.flags_after) and is_fail_closed(outcome.flags_after),
        },
        ensure_ascii=False, sort_keys=True,
    ))
    return outcome.exit_code


def _build_worker(
    settings: Settings, offline_only: bool = False, *,
    clock: Clock | None = None,
    lease_owner: str | None = None,
) -> tuple[Worker, SqliteStorage]:
    """Composes the same runtime dependencies used by the application, once."""
    # Keep paid-provider imports out of the CLI module import graph.  In
    # particular the reconciliation commands must stay usable with no SDK or
    # worker/client composition at all.
    from app.scheduler.dispatcher import JobDispatcher
    from app.scheduler.worker import Worker

    settings = replace(settings, dry_run=True)
    storage = SqliteStorage.open(settings.db_path)
    clock = clock or SystemClock()
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = JobDispatcher(
        settings=settings, storage=storage, policy=policy, clock=clock,
        allow_real_research=not offline_only,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner=lease_owner or f"cli-worker-{uuid4()}", lease_seconds=60,
        heartbeat_interval_seconds=20.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
    ), storage


def _cmd_worker(args: argparse.Namespace) -> int:
    from app.scheduler.worker import WorkerIterationStatus

    settings = replace(load_settings(), dry_run=True)
    worker, storage = _build_worker(settings, args.offline_only)
    try:
        if args.once:
            result = worker.run_once()
            print(f"WORKER: {result.status.value}" + (f" job={result.job_id}" if result.job_id else ""))
            return 0 if result.status is not WorkerIterationStatus.BLOCKED else 2
        # `--poll-seconds` is required by the parser for this branch, so no CLI
        # invocation can accidentally become a continuous worker.
        worker.run_forever(poll_seconds=args.poll_seconds)
        return 0
    finally:
        storage.close()


def _positive_seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("musi być liczbą dodatnią.") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("musi być skończoną liczbą dodatnią.")
    return seconds


def _cmd_reap_runs(args: argparse.Namespace) -> int:
    """Runs one offline-only recovery plus stale-run reaper pass."""
    settings = load_settings()
    storage = SqliteStorage.open(settings.db_path)
    try:
        clock = SystemClock()
        now = clock.now()
        recovery = storage.release_or_requeue_expired_leases(clock=clock)
        result = storage.reap_orphaned_stale_runs(
            now - timedelta(seconds=args.stale_after_seconds), clock=clock,
        )
        print(
            "REAPER: "
            f"checked={result.checked_count} stopped={result.stopped_count} "
            f"recovered(requeued={recovery.requeued_count}, "
            f"needs_verification={recovery.needs_verification_count}, "
            f"failed={recovery.failed_count}, "
            f"escalated_reconciliations={recovery.escalated_reconciliation_count}, "
            f"settled_execution_recovered={recovery.settled_execution_recovery_count}, "
            f"settled_execution_blocked={recovery.settled_execution_blocked_count})"
        )
        return 0
    finally:
        storage.close()


def _cmd_maintain(args: argparse.Namespace) -> int:
    """Run explicit offline safety maintenance, once or in a controlled poll."""
    settings = load_settings()
    runner = MaintenanceRunner(
        storage_factory=lambda: SqliteStorage.open(settings.db_path),
        stale_after_seconds=args.stale_after_seconds,
        clock=SystemClock(),
    )
    try:
        if args.once:
            result = runner.run_once()
            print(
                "MAINTENANCE: "
                f"checked={result.reaper.checked_count} stopped={result.reaper.stopped_count} "
                f"recovered(requeued={result.recovery.requeued_count}, "
                f"needs_verification={result.recovery.needs_verification_count}, "
                f"failed={result.recovery.failed_count}, "
                f"escalated_reconciliations={result.recovery.escalated_reconciliation_count}, "
                f"settled_execution_recovered={result.recovery.settled_execution_recovery_count}, "
                f"settled_execution_blocked={result.recovery.settled_execution_blocked_count})"
            )
            return 0
        runner.run_forever(interval_seconds=args.interval_seconds)
        return 0
    except KeyboardInterrupt:
        print("MAINTENANCE: interrupted; polling stopped.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"MAINTENANCE: failed closed: {exc}", file=sys.stderr)
        return 1


_REPORT_EXIT_OK = 0
_REPORT_EXIT_DEGRADED = 2
_REPORT_EXIT_CONFIG = 3
_REPORT_EXIT_STORAGE = 6


def _operational_value(field: OperationalScalar) -> str:
    if field.status is OperationalFieldStatus.OK:
        return str(field.value)
    detail = f" ({field.detail})" if field.detail else ""
    return f"UNKNOWN/BLOCKED{detail}"


def _cmd_operational_report(args: argparse.Namespace) -> int:
    """Render a read-only snapshot; opening the database never runs migrations."""
    del args
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"OPERATIONAL REPORT: config error: {exc}", file=sys.stderr)
        return _REPORT_EXIT_CONFIG
    storage = None
    controlled_live_marker = None
    controlled_live_attempt_state = None
    try:
        storage = SqliteStorage.open_read_only(settings.db_path)
        report = storage.read_operational_report(clock=SystemClock())
        from app.operations.controlled_live import read_session_marker

        controlled_live_marker = read_session_marker(
            settings.project_root / "runtime"
        )
        if controlled_live_marker is not None:
            request_id = controlled_live_marker.get("expected_request_id")
            if isinstance(request_id, str) and request_id:
                row = storage.conn.execute(
                    "SELECT status,request_started_at,request_id FROM provider_attempts "
                    "WHERE request_id=?",
                    (request_id,),
                ).fetchone()
                if row is not None:
                    controlled_live_attempt_state = {
                        "status": str(row["status"]),
                        "request_id": str(row["request_id"]),
                        "provider_request_started": row["request_started_at"]
                        is not None,
                    }
        closing, storage = storage, None
        closing.close()
    except (OSError, RuntimeError, sqlite3.Error, ValueError) as exc:
        print(f"OPERATIONAL REPORT: storage error: {exc}", file=sys.stderr)
        return _REPORT_EXIT_STORAGE
    finally:
        if storage is not None:
            try:
                storage.close()
            except (OSError, RuntimeError, sqlite3.Error):
                pass

    print("OPERATIONAL REPORT — READ ONLY")
    print(f"schema_migrations={_operational_value(report.schema_migrations)}")
    if report.job_counts_status is OperationalFieldStatus.OK and report.job_counts is not None:
        for status, count in report.job_counts.items():
            print(f"jobs.{status}={count}")
    else:
        print("jobs=UNKNOWN/BLOCKED")
    print(f"active_leases={_operational_value(report.active_leases)}")
    print(
        "needs_verification_jobs="
        f"{_operational_value(report.needs_verification_jobs)}"
    )
    print(
        "needs_reconciliation_attempts="
        f"{_operational_value(report.needs_reconciliation_attempts)}"
    )
    print(f"active_reservations={_operational_value(report.active_reservations)}")
    print(
        "active_reserved_cost_usd="
        f"{_operational_value(report.active_reserved_cost_usd)}"
    )
    for key, flag in report.system_flags.items():
        if flag.status is OperationalFieldStatus.OK:
            rendered = str(flag.value).lower()
        else:
            rendered = (
                "UNKNOWN/BLOCKED "
                f"(effective_fail_closed={str(flag.effective_fail_closed_value).lower()})"
            )
        print(f"system_flag.{key}={rendered}")
    print(f"last_maintenance_at={_operational_value(report.last_maintenance_at)}")
    # LA-01-B: surface an unclosed controlled-live session (read-only filesystem
    # marker).  The read-only report never forces flags; it makes the operator and
    # the entrypoint aware that fail-closed must be forced before any provider work.
    controlled_live_recovery = False
    if controlled_live_marker is not None:
        controlled_live_recovery = True
        print(
            "controlled_live_session=RECOVERY_REQUIRED "
            f"(session={controlled_live_marker.get('session_id')}, "
            f"status={controlled_live_marker.get('status')})"
        )
        if controlled_live_attempt_state is not None:
            print(
                "controlled_live_provider_attempt="
                f"{controlled_live_attempt_state['status']} "
                "provider_request_started="
                f"{str(controlled_live_attempt_state['provider_request_started']).lower()}"
            )
        else:
            print("controlled_live_provider_attempt=none_or_unknown")
    else:
        print("controlled_live_session=none")
    if report.unknown_reasons:
        for reason in report.unknown_reasons:
            print(f"unknown_reason={reason}")
        print("REPORT_STATUS=DEGRADED_UNKNOWN")
        return _REPORT_EXIT_DEGRADED
    if controlled_live_recovery:
        print("REPORT_STATUS=DEGRADED_CONTROLLED_LIVE_RECOVERY")
        return _REPORT_EXIT_DEGRADED
    print("REPORT_STATUS=OK")
    return _REPORT_EXIT_OK


def _cmd_controlled_live_once(args: argparse.Namespace) -> int:
    """Canonical composition root for one fenced controlled-live session."""
    from app.operations.controlled_live import (
        CanonicalControlledWorkerAdapter,
        ControlledLiveRequest,
        DbFingerprint,
        DeterministicFakeControlledWorkerAdapter,
        REAL_CONTROLLED_LIVE_EMERGENCY_STOP,
        evidence_research_execution_authorized,
        run_controlled_live_once,
        run_controlled_live_quiescence_check,
    )
    from app.research.durable_intent import controlled_research_job_id

    settings = load_settings()
    fake_mode = (
        os.environ.get("NIA_TEST_MODE") == "1"
        and os.environ.get("NIA_CONTROLLED_LIVE_FAKE") == "1"
    )
    runtime_dir = settings.project_root / "runtime"
    if fake_mode:
        test_db = os.environ.get("NIA_CONTROLLED_LIVE_TEST_DB_PATH")
        test_runtime = os.environ.get("NIA_CONTROLLED_LIVE_TEST_RUNTIME_DIR")
        if not test_db or not test_runtime:
            print(
                "CONTROLLED-LIVE-ONCE: fake gate requires temporary DB and runtime paths.",
                file=sys.stderr,
            )
            return 2
        protected = (settings.project_root / "data" / "agent.db").resolve()
        if Path(test_db).resolve() == protected:
            print(
                "CONTROLLED-LIVE-ONCE: fake gate refuses the production database.",
                file=sys.stderr,
            )
            return 2
        settings = replace(
            settings,
            db_path=Path(test_db),
            model_quality=args.model,
            dry_run=False,
        )
        runtime_dir = Path(test_runtime)

    # Schema authorization precedes quiescence, marker/report work, flags,
    # worker composition and any provider-capable path.
    require_database_schema(settings.db_path)

    request = ControlledLiveRequest(
        account_id=args.account,
        topic_id=args.topic_id,
        operation_key=args.operation_key,
        model=args.model,
        pricing_profile_id=args.pricing_profile,
        max_tokens=args.max_tokens,
        max_web_searches=args.max_web_searches,
        max_cost_usd=args.max_cost_usd,
        expected_db_sha256=args.expected_db_sha,
        expected_schema=args.expected_schema,
        expected_branch=args.expected_branch,
        expected_head=args.expected_head,
        max_attempts=args.max_attempts,
        max_retries=args.max_retries,
    )
    if fake_mode:
        def fake_pre_storage_probe(_project_root: Path, _db_path: Path):
            return {
                "project_process_ids": (),
                "scheduled_tasks": (),
                "locked_paths": (),
            }

        pre_storage_kwargs = {"quiescence_probe": fake_pre_storage_probe}
    else:
        pre_storage_kwargs = {}

    # LA-03: the zero-sharing DB/WAL/SHM probe must run before the main
    # SqliteStorage connection exists.  The payload is then frozen and reused by
    # the durable wrapper; probing again after open would deterministically
    # classify our own connection as a foreign handle.
    pre_storage_exit, pre_storage = run_controlled_live_quiescence_check(
        project_root=settings.project_root,
        db_path=settings.db_path,
        **pre_storage_kwargs,
    )
    if pre_storage_exit != 0:
        print(
            "CONTROLLED-LIVE-ONCE: PREFLIGHT_FAILED "
            f"reason={pre_storage.get('reason_code', 'QUIESCENCE_CHECK_FAILED')}"
        )
        print(json.dumps(pre_storage, ensure_ascii=False, sort_keys=True))
        return pre_storage_exit

    database_after = pre_storage.get("database_after")
    database_record = (
        database_after.get("database")
        if isinstance(database_after, dict)
        else None
    )
    observed_pre_storage_sha = (
        database_record.get("sha256")
        if isinstance(database_record, dict)
        else None
    )
    if (
        not isinstance(observed_pre_storage_sha, str)
        or observed_pre_storage_sha.upper() != args.expected_db_sha.upper()
    ):
        print("CONTROLLED-LIVE-ONCE: PREFLIGHT_FAILED reason=DB_SHA_MISMATCH")
        return 2

    frozen_quiescence = {
        "project_process_ids": pre_storage.get("project_process_ids", ()),
        "scheduled_tasks": pre_storage.get("scheduled_tasks", ()),
        "locked_paths": pre_storage.get("locked_paths", ()),
        "probe_current_pid": pre_storage.get("probe_current_pid"),
        "probe_parent_pid": pre_storage.get("probe_parent_pid"),
        "probe_ancestry_process_ids": pre_storage.get(
            "probe_ancestry_process_ids", ()
        ),
        "probe_helper_process_ids": pre_storage.get(
            "probe_helper_process_ids", ()
        ),
        "process_diagnostics": pre_storage.get("process_diagnostics", ()),
    }

    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()
    policy = PolicyEngine(settings, storage, clock)

    if fake_mode:
        worker_adapter = DeterministicFakeControlledWorkerAdapter(
            storage=storage,
            settings=settings,
            clock=clock,
        )
        # The fake CLI may create its temp-only job during durable preflight, so
        # its injected fingerprint remains stable by construction.  Real mode
        # always uses the physical post-open fingerprint below.
        database_fingerprint = lambda _path: DbFingerprint(
            sha256=args.expected_db_sha,
            size=Path(settings.db_path).stat().st_size,
            schema_tail=args.expected_schema,
        )
    else:
        from app.scheduler.dispatcher import JobDispatcher
        from app.scheduler.worker import Worker

        dispatcher = JobDispatcher(
            settings=settings,
            storage=storage,
            policy=policy,
            clock=clock,
            allow_real_research=True,
        )

        def worker_factory(lease_owner: str):
            return Worker(
                storage=storage,
                policy=policy,
                dispatcher=dispatcher,
                lease_owner=lease_owner,
                lease_seconds=60,
                heartbeat_interval_seconds=20.0,
                heartbeat_startup_timeout_seconds=5.0,
                heartbeat_shutdown_timeout_seconds=5.0,
                heartbeat_storage_factory=lambda: SqliteStorage.open(
                    settings.db_path
                ),
                clock=clock,
            )

        worker_adapter = CanonicalControlledWorkerAdapter(
            storage=storage,
            worker_factory=worker_factory,
        )
        database_fingerprint = None

    # E3: właściwą zgodą właściciela na realne wykonanie jest trwały,
    # jednorazowy, audytowalny approval L1 EVIDENCE_RESEARCH w SQLite —
    # nigdy edycja źródeł. Stała emergency-stop pozostaje wyłącznie awaryjną
    # blokadą bezpieczeństwa ponad zgodą.
    if fake_mode:
        real_execution_authorized = False
    else:
        real_execution_authorized = (
            not REAL_CONTROLLED_LIVE_EMERGENCY_STOP
            and evidence_research_execution_authorized(
                storage,
                controlled_research_job_id(args.operation_key),
                now=clock.now(),
            )
        )

    try:
        kwargs = {}
        if database_fingerprint is not None:
            kwargs["db_fingerprint"] = database_fingerprint
        outcome = run_controlled_live_once(
            request,
            settings=settings,
            storage=storage,
            storage_reopener=lambda: SqliteStorage.open(settings.db_path),
            project_root=settings.project_root,
            runtime_dir=runtime_dir,
            worker_runner=worker_adapter,
            frozen_quiescence=frozen_quiescence,
            clock=clock,
            allow_execution=fake_mode or real_execution_authorized,
            allow_job_creation=fake_mode,
            **kwargs,
        )
    finally:
        try:
            storage.close()
        except (OSError, RuntimeError, sqlite3.Error):
            pass
    print(
        f"CONTROLLED-LIVE-ONCE: {outcome.status} "
        f"session={outcome.session_id}"
    )
    if outcome.report_path is not None:
        print(f"operator_report={outcome.report_path}")
    if outcome.detail:
        print(outcome.detail)
    return outcome.exit_code


def _cmd_controlled_live_quiescence_check(args: argparse.Namespace) -> int:
    """Read-only canonical process/task/handle check; never opens storage."""
    from app.operations.controlled_live import run_controlled_live_quiescence_check

    settings = load_settings()
    db_path = Path(args.db_path).resolve() if args.db_path else settings.db_path
    try:
        exit_code, payload = run_controlled_live_quiescence_check(
            project_root=settings.project_root,
            db_path=db_path,
        )
    except BaseException as exc:
        # The CLI remains fail-closed even if the DB cannot be fingerprinted.
        payload = {
            "status": "STOP",
            "reason_code": "QUIESCENCE_CHECK_FAILED",
            "error_class": type(exc).__name__,
            "provider_constructed": False,
            "provider_request_started": False,
            "storage_opened": False,
            "session_marker_created": False,
        }
        exit_code = 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print(f"CONTROLLED-LIVE-QUIESCENCE: {payload['status']}")
    return exit_code


def _cmd_list_reconciliations(args: argparse.Namespace) -> int:
    """Local read-only L1 queue; it has no provider or worker composition root.

    Every stage — configuration, storage open, the queue query, result
    formatting and the storage close — maps onto the same controlled exit
    codes as ``reconcile-attempt`` (config -> 3, storage/OS -> 6); no stage may
    escape as an uncontrolled traceback.
    """
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"RECONCILIATION: config error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_CONFIG
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"RECONCILIATION: storage error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_STORAGE
    storage = None
    try:
        storage = SqliteStorage.open_read_only(settings.db_path)
        attempts = storage.list_provider_attempts_needing_reconciliation(account_id=args.account_id)
        for attempt in attempts:
            print(
                f"request_id={attempt.request_id} status={attempt.status.value} "
                f"reserved_amount_usd={attempt.reserved_amount_usd:.6f} stage={attempt.stage}"
            )
        print(f"RECONCILIATIONS: {len(attempts)}")
        closing, storage = storage, None
        closing.close()
        return 0
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"RECONCILIATION: storage error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_STORAGE
    finally:
        if storage is not None:
            try:
                storage.close()
            except (OSError, RuntimeError, sqlite3.Error):
                # Best-effort close on an error path: the primary controlled
                # exit code above already reports the failure.
                pass


# reconcile-attempt controlled exit codes (deterministic; documented contract):
#   0  preview shown / confirmed / idempotent no-op / observation recorded
#   2  reconciliation rejected (wrong account or database, missing request,
#      invalid combination, already-reconciled-conflicting, ledger/card/relation)
#   3  configuration error
#   4  invalid CLI input (cost NaN/Infinity/format, or missing version token)
#   5  stale preview token
#   6  storage / OS error
_RECONCILE_EXIT_OK = 0
_RECONCILE_EXIT_REJECTED = 2
_RECONCILE_EXIT_CONFIG = 3
_RECONCILE_EXIT_INPUT = 4
_RECONCILE_EXIT_STALE = 5
_RECONCILE_EXIT_STORAGE = 6


def _cli_cost_is_finite(raw: str) -> bool:
    """Reject NaN/Infinity/non-decimal before the durable money contract runs."""
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError, TypeError):
        return False
    return parsed.is_finite()


def _cmd_reconcile_attempt(args: argparse.Namespace) -> int:
    """Manual resolver: read-only preview by default; one atomic write with --confirm."""
    financial = FinancialResolution(args.financial_resolution)
    execution = ExecutionResolution(args.execution_resolution)
    if args.actual_cost_usd is not None and not _cli_cost_is_finite(args.actual_cost_usd):
        print("RECONCILIATION: invalid --actual-cost-usd (must be a finite decimal).", file=sys.stderr)
        return _RECONCILE_EXIT_INPUT
    try:
        settings = load_settings()
        storage = SqliteStorage.open(settings.db_path)
    except ConfigError as exc:
        print(f"RECONCILIATION: config error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_CONFIG
    except (OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"RECONCILIATION: storage error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_STORAGE
    try:
        if not args.confirm:
            preview = storage.preview_provider_attempt_reconciliation(
                request_id=args.request_id, account_id=args.account_id,
            )
            print("RECONCILIATION PREVIEW")
            print(f"request_id={preview.request_id}")
            print(f"account_id={preview.account_id}")
            print(f"attempt_status={preview.attempt_status.value}")
            print(f"job_status={preview.job_status}")
            print(f"run_status={preview.run_status}")
            print(f"research_run_status={preview.research_run_status}")
            print(f"usage_count={preview.usage_count} canonical_cost_usd={preview.canonical_cost_usd}")
            print(
                f"reserved_amount_usd={preview.reserved_amount_usd:.6f} "
                f"reservation_active={str(preview.reservation_active).lower()}"
            )
            print(f"research_card_id={preview.research_card_id}")
            print(f"event_count={preview.event_count}")
            print(f"proposed_financial_resolution={financial.value}")
            print(f"proposed_execution_resolution={execution.value}")
            print(
                "proposed_actual_cost_usd="
                f"{args.actual_cost_usd if args.actual_cost_usd is not None else '<none>'}"
            )
            print("provider_call=false enqueue=false retry=false attempt_2=false")
            print(f"version_token={preview.version_token}")
            print("PREVIEW ONLY: pass --confirm and --version-token from this preview to execute.")
            return _RECONCILE_EXIT_OK
        if not args.version_token or not args.version_token.strip():
            print("RECONCILIATION: --confirm requires --version-token from a fresh preview.", file=sys.stderr)
            return _RECONCILE_EXIT_INPUT
        result = storage.resolve_provider_attempt_reconciliation(
            request_id=args.request_id,
            account_id=args.account_id,
            financial_resolution=financial,
            execution_resolution=execution,
            actual_cost_usd=args.actual_cost_usd,
            reconciled_by=args.reconciled_by,
            note=args.note,
            expected_version_token=args.version_token,
        )
        if result.observed:
            seq = result.event.sequence_number if result.event is not None else 0
            print(
                "OBSERVED — STILL NEEDS_RECONCILIATION: "
                f"attempt_status={result.attempt.status.value} event_seq={seq} "
                f"idempotent={str(result.idempotent).lower()}"
            )
            return _RECONCILE_EXIT_OK
        print(
            f"RECONCILED: status={result.attempt.status.value} usage_id={result.usage_id} "
            f"idempotent={str(result.idempotent).lower()}"
        )
        return _RECONCILE_EXIT_OK
    except ReconciliationPreviewStaleError as exc:
        print(f"RECONCILIATION: stale preview: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_STALE
    except ProviderAttemptReconciliationError as exc:
        print(f"RECONCILIATION: failed closed: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_REJECTED
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(f"RECONCILIATION: storage error: {exc}", file=sys.stderr)
        return _RECONCILE_EXIT_STORAGE
    finally:
        try:
            storage.close()
        except (OSError, RuntimeError, sqlite3.Error):
            # The command outcome was already decided (and any confirm already
            # committed); a close failure must not become an uncontrolled crash.
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.main", description="Nothing Is Accidental agent (MVP).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_topics = sub.add_parser("run-topics", help="Wygeneruj i oceń tematy (dry_run).")
    p_topics.add_argument("--count", type=int, default=6, help="Liczba tematów (domyślnie 6).")
    p_topics.add_argument("--account", default=DEFAULT_ACCOUNT, help="ID konta.")
    p_topics.add_argument("--real", action="store_true",
                          help="Wymuś realne wywołanie Anthropic (poza dry_run). Wydaje budżet.")
    p_topics.set_defaults(func=_cmd_run_topics)

    p_research = sub.add_parser("run-research", help="Research dla wybranego tematu SELECTED (dry_run).")
    p_research.add_argument("--topic-id", type=int, default=None,
                            help="ID tematu; domyślnie najlepszy SELECTED.")
    p_research.add_argument("--account", default=DEFAULT_ACCOUNT, help="ID konta.")
    p_research.add_argument("--real", action="store_true",
                            help="ZABLOKOWANE (P0-3, docs/archive/superseded_plans/AUDYT_ARCHITEKTURY_2026-07-12.md) — "
                                 "ta ścieżka nie ma capu ani limitu web searchy. Do realnego "
                                  "researchu użyj scripts/run_capped_research.py.")
    p_research.add_argument("--force-re-research", action="store_true",
                            help="Jawnie zezwól na nowy research tematu z kompletną kartą. "
                                 "Może uruchomić kosztowny research; nie omija innych bramek.")
    p_research.set_defaults(func=_cmd_run_research)

    p_enqueue_research = sub.add_parser(
        "enqueue-research", help="Dodaj wyłącznie zaplanowany job RESEARCH dry-run bez uruchamiania workera.",
    )
    p_enqueue_research.add_argument("--account-id", required=True, help="ID aktywnego konta.")
    p_enqueue_research.add_argument("--topic-id", required=True, type=int, help="ID tematu dla dry-run.")
    p_enqueue_research.add_argument(
        "--requested-at", type=_parse_requested_at,
        help="Opcjonalny ISO-8601 z jawną strefą czasową; polityka odroczy czas poza oknem.",
    )
    p_enqueue_research.add_argument(
        "--show-schedule", action="store_true",
        help="Akceptowane dla jawności; harmonogram jest zawsze wypisywany.",
    )
    p_enqueue_research.set_defaults(func=_cmd_enqueue_research)

    p_enqueue_evidence = sub.add_parser(
        "enqueue-offline-evidence-research",
        help="Dodaj wersjonowany, zero-cost job E2-A z lokalnego fixture JSON.",
    )
    p_enqueue_evidence.add_argument("--account-id", required=True)
    p_enqueue_evidence.add_argument("--topic-id", required=True, type=int)
    p_enqueue_evidence.add_argument("--fixture-path", required=True, type=Path)
    p_enqueue_evidence.add_argument("--requested-at", type=_parse_requested_at)
    p_enqueue_evidence.set_defaults(func=_cmd_enqueue_offline_evidence)

    p_enqueue_fetch = sub.add_parser(
        "enqueue-controlled-fetch",
        help="E2-B: zamroź trwały intent jednego kontrolowanego pobrania "
             "(bez wykonania; wymaga późniejszej zgody L1).",
    )
    p_enqueue_fetch.add_argument("--account-id", required=True)
    p_enqueue_fetch.add_argument("--topic-id", required=True, type=int)
    p_enqueue_fetch.add_argument("--url", required=True,
                                 help="Dokładny jawny URL http/https jednego dokumentu.")
    p_enqueue_fetch.add_argument("--source-identity", required=True,
                                 help="Stabilna tożsamość źródła (np. slug dokumentu).")
    p_enqueue_fetch.add_argument("--timeout-seconds", required=True, type=int)
    p_enqueue_fetch.add_argument("--max-bytes", required=True, type=int)
    p_enqueue_fetch.add_argument("--max-redirects", required=True, type=int)
    p_enqueue_fetch.add_argument("--expires-at", required=True, type=_parse_requested_at,
                                 help="ISO-8601 z jawną strefą; po tym czasie intent wygasa.")
    p_enqueue_fetch.add_argument("--requested-at", type=_parse_requested_at)
    p_enqueue_fetch.set_defaults(func=_cmd_enqueue_controlled_fetch)

    p_approve_fetch = sub.add_parser(
        "approve-controlled-fetch",
        help="E2-B: jednorazowa zgoda L1 dla dokładnie jednego joba controlled fetch.",
    )
    p_approve_fetch.add_argument("--job-id", required=True)
    p_approve_fetch.add_argument("--account-id", required=True)
    p_approve_fetch.add_argument("--approved-by", required=True,
                                 help="Tożsamość człowieka L1 podejmującego decyzję.")
    p_approve_fetch.add_argument("--expires-at", required=True, type=_parse_requested_at,
                                 help="ISO-8601 z jawną strefą; zgoda wygasa najpóźniej wtedy.")
    p_approve_fetch.set_defaults(func=_cmd_approve_controlled_fetch)

    p_approve_evidence = sub.add_parser(
        "approve-evidence-research",
        help="E3: jednorazowa zgoda L1 dla dokładnie jednego joba evidence research.",
    )
    p_approve_evidence.add_argument("--job-id", required=True)
    p_approve_evidence.add_argument("--account-id", required=True)
    p_approve_evidence.add_argument("--approved-by", required=True,
                                    help="Tożsamość człowieka L1 podejmującego decyzję.")
    p_approve_evidence.add_argument("--expires-at", required=True, type=_parse_requested_at,
                                    help="ISO-8601 z jawną strefą; zgoda wygasa najpóźniej wtedy.")
    p_approve_evidence.set_defaults(func=_cmd_approve_evidence_research)

    p_worker = sub.add_parser("worker", help="Wykonaj bezpieczny, trwały job offline.")
    worker_mode = p_worker.add_mutually_exclusive_group(required=True)
    worker_mode.add_argument("--once", action="store_true", help="Podejmij najwyżej jeden job.")
    worker_mode.add_argument(
        "--poll-seconds", type=float,
        help="Uruchom kontrolowaną pętlę z podanym interwałem (> 0).",
    )
    p_worker.add_argument(
        "--offline-only", action="store_true",
        help="Zablokuj durable paid research niezależnie od runtime flags; wymagane przez system scheduler.",
    )
    p_worker.set_defaults(func=_cmd_worker)

    p_reaper = sub.add_parser("reap-runs", help="Jednorazowo odzyskaj joby i zatrzymaj osierocone runy offline.")
    p_reaper.add_argument("--once", action="store_true", required=True,
                          help="Jawnie wykonaj dokładnie jeden przebieg reapera.")
    p_reaper.add_argument("--stale-after-seconds", type=_positive_seconds, required=True,
                          help="Jawny dodatni próg wieku RUNNING runu.")
    p_reaper.set_defaults(func=_cmd_reap_runs)

    p_maintain = sub.add_parser(
        "maintain",
        help="Offline maintenance: recovery wygasłych lease, potem stale-run reaper.",
    )
    maintenance_mode = p_maintain.add_mutually_exclusive_group(required=True)
    maintenance_mode.add_argument("--once", action="store_true",
                                  help="Wykonaj dokładnie jeden przebieg maintenance.")
    maintenance_mode.add_argument("--poll", action="store_true",
                                  help="Uruchom sekwencyjną pętlę maintenance.")
    p_maintain.add_argument("--interval-seconds", type=_positive_seconds,
                            help="Wymagany dodatni interwał tylko dla --poll.")
    p_maintain.add_argument("--stale-after-seconds", type=_positive_seconds, required=True,
                            help="Jawny dodatni próg wieku RUNNING runu.")
    p_maintain.set_defaults(func=_cmd_maintain)

    p_list_reconciliations = sub.add_parser(
        "list-reconciliations", help="Read-only list of durable provider attempts awaiting an L1 operator.",
    )
    p_list_reconciliations.add_argument("--account-id", help="Optional account isolation filter.")
    p_list_reconciliations.set_defaults(func=_cmd_list_reconciliations)

    p_operational_report = sub.add_parser(
        "operational-report",
        help="Read-only Stage 1 status report; never migrates, claims, dispatches or loads an SDK.",
    )
    p_operational_report.set_defaults(func=_cmd_operational_report)

    p_controlled_live = sub.add_parser(
        "controlled-live-once",
        help="LA-01 candidate: canonical operator wrapper for exactly one controlled live "
             "acceptance. Real execution is not yet authorized (fail-closed).",
    )
    p_controlled_live.add_argument("--account", default=DEFAULT_ACCOUNT)
    p_controlled_live.add_argument("--topic-id", type=int, required=True)
    p_controlled_live.add_argument("--operation-key", required=True)
    p_controlled_live.add_argument("--model", required=True)
    p_controlled_live.add_argument("--pricing-profile", required=True)
    p_controlled_live.add_argument("--max-tokens", type=int, required=True)
    p_controlled_live.add_argument("--max-web-searches", type=int, default=4)
    p_controlled_live.add_argument("--max-cost-usd", required=True)
    p_controlled_live.add_argument("--expected-db-sha", required=True)
    p_controlled_live.add_argument("--expected-schema", required=True)
    p_controlled_live.add_argument("--expected-branch", required=True)
    p_controlled_live.add_argument("--expected-head", required=True)
    p_controlled_live.add_argument("--max-attempts", type=int, default=1)
    p_controlled_live.add_argument("--max-retries", type=int, default=0)
    p_controlled_live.set_defaults(func=_cmd_controlled_live_once)

    p_fetch_live = sub.add_parser(
        "controlled-fetch-live-once",
        help="Execute exactly one approved CONTROLLED_FETCH job: opens the minimal "
             "security profile process-locally and always restores fail-closed. "
             "URL/timeout/limits come only from the frozen job intent.",
    )
    p_fetch_live.add_argument("--job-id", required=True)
    p_fetch_live.add_argument("--account-id", required=True)
    p_fetch_live.add_argument("--expected-db-sha", required=True)
    p_fetch_live.add_argument("--expected-schema", required=True)
    p_fetch_live.add_argument("--expected-branch", required=True)
    p_fetch_live.add_argument("--expected-head", required=True)
    p_fetch_live.set_defaults(func=_cmd_controlled_fetch_live_once)

    p_quiescence_check = sub.add_parser(
        "controlled-live-quiescence-check",
        help="Read-only LA-02 check using the canonical controlled-live quiescence probe.",
    )
    p_quiescence_check.add_argument(
        "--db-path",
        help="Optional DB path; defaults to the configured database and is never opened as SQLite.",
    )
    p_quiescence_check.set_defaults(func=_cmd_controlled_live_quiescence_check)

    p_reconcile = sub.add_parser(
        "reconcile-attempt", help="Resolve one persisted NEEDS_RECONCILIATION attempt without a provider call.",
    )
    p_reconcile.add_argument("--request-id", required=True)
    p_reconcile.add_argument("--account-id", required=True)
    p_reconcile.add_argument("--financial-resolution", required=True,
                             choices=[item.value for item in FinancialResolution],
                             type=lambda value: value.upper().replace("-", "_"))
    p_reconcile.add_argument("--execution-resolution", required=True,
                             choices=[item.value for item in ExecutionResolution],
                             type=lambda value: value.upper().replace("-", "_"))
    p_reconcile.add_argument("--actual-cost-usd", type=str)
    p_reconcile.add_argument("--reconciled-by", required=True)
    p_reconcile.add_argument("--note", required=True)
    p_reconcile.add_argument("--confirm", action="store_true")
    p_reconcile.add_argument(
        "--version-token",
        help="State fingerprint from a fresh preview; required with --confirm and rejected if stale.",
    )
    p_reconcile.set_defaults(func=_cmd_reconcile_attempt)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "maintain" and args.poll and args.interval_seconds is None:
        parser.error("maintain --poll wymaga --interval-seconds.")
    if args.command == "maintain" and args.once and args.interval_seconds is not None:
        parser.error("maintain --once nie przyjmuje --interval-seconds.")
    try:
        return args.func(args)
    except SchemaVersionError as exc:
        print(f"SCHEMA GATE: failed closed: {exc}", file=sys.stderr)
        return 7


if __name__ == "__main__":
    sys.exit(main())
