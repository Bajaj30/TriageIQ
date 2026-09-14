# TriageIQ — Engineering Bible (v2)

**Project:** CFPB complaint payout prediction — PostgreSQL point-in-time feature engineering +
fine-tuned transformer fusion model + containerized cloud deployment.

**Audience:** You (solo builder), and any hiring manager who opens the repo.

**Status:** Living document. Every decision states *what it does, why we chose it, how to implement
it, what to expect, and where it will hurt.* When reality contradicts this doc, update the doc —
that habit is itself a portfolio signal.

**v1 is archived at `Context/TriageIQ_v1_archive.md`.** Do not delete it. The delta between v1 and
v2 is a portfolio artifact in its own right — see §0.5.

---

## 0. Ground rules and constraints

1. **Sequencing.** SQL is being learned *now*, MLOps *later*. Each phase must be completable with
   only the skills available at that point and must end in a demo-able artifact.
2. **No JavaScript, ever.** The frontend is FastAPI's auto-generated Swagger UI. Full stop.
3. **Free tier or student laptop only.** No GPU cloud bills. Fine-tuning on Colab/Kaggle free GPU.
4. **One source of truth for features.** All feature logic lives in SQL inside Postgres. Python never
   re-implements a feature. This is the training/serving consistency guarantee and the project's
   central architectural claim.
5. **No leakage.** Every feature attached to a complaint must be computable from information that
   existed *at the moment the complaint was received*. Most common way this class of project dies.
6. **Reproducible.** Fixed seeds (SEED=42), versioned snapshots, logged run configs. If you can't
   rebuild an artifact from the repo, it isn't done.

**Definition of done:** a stranger can rebuild the DB, rerun feature engineering, retrain from a
snapshot, `docker compose up` the full stack, and hit a live cloud URL for a prediction.

---

## 0.5 Design history — what changed in v2 and why

**v1 assumed:** real ticket text + a *synthetic* transactional world (customers, orders, payments,
refunds, subscriptions), with an escalation label derived from a generated `ticket_events` log.

**What broke it:** the chosen corpus (CFPB) has **no consumer identity**. Every complaint is
anonymous. Customer-level features — lifetime spend, refund ratio, ticket velocity, prior
escalations — have nothing to attach to. Inventing a synthetic customer layer would have meant the
fusion model was learning our own generator, which v1 itself flagged as the #1 risk.

**What we measured before deciding** (all temporal splits, train ≤2023 / test 2024):

| finding | number | consequence |
|---|---|---|
| Predicting monetary relief across all 21 products, `Product` alone | AUC 0.957 | label nearly determined by a field given at intake |
| Same, `Company` alone | AUC 0.976 | ditto — degenerate before text is involved |
| Pooled fusion AUC vs **within-company** fusion AUC | 0.835 → 0.768 | pooled metrics are inflated by between-company variation |
| **Text only, within (Product × Issue) strata** | **AUC 0.898** | the narrative carries real, independent signal |
| Metadata only, same strata | AUC 0.940 | |
| **Fusion, same strata** | **AUC 0.945** | both modalities contribute — fusion justified |
| `any_relief` label: text vs metadata within strata | 0.628 vs 0.702 | **rejected** — metadata-dominated, kills the NLP thesis |
| Monetary-relief positives available | 35,375 (2.16%) | sparse *rate*, ample *count* — a sampling problem, not a viability one |

**Decisions that follow:**

1. **No synthetic data.** The project is now 100% real, public, verifiable data end to end. An
   interviewer can download CFPB and check every number.
2. **The entity carrying history is the company / issue, not the customer.** Point-in-time discipline
   and the entire window-function curriculum survive — only the partition key changes.
3. **The label is `Closed with monetary relief`** — "did this complaint cost the company money."
4. **No product filter, no rule tier.** An earlier draft filtered to five "money-bearing" products and
   routed the rest to a template response by rule. That was wrong: text-only AUC is 0.809 within
   Mortgage and 0.771 within Vehicle loan, so a serious complaint in a low-payout product is still
   rankable by what the consumer wrote. The rule tier would have discarded exactly those cases.
