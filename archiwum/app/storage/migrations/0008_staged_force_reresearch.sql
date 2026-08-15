-- Migracja 0008: trwały marker jawnego --force-re-research dla staged B.
--
-- Bez markera zgoda force żyła tylko w pamięci świeżego procesu. Po awarii B
-- dispatcher resume nie mógł odtworzyć legalnego prawa do finalizacji tematu
-- USED z wcześniejszą kompletną kartą. DEFAULT 0 zachowuje semantykę każdego
-- historycznego runu: żaden nie dostaje zgody force retrospektywnie.
ALTER TABLE research_runs
    ADD COLUMN is_force_reresearch INTEGER NOT NULL DEFAULT 0
    CHECK (is_force_reresearch IN (0, 1));
