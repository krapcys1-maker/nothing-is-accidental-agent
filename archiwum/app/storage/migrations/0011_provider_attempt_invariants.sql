-- WAVE 0B.1: provider attempts are a durable state machine, not merely a
-- bookkeeping table. SQLite table rebuild keeps historical 0010 databases
-- transactional while rejecting malformed pre-existing attempts.

CREATE TABLE provider_attempts_new (
    job_id              TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage               TEXT NOT NULL
                            CHECK (length(stage) BETWEEN 1 AND 64)
                            CHECK (stage NOT GLOB '*[^a-z0-9_-]*'),
    attempt_no          INTEGER NOT NULL CHECK (attempt_no >= 1),
    request_id          TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL CHECK (status IN (
                            'RESERVED', 'REQUEST_STARTED', 'SETTLED',
                            'RELEASED', 'NEEDS_RECONCILIATION'
                        )),
    reserved_amount_usd REAL NOT NULL
                            CHECK (typeof(reserved_amount_usd) IN ('integer', 'real'))
                            CHECK (reserved_amount_usd > 0)
                            CHECK (reserved_amount_usd = reserved_amount_usd)
                            CHECK (abs(reserved_amount_usd) <= 1.7976931348623157e308),
    reserved_at         TEXT NOT NULL,
    request_started_at  TEXT,
    settled_at          TEXT,
    released_at         TEXT,
    actual_cost_usd     REAL
                            CHECK (actual_cost_usd IS NULL OR (
                                typeof(actual_cost_usd) IN ('integer', 'real')
                                AND actual_cost_usd >= 0
                                AND actual_cost_usd = actual_cost_usd
                                AND abs(actual_cost_usd) <= 1.7976931348623157e308
                            )),
    error_code          TEXT,
    PRIMARY KEY (job_id, stage, attempt_no),
    CHECK (
        (status = 'RESERVED'
            AND request_started_at IS NULL AND settled_at IS NULL
            AND released_at IS NULL AND actual_cost_usd IS NULL)
        OR (status = 'REQUEST_STARTED'
            AND request_started_at IS NOT NULL AND settled_at IS NULL
            AND released_at IS NULL AND actual_cost_usd IS NULL)
        OR (status = 'NEEDS_RECONCILIATION'
            AND request_started_at IS NOT NULL AND settled_at IS NULL
            AND released_at IS NULL AND actual_cost_usd IS NULL)
        OR (status = 'SETTLED'
            AND request_started_at IS NOT NULL AND settled_at IS NOT NULL
            AND released_at IS NULL AND actual_cost_usd IS NOT NULL)
        OR (status = 'RELEASED'
            AND request_started_at IS NULL AND settled_at IS NULL
            AND released_at IS NOT NULL AND actual_cost_usd IS NULL)
    )
);

-- The INSERT validates all historical 0010 rows before the old table is
-- replaced. Invalid rows fail the enclosing migration transaction unchanged.
INSERT INTO provider_attempts_new (
    job_id, stage, attempt_no, request_id, status, reserved_amount_usd,
    reserved_at, request_started_at, settled_at, released_at, actual_cost_usd, error_code
)
SELECT
    job_id, stage, attempt_no, request_id, status, reserved_amount_usd,
    reserved_at, request_started_at,
    CASE WHEN status = 'RELEASED' THEN NULL ELSE settled_at END,
    CASE WHEN status = 'RELEASED' THEN settled_at ELSE NULL END,
    actual_cost_usd, error_code
FROM provider_attempts;

DROP TABLE provider_attempts;
ALTER TABLE provider_attempts_new RENAME TO provider_attempts;

CREATE INDEX ix_provider_attempts_active_reservations
    ON provider_attempts(status, reserved_at)
    WHERE status IN ('RESERVED', 'REQUEST_STARTED', 'NEEDS_RECONCILIATION');

CREATE TRIGGER provider_attempts_initial_state
BEFORE INSERT ON provider_attempts
WHEN NEW.status != 'RESERVED'
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt must start RESERVED');
END;

CREATE TRIGGER provider_attempts_request_id_matches_identity
BEFORE INSERT ON provider_attempts
WHEN NEW.request_id != NEW.job_id || ':' || NEW.stage || ':' || NEW.attempt_no
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt request_id does not match identity');
END;

CREATE TRIGGER provider_attempts_identity_is_immutable
BEFORE UPDATE OF job_id, stage, attempt_no, request_id ON provider_attempts
WHEN NEW.job_id IS NOT OLD.job_id
  OR NEW.stage IS NOT OLD.stage
  OR NEW.attempt_no IS NOT OLD.attempt_no
  OR NEW.request_id IS NOT OLD.request_id
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt identity is immutable');
END;

