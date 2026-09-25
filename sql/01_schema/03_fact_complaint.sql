-- ============================================================
-- 01_schema/03_fact_complaint.sql
-- PURPOSE : CREATE the fact table — structure only, no data
-- DESIGN  : one row per complaint, ALL of F1 incl. no-narrative rows (D10)
--           date_received here as the point-in-time anchor (D3)
--           product_id AND sub_product_id, issue_id AND sub_issue_id (D11 — hot path)
--           NO outcome columns here — the label lives in complaint_events (D2)
-- REF     : Context/schema_explanation.md
-- EXPECT  (after load): 4,826,564 rows
-- ============================================================
DROP TABLE IF EXISTS fact_complaint CASCADE;

CREATE TABLE fact_complaint (
    complaint_id    BIGINT  PRIMARY KEY,               -- BIGINT: text sort != numeric sort
    date_received   DATE    NOT NULL,                  -- DATE not TIMESTAMPTZ: source has no time of day;
                                                       -- a timestamp would invent midnight
    company_id      INTEGER NOT NULL REFERENCES dim_company (company_id),
    state_id        INTEGER NOT NULL REFERENCES dim_state (state_id),
    product_id      INTEGER NOT NULL,
    sub_product_id  INTEGER NOT NULL,
    issue_id        INTEGER NOT NULL,
    sub_issue_id    INTEGER NOT NULL,
    raw_product     TEXT    NOT NULL,                  -- pre-crosswalk name, kept for traceability (D8)
    submitted_via   TEXT    NOT NULL,                  -- OPEN decision: 5 values in F1, 1 in F2
    tags            TEXT,                              -- OPEN decision: 94.5% NULL in F1

    -- Composite FKs: storing product_id beside sub_product_id is denormalised (D11), so the
    -- database must PROVE they agree — a sub-product can only sit with its own parent.
    FOREIGN KEY (sub_product_id, product_id) REFERENCES dim_sub_product (sub_product_id, product_id),
    FOREIGN KEY (sub_issue_id,   issue_id)   REFERENCES dim_sub_issue   (sub_issue_id,   issue_id),

    CHECK (date_received BETWEEN DATE '2022-01-01' AND DATE '2024-12-31')   -- the working window
);
