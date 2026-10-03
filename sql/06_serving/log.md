# 06_serving — the small database the live API reads (schema `serving`, shipped with pg_dump)

- `01_snapshot.sql` — schema `serving`, 5 scoreboard tables (counts per product / issue / company / company×issue / national, "as of" a day) + procedure `build_serving_snapshot(date)`; live snapshot = 2025-01-01; builds in ~12 s; 4,946 companies · 31,378 pairs. ✅
- `02_features_fn.sql` — `serving.model_input(company, product, sub_product, issue, state, older, servicemember [, as_of])` → the 19 inputs in `v_model_input` order; ~0.06 ms; a new company (NULL) gets the product prior + no-history flags. ✅
- `03_serving_db.sql` — lists (dims), `serving.clean_narrative()` copied from public's definition (2,000/2,000 identical), `serving.test_complaints` (150,000 · 3,471 payouts); schema total 187 MB. ✅
- Ship: `docker exec triageiq-postgres pg_dump -U triageiq -d triageiq -n serving -Fc > training/outputs/serving_v3/serving_db.dump` → 57 MB; restored into an empty database and queried — stands alone. ✅
