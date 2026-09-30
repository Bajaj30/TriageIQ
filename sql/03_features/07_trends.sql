-- ============================================================
-- 03_features/07_trends.sql
-- TARGET  : view v_trends
-- READS   : v_volume, v_base
-- EXPECT  : 4,826,564 rows · no divide-by-zero · trends and shares never NULL (except shares on day one)
-- CONCEPT : Two frames on one row: last 90 days vs the 90 before. Ratios instead of raw counts.
-- PROBLEM : "Is this company's (or issue's) complaint volume rising or falling?"
--           Why: direction matters, not just level — a company whose complaints doubled is getting worse.
--           Without zero handling: divide-by-zero, or huge fake 'trends' for companies with an empty past.
-- ============================================================
-- STEPS
--  1. company: count 1-90 days ago and 91-180 days ago
--  2. trend = recent / NULLIF(earlier, 0), plus a flag for 'earlier period was empty'
--  3. same for issue, system-wide

-- Two changes from the steps above, both on purpose:
--  * trend = ln((recent + 1) / (earlier + 1)) instead of recent / NULLIF(earlier, 0).
--    0 = flat, +0.69 = doubled, -0.69 = halved. The +1 (add-one smoothing) means it never divides by
--    zero and is never NULL, so no extra flag is needed; a doubling and a halving get the same size.
--  * SHARES of national volume, added. Raw counts drift: complaint volume tripled from 2022 to 2024
--    (03_features/log.md), so a 2024 count looks "big" to a model trained on 2022-23. A share —
--    this company's slice of all complaints in the last 90 days — doesn't grow with total volume.
-- Frames: recent = days d-90..d-1 (already in v_volume) · earlier = days d-180..d-91 (new, here).
-- Warm-up: before 2022-06-30 the earlier window reaches back before the data starts, so it is
-- partly empty and trends read too high in early 2022. Note it for the training-set cut.
-- v_trends carries every column of v_volume (v.*), so 08 reads one view, not two.

CREATE OR REPLACE VIEW v_trends AS
WITH earlier AS (                              -- step 1 + 3: the new windows — 91..180 days back
    SELECT complaint_id,
           count(*) OVER (PARTITION BY company_id ORDER BY date_received
                          RANGE BETWEEN INTERVAL '180 days' PRECEDING AND INTERVAL '91 days' PRECEDING) AS company_n_prev_90d,
           count(*) OVER (PARTITION BY issue_id   ORDER BY date_received
                          RANGE BETWEEN INTERVAL '180 days' PRECEDING AND INTERVAL '91 days' PRECEDING) AS issue_n_prev_90d,
           count(*) OVER (                        ORDER BY date_received
                          RANGE BETWEEN INTERVAL '90 days'  PRECEDING AND INTERVAL '1 day' PRECEDING)   AS national_n_90d
    FROM   v_base
)
SELECT v.*,
       e.company_n_prev_90d, e.issue_n_prev_90d, e.national_n_90d,
       -- step 2: rising or falling
       ln((v.company_n_90d + 1.0) / (e.company_n_prev_90d + 1.0))           AS company_trend_90d,
       ln((v.issue_n_90d   + 1.0) / (e.issue_n_prev_90d   + 1.0))           AS issue_trend_90d,
       -- shares: this group's slice of every complaint in the last 90 days (NULL only on day one)
       v.company_n_90d::numeric       / NULLIF(e.national_n_90d, 0)          AS company_share_90d,
       v.company_issue_n_90d::numeric / NULLIF(e.national_n_90d, 0)          AS company_issue_share_90d,
       v.issue_n_90d::numeric         / NULLIF(e.national_n_90d, 0)          AS issue_share_90d
FROM   v_volume v
JOIN   earlier  e USING (complaint_id);          -- one row each side per complaint: no fan-out
-- "+ 1.0", not "+ 1": integer / integer would round down to a whole number before ln().

-- CHECKS — each reads the view ONCE (a MATERIALIZED CTE).

-- 1. grain and sanity. Expect rows = complaints = 4,826,564; null_trends = 0; null_shares = only the
--    complaints of 2022-01-01 (no earlier day exists); shares between 0 and 1.
WITH v AS MATERIALIZED (SELECT * FROM v_trends)
SELECT count(*)                                                          AS rows,
       count(DISTINCT complaint_id)                                      AS complaints,
       count(*) FILTER (WHERE company_trend_90d IS NULL OR issue_trend_90d IS NULL) AS null_trends,
       count(*) FILTER (WHERE company_share_90d IS NULL)                 AS null_shares,
       (SELECT count(*) FROM fact_complaint WHERE date_received = DATE '2022-01-01') AS day_one_complaints,
       count(*) FILTER (WHERE company_share_90d > 1 OR issue_share_90d > 1
                           OR company_issue_share_90d > company_share_90d) AS share_broken
FROM   v;

-- 2. DRIFT CHECK — the point of shares: raw counts grow by year, shares should not.
WITH v AS MATERIALIZED (SELECT * FROM v_trends)
SELECT extract(year FROM b.date_received)::int           AS year,
       round(avg(v.company_n_90d))                      AS avg_company_n_90d,
       round(100 * avg(v.company_share_90d), 3)         AS avg_company_share_pct,
       round(avg(v.company_trend_90d), 3)               AS avg_company_trend
FROM   v JOIN v_base b USING (complaint_id)
GROUP  BY 1 ORDER BY 1;
