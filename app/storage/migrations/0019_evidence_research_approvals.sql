-- Stage 2 / Wave E3: generalized one-shot L1 approvals.
--
-- This migration generalizes the EXISTING `controlled_fetch_approvals` table
-- (it does NOT create a new approval family) so that the same durable,
-- append-only, consume-exactly-once contract can authorize two closed action
-- types:
--   * CONTROLLED_FETCH   — byte-for-byte the 0018 contract, no regression;
--   * EVIDENCE_RESEARCH  — the one-shot human L1 consent for exactly one
--     durable_provider_v2 evidence-research job.  The row durably stores the
--     COMPLETE canonical `execution_intent` JSON (the literal preimage of
--     `intent_fingerprint`), so the authoritative evidence input
--     (retrieval IDs + canonical hashes + model + caps + limits) survives any
--     later mutation of the mutable `jobs.payload_json`.
--
-- Trust boundary (stated honestly, mirroring 0016/0018): these floors bind
-- values persisted in this database to each other.  `evidence_sha256_hex` is
-- the deterministic application function registered by app.storage.db on every
-- controlled connection (0016 contract): a writer without it cannot INSERT an
-- EVIDENCE_RESEARCH approval at all (fail closed), and a writer with the
-- genuine function cannot persist a fingerprint that is not the SHA-256 of the
-- stored preimage.  None of the floors defends against a writer who alters the
-- schema or drops triggers; that writer is outside the threat model.

-- Rename-and-replace of a table with INCOMING foreign keys
-- (controlled_fetch_attempts.approval_id) follows the sanctioned SQLite
-- rebuild procedure: BOTH foreign_keys=OFF AND legacy_alter_table=ON are
-- required (verified against SQLite 3.49) so that ALTER TABLE RENAME does not
-- rewrite the REFERENCES clause of controlled_fetch_attempts to the temporary
-- name.  foreign_keys is a no-op inside a transaction — so this migration
-- manages its own explicit transaction (the same contract as 0006) and is
-- intentionally NOT wrapped by the transactional runner.  A fault inside the
-- transaction rolls back both the schema change and (because the ledger row
-- is only written after a successful script) the migration ledger.
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

BEGIN IMMEDIATE;

-- Triggers on OTHER tables that reference controlled_fetch_approvals must be
-- dropped before the rename (ALTER TABLE RENAME would rewrite their bodies).
DROP TRIGGER IF EXISTS controlled_fetch_attempts_bind_consumed_approval;
DROP TRIGGER IF EXISTS controlled_fetch_approvals_bind_frozen_job;
DROP TRIGGER IF EXISTS controlled_fetch_approvals_born_unconsumed;
DROP TRIGGER IF EXISTS controlled_fetch_approvals_consume_exactly_once;
DROP TRIGGER IF EXISTS controlled_fetch_approvals_consume_before_expiry;
DROP TRIGGER IF EXISTS controlled_fetch_approvals_no_delete;

ALTER TABLE controlled_fetch_approvals RENAME TO controlled_fetch_approvals_0018_old;

