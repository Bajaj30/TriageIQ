# sql/ — run order

Every file is plain SQL: open it in pgAdmin's Query Tool on the `triageiq` database
(server `localhost:5433`) and run it. Folders and files run in number order.

| folder | what | status |
|---|---|---|
| `00_staging/` | CSV → `stg_complaints_raw`, untouched | next |
| `01_schema/` | CREATE TABLE for the modelled layer | designed (`Context/schema_explanation.md`) |
| `02_load/` | staging → modelled tables | |
| `03_features/` | Stage 1 — features over all 4.8M rows | not designed |
| `04_training_set/` | Stage 2 — the funnel down to train/val/test | |
| `05_export/` | snapshot to Parquet | |
| `tests/` | hand-verified feature checks | |

**Rule:** check the row count after every step.
