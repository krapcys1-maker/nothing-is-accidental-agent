-- Forward-only: a review may span more than one paid provider call.
--
-- WHY THIS EXISTS
-- ---------------
-- The reviewer's output ceiling is 8192 tokens and it cannot be raised: the
-- qualified capability declaration is 32000/8192, so a wider ceiling needs a
-- new paid qualification.  Reviewer output grows with the number of SEGMENTS
-- to account for, not with article length: a 48-segment draft came back whole,
-- a 64-segment draft of the same length ran out of output tokens mid-JSON and
-- the entire paid review was discarded as REVIEWER_RESPONSE_NOT_JSON.  Because
-- ``content_frozen_inputs.input_sha256`` is globally UNIQUE, that terminal
-- failure also destroys the paid research card for good.
--
-- The application fix is to split the per-segment accounting across several
-- reviewer calls, each carrying the whole article and the whole evidence
-- package but accounting for only part of the segment list.  Each of those
-- calls is a separate paid external effect, so each needs its own durable
-- pre-effect reservation and its own single settlement.  0032's
-- ``role_provider_executions`` cannot hold them: it is UNIQUE on
-- (content_id, logical_role, attempt_no) with attempt_no restricted to (1,2),
-- which is exactly one reviewer row per writer attempt, by construction.
--
-- WHAT THIS ADDS
-- --------------
-- One additive table.  Nothing existing is rebuilt, dropped or re-triggered.
--
-- The role execution stays the umbrella: it is reserved before the first chunk
-- call at the full legal ceiling of ALL planned chunks, and it settles exactly
-- once with the complete aggregated entry set, the whole-article verdict and
-- the summed usage.  Every existing floor therefore keeps working verbatim --
-- including ``role_provider_executions_settle`` and the settlement validator,
-- which rebuild the segment surface from the stored draft and refuse a SUCCESS
-- that does not account for every segment exactly once.  Coverage across all
-- chunks combined is thus validated by the same rule that validated coverage
-- of a single call, with no change to the rule.
--
-- Each chunk call gets one row here: its own execution ref, its own
-- reservation written before the transport is touched, its own external-effect
-- stamp, and its own terminal settlement carrying that call's usage and cost.
-- Chunk rows never write ``model_usage`` -- the umbrella settles the summed
-- usage once -- so no cost is counted twice in any daily, monthly, run or job
-- ledger.
--
-- A single-call review writes nothing here: the umbrella row IS that one call,
-- exactly as before this migration.  ``chunk_count >= 2`` states that durably.

