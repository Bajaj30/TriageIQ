-- ============================================================
-- 01_schema/08_narrative_amounts.sql          (DDL — run after 07_narrative_columns.sql)
-- PURPOSE : the dollar amounts a consumer writes in the complaint, computed ONCE by the database
-- WHY     : 19.2% of narratives mention an amount; they pay out 7.10% vs 0.99% and hold 63% of all
--           payouts (complaints with text, measured 2026-10-02). Known at intake — it's in the complaint.
-- FORMAT  : CFPB writes amounts as {$760.00} or {$1,500.00}; redacted ones never appear as {$XXXX}.
-- DESIGN  : GENERATED ... STORED columns (like n_words, n_real_words). The max needs a set-returning
--           regex, which a generated column can't hold directly — so it lives in an IMMUTABLE function.
-- COST    : rewrites the 1.6M-row table once (~2-4 min). Re-runnable (IF NOT EXISTS).
-- ============================================================
CREATE OR REPLACE FUNCTION max_claimed_amount(t TEXT) RETURNS NUMERIC
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT max(replace(m[1], ',', '')::numeric)                        -- '1,500.00' -> 1500.00
    FROM   regexp_matches(t, '\{\$([0-9][0-9,]*(?:\.[0-9]+)?)\}', 'g') AS m
$$;
-- NULL when the text mentions no amount (max over zero rows).

ALTER TABLE complaint_narrative
    ADD COLUMN IF NOT EXISTS n_amounts  INTEGER GENERATED ALWAYS AS (regexp_count(narrative, '\{\$[0-9]')) STORED,
    ADD COLUMN IF NOT EXISTS max_amount NUMERIC GENERATED ALWAYS AS (max_claimed_amount(narrative)) STORED;
ANALYZE complaint_narrative;

-- CHECKS
-- 1. the function on hand-made examples. Expect every row PASS.
SELECT input, max_claimed_amount(input) AS got,
       CASE WHEN max_claimed_amount(input) IS NOT DISTINCT FROM expected THEN 'PASS' ELSE '** FAIL **' END AS result
FROM (VALUES
    ('charged {$40.00} twice',                 40.00::numeric),
    ('paid {$1,500.00} then {$760.00}',        1500.00),
    ('a fee of {$2.00}',                       2.00),
    ('no amount here',                         NULL),
    ('dollars without braces $500',            NULL)            -- only CFPB's {$...} format counts
) AS t (input, expected);

-- 2. coverage. Expect with_amount = 314,072 (19.2% of 1,639,068 — the measured count); 0 negative.
SELECT count(*) FILTER (WHERE n_amounts > 0)           AS with_amount,
       round(100.0 * avg((n_amounts > 0)::int), 1)       AS pct_with_amount,
       count(*) FILTER (WHERE max_amount < 0)            AS negative,
       count(*) FILTER (WHERE n_amounts > 0 AND max_amount IS NULL) AS count_without_max
FROM   complaint_narrative;

-- 3. signal: payout rate by the largest amount mentioned (complaints with text, all years).
SELECT CASE WHEN max_amount IS NULL   THEN '0: none'
            WHEN max_amount < 100     THEN '1: under $100'
            WHEN max_amount < 1000    THEN '2: $100-999'
            WHEN max_amount < 10000   THEN '3: $1k-9,999'
            ELSE                           '4: $10k+' END      AS largest_amount,
       count(*)                                                AS complaints,
       round(100.0 * avg(l.paid), 2)                           AS payout_pct
FROM   complaint_narrative n JOIN v_label l USING (complaint_id)
GROUP  BY 1 ORDER BY 1;
