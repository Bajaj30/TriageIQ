-- ============================================================
-- tests/06_serving_check.sql — the SKEW TEST
-- TESTS   : sql/06_serving (snapshot + serving.model_input) against training's own numbers (v_model_input)
-- IDEA    : two implementations of the same 19 inputs now exist — window functions for training, a
--           scoreboard + formula for serving. Rebuild the scoreboard AS OF three real past days, send every
--           complaint received on those days through serving.model_input, and compare with what training
--           stored for them. Like checking a new calculator on yesterday's sums whose answers you know.
-- DAYS    : 2022-03-15  warm-up: many companies with no history yet, first-ever complaints
--           2023-08-28  just after the CFPB form change (renamed products / issue)
--           2024-12-10  the busiest day in the data (one company: 4,245 complaints — thousands of ties)
-- ONE RULE TO KNOW — quiet days: training orders a company's complaints by (date, id), so the 2nd, 3rd …
--   complaint of the same company on the same day has a "previous complaint" that same day: gap 0. A live
--   complaint is scored alone against end-2024 data — there is no same-day predecessor. So the expected
--   serving value is the snapshot's gap for the company's FIRST complaint of the day, and 0 for the rest.
-- EXPECT  : every input PASS (mismatches 0) · probe snapshots removed at the end · ~1 min
-- ============================================================

CALL build_serving_snapshot(DATE '2022-03-15');
CALL build_serving_snapshot(DATE '2023-08-28');
CALL build_serving_snapshot(DATE '2024-12-10');

WITH c AS MATERIALIZED (                      -- every complaint received on the three days
    SELECT b.complaint_id, b.date_received, b.company_id, b.product_id, b.sub_product_id, b.issue_id,
           b.state_id, b.is_older_american, b.is_servicemember,
           row_number() OVER (PARTITION BY b.company_id, b.date_received ORDER BY b.complaint_id) AS nth_today
    FROM   v_base b
    WHERE  b.date_received IN (DATE '2022-03-15', DATE '2023-08-28', DATE '2024-12-10')
),
pairs AS MATERIALIZED (                       -- training's value next to serving's, one row per input
    SELECT c.complaint_id, c.date_received, v.input, v.train, v.serve
    FROM   c
    JOIN   v_model_input t USING (complaint_id)
    CROSS  JOIN LATERAL serving.model_input(c.company_id, c.product_id, c.sub_product_id, c.issue_id,
                                            c.state_id, c.is_older_american, c.is_servicemember,
                                            c.date_received) f
    CROSS  JOIN LATERAL (VALUES
        ('01 product_id',               t.product_id::numeric,              f.product_id::numeric),
        ('02 sub_product_id',           t.sub_product_id::numeric,          f.sub_product_id::numeric),
        ('03 issue_id',                 t.issue_id::numeric,                f.issue_id::numeric),
        ('04 state_id',                 t.state_id::numeric,                f.state_id::numeric),
        ('05 is_older_american',        t.is_older_american::numeric,       f.is_older_american::numeric),
        ('06 is_servicemember',         t.is_servicemember::numeric,        f.is_servicemember::numeric),
        ('07 company_no_history',       t.company_no_history::numeric,      f.company_no_history::numeric),
        ('08 company_issue_no_history', t.company_issue_no_history::numeric, f.company_issue_no_history::numeric),
        ('09 company_issue_rate_s',     t.company_issue_rate_s,             f.company_issue_rate_s),
        ('10 company_rate_s',           t.company_rate_s,                   f.company_rate_s),
        ('11 issue_rate_s',             t.issue_rate_s,                     f.issue_rate_s),
        ('12 product_rate_s',           t.product_rate_s,                   f.product_rate_s),
        ('13 company_untimely_rate',    t.company_untimely_rate,            f.company_untimely_rate),
        ('14 company_share_90d',        t.company_share_90d,                f.company_share_90d),
        ('15 company_issue_share_90d',  t.company_issue_share_90d,          f.company_issue_share_90d),
        ('16 issue_share_90d',          t.issue_share_90d,                  f.issue_share_90d),
        ('17 company_trend_90d',        t.company_trend_90d,                f.company_trend_90d),
        ('18 issue_trend_90d',          t.issue_trend_90d,                  f.issue_trend_90d),
        ('19 company_quiet_days',       t.company_quiet_days::numeric,
                                        CASE WHEN c.nth_today = 1 THEN f.company_quiet_days ELSE 0 END::numeric)
    ) AS v (input, train, serve)
)
SELECT input,
       count(*)                                                                  AS complaints,
       count(*) FILTER (WHERE train IS DISTINCT FROM serve
                          AND NOT coalesce(abs(train - serve) < 1e-12, false))   AS mismatches,
       max(abs(train - serve))                                                   AS max_abs_diff,
       CASE WHEN count(*) FILTER (WHERE train IS DISTINCT FROM serve
                                    AND NOT coalesce(abs(train - serve) < 1e-12, false)) = 0
            THEN 'PASS' ELSE '** FAIL **' END                                    AS result
FROM   pairs
GROUP  BY input ORDER BY input;

-- The test has teeth only if the hard cases are in it. Expect every count > 0.
SELECT b.date_received                                                        AS day,
       count(*)                                                               AS complaints,
       count(*) FILTER (WHERE m.company_no_history = 1)                       AS company_no_history,
       count(*) FILTER (WHERE m.company_issue_no_history = 1)                 AS pair_no_history,
       count(*) FILTER (WHERE m.days_since_prev_company_complaint IS NULL)    AS first_ever_complaint,
       count(*) FILTER (WHERE m.days_since_prev_company_complaint = 0)        AS same_day_ties
FROM   v_base b JOIN mv_features m USING (complaint_id)
WHERE  b.date_received IN (DATE '2022-03-15', DATE '2023-08-28', DATE '2024-12-10')
GROUP  BY 1 ORDER BY 1;

-- Clean up: only the live snapshot stays. Expect 1 row: 2025-01-01.
DELETE FROM serving.snap_product       WHERE as_of <> DATE '2025-01-01';
DELETE FROM serving.snap_issue         WHERE as_of <> DATE '2025-01-01';
DELETE FROM serving.snap_company       WHERE as_of <> DATE '2025-01-01';
DELETE FROM serving.snap_company_issue WHERE as_of <> DATE '2025-01-01';
DELETE FROM serving.snap_national      WHERE as_of <> DATE '2025-01-01';
SELECT as_of FROM serving.snap_national;
