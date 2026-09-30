-- ============================================================
-- tests/07_trends_check.sql
-- TESTS   : view v_trends (03_features/07_trends.sql) — the columns it adds on top of v_volume
-- HOW     : recount the new windows with plain WHERE ... BETWEEN (no window functions) and rebuild the
--           trends and shares from those counts, for 20 complaints by hash + the busiest company-day.
--           (v_volume's own columns are covered by 03_volume_check.sql.)
-- EXPECT  : every row PASS (numeric results compared after rounding to 12 decimals)
-- ============================================================
WITH busiest_day AS (
    SELECT company_id, date_received FROM fact_complaint
    GROUP  BY company_id, date_received ORDER BY count(*) DESC LIMIT 1
),
sample AS (
    (SELECT complaint_id, 'random' AS why FROM fact_complaint ORDER BY md5(complaint_id::text) LIMIT 20)
    UNION ALL
    SELECT min(f.complaint_id), 'busiest day' FROM fact_complaint f JOIN busiest_day USING (company_id, date_received)
),
s AS (
    SELECT sample.complaint_id, sample.why, f.company_id, f.issue_id, f.date_received AS d
    FROM   sample JOIN fact_complaint f USING (complaint_id)
),
counts AS (
    SELECT s.complaint_id, s.why,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id
                          AND x.date_received BETWEEN s.d - 90  AND s.d - 1)   AS company_now,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id
                          AND x.date_received BETWEEN s.d - 180 AND s.d - 91)  AS company_prev,
      (SELECT count(*) FROM fact_complaint x WHERE x.issue_id = s.issue_id
                          AND x.date_received BETWEEN s.d - 90  AND s.d - 1)   AS issue_now,
      (SELECT count(*) FROM fact_complaint x WHERE x.issue_id = s.issue_id
                          AND x.date_received BETWEEN s.d - 180 AND s.d - 91)  AS issue_prev,
      (SELECT count(*) FROM fact_complaint x WHERE x.company_id = s.company_id AND x.issue_id = s.issue_id
                          AND x.date_received BETWEEN s.d - 90  AND s.d - 1)   AS pair_now,
      (SELECT count(*) FROM fact_complaint x
                          WHERE x.date_received BETWEEN s.d - 90  AND s.d - 1) AS national_now
    FROM s
),
direct AS (
    SELECT complaint_id, why, company_prev, issue_prev, national_now,
           round(ln((company_now + 1.0) / (company_prev + 1.0)), 12)       AS company_trend,
           round(ln((issue_now   + 1.0) / (issue_prev   + 1.0)), 12)       AS issue_trend,
           round(company_now::numeric / NULLIF(national_now, 0), 12)       AS company_share,
           round(pair_now::numeric    / NULLIF(national_now, 0), 12)       AS pair_share,
           round(issue_now::numeric   / NULLIF(national_now, 0), 12)       AS issue_share
    FROM counts
),
v AS MATERIALIZED (
    SELECT * FROM v_trends WHERE complaint_id IN (SELECT complaint_id FROM sample)
)
SELECT d.why, d.complaint_id,
       v.company_n_prev_90d, round(v.company_trend_90d, 3) AS company_trend,
       round(100 * v.company_share_90d, 3) AS company_share_pct,
       CASE WHEN (v.company_n_prev_90d, v.issue_n_prev_90d, v.national_n_90d,
                  round(v.company_trend_90d, 12), round(v.issue_trend_90d, 12),
                  round(v.company_share_90d, 12), round(v.company_issue_share_90d, 12), round(v.issue_share_90d, 12))
                 IS NOT DISTINCT FROM
                 (d.company_prev, d.issue_prev, d.national_now,
                  d.company_trend, d.issue_trend, d.company_share, d.pair_share, d.issue_share)
            THEN 'PASS' ELSE '** FAIL **' END AS result
FROM   direct d LEFT JOIN v USING (complaint_id)
ORDER  BY d.why, d.complaint_id;
