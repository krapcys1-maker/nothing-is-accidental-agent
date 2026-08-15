-- Stage 2 / Wave E2-B: controlled fetch foundation.
--
-- Durable substrate for exactly one approved external fetch per job:
--   * controlled_fetch_approvals — the one-shot human L1 consent, bound to one
--     job, one account, one URL and one intent fingerprint; consumed atomically
--     exactly once, never transferable, never restorable after restart.
--   * controlled_fetch_attempts — the closed request lifecycle
--     RESERVED -> REQUEST_STARTED -> SUCCEEDED | FAILED | NEEDS_VERIFICATION,
--     at most one attempt per job and per approval, linked to at most one
--     append-only evidence retrieval.
--   * P2-3 narrow barrier — jobs.payload_json of a controlled_fetch_v1 job is
--     frozen at the SQL level, so the contract the human approved is the
--     contract the worker executes.  Other job payloads are intentionally NOT
--     covered here (E2-A-P2-03 remains open for them).
--
-- Trust boundary (stated honestly, mirroring 0016): these floors bind values
-- persisted in this database to each other.  They do not defend against a
-- writer who alters the schema or drops triggers; that writer is outside the
-- E2-B threat model.  The Python transaction additionally revalidates the
-- intent fingerprint from the payload before consumption.

