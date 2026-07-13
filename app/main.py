"""CLI walking skeleton.

Uruchomienie:
    python -m app.main run-topics --count 6

Domyślnie działa w dry_run (klient zastępczy, brak realnego kosztu, zero akcji na Substacku).
"""
from __future__ import annotations

import argparse
import logging
import math
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.clock import SystemClock
from app.core.config import ConfigError, Settings, load_settings
from app.models import JobKind, WorkflowType
from app.orchestrator.runner import DEFAULT_ACCOUNT, run_research, run_topics
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
from app.scheduler.enqueue import ScheduledJobEnqueuer, ScheduledJobRequest
from app.scheduler.maintenance import MaintenanceRunner
from app.scheduler.scheduling import SchedulingPolicy, SchedulingValidationError
from app.scheduler.worker import Worker, WorkerIterationStatus
from app.storage.repositories import SqliteStorage


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


def _build_worker(settings: Settings) -> tuple[Worker, SqliteStorage]:
    """Composes the same runtime dependencies used by the application, once."""
    storage = SqliteStorage.open(settings.db_path)
    clock = SystemClock()
    policy = PolicyEngine(settings, storage, clock)
    dispatcher = JobDispatcher(
        settings=settings, storage=storage, policy=policy, clock=clock,
    )
    return Worker(
        storage=storage, policy=policy, dispatcher=dispatcher,
        lease_owner=f"cli-worker-{uuid4()}", lease_seconds=60,
        heartbeat_interval_seconds=20.0,
        heartbeat_startup_timeout_seconds=5.0,
        heartbeat_shutdown_timeout_seconds=5.0,
        heartbeat_storage_factory=lambda: SqliteStorage.open(settings.db_path),
        clock=clock,
    ), storage


def _cmd_worker(args: argparse.Namespace) -> int:
    settings = load_settings()
    worker, storage = _build_worker(settings)
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
        now = SystemClock().now()
        recovery = storage.release_or_requeue_expired_leases(now=now)
        result = storage.reap_orphaned_stale_runs(
            now - timedelta(seconds=args.stale_after_seconds), now=now,
        )
        print(
            "REAPER: "
            f"checked={result.checked_count} stopped={result.stopped_count} "
            f"recovered(requeued={recovery.requeued_count}, "
            f"needs_verification={recovery.needs_verification_count}, "
            f"failed={recovery.failed_count})"
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
                f"failed={result.recovery.failed_count})"
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

    p_worker = sub.add_parser("worker", help="Wykonaj bezpieczny, trwały job offline.")
    worker_mode = p_worker.add_mutually_exclusive_group(required=True)
    worker_mode.add_argument("--once", action="store_true", help="Podejmij najwyżej jeden job.")
    worker_mode.add_argument(
        "--poll-seconds", type=float,
        help="Uruchom kontrolowaną pętlę z podanym interwałem (> 0).",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "maintain" and args.poll and args.interval_seconds is None:
        parser.error("maintain --poll wymaga --interval-seconds.")
    if args.command == "maintain" and args.once and args.interval_seconds is not None:
        parser.error("maintain --once nie przyjmuje --interval-seconds.")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
