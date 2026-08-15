-- Stage 2 / Wave: durable autonomous TOPIC_GENERATION lifecycle.
--
-- This migration adds the smallest schema surface that makes one paid,
-- durable topic-generation request representable inside the EXISTING provider
-- lifecycle (one worker, one dispatcher, one policy engine, one
-- `provider_attempts` table, one `model_usage` ledger, one settlement and one
-- reconciliation mechanism).  It adds NO parallel ledger and NO second cost
-- accounting path.
--
-- It contains four things:
--   1. a `jobs` rebuild that admits the new `TOPIC_GENERATION` kind and pins
--      its defining contract: such a job NEVER carries a topic_id, because the
--      topic does not exist until the model has answered;
--   2. `topic_generation_approvals` — the durable, append-only, consume-exactly
--      -once human L1 consent for exactly one topic-generation job, storing the
--      COMPLETE canonical `execution_intent` JSON (the literal preimage of
--      `intent_fingerprint`) so the authoritative contract survives any later
--      mutation of the mutable `jobs.payload_json`;
--   3. `generated_topics` — the durable lineage that proves, after reopening
--      the database, which job/run/provider attempt/request produced which
--      topic, at which batch rank, and which single candidate was selected;
--   4. `provider_attempts` floors making a topic-generation attempt
--      unrepresentable without one consumed, unexpired, fingerprint-matching
--      approval, and limiting the whole consent to exactly one attempt.
--
-- Deliberately NOT added: any global `UNIQUE(account_id) WHERE
-- status='SELECTED'` on `topics`.  Production legitimately already holds
-- several SELECTED topics on one account.  The invariant this migration
-- enforces is strictly narrower and is carried by `generated_topics`:
-- AT MOST ONE topic may be marked selected BY A SINGLE topic-generation
-- execution (`ux_generated_topics_one_selected_per_run`).  Historical, fake and
-- owner-proposed topics keep no lineage row at all and remain fully legal.
--
-- Trust boundary (stated honestly, mirroring 0016/0018/0019): these floors bind
-- values persisted in this database to each other.  `evidence_sha256_hex` is
-- the deterministic application function registered by app.storage.db on every
-- controlled connection (0016 contract): a writer without it cannot INSERT a
-- topic-generation approval at all (fail closed), and a writer with the genuine
-- function cannot persist a fingerprint that is not the SHA-256 of the stored
-- preimage.  None of the floors defends against a writer who alters the schema
-- or drops triggers; that writer is outside the threat model.
--
-- Rebuilding `jobs` — a table with INCOMING foreign keys (provider_attempts,
-- controlled_fetch_attempts, controlled_fetch_approvals) — follows the
-- sanctioned SQLite rebuild procedure: BOTH foreign_keys=OFF AND
-- legacy_alter_table=ON.  Verified empirically against SQLite 3.49.1: under
-- these pragmas `ALTER TABLE jobs RENAME` rewrites ONLY the six triggers that
-- are themselves defined ON jobs (which are dropped together with the old
-- table and recreated verbatim below); no other trigger body and no other
-- table's REFERENCES clause is touched.  foreign_keys is a no-op inside a
-- transaction — so this migration manages its own explicit transaction (the
-- same contract as 0006 and 0019) and is intentionally NOT wrapped by the
-- transactional runner.  A fault inside the transaction rolls back both the
-- schema change and (because the ledger row is only written after a successful
-- script) the migration ledger.
PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

BEGIN IMMEDIATE;

-- ---- 1. jobs rebuild: admit TOPIC_GENERATION, pin topic_id IS NULL ---------

ALTER TABLE jobs RENAME TO jobs_0019_old;

