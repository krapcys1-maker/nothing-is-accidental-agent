"""StoragePort — kontrakt trwałego stanu.

Każda metoda per-konto przyjmuje account_id jako obowiązkowy parametr (izolacja kont).
Lokalny adapter: app/storage/repositories.py (SQLite). Później: Postgres.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from app.models import (
    Account,
    ModelUsage,
    ResearchCard,
    ResearchRun,
    ResearchSourceRecord,
    ResearchStageName,
    ResearchStageStatus,
    Run,
    SourceCandidateRecord,
    SourceCandidateStatus,
    SourceType,
    SourceVerification,
    Topic,
    TopicStatus,
)


class StoragePort(Protocol):
    def ensure_account(self, account: Account) -> None: ...

    def add_topic(self, account_id: str, topic: Topic) -> Topic: ...

    def list_topics(self, account_id: str) -> Sequence[Topic]: ...

    def list_topic_titles_for_dedup(self, account_id: str) -> list[tuple[int, str]]: ...

    def list_topics_by_status(self, account_id: str, status: TopicStatus) -> Sequence[Topic]: ...

    def create_run(self, run: Run) -> Run: ...

    def finish_run(self, run_id: str, status: str, cost_usd: float,
                   error: str | None = None) -> None: ...

    def add_model_usage(self, usage: ModelUsage) -> ModelUsage: ...

    def sum_real_cost_usd(self, since_prefix: str) -> float:
        """Suma estimated_cost_usd dla realnych (nie dry_run) wpisów, których
        created_at zaczyna się od podanego prefiksu (np. '2026-07' dla miesiąca)."""
        ...

    def add_research_card(self, card: ResearchCard) -> ResearchCard: ...

    def get_research_card(self, card_id: int) -> ResearchCard | None: ...

    def list_research_cards(self, account_id: str) -> list[ResearchCard]: ...

    # --- wznawialny dwuetapowy research ---

    def create_research_run(self, research_run: ResearchRun) -> ResearchRun: ...

    def get_research_run(self, research_run_id: str) -> ResearchRun | None: ...

    def mark_single_research_run_complete(
        self, research_run_id: str, research_card_id: int, total_cost_usd: float,
    ) -> None: ...

    def add_research_sources(self, research_run_id: str,
                             sources: list[ResearchSourceRecord]) -> list[ResearchSourceRecord]: ...

    def list_research_sources(self, research_run_id: str) -> list[ResearchSourceRecord]: ...

    def mark_research_stage_a_success(
        self, research_run_id: str, sources: list[ResearchSourceRecord],
    ) -> list[ResearchSourceRecord]: ...

    def mark_research_run_failed(self, research_run_id: str, error: str) -> None: ...

    def mark_research_run_partial(self, research_run_id: str, error: str) -> None: ...

    def mark_research_run_complete(self, research_run_id: str, research_card_id: int,
                                   total_cost_usd: float) -> None: ...

    def add_research_stage_result(self, research_run_id: str, stage: ResearchStageName,
                                  status: ResearchStageStatus, error: str | None = None) -> None: ...

    def get_research_usage(self, research_run_id: str) -> list[ModelUsage]: ...

    def sync_run_cost_from_research_usage(self, research_run_id: str) -> float:
        """Idempotentnie ustawia runs.cost_usd na kanoniczną sumę model_usage runu."""
        ...

    # --- etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis) ---

    def create_source_candidates(
        self, research_run_id: str, candidates: list[SourceCandidateRecord],
    ) -> list[SourceCandidateRecord]: ...

    def list_source_candidates(
        self, research_run_id: str, status: SourceCandidateStatus | None = None,
    ) -> list[SourceCandidateRecord]: ...

    def mark_extraction_in_progress(self, research_run_id: str) -> None: ...

    def update_source_candidate_extracted(
        self, candidate_id: int, *, title: str | None, author_or_org: str | None,
        published_at: str | None, source_type: SourceType, supported_claims: list[str],
        numeric_facts: list[str], verification_status: SourceVerification,
        source_quality_score: float,
    ) -> None: ...

    def mark_source_candidate_failed(self, candidate_id: int, error: str) -> None: ...

    def mark_sources_complete(self, research_run_id: str) -> None: ...

    def mark_synthesis_pending(self, research_run_id: str) -> None: ...

    def revert_to_sources_complete(self, research_run_id: str, error: str) -> None: ...
