-- ============================================================
-- 06_serving/01_snapshot.sql
-- TARGET  : schema serving · 5 snapshot tables · serving.feature_params · procedure build_serving_snapshot(date)
-- READS   : v_base, feature_params
-- PROBLEM : "A NEW complaint needs its 19 inputs in milliseconds — without replaying 4.8M rows of history."
-- ============================================================
-- CONCEPT : training-time features vs live features.
--   Training needed every complaint's inputs AS OF ITS OWN DAY -> window functions over all rows (mv_features).
--   A live complaint needs them as of ONE day: "now". For one fixed day every window collapses into a plain
--   GROUP BY with a date filter — a scoreboard per company / issue / product. These tables are that scoreboard.
--   The formula that turns counts into the 19 inputs lives in 02_features_fn.sql.
--
-- AS OF A DAY D = "what a complaint RECEIVED ON D would see" — exactly the training frames:
--   outcomes (frame A) : complaints received on or before D - 60          (n_known, payouts, untimely rate)
--   volume   (frame B) : complaints received D - 90 .. D - 1              (n_90d; national n_90d)
--   trends             : and the 90 days before that, D - 180 .. D - 91   (n_prev_90d)
--   quiet days         : the company's last complaint before D            (last_date)
-- The live snapshot uses D = 2025-01-01 (the day after the data ends). The skew test
-- (sql/tests/06_serving_check.sql) builds it for PAST days and compares with mv_features — that is the proof
-- that this second way of counting gives the same numbers as training.
--
-- WHY A SCHEMA: everything the live system needs sits in schema `serving`; `pg_dump -n serving` ships it
-- as one file. The build procedure stays in public (it reads the full history, which never ships).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS serving;

-- ---------------------------------------------------------------- the scoreboard, one table per level
-- Column types copy what the training windows produce (count/sum -> bigint, avg -> numeric), so the
-- formulas in 02 do the same arithmetic as 05_smoothing / 07_trends — down to the last digit.
CREATE TABLE IF NOT EXISTS serving.snap_product (
    as_of      DATE    NOT NULL,
    product_id INTEGER NOT NULL,
    n_known    BIGINT  NOT NULL,     -- complaints with a known outcome (received <= D - 60)
    payouts    BIGINT,               -- of those, paid; NULL when n_known = 0 (sum of nothing), as in training
    PRIMARY KEY (as_of, product_id)
);
CREATE TABLE IF NOT EXISTS serving.snap_issue (
    as_of      DATE    NOT NULL,
    issue_id   INTEGER NOT NULL,
    n_known    BIGINT  NOT NULL,
    payouts    BIGINT,
    n_90d      BIGINT  NOT NULL,     -- received D - 90 .. D - 1
    n_prev_90d BIGINT  NOT NULL,     -- received D - 180 .. D - 91
    PRIMARY KEY (as_of, issue_id)
);
CREATE TABLE IF NOT EXISTS serving.snap_company (
    as_of         DATE    NOT NULL,
    company_id    INTEGER NOT NULL,
    n_known       BIGINT  NOT NULL,
    payouts       BIGINT,
    untimely_rate NUMERIC,           -- avg(untimely) over known outcomes; NULL = no history
    n_90d         BIGINT  NOT NULL,
    n_prev_90d    BIGINT  NOT NULL,
    last_date     DATE    NOT NULL,  -- the company's latest complaint before D (quiet days = D - last_date)
    PRIMARY KEY (as_of, company_id)
);
CREATE TABLE IF NOT EXISTS serving.snap_company_issue (
    as_of      DATE    NOT NULL,
    company_id INTEGER NOT NULL,
    issue_id   INTEGER NOT NULL,
    n_known    BIGINT  NOT NULL,
    payouts    BIGINT,
    n_90d      BIGINT  NOT NULL,
    PRIMARY KEY (as_of, company_id, issue_id)
);
CREATE TABLE IF NOT EXISTS serving.snap_national (
    as_of DATE   PRIMARY KEY,
    n_90d BIGINT NOT NULL            -- every complaint received D - 90 .. D - 1 (the share denominator)
);

-- The smoothing settings travel with the snapshot: K and the 2021 fallback, copied from the ONE place
-- they live (public.feature_params). Re-running this file refreshes the copy.
CREATE TABLE IF NOT EXISTS serving.feature_params (
    param  TEXT    PRIMARY KEY,
    value  NUMERIC NOT NULL,
    source TEXT    NOT NULL
);
INSERT INTO serving.feature_params SELECT * FROM public.feature_params
ON CONFLICT (param) DO UPDATE SET value = EXCLUDED.value, source = EXCLUDED.source;

