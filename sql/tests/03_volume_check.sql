-- ============================================================
-- tests/03_volume_check.sql
-- TESTS   : view v_volume (03_features/03_volume.sql)
-- HOW     : recompute every count a SECOND way — plain WHERE ... BETWEEN, no window functions — for
--           a sample of complaints, and compare. Two different methods agreeing = strong evidence.
-- SAMPLE  : 20 complaints picked by hash (same 20 every run) + the FIRST and LAST complaint of the
--           busiest company-day in the data (4,245 complaints on one day) — the hardest case for ties.
-- EXPECT  : every row PASS. The two busiest-day complaints show IDENTICAL company and national counts:
--           same company, same day, and the current day is excluded — so their order within the day
--           cannot matter. (Their issue-level counts differ only because their issues differ.)
-- ============================================================
WITH busiest_day AS (
    SELECT company_id, date_received
    FROM   fact_complaint
    GROUP  BY company_id, date_received
    ORDER  BY count(*) DESC
    LIMIT  1
),
sample AS (
    (SELECT complaint_id, 'random' AS why
     FROM   fact_complaint
     ORDER  BY md5(complaint_id::text)
     LIMIT  20)
    UNION ALL
    SELECT min(f.complaint_id), 'busiest day: first' FROM fact_complaint f JOIN busiest_day USING (company_id, date_received)
    UNION ALL
    SELECT max(f.complaint_id), 'busiest day: last'  FROM fact_complaint f JOIN busiest_day USING (company_id, date_received)
),
s AS (   -- the sample complaints with their ids and date
    SELECT f.complaint_id, sample.why, f.company_id, f.issue_id, f.date_received AS d
    FROM   sample JOIN fact_complaint f USING (complaint_id)
),
direct AS (   -- method 2: plain counting — "rows of the same group whose date is in [d-N, d-1]"
    SELECT s.complaint_id, s.why,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id
                                             AND x.date_received <  s.d)                              AS company_n_prior,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id
                                             AND x.date_received BETWEEN s.d - 30 AND s.d - 1)        AS company_n_30d,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id
                                             AND x.date_received BETWEEN s.d - 90 AND s.d - 1)        AS company_n_90d,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id AND x.issue_id = s.issue_id
                                             AND x.date_received BETWEEN s.d - 90 AND s.d - 1)        AS company_issue_n_90d,
      (SELECT count(*) FROM fact_complaint x WHERE x.issue_id = s.issue_id
                                             AND x.date_received BETWEEN s.d - 90 AND s.d - 1)        AS issue_n_90d,
      (SELECT count(*) FROM fact_complaint x WHERE x.date_received BETWEEN s.d - 7 AND s.d - 1)       AS national_n_7d
    FROM s
),
v AS MATERIALIZED (   -- method 1: the view (window functions)
    SELECT * FROM v_volume WHERE complaint_id IN (SELECT complaint_id FROM sample)
)
SELECT d.why, d.complaint_id,
       v.company_n_prior, v.company_n_30d, v.company_n_90d,
       v.company_issue_n_90d, v.issue_n_90d, v.national_n_7d,
       CASE WHEN (v.company_n_prior, v.company_n_30d, v.company_n_90d,
                  v.company_issue_n_90d, v.issue_n_90d, v.national_n_7d)
               = (d.company_n_prior, d.company_n_30d, d.company_n_90d,
                  d.company_issue_n_90d, d.issue_n_90d, d.national_n_7d)
            THEN 'PASS' ELSE '** FAIL **' END AS result
FROM   direct d
LEFT   JOIN v USING (complaint_id)       -- LEFT: a complaint missing from the view shows as FAIL
ORDER  BY d.why, d.complaint_id;
