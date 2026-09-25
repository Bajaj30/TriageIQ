# 02_load — fills the modelled tables from staging, one table per file

- `01_views.sql` — creates views `stg_window` (2022–24 rows only) and `stg_canonical` (adds the crosswalked product). ✅
- `02_dim_state.sql` — inserts the 62 states into `dim_state`. ✅
- `03_dim_company.sql` — inserts companies into `dim_company`, merging case-only duplicates.
- `04_dim_issue.sql` — inserts issues into `dim_issue`.
- `05_dim_product.sql` — inserts the 11 canonical products into `dim_product`.
- `06_dim_sub_issue.sql` — inserts (issue, sub-issue) pairs into `dim_sub_issue`.
- `07_dim_sub_product.sql` — inserts (product, sub-product) pairs into `dim_sub_product`.
- `08_fact_complaint.sql` — inserts every complaint into `fact_complaint`, with names swapped for ids.
- `09_complaint_narrative.sql` — inserts complaint text into `complaint_narrative`.
- `10_complaint_events.sql` — inserts the 3 events per complaint into `complaint_events`.
- `11_validate.sql` — checks every count before moving on.
- `12_indexes.sql` — creates the indexes; runs last.
