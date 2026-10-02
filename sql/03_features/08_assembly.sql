-- ============================================================
-- 03_features/08_assembly.sql
-- TARGET  : materialized view mv_features  +  view v_model_input
-- READS   : v_base + 03 .. 07
-- EXPECT  : 4,826,564 rows · complaint_id unique · 15-25 features
-- CONCEPT : A MATERIALIZED view is computed once and stored: the training export and the API read the same rows.
-- PROBLEM : "One row per complaint with every feature, stored and ready" — the exact table the model trains
--           on AND the API reads.
--           Why: one source of truth (ground rule 4) — training and serving see identical numbers.
--           Without it: recompute ~20 window features over 4.8M rows per request (too slow), or copy the
--           logic into Python and let the two drift apart.
-- ============================================================
-- STEPS
--  1. join every layer ON complaint_id — each is one row per complaint, so the count stays 4,826,564
--  2. UNIQUE INDEX on complaint_id; index on company_id (the API's lookups)
--  3. time the build — the reason it is materialized
--  4. every feature gets an entry in feature_dictionary.md, or it doesn't ship

-- REFRESH is manual for now; Phase 3 automates it. Stale data is silent — say so in the README.

-- Two layers, on purpose:
--  * mv_features  — the FEATURE STORE: every feature built in 03-07, stored. Includes columns the model
--                   will NOT use (raw counts, clocks) so they stay available for analysis and drift checks.
--  * v_model_input — the MODEL'S LIST: exactly the 23 columns the model reads. Choosing features is a
--                   design decision, so it lives in SQL too, in one place — the export and the API both
--                   read this view. Change the model's inputs = edit this view, nothing else.
-- NEVER in either: paid, untimely, company_response — the answer itself (check 2 proves it).
-- The label is joined only when the training set is built (04_training_set).

-- Rebuild: DROP ... CASCADE also drops v_model_input, which is re-created below.
DROP MATERIALIZED VIEW IF EXISTS mv_features CASCADE;

CREATE MATERIALIZED VIEW mv_features AS
SELECT
    -- keys: which complaint, when, and its categories
    b.complaint_id, b.date_received,
    b.company_id, b.state_id, b.product_id, b.sub_product_id, b.issue_id, b.sub_issue_id,
    -- 02: consumer tags
    b.is_older_american, b.is_servicemember,
    -- 03 + 07: volume, trends, shares
    t.company_n_prior, t.company_n_30d, t.company_n_90d, t.company_issue_n_90d, t.issue_n_90d,
    t.national_n_7d, t.company_n_prev_90d, t.issue_n_prev_90d, t.national_n_90d,
    t.company_trend_90d, t.issue_trend_90d,
    t.company_share_90d, t.company_issue_share_90d, t.issue_share_90d,
    -- 04 + 05: track records (smoothed, K = 5) and how much history is behind them
    s.company_n_known, s.company_issue_n_known, s.issue_n_known, s.product_n_known,
    s.company_rate_s, s.company_issue_rate_s, s.issue_rate_s, s.product_rate_s,
    coalesce(s.company_untimely_rate, 0) AS company_untimely_rate,   -- NULL only with no history,
                                                                      -- which company_no_history flags
    s.company_no_history, s.company_issue_no_history,
    -- 06: the company's own timeline
    q.days_since_prev_company_complaint,
    coalesce(q.days_since_prev_company_complaint, q.days_since_start) AS company_quiet_days,
    --       ^ first-ever complaint: no previous one inside the data, so the company has been quiet
    --         for AT LEAST the days since the data began — a lower bound, never NULL
    q.company_rank_this_month, q.company_tenure_days, q.days_since_start,
    -- added 2026-10-02: RECENT track records (04/05) and the AMOUNT the consumer mentions (01_schema/08)
    s.company_issue_n_recent, s.company_n_recent,
    s.company_issue_recent_rate_s, s.company_recent_rate_s,
    coalesce(n.n_amounts, 0)                         AS n_amounts,
    n.max_amount,                                                       -- NULL = no amount mentioned
    (n.max_amount IS NOT NULL)::int                  AS has_amount,      -- parsed value, not the raw count
    ln(1 + coalesce(n.max_amount, 0))                AS log_max_amount   -- $10 vs $10,000: a log scale
FROM   v_base     b
JOIN   v_trends   t USING (complaint_id)
JOIN   v_smoothed s USING (complaint_id)
JOIN   v_sequence q USING (complaint_id)
LEFT   JOIN complaint_narrative n USING (complaint_id);   -- LEFT: 3.2M complaints have no text (amount = none)
-- each view is one row per complaint -> every join is 1:1 -> still 4,826,564 rows (check 1)

-- step 2: UNIQUE on complaint_id — the grain, enforced. It also allows REFRESH ... CONCURRENTLY
-- later (the API keeps reading while it rebuilds), and serves the API's one-complaint lookup.
CREATE UNIQUE INDEX ux_mv_features_complaint ON mv_features (complaint_id);
CREATE INDEX        ix_mv_features_company   ON mv_features (company_id, date_received);
ANALYZE mv_features;

-- ---------------------------------------------------------------- the model's list: 23 inputs
-- Why each is in or out: sql/03_features/feature_dictionary.md
CREATE OR REPLACE VIEW v_model_input AS
SELECT complaint_id,
       -- categories (4) — the model learns one small vector per value
       product_id, sub_product_id, issue_id, state_id,
       -- yes/no flags (4)
       is_older_american, is_servicemember, company_no_history, company_issue_no_history,
       -- track records (5) — the strongest non-text signal
       company_issue_rate_s, company_rate_s, issue_rate_s, product_rate_s, company_untimely_rate,
       -- volume, as shares and trends — not raw counts, which drift with total volume (5)
       company_share_90d, company_issue_share_90d, issue_share_90d, company_trend_90d, issue_trend_90d,
       -- timeline (1)
       company_quiet_days,
       -- added 2026-10-02 (4): recent track records + the amount in the complaint
       company_issue_recent_rate_s, company_recent_rate_s, has_amount, log_max_amount
FROM   mv_features;

-- CHECKS

-- 1. grain + NULLs in the model's 19 inputs. Expect rows = complaints = 4,826,564;
--    null_inputs = 535 (the three shares on 2022-01-01, when no earlier day exists) and nothing else.
WITH i AS MATERIALIZED (             -- the model's view + the date, to spot day one
    SELECT i.*, m.date_received FROM v_model_input i JOIN mv_features m USING (complaint_id)
)
SELECT count(*)                          AS rows,
       count(DISTINCT complaint_id)      AS complaints,
       count(*) FILTER (WHERE num_nulls(product_id, sub_product_id, issue_id, state_id,
                                        is_older_american, is_servicemember, company_no_history,
                                        company_issue_no_history, company_issue_rate_s, company_rate_s,
                                        issue_rate_s, product_rate_s, company_untimely_rate,
                                        company_share_90d, company_issue_share_90d, issue_share_90d,
                                        company_trend_90d, issue_trend_90d, company_quiet_days,
                                        company_issue_recent_rate_s, company_recent_rate_s,
                                        has_amount, log_max_amount) > 0) AS null_inputs,
       count(*) FILTER (WHERE company_share_90d IS NULL AND date_received = DATE '2022-01-01') AS of_which_day_one
FROM   i;

-- 2. LEAK GUARD — the answer must not be stored anywhere in the feature layer. Expect 0.
SELECT count(*) AS label_columns_found
FROM   pg_attribute
WHERE  attrelid IN ('mv_features'::regclass, 'v_model_input'::regclass)
AND    attname  IN ('paid', 'untimely', 'company_response')
AND    NOT attisdropped;

-- 3. how many inputs, and how big the store is. Expect 23 inputs (+ complaint_id).
SELECT (SELECT count(*) - 1 FROM pg_attribute
        WHERE attrelid = 'v_model_input'::regclass AND attnum > 0 AND NOT attisdropped) AS model_inputs,
       (SELECT count(*) FROM pg_attribute
        WHERE attrelid = 'mv_features'::regclass AND attnum > 0 AND NOT attisdropped)   AS stored_columns,
       pg_size_pretty(pg_total_relation_size('mv_features'))                             AS store_size;

-- 4. a lookup like the API's: one complaint's inputs, straight from the unique index.
EXPLAIN (ANALYZE, COSTS OFF)
SELECT * FROM v_model_input WHERE complaint_id = (SELECT max(complaint_id) FROM mv_features);
