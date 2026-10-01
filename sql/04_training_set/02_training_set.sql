-- ============================================================
-- 04_training_set/02_training_set.sql
-- TARGET  : table training_pool (every eligible complaint + why it was kept or dropped)
--           table training_set  (the sampled train / val / test rows)       -- version v3
--           table training_manifest (the rules, the funnel, the recalibration offset)
-- READS   : fact_complaint, complaint_narrative, v_label
-- PROBLEM : "Which complaints does the model study, tune on, and get examined on?" — reproducible,
--           in SQL, with seed 42. Replaces the pandas build in Data/EDA.ipynb (v2).
-- ============================================================
-- RULES (decided; revisit after training)
--  1. text      : >= 20 real words (n_real_words)                     replaces min-words + <=30% blanks
--  2. warm-up   : date_received >= 2022-04-01                         Q1 2022 has no history (68.71%)
--  3. split     : train < 2023-10-01 · val 2023-10-01..2023-12-31 · test 2024        by DATE, never random
--  4. one text, one split : a text belongs to the split where it FIRST appeared (any date, any copy);
--                 later copies in later splits are dropped, never moved          CLAUDE.md trap 7
--  5. cap       : at most 25 copies of the same text            v2 dropped whole 26+ clusters — changed
--  6. sample    : train = ALL payouts + 3 non-payouts each (case-control) · val 80,000 · test 150,000
--                 at natural prevalence. Order = md5('42:' || complaint_id): same rows on every run.
-- ============================================================

DROP TABLE IF EXISTS training_set;
DROP TABLE IF EXISTS training_pool;
DROP TABLE IF EXISTS training_manifest;

-- ---------------------------------------------------------------- the pool: every candidate + flags
CREATE TABLE training_pool AS
WITH first_seen AS (            -- rule 4: where each TEXT first appeared — over ALL narratives
    SELECT n.text_hash, min(f.date_received) AS first_date
    FROM   complaint_narrative n JOIN fact_complaint f USING (complaint_id)
    GROUP  BY n.text_hash
),
cand AS (                       -- rules 1 + 2
    SELECT f.complaint_id, f.date_received, n.text_hash, l.paid,
           CASE WHEN f.date_received < DATE '2023-10-01' THEN 'train'          -- rule 3
                WHEN f.date_received < DATE '2024-01-01' THEN 'val'
                ELSE 'test' END AS split,
           CASE WHEN s.first_date < DATE '2023-10-01' THEN 'train'
                WHEN s.first_date < DATE '2024-01-01' THEN 'val'
                ELSE 'test' END AS first_split
    FROM   fact_complaint      f
    JOIN   complaint_narrative n USING (complaint_id)
    JOIN   v_label             l USING (complaint_id)
    JOIN   first_seen          s USING (text_hash)
    WHERE  f.date_received >= DATE '2022-04-01'
    AND    n.n_real_words  >= 20
)
SELECT c.*,
       (c.split = c.first_split) AS passes_one_split,                          -- rule 4
       row_number() OVER (PARTITION BY c.text_hash, (c.split = c.first_split)
                          ORDER BY md5('42:' || c.complaint_id)) AS copy_rank  -- rule 5 (<= 25)
FROM   cand c;

ALTER TABLE training_pool ADD PRIMARY KEY (complaint_id);

-- ---------------------------------------------------------------- the sample
CREATE TABLE training_set AS
WITH eligible AS (
    SELECT * FROM training_pool WHERE passes_one_split AND copy_rank <= 25
),
ranked AS (
    SELECT e.*,
           row_number() OVER (PARTITION BY e.split, e.paid ORDER BY md5('42:' || e.complaint_id)) AS r_by_class,
           row_number() OVER (PARTITION BY e.split         ORDER BY md5('42:' || e.complaint_id)) AS r_in_split,
           sum(e.paid) OVER (PARTITION BY e.split) AS split_payouts
    FROM   eligible e
)
SELECT complaint_id, split, paid, date_received, text_hash
FROM   ranked
WHERE  (split = 'train' AND (paid = 1 OR r_by_class <= 3 * split_payouts))   -- all payouts + 3x
   OR  (split = 'val'   AND r_in_split <= 80000)                             -- natural prevalence
   OR  (split = 'test'  AND r_in_split <= 150000);

ALTER TABLE training_set ADD PRIMARY KEY (complaint_id);

-- ---------------------------------------------------------------- the manifest: rules + funnel
CREATE TABLE training_manifest (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO training_manifest (key, value)
SELECT k, v FROM (
    SELECT 'version', 'v3' UNION ALL
    SELECT 'built_at', now()::text UNION ALL
    SELECT 'seed', '42' UNION ALL
    SELECT 'rules', 'real_words>=20; date>=2022-04-01; split train<2023-10-01, val<2024-01-01, test 2024; '
                 || 'one text one split (first appearance); cap 25 copies; train = all payouts + 3x; val 80k; test 150k' UNION ALL
    SELECT 'funnel.candidates',         (SELECT count(*) FROM training_pool)::text UNION ALL
    SELECT 'funnel.after_one_split',    (SELECT count(*) FROM training_pool WHERE passes_one_split)::text UNION ALL
    SELECT 'funnel.after_cap',          (SELECT count(*) FROM training_pool WHERE passes_one_split AND copy_rank <= 25)::text UNION ALL
    SELECT 'train.eligible_negatives',  (SELECT count(*) FROM training_pool
                                         WHERE split = 'train' AND paid = 0 AND passes_one_split AND copy_rank <= 25)::text UNION ALL
    SELECT 'train.negative_keep_fraction',
           ((SELECT count(*) FROM training_set WHERE split = 'train' AND paid = 0)::numeric
           / (SELECT count(*) FROM training_pool
              WHERE split = 'train' AND paid = 0 AND passes_one_split AND copy_rank <= 25))::text
) x (k, v);
INSERT INTO training_manifest (key, value)
SELECT 'recalibration_logit_offset', ln(value::numeric)::text
FROM   training_manifest WHERE key = 'train.negative_keep_fraction';

-- CHECKS
-- 1. the split table. Expect: train ~25% payouts (exactly 1 in 4), val/test at natural prevalence.
SELECT split, count(*) AS rows, sum(paid) AS payouts, round(100.0 * avg(paid), 2) AS payout_pct,
       min(date_received) AS first_day, max(date_received) AS last_day
FROM   training_set GROUP BY split ORDER BY min(date_received);

-- 2. the rules hold. Expect every column 0.
SELECT count(*) FILTER (WHERE t.date_received < DATE '2022-04-01')               AS before_warmup_cut,
       (SELECT count(*) FROM (SELECT text_hash FROM training_set
                              GROUP BY text_hash HAVING count(DISTINCT split) > 1) x) AS texts_in_two_splits,
       (SELECT count(*) FROM (SELECT text_hash FROM training_set
                              GROUP BY text_hash HAVING count(*) > 25) x)        AS texts_over_25_copies,
       count(*) FILTER (WHERE n.n_real_words < 20)                               AS under_20_real_words
FROM   training_set t JOIN complaint_narrative n USING (complaint_id);

-- 3. the manifest.
SELECT key, value FROM training_manifest ORDER BY key;
