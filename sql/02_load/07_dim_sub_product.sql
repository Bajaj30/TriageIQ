-- ============================================================
-- 02_load/07_dim_sub_product.sql
-- TARGET  : dim_sub_product
-- READS   : stg_canonical, dim_product
-- EXPECT  : 62 (product, sub-product) pairs = 60 real + 2 '(not specified)'
-- CONCEPT : Same child pattern as 06 — but the parent is the CANONICAL product (D12).
-- ============================================================
-- STEPS
--  1. DISTINCT (canonical product, sub-product) pairs from stg_canonical, NULL -> '(not specified)'
--  2. JOIN dim_product on the name to swap the product NAME for its product_id
--  3. INSERT the (product_id, sub_product_name) pairs

-- Checked first: 0 blank and 0 case-only duplicate sub-products.
-- Only 32 complaints have no sub-product (22 Checking or savings, 10 old-name Payday) -> 2 placeholders.
-- 58 names -> 60 real pairs: 'Title loan' (Payday + Vehicle loan) and 'Credit reporting'
-- (Credit reporting + 1 complaint under Checking) each sit under 2 products.
-- Reads stg_canonical, NOT stg_window: the 3 retired raw product names are not in dim_product,
-- so the inner join would silently drop every sub-product filed under them.

WITH pairs AS (                                           -- step 1: 4.8M rows shrink to 62 pairs
    SELECT DISTINCT
           canonical_product                        AS product_name,
           COALESCE(sub_product, '(not specified)') AS sub_product_name
    FROM   stg_canonical
)
INSERT INTO dim_sub_product (product_id, sub_product_name)
SELECT d.product_id, p.sub_product_name                   -- step 2: parent name -> parent id
FROM   pairs       p
JOIN   dim_product d ON d.product_name = p.product_name
ORDER  BY d.product_id, p.sub_product_name
ON CONFLICT (product_id, sub_product_name) DO NOTHING;

-- CHECKS
-- 1. expect 62. Fewer = pairs were dropped by the join.
SELECT count(*) AS sub_products FROM dim_sub_product;

-- 2. placeholder members. Expect 2 rows: Checking or savings account, Payday loan...
SELECT d.product_name
FROM   dim_sub_product sp
JOIN   dim_product     d ON d.product_id = sp.product_id
WHERE  sp.sub_product_name = '(not specified)';

-- 3. real names under more than one product. Expect 2 rows: Credit reporting, Title loan.
SELECT sub_product_name, count(*) AS n_products
FROM   dim_sub_product
WHERE  sub_product_name <> '(not specified)'
GROUP  BY sub_product_name
HAVING count(*) > 1;

-- 4. sub-products per product — the split worked if Credit card has 2, Prepaid card 5,
--    Debt or credit management 4 (2 routed in: Credit repair services, Debt settlement). Sums to 62.
SELECT d.product_name, count(*) AS sub_products
FROM   dim_sub_product sp
JOIN   dim_product     d ON d.product_id = sp.product_id
GROUP  BY d.product_name
ORDER  BY sub_products DESC;

-- 5. every window complaint finds exactly one sub-product. Expect 4,826,564.
SELECT count(*) AS complaints_matched
FROM   stg_canonical   s
JOIN   dim_product     d  ON d.product_name       = s.canonical_product
JOIN   dim_sub_product sp ON sp.product_id        = d.product_id
                         AND sp.sub_product_name  = COALESCE(s.sub_product, '(not specified)');
