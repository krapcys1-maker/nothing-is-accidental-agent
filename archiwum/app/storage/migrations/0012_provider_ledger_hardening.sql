-- WAVE 0B.2: validate historical durable relations before rebuilding the
-- provider ledger. The migration runner wraps this whole file and its ledger
-- entry in one BEGIN IMMEDIATE transaction.

-- Preflight must happen before either old table is replaced. SQLite's RAISE()
-- is trigger-only, so a one-row CHECK table turns a failed predicate into an
-- atomic migration error without changing the original ledger.
CREATE TABLE provider_attempts_0012_preflight (
    valid INTEGER NOT NULL CHECK (valid = 1)
);
INSERT INTO provider_attempts_0012_preflight(valid)
SELECT CASE WHEN EXISTS (
    SELECT 1 FROM provider_attempts
    WHERE request_id != job_id || ':' || stage || ':' || attempt_no
) THEN 0 ELSE 1 END;
DROP TABLE provider_attempts_0012_preflight;

CREATE TABLE model_usage_0012_preflight (
    valid INTEGER NOT NULL CHECK (valid = 1)
);
INSERT INTO model_usage_0012_preflight(valid)
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM model_usage u
    LEFT JOIN provider_attempts p ON p.request_id = u.request_id
    LEFT JOIN jobs j ON j.id = p.job_id
    WHERE u.dry_run = 0 AND u.request_id IS NOT NULL
      AND (
          p.request_id IS NULL
          OR p.status NOT IN ('REQUEST_STARTED', 'SETTLED')
          OR j.run_id IS NULL
          OR j.run_id != u.run_id
      )
) THEN 0 ELSE 1 END;
DROP TABLE model_usage_0012_preflight;

