# TriageIQ — Agent Context

> **Read order for a fresh session:** this file → `Context/FACTS.md` (every number) →
> `Context/schema_explanation.md` (current phase) → `Context/TriageIQ.md` (full spec, when needed).
> **`Context/FACTS.md` is the only source of numbers.** If this file disagrees with it, FACTS.md wins.
> Regenerate it with `python training/canonical_facts.py`.
> **Keep this file updated as work progresses** — it is the handoff artifact between sessions.

Last updated: 2026-09-25 · DDL complete · staging loaded · next: Shivam writes the load queries

---

## 1. What this project is

**Predict whether an incoming CFPB consumer complaint will cost the company money**, so a compliance
desk can staff senior analysts against a 15-day regulatory response deadline.

```
complaint arrives → P(monetary relief) → high: senior analyst / low: template response
```

- **PostgreSQL** holds 4.8M real complaints and computes point-in-time company / issue features.
- **A fine-tuned DistilBERT** reads the complaint narrative.
- **A fusion model + FastAPI on Cloud Run** combines both, reading features from the same view
  training used.

**The thesis, measured on the shipped training artifact (F3):**

| | within (Product×Issue) | **within-company** |
|---|---|---|
| text only | 0.8905 | **0.7900** |
| metadata only | 0.9076 | 0.7463 |
| fusion | **0.9330** | **0.8034** |

Neither modality subsumes the other. Note the flip: holding product and issue fixed, metadata wins;
**inside one company's queue — the deployment view — text wins.** Never quote one frame as if it
were the other.

---

## 2. How to work with Shivam — read before responding

**Learning project, not a delivery contract.** He does a sub-task, reports back, gets reviewed,
gets the next step.

**Style**
- **Small steps.** One decision or concept at a time, so he can hold the context himself.
- **Crisp, simple language, no story-type responses.** Tie each step back to basics and to the core
  goal above.
- **Do not circle.** When he states a requirement, map every decision to it directly.

**Rigor**
- **Ask when in doubt; never assume.** If an instruction is ambiguous, ask — or state the
  interpretation explicitly before acting on it.
- **Every number states its frame** (F1 / F2 / F3 — see `FACTS.md`). Numbers come from `FACTS.md`
  or a fresh query, **never from memory**. Quoting stats without a frame caused a whole round of
  doc corrections and a re-evaluation of the entire project.
- **Verify before agreeing.** Check the data before accepting a design assumption — e.g. "each
  sub-product has one parent" was false for 87.5% of rows.
- **Never claim an action you haven't verified** (a file saved, a commit made). Both happened once.
- **Correct the reasoning, not just the conclusion.** If he reaches the right answer for the wrong
  reason (e.g. "surrogate keys are more readable"), say so — wrong reasons resurface later.

**Boundaries**
- **Do not hand over finished code for the curriculum**: SQL, Docker, schema design, DDL. Explain,
  review, ask hard questions. He draws the ERD and writes the DDL.
- Analysis / verification / profiling code on his behalf is fine and expected.
- He values honesty about limitations over polish; diagnosing a flaw is an explicit project goal.

**Machine:** MacBook M4, 16GB. Mac does SQL, data prep, and 1k-row training smoke tests on MPS.
**All real training runs go to Kaggle free tier (T4).**

**Git:** remote `git@github.com:Bajaj30/TriageIQ.git`, branch `main`. Commit + push after doc/decision
updates. Personal documents (`Context/*.docx`, `*.pages`) are gitignored — never commit them.

---

## 3. Ground rules — never violate without writing down why

1. **Sequencing:** SQL now, MLOps later. Each phase ends in a demo-able artifact.
2. **No JavaScript, ever.** Frontend is FastAPI's Swagger UI.
3. **Free tier or student laptop only.** No GPU bills.
4. **One source of truth for features.** All feature logic in SQL. Python never re-implements a
   feature. The central architectural claim.
5. **No leakage.** Every feature computable only from what existed at complaint receipt.
6. **Reproducible.** SEED=42, versioned snapshots, logged configs, code for every quoted number.

---

## 4. Repo map

