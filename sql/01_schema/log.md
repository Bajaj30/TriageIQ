# 01_schema — table structures only (no data); all constraint-tested

- `01_dimensions.sql` — creates the 6 dimension tables (company, state, product, sub-product, issue, sub-issue). ✅
- `02_product_crosswalk.sql` — creates the product mapping table and seeds its 12 rename/split rules. ✅
- `03_fact_complaint.sql` — creates the fact table: one row per complaint, ids only. ✅
- `04_complaint_narrative.sql` — creates the table holding complaint text, split out from the fact. ✅
- `05_complaint_events.sql` — creates the event log (received / sent / responded) where the label lives. ✅