CREATE TABLE provider_attempts_0012_new (
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
INSERT INTO provider_attempts_0012_new (
    job_id, stage, attempt_no, request_id, status, reserved_amount_usd,
    reserved_at, request_started_at, settled_at, released_at, actual_cost_usd, error_code
)
SELECT job_id, stage, attempt_no, request_id, status, reserved_amount_usd,
       reserved_at, request_started_at, settled_at, released_at, actual_cost_usd, error_code
FROM provider_attempts;
-- `model_usage_requires_active_attempt` (from 0011) references this table.
-- Remove it before the table swap; the stricter replacement is installed below.
DROP TRIGGER model_usage_requires_active_attempt;
DROP TRIGGER model_usage_durable_identity_is_immutable;

DROP TABLE provider_attempts;
ALTER TABLE provider_attempts_0012_new RENAME TO provider_attempts;

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

CREATE TRIGGER provider_attempts_no_retry_without_resolver
BEFORE INSERT ON provider_attempts
WHEN NEW.attempt_no > 1 AND EXISTS (
    SELECT 1 FROM provider_attempts p
    WHERE p.job_id = NEW.job_id AND p.stage = NEW.stage
)
BEGIN
    SELECT RAISE(ABORT, 'provider_attempt retry requires explicit reconciliation resolver');
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

CREATE TABLE model_usage_0012_new (
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
INSERT INTO model_usage_0012_new (
    id, run_id, provider, model, task, input_tokens, output_tokens,
    cache_read_tokens, cache_write_tokens, web_search_requests,
    estimated_cost_usd, dry_run, request_id, is_legacy_usage, created_at
)
SELECT id, run_id, provider, model, task, input_tokens, output_tokens,
       cache_read_tokens, cache_write_tokens, web_search_requests,
       estimated_cost_usd, dry_run, request_id,
       CASE WHEN dry_run = 0 AND request_id IS NULL THEN 1 ELSE 0 END,
       created_at
FROM model_usage;
DROP TABLE model_usage;
ALTER TABLE model_usage_0012_new RENAME TO model_usage;

CREATE INDEX ix_usage_run ON model_usage(run_id);
CREATE INDEX ix_usage_created ON model_usage(created_at);
CREATE UNIQUE INDEX ux_model_usage_request_id
    ON model_usage(request_id)
    WHERE request_id IS NOT NULL;

CREATE TABLE legacy_model_usage_proofs (
    usage_id          INTEGER PRIMARY KEY REFERENCES model_usage(id) ON DELETE RESTRICT,
    migration_version TEXT NOT NULL CHECK (migration_version = '0012_provider_ledger_hardening'),
    classified_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO legacy_model_usage_proofs (usage_id, migration_version)
SELECT id, '0012_provider_ledger_hardening'
FROM model_usage
WHERE is_legacy_usage = 1;

CREATE TRIGGER legacy_model_usage_proofs_no_runtime_insert
BEFORE INSERT ON legacy_model_usage_proofs
BEGIN
    SELECT RAISE(ABORT, 'legacy usage proof is migration-only');
END;
CREATE TRIGGER legacy_model_usage_proofs_immutable
BEFORE UPDATE ON legacy_model_usage_proofs
BEGIN
    SELECT RAISE(ABORT, 'legacy usage proof is immutable');
END;
CREATE TRIGGER legacy_model_usage_proofs_no_delete
BEFORE DELETE ON legacy_model_usage_proofs
BEGIN
    SELECT RAISE(ABORT, 'legacy usage proof cannot be deleted');
END;

CREATE TRIGGER model_usage_legacy_proof_required
BEFORE INSERT ON model_usage
WHEN NEW.is_legacy_usage = 1 AND NOT EXISTS (
    SELECT 1 FROM legacy_model_usage_proofs p WHERE p.usage_id = NEW.id
)
BEGIN
    SELECT RAISE(ABORT, 'new model_usage cannot self-declare legacy');
END;

CREATE TRIGGER model_usage_legacy_row_no_delete
BEFORE DELETE ON model_usage
WHEN OLD.is_legacy_usage = 1
BEGIN
    SELECT RAISE(ABORT, 'legacy model_usage is immutable history');
END;

CREATE TRIGGER model_usage_requires_request_job_run_relation
BEFORE INSERT ON model_usage
WHEN NEW.dry_run = 0 AND NEW.is_legacy_usage = 0 AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id = p.job_id
    JOIN runs r ON r.id = j.run_id
    WHERE p.request_id = NEW.request_id
      AND p.status IN ('REQUEST_STARTED', 'SETTLED')
      AND j.run_id = NEW.run_id
      AND r.id = NEW.run_id
      AND r.account_id = j.account_id
)
BEGIN
    SELECT RAISE(ABORT, 'new real model_usage requires request->job->run relation');
END;

CREATE TRIGGER model_usage_request_job_run_relation_on_update
BEFORE UPDATE OF run_id, request_id, dry_run, is_legacy_usage ON model_usage
WHEN NEW.dry_run = 0 AND NEW.is_legacy_usage = 0 AND NOT EXISTS (
    SELECT 1
    FROM provider_attempts p
    JOIN jobs j ON j.id = p.job_id
    JOIN runs r ON r.id = j.run_id
    WHERE p.request_id = NEW.request_id
      AND p.status IN ('REQUEST_STARTED', 'SETTLED')
      AND j.run_id = NEW.run_id
      AND r.id = NEW.run_id
      AND r.account_id = j.account_id
)
BEGIN
    SELECT RAISE(ABORT, 'updated real model_usage requires request->job->run relation');
END;

CREATE TRIGGER model_usage_durable_identity_is_immutable
BEFORE UPDATE OF run_id, dry_run, request_id, is_legacy_usage ON model_usage
WHEN NEW.run_id IS NOT OLD.run_id
  OR NEW.dry_run IS NOT OLD.dry_run
  OR NEW.request_id IS NOT OLD.request_id
  OR NEW.is_legacy_usage IS NOT OLD.is_legacy_usage
BEGIN
    SELECT RAISE(ABORT, 'model_usage durable identity is immutable');
END;
