-- A frozen evidence retrieval/excerpt is immutable evidence identity, not the
-- identity of one research run.  Re-research must therefore be able to bind
-- the same retrieval and verified excerpt into a different run while keeping
-- every link unique inside that run.

PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;
BEGIN IMMEDIATE;

DROP TRIGGER evidence_candidate_retrievals_integrity;
DROP TRIGGER evidence_candidate_retrievals_no_update;
DROP TRIGGER evidence_candidate_retrievals_no_delete;
DROP TRIGGER evidence_candidate_excerpts_integrity;
DROP TRIGGER evidence_candidate_excerpts_no_update;
DROP TRIGGER evidence_candidate_excerpts_no_delete;
DROP TRIGGER evidence_source_lineage_integrity;
DROP TRIGGER evidence_source_lineage_claim_identity;
DROP TRIGGER evidence_source_lineage_no_update;
DROP TRIGGER evidence_source_lineage_no_delete;

CREATE TABLE evidence_candidate_retrievals_0037_new (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL
        REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    UNIQUE (research_run_id, retrieval_id)
);

CREATE TABLE evidence_candidate_excerpts_0037_new (
    candidate_id INTEGER PRIMARY KEY
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL
        REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    excerpt_id INTEGER NOT NULL
        REFERENCES evidence_excerpts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    UNIQUE (research_run_id, retrieval_id),
    UNIQUE (research_run_id, excerpt_id)
);

CREATE TABLE evidence_source_lineage_0037_new (
    source_id INTEGER PRIMARY KEY REFERENCES sources(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    candidate_id INTEGER NOT NULL UNIQUE
        REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    retrieval_id INTEGER NOT NULL REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    excerpt_id INTEGER NOT NULL REFERENCES evidence_excerpts(id) ON DELETE RESTRICT,
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    confirmed_claim_ordinal INTEGER CHECK (confirmed_claim_ordinal >= 0),
    confirmed_claim_id TEXT,
    confirmed_claim_sha256 TEXT,
    research_job_id TEXT REFERENCES jobs(id) ON DELETE RESTRICT,
    topic_id INTEGER REFERENCES topics(id) ON DELETE RESTRICT,
    lineage_fingerprint TEXT,
    UNIQUE (research_run_id, excerpt_id)
);

INSERT INTO evidence_candidate_retrievals_0037_new
SELECT * FROM evidence_candidate_retrievals;
INSERT INTO evidence_candidate_excerpts_0037_new
SELECT * FROM evidence_candidate_excerpts;
INSERT INTO evidence_source_lineage_0037_new
SELECT * FROM evidence_source_lineage;

DROP TABLE evidence_source_lineage;
DROP TABLE evidence_candidate_excerpts;
DROP TABLE evidence_candidate_retrievals;
ALTER TABLE evidence_candidate_retrievals_0037_new
    RENAME TO evidence_candidate_retrievals;
ALTER TABLE evidence_candidate_excerpts_0037_new
    RENAME TO evidence_candidate_excerpts;
ALTER TABLE evidence_source_lineage_0037_new
    RENAME TO evidence_source_lineage;

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
      AND r.account_id = NEW.account_id AND r.workflow = 'RESEARCH'
      AND j.account_id = NEW.account_id AND j.topic_id = rr.topic_id
      AND j.kind = 'RESEARCH' AND j.workflow = 'RESEARCH'
      AND er.account_id = NEW.account_id
      AND (
        (json_extract(j.payload_json, '$.execution') = 'offline_evidence_v1'
         AND json_extract(j.payload_json, '$.dry_run') = 1
         AND er.requested_url = c.url)
        OR
        (json_extract(j.payload_json, '$.execution_intent.evidence_input') IS NOT NULL
         AND (er.requested_url = c.url OR er.final_url = c.url))
      )
)
BEGIN SELECT RAISE(ABORT, 'invalid account/run/candidate/retrieval evidence lineage'); END;

