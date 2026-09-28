-- ============================================================
-- 02_load/06_dim_sub_issue.sql
-- TARGET  : dim_sub_issue
-- READS   : stg_canonical, dim_issue
-- EXPECT  : 293 (issue, sub-issue) pairs = 241 real + 52 '(not specified)'
-- CONCEPT : First CHILD dimension. A child row stores its parent's ID, so we must join to the parent.
-- ============================================================
-- STEPS
--  1. DISTINCT (canonical issue, sub-issue) pairs from stg_canonical, NULL -> '(not specified)'
--  2. JOIN dim_issue on the name to swap the issue NAME for its issue_id
--  3. INSERT the (issue_id, sub_issue_name) pairs

-- Checked first: 0 blank and 0 case-only duplicate sub-issues.
-- 122,207 complaints have no sub-issue, spread over 51 issues -> 51 placeholder members,
-- +1 under the '(not specified)' issue (its 6 complaints have neither) = 52.
-- 29 sub-issue names sit under more than one issue, so the PAIR is unique, not the name (D6).
-- Parent = CANONICAL issue (D17): the renamed issue's 5 sub-issues exist under both names;
-- they merge into 5 pairs under the new name (298 raw pairs -> 293).

WITH pairs AS (                                        -- step 1: 4.8M rows shrink to 293 pairs
    SELECT DISTINCT
           COALESCE(canonical_issue, '(not specified)') AS issue_name,
           COALESCE(sub_issue,       '(not specified)') AS sub_issue_name
    FROM   stg_canonical
)
INSERT INTO dim_sub_issue (issue_id, sub_issue_name)
SELECT i.issue_id, p.sub_issue_name                    -- step 2: parent name -> parent id
FROM   pairs     p
JOIN   dim_issue i ON i.issue_name = p.issue_name      -- joins 293 rows, not 4.8M (aggregate, then join)
ORDER  BY i.issue_id, p.sub_issue_name                 -- ids come out grouped by parent
ON CONFLICT (issue_id, sub_issue_name) DO NOTHING;

-- An INNER join drops a pair whose issue is missing from dim_issue — silently. Check 1 catches that.

-- CHECKS
-- 1. expect 293. Fewer = pairs were dropped by the join.
SELECT count(*) AS sub_issues FROM dim_sub_issue;

-- 2. placeholder members. Expect 52.
SELECT count(*) AS placeholders
FROM   dim_sub_issue
WHERE  sub_issue_name = '(not specified)';

-- 3. why the unique key is the PAIR: real names under more than one issue. Expect 29.
SELECT count(*) AS names_under_many_issues
FROM  (SELECT sub_issue_name
       FROM   dim_sub_issue
       WHERE  sub_issue_name <> '(not specified)'
       GROUP  BY sub_issue_name
       HAVING count(*) > 1) x;

-- 4. every window complaint finds exactly one sub-issue. Expect 4,826,564.
--    Fewer = rows dropped; more = one complaint matched two rows (fan-out).
SELECT count(*) AS complaints_matched
FROM   stg_canonical w
JOIN   dim_issue     i  ON i.issue_name      = COALESCE(w.canonical_issue, '(not specified)')
JOIN   dim_sub_issue si ON si.issue_id       = i.issue_id
                       AND si.sub_issue_name = COALESCE(w.sub_issue, '(not specified)');
