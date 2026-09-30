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

-- CREATE OR REPLACE, not DROP + CREATE: later views (v_base ...) will be built on this one, and
-- DROP would refuse (or, with CASCADE, delete them too). OR REPLACE swaps the definition in place.
-- Its one limit: it can ADD columns at the end, but not rename or remove one — that needs a DROP.
CREATE OR REPLACE VIEW v_label AS
SELECT complaint_id,
       CASE WHEN company_response = 'Closed with monetary relief' THEN 1 ELSE 0 END AS paid,
       --   NULL (19 unknowns) and 'Untimely response' both fail this test -> ELSE -> 0
       CASE WHEN company_response = 'Untimely response'           THEN 1 ELSE 0 END AS untimely,
       company_response                                          -- raw text, kept for traceability
FROM   complaint_events
WHERE  event_type = 'responded';       -- 1 of the 3 events per complaint -> one row per complaint

-- Speed: this is exactly the shape of the partial index ix_events_responded (12_indexes.sql) —
-- only 'responded' rows, carrying company_response — so the view reads a 247 MB index, not the
-- 2.4 GB events table. Check 2 shows it.

-- CHECKS
-- 1. one row, every number fixed in advance:
--    rows 4,826,564 · complaints 4,826,564 (grain) · paid 60,952 · untimely 2,785
--    unknown_as_0 19 · paid_and_untimely 0 · base rate 1.26% (all complaints, F1)
SELECT count(*)                                                    AS rows,
       count(DISTINCT complaint_id)                                AS complaints,
       sum(paid)                                                   AS paid,
       sum(untimely)                                               AS untimely,
       count(*) FILTER (WHERE company_response IS NULL AND paid = 0) AS unknown_as_0,
       count(*) FILTER (WHERE paid = 1 AND untimely = 1)           AS paid_and_untimely,
       round(100.0 * avg(paid), 2)                                 AS base_rate_pct
FROM   v_label;

-- 2. the plan: expect an Index Only Scan on ix_events_responded, not a scan of complaint_events.
EXPLAIN (COSTS OFF)
SELECT count(*), sum(paid) FROM v_label;
