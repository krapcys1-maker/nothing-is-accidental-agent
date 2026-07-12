-- Migracja 0004 — wznawialny dwuetapowy research (stabilizacja Research Pipeline).
-- Powód: jednoetapowy research (V2) tracił WSZYSTKO przy błędzie finalnego JSON-a,
-- łącznie z realnie opłaconymi wynikami wyszukiwania. Dwuetapowy pipeline (ADR-016)
-- rozdzielił search od syntezy, ale wyniki etapu A nadal żyły tylko w pamięci procesu
-- w trakcie jednego wywołania — awaria procesu między etapem A i B nadal traciła dane
-- (i pieniądze). Ta migracja czyni etap A TRWAŁYM od razu po sukcesie.

-- research_runs: stan maszyny stanów per próba researchu. `id` = TO SAMO id co w `runs`
-- (rozszerzenie 1:1, nie osobna przestrzeń identyfikatorów) — model_usage.run_id
-- już wskazuje na runs.id, więc koszt obu etapów jest naturalnie powiązany.
CREATE TABLE research_runs (
    id                    TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    account_id            TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    topic_id              INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    status                TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING|SOURCE_COLLECTED|PARTIAL|COMPLETE|FAILED
    stage_a_completed_at  TEXT,
    stage_b_completed_at  TEXT,
    research_card_id      INTEGER REFERENCES research_cards(id) ON DELETE SET NULL,
    total_cost_usd        REAL NOT NULL DEFAULT 0.0,
    error                 TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_research_runs_account ON research_runs(account_id, status);
CREATE INDEX ix_research_runs_topic ON research_runs(topic_id);

-- research_sources: TRWAŁY wynik etapu A (gather_sources). Przetrwa niezależnie od tego,
-- czy etap B kiedykolwiek się wykona albo powiedzie — to jest właśnie mechanizm
-- "nie trać wyników wyszukiwania" i "wznów bez ponownego web search".
CREATE TABLE research_sources (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id      TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    url                  TEXT NOT NULL,
    title                TEXT,
    author_or_org        TEXT,
    published_at         TEXT,
    source_type          TEXT NOT NULL DEFAULT 'OTHER',
    key_facts_json        TEXT,                            -- JSON list — surowe fakty z etapu A
    verification_status  TEXT NOT NULL DEFAULT 'UNVERIFIED',
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX ix_research_sources_run ON research_sources(research_run_id);

-- research_stage_results: log KAŻDEJ próby KAŻDEGO etapu — w tym nieudanych, w tym
-- retry. Audytowalność: widać nie tylko stan końcowy, ale historię prób.
CREATE TABLE research_stage_results (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id   TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    stage             TEXT NOT NULL,                        -- 'A' | 'B'
    status            TEXT NOT NULL,                        -- 'SUCCESS' | 'FAILED'
    started_at        TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at       TEXT,
    error             TEXT
);
CREATE INDEX ix_research_stage_results_run ON research_stage_results(research_run_id);

-- Celowo BRAK nowej fizycznej tabeli "research_usage": koszty per etap już mieszczą się
-- w istniejącej model_usage (task='research_gather'|'research_synthesize', run_id wskazuje
-- na research_runs.id). Osobna tabela dublowałaby księgowanie kosztów zamiast je
-- rozszerzać — patrz ADR w docs/DECISIONS.md (ta migracja) po uzasadnienie.
