-- WAVE 1A: durable, operator-only reconciliation.  `model_usage` remains the
-- sole canonical cost ledger; the append-only `reconciliation_events` table is
-- the authoritative operator audit history.  The summary columns on
-- provider_attempts hold only the terminal outcome and are NULL in every
-- non-terminal state, so history can never live solely on the attempt row.
--
-- This migration is a full in-place rebuild of the WAVE 1A contract.  It keeps
-- every 0010-0013 invariant (the provider_attempts table rebuild auto-drops the
-- triggers defined on it, so all are recreated below) and adds:
--   * a complete state matrix with trimmed, enumerated audit fields;
--   * terminal RECONCILED_* immutability and un-deletability;
--   * the append-only reconciliation_events log;
--   * exclusive Research Card ownership on research_runs;
--   * a tightened model_usage insert relation;
--   * the crash/failure-window escalation contract: a RESERVED attempt whose
--     execution failed before the request boundary may be escalated to
--     NEEDS_RECONCILIATION with one of the controlled before-request reasons;
--     such an attempt (request_started_at stays NULL) may only terminalize as
--     RECONCILED_RELEASED;
--   * full terminalization atomicity at the SQLite layer (W1A-SQLITE-01): an
--     attempt may only become RECONCILED_* when, in the same transaction, the
--     job/run/research_run lifecycle is terminal and consistent with the
--     resolution, a matching FINAL_RESOLUTION event exists, the reservation is
--     released, and the cost caches equal the canonical model_usage ledger;
--   * canonical-ledger immutability after terminal reconciliation
--     (W1A-SQLITE-02): the canonical model_usage row of a reconciled attempt
--     cannot be updated or deleted, and the run cost caches are frozen.

-- model_usage triggers live on model_usage (not auto-dropped by the rebuild):
-- drop only the two relation triggers we tighten below.
DROP TRIGGER IF EXISTS model_usage_requires_request_job_run_relation;
DROP TRIGGER IF EXISTS model_usage_request_job_run_relation_on_update;
DROP TRIGGER IF EXISTS model_usage_reconciled_attempt_is_immutable;
DROP TRIGGER IF EXISTS model_usage_reconciled_attempt_no_delete;
DROP TRIGGER IF EXISTS runs_cost_cache_frozen_after_reconciliation;
DROP TRIGGER IF EXISTS research_runs_cost_cache_frozen_after_reconciliation;
DROP TRIGGER IF EXISTS jobs_terminal_requires_provider_attempt_normalized;
DROP TRIGGER IF EXISTS runs_terminal_requires_provider_attempt_normalized;
DROP TRIGGER IF EXISTS research_runs_terminal_requires_provider_attempt_normalized;
-- provider_attempts triggers are auto-dropped by the table rebuild; drop
-- defensively so a partially-migrated database still rebuilds cleanly.
DROP TRIGGER IF EXISTS provider_attempts_initial_state;
DROP TRIGGER IF EXISTS provider_attempts_request_id_matches_identity;
DROP TRIGGER IF EXISTS provider_attempts_no_retry_without_resolver;
DROP TRIGGER IF EXISTS provider_attempts_identity_is_immutable;
DROP TRIGGER IF EXISTS provider_attempts_execution_intent_fingerprint_is_immutable;
DROP TRIGGER IF EXISTS provider_attempts_durable_v2_requires_execution_intent_fingerprint;
DROP TRIGGER IF EXISTS provider_attempts_controlled_transition;
DROP TRIGGER IF EXISTS provider_attempts_no_delete_with_nonlegacy_usage;

