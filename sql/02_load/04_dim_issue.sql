-- ============================================================
-- 02_load/04_dim_issue.sql
-- TARGET  : dim_issue
-- READS   : stg_canonical
-- EXPECT  : 93 (92 canonical issues + '(not specified)' for 6 NULL rows)
-- CONCEPT : Same pattern as dim_state.
-- ============================================================
-- STEPS
--  1. SELECT DISTINCT COALESCE(canonical_issue, '(not specified)')

-- Reads stg_canonical, NOT stg_window: the dimension holds CANONICAL names (D17).
-- 93 raw issue names -> 92: the renamed investigation issue keeps only its new name.

-- Checked first: 6 window rows have a NULL issue, 0 have a blank-but-not-NULL one.
-- COALESCE only catches NULL — if blanks existed, they would become a separate '' member.

INSERT INTO dim_issue (issue_name)
SELECT DISTINCT COALESCE(canonical_issue, '(not specified)')   -- 6 NULL issues -> placeholder (D9)
FROM   stg_canonical
ORDER  BY 1
ON CONFLICT (issue_name) DO NOTHING;

-- CHECKS
-- 1. expect 93  (92 canonical issues + '(not specified)')
SELECT count(*) AS issues FROM dim_issue;

-- 1b. the retired name must NOT be in the dimension. Expect 0 rows.
SELECT issue_name FROM dim_issue
WHERE  issue_name = 'Problem with a credit reporting company''s investigation into an existing problem';

-- 2. the placeholder, and how many complaints will use it (expect 6)
SELECT d.issue_id, d.issue_name, count(*) AS complaints
FROM   dim_issue  d
JOIN   stg_canonical w ON COALESCE(w.canonical_issue, '(not specified)') = d.issue_name
WHERE  d.issue_name = '(not specified)'
GROUP  BY d.issue_id, d.issue_name;

-- 3. every window complaint finds its issue. Expect 4,826,564.
SELECT count(*) AS complaints_matched
FROM   stg_canonical w
JOIN   dim_issue     d ON d.issue_name = COALESCE(w.canonical_issue, '(not specified)');
