-- ============================================================
-- 06_serving/03_serving_db.sql
-- TARGET  : the rest of schema serving — lists (dims), clean_narrative(), the 150k demo complaints
-- READS   : dim_*, clean_narrative(), v_training_export (training_set v3 test rows), v_label
-- PROBLEM : "Ship only what the live system needs — one file, not the 16 GB database."
-- ============================================================
-- CONCEPT : the full database stays on the Mac as the SOURCE (rebuild anything from it). The live system
--   gets a small, read-mostly copy:
--     lists          — company / product / sub-product / issue / state names <-> ids (people pick names)
--     scoreboard     — snap_* as of 2025-01-01 + serving.model_input()            (01, 02)
--     text cleaning  — serving.clean_narrative(): COPIED FROM public's definition, not retyped, so typed-in
--                      text is cleaned exactly like training text (train/serve skew for text)
--     demo complaints— the 150,000 test complaints of 2024: the inputs training stored for them (as of their
--                      own day), the cleaned text the model read, and what really happened
--   Then: pg_dump -n serving -> one file (see the end of this file).
-- RE-RUNNABLE: every object is dropped and rebuilt.
-- ============================================================
SET max_parallel_workers_per_gather = 0;

-- ---------------------------------------------------------------- 1. the lists
DROP TABLE IF EXISTS serving.company, serving.product, serving.sub_product, serving.issue, serving.state;
CREATE TABLE serving.company     AS SELECT company_id, company_name                     FROM dim_company;
CREATE TABLE serving.product     AS SELECT product_id, product_name                     FROM dim_product;
CREATE TABLE serving.sub_product AS SELECT sub_product_id, product_id, sub_product_name FROM dim_sub_product;
CREATE TABLE serving.issue       AS SELECT issue_id, issue_name                         FROM dim_issue;
CREATE TABLE serving.state       AS SELECT state_id, state_code                         FROM dim_state;
ALTER TABLE serving.company     ADD PRIMARY KEY (company_id);
ALTER TABLE serving.product     ADD PRIMARY KEY (product_id);
ALTER TABLE serving.sub_product ADD PRIMARY KEY (sub_product_id);
ALTER TABLE serving.issue       ADD PRIMARY KEY (issue_id);
ALTER TABLE serving.state       ADD PRIMARY KEY (state_id);
CREATE INDEX ix_serving_company_name ON serving.company (lower(company_name));   -- name search

-- ---------------------------------------------------------------- 2. text cleaning: copy, don't retype
-- pg_get_functiondef returns public's exact definition; only the schema name changes.
DO $$
BEGIN
    EXECUTE replace(pg_get_functiondef('public.clean_narrative(text)'::regprocedure),
                    'FUNCTION public.clean_narrative', 'FUNCTION serving.clean_narrative');
END $$;

-- ---------------------------------------------------------------- 3. the demo complaints (2024 test set)
DROP TABLE IF EXISTS serving.test_complaints;
CREATE TABLE serving.test_complaints AS
SELECT e.complaint_id, e.date_received, e.company_id,
       e.product_id, e.sub_product_id, e.issue_id, e.state_id,               -- the 19 inputs, as training
       e.is_older_american, e.is_servicemember, e.company_no_history,       -- stored them (as of each
       e.company_issue_no_history, e.company_issue_rate_s, e.company_rate_s, -- complaint's own day)
       e.issue_rate_s, e.product_rate_s, e.company_untimely_rate,
       e.company_share_90d, e.company_issue_share_90d, e.issue_share_90d,
       e.company_trend_90d, e.issue_trend_90d, e.company_quiet_days,
       e.text,                                                              -- cleaned, as the model read it
       e.paid,                                                              -- the answer
       l.company_response                                                   -- what the company actually did
FROM   v_training_export e
JOIN   v_label l USING (complaint_id)
WHERE  e.split = 'test';
ALTER TABLE serving.test_complaints ADD PRIMARY KEY (complaint_id);
ANALYZE serving.test_complaints;

-- CHECKS
-- 1. the demo set. Expect 150,000 complaints · 3,471 payouts (FACTS.md) · dates 2024-01-01 .. 2024-12-31.
SELECT count(*) AS complaints, sum(paid) AS payouts, min(date_received) AS first_day, max(date_received) AS last_day
FROM   serving.test_complaints;

-- 2. the copied cleaner equals the original on 2,000 real narratives. Expect differ = 0.
SELECT count(*) FILTER (WHERE serving.clean_narrative(narrative) IS DISTINCT FROM public.clean_narrative(narrative)) AS differ
FROM  (SELECT narrative FROM complaint_narrative ORDER BY md5(complaint_id::text) LIMIT 2000) s;

-- 3. what ships. Expect roughly 300 MB in total.
SELECT c.relname AS object, pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM   pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE  n.nspname = 'serving' AND c.relkind = 'r'
UNION ALL
SELECT 'TOTAL', pg_size_pretty(sum(pg_total_relation_size(c.oid)))
FROM   pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE  n.nspname = 'serving' AND c.relkind = 'r'
ORDER  BY 1;

-- ---------------------------------------------------------------- 4. ship it (run in a terminal, not pgAdmin)
-- docker exec triageiq-postgres pg_dump -U triageiq -d triageiq -n serving -Fc > training/outputs/serving_v3/serving_db.dump
-- Proof the file stands alone: restore it into an empty database and score one complaint (see sql/06_serving/log.md).
