-- ============================================================
-- 04_training_set/01_clean_narrative.sql
-- TARGET  : function clean_narrative(text) -> text
-- PURPOSE : collapse CFPB's privacy blanks into ONE short marker each, before the text reaches the model.
--           The training export AND the API call this same function, so train and serve can't drift
--           (CLAUDE.md §9, step 1). Keeps meaning: WHERE blanks are stays visible; their bulk goes.
-- RULES   : 1. dates  XX/XX/XXXX · XX/XX/XX · XX/XX/2019 · XX/XX      ->  [DATE]
--           2. a run of blanks  XXXX · XXXX XXXX · XX                 ->  [REDACTED]   (one per run)
--           3. whitespace collapsed to single spaces, ends trimmed
-- PHASE 2 : register '[DATE]' and '[REDACTED]' as SPECIAL tokens in the tokenizer. As plain text,
--           '[REDACTED]' is 5 word-pieces (more than 'XXXX' = 2) — measured 2026-10-01.
-- MEASURED: heavy-blank texts (>= 30% blanks) median 238 -> 109 tokens; over 512: 12.1% -> 3.6%.
-- ============================================================
CREATE OR REPLACE FUNCTION clean_narrative(t TEXT) RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT btrim(regexp_replace(
               regexp_replace(
                   regexp_replace(t, '\yX{2,}/X{2,}(?:/(?:X{2,}|[0-9]{2,4}))?\y', ' [DATE] ', 'g'),  -- rule 1
                   '\yX{2,}\y(?:\s*\yX{2,}\y)*', ' [REDACTED] ', 'g'),                               -- rule 2
               '\s+', ' ', 'g'))                                                                    -- rule 3
$$;
-- IMMUTABLE: same input -> same output, always. Lets Postgres use it in indexes and parallel plans.

-- CHECKS
-- 1. the rules on hand-made examples. Expect every row PASS.
SELECT input, clean_narrative(input) AS output,
       CASE WHEN clean_narrative(input) = expected THEN 'PASS' ELSE '** FAIL **' END AS result
FROM (VALUES
    ('On XX/XX/XXXX I called',                 'On [DATE] I called'),
    ('On XX/XX/2019 I called',                 'On [DATE] I called'),
    ('account XXXX XXXX XXXX was closed',      'account [REDACTED] was closed'),
    ('Mr. XXXX at XXXX bank',                  'Mr. [REDACTED] at [REDACTED] bank'),
    ('I paid  $500   to   them',               'I paid $500 to them'),           -- spaces only
    ('EXXON and XYZ are not blanks',           'EXXON and XYZ are not blanks')   -- X inside words stays
) AS t (input, expected);

-- 2. on real data: tokens are not counted here, but WORDS are — expect fewer words after cleaning.
SELECT round(avg(array_length(regexp_split_to_array(btrim(narrative), '\s+'), 1)))                   AS avg_words_before,
       round(avg(array_length(regexp_split_to_array(clean_narrative(narrative), '\s+'), 1)))         AS avg_words_after
FROM   (SELECT narrative FROM complaint_narrative ORDER BY md5(complaint_id::text) LIMIT 20000) s;
