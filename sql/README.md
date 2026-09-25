# sql/ — run order

Every file is plain SQL: open it in pgAdmin's Query Tool on the `triageiq` database
(server `localhost:5433`) and run it. Folders and files run in number order.

| folder | what | who writes it |
|---|---|---|
| `00_staging/` | CSV → `stg_complaints_raw`, untouched | DDL: Claude · validation: Shivam |
| `01_schema/` | CREATE TABLE for the modelled layer | **Claude — done and constraint-tested** |
| `02_load/` | staging → modelled tables (`06_indexes.sql` is DDL) | **Shivam** |
| `03_features/` | Stage 1 — features over all 4.8M rows | Shivam |
| `04_training_set/` | Stage 2 — the funnel down to train/val/test | Shivam |
| `05_export/` | snapshot to Parquet | |
| `tests/` | hand-verified feature checks | |

**Rule:** check the row count after every step.

**Re-run `01_schema/` as a whole, in order.** Its files drop tables with `CASCADE`, so re-running
`01_dimensions.sql` alone silently removes the fact table's foreign keys.

Identity ids never roll back — gaps in ids are normal. Never rely on an id value.
