# 01_schema — table structures only (no data); all constraint-tested

- `01_dimensions.sql` — creates the 6 dimension tables (company, state, product, sub-product, issue, sub-issue). ✅
- `02_product_crosswalk.sql` — creates the product mapping table and seeds its 12 rename/split rules. ✅
- `03_fact_complaint.sql` — creates the fact table: one row per complaint, ids only. ✅
- `04_complaint_narrative.sql` — creates the table holding complaint text, split out from the fact. ✅
- `05_complaint_events.sql` — creates the event log (received / sent / responded) where the label lives. ✅
- `07_narrative_columns.sql` — adds stored `n_real_words` and `text_hash` to `complaint_narrative` (+ index); re-runnable. ✅
- `08_narrative_amounts.sql` — function `max_claimed_amount()` + stored `n_amounts`, `max_amount` on `complaint_narrative`; 5/5 examples, 314,072 with an amount. ✅
- `06_issue_crosswalk.sql` — creates the issue mapping table and seeds its 1 rename rule (D17). ✅