-- ---------------------------------------------------------------- the builder
-- One pass over the history before D (a temp table), then one GROUP BY per level. FILTER (WHERE …) gives
-- each window its own date range inside a single scan. Re-runnable: it replaces that day's rows.
CREATE OR REPLACE PROCEDURE build_serving_snapshot(p_as_of DATE)
LANGUAGE plpgsql
SET max_parallel_workers_per_gather = 0          -- parallel hashes overflow Docker's 1 GB shm (trap 12)
AS $$
BEGIN
    DROP TABLE IF EXISTS _hist;
    CREATE TEMP TABLE _hist AS
    SELECT company_id, issue_id, product_id, date_received, paid, untimely
    FROM   v_base
    WHERE  date_received < p_as_of;              -- only the past: nothing on or after D can be seen

    DELETE FROM serving.snap_product       WHERE as_of = p_as_of;
    DELETE FROM serving.snap_issue         WHERE as_of = p_as_of;
    DELETE FROM serving.snap_company       WHERE as_of = p_as_of;
    DELETE FROM serving.snap_company_issue WHERE as_of = p_as_of;
    DELETE FROM serving.snap_national      WHERE as_of = p_as_of;

    INSERT INTO serving.snap_product
    SELECT p_as_of, product_id,
           count(*)  FILTER (WHERE date_received <= p_as_of - 60),
           sum(paid) FILTER (WHERE date_received <= p_as_of - 60)
    FROM   _hist GROUP BY product_id;

    INSERT INTO serving.snap_issue
    SELECT p_as_of, issue_id,
           count(*)  FILTER (WHERE date_received <= p_as_of - 60),
           sum(paid) FILTER (WHERE date_received <= p_as_of - 60),
           count(*)  FILTER (WHERE date_received >= p_as_of - 90),
           count(*)  FILTER (WHERE date_received BETWEEN p_as_of - 180 AND p_as_of - 91)
    FROM   _hist GROUP BY issue_id;

    INSERT INTO serving.snap_company
    SELECT p_as_of, company_id,
           count(*)      FILTER (WHERE date_received <= p_as_of - 60),
           sum(paid)     FILTER (WHERE date_received <= p_as_of - 60),
           avg(untimely) FILTER (WHERE date_received <= p_as_of - 60),
           count(*)      FILTER (WHERE date_received >= p_as_of - 90),
           count(*)      FILTER (WHERE date_received BETWEEN p_as_of - 180 AND p_as_of - 91),
           max(date_received)
    FROM   _hist GROUP BY company_id;

    INSERT INTO serving.snap_company_issue
    SELECT p_as_of, company_id, issue_id,
           count(*)  FILTER (WHERE date_received <= p_as_of - 60),
           sum(paid) FILTER (WHERE date_received <= p_as_of - 60),
           count(*)  FILTER (WHERE date_received >= p_as_of - 90)
    FROM   _hist GROUP BY company_id, issue_id;

    INSERT INTO serving.snap_national
    SELECT p_as_of, count(*) FROM _hist WHERE date_received >= p_as_of - 90;

    DROP TABLE _hist;
END $$;

-- ---------------------------------------------------------------- build the live snapshot
-- D = 2025-01-01: a complaint arriving the day after the data ends. Outcomes count up to 2024-11-02
-- (the 60-day lag); volume counts the last 90 days of 2024. ~30 s.
CALL build_serving_snapshot(DATE '2025-01-01');

-- CHECKS
-- 1. one day built, sizes. Expect as_of 2025-01-01 · companies = every company with a complaint (4,946)
--    · pairs = 31,378 (CLAUDE.md §5) · national_90d > 0.
SELECT (SELECT max(as_of) FROM serving.snap_national)                               AS as_of,
       (SELECT count(*) FROM serving.snap_product       WHERE as_of = '2025-01-01') AS products,
       (SELECT count(*) FROM serving.snap_issue         WHERE as_of = '2025-01-01') AS issues,
       (SELECT count(*) FROM serving.snap_company       WHERE as_of = '2025-01-01') AS companies,
       (SELECT count(*) FROM serving.snap_company_issue WHERE as_of = '2025-01-01') AS company_issue_pairs,
       (SELECT n_90d    FROM serving.snap_national      WHERE as_of = '2025-01-01') AS national_90d;

-- 2. no outcome after the cut-off leaked in: every count of KNOWN outcomes must equal a plain recount of
--    complaints received on or before 2024-11-02. Expect 0 mismatches.
SELECT count(*) AS mismatched_products
FROM   serving.snap_product s
JOIN  (SELECT product_id, count(*) AS n FROM v_base WHERE date_received <= DATE '2025-01-01' - 60
       GROUP BY product_id) r USING (product_id)
WHERE  s.as_of = '2025-01-01' AND s.n_known <> r.n;
