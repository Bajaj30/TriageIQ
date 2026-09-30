-- ============================================================
-- 02_load/11_validate.sql
-- TARGET  : (checks only — changes nothing)
-- READS   : every loaded table + expected_facts (00_expected_facts.sql — run it first)
-- EXPECT  : one grid, every row PASS, last row "ALL CHECKS" = PASS — before indexing
-- CONCEPT : Trust nothing until counted. Each earlier file checked ITSELF; this checks them TOGETHER.
-- ============================================================
-- STEPS
--  1. counts: fact 4,826,564 · narrative 1,639,068 · events 14,479,692
--  2. grain: count(*) = count(DISTINCT complaint_id) on fact and narrative
--  3. every complaint has exactly 3 events
--  4. positives: responded + 'Closed with monetary relief' = 60,952
--  5. re-routed: fact rows where raw_product <> canonical name = 1,334,958

-- Three kinds of expected value, on purpose:
--  * expected('key')  — a fact from training/canonical_facts.json, computed by a SEPARATE pandas
--                       pipeline. Same numbers as Context/FACTS.md, so the two can never disagree.
--  * a subquery       — compares two stages of the load (staging vs fact): catches lost rows.
--  * a literal 0      — a rule that must always hold (no duplicates, 3 events each), not a fact.
-- The CTE is used twice (grid + summary), so Postgres runs each count ONCE and reuses it.

WITH checks (n, check_name, expected, actual) AS (
    -- 1. row counts -----------------------------------------------------------
              SELECT  1, 'fact_complaint rows (F1)',         expected('F1.rows'), (SELECT count(*) FROM fact_complaint)
    UNION ALL SELECT  2, 'complaint_narrative rows (F2)',    expected('F2.rows'), (SELECT count(*) FROM complaint_narrative)
    UNION ALL SELECT  3, 'complaint_events rows (3 x F1)',   expected('load.events'), (SELECT count(*) FROM complaint_events)
    UNION ALL SELECT  4, 'fact = window in staging',         (SELECT count(*) FROM stg_window),
                                                             (SELECT count(*) FROM fact_complaint)
    -- 2. grain: one row per complaint (the primary keys guarantee it — counted anyway) ------
    UNION ALL SELECT  5, 'fact: duplicate complaint_ids',    0,
                         (SELECT count(*) - count(DISTINCT complaint_id) FROM fact_complaint)
    UNION ALL SELECT  6, 'narrative: duplicate complaint_ids', 0,
                         (SELECT count(*) - count(DISTINCT complaint_id) FROM complaint_narrative)
    -- 3. every complaint has exactly 3 events (aggregate events first, THEN join — no fan-out) --
    UNION ALL SELECT  7, 'complaints without exactly 3 events', 0,
                         (SELECT count(*)
                          FROM   fact_complaint f
                          LEFT   JOIN (SELECT complaint_id, count(*) AS n_events
                                       FROM complaint_events GROUP BY complaint_id) e USING (complaint_id)
                          WHERE  coalesce(e.n_events, 0) <> 3)
    UNION ALL SELECT  8, 'sent_to_company before received',  0,
                         (SELECT count(*)
                          FROM   complaint_events r
                          JOIN   complaint_events s ON s.complaint_id = r.complaint_id
                                                   AND s.event_type = 'sent_to_company'
                          WHERE  r.event_type = 'received' AND s.event_date < r.event_date)
    -- 4. the label ------------------------------------------------------------
    UNION ALL SELECT  9, 'positives: monetary relief (F1)',  expected('F1.positives'),
                         (SELECT count(*) FROM complaint_events
                          WHERE  event_type = 'responded' AND company_response = 'Closed with monetary relief')
    UNION ALL SELECT 10, 'positives with a narrative (F2)',  expected('F2.positives'),
                         (SELECT count(*) FROM complaint_events e JOIN complaint_narrative USING (complaint_id)
                          WHERE  e.event_type = 'responded' AND e.company_response = 'Closed with monetary relief')
    UNION ALL SELECT 11, 'label matches staging',            (SELECT count(*) FROM stg_window
                                                              WHERE company_response_to_consumer = 'Closed with monetary relief'),
                         (SELECT count(*) FROM complaint_events
                          WHERE  event_type = 'responded' AND company_response = 'Closed with monetary relief')
    UNION ALL SELECT 12, 'NULL outcomes (label 0)',          expected('schema.null_response_F1'),
                         (SELECT count(*) FROM complaint_events
                          WHERE  event_type = 'responded' AND company_response IS NULL)
    UNION ALL SELECT 13, 'Untimely response (label 0)',      expected('load.untimely'),
                         (SELECT count(*) FROM complaint_events
                          WHERE  event_type = 'responded' AND company_response = 'Untimely response')
    -- 5. the crosswalks survived into the fact ---------------------------------------------
    UNION ALL SELECT 14, 'products re-routed (D12)',         expected('load.products_rerouted'),
                         (SELECT count(*) FROM fact_complaint f JOIN dim_product p USING (product_id)
                          WHERE  f.raw_product <> p.product_name)
    UNION ALL SELECT 15, 'issues re-routed (D17)',           expected('load.issues_rerouted'),
                         (SELECT count(*) FROM fact_complaint f JOIN dim_issue i USING (issue_id)
                          WHERE  f.raw_issue <> i.issue_name)
    -- 6. dimension sizes -----------------------------------------------------------------
    UNION ALL SELECT 16, 'dim_company',       expected('load.dim_company'), (SELECT count(*) FROM dim_company)
    UNION ALL SELECT 17, 'dim_state',         expected('load.dim_state'), (SELECT count(*) FROM dim_state)
    UNION ALL SELECT 18, 'dim_product',       expected('load.dim_product'), (SELECT count(*) FROM dim_product)
    UNION ALL SELECT 19, 'dim_sub_product',   expected('load.dim_sub_product'), (SELECT count(*) FROM dim_sub_product)
    UNION ALL SELECT 20, 'dim_issue',         expected('load.dim_issue'), (SELECT count(*) FROM dim_issue)
    UNION ALL SELECT 21, 'dim_sub_issue',     expected('load.dim_sub_issue'), (SELECT count(*) FROM dim_sub_issue)
)
SELECT n, check_name, expected, actual,
       CASE WHEN actual = expected THEN 'PASS' ELSE '** FAIL **' END AS result
FROM   checks
UNION ALL
SELECT 99, 'ALL CHECKS', count(*), count(*) FILTER (WHERE actual = expected),   -- checks run / passed
       CASE WHEN bool_and(coalesce(actual = expected, false)) THEN 'PASS' ELSE '** FAIL **' END
       --        coalesce: a missing expected value (NULL) must FAIL; bool_and alone would skip it
FROM   checks
ORDER  BY n;
