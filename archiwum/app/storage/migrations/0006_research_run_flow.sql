-- Migracja 0006 — jawny typ przepływu każdego research runu.
--
-- `flow` jest od tej migracji jedynym źródłem prawdy dla wyboru ścieżki resume.
-- Dwa lokalne runy single są mapowane jawną korektą historii (pełny UUID,
-- account_id, topic_id i — jeśli istnieje — research_card_id). Pozostałe flow
-- korzystają wyłącznie z jednoznacznych tasków, stage logu i właściwych tabel
-- źródeł. Status PARTIAL celowo NIE uczestniczy w klasyfikacji.
--
-- SQLite nie pozwala dodać do niepustej tabeli kolumny NOT NULL bez DEFAULT.
-- Nie chcemy DEFAULT, bo ukrywałby brak decyzji wywołującego, dlatego tabela jest
-- przebudowywana w transakcji, a każdy istniejący run musi przejść walidację.

PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TEMP TABLE _0006_known_single_runs (
    id               TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL,
    topic_id         INTEGER NOT NULL,
    research_card_id INTEGER
);
INSERT INTO _0006_known_single_runs(id, account_id, topic_id, research_card_id) VALUES
    ('1b649314-27cf-4b29-857e-287175664a3f', 'nothing_is_accidental', 2, NULL),
    ('bda661bc-59c9-4f4e-9313-86c659bde74d', 'nothing_is_accidental', 1, 1);

CREATE TEMP TABLE _0006_flow_classification AS
SELECT
    r.id,
    CASE WHEN EXISTS (
        SELECT 1 FROM _0006_known_single_runs known
        WHERE known.id = r.id AND known.account_id = r.account_id
          AND (
              NOT EXISTS (SELECT 1 FROM research_runs rr WHERE rr.id = r.id)
              OR EXISTS (
                  SELECT 1 FROM research_runs rr
                  WHERE rr.id = r.id
                    AND rr.account_id = known.account_id
                    AND rr.topic_id = known.topic_id
                    AND (
                        known.research_card_id IS NULL
                        OR rr.research_card_id = known.research_card_id
                    )
              )
          )
    )
    THEN 1 ELSE 0 END AS is_single,
    CASE WHEN
        EXISTS (
            SELECT 1 FROM model_usage mu
            WHERE mu.run_id = r.id
              AND mu.task IN ('research_gather', 'research_synthesize')
        )
        OR EXISTS (
            SELECT 1 FROM research_stage_results rsr
            WHERE rsr.research_run_id = r.id AND rsr.stage = 'A'
        )
        OR EXISTS (
            SELECT 1 FROM research_sources rs
            WHERE rs.research_run_id = r.id
        )
    THEN 1 ELSE 0 END AS is_two_stage,
    CASE WHEN
        EXISTS (
            SELECT 1 FROM model_usage mu
            WHERE mu.run_id = r.id
              AND mu.task IN (
                  'research_discover', 'research_extract', 'research_synthesize_cards'
              )
        )
        OR EXISTS (
            SELECT 1 FROM research_stage_results rsr
            WHERE rsr.research_run_id = r.id AND rsr.stage IN ('A1', 'A2')
        )
        OR EXISTS (
            SELECT 1 FROM research_source_candidates rsc
            WHERE rsc.research_run_id = r.id
        )
    THEN 1 ELSE 0 END AS is_staged
FROM runs r
WHERE r.workflow = 'RESEARCH';

-- Nazwana kontrola daje czytelny błąd i wycofuje całą transakcję, jeżeli dane
-- wskazują zero albo więcej niż jeden flow. Nie ma arbitralnego fallbacku.
CREATE TEMP TABLE _0006_classification_guard (
    ok INTEGER NOT NULL,
    CONSTRAINT migration_0006_requires_exactly_one_flow CHECK (ok = 1)
);
INSERT INTO _0006_classification_guard(ok)
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM _0006_flow_classification c
    WHERE c.is_single + c.is_two_stage + c.is_staged <> 1
) THEN 0 ELSE 1 END;

