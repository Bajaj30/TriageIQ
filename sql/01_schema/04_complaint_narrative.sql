-- ============================================================
-- 01_schema/04_complaint_narrative.sql
-- PURPOSE : CREATE the narrative extension table — structure only
-- DESIGN  : same grain as the fact (one row per complaint), but only complaints WITH text (D1).
--           Split out because the feature pipeline never reads text.
-- EXPECT  (after load): 1,639,068 rows
-- ============================================================
DROP TABLE IF EXISTS complaint_narrative;

CREATE TABLE complaint_narrative (
    complaint_id  BIGINT PRIMARY KEY REFERENCES fact_complaint (complaint_id),
    narrative     TEXT   NOT NULL CHECK (btrim(narrative) <> ''),
    -- Derived by the database itself, so every query sees the same definition of "word count".
    n_words       INTEGER GENERATED ALWAYS AS
                  (coalesce(array_length(regexp_split_to_array(btrim(narrative), '\s+'), 1), 0)) STORED
);
