-- PR1-MAJ-001: a provider request can be financially SETTLED before the worker
-- atomically persists its execution result.  Financial reconciliation is not
-- appropriate in that window: the canonical usage and actual cost are known.
--
-- This additive migration extends the existing append-only operator audit with
-- one execution-only event.  The attempt stays SETTLED.  Inserting the event is
-- the single SQLite authorization that terminalizes job/run/research_run; direct
-- terminalization of a reviewable SETTLED execution without the event is blocked.

DROP TRIGGER IF EXISTS provider_attempts_terminal_requires_final_event;
DROP TRIGGER IF EXISTS reconciliation_events_sequence_is_monotonic;
DROP TRIGGER IF EXISTS reconciliation_events_require_active_attempt;
DROP TRIGGER IF EXISTS reconciliation_events_no_update;
DROP TRIGGER IF EXISTS reconciliation_events_no_delete;

ALTER TABLE reconciliation_events RENAME TO reconciliation_events_0014_old;

CREATE TABLE reconciliation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES provider_attempts(request_id) ON DELETE RESTRICT,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 1),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'UNRESOLVED_OBSERVATION','FOLLOW_UP','FINAL_RESOLUTION','AUTO_ESCALATION',
        'EXECUTION_RECOVERY'
    )),
    financial_resolution TEXT NOT NULL CHECK (
        financial_resolution IN ('CHARGED_KNOWN','NOT_CHARGED','CHARGE_UNKNOWN')
    ),
    execution_resolution TEXT NOT NULL CHECK (execution_resolution IN (
        'EXECUTION_FAILED','RESULT_ALREADY_FINALIZED','MANUAL_REVIEW_REMAINS_REQUIRED'
    )),
    operator TEXT NOT NULL CHECK (
        length(trim(operator, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    note TEXT NOT NULL CHECK (
        length(trim(note, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    previous_attempt_status TEXT NOT NULL,
    resulting_attempt_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    UNIQUE (request_id, sequence_number),
    CHECK (
        (event_type IN ('UNRESOLVED_OBSERVATION','FOLLOW_UP')
            AND financial_resolution='CHARGE_UNKNOWN'
            AND execution_resolution='MANUAL_REVIEW_REMAINS_REQUIRED'
            AND previous_attempt_status='NEEDS_RECONCILIATION'
            AND resulting_attempt_status='NEEDS_RECONCILIATION')
        OR (event_type='AUTO_ESCALATION'
            AND ((previous_attempt_status='RESERVED' AND financial_resolution='NOT_CHARGED')
                 OR (previous_attempt_status='REQUEST_STARTED' AND financial_resolution='CHARGE_UNKNOWN'))
            AND execution_resolution='MANUAL_REVIEW_REMAINS_REQUIRED'
            AND resulting_attempt_status='NEEDS_RECONCILIATION')
        OR (event_type='FINAL_RESOLUTION'
            AND execution_resolution IN ('EXECUTION_FAILED','RESULT_ALREADY_FINALIZED')
            AND previous_attempt_status='NEEDS_RECONCILIATION'
            AND ((financial_resolution='CHARGED_KNOWN' AND resulting_attempt_status='RECONCILED_SETTLED')
                 OR (financial_resolution='NOT_CHARGED' AND resulting_attempt_status='RECONCILED_RELEASED')))
        OR (event_type='EXECUTION_RECOVERY'
            AND financial_resolution='CHARGED_KNOWN'
            AND execution_resolution IN ('EXECUTION_FAILED','RESULT_ALREADY_FINALIZED')
            AND previous_attempt_status='SETTLED'
            AND resulting_attempt_status='SETTLED')
    )
);

INSERT INTO reconciliation_events (
    id,request_id,sequence_number,event_type,financial_resolution,
    execution_resolution,operator,note,previous_attempt_status,
    resulting_attempt_status,created_at,idempotency_key
)
SELECT
    id,request_id,sequence_number,event_type,financial_resolution,
    execution_resolution,operator,note,previous_attempt_status,
    resulting_attempt_status,created_at,idempotency_key
FROM reconciliation_events_0014_old;

DROP TABLE reconciliation_events_0014_old;

CREATE INDEX ix_reconciliation_events_request
    ON reconciliation_events(request_id, sequence_number);
CREATE UNIQUE INDEX ux_reconciliation_events_execution_recovery
    ON reconciliation_events(request_id) WHERE event_type='EXECUTION_RECOVERY';

CREATE TRIGGER reconciliation_events_sequence_is_monotonic
BEFORE INSERT ON reconciliation_events
WHEN NEW.sequence_number != COALESCE(
    (SELECT MAX(sequence_number) FROM reconciliation_events WHERE request_id=NEW.request_id), 0
) + 1
BEGIN SELECT RAISE(ABORT, 'reconciliation_event sequence_number must be contiguous per attempt'); END;

CREATE TRIGGER reconciliation_events_require_active_attempt
BEFORE INSERT ON reconciliation_events
WHEN NOT (
    (NEW.event_type='EXECUTION_RECOVERY'
     AND (SELECT status FROM provider_attempts WHERE request_id=NEW.request_id)='SETTLED')
    OR
    (NEW.event_type!='EXECUTION_RECOVERY'
     AND (SELECT status FROM provider_attempts WHERE request_id=NEW.request_id)='NEEDS_RECONCILIATION')
)
BEGIN SELECT RAISE(ABORT, 'reconciliation_event requires NEEDS_RECONCILIATION or compatible SETTLED execution recovery'); END;

CREATE TRIGGER reconciliation_events_no_update BEFORE UPDATE ON reconciliation_events
BEGIN SELECT RAISE(ABORT, 'reconciliation_events is append-only'); END;
CREATE TRIGGER reconciliation_events_no_delete BEFORE DELETE ON reconciliation_events
BEGIN SELECT RAISE(ABORT, 'reconciliation_events is append-only'); END;

-- Preserve the 0014 terminal-financial contract after rebuilding the event table.
CREATE TRIGGER provider_attempts_terminal_requires_final_event
BEFORE UPDATE OF status ON provider_attempts
WHEN OLD.status='NEEDS_RECONCILIATION'
 AND NEW.status IN ('RECONCILED_SETTLED','RECONCILED_RELEASED')
 AND NOT EXISTS (
   SELECT 1 FROM reconciliation_events e
   WHERE e.request_id=NEW.request_id AND e.event_type='FINAL_RESOLUTION'
     AND e.resulting_attempt_status=NEW.status
     AND e.financial_resolution || ':' || e.execution_resolution = NEW.reconciliation_resolution
     AND e.operator=NEW.reconciled_by AND e.note=NEW.reconciliation_note
 )
BEGIN SELECT RAISE(ABORT, 'terminal reconciliation requires a matching FINAL_RESOLUTION event'); END;

-- The application additionally verifies the SHA-256 durable-intent fingerprint.
-- SQLite enforces every relation it can prove without recomputing that hash.
CREATE TRIGGER settled_execution_recovery_requires_consistent_prestate
BEFORE INSERT ON reconciliation_events
WHEN NEW.event_type='EXECUTION_RECOVERY' AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id=p.job_id
    JOIN runs r ON r.id=j.run_id
    JOIN research_runs rr ON rr.id=j.run_id
    JOIN topics t ON t.id=j.topic_id
    WHERE p.request_id=NEW.request_id
      AND p.status='SETTLED' AND p.actual_cost_usd IS NOT NULL
      AND j.status='NEEDS_VERIFICATION'
      AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
      AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
      AND j.kind='RESEARCH' AND j.workflow='RESEARCH'
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
      )
)
BEGIN SELECT RAISE(ABORT, 'execution recovery requires one consistent settled single-flow prestate'); END;

-- A privileged raw writer cannot terminalize the reviewable SETTLED crash state
-- without first inserting the durable execution-recovery authorization.
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

CREATE TRIGGER runs_settled_recovery_requires_event
BEFORE UPDATE OF status ON runs
WHEN NEW.status IN ('SUCCESS','FAILED') AND NEW.status IS NOT OLD.status
 AND EXISTS (
     SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
     WHERE j.run_id=OLD.id AND j.status='NEEDS_VERIFICATION' AND p.status='SETTLED'
 )
 AND NOT EXISTS (
     SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
     JOIN reconciliation_events e ON e.request_id=p.request_id
     WHERE j.run_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
       AND ((NEW.status='SUCCESS' AND e.execution_resolution='RESULT_ALREADY_FINALIZED')
            OR (NEW.status='FAILED' AND e.execution_resolution='EXECUTION_FAILED'))
 )
BEGIN SELECT RAISE(ABORT, 'settled run terminalization requires EXECUTION_RECOVERY event'); END;

CREATE TRIGGER research_runs_settled_recovery_requires_event
BEFORE UPDATE OF status ON research_runs
WHEN NEW.status IN ('COMPLETE','FAILED') AND NEW.status IS NOT OLD.status
 AND EXISTS (
     SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
     WHERE j.run_id=OLD.id AND j.status='NEEDS_VERIFICATION' AND p.status='SETTLED'
 )
 AND NOT EXISTS (
     SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
     JOIN reconciliation_events e ON e.request_id=p.request_id
     WHERE j.run_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
       AND ((NEW.status='COMPLETE' AND e.execution_resolution='RESULT_ALREADY_FINALIZED')
            OR (NEW.status='FAILED' AND e.execution_resolution='EXECUTION_FAILED'))
 )
BEGIN SELECT RAISE(ABORT, 'settled research_run terminalization requires EXECUTION_RECOVERY event'); END;

-- The event is the operation: its AFTER trigger performs the only authorized
-- lifecycle writes and then verifies the complete durable result before commit.
CREATE TRIGGER settled_execution_recovery_terminalizes_lifecycle
AFTER INSERT ON reconciliation_events
WHEN NEW.event_type='EXECUTION_RECOVERY'
BEGIN
    UPDATE runs
    SET status=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN 'SUCCESS' ELSE 'FAILED' END,
        error=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN NULL
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
        last_error=CASE NEW.execution_resolution
            WHEN 'RESULT_ALREADY_FINALIZED' THEN NULL
            ELSE 'SETTLED_EXECUTION_RECOVERY:EXECUTION_FAILED' END,
        lease_owner=NULL,lease_expires_at=NULL,reserved_cost_usd=0.0,
        budget_reserved_at=NULL,updated_at=NEW.created_at,finished_at=NEW.created_at
    WHERE id=(SELECT job_id FROM provider_attempts WHERE request_id=NEW.request_id)
      AND status='NEEDS_VERIFICATION';

    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM provider_attempts p
        JOIN jobs j ON j.id=p.job_id
        JOIN runs r ON r.id=j.run_id
        JOIN research_runs rr ON rr.id=j.run_id
        WHERE p.request_id=NEW.request_id AND p.status='SETTLED'
          AND j.lease_owner IS NULL AND j.lease_expires_at IS NULL
          AND j.reserved_cost_usd=0.0 AND j.budget_reserved_at IS NULL
          AND ((NEW.execution_resolution='EXECUTION_FAILED'
                AND j.status='FAILED' AND r.status='FAILED' AND rr.status='FAILED'
                AND rr.research_card_id IS NULL)
               OR
               (NEW.execution_resolution='RESULT_ALREADY_FINALIZED'
                AND j.status='DONE' AND r.status='SUCCESS' AND rr.status='COMPLETE'
                AND rr.research_card_id IS NOT NULL))
    ) THEN RAISE(ABORT, 'execution recovery did not produce a complete terminal lifecycle') END;
END;

-- Once recovered, the execution audit, canonical usage, caches and terminal
-- lifecycle are immutable.  The provider attempt was already immutable SETTLED.
CREATE TRIGGER model_usage_execution_recovery_is_immutable
BEFORE UPDATE ON model_usage
WHEN OLD.request_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM reconciliation_events e
    WHERE e.request_id=OLD.request_id AND e.event_type='EXECUTION_RECOVERY'
)
BEGIN SELECT RAISE(ABORT, 'canonical usage of a recovered settled execution is immutable'); END;

CREATE TRIGGER model_usage_execution_recovery_no_delete
BEFORE DELETE ON model_usage
WHEN OLD.request_id IS NOT NULL AND EXISTS (
    SELECT 1 FROM reconciliation_events e
    WHERE e.request_id=OLD.request_id AND e.event_type='EXECUTION_RECOVERY'
)
BEGIN SELECT RAISE(ABORT, 'canonical usage of a recovered settled execution cannot be deleted'); END;

CREATE TRIGGER runs_execution_recovery_terminal_is_immutable
BEFORE UPDATE OF status,cost_usd ON runs
WHEN OLD.status IN ('SUCCESS','FAILED')
 AND (NEW.status IS NOT OLD.status OR NEW.cost_usd IS NOT OLD.cost_usd)
 AND EXISTS (
    SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
    JOIN reconciliation_events e ON e.request_id=p.request_id
    WHERE j.run_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
 )
BEGIN SELECT RAISE(ABORT, 'terminal run of a recovered settled execution is immutable'); END;

CREATE TRIGGER research_runs_execution_recovery_terminal_is_immutable
BEFORE UPDATE OF status,total_cost_usd,research_card_id ON research_runs
WHEN OLD.status IN ('COMPLETE','FAILED')
 AND (NEW.status IS NOT OLD.status OR NEW.total_cost_usd IS NOT OLD.total_cost_usd
      OR NEW.research_card_id IS NOT OLD.research_card_id)
 AND EXISTS (
    SELECT 1 FROM jobs j JOIN provider_attempts p ON p.job_id=j.id
    JOIN reconciliation_events e ON e.request_id=p.request_id
    WHERE j.run_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
 )
BEGIN SELECT RAISE(ABORT, 'terminal research_run of a recovered settled execution is immutable'); END;

CREATE TRIGGER jobs_execution_recovery_terminal_is_immutable
BEFORE UPDATE OF status,run_id,reserved_cost_usd,budget_reserved_at,lease_owner,lease_expires_at ON jobs
WHEN OLD.status IN ('DONE','FAILED')
 AND (NEW.status IS NOT OLD.status OR NEW.run_id IS NOT OLD.run_id
      OR NEW.reserved_cost_usd IS NOT OLD.reserved_cost_usd
      OR NEW.budget_reserved_at IS NOT OLD.budget_reserved_at
      OR NEW.lease_owner IS NOT OLD.lease_owner
      OR NEW.lease_expires_at IS NOT OLD.lease_expires_at)
 AND EXISTS (
    SELECT 1 FROM provider_attempts p JOIN reconciliation_events e ON e.request_id=p.request_id
    WHERE p.job_id=OLD.id AND e.event_type='EXECUTION_RECOVERY'
 )
BEGIN SELECT RAISE(ABORT, 'terminal job of a recovered settled execution is immutable'); END;
