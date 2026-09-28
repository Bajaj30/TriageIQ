-- ============================================================
-- 02_load/10_complaint_events.sql
-- TARGET  : complaint_events
-- READS   : stg_window, fact_complaint
-- EXPECT  : 4,826,564 per event type · 14,479,692 total
-- CONCEPT : Event log: one complaint becomes three rows. A different grain from the fact.
-- ============================================================
-- STEPS
--  1. 'received'        — event_date = date_received::date
--  2. 'sent_to_company' — event_date = date_sent_to_company::date
--  3. 'responded'       — event_date NULL; company_response, timely_response, public_response
--     keep NULL responses as NULL (19 rows): unknown is not negative

-- Checked first (F1): 0 missing sent dates, 0 sent before received (the CHECKs would reject them).
-- Outcomes: explanation 2,588,007 · non-monetary 2,174,801 · MONETARY 60,952 · untimely 2,785 · NULL 19.

-- UNPIVOT with CROSS JOIN LATERAL (VALUES ...): each staging row is read ONCE and turned into
-- 3 rows. Three separate INSERTs (or a UNION ALL) would scan the 17M-row staging table 3 times.
INSERT INTO complaint_events (complaint_id, event_type, event_date,
                              company_response, timely_response, public_response)
SELECT w.complaint_id::bigint,
       e.event_type, e.event_date,
       e.company_response, e.timely_response, e.public_response
FROM   stg_window w
CROSS  JOIN LATERAL (VALUES
       --  event_type        event_date                     outcome columns: 'responded' only
       ('received',        w.date_received::date,         NULL, NULL, NULL),
       ('sent_to_company', w.date_sent_to_company::date,  NULL, NULL, NULL),
       ('responded',       NULL::date,                    -- CFPB never records WHEN (D15)
                           w.company_response_to_consumer,
                           w.timely_response,
                           w.company_public_response)
) AS e (event_type, event_date, company_response, timely_response, public_response)
ON CONFLICT (complaint_id, event_type) DO NOTHING;

-- Note: a re-run inserts 0 rows but still burns 14.5M event_id values — ON CONFLICT draws the id
-- before it detects the conflict. Harmless (BIGINT), and one more reason never to rely on an id value.

-- CHECKS
-- 1. expect 3 rows of 4,826,564 each. Uneven = some complaint lost an event.
SELECT event_type, count(*) AS events FROM complaint_events GROUP BY 1 ORDER BY 1;

-- 2. THE LABEL. Expect 60,952 monetary relief · 19 NULL (unknown — to be EXCLUDED by the label view).
SELECT coalesce(company_response, '(NULL = unknown)') AS outcome, count(*)
FROM   complaint_events
WHERE  event_type = 'responded'
GROUP  BY 1 ORDER BY 2 DESC;

-- 3. positives among complaints WITH text (F2). Expect 35,375 — matches FACTS.md.
SELECT count(*) AS f2_positives
FROM   complaint_events    e
JOIN   complaint_narrative n USING (complaint_id)
WHERE  e.event_type = 'responded'
AND    e.company_response = 'Closed with monetary relief';

-- 4. days from received to sent — a POST-intake fact (never a feature), shown for context.
SELECT percentile_cont(0.5)  WITHIN GROUP (ORDER BY s.event_date - r.event_date) AS median_days,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY s.event_date - r.event_date) AS p99_days,
       max(s.event_date - r.event_date)                                           AS max_days
FROM   complaint_events r
JOIN   complaint_events s ON s.complaint_id = r.complaint_id AND s.event_type = 'sent_to_company'
WHERE  r.event_type = 'received';