CREATE TABLE content_review_chunk_executions (
    chunk_execution_ref TEXT PRIMARY KEY
        CHECK (length(trim(chunk_execution_ref)) BETWEEN 1 AND 200),
    -- Deliberately NOT a SQL foreign key: 0032 relies on
    -- role_provider_executions having no incoming references so it can be
    -- rebuilt without PRAGMA foreign_keys=OFF.  The contract trigger below
    -- enforces something strictly stronger than a foreign key anyway -- the
    -- parent must exist, be the ARTICLE_REVIEWER umbrella for this exact
    -- content and attempt, and still be IN_FLIGHT -- and the parent table is
    -- already delete-proof.
    parent_execution_ref TEXT NOT NULL
        CHECK (length(trim(parent_execution_ref)) BETWEEN 1 AND 200),
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    content_id INTEGER NOT NULL REFERENCES content_items(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no IN (1,2)),
    chunk_no INTEGER NOT NULL CHECK (chunk_no >= 1),
    -- A one-chunk review is an ordinary role execution and never appears here.
    chunk_count INTEGER NOT NULL CHECK (chunk_count >= 2),
    segment_count INTEGER NOT NULL CHECK (segment_count >= 1),
    -- The exact segment list this call was asked to account for, hashed from
    -- the ordered segment ids.  Two chunks of the same review can never claim
    -- the same slice without it being visible.
    accounted_segments_fingerprint TEXT NOT NULL CHECK (
        length(accounted_segments_fingerprint)=64
        AND accounted_segments_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    prompt_fingerprint TEXT NOT NULL CHECK (
        length(prompt_fingerprint)=64
        AND prompt_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    -- The whole-article verdict is asked for in the first chunk only, so it is
    -- neither duplicated nor self-contradictory across calls.
    requests_document_review INTEGER NOT NULL CHECK (
        requests_document_review IN (0,1)
    ),
    provider TEXT NOT NULL CHECK (provider='ANTHROPIC'),
    technical_model_id TEXT NOT NULL,
    returned_model_id TEXT,
    reserved_cost_usd TEXT NOT NULL CHECK (
        reserved_cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
        AND reserved_cost_usd NOT GLOB '*[^0-9.]*'
    ),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('IN_FLIGHT','SUCCESS','FAILURE','NEEDS_VERIFICATION')
    ),
    failure_kind TEXT,
    input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens>=0),
    output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens>=0),
    cache_read_tokens INTEGER CHECK (
        cache_read_tokens IS NULL OR cache_read_tokens>=0
    ),
    cache_write_tokens INTEGER CHECK (
        cache_write_tokens IS NULL OR cache_write_tokens>=0
    ),
    web_search_requests INTEGER CHECK (
        web_search_requests IS NULL OR web_search_requests>=0
    ),
    cost_usd TEXT CHECK (
        cost_usd IS NULL
        OR (cost_usd GLOB '[0-9]*.[0-9][0-9][0-9][0-9][0-9][0-9]'
            AND cost_usd NOT GLOB '*[^0-9.]*')
    ),
    result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
    result_fingerprint TEXT UNIQUE CHECK (
        result_fingerprint IS NULL
        OR (length(result_fingerprint)=64
            AND result_fingerprint NOT GLOB '*[^0-9a-f]*')
    ),
    reserved_at TEXT NOT NULL CHECK (length(reserved_at)>=19),
    external_effect_started_at TEXT CHECK (
        external_effect_started_at IS NULL
        OR length(external_effect_started_at)>=19
    ),
    settled_at TEXT CHECK (settled_at IS NULL OR length(settled_at)>=19),
    created_at TEXT NOT NULL CHECK (length(created_at)>=19),
    UNIQUE (content_id, attempt_no, chunk_no),
    CHECK (chunk_no <= chunk_count),
    CHECK (requests_document_review = (CASE WHEN chunk_no=1 THEN 1 ELSE 0 END)),
    -- A reserved row carries no answer at all.
    CHECK (
      outcome!='IN_FLIGHT'
      OR (returned_model_id IS NULL AND failure_kind IS NULL
          AND input_tokens IS NULL AND output_tokens IS NULL
          AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
          AND web_search_requests IS NULL AND cost_usd IS NULL
          AND result_json IS NULL AND result_fingerprint IS NULL
          AND settled_at IS NULL)
    ),
    -- Known terminal results are complete; NEEDS_VERIFICATION may instead be
    -- literally unknown.  NULL means unknown and zero is never synthesized.
    CHECK (
      outcome='IN_FLIGHT'
      OR (outcome IN ('SUCCESS','FAILURE')
          AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
          AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL
          AND web_search_requests IS NOT NULL AND cost_usd IS NOT NULL
          AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL
          AND settled_at IS NOT NULL)
      OR (outcome='NEEDS_VERIFICATION'
          AND result_json IS NOT NULL AND result_fingerprint IS NOT NULL
          AND settled_at IS NOT NULL
          AND (
            (input_tokens IS NOT NULL AND output_tokens IS NOT NULL
             AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL
             AND web_search_requests IS NOT NULL AND cost_usd IS NOT NULL)
            OR
            (input_tokens IS NULL AND output_tokens IS NULL
             AND cache_read_tokens IS NULL AND cache_write_tokens IS NULL
             AND web_search_requests IS NULL AND cost_usd IS NULL)
          ))
    ),
    CHECK (
      (outcome='SUCCESS' AND failure_kind IS NULL)
      OR (outcome IN ('FAILURE','NEEDS_VERIFICATION') AND failure_kind IS NOT NULL)
      OR (outcome='IN_FLIGHT' AND failure_kind IS NULL)
    )
);

CREATE INDEX ix_content_review_chunk_executions_parent
    ON content_review_chunk_executions(parent_execution_ref, chunk_no);

