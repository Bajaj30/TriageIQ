-- ============================================================
-- tests/06_sequence_check.sql
-- TESTS   : view v_sequence (03_features/06_sequence.sql)
-- HOW     : recompute every feature a SECOND way, with no window functions. "Before this complaint" is a
--           plain row comparison: (date_received, complaint_id) < (d, id) — compares date first, then id,
--           exactly the frame-C order.
-- SAMPLE  : 20 complaints by hash (same every run) + the FIRST and LAST complaint (by id) of the busiest
--           company-day — the case where the tiebreak decides everything.
-- EXPECT  : every row PASS. Busiest day: the first complaint (by id) gets the gap to the previous day,
--           the last gets 0; their ranks this month differ by 4,244.
-- ============================================================
WITH busiest_day AS (
    SELECT company_id, date_received FROM fact_complaint
    GROUP  BY company_id, date_received ORDER BY count(*) DESC LIMIT 1
),
sample AS (
    (SELECT complaint_id, 'random' AS why FROM fact_complaint ORDER BY md5(complaint_id::text) LIMIT 20)
    UNION ALL
    SELECT min(f.complaint_id), 'busiest day: first' FROM fact_complaint f JOIN busiest_day USING (company_id, date_received)
    UNION ALL
    SELECT max(f.complaint_id), 'busiest day: last'  FROM fact_complaint f JOIN busiest_day USING (company_id, date_received)
),
s AS (
    SELECT sample.complaint_id AS id, sample.why, f.company_id, f.date_received AS d
    FROM   sample JOIN fact_complaint f USING (complaint_id)
),
direct AS (
    SELECT s.id AS complaint_id, s.why,
           s.d - (SELECT max(x.date_received) FROM fact_complaint x
                  WHERE x.company_id = s.company_id
                    AND (x.date_received, x.complaint_id) < (s.d, s.id))           AS days_since_prev_company_complaint,
           (SELECT count(*) FROM fact_complaint x
            WHERE  x.company_id = s.company_id
              AND  date_trunc('month', x.date_received) = date_trunc('month', s.d)
              AND  (x.date_received, x.complaint_id) <= (s.d, s.id))               AS company_rank_this_month,
           s.d - (SELECT min(x.date_received) FROM fact_complaint x
                  WHERE x.company_id = s.company_id)                                AS company_tenure_days,
           s.d - DATE '2022-01-01'                                                  AS days_since_start
    FROM   s
),
v AS MATERIALIZED (
    SELECT * FROM v_sequence WHERE complaint_id IN (SELECT complaint_id FROM sample)
)
SELECT d.why, d.complaint_id,
       v.days_since_prev_company_complaint AS gap, v.company_rank_this_month AS rank_month,
       v.company_tenure_days AS tenure, v.days_since_start,
       CASE WHEN (v.days_since_prev_company_complaint, v.company_rank_this_month,
                  v.company_tenure_days, v.days_since_start)
                 IS NOT DISTINCT FROM
                 (d.days_since_prev_company_complaint, d.company_rank_this_month::int,
                  d.company_tenure_days, d.days_since_start)
            THEN 'PASS' ELSE '** FAIL **' END AS result
FROM   direct d LEFT JOIN v USING (complaint_id)
ORDER  BY d.why, d.complaint_id;
