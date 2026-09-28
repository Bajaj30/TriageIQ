# TriageIQ — Blog log

Raw material for the project blog. **Pointer style:** what happened → why it's interesting → where the
detail lives. Updated as we go; new entries go at the bottom of their section.

**Every number carries its frame.** F1 = all 4,826,564 complaints (2022–24) · F2 = the 1,639,068 with a
narrative · F3 = the 301,460-row training set. Source of numbers: `Context/FACTS.md`.

> **Naming note for the blog:** don't write "F1 / F2 / F3" there — readers will read "F1" as F1-score.
> Say "all complaints / complaints with text / training set".

---

## 1. The arc

| phase | one line |
|---|---|
| 0.2 EDA | Streamed a 9.2 GB CSV in chunks, proved the text is human-written, built a training set |
| v1 → v2 pivot | Dropped invented customers; the thing with history became the company × issue |
| Evaluation | Found the headline AUC was mostly "which product / which company"; switched to within-group metrics |
| 0.3 Schema | Snowflake schema, 16 decisions (D1–D16), each tied to a concept |
| 0.4 Load | Docker Postgres → raw staging → 6 dimensions ✅ → fact, text, events (in progress) |
| next | Point-in-time features in SQL (Phase 1) → DistilBERT + fusion (Phase 2) → API (Phase 3) |

---

## 2. Discarded ideas — and why

| # | idea | why it died | replaced by |
|---|---|---|---|
| 1 | Synthetic customers + transactions (v1) | CFPB has no consumer identity — the customer branch had nothing to attach to; invented data can't be verified | Real data only; entity = company × issue |
| 2 | Cap each product at 16k rows to "balance" | Silently raised the payout rate from the true 2.16% (F2) to 7.5% — the sampler was editing the label | Natural mix + case-control sampling with a recorded correction |
| 3 | Full de-duplication | Real consumers copy the same forum templates; full dedup erases a true property of the data | Cap each duplicate cluster at 25 (dup rate 19.8% → 0.3%) |
| 4 | Rule tier: auto-template low-payout products | A $200k student-loan failure gets a template reply (student loans pay out 1.11%, F1), yet text still ranked well inside such products (exploration: Mortgage 0.809, Vehicle loan 0.771 AUC) | Model every product |
| 5 | `any_relief` label (money + non-money relief) | Metadata-dominated — the transformer would be decorative | `Closed with monetary relief` |
| 6 | Predict consumer severity | CFPB publishes no severity label — nothing to validate against | Company cost; optional `P × claimed amount` layer |
| 7 | Drop the 3.2M complaints with no text, keep a count/ratio column | They hold 25,577 payouts = 42% of all positives (F1). A rate differs on every date, so one column either leaks the future or becomes the feature table | Keep every row; compute rates as-of date |
| 8 | Move `date_received` off the fact ("repeated dates break grain") | Grain is about rows, not repeated values | Date on the fact **and** in the event log |
| 9 | Narrative as a dimension | It describes one complaint at the same grain → an extension, not a dimension | `complaint_narrative` table |
| 10 | Child tables unique on the name | Names repeat across parents — 29 sub-issue names sit under 2–3 issues (F1) | Unique on (parent_id, name) |
| 11 | Issue as a child of Product | 51 of 93 issues span several products (F1) | Two independent dimensions |
| 12 | Map renamed/split products by name, top-down | One old product can't map to two new ones by name alone | Route bottom-up by sub-product; crosswalk table (14 raw → 11) |
| 13 | NULL foreign key for "no sub-issue" | Any inner join silently drops those 122,207 complaints (F1) | A `'(not specified)'` member per parent |
| 14 | `TIMESTAMPTZ` for the complaint date | The source has no time of day | `DATE` |
| 15 | SQL's default window frame | It includes rows tied on the same date → a complaint's own label leaks into its own feature | Three explicit frame patterns (`TriageIQ.md` §1.4a) |
| 16 | Tiebreak `(date, complaint_id)` everywhere | Postgres rejects two ORDER BY columns with interval `RANGE` frames | Frame chosen by what the feature means |
| 17 | Target encoding fitted on the resampled train set | Train is 25% positive vs ~3.4% real → cost the metadata branch 0.032 AUC | Entity rates computed over F1 in Postgres |
| 18 | A long-context encoder now (ModernBERT, Longformer, BigBird) | ModernBERT's speed needs FlashAttention-2 (Ampere+ GPUs); free T4/P100 and Mac MPS lack it; 2.3× DistilBERT's parameters. And payout rate peaks at 512–1k tokens, then falls | DistilBERT @512; test 256 vs 512 first; head+tail truncation before any bigger model |
| 19 | Dynamic padding as the speed-up | Measured **1.00×** — with long-tailed lengths almost every batch holds one long complaint | Group similar lengths per batch: 2.23× fewer padded tokens |
| 20 | Google Cloud $300 credits for GPUs | Free-trial accounts have historically blocked GPUs; upgrading allows real charges → breaks "no GPU bills" (not re-verified) | Kaggle free T4 |
| 21 | Reuse the local Postgres.app on port 5432 | Port clash; the project must rebuild from one compose file | Docker container on 5433, fresh database |

