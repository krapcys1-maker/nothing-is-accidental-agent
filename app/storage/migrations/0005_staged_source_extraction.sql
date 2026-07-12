-- Migracja 0005 — etapowy research A1 (discovery) / A2 (per-source extraction) / B (synthesis).
-- Powód: drugi realny test (2026-07-12, run 2a3b4bb9) pokazał, że nawet lekki schemat
-- etapu A (gather_sources, migracja 0004) wciąż jest zbyt kruchy — JEDEN duży JSON
-- obejmujący WSZYSTKIE źródła naraz ucina się, zanim zdąży opisać ostatnie z nich, i
-- wtedy WSZYSTKIE źródła (nie tylko ostatnie) giną razem. Ta migracja rozbija etap A
-- na: A1 (tylko lista kandydatów URL, JSONL, najlżejszy możliwy ładunek) i A2 (JEDNO
-- źródło na wywołanie API, zapisywane do bazy NATYCHMIAST po każdym) — awaria na
-- źródle N nie ma już wpływu na źródła 1..N-1. Patrz docs/DECISIONS.md ADR-020.
--
-- research_sources (migracja 0004) NIE jest usuwana ani zmieniana — zostaje jako
-- trwały zapis STAREGO, dwuetapowego przepływu (gather_sources+synthesize_card,
-- ADR-016/019), który nadal działa i ma 17 zielonych testów. Ta migracja go NIE
-- zastępuje, tylko dodaje NOWĄ, równoległą ścieżkę dla nowego, trzyetapowego
-- przepływu — supersede-nie-usuń, zgodnie z dotychczasową praktyką w tym projekcie
-- (patrz ADR-017->018: stare dokumenty oznaczane SUPERSEDED, nie kasowane).

-- research_source_candidates: JEDEN wiersz na kandydata z etapu A1, wzbogacany W
-- MIEJSCU przez etap A2 (ta sama tabela, nie osobny "Source Card" gdzieś indziej) —
-- to jest właśnie "kandydat" ewoluujący w "Source Card" po ekstrakcji. Status
-- śledzi tę ewolucję: PENDING_EXTRACTION (świeżo z A1) -> EXTRACTED (A2 się udał) |
-- EXTRACTION_FAILED (A2 padł dla TEGO źródła — inne źródła nietknięte).
CREATE TABLE research_source_candidates (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id        TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
    url                    TEXT NOT NULL,
    title                  TEXT,                                    -- z A1; A2 może nadpisać dokładniejszym
    author_or_org          TEXT,                                    -- wypełniane przez A2
    published_at           TEXT,                                    -- wypełniane przez A2
    source_type            TEXT NOT NULL DEFAULT 'OTHER',            -- wypełniane przez A2
    supported_claims_json  TEXT,                                    -- JSON list, wypełniane przez A2 (2-4 twierdzenia)
    numeric_facts_json     TEXT,                                    -- JSON list, wypełniane przez A2 (liczby Z KONTEKSTEM)
    verification_status    TEXT NOT NULL DEFAULT 'UNVERIFIED',
    source_quality_score   REAL NOT NULL DEFAULT 0.0,
    status                 TEXT NOT NULL DEFAULT 'PENDING_EXTRACTION', -- PENDING_EXTRACTION|EXTRACTED|EXTRACTION_FAILED
    extraction_error       TEXT,
    discovered_at          TEXT NOT NULL DEFAULT (datetime('now')),   -- kiedy A1 znalazł kandydata
    extracted_at           TEXT                                      -- kiedy A2 (próbował) go wzbogacić
);
CREATE INDEX ix_research_source_candidates_run ON research_source_candidates(research_run_id, status);

-- Celowo BRAK nowej tabeli kosztów — koszt A1/A2/B czytany z istniejącej model_usage
-- (task='research_discover'|'research_extract'|'research_synthesize_cards'), tak jak
-- w migracji 0004. Osobna tabela dublowałaby księgowanie.