CREATE TRIGGER provider_attempts_controlled_transition
BEFORE UPDATE ON provider_attempts
WHEN NOT (
    (OLD.status = 'RESERVED' AND NEW.status = 'REQUEST_STARTED'
        AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd
        AND NEW.reserved_at IS OLD.reserved_at
        AND NEW.request_started_at IS NOT NULL
        AND NEW.settled_at IS NULL AND NEW.released_at IS NULL
        AND NEW.actual_cost_usd IS NULL)
    OR
    (OLD.status = 'RESERVED' AND NEW.status = 'RELEASED'
        AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd
        AND NEW.reserved_at IS OLD.reserved_at
        AND NEW.request_started_at IS NULL AND NEW.settled_at IS NULL
        AND NEW.released_at IS NOT NULL AND NEW.actual_cost_usd IS NULL)
    OR
    (OLD.status = 'REQUEST_STARTED' AND NEW.status = 'SETTLED'
        AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd
        AND NEW.reserved_at IS OLD.reserved_at
        AND NEW.request_started_at IS OLD.request_started_at
        AND NEW.settled_at IS NOT NULL AND NEW.released_at IS NULL
        AND NEW.actual_cost_usd IS NOT NULL)
    OR
    (OLD.status = 'REQUEST_STARTED' AND NEW.status = 'NEEDS_RECONCILIATION'
        AND NEW.reserved_amount_usd IS OLD.reserved_amount_usd
        AND NEW.reserved_at IS OLD.reserved_at
        AND NEW.request_started_at IS OLD.request_started_at
        AND NEW.settled_at IS NULL AND NEW.released_at IS NULL
        AND NEW.actual_cost_usd IS NULL)
)
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt transition is not allowed');
END;

-- 0010's model_usage accepts historical paid rows with no request identity.
-- They are preserved as explicit legacy records. New rows default to 0 and
-- must satisfy the durable request guard below.
CREATE TABLE model_usage_new (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    provider            TEXT NOT NULL DEFAULT 'anthropic',
    model               TEXT NOT NULL,
    task                TEXT,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens   INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens  INTEGER NOT NULL DEFAULT 0,
    web_search_requests INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd  REAL NOT NULL DEFAULT 0.0,
    dry_run             INTEGER NOT NULL DEFAULT 0 CHECK (dry_run IN (0, 1)),
    request_id          TEXT,
    is_legacy_usage     INTEGER NOT NULL DEFAULT 0 CHECK (is_legacy_usage IN (0, 1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (dry_run = 1 OR is_legacy_usage = 1 OR request_id IS NOT NULL)
);

INSERT INTO model_usage_new (
    id, run_id, provider, model, task, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens, web_search_requests,
    estimated_cost_usd, dry_run, request_id, is_legacy_usage, created_at
)
SELECT
    id, run_id, provider, model, task, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens, web_search_requests,
    estimated_cost_usd, dry_run, request_id, 1, created_at
FROM model_usage;

DROP TABLE model_usage;
ALTER TABLE model_usage_new RENAME TO model_usage;

CREATE INDEX ix_usage_run ON model_usage(run_id);
CREATE INDEX ix_usage_created ON model_usage(created_at);
CREATE UNIQUE INDEX ux_model_usage_request_id
    ON model_usage(request_id)
    WHERE request_id IS NOT NULL;

-- An FK cannot be added safely because pre-durable historical real usage has
-- no provider attempt to reference. This trigger gives new real rows the same
-- durable referential check while retaining the immutable historical ledger.
CREATE TRIGGER model_usage_requires_active_attempt
BEFORE INSERT ON model_usage
WHEN NEW.dry_run = 0 AND NEW.is_legacy_usage = 0 AND (
    NEW.request_id IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM provider_attempts
        WHERE request_id = NEW.request_id AND status = 'REQUEST_STARTED'
    )
)
BEGIN
    SELECT RAISE(ABORT, 'new real model_usage requires active provider_attempt');
END;

CREATE TRIGGER model_usage_durable_identity_is_immutable
BEFORE UPDATE OF dry_run, request_id, is_legacy_usage ON model_usage
WHEN NEW.dry_run IS NOT OLD.dry_run
  OR NEW.request_id IS NOT OLD.request_id
  OR NEW.is_legacy_usage IS NOT OLD.is_legacy_usage
BEGIN
    SELECT RAISE(ABORT, 'model_usage durable identity is immutable');
END;
