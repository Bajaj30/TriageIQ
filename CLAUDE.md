# TriageIQ — Agent Context

> **`Context/FACTS.md` is the single source of truth for every number.**
> If this file disagrees with it, FACTS.md wins. Regenerate with `training/canonical_facts.py`.

> **Read this instead of `Context/TriageIQ.md` for orientation.** The bible (v2) is the authoritative
> spec; this file is the working state, the decisions already made, and the traps.
> **Keep this file updated as work progresses** — it is the handoff artifact between agent windows.

Last updated: 2026-09-11 · Phase 0.2 complete, training set built · Phase 0.3 (schema) in progress

---

## 1. What this project is

**Predict whether an incoming CFPB consumer complaint will cost the company money**, so a compliance
desk can staff senior analysts against a 15-day regulatory response deadline.

```
complaint arrives → P(monetary relief) → high: senior analyst / low: template response
```

Three systems, one pipeline:
- **PostgreSQL** holds 4.8M real complaints and turns them into point-in-time entity features
  (company / issue relief rates, volume trends) via layered SQL.
- **A fine-tuned DistilBERT** reads the complaint narrative — this is the primary signal.
- **A fusion model + FastAPI on Cloud Run** combines both, pulling features live from the same view
  training used.

**The thesis, measured on the shipped artifact:** within (Product × Issue) strata, text alone gets
**0.8905** AUC, metadata alone **0.9076**, fusion **0.9330**. Neither modality subsumes the other.
All numbers live in `Context/FACTS.md` — that file wins over this one.

---

## 2. v2 pivot — read this before touching anything

v1 assumed real ticket text + a **synthetic** transactional world (customers, orders, payments,
refunds) with an escalation label from a generated event log. **That design is dead.**

**Why:** CFPB has **no consumer identity**. Every complaint is anonymous, so customer-level features
(lifetime spend, ticket velocity, prior escalations) have nothing to attach to.

**What we measured before deciding** (temporal split, train ≤2023 / test 2024):

| finding | number | consequence |
|---|---|---|
| monetary relief across all products, `Product` alone | AUC 0.957 | degenerate — label nearly determined by an intake field |
| same, `Company` alone | AUC 0.976 | ditto |
| pooled vs **within-company** fusion AUC | 0.835 → 0.768 | pooled metrics inflated by between-company variation |
| **text only, within (Product×Issue)** | **AUC 0.898** | narrative carries real independent signal |
| fusion, same strata | **AUC 0.945** | fusion justified |
| `any_relief` label, text vs metadata | 0.628 vs 0.702 | **rejected** — metadata-dominated, kills the NLP thesis |
| monetary-relief positives | 35,375 (2.16%) | sparse rate, ample count |

**Decisions locked in:**
1. **No synthetic data.** 100% real, public, verifiable end to end.
2. **Entity = company / issue, not customer.** Point-in-time discipline and the whole window-function
   curriculum survive; only the partition key changes.
3. **Label = `Closed with monetary relief`.** "Did this cost the company money."
4. **No product filter, no rule tier.** An earlier draft filtered to five "money-bearing" products and
   template-routed the rest. **Wrong** — text-only AUC is 0.809 within Mortgage, 0.771 within Vehicle
   loan, so serious complaints in low-payout products are still rankable by narrative. The rule tier
   would have discarded exactly those.
5. **Target is company cost, not consumer harm.** CFPB has no severity label; any severity model would
   be unvalidatable. Documented as a limitation, not hidden.
6. **Serving the company, not the consumer.** "Get a senior analyst" is a company staffing decision.
   The consumer-facing view comes free via §2.5 precedent retrieval — *same model, same label,
   different framing.* Consumer-facing does **not** imply severity; that pairing was a wrong turn.

v1 is archived at `Context/old_context/TriageIQ_v1_archive.md`. **Do not delete it** — the v1→v2 delta is itself
a portfolio artifact and an interview story.

---

## 3. Ground rules — never violate without writing down why

