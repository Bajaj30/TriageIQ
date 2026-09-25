-- ============================================================
-- 02_load/06_indexes.sql          (DDL — run AFTER all loads in this folder)
-- PURPOSE : indexes for the feature pipeline's hot paths
-- WHY LAST: building an index once over loaded data is far faster than updating it
--           on every one of 4.8M inserts.
-- ============================================================
-- Window functions PARTITION BY an entity and ORDER BY date: index exactly that shape.
CREATE INDEX IF NOT EXISTS ix_fact_company_date   ON fact_complaint (company_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_issue_date     ON fact_complaint (issue_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_product_date   ON fact_complaint (product_id, date_received);
CREATE INDEX IF NOT EXISTS ix_fact_date           ON fact_complaint (date_received);
CREATE INDEX IF NOT EXISTS ix_events_type         ON complaint_events (event_type, complaint_id);

ANALYZE fact_complaint;          -- refresh planner statistics after the bulk load
ANALYZE complaint_events;
ANALYZE complaint_narrative;
