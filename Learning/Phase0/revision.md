# Phase 0 — Revision: data, schema, bulk load, label

Interview prep for everything before the features: Docker, the dataset, the schema, the load, the label.
Your own notes for 0.1–0.3 are in `learning_log.md` — read them too; they hold *your* confusions.
Numbers: `Context/FACTS.md`. Decisions: `CLAUDE.md` §6 (D1–D17), `Context/schema_explanation.md`.

---

## A. Data and setup

### 1. Postgres in Docker
- **Idea:** the database runs in a sealed box, rebuilt the same way on any machine from one file.
- **In TriageIQ:** `docker-compose.yml` — pinned image `pgvector/pgvector:0.8.0-pg16`, named volume `pgdata`
  (data survives restarts), port `5433:5432` (Postgres.app owns 5432 on the Mac), a healthcheck.
- **Q:** Why Docker for a local database? → **A:** Reproducible from one file, pinned versions, isolated from
  the laptop's own Postgres; the same image runs in the cloud later.
- **Watch:** TechWorld with Nana — "Docker Tutorial for Beginners" (also used in Phase 3.5).

### 2. A file too big for memory
- **Idea:** read a huge file in slices, keep only the needed columns, cache the result in a compact format.
- **In TriageIQ:** the 9.2 GB CSV streamed in 250k-row chunks → Parquet (columnar, compressed): later passes
  took 14 s instead of re-parsing 9.2 GB. Later, `COPY` loaded all 17,355,295 raw rows into Postgres.
- **Q:** Why Parquet over CSV? → **A:** Columnar (read only the columns you need), typed, compressed.

### 3. Is the data real? — a measurable gate
- **Idea:** test authenticity with numbers, not a vibe: duplicate rate, sentence-length variation, word
  variety, repeated openers, unfilled placeholders.
- **In TriageIQ:** sentence-length CV 0.94 (machine text < 0.35). The top repeated opener was legal wording
  consumers copy from forums — evidence *for* real people.
- **Q:** How do you know the dataset isn't LLM-generated? → **A:** A five-metric gate, and I printed the
  suspicious matches instead of trusting counters (two "red flags" were my own regex bugs).

### 4. Frames — every number belongs to a population
- **Idea:** "1.26%" is meaningless until you say *of what*.
- **In TriageIQ:** all complaints 4,826,564 (payouts 1.26%) · complaints with text 1,639,068 (2.16%) ·
  the training artifact. Mixing frames once forced a full round of doc corrections.
- **Q:** What went wrong when frames got mixed? → **A:** Cardinalities from all years (21 products) were
  about to size the schema for 2022–24 (14 products); one generated FACTS file fixed it for good.

---

## B. Schema design

### 5. Grain; fact vs dimension vs extension
- **Idea:** grain = "one row per *what*". A fact records events; a dimension describes things many facts
  share; an extension table holds more columns of the *same* grain.
- **In TriageIQ:** `fact_complaint` = one row per complaint; `dim_company`, `dim_product` … ;
  `complaint_narrative` is an **extension** (one text per complaint), not a dimension.
- **Q:** Thousands of complaints share a date — does that break the grain? → **A:** No. Grain is about
  *rows*, not repeated *values*; only a join that adds rows changes grain.

### 6. Surrogate keys
- **Idea:** a meaningless integer id instead of the name.
- **In TriageIQ:** every dimension (D4). Real reasons: integer `PARTITION BY` over 4.8M rows is faster and
  smaller, and two spellings of a company map to one id. (Not "readability" — `1847` is *less* readable.)
- **Q:** Natural or surrogate key? → **A:** Surrogate, for speed/size and because names change and collide.

### 7. Snowflake, hierarchies, independent dimensions
- **Idea:** star = flat dimensions; snowflake = parent → child dimension tables.
- **In TriageIQ:** product → sub-product, issue → sub-issue. Child names repeat across parents (87.5% of
  complaints carry a shared sub-product name) → child is **unique on (parent_id, name)**. Issue is **not**
  a child of product: 51 of 93 issues appear under several products → two independent dimensions.
- **Q:** Why a snowflake? → **A:** The hierarchies are real and change; a composite FK makes the database
  refuse a sub-product under the wrong product.

### 8. Renames — the crosswalk
- **Idea:** a two-column translation table: old name → today's name. *(tech: concordance table; slowly
  changing dimension, type 1 — overwrite with the current name, keep the original alongside)*
- **In TriageIQ:** the CFPB form change of Aug 2023 renamed/split products (14 raw → 11 canonical;
  1,334,958 complaints rerouted, routed by sub-product because one old product split in two) and renamed one
  issue (337,252 rerouted). Without it, the biggest issue's history would reset 5 weeks before validation.
- **Q:** Was the rename a leak? → **A:** No — both names are known at intake. It was a **history reset**
  (a shift), fixed by mapping old → new at the source.

