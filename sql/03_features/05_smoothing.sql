-- ============================================================
-- 03_features/05_smoothing.sql
-- TARGET  : table feature_params (K + fallback) · view v_smoothed
-- READS   : v_outcome_rates, feature_params, stg_complaints_raw (once, for the fallback)
-- EXPECT  : 4,826,564 rows · smoothed rates in [0, 1], never NULL
-- CONCEPT : Shrinkage: (payouts + K x prior) / (n + K) — small samples pulled toward a sensible default.
-- PROBLEM : "How far can we trust a rate built from only a few complaints?"
--           Why: 1 payout in 3 complaints is not a real '33% payer', and most of the 4,946 companies are small.
--           Without it: the model over-reacts to tiny samples — noise dressed up as signal.
-- ============================================================
-- STEPS
--  1. prior = the PRODUCT's payout rate to date (from 04) — itself as-of date   (trap #9)
--  2. company and company x issue rates: shrink toward that prior with weight K
--  3. when the prior is NULL too (a product's first 60 days), fall back to a stated constant
--  K = 5 — MEASURED in 05a_choose_k.sql (tuning period, AUC + Brier; 2..7 about equal, 50 clearly worse)
--  prior = the product's rate to date (trap #9)

-- The prior must also be as-of date — an all-time prior leaks the future (guardrail §10).

-- ---------------------------------------------------------------- the parameters, as DATA
-- Same idea as the crosswalks: a setting lives in a table, not buried in the view. Changing K later is
-- one UPDATE; the view picks it up on its next read. IF NOT EXISTS: the view depends on this table,
-- so it is never dropped — re-running the file only refreshes the values (ON CONFLICT DO UPDATE).
CREATE TABLE IF NOT EXISTS feature_params (
    param   TEXT    PRIMARY KEY,
    value   NUMERIC NOT NULL,
    source  TEXT    NOT NULL                 -- where the number came from: every number has a reason
);

INSERT INTO feature_params (param, value, source)
VALUES ('k', 5, '05a_choose_k.sql — tuning period Oct-Dec 2023; decided 2026-10-01, with a grain of salt')
ON CONFLICT (param) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source;

-- step 3 — the fallback for the first 60 days of 2022, when NO outcome is known yet for anything.
-- It must also be known BEFORE the window starts: the overall payout rate of 2021, computed from the
-- raw file (0.028576 = 14,172 of 495,939). Pre-window data, so it cannot leak. ~20 s: it scans staging.
INSERT INTO feature_params (param, value, source)
SELECT 'fallback_prior',
       avg((company_response_to_consumer = 'Closed with monetary relief')::int),
       'overall payout rate of 2021 (pre-window, stg_complaints_raw): used only before any product rate exists'
FROM   stg_complaints_raw
WHERE  date_received::date BETWEEN DATE '2021-01-01' AND DATE '2021-12-31'
ON CONFLICT (param) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source;

-- ---------------------------------------------------------------- the view
-- A chain of two shrinks, the same formula each time:
--   product rate  shrinks toward the 2021 fallback  -> never NULL (its n is huge after 60 days,
--                                                       so K = 5 barely touches it)
--   company, company x issue, issue rates shrink toward that smoothed product rate
-- No history at all (n = 0): the formula gives exactly the prior — no special case needed.
-- v_smoothed carries EVERY column of v_outcome_rates (o.*) plus the smoothed ones, so 08 reads one
-- view. Joining both views in 08 would compute the four windows twice.
-- Not smoothed: company_untimely_rate — there is no product-level untimely rate to shrink toward yet;
-- it stays raw (NULL = no history) and 08 decides.

-- DROP ... CASCADE, not OR REPLACE: 04 gained columns (recent history), which shifts prior.* — OR REPLACE
-- refuses to move columns. CASCADE also drops mv_features + v_model_input: re-run 08_assembly.sql after.
DROP VIEW IF EXISTS v_smoothed CASCADE;
CREATE VIEW v_smoothed AS
WITH p AS (                                   -- the two parameters, read once
    SELECT max(value) FILTER (WHERE param = 'k')              AS k,
           max(value) FILTER (WHERE param = 'fallback_prior') AS fallback
    FROM   feature_params
),
prior AS (                                    -- step 1 + 3: the smoothed product rate is the prior
    SELECT o.*, p.k,
           (coalesce(o.product_payouts, 0) + p.k * p.fallback) / (o.product_n_known + p.k) AS product_rate_s
    FROM   v_outcome_rates o CROSS JOIN p
),
longrun AS (                                  -- step 2: (payouts + K x prior) / (n + K)
    SELECT prior.*,
           (coalesce(company_payouts, 0)       + k * product_rate_s) / (company_n_known       + k) AS company_rate_s,
           (coalesce(company_issue_payouts, 0) + k * product_rate_s) / (company_issue_n_known + k) AS company_issue_rate_s,
           (coalesce(issue_payouts, 0)         + k * product_rate_s) / (issue_n_known         + k) AS issue_rate_s
    FROM   prior
)
SELECT longrun.*,                             -- everything above, plus RECENT rates (added 2026-10-02):
       -- the same formula one level down: the last 12 months, pulled toward the entity's OWN all-time rate.
       -- Few recent complaints -> close to the long-run rate; many -> the recent behaviour shows through.
       (coalesce(company_issue_payouts_recent, 0) + k * company_issue_rate_s) / (company_issue_n_recent + k)
                                                                                    AS company_issue_recent_rate_s,
       (coalesce(company_payouts_recent, 0)       + k * company_rate_s)       / (company_n_recent       + k)
                                                                                    AS company_recent_rate_s
FROM   longrun;
-- coalesce(payouts, 0): sum() over an empty frame is NULL, and NULL + anything = NULL.

-- CHECKS — each reads the view ONCE (a MATERIALIZED CTE); ~45 s each.

-- 1. the parameters. Expect k = 5 and fallback_prior = 0.028576 (rounded).
SELECT param, round(value, 6) AS value, source FROM feature_params ORDER BY param;

-- 2. grain and sanity. Expect rows = complaints = 4,826,564 and every other column 0.
WITH v AS MATERIALIZED (SELECT * FROM v_smoothed)
SELECT count(*)                                                        AS rows,
       count(DISTINCT complaint_id)                                    AS complaints,
       count(*) FILTER (WHERE product_rate_s IS NULL OR company_rate_s IS NULL
                           OR company_issue_rate_s IS NULL OR issue_rate_s IS NULL
                           OR company_issue_recent_rate_s IS NULL OR company_recent_rate_s IS NULL) AS any_null,
       count(*) FILTER (WHERE least(product_rate_s, company_rate_s, company_issue_rate_s, issue_rate_s,
                                    company_issue_recent_rate_s, company_recent_rate_s) < 0
                           OR greatest(product_rate_s, company_rate_s, company_issue_rate_s, issue_rate_s,
                                    company_issue_recent_rate_s, company_recent_rate_s) > 1)
                                                                       AS out_of_range
FROM   v;

-- 3. how far smoothing moved each pair's rate, by how much history it has. Expect: big moves for
--    1-9 complaints, almost nothing for 1,000+ (K = 5 is tiny next to 1,000 real complaints).
WITH v AS MATERIALIZED (SELECT company_issue_n_known AS n, company_issue_paid_rate AS raw,
                               company_issue_rate_s AS smoothed FROM v_smoothed)
SELECT CASE WHEN n = 0 THEN '1: none' WHEN n < 10 THEN '2: 1-9' WHEN n < 50 THEN '3: 10-49'
            WHEN n < 200 THEN '4: 50-199' WHEN n < 1000 THEN '5: 200-999' ELSE '6: 1,000+' END AS pair_history,
       count(*)                                          AS complaints,
       round(100 * avg(abs(smoothed - raw)), 3)          AS avg_move_pct_points,
       round(100 * max(abs(smoothed - raw)), 3)          AS max_move_pct_points
FROM   v GROUP BY 1 ORDER BY 1;
-- ("none" shows NULL moves: there is no raw rate to move — those complaints simply get the prior.)
