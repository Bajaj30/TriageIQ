-- ============================================================
-- 02_load/05_dim_product.sql
-- TARGET  : dim_product
-- READS   : stg_canonical
-- EXPECT  : 11 canonical products — 'Credit card or prepaid card' must NOT appear
-- CONCEPT : The crosswalk in action: 14 raw names collapse to 11.
-- ============================================================
-- STEPS
--  1. SELECT DISTINCT canonical_product FROM stg_canonical

-- Checked first: 0 NULL and 0 blank products in the window, so no placeholder member is needed.
-- Reads stg_canonical, NOT stg_window: the dimension holds CANONICAL names, never raw ones.

INSERT INTO dim_product (product_name)
SELECT DISTINCT canonical_product      -- 14 raw names collapse to 11 here (D12 crosswalk)
FROM   stg_canonical
ORDER  BY 1
ON CONFLICT (product_name) DO NOTHING;

-- CHECKS
-- 1. expect 11
SELECT count(*) AS products FROM dim_product;

-- 2. the 3 retired raw names must NOT be in the dimension. Expect 0 rows.
SELECT product_name
FROM   dim_product
WHERE  product_name IN ('Credit card or prepaid card',
                        'Credit reporting, credit repair services, or other personal consumer reports',
                        'Payday loan, title loan, or personal loan');

-- 3. complaints per canonical product — the split products should now show continuous volume
SELECT d.product_id, d.product_name, count(*) AS complaints
FROM   dim_product   d
JOIN   stg_canonical s ON s.canonical_product = d.product_name
GROUP  BY d.product_id, d.product_name
ORDER  BY complaints DESC;

-- 4. every window complaint finds its product. Expect 4,826,564.
SELECT count(*) AS complaints_matched
FROM   stg_canonical s
JOIN   dim_product   d ON d.product_name = s.canonical_product;
