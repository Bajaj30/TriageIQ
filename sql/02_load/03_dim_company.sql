-- ============================================================
-- 02_load/03_dim_company.sql
-- TARGET  : dim_company
-- READS   : stg_window
-- EXPECT  : 4,946 (4,950 raw names − 4 case-only duplicates)
-- CONCEPT : GROUP BY + aggregate. One row per company, with a value computed across all its complaints.
-- ============================================================
-- STEPS
--  1. GROUP BY lower(company) — merges 'ATM OPS Inc' / 'ATM OPS INC'
--  2. keep one spelling: MIN(company)
--  3. first_seen_in_window = MIN(date_received::date)

-- Checked first: 0 window rows have a NULL or blank company, so no placeholder member is needed
-- (unlike dim_state). Company is NOT NULL in the schema — a NULL here would make the insert fail.

INSERT INTO dim_company (company_name, first_seen_in_window)
SELECT MIN(company),                 -- 'ATM OPS Inc' vs 'ATM OPS INC': keep ONE spelling. Which one is
                                     --   irrelevant — the fact table joins on lower(), never the spelling
       MIN(date_received::date)      -- the company's first complaint IN OUR WINDOW (not its real age)
FROM   stg_window
GROUP  BY lower(company)             -- GROUP BY, not DISTINCT: we need a per-company aggregate (MIN date)
ORDER  BY 1                          -- stable ids across rebuilds
ON CONFLICT ((lower(company_name))) DO NOTHING;
--          ^ double brackets: the conflict target is the EXPRESSION lower(company_name), matching the
--            case-insensitive unique index from 01_schema. A plain (company_name) would find no index.

-- CHECKS
-- 1. expect 4,946  (4,950 raw spellings - 4 case-only duplicates)
SELECT count(*) AS companies FROM dim_company;

-- 2. the 4 merges, visible: raw spellings that now share one company row
SELECT d.company_id, d.company_name AS kept, string_agg(DISTINCT w.company, ' | ') AS raw_spellings
FROM   dim_company d
JOIN   stg_window  w ON lower(w.company) = lower(d.company_name)
GROUP  BY d.company_id, d.company_name
HAVING count(DISTINCT w.company) > 1;

-- 3. every window complaint finds its company. Expect 4,826,564.
SELECT count(*) AS complaints_matched
FROM   stg_window  w
JOIN   dim_company d ON lower(d.company_name) = lower(w.company);
