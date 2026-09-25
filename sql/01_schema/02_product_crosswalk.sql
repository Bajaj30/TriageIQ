-- ============================================================
-- 01_schema/02_product_crosswalk.sql
-- PURPOSE : the D12 mapping — raw (product, sub-product) -> canonical product
-- DESIGN  : bottom-up routing for products renamed/split in the 2023-08-24 CFPB form change.
--           Keyed on (raw_product, raw_sub_product), NEVER sub-product alone (would collide with D6).
--           Only the EXCEPTIONS are listed. Any raw pair not found here keeps its raw product name.
--           raw_sub_product NULL = "any sub-product" (used for the payday rename).
-- REF     : Context/schema_explanation.md — D12
-- EXPECT  : 12 rules · 1,334,958 F1 rows re-routed · 14 raw products -> 11 canonical
-- ============================================================
DROP TABLE IF EXISTS product_crosswalk;

CREATE TABLE product_crosswalk (
    raw_product        TEXT NOT NULL,
    raw_sub_product    TEXT,               -- NULL = matches any sub-product of raw_product
    canonical_product  TEXT NOT NULL,
    reason             TEXT NOT NULL,
    UNIQUE NULLS NOT DISTINCT (raw_product, raw_sub_product)   -- one rule per pair, NULL included
);

-- Seed data IS the design decision, so it lives with the DDL. Strings verified against staging.
INSERT INTO product_crosswalk (raw_product, raw_sub_product, canonical_product, reason) VALUES
 ('Credit card or prepaid card', 'General-purpose credit card or charge card', 'Credit card',  'split'),
 ('Credit card or prepaid card', 'Store credit card',                          'Credit card',  'split'),
 ('Credit card or prepaid card', 'General-purpose prepaid card',               'Prepaid card', 'split'),
 ('Credit card or prepaid card', 'Government benefit card',                    'Prepaid card', 'split'),
 ('Credit card or prepaid card', 'Gift card',                                  'Prepaid card', 'split'),
 ('Credit card or prepaid card', 'Payroll card',                               'Prepaid card', 'split'),
 ('Credit card or prepaid card', 'Student prepaid card',                       'Prepaid card', 'split'),
 ('Credit reporting, credit repair services, or other personal consumer reports', 'Credit reporting',
    'Credit reporting or other personal consumer reports', 'rename'),
 ('Credit reporting, credit repair services, or other personal consumer reports', 'Other personal consumer report',
    'Credit reporting or other personal consumer reports', 'rename'),
 ('Credit reporting, credit repair services, or other personal consumer reports', 'Credit repair services',
    'Debt or credit management', 'split-off'),
 ('Payday loan, title loan, or personal loan', NULL,
    'Payday loan, title loan, personal loan, or advance loan', 'rename'),
 ('Money transfer, virtual currency, or money service', 'Debt settlement',
    'Debt or credit management', 'split-off (hidden: the parent product never changed)');

SELECT count(*) AS rules FROM product_crosswalk;   -- expect 12
