-- ============================================================
-- 01_schema/01_dimensions.sql
-- PURPOSE : CREATE the dimension tables — structure only, no data
-- DESIGN  : surrogate keys (D4) · children UNIQUE (parent_id, name) (D6)
--           Issue independent of Product (D7) · '(not specified)' members, never NULL keys (D9)
-- REF     : Context/schema_explanation.md
-- EXPECT  (F1, after load): 4,950 companies · 61 states + '(not specified)'
--           11 canonical products · 93 issues
-- ============================================================
-- Drop children before parents (foreign keys point child -> parent).
DROP TABLE IF EXISTS dim_sub_issue, dim_issue, dim_sub_product, dim_product, dim_state, dim_company CASCADE;

-- Company ------------------------------------------------------------
-- Thin by design (D5): attributes only. Counts and rates are MEASURES, computed as-of-date later.
CREATE TABLE dim_company (
    company_id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_name          TEXT NOT NULL,
    first_seen_in_window  DATE          -- first complaint in OUR 2022-24 data, NOT company age
);
-- 4 names differ only by case ('ATM OPS Inc' / 'ATM OPS INC'): one company, one id.
CREATE UNIQUE INDEX uq_dim_company_name_ci ON dim_company (lower(company_name));

-- State --------------------------------------------------------------
CREATE TABLE dim_state (
    state_id    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state_code  TEXT NOT NULL UNIQUE     -- includes '(not specified)' for the 0.23% NULL
);

-- Product -> Sub-product (parent -> child) ------------------------------
CREATE TABLE dim_product (
    product_id    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name  TEXT NOT NULL UNIQUE   -- CANONICAL name (new CFPB taxonomy, D12)
);

CREATE TABLE dim_sub_product (
    sub_product_id    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id        INTEGER NOT NULL REFERENCES dim_product (product_id),
    sub_product_name  TEXT NOT NULL,      -- '(not specified)' when the complaint had none
    -- The same name exists under several products ('Credit reporting' under 3): unique on the PAIR.
    UNIQUE (product_id, sub_product_name),
    -- Lets fact_complaint prove its product_id agrees with its sub_product_id (see 03_fact).
    UNIQUE (sub_product_id, product_id)
);

-- Issue -> Sub-issue (parent -> child), independent of Product ----------
CREATE TABLE dim_issue (
    issue_id    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_sub_issue (
    sub_issue_id    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_id        INTEGER NOT NULL REFERENCES dim_issue (issue_id),
    sub_issue_name  TEXT NOT NULL,        -- '(not specified)' for the 122,207 with none (D9)
    UNIQUE (issue_id, sub_issue_name),
    UNIQUE (sub_issue_id, issue_id)
);