-- A chunk may only be reserved under a live reviewer umbrella that already
-- states this exact identity, and only in order, and only while every earlier
-- chunk of the same review is already terminal.  The last clause is the
-- durable form of "settle after each call": chunk k+1 cannot be reserved while
-- chunk k's provider outcome is still unknown.
--
-- The reservation arithmetic is the job ceiling, restated per review: the sum
-- of what the siblings have actually cost, plus what the still-open siblings
-- have reserved, plus this reservation, may never exceed what the umbrella
-- reserved against the ARTICLE approval.  A review therefore cannot spend more
-- across N chunks than it was authorised to spend as a whole.
CREATE TRIGGER content_review_chunk_executions_contract
BEFORE INSERT ON content_review_chunk_executions
WHEN NEW.outcome!='IN_FLIGHT'
 OR NEW.external_effect_started_at IS NOT NULL
 OR NOT EXISTS (
    SELECT 1 FROM role_provider_executions e
    WHERE e.execution_ref=NEW.parent_execution_ref
      AND e.logical_role='ARTICLE_REVIEWER'
      AND e.outcome='IN_FLIGHT'
      AND e.job_id=NEW.job_id AND e.run_id=NEW.run_id
      AND e.content_id=NEW.content_id AND e.attempt_no=NEW.attempt_no
      AND e.provider=NEW.provider
      AND e.technical_model_id=NEW.technical_model_id
 )
 -- Chunks are reserved strictly in order, with no gaps and no re-entry.
 OR NEW.chunk_no!=1+(
    SELECT COALESCE(MAX(s.chunk_no),0) FROM content_review_chunk_executions s
    WHERE s.parent_execution_ref=NEW.parent_execution_ref
 )
 OR EXISTS (
    SELECT 1 FROM content_review_chunk_executions s
    WHERE s.parent_execution_ref=NEW.parent_execution_ref
      AND (s.outcome='IN_FLIGHT' OR s.chunk_count!=NEW.chunk_count)
 )
 OR (
    SELECT CAST(e.reserved_cost_usd AS REAL) FROM role_provider_executions e
    WHERE e.execution_ref=NEW.parent_execution_ref
 ) + 0.0000005 < CAST(NEW.reserved_cost_usd AS REAL) + (
    SELECT COALESCE(SUM(CAST(
      COALESCE(s.cost_usd, s.reserved_cost_usd) AS REAL)), 0.0)
    FROM content_review_chunk_executions s
    WHERE s.parent_execution_ref=NEW.parent_execution_ref
 )
BEGIN SELECT RAISE(ABORT, 'review chunk must be reserved in order under a live umbrella within its cost'); END;

-- Exactly two mutations are legal, the same two the role ledger permits:
-- the pre-effect stamp, and one settlement.  Identity and reservation columns
-- are immutable in both, and a settled SUCCESS must name the authorised model.
CREATE TRIGGER content_review_chunk_executions_settle
BEFORE UPDATE ON content_review_chunk_executions
WHEN NEW.chunk_execution_ref!=OLD.chunk_execution_ref
 OR NEW.parent_execution_ref!=OLD.parent_execution_ref
 OR NEW.job_id!=OLD.job_id OR NEW.run_id!=OLD.run_id
 OR NEW.content_id!=OLD.content_id OR NEW.attempt_no!=OLD.attempt_no
 OR NEW.chunk_no!=OLD.chunk_no OR NEW.chunk_count!=OLD.chunk_count
 OR NEW.segment_count!=OLD.segment_count
 OR NEW.accounted_segments_fingerprint!=OLD.accounted_segments_fingerprint
 OR NEW.prompt_fingerprint!=OLD.prompt_fingerprint
 OR NEW.requests_document_review!=OLD.requests_document_review
 OR NEW.provider!=OLD.provider
 OR NEW.technical_model_id!=OLD.technical_model_id
 OR NEW.reserved_cost_usd!=OLD.reserved_cost_usd
 OR NEW.reserved_at!=OLD.reserved_at OR NEW.created_at!=OLD.created_at
 OR NOT (
      (OLD.outcome='IN_FLIGHT' AND NEW.outcome='IN_FLIGHT'
       AND OLD.external_effect_started_at IS NULL
       AND NEW.external_effect_started_at IS NOT NULL
       AND NEW.settled_at IS NULL AND NEW.result_json IS NULL
       AND NEW.result_fingerprint IS NULL AND NEW.failure_kind IS NULL
       AND NEW.returned_model_id IS NULL AND NEW.cost_usd IS NULL)
      OR
      (OLD.outcome='IN_FLIGHT'
       AND NEW.outcome IN ('SUCCESS','FAILURE','NEEDS_VERIFICATION')
       AND NEW.external_effect_started_at IS OLD.external_effect_started_at
       AND NEW.settled_at IS NOT NULL AND NEW.result_json IS NOT NULL
       AND NEW.result_fingerprint IS evidence_sha256_hex(NEW.result_json)
       AND NOT (NEW.returned_model_id IS NOT NULL
                AND NEW.returned_model_id!=NEW.technical_model_id
                AND NEW.outcome='SUCCESS'))
 )
BEGIN SELECT RAISE(ABORT, 'review chunk admits one effect stamp and one settlement'); END;

CREATE TRIGGER content_review_chunk_executions_no_delete
BEFORE DELETE ON content_review_chunk_executions
BEGIN SELECT RAISE(ABORT, 'review chunk executions are append-only'); END;
