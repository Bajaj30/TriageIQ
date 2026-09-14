# TriageIQ — Interview Notes

Phase-by-phase: what it does, what broke, how it was fixed.
Kept short on purpose — each entry should be speakable in under a minute.

**One-line pitch:** Predict whether an incoming CFPB consumer complaint will end in monetary relief,
so a compliance desk can staff senior analysts against a 15-day regulatory deadline instead of
guessing from the text alone.

---

## Phase 0.1 — Docker + Postgres
**What it does:** Runs PostgreSQL 16 (pgvector image) locally via Docker Compose, so the database is
reproducible from day one and Phase 2 needs no migration.

*Status: partial — concepts learned, compose file not yet written. No issues logged yet.*

---

## Phase 0.2 — Source dataset and EDA
**What it does:** Profiles the 9.2 GB CFPB Consumer Complaint dump (17.3M rows), proves the text is
real rather than LLM-generated, and funnels it into a versioned training set.

### Issue 1 — The file doesn't fit in memory
A 9.2 GB CSV cannot be loaded with `pd.read_csv`. Everything downstream (profiling, label counts,
sampling) depends on getting a full pass over it.

**Fix:** Streamed it in 250k-row chunks, extracting only the needed columns per chunk and caching the
result as Parquet. Later passes read the ~1.7 GB Parquet in 14 seconds instead of re-parsing 9.2 GB.

### Issue 2 — Is the corpus real or LLM-generated?
Kaggle-era datasets are often synthetic, which would make a transformer branch pure theatre. Needed
an objective test, not a vibe check.

**Fix:** Built a five-metric gate — exact-duplicate rate, sentence-length coefficient of variation,
type-token ratio, repeated-opener share, unfilled placeholders. CFPB passed clearly (CV 0.94 vs
<0.35 suspicious; TTR 0.065). The top repeated opener turned out to be FCRA legal boilerplate that
real consumers copy-paste from credit-repair forums — evidence *for* authenticity, not against.

### Issue 3 — Two false alarms that looked like fatal data problems
The placeholder count rose 1→15 after filtering, which looked like the funnel was making the data
*more* synthetic. Separately, 40+ character "words" suggested whitespace corruption.

**Fix:** Printed the actual matches instead of trusting the counter. The "placeholders" were
`{XXXX}` — CFPB's currency-redaction convention — matched because the detector regex `\{[a-z_]+\}`
ran with `case=False`, so `[a-z_]` matched uppercase X. The long "words" were URLs: 0.26% of rows,
0 materially corrupted. Both were my measurement bugs, not data defects.

### Issue 4 — 41% of rows sit in duplicate groups, one cluster had 30,110 copies
Templated complaints circulate on consumer forums, so identical text appears thousands of times
across different companies (87% of duplicate groups span multiple companies).

**Fix:** Capped cluster size at 25 rather than deduplicating fully — full dedup would erase a real
property of the domain, while the cap kills the pathological clusters. Dropped the exact-duplicate
rate from 19.8% to 0.3%.

### Issue 5 — The sampler was silently editing the label
v1 capped each product at 16k rows to "balance" the mix. The cap flattened 10 products to ~9% each
*and* pushed the monetary-relief base rate from the true 2.16% to 7.5% — a 3.5× distortion, because
it upweighted card/bank products where payouts are common.

**Fix:** Removed the cap entirely and kept the natural product mix. Sampling must never touch the
label distribution; if the base rate needs changing, do it explicitly via case-control sampling where
the correction factor is recorded and reversible.

### Issue 6 — 2.16% positives is too sparse to fine-tune on
A transformer trained on a 2% positive rate over 1.6M rows is both slow and unstable.

**Fix:** Case-control sampling — keep **all** 35,375 positives, downsample negatives to 3:1 (25%
positive). Critically, the temporal split happens *first*, and only the train split is resampled:
val and test stay at natural prevalence, because PR-AUC moves with base rate and scoring on a
resampled test set would inflate the headline number ~10×. The negative keep-fraction (0.1046) is
stored in the manifest so predictions can be recalibrated with a logit offset of −2.2572.

---

## The v1 → v2 pivot (cross-cutting — the best story in the project)
**What it does:** Replaced a design built on synthetic customer data with one built entirely on real
public data, after measuring that the original design could not work.

### Issue 7 — The chosen dataset has no consumer identity
v1's architecture rested on customer-level features: lifetime spend, ticket velocity, prior
escalations. CFPB complaints are anonymous — one row, one complaint, no customer key. The entire
tabular branch had nothing to attach to.

**Fix:** Pivoted the entity from *customer* to *company × issue*. "How often has this company paid
out on this kind of complaint, as of today" is the same window-function problem with a different
partition key, so the point-in-time SQL curriculum survived intact — and it deleted the synthetic
data generator, which was the project's highest-risk task.

### Issue 8 — The problem was degenerate before any modelling
Predicting monetary relief across all products gave ROC-AUC 0.957 from `Product` alone and 0.976
from `Company` alone. The label was nearly determined by a field handed over at intake, so text
would have added nothing.

**Fix:** Evaluated *within* (Product × Issue) strata instead of pooled. Inside a stratum the
metadata shortcut disappears and text-only reaches 0.898 AUC — real, independent signal. The lesson
generalises: a high pooled AUC can be entirely between-group variation that is useless to any single
deployed user.

### Issue 9 — A "fix" that would have thrown away the important cases
An intermediate design filtered to five "money-bearing" products and template-routed the rest by
rule. A $200k student-loan disbursement failure would have been auto-templated because student loans
have a 1.2% payout rate.