5. **The target is company cost, not consumer harm.** CFPB has no severity label; any severity model
   would be unvalidatable. Stated as a limitation in the README, not hidden. Magnitude is partially
   recovered by the Phase 2.6 ranking layer.

**Risks retired by this pivot:** v1's #1 (weak synthetic correlations → no fusion lift; now measured
and real) and #3 (synthetic-data rabbit hole; the generator no longer exists).

---

## Phase 0 — Data Foundation

**Goal:** a populated, normalized PostgreSQL database over the real CFPB corpus with a defensible,
leakage-free label.
**Exit criteria:** ERD committed; all tables loaded; row counts and integrity checks documented;
label distribution measured and written down.

### 0.1 Development environment — *status: partial*

Local PostgreSQL 16+ in Docker via a single Compose file from day one. Use the
`pgvector/pgvector:pg16` image from the start so Phase 2 needs zero migration. Named volume for
persistence, port 5432 published, password from a git-ignored `.env` with a committed `.env.example`.

**Pitfalls:** committing credentials; `latest` image tags (pin versions); forgetting the volume and
losing data; port 5432 already taken by a native Postgres install.

### 0.2 Source dataset — *status: complete*

**CFPB Consumer Complaint Database.** Real, US-government-published, redistributable.

| | |
|---|---|
| raw | 17,355,295 rows / 9.2 GB |
| with narrative | 3,843,057 (22%) |
| working window | 2022-01-01 → 2024-12-31 |
| complaints in window | **4,826,564** (all) |
| with narrative in window | **1,639,068** |
| monetary-relief positives | **35,375 (2.16%)** |

Synthetic-vs-real gate **passed** — sentence-length CV 0.94, TTR 0.065, exact-dup 19.8% raw. Two
apparent red flags were false alarms; both are documented in `Data/docs/data_profile.md` and must not
be re-litigated. Full profiling lives in `Data/EDA.ipynb`.

> **Note:** `Data/data/interim/triageiq_tickets_v1.parquet` (the 40k product-capped sample) is
> **obsolete under v2**. Cell 8 of the notebook must be rewritten for case-control sampling (§2.2).
> Cells 0–7 and 10 remain valid.

### 0.3 Schema design — *status: next*

**Shape: a star schema over one real fact table.** There is no synthetic transactional world.

| table | grain | notes |
|---|---|---|
| `dim_company` | one row per company | 4,950 distinct names in window; only 53 in any name-collision group, most genuinely distinct firms — raw name is a usable key with near-zero cleaning |
| `dim_product` | product / sub-product | 21 products, 85 sub-products |
| `dim_issue` | issue / sub-issue | 173 issues, 266 sub-issues; sub-issue 2.5% null |
| `dim_state` | state code | 63 values, 0.2% null |
| `fact_complaint` | **one row per complaint** | `complaint_id` PK — verified unique across all 4,826,564 window rows |
| `complaint_events` | one row per event | append-only log built from `Date received` → `Date sent to company` → response |

**Why an event log rather than mutable status columns:** it mirrors production systems, preserves
history, and makes point-in-time correctness *possible*. `Date sent to company` is **100% populated**
across all 17.3M rows, so this is a real log, not a stub.

**The tiebreak decision — settle this before writing any DDL.** `Date received` is **day-granularity
only**. In the window, **43.5% of company-days carry more than one complaint**, with up to 4,245 in a
single company-day. Every window function ordering by date alone will tie non-deterministically and
your features will not be reproducible run-to-run. **Order by `(date_received, complaint_id)`
everywhere**, and state the convention in the feature dictionary.

**Nullability from the data:** `State` 0.2% null · `Sub-issue` 2.5% · `Tags` **94.5% null** (drop or
treat as a sparse flag) · `Submitted via` is single-valued ("Web") for narrative rows and carries no
information.

