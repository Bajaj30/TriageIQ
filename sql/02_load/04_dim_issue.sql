-- ============================================================
-- 02_load/04_dim_issue.sql
-- TARGET  : dim_issue
-- READS   : stg_window
-- EXPECT  : 94 (93 issues + '(not specified)' for 6 NULL rows)
-- CONCEPT : Same pattern as dim_state.
-- ============================================================
-- STEPS
--  1. SELECT DISTINCT COALESCE(issue, '(not specified)')

-- Checked first: 6 window rows have a NULL issue, 0 have a blank-but-not-NULL one.
-- COALESCE only catches NULL — if blanks existed, they would become a separate '' member.

INSERT INTO dim_issue (issue_name)
SELECT DISTINCT COALESCE(issue, '(not specified)')   -- 6 NULL issues -> placeholder member (D9)
FROM   stg_window
ORDER  BY 1
ON CONFLICT (issue_name) DO NOTHING;

-- CHECKS
-- 1. expect 94  (93 real issues + '(not specified)')
SELECT count(*) AS issues FROM dim_issue;

-- 2. the placeholder, and how many complaints will use it (expect 6)
SELECT d.issue_id, d.issue_name, count(*) AS complaints
FROM   dim_issue  d
JOIN   stg_window w ON COALESCE(w.issue, '(not specified)') = d.issue_name
WHERE  d.issue_name = '(not specified)'
GROUP  BY d.issue_id, d.issue_name;

-- 3. every window complaint finds its issue. Expect 4,826,564.
SELECT count(*) AS complaints_matched
FROM   stg_window w
JOIN   dim_issue  d ON d.issue_name = COALESCE(w.issue, '(not specified)');
