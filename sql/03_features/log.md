# 03_features — point-in-time features over all 4,826,564 complaints, one row per complaint

Order: label → base → volume → outcome rates → smoothing → sequence → trends → assembly.
Each file builds one view; 08 stitches them into the materialized view the model reads.

- `01_label.sql` — view `v_label`: did the complaint pay (1/0) and was it untimely; Phase 0.5. ✅
- `02_base.sql` — view `v_base`: fact + label + 2 tag flags, one row per complaint, feature columns only. ✅
- `03_volume.sql` — view `v_volume`: how many complaints before today (frame B); 6 counts, test 22/22. ✅
  **Drift, decide in 08:** counts grow with calendar time (avg company all-time count, all complaints:
  2022 63,274 → 2024 751,264). `company_n_prior` mostly measures *how far into the data we are* — a clock.
  Candidates: drop it, or use ratios (company 30d ÷ 90d, company ÷ national) that don't grow with time.
- `04_outcome_rates.sql` — view `v_outcome_rates`: payout / untimely rates to date, 60-day lag (frame A); recount 21/21, leak test 3/3. ✅
  **Warm-up, decide in `04_training_set`:** 14.07% of 2022 complaints have no known company history
  (0.10% in 2023, 0.06% in 2024) — the first 60 days of data see no outcomes at all. Consider starting
  training rows later than 2022-01-01, or rely on the no-history flags.
- `05_smoothing.sql` — view `v_smoothed`: small-sample rates pulled toward the product's rate.
- `06_sequence.sql` — view `v_sequence`: gaps, ranks and tenure (frame C, deterministic tiebreak).
- `07_trends.sql` — view `v_trends`: last 90 days vs the 90 before.
- `08_assembly.sql` — materialized view `mv_features`: every feature, one row per complaint.
