-- ============================================================
-- 03_features/05a_choose_k.sql          (TUNING — changes nothing; run before 05)
-- TARGET  : the smoothing strength K used in 05_smoothing.sql
-- READS   : v_outcome_rates, v_base
-- PROBLEM : smoothed = (payouts + K x product_rate) / (complaints + K). Small K trusts tiny samples,
--           big K throws the entity's own history away. Which K makes the rate most useful?
-- METHOD  : for each candidate K, score every complaint of the TUNING period (2023-10-01..2023-12-31,
--           all complaints) with its smoothed rate and measure:
--             AUC   — how often a complaint that paid is ranked above one that didn't (higher = better)
--             Brier — average (rate - outcome)^2: how close the rate is to reality (lower = better)
--           overall, and on the complaints where K matters: history under 200.
--           NEVER the 2024 test period — choosing K there would leak the exam into the design.
-- NOTE    : K = 0 is the raw rate; with no history at all every K falls back to the product rate.
-- ============================================================
WITH v AS MATERIALIZED (
    SELECT e.entity, e.n, e.payouts, o.product_paid_rate AS prior, b.paid
    FROM   v_outcome_rates o
    JOIN   v_base          b USING (complaint_id)
    CROSS  JOIN LATERAL (VALUES ('company x issue', o.company_issue_n_known, o.company_issue_payouts),
                                ('company',         o.company_n_known,       o.company_payouts)
                        ) AS e (entity, n, payouts)
    WHERE  b.date_received BETWEEN DATE '2023-10-01' AND DATE '2023-12-31'
),
k AS (SELECT unnest(ARRAY[0, 1, 2, 3, 5, 7, 10, 25, 50, 100, 200, 500]) AS k),
scored AS (
    SELECT v.entity, k.k, v.paid, (v.n < 200) AS small,
           CASE WHEN v.n + k.k = 0 THEN v.prior                                   -- no history, K = 0
                ELSE (coalesce(v.payouts, 0) + k.k * v.prior) / (v.n + k.k) END AS score
    FROM   v CROSS JOIN k
),
by_score AS (          -- AUC with ties counted as half: group equal scores, count paid / not paid
    SELECT entity, k, subset, score, sum(paid) AS pos, count(*) - sum(paid) AS neg
    FROM   scored
    CROSS  JOIN LATERAL (VALUES ('all'), (CASE WHEN small THEN 'history < 200' END)) AS s (subset)
    WHERE  subset IS NOT NULL
    GROUP  BY entity, k, subset, score
),
ranked AS (
    SELECT *, coalesce(sum(neg) OVER (PARTITION BY entity, k, subset ORDER BY score
                                      ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING), 0) AS neg_below
    FROM   by_score
),
auc AS (
    SELECT entity, k, subset,
           sum(pos * (neg_below + 0.5 * neg)) / (sum(pos) * sum(neg)) AS auc,
           sum(pos + neg) AS complaints
    FROM   ranked GROUP BY entity, k, subset
),
brier AS (
    SELECT entity, k, subset, avg((score - paid) ^ 2) AS brier
    FROM   scored
    CROSS  JOIN LATERAL (VALUES ('all'), (CASE WHEN small THEN 'history < 200' END)) AS s (subset)
    WHERE  subset IS NOT NULL
    GROUP  BY entity, k, subset
)
SELECT entity, subset, k, complaints,
       round(auc, 4)                 AS auc,
       round(brier * 1000, 3)        AS brier_x1000
FROM   auc JOIN brier USING (entity, k, subset)
ORDER  BY entity DESC, subset, k;