```
CLAUDE.md                     this file
Context/FACTS.md              every number, three frames — generated, never hand-edit
Context/schema_explanation.md Phase 0.3 decisions, each tied to a concept   ← current work
Context/TriageIQ.md           full engineering spec (bible v2); §1.4a = verified window-frame rules
Context/WHAT_WHY.md           pitch and positioning
Context/interview.md          per-phase: what broke, how it was fixed
Context/audit.md              prompt for an independent audit
Context/audit_findings_2026-09-12.md   audit results + resolution status
Context/old_context/          v1 archives (synthetic-customer design) — do not delete
Learning/Phase0/              directions.md (learning guide) · learning_log.md (his notes)
Data/EDA.ipynb                profiling + v2 training-set build (Cell 8)
Data/docs/data_profile.md     dataset profile
Data/complaints.csv           9.2GB raw — gitignored
Data/data/interim/            meta.parquet · narratives.parquet · triageiq_training_v2.parquet — gitignored
training/verify_ablation.py   reproduces every baseline number
training/canonical_facts.py   regenerates FACTS.md
claude_agent/                 CLI agent on the Anthropic API (used for the audit)
docker-compose.yml            Postgres 16 + pgvector, host port **5433** (Postgres.app owns 5432)
sql/                          numbered SQL pipeline, run in pgAdmin — see sql/README.md
```

Not yet created: `api/`, `deploy/`, top-level `README.md`.

**Postgres:** container `triageiq-postgres`, database `triageiq`, user `triageiq`, `localhost:5433`,
password in `.env`. CSV mounted read-only at `/import/complaints.csv`. **Division of labour:** I do
infrastructure and dependencies; **Shivam writes every query** in `sql/`, I explain and review.

---

## 5. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0.1 | Docker + Compose, pgvector Postgres 16 | **Complete** — running on port 5433 |
| 0.2 | Source dataset + profiling | **Complete** — v2 training set built |
| 0.3 | **Schema + DDL** | **DDL done** — all tables created, 12/12 constraint tests pass |
| 0.4 | Bulk load | **Staging loaded** (17,355,295 rows). Next: Shivam writes `sql/02_load/` |
| 0.5 | Label as a SQL view | Not started |
| 1 | Layered CTE point-in-time pipeline | Not started |
| 2 | pgvector, fusion, stratified ablation | Not started — plan in §9 |
| 3 | FastAPI, Docker, Cloud Run, CI/CD, monitoring | Not started |

---

## 6. Phase 0.3 — schema decisions (full reasoning: `Context/schema_explanation.md`)

| # | decision |
|---|---|
| D1 | Narrative in its own **extension** table `complaint_narrative` (1,639,068 rows) — not a dimension |
| D2 | Outcome / label lives in `complaint_events`, never on the fact — leakage needs a deliberate join |
| D3 | `date_received` on the fact (point-in-time anchor) **and** in the event log |
| D4 | **Surrogate** integer keys on every dimension; id mapping assigned once, never regenerated |
| D5 | `dim_company (company_id, company_name, first_seen_in_window)` — thin; no counts or rates |
| D6 | Hierarchies = two tables; child **UNIQUE (parent_id, child_name)** — names repeat across parents |
| D7 | Issue and Product are **independent** — 55% of issues span several products |
| D8 | Renamed products map to **one canonical** `product_id` |
| D9 | NULL child → `'(not specified)'` member, never a NULL FK (inner joins drop NULLs silently) |
| D10 | Keep **all** F1 rows; never store a pre-computed ratio in place of rows |
| D11 | Both `product_id` and `sub_product_id` (and issue pair) on the fact — hot path |
| D12 | Split/renamed products **route by sub-product** (bottom-up), keyed on (raw_product, raw_sub_product) — 14 raw → 11 canonical, new taxonomy names |
| D13 | Crosswalk is a **table** (`product_crosswalk`, 12 rules seeded in DDL) |
| D14 | `date_received` is `DATE` — source has no time of day |
| D15 | `responded` event has **no date** — CFPB never records it; the 60-day lag is an assumption |
| D16 | Composite FKs make the database reject a sub-product under the wrong product |

**Open, decide before DDL:**
1. **Where the D12 product crosswalk lives** — mapping table in Postgres vs load-time transformation.
2. **`Submitted via`** — 1 value in F2, 5 in F1. Dead for the model, not for volume features.
3. **`Tags`** — 94.49% null in F1, 87.82% in F3. Drop or sparse flag.
4. **`Date sent to company`** — missing from `meta.parquet`. Rebuild cache or backfill at load.
5. **NULL outcomes** — 19 in F1; label view must **exclude**, not count as 0.

---

## 7. The v2 pivot — history, settled, do not re-litigate

v1 assumed a **synthetic** customer/transaction world. **Dead** — CFPB has no consumer identity.

