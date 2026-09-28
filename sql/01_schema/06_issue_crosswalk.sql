-- ============================================================
-- 01_schema/06_issue_crosswalk.sql
-- PURPOSE : the D17 mapping — raw issue name -> canonical issue name
-- DESIGN  : the 2023-08-25 CFPB form change renamed an ISSUE too, not just products.
--           Same idea as the product crosswalk (D8, D13): two names for one thing -> one id.
--           Keyed on the issue name alone: the rename happened under every product on the same day.
--           Only PROVEN renames are listed; any issue not found here keeps its raw name.
-- REF     : Context/schema_explanation.md — D17
-- EXPECT  : 1 rule · 337,252 F1 rows re-routed · dim_issue 94 -> 93
-- ============================================================
DROP TABLE IF EXISTS issue_crosswalk CASCADE;   -- CASCADE: view stg_canonical depends on it;
                                                -- 02_load/01_views.sql rebuilds the view

CREATE TABLE issue_crosswalk (
    raw_issue        TEXT PRIMARY KEY,   -- one rule per raw name, so the LEFT JOIN can never fan out
    canonical_issue  TEXT NOT NULL,
    reason           TEXT NOT NULL
);

-- Evidence (F1): old name last seen 2023-08-25, new name first seen 2023-08-25; both appear under
-- the same 7 products; both carry the same 5 sub-issues. A pure rename, 893,566 complaints in total.
-- Unfixed, the company x issue history of the most common issue resets 5 weeks before validation.
INSERT INTO issue_crosswalk (raw_issue, canonical_issue, reason) VALUES
 ('Problem with a credit reporting company''s investigation into an existing problem',
  'Problem with a company''s investigation into an existing problem',
  'rename 2023-08-25');

-- sanity: expect 1
SELECT count(*) AS rules FROM issue_crosswalk;
