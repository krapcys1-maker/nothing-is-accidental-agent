"""Deterministic editorial-angle memory and semantic novelty gate.

The gate deliberately uses only durable local text.  It is not a general
semantic model: it compares the title, the causal question, the researched
thesis and (for already written content) the article text.  Exact-title checks
remain strict, while thesis checks require several shared canonical concepts so
that a broad area alone cannot block a genuinely different angle.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


_STOPWORDS = frozenset("""
a an and are as at be been being but by can could did do does for from had has
have how i if in into is it its may might more most of on or our should so than
that the their them then there these they this those to was were what when where
which who why will with would you your behind every really same way
""".split())

# Small, explicit concept aliases cover editorial paraphrases without pretending
# to be an embedding model.  Values are intentionally domain-generic and only
# collapse near-synonyms, never whole topics.
_ALIASES = {
    "airfare": "fare", "fares": "fare", "ticket": "fare", "tickets": "fare",
    "cost": "price", "costs": "price", "prices": "price", "pricing": "price",
    "changes": "change", "changed": "change", "changing": "change",
    "shifts": "change", "shifted": "change", "fluctuates": "change",
    "fluctuation": "change", "varies": "change", "vary": "change",
    "dynamic": "change", "moves": "change",
    "airlines": "airline", "flights": "flight",
    "supermarkets": "supermarket", "groceries": "grocery",
    "placement": "place", "placed": "place", "located": "place",
    "incentives": "incentive", "motivation": "incentive",
    "systems": "system", "mechanisms": "mechanism", "processes": "process",
    "decisions": "decision", "choices": "decision",
    "customers": "customer", "consumers": "customer", "buyers": "customer",
    "profits": "profit", "revenue": "profit", "revenues": "profit",
    "hidden": "concealed", "invisible": "concealed", "unseen": "concealed",
}


def _stem(token: str) -> str:
    token = _ALIASES.get(token, token)
    for suffix in ("ization", "ational", "fulness", "iveness", "ments", "ment",
                   "ingly", "edly", "ation", "ities", "ity", "ing", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            token = token[:-len(suffix)]
            break
    return _ALIASES.get(token, token)


def normalize_editorial_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text.lower()))


def editorial_concepts(value: str) -> frozenset[str]:
    return frozenset(
        _stem(token) for token in normalize_editorial_text(value).split()
        if len(token) >= 3 and token not in _STOPWORDS
    )


def _text_similarity(left: str, right: str) -> tuple[float, int]:
    a = normalize_editorial_text(left)
    b = normalize_editorial_text(right)
    if not a or not b:
        return 0.0, 0
    if a == b:
        return 1.0, len(editorial_concepts(a))
    ac, bc = editorial_concepts(a), editorial_concepts(b)
    shared = len(ac & bc)
    union = len(ac | bc)
    jaccard = shared / union if union else 0.0
    containment = shared / min(len(ac), len(bc)) if ac and bc else 0.0
    sequence = SequenceMatcher(None, a, b).ratio()
    return max(jaccard, containment * 0.92, sequence * 0.82), shared


@dataclass(frozen=True)
class EditorialMemoryRecord:
    source_kind: str
    source_id: int
    topic_id: int
    research_card_id: int | None
    content_id: int | None
    title: str
    question: str
    central_thesis: str
    body: str
    status: str
    created_at: str


@dataclass(frozen=True)
class EditorialDuplicateMatch:
    existing: EditorialMemoryRecord
    reason: str
    score: float


def find_editorial_duplicate(
    candidate: EditorialMemoryRecord,
    existing: list[EditorialMemoryRecord] | tuple[EditorialMemoryRecord, ...],
) -> EditorialDuplicateMatch | None:
    """Return the strongest thesis-level duplicate, or ``None``.

    A title alone blocks only when exact or a strong paraphrase.  Otherwise the
    causal question/thesis must agree.  This keeps "airline prices" eligible for
    a new thesis while rejecting a renamed version of the old causal claim.
    """
    best: EditorialDuplicateMatch | None = None
    candidate_thesis = candidate.central_thesis or candidate.question
    candidate_angle = " ".join(
        part for part in (candidate.question, candidate_thesis) if part.strip()
    )
    for record in existing:
        title_score, title_shared = _text_similarity(candidate.title, record.title)
        if normalize_editorial_text(candidate.title) == normalize_editorial_text(record.title):
            match = EditorialDuplicateMatch(record, "EXACT_TOPIC", 1.0)
        else:
            record_thesis = record.central_thesis or record.question
            record_angle = " ".join(
                part for part in (record.question, record_thesis) if part.strip()
            )
            thesis_score, thesis_shared = _text_similarity(candidate_angle, record_angle)
            body_score, body_shared = _text_similarity(candidate_angle, record.body[:4000])
            if title_score >= 0.72 and title_shared >= 3 and thesis_score >= 0.42:
                match = EditorialDuplicateMatch(
                    record, "STRONG_TOPIC_PARAPHRASE", max(title_score, thesis_score),
                )
            elif thesis_score >= 0.70 and thesis_shared >= 3:
                match = EditorialDuplicateMatch(record, "SAME_CENTRAL_THESIS", thesis_score)
            elif body_score >= 0.76 and body_shared >= 4:
                match = EditorialDuplicateMatch(record, "PRIOR_CONTENT_PARAPHRASE", body_score)
            else:
                continue
        if best is None or match.score > best.score:
            best = match
    return best


def bounded_history_snapshot(
    records: list[EditorialMemoryRecord] | tuple[EditorialMemoryRecord, ...],
    *,
    limit: int = 40,
    field_limit: int = 240,
) -> tuple[dict[str, str], ...]:
    """Build a deterministic prompt-safe history; never include article bodies."""
    if limit < 1 or field_limit < 32:
        raise ValueError("Editorial history bounds must be positive and explicit.")
    # Prefer the richest/latest record per topic, then bound the final snapshot.
    by_topic: dict[int, EditorialMemoryRecord] = {}
    for record in records:
        current = by_topic.get(record.topic_id)
        if current is None or (
            bool(record.central_thesis), record.created_at, record.source_kind, record.source_id
        ) >= (
            bool(current.central_thesis), current.created_at, current.source_kind, current.source_id
        ):
            by_topic[record.topic_id] = record
    selected = sorted(
        by_topic.values(), key=lambda row: (row.created_at, row.topic_id, row.source_id)
    )[-limit:]
    return tuple({
        "title": row.title[:field_limit],
        "question": row.question[:field_limit],
        "central_thesis": row.central_thesis[:field_limit],
        "status": row.status[:40],
    } for row in selected)