**Fix:** Killed the rule tier after measuring text-only AUC *inside* the low-payout products —
0.809 in Mortgage, 0.771 in Vehicle loan. The narrative ranks complaints within a product perfectly
well, so filtering by product discards exactly the cases that need human judgement.

### Issue 10 — Pooled metrics were flattering the design
Pooled fusion AUC was 0.835 but **within-company** it was 0.768. The gap was company-identity
signal — useless to a bank triaging its own queue, where "which company" is constant.

**Fix:** Report all three numbers (pooled / within-strata / within-company) and explain the gap in
the README rather than quoting the best one. A sharp interviewer will ask; answering before they ask
is the stronger move.

### Issue 11 — The target measures company cost, not consumer harm
`Closed with monetary relief` captures whether the company wrote a cheque, not how badly the
consumer was hurt. CFPB publishes no severity label, so a severity model would be unvalidatable.

**Fix:** Stated the limitation explicitly rather than overclaiming, and recovered the *magnitude*
intuition with a thin ranking layer: `expected_cost = P(relief) × claimed_amount`, with the amount
regex-extracted from the narrative. A $200k claim at P=0.012 scores $2,400; a $10 claim at P=0.285
scores $3 — 800× separation, correctly ordered, without inventing a label.

---

## Phase 0.3 — Schema design *(in progress)*
**What it does:** A star schema over one real fact table — `fact_complaint` plus company / product /
issue / state dimensions, and an append-only `complaint_events` log (received → sent to company →
responded).

### Issue 12 — Dates have no time component, and ties are everywhere
`Date received` is day-granularity, and 43.5% of company-days hold more than one complaint (max
4,245 in a single day). "The complaints before this one" is undefined among same-day rows.

**Fix (verified on live PostgreSQL 18.4):** Three window-frame patterns chosen by what the feature
*means*, because no single frame works. Outcome rates use
`RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING` (excludes the day *and* CFPB's response
lag); volume counts use `RANGE '90 days' PRECEDING AND '1 day' PRECEDING`; sequence features (LAG,
rank) use `ORDER BY date_received, complaint_id`. See `TriageIQ.md` §1.4a.

### Issue 13 — SQL's default window frame leaks the label
Writing `avg(paid) OVER (PARTITION BY company ORDER BY d)` with no frame clause uses the default
`RANGE ... CURRENT ROW`, which in RANGE mode includes **every row tied with the current one** — so a
complaint's own outcome lands inside its own feature. Tested: all five same-day rows returned 2/5.

**Fix:** Never rely on the default frame. Also discovered the obvious fix (adding `complaint_id` to
`ORDER BY`) is *illegal* with interval frames — Postgres errors with "RANGE with offset requires
exactly one ORDER BY column" — which is why the three-pattern rule exists. Separately: `ROWS` is not
a time window; across an 8-month gap it reported 3 "recent" complaints where `RANGE '90 days'`
correctly reported 0.

### Issue 14 — The same query returned different numbers between runs
With tied dates and no tiebreak, window results depend on physical row order. Identical data and
SQL produced `NULL, 1.0, 1.0, 0.667, 0.5` in one row order and `0.25, 0, 0, 0, NULL` in another.

**Fix:** A deterministic tiebreak where the frame allows it, and excluding the whole current day
where it doesn't. Also flagged that `complaint_id` is stored as text (`'10000000' < '8688670'` under
string sort) so it must be cast to `bigint`, and that it is a deterministic tiebreak — not a clock.

---

## Audit (2026-09-12)
**What it does:** An adversarial audit of every quantitative claim, run partly by an independent
model and partly as a self-audit (disclosed). Full report: `Context/audit_findings_2026-09-12.md`.

### Issue 15 — The headline numbers existed nowhere in the repo
The ablation figures quoted throughout the docs were produced by throwaway scripts that were never
saved. Unreproducible by definition, which violates the project's own ground rule 6.

**Fix:** Wrote `training/verify_ablation.py`, committed with its results JSON. The numbers reproduced
to three decimals (0.9706 / 0.9714 / 0.9786 pooled) — but the exercise surfaced a worse problem
(below), which is the argument for making things reproducible in the first place.

### Issue 16 — The baselines were measured on the wrong dataset
The quoted numbers came from a 500k random sample with a different split than the shipped artifact.
Re-run on the actual training set, fusion within-strata fell 0.9447 → 0.9330 and metadata-only fell
0.9400 → **0.9076**.

**Fix:** Traced the metadata collapse to target encoding fitted on **case-control-resampled** train
data, where the positive rate is 25% instead of the true 3.4% — distorting both the encoded rates
and the smoothing prior. This is a concrete argument for the two-tier rule: entity rates must be
computed over the full population in Postgres, never over resampled training rows.

### Issue 17 — Documented cardinalities were from the wrong time frame
The DDL was about to be written against all-time figures (Product 21, Issue 173, Sub-issue 266) when
the project operates on the 2022–24 window, where the real values are 14 / 93 / 212.

**Fix:** Re-derived every documented statistic against four explicit frames (window-all,
window-narrative, all-time, shipped training set) and corrected the docs. Same class of error had
made `Tags` look 94.5% null when it is 87.8% in the training set, and made `Submitted via` look dead
when it has five values in the feature population.

### Issue 18 — The project had zero version control
`git init` had been run; nothing had ever been committed. Every document and derived artifact was
untracked — one bad command from total loss, while ground rule 6 claims reproducibility.

**Fix: NOT YET DONE.** Open action — commit before any schema work. The lesson is that
"reproducible" is a property you have to actually check, not one you get by writing it in a rules
list: the project asserted reproducibility in ground rule 6 for weeks while having no history at all.
