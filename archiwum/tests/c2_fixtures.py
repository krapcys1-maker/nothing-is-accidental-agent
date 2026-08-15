"""Deterministic authoritative Research Card fixture for WAVE C2 tests."""
from __future__ import annotations

import hashlib
import json

from app.models import Topic, TopicStatus


CLAIM = "A hidden fee changes the apparent price."
URL = "https://example.test/source"
CANONICAL = (
    "A hidden fee changes the apparent price because the displayed amount "
    "excludes a mandatory charge."
)
EXCERPT = "A hidden fee changes the apparent price"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def seed_c2_research(storage, account, *, topic_title: str = "The hidden fee") -> dict[str, object]:
    storage.ensure_account(account)
    topic = storage.add_topic(account.id, Topic(
        account_id=account.id,
        title=topic_title,
        question="Why does the price change?",
        status=TopicStatus.SELECTED,
    ))
    assert topic.id is not None
    card = storage.conn.execute(
        "INSERT INTO research_cards (topic_id,question,thesis,mechanism,facts_json,"
        "counterargument,citable_numbers,visual_idea,confidence,working_thesis,"
        "confirmed_claims,uncertain_claims,contradictions,source_quality_score,"
        "publication_recommendation,rejection_reason,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            topic.id, "Why does the price change?", "Fees hide the mechanism.",
            "Mandatory charges are excluded.", "[]", "The fee is disclosed.",
            "[]", "A split receipt", 0.9, "Fees hide the mechanism.",
            json.dumps([CLAIM]), "[]", "[]", 0.95, "PROCEED", None,
            "2026-07-23 11:00:00",
        ),
    )
    card_id = int(card.lastrowid)
    source = storage.conn.execute(
        "INSERT INTO sources (research_card_id,url,title,source_type,verified,"
        "author_or_org,supports_claim,verification_status) "
        "VALUES (?,?,?,'PRIMARY',1,'Example Org',?,'VERIFIED')",
        (card_id, URL, "Source", CLAIM),
    )
    source_id = int(source.lastrowid)
    retrieval = storage.conn.execute(
        "INSERT INTO evidence_retrievals (account_id,requested_url,final_url,"
        "fetched_at,status,http_status,content_type,fetch_error,raw_size_bytes,"
        "raw_sha256,extracted_chars,extracted_sha256,canonical_text,"
        "canonical_chars,canonical_sha256,truncated,created_at) "
        "VALUES (?,?,?,'2026-07-23 11:01:00','OK',200,'text/plain',NULL,"
        "?,?,?,?,?,?,?,0,'2026-07-23 11:01:00')",
        (
            account.id, URL, URL, len(CANONICAL.encode()), sha(CANONICAL),
            len(CANONICAL), sha(CANONICAL), CANONICAL, len(CANONICAL),
            sha(CANONICAL),
        ),
    )
    retrieval_id = int(retrieval.lastrowid)
    excerpt = storage.conn.execute(
        "INSERT INTO evidence_excerpts (account_id,retrieval_id,claim_text,"
        "claim_sha256,excerpt_text,start_offset,end_offset,created_at) "
        "VALUES (?,?,?,?,?,?,?,'2026-07-23 11:02:00')",
        (
            account.id, retrieval_id, CLAIM, sha(CLAIM), EXCERPT, 0, len(EXCERPT),
        ),
    )
    excerpt_id = int(excerpt.lastrowid)
    research_run_id = f"research-run-c2-{topic.id}"
    research_job_id = f"research-job-c2-{topic.id}"
    storage.conn.execute(
        "INSERT INTO runs (id,account_id,workflow,status,current_state,started_at,"
        "finished_at,cost_usd,human_intervention_count) "
        "VALUES (?,?,'RESEARCH','DRY_RUN','COMPLETE','2026-07-23 10:00:00',"
        "'2026-07-23 11:03:00',0,0)",
        (research_run_id, account.id),
    )
    storage.conn.execute(
        "INSERT INTO research_runs (id,account_id,topic_id,flow,status,"
        "research_card_id,total_cost_usd,created_at,updated_at) "
        "VALUES (?,?,?,'staged','COMPLETE',?,0,"
        "'2026-07-23 10:00:00','2026-07-23 11:03:00')",
        (research_run_id, account.id, topic.id, card_id),
    )
    storage.conn.execute(
        "INSERT INTO jobs (id,account_id,kind,workflow,status,idempotency_key,"
        "topic_id,run_id,payload_json,schedule_reason,earliest_run_at,attempts,"
        "max_attempts,reserved_cost_usd,created_at,finished_at,updated_at) "
        "VALUES (?,?,'RESEARCH','RESEARCH','DONE',?,?,?,?,'WITHIN_EDITORIAL_WINDOW',"
        "'2026-07-23 10:00:00',1,1,0,'2026-07-23 10:00:00',"
        "'2026-07-23 11:03:00','2026-07-23 11:03:00')",
        (
            research_job_id, account.id, f"idem-{research_job_id}", topic.id,
            research_run_id,
            json.dumps({"execution": "offline_evidence_v1", "dry_run": 1}),
        ),
    )
    candidate = storage.conn.execute(
        "INSERT INTO research_source_candidates (research_run_id,url,title,"
        "verification_status,status,source_quality_score,attempts) "
        "VALUES (?,?,?,'VERIFIED','EXTRACTED',0.95,1)",
        (research_run_id, URL, "Source"),
    )
    candidate_id = int(candidate.lastrowid)
    storage.conn.execute(
        "INSERT INTO evidence_candidate_retrievals (candidate_id,research_run_id,"
        "account_id,retrieval_id,created_at) VALUES (?,?,?,?,?)",
        (candidate_id, research_run_id, account.id, retrieval_id, "2026-07-23 11:01:00"),
    )
    storage.conn.execute(
        "INSERT INTO evidence_candidate_excerpts (candidate_id,research_run_id,"
        "account_id,retrieval_id,excerpt_id,created_at) VALUES (?,?,?,?,?,?)",
        (
            candidate_id, research_run_id, account.id, retrieval_id, excerpt_id,
            "2026-07-23 11:02:00",
        ),
    )
    claim_id = f"research-card:{card_id}:confirmed-claim:0"
    lineage = {
        "account_id": account.id,
        "candidate_id": candidate_id,
        "confirmed_claim_id": claim_id,
        "confirmed_claim_ordinal": 0,
        "excerpt_id": excerpt_id,
        "research_card_id": card_id,
        "research_job_id": research_job_id,
        "research_run_id": research_run_id,
        "retrieval_id": retrieval_id,
        "source_id": source_id,
        "topic_id": int(topic.id),
    }
    lineage_fingerprint = sha(json.dumps(
        lineage, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ))
    storage.conn.execute(
        "INSERT INTO evidence_source_lineage (source_id,research_card_id,"
        "candidate_id,research_run_id,account_id,retrieval_id,excerpt_id,"
        "created_at,confirmed_claim_ordinal,confirmed_claim_id,"
        "confirmed_claim_sha256,research_job_id,topic_id,lineage_fingerprint) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            source_id, card_id, candidate_id, research_run_id, account.id,
            retrieval_id, excerpt_id, "2026-07-23 11:03:00", 0, claim_id,
            sha(CLAIM), research_job_id, topic.id, lineage_fingerprint,
        ),
    )
    storage.conn.commit()
    return {
        "account_id": account.id,
        "topic_id": topic.id,
        "card_id": card_id,
        "claim_id": claim_id,
    }
