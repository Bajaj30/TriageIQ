# 00_staging — the raw CSV inside Postgres, exactly as downloaded

- `01_load_raw.sql` — creates `stg_complaints_raw` (16 TEXT columns) and COPYs all 17,355,295 CSV rows into it. ✅
- `02_validate_raw.sql` — checks the raw load is complete before anything is built on it.
