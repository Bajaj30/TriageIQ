# Phase 0 — Learning Directions & Ready-Made Prompts

> [!IMPORTANT]
> Come back to the TriageIQ main chat after completing each sub-task to report what you did. I'll review and guide the next step.

---

## 0.1 Docker + Docker Compose for Postgres

### What you need to learn (just enough, not everything)
- What a `docker-compose.yml` file is
- How to define a single service (Postgres), expose a port, mount a volume
- `docker compose up -d` / `docker compose down`
- How to connect to the running Postgres via `psql` (from inside the container)

### Resources
- [Docker official getting started](https://docs.docker.com/get-started/) — skim parts 1-2 only
- [Compose quickstart](https://docs.docker.com/compose/gettingstarted/) — the Python+Redis example; understand the *pattern*, you'll adapt it for Postgres
- [Official Postgres Docker image docs](https://hub.docker.com/_/postgres) — read the "How to use this image" section carefully

### Prompt for a learning chat

```
I'm setting up PostgreSQL 16 using Docker Compose for a data engineering project. I have Docker installed but have never used it.

Teach me step by step:
1. What docker-compose.yml is and how it works (conceptually, brief)
2. How to write a compose file with one service: the pgvector/pgvector:pg16 image, a named volume for data persistence, port 5432 exposed, and password via an .env file
3. How to start/stop the container
4. How to connect to the running Postgres using psql from inside the container
5. Common gotchas (port conflicts, data disappearing without volumes)

Keep it practical — I want to have a running Postgres in 30 minutes, not become a Docker expert today.
```

### Done when
- `docker compose up -d` starts Postgres
- You can connect with `psql` and run `SELECT 1;`
- You have `.env` (git-ignored) and `.env.example` (committed)

---

## 0.2 Finding the Source Text Dataset

### Where to look
1. **Kaggle** — search: "customer support tickets", "helpdesk tickets", "support ticket dataset"
2. **Hugging Face Datasets** — search same terms
3. Look for datasets with: subject/body text, ≥10k rows, some metadata (priority, category, channel)

### Top candidates to evaluate
| Dataset | Where | Notes |
|---------|-------|-------|
| "Customer Support Ticket Dataset" by various uploaders | Kaggle | Multiple versions exist — check each carefully |
| `bitext/Bitext-customer-support-llm-chatbot-training-dataset` | HuggingFace | Large but check if it's conversational format |
| Any dataset from a real company (e.g., scraped from public issue trackers) | Various | Often messier = more realistic |

### How to spot LLM-generated / synthetic datasets

> [!WARNING]
> This is critical — a synthetic text dataset will ruin Phase 2's transformer work.

Red flags to check:
1. **Suspiciously uniform length** — real tickets have huge variance (3 words to 3 paragraphs). If most are ~50-80 words, it's generated.
2. **Repeated sentence structures** — open 50 random samples. If they all follow "I am writing to inform you about..." or similar templates, it's fake.
3. **Too-clean language** — real tickets have typos, slang, broken grammar, ALL CAPS rage. Perfect English everywhere = LLM.
4. **Check the "About" section** — many Kaggle uploaders now honestly state "generated using GPT/Claude." Read it.
5. **Upload date** — datasets uploaded after mid-2023 on Kaggle have a higher chance of being LLM-generated. Not a rule, but a signal.
6. **Vocabulary diversity** — LLMs love certain phrases ("I understand your concern", "I apologize for the inconvenience"). Grep for these.

### Prompt for a learning chat

```
  
```

### Done when
- You have a downloaded dataset in `data/raw/` (git-ignored)
- You've written a `data_profile.md` with: row count, length stats, duplicate rate, language check, your assessment of whether it's real or synthetic
- You've committed a `data/README.md` with download instructions (not the data itself)

---

## 0.3 Schema Design (ERD)

> [!WARNING]
> v1 described 7 tables for a **synthetic** transactional world (customers, orders, payments…).
> **That design is dead** — CFPB has no consumer identity. See `Context/TriageIQ.md` §0.5.
> Running decisions and the reasoning behind each: **`Context/schema_explanation.md`**.

### What you need to learn (just enough)
- **Grain** — "one row per *what*". The concept that matters most; most schema bugs are grain bugs
- **Fact vs dimension vs extension table**
- **Attribute vs measure** — what may live on a dimension, and what must be computed later
- **PK / FK / cardinality** — one-to-many, and reading it off a diagram
- **Natural vs surrogate keys**
- **Star vs snowflake** — flattened dimensions vs parent-child dimension tables
- **`TIMESTAMPTZ` vs `DATE`**, stored UTC
- **Constraints** — `NOT NULL`, `CHECK`, `UNIQUE` as executable documentation
- **Append-only event log** — why it beats a mutable status column
- **B-tree indexes** — what they are and why the serving path needs them

Skip for now: normal forms beyond "don't repeat data", partitioning, materialized view internals.

### How to approach it
**Work backwards from the features, never forwards from the tables.**
1. Write the ~15 Phase-1 features down first
2. For each, ask: *can my tables answer this using only rows that existed before this complaint arrived?*
3. Only then draw: fact grain → dimensions → event log → constraints → indexes
4. Trace three features end-to-end on paper before writing any DDL

Tool: [dbdiagram.io](https://dbdiagram.io) — write DBML, see the diagram, iterate in minutes.

### The v2 shape — snowflake over one real fact table
- `fact_complaint` — one row per complaint (all 4,826,564, including the ones with no text)
- `complaint_narrative` — extension table, 1,639,068 rows, text only
- `complaint_events` — append-only: received → sent to company → responded. **The label lives here**
- `dim_company` — thin: id, name, `first_seen_in_window`
- `dim_product` → `dim_sub_product` and `dim_issue` → `dim_sub_issue` — parent-child pairs
- `dim_state`

### Non-negotiables (each one found the hard way — see `schema_explanation.md`)
- Surrogate integer keys on every dimension; the id mapping is assigned once and never regenerated
- A child dimension is **unique on (parent_id, child_name)** — child names repeat across parents
- Issue and Product are **independent** — do not link them
- Renamed products map to **one** canonical `product_id`
- NULL children get a `'(not specified)'` member — never a NULL foreign key
- `complaint_id` is `BIGINT` (text sort ≠ numeric sort)
- Timestamps `TIMESTAMPTZ`, UTC
- Ordering convention for window functions — see `Context/TriageIQ.md` §1.4a
- Post-intake columns are **never features**: `Date sent to company`, `Company response to consumer`,
  `Timely response?`, `Company public response`
- Numbers for sizing come from **`Context/FACTS.md`, frame F1** — never all-time figures

### Done when
- ERD drawn in dbdiagram.io
- You can explain every relationship, cardinality and grain
- DDL written with all constraints
- At least 3 Phase-1 features traced through it at a point in time

---

## Suggested Order & Timeline

```
Week 1:
  Day 1    →  0.1 (Docker + Postgres running)
  Day 1-2  →  0.2 (Find and profile dataset)
  Day 3-4  →  0.3 (ERD + DDL)
  Day 5-8  →  0.4 (Bulk load 4.8M rows into Postgres via COPY)

Week 2:
  Day 9    →  0.5 (Label as a SQL view over the response column)
  Day 9-10 →  Validation, integrity checks, documentation
```

> [!TIP]
> After each sub-task, come back to the main TriageIQ chat and say: "I finished 0.X, here's what I did." I'll review, ask hard questions, and point you to the next step.
