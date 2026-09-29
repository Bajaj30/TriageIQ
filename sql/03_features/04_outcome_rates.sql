-- ============================================================
-- 03_features/04_outcome_rates.sql
-- TARGET  : view v_outcome_rates
-- READS   : v_base (paid, untimely)
-- EXPECT  : 4,826,564 rows · rates in [0, 1] or NULL (no known history yet) · counts >= 0
-- CONCEPT : FRAME A — RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING. The leak-prone file.
-- ============================================================
-- STEPS
--  1. payout rate to date: company · company x issue · issue · product   (avg(paid) OVER ...)
--  2. untimely rate to date: company                                     (avg(untimely) OVER ...)
--  3. next to every rate, the count behind it (count(*) OVER the same window)
--  4. is_first flags: count = 0 means 'no history', which is NOT the same as rate = 0
--  5. issue-level only — no sub-issue features (trap #10)

-- Why 60 days: an outcome isn't known the day a complaint arrives; the company has time to answer.
-- Proof — the LEAK TEST (sql/tests/): flip paid for every complaint of one company-day, recompute;
-- the features of those same complaints must not change at all.

-- query goes here
