-- ============================================================
-- 03_features/04_outcome_rates.sql
-- TARGET  : view v_outcome_rates
-- READS   : v_base (paid, untimely)
-- EXPECT  : 4,826,564 rows · rates in [0, 1] or NULL (no known history yet) · counts >= 0
-- CONCEPT : FRAME A — RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING. The leak-prone file.
-- PROBLEM : "Before this complaint, how often did this company — on this kind of problem — end up paying?"
--           Why: the track record is the strongest non-text answer to the SOP's question "is it money-bearing?";
--                company x issue is the project's main unit.
--           Without the 60-day lag: the answer key leaks — recent outcomes weren't known yet when it arrived.
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

-- How frame A reads, for a complaint received on day d:
--   RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60 days' PRECEDING  =  every day up to d-60
--   The last 59 days are skipped on purpose: CFPB never records WHEN a company answered (D15), so we
--   assume an outcome is known 60 days after arrival. Same-day ties can't matter: day d is far outside.
-- This time the FRAME goes inside the named WINDOW: every feature of one entity must see exactly the
-- same rows, so it is written once. (TriageIQ.md §1.4a — "named windows".)
-- Empty frame: count(*) = 0, avg() = NULL. NULL rate means "no known history", NOT "never pays" —
-- so rates stay NULL here, and 05 decides what to use instead.
-- payouts (sum) are carried too: 05's smoothing needs the raw counts, not just the ratio.

CREATE OR REPLACE VIEW v_outcome_rates AS
SELECT complaint_id,
       -- step 1-3: the company
       count(*)      OVER w_company  AS company_n_known,        -- complaints with a KNOWN outcome
       sum(paid)     OVER w_company  AS company_payouts,
       avg(paid)     OVER w_company  AS company_paid_rate,
       avg(untimely) OVER w_company  AS company_untimely_rate,  -- step 2: ignores the regulator?
       -- the company on THIS issue — the main unit
       count(*)      OVER w_co_issue AS company_issue_n_known,
       sum(paid)     OVER w_co_issue AS company_issue_payouts,
       avg(paid)     OVER w_co_issue AS company_issue_paid_rate,
       -- this issue, every company (step 5: issue, never sub-issue)
       count(*)      OVER w_issue    AS issue_n_known,
       sum(paid)     OVER w_issue    AS issue_payouts,
       avg(paid)     OVER w_issue    AS issue_paid_rate,
       -- this product, every company — also 05's smoothing prior (trap #9)
       count(*)      OVER w_product  AS product_n_known,
       sum(paid)     OVER w_product  AS product_payouts,
       avg(paid)     OVER w_product  AS product_paid_rate,
       -- step 4: explicit "no history" flags for the two company-level entities
       (count(*) OVER w_company  = 0)::int AS company_no_history,
       (count(*) OVER w_co_issue = 0)::int AS company_issue_no_history,
       -- RECENT history (added 2026-10-02): only the 12 months that END 60 days ago. Companies change
       -- policy; the all-time rate above remembers 2022 as strongly as last quarter. Same 60-day lag,
       -- so the leak test covers these columns too. Smoothed in 05 toward the all-time rate.
       count(*)      OVER w_co_issue_recent AS company_issue_n_recent,
       sum(paid)     OVER w_co_issue_recent AS company_issue_payouts_recent,
       count(*)      OVER w_company_recent  AS company_n_recent,
       sum(paid)     OVER w_company_recent  AS company_payouts_recent
FROM   v_base
WINDOW w_company  AS (PARTITION BY company_id           ORDER BY date_received
                      RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60 days' PRECEDING),
       w_co_issue AS (PARTITION BY company_id, issue_id ORDER BY date_received
                      RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60 days' PRECEDING),
       w_issue    AS (PARTITION BY issue_id             ORDER BY date_received
                      RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60 days' PRECEDING),
       w_product  AS (PARTITION BY product_id           ORDER BY date_received
                      RANGE BETWEEN UNBOUNDED PRECEDING AND INTERVAL '60 days' PRECEDING),
       -- frame A, but with a START: days d-425 .. d-60 = the 365 days of outcomes known most recently
       w_co_issue_recent AS (PARTITION BY company_id, issue_id ORDER BY date_received
                      RANGE BETWEEN INTERVAL '425 days' PRECEDING AND INTERVAL '60 days' PRECEDING),
       w_company_recent  AS (PARTITION BY company_id           ORDER BY date_received
                      RANGE BETWEEN INTERVAL '425 days' PRECEDING AND INTERVAL '60 days' PRECEDING);

-- CHECKS — a view recomputes on every query; each check reads it ONCE (a MATERIALIZED CTE).
-- (If a check crawls: SHOW work_mem; must say 256MB — see CLAUDE.md trap #11.)

-- 1. grain and sanity in one row. Expect rows = complaints = 4,826,564 and every other column 0.
WITH v AS MATERIALIZED (SELECT * FROM v_outcome_rates)
SELECT count(*)                                                              AS rows,
       count(DISTINCT complaint_id)                                          AS complaints,
       count(*) FILTER (WHERE company_paid_rate NOT BETWEEN 0 AND 1
                           OR company_issue_paid_rate NOT BETWEEN 0 AND 1
                           OR issue_paid_rate NOT BETWEEN 0 AND 1
                           OR product_paid_rate NOT BETWEEN 0 AND 1)         AS rate_out_of_range,
       count(*) FILTER (WHERE (company_paid_rate IS NULL) <> (company_n_known = 0)) AS null_rate_mismatch,
       count(*) FILTER (WHERE company_issue_n_known > company_n_known)       AS pair_exceeds_company,
       count(*) FILTER (WHERE company_payouts > company_n_known)             AS payouts_exceed_n
FROM   v;

-- 2. the warm-up and the drift, by year: share of complaints with NO known company history, and the
--    average known history. 2022 starts with nothing (the first 60 days see no outcomes at all).
WITH v AS MATERIALIZED (SELECT * FROM v_outcome_rates)
SELECT extract(year FROM b.date_received)::int                AS year,
       round(100.0 * avg(v.company_no_history), 2)            AS pct_no_company_history,
       round(100.0 * avg(v.company_issue_no_history), 2)      AS pct_no_pair_history,
       round(avg(v.company_n_known))                          AS avg_company_n_known
FROM   v JOIN v_base b USING (complaint_id)
GROUP  BY 1 ORDER BY 1;

-- 3. DOES IT CARRY SIGNAL? Bucket each complaint by its company x issue payout rate (known before it
--    arrived) and show how often complaints in each bucket really paid. Rising = the feature works.
WITH v AS MATERIALIZED (SELECT complaint_id, company_issue_paid_rate FROM v_outcome_rates)
SELECT CASE WHEN v.company_issue_paid_rate IS NULL   THEN '0: no history'
            WHEN v.company_issue_paid_rate = 0       THEN '1: never paid'
            WHEN v.company_issue_paid_rate <= 0.01   THEN '2: up to 1%'
            WHEN v.company_issue_paid_rate <= 0.05   THEN '3: 1-5%'
            WHEN v.company_issue_paid_rate <= 0.15   THEN '4: 5-15%'
            ELSE                                          '5: over 15%' END AS pair_rate_bucket,
       count(*)                                    AS complaints,
       round(100.0 * avg(b.paid), 2)               AS actual_payout_pct
FROM   v JOIN v_base b USING (complaint_id)
GROUP  BY 1 ORDER BY 1;
