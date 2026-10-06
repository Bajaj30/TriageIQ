# sql/ — the whole pipeline, run folder by folder in number order (pgAdmin, database `triageiq`, port 5433)

- `00_staging/` — raw CSV copied into Postgres untouched.
- `01_schema/` — CREATE TABLE statements for the modelled tables (structure only, no data).
- `02_load/` — fills the modelled tables from staging, one table per file.
- `03_features/` — point-in-time features over all 4.8M complaints: label view → `mv_features` → `v_model_input` (19 inputs). ✅
- `04_training_set/` — `clean_narrative()` + the v3 funnel to train / val / test. ✅
- `05_export/` — view `v_training_export`, copied to Parquet for Kaggle. ✅
- `06_serving/` — schema `serving` for the live API (snapshot, `model_input()`, lists, demo complaints) → pg_dump. ✅
- `tests/` — hand recounts of every feature family, the leak test, and the train/serve skew test. ✅

Rules: re-run `01_schema/` as a whole, never one file (CASCADE drops). Never rely on an id value.
