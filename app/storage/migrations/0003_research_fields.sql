-- Migracja 0003 — pełne pola Research Card i źródeł.
ALTER TABLE research_cards ADD COLUMN working_thesis TEXT;
ALTER TABLE research_cards ADD COLUMN confirmed_claims TEXT;      -- JSON list
ALTER TABLE research_cards ADD COLUMN uncertain_claims TEXT;      -- JSON list
ALTER TABLE research_cards ADD COLUMN contradictions TEXT;        -- JSON list
ALTER TABLE research_cards ADD COLUMN source_quality_score REAL NOT NULL DEFAULT 0.0;
ALTER TABLE research_cards ADD COLUMN publication_recommendation TEXT;
ALTER TABLE research_cards ADD COLUMN rejection_reason TEXT;

ALTER TABLE sources ADD COLUMN author_or_org TEXT;
ALTER TABLE sources ADD COLUMN supports_claim TEXT;
ALTER TABLE sources ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED';
