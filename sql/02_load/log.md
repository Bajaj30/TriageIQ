# 02_load — fills the modelled tables from staging, one table per file

- `00_expected_facts.sql` — **generated** by `training/canonical_facts.py`: table `expected_facts` (144 numbers) + function `expected()`. Never hand-edit. ✅
- `01_views.sql` — creates views `stg_window` (2022–24 rows only) and `stg_canonical` (adds the crosswalked product and issue). ✅
- `02_dim_state.sql` — inserts the 62 states into `dim_state`. ✅
- `03_dim_company.sql` — inserts companies into `dim_company`, merging case-only duplicates. ✅
- `04_dim_issue.sql` — inserts the 93 canonical issues into `dim_issue`. ✅
- `05_dim_product.sql` — inserts the 11 canonical products into `dim_product`. ✅
- `06_dim_sub_issue.sql` — inserts the 293 (issue, sub-issue) pairs into `dim_sub_issue`. ✅
- `07_dim_sub_product.sql` — inserts the 62 (product, sub-product) pairs into `dim_sub_product`. ✅
- `08_fact_complaint.sql` — inserts all 4,826,564 complaints into `fact_complaint`, with names swapped for ids. ✅
- `09_complaint_narrative.sql` — inserts the 1,639,068 complaint texts into `complaint_narrative`. ✅
- `10_complaint_events.sql` — inserts the 3 events per complaint (14,479,692 rows) into `complaint_events`. ✅
- `11_validate.sql` — one grid of 21 cross-table checks; expected values come from `expected()` (FACTS), all PASS. ✅
- `12_indexes.sql` — builds 6 indexes (incl. company×issue×date and a covering 'responded' index), then VACUUM ANALYZE; runs last. ✅
