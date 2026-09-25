-- ============================================================
-- 01_schema/05_complaint_events.sql
-- PURPOSE : CREATE the append-only event log — structure only
-- DESIGN  : one row per EVENT, 2-3 per complaint — a DIFFERENT grain from the fact (D2).
--           Aggregate before joining to the fact, or the grain breaks.
--           The LABEL lives here: event_type 'responded', company_response = 'Closed with monetary relief'.
-- FINDING : CFPB records when a complaint was received and sent — NOT when the company responded.
--           So 'responded' has no date (event_date NULL). This is why the 60-day outcome lag in
--           TriageIQ.md §1.4a is an ASSUMPTION, not a measurement.
-- EXPECT  (after load): 4,826,564 x 3 = 14,479,692 rows
-- ============================================================
DROP TABLE IF EXISTS complaint_events;

CREATE TABLE complaint_events (
    event_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    complaint_id      BIGINT NOT NULL REFERENCES fact_complaint (complaint_id),
    event_type        TEXT   NOT NULL CHECK (event_type IN ('received', 'sent_to_company', 'responded')),
    event_date        DATE,                     -- NULL only for 'responded' (timing unknown)
    company_response  TEXT,                     -- 'responded' only. NULL response = UNKNOWN, not negative
    timely_response   TEXT,                     -- 'responded' only
    public_response   TEXT,                     -- 'responded' only
    UNIQUE (complaint_id, event_type),          -- each event happens at most once per complaint
    CHECK (event_type =  'responded' OR event_date IS NOT NULL),
    CHECK (event_type =  'responded' OR (company_response IS NULL AND timely_response IS NULL
                                         AND public_response IS NULL))
);
