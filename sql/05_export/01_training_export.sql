-- ============================================================
-- 05_export/01_training_export.sql
-- TARGET  : view v_training_export — exactly what goes to Kaggle, one row per training complaint
-- READS   : training_set, v_model_input, mv_features, complaint_narrative, clean_narrative()
-- EXPECT  : 292,940 rows (train 62,940 · val 80,000 · test 150,000) · 0 NULLs anywhere
-- PROBLEM : "Hand the GPU everything it needs and nothing it shouldn't."
-- ============================================================
-- Column roles (the export script writes them into the manifest):
--   split, paid           — which part, and the answer
--   text                  — clean_narrative(narrative): blanks collapsed (DistilBERT reads this)
--   19 inputs             — straight from v_model_input (the model's list lives there, nowhere else)
--   EVAL-ONLY             — date_received, company_id: for the honest within-company scores and slices.
--                           Never model inputs (feature_dictionary.md).
-- The Python side (training/export_training_set.py) only copies these rows to Parquet.

CREATE OR REPLACE VIEW v_training_export AS
SELECT t.complaint_id,
       t.split,
       t.paid,
       clean_narrative(n.narrative)      AS text,
       i.product_id, i.sub_product_id, i.issue_id, i.state_id,
       i.is_older_american, i.is_servicemember, i.company_no_history, i.company_issue_no_history,
       i.company_issue_rate_s, i.company_rate_s, i.issue_rate_s, i.product_rate_s, i.company_untimely_rate,
       i.company_share_90d, i.company_issue_share_90d, i.issue_share_90d, i.company_trend_90d, i.issue_trend_90d,
       i.company_quiet_days,
       m.date_received,                  -- eval-only
       m.company_id                      -- eval-only
FROM   training_set        t
JOIN   v_model_input       i USING (complaint_id)
JOIN   mv_features         m USING (complaint_id)
JOIN   complaint_narrative n USING (complaint_id);

-- CHECKS
-- 1. rows per split and NULLs. Expect 62,940 / 80,000 / 150,000 and rows_with_null = 0
--    (the only NULLs in the inputs are on 2022-01-01, before the warm-up cut).
SELECT split, count(*) AS rows, sum(paid) AS payouts,
       count(*) FILTER (WHERE num_nulls(text, product_id, sub_product_id, issue_id, state_id,
                           is_older_american, is_servicemember, company_no_history, company_issue_no_history,
                           company_issue_rate_s, company_rate_s, issue_rate_s, product_rate_s,
                           company_untimely_rate, company_share_90d, company_issue_share_90d, issue_share_90d,
                           company_trend_90d, issue_trend_90d, company_quiet_days, date_received, company_id) > 0)
                                                                AS rows_with_null,
       round(avg(length(text)))                                 AS avg_text_chars
FROM   v_training_export GROUP BY split ORDER BY min(date_received);
