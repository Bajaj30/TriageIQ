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
- `05a_choose_k.sql` — tuning: AUC + Brier of the smoothed rate for 12 values of K on Oct–Dec 2023; best K ≈ 5. ✅
- `05_smoothing.sql` — table `feature_params` (K = 5, 2021 fallback 2.86%) + view `v_smoothed`: every 04 column plus 4 smoothed rates, never NULL. ✅
- `06_sequence.sql` — view `v_sequence`: gaps, ranks and tenure (frame C, deterministic tiebreak); exact counts 4,946 / 50,827, test 22/22. ✅
  **Clocks, decide in 08:** `days_since_start` is the calendar itself, and `company_tenure_days` equals it for
  91.68% of complaints (111 companies present on 2022-01-01). Together with `company_n_prior` (03), these
  mostly tell the model *when*, not *what* — candidates to drop, or replace with a 'new company' flag.
  Gap signal is weak: same-day 1.18% payout (busy companies) vs 1.79–3.82% otherwise (all complaints).
- `07_trends.sql` — view `v_trends`: v_volume + log-ratio trends (last 90 vs the 90 before) + shares of national volume; test 21/21. ✅
  Shares fix most of the count drift: avg company 90d count ×5.5 from 2022 to 2024, avg share ×1.5
  (15.6% → 23.4%, a real shift toward the bureaus). Trends read high in 2022 (avg 1.968) — warm-up.
- `08_assembly.sql` — materialized view `mv_features` (40 columns, 1.75 GB, ~80 s build) + view `v_model_input` (the 19 model inputs); leak guard 0 label columns; lookup 0.036 ms. ✅
- `feature_dictionary.md` — every stored column: meaning, frame, and why it is (or is not) a model input.
