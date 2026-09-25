-- ============================================================
-- 02_load/02_dim_state.sql
-- TARGET  : dim_state
-- READS   : stg_window
-- EXPECT  : 62 (61 states + '(not specified)')
-- CONCEPT : INSERT ... SELECT DISTINCT. DISTINCT sets the grain: one row per state.
-- ============================================================
-- STEPS
--  1. SELECT DISTINCT COALESCE(state, '(not specified)')
--  2. INSERT only the name — state_id is generated

INSERT INTO dim_state (state_code)                 -- only the name: state_id is generated
SELECT DISTINCT COALESCE(state, '(not specified)')  -- DISTINCT = one row per state (the grain)
FROM   stg_window                                   -- NULL state -> a real member (D9)
ORDER  BY 1                                         -- alphabetical -> ids come out the same every rebuild
ON CONFLICT (state_code) DO NOTHING;                -- re-runnable: a second run adds nothing

-- CHECKS
-- 1. expect 62
SELECT count(*) AS states FROM dim_state;

-- 2. the placeholder member must exist
SELECT state_id, state_code FROM dim_state WHERE state_code = '(not specified)';

-- 3. THE REAL TEST: every window complaint finds its state. Expect 4,826,564.
--    Lower = some complaints would vanish from the fact table later.
SELECT count(*) AS complaints_matched
FROM   stg_window w
JOIN   dim_state  s ON s.state_code = COALESCE(w.state, '(not specified)');
