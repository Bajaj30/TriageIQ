-- ============================================================
-- 03_features/08_assembly.sql
-- TARGET  : materialized view mv_features
-- READS   : v_base + 03 .. 07
-- EXPECT  : 4,826,564 rows · complaint_id unique · 15-25 features
-- CONCEPT : A MATERIALIZED view is computed once and stored: the training export and the API read the same rows.
-- ============================================================
-- STEPS
--  1. join every layer ON complaint_id — each is one row per complaint, so the count stays 4,826,564
--  2. UNIQUE INDEX on complaint_id; index on company_id (the API's lookups)
--  3. time the build — the reason it is materialized
--  4. every feature gets an entry in feature_dictionary.md, or it doesn't ship

-- REFRESH is manual for now; Phase 3 automates it. Stale data is silent — say so in the README.

-- query goes here
