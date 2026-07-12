-- Migracja 0002 — deduplikacja tematów.
-- Nowe kolumny: powiązanie duplikatu z istniejącym tematem + powód odrzucenia.
ALTER TABLE topics ADD COLUMN duplicate_of INTEGER REFERENCES topics(id) ON DELETE SET NULL;
ALTER TABLE topics ADD COLUMN rejection_reason TEXT;
CREATE INDEX IF NOT EXISTS ix_topics_dup ON topics(account_id, duplicate_of);
