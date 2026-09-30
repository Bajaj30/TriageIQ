-- ============================================================
-- 03_features/05_smoothing.sql
-- TARGET  : view v_smoothed
-- READS   : v_outcome_rates
-- EXPECT  : 4,826,564 rows · smoothed rates in [0, 1], never NULL
-- CONCEPT : Shrinkage: (payouts + K x prior) / (n + K) — small samples pulled toward a sensible default.
-- PROBLEM : "How far can we trust a rate built from only a few complaints?"
--           Why: 1 payout in 3 complaints is not a real '33% payer', and most of the 4,946 companies are small.
--           Without it: the model over-reacts to tiny samples — noise dressed up as signal.
-- ============================================================
-- STEPS
--  1. prior = the PRODUCT's payout rate to date (from 04) — itself as-of date   (trap #9)
--  2. company and company x issue rates: shrink toward that prior with weight K
--  3. when the prior is NULL too (a product's first 60 days), fall back to a stated constant
--  K = 5 — MEASURED in 05a_choose_k.sql (tuning period, AUC + Brier; 2..7 about equal, 50 clearly worse)
--  prior = the product's rate to date (trap #9)

-- The prior must also be as-of date — an all-time prior leaks the future (guardrail §10).

-- query goes here
