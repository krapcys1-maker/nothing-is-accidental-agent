"""Kontrakt klienta językowego i wspólne typy danych."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import Account

# Kryteria scoringu tematu (klucze breakdown). Wagi pochodzą z konfiguracji.
TOPIC_CRITERIA = [
    "curiosity",
    "source_quality",
    "non_obvious",
    "universality",
    "discussion_potential",
    "visual_potential",
    "originality",
]


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_search_requests: int = 0


@dataclass
class TopicIdea:
    title: str
    question: str
    # breakdown: klucz kryterium -> ocena 0.0..1.0
    score_breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class TopicGenerationResult:
    ideas: list[TopicIdea]
    usage: Usage
    model: str


class LLMClient(Protocol):
    """Jedno wywołanie 'wygeneruj i oceń tematy'. Implementacje: Fake (dry_run) i Anthropic."""

    model: str

    def generate_and_score_topics(self, account: Account, count: int) -> TopicGenerationResult: ...
