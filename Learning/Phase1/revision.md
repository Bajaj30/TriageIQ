# Phase 1 — Revision: point-in-time features in SQL

Interview prep for `sql/03_features/` (label → base → volume → outcome rates → smoothing → sequence →
trends → assembly) and its tests (`sql/tests/`). Every feature: `sql/03_features/feature_dictionary.md`.
Numbers: `Context/FACTS.md` or the file named. All numbers here are **all complaints, 2022–24** unless stated.

**The one-line version for an interview:** *"I built each complaint's company and issue track record as of
the day it arrived, with window functions over all 4.8 million complaints, proved there's no leak with a
test that flips future answers, and chose 19 of 48 stored columns after showing the rest only encode the
calendar."*

---

### 1. Point-in-time correctness — the rule under everything
- **Idea:** a feature may use only what existed the moment the complaint arrived. The answer key must
  never leak into the exam.
- **In TriageIQ:** every feature is "as of" `date_received`; outcomes also need a **60-day lag** (below).
- **Q:** What is data leakage? → **A:** Training on information you won't have at prediction time — the
  model looks brilliant offline and fails live. Here: a company's payout rate computed *including* this
  complaint's own outcome, or outcomes not yet known on that day.
- **Watch:** StatQuest — "One-Hot, Label, Target and K-Fold Target Encoding" (leakage via target encoding,
  15 min). *Book:* Chip Huyen, *Designing ML Systems*, ch. 5 (data leakage).

### 2. Window functions — the anatomy
- **Idea:** compute over related rows *without collapsing them*: `agg(...) OVER (PARTITION BY who ORDER BY
  when <frame>)` → one answer per row, from its own group, looking back.
- **In TriageIQ:** company / company × issue / issue / product windows (`WINDOW` clauses named once).
- **Q:** GROUP BY vs a window function? → **A:** GROUP BY returns one row per group; a window keeps every
  row and attaches the group calculation to it — exactly "this company's record as of this complaint".
- **Watch:** CMU 15-445 (Andy Pavlo), Lecture 02 "Modern SQL" (window functions, CTEs).

### 3. Frames, ties, and the default-frame leak
- **Idea:** the *frame* says which earlier rows count. The **default** frame with `ORDER BY` includes every
  row tied with the current one — same-day complaints, *including its own outcome*.
- **In TriageIQ:** 43.46% of company-days have >1 complaint, so ties are everywhere. Three frames by meaning:
  - **A, outcome rates:** `RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING`
  - **B, volume:** `RANGE BETWEEN '90 days' PRECEDING AND '1 day' PRECEDING`
  - **C, sequence (LAG, rank):** `ORDER BY date_received, complaint_id` (a deterministic tiebreak)
  `RANGE` with an interval **refuses** a second ORDER BY column — so a tiebreak is impossible there and the
  whole current day is excluded instead. `ROWS` counts rows, not days — not a time window.
- **Q:** Why not just add `complaint_id` to ORDER BY everywhere? → **A:** Postgres rejects it for interval
  frames; and without a tiebreak, results change with physical row order between runs.

### 4. The 60-day lag — labels arrive late
- **Idea:** an outcome isn't known the day a complaint arrives; the company answers later.
- **In TriageIQ:** CFPB never records *when* a company answered (D15), so rates use only complaints at least
  60 days old — an **assumption**, stated openly.
- **Q:** Why 60 days? → **A:** A conservative bound past the 15-day response deadline; a stated assumption,
  not a measured fact.

### 5. Layered views → a materialized view (a feature store)
- **Idea:** one view per concept, each tested alone; the last step stores the result on disk.
- **In TriageIQ:** 01–07 are views; `08_assembly.sql` builds `mv_features` (4,826,564 rows × 48 columns,
  2,081 MB) with a unique index (lookup 0.036 ms), and `v_model_input` lists the model's inputs — training
  export and API both read it. **Refresh is manual** (`REFRESH MATERIALIZED VIEW CONCURRENTLY`); stale data
  is silent — Phase 3 automates it.
- **Q:** View vs materialized view? → **A:** A view re-runs its query on every read (always fresh, can be
  slow); a materialized view stores the result (fast reads, must be refreshed).

### 6. Smoothing — don't trust a small sample *(tech: shrinkage, empirical Bayes)*
- **Idea:** 1 payout in 3 complaints isn't a "33% payer" — it's luck. Pretend each company starts with K
  imaginary complaints at a sensible default rate, then add the real ones:
  **smoothed = (payouts + K × prior) / (complaints + K)**.
- **In TriageIQ:** prior = the **product's** rate as of that day (not the global rate — that is mostly
  credit reports, 83% of complaints but 3% of payouts). K **measured** on Oct–Dec 2023: company × issue with
  < 200 history, AUC K=0 0.8690 · **K=5 0.8901** · K=50 0.8754 · K=500 0.8495; Brier best at K=5. Before any
  product rate exists (first 60 days of 2022): the 2021 overall rate 2.86% — known before the data starts.
  K lives in a table (`feature_params`), not in code.
- **Q:** How did you choose K? → **A:** Measured, on a tuning period, never the test year; 2–7 were equal —
  the big win is smoothing at all.
- **Watch:** 3Blue1Brown — "Binomial distributions | Probabilities of probabilities, part 1" (the 10/10 vs
  48/50 reviews puzzle — the same idea).

### 7. Target encoding and the two-tier rule
- **Idea:** replacing a category (a company) with its average outcome is *target encoding* — powerful and
  leak-prone.
- **In TriageIQ:** rates computed over **all 4.8M complaints**, never over the training sample. An earlier
  version encoded from the case-control sample (25% payouts vs ~3%) — inflated rates cost the history-only
  model 0.032 AUC. Sampling decides what the model *reads*, never what the history *knows*.
