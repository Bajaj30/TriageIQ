-- ============================================================
-- 00_staging/02_validate_raw.sql
-- PURPOSE : prove the load is complete and correct before building anything on it
-- CHECKS  : total rows = 17,355,295 · distinct complaint ids = total rows
--           rows in 2022-01-01..2024-12-31 = 4,826,564 (F1 in Context/FACTS.md)
--           rows in window with a narrative = 1,639,068 (F2)
-- ============================================================

-- your query here
