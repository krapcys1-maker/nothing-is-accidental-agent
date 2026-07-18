-- Stage 2 / Wave E2-A: minimal durable lineage for the explicitly offline
-- staged evidence integration spine. Existing evidence rows remain append-only.

CREATE TABLE evidence_candidate_retrievals (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL UNIQUE
        REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19)
);

CREATE TABLE evidence_candidate_excerpts (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL UNIQUE
        REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    excerpt_id INTEGER NOT NULL UNIQUE
        REFERENCES evidence_excerpts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19)
);

CREATE TABLE evidence_source_lineage (
    source_id INTEGER PRIMARY KEY REFERENCES sources(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    candidate_id INTEGER NOT NULL UNIQUE
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    excerpt_id INTEGER NOT NULL UNIQUE REFERENCES evidence_excerpts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19)
);

-- A retrieval link must join the exact account/run/candidate/job chain and URL.
-- json_extract also makes this relation exclusive to the versioned E2-A intent.
CREATE TRIGGER evidence_candidate_retrievals_integrity
BEFORE INSERT ON evidence_candidate_retrievals
WHEN NOT EXISTS (
    SELECT 1
    FROM research_source_candidates c
    JOIN research_runs rr ON rr.id = c.research_run_id
    JOIN runs r ON r.id = rr.id
    JOIN jobs j ON j.run_id = rr.id
    JOIN evidence_retrievals er ON er.id = NEW.retrieval_id
    WHERE c.id = NEW.candidate_id
      AND c.research_run_id = NEW.research_run_id
      AND rr.account_id = NEW.account_id
      AND r.account_id = NEW.account_id
      AND r.workflow = 'RESEARCH'
      AND j.account_id = NEW.account_id
      AND j.topic_id = rr.topic_id
      AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH'
      AND json_extract(j.payload_json, '$.execution') = 'offline_evidence_v1'
      AND json_extract(j.payload_json, '$.dry_run') = 1
      AND er.account_id = NEW.account_id
      AND er.requested_url = c.url
)
BEGIN
    SELECT RAISE(ABORT, 'invalid account/run/candidate/retrieval evidence lineage');
END;

CREATE TRIGGER evidence_candidate_excerpts_integrity
BEFORE INSERT ON evidence_candidate_excerpts
WHEN NOT EXISTS (
    SELECT 1
    FROM evidence_candidate_retrievals cr
    JOIN evidence_excerpts ee ON ee.id = NEW.excerpt_id
    WHERE cr.candidate_id = NEW.candidate_id
      AND cr.research_run_id = NEW.research_run_id
      AND cr.account_id = NEW.account_id
      AND cr.retrieval_id = NEW.retrieval_id
      AND ee.account_id = NEW.account_id
      AND ee.retrieval_id = NEW.retrieval_id
)
BEGIN
    SELECT RAISE(ABORT, 'invalid candidate/retrieval/excerpt evidence lineage');
END;

CREATE TRIGGER evidence_source_lineage_integrity
BEFORE INSERT ON evidence_source_lineage
WHEN NOT EXISTS (
    SELECT 1
    FROM evidence_candidate_excerpts ce
    JOIN research_source_candidates c ON c.id = ce.candidate_id
    JOIN research_runs rr ON rr.id = ce.research_run_id
    JOIN research_cards rc ON rc.id = NEW.research_card_id
    JOIN sources s ON s.id = NEW.source_id
    WHERE ce.candidate_id = NEW.candidate_id
      AND ce.research_run_id = NEW.research_run_id
      AND ce.account_id = NEW.account_id
      AND ce.retrieval_id = NEW.retrieval_id
      AND ce.excerpt_id = NEW.excerpt_id
      AND c.status = 'EXTRACTED'
      AND c.verification_status = 'VERIFIED'
      AND rr.account_id = NEW.account_id
      AND rr.topic_id = rc.topic_id
      AND s.research_card_id = rc.id
      AND s.url = c.url
      AND s.verification_status = 'VERIFIED'
)
BEGIN
    SELECT RAISE(ABORT, 'invalid evidence-to-research-card source lineage');
END;

CREATE TRIGGER evidence_candidate_retrievals_no_update
BEFORE UPDATE ON evidence_candidate_retrievals
BEGIN SELECT RAISE(ABORT, 'evidence_candidate_retrievals is append-only'); END;
CREATE TRIGGER evidence_candidate_retrievals_no_delete
BEFORE DELETE ON evidence_candidate_retrievals
BEGIN SELECT RAISE(ABORT, 'evidence_candidate_retrievals is append-only'); END;
CREATE TRIGGER evidence_candidate_excerpts_no_update
BEFORE UPDATE ON evidence_candidate_excerpts
BEGIN SELECT RAISE(ABORT, 'evidence_candidate_excerpts is append-only'); END;
CREATE TRIGGER evidence_candidate_excerpts_no_delete
BEFORE DELETE ON evidence_candidate_excerpts
BEGIN SELECT RAISE(ABORT, 'evidence_candidate_excerpts is append-only'); END;
CREATE TRIGGER evidence_source_lineage_no_update
BEFORE UPDATE ON evidence_source_lineage
BEGIN SELECT RAISE(ABORT, 'evidence_source_lineage is append-only'); END;
CREATE TRIGGER evidence_source_lineage_no_delete
BEFORE DELETE ON evidence_source_lineage
BEGIN SELECT RAISE(ABORT, 'evidence_source_lineage is append-only'); END;
