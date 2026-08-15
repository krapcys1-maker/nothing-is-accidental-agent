"""Typed boundary for ARTICLE_RESEARCH A1 source discovery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.llm.base import Usage


@dataclass(frozen=True)
class SourceDiscoveryRequest:
    account_id: str
    topic_id: int
    research_run_id: str
    query: str
    max_results: int


@dataclass(frozen=True)
class SourceDiscoveryCandidate:
    canonical_url: str
    canonical_source_identity: str
    title: str
    result_identity: str
    observed_at: str
    # Publication date as the search tool reported it, when it reported one.
    # Without this the freshness gate had nothing to read and treated every
    # corpus as undated, which it then scored as stale.
    published_at: str | None = None


@dataclass(frozen=True)
class SourceDiscoveryResponse:
    candidates: tuple[SourceDiscoveryCandidate, ...]
    returned_model_id: str
    request_id: str
    usage: Usage
    port_name: str


class SourceDiscoveryPort(Protocol):
    def discover(self, request: SourceDiscoveryRequest) -> SourceDiscoveryResponse: ...
