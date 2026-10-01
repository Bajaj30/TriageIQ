-- ============================================================
-- 01_schema/07_narrative_columns.sql          (DDL — run after 02_load/09_complaint_narrative.sql)
-- PURPOSE : two values per narrative that the training set needs, computed ONCE by the database
-- DESIGN  : GENERATED ... STORED columns, like n_words: the database fills them for every row (and
--           for every future row), so no query ever re-implements them.
--           ADD COLUMN IF NOT EXISTS: re-runnable; on a fresh build it can run before or after the load.
-- COST    : adding a stored column rewrites the 1.6M-row table once (~5 min: two regex passes).
-- ============================================================
ALTER TABLE complaint_narrative
    -- real words: runs of letters, minus the privacy blanks (XX, XXXX ...). Numbers and punctuation
    -- never count. Decided 2026-10-01: a training text needs >= 20 real words (replaces the old
    -- "20 words incl. blanks" + "<= 30% blanks" rules — measured: 1,553,638 kept vs 1,444,945).
    ADD COLUMN IF NOT EXISTS n_real_words INTEGER GENERATED ALWAYS AS
        (regexp_count(narrative, '\y[A-Za-z]+\y') - regexp_count(narrative, '\yX{2,}\y')) STORED,
    -- the text's fingerprint: same normalization as Data/EDA.ipynb (lowercase, trim, collapse
    -- whitespace, then md5). Identical texts get identical hashes — duplicate clusters and the
    -- group-aware split (CLAUDE.md trap 7) are built on it.
    ADD COLUMN IF NOT EXISTS text_hash TEXT GENERATED ALWAYS AS
        (md5(regexp_replace(lower(btrim(narrative)), '\s+', ' ', 'g'))) STORED;

CREATE INDEX IF NOT EXISTS ix_narrative_text_hash ON complaint_narrative (text_hash);
ANALYZE complaint_narrative;

-- CHECKS
-- 1. expect 1,639,068 rows, 0 NULLs; with_20_real_words = 1,553,638 (the measured count)
SELECT count(*)                                   AS narratives,
       count(*) FILTER (WHERE n_real_words IS NULL OR text_hash IS NULL) AS nulls,
       count(*) FILTER (WHERE n_real_words >= 20) AS with_20_real_words,
       count(DISTINCT text_hash)                  AS distinct_texts
FROM   complaint_narrative;
