"""CLI walking skeleton.

Uruchomienie:
    python -m app.main run-topics --count 6

Domyślnie działa w dry_run (klient zastępczy, brak realnego kosztu, zero akcji na Substacku).
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.orchestrator.runner import DEFAULT_ACCOUNT, run_research, run_topics


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
    summary = run_research(topic_id=args.topic_id, account_id=args.account, force_real=args.real)

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
                            help="ZABLOKOWANE (P0-3, docs/AUDYT_ARCHITEKTURY_2026-07-12.md) — "
                                 "ta ścieżka nie ma capu ani limitu web searchy. Do realnego "
                                 "researchu użyj scripts/run_capped_research.py.")
    p_research.set_defaults(func=_cmd_run_research)
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
