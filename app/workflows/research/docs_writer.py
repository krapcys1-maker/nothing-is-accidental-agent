"""Automatyczny wpis do docs/RESEARCH_LOG.md po zakończonym researchu."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.models import ResearchCard, Topic


def make_research_log_writer(path: Path) -> Callable[[ResearchCard, Topic, object], None]:
    path = Path(path)

    def writer(card: ResearchCard, topic: Topic, summary: object) -> None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dry_run = bool(getattr(summary, "dry_run", True))
        cost_usd = getattr(summary, "cost_usd", 0.0)
        impact = (
            "dry-run/demonstracja pipeline researchu (brak realnego kosztu)."
            if dry_run else
            f"REALNE wywołanie Anthropic (płatne) — koszt {cost_usd:.6f} USD."
        )
        lines = [
            f"\n### [{date}] {topic.title}",
            f"- **Konto:** {topic.account_id}",
            f"- **Powiązanie:** research_card #{card.id} / topic #{topic.id}",
            f"- **Pytanie badawcze:** {card.question}",
            "- **Źródła:**",
        ]
        for i, s in enumerate(card.sources, 1):
            meta = f"{s.source_type.value}, {s.published_at or 'brak daty'}"
            lines.append(f"  {i}. [{s.title}]({s.url}) — {meta} — wspiera: {s.supports_claim}")
        lines += [
            f"- **Najważniejsze fakty (potwierdzone):** {', '.join(card.confirmed_claims) or '—'}",
            f"- **Elementy niepewne:** {', '.join(card.uncertain_claims) or '—'}",
            f"- **Sprzeczności między źródłami:** {', '.join(card.contradictions) or '—'}",
            f"- **Wniosek (teza robocza):** {card.working_thesis}",
            f"- **Confidence:** {card.confidence_score}  |  **Source quality:** {card.source_quality_score}",
            f"- **Rekomendacja:** {card.publication_recommendation.value}"
            + (f" (powód: {card.rejection_reason})" if card.rejection_reason else ""),
            f"- **Wpływ:** {impact}",
        ]
        with path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    return writer
