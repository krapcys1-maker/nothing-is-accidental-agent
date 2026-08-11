"""Automatic controlled-fetch corpus -> ARTICLE_RESEARCH job connection."""
from __future__ import annotations

from dataclasses import replace

from app.core.clock import Clock
from app.core.config import Settings
from app.models import Account, Job, JobKind, Topic, WorkflowType
from app.research.corpus_packer import CorpusDocument, CorpusPackingError, pack_research_corpus
from app.research.durable_intent import DurableResearchExecutionIntent, evidence_input_payload


def enqueue_evidence_research_if_ready(
    *, storage: object, settings: Settings, account: Account, topic: Topic, clock: Clock,
) -> str | None:
    """Create exactly one evidence job once three approved successful fetches fit."""
    job_id = f"article-research-evidence-{int(topic.id)}"
    existing = storage.get_job(job_id)
    if existing is not None:
        return job_id
    rows = storage.conn.execute(
        "SELECT c.canonical_source_identity,a.retrieval_id,r.canonical_sha256,"
        "r.canonical_chars,r.canonical_text "
        "FROM source_candidate_fetch_approvals fa "
        "JOIN research_source_candidates c ON c.id=fa.candidate_id "
        "JOIN controlled_fetch_attempts a ON a.job_id=fa.fetch_job_id "
        "JOIN evidence_retrievals r ON r.id=a.retrieval_id "
        "WHERE fa.account_id=? AND fa.topic_id=? AND a.status='SUCCEEDED' "
        "AND r.status='OK' ORDER BY c.canonical_source_identity,a.retrieval_id",
        (account.id, int(topic.id)),
    ).fetchall()
    try:
        packed = pack_research_corpus([
            CorpusDocument(
                retrieval_id=int(row["retrieval_id"]),
                source_identity=str(row["canonical_source_identity"]),
                canonical_sha256=str(row["canonical_sha256"]),
                canonical_chars=int(row["canonical_chars"]),
                canonical_text=str(row["canonical_text"]),
            )
            for row in rows
        ])
    except CorpusPackingError:
        return None

    exact_settings = replace(settings, model_quality="claude-opus-5", dry_run=False)
    active = storage.get_active_model_for_role("ARTICLE_RESEARCH")
    if active is None or active.technical_model_id != "claude-opus-5" or not active.pricing_ref:
        raise CorpusPackingError("exact active ARTICLE_RESEARCH pricing authority is missing")
    profile = storage.get_model_pricing_profile(active.pricing_ref)
    if profile is None or profile.prices is None:
        raise CorpusPackingError("verified ARTICLE_RESEARCH pricing is missing")
    intent = DurableResearchExecutionIntent.from_settings(
        settings=exact_settings,
        account_id=account.id,
        topic_id=int(topic.id),
        cap_usd="1.000000",
        max_web_searches=0,
        question=topic.question or topic.title,
        niche=account.niche,
        max_tokens=8192,
        evidence_input=evidence_input_payload([
            (doc.retrieval_id, doc.canonical_sha256, doc.canonical_chars)
            for doc in packed.documents
        ]),
        pricing_prices=profile.prices.as_storage_mapping(),
        pricing_profile_id=profile.pricing_ref,
        pricing_profile_version=profile.contract_fingerprint(),
        pricing_currency=profile.currency,
        pricing_unit=profile.unit,
    )
    payload = {
        "account_id": account.id,
        "topic_id": int(topic.id),
        "dry_run": False,
        "execution": "durable_provider_v2",
        "mode": "single",
        "max_cost_usd": intent.cap_usd,
        "execution_intent": intent.as_payload(),
    }
    storage.enqueue_job(Job(
        id=job_id,
        account_id=account.id,
        kind=JobKind.RESEARCH,
        workflow=WorkflowType.RESEARCH,
        idempotency_key=f"article-research-evidence:{account.id}:{int(topic.id)}",
        topic_id=int(topic.id),
        payload=payload,
        schedule_reason="WITHIN_EDITORIAL_WINDOW",
        earliest_run_at=clock.now(),
        max_attempts=1,
        created_at=clock.now(),
    ))
    return job_id