CREATE TABLE controlled_fetch_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT CHECK (
        length(trim(account_id, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    action_type TEXT NOT NULL CHECK (
        action_type IN ('CONTROLLED_FETCH','EVIDENCE_RESEARCH')
    ),
    requested_url TEXT,
    intent_fingerprint TEXT NOT NULL CHECK (
        length(intent_fingerprint) = 64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    timeout_seconds INTEGER,
    max_bytes INTEGER,
    max_redirects INTEGER,
    topic_id INTEGER REFERENCES topics(id) ON DELETE RESTRICT,
    execution_intent_json TEXT,
    approved_by TEXT NOT NULL CHECK (
        length(trim(approved_by, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    approved_at TEXT NOT NULL CHECK (length(approved_at) >= 19),
    expires_at TEXT NOT NULL CHECK (length(expires_at) >= 19 AND expires_at > approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at) >= 19),
    -- NULL-proof branch matrix: each action type pins every branch column.
    CHECK (
        (action_type = 'CONTROLLED_FETCH'
            AND requested_url IS NOT NULL
            AND length(trim(requested_url, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
            AND timeout_seconds IS NOT NULL AND timeout_seconds BETWEEN 1 AND 120
            AND max_bytes IS NOT NULL AND max_bytes BETWEEN 1 AND 2000000
            AND max_redirects IS NOT NULL AND max_redirects BETWEEN 0 AND 5
            AND topic_id IS NULL
            AND execution_intent_json IS NULL)
        OR
        (action_type = 'EVIDENCE_RESEARCH'
            AND requested_url IS NULL
            AND timeout_seconds IS NULL
            AND max_bytes IS NULL
            AND max_redirects IS NULL
            AND topic_id IS NOT NULL
            AND execution_intent_json IS NOT NULL
            AND json_valid(execution_intent_json)
            AND length(execution_intent_json) > 2)
    )
);

INSERT INTO controlled_fetch_approvals (
    id, job_id, account_id, action_type, requested_url, intent_fingerprint,
    timeout_seconds, max_bytes, max_redirects, topic_id, execution_intent_json,
    approved_by, approved_at, expires_at, consumed_at
)
SELECT
    id, job_id, account_id, action_type, requested_url, intent_fingerprint,
    timeout_seconds, max_bytes, max_redirects, NULL, NULL,
    approved_by, approved_at, expires_at, consumed_at
FROM controlled_fetch_approvals_0018_old;

DROP TABLE controlled_fetch_approvals_0018_old;

-- ---- CONTROLLED_FETCH branch: the exact 0018 floors, scoped to the branch --

CREATE TRIGGER controlled_fetch_approvals_bind_frozen_job
BEFORE INSERT ON controlled_fetch_approvals
WHEN NEW.action_type = 'CONTROLLED_FETCH' AND NOT EXISTS (
    SELECT 1 FROM jobs j
    WHERE j.id = NEW.job_id
      AND j.account_id = NEW.account_id
      AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH'
      AND json_extract(j.payload_json, '$.execution') = 'controlled_fetch_v1'
      AND json_extract(j.payload_json, '$.dry_run') = 0
      AND json_extract(j.payload_json, '$.account_id') = NEW.account_id
      AND json_extract(j.payload_json, '$.execution_intent.requested_url') = NEW.requested_url
      AND json_extract(j.payload_json, '$.execution_intent.fingerprint') = NEW.intent_fingerprint
      AND json_extract(j.payload_json, '$.execution_intent.timeout_seconds') = NEW.timeout_seconds
      AND json_extract(j.payload_json, '$.execution_intent.max_bytes') = NEW.max_bytes
      AND json_extract(j.payload_json, '$.execution_intent.max_redirects') = NEW.max_redirects
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch approval must bind the exact frozen controlled_fetch_v1 job contract');
END;

-- ---- EVIDENCE_RESEARCH branch floors ---------------------------------------

-- The approval may only ever bind one durable evidence-research job of the
-- same account and topic whose persisted payload declares an evidence input.
CREATE TRIGGER controlled_fetch_approvals_bind_frozen_evidence_job
BEFORE INSERT ON controlled_fetch_approvals
WHEN NEW.action_type = 'EVIDENCE_RESEARCH' AND NOT EXISTS (
    SELECT 1 FROM jobs j
    WHERE j.id = NEW.job_id
      AND j.account_id = NEW.account_id
      AND j.topic_id = NEW.topic_id
      AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH'
      AND json_extract(j.payload_json, '$.execution') = 'durable_provider_v2'
      AND json_extract(j.payload_json, '$.dry_run') = 0
      AND json_extract(j.payload_json, '$.account_id') = NEW.account_id
      AND json_extract(j.payload_json, '$.topic_id') = NEW.topic_id
      AND json_extract(j.payload_json, '$.execution_intent.evidence_input') IS NOT NULL
)
BEGIN
    SELECT RAISE(ABORT,
        'evidence research approval must bind one durable evidence-research job of the same account and topic');
END;

-- The stored execution intent JSON IS the preimage of the stored fingerprint.
-- Recomputed inside SQLite via the registered deterministic application
-- function; a writer without the function cannot INSERT at all (fail closed).
CREATE TRIGGER controlled_fetch_approvals_evidence_preimage_hash
BEFORE INSERT ON controlled_fetch_approvals
WHEN NEW.action_type = 'EVIDENCE_RESEARCH'
 AND NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.execution_intent_json)
BEGIN
    SELECT RAISE(ABORT,
        'evidence research approval fingerprint must be the SHA-256 of its frozen execution_intent_json');
END;

-- ---- Shared floors (both branches) -----------------------------------------

CREATE TRIGGER controlled_fetch_approvals_born_unconsumed
BEFORE INSERT ON controlled_fetch_approvals
WHEN NEW.consumed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'controlled fetch approval cannot be created already consumed');
END;

-- The only legal mutation in the approval''s whole life: one consumption
-- transition NULL -> timestamp with every other column byte-identical.
CREATE TRIGGER controlled_fetch_approvals_consume_exactly_once
BEFORE UPDATE ON controlled_fetch_approvals
WHEN NOT (
    OLD.consumed_at IS NULL
    AND NEW.consumed_at IS NOT NULL
    AND NEW.id = OLD.id AND NEW.job_id = OLD.job_id
    AND NEW.account_id = OLD.account_id AND NEW.action_type = OLD.action_type
    AND NEW.requested_url IS OLD.requested_url
    AND NEW.intent_fingerprint = OLD.intent_fingerprint
    AND NEW.timeout_seconds IS OLD.timeout_seconds
    AND NEW.max_bytes IS OLD.max_bytes
    AND NEW.max_redirects IS OLD.max_redirects
    AND NEW.topic_id IS OLD.topic_id
    AND NEW.execution_intent_json IS OLD.execution_intent_json
    AND NEW.approved_by = OLD.approved_by AND NEW.approved_at = OLD.approved_at
    AND NEW.expires_at = OLD.expires_at
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch approval permits only one immutable consumption transition');
END;

CREATE TRIGGER controlled_fetch_approvals_consume_before_expiry
BEFORE UPDATE ON controlled_fetch_approvals
WHEN OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL
     AND NEW.consumed_at >= OLD.expires_at
BEGIN
    SELECT RAISE(ABORT, 'controlled fetch approval cannot be consumed after expiry');
END;

CREATE TRIGGER controlled_fetch_approvals_no_delete
BEFORE DELETE ON controlled_fetch_approvals
BEGIN SELECT RAISE(ABORT, 'controlled_fetch_approvals is append-only'); END;

-- ---- Recreate the 0018 controlled-fetch attempt floor unchanged ------------

CREATE TRIGGER controlled_fetch_attempts_bind_consumed_approval
BEFORE INSERT ON controlled_fetch_attempts
WHEN NOT EXISTS (
    SELECT 1
    FROM jobs j
    JOIN controlled_fetch_approvals a ON a.id = NEW.approval_id
    JOIN runs r ON r.id = NEW.run_id
    WHERE j.id = NEW.job_id
      AND j.account_id = NEW.account_id
      AND j.topic_id = NEW.topic_id
      AND j.run_id = NEW.run_id
      AND j.kind = 'RESEARCH'
      AND j.workflow = 'RESEARCH'
      AND json_extract(j.payload_json, '$.execution') = 'controlled_fetch_v1'
      AND json_extract(j.payload_json, '$.execution_intent.requested_url') = NEW.requested_url
      AND json_extract(j.payload_json, '$.execution_intent.fingerprint') = NEW.intent_fingerprint
      AND json_extract(j.payload_json, '$.execution_intent.source_identity') = NEW.source_identity
      AND r.account_id = NEW.account_id
      AND r.workflow = 'RESEARCH'
      AND a.job_id = NEW.job_id
      AND a.account_id = NEW.account_id
      AND a.action_type = 'CONTROLLED_FETCH'
      AND a.requested_url = NEW.requested_url
      AND a.intent_fingerprint = NEW.intent_fingerprint
      AND a.consumed_at IS NOT NULL
      AND a.expires_at > NEW.reserved_at
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch attempt must bind a consumed approval and the frozen job contract');
END;

-- ---- Provider attempt floors for evidence research -------------------------

-- An evidence-research provider attempt is unrepresentable without one
-- already-consumed, unexpired approval whose fingerprint equals the attempt''s
-- immutable execution_intent_fingerprint.  A payload mutated after approval
-- yields a different fingerprint and therefore cannot reserve an attempt.
CREATE TRIGGER provider_attempts_evidence_research_requires_consumed_approval
BEFORE INSERT ON provider_attempts
WHEN json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution') = 'durable_provider_v2'
 AND json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution_intent.evidence_input') IS NOT NULL
 AND NOT EXISTS (
    SELECT 1 FROM controlled_fetch_approvals a
    WHERE a.job_id = NEW.job_id
      AND a.action_type = 'EVIDENCE_RESEARCH'
      AND a.consumed_at IS NOT NULL
      AND a.expires_at > NEW.reserved_at
      AND a.intent_fingerprint = NEW.execution_intent_fingerprint
)
BEGIN
    SELECT RAISE(ABORT,
        'evidence research provider attempt requires one consumed matching L1 approval');
END;

-- The one-shot consent authorizes exactly one research attempt.
CREATE TRIGGER provider_attempts_evidence_research_single_attempt
BEFORE INSERT ON provider_attempts
WHEN json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution') = 'durable_provider_v2'
 AND json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution_intent.evidence_input') IS NOT NULL
 AND (NEW.stage != 'research' OR NEW.attempt_no != 1)
BEGIN
    SELECT RAISE(ABORT,
        'evidence research supports exactly one attempt of the research stage');
END;

COMMIT;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
