# 05_export — writes the training set to Parquet for Kaggle

- `01_training_export.sql` — view `v_training_export`: training_set + cleaned text + the 19 inputs + eval-only date/company; 292,940 rows, 0 NULLs. ✅
- Copied to Parquet by `training/export_training_set.py` (rows only, no logic) → `Data/data/interim/triageiq_training_v3.parquet` (155 MB) + manifest (sha256, roles, offset −2.4165).
