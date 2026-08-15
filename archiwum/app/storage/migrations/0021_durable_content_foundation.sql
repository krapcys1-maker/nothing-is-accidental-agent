-- Stage 3 / Wave C1: durable content foundation only.
--
-- This migration deliberately adds no planner, writer, audit implementation,
-- approval workflow, provider call, browser or publication path.  It provides:
--   * one CONTENT job kind inside the existing jobs/runs infrastructure;
--   * a frozen Research Card + evidence manifest snapshot;
--   * a closed Stage 3 content lifecycle and one-to-one content run;
--   * a pre-network call intent and strict canonical-ledger extension;
--   * minimal fact/style/growth evaluation storage.
-- No provider caller or external request path is added.
--
-- `jobs` must be rebuilt because its current CHECK(kind) is closed.  The
-- migration therefore owns its transaction (foreign_keys=OFF must be set
-- before BEGIN) and writes its own schema_migrations row in the same COMMIT.
-- app.storage.db treats this version as self-ledgered and never writes a second
-- ledger row.
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

BEGIN IMMEDIATE;

-- ---- 1. Existing queue, extended by one non-public CONTENT kind ------------

ALTER TABLE jobs RENAME TO jobs_0020_old;

CREATE TABLE jobs (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL CHECK (
                            kind IN ('LOCAL','RESEARCH','BROWSER','TOPIC_GENERATION','CONTENT')
                        ),
    workflow            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'QUEUED'
                            CHECK (status IN (
                                'QUEUED','LEASED','RUNNING','DONE','FAILED',
                                'NEEDS_VERIFICATION','CANCELLED'
                            )),
    priority            INTEGER NOT NULL DEFAULT 0,
    idempotency_key     TEXT NOT NULL UNIQUE,
    topic_id            INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    run_id              TEXT REFERENCES runs(id) ON DELETE SET NULL,
    payload_json        TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload_json)),
    schedule_reason     TEXT NOT NULL DEFAULT '',
    earliest_run_at     TEXT NOT NULL,
    deadline_at         TEXT,
    lease_owner         TEXT,
    lease_expires_at    TEXT,
    execution_generation INTEGER NOT NULL DEFAULT 0
                            CHECK (execution_generation >= 0),
    attempts            INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts        INTEGER NOT NULL DEFAULT 1 CHECK (max_attempts >= 1),
    reserved_cost_usd   REAL NOT NULL DEFAULT 0.0 CHECK (reserved_cost_usd >= 0),
    budget_reserved_at  TEXT,
    external_effect_started_at TEXT,
    last_error          TEXT,
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    finished_at         TEXT,
    updated_at          TEXT NOT NULL,
    CHECK (attempts <= max_attempts),
    CHECK (kind != 'RESEARCH' OR topic_id IS NOT NULL),
    CHECK (kind != 'TOPIC_GENERATION' OR topic_id IS NULL),
    CHECK (
        kind != 'CONTENT'
        OR (topic_id IS NOT NULL AND workflow IN ('ARTICLE','NOTE'))
    ),
    CHECK (
        (status IN ('LEASED','RUNNING')
            AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status NOT IN ('LEASED','RUNNING')
            AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);

INSERT INTO jobs (
    id,account_id,kind,workflow,status,priority,idempotency_key,topic_id,run_id,
    payload_json,schedule_reason,earliest_run_at,deadline_at,lease_owner,
    lease_expires_at,execution_generation,attempts,max_attempts,reserved_cost_usd,budget_reserved_at,
    external_effect_started_at,last_error,created_at,started_at,finished_at,updated_at
)
SELECT
    id,account_id,kind,workflow,status,priority,idempotency_key,topic_id,run_id,
    payload_json,schedule_reason,earliest_run_at,deadline_at,lease_owner,
    lease_expires_at,0,attempts,max_attempts,reserved_cost_usd,budget_reserved_at,
    external_effect_started_at,last_error,created_at,started_at,finished_at,updated_at
FROM jobs_0020_old;

DROP TABLE jobs_0020_old;

CREATE INDEX ix_jobs_active_reservations
    ON jobs(status,budget_reserved_at)
    WHERE budget_reserved_at IS NOT NULL;
CREATE INDEX ix_jobs_claimable
    ON jobs(status,earliest_run_at,priority DESC,deadline_at,created_at);
CREATE UNIQUE INDEX ux_jobs_active_research_topic
    ON jobs(account_id,topic_id)
    WHERE kind='RESEARCH' AND topic_id IS NOT NULL
      AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION');
CREATE UNIQUE INDEX ux_jobs_active_topic_generation_account
    ON jobs(account_id)
    WHERE kind='TOPIC_GENERATION'
      AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION');
CREATE UNIQUE INDEX ux_jobs_active_content_intent
    ON jobs(json_extract(payload_json,'$.intent_key'))
    WHERE kind='CONTENT'
      AND status IN ('QUEUED','LEASED','RUNNING','NEEDS_VERIFICATION');

-- Recreate every jobs trigger present at 0020.
CREATE TRIGGER jobs_terminal_requires_provider_attempt_normalized
BEFORE UPDATE OF status ON jobs
WHEN NEW.status IN ('DONE','FAILED','CANCELLED') AND NEW.status IS NOT OLD.status
 AND EXISTS (
   SELECT 1 FROM provider_attempts p
   WHERE p.job_id=OLD.id AND p.status IN ('RESERVED','REQUEST_STARTED')
 )
BEGIN SELECT RAISE(ABORT, 'terminal job requires provider_attempt normalization'); END;

CREATE TRIGGER jobs_settled_recovery_requires_event
BEFORE UPDATE OF status ON jobs
WHEN OLD.status='NEEDS_VERIFICATION' AND NEW.status IN ('DONE','FAILED')
 AND EXISTS (SELECT 1 FROM provider_attempts p WHERE p.job_id=OLD.id AND p.status='SETTLED')
 AND NOT EXISTS (
     SELECT 1 FROM provider_attempts p JOIN reconciliation_events e ON e.request_id=p.request_id
     WHERE p.job_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
       AND ((NEW.status='DONE' AND e.execution_resolution='RESULT_ALREADY_FINALIZED')
            OR (NEW.status='FAILED' AND e.execution_resolution='EXECUTION_FAILED'))
 )
BEGIN SELECT RAISE(ABORT, 'settled execution terminalization requires EXECUTION_RECOVERY event'); END;

CREATE TRIGGER jobs_execution_recovery_terminal_is_immutable
BEFORE UPDATE OF status,run_id,reserved_cost_usd,budget_reserved_at,lease_owner,lease_expires_at,external_effect_started_at ON jobs
WHEN OLD.status IN ('DONE','FAILED')
 AND (NEW.status IS NOT OLD.status OR NEW.run_id IS NOT OLD.run_id
      OR NEW.reserved_cost_usd IS NOT OLD.reserved_cost_usd
      OR NEW.budget_reserved_at IS NOT OLD.budget_reserved_at
      OR NEW.lease_owner IS NOT OLD.lease_owner
      OR NEW.lease_expires_at IS NOT OLD.lease_expires_at
      OR NEW.external_effect_started_at IS NOT OLD.external_effect_started_at)
 AND EXISTS (
    SELECT 1 FROM provider_attempts p JOIN reconciliation_events e ON e.request_id=p.request_id
    WHERE p.job_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
 )
BEGIN SELECT RAISE(ABORT, 'terminal job of a recovered settled execution is immutable'); END;

CREATE TRIGGER jobs_controlled_fetch_payload_frozen
BEFORE UPDATE OF payload_json ON jobs
WHEN (
    json_extract(OLD.payload_json,'$.execution')='controlled_fetch_v1'
    OR json_extract(NEW.payload_json,'$.execution')='controlled_fetch_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN SELECT RAISE(ABORT, 'controlled_fetch_v1 job payload is immutable'); END;

CREATE TRIGGER jobs_controlled_fetch_terminal_requires_resolved_attempt
BEFORE UPDATE OF status ON jobs
WHEN NEW.status IN ('DONE','FAILED','CANCELLED','NEEDS_VERIFICATION')
 AND EXISTS (
    SELECT 1 FROM controlled_fetch_attempts a
    WHERE a.job_id=NEW.id AND a.status IN ('RESERVED','REQUEST_STARTED')
 )
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch job cannot terminalize with an unresolved fetch attempt');
END;

CREATE TRIGGER jobs_controlled_fetch_done_requires_succeeded_attempt
BEFORE UPDATE OF status ON jobs
WHEN NEW.status='DONE'
 AND json_extract(NEW.payload_json,'$.execution')='controlled_fetch_v1'
 AND NOT EXISTS (
    SELECT 1 FROM controlled_fetch_attempts a
    WHERE a.job_id=NEW.id AND a.status='SUCCEEDED'
 )
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch job DONE requires exactly one SUCCEEDED fetch attempt');
END;

CREATE TRIGGER jobs_topic_generation_payload_frozen
BEFORE UPDATE OF payload_json ON jobs
WHEN (
    json_extract(OLD.payload_json,'$.execution')='durable_topic_generation_v1'
    OR json_extract(NEW.payload_json,'$.execution')='durable_topic_generation_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN SELECT RAISE(ABORT, 'durable_topic_generation_v1 job payload is immutable'); END;

CREATE TRIGGER jobs_content_payload_frozen
BEFORE UPDATE OF payload_json ON jobs
WHEN (
    json_extract(OLD.payload_json,'$.execution')='durable_content_foundation_v1'
    OR json_extract(NEW.payload_json,'$.execution')='durable_content_foundation_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN SELECT RAISE(ABORT, 'durable content job payload is immutable'); END;

-- ---- 2. Preserve the 0001 table surface, add the C1 durable identity --------

ALTER TABLE content_items RENAME TO content_items_0020_old;

CREATE TABLE content_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    type              TEXT NOT NULL CHECK (type IN ('ARTICLE','NOTE')),
    title             TEXT,
    subtitle          TEXT,
    body              TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'DRAFT' CHECK (status IN (
                          'DRAFT','PREPARED','RUNNING','REVISE','SKIPPED',
                          'PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION',
                          -- Historical publication states retained solely so a
                          -- pre-0021 row can migrate without data rewriting.
                          'APPROVED','REJECTED','QUEUED','PUBLISHING',
                          'PUBLISHED','UNCERTAIN'
                      )),
    score             REAL CHECK (score IS NULL OR (
                          typeof(score) IN ('integer','real')
                          AND score=score AND score BETWEEN 0 AND 1
                      )),
    duplicate_score   REAL CHECK (duplicate_score IS NULL OR (
                          typeof(duplicate_score) IN ('integer','real')
                          AND duplicate_score=duplicate_score
                          AND duplicate_score BETWEEN 0 AND 1
                      )),
    research_card_id  INTEGER REFERENCES research_cards(id) ON DELETE RESTRICT,
    job_id            TEXT UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id            TEXT UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    input_sha256      TEXT CHECK (input_sha256 IS NULL OR (
                          length(input_sha256)=64
                          AND input_sha256 NOT GLOB '*[^0-9a-f]*'
                      )),
    intent_key        TEXT UNIQUE CHECK (intent_key IS NULL OR (
                          length(intent_key)=64
                          AND intent_key NOT GLOB '*[^0-9a-f]*'
                      )),
    reason_code       TEXT,
    final_result_json TEXT CHECK (
                          final_result_json IS NULL OR json_valid(final_result_json)
                      ),
    scheduled_at      TEXT,
    published_at      TEXT,
    external_url      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL,
    CHECK (
        status NOT IN (
            'DRAFT','PREPARED','RUNNING','REVISE','SKIPPED',
            'PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION'
        )
        OR status = 'DRAFT'
        OR (
            research_card_id IS NOT NULL
            AND job_id IS NOT NULL
            AND input_sha256 IS NOT NULL
            AND intent_key IS NOT NULL
        )
    ),
    CHECK (
        (status IN ('SKIPPED','FAILED','NEEDS_VERIFICATION','REVISE')
            AND reason_code IS NOT NULL AND length(trim(reason_code)) BETWEEN 1 AND 100)
        OR
        (status IN ('DRAFT','PREPARED','RUNNING','PENDING_APPROVAL')
            AND reason_code IS NULL)
        OR
        status IN ('APPROVED','REJECTED','QUEUED','PUBLISHING','PUBLISHED','UNCERTAIN')
    )
);

INSERT INTO content_items (
    id,account_id,type,title,subtitle,body,status,score,duplicate_score,
    research_card_id,scheduled_at,published_at,external_url,created_at,updated_at
)
SELECT
    id,account_id,type,title,subtitle,body,status,score,duplicate_score,
    research_card_id,scheduled_at,published_at,external_url,created_at,created_at
FROM content_items_0020_old;

DROP TABLE content_items_0020_old;

CREATE INDEX ix_content_account ON content_items(account_id,type,status);
CREATE INDEX ix_content_research_card ON content_items(account_id,research_card_id,type);

-- ---- 3. Frozen input and normalized evidence lineage -----------------------

-- 0017 linked a final source to the exact candidate/retrieval/excerpt chain,
-- but the Research Card claim was still implicit in mutable text.  Extend that
-- one authoritative lineage in place; do not create a parallel evidence graph.
DROP TRIGGER evidence_source_lineage_no_update;

ALTER TABLE evidence_source_lineage
    ADD COLUMN confirmed_claim_ordinal INTEGER CHECK (confirmed_claim_ordinal>=0);
ALTER TABLE evidence_source_lineage
    ADD COLUMN confirmed_claim_id TEXT;
ALTER TABLE evidence_source_lineage
    ADD COLUMN confirmed_claim_sha256 TEXT;
ALTER TABLE evidence_source_lineage
    ADD COLUMN research_job_id TEXT REFERENCES jobs(id) ON DELETE RESTRICT;
ALTER TABLE evidence_source_lineage
    ADD COLUMN topic_id INTEGER REFERENCES topics(id) ON DELETE RESTRICT;
ALTER TABLE evidence_source_lineage
    ADD COLUMN lineage_fingerprint TEXT;

-- Rows created before 0021 do not contain an authoritative confirmed-claim
-- key.  They remain immutable history with NULL extension columns and are not
-- eligible for content snapshots.  In particular, 0021 never fabricates that
-- missing identity by comparing claim text, source text, URLs, or row order.
-- Every new lineage row must provide the explicit keys checked below.

CREATE TRIGGER evidence_source_lineage_claim_identity
BEFORE INSERT ON evidence_source_lineage
WHEN NEW.confirmed_claim_ordinal IS NULL
 OR NEW.confirmed_claim_id IS NULL
 OR NEW.confirmed_claim_sha256 IS NULL
 OR NEW.research_job_id IS NULL
 OR NEW.topic_id IS NULL
 OR NEW.lineage_fingerprint IS NULL
 OR NOT EXISTS (
    SELECT 1
    FROM research_cards rc
    JOIN sources s ON s.id=NEW.source_id
    JOIN research_runs rr ON rr.id=NEW.research_run_id
    JOIN jobs j ON j.id=NEW.research_job_id
    JOIN json_each(COALESCE(rc.confirmed_claims,'[]')) claim
    WHERE rc.id=NEW.research_card_id
      AND s.research_card_id=rc.id
      AND rr.id=NEW.research_run_id
      AND rr.topic_id=NEW.topic_id
      AND rr.account_id=NEW.account_id
      AND j.run_id=rr.id
      AND j.kind='RESEARCH'
      AND j.workflow='RESEARCH'
      AND j.account_id=NEW.account_id
      AND CAST(claim.key AS INTEGER)=NEW.confirmed_claim_ordinal
      AND claim.type='text'
      AND evidence_sha256_hex(claim.value)=NEW.confirmed_claim_sha256
      AND NEW.confirmed_claim_id=printf(
          'research-card:%d:confirmed-claim:%d',
          NEW.research_card_id, NEW.confirmed_claim_ordinal
      )
      AND NEW.lineage_fingerprint=evidence_sha256_hex(json_object(
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

CREATE TRIGGER evidence_source_lineage_no_update
BEFORE UPDATE ON evidence_source_lineage
BEGIN SELECT RAISE(ABORT, 'evidence_source_lineage is append-only'); END;

CREATE TABLE content_frozen_inputs (
    content_id INTEGER PRIMARY KEY REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    input_schema_version TEXT NOT NULL CHECK (length(trim(input_schema_version)) BETWEEN 1 AND 100),
    output_schema_version TEXT NOT NULL CHECK (length(trim(output_schema_version)) BETWEEN 1 AND 100),
    prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
    style_guide_version TEXT NOT NULL CHECK (length(trim(style_guide_version)) BETWEEN 1 AND 200),
    article_brief_placeholder_json TEXT NOT NULL CHECK (json_valid(article_brief_placeholder_json)),
    article_brief_placeholder_sha256 TEXT NOT NULL CHECK (
        length(article_brief_placeholder_sha256)=64
        AND article_brief_placeholder_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    research_card_snapshot_json TEXT NOT NULL CHECK (json_valid(research_card_snapshot_json)),
    evidence_manifest_json TEXT NOT NULL CHECK (json_valid(evidence_manifest_json)),
    evidence_manifest_sha256 TEXT NOT NULL CHECK (
        length(evidence_manifest_sha256)=64
        AND evidence_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    evidence_item_count INTEGER NOT NULL CHECK (evidence_item_count > 0),
    input_snapshot_json TEXT NOT NULL CHECK (json_valid(input_snapshot_json)),
    input_sha256 TEXT NOT NULL UNIQUE CHECK (
        length(input_sha256)=64 AND input_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);

CREATE TABLE content_evidence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content_frozen_inputs(content_id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL CHECK (ordinal>=0),
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE RESTRICT,
    research_job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    confirmed_claim_id TEXT NOT NULL,
    confirmed_claim_ordinal INTEGER NOT NULL CHECK (confirmed_claim_ordinal>=0),
    claim_text TEXT NOT NULL CHECK (length(trim(claim_text))>0),
    claim_sha256 TEXT NOT NULL CHECK (
        length(claim_sha256)=64 AND claim_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    candidate_id INTEGER NOT NULL REFERENCES research_source_candidates(id) ON DELETE RESTRICT,
    source_id INTEGER NOT NULL REFERENCES evidence_source_lineage(source_id) ON DELETE RESTRICT,
    source_url TEXT NOT NULL CHECK (length(trim(source_url))>0),
    source_url_sha256 TEXT NOT NULL CHECK (
        length(source_url_sha256)=64 AND source_url_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    source_claim_text TEXT NOT NULL CHECK (length(trim(source_claim_text))>0),
    source_claim_sha256 TEXT NOT NULL CHECK (
        length(source_claim_sha256)=64 AND source_claim_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    excerpt_id INTEGER NOT NULL REFERENCES evidence_excerpts(id) ON DELETE RESTRICT,
    excerpt_text TEXT NOT NULL CHECK (length(excerpt_text)>0),
    excerpt_sha256 TEXT NOT NULL CHECK (
        length(excerpt_sha256)=64 AND excerpt_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    retrieval_id INTEGER NOT NULL REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    requested_url_sha256 TEXT NOT NULL CHECK (
        length(requested_url_sha256)=64 AND requested_url_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    final_url_sha256 TEXT NOT NULL CHECK (
        length(final_url_sha256)=64 AND final_url_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    canonical_sha256 TEXT NOT NULL CHECK (
        length(canonical_sha256)=64 AND canonical_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    lineage_fingerprint TEXT NOT NULL CHECK (
        length(lineage_fingerprint)=64
        AND lineage_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE(content_id,ordinal),
    UNIQUE(content_id,source_id,excerpt_id)
);
CREATE INDEX ix_content_evidence_claim
    ON content_evidence_items(content_id,claim_sha256);

CREATE TRIGGER content_frozen_inputs_authoritative_hashes
BEFORE INSERT ON content_frozen_inputs
WHEN NEW.article_brief_placeholder_sha256
        IS NOT evidence_sha256_hex(NEW.article_brief_placeholder_json)
 OR NEW.evidence_manifest_sha256
        IS NOT evidence_sha256_hex(NEW.evidence_manifest_json)
 OR NEW.input_sha256 IS NOT evidence_sha256_hex(NEW.input_snapshot_json)
BEGIN SELECT RAISE(ABORT, 'content frozen input hash does not match its preimage'); END;

CREATE TRIGGER content_frozen_inputs_bind_content
BEFORE INSERT ON content_frozen_inputs
WHEN NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN research_cards rc ON rc.id=NEW.research_card_id
    JOIN topics t ON t.id=rc.topic_id
    WHERE c.id=NEW.content_id
      AND c.account_id=NEW.account_id
      AND c.research_card_id=NEW.research_card_id
      AND c.type=NEW.content_type
      AND c.status='DRAFT'
      AND t.account_id=NEW.account_id
      AND rc.publication_recommendation='PROCEED'
)
BEGIN SELECT RAISE(ABORT, 'frozen content input must bind one account-scoped PROCEED card'); END;

CREATE TRIGGER content_evidence_items_authoritative_hashes
BEFORE INSERT ON content_evidence_items
WHEN NEW.claim_sha256 IS NOT evidence_sha256_hex(NEW.claim_text)
 OR NEW.source_url_sha256 IS NOT evidence_sha256_hex(NEW.source_url)
 OR NEW.source_claim_sha256 IS NOT evidence_sha256_hex(NEW.source_claim_text)
 OR NEW.excerpt_sha256 IS NOT evidence_sha256_hex(NEW.excerpt_text)
BEGIN SELECT RAISE(ABORT, 'content evidence item hash does not match its preimage'); END;

CREATE TRIGGER content_evidence_items_complete_lineage
BEFORE INSERT ON content_evidence_items
WHEN NOT EXISTS (
    SELECT 1
    FROM content_frozen_inputs fi
    JOIN evidence_source_lineage sl ON sl.source_id=NEW.source_id
    JOIN research_cards rc ON rc.id=fi.research_card_id
    JOIN topics t ON t.id=rc.topic_id
    JOIN research_runs rr ON rr.id=sl.research_run_id
    JOIN jobs rj ON rj.id=sl.research_job_id
    JOIN research_source_candidates c ON c.id=sl.candidate_id
    JOIN sources s ON s.id=sl.source_id
    JOIN evidence_excerpts ee ON ee.id=sl.excerpt_id
    JOIN evidence_retrievals er ON er.id=sl.retrieval_id
    WHERE fi.content_id=NEW.content_id
      AND fi.account_id=NEW.account_id
      AND fi.research_card_id=NEW.research_card_id
      AND t.account_id=NEW.account_id
      AND t.id=NEW.topic_id
      AND sl.account_id=NEW.account_id
      AND sl.research_card_id=NEW.research_card_id
      AND sl.topic_id=NEW.topic_id
      AND sl.research_run_id=NEW.research_run_id
      AND sl.research_job_id=NEW.research_job_id
      AND sl.candidate_id=NEW.candidate_id
      AND sl.excerpt_id=NEW.excerpt_id
      AND sl.retrieval_id=NEW.retrieval_id
      AND sl.confirmed_claim_id=NEW.confirmed_claim_id
      AND sl.confirmed_claim_ordinal=NEW.confirmed_claim_ordinal
      AND sl.lineage_fingerprint=NEW.lineage_fingerprint
      AND rr.account_id=NEW.account_id
      AND rr.topic_id=NEW.topic_id
      AND rj.run_id=NEW.research_run_id
      AND rj.account_id=NEW.account_id
      AND rj.topic_id=NEW.topic_id
      AND rj.kind='RESEARCH'
      AND rj.workflow='RESEARCH'
      AND c.research_run_id=NEW.research_run_id
      AND c.id=NEW.candidate_id
      AND s.research_card_id=NEW.research_card_id
      AND s.verification_status='VERIFIED'
      AND s.url=NEW.source_url
      AND ee.account_id=NEW.account_id
      AND ee.retrieval_id=NEW.retrieval_id
      AND ee.excerpt_text=NEW.excerpt_text
      AND er.account_id=NEW.account_id
      AND er.status='OK'
      AND er.canonical_sha256=NEW.canonical_sha256
      AND evidence_sha256_hex(er.requested_url)=NEW.requested_url_sha256
      AND evidence_sha256_hex(er.final_url)=NEW.final_url_sha256
      AND evidence_sha256_hex(json_extract(
          rc.confirmed_claims,
          '$[' || NEW.confirmed_claim_ordinal || ']'
      ))=NEW.claim_sha256
      AND sl.confirmed_claim_sha256=NEW.claim_sha256
      AND evidence_sha256_hex(s.supports_claim)=NEW.source_claim_sha256
      AND ee.claim_sha256=NEW.claim_sha256
)
BEGIN
    SELECT RAISE(ABORT,
        'content evidence must bind authoritative evidence_source_lineage keys');
END;

CREATE TRIGGER content_frozen_inputs_no_update
BEFORE UPDATE ON content_frozen_inputs
BEGIN SELECT RAISE(ABORT, 'content_frozen_inputs is append-only'); END;
CREATE TRIGGER content_frozen_inputs_no_delete
BEFORE DELETE ON content_frozen_inputs
BEGIN SELECT RAISE(ABORT, 'content_frozen_inputs is append-only'); END;
CREATE TRIGGER content_evidence_items_no_update
BEFORE UPDATE ON content_evidence_items
BEGIN SELECT RAISE(ABORT, 'content_evidence_items is append-only'); END;
CREATE TRIGGER content_evidence_items_no_delete
BEFORE DELETE ON content_evidence_items
BEGIN SELECT RAISE(ABORT, 'content_evidence_items is append-only'); END;

-- ---- 4. Job preparation and closed content lifecycle -----------------------

CREATE TRIGGER jobs_content_contract
BEFORE INSERT ON jobs
WHEN NEW.kind='CONTENT' AND NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN research_cards rc ON rc.id=c.research_card_id
    WHERE c.id=json_extract(NEW.payload_json,'$.content_id')
      AND c.account_id=NEW.account_id
      AND c.research_card_id=json_extract(NEW.payload_json,'$.research_card_id')
      AND c.type=NEW.workflow
      AND c.status='DRAFT'
      AND c.job_id IS NULL
      AND fi.account_id=NEW.account_id
      AND fi.input_sha256=json_extract(NEW.payload_json,'$.frozen_input_sha256')
      AND fi.evidence_manifest_sha256=json_extract(NEW.payload_json,'$.evidence_manifest_sha256')
      AND json_extract(NEW.payload_json,'$.execution')='durable_content_foundation_v1'
      AND json_extract(NEW.payload_json,'$.execution_mode')='FOUNDATION_ONLY'
      AND json_extract(NEW.payload_json,'$.provider_enabled')=0
      AND NEW.topic_id=rc.topic_id
)
BEGIN SELECT RAISE(ABORT, 'CONTENT job does not match its frozen content input'); END;

CREATE TRIGGER content_items_prepare_contract
BEFORE UPDATE OF status,job_id,input_sha256,intent_key ON content_items
WHEN OLD.status='DRAFT' AND NEW.status='PREPARED' AND NOT EXISTS (
    SELECT 1
    FROM content_frozen_inputs fi
    JOIN jobs j ON j.id=NEW.job_id
    WHERE fi.content_id=OLD.id
      AND fi.account_id=OLD.account_id
      AND fi.research_card_id=OLD.research_card_id
      AND fi.content_type=OLD.type
      AND fi.input_sha256=NEW.input_sha256
      AND fi.evidence_item_count=(
          SELECT count(*) FROM content_evidence_items e WHERE e.content_id=OLD.id
      )
      AND j.kind='CONTENT'
      AND j.account_id=OLD.account_id
      AND j.workflow=OLD.type
      AND json_extract(j.payload_json,'$.content_id')=OLD.id
      AND json_extract(j.payload_json,'$.frozen_input_sha256')=NEW.input_sha256
      AND json_extract(j.payload_json,'$.intent_key')=NEW.intent_key
)
BEGIN SELECT RAISE(ABORT, 'content preparation is incomplete or inconsistent'); END;

CREATE TRIGGER content_items_identity_immutable
BEFORE UPDATE OF account_id,type,research_card_id,job_id,input_sha256,intent_key,created_at ON content_items
WHEN OLD.status!='DRAFT'
 AND (
    NEW.account_id IS NOT OLD.account_id OR NEW.type IS NOT OLD.type
    OR NEW.research_card_id IS NOT OLD.research_card_id
    OR NEW.job_id IS NOT OLD.job_id
    OR NEW.input_sha256 IS NOT OLD.input_sha256
    OR NEW.intent_key IS NOT OLD.intent_key
    OR NEW.created_at IS NOT OLD.created_at
 )
BEGIN SELECT RAISE(ABORT, 'prepared content identity is immutable'); END;

CREATE TRIGGER content_items_closed_transition
BEFORE UPDATE OF status ON content_items
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status='DRAFT' AND NEW.status='PREPARED')
    OR
    (OLD.status='PREPARED' AND NEW.status IN (
        'RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='RUNNING' AND NEW.status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='REVISE' AND NEW.status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    -- Historical publication states are preserved but C1 never transitions
    -- into or out of them.
)
BEGIN SELECT RAISE(ABORT, 'illegal content item lifecycle transition'); END;

CREATE TRIGGER content_items_run_binding_once
BEFORE UPDATE OF run_id ON content_items
WHEN NOT (
    OLD.run_id IS NULL AND NEW.run_id IS NOT NULL
    AND EXISTS (
        SELECT 1 FROM content_runs cr
        WHERE cr.run_id=NEW.run_id AND cr.content_id=OLD.id
          AND cr.job_id=OLD.job_id AND cr.account_id=OLD.account_id
          AND cr.research_card_id=OLD.research_card_id
          AND cr.input_sha256=OLD.input_sha256
    )
)
BEGIN SELECT RAISE(ABORT, 'content run_id can be attached exactly once'); END;

CREATE TABLE content_runs (
    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    workflow TEXT NOT NULL CHECK (workflow IN ('ARTICLE','NOTE')),
    input_sha256 TEXT NOT NULL CHECK (
        length(input_sha256)=64 AND input_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (status IN (
        'PREPARED','RUNNING','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    )),
    reason_code TEXT,
    final_result_json TEXT CHECK (
        final_result_json IS NULL OR json_valid(final_result_json)
    ),
    score REAL CHECK (score IS NULL OR (
        typeof(score) IN ('integer','real') AND score=score AND score BETWEEN 0 AND 1
    )),
    started_at TEXT NOT NULL CHECK (length(started_at)>=19),
    updated_at TEXT NOT NULL CHECK (length(updated_at)>=19),
    finished_at TEXT,
    CHECK (
        (status IN ('REVISE','SKIPPED','FAILED','NEEDS_VERIFICATION')
            AND reason_code IS NOT NULL AND length(trim(reason_code)) BETWEEN 1 AND 100)
        OR
        (status IN ('PREPARED','RUNNING','PENDING_APPROVAL') AND reason_code IS NULL)
    ),
    CHECK (
        (status IN ('SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION')
            AND finished_at IS NOT NULL)
        OR
        (status IN ('PREPARED','RUNNING','REVISE') AND finished_at IS NULL)
    )
);

CREATE TRIGGER content_runs_insert_contract
BEFORE INSERT ON content_runs
WHEN NEW.status!='RUNNING' OR NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN jobs j ON j.id=NEW.job_id
    JOIN runs r ON r.id=NEW.run_id
    WHERE c.id=NEW.content_id
      AND c.status='PREPARED'
      AND c.run_id IS NULL
      AND c.job_id=NEW.job_id
      AND c.account_id=NEW.account_id
      AND c.research_card_id=NEW.research_card_id
      AND c.type=NEW.workflow
      AND c.input_sha256=NEW.input_sha256
      AND fi.input_sha256=NEW.input_sha256
      AND j.kind='CONTENT'
      AND j.workflow=NEW.workflow
      AND j.account_id=NEW.account_id
      AND j.status IN ('LEASED','RUNNING')
      AND j.run_id IS NULL
      AND r.account_id=NEW.account_id
      AND r.workflow=NEW.workflow
      AND r.status='RUNNING'
)
BEGIN SELECT RAISE(ABORT, 'content run does not match the active job and frozen input'); END;

CREATE TRIGGER content_runs_identity_immutable
BEFORE UPDATE OF run_id,content_id,job_id,account_id,research_card_id,workflow,input_sha256,started_at ON content_runs
WHEN NEW.run_id IS NOT OLD.run_id OR NEW.content_id IS NOT OLD.content_id
 OR NEW.job_id IS NOT OLD.job_id OR NEW.account_id IS NOT OLD.account_id
 OR NEW.research_card_id IS NOT OLD.research_card_id
 OR NEW.workflow IS NOT OLD.workflow
 OR NEW.input_sha256 IS NOT OLD.input_sha256
 OR NEW.started_at IS NOT OLD.started_at
BEGIN SELECT RAISE(ABORT, 'content run identity is immutable'); END;

CREATE TRIGGER content_runs_closed_transition
BEFORE UPDATE OF status ON content_runs
WHEN NEW.status IS NOT OLD.status AND NOT (
    (OLD.status='PREPARED' AND NEW.status IN (
        'RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='RUNNING' AND NEW.status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (OLD.status='REVISE' AND NEW.status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
)
BEGIN SELECT RAISE(ABORT, 'illegal content lifecycle transition'); END;

CREATE TRIGGER content_runs_no_delete
BEFORE DELETE ON content_runs
BEGIN SELECT RAISE(ABORT, 'content_runs cannot be deleted'); END;

CREATE TRIGGER content_items_status_matches_run
BEFORE UPDATE OF status,reason_code,final_result_json,score ON content_items
WHEN NEW.run_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM content_runs cr
    WHERE cr.run_id=NEW.run_id AND cr.content_id=NEW.id
      AND cr.status=NEW.status
      AND cr.reason_code IS NEW.reason_code
      AND cr.final_result_json IS NEW.final_result_json
      AND cr.score IS NEW.score
)
BEGIN SELECT RAISE(ABORT, 'content item lifecycle must mirror content_runs'); END;

CREATE TRIGGER content_runs_sync_content_item
AFTER UPDATE OF status,reason_code,final_result_json,score,updated_at,finished_at ON content_runs
BEGIN
    UPDATE content_items
    SET status=NEW.status,
        reason_code=NEW.reason_code,
        final_result_json=NEW.final_result_json,
        score=NEW.score,
        updated_at=NEW.updated_at
    WHERE id=NEW.content_id AND run_id=NEW.run_id AND job_id=NEW.job_id;
    SELECT CASE changes()
        WHEN 1 THEN NULL
        ELSE RAISE(ABORT, 'content run sync must update exactly one content item')
    END;
END;

-- Every post-initialization content transition is expressed as one immutable
-- command.  Its AFTER trigger is the sole SQL boundary allowed to update the
-- content_run/content_item pair and, for terminal outcomes, the general
-- run/job pair.  Direct UPDATE statements therefore fail closed while one
-- INSERT can still perform the complete ordered transaction.
CREATE TABLE content_transition_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('EXECUTION','RECOVERY')),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    workflow TEXT NOT NULL CHECK (workflow IN ('ARTICLE','NOTE')),
    source_content_status TEXT NOT NULL CHECK (source_content_status IN (
        'PREPARED','RUNNING','REVISE'
    )),
    target_content_status TEXT NOT NULL CHECK (target_content_status IN (
        'PREPARED','RUNNING','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    )),
    target_run_status TEXT NOT NULL CHECK (target_run_status IN (
        'RUNNING','SUCCESS','FAILED','STOPPED'
    )),
    target_job_status TEXT NOT NULL CHECK (target_job_status IN (
        'QUEUED','RUNNING','DONE','FAILED','NEEDS_VERIFICATION'
    )),
    lease_owner TEXT NOT NULL CHECK (length(trim(lease_owner))>0),
    execution_generation INTEGER NOT NULL CHECK (execution_generation>0),
    lease_expires_at TEXT NOT NULL CHECK (length(lease_expires_at)>=19),
    reason_code TEXT,
    final_result_json TEXT CHECK (
        final_result_json IS NULL OR json_valid(final_result_json)
    ),
    score REAL CHECK (score IS NULL OR (
        typeof(score) IN ('integer','real') AND score=score AND score BETWEEN 0 AND 1
    )),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    applied INTEGER NOT NULL DEFAULT 0 CHECK (applied IN (0,1)),
    CHECK (
        (target_content_status='SKIPPED'
            AND target_run_status='SUCCESS' AND target_job_status='DONE')
        OR
        (target_content_status='PENDING_APPROVAL'
            AND target_run_status='SUCCESS' AND target_job_status='DONE')
        OR
        (target_content_status='FAILED'
            AND target_run_status='FAILED' AND target_job_status='FAILED')
        OR
        (target_content_status='NEEDS_VERIFICATION'
            AND target_run_status='STOPPED'
            AND target_job_status='NEEDS_VERIFICATION')
        OR
        (mode='RECOVERY' AND target_content_status='PREPARED'
            AND target_run_status='RUNNING' AND target_job_status='QUEUED')
        OR
        (mode='EXECUTION'
            AND target_content_status IN ('PREPARED','RUNNING','REVISE')
            AND target_run_status='RUNNING' AND target_job_status='RUNNING')
    ),
    CHECK (
        (target_content_status IN ('REVISE','SKIPPED','FAILED','NEEDS_VERIFICATION')
            AND reason_code IS NOT NULL
            AND length(trim(reason_code)) BETWEEN 1 AND 100)
        OR
        (target_content_status IN ('PREPARED','RUNNING','PENDING_APPROVAL')
            AND reason_code IS NULL)
    )
);
CREATE UNIQUE INDEX ux_content_one_terminal_command
    ON content_transition_commands(run_id)
    WHERE target_content_status IN (
        'SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION'
    );

CREATE TRIGGER content_transition_commands_contract
BEFORE INSERT ON content_transition_commands
WHEN (
    NEW.source_content_status=NEW.target_content_status
    AND NOT (
        NEW.mode='RECOVERY'
        AND NEW.source_content_status='PREPARED'
        AND NEW.target_content_status='PREPARED'
    )
 )
 OR NOT (
    (NEW.mode='RECOVERY' AND NEW.source_content_status='PREPARED'
        AND NEW.target_content_status='PREPARED')
    OR
    (NEW.source_content_status='PREPARED' AND NEW.target_content_status IN (
        'RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (NEW.source_content_status='RUNNING' AND NEW.target_content_status IN (
        'PREPARED','REVISE','SKIPPED','PENDING_APPROVAL',
        'FAILED','NEEDS_VERIFICATION'
    ))
    OR
    (NEW.source_content_status='REVISE' AND NEW.target_content_status IN (
        'PREPARED','RUNNING','SKIPPED','FAILED','NEEDS_VERIFICATION'
    ))
 )
 OR NOT EXISTS (
    SELECT 1
    FROM jobs j
    JOIN runs r ON r.id=NEW.run_id
    JOIN content_runs cr ON cr.run_id=NEW.run_id
    JOIN content_items c ON c.id=NEW.content_id
    WHERE j.id=NEW.job_id
      AND j.kind='CONTENT'
      AND j.account_id=NEW.account_id
      AND j.workflow=NEW.workflow
      AND j.run_id=NEW.run_id
      AND j.status IN ('LEASED','RUNNING')
      AND j.lease_owner=NEW.lease_owner
      AND j.lease_expires_at=NEW.lease_expires_at
      AND j.execution_generation=NEW.execution_generation
      AND (
          (NEW.mode='EXECUTION' AND j.lease_expires_at>=NEW.created_at)
          OR
          (NEW.mode='RECOVERY' AND j.lease_expires_at<NEW.created_at)
      )
      AND r.account_id=NEW.account_id
      AND r.workflow=NEW.workflow
      AND r.status='RUNNING'
      AND r.finished_at IS NULL
      AND cr.content_id=NEW.content_id
      AND cr.job_id=NEW.job_id
      AND cr.account_id=NEW.account_id
      AND cr.workflow=NEW.workflow
      AND cr.status=NEW.source_content_status
      AND c.job_id=NEW.job_id
      AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id
      AND c.type=NEW.workflow
      AND c.status=NEW.source_content_status
 )
BEGIN SELECT RAISE(ABORT, 'content transition command lacks one current fenced relation'); END;

CREATE TRIGGER content_runs_require_transition_command
BEFORE UPDATE OF status,reason_code,final_result_json,score,updated_at,finished_at
ON content_runs
WHEN (
    NEW.status IS NOT OLD.status
    OR NEW.reason_code IS NOT OLD.reason_code
    OR NEW.final_result_json IS NOT OLD.final_result_json
    OR NEW.score IS NOT OLD.score
    OR NEW.finished_at IS NOT OLD.finished_at
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.run_id
      AND cmd.job_id=OLD.job_id
      AND cmd.content_id=OLD.content_id
      AND cmd.source_content_status=OLD.status
      AND cmd.target_content_status=NEW.status
      AND cmd.reason_code IS NEW.reason_code
      AND cmd.final_result_json IS NEW.final_result_json
      AND cmd.score IS NEW.score
      AND cmd.created_at=NEW.updated_at
      AND cmd.applied=0
)
BEGIN SELECT RAISE(ABORT, 'content_runs may change only through a transition command'); END;

CREATE TRIGGER content_items_require_transition_command
BEFORE UPDATE OF status,reason_code,final_result_json,score,updated_at
ON content_items
WHEN OLD.run_id IS NOT NULL
AND (
    NEW.status IS NOT OLD.status
    OR NEW.reason_code IS NOT OLD.reason_code
    OR NEW.final_result_json IS NOT OLD.final_result_json
    OR NEW.score IS NOT OLD.score
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.run_id
      AND cmd.job_id=OLD.job_id
      AND cmd.content_id=OLD.id
      AND cmd.source_content_status=OLD.status
      AND cmd.target_content_status=NEW.status
      AND cmd.reason_code IS NEW.reason_code
      AND cmd.final_result_json IS NEW.final_result_json
      AND cmd.score IS NEW.score
      AND cmd.created_at=NEW.updated_at
      AND cmd.applied=0
)
BEGIN SELECT RAISE(ABORT, 'content_items may change only through a transition command'); END;

CREATE TRIGGER runs_content_require_transition_command
BEFORE UPDATE OF status,current_state,finished_at,error ON runs
WHEN EXISTS (SELECT 1 FROM content_runs cr WHERE cr.run_id=OLD.id)
AND (
    NEW.status IS NOT OLD.status
    OR NEW.current_state IS NOT OLD.current_state
    OR NEW.finished_at IS NOT OLD.finished_at
    OR NEW.error IS NOT OLD.error
)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.run_id=OLD.id
      AND cmd.target_run_status=NEW.status
      AND cmd.target_content_status=NEW.current_state
      AND cmd.created_at=NEW.finished_at
      AND cmd.applied=0
)
BEGIN SELECT RAISE(ABORT, 'content general run may terminalize only through a transition command'); END;

CREATE TRIGGER jobs_content_require_transition_command
BEFORE UPDATE OF status,last_error,lease_owner,lease_expires_at,finished_at,
    reserved_cost_usd,budget_reserved_at,external_effect_started_at
ON jobs
WHEN OLD.kind='CONTENT'
AND NEW.status IN ('QUEUED','DONE','FAILED','NEEDS_VERIFICATION','CANCELLED')
AND NEW.status IS NOT OLD.status
AND (NEW.status!='QUEUED' OR OLD.run_id IS NOT NULL)
AND NOT EXISTS (
    SELECT 1 FROM content_transition_commands cmd
    WHERE cmd.job_id=OLD.id
      AND cmd.run_id=OLD.run_id
      AND cmd.target_job_status=NEW.status
      AND cmd.execution_generation=OLD.execution_generation
      AND cmd.applied=0
)
BEGIN SELECT RAISE(ABORT, 'CONTENT job may transition only through a content command'); END;

CREATE TRIGGER content_transition_commands_apply
AFTER INSERT ON content_transition_commands
BEGIN
    UPDATE content_runs
    SET status=NEW.target_content_status,
        reason_code=NEW.reason_code,
        final_result_json=NEW.final_result_json,
        score=NEW.score,
        updated_at=NEW.created_at,
        finished_at=CASE
            WHEN NEW.target_content_status IN (
                'SKIPPED','PENDING_APPROVAL','FAILED','NEEDS_VERIFICATION'
            ) THEN NEW.created_at
            ELSE NULL
        END
    WHERE run_id=NEW.run_id
      AND content_id=NEW.content_id
      AND job_id=NEW.job_id
      AND account_id=NEW.account_id
      AND workflow=NEW.workflow
      AND status=NEW.source_content_status;
    SELECT CASE changes()
        WHEN 1 THEN NULL
        ELSE RAISE(ABORT, 'content transition must update exactly one content_run')
    END;

    UPDATE runs
    SET status=NEW.target_run_status,
        current_state=NEW.target_content_status,
        finished_at=NEW.created_at,
        error=CASE
            WHEN NEW.target_run_status='SUCCESS' THEN NULL
            ELSE NEW.reason_code
        END
    WHERE id=NEW.run_id
      AND account_id=NEW.account_id
      AND workflow=NEW.workflow
      AND status='RUNNING'
      AND finished_at IS NULL
      AND NEW.target_run_status!='RUNNING';
    SELECT CASE
        WHEN NEW.target_run_status='RUNNING' THEN NULL
        WHEN changes()=1 THEN NULL
        ELSE RAISE(ABORT, 'terminal content transition must update exactly one run')
    END;

    UPDATE jobs
    SET status=NEW.target_job_status,
        last_error=NEW.reason_code,
        lease_owner=NULL,
        lease_expires_at=NULL,
        finished_at=CASE
            WHEN NEW.target_job_status='QUEUED' THEN NULL
            ELSE NEW.created_at
        END,
        updated_at=NEW.created_at,
        reserved_cost_usd=0.0,
        budget_reserved_at=NULL,
        external_effect_started_at=NULL
    WHERE id=NEW.job_id
      AND run_id=NEW.run_id
      AND account_id=NEW.account_id
      AND workflow=NEW.workflow
      AND kind='CONTENT'
      AND status IN ('LEASED','RUNNING')
      AND lease_owner=NEW.lease_owner
      AND lease_expires_at=NEW.lease_expires_at
      AND execution_generation=NEW.execution_generation
      AND (
          NEW.target_job_status!='RUNNING'
      );
    SELECT CASE
        WHEN NEW.target_job_status='RUNNING' THEN NULL
        WHEN changes()=1 THEN NULL
        ELSE RAISE(ABORT, 'content transition must update exactly one job')
    END;

    UPDATE content_transition_commands
    SET applied=1
    WHERE id=NEW.id AND applied=0;
    SELECT CASE changes()
        WHEN 1 THEN NULL
        ELSE RAISE(ABORT, 'content transition command must be consumed exactly once')
    END;
END;

CREATE TRIGGER content_transition_commands_no_update
BEFORE UPDATE ON content_transition_commands
WHEN NOT (
    OLD.applied=0 AND NEW.applied=1
    AND NEW.id IS OLD.id
    AND NEW.command_id IS OLD.command_id
    AND NEW.mode IS OLD.mode
    AND NEW.job_id IS OLD.job_id
    AND NEW.run_id IS OLD.run_id
    AND NEW.content_id IS OLD.content_id
    AND NEW.account_id IS OLD.account_id
    AND NEW.workflow IS OLD.workflow
    AND NEW.source_content_status IS OLD.source_content_status
    AND NEW.target_content_status IS OLD.target_content_status
    AND NEW.target_run_status IS OLD.target_run_status
    AND NEW.target_job_status IS OLD.target_job_status
    AND NEW.lease_owner IS OLD.lease_owner
    AND NEW.execution_generation IS OLD.execution_generation
    AND NEW.lease_expires_at IS OLD.lease_expires_at
    AND NEW.reason_code IS OLD.reason_code
    AND NEW.final_result_json IS OLD.final_result_json
    AND NEW.score IS OLD.score
    AND NEW.created_at IS OLD.created_at
)
BEGIN SELECT RAISE(ABORT, 'content_transition_commands is append-only'); END;
CREATE TRIGGER content_transition_commands_no_delete
BEFORE DELETE ON content_transition_commands
BEGIN SELECT RAISE(ABORT, 'content_transition_commands is append-only'); END;

-- ---- 5. Article Brief and pre-network paid-call ledger contract ------------

CREATE TABLE content_article_briefs (
    content_id INTEGER PRIMARY KEY REFERENCES content_items(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    brief_schema_version TEXT NOT NULL CHECK (length(trim(brief_schema_version)) BETWEEN 1 AND 100),
    brief_json TEXT NOT NULL CHECK (json_valid(brief_json)),
    brief_sha256 TEXT NOT NULL UNIQUE CHECK (
        length(brief_sha256)=64 AND brief_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);

CREATE TRIGGER content_article_briefs_contract
BEFORE INSERT ON content_article_briefs
WHEN NEW.brief_sha256 IS NOT evidence_sha256_hex(NEW.brief_json)
 OR NOT EXISTS (
    SELECT 1 FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id
    WHERE c.id=NEW.content_id AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id
      AND cr.job_id=NEW.job_id AND cr.run_id=NEW.run_id
      AND cr.status IN ('RUNNING','REVISE')
 )
BEGIN SELECT RAISE(ABORT, 'Article Brief must bind the active content execution and its hash'); END;
CREATE TRIGGER content_article_briefs_no_update
BEFORE UPDATE ON content_article_briefs
BEGIN SELECT RAISE(ABORT, 'content_article_briefs is append-only'); END;
CREATE TRIGGER content_article_briefs_no_delete
BEFORE DELETE ON content_article_briefs
BEGIN SELECT RAISE(ABORT, 'content_article_briefs is append-only'); END;

CREATE TABLE content_call_intents (
    intent_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    research_card_id INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE RESTRICT,
    content_type TEXT NOT NULL CHECK (content_type IN ('ARTICLE','NOTE')),
    stage TEXT NOT NULL CHECK (stage='content_draft'),
    frozen_input_sha256 TEXT NOT NULL,
    article_brief_sha256 TEXT NOT NULL,
    evidence_manifest_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 200),
    pricing_profile_id TEXT NOT NULL CHECK (length(trim(pricing_profile_id)) BETWEEN 1 AND 200),
    pricing_profile_version TEXT NOT NULL CHECK (length(trim(pricing_profile_version)) BETWEEN 1 AND 100),
    pricing_fingerprint TEXT NOT NULL CHECK (
        length(pricing_fingerprint)=64 AND pricing_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    max_input_tokens INTEGER NOT NULL CHECK (max_input_tokens>0),
    max_context_tokens INTEGER NOT NULL CHECK (
        max_context_tokens>0 AND max_context_tokens>=max_input_tokens
    ),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens>0),
    web_searches INTEGER NOT NULL CHECK (web_searches=0),
    max_retries INTEGER NOT NULL CHECK (max_retries=0),
    attempt_no INTEGER NOT NULL CHECK (attempt_no=1),
    prompt_version TEXT NOT NULL CHECK (length(trim(prompt_version)) BETWEEN 1 AND 100),
    style_guide_version TEXT NOT NULL CHECK (length(trim(style_guide_version)) BETWEEN 1 AND 200),
    output_schema_version TEXT NOT NULL CHECK (length(trim(output_schema_version)) BETWEEN 1 AND 100),
    max_cost_usd REAL NOT NULL CHECK (
        typeof(max_cost_usd) IN ('integer','real') AND max_cost_usd>0
        AND max_cost_usd=max_cost_usd
    ),
    expires_at TEXT NOT NULL CHECK (length(expires_at)>=19),
    intent_json TEXT NOT NULL CHECK (json_valid(intent_json)),
    intent_fingerprint TEXT NOT NULL UNIQUE CHECK (
        length(intent_fingerprint)=64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);

CREATE TRIGGER content_call_intents_contract
BEFORE INSERT ON content_call_intents
WHEN NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.intent_json)
 OR NEW.expires_at<=NEW.created_at
 OR NOT EXISTS (
    SELECT 1
    FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id
    JOIN content_frozen_inputs fi ON fi.content_id=c.id
    JOIN content_article_briefs b ON b.content_id=c.id
    JOIN jobs j ON j.id=c.job_id
    WHERE c.id=NEW.content_id
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id
      AND c.research_card_id=NEW.research_card_id
      AND c.type=NEW.content_type
      AND c.status IN ('RUNNING','REVISE')
      AND cr.job_id=NEW.job_id AND cr.run_id=NEW.run_id
      AND fi.input_sha256=NEW.frozen_input_sha256
      AND fi.evidence_manifest_sha256=NEW.evidence_manifest_sha256
      AND b.brief_sha256=NEW.article_brief_sha256
      AND j.kind='CONTENT' AND j.status='RUNNING'
      AND json_extract(NEW.intent_json,'$.execution')='durable_content_call_v1'
      AND json_extract(NEW.intent_json,'$.intent_id')=NEW.intent_id
      AND json_extract(NEW.intent_json,'$.job_id')=NEW.job_id
      AND json_extract(NEW.intent_json,'$.run_id')=NEW.run_id
      AND json_extract(NEW.intent_json,'$.content_id')=NEW.content_id
      AND json_extract(NEW.intent_json,'$.account_id')=NEW.account_id
      AND json_extract(NEW.intent_json,'$.research_card_id')=NEW.research_card_id
      AND json_extract(NEW.intent_json,'$.content_type')=NEW.content_type
      AND json_extract(NEW.intent_json,'$.stage')=NEW.stage
      AND json_extract(NEW.intent_json,'$.frozen_input_sha256')=NEW.frozen_input_sha256
      AND json_extract(NEW.intent_json,'$.article_brief_sha256')=NEW.article_brief_sha256
      AND json_extract(NEW.intent_json,'$.evidence_manifest_sha256')=NEW.evidence_manifest_sha256
      AND json_extract(NEW.intent_json,'$.provider')=NEW.provider
      AND json_extract(NEW.intent_json,'$.model')=NEW.model
      AND json_extract(NEW.intent_json,'$.pricing_profile_id')=NEW.pricing_profile_id
      AND json_extract(NEW.intent_json,'$.pricing_profile_version')=NEW.pricing_profile_version
      AND json_extract(NEW.intent_json,'$.pricing_fingerprint')=NEW.pricing_fingerprint
      AND json_extract(NEW.intent_json,'$.max_input_tokens')=NEW.max_input_tokens
      AND json_extract(NEW.intent_json,'$.max_context_tokens')=NEW.max_context_tokens
      AND json_extract(NEW.intent_json,'$.max_output_tokens')=NEW.max_output_tokens
      AND json_extract(NEW.intent_json,'$.web_searches')=0
      AND json_extract(NEW.intent_json,'$.max_retries')=0
      AND json_extract(NEW.intent_json,'$.attempt_no')=1
      AND json_extract(NEW.intent_json,'$.prompt_version')=NEW.prompt_version
      AND json_extract(NEW.intent_json,'$.style_guide_version')=NEW.style_guide_version
      AND json_extract(NEW.intent_json,'$.output_schema_version')=NEW.output_schema_version
      AND CAST(json_extract(NEW.intent_json,'$.max_cost_usd') AS REAL)=NEW.max_cost_usd
      AND json_extract(NEW.intent_json,'$.expires_at')=NEW.expires_at
 )
BEGIN SELECT RAISE(ABORT, 'content call intent does not match its frozen execution'); END;

CREATE TRIGGER content_call_intents_no_update
BEFORE UPDATE ON content_call_intents
BEGIN SELECT RAISE(ABORT, 'content_call_intents is append-only'); END;
CREATE TRIGGER content_call_intents_no_delete
BEFORE DELETE ON content_call_intents
BEGIN SELECT RAISE(ABORT, 'content_call_intents is append-only'); END;

-- Extension lineage for the shared provider_attempts ledger.  C1 may reserve
-- the atomic parent+extension pair for local contract verification, but adds
-- no SDK caller and crosses no external request boundary.
CREATE TABLE content_provider_attempts (
    request_id TEXT PRIMARY KEY
        REFERENCES provider_attempts(request_id) ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    intent_id TEXT NOT NULL UNIQUE REFERENCES content_call_intents(intent_id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL UNIQUE REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    stage TEXT NOT NULL CHECK (stage='content_draft'),
    attempt_no INTEGER NOT NULL CHECK (attempt_no=1),
    provider TEXT NOT NULL CHECK (length(trim(provider)) BETWEEN 1 AND 100),
    model TEXT NOT NULL CHECK (length(trim(model)) BETWEEN 1 AND 200),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19)
);

CREATE TRIGGER content_provider_attempts_contract
BEFORE INSERT ON content_provider_attempts
WHEN NEW.request_id != NEW.job_id || ':' || NEW.stage || ':' || NEW.attempt_no
 OR NOT EXISTS (
    SELECT 1
    FROM content_call_intents ci
    JOIN jobs j ON j.id=ci.job_id
    JOIN runs r ON r.id=ci.run_id
    JOIN content_runs cr ON cr.run_id=ci.run_id
    JOIN content_items c ON c.id=ci.content_id
    WHERE ci.intent_id=NEW.intent_id
      AND ci.job_id=NEW.job_id
      AND ci.run_id=NEW.run_id
      AND ci.content_id=NEW.content_id
      AND ci.account_id=NEW.account_id
      AND ci.stage=NEW.stage
      AND ci.attempt_no=NEW.attempt_no
      AND ci.provider=NEW.provider
      AND ci.model=NEW.model
      AND j.id=NEW.job_id
      AND j.kind='CONTENT'
      AND j.run_id=NEW.run_id
      AND j.account_id=NEW.account_id
      AND j.workflow=ci.content_type
      AND r.id=NEW.run_id
      AND r.account_id=NEW.account_id
      AND r.workflow=ci.content_type
      AND cr.job_id=NEW.job_id
      AND cr.content_id=NEW.content_id
      AND cr.account_id=NEW.account_id
      AND cr.workflow=ci.content_type
      AND c.job_id=NEW.job_id
      AND c.run_id=NEW.run_id
      AND c.account_id=NEW.account_id
      AND c.type=ci.content_type
)
BEGIN SELECT RAISE(ABORT, 'content attempt extension does not match its call intent'); END;

CREATE TRIGGER provider_attempts_content_requires_extension
BEFORE INSERT ON provider_attempts
WHEN EXISTS (SELECT 1 FROM jobs j WHERE j.id=NEW.job_id AND j.kind='CONTENT')
AND NOT EXISTS (
    SELECT 1
    FROM content_provider_attempts cpa
    JOIN content_call_intents ci ON ci.intent_id=cpa.intent_id
    WHERE cpa.request_id=NEW.request_id
      AND cpa.job_id=NEW.job_id
      AND cpa.stage=NEW.stage
      AND cpa.attempt_no=NEW.attempt_no
      AND ci.intent_fingerprint=NEW.execution_intent_fingerprint
)
BEGIN
    SELECT RAISE(ABORT,
        'CONTENT provider attempt requires its exact 1:1 extension');
END;

CREATE TRIGGER model_usage_content_attempt_contract
BEFORE INSERT ON model_usage
WHEN NEW.request_id IS NOT NULL
AND EXISTS (
    SELECT 1 FROM content_provider_attempts cpa
    WHERE cpa.request_id=NEW.request_id
)
AND NOT EXISTS (
    SELECT 1
    FROM content_provider_attempts cpa
    JOIN content_call_intents ci ON ci.intent_id=cpa.intent_id
    JOIN provider_attempts pa ON pa.request_id=cpa.request_id
    WHERE cpa.request_id=NEW.request_id
      AND pa.job_id=cpa.job_id
      AND pa.stage=cpa.stage
      AND pa.attempt_no=cpa.attempt_no
      AND NEW.run_id=cpa.run_id
      AND NEW.provider=cpa.provider
      AND NEW.model=cpa.model
      AND NEW.task=cpa.stage
      AND ci.intent_fingerprint=pa.execution_intent_fingerprint
)
BEGIN SELECT RAISE(ABORT, 'model_usage does not match the canonical content attempt'); END;

CREATE TRIGGER content_provider_attempts_no_update
BEFORE UPDATE ON content_provider_attempts
BEGIN SELECT RAISE(ABORT, 'content_provider_attempts is append-only'); END;
CREATE TRIGGER content_provider_attempts_no_delete
BEFORE DELETE ON content_provider_attempts
BEGIN SELECT RAISE(ABORT, 'content_provider_attempts is append-only'); END;

-- ---- 6. Minimal audit result storage; no audit logic -----------------------

CREATE TABLE evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('FACT','STYLE','GROWTH')),
    audit_version TEXT NOT NULL CHECK (length(trim(audit_version)) BETWEEN 1 AND 100),
    status TEXT NOT NULL CHECK (status IN ('PENDING','PASSED','FAILED','ERROR')),
    score REAL CHECK (score IS NULL OR (
        typeof(score) IN ('integer','real') AND score=score AND score BETWEEN 0 AND 1
    )),
    findings_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(findings_json)),
    reason_codes_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(reason_codes_json)),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    updated_at TEXT NOT NULL CHECK (length(updated_at)>=19),
    UNIQUE(content_id,kind,audit_version)
);
CREATE INDEX ix_evaluations_content ON evaluations(content_id,kind,status);

CREATE TRIGGER evaluations_bind_content_execution
BEFORE INSERT ON evaluations
WHEN NOT EXISTS (
    SELECT 1 FROM content_items c
    JOIN content_runs cr ON cr.content_id=c.id
    WHERE c.id=NEW.content_id AND c.account_id=NEW.account_id
      AND c.job_id=NEW.job_id AND c.run_id=NEW.run_id
      AND cr.job_id=NEW.job_id AND cr.run_id=NEW.run_id
)
BEGIN SELECT RAISE(ABORT, 'evaluation must bind one content execution'); END;

CREATE TRIGGER evaluations_identity_immutable
BEFORE UPDATE OF content_id,account_id,job_id,run_id,kind,audit_version,created_at ON evaluations
WHEN NEW.content_id IS NOT OLD.content_id OR NEW.account_id IS NOT OLD.account_id
 OR NEW.job_id IS NOT OLD.job_id OR NEW.run_id IS NOT OLD.run_id
 OR NEW.kind IS NOT OLD.kind OR NEW.audit_version IS NOT OLD.audit_version
 OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT, 'evaluation identity is immutable'); END;

CREATE TRIGGER evaluations_closed_transition
BEFORE UPDATE OF status ON evaluations
WHEN NEW.status IS NOT OLD.status
 AND NOT (OLD.status='PENDING' AND NEW.status IN ('PASSED','FAILED','ERROR'))
BEGIN SELECT RAISE(ABORT, 'illegal evaluation lifecycle transition'); END;
CREATE TRIGGER evaluations_no_delete
BEFORE DELETE ON evaluations
BEGIN SELECT RAISE(ABORT, 'evaluations cannot be deleted'); END;

-- Test-only function is registered as a no-op in ordinary migrations and may
-- raise here to prove that schema and ledger roll back together.
SELECT _nia_transactional_migration_failpoint('0021_durable_content_foundation');
INSERT INTO schema_migrations(version)
VALUES ('0021_durable_content_foundation');

COMMIT;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
