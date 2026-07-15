-- WAVE 0B: durable identity and conservative budget reservation for each
-- provider request.  A request_id is created before the network boundary and
-- never regenerated for the same job/stage/attempt identity.

CREATE TABLE provider_attempts (
    job_id              TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    stage               TEXT NOT NULL,
    attempt_no          INTEGER NOT NULL CHECK (attempt_no >= 1),
    request_id          TEXT NOT NULL UNIQUE,
    status              TEXT NOT NULL CHECK (status IN (
                            'RESERVED', 'REQUEST_STARTED', 'SETTLED',
                            'RELEASED', 'NEEDS_RECONCILIATION'
                        )),
    reserved_amount_usd REAL NOT NULL CHECK (reserved_amount_usd >= 0),
    reserved_at         TEXT NOT NULL,
    request_started_at  TEXT,
    settled_at          TEXT,
    actual_cost_usd     REAL CHECK (actual_cost_usd IS NULL OR actual_cost_usd >= 0),
    error_code          TEXT,
    PRIMARY KEY (job_id, stage, attempt_no),
    CHECK (
        (status = 'RESERVED' AND request_started_at IS NULL AND settled_at IS NULL)
        OR (status = 'REQUEST_STARTED' AND request_started_at IS NOT NULL AND settled_at IS NULL)
        OR (status = 'NEEDS_RECONCILIATION' AND request_started_at IS NOT NULL AND settled_at IS NULL)
        OR (status IN ('SETTLED', 'RELEASED') AND settled_at IS NOT NULL)
    )
);

CREATE INDEX ix_provider_attempts_active_reservations
    ON provider_attempts(status, reserved_at)
    WHERE status IN ('RESERVED', 'REQUEST_STARTED', 'NEEDS_RECONCILIATION');

ALTER TABLE model_usage ADD COLUMN request_id TEXT;
CREATE UNIQUE INDEX ux_model_usage_request_id
    ON model_usage(request_id)
    WHERE request_id IS NOT NULL;