- **Q:** Why not compute company rates in pandas from the training set? → **A:** Resampled data distorts the
  rates; and a second implementation outside SQL could drift from what the API serves.

### 8. Cold start — "no history" ≠ "never pays"
- **Idea:** a new company has no record; say so explicitly instead of a misleading 0.
- **In TriageIQ:** `company_no_history`, `company_issue_no_history` flags; with n = 0 the smoothing formula
  returns exactly the prior. 14.07% of 2022 complaints have no company history (warm-up), 0.06% in 2024.
- **Q:** What does the model see for a brand-new company? → **A:** The product prior + a no-history flag.

### 9. Volume: shares and trends, not raw counts
- **Idea:** in a growing system raw counts drift; ratios don't.
- **In TriageIQ:** an average company's 90-day count grew ×5.5 from 2022 to 2024; its *share* of all
  complaints grew ×1.5. Trend = ln((last 90 days + 1) / (the 90 before + 1)) — 0.69 means doubled.
- **Q:** Why log-ratios? → **A:** Symmetric (halving = −0.69, doubling = +0.69), +1 avoids dividing by zero.

### 10. Clocks — and choosing 19 of 48
- **Idea:** a feature that grows with calendar time teaches the model *when*, not *what* — and test-year
  values fall outside anything seen in training. *(tech: covariate shift)*
- **In TriageIQ:** e.g. a company's all-time count averaged ~108,569 in training years vs ~588,157 in 2024.
  Tested: 19 inputs → within-company 0.7500; 19 + the 16 excluded → 0.7499 (logistic regression, v3 test).
  `company_id` is also out — it would memorise 4,946 companies; the rates carry company behaviour instead.
- **Q:** How did you select features? → **A:** By meaning first (drop clocks and raw counts), then tested
  that the dropped ones add nothing.
- **Watch:** *Book:* Chip Huyen, ch. 8 (covariate shift).

### 11. One box, two answers — multi-hot flags
- **Idea:** "Older American", "Servicemember", or both → two yes/no flags, so "both" shares what each learns.
- **In TriageIQ:** `is_older_american`, `is_servicemember` in `02_base.sql` (no schema change — a view reads
  the column).

### 12. Testing features — two methods, and a test that can fail
- **Idea:** recompute the same number a completely different way; and prove "no leak" with a test that
  *would* fail if there were one.
- **In TriageIQ:** recounts with plain `WHERE date <= d - 60` (no windows) for 20+ complaints per view —
  all PASS. **Leak test:** inside `BEGIN … ROLLBACK`, flip every outcome of one company's busiest day (3,495
  complaints); same day and +59 days: unchanged; +60: the rate jumps 0.0034% → 0.34%. Then roll back.
- **Q:** How do you *prove* no leakage? → **A:** Change the future and show the past features don't move —
  and that they *do* move exactly when the lag allows. A test that can't fail proves nothing.
- **Watch (optional):** CMU 15-445 — the transactions / concurrency-control intro lecture (why ROLLBACK undoes everything).

### 13. Performance — memory, sorts, parallel workers
- **Idea:** window functions sort. If the sort doesn't fit in memory, it spills to disk (external merge sort).
- **In TriageIQ:** default `work_mem` 4 MB → the volume check wrote 28 GB of temp files, 11+ min.
  `ALTER DATABASE triageiq SET work_mem = '256MB'` → 16 s (an *old* pgAdmin connection kept the old setting).
  Heavy queries: `SET max_parallel_workers_per_gather = 0` — parallel hash tables overflowed Docker's 1 GB
  shared memory.
- **Q:** A query is slow — first steps? → **A:** `EXPLAIN ANALYZE`, look for disk spills / seq scans, then
  memory settings and indexes; change one thing, re-measure.
- **Watch:** CMU 15-445 — the "Sorting & Aggregation Algorithms" lecture (external merge sort).

### 14. Does the track record work before any model?
- **In TriageIQ:** complaints whose company × issue rate was > 15% really paid 28.74%; ≤ 1% → 0.03%.
- **Q:** How did you sanity-check a feature? → **A:** Bucket it and look at the real payout rate per bucket.

---

## What broke, and the fix

| what happened | fix | lesson |
|---|---|---|
| Volume check ran 11+ min (28 GB temp) | `work_mem` 256 MB → 16 s | measure memory before rewriting SQL |
| "could not resize shared memory segment" | no parallel workers for heavy queries | Docker's shm limit is real |
| Leak test silently lost its day-60 probe (busiest day was 21 days from the data's end) | probe a day with ≥ 90 days after it; a missing probe = FAIL | a test must not pass by losing its cases |
| `bool_and` ignored NULLs → false PASS | `coalesce(actual = expected, false)` | NULL is not true |
| Counts and tenure grew with the calendar | shares, trends; clocks excluded | ask "does this encode *when*?" |
| `DROP VIEW … CASCADE` also dropped `mv_features` and the export view | re-run 08 and the export after | know your dependency chain |

## Numbers to know
Features over **4,826,564** complaints · `mv_features` **48 columns, 2,081 MB** · `v_model_input` lists 23
inputs (v4); the chosen model reads the first **19** · K = **5** · frames A/B/C · recount tests: volume 22/22 ·
outcome rates 21/21 · sequence 22/22 · trends 21/21 · leak test 3/3.

## Lectures to re-watch
- CMU 15-445: Lecture 02 "Modern SQL"; "Sorting & Aggregation Algorithms".
- 3Blue1Brown: "Binomial distributions | Probabilities of probabilities, part 1".
- StatQuest: "One-Hot, Label, Target and K-Fold Target Encoding, Clearly Explained!!!".
- *Book:* Chip Huyen, *Designing Machine Learning Systems* — ch. 5 (leakage), ch. 8 (shift).
