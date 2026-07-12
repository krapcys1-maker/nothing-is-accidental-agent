-- Migracja 0001 — schemat bazy (zgodny z IMPLEMENTATION_PLAN.md §B.4).
-- Refinement względem planu: model_usage.dry_run (odróżnia estymacje dry_run od realnych kosztów).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    mode                  TEXT NOT NULL,
    autonomy_level        TEXT NOT NULL,
    active                INTEGER NOT NULL DEFAULT 0,
    browser_profile_path  TEXT NOT NULL,
    writing_profile_path  TEXT NOT NULL,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS account_policies (
    account_id                TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    daily_comment_limit       INTEGER NOT NULL DEFAULT 5,
    daily_note_limit          INTEGER NOT NULL DEFAULT 2,
    weekly_article_limit      INTEGER NOT NULL DEFAULT 2,
    max_per_author_per_day    INTEGER NOT NULL DEFAULT 1,
    require_comment_approval  INTEGER NOT NULL DEFAULT 1,
    require_note_approval     INTEGER NOT NULL DEFAULT 1,
    require_article_approval  INTEGER NOT NULL DEFAULT 1,
    require_restack_approval  INTEGER NOT NULL DEFAULT 1,
    allow_links               INTEGER NOT NULL DEFAULT 1,
    link_ratio_limit          REAL NOT NULL DEFAULT 0.10
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id      TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    question        TEXT,
    score           REAL,
    score_breakdown TEXT,
    status          TEXT NOT NULL DEFAULT 'DISCOVERED',
    source          TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_topics_account ON topics(account_id, status);

CREATE TABLE IF NOT EXISTS research_cards (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_id        INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    question        TEXT NOT NULL,
    thesis          TEXT NOT NULL,
    mechanism       TEXT,
    facts_json      TEXT,
    counterargument TEXT,
    citable_numbers TEXT,
    visual_idea     TEXT,
    confidence      REAL NOT NULL DEFAULT 0.0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_research_topic ON research_cards(topic_id);

CREATE TABLE IF NOT EXISTS sources (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    research_card_id  INTEGER NOT NULL REFERENCES research_cards(id) ON DELETE CASCADE,
    url               TEXT NOT NULL,
    title             TEXT,
    source_type       TEXT NOT NULL DEFAULT 'OTHER',
    published_at      TEXT,
    verified          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_sources_card ON sources(research_card_id);

CREATE TABLE IF NOT EXISTS content_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    type              TEXT NOT NULL,
    title             TEXT,
    subtitle          TEXT,
    body              TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'DRAFT',
    score             REAL,
    duplicate_score   REAL,
    research_card_id  INTEGER REFERENCES research_cards(id) ON DELETE SET NULL,
    scheduled_at      TEXT,
    published_at      TEXT,
    external_url      TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_content_account ON content_items(account_id, type, status);

CREATE TABLE IF NOT EXISTS target_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id          TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    author_name         TEXT NOT NULL,
    author_url          TEXT,
    item_url            TEXT NOT NULL,
    item_type           TEXT NOT NULL,
    relevance_score     REAL,
    last_interaction_at TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(account_id, item_url)
);
CREATE INDEX IF NOT EXISTS ix_target_account ON target_items(account_id);

CREATE TABLE IF NOT EXISTS interactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id       TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    target_item_id   INTEGER REFERENCES target_items(id) ON DELETE SET NULL,
    type             TEXT NOT NULL,
    body             TEXT NOT NULL DEFAULT '',
    contains_link    INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'DRAFT',
    published_at     TEXT,
    likes_received   INTEGER NOT NULL DEFAULT 0,
    replies_received INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_interactions_account ON interactions(account_id, type, status);

CREATE TABLE IF NOT EXISTS approvals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id   TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    object_type  TEXT NOT NULL,
    object_id    INTEGER NOT NULL,
    decision     TEXT NOT NULL DEFAULT 'PENDING',
    decided_at   TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_approvals_account ON approvals(account_id, decision);

CREATE TABLE IF NOT EXISTS metrics_daily (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    date              TEXT NOT NULL,
    subscribers       INTEGER,
    followers         INTEGER,
    views             INTEGER,
    likes_received    INTEGER,
    comments_received INTEGER,
    restacks          INTEGER,
    profile_visits    INTEGER,
    is_estimated      INTEGER NOT NULL DEFAULT 0,
    UNIQUE(account_id, date)
);

CREATE TABLE IF NOT EXISTS runs (
    id                       TEXT PRIMARY KEY,
    account_id               TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    workflow                 TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'RUNNING',
    current_state            TEXT,
    started_at               TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at              TEXT,
    cost_usd                 REAL NOT NULL DEFAULT 0.0,
    error                    TEXT,
    human_intervention_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_runs_account ON runs(account_id, workflow, status);

CREATE TABLE IF NOT EXISTS model_usage (
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
    dry_run             INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_usage_run ON model_usage(run_id);
CREATE INDEX IF NOT EXISTS ix_usage_created ON model_usage(created_at);

CREATE TABLE IF NOT EXISTS screenshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    account_id  TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    path        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