CREATE TABLE research_runs_new (
    id                    TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    account_id            TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    topic_id              INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    flow                  TEXT NOT NULL CHECK (flow IN ('single', 'two_stage', 'staged')),
    status                TEXT NOT NULL DEFAULT 'PENDING',
    stage_a_completed_at  TEXT,
    stage_b_completed_at  TEXT,
    research_card_id      INTEGER REFERENCES research_cards(id) ON DELETE SET NULL,
    total_cost_usd        REAL NOT NULL DEFAULT 0.0,
    error                 TEXT,
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Runy, które już miały rozszerzenie research_runs (two-stage/staged oraz
-- ewentualne historyczne single w innych kopiach bazy).
INSERT INTO research_runs_new (
    id, account_id, topic_id, flow, status,
    stage_a_completed_at, stage_b_completed_at, research_card_id,
    total_cost_usd, error, created_at, updated_at
)
SELECT
    rr.id, rr.account_id, rr.topic_id,
    CASE
        WHEN c.is_single = 1 THEN 'single'
        WHEN c.is_two_stage = 1 THEN 'two_stage'
        WHEN c.is_staged = 1 THEN 'staged'
    END,
    rr.status, rr.stage_a_completed_at, rr.stage_b_completed_at,
    rr.research_card_id, rr.total_cost_usd, rr.error,
    rr.created_at, rr.updated_at
FROM research_runs rr
JOIN _0006_flow_classification c ON c.id = rr.id;

-- Dwa dokładnie znane lokalne runy single nie miały jeszcze research_runs.
-- To jawna migracja danych historycznych tej instalacji, nie ogólny klasyfikator.
-- Każde pole mapowania jest weryfikowane przez join; brak topic/card uruchomi
-- końcowy guard zamiast dopasowania po czasie lub zastosowania fallbacku.
INSERT INTO research_runs_new (
    id, account_id, topic_id, flow, status, stage_b_completed_at,
    research_card_id, total_cost_usd, error, created_at, updated_at
)
SELECT
    r.id, r.account_id, known.topic_id, 'single',
    CASE
        WHEN r.status IN ('SUCCESS', 'DRY_RUN') THEN 'COMPLETE'
        WHEN r.status = 'FAILED' THEN 'FAILED'
        ELSE 'PENDING'
    END,
    CASE WHEN r.status IN ('SUCCESS', 'DRY_RUN') THEN r.finished_at ELSE NULL END,
    known.research_card_id, r.cost_usd, r.error,
    r.started_at, COALESCE(r.finished_at, r.started_at)
FROM runs r
JOIN _0006_flow_classification c ON c.id = r.id AND c.is_single = 1
JOIN _0006_known_single_runs known
  ON known.id = r.id AND known.account_id = r.account_id
JOIN topics t ON t.id = known.topic_id AND t.account_id = known.account_id
LEFT JOIN research_cards rc
  ON rc.id = known.research_card_id AND rc.topic_id = known.topic_id
WHERE (known.research_card_id IS NULL OR rc.id IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM research_runs_new rr WHERE rr.id = r.id);

CREATE TEMP TABLE _0006_coverage_guard (
    ok INTEGER NOT NULL,
    CONSTRAINT migration_0006_unmapped_research_run CHECK (ok = 1)
);
INSERT INTO _0006_coverage_guard(ok)
SELECT CASE WHEN EXISTS (
    SELECT 1
    FROM _0006_flow_classification c
    WHERE NOT EXISTS (SELECT 1 FROM research_runs_new rr WHERE rr.id = c.id)
) OR EXISTS (
    SELECT 1
    FROM research_runs rr
    WHERE NOT EXISTS (SELECT 1 FROM research_runs_new n WHERE n.id = rr.id)
) THEN 0 ELSE 1 END;

DROP TABLE research_runs;
ALTER TABLE research_runs_new RENAME TO research_runs;
CREATE INDEX ix_research_runs_account ON research_runs(account_id, status);
CREATE INDEX ix_research_runs_topic ON research_runs(topic_id);
CREATE INDEX ix_research_runs_flow ON research_runs(flow, status);

DROP TABLE _0006_coverage_guard;
DROP TABLE _0006_classification_guard;
DROP TABLE _0006_flow_classification;
DROP TABLE _0006_known_single_runs;

COMMIT;
PRAGMA foreign_keys = ON;
