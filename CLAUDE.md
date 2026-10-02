# TriageIQ — Agent Context

> **Read order for a fresh session:** this file → `Context/FACTS.md` (every number) →
> `Context/schema_explanation.md` (current phase) → `Context/TriageIQ.md` (full spec, when needed).
> **`Context/FACTS.md` is the only source of numbers.** If this file disagrees with it, FACTS.md wins.
> Regenerate it with `python training/canonical_facts.py`.
> **Keep this file updated as work progresses** — it is the handoff artifact between sessions.

Last updated: 2026-10-01 · v3 baselines done · fusion notebook `training/fusion_distilbert.ipynb` passes the Mac test · next: Kaggle smoke (10k)

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

**The thesis, measured on training set v3** (test = 150,000 complaints from 2024, 2.31% payouts;
TF-IDF + logistic regression; `training/test.ipynb`; FACTS.md "Baselines on training set v3"):

| | within (Product×Issue) | **within-company** |
|---|---|---|
| text only | 0.8916 | **0.7956** |
| features only (19 SQL inputs) | 0.9276 | 0.7500 |
| fusion | **0.9457** | **0.8115** |

*(v2, historical: 0.8905 / 0.9076 / 0.9330 and 0.7900 / 0.7463 / 0.8034 — a different test set.)*

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
- **Division of labour (current, agreed 2026-09-25):** I write infrastructure, DDL and the `02_load/`
  queries — **one file per "go N"**, with reasoning in the SQL comments. He reviews each before the
  next. Chat replies stay short and only add what the comments don't say.
- **From Phase 0.5 on (agreed 2026-09-28): back and forth.** He writes some queries himself (review them
  properly — correct the reasoning, not just the SQL), I write others on request. He picks per file.
- Analysis / verification / profiling code on his behalf is fine and expected.
- **Blog log (standing duty):** he is writing a blog about the project. Whenever something blog-worthy
  happens — an idea discarded (and why), a realisation, textbook theory used in practice, a SQL
  technique — add a line to `Context/blog_log.md`, with its frame on every number.
  **Write it for readers with little tech knowledge** (his standing rule, also for the README): plain
  words, everyday comparisons, intuitive and interesting; jargon only as a small *(tech: …)* tag;
  frames described in words ("all complaints", not "F1").
  **Future deliverable (promised 2026-09-28):** a good-looking, working **web-page blog** built from
  `blog_log.md` — plan for it when the project nears its end. Must include an interactive
  **snowflake-schema visual**. Diagrams live ONLY in `README.md` (§5 = snowflake, journey,
  track-record steps); `blog_log.md` §8 lists what to reuse. Never duplicate a diagram.
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
README.md                     public, plain-language (non-technical reader), Mermaid diagrams.
                              **Fill its ⏳ placeholders as phases finish; numbers must match FACTS.md.**
Context/FACTS.md              every number, three frames — generated, never hand-edit
sql/03_features/feature_dictionary.md   every feature: meaning, frame, model input yes/no and why
Context/schema_explanation.md Phase 0.3 decisions, each tied to a concept   ← current work
Context/TriageIQ.md           full engineering spec (bible v2); §1.4a = verified window-frame rules
Context/WHAT_WHY.md           pitch and positioning
Context/interview.md          per-phase: what broke, how it was fixed
Context/blog_log.md           blog raw material: discarded ideas, realisations, theory used, SQL — keep adding
Context/audit.md              prompt for an independent audit
Context/audit_findings_2026-09-12.md   audit results + resolution status
Context/old_context/          v1 archives (synthetic-customer design) — do not delete
Learning/Phase0/              directions.md (learning guide) · learning_log.md (his notes)
Data/EDA.ipynb                profiling + v2 training-set build (Cell 8)
Data/docs/data_profile.md     dataset profile
Data/complaints.csv           9.2GB raw — gitignored
Data/data/interim/            meta.parquet · narratives.parquet · triageiq_training_v2.parquet — gitignored
training/verify_ablation.py   reproduces every baseline number
training/export_training_set.py   copies v_training_export → triageiq_training_v3.parquet + manifest (moves rows only)
                              NOTE: FACTS.md 'F3' and all baselines are still the v2 artifact — re-measure on v3
