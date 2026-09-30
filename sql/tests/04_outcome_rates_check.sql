-- ============================================================
-- tests/04_outcome_rates_check.sql
-- TESTS   : view v_outcome_rates (03_features/04_outcome_rates.sql)
-- PART A  : RECOUNT — every feature for 21 complaints, recomputed with plain WHERE date <= d - 60
--           (no window functions). 20 by hash (same every run) + the first complaint in the data,
--           which has NO history: its counts must be 0 and its rates NULL.
-- PART B  : LEAK TEST — inside a transaction, flip the answer (paid <-> not paid) of every complaint
--           of the busiest company-day, recompute, compare, then ROLLBACK. Expect:
--             complaints on that day, and up to 59 days later  -> features UNCHANGED (no leak)
--             the first complaint 60+ days later               -> features CHANGED (the test has teeth)
-- SAFETY  : Part B edits complaint_events ONLY inside BEGIN ... ROLLBACK — nothing is ever saved.
--           If it stops on an error in pgAdmin, run ROLLBACK; (or close the tab) before anything else.
-- EXPECT  : every row PASS — Part B prints exactly 3 probes · last line: paid = 60,952 (the rollback worked)
-- ============================================================

-- ---------------------------------------------------------------- PART A: recount
WITH sample AS (
    (SELECT complaint_id, 'random' AS why FROM fact_complaint ORDER BY md5(complaint_id::text) LIMIT 20)
    UNION ALL
    (SELECT complaint_id, 'first complaint (no history)' FROM fact_complaint
     ORDER BY date_received, complaint_id LIMIT 1)
),
s AS (
    SELECT sample.complaint_id, sample.why, f.company_id, f.issue_id, f.product_id, f.date_received AS d
    FROM   sample JOIN fact_complaint f USING (complaint_id)
),
direct AS (   -- method 2: "rows of the same group whose date is at least 60 days before d"
    SELECT s.complaint_id, s.why, c.*, ci.*, i.*, p.*
    FROM   s
    CROSS  JOIN LATERAL (SELECT count(*) AS company_n_known, sum(paid) AS company_payouts,
                                avg(paid) AS company_paid_rate, avg(untimely) AS company_untimely_rate
                         FROM v_base b WHERE b.company_id = s.company_id
                                         AND b.date_received <= s.d - 60) c
    CROSS  JOIN LATERAL (SELECT count(*) AS company_issue_n_known, sum(paid) AS company_issue_payouts,
                                avg(paid) AS company_issue_paid_rate
                         FROM v_base b WHERE b.company_id = s.company_id AND b.issue_id = s.issue_id
                                         AND b.date_received <= s.d - 60) ci
    CROSS  JOIN LATERAL (SELECT count(*) AS issue_n_known, sum(paid) AS issue_payouts, avg(paid) AS issue_paid_rate
                         FROM v_base b WHERE b.issue_id = s.issue_id
                                         AND b.date_received <= s.d - 60) i
    CROSS  JOIN LATERAL (SELECT count(*) AS product_n_known, sum(paid) AS product_payouts, avg(paid) AS product_paid_rate
                         FROM v_base b WHERE b.product_id = s.product_id
                                         AND b.date_received <= s.d - 60) p
),
v AS MATERIALIZED (   -- method 1: the view
    SELECT * FROM v_outcome_rates WHERE complaint_id IN (SELECT complaint_id FROM sample)
)
SELECT d.why, d.complaint_id, v.company_n_known, round(v.company_paid_rate, 4) AS company_rate,
       v.company_issue_n_known, round(v.company_issue_paid_rate, 4) AS pair_rate,
       CASE WHEN (v.company_n_known, v.company_payouts, v.company_paid_rate, v.company_untimely_rate,
                  v.company_issue_n_known, v.company_issue_payouts, v.company_issue_paid_rate,
                  v.issue_n_known, v.issue_payouts, v.issue_paid_rate,
                  v.product_n_known, v.product_payouts, v.product_paid_rate)
                 IS NOT DISTINCT FROM          -- like "=", but NULL matches NULL (the no-history row)
                 (d.company_n_known, d.company_payouts, d.company_paid_rate, d.company_untimely_rate,
                  d.company_issue_n_known, d.company_issue_payouts, d.company_issue_paid_rate,
                  d.issue_n_known, d.issue_payouts, d.issue_paid_rate,
                  d.product_n_known, d.product_payouts, d.product_paid_rate)
            THEN 'PASS' ELSE '** FAIL **' END AS result
