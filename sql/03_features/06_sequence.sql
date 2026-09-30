-- ============================================================
-- 03_features/06_sequence.sql
-- TARGET  : view v_sequence
-- READS   : v_base, dim_company
-- EXPECT  : 4,826,564 rows · identical results on every run
-- CONCEPT : FRAME C — ORDER BY date_received, complaint_id: here row order matters, so the tiebreak is required.
-- PROBLEM : "Where does this complaint sit in the company's own timeline?" — first in months, or the 50th
--           this month; a new company or an old one.
--           Why: back-to-back bursts and brand-new companies behave differently from steady ones.
--           Without the tiebreak: numbers change between runs, so the training data can't be reproduced.
-- ============================================================
-- STEPS
--  1. days since this company's previous complaint — lag(date_received); same day -> 0; first -> NULL
--  2. this complaint's rank for its company this month — row_number()
--  3. company tenure — days since the company's first complaint in the window (known at intake)
--  4. days since 2022-01-01 — a drift marker

-- complaint_id breaks ties deterministically — it is NOT a clock (TriageIQ.md §1.4a).
-- Proof: run twice, compare — any difference means a missing tiebreak.

-- Why frame C here and not A/B: LAG and row_number look at the row DIRECTLY before this one — there is
-- no date range to express, so no RANGE frame. But on a busy day hundreds of rows share a date, and
-- "directly before" is undefined without a second sort key. (date_received, complaint_id) is unique,
-- so the order is total: same input, same answer, every run.
-- The honest assumption: within ONE day, a smaller complaint_id is treated as "arrived earlier". IDs
-- are not a clock (they overlap across days), so this is an approximation. It only affects SAME-DAY
-- rows: which one gets the gap to the previous day (the rest get 0), and the order of ranks that day.
-- Tenure uses first_seen_in_window: the company's earliest date, always <= this complaint's date, so it
-- is known at intake. It starts counting on 2022-01-01 — older companies look young in early 2022.

CREATE OR REPLACE VIEW v_sequence AS
SELECT b.complaint_id,
       -- step 1: gap to the company's previous complaint (NULL = first ever seen)
       b.date_received - lag(b.date_received) OVER w_company            AS days_since_prev_company_complaint,
       -- step 2: 1 = the company's first complaint this calendar month
       row_number() OVER (PARTITION BY b.company_id, date_trunc('month', b.date_received)
                          ORDER BY b.date_received, b.complaint_id)       AS company_rank_this_month,
       -- step 3: how long the company has been in the data
       b.date_received - c.first_seen_in_window                           AS company_tenure_days,
       -- step 4: the calendar itself — a drift marker (see the note in 03_features/log.md)
       b.date_received - DATE '2022-01-01'                                AS days_since_start
FROM   v_base      b
JOIN   dim_company c USING (company_id)
WINDOW w_company AS (PARTITION BY b.company_id ORDER BY b.date_received, b.complaint_id);
-- Subtracting two DATEs gives a whole number of days (an integer), not an interval.

-- CHECKS — each reads the view ONCE (a MATERIALIZED CTE).

-- 1. exact counts, fixed in advance:
--    rows = complaints = 4,826,564
--    first_complaints   = 4,946   (one per company: the only rows with no previous complaint)
--    month_starts       = 50,827  (one rank-1 row per company-month)
--    tenure_zero_bad    = 0       (tenure 0 must mean "a complaint on the company's first day")
--    negatives          = 0
WITH v AS MATERIALIZED (SELECT * FROM v_sequence)
SELECT count(*)                                                        AS rows,
       count(DISTINCT complaint_id)                                    AS complaints,
       count(*) FILTER (WHERE days_since_prev_company_complaint IS NULL) AS first_complaints,
       count(*) FILTER (WHERE company_rank_this_month = 1)             AS month_starts,
       count(*) FILTER (WHERE company_tenure_days = 0
                          AND days_since_prev_company_complaint > 0)   AS tenure_zero_bad,
       count(*) FILTER (WHERE days_since_prev_company_complaint < 0
                           OR company_tenure_days < 0 OR days_since_start < 0) AS negatives
FROM   v;

-- 2. DOES IT CARRY SIGNAL? Payout rate by how long the company had been quiet before this complaint.
WITH v AS MATERIALIZED (SELECT complaint_id, days_since_prev_company_complaint AS gap FROM v_sequence)
SELECT CASE WHEN gap IS NULL THEN '0: first ever'
            WHEN gap = 0     THEN '1: same day'
            WHEN gap <= 7    THEN '2: 1-7 days'
            WHEN gap <= 30   THEN '3: 8-30 days'
            WHEN gap <= 180  THEN '4: 31-180 days'
            ELSE                  '5: 180+ days' END   AS quiet_before,
       count(*)                                     AS complaints,
       round(100.0 * avg(b.paid), 2)                AS actual_payout_pct
FROM   v JOIN v_base b USING (complaint_id)
GROUP  BY 1 ORDER BY 1;