1. **Sequencing:** SQL now, MLOps later. Each phase ends in a demo-able artifact.
2. **No JavaScript, ever.** Frontend is FastAPI's Swagger UI.
3. **Free tier or student laptop only.** No GPU bills.
4. **One source of truth for features.** All feature logic in SQL. Python never re-implements a
   feature. The central architectural claim.
5. **No leakage.** Every feature computable only from what existed at complaint receipt.
6. **Reproducible.** SEED=42, versioned snapshots, logged configs.

---

## 4. How to work with Shivam

**Learning project, not a delivery contract.** Pattern: he does a sub-task, reports back, gets
reviewed, gets the next step.

- **Do not hand over finished code for something he's meant to learn.** SQL, Docker, and schema design
  are the curriculum. Explain, review, ask hard questions.
- Writing throwaway *analysis* code (verification, profiling, ablation probes) on his behalf is fine
  and expected — that's not the curriculum.
- **Verify claims against the artifact on disk before agreeing.** Several "red flags" so far were
  measurement artifacts, not data problems.
- **Do not circle.** When he states a requirement, map every design decision to it directly. He will
  call out hedging and repetition, and he's right to.
- He values honesty about limitations over polish. Diagnosing a flaw is an explicit project goal.

---

## 5. Repo map

```
Context/   TriageIQ.md (bible v2) · WHAT_WHY.md (pitch v2) · diagram.png
Context/old_context/  v1 archives — TriageIQ_v1_archive.md, WHAT_WHY_v1_archive.md, data_profile_placeholder.md
Learning/Phase0/  directions.md (sub-task guide) · learning_log.md
Data/      EDA.ipynb · complaints.csv (9.2GB, gitignored)
Data/data/interim/  meta.parquet · narratives.parquet · triageiq_training_v2.parquet + manifest
Data/docs/ data_profile.md (v2, complete)
pyproject.toml  Poetry, Python 3.11. pandas/numpy/pyarrow/matplotlib/langdetect/ipykernel/sklearn
```

Not yet created: `db/`, `sql/`, `etl/`, `training/`, `api/`, `deploy/`, top-level `README.md`.

---

## 6. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0.1 | Docker + Compose, `pgvector/pgvector:pg16` | **Partial** — lecture watched, no compose file exists |
| 0.2 | Source dataset + profiling | **Complete** — v2 training set built, profile written |
| 0.3 | **Star schema + DDL** | **NEXT** |
| 0.4 | Bulk load 4.8M rows (replaces synthetic generator) | Not started |
| 0.5 | Label as a SQL view | Not started |
| 1 | Layered CTE point-in-time pipeline | Not started |
| 2 | pgvector, fusion, stratified ablation | Not started |
| 3 | FastAPI, Docker, Cloud Run, CI/CD, monitoring | Not started |

---

## 7. The dataset — CFPB Consumer Complaints

Real, US-government-published, redistributable.

| | |
|---|---|
| raw | 17,355,295 rows / 9.2 GB |
| with narrative | 3,843,057 (22%) |
| working window | 2022-01-01 → 2024-12-31 |
| complaints in window | **4,826,564** |
| with narrative in window | **1,639,068** |
| monetary-relief positives | **35,375 (2.16%)** |

### Gate check — PASSED, data is real

| metric | raw | note |
|---|---|---|
| exact-dup rate | 19.8% | drops to 0.3% after cluster capping |
| sentence-length CV | 0.94 | <0.35 suspicious |
| TTR | 0.065 | <0.08 suspicious |
| top opener | 3.7% | FCRA boilerplate — *evidence for* real humans |

**Two false alarms — do not re-litigate.** (a) "placeholders 1→15" is a regex bug: `\{[a-z_]+\}` with
`case=False` matches `{XXXX}`, CFPB's currency-redaction convention. Zero real LLM placeholders.
(b) "40+ char words" are URLs — 103 rows (0.26%) in the sampled artifact, 0 materially corrupted.

### Column reality check — read before writing DDL

