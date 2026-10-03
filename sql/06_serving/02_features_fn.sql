-- ============================================================
-- 06_serving/02_features_fn.sql
-- TARGET  : function serving.model_input(...) -> the 19 model inputs for ONE complaint, as of a snapshot day
-- READS   : serving.snap_* (01), serving.feature_params
-- PROBLEM : "Turn the scoreboard into exactly the numbers the model was trained on."
-- ============================================================
-- CONCEPT : the calculator on top of the scoreboard. Every formula below is the training formula,
--   rewritten for ONE day instead of every day:
--     smoothing  (05_smoothing.sql) : (payouts + K x prior) / (n + K); prior = the product's smoothed rate;
--                                     the product's own prior = the 2021 fallback
--     shares     (07_trends.sql)    : n_90d / national n_90d
--     trends     (07_trends.sql)    : ln((n_90d + 1) / (n_prev_90d + 1))
--     quiet days (06_sequence.sql + 08) : days since the company's last complaint; never had one -> days
--                                     since the data starts (2022-01-01), the same lower bound as training
--   Counts that don't exist (a new company, a never-seen company x issue pair) are 0 — the formula then
--   returns the product prior and the no-history flag = 1, which is what training did for first complaints.
--   Output columns and their ORDER = v_model_input (the first 19, v3) — the API passes them straight on.
-- WHY TWO IMPLEMENTATIONS ARE OK HERE: training needs every day (windows); serving needs one day (lookups).
--   The skew test (sql/tests/06_serving_check.sql) proves they agree, digit for digit, on real past days.
-- INPUTS  : the ids the user picks (company may be NULL = a company not in our data), the two tag flags,
--           and optionally the snapshot day (default: the newest one).
-- ============================================================

CREATE OR REPLACE FUNCTION serving.model_input(
    p_company_id        INTEGER,
    p_product_id        INTEGER,
    p_sub_product_id    INTEGER,
    p_issue_id          INTEGER,
    p_state_id          INTEGER,
    p_is_older_american INTEGER,
    p_is_servicemember  INTEGER,
    p_as_of             DATE DEFAULT NULL)
RETURNS TABLE (
    product_id INTEGER, sub_product_id INTEGER, issue_id INTEGER, state_id INTEGER,
    is_older_american INTEGER, is_servicemember INTEGER, company_no_history INTEGER, company_issue_no_history INTEGER,
    company_issue_rate_s NUMERIC, company_rate_s NUMERIC, issue_rate_s NUMERIC, product_rate_s NUMERIC,
    company_untimely_rate NUMERIC, company_share_90d NUMERIC, company_issue_share_90d NUMERIC,
    issue_share_90d NUMERIC, company_trend_90d NUMERIC, issue_trend_90d NUMERIC, company_quiet_days INTEGER)
LANGUAGE sql STABLE AS $$
    WITH d AS (                                          -- which snapshot day
        SELECT coalesce(p_as_of, (SELECT max(n.as_of) FROM serving.snap_national n)) AS day
    ),
    prm AS (                                             -- K and the fallback, read once
        SELECT max(f.value) FILTER (WHERE f.param = 'k')              AS k,
               max(f.value) FILTER (WHERE f.param = 'fallback_prior') AS fallback
        FROM   serving.feature_params f
    ),
    c AS (                                               -- the counts; missing row -> 0 (sum stays NULL-safe)
        SELECT d.day, prm.k, prm.fallback,
               coalesce(pr.n_known, 0) AS pr_n,  coalesce(pr.payouts, 0) AS pr_pay,
               coalesce(co.n_known, 0) AS co_n,  coalesce(co.payouts, 0) AS co_pay, co.untimely_rate AS co_untimely,
               coalesce(co.n_90d, 0)   AS co_90, coalesce(co.n_prev_90d, 0) AS co_prev, co.last_date AS co_last,
               coalesce(ci.n_known, 0) AS ci_n,  coalesce(ci.payouts, 0) AS ci_pay, coalesce(ci.n_90d, 0) AS ci_90,
               coalesce(i.n_known, 0)  AS i_n,   coalesce(i.payouts, 0)  AS i_pay,
               coalesce(i.n_90d, 0)    AS i_90,  coalesce(i.n_prev_90d, 0) AS i_prev,
               na.n_90d                AS nat_90
        FROM   d CROSS JOIN prm
        LEFT   JOIN serving.snap_product       pr ON pr.as_of = d.day AND pr.product_id = p_product_id
        LEFT   JOIN serving.snap_company       co ON co.as_of = d.day AND co.company_id = p_company_id
        LEFT   JOIN serving.snap_company_issue ci ON ci.as_of = d.day AND ci.company_id = p_company_id
                                                                      AND ci.issue_id   = p_issue_id
        LEFT   JOIN serving.snap_issue         i  ON i.as_of  = d.day AND i.issue_id    = p_issue_id
        LEFT   JOIN serving.snap_national      na ON na.as_of = d.day
    ),
    s AS (                                               -- step 1: the product rate is everyone's prior
        SELECT c.*, (c.pr_pay + c.k * c.fallback) / (c.pr_n + c.k) AS prior FROM c
    )
    SELECT p_product_id, p_sub_product_id, p_issue_id, p_state_id,
           p_is_older_american, p_is_servicemember,
           (s.co_n = 0)::int,
           (s.ci_n = 0)::int,
           (s.ci_pay + s.k * s.prior) / (s.ci_n + s.k),                         -- company x issue, smoothed
           (s.co_pay + s.k * s.prior) / (s.co_n + s.k),                         -- company, smoothed
           (s.i_pay  + s.k * s.prior) / (s.i_n  + s.k),                         -- issue, smoothed
           s.prior,                                                             -- product, smoothed
           coalesce(s.co_untimely, 0),
           s.co_90::numeric / NULLIF(s.nat_90, 0),
           s.ci_90::numeric / NULLIF(s.nat_90, 0),
           s.i_90::numeric  / NULLIF(s.nat_90, 0),
           ln((s.co_90 + 1.0) / (s.co_prev + 1.0)),
           ln((s.i_90  + 1.0) / (s.i_prev  + 1.0)),
           coalesce(s.day - s.co_last, s.day - DATE '2022-01-01')
    FROM   s
$$;

-- CHECKS
-- 1. a real pair and a brand-new company, as of the live snapshot. Expect: the new company has both
--    no-history flags = 1, company rates = the product prior, shares 0, trends 0, quiet days 1096.
SELECT 'busiest pair' AS who, f.*
FROM   (SELECT company_id, issue_id FROM serving.snap_company_issue
        WHERE as_of = '2025-01-01' ORDER BY n_90d DESC LIMIT 1) top
JOIN   LATERAL (SELECT product_id, sub_product_id, state_id FROM fact_complaint fc
                WHERE fc.company_id = top.company_id AND fc.issue_id = top.issue_id LIMIT 1) eg ON true
CROSS  JOIN LATERAL serving.model_input(top.company_id, eg.product_id, eg.sub_product_id, top.issue_id,
                                        eg.state_id, 0, 0) f
UNION ALL
SELECT 'new company', f.*
FROM   serving.model_input(NULL, 1, 1, 1, 1, 1, 0) f;

-- 2. speed: one call. Expect well under 5 ms.
EXPLAIN (ANALYZE, COSTS OFF, SUMMARY ON)
SELECT * FROM serving.model_input(1, 1, 1, 1, 1, 0, 0);
