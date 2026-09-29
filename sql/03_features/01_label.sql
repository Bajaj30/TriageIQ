-- ============================================================
-- 03_features/01_label.sql
-- TARGET  : view v_label  (Phase 0.5)
-- READS   : complaint_events ('responded' rows only)
-- EXPECT  : 4,826,564 rows · paid = 1 for 60,952 · paid never NULL
-- CONCEPT : The label is a VIEW, not a stored column: its definition is visible and changeable in one place.
-- PROBLEM : "Did this complaint cost the company money?" — the answer the model learns to predict.
--           Why: every outcome feature (04) and every training row needs it, meaning the SAME thing everywhere.
--           Without it: each query writes its own CASE; one day two definitions disagree, and train and serve drift.
-- ============================================================
-- STEPS
--  1. keep event_type = 'responded' — exactly one row per complaint, so no fan-out
--  2. paid = 1 when company_response = 'Closed with monetary relief', else 0
--     ELSE also catches 'Untimely response' (2,785) and NULL (19) -> 0   (decided 2026-09-28 / 29)
--  3. also untimely = 1 when company_response = 'Untimely response' — an OUTCOME, used only in 04
--  4. keep complaint_id, paid, untimely (+ company_response, for traceability)

-- Hint: in CASE WHEN x = 'a' THEN 1 ELSE 0 END, a NULL x falls to ELSE — NULL = 'a' is not true.

-- query goes here