FROM   direct d LEFT JOIN v USING (complaint_id)
ORDER  BY d.why, d.complaint_id;

-- ---------------------------------------------------------------- PART B: leak test
BEGIN;

CREATE TEMP TABLE lt_day AS                       -- the busiest company-day WITH 90+ days of data after it
SELECT company_id, date_received AS d             -- (the overall busiest, 2024-12-10, is 21 days from the
FROM   fact_complaint                             --  end — no "+60" probe exists; the first run lost it)
WHERE  date_received <= (SELECT max(date_received) FROM fact_complaint) - 90
GROUP  BY company_id, date_received
ORDER  BY count(*) DESC LIMIT 1;

CREATE TEMP TABLE lt_probe AS                     -- three complaints of that company, at three distances
SELECT 'same day'              AS probe, 'unchanged' AS expect,
       (SELECT min(f.complaint_id) FROM fact_complaint f, lt_day
        WHERE f.company_id = lt_day.company_id AND f.date_received = lt_day.d) AS complaint_id
UNION ALL
SELECT 'last day before +60', 'unchanged',
       (SELECT f.complaint_id FROM fact_complaint f, lt_day
        WHERE f.company_id = lt_day.company_id AND f.date_received BETWEEN lt_day.d + 1 AND lt_day.d + 59
        ORDER BY f.date_received DESC, f.complaint_id LIMIT 1)
UNION ALL
SELECT 'first day from +60', 'changed',
       (SELECT f.complaint_id FROM fact_complaint f, lt_day
        WHERE f.company_id = lt_day.company_id AND f.date_received >= lt_day.d + 60
        ORDER BY f.date_received, f.complaint_id LIMIT 1);

CREATE TEMP TABLE lt_before AS
SELECT * FROM v_outcome_rates WHERE complaint_id IN (SELECT complaint_id FROM lt_probe);

UPDATE complaint_events e                         -- flip every answer of that company-day
SET    company_response = CASE WHEN e.company_response = 'Closed with monetary relief'
                               THEN 'Closed with explanation' ELSE 'Closed with monetary relief' END
FROM   fact_complaint f, lt_day
WHERE  e.complaint_id = f.complaint_id AND e.event_type = 'responded'
AND    f.company_id = lt_day.company_id AND f.date_received = lt_day.d;

CREATE TEMP TABLE lt_after AS
SELECT * FROM v_outcome_rates WHERE complaint_id IN (SELECT complaint_id FROM lt_probe);

SELECT p.probe,
       fb.date_received - lt_day.d                       AS days_after_flip,
       round(b.company_paid_rate, 6)                     AS rate_before,
       round(a.company_paid_rate, 6)                     AS rate_after,
       p.expect,
       CASE WHEN p.complaint_id IS NULL THEN '** FAIL ** (no such complaint)'   -- a probe must never vanish
            WHEN (ROW(b.*) IS NOT DISTINCT FROM ROW(a.*)) = (p.expect = 'unchanged')   -- all 16 columns
            THEN 'PASS' ELSE '** FAIL **' END            AS result
FROM   lt_probe p                                  -- LEFT joins: all 3 probes always print
LEFT   JOIN lt_before b USING (complaint_id)
LEFT   JOIN lt_after  a USING (complaint_id)
LEFT   JOIN fact_complaint fb USING (complaint_id)
CROSS  JOIN lt_day
ORDER  BY days_after_flip;

ROLLBACK;                                         -- every flip undone, temp tables gone

SELECT sum(paid) AS paid_after_rollback FROM v_label;   -- expect 60,952