CREATE TABLE controlled_fetch_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT CHECK (
        length(trim(account_id, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    action_type TEXT NOT NULL CHECK (action_type = 'CONTROLLED_FETCH'),
    requested_url TEXT NOT NULL CHECK (
        length(trim(requested_url, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    intent_fingerprint TEXT NOT NULL CHECK (
        length(intent_fingerprint) = 64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    timeout_seconds INTEGER NOT NULL CHECK (timeout_seconds BETWEEN 1 AND 120),
    max_bytes INTEGER NOT NULL CHECK (max_bytes BETWEEN 1 AND 2000000),
    max_redirects INTEGER NOT NULL CHECK (max_redirects BETWEEN 0 AND 5),
    approved_by TEXT NOT NULL CHECK (
        length(trim(approved_by, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    approved_at TEXT NOT NULL CHECK (length(approved_at) >= 19),
    expires_at TEXT NOT NULL CHECK (length(expires_at) >= 19 AND expires_at > approved_at),
    consumed_at TEXT CHECK (consumed_at IS NULL OR length(consumed_at) >= 19)
);

-- The approval may only ever bind to the exact frozen controlled_fetch_v1 job
-- contract: same account, same URL, same fingerprint, same execution limits.
CREATE TRIGGER controlled_fetch_approvals_bind_frozen_job
BEFORE INSERT ON controlled_fetch_approvals
WHEN NOT EXISTS (
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
    AND NEW.requested_url = OLD.requested_url
    AND NEW.intent_fingerprint = OLD.intent_fingerprint
    AND NEW.timeout_seconds = OLD.timeout_seconds
    AND NEW.max_bytes = OLD.max_bytes
    AND NEW.max_redirects = OLD.max_redirects
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

-- P2-3 narrow barrier (E2-A-P2-03 for controlled_fetch_v1): once a payload is
-- a controlled fetch contract it can never change, and no other payload can
-- ever become one by mutation.  The approved bytes are the executed bytes.
CREATE TRIGGER jobs_controlled_fetch_payload_frozen
BEFORE UPDATE OF payload_json ON jobs
WHEN (
    json_extract(OLD.payload_json, '$.execution') = 'controlled_fetch_v1'
    OR json_extract(NEW.payload_json, '$.execution') = 'controlled_fetch_v1'
) AND NEW.payload_json IS NOT OLD.payload_json
BEGIN
    SELECT RAISE(ABORT, 'controlled_fetch_v1 job payload is immutable');
END;

CREATE TABLE controlled_fetch_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE RESTRICT,
    approval_id INTEGER NOT NULL UNIQUE
        REFERENCES controlled_fetch_approvals(id) ON DELETE RESTRICT,
    attempt_no INTEGER NOT NULL CHECK (attempt_no = 1),
    source_identity TEXT NOT NULL CHECK (
        length(trim(source_identity, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    requested_url TEXT NOT NULL CHECK (
        length(trim(requested_url, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    intent_fingerprint TEXT NOT NULL CHECK (
        length(intent_fingerprint) = 64 AND intent_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    status TEXT NOT NULL CHECK (
        status IN ('RESERVED','REQUEST_STARTED','SUCCEEDED','FAILED','NEEDS_VERIFICATION')
    ),
    lease_owner TEXT NOT NULL CHECK (
        length(trim(lease_owner, char(9)||char(10)||char(11)||char(12)||char(13)||char(32))) > 0
    ),
    reserved_at TEXT NOT NULL CHECK (length(reserved_at) >= 19),
    request_started_at TEXT CHECK (request_started_at IS NULL OR length(request_started_at) >= 19),
    terminalized_at TEXT CHECK (terminalized_at IS NULL OR length(terminalized_at) >= 19),
    retrieval_id INTEGER UNIQUE REFERENCES evidence_retrievals(id) ON DELETE RESTRICT,
    outcome_reason TEXT CHECK (outcome_reason IS NULL OR length(outcome_reason) > 0),
    -- NULL-proof lifecycle shape: each status pins every stage timestamp.
    CHECK (
        (status = 'RESERVED' AND request_started_at IS NULL
            AND terminalized_at IS NULL AND retrieval_id IS NULL)
        OR (status = 'REQUEST_STARTED' AND request_started_at IS NOT NULL
            AND terminalized_at IS NULL AND retrieval_id IS NULL)
        OR (status = 'SUCCEEDED' AND request_started_at IS NOT NULL
            AND terminalized_at IS NOT NULL AND retrieval_id IS NOT NULL)
        OR (status = 'FAILED' AND terminalized_at IS NOT NULL)
        OR (status = 'NEEDS_VERIFICATION' AND request_started_at IS NOT NULL
            AND terminalized_at IS NOT NULL AND retrieval_id IS NULL)
    )
);

CREATE TRIGGER controlled_fetch_attempts_born_reserved
BEFORE INSERT ON controlled_fetch_attempts
WHEN NEW.status != 'RESERVED'
BEGIN
    SELECT RAISE(ABORT, 'controlled fetch attempt must start its lifecycle as RESERVED');
END;

-- One INSERT floor binds the whole chain: frozen job contract, same-account
-- run, and an ALREADY-CONSUMED, unexpired approval of the same job/URL/
-- fingerprint (consumption happens earlier inside the same transaction).
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

-- Closed transition floor: identity immutable, request_started_at immutable
-- after it is set, and only the enumerated lifecycle edges exist.
CREATE TRIGGER controlled_fetch_attempts_controlled_transition
BEFORE UPDATE ON controlled_fetch_attempts
WHEN NOT (
    NEW.id = OLD.id AND NEW.job_id = OLD.job_id AND NEW.run_id = OLD.run_id
    AND NEW.account_id = OLD.account_id AND NEW.topic_id = OLD.topic_id
    AND NEW.approval_id = OLD.approval_id AND NEW.attempt_no = OLD.attempt_no
    AND NEW.source_identity = OLD.source_identity
    AND NEW.requested_url = OLD.requested_url
    AND NEW.intent_fingerprint = OLD.intent_fingerprint
    AND NEW.lease_owner = OLD.lease_owner
    AND NEW.reserved_at = OLD.reserved_at
    AND (OLD.request_started_at IS NULL OR NEW.request_started_at = OLD.request_started_at)
    AND (
        (OLD.status = 'RESERVED' AND NEW.status IN ('REQUEST_STARTED','FAILED'))
        OR (OLD.status = 'REQUEST_STARTED'
            AND NEW.status IN ('SUCCEEDED','FAILED','NEEDS_VERIFICATION'))
    )
)
BEGIN
    SELECT RAISE(ABORT, 'controlled fetch attempt transition is outside the closed lifecycle');
END;

CREATE TRIGGER controlled_fetch_attempts_success_requires_ok_retrieval
BEFORE UPDATE ON controlled_fetch_attempts
WHEN NEW.status = 'SUCCEEDED' AND NOT EXISTS (
    SELECT 1 FROM evidence_retrievals er
    WHERE er.id = NEW.retrieval_id
      AND er.account_id = NEW.account_id
      AND er.requested_url = NEW.requested_url
      AND er.status = 'OK'
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch SUCCEEDED requires one OK retrieval of the same account and URL');
END;

CREATE TRIGGER controlled_fetch_attempts_failed_retrieval_consistent
BEFORE UPDATE ON controlled_fetch_attempts
WHEN NEW.status = 'FAILED' AND NEW.retrieval_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM evidence_retrievals er
    WHERE er.id = NEW.retrieval_id
      AND er.account_id = NEW.account_id
      AND er.requested_url = NEW.requested_url
      AND er.status = 'FAILED'
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch FAILED may only link a FAILED retrieval of the same account and URL');
END;

CREATE TRIGGER controlled_fetch_attempts_no_delete
BEFORE DELETE ON controlled_fetch_attempts
BEGIN SELECT RAISE(ABORT, 'controlled_fetch_attempts is append-only'); END;

-- Jobs floor: a controlled fetch job can never terminalize around an
-- unresolved attempt, and DONE exists only above a SUCCEEDED attempt.
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

CREATE TRIGGER runs_controlled_fetch_terminal_requires_resolved_attempt
BEFORE UPDATE OF status ON runs
WHEN NEW.status IN ('SUCCESS','FAILED','STOPPED')
 AND EXISTS (
    SELECT 1 FROM controlled_fetch_attempts a
    WHERE a.run_id = NEW.id AND a.status IN ('RESERVED','REQUEST_STARTED')
)
BEGIN
    SELECT RAISE(ABORT,
        'controlled fetch run cannot terminalize with an unresolved fetch attempt');
END;