**How:** draw the ERD first (dbdiagram.io or Mermaid), check it against every Phase 1 feature ("can
this schema answer this question *at a point in time*?"), then write DDL with explicit PKs, FKs, NOT
NULL and CHECK constraints. Timestamps `TIMESTAMPTZ`, stored UTC.

**Leakage traps to mark in the DDL comments** — these columns exist and must never become features:
`Date sent to company`, `Company response to consumer`, `Timely response?`, `Company public
response`. All are knowable only *after* intake. They are label material or event-log material, never
inputs.

### 0.4 Bulk load — *replaces v1's synthetic generator*

Load the **full window**, not a sample: 4,826,564 complaint rows (metadata for all, narrative where
present). Feature aggregates must be computed over the complete population — see §1.0.

**How:** stream the 9 GB CSV in chunks, `COPY` into staging, then insert into dimensions and fact
with FK resolution. Never row-by-row. Validate with a permanent `validation.sql`: FK orphans (zero),
date sanity (`date_sent_to_company >= date_received`), grain uniqueness on `complaint_id`,
distribution sanity against the numbers in §0.2.

**Expect:** the load is the bulk-COPY lesson v1 promised, now on real data. Budget an evening.

### 0.5 Label construction

**Label:** `Closed with monetary relief` → 1, everything else → 0. **35,375 positives, 2.16%.**

Write it as a **SQL view over the response column**, never a column baked in at load time, so the
definition is transparent, versioned, and changeable.

**Why this label:** it is the only outcome in CFPB that is (a) real, (b) unambiguous, (c) directly
answers "did this cost the company money," and (d) **text-predictable** — 0.898 within-strata AUC.
`any_relief` was measured and rejected: metadata beats text on it (0.702 vs 0.628), which would make
the transformer decorative.

**Known limitation, state it in the README:** this measures *company payout*, not *consumer harm*.
A severe complaint resolved without a cheque is a negative. CFPB has no severity label and any
severity model would be unvalidatable. §2.6 recovers magnitude, not severity.

**Note on the 2.16% rate:** v1 warned that below ~5% positives training destabilizes. That assumed a
~10k dataset where 2% is 200 positives. Here 2.16% is **35,375 positives** — abundant. It is a
sampling problem (§2.2), not a viability problem.

---

## Phase 1 — SQL Feature Engineering

**Goal:** a layered, leakage-free CTE pipeline producing one feature row per complaint, exposed as a
materialized view.
**Exit criteria:** `feature_assembly` built and refreshable; every feature documented; anti-leakage
spot checks pass.

### 1.0 The two-tier rule — read before writing any aggregate

**Feature-computation population ≠ training sample.**

Aggregates are computed over **all 4,826,564 complaints in the window**, including the ~3.2M with no
narrative text. A complaint with no text still counts toward "how many complaints did this company
receive in the last 90 days." The training sample (§2.2) is a much smaller subset of the rows that
*have* text.

**Why this matters concretely:** Bank of America has ~16k narrative complaints in the window. Compute
its 90-day trailing count on a 20% sample and you get ~70 instead of ~350 — wrong by 5×. At serving
time the API queries the full table and gets 350. That is training/serving skew, the exact failure
ground rule 4 exists to prevent.

### 1.1 Architecture: layered CTEs

One master SQL file as a chain of named CTEs — `cleaned_complaints` → `entity_profiles` →
`behavioral_windows` → `feature_assembly` — materialized at the end.

Build it **one CTE at a time**: write it, SELECT from it, eyeball 20 rows, check row counts against
expectation, then append to the master file with a comment block stating its contract (grain,
purpose, invariants). The file grows by accretion of verified pieces.

Materialized because the pipeline involves multiple window scans over millions of rows and is far too
slow per-request. One artifact, two consumers (training export + inference service) — that *is* the
training/serving consistency story.

### 1.2 Layer 1 — cleaning

Deduplicate (CFPB contains genuine forum-circulated template complaints — decide and document the
policy); coalesce NULL categoricals into explicit unknown buckets; trim and collapse whitespace only.
Heavy text cleaning belongs to the tokenizer in Phase 2, not SQL.

**The #1 bug of this phase:** a join that silently changes grain. **After every join, check the row
count.** Make it a reflex now.

### 1.3 Layer 2 — entity aggregates, as-of complaint date

Per-entity aggregates joined at the (complaint, entity) grain, **not** pure entity grain:

- company complaint volume: lifetime-to-date, 30d, 90d
- **company relief rate to date** — of complaints against this company received *before* this one,
  what fraction closed with monetary relief
- company untimely-response rate to date
- company product breadth; company tenure (days since its first complaint in the data)
- issue-level relief rate to date; product-level relief rate to date
- **company × issue relief rate to date** — the highest-value feature, and the one that survives when
  the system is deployed inside a single company

**The point-in-time discipline:** join with `event_timestamp < complaint_timestamp`, ordering by
`(date_received, complaint_id)`. A rate computed over all time leaks the future. This is heavier than
a naive `GROUP BY` — that is the cost of correctness, and articulating it is a top-tier interview
moment.

**Smoothing:** entities with three complaints have unstable rates. Shrink toward the global prior
(`(successes + K·prior) / (n + K)`, K≈50). Doing this *as-of date, in SQL* is genuinely advanced and
is a leakage trap in its own right — the prior must also be as-of.

**Pitfall:** aggregate each child relation in its own CTE *first*, then join the pre-aggregated
results. Aggregating two children in the same join multiplies rows and inflates sums.

### 1.4 Layer 3 — window functions, behavioral trajectories

- **company volume trend** — last 90 days vs prior 90 days before this complaint, as a ratio with
  explicit zero-denominator handling. Signals a deteriorating company.
- **issue volume trend** — is this issue type spiking system-wide? Emerging systemic problem.
- **days since this company's previous complaint** — `LAG` over the company's complaints.
- **complaint rank for this company this month.**
- **national complaint volume that week** — surge context.
- **days since dataset start** — drift proxy.

Every one of these is "for each row, look at *other rows* of the same entity, ordered in time." That
is the definition of a window function, and correctly framing them — partition, ordering, frame
bounds, exclusion of the current row — is the SQL depth that separates you from GROUP-BY-only
candidates.

**Expect** off-by-one boundary errors constantly. Is the frame `< received_at` or `<= received_at`?
Inclusive frames silently include the current row and leak the label. For each feature, hand-verify:
pick one busy company, list its complaints chronologically, compute on paper, compare. Keep these in
`tests/sql/`.

### 1.4a Window frame patterns — verified against PostgreSQL 18.4

*This subsection is empirical, not theoretical. Every claim below was tested on a live Postgres
cluster; the failing cases are real error messages and real wrong numbers. This is the most
interview-valuable page in the document — it is a concrete story about a leak you found, measured,
and fixed.*

**The root problem.** `Date received` has day granularity and no time component. 43.5% of
company-days carry more than one complaint (up to 4,245). So "the complaints before this one" is
undefined among same-day rows, and SQL will resolve that ambiguity for you — badly, and differently
on each run.

#### Finding 1 — the default frame silently includes the row's own label

Writing the natural thing:

```sql
avg(paid) OVER (PARTITION BY company ORDER BY d)          -- NO frame clause
```

The SQL default is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, and in `RANGE` mode
"CURRENT ROW" means *every row tied with this one*. Tested on five same-day complaints where two
were paid:

| complaint | paid | default_frame |
|---|---|---|
| 101 | 1 | 0.400 |
| 102 | 1 | 0.400 |
| 103 | 0 | 0.400 |
| 104 | 0 | 0.400 |
| 105 | 0 | 0.400 |

Every row got 2/5 — the average of the whole day **including itself**. Complaint 101's own payout is
inside 101's feature. On a 4,245-complaint company-day this pulls in 4,245 unknowable outcomes.

#### Finding 2 — without a tiebreak, the same query returns different numbers

Same data, same SQL, only the *physical row order* of the table changed:

| complaint | physical order ASC | physical order DESC |
|---|---|---|
| 101 | NULL | 0.250 |
| 102 | 1.000 | 0.000 |
| 103 | 1.000 | 0.000 |
| 104 | 0.667 | 0.000 |
| 105 | 0.500 | NULL |

No error, no warning — the features just change. After a `VACUUM`, an added index, or a parallel
scan, your training data is no longer the training data you trained on. This breaks ground rule 6.

#### Finding 3 — you cannot combine a tiebreak with a rolling time window

The obvious fix — add `complaint_id` to the `ORDER BY` — makes every rolling feature illegal:

```
ERROR: RANGE with offset PRECEDING/FOLLOWING requires exactly one ORDER BY column
```

`RANGE BETWEEN '90 days' PRECEDING …` demands exactly one ordering column. So the tiebreak and the
90-day window are mutually exclusive. **This is why there is no single correct frame.**

#### Finding 4 — `ROWS` is not a time window

With an 8-month gap in a company's history:

| complaint | date | `ROWS UNBOUNDED PRECEDING` | `RANGE '90 days'` |
|---|---|---|---|
| 4 | 2024-09-01 | **3** | **0** |

`ROWS` counts rows regardless of age, so "recent activity" built on `ROWS` counts ancient history as
recent. Time windows must use `RANGE`.

#### The resolution — three patterns, chosen by what the feature means

```sql
-- A. OUTCOME features (relief rate). The outcome of a complaint is not knowable until the
--    company responds, which CFPB allows up to 60 days. Exclude the lag, not just the day.
avg(paid) OVER (PARTITION BY company_id ORDER BY date_received
                RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING)

-- B. VOLUME features (counts). Arrival IS knowable at intake; only same-day order is ambiguous,
--    so exclude just the current day. Survives gaps correctly.
count(*) OVER (PARTITION BY company_id ORDER BY date_received
               RANGE BETWEEN '90 days' PRECEDING AND '1 day' PRECEDING)

-- C. SEQUENCE features (LAG, within-company rank). Here row order genuinely matters and RANGE
--    is not involved, so the deterministic tiebreak is both legal and required.
lag(date_received) OVER (PARTITION BY company_id ORDER BY date_received, complaint_id)
```

Patterns A and B need **no** tiebreak — excluding the whole current day makes intra-day order
irrelevant, which is a cleaner fix than trying to invent an order that doesn't exist.

#### Two mechanics worth knowing

**Named windows.** Don't repeat a frame spec across ten features — declare it once. Repeating it is
how the tenth feature ends up with a subtly different frame:

```sql
SELECT complaint_id,
       count(*)   OVER w AS n_prior,
       avg(paid)  OVER w AS relief_rate_prior
FROM   complaints
WINDOW w AS (PARTITION BY company_id ORDER BY date_received
             RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING);
```

**`COUNT` = 0 vs `AVG` = NULL.** On an empty frame `count(*)` returns 0 but `avg()` returns NULL.
That difference is free information — it distinguishes *"this company has no prior history"* from
*"it has history and the rate is zero."* Emit both: `COALESCE(avg(...), 0)` as the feature and
`count(*) = 0` as an explicit `is_first_complaint` flag. Never let a COALESCE erase the distinction.

#### Two more traps in the same area

- **`complaint_id` is stored as text and text sort is not numeric sort** (`'10000000' < '8688670'`).
  Cast to `bigint` in the DDL.
- **It is a deterministic tiebreak, not a clock.** Spearman correlation with date is 0.99998
  globally, but 99.9% of consecutive days have overlapping ID ranges (median overlap 41,552 IDs). It
  makes runs reproducible; it does not recover true intra-day ordering. Do not claim otherwise.

#### The interview version

*"My complaint dates had no time component and 43% of company-days had collisions. The default
window frame in SQL includes all tied rows, so every complaint's own outcome was landing inside its
own feature — the model was reading the answer. I also found the features changed between runs
because ties resolved by physical row order. The obvious fix, adding an ID tiebreak, turned out to be
incompatible with `RANGE` interval frames, so I ended up with three frame patterns chosen by what
each feature means — outcome rates lagged 60 days for resolution time, volume counts excluding only
the current day, and sequence features using the tiebreak. I verified each one against Postgres
rather than trusting the docs."*

### 1.5 Layer 4 — assembly and the materialized view

Stitch complaint-level fields + Layer 2 + Layer 3 + the label view into one row per complaint.
Enforce the grain contract with a uniqueness check on `complaint_id`. B-tree indexes on
`complaint_id` and `company_id` — Phase 3's per-request lookups need them.

Target **15–25 features**. Every feature needs a `feature_dictionary.md` entry (name, definition,
grain, business rationale, expected range, leakage note) or it doesn't ship.

**Expect** a multi-minute refresh at 4.8M rows. Note the runtime; you'll reference it when explaining
why the view is materialized. Materialized views go stale silently — write "REFRESH is manual now,
automated in Phase 3" in the README today.

### 1.6 Deliverables

ERD · DDL + migrations + `validation.sql` · master pipeline SQL with layer contracts ·
`feature_dictionary.md` · hand-verification queries in `tests/sql/` · `leakage.md` explaining the
point-in-time design and the `(date_received, complaint_id)` tiebreak convention.

---

## Phase 2 — Embeddings, Fusion Model, Evaluation

**Goal:** a fine-tuned transformer + tabular fusion model with an ablation proving both modalities
matter, plus pgvector similarity search.

### 2.1 pgvector embedding store

Enable the extension; add a vector column on the complaint table sized to the encoder's hidden
dimension. Batch-embed with the **base** pretrained encoder (not the fine-tuned classifier) so
vectors stay comparable across time. Record encoder name + version in a metadata column — dimension
mismatch fails loudly, *model* mismatch fails silently.

Exact nearest-neighbour is fine at this scale; add HNSW only if queries feel slow, and note the
recall-vs-speed tradeoff either way. Embedding cost is the reason to embed the *training subset*
first and backfill later if needed.

### 2.2 Training export — case-control sampling and the temporal split

**The sampling design, which is a decision and not a utility call:**

Keep **all 35,375 positives**, sample ~105k negatives → ≈140k rows at ~25% positive. Train with
sample weights (or recalibrate afterwards) so predicted probabilities return to the true 2.16% prior.
This is standard case-control design: it makes fine-tuning tractable on free-tier GPU without
throwing away a single positive.

**The split is temporal, never random.** Train on earlier complaints, test on later ones. Random
splits leak future-period statistics backward. Temporal honestly simulates deployment and *depresses*
your metrics — expect that, and say so proudly.

Write a versioned Parquet snapshot plus a manifest: row count, feature list, label rate, sampling
ratio, pipeline git commit. Preprocessing is fit on **train only**, persisted, and reused verbatim at
inference.

### 2.3 Fusion architecture

- **Text branch:** DistilBERT, fine-tuned, pooled representation. **This is the primary signal** —
  0.898 within-strata AUC on its own.
- **Tabular branch:** small MLP over the 15–25 standardized point-in-time features → compact vector
  (~64-dim).
- **Fusion head:** concatenate → dense + dropout → sigmoid.

**Balance trap:** a 768-dim text vector concatenated with 25 raw features lets text drown the tabular
signal by dimensionality alone. Project tabular up (and optionally text down).

**Training regime:** freeze the encoder for the first epoch(s) and train the tabular branch + head,
then unfreeze with discriminative learning rates (~2e-5 encoder / 1e-3 head). Handle residual
imbalance with a positively-weighted loss. Early stopping on validation PR-AUC. Log every run's
config and metrics.

**Build the cheap baselines first and beat them** — XGBoost on frozen embeddings + tabular is an
honest, strong baseline. Beating a credible baseline is worth more than any architecture diagram.

### 2.4 The ablation — the project's centerpiece

**You already have the numbers to beat.** Measured with TF-IDF + logistic regression and smoothed
point-in-time rate features, temporal split, 2024 held out:

| model | pooled AUC | pooled PR-AUC | within (Product×Issue) AUC |
|---|---|---|---|
| base rate | — | 0.017 | — |
| text only | 0.971 | 0.368 | 0.898 |
| metadata only | 0.971 | 0.362 | 0.940 |
| **fusion** | **0.979** | **0.438** | **0.945** |

**Report stratified metrics, not just pooled.** Pooled numbers are inflated by across-product and
across-company separation. Per-product PR-AUC and within-company AUC are the honest views, and
publishing both — with an explanation of the gap — is a better artifact than either alone. A sharp
interviewer *will* ask whether your AUC is inflated by between-entity variation; answer it in the
README before they ask.

**Why these metrics:** at a 2.16% positive rate accuracy is a lie. PR-AUC measures ranking where it
matters; recall-at-fixed-precision translates to the business sentence — *"at a precision the
compliance desk tolerates, we catch X% of complaints that end in a payout."* Practice saying it.

Supplement with error analysis: 5–10 cases fusion gets right that text-only misses, and vice versa.

### 2.5 Similarity search — serves both audiences

For any complaint, the 5 nearest historical complaints by embedding distance with their outcomes.
One endpoint, two framings: the company sees *"4 of 5 similar complaints ended in payout — staff
it"*; a consumer-facing view would see *"complaints like yours got relief 4 times out of 5."* Zero
extra infrastructure, and it is the interpretability story that lands with non-ML interviewers.

### 2.6 Expected-cost ranking layer — *optional, cuttable*

The model outputs a probability; a triage queue wants dollars. Rank by
**`expected_cost = P(monetary relief) × claimed_amount`**, extracting the claimed amount by regex
from the narrative and falling back to the product median when absent.

**Why it earns its place:** it fixes the ordering objection that a low-probability, high-stakes
complaint outranks a high-probability trivial one. A $200k student-loan disbursement failure at
P=0.012 scores $2,400 expected; a $10 prepaid-card recharge at P=0.285 scores $3. **800× separation,
correctly ordered** — without any severity label.

**Measured feasibility:** 18.5% of narratives contain a usable `$` figure overall, rising to 34–53%
inside the high-value products (student loan 34%, mortgage 42%, checking 48%, money transfer 53%).
Median claimed amounts are face-valid: vehicle loan $5,000, student loan $4,900, mortgage $4,800,
credit card $900.

**State the limitations:** the amount is *claimed*, not verified; 81.5% of complaints need the median
fallback. This layer is thin, transparent, and business-facing — keep it out of the model.

---

## Phase 3 — MLOps & Deployment

**Goal:** the system live behind a public URL, containerized, talking to managed Postgres, with CI/CD
and prediction logging.

### 3.1 FastAPI inference service

Four endpoints: `POST /predict` (company + product + issue + state + narrative → score, factors,
model version) · `GET /similar-complaints` · `GET /health` (includes DB connectivity) ·
`GET /model-info` (model version, snapshot id, feature list, **and the deployment population and
calibration prior**).

**The design decision to defend hardest:** the caller sends *identifiers and text*, never features.
The server fetches point-in-time features from the same view training used, so there is exactly one
feature implementation and it cannot drift. **State the trade-off** — a DB round-trip of latency per
request and coupling to DB availability. Senior engineers narrate trade-offs, not just choices.

Load model + tokenizer + fitted preprocessing once at startup. Connection-pool Postgres. Handle the
cold-start case (a company with no history) explicitly with the has-history flags rather than 500ing.

### 3.2 Containerization

One multi-stage image for the API; Postgres stays a separate service. CPU-only torch wheels and
multi-stage discipline keep the image from ballooning past 5 GB. Compose with two services, shared
network, credentials via env file, **healthcheck-based startup ordering** — the API must wait for
Postgres readiness, not just container start.

**Pitfalls:** using `localhost` as the DB host inside a container; forgetting `.dockerignore` and
shipping the 9 GB CSV into the build context; pinning nothing.

### 3.3 Cloud deployment

Managed Postgres (Supabase/Neon, pgvector supported, free tier) + container on Cloud Run (or AWS App
Runner — knowing they're interchangeable is the skill). Replay DDL and migrations on the managed
instance, load, refresh the view, backfill embeddings. **The same image runs locally and in prod;
only environment differs.**

Restrict the DB to TLS and create a **read-only role** for the API — SELECT on the feature view and
complaints, INSERT only on the prediction log. Least privilege, cheap, disproportionately impressive.

**Watch for:** free-tier Postgres pausing on inactivity; set billing alerts *before* creating
anything; budget a day of IAM friction on first deploy — everyone pays that tax once.

### 3.4 CI/CD

GitHub Actions: on every push — lint, tests (a handful of API tests plus your SQL validation checks),
build. On main — push to registry and redeploy. Build it incrementally: lint-only, then tests, then
build, then deploy. Four steps that always run beat twelve that are flaky.

### 3.5 Monitoring and the closed loop

Every prediction inserted into `prediction_log` (timestamp, complaint reference, score, latency,
model version). Drift checks are then *just more SQL* — a window-function query comparing this week's
score distribution to the trailing month's. Log asynchronously; a logging failure must never fail a
prediction. Automate the materialized-view refresh here, retiring the Phase 1 manual step.

This closes the loop with poetic economy: monitoring analytics land back in the same database,
analyzed with the same skill the project started with.

---

## Cross-cutting

### Repository structure

Top-level README leads with the architecture diagram, the one-line pitch, the ablation table, and the
live URL — a hiring manager gives you 90 seconds, so the proof goes above the fold.

```
db/        DDL, migrations, validation.sql
sql/       feature pipeline + tests/sql/
etl/       CSV → Postgres bulk load
training/  scripts + configs (notebooks quarantined in notebooks/)
api/
deploy/    Dockerfiles, Compose, CI workflows
docs/      data_profile.md, feature_dictionary.md, leakage.md, design_decisions.md
```

`design_decisions.md` records every "why X over Y" in this bible in your own words — including the
v1→v2 pivot. It is the single most senior-reading artifact in the repo.

### Risk register (v2, ranked by expected pain)

1. **Subtle leakage.** The label lives in the same table as the features. Frame boundaries, the
   `(date_received, complaint_id)` tiebreak, as-of smoothing priors, and the temporal split are all
   places it can creep in. *Smell test:* within-strata AUC materially above ~0.95 means hunt for it.
2. **Pooled metrics mistaken for real performance.** Pooled 0.979 vs within-strata 0.945 vs
   within-company 0.768 are three different claims. Report the honest one prominently.
3. **Scale friction.** 4.8M rows is ~100× v1's assumption. Bulk COPY, indexes, and materialization
   matter now; naive queries will be painfully slow.
4. **Scope creep in Phase 3** (Kubernetes, Terraform, feature stores). The stack above is complete;
   extras go in a "future work" section, which costs nothing and reads just as well.
5. **Cold-start/pause ruining a live demo.** Warm the DB and the container five minutes before; keep
   a local Compose fallback.

*Retired from v1:* weak synthetic correlations (no synthetic data) and the synthetic-data rabbit hole
(no generator).

### The narrative arc

**For ML/DL roles:** lead with Phase 2 — the fusion architecture, fine-tuning delta, the stratified
ablation, and error analysis.

**For data engineer/analyst roles:** lead with Phases 0–1 — star schema over 4.8M real rows, event-log
modeling, layered CTEs, point-in-time window functions, leakage discipline, and the SQL-native
monitoring loop.

**The pivot itself is a third story, and it may be the best one:** *"My first design needed synthetic
customers. I measured whether that was necessary, found the label was 95% determined by a metadata
field, and rebuilt the project around what the data could actually support."* Diagnosing a design
before building it is a more senior signal than any metric.

Same repo, three rehearsed openings. Write all three down now and refine them as artifacts
materialize — the project isn't finished when it deploys, it's finished when you can tell it.
