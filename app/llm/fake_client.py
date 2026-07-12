"""Deterministyczny klient zastępczy używany w dry_run i w testach.

Nie wykonuje żadnego wywołania sieciowego i nie generuje realnego kosztu.
Zwraca stały zestaw tematów z niszy 'Nothing Is Accidental' i szacunkowe zużycie tokenów,
żeby zademonstrować tracking kosztów bez wydawania budżetu.
"""
from __future__ import annotations

from app.llm.base import LLMClient, TopicGenerationResult, TopicIdea, Usage
from app.models import Account

# Stałe tematy z rozkładem ocen dobranym tak, by pokryć wszystkie progi:
# część kwalifikuje się na artykuł (>=75), część na Note (>=65), część odpada.
_FIXTURE_TOPICS: list[TopicIdea] = [
    TopicIdea(
        title="Why airline ticket prices change every few hours",
        question="What pricing system makes fares move so often?",
        score_breakdown={"curiosity": 0.90, "source_quality": 0.90, "non_obvious": 0.90,
                         "universality": 0.90, "discussion_potential": 0.90,
                         "visual_potential": 0.90, "originality": 0.80},
    ),
    TopicIdea(
        title="What really happens to your suitcase after check-in",
        question="What is the hidden logistics chain behind checked luggage?",
        score_breakdown={"curiosity": 0.85, "source_quality": 0.85, "non_obvious": 0.85,
                         "universality": 0.85, "discussion_potential": 0.85,
                         "visual_potential": 0.85, "originality": 0.90},
    ),
    TopicIdea(
        title="Why supermarkets put essentials at the back",
        question="What incentive puts milk and bread far from the entrance?",
        score_breakdown={"curiosity": 0.85, "source_quality": 0.80, "non_obvious": 0.75,
                         "universality": 0.75, "discussion_potential": 0.70,
                         "visual_potential": 0.70, "originality": 0.60},
    ),
    TopicIdea(
        title="Why queues slow down even when more counters open",
        question="What queueing dynamics defeat extra counters?",
        score_breakdown={"curiosity": 0.75, "source_quality": 0.70, "non_obvious": 0.65,
                         "universality": 0.70, "discussion_potential": 0.70,
                         "visual_potential": 0.60, "originality": 0.60},
    ),
    TopicIdea(
        title="Why hotel rooms skip certain floor numbers",
        question="What drives the missing 13th (and other) floors?",
        score_breakdown={"curiosity": 0.72, "source_quality": 0.70, "non_obvious": 0.65,
                         "universality": 0.68, "discussion_potential": 0.66,
                         "visual_potential": 0.62, "originality": 0.60},
    ),
    TopicIdea(
        title="Why shopping carts are shaped the way they are",
        question="What decisions shaped the modern cart?",
        score_breakdown={"curiosity": 0.60, "source_quality": 0.55, "non_obvious": 0.55,
                         "universality": 0.60, "discussion_potential": 0.55,
                         "visual_potential": 0.50, "originality": 0.50},
    ),
]


class FakeLLMClient(LLMClient):
    def __init__(self, model: str = "dry-run-fake") -> None:
        self.model = model

    def generate_and_score_topics(self, account: Account, count: int) -> TopicGenerationResult:
        ideas = [
            TopicIdea(t.title, t.question, dict(t.score_breakdown))
            for t in _FIXTURE_TOPICS[: max(0, count)]
        ]
        # Szacunkowe zużycie: stały prompt + ~100 tokenów wyjścia na temat.
        usage = Usage(input_tokens=1200, output_tokens=100 * len(ideas))
        return TopicGenerationResult(ideas=ideas, usage=usage, model=self.model)