### 9. NULL means something
- **Idea:** decide what a blank *means* before handling it.
- **In TriageIQ:** 122,207 complaints have no sub-issue — stored as NULL FKs, every inner join would drop them
  silently → an explicit `'(not specified)'` member. Tags are blank for 94.49% of all complaints, but blank =
  "no tag", and tagged Older Americans pay 10.08% vs 1.06% untagged.
- **Q:** A column is 94% empty — drop it? → **A:** Only after asking what empty means. Here it's a checkbox
  left unticked, and the ticked rows carry strong signal.

### 10. Constraints as executable documentation
- **Idea:** let the database refuse nonsense: `NOT NULL`, `CHECK`, `UNIQUE`, foreign keys (incl. composite).
- **In TriageIQ:** 12 of 12 deliberately wrong inserts rejected.
- **Q:** Why constraints when the load code is correct? → **A:** Code changes; constraints keep holding.

### 11. Append-only event log; the label lives there
- **Idea:** record events as new rows instead of overwriting a status column — history is kept.
- **In TriageIQ:** `complaint_events` (received → sent → responded), 14,479,692 rows. The outcome is
  **not** on the fact table, so using it as a feature requires a deliberate join (D2).
- **Q:** Why not a `status` column? → **A:** It overwrites history and puts the label one `SELECT *` away
  from the features.

---

## C. The load

### 12. Stage raw, then transform (ELT)
- **Idea:** photocopy the documents before marking them up — copy the raw file untouched, then build typed
  tables from it with SQL.
- **In TriageIQ:** `stg_complaints_raw` (all TEXT) → views `stg_window`, `stg_canonical` → one numbered file
  per table. Fact table: 4,826,564 rows in 81 s; events: "read once, write three times", under 2 minutes.
- **Q:** Why not clean in Python and insert? → **A:** The rules live in SQL (one source of truth), every step
  is re-runnable from the raw copy, and the database does the heavy lifting.

### 13. Idempotency
- **Idea:** run it twice, nothing doubles.
- **In TriageIQ:** `ON CONFLICT DO NOTHING` / re-runnable files. Side effect learned: a re-run inserted 0 rows
  but used up 14.5M id numbers (sequences never give ids back) — never rely on an id meaning anything.
- **Q:** What's idempotent and why care? → **A:** Same result however many times it runs — safe retries.

### 14. Validation by an independent implementation
- **Idea:** two different programs reaching the same number is stronger than one program checking itself.
- **In TriageIQ:** `training/canonical_facts.py` re-does the load rules in pandas → `expected_facts`;
  `11_validate.sql` runs 21 checks against it (27 s). NULL counts as FAIL; feeding one wrong expected number
  makes it FAIL — the tester was tested.
- **Q:** How do you know the load is right? → **A:** Independent re-implementation + a check that can fail.

### 15. Indexes and statistics
- **Idea:** a book's index — look up instead of reading every page. Composite = several columns; covering =
  the index holds every column the query needs (index-only scan); partial = only some rows.
- **In TriageIQ:** 6 indexes in 11 s; a company × issue history lookup: 797 complaints in 0.19 ms without
  touching the table. `VACUUM ANALYZE` refreshes the statistics the planner uses.
- **Q:** Why did the covering index matter? → **A:** The hot query never visits the 4.8M-row table.
- **Watch:** CMU 15-445 (Andy Pavlo) — the B+Tree / tree-indexes lecture.

### 16. The label as a view
- **Idea:** one definition of the answer, asked the same way everywhere.
- **In TriageIQ:** `v_label` — paid 60,952 · untimely 2,785 · 19 unknown → 0 (Shivam's decision: no money
  left the company). Base rate 1.26% (all complaints). Reads a partial index; about 1 s.
- **Q:** Why a view, not a column? → **A:** A copied column can drift; a view can't mean two things.

---

## What broke, and the fix

| what happened | fix | lesson |
|---|---|---|
| "Placeholders" rose after filtering | the regex ran case-insensitive; matches were CFPB's `{XXXX}` | print matches, don't trust counters |
| Product cap pushed payouts 2.16% → 7.5% | removed; sampling only via undoable case-control | sampling must not silently edit the label |
| Schema sized on all-years numbers | one generated FACTS file with frames | every number states its frame |
| No commits for weeks while claiming "reproducible" | git + GitHub, secret scan | check claims, don't assert them |
| Issue rename found after the fact load | issue crosswalk + rebuild (minutes) | change the design early |
| Tests assumed fixed id numbers | look up by name | ids carry no meaning |

## Numbers to know (state the group!)

All complaints 2022–24: **4,826,564** · payouts **60,952 (1.26%)** · with text **1,639,068** (2.16% pay) ·
no-text complaints hold **42% of payouts** · 43.46% of company-days have >1 complaint (max 4,245) ·
14 → 11 products · validation 21/21.

## Lectures to re-watch
- CMU 15-445 Database Systems (Andy Pavlo, free on YouTube): Lecture 01 (relational model), Lecture 02
  (Modern SQL), the tree-indexes lecture.
- *Book, no good lecture:* Kimball & Ross, *The Data Warehouse Toolkit* — the dimensional-modelling basics
  (grain, facts, dimensions) and slowly changing dimensions.
