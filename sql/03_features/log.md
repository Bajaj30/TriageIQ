# 03_features — point-in-time features over all 4,826,564 complaints, one row per complaint

Order: label → base → volume → outcome rates → smoothing → sequence → trends → assembly.
Each file builds one view; 08 stitches them into the materialized view the model reads.

- `01_label.sql` — view `v_label`: did the complaint pay (1/0) and was it untimely; Phase 0.5.
- `02_base.sql` — view `v_base`: fact + label, one row per complaint, feature columns only.
- `03_volume.sql` — view `v_volume`: how many complaints before today (frame B).
- `04_outcome_rates.sql` — view `v_outcome_rates`: payout / untimely rates to date, 60-day lag (frame A).
- `05_smoothing.sql` — view `v_smoothed`: small-sample rates pulled toward the product's rate.
- `06_sequence.sql` — view `v_sequence`: gaps, ranks and tenure (frame C, deterministic tiebreak).
- `07_trends.sql` — view `v_trends`: last 90 days vs the 90 before.
- `08_assembly.sql` — materialized view `mv_features`: every feature, one row per complaint.
