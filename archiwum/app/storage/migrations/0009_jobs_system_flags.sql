-- Migracja 0009: trwała kolejka Etapu 1 oraz runtime system flags.
--
-- jobs są jedynym źródłem prawdy o lease, idempotencji i rezerwacji budżetu.
-- Nie uruchamiają workera ani nie wykonują żadnej akcji zewnętrznej.

CREATE TABLE jobs (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL CHECK (kind IN ('LOCAL', 'RESEARCH', 'BROWSER')),
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
    CHECK (
        (status IN ('LEASED', 'RUNNING')
            AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (status NOT IN ('LEASED', 'RUNNING')
            AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);

-- Jeden aktywny research job na konto+topic. NEEDS_VERIFICATION pozostaje aktywny,
-- bo jego ponowienie mogłoby zdublować niezweryfikowany skutek.
CREATE UNIQUE INDEX ux_jobs_active_research_topic
    ON jobs(account_id, topic_id)
    WHERE kind = 'RESEARCH'
      AND topic_id IS NOT NULL
      AND status IN ('QUEUED', 'LEASED', 'RUNNING', 'NEEDS_VERIFICATION');

CREATE INDEX ix_jobs_claimable
    ON jobs(status, earliest_run_at, priority DESC, deadline_at, created_at);
CREATE INDEX ix_jobs_active_reservations
    ON jobs(status, budget_reserved_at)
    WHERE budget_reserved_at IS NOT NULL;

CREATE TABLE system_flags (
    key         TEXT PRIMARY KEY,
    value_json  TEXT NOT NULL CHECK (json_valid(value_json)),
    updated_at  TEXT NOT NULL,
    updated_by  TEXT,
    reason      TEXT
);
