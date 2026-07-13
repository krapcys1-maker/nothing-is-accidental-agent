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
from datetime import timedelta
from uuid import uuid4

from app.core.clock import SystemClock
from app.core.config import Settings, load_settings
from app.orchestrator.runner import DEFAULT_ACCOUNT, run_research, run_topics
from app.policies.policy_engine import PolicyEngine
from app.scheduler.dispatcher import JobDispatcher
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
        lease_owner=f"cli-worker-{uuid4()}", clock=clock,
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
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