CREATE TABLE jobs (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL CHECK (kind IN ('LOCAL', 'RESEARCH', 'BROWSER', 'TOPIC_GENERATION')),
    workflow            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'QUEUED'
                            CHECK (status IN (
                                'QUEUED', 'LEASED', 'RUNNING', 'DONE', 'FAILED',
                                'NEEDS_VERIFICATION', 'CANCELLED'
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
    -- The defining contract of the new kind: a topic-generation job cannot
    -- reference a topic, because no topic exists before the model answers.
    CHECK (kind != 'TOPIC_GENERATION' OR topic_id IS NULL),
    CHECK (
        (status IN ('LEASED', 'RUNNING')
            AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status NOT IN ('LEASED', 'RUNNING')
            AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);

INSERT INTO jobs (
    id, account_id, kind, workflow, status, priority, idempotency_key, topic_id,
    run_id, payload_json, schedule_reason, earliest_run_at, deadline_at,
    lease_owner, lease_expires_at, attempts, max_attempts, reserved_cost_usd,
    budget_reserved_at, external_effect_started_at, last_error, created_at,
    started_at, finished_at, updated_at
)
SELECT
    id, account_id, kind, workflow, status, priority, idempotency_key, topic_id,
    run_id, payload_json, schedule_reason, earliest_run_at, deadline_at,
    lease_owner, lease_expires_at, attempts, max_attempts, reserved_cost_usd,
    budget_reserved_at, external_effect_started_at, last_error, created_at,
    started_at, finished_at, updated_at
FROM jobs_0019_old;

DROP TABLE jobs_0019_old;

-- ---- 1a. recreate every pre-existing jobs index verbatim -------------------

CREATE INDEX ix_jobs_active_reservations
    ON jobs(status, budget_reserved_at)
    WHERE budget_reserved_at IS NOT NULL;

CREATE INDEX ix_jobs_claimable
    ON jobs(status, earliest_run_at, priority DESC, deadline_at, created_at);

CREATE UNIQUE INDEX ux_jobs_active_research_topic
    ON jobs(account_id, topic_id)
    WHERE kind = 'RESEARCH'
      AND topic_id IS NOT NULL
      AND status IN ('QUEUED', 'LEASED', 'RUNNING', 'NEEDS_VERIFICATION');

-- New: at most one ACTIVE topic-generation job per account.  The status set is
-- identical to the research index above, so it agrees with current scheduling
-- and never blocks a terminalized job from being followed by a new one.
CREATE UNIQUE INDEX ux_jobs_active_topic_generation_account
    ON jobs(account_id)
    WHERE kind = 'TOPIC_GENERATION'
      AND status IN ('QUEUED', 'LEASED', 'RUNNING', 'NEEDS_VERIFICATION');

-- ---- 1b. recreate every pre-existing jobs trigger verbatim -----------------

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
    json_extract(OLD.payload_json, '$.execution') = 'controlled_fetch_v1'
    OR json_extract(NEW.payload_json, '$.execution') = 'controlled_fetch_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN
    SELECT RAISE(ABORT, 'controlled_fetch_v1 job payload is immutable');
END;

CREATE TRIGGER jobs_controlled_fetch_terminal_requires_resolved_attempt
BEFORE UPDATE OF status ON jobs
WHEN NEW.status IN ('DONE','FAILED','CANCELLED','NEEDS_VERIFICATION')
 AND EXISTS (
    SELECT 1 FROM controlled_fetch_attempts a
    WHERE a.job_id = NEW.id AND a.status IN ('RESERVED','REQUEST_STARTED')
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch job cannot terminalize with an unresolved fetch attempt');
END;

CREATE TRIGGER jobs_controlled_fetch_done_requires_succeeded_attempt
BEFORE UPDATE OF status ON jobs
WHEN NEW.status = 'DONE'
 AND json_extract(NEW.payload_json, '$.execution') = 'controlled_fetch_v1'
 AND NOT EXISTS (
    SELECT 1 FROM controlled_fetch_attempts a
    WHERE a.job_id = NEW.id AND a.status = 'SUCCEEDED'
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch job DONE requires exactly one SUCCEEDED fetch attempt');
END;

-- ---- 1c. new floor: freeze the topic-generation payload after enqueue ------
-- The approval binds a fingerprint derived from this payload; allowing the
-- payload to drift afterwards would let a consumed consent authorize a
-- different request.
CREATE TRIGGER jobs_topic_generation_payload_frozen
BEFORE UPDATE OF payload_json ON jobs
WHEN (
    json_extract(OLD.payload_json, '$.execution') = 'durable_topic_generation_v1'
    OR json_extract(NEW.payload_json, '$.execution') = 'durable_topic_generation_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN
    SELECT RAISE(ABORT, 'durable_topic_generation_v1 job payload is immutable');
END;

-- ---- 2. durable one-shot L1 consent for one topic-generation job ----------

CREATE TABLE topic_generation_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT CHECK (
        length(trim(account_id, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    intent_fingerprint TEXT NOT NULL CHECK (
        length(intent_fingerprint) = 64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    execution_intent_json TEXT NOT NULL CHECK (
        json_valid(execution_intent_json) AND length(execution_intent_json) > 2
    ),
    model TEXT NOT NULL CHECK (
        length(trim(model, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    cap_usd TEXT NOT NULL CHECK (
        length(cap_usd) > 0 AND cap_usd NOT GLOB '*[^0-9.]*'
    ),
    max_tokens INTEGER NOT NULL CHECK (max_tokens BETWEEN 256 AND 8192),
    approved_by TEXT NOT NULL CHECK (
        length(trim(approved_by, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    approved_at TEXT NOT NULL CHECK (length(approved_at) >= 19),
    expires_at TEXT NOT NULL CHECK (length(expires_at) >= 19 AND expires_at > approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at) >= 19)
);

-- The approval may only ever bind one durable topic-generation job of the same
-- account whose persisted payload declares exactly this model, cap and output
-- limit — and which, by contract, carries no topic.
CREATE TRIGGER topic_generation_approvals_bind_frozen_job
BEFORE INSERT ON topic_generation_approvals
WHEN NOT EXISTS (
    SELECT 1 FROM jobs j
    WHERE j.id = NEW.job_id
      AND j.account_id = NEW.account_id
      AND j.kind = 'TOPIC_GENERATION'
      AND j.workflow = 'TOPIC_GENERATION'
      AND j.topic_id IS NULL
      AND json_extract(j.payload_json, '$.execution') = 'durable_topic_generation_v1'
      AND json_extract(j.payload_json, '$.dry_run') = 0
      AND json_extract(j.payload_json, '$.account_id') = NEW.account_id
      AND json_extract(j.payload_json, '$.execution_intent.account_id') = NEW.account_id
      AND json_extract(j.payload_json, '$.execution_intent.model') = NEW.model
      AND json_extract(j.payload_json, '$.execution_intent.cap_usd') = NEW.cap_usd
      AND json_extract(j.payload_json, '$.execution_intent.max_tokens') = NEW.max_tokens
)
BEGIN
    SELECT RAISE(ABORT,
        'topic generation approval must bind the exact frozen durable_topic_generation_v1 job contract');
END;

-- The stored execution intent JSON IS the preimage of the stored fingerprint.
-- Recomputed inside SQLite via the registered deterministic application
-- function; a writer without the function cannot INSERT at all (fail closed).
CREATE TRIGGER topic_generation_approvals_preimage_hash
BEFORE INSERT ON topic_generation_approvals
WHEN NEW.intent_fingerprint IS NOT evidence_sha256_hex(NEW.execution_intent_json)
BEGIN
    SELECT RAISE(ABORT,
        'topic generation approval fingerprint must be the SHA-256 of its frozen execution_intent_json');
END;

CREATE TRIGGER topic_generation_approvals_born_unconsumed
BEFORE INSERT ON topic_generation_approvals
WHEN NEW.consumed_at IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'topic generation approval cannot be created already consumed');
END;

-- The only legal mutation in the approval's whole life: one consumption
-- transition NULL -> timestamp with every other column byte-identical.
CREATE TRIGGER topic_generation_approvals_consume_exactly_once
BEFORE UPDATE ON topic_generation_approvals
WHEN NOT (
    OLD.consumed_at IS NULL
    AND NEW.consumed_at IS NOT NULL
    AND NEW.id = OLD.id AND NEW.job_id = OLD.job_id
    AND NEW.account_id = OLD.account_id
    AND NEW.intent_fingerprint = OLD.intent_fingerprint
    AND NEW.execution_intent_json = OLD.execution_intent_json
    AND NEW.model = OLD.model AND NEW.cap_usd = OLD.cap_usd
    AND NEW.max_tokens = OLD.max_tokens
    AND NEW.approved_by = OLD.approved_by AND NEW.approved_at = OLD.approved_at
    AND NEW.expires_at = OLD.expires_at
)
BEGIN
    SELECT RAISE(ABORT,
        'topic generation approval permits only one immutable consumption transition');
END;

CREATE TRIGGER topic_generation_approvals_consume_before_expiry
BEFORE UPDATE ON topic_generation_approvals
WHEN OLD.consumed_at IS NULL AND NEW.consumed_at IS NOT NULL
     AND NEW.consumed_at >= OLD.expires_at
BEGIN
    SELECT RAISE(ABORT, 'topic generation approval cannot be consumed after expiry');
END;

CREATE TRIGGER topic_generation_approvals_no_delete
BEFORE DELETE ON topic_generation_approvals
BEGIN SELECT RAISE(ABORT, 'topic_generation_approvals is append-only'); END;

-- ---- 3. provider attempt floors for topic generation ----------------------

-- A topic-generation provider attempt is unrepresentable without one
-- already-consumed, unexpired approval whose fingerprint equals the attempt's
-- immutable execution_intent_fingerprint.  A payload mutated after approval
-- yields a different fingerprint and therefore cannot reserve an attempt.
CREATE TRIGGER provider_attempts_topic_generation_requires_consumed_approval
BEFORE INSERT ON provider_attempts
WHEN json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution') = 'durable_topic_generation_v1'
 AND NOT EXISTS (
    SELECT 1 FROM topic_generation_approvals a
    WHERE a.job_id = NEW.job_id
      AND a.consumed_at IS NOT NULL
      AND a.expires_at > NEW.reserved_at
      AND a.intent_fingerprint = NEW.execution_intent_fingerprint
)
BEGIN
    SELECT RAISE(ABORT,
        'topic generation provider attempt requires one consumed matching L1 approval');
END;

-- The one-shot consent authorizes exactly one attempt of the topics stage.
CREATE TRIGGER provider_attempts_topic_generation_single_attempt
BEFORE INSERT ON provider_attempts
WHEN json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution') = 'durable_topic_generation_v1'
 AND (NEW.stage != 'topics' OR NEW.attempt_no != 1)
BEGIN
    SELECT RAISE(ABORT,
        'topic generation supports exactly one attempt of the topics stage');
END;

-- A topic-generation attempt is a durable frozen-intent attempt exactly like
-- durable_provider_v2, so it must carry the same immutable fingerprint.
CREATE TRIGGER provider_attempts_topic_generation_requires_fingerprint
BEFORE INSERT ON provider_attempts
WHEN json_extract(
        (SELECT payload_json FROM jobs WHERE id = NEW.job_id),
        '$.execution') = 'durable_topic_generation_v1'
 AND (NEW.execution_intent_fingerprint IS NULL
      OR length(NEW.execution_intent_fingerprint) != 64
      OR NEW.execution_intent_fingerprint GLOB '*[^0-9a-f]*')
BEGIN
    SELECT RAISE(ABORT,
        'durable_topic_generation_v1 attempt requires immutable execution intent fingerprint');
END;

-- ---- 4. durable lineage of every generated topic --------------------------

CREATE TABLE generated_topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id INTEGER NOT NULL UNIQUE REFERENCES topics(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    candidate_index INTEGER NOT NULL CHECK (candidate_index >= 0),
    is_selected INTEGER NOT NULL DEFAULT 0 CHECK (is_selected IN (0, 1)),
    created_at TEXT NOT NULL CHECK (length(created_at) >= 19),
    UNIQUE (run_id, candidate_index)
);

-- THE narrow invariant replacing any global SELECTED uniqueness: one
-- topic-generation execution may mark at most one of its candidates selected.
CREATE UNIQUE INDEX ux_generated_topics_one_selected_per_run
    ON generated_topics(run_id) WHERE is_selected = 1;

CREATE INDEX ix_generated_topics_job ON generated_topics(job_id);
CREATE INDEX ix_generated_topics_request ON generated_topics(request_id);

-- One insert must prove the whole chain job->run->attempt->topic, all inside
-- one account, and a selected row must really be a SELECTED topic.
CREATE TRIGGER generated_topics_integrity
BEFORE INSERT ON generated_topics
WHEN NOT EXISTS (
    SELECT 1
    FROM jobs j
    JOIN runs r ON r.id = j.run_id
    JOIN provider_attempts p ON p.job_id = j.id
    JOIN topics t ON t.id = NEW.topic_id
    WHERE j.id = NEW.job_id
      AND j.account_id = NEW.account_id
      AND j.kind = 'TOPIC_GENERATION'
      AND j.workflow = 'TOPIC_GENERATION'
      AND j.topic_id IS NULL
      AND j.run_id = NEW.run_id
      AND r.id = NEW.run_id
      AND r.account_id = NEW.account_id
      AND r.workflow = 'TOPIC_GENERATION'
      AND p.request_id = NEW.request_id
      AND p.stage = 'topics'
      AND p.attempt_no = 1
      AND t.account_id = NEW.account_id
      AND (NEW.is_selected = 0 OR t.status = 'SELECTED')
)
BEGIN
    SELECT RAISE(ABORT,
        'generated topic lineage must bind one consistent topic-generation job, run, attempt and topic');
END;

CREATE TRIGGER generated_topics_immutable
BEFORE UPDATE ON generated_topics
BEGIN SELECT RAISE(ABORT, 'generated_topics is append-only'); END;

CREATE TRIGGER generated_topics_no_delete
BEFORE DELETE ON generated_topics
BEGIN SELECT RAISE(ABORT, 'generated_topics is append-only'); END;

-- ---- 5. reconciliation floors for the second legal lifecycle --------------
--
-- 0014 defines reconciliation over RESEARCH.  TOPIC_GENERATION deliberately
-- has no research_run, so 0020 replaces only the three polymorphic terminal
-- floors with two explicit branches.  The RESEARCH predicates below are kept
-- semantically identical to 0014; the new branch proves job -> run -> attempt,
-- the consumed frozen approval and the exact topics:1 request identity.

-- 0015 originally authorized EXECUTION_RECOVERY only for a single RESEARCH
-- lifecycle.  Keep that branch semantically unchanged and add the one legal
-- TOPIC_GENERATION crash window: SETTLED + exactly one canonical topics usage
-- + no generated result.  The event remains the sole authorization and the
-- provider attempt stays SETTLED.
DROP TRIGGER IF EXISTS settled_execution_recovery_requires_consistent_prestate;
CREATE TRIGGER settled_execution_recovery_requires_consistent_prestate
BEFORE INSERT ON reconciliation_events
WHEN NEW.event_type='EXECUTION_RECOVERY' AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    LEFT JOIN research_runs rr ON rr.id=j.run_id
    LEFT JOIN topics t ON t.id=j.topic_id
    LEFT JOIN topic_generation_approvals a ON a.job_id=j.id
    WHERE p.request_id=NEW.request_id
      AND p.status='SETTLED' AND p.actual_cost_usd IS NOT NULL
      AND j.status='NEEDS_VERIFICATION'
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
      AND (
        (j.kind='RESEARCH' AND j.workflow='RESEARCH'
         AND r.account_id=j.account_id AND r.workflow='RESEARCH'
         AND rr.account_id=j.account_id AND rr.topic_id=j.topic_id AND rr.flow='single'
         AND t.account_id=j.account_id
         AND json_extract(j.payload_json,'$.account_id')=j.account_id
         AND json_extract(j.payload_json,'$.topic_id')=j.topic_id
         AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
         AND json_extract(j.payload_json,'$.execution_intent.topic_id')=j.topic_id
         AND (SELECT COUNT(*) FROM model_usage u
              WHERE u.request_id=p.request_id AND u.dry_run=0 AND u.is_legacy_usage=0)=1
         AND EXISTS (
             SELECT 1 FROM model_usage u
             WHERE u.request_id=p.request_id AND u.run_id=j.run_id
               AND u.dry_run=0 AND u.is_legacy_usage=0
               AND u.task IN ('research','research_gather','research_synthesize',
                              'research_discover','research_extract',
                              'research_synthesize_cards','research_reconciliation')
               AND u.provider=json_extract(j.payload_json,'$.execution_intent.provider')
               AND u.model=json_extract(j.payload_json,'$.execution_intent.model')
               AND abs(u.estimated_cost_usd-p.actual_cost_usd) < 0.0000005
         )
         AND abs(r.cost_usd - COALESCE((
             SELECT SUM(u.estimated_cost_usd) FROM model_usage u
             WHERE u.run_id=j.run_id AND u.task IN (
                 'research','research_gather','research_synthesize','research_discover',
                 'research_extract','research_synthesize_cards','research_reconciliation'
             )),0)) < 0.0000005
         AND (
             (rr.status='PENDING' AND abs(rr.total_cost_usd) < 0.0000005)
             OR
             (rr.status IN ('COMPLETE','FAILED')
              AND abs(rr.total_cost_usd - COALESCE((
                  SELECT SUM(u.estimated_cost_usd) FROM model_usage u
                  WHERE u.run_id=j.run_id AND u.task IN (
                      'research','research_gather','research_synthesize','research_discover',
                      'research_extract','research_synthesize_cards','research_reconciliation'
                  )),0)) < 0.0000005)
         )
         AND (
             (NEW.execution_resolution='EXECUTION_FAILED'
              AND rr.research_card_id IS NULL
              AND r.status IN ('RUNNING','STOPPED','FAILED')
              AND rr.status IN ('PENDING','FAILED'))
             OR
             (NEW.execution_resolution='RESULT_ALREADY_FINALIZED'
              AND rr.research_card_id IS NOT NULL
              AND r.status IN ('RUNNING','STOPPED','SUCCESS')
              AND rr.status IN ('PENDING','COMPLETE')
              AND EXISTS (
                  SELECT 1 FROM research_cards c
                  WHERE c.id=rr.research_card_id AND c.topic_id=rr.topic_id
              ))
         ))
        OR
        (j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
         AND j.topic_id IS NULL AND rr.id IS NULL
         AND r.account_id=j.account_id AND r.workflow='TOPIC_GENERATION'
         AND r.status IN ('RUNNING','STOPPED','FAILED')
         AND NEW.execution_resolution='EXECUTION_FAILED'
         AND p.stage='topics' AND p.attempt_no=1
         AND p.request_id=p.job_id || ':topics:1'
         AND (SELECT COUNT(*) FROM provider_attempts p2 WHERE p2.job_id=j.id)=1
         AND json_extract(j.payload_json,'$.execution')='durable_topic_generation_v1'
         AND json_extract(j.payload_json,'$.dry_run')=0
         AND json_extract(j.payload_json,'$.account_id')=j.account_id
         AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
         AND json_extract(j.payload_json,'$.execution_intent.workflow')='TOPIC_GENERATION'
         AND json_extract(j.payload_json,'$.execution_intent.stage')='topics'
         AND json_type(j.payload_json,'$.execution_intent.topic_id') IS NULL
         AND a.account_id=j.account_id AND a.consumed_at IS NOT NULL
         AND a.expires_at > p.reserved_at
         AND a.intent_fingerprint=p.execution_intent_fingerprint
         AND a.execution_intent_json=json_extract(j.payload_json,'$.execution_intent')
         AND (SELECT COUNT(*) FROM model_usage u WHERE u.run_id=j.run_id)=1
         AND EXISTS (
             SELECT 1 FROM model_usage u
             WHERE u.request_id=p.request_id AND u.run_id=j.run_id
               AND u.dry_run=0 AND u.is_legacy_usage=0 AND u.task='topics'
               AND u.provider=json_extract(j.payload_json,'$.execution_intent.provider')
               AND u.model=json_extract(j.payload_json,'$.execution_intent.model')
               AND abs(u.estimated_cost_usd-p.actual_cost_usd) < 0.0000005
         )
         AND abs(r.cost_usd - COALESCE((
             SELECT SUM(u.estimated_cost_usd) FROM model_usage u
             WHERE u.run_id=j.run_id AND u.task='topics'
         ),0)) < 0.0000005
         AND NOT EXISTS (
             SELECT 1 FROM generated_topics g
             WHERE g.job_id=j.id OR g.run_id=j.run_id OR g.request_id=p.request_id
         ))
      )
)
BEGIN SELECT RAISE(ABORT, 'execution recovery requires one consistent settled supported prestate'); END;

DROP TRIGGER IF EXISTS settled_execution_recovery_terminalizes_lifecycle;
CREATE TRIGGER settled_execution_recovery_terminalizes_lifecycle
AFTER INSERT ON reconciliation_events
WHEN NEW.event_type='EXECUTION_RECOVERY'
BEGIN
    UPDATE runs
    SET status=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN 'SUCCESS' ELSE 'FAILED' END,
        error=CASE
            WHEN NEW.execution_resolution='RESULT_ALREADY_FINALIZED' THEN NULL
            WHEN workflow='TOPIC_GENERATION' THEN
                COALESCE(error,'SETTLED_TOPIC_EXECUTION_RECOVERED_BEFORE_RESULT_FINALIZATION')
            ELSE COALESCE(error,'SETTLED_EXECUTION_RECOVERY_FAILED') END,
        finished_at=NEW.created_at
    WHERE id=(
        SELECT j.run_id FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
        WHERE p.request_id=NEW.request_id
    );

    UPDATE research_runs
    SET status=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN 'COMPLETE' ELSE 'FAILED' END,
        total_cost_usd=(
            SELECT p.actual_cost_usd FROM provider_attempts p
            WHERE p.request_id=NEW.request_id
        ),
        error=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN NULL
            ELSE 'SETTLED_EXECUTION_RECOVERY_FAILED' END,
        updated_at=NEW.created_at
    WHERE id=(
        SELECT j.run_id FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
        WHERE p.request_id=NEW.request_id
    );

    UPDATE topics SET status='USED'
    WHERE NEW.execution_resolution='RESULT_ALREADY_FINALIZED'
      AND id=(
          SELECT j.topic_id FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
          WHERE p.request_id=NEW.request_id
      ) AND status IN ('SELECTED','USED');

    UPDATE jobs
    SET status=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN 'DONE' ELSE 'FAILED' END,
        last_error=CASE
            WHEN NEW.execution_resolution='RESULT_ALREADY_FINALIZED' THEN NULL
            WHEN kind='TOPIC_GENERATION' THEN
                'SETTLED_TOPIC_EXECUTION_RECOVERED_BEFORE_RESULT_FINALIZATION'
            ELSE 'SETTLED_EXECUTION_RECOVERY:EXECUTION_FAILED' END,
        lease_owner=NULL,lease_expires_at=NULL,reserved_cost_usd=0.0,
        budget_reserved_at=NULL,
        external_effect_started_at=CASE
            WHEN kind='TOPIC_GENERATION' THEN NULL
            ELSE external_effect_started_at END,
        updated_at=NEW.created_at,finished_at=NEW.created_at
    WHERE id=(SELECT job_id FROM provider_attempts WHERE request_id=NEW.request_id)
      AND status='NEEDS_VERIFICATION';

    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM provider_attempts p
        JOIN jobs j ON j.id=p.job_id
        JOIN runs r ON r.id=j.run_id
        LEFT JOIN research_runs rr ON rr.id=j.run_id
        WHERE p.request_id=NEW.request_id AND p.status='SETTLED'
          AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
          AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
          AND (
            (j.kind='RESEARCH'
             AND ((NEW.execution_resolution='EXECUTION_FAILED'
                   AND j.status='FAILED' AND r.status='FAILED' AND rr.status='FAILED'
                   AND rr.research_card_id IS NULL)
                  OR
                  (NEW.execution_resolution='RESULT_ALREADY_FINALIZED'
                   AND j.status='DONE' AND r.status='SUCCESS' AND rr.status='COMPLETE'
                   AND rr.research_card_id IS NOT NULL)))
            OR
            (j.kind='TOPIC_GENERATION' AND NEW.execution_resolution='EXECUTION_FAILED'
             AND j.status='FAILED' AND r.status='FAILED' AND rr.id IS NULL
             AND j.external_effect_started_at IS NULL
             AND NOT EXISTS (
                 SELECT 1 FROM generated_topics g
                 WHERE g.job_id=j.id OR g.run_id=j.run_id OR g.request_id=p.request_id
             ))
          )
    ) THEN RAISE(ABORT, 'execution recovery did not produce a complete terminal lifecycle') END;
END;

DROP TRIGGER IF EXISTS provider_attempts_terminal_requires_terminal_lifecycle;
CREATE TRIGGER provider_attempts_terminal_requires_terminal_lifecycle
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
     AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
     AND (
       (j.kind='RESEARCH' AND j.workflow='RESEARCH'
        AND (
          (NEW.reconciliation_resolution LIKE '%:EXECUTION_FAILED'
           AND j.status='FAILED' AND r.status='FAILED' AND rr.status='FAILED'
           AND rr.research_card_id IS NULL)
          OR
          (NEW.reconciliation_resolution LIKE '%:RESULT_ALREADY_FINALIZED'
           AND j.status='DONE' AND r.status='SUCCESS' AND rr.status='COMPLETE'
           AND rr.research_card_id IS NOT NULL)
        ))
       OR
       (j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
        AND j.topic_id IS NULL AND r.workflow='TOPIC_GENERATION'
        AND r.account_id=j.account_id AND rr.id IS NULL
        AND NEW.reconciliation_resolution LIKE '%:EXECUTION_FAILED'
        AND j.status='FAILED' AND r.status='FAILED'
        AND j.external_effect_started_at IS NULL
        AND NOT EXISTS (
          SELECT 1 FROM generated_topics g
          WHERE g.job_id=j.id OR g.run_id=j.run_id OR g.request_id=NEW.request_id
        ))
     )
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires a terminal consistent lifecycle'); END;

DROP TRIGGER IF EXISTS provider_attempts_terminal_requires_consistent_cost_cache;
CREATE TRIGGER provider_attempts_terminal_requires_consistent_cost_cache
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND (
       (j.kind='RESEARCH'
        AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task IN
              ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005
        AND abs(rr.total_cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task IN
              ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005)
       OR
       (j.kind='TOPIC_GENERATION' AND rr.id IS NULL
        AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd)
              FROM model_usage u WHERE u.run_id=j.run_id AND u.task='topics'),0)) < 0.0000005)
     )
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires cost caches equal to the canonical ledger'); END;

DROP TRIGGER IF EXISTS provider_attempts_reconcile_requires_consistent_lineage;
CREATE TRIGGER provider_attempts_reconcile_requires_consistent_lineage
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   LEFT JOIN topic_generation_approvals a ON a.job_id=j.id
   WHERE j.id=NEW.job_id
     AND (
       (j.kind='RESEARCH' AND j.workflow='RESEARCH'
        AND r.account_id=j.account_id AND r.workflow='RESEARCH'
        AND rr.account_id=j.account_id AND rr.topic_id=j.topic_id AND rr.flow='single'
        AND json_extract(j.payload_json,'$.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.topic_id')=j.topic_id
        AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.topic_id')=j.topic_id)
       OR
       (j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
        AND j.topic_id IS NULL AND rr.id IS NULL
        AND r.account_id=j.account_id AND r.workflow='TOPIC_GENERATION'
        AND NEW.stage='topics' AND NEW.attempt_no=1
        AND NEW.request_id=NEW.job_id || ':topics:1'
        AND json_extract(j.payload_json,'$.execution')='durable_topic_generation_v1'
        AND json_extract(j.payload_json,'$.dry_run')=0
        AND json_extract(j.payload_json,'$.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
        AND json_extract(j.payload_json,'$.execution_intent.workflow')='TOPIC_GENERATION'
        AND json_extract(j.payload_json,'$.execution_intent.stage')='topics'
        AND json_type(j.payload_json,'$.execution_intent.topic_id') IS NULL
        AND a.account_id=j.account_id AND a.consumed_at IS NOT NULL
        AND a.intent_fingerprint=NEW.execution_intent_fingerprint
        AND a.execution_intent_json=json_extract(j.payload_json,'$.execution_intent'))
     )
 )
BEGIN SELECT RAISE(ABORT, 'reconciled attempt requires a consistent supported lineage'); END;

-- A charged topic reconciliation has exactly one canonical topics usage with
-- the provider/model frozen in the durable intent.  The existing UNIQUE
-- request_id floor prevents a second row; this trigger prevents a wrong task or
-- identity from satisfying the generic 0014 usage-exists floor.
CREATE TRIGGER provider_attempts_topic_generation_reconcile_requires_usage_identity
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status='RECONCILED_SETTLED'
 AND EXISTS (SELECT 1 FROM jobs j WHERE j.id=NEW.job_id AND j.kind='TOPIC_GENERATION')
 AND NOT EXISTS (
   SELECT 1 FROM model_usage u JOIN jobs j ON j.id=NEW.job_id
   WHERE u.request_id=NEW.request_id AND u.run_id=j.run_id
     AND u.dry_run=0 AND u.is_legacy_usage=0 AND u.task='topics'
     AND u.provider=json_extract(j.payload_json,'$.execution_intent.provider')
     AND u.model=json_extract(j.payload_json,'$.execution_intent.model')
 )
BEGIN SELECT RAISE(ABORT, 'charged topic reconciliation requires canonical topics usage identity'); END;

-- CHARGE_UNKNOWN is also protected by the topic lineage floor.  It remains an
-- append-only observation and does not release the reservation or unblock the
-- account; a later terminal decision is still legal for the same attempt.
CREATE TRIGGER reconciliation_events_topic_generation_requires_consistent_lineage
BEFORE INSERT ON reconciliation_events
WHEN EXISTS (
  SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
  WHERE p.request_id=NEW.request_id AND j.kind='TOPIC_GENERATION'
)
 AND NOT EXISTS (
   SELECT 1 FROM provider_attempts p
   JOIN jobs j ON j.id=p.job_id
   JOIN runs r ON r.id=j.run_id
   LEFT JOIN research_runs rr ON rr.id=j.run_id
   JOIN topic_generation_approvals a ON a.job_id=j.id
   WHERE p.request_id=NEW.request_id
     AND j.kind='TOPIC_GENERATION' AND j.workflow='TOPIC_GENERATION'
     AND j.topic_id IS NULL AND rr.id IS NULL
     AND r.account_id=j.account_id AND r.workflow='TOPIC_GENERATION'
     AND p.stage='topics' AND p.attempt_no=1
     AND p.request_id=p.job_id || ':topics:1'
     AND p.execution_intent_fingerprint=a.intent_fingerprint
     AND a.account_id=j.account_id AND a.consumed_at IS NOT NULL
     AND a.execution_intent_json=json_extract(j.payload_json,'$.execution_intent')
 )
BEGIN SELECT RAISE(ABORT, 'topic reconciliation event requires consistent topic-generation lineage'); END;

COMMIT;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
