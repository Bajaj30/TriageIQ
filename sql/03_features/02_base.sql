-- ============================================================
-- 03_features/02_base.sql
-- TARGET  : view v_base
-- READS   : fact_complaint, v_label
-- EXPECT  : 4,826,564 rows — exactly the fact's count. A different count means the join broke the grain.
-- CONCEPT : One row per complaint, only the columns features need. Check the row count after EVERY join.
-- PROBLEM : "One clean starting table: each complaint exactly once, with its ids and its answer."
--           Why: every feature file reads from here, so the row count is proven ONCE, in one place.
--           Without it: each file repeats the join; one bad join silently duplicates or drops complaints.
-- ============================================================
-- STEPS
--  1. from fact_complaint: complaint_id, date_received, company_id, product_id, issue_id, state_id
--  2. JOIN v_label USING (complaint_id) — one-to-one
--  3. check: count = 4,826,564 · sum(paid) = 60,952
--  4. NO post-intake columns (sent date, response, timely, public response) — trap #4
--  5. tags -> TWO 0/1 flags: is_older_american, is_servicemember (a complaint can have both)
--     values: NULL (no tag) · 'Servicemember' · 'Older American' · 'Older American, Servicemember'
--     Hint: NULL LIKE '%x%' is NULL, not false — wrap the test so 'no tag' becomes 0.

-- Column choices:
--  * sub_product_id / sub_issue_id are carried as plain ids for the model. No RATES are built on
--    sub-issue (trap #10: for 4 issues a blank sub-issue means "filed before Aug 2023").
--  * submitted_via is left out: among complaints with text (the training rows) it has ONE value
--    (Web), so it can't teach the model anything. It stays in the fact table.
--  * paid / untimely are OUTCOMES. They are here only so 04 can build past-outcome rates with the
--    60-day lag — never as inputs for the complaint's own row (08 leaves them out).

CREATE OR REPLACE VIEW v_base AS
SELECT f.complaint_id,
       f.date_received,
       f.company_id,
       f.state_id,
       f.product_id,
       f.sub_product_id,
       f.issue_id,
       f.sub_issue_id,
       -- step 5: two yes/no flags. coalesce turns "no tag" (NULL) into '' so LIKE gives false, not NULL.
       (coalesce(f.tags, '') LIKE '%Older American%')::int AS is_older_american,
       (coalesce(f.tags, '') LIKE '%Servicemember%')::int  AS is_servicemember,
       l.paid,                                   -- the label (outcome)
       l.untimely                                -- an outcome too — only used lagged, in 04
FROM   fact_complaint f
JOIN   v_label        l USING (complaint_id);    -- step 2: exactly one label per complaint

-- CHECKS
-- 1. grain + label + flags, all in one row. Expect:
--    rows 4,826,564 · complaints 4,826,564 · paid 60,952 · untimely 2,785
--    older_american 84,865 (65,016 alone + 19,849 both) · servicemember 201,147 (181,298 + 19,849) · both 19,849
SELECT count(*)                                                        AS rows,
       count(DISTINCT complaint_id)                                    AS complaints,
       sum(paid)                                                       AS paid,
       sum(untimely)                                                   AS untimely,
       sum(is_older_american)                                          AS older_american,
       sum(is_servicemember)                                           AS servicemember,
       count(*) FILTER (WHERE is_older_american = 1 AND is_servicemember = 1) AS both_tags
FROM   v_base;

-- 2. the flags carry signal: payout rate by flag (all complaints). Older Americans ~10%, untagged ~1%.
SELECT is_older_american, is_servicemember,
       count(*)                     AS complaints,
       round(100.0 * avg(paid), 2)  AS payout_pct
FROM   v_base
GROUP  BY 1, 2
ORDER  BY 1, 2;
