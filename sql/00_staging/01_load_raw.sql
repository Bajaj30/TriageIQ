-- ============================================================
-- 00_staging/01_load_raw.sql
-- PURPOSE : copy the CSV into Postgres exactly as-is. No cleaning, no filtering.
-- INPUT   : /import/complaints.csv  (path INSIDE the container = Data/complaints.csv on your Mac)
-- OUTPUT  : table stg_complaints_raw
-- GRAIN   : one row per CSV row
-- EXPECT  : 17,355,295 rows, 16 columns, every column TEXT
-- NOTES   : COPY matches columns by POSITION, so column order must match the CSV header.
--           Runs several minutes. Re-runnable: the table is dropped and rebuilt.
-- ============================================================

-- Why every column is TEXT: one malformed date typed as DATE would abort the whole
-- 9.2 GB load at row 14 million. Load raw; convert types later where bad rows are visible.
DROP TABLE IF EXISTS stg_complaints_raw;

CREATE TABLE stg_complaints_raw (
    date_received                  TEXT,   --  1
    product                        TEXT,   --  2
    sub_product                    TEXT,   --  3
    issue                          TEXT,   --  4
    sub_issue                      TEXT,   --  5
    consumer_complaint_narrative   TEXT,   --  6
    company_public_response        TEXT,   --  7  post-intake: never a feature
    company                        TEXT,   --  8
    state                          TEXT,   --  9
    zip_code                       TEXT,   -- 10  dropped from the model (19% redacted)
    tags                           TEXT,   -- 11
    submitted_via                  TEXT,   -- 12
    date_sent_to_company           TEXT,   -- 13  post-intake: never a feature
    company_response_to_consumer   TEXT,   -- 14  the LABEL source
    timely_response                TEXT,   -- 15  post-intake: never a feature
    complaint_id                   TEXT    -- 16
);

COPY stg_complaints_raw
FROM '/import/complaints.csv'
WITH (FORMAT csv, HEADER true);

-- sanity: expect 17,355,295
SELECT count(*) AS rows_loaded FROM stg_complaints_raw;
