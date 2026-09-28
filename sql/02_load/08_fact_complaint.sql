-- ============================================================
-- 02_load/08_fact_complaint.sql
-- TARGET  : fact_complaint
-- READS   : stg_canonical + all 6 dimensions
-- EXPECT  : 4,826,564 — one row per complaint in the window (D10)
-- CONCEPT : Swap every name for its id. Each join must use EXACTLY the expression used to build that dimension.
-- ============================================================
-- STEPS
--  1. JOIN each dimension on the same expression used to build it (lower(), COALESCE(...))
--  2. sub-dimensions join on BOTH parent id and name
--  3. cast complaint_id::bigint, date_received::date; raw_product = original product name
--  4. if short: switch joins to LEFT JOIN one at a time, look for WHERE <id> IS NULL

-- LEFT JOIN, not INNER, on purpose: every id column is NOT NULL, so a complaint whose name finds no
-- dimension row gets a NULL id and the INSERT FAILS LOUDLY. An INNER JOIN would drop it silently.
-- LEFT JOIN + NOT NULL turns "fewer rows" into an error message.
-- Each dimension is unique on its join key, so no join can add rows (no fan-out). Check 1 proves it.

INSERT INTO fact_complaint (complaint_id, date_received,
                            company_id, state_id,
                            product_id, sub_product_id,
                            issue_id,   sub_issue_id,
                            raw_product, submitted_via, tags)
SELECT s.complaint_id::bigint,                              -- step 3: text -> real types
       s.date_received::date,
       c.company_id,
       st.state_id,
       p.product_id,  sp.sub_product_id,
       i.issue_id,    si.sub_issue_id,
       s.product,                                           -- raw name, before the crosswalk (D8)
       s.submitted_via,
       s.tags                                               -- stays NULL when absent (open decision)
FROM   stg_canonical   s
LEFT   JOIN dim_company     c  ON lower(c.company_name) = lower(s.company)          -- same as 03
LEFT   JOIN dim_state       st ON st.state_code   = COALESCE(s.state, '(not specified)')
LEFT   JOIN dim_product     p  ON p.product_name  = s.canonical_product           -- canonical, not raw
LEFT   JOIN dim_sub_product sp ON sp.product_id   = p.product_id                   -- step 2: parent id
                              AND sp.sub_product_name = COALESCE(s.sub_product, '(not specified)')
LEFT   JOIN dim_issue       i  ON i.issue_name    = COALESCE(s.issue, '(not specified)')
LEFT   JOIN dim_sub_issue   si ON si.issue_id     = i.issue_id
                              AND si.sub_issue_name   = COALESCE(s.sub_issue, '(not specified)')
ON CONFLICT (complaint_id) DO NOTHING;

-- CHECKS
-- 1. expect 4,826,564. More = a join fanned out; fewer is impossible (it would have errored).
SELECT count(*) AS complaints FROM fact_complaint;

-- 2. date range must sit inside the window (the CHECK constraint already enforces it).
SELECT min(date_received) AS first_day, max(date_received) AS last_day FROM fact_complaint;

-- 3. the crosswalk survived into the fact: rows whose raw name differs from the canonical one.
--    Expect 1,334,958 (same number 01_views reported).
SELECT count(*) AS rerouted
FROM   fact_complaint f
JOIN   dim_product    p ON p.product_id = f.product_id
WHERE  f.raw_product <> p.product_name;

-- 4. placeholder members in use. Expect: sub-product 32, issue 6, sub-issue 122,207.
SELECT 'sub_product' AS placeholder, count(*) FROM fact_complaint f
  JOIN dim_sub_product x ON x.sub_product_id = f.sub_product_id WHERE x.sub_product_name = '(not specified)'
UNION ALL
SELECT 'issue',       count(*) FROM fact_complaint f
  JOIN dim_issue       x ON x.issue_id       = f.issue_id       WHERE x.issue_name       = '(not specified)'
UNION ALL
SELECT 'sub_issue',   count(*) FROM fact_complaint f
  JOIN dim_sub_issue   x ON x.sub_issue_id   = f.sub_issue_id   WHERE x.sub_issue_name   = '(not specified)'
UNION ALL
SELECT 'state',       count(*) FROM fact_complaint f
  JOIN dim_state       x ON x.state_id       = f.state_id       WHERE x.state_code       = '(not specified)';

-- 5. submitted_via — the open decision, now measurable in SQL. Expect 5 values.
SELECT submitted_via, count(*) FROM fact_complaint GROUP BY 1 ORDER BY 2 DESC;
