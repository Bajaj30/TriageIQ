-- ============================================================
-- 02_load/12_indexes.sql          (DDL — run LAST, after 11_validate passes)
-- PURPOSE : indexes for the hot paths, then fresh statistics
-- WHY LAST: one index build over loaded data is far faster than updating it on every insert
-- EXPECT  : 6 new indexes · both EXPLAINs at the bottom show an Index (Only) Scan
-- ============================================================
-- pgAdmin note: VACUUM refuses to run inside a transaction. pgAdmin sends a whole script as ONE
-- transaction, so there run the VACUUM lines on their own (select them, then Execute). psql is fine.

SET maintenance_work_mem = '512MB';   -- this session only: index builds sort in memory, not on disk

-- Fact: "entity, then date" — exactly the shape of PARTITION BY entity ORDER BY date_received,
-- and of the API's lookup "this company's complaints BEFORE this date".
CREATE INDEX IF NOT EXISTS ix_fact_company_date       ON fact_complaint (company_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_company_issue_date ON fact_complaint (company_id, issue_id, date_received);
                                                       -- company x issue: the project's main entity
CREATE INDEX IF NOT EXISTS ix_fact_issue_date         ON fact_complaint (issue_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_product_date       ON fact_complaint (product_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_date               ON fact_complaint (date_received);

-- Events: every outcome feature and the label view need ONE thing — the 'responded' outcome of a
-- complaint. A PARTIAL index (only 4.8M 'responded' rows, not all 14.5M) that also CARRIES the
-- outcome (INCLUDE) answers that from the index alone, never touching the 2.4 GB table.
-- It replaces the planned generic (event_type, complaint_id) index.
CREATE INDEX IF NOT EXISTS ix_events_responded        ON complaint_events (complaint_id)
                                                      INCLUDE (company_response)
                                                      WHERE event_type = 'responded';

-- VACUUM marks pages "all visible" — without that, an Index ONLY Scan still visits the table.
-- ANALYZE refreshes the planner's statistics after the bulk load.
VACUUM (ANALYZE) fact_complaint;
VACUUM (ANALYZE) complaint_events;
VACUUM (ANALYZE) complaint_narrative;

-- CHECKS
-- 1. the indexes and their sizes
SELECT indexrelname AS index_name, relname AS on_table,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM   pg_stat_user_indexes
WHERE  relname IN ('fact_complaint', 'complaint_events', 'complaint_narrative')
ORDER  BY relname, indexrelname;

-- 2. the API's lookup — one company x issue, everything before a date. Expect an Index Only Scan
--    on ix_fact_company_issue_date. The pair is picked automatically — a TYPICAL one (~1,000
--    complaints) — so the check never depends on a name or an id value. The first part of the plan
--    (finding the pair) scans the whole table; that's expected. The lookup is the part that matters.
EXPLAIN (ANALYZE, COSTS OFF)
WITH typical_pair AS (
    SELECT company_id, issue_id
    FROM   fact_complaint
    GROUP  BY company_id, issue_id
    ORDER  BY abs(count(*) - 1000)
    LIMIT  1
)
SELECT count(*)
FROM   fact_complaint f
JOIN   typical_pair  t USING (company_id, issue_id)
WHERE  f.date_received < DATE '2024-01-01';

-- 3. the label for one complaint. Expect an Index Only Scan on ix_events_responded.
EXPLAIN (ANALYZE, COSTS OFF)
SELECT company_response
FROM   complaint_events
WHERE  event_type = 'responded'
AND    complaint_id = (SELECT min(complaint_id) FROM fact_complaint);