training/KAGGLE_SETUP.md      upload v3 Parquet + manifest as a private Kaggle Dataset; GPU notebook; Cell 1 checks sha256 + counts vs manifest, confirms T4
training/fusion_distilbert.ipynb   Phase 2 model: DistilBERT + 19 SQL inputs. RUN = mac (512 rows) / smoke (Kaggle
                              10k) / full. Saves model.pt, preprocessing.json, metrics.json, test predictions.
                              Mac: run with USE_TF=0 (conda env's TensorFlow is broken); test pass on CPU.
training/test.ipynb           v3 baselines (TF-IDF + LR) — the bar: within-company 0.8115
training/canonical_facts.py   regenerates FACTS.md, canonical_facts.json AND sql/02_load/00_expected_facts.sql
                              (generated — never hand-edit). It re-implements the load rules in pandas; the
                              SQL load must match it (11_validate reads expected('key')). Change a crosswalk
                              rule in BOTH places, or validation fails — on purpose.
docker-compose.yml            Postgres 16 + pgvector, host port **5433** (Postgres.app owns 5432)
sql/                          numbered SQL pipeline, run in pgAdmin — every folder has a log.md
                              (1–2 lines per file). **Update the log.md whenever a file is added or done.**
```

Not yet created: `api/`, `deploy/`.

**Postgres:** container `triageiq-postgres`, database `triageiq`, user `triageiq`, `localhost:5433`,
password in `.env`. CSV mounted read-only at `/import/complaints.csv`. **Division of labour:** I do
infrastructure, dependencies and DDL. **Load queries (`sql/02_load/`): one file at a time, only when
Shivam says go** — I write it, he reviews and understands it, then the next. Features (window/CTE
work) come after all tables are loaded.

---

## 5. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0.1 | Docker + Compose, pgvector Postgres 16 | **Complete** — running on port 5433 |
| 0.2 | Source dataset + profiling | **Complete** — v2 training set built |
| 0.3 | **Schema + DDL** | **DDL done** — all tables created, 12/12 constraint tests pass |
| 0.4 | Bulk load | **Complete** — fact 4,826,564 · narrative 1,639,068 · events 14,479,692 · validated 21/21 · 6 indexes (company×issue lookup 0.19 ms, index-only); 31,378 company×issue pairs (F1) |
| 0.5 | Label as a SQL view | **Complete** — `v_label`: 4,826,564 rows · paid 60,952 · untimely 2,785 · 19 unknown → 0 · base rate 1.26% (F1); reads the partial index, 1 s |
| 1 | Layered point-in-time pipeline | **Complete** — `sql/03_features/` 01–08: `mv_features` (4,826,564 rows × 40 cols, ~80 s build) → `v_model_input` (**19 inputs**, see `sql/03_features/feature_dictionary.md`); recount tests + leak test pass (`sql/tests/`) |
| 2 | pgvector, fusion, stratified ablation | **Started** — v3 uploaded as a private Kaggle Dataset; Cell 1 smoke test passed (sha256 `16e3c4127dd1…`, counts match, 2× T4). Next: re-baseline on v3 (cheap, CPU), then DistilBERT |
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
| D17 | Renamed **issue** → one canonical `issue_id` via `issue_crosswalk` (1 rule, 337,252 F1 rows rerouted); fact keeps `raw_issue` |

**Still open (none block the load):**
1. **`Submitted via`** — **CLOSED (2026-09-30): not a model input.** 1 value (Web) among complaints with
   text (F2) — constant on every training row. Stays in the fact table; left out of `v_base`.
2. **`Tags`** — kept as a nullable fact column. 94.49% null in F1, 87.82% in F3. **NULL = "no tag", not
   missing** (a form checkbox, known at intake). Payout rate F1: no tag 1.06% · Servicemember 2.43% ·
   **Older American 10.08%** · both 8.54%. Holds within product (credit card 26.41% vs 13.81%; credit
   reports 0.74% vs 0.04%) — not just mix. **DECIDED (2026-09-29): encode it — as two 0/1 flags**
   (`is_older_american`, `is_servicemember`) computed in `02_base`, not a 4-way one-hot: the value is a
   list, so 'both' must share what each flag learns. No schema change — a view reads the column.
3. **NULL outcomes** — 19 in F1. **DECIDED (Shivam, 2026-09-29): label 0**, like untimely. 8 have text;
   1 is in the shipped training set (test) and already has y = 0. The events table still stores NULL
   (raw truth); only the label view maps it to 0. Every complaint now has a label: 4,826,564 rows.
4. **`Untimely response`** — 2,785 in F1: the company **never answered** — no final outcome exists, no public
   response. (Different from *late*: 18,374 late answers, 15,589 still closed normally, 637 with money.)
   Almost all tiny companies: <10 complaints → 13.27% untimely; 1k+ complaints → 21 of 4.6M.
   **DECIDED (Shivam, 2026-09-28): label 0** — no money left the company, and the target is company cost.
   (My proposal to exclude was rejected.)

*Resolved:* crosswalk location → D13 (a table); `Date sent to company` → loaded straight from the CSV.

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
5. **Three evaluation frames, three claims** — pooled 0.9713 / within-strata 0.9457 / within-company
   0.8115 (fusion, v3). Report the honest one; explain the gap.
6. **Recalibration is mandatory** — case-control keep-fraction 0.104639 → logit offset −2.2572.
7. **721 narratives straddle splits** (3,120 rows, 1.03%, 3 positives) — dup filter isn't group-aware.
   Fix before Phase 2: assign each narrative hash to one split.
8. **Undeclared dependency:** scikit-learn is required but not in `pyproject.toml`.
9. **A global average is a credit-reporting average.** Credit reporting is 83.2% of F1 rows but 3.3% of
   payouts, so the global rate (1.26%, F1) is mostly its number. Smooth entity rates toward the
   **product** rate, not the global one. **K measured (2026-10-01, `05a_choose_k.sql`, tuning period
   Oct–Dec 2023, F1):** company × issue, history < 200 — AUC K=0 0.8690 · K=5 0.8901 · K=50 0.8754 ·
   K=500 0.8495; Brier best at K=5. Flat from 2 to 7. **DECIDED (Shivam, 2026-10-01): K = 5 — with a
   grain of salt:** (a) measured on each rate ALONE, not inside the fusion model — re-check K in the
   Phase 2 ablation; (b) one quarter of tuning data (Oct–Dec 2023); (c) differences are small overall
   (0.9777 vs 0.9769 at K=50, all complaints) — the gain is mainly for small-history pairs. K lives in
   ONE place, table `feature_params` — changing it is one UPDATE, never an edit to the view.
10. **Sub-issue changed meaning in Aug 2023.** All 122,207 missing sub-issues (F1) are structural, none
    skipped: 45 issues never have one (79,614); 3 depend on product — none under Payday (5,334); and
    **4 mortgage/payment issues got sub-issues only with the Aug-2023 form change (37,259)**. For those 4,
    `(not specified)` means "filed before Aug 2023": train (<2023-10) mostly sees it, test (2024) almost
    never. A sub-issue feature there encodes the date — use issue-level features; decide in Phase 1.
    **Bigger: Aug-2023 also RENAMED an issue.** 'Problem with a credit reporting company's investigation…'
    → 'Problem with a company's investigation…' on 2023-08-25 — same products, same 5 sub-issues:
    **893,566 complaints (18.5% of F1)**. Unfixed, its company×issue history resets 5 weeks before val.
    Plus 4 before-only and 14 after-only small issues (≤ 3,980 each). **Not a leak** (known at receipt) —
    a history reset + shift. **Fixed by D17** (issue crosswalk, 2026-09-28). The small ones and the 4
    sub-issue cases are still open → smoothing toward the parent rate, Phase 1.

12. **Training set v3 (2026-10-01) — rules chosen by me on Shivam's delegation; revisit after training.**
    Start 2022-04-01 (warm-up) · ≥20 real words (one rule replaces min-words + ≤30% blanks) · one text, one
    split (first appearance; later copies dropped, never moved) · cap 25 copies (v2 code DROPPED whole 26+
    clusters — contradicted its own docs) · train all payouts + 3× · val 80k · test 150k · seed 42.
    Result: train 62,940 (15,735 payouts) · val 80,000 (3.50%) · test 150,000 (2.31%) · **offset −2.4165**
    (keep-fraction 0.0892 — v2's −2.2572 no longer applies). Rule 4 dropped 106,942 complaints / 9 payouts,
    the cap 195,545 / 14: repeated templates almost never pay (unique texts 3.84% vs copies ≤0.05%).
    Idea for later: an as-of 'identical text seen before' count is a legit, likely strong feature.
    Heavy queries: `SET max_parallel_workers_per_gather = 0` — parallel hashes overflow the 1 GB shm_size.
11. **Sort memory.** Default `work_mem` 4MB made window sorts over 4.8M rows spill to disk (28 GB temp,
    11+ min). Set `ALTER DATABASE triageiq SET work_mem = '256MB'` (in `12_indexes.sql`): same check 16 s.
    Docker VM has 8 GB — don't raise much further; a query can hold several sorts at once.
---

## 9. Phase 2 plan — decided

- **Encoder: DistilBERT**, revisit only if measurement says so. Cheaper upgrade path if needed:
  DistilRoBERTa (same speed, better pretraining) → DeBERTa-v3-base (strongest at 512).
- **`max_length=512`** (DistilBERT's hard ceiling). Length correlates with the label — positive rate
  peaks at 512–1k tokens (39.6%) then declines; 512 reads ~78% of the median doc in that band.
  **Measured 2026-09-28** (DistilBERT tokenizer, 20,000-narrative random sample of F2): 1.24 tokens/word
  median (p90 1.51; XXXX redactions push it up: 1.28 vs 1.17) → 512 tokens ≈ **410 words** (≈ 340 worst
  10%). Fit fully: 72.7% @256 · **91.8% @512** · 98.1% @1024. Tokens p50 149, p99 1,341.
- **512 is the baseline — no 256 run (Shivam, 2026-09-28).** His concern: long complaints matter
  (8.2% of the sample exceed 512, median 729 tokens). Order of attack:
  1. Collapse CFPB redactions (`XX/XX/XXXX`, `XXXX` runs → one special token each) — keeps meaning;
     70.3% of F2 narratives contain XXXX; alone it makes 18.2% of the long ones fit. *Proposed.*
     Cost today: `XXXX` = 2 tokens, a redacted date = 6; **15.5% of all tokens are blanks** (20k F2
     sample); 20.2% of complaints are ≥20% blanks, 8.6% ≥40%. Collapse to typed markers ([DATE],
     [REDACTED]) — don't delete: where and how many blanks appear is itself signal.
     **Where:** one SQL function `clean_narrative(text)` — the training export AND the API call it, so
     train and serve can't drift. **Already in place:** training drops complaints with ≥30% blank words
     (manifest: 1,569,044 → 1,444,945). Open (decide in `04_training_set`): that filter hides heavy-blank
     complaints from training though they still arrive in production — after collapsing, loosen it to
     drop only texts with almost no real words left.
     **Measured 2026-10-01 (all F2):** blanks ≥30% = 126,596 complaints (7.72%) but only 129 payouts
     (0.08–0.13% rate). After collapsing (5,000-sample each side): median 238 → 109 tokens, over 512:
     12.1% → 3.6% — heavy-blank texts get SHORTER, so loosening the filter can't push real words out.
     **Catch:** as plain text `[REDACTED]` = 5 word-pieces vs `XXXX` = 2 → register the markers as
     **special tokens** (`add_special_tokens` + resize embeddings), or collapsing lengthens typical texts.
  2. Head + tail truncation for the long ones.
  3. **Slice evaluation:** score the model separately on complaints cut at 512 vs those that fit —
     this is how we learn whether length matters (replaces the 256 ablation).
     **TF-IDF reference (v3 test, `test.ipynb` 6b):** 12,602 cut (8.4%), paying 3.41% vs 2.21%. AUC fits /
     cut — text 0.9603 / 0.9542 · features 0.9656 / 0.9495 · fusion 0.9722 / 0.9614. **Long complaints are
     harder for every model, even features-only (which reads no text).** So a DistilBERT gap alone proves
     nothing: truncation hurts only if DistilBERT's cut-slice AUC falls clearly below TF-IDF fusion's 0.9614.
     Smoke (10k, noisy): DistilBERT 0.9721 / 0.9529.
  4. If the cut slice underperforms: chunk + pool with the same DistilBERT (median 2, p90 3 chunks).
  5. Last resort: a 1024+ model (jina-embeddings-v2-small, ~33M, 8,192 ctx).
  **Rejected, measured:** lemmatization — even an impossible best case (every `##` piece removed)
  fits only 22.0% of the long ones, and it feeds DistilBERT unnatural text; stopword removal — fits
  55.5% but deletes not / no / never / nothing / cannot.
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
