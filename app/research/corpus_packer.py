"""Deterministic whole-document evidence packing for the 32k Researcher."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from app.content.cost_estimate import (
    ARTICLE_RESEARCH_MAX_CONTEXT_TOKENS,
    ARTICLE_RESEARCH_MAX_INPUT_TOKENS,
    ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS,
)
from app.research.durable_intent import EVIDENCE_PROMPT_OVERHEAD_CHARS
from app.research.output_contract import CONSERVATIVE_CHARS_PER_TOKEN

MIN_RESEARCH_SOURCES = 3


class CorpusPackingError(ValueError):
    code = "RESEARCH_CORPUS_INCOMPLETE"


@dataclass(frozen=True)
class CorpusDocument:
    retrieval_id: int
    source_identity: str
    canonical_sha256: str
    canonical_chars: int
    canonical_text: str


@dataclass(frozen=True)
class PackedCorpus:
    documents: tuple[CorpusDocument, ...]
    estimated_input_tokens: int
    max_output_tokens: int = ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS

    @property
    def context_tokens(self) -> int:
        return self.estimated_input_tokens + self.max_output_tokens


def pack_research_corpus(documents: Sequence[CorpusDocument]) -> PackedCorpus:
    """Select complete documents in a stable source-identity order.

    No document is split.  The conservative repository-wide 3.5 chars/token
    estimator includes the pinned evidence prompt overhead.
    """
    ordered = sorted(
        documents,
        key=lambda item: (item.source_identity, item.canonical_sha256, item.retrieval_id),
    )
    selected: list[CorpusDocument] = []
    selected_chars = 0
    for item in ordered:
        if item.canonical_chars != len(item.canonical_text) or item.canonical_chars < 1:
            raise CorpusPackingError("retrieval canonical length is inconsistent")
        projected = math.ceil(
            (EVIDENCE_PROMPT_OVERHEAD_CHARS + selected_chars + item.canonical_chars)
            / CONSERVATIVE_CHARS_PER_TOKEN
        )
        if projected <= ARTICLE_RESEARCH_MAX_INPUT_TOKENS:
            selected.append(item)
            selected_chars += item.canonical_chars
    estimated = math.ceil(
        (EVIDENCE_PROMPT_OVERHEAD_CHARS + selected_chars)
        / CONSERVATIVE_CHARS_PER_TOKEN
    )
    if len(selected) < MIN_RESEARCH_SOURCES:
        raise CorpusPackingError(
            "fewer than three complete canonical sources fit the 23,808-token input envelope"
        )
    if (
        estimated > ARTICLE_RESEARCH_MAX_INPUT_TOKENS
        or ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS != 8192
        or estimated + ARTICLE_RESEARCH_MAX_OUTPUT_TOKENS > ARTICLE_RESEARCH_MAX_CONTEXT_TOKENS
    ):
        raise CorpusPackingError("packed corpus exceeds the 23,808/8,192/32,000 envelope")
    return PackedCorpus(tuple(selected), estimated)
