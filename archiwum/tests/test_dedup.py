"""Testy deduplikatora tematów (lokalny, bez płatnych wywołań)."""
from __future__ import annotations

from app.workflows.topics.dedup import TopicDeduplicator, normalize_title, similarity

_BASE = "Why airline ticket prices change every few hours"


def _dedup() -> TopicDeduplicator:
    return TopicDeduplicator(threshold=0.72)


def test_identical_title_is_duplicate():
    match = _dedup().find_duplicate(_BASE, [(1, _BASE)])
    assert match is not None
    assert match.existing_id == 1
    assert match.reason == "EXACT_NORMALIZED_TITLE"


def test_different_case_is_duplicate():
    match = _dedup().find_duplicate("WHY AIRLINE TICKET PRICES CHANGE EVERY FEW HOURS",
                                    [(7, _BASE)])
    assert match is not None
    assert match.reason == "EXACT_NORMALIZED_TITLE"


def test_different_punctuation_is_duplicate():
    match = _dedup().find_duplicate("Why airline ticket prices change every few hours!!!",
                                    [(7, _BASE)])
    assert match is not None
    assert match.reason == "EXACT_NORMALIZED_TITLE"


def test_paraphrase_is_duplicate():
    match = _dedup().find_duplicate("Why do airline ticket prices shift every few hours",
                                    [(3, _BASE)])
    assert match is not None
    assert match.existing_id == 3
    assert match.reason.startswith("SEMANTIC_SIMILARITY")


def test_clearly_different_topic_is_not_duplicate():
    match = _dedup().find_duplicate("What really happens to your suitcase after check-in",
                                    [(3, _BASE)])
    assert match is None


def test_normalization_helpers():
    assert normalize_title("  Why, Airline!!  Prices? ") == "why airline prices"
    assert similarity(_BASE, _BASE) == 1.0
