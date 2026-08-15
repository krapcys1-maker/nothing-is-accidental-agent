-- Migration 0007: atomically reserved/started A2 attempts per source candidate.
--
-- Historical values are conservative lower bounds, not a reconstructed history:
-- PENDING proves no reserved A2 attempt (0); EXTRACTED and EXTRACTION_FAILED prove
-- at least one attempt (1). The migration runner owns BEGIN/COMMIT together with
-- the schema_migrations ledger entry, so this file deliberately has no transaction.

ALTER TABLE research_source_candidates
    ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

UPDATE research_source_candidates
SET attempts = CASE status
    WHEN 'EXTRACTED' THEN 1
    WHEN 'EXTRACTION_FAILED' THEN 1
    ELSE 0
END;