| column | verdict |
|---|---|
| `Consumer complaint narrative` | **The primary signal.** 0.898 within-strata AUC alone |
| `Complaint ID` | **Verified unique PK** across all 4,826,564 window rows |
| `Date received` | **Day granularity only** — see the tiebreak trap below |
| `Date sent to company` | **100% populated** → real event log. Post-intake = leakage if used as a feature |
| `Product` / `Sub-product` | **14 / 58** in window (21 / 85 is the all-time figure — do not use) |
| `Issue` / `Sub-issue` | **93 / 212** in window; sub-issue 2.53% null (F1) / 4.17% (F2) |
| `Company` | 4,950 in window; only 53 in name-collision groups → raw name usable as dim key |
| `State` | **61** in window, 0.23% null |
| `Company response to consumer` | **The label source.** Post-intake — never a feature |
| `Timely response?` | **99.62%** Yes (F1). Post-intake — never a feature |
| `Tags` | **DROPPED** — 94.49% null in F1, but **87.82% in the training set**; revisit if a sparse flag is wanted |
| `Submitted via` | Single-valued in F2, but **5 values in F1** (Phone 67,953 · Referral 34,071 · Postal 17,873). Dead for the model, NOT for company-volume features — decide deliberately |
| `ZIP code` | **DROPPED** — 19% redacted, thousands of levels, `State` alone is only AUC 0.549 |

### Measured baselines to beat (TF-IDF + LR, temporal split, 2024 held out)

| model | pooled AUC | pooled PR | within (Product×Issue) AUC |
|---|---|---|---|
| base rate | — | 0.028 | — |
| text only | 0.9542 | 0.3551 | 0.8905 |
| metadata only | 0.9533 | 0.3414 | 0.9076 |
| **fusion** | **0.9634** | **0.4073** | **0.9330** |

Measured on the **shipped v2 artifact** (`training/verify_ablation.py`). An earlier table quoted
0.898 / 0.940 / 0.945 — those came from a 500k random sample with a *different* split and are not
the target. **Beat 0.9330.**

Per-product text-only AUC: credit card 0.833 · mortgage 0.809 · vehicle loan 0.771 · checking 0.754 ·
debt collection 0.879 · credit reporting 0.932.

---

## 8. Traps — active, carry forward

1. **Window frames — three patterns, verified on PostgreSQL 18.4.** `Date received` is
   day-granularity and 43.5% of company-days hold >1 complaint (max 4,245). Tested consequences:
   the **default frame includes all tied rows plus the current row**, so a complaint's own outcome
   lands in its own feature (all five same-day test rows returned 2/5); and without a tiebreak the
   same query on the same data returns different values when physical row order changes
   (`NULL,1.0,1.0,0.667,0.5` → `0.25,0,0,0,NULL`). **There is no single correct frame** — adding
   `complaint_id` to `ORDER BY` is rejected by `RANGE` interval frames
   (`ERROR: RANGE with offset PRECEDING/FOLLOWING requires exactly one ORDER BY column`), and `ROWS`
   is not a time window (across an 8-month gap it reported 3 prior vs `RANGE '90 days'` = 0). Use:
   - **outcome rates** → `ORDER BY date_received RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING`
     (excludes the day *and* CFPB's response lag — an outcome isn't knowable for up to 60 days)
   - **volume counts** → `ORDER BY date_received RANGE BETWEEN '90 days' PRECEDING AND '1 day' PRECEDING`
   - **sequence (LAG, rank)** → `ORDER BY date_received, complaint_id` (tiebreak required here, no RANGE)

   Also: `complaint_id` is stored as **text** — text sort ≠ numeric sort (`'10000000' < '8688670'`),
   cast to `bigint`. It is a deterministic tiebreak, **not** a clock (Spearman 0.99998 with date, but
   99.9% of consecutive days have overlapping ID ranges). Use named `WINDOW w AS (...)` clauses so ten
   features can't drift to nine different frames. `count(*)`=0 vs `avg()`=NULL distinguishes "no
   history" from "zero rate" — emit both. Full write-up with evidence: `Context/TriageIQ.md` §1.4a.

