# 04_training_set — the funnel from all complaints down to train / val / test

- `01_clean_narrative.sql` — function `clean_narrative()`: blanks → `[DATE]` / `[REDACTED]`; export and API both use it; 6/6 rule tests. ✅
- `02_training_set.sql` — tables `training_pool`, `training_set` (v3: train 62,940 · val 80,000 · test 150,000), `training_manifest` (rules, funnel, offset −2.4165); seed 42; all rule checks 0. ✅