---

## 3. Realisations

1. **One model, three honest-sounding numbers.** Fusion (F3): 0.9634 pooled · 0.9330 within product×issue ·
   0.8034 within one company. Pooled is inflated by "which product / which company".
2. **The winner flips with the frame.** Holding product and issue fixed, metadata beats text (0.9076 vs
   0.8905). Inside one company — what a bank actually sees — text wins (0.7900 vs 0.7463). A model
   comparison means nothing without its frame.
3. **The label was nearly decided at intake.** Product alone gave 0.957 AUC, company alone 0.976
   (exploration subsets, historical). That is why within-group evaluation exists.
4. **Most complaints aren't where the money is.** Credit reporting = 83.2% of complaints but 3.3% of payouts
   (F1). Credit card + checking = 6.4% of complaints but 76.2% of payouts.
5. **Rows the model never reads still matter.** 42% of payouts sit in complaints with no narrative (F1).
   The model trains on text rows; the features need every row.
6. **The future is harder than the past.** Payout rate by year (F2): 2022 2.74% → 2023 2.51% → 2024 1.71%.
   A temporal split shows this; a random split would hide it.
7. **The source changed its own categories mid-dataset.** Around 2023-08-24 CFPB renamed and split
   products. Loaded naively, credit-reporting history restarts from zero weeks before validation. The
   crosswalk reroutes 1,334,958 complaints (F1).
8. **Same-day ties are the norm.** 43.46% of company-days hold more than one complaint; max 4,245 in one
   day (F1). "The complaints before this one" is undefined without a rule.
9. **Repetition was evidence of real people.** The most repeated opener was FCRA legal boilerplate that
   consumers copy from credit-repair forums — not an LLM template.
10. **SQL doesn't make fine-tuning faster — it makes it easier.** Token counts are the same, so GPU time is
    the same. What SQL saves is a learning problem: without it, DistilBERT would have to infer the company
    from the text and memorise the payout history of 4,946 companies from 71,460 examples.
11. **"Reproducible" was a claim, not a property.** Headline numbers came from throwaway scripts, and the
    repo had no git history for weeks. Re-running on the shipped data dropped metadata within-strata AUC
    0.9400 → 0.9076.
12. **Company names hide case-only duplicates.** 4 companies appear twice with different capitalisation
    (`'ATM OPS Inc'` / `'ATM OPS INC'`) → merged to one id each.

---

## 4. Theory that came in clutch