2. **Two-tier rule: feature population ≠ training sample.** Aggregates computed over all 4,826,564
   complaints (including the ~3.2M with no text — they still count toward company volume). Training
   set is a case-control sample of the rows that *have* text. Compute a 90-day company count on a 20%
   sample and you get ~70 instead of ~350 → training/serving skew.
3. **Post-intake columns are label material, never features:** `Date sent to company`,
   `Company response to consumer`, `Timely response?`, `Company public response`.
4. **Pooled metrics lie.** Pooled 0.979 / within-strata 0.945 / within-company 0.768 are three
   different claims. Report the honest one prominently and explain the gap.
5. **Training set is built (v2).** `Data/data/interim/triageiq_training_v2.parquet` — 301,460 rows.
   Temporal split applied **before** sampling; case-control on train only.
   | split | period | rows | pos | rate |
   |---|---|---|---|---|
   | train | <2023-10-01 | 71,460 | 17,865 | 25.00% (case-control, ALL positives kept) |
   | val | 2023-10-01..12-31 | 80,000 | 3,102 | 3.88% (natural) |
   | test | 2024 | 150,000 | 4,164 | 2.78% (natural) |

   **Recalibration is mandatory:** negative keep-fraction 0.104639 → apply logit offset
   **−2.2572** to return predictions to the true prior. val/test are left at natural prevalence
   because PR-AUC is base-rate sensitive.
   No product cap — mix is natural (credit reporting ~62%). Quality filters retain 98.5% of
   positives while cutting 33% of rows, lifting the eligible base rate 2.16% → 3.15%.
   Base rate drifts **down** (2022 3.38% / 2023 3.49% / 2024 2.79%) — test is genuinely harder.
6. **EDA notebook is v2-current.** Cells 8, 9, 10 rewritten; no stale v1 references remain.
   Cells 19–22 replaced in place; user-added cells (placeholder inspection, long-word check) preserved.
   `data_profile.md` regenerated, **all TODOs resolved**.
7. **Notebook hygiene** (low priority): two full 9GB CSV passes; `norm()`/`sents()` defined in Cell 3b
   but used in Cells 4/10; `datetime.utcnow()` deprecated; `groupby.apply` FutureWarning in Cell 8.

---

## 9. Guardrails to check against later

- Every feature computed **as-of complaint receipt**, never as-of today.
- Window frames must **exclude the current row** — the label lives in the same table.
- Smoothing priors (`(successes + K·prior)/(n + K)`, K≈50) must **also** be as-of date.
- Train/test split is **temporal**, never random. Expect worse numbers and say so proudly.
- Case-control sampling requires **recalibrating** predictions back to the 2.16% prior.
- Preprocessing fit on train only, persisted, reused verbatim at inference.
- The API accepts **identifiers + text, never features**. State the trade-off (DB round-trip latency,
  coupling to DB availability) rather than hiding it.
- Aggregate-then-join, never join-then-aggregate. **Check row count after every join.**
- Smell test: within-strata AUC materially above ~0.95 → hunt for the leak.

---

## 10. Optional, cuttable — expected-cost ranking (Phase 2.6)

Rank the queue by `expected_cost = P(monetary relief) × claimed_amount`, regex-extracting the amount
from the narrative with a product-median fallback. Fixes the ordering objection: a $200k student-loan
disbursement failure at P=0.012 → $2,400 expected; a $10 prepaid recharge at P=0.285 → $3. **800×
separation, correctly ordered, with no severity label.**

Feasibility measured: 18.5% of narratives carry a usable `$` figure overall, 34–53% in high-value
products. Median claimed amounts are face-valid (vehicle $5,000 · student loan $4,900 · mortgage
$4,800 · credit card $900). Limitations: amount is *claimed*, not verified; 81.5% need the fallback.
Keep this layer outside the model — thin, transparent, business-facing.
