-- ============================================================
-- 02_load/09_complaint_narrative.sql
-- TARGET  : complaint_narrative
-- READS   : stg_window, fact_complaint
-- EXPECT  : 1,639,068 (F2 — the complaints the AI can read)
-- CONCEPT : Extension table: same grain as the fact, only rows that have text.
-- ============================================================
-- STEPS
--  1. keep rows where btrim(narrative) is not empty
--  2. INSERT complaint_id::bigint, narrative — n_words fills itself

-- Checked first (F1): 3,187,496 NULL narratives, 0 blank-but-not-NULL, 1,639,068 with text.
-- The text is stored exactly as CFPB published it (XXXX redactions included); cleaning belongs
-- to the model's preprocessing, not to the database.

INSERT INTO complaint_narrative (complaint_id, narrative)   -- n_words is GENERATED: never inserted
SELECT complaint_id::bigint,
       consumer_complaint_narrative
FROM   stg_window
WHERE  btrim(consumer_complaint_narrative) <> ''   -- also drops NULLs: btrim(NULL) <> '' is NULL, not true
ON CONFLICT (complaint_id) DO NOTHING;

-- No join to fact_complaint needed: the FOREIGN KEY checks that every complaint_id exists there.

-- CHECKS
-- 1. expect 1,639,068.
SELECT count(*) AS narratives FROM complaint_narrative;

-- 2. share of complaints with text. Expect 33.96% (about 1 in 3).
SELECT round(100.0 * (SELECT count(*) FROM complaint_narrative)
                   / (SELECT count(*) FROM fact_complaint), 2) AS pct_with_text;

-- 3. length profile of the text the AI will read (words, not tokens).
SELECT min(n_words)                                            AS min_words,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY n_words)   AS median_words,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY n_words)   AS p99_words,
       max(n_words)                                            AS max_words
FROM   complaint_narrative;
