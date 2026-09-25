-- ============================================================
-- 02_load/01_views.sql
-- TARGET  : stg_window, stg_canonical
-- READS   : stg_complaints_raw, product_crosswalk
-- EXPECT  : stg_window 4,826,564 · stg_canonical 4,826,564 (the LEFT JOIN must NOT change the count)
-- CONCEPT : VIEW = a saved query that stores nothing. Write the window filter and the crosswalk logic ONCE;
--           every later step reads from these views.
-- ============================================================
-- STEPS
--  1. stg_window: staging rows with date_received::date between 2022-01-01 and 2024-12-31
--  2. stg_canonical: stg_window + one column canonical_product =
--     COALESCE(crosswalk.canonical_product, raw product), via a LEFT JOIN on
--     raw_product = product AND (raw_sub_product = sub_product OR raw_sub_product IS NULL)
--  3. Count both. If stg_canonical has MORE rows, one complaint matched two rules — a fan-out.

-- Drop the dependent view first: stg_canonical is built on top of stg_window.
DROP VIEW IF EXISTS stg_canonical;
DROP VIEW IF EXISTS stg_window;

-- ---------------------------------------------------------------------------
-- VIEW 1 — stg_window: only complaints received inside the working window.
-- A view stores NO data. Every time you SELECT from it, Postgres re-runs this query
-- against stg_complaints_raw. It's a saved filter, so no later file repeats it.
-- ---------------------------------------------------------------------------
CREATE VIEW stg_window AS
SELECT *
FROM   stg_complaints_raw
WHERE  date_received::date BETWEEN DATE '2022-01-01' AND DATE '2024-12-31';
--     ^ staging holds dates as TEXT; ::date converts before comparing

-- ---------------------------------------------------------------------------
-- VIEW 2 — stg_canonical: stg_window + one extra column, canonical_product.
-- This is the D12 crosswalk applied to every row, written once.
-- ---------------------------------------------------------------------------
CREATE VIEW stg_canonical AS
SELECT w.*,
       COALESCE(cw.canonical_product, w.product) AS canonical_product
       --       ^ a rule matched: use it     ^ no rule: keep the raw name
FROM   stg_window w
LEFT JOIN product_crosswalk cw                       -- LEFT: most rows have NO rule; they must survive
       ON cw.raw_product = w.product
      AND (cw.raw_sub_product = w.sub_product        -- a rule for this exact sub-product ...
           OR cw.raw_sub_product IS NULL);           -- ... or a rule that covers ANY sub-product (payday)

-- ---------------------------------------------------------------------------
-- CHECKS
-- ---------------------------------------------------------------------------
-- 1. Both counts must be 4,826,564. If stg_canonical is HIGHER, some complaint matched
--    two crosswalk rules and got duplicated (a fan-out).
SELECT 'stg_window'    AS view_name, count(*) AS rows FROM stg_window
UNION ALL
SELECT 'stg_canonical',              count(*)         FROM stg_canonical;

-- 2. See the crosswalk work: every raw name that changed, and what it became.
SELECT product            AS raw_product,
       canonical_product,
       count(*)           AS rows
FROM   stg_canonical
WHERE  canonical_product <> product
GROUP  BY product, canonical_product
ORDER  BY rows DESC;
