# sql/ — the whole pipeline, run folder by folder in number order (pgAdmin, database `triageiq`, port 5433)

- `00_staging/` — raw CSV copied into Postgres untouched.
- `01_schema/` — CREATE TABLE statements for the modelled tables (structure only, no data).
- `02_load/` — fills the modelled tables from staging, one table per file.
- `03_features/` — point-in-time features over all 4.8M complaints (not started).
- `04_training_set/` — filters features down to train / val / test (not started).
- `05_export/` — snapshot of the training set to Parquet for Kaggle (not started).
- `tests/` — hand-verified checks of the window-function features (not started).

Rules: re-run `01_schema/` as a whole, never one file (CASCADE drops). Never rely on an id value.