| concept | textbook version | where it showed up here |
|---|---|---|
| Type-token ratio (TTR) | unique words ÷ total words; generated text reuses vocabulary | Real-vs-synthetic gate in EDA, on a fixed 100k-token budget. Twist: raw TTR 0.065 sat **below** our own 0.08 "suspicious" line; it rose to 0.081 after capping duplicate clusters. The "real" verdict rested on the other metrics |
| Heaps' law | vocabulary grows slower than text length, so TTR falls as you count more words | Why TTR is only comparable at a fixed token count (the notebook uses 100k) |
| Coefficient of variation | std ÷ mean | Sentence-length CV 0.94 vs < 0.35 = suspiciously uniform (LLM-like) |
| Accuracy paradox; ROC-AUC vs PR-AUC | with rare positives accuracy is useless; ROC-AUC ignores the base rate, PR-AUC moves with it | Base rate 2.16% (F2). PR-AUC is a headline metric; val/test kept at the natural rate so PR-AUC isn't inflated |
| Precision/recall trade-off; F-beta | F1-score weights both equally; F2-score weights recall 2× | Recall matters more here — a missed payout costs more than an extra senior review. So far expressed as PR-AUC and recall at a fixed precision; **no F-score used yet** — F2-score is a candidate when the routing threshold is picked |
| Case-control sampling + prior correction (King & Zeng 2001) | sample on the outcome, then shift the intercept by log(keep-fraction) | All positives + 3 negatives each → keep-fraction 0.104639 → logit offset ln(0.104639) = −2.2572 |
| Between- vs within-group variation (cousin of Simpson's paradox) | a pooled result can be driven by group membership alone | Pooled vs within-strata vs within-company AUC |
| Data leakage; point-in-time correctness | use only what existed at prediction time | Post-intake columns banned; window frames exclude the current day |
| Temporal validation; drift | split by time, never randomly | train < 2023-10-01 · val Q4 2023 · test 2024 |
| Target encoding + smoothing (empirical Bayes) | shrink small-group rates toward a prior | Broke when fitted on resampled data. The prior must be as-of date — and product-level, not global: the global rate (1.26%, F1) is mostly a credit-reporting number |
| Dimensional modelling (Kimball) | grain, fact vs dimension, star vs snowflake, surrogate keys | D1–D16 in `Context/schema_explanation.md` |
| Three-valued logic (NULL) | NULL = unknown; `NULL = NULL` isn't true; inner joins drop NULL keys | Placeholder members; `UNIQUE NULLS NOT DISTINCT` on the crosswalk; 19 NULL outcomes (F1) excluded, not counted as 0 |
| Referential integrity; composite FKs | a foreign key over several columns | The database rejects a sub-product under the wrong product (D16) |
| Window frames: ROWS vs RANGE, peers | default frame = `RANGE … CURRENT ROW`, which includes every tied row | The label-leak trap; `ROWS` is not a time window |
| Idempotency | running twice = running once | `ON CONFLICT DO NOTHING`; every load re-run inserts 0 |
| Transformer length limits | learned position embeddings cap the input length; attention cost grows with length² | DistilBERT's 512 ceiling; the 256-vs-512 ablation; head+tail truncation |
| Heavy-tailed distributions | a few extreme values dominate | A 30,110-copy duplicate cluster; the length tail that made dynamic padding useless |
| Mixed precision (fp16 vs bf16) | bf16 needs Ampere-or-newer GPUs | T4 → fp16 only |

---

## 5. How we used SQL

- **Everything lives in PostgreSQL 16**, in Docker (pgvector image, port 5433). Data sits in a named
  volume — it survived Docker stopping overnight.
- **Staging first:** one `COPY` loads all 17,355,295 raw rows as TEXT. Load raw, decide types later.
- **Views as a shared filter:** `stg_window` (2022–24) and `stg_canonical` (crosswalk applied) store
  nothing, so every load file reads the same definition.
- **Rules as data:** the product crosswalk is a 12-row table, not CASE logic hidden in code — auditable
  and joinable. It reroutes 1,334,958 complaints (F1).
- **One file per table**, each with a TARGET / READS / EXPECT / CONCEPT header and CHECKS at the bottom.
  Every load proves its count (all 4,826,564 complaints find their dimension row).
- **Idempotent loads:** `ON CONFLICT DO NOTHING`, so re-runs insert 0.
- **Aggregate, then join:** child dimensions shrink 4.8M rows to 298 pairs *before* touching the parent.
- **LEFT JOIN + NOT NULL = a loud failure.** Loading the fact, a name with no dimension match would vanish
  under an INNER JOIN. With LEFT JOIN its id is NULL, and the NOT NULL column stops the whole insert.
  4,826,564 rows went in (F1) in 81 seconds on a laptop.
- **The database enforces the design:** composite FKs, CHECKs, NOT NULL. 12/12 deliberately bad inserts
  were rejected.
- **Coming (Phase 1):** point-in-time features with window functions (3 frame patterns), the label as a
  view, deterministic training-set sampling, export for Kaggle.
- **Why SQL at all:** one source of truth — training and serving read the same feature view. The 4.8M-row
  work stays in the database; the GPU only sees the 301,460-row training set (F3).

---

## 6. Mistakes and corrections — mine and the AI's

- **Numbers without a frame.** Stats from all-time vs 2022–24, or a subset vs the shipped data, got mixed
  in the docs → a full correction round. Fix: `FACTS.md`, generated by a script, is the only source of numbers.
- **The AI claimed actions it hadn't done** (a file "saved", a git fix "done"). Rule since: never claim an
  unverified action.
- **My reasoning errors, caught early:** "surrogate keys are more readable" (backwards — they're *less*
  readable; the real reasons are speed, size and stable ids); the narrative as a "dimension"; repeated values
  mistaken for a grain problem; "each sub-product has one parent" (false for 87.5% of rows, F1).
- **Measurement bugs that looked like data problems:** a regex with `case=False` counted CFPB's `XXXX`
  redactions as "placeholders"; 40+ character "words" were URLs; one stat was measured on the wrong frame.
- **Tests that hard-coded ids failed:** identity sequences don't roll back after a failed insert. Look ids
  up by name.
- **No git for weeks** while the rules said "reproducible".

---

## 7. Open threads — possible blog material later

- TTR sat below our own threshold on raw data — explain it properly or drop it from the gate.
- Smoothing prior: product-level vs global — decide in Phase 1.
- 721 narratives appear in more than one split — needs a group-aware split before Phase 2.
- Routing threshold: pick it from the desk's capacity; F2-score is a candidate.
- The 60-day response lag is an assumption — CFPB never records the response date.
- Length vs label ("payout rate peaks at 512–1k tokens, 39.6%"): the frame wasn't recorded — re-check
  before publishing.
