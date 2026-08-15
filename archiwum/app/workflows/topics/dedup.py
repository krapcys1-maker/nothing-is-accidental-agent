"""Lokalna deduplikacja tematów — bez płatnego wywołania modelu.

Strategia:
1. znormalizowany tytuł (lower, bez interpunkcji, złożone spacje) — dopasowanie dokładne,
2. fallback deterministyczny: podobieństwo tokenów (Jaccard) po usunięciu słów-funkcyjnych,
   wsparte difflib.SequenceMatcher; próg z konfiguracji.
Deduplikacja jest zawsze w obrębie jednego account_id (wywołujący podaje istniejące tematy konta).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

# Minimalny zestaw słów-funkcyjnych; celowo mały, by nie sklejać różnych tematów.
_STOPWORDS = {
    "the", "a", "an", "of", "to", "is", "are", "and", "so", "that", "how",
    "why", "do", "does", "did", "what", "when", "on", "in", "for", "your",
}
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    text = title.strip().lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def content_tokens(title: str) -> set[str]:
    return {t for t in normalize_title(title).split() if t and t not in _STOPWORDS}


def jaccard(a: str, b: str) -> float:
    ta, tb = content_tokens(a), content_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def similarity(a: str, b: str) -> float:
    """Maks. z Jaccarda tokenów i SequenceMatcher na znormalizowanych tytułach (0..1)."""
    seq = SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()
    return max(jaccard(a, b), seq)


@dataclass
class DuplicateMatch:
    existing_id: int
    existing_title: str
    reason: str
    score: float


class TopicDeduplicator:
    def __init__(self, threshold: float = 0.72) -> None:
        self.threshold = threshold

    def find_duplicate(
        self, candidate_title: str, existing: list[tuple[int, str]]
    ) -> DuplicateMatch | None:
        """existing: lista (topic_id, title) z TEGO SAMEGO konta. Zwraca dopasowanie lub None."""
        cand_norm = normalize_title(candidate_title)
        best: DuplicateMatch | None = None
        for topic_id, title in existing:
            if normalize_title(title) == cand_norm:
                return DuplicateMatch(topic_id, title, "EXACT_NORMALIZED_TITLE", 1.0)
            score = similarity(candidate_title, title)
            if score >= self.threshold and (best is None or score > best.score):
                best = DuplicateMatch(topic_id, title,
                                      f"SEMANTIC_SIMILARITY>={self.threshold:.2f}", round(score, 3))
        return best