CREATE TRIGGER evidence_candidate_excerpts_integrity
BEFORE INSERT ON evidence_candidate_excerpts
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_candidate_retrievals cr
    JOIN evidence_excerpts ee ON ee.id = NEW.excerpt_id
    WHERE cr.candidate_id = NEW.candidate_id
      AND cr.research_run_id = NEW.research_run_id
      AND cr.account_id = NEW.account_id
      AND cr.retrieval_id = NEW.retrieval_id
      AND ee.account_id = NEW.account_id
      AND ee.retrieval_id = NEW.retrieval_id
)
BEGIN SELECT RAISE(ABORT, 'invalid candidate/retrieval/excerpt evidence lineage'); END;

CREATE TRIGGER evidence_source_lineage_integrity
BEFORE INSERT ON evidence_source_lineage
WHEN NOT EXISTS (
    SELECT 1 FROM evidence_candidate_excerpts ce
    JOIN research_source_candidates c ON c.id = ce.candidate_id
    JOIN research_runs rr ON rr.id = ce.research_run_id
    JOIN research_cards rc ON rc.id = NEW.research_card_id
    JOIN sources s ON s.id = NEW.source_id
    WHERE ce.candidate_id = NEW.candidate_id
      AND ce.research_run_id = NEW.research_run_id
      AND ce.account_id = NEW.account_id
      AND ce.retrieval_id = NEW.retrieval_id
      AND ce.excerpt_id = NEW.excerpt_id
      AND c.status = 'EXTRACTED' AND c.verification_status = 'VERIFIED'
      AND rr.account_id = NEW.account_id AND rr.topic_id = rc.topic_id
      AND s.research_card_id = rc.id AND s.url = c.url
      AND s.verification_status = 'VERIFIED'
)
BEGIN SELECT RAISE(ABORT, 'invalid evidence-to-research-card source lineage'); END;

CREATE TRIGGER evidence_source_lineage_claim_identity
BEFORE INSERT ON evidence_source_lineage
WHEN NEW.confirmed_claim_ordinal IS NULL
 OR NEW.confirmed_claim_id IS NULL
 OR NEW.confirmed_claim_sha256 IS NULL
 OR NEW.research_job_id IS NULL
 OR NEW.topic_id IS NULL
 OR NEW.lineage_fingerprint IS NULL
 OR NOT EXISTS (
    SELECT 1 FROM research_cards rc
    JOIN sources s ON s.id = NEW.source_id
    JOIN research_runs rr ON rr.id = NEW.research_run_id
    JOIN jobs j ON j.id = NEW.research_job_id
    JOIN json_each(COALESCE(rc.confirmed_claims,'[]')) claim
    WHERE rc.id = NEW.research_card_id
      AND s.research_card_id = rc.id
      AND rr.id = NEW.research_run_id
      AND rr.topic_id = NEW.topic_id AND rr.account_id = NEW.account_id
      AND j.run_id = rr.id AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH' AND j.account_id = NEW.account_id
      AND CAST(claim.key AS INTEGER) = NEW.confirmed_claim_ordinal
      AND claim.type = 'text'
      AND evidence_sha256_hex(claim.value) = NEW.confirmed_claim_sha256
      AND NEW.confirmed_claim_id = printf(
          'research-card:%d:confirmed-claim:%d',
          NEW.research_card_id, NEW.confirmed_claim_ordinal
      )
      AND NEW.lineage_fingerprint = evidence_sha256_hex(json_object(
          'account_id',NEW.account_id,
          'candidate_id',NEW.candidate_id,
          'confirmed_claim_id',NEW.confirmed_claim_id,
          'confirmed_claim_ordinal',NEW.confirmed_claim_ordinal,
          'excerpt_id',NEW.excerpt_id,
          'research_card_id',NEW.research_card_id,
          'research_job_id',NEW.research_job_id,
          'research_run_id',NEW.research_run_id,
          'retrieval_id',NEW.retrieval_id,
          'source_id',NEW.source_id,
          'topic_id',NEW.topic_id
      ))
)
BEGIN SELECT RAISE(ABORT, 'invalid durable confirmed-claim evidence lineage'); END;

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

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0037_evidence_reresearch_lineage', datetime('now'));
COMMIT;
PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
