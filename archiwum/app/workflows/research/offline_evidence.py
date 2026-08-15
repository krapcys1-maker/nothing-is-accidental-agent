"""E2-A offline CLI/worker staged pipeline backed by FakeFetch and E1 evidence."""
from __future__ import annotations

import json
from typing import Callable

from app.core.clock import Clock
from app.core.config import Settings
from app.core.ids import new_run_id
from app.models import (
    Account,
    EvidenceRetrievalStatus,
    JobExecutionContext,
    ResearchCard,
    ResearchRecommendation,
    ResearchRunStatus,
    ResearchJobExecution,
    Source,
    SourceCandidateRecord,
    SourceType,
    SourceVerification,
    Topic,
)
from app.policies.policy_engine import PolicyEngine
from app.ports.storage import StoragePort
from app.research import injection_guard
from app.research.base import ResearchPlan, SourceCandidate, SourceCardDraft
from app.research.offline_evidence_intent import (
    OfflineEvidenceIntent,
    OfflineEvidenceResearchClient,
)
from app.research.validation import validate_draft
from app.workflows.research.pipeline import ResearchRunSummary


CheckpointHook = Callable[[str], None]


def run_offline_evidence_research(
    account: Account,
    topic: Topic,
    *,
    settings: Settings,
    storage: StoragePort,
    policy: PolicyEngine,
    clock: Clock,
    job_execution: ResearchJobExecution,
    intent: OfflineEvidenceIntent,
    checkpoint_hook: CheckpointHook | None = None,
) -> ResearchRunSummary:
    """Run/resume one zero-cost STAGED job; every write is lease-fenced."""
    initialized = storage.initialize_offline_evidence_run_for_job(
        job_execution.job_id, job_execution.lease_owner, new_run_id(), clock=clock,
    )
    execution = JobExecutionContext(
        job_id=job_execution.job_id, lease_owner=job_execution.lease_owner,
        run_id=initialized.run.id, clock=clock,
    )
    summary = ResearchRunSummary(
        run_id=execution.run_id, account_id=account.id, topic_id=int(topic.id),
        dry_run=True, model="offline-evidence-fixture",
    )
    client = OfflineEvidenceResearchClient(intent)
    fetch = intent.fake_fetch(clock.now())
    plan = ResearchPlan(
        topic_id=int(topic.id), account_id=account.id,
        question=topic.question or topic.title, niche=list(account.niche),
    )

    def checkpoint(name: str) -> None:
        storage.assert_offline_evidence_execution_active(execution)
        if checkpoint_hook is not None:
            checkpoint_hook(name)

    try:
        research_run = initialized.research_run
        if research_run.status is ResearchRunStatus.DISCOVERY_PENDING:
            discovery = client.discover_sources(plan, max_searches=len(intent.sources))
            storage.persist_offline_evidence_discovery(
                execution,
                [
                    SourceCandidateRecord(
                        research_run_id=execution.run_id,
                        url=item.url, title=item.title,
                    )
                    for item in discovery.candidates
                ],
            )
            checkpoint("after_discovery")

        by_url = {source.url: source for source in intent.sources}
        for row in storage.get_offline_evidence_lineage(execution.run_id):
            fixture = by_url[row["url"]]
            retrieval_id = row["retrieval_id"]
            if retrieval_id is None:
                document = fetch.fetch(row["url"])
                retrieval = storage.persist_offline_evidence_retrieval(
                    execution, int(row["id"]), document,
                )
                retrieval_id = retrieval.id
                checkpoint("after_retrieval")
            else:
                retrieval = storage.get_evidence_retrieval(
                    int(retrieval_id), account_id=account.id,
                )
            if retrieval is None or retrieval.status is not EvidenceRetrievalStatus.OK:
                raise RuntimeError("offline fetch did not produce a successful retrieval.")
            # Internet/fixture content remains data. Calling the guard here proves
            # the integration does not reinterpret it as control input.
            injection_guard.contains_injection(retrieval.canonical_text)

            if row["excerpt_id"] is None:
                extracted = client.extract_source(
                    plan, SourceCandidate(url=row["url"], title=row["title"]),
                )
                proposed = extracted.card
                start = retrieval.canonical_text.find(fixture.excerpt)
                end = start + len(fixture.excerpt) if start >= 0 else -1
                storage.persist_offline_verified_excerpt(
                    execution, int(row["id"]),
                    claim_text=fixture.claim, excerpt_text=fixture.excerpt,
                    start_offset=start, end_offset=end,
                    title=proposed.title, author_or_org=proposed.author_or_org,
                    published_at=proposed.published_at,
                    source_type=proposed.source_type,
                    source_quality_score=proposed.source_quality_score,
                )
                checkpoint("after_excerpt")

        lineage = storage.get_offline_evidence_lineage(execution.run_id)
        verified_cards = [
            SourceCardDraft(
                url=row["url"], title=row["title"],
                author_or_org=row["author_or_org"], published_at=row["published_at"],
                source_type=SourceType(row["source_type"]),
                supported_claims=json.loads(row["supported_claims_json"] or "[]"),
                numeric_facts=json.loads(row["numeric_facts_json"] or "[]"),
                verification=SourceVerification(row["verification_status"]),
                source_quality_score=float(row["source_quality_score"]),
            )
            for row in lineage
            if row["excerpt_id"] is not None
            and row["verification_status"] == SourceVerification.VERIFIED.value
        ]
        if len(verified_cards) < settings.research_min_sources:
            raise RuntimeError("offline evidence did not meet the configured source threshold.")

        current = storage.get_research_run(execution.run_id)
        if current is None:
            raise RuntimeError("offline research run disappeared.")
        if current.status is not ResearchRunStatus.SYNTHESIS_PENDING:
            storage.prepare_offline_evidence_synthesis(
                execution, min_verified_sources=settings.research_min_sources,
            )
            checkpoint("before_synthesis")

        synthesized = client.synthesize_from_cards(plan, verified_cards)
        draft = synthesized.draft
        if injection_guard.contains_injection(draft.working_thesis):
            draft.working_thesis = injection_guard.neutralize(draft.working_thesis)
        if draft.strongest_counterargument and injection_guard.contains_injection(
            draft.strongest_counterargument
        ):
            draft.strongest_counterargument = injection_guard.neutralize(
                draft.strongest_counterargument
            )
        outcome = validate_draft(
            draft,
            min_sources=settings.research_min_sources,
            min_confidence=settings.research_min_confidence,
            min_source_quality=settings.research_min_source_quality,
            min_verified_sources=settings.research_min_sources,
        )
        if not outcome.passed:
            raise RuntimeError(
                "offline synthesis failed the existing quality gate: "
                + ",".join(outcome.reasons)
            )
        card = ResearchCard(
            topic_id=int(topic.id), question=draft.question,
            working_thesis=draft.working_thesis,
            main_mechanism=draft.main_mechanism,
            confirmed_claims=list(draft.confirmed_claims),
            uncertain_claims=list(draft.uncertain_claims),
            contradictions=list(draft.contradictions),
            strongest_counterargument=draft.strongest_counterargument,
            citable_numbers=list(draft.citable_numbers),
            visual_idea=draft.visual_idea,
            confidence_score=draft.confidence_score,
            source_quality_score=draft.source_quality_score,
            publication_recommendation=ResearchRecommendation.PROCEED,
            created_at=clock.now(),
            sources=[
                Source(
                    url=source.url, title=source.title,
                    author_or_org=source.author_or_org,
                    published_at=source.published_at,
                    source_type=source.source_type,
                    supports_claim=source.supported_claims[0],
                    verification_status=SourceVerification.VERIFIED,
                )
                for source in verified_cards
            ],
        )
        checkpoint("before_finalization")
        card = storage.finalize_offline_evidence_execution(
            execution, card, min_verified_sources=settings.research_min_sources,
        )
        summary.card = card
        summary.passed = True
        summary.recommendation = ResearchRecommendation.PROCEED.value
        summary.sources_count = len(card.sources)
        summary.candidates_discovered = len(lineage)
        summary.sources_extracted = len(verified_cards)
        return summary
    except Exception as exc:
        summary.error = f"{type(exc).__name__}: {str(exc)}"[:240]
        storage.fail_offline_evidence_execution(execution, summary.error)
        return summary