**Decisions locked in:**
1. **No synthetic data.** 100% real, public, verifiable.
2. **Entity = company / issue**, not customer. Point-in-time window features survive.
3. **Label = `Closed with monetary relief`** — company cost, not consumer harm (no severity label
   exists; documented as a limitation).
4. **All products, no rule tier.** Text ranks complaints *within* low-payout products too.
5. **Serving the company.** Consumer view comes free via precedent retrieval — same model.
6. **`any_relief` rejected** — metadata-dominated, would make the transformer decorative.

*The exploration measurements behind these (Product-alone AUC 0.957, Company-alone 0.976, etc.)
were taken on various subsets and are **historical**. Current numbers: `FACTS.md` only.*

v1 archive: `Context/old_context/TriageIQ_v1_archive.md`. **Do not delete.**

---

## 8. Traps — active

1. **Window frames — three patterns, verified on PostgreSQL 18.4** (`TriageIQ.md` §1.4a).
   `date_received` is day-granularity; 43.46% of company-days hold >1 complaint. The **default frame
   includes the current row's own label**; without a tiebreak results change between runs; adding
   `complaint_id` to `ORDER BY` is **rejected** by `RANGE` interval frames; `ROWS` is not a time window.
   - outcome rates → `ORDER BY date_received RANGE BETWEEN UNBOUNDED PRECEDING AND '60 days' PRECEDING`
   - volume counts → `ORDER BY date_received RANGE BETWEEN '90 days' PRECEDING AND '1 day' PRECEDING`
   - sequence (LAG, rank) → `ORDER BY date_received, complaint_id`
2. **Two-tier rule.** Features computed over F1 (4,826,564); training on F3. The 3.2M no-narrative
   rows hold 42% of all payout outcomes.
3. **Target encoding must never be fitted on case-control-resampled data** — it cost the metadata
   branch 0.032 AUC. Entity rates come from F1 in Postgres.
4. **Post-intake columns are never features:** `Date sent to company`, `Company response to
   consumer`, `Timely response?`, `Company public response`.
5. **Three evaluation frames, three claims** — pooled 0.9634 / within-strata 0.9330 / within-company
   0.8034 (fusion, F3). Report the honest one; explain the gap.
6. **Recalibration is mandatory** — case-control keep-fraction 0.104639 → logit offset −2.2572.
7. **721 narratives straddle splits** (3,120 rows, 1.03%, 3 positives) — dup filter isn't group-aware.
   Fix before Phase 2: assign each narrative hash to one split.
8. **Undeclared dependency:** scikit-learn is required but not in `pyproject.toml`.

---

## 9. Phase 2 plan — decided

- **Encoder: DistilBERT**, revisit only if measurement says so. Cheaper upgrade path if needed:
  DistilRoBERTa (same speed, better pretraining) → DeBERTa-v3-base (strongest at 512).
- **`max_length=512`** (DistilBERT's hard ceiling). Length correlates with the label — positive rate
  peaks at 512–1k tokens (39.6%) then declines; 512 reads ~78% of the median doc in that band.
  First ablation: 256 vs 512. Try head+tail truncation before any long-context model.
- **Long-context fallback only if 256→512 gain is large:** jina-embeddings-v2-small (~33M, 8192 ctx).
- **Training speed:** `group_by_length=True` is the big win (2.23× fewer tokens; dynamic padding
  alone does *nothing* on this data), `fp16` on T4, freeze encoder epoch 1, early stop on val PR-AUC,
  ≤3 epochs, develop on a 10k subset.

---

## 10. Guardrails

- Every feature computed **as-of complaint receipt**, never as-of today.
- Window frames **exclude the current row** — the label lives in the same database.
- Smoothing priors must **also** be as-of date.
- Split is **temporal**, never random.
- Preprocessing fit on train only, persisted, reused verbatim at inference.
- The API accepts **identifiers + text, never features**. State the trade-off.
- Aggregate-then-join. **Check row count after every join.**
- Smell test: within-strata AUC materially above ~0.95 → hunt for the leak.

---

## 11. Optional, cuttable — expected-cost ranking (Phase 2.6)

`expected_cost = P(monetary relief) × claimed_amount` (amount regex-extracted, product-median
fallback). A $200k claim at P=0.012 → $2,400; a $10 claim at P=0.285 → $3. Recovers magnitude
without a severity label. Amount is *claimed*, not verified; ~81% of complaints need the fallback.
