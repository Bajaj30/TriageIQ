-- ============================================================
-- 03_features/03_volume.sql
-- TARGET  : view v_volume
-- READS   : v_base
-- EXPECT  : 4,826,564 rows · every count >= 0, never NULL
-- CONCEPT : FRAME B — RANGE BETWEEN 'N days' PRECEDING AND '1 day' PRECEDING, declared once as a named WINDOW.
-- PROBLEM : "How busy was this company — and this issue, and the whole system — just before this complaint?"
--           Why: a sudden flood of complaints signals trouble at a company, and arrivals are known at intake.
--           Without it: the model can't tell a company having a bad month from a quiet one.
-- ============================================================
-- STEPS
--  1. company: complaints before today — all-time, last 30 days, last 90 days
--     PARTITION BY company_id ORDER BY date_received
--  2. company x issue: last 90 days   — PARTITION BY company_id, issue_id
--  3. issue, system-wide: last 90 days — PARTITION BY issue_id
--  4. national: last 7 days            — no PARTITION
--  5. every frame stops at '1 day' PRECEDING: arrival is known at intake, same-day ORDER is not

-- No label here, so no leak risk — the safe place to learn frames.
-- 'All-time' starts 2022-01-01: early-2022 rows have short histories (a warm-up period — note it).
-- Proof: hand-count one busy company in sql/tests/.

-- How the frames read, for a complaint received on day d:
--   RANGE BETWEEN INTERVAL '30 days' PRECEDING AND INTERVAL '1 day' PRECEDING  =  days d-30 .. d-1
--   RANGE counts by DATE VALUE, not by rows: a gap of 8 quiet months correctly gives 0 (ROWS would not).
--   Stopping at d-1 drops the whole current day, so same-day ties never matter — no tiebreak needed.
-- The named WINDOWs below fix only WHO (partition) and ORDER; each feature adds its own frame.
-- A window that names another window may add a frame — that's how one definition serves 3 features.

CREATE OR REPLACE VIEW v_volume AS
SELECT complaint_id,
       -- step 1: the company
       count(*) OVER (w_company  RANGE BETWEEN UNBOUNDED PRECEDING     AND INTERVAL '1 day' PRECEDING) AS company_n_prior,
       count(*) OVER (w_company  RANGE BETWEEN INTERVAL '30 days' PRECEDING AND INTERVAL '1 day' PRECEDING) AS company_n_30d,
       count(*) OVER (w_company  RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '1 day' PRECEDING) AS company_n_90d,
       -- step 2: the company on THIS issue — the project's main unit
       count(*) OVER (w_co_issue RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '1 day' PRECEDING) AS company_issue_n_90d,
       -- step 3: this issue across every company — is the problem spreading?
       count(*) OVER (w_issue    RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '1 day' PRECEDING) AS issue_n_90d,
       -- step 4: every complaint in the country — a surge in general
       count(*) OVER (w_national RANGE BETWEEN INTERVAL '7 days'  PRECEDING AND INTERVAL '1 day' PRECEDING) AS national_n_7d
FROM   v_base
WINDOW w_company  AS (PARTITION BY company_id           ORDER BY date_received),
       w_co_issue AS (PARTITION BY company_id, issue_id ORDER BY date_received),
       w_issue    AS (PARTITION BY issue_id             ORDER BY date_received),
       w_national AS (                                  ORDER BY date_received);

-- count(*) over an EMPTY frame is 0, never NULL — so "no history" shows up as 0 here.
-- (Rates in 04 behave differently: avg() over an empty frame is NULL.)

-- CHECKS — the view recomputes all four windows every time it is queried (~15 s with work_mem 256MB — 12_indexes.sql), so every
-- check reads it ONCE into a CTE. 08_assembly will store the result; until then, queries are slow.

-- 1. grain and sanity in one row. Expect rows = complaints = 4,826,564, every *_negative / *_null = 0,
--    and 30d <= 90d <= all-time for the company (a smaller window can never count more).
WITH v AS MATERIALIZED (SELECT * FROM v_volume)
SELECT count(*)                                                        AS rows,
       count(DISTINCT complaint_id)                                    AS complaints,
       count(*) FILTER (WHERE least(company_n_prior, company_n_30d, company_n_90d,
                                    company_issue_n_90d, issue_n_90d, national_n_7d) < 0) AS any_negative,
       count(*) FILTER (WHERE company_n_30d > company_n_90d
                           OR company_n_90d > company_n_prior)         AS window_order_broken,
       count(*) FILTER (WHERE company_issue_n_90d > company_n_90d)     AS pair_exceeds_company,
       max(national_n_7d)                                              AS max_national_7d
FROM   v;

-- 2. DRIFT — the average of each count by year. Complaint volume grew from 800,245 (2022) to
--    2,734,270 (2024) in the window, so raw counts are bigger in the test year than in training.
--    Read this before deciding which counts the model gets (see the note in 03_features/log.md).
WITH v AS MATERIALIZED (SELECT * FROM v_volume)
SELECT extract(year FROM b.date_received)::int      AS year,
       round(avg(v.company_n_prior))                AS avg_company_prior,
       round(avg(v.company_n_90d))                  AS avg_company_90d,
       round(avg(v.company_issue_n_90d))            AS avg_company_issue_90d,
       round(avg(v.national_n_7d))                  AS avg_national_7d
FROM   v JOIN v_base b USING (complaint_id)
GROUP  BY 1 ORDER BY 1;