CREATE TABLE provider_attempts_0014_new (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL CHECK (length(stage) BETWEEN 1 AND 64)
        CHECK (stage NOT GLOB '*[^a-z0-9_-]*'),
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    request_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN (
        'RESERVED','REQUEST_STARTED','SETTLED','RELEASED','NEEDS_RECONCILIATION',
        'RECONCILED_SETTLED','RECONCILED_RELEASED'
    )),
    reserved_amount_usd REAL NOT NULL CHECK (typeof(reserved_amount_usd) IN ('integer','real'))
        CHECK (reserved_amount_usd > 0) CHECK (reserved_amount_usd = reserved_amount_usd)
        CHECK (abs(reserved_amount_usd) <= 1.7976931348623157e308),
    reserved_at TEXT NOT NULL,
    request_started_at TEXT,
    settled_at TEXT,
    released_at TEXT,
    actual_cost_usd REAL CHECK (actual_cost_usd IS NULL OR (
        typeof(actual_cost_usd) IN ('integer','real') AND actual_cost_usd >= 0
        AND actual_cost_usd = actual_cost_usd AND abs(actual_cost_usd) <= 1.7976931348623157e308
    )),
    error_code TEXT,
    execution_intent_fingerprint TEXT,
    reconciled_at TEXT,
    reconciled_by TEXT,
    reconciliation_note TEXT,
    reconciliation_resolution TEXT,
    PRIMARY KEY (job_id, stage, attempt_no),
    -- Full state matrix.  Non-terminal states forbid every audit column; the two
    -- terminal states require trimmed operator + note and an enumerated combined
    -- resolution.  Costs never live here: RECONCILED_SETTLED keeps actual_cost_usd
    -- NULL and relies on the canonical model_usage ledger (trigger below).
    CHECK (
        (status='RESERVED' AND request_started_at IS NULL AND settled_at IS NULL AND released_at IS NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        OR (status='REQUEST_STARTED' AND request_started_at IS NOT NULL AND settled_at IS NULL AND released_at IS NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        OR (status='NEEDS_RECONCILIATION' AND request_started_at IS NOT NULL AND settled_at IS NULL AND released_at IS NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        -- A never-started reconciliation is representable only through one of
        -- the two controlled RESERVED escalation boundaries.
        OR (status='NEEDS_RECONCILIATION' AND request_started_at IS NULL AND settled_at IS NULL AND released_at IS NULL AND actual_cost_usd IS NULL
            AND error_code IN ('LEASE_EXPIRED_BEFORE_REQUEST_STARTED','UNEXPECTED_EXECUTION_FAILURE_BEFORE_REQUEST_STARTED')
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        OR (status='SETTLED' AND request_started_at IS NOT NULL AND settled_at IS NOT NULL AND released_at IS NULL AND actual_cost_usd IS NOT NULL
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        OR (status='RELEASED' AND request_started_at IS NULL AND settled_at IS NULL AND released_at IS NOT NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NULL AND reconciled_by IS NULL AND reconciliation_note IS NULL AND reconciliation_resolution IS NULL)
        OR (status='RECONCILED_SETTLED' AND request_started_at IS NOT NULL AND settled_at IS NOT NULL AND released_at IS NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NOT NULL
            AND reconciled_by IS NOT NULL AND length(trim(reconciled_by, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
            AND reconciliation_note IS NOT NULL AND length(trim(reconciliation_note, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
            AND reconciliation_resolution IN ('CHARGED_KNOWN:EXECUTION_FAILED','CHARGED_KNOWN:RESULT_ALREADY_FINALIZED'))
        -- RECONCILED_RELEASED accepts a NULL request_started_at: an escalated
        -- never-started RESERVED attempt is resolved NOT_CHARGED (W1A-AUD-04).
        OR (status='RECONCILED_RELEASED' AND settled_at IS NULL AND released_at IS NOT NULL AND actual_cost_usd IS NULL
            AND reconciled_at IS NOT NULL
            AND reconciled_by IS NOT NULL AND length(trim(reconciled_by, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
            AND reconciliation_note IS NOT NULL AND length(trim(reconciliation_note, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
            AND reconciliation_resolution IN ('NOT_CHARGED:EXECUTION_FAILED','NOT_CHARGED:RESULT_ALREADY_FINALIZED'))
    )
);
INSERT INTO provider_attempts_0014_new (
    job_id,stage,attempt_no,request_id,status,reserved_amount_usd,reserved_at,
    request_started_at,settled_at,released_at,actual_cost_usd,error_code,execution_intent_fingerprint
)
SELECT job_id,stage,attempt_no,request_id,status,reserved_amount_usd,reserved_at,
       request_started_at,settled_at,released_at,actual_cost_usd,error_code,execution_intent_fingerprint
FROM provider_attempts;
DROP TABLE provider_attempts;
ALTER TABLE provider_attempts_0014_new RENAME TO provider_attempts;

CREATE INDEX ix_provider_attempts_active_reservations
    ON provider_attempts(status, reserved_at)
    WHERE status IN ('RESERVED','REQUEST_STARTED','NEEDS_RECONCILIATION');

-- ---- provider_attempts invariants (0011-0013 preserved) --------------------
CREATE TRIGGER provider_attempts_initial_state BEFORE INSERT ON provider_attempts
WHEN NEW.status != 'RESERVED' BEGIN SELECT RAISE(ABORT, 'provider_attempt must start RESERVED'); END;
CREATE TRIGGER provider_attempts_request_id_matches_identity BEFORE INSERT ON provider_attempts
WHEN NEW.request_id != NEW.job_id || ':' || NEW.stage || ':' || NEW.attempt_no
BEGIN SELECT RAISE(ABORT, 'provider_attempt request_id does not match identity'); END;
CREATE TRIGGER provider_attempts_no_retry_without_resolver BEFORE INSERT ON provider_attempts
WHEN NEW.attempt_no > 1 AND EXISTS (SELECT 1 FROM provider_attempts p WHERE p.job_id=NEW.job_id AND p.stage=NEW.stage)
BEGIN SELECT RAISE(ABORT, 'provider_attempt retry requires explicit reconciliation resolver'); END;
CREATE TRIGGER provider_attempts_identity_is_immutable BEFORE UPDATE OF job_id,stage,attempt_no,request_id ON provider_attempts
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.stage IS NOT OLD.stage OR NEW.attempt_no IS NOT OLD.attempt_no OR NEW.request_id IS NOT OLD.request_id
BEGIN SELECT RAISE(ABORT, 'provider_attempt identity is immutable'); END;
CREATE TRIGGER provider_attempts_execution_intent_fingerprint_is_immutable BEFORE UPDATE OF execution_intent_fingerprint ON provider_attempts
WHEN NEW.execution_intent_fingerprint IS NOT OLD.execution_intent_fingerprint
BEGIN SELECT RAISE(ABORT, 'provider_attempt execution intent fingerprint is immutable'); END;
CREATE TRIGGER provider_attempts_durable_v2_requires_execution_intent_fingerprint BEFORE INSERT ON provider_attempts
WHEN json_extract((SELECT payload_json FROM jobs WHERE id=NEW.job_id), '$.execution')='durable_provider_v2'
 AND (NEW.execution_intent_fingerprint IS NULL OR length(NEW.execution_intent_fingerprint)!=64 OR NEW.execution_intent_fingerprint GLOB '*[^0-9a-f]*')
BEGIN SELECT RAISE(ABORT, 'durable_provider_v2 attempt requires immutable execution intent fingerprint'); END;

-- Controlled transitions.  The only moves out of NEEDS_RECONCILIATION are to the
-- two terminal reconciled states; observations are append-only events and never
-- touch the attempt, so the old NEEDS_RECONCILIATION self-loop is removed.
-- The RESERVED escalation arm accepts only the maintenance lease-expiry reason
-- or the centralized worker failure-boundary reason.
CREATE TRIGGER provider_attempts_controlled_transition BEFORE UPDATE ON provider_attempts
WHEN NOT (
 (OLD.status='RESERVED' AND NEW.status='REQUEST_STARTED' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS NOT NULL AND NEW.settled_at IS NULL AND NEW.released_at IS NULL AND NEW.actual_cost_usd IS NULL)
 OR (OLD.status='RESERVED' AND NEW.status='RELEASED' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS NULL AND NEW.settled_at IS NULL AND NEW.released_at IS NOT NULL AND NEW.actual_cost_usd IS NULL)
 OR (OLD.status='RESERVED' AND NEW.status='NEEDS_RECONCILIATION' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS NULL AND NEW.settled_at IS NULL AND NEW.released_at IS NULL AND NEW.actual_cost_usd IS NULL AND NEW.error_code IN ('LEASE_EXPIRED_BEFORE_REQUEST_STARTED','UNEXPECTED_EXECUTION_FAILURE_BEFORE_REQUEST_STARTED'))
 OR (OLD.status='REQUEST_STARTED' AND NEW.status='SETTLED' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS OLD.request_started_at AND NEW.settled_at IS NOT NULL AND NEW.released_at IS NULL AND NEW.actual_cost_usd IS NOT NULL)
 OR (OLD.status='REQUEST_STARTED' AND NEW.status='NEEDS_RECONCILIATION' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS OLD.request_started_at AND NEW.settled_at IS NULL AND NEW.released_at IS NULL AND NEW.actual_cost_usd IS NULL)
 OR (OLD.status='NEEDS_RECONCILIATION' AND NEW.status='RECONCILED_SETTLED' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS OLD.request_started_at AND NEW.settled_at IS NOT NULL AND NEW.released_at IS NULL AND NEW.actual_cost_usd IS NULL AND NEW.reconciled_at IS NOT NULL AND NEW.reconciled_by IS NOT NULL AND NEW.reconciliation_note IS NOT NULL AND NEW.reconciliation_resolution IS NOT NULL)
 OR (OLD.status='NEEDS_RECONCILIATION' AND NEW.status='RECONCILED_RELEASED' AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd AND NEW.reserved_at IS OLD.reserved_at AND NEW.request_started_at IS OLD.request_started_at AND NEW.settled_at IS NULL AND NEW.released_at IS NOT NULL AND NEW.actual_cost_usd IS NULL AND NEW.reconciled_at IS NOT NULL AND NEW.reconciled_by IS NOT NULL AND NEW.reconciliation_note IS NOT NULL AND NEW.reconciliation_resolution IS NOT NULL)
) BEGIN SELECT RAISE(ABORT, 'provider_attempt transition is not allowed'); END;

-- W1A-R4-01 durable-state floor.  StoragePort performs the semantic failure
-- normalization atomically.  These guards make a terminal lifecycle row
-- unrepresentable while the linked attempt is still RESERVED/REQUEST_STARTED.
-- They deliberately allow NEEDS_RECONCILIATION so the authorized resolver can
-- build its consistent terminal state in one transaction.  As SQL constraints,
-- they do not prove provenance against a privileged writer that can mutate many
-- tables in a different permitted order.
CREATE TRIGGER jobs_terminal_requires_provider_attempt_normalized
BEFORE UPDATE OF status ON jobs
WHEN NEW.status IN ('DONE','FAILED','CANCELLED') AND NEW.status IS NOT OLD.status
 AND EXISTS (
   SELECT 1 FROM provider_attempts p
   WHERE p.job_id=OLD.id AND p.status IN ('RESERVED','REQUEST_STARTED')
 )
BEGIN SELECT RAISE(ABORT, 'terminal job requires provider_attempt normalization'); END;

CREATE TRIGGER runs_terminal_requires_provider_attempt_normalized
BEFORE UPDATE OF status ON runs
WHEN NEW.status IN ('SUCCESS','FAILED','STOPPED','DRY_RUN') AND NEW.status IS NOT OLD.status
 AND EXISTS (
   SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
   WHERE j.run_id=OLD.id AND p.status IN ('RESERVED','REQUEST_STARTED')
 )
BEGIN SELECT RAISE(ABORT, 'terminal run requires provider_attempt normalization'); END;

CREATE TRIGGER research_runs_terminal_requires_provider_attempt_normalized
BEFORE UPDATE OF status ON research_runs
WHEN NEW.status IN ('COMPLETE','FAILED') AND NEW.status IS NOT OLD.status
 AND EXISTS (
   SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
   WHERE j.run_id=OLD.id AND p.status IN ('RESERVED','REQUEST_STARTED')
 )
BEGIN SELECT RAISE(ABORT, 'terminal research_run requires provider_attempt normalization'); END;

-- Terminal reconciled attempts are immutable and un-deletable.  The DELETE guard
-- closes the RECONCILED_RELEASED gap (no usage, so the non-legacy-usage guard did
-- not cover it).
CREATE TRIGGER provider_attempts_reconciled_terminal_is_immutable BEFORE UPDATE ON provider_attempts
WHEN OLD.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
BEGIN SELECT RAISE(ABORT, 'reconciled terminal provider_attempt is immutable'); END;
CREATE TRIGGER provider_attempts_reconciled_terminal_no_delete BEFORE DELETE ON provider_attempts
WHEN OLD.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
BEGIN SELECT RAISE(ABORT, 'reconciled terminal provider_attempt cannot be deleted'); END;

-- 0013 ledger reference guard.
CREATE TRIGGER provider_attempts_no_delete_with_nonlegacy_usage BEFORE DELETE ON provider_attempts
WHEN EXISTS (SELECT 1 FROM model_usage u WHERE u.request_id=OLD.request_id AND u.dry_run=0 AND u.is_legacy_usage=0)
BEGIN SELECT RAISE(ABORT, 'provider_attempt is referenced by non-legacy model_usage'); END;

-- Financial ledger coupling: settled requires exactly the canonical usage,
-- released forbids any.
CREATE TRIGGER provider_attempts_reconciled_settled_requires_canonical_usage
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status='RECONCILED_SETTLED'
 AND NOT EXISTS (SELECT 1 FROM model_usage u WHERE u.request_id=NEW.request_id AND u.dry_run=0 AND u.is_legacy_usage=0)
BEGIN SELECT RAISE(ABORT, 'reconciled settled attempt requires canonical non-legacy model_usage'); END;
CREATE TRIGGER provider_attempts_reconciled_released_forbids_canonical_usage
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status='RECONCILED_RELEASED'
 AND EXISTS (SELECT 1 FROM model_usage u WHERE u.request_id=NEW.request_id AND u.dry_run=0 AND u.is_legacy_usage=0)
BEGIN SELECT RAISE(ABORT, 'reconciled released attempt forbids canonical non-legacy model_usage'); END;

-- ---- W1A-SQLITE-01: full terminalization atomicity floor -------------------
-- The application terminalizes in one transaction and flips the attempt LAST:
-- validation -> lifecycle -> usage/cache -> FINAL_RESOLUTION event -> attempt.
-- These triggers make a terminal attempt unrepresentable unless the whole
-- consistent end state already exists in the same transaction.

-- A terminal attempt requires its exact FINAL_RESOLUTION event (same request,
-- same resulting status, same combined resolution, same operator and note).
CREATE TRIGGER provider_attempts_terminal_requires_final_event
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM reconciliation_events e
   WHERE e.request_id=NEW.request_id AND e.event_type='FINAL_RESOLUTION'
     AND e.resulting_attempt_status=NEW.status
     AND e.financial_resolution || ':' || e.execution_resolution = NEW.reconciliation_resolution
     AND e.operator=NEW.reconciled_by AND e.note=NEW.reconciliation_note
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires a matching FINAL_RESOLUTION event'); END;

-- A terminal attempt requires a terminal job/run/research_run lifecycle that is
-- consistent with the execution resolution, with the reservation released.
CREATE TRIGGER provider_attempts_terminal_requires_terminal_lifecycle
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
     AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
     AND (
       (NEW.reconciliation_resolution LIKE '%:EXECUTION_FAILED'
         AND j.status='FAILED' AND r.status='FAILED' AND rr.status='FAILED'
         AND rr.research_card_id IS NULL)
       OR
       (NEW.reconciliation_resolution LIKE '%:RESULT_ALREADY_FINALIZED'
         AND j.status='DONE' AND r.status='SUCCESS' AND rr.status='COMPLETE'
         AND rr.research_card_id IS NOT NULL)
     )
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires a terminal consistent lifecycle'); END;

-- A terminal attempt requires both cost caches to equal the canonical ledger
-- (research-task usage summed per run; tolerance is half of the USD quantum so
-- binary-float noise can never fail a correct Decimal settlement).
CREATE TRIGGER provider_attempts_terminal_requires_consistent_cost_cache
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION' AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND abs(r.cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd) FROM model_usage u
           WHERE u.run_id=j.run_id AND u.task IN
             ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005
     AND abs(rr.total_cost_usd - COALESCE((SELECT SUM(u.estimated_cost_usd) FROM model_usage u
           WHERE u.run_id=j.run_id AND u.task IN
             ('research','research_discover','research_extract','research_synthesize_cards','research_reconciliation')),0)) < 0.0000005
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires cost caches equal to the canonical ledger'); END;

-- Defense-in-depth lineage floor (W1A-VERIFY-02): a terminal reconciliation may
-- only be written when the whole durable relation agrees.  The application layer
-- validates the same relation (with the fingerprint recompute the SQL layer
-- cannot do), but this trigger makes a foreign runs.account_id, a non-research
-- runs.workflow, a cross-account/topic research_run, a wrong flow, a wrong job
-- kind/workflow, or a payload identity that disagrees with the job unrepresentable
-- as a terminal reconciled attempt.  json_extract failure (NULL) fails closed.
CREATE TRIGGER provider_attempts_reconcile_requires_consistent_lineage
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM jobs j
   JOIN runs r ON r.id=j.run_id
   JOIN research_runs rr ON rr.id=j.run_id
   WHERE j.id=NEW.job_id
     AND j.kind='RESEARCH' AND j.workflow='RESEARCH'
     AND r.account_id=j.account_id AND r.workflow='RESEARCH'
     AND rr.account_id=j.account_id AND rr.topic_id=j.topic_id AND rr.flow='single'
     AND json_extract(j.payload_json,'$.account_id')=j.account_id
     AND json_extract(j.payload_json,'$.topic_id')=j.topic_id
     AND json_extract(j.payload_json,'$.execution_intent.account_id')=j.account_id
     AND json_extract(j.payload_json,'$.execution_intent.topic_id')=j.topic_id
 )
BEGIN SELECT RAISE(ABORT, 'reconciled attempt requires a consistent research lineage'); END;

-- ---- model_usage request->job->run relation (tightened) --------------------
-- New real usage may only be written while the attempt is actively RESERVED-past
-- (REQUEST_STARTED/SETTLED) or under active reconciliation (NEEDS_RECONCILIATION,
-- the resolver inserts before flipping to RECONCILED_SETTLED).  RECONCILED_SETTLED
-- is intentionally excluded: a terminal attempt never gains new usage.
CREATE TRIGGER model_usage_requires_request_job_run_relation BEFORE INSERT ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT EXISTS (
 SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id JOIN runs r ON r.id=j.run_id
 WHERE p.request_id=NEW.request_id AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
   AND j.run_id=NEW.run_id AND r.id=NEW.run_id AND r.account_id=j.account_id
) BEGIN SELECT RAISE(ABORT, 'new real model_usage requires request->job->run relation'); END;
CREATE TRIGGER model_usage_request_job_run_relation_on_update BEFORE UPDATE OF run_id,request_id,dry_run,is_legacy_usage ON model_usage
WHEN NEW.dry_run=0 AND NEW.is_legacy_usage=0 AND NOT EXISTS (
 SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id JOIN runs r ON r.id=j.run_id
 WHERE p.request_id=NEW.request_id AND p.status IN ('REQUEST_STARTED','SETTLED','NEEDS_RECONCILIATION')
   AND j.run_id=NEW.run_id AND r.id=NEW.run_id AND r.account_id=j.account_id
) BEGIN SELECT RAISE(ABORT, 'updated real model_usage requires request->job->run relation'); END;

-- ---- W1A-SQLITE-02: canonical ledger immutability after reconciliation -----
-- The canonical usage row of a RECONCILED_* attempt is permanent history: no
-- column (cost, tokens, identity) may change and the row may not be deleted.
-- New usage for such an attempt is already unrepresentable (the insert relation
-- trigger excludes RECONCILED_* and request_id is UNIQUE).
CREATE TRIGGER model_usage_reconciled_attempt_is_immutable BEFORE UPDATE ON model_usage
WHEN OLD.dry_run=0 AND OLD.is_legacy_usage=0 AND OLD.request_id IS NOT NULL AND EXISTS (
 SELECT 1 FROM provider_attempts p WHERE p.request_id=OLD.request_id
   AND p.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
) BEGIN SELECT RAISE(ABORT, 'canonical model_usage of a reconciled attempt is immutable'); END;
CREATE TRIGGER model_usage_reconciled_attempt_no_delete BEFORE DELETE ON model_usage
WHEN OLD.dry_run=0 AND OLD.is_legacy_usage=0 AND OLD.request_id IS NOT NULL AND EXISTS (
 SELECT 1 FROM provider_attempts p WHERE p.request_id=OLD.request_id
   AND p.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
) BEGIN SELECT RAISE(ABORT, 'canonical model_usage of a reconciled attempt cannot be deleted'); END;

-- The run cost caches of a reconciled attempt's run are frozen: a raw cache
-- update without the ledger (or vice versa) is unrepresentable after the
-- terminal reconciliation.  The application refreshes both caches inside the
-- reconciliation transaction, before the attempt flip, so this never fires for
-- a correct settlement.
CREATE TRIGGER runs_cost_cache_frozen_after_reconciliation BEFORE UPDATE OF cost_usd ON runs
WHEN EXISTS (
 SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
 WHERE j.run_id=OLD.id AND p.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
) BEGIN SELECT RAISE(ABORT, 'run cost cache is frozen after terminal reconciliation'); END;
CREATE TRIGGER research_runs_cost_cache_frozen_after_reconciliation BEFORE UPDATE OF total_cost_usd ON research_runs
WHEN EXISTS (
 SELECT 1 FROM provider_attempts p JOIN jobs j ON j.id=p.job_id
 WHERE j.run_id=OLD.id AND p.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
) BEGIN SELECT RAISE(ABORT, 'research_run cost cache is frozen after terminal reconciliation'); END;

-- ---- append-only reconciliation audit history -----------------------------
CREATE TABLE reconciliation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 1),
    event_type TEXT NOT NULL CHECK (event_type IN ('UNRESOLVED_OBSERVATION','FOLLOW_UP','FINAL_RESOLUTION','AUTO_ESCALATION')),
    financial_resolution TEXT NOT NULL CHECK (financial_resolution IN ('CHARGED_KNOWN','NOT_CHARGED','CHARGE_UNKNOWN')),
    execution_resolution TEXT NOT NULL CHECK (execution_resolution IN ('EXECUTION_FAILED','RESULT_ALREADY_FINALIZED','MANUAL_REVIEW_REMAINS_REQUIRED')),
    operator TEXT NOT NULL CHECK (length(trim(operator, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0),
    note TEXT NOT NULL CHECK (length(trim(note, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0),
    previous_attempt_status TEXT NOT NULL,
    resulting_attempt_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    UNIQUE (request_id, sequence_number),
    -- event_type <-> resolution coherence
    CHECK (
        (event_type IN ('UNRESOLVED_OBSERVATION','FOLLOW_UP')
            AND financial_resolution='CHARGE_UNKNOWN'
            AND execution_resolution='MANUAL_REVIEW_REMAINS_REQUIRED'
            AND previous_attempt_status='NEEDS_RECONCILIATION'
            AND resulting_attempt_status='NEEDS_RECONCILIATION')
        -- W1A-AUD-04: durable audit of the automatic crash-window escalation.
        OR (event_type='AUTO_ESCALATION'
            AND ((previous_attempt_status='RESERVED' AND financial_resolution='NOT_CHARGED')
                 OR (previous_attempt_status='REQUEST_STARTED' AND financial_resolution='CHARGE_UNKNOWN'))
            AND execution_resolution='MANUAL_REVIEW_REMAINS_REQUIRED'
            AND resulting_attempt_status='NEEDS_RECONCILIATION')
        OR (event_type='FINAL_RESOLUTION'
            AND execution_resolution IN ('EXECUTION_FAILED','RESULT_ALREADY_FINALIZED')
            AND previous_attempt_status='NEEDS_RECONCILIATION'
            AND (
                (financial_resolution='CHARGED_KNOWN' AND resulting_attempt_status='RECONCILED_SETTLED')
                OR (financial_resolution='NOT_CHARGED' AND resulting_attempt_status='RECONCILED_RELEASED')
            ))
    )
);
CREATE INDEX ix_reconciliation_events_request ON reconciliation_events(request_id, sequence_number);

-- Per-attempt contiguous monotonic sequence.
CREATE TRIGGER reconciliation_events_sequence_is_monotonic BEFORE INSERT ON reconciliation_events
WHEN NEW.sequence_number != COALESCE((SELECT MAX(sequence_number) FROM reconciliation_events WHERE request_id=NEW.request_id), 0) + 1
BEGIN SELECT RAISE(ABORT, 'reconciliation_event sequence_number must be contiguous per attempt'); END;
-- Every event is written while the attempt is still actively reconciling: the
-- FINAL_RESOLUTION event precedes the terminal attempt flip in the same
-- transaction (the flip trigger then requires the matching event), and no event
-- of any kind may be appended to an already-terminal attempt.
CREATE TRIGGER reconciliation_events_require_active_attempt BEFORE INSERT ON reconciliation_events
WHEN (SELECT status FROM provider_attempts WHERE request_id=NEW.request_id) IS NOT 'NEEDS_RECONCILIATION'
BEGIN SELECT RAISE(ABORT, 'reconciliation_event requires an attempt in NEEDS_RECONCILIATION'); END;
-- Strictly append-only: no update, no delete, ever (blocks cascade deletes too).
CREATE TRIGGER reconciliation_events_no_update BEFORE UPDATE ON reconciliation_events
BEGIN SELECT RAISE(ABORT, 'reconciliation_events is append-only'); END;
CREATE TRIGGER reconciliation_events_no_delete BEFORE DELETE ON reconciliation_events
BEGIN SELECT RAISE(ABORT, 'reconciliation_events is append-only'); END;

-- ---- exclusive durable Research Card ownership ----------------------------
-- A finalized Research Card belongs to exactly one research_run.  This makes a
-- shared card unrepresentable, which is the durable proof RESULT_ALREADY_FINALIZED
-- relies on.
CREATE UNIQUE INDEX ux_research_runs_research_card
    ON research_runs(research_card_id)
    WHERE research_card_id IS NOT NULL;
