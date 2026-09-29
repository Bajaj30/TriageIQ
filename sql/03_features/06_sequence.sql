-- ============================================================
-- 03_features/06_sequence.sql
-- TARGET  : view v_sequence
-- READS   : v_base, dim_company
-- EXPECT  : 4,826,564 rows · identical results on every run
-- CONCEPT : FRAME C — ORDER BY date_received, complaint_id: here row order matters, so the tiebreak is required.
-- ============================================================
-- STEPS
--  1. days since this company's previous complaint — lag(date_received); same day -> 0; first -> NULL
--  2. this complaint's rank for its company this month — row_number()
--  3. company tenure — days since the company's first complaint in the window (known at intake)
--  4. days since 2022-01-01 — a drift marker

-- complaint_id breaks ties deterministically — it is NOT a clock (TriageIQ.md §1.4a).
-- Proof: run twice, compare — any difference means a missing tiebreak.

-- query goes here
