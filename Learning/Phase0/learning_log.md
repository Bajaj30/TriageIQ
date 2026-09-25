One suggestion: 
-> when you write your learning logs, jot down not just what you learned but also what confused you and how you resolved it. That reflective piece is genuinely useful when you revisit months later, and it's also great interview material ("I ran into X, here's how I debugged it").

# Phase - 0

## 0.1 Docker + Docker Compose for 

Postgres -> Doen watched a leacture on docker , understod -
1. overall structure 
2. whata and why 
3. images and containers , thier relatiom 
4. what is conpose and volumn
5. what is compose.yaml file 

## 0.2 Finding the Source Text Dataset and EDA

Dataset -> **CFPB Consumer Complaints** (US gov, public, redistributable). 17.3M rows / 9.2GB raw, 3.84M with narrative text.
Final artifact -> ~~`triageiq_tickets_v1.parquet` (40k, product-capped)~~ **deleted — replaced by `triageiq_training_v2.parquet`** (301,460 rows, case-control train split, no product cap).

### What I did
1. Streamed a 9GB CSV in 250k chunks (can't load it whole) -> built a meta table + narrative corpus, cached both as parquet
2. Bias check — do narrative rows skew vs non-narrative? Yes, but usably (credit reporting 43% vs 75%)
3. Synthetic-vs-real gate — dup rate, sentence-length CV, type-token ratio, opener repetition, placeholders
4. Duplicate anatomy — 41% of rows sit in a dup group, largest cluster 30,110 copies, 87% span multiple companies
5. Redaction analysis — 69% of narratives have ≥1 `XXXX`, 5.6% are redaction soup
6. Field audit — null rate + cardinality per column, to decide what survives into the DDL
7. Built the funnel: date window -> min words -> redaction -> dup cluster cap -> product cap -> 40k sample
8. Re-ran the gate on the final 40k to prove filtering didn't make the data worse

### Gate verdict — data is REAL
| metric | raw | final 40k | suspicious if |
|---|---|---|---|
| dup rate | 19.8% | 0.3% | — |
| sentence CV | 0.94 | 0.83 | < 0.35 |
| TTR | 0.065 | 0.081 | < 0.08 |
| top opener | 3.7% | 2.4% | > 5% |

### What confused me and how I resolved it
1. **Placeholders went UP (1 -> 15) after filtering** — looked like the funnel made data *more* synthetic.
   -> Printed the actual matches: all were `{XXXX}`. That's CFPB's redaction convention for dollar amounts, not an LLM template.
   -> Root cause: my regex `\{[a-z_]+\}` runs with `case=False`, so `[a-z_]` matches uppercase X. **False positive, my bug.**
2. **Top opener "in accordance with the fair…" at 3.7%** — repetition usually means generated text.
   -> It's FCRA legal boilerplate real consumers copy-paste off credit-repair forums. Repetition here is *evidence of real humans*, not against it.
3. **Words 40+ chars long** — worried the text had whitespace-collapse corruption (`Thefollowingaccountsthat…`).
   -> On the final 40k: only 103 rows (0.26%), and they're mostly URLs. 0 docs materially corrupted.
   -> The corrupted ones were *also* redaction soup, so `MAX_REDACT=0.30` had already removed them. A filter cleaned a defect it wasn't aimed at.
4. **I measured #3 on the wrong frame first** (~1.1M pre-sample pool, not the 40k). Lesson: always state which frame a stat came from.

### Decisions
1. Real text + synthetic transactions — text needs *semantic* truth, transactions only need statistical *shape*
   **(SUPERSEDED in v2: no synthetic data at all. See `Context/TriageIQ.md` §0.5.)**
2. Cluster cap (≤25) instead of full dedup — keeps natural template repetition, kills the 30k-copy monsters
3. Date window 2022–2024 — narrative share peaks ~2017 then declines; this balances volume vs recency
4. 40k not 3.8M — sized for free-tier GPU

### Known problem to carry forward
- The product cap doesn't do what its comment says: `int(0.40 * 40_000)` = flat 16k cap **per product**, applied before the downsample. It bound on all 10 big products and flattened them to ~9% each. Real CFPB mix (43% credit reporting) is gone. Defensible as a rebalance — but must be documented as a deliberate choice, not left looking accidental.
- CFPB has **no customer ID**. Every complaint is anonymous.
  **Resolved in v2:** we do NOT invent customers. The entity that accumulates history is the
  **company / issue**, not the consumer. Point-in-time window features survive; only the partition
  key changes. See `Context/TriageIQ.md` §0.5.

## 0.3 Schema Design (in progress)

Full decisions + reasoning -> `Context/schema_explanation.md`. Numbers -> `Context/FACTS.md`.

### What I learned
1. **Grain** = "one row per WHAT". The most important schema concept — most bugs are grain bugs
2. **Fact vs dimension vs extension** — dimension = shared by many facts; extension = same grain, split out
3. **Attribute vs measure** — if it changes when new complaints arrive, it's a measure -> compute it, don't store it
4. **Natural vs surrogate keys** — surrogate = meaningless integer id
5. **Snowflake vs star** — parent-child dimension tables vs one flattened table
6. **Event log** — append-only rows keep history; a mutable status column overwrites it

### What confused me and how I resolved it
1. **Thought repeated dates broke the fact table's grain** -> wanted to move `date_received` to the event table.
   -> Grain is about ROWS, not repeated VALUES. `company_id` repeats across 16k rows too.
   -> Only a join that ADDS rows changes grain. Ask "did this add rows?", not "does this repeat?"
2. **Wanted to drop the 3.2M complaints with no text and keep a count/ratio column instead.**
   -> Those rows hold 42% of all payout outcomes. Without them, company relief rates are off by a median 15%.
   -> A ratio isn't one number — it's different on every date. Can recompute a count from rows, never rows from a count.
   -> Also: those rows live in Postgres on disk; the GPU only ever sees a 44MB training slice.
3. **Called the narrative table a "dimension".** -> It's an EXTENSION: describes one complaint, same grain.
   -> Mattered because calling it a dimension tempts you to join it in the feature pipeline.
4. **Picked surrogate keys because they're "more readable".** -> Backwards: `1847` is LESS readable than a name.
   -> Real reasons: integer PARTITION BY on 4.8M rows, 10MB vs 145MB, and name collisions map to one id.
5. **Assumed each sub-product has one parent product.** -> False for 87.5% of rows ('Credit reporting' sits under 3 products).
   -> Child table must be UNIQUE on (parent_id, name), not name alone.
   -> Two different problems: two names/one thing (rename) -> MERGE; one name/different things -> KEEP SEPARATE.

### Decisions made
Surrogate keys · narrative in its own table · label in the event log · `date_received` on both ·
thin `dim_company` · parent-child dims unique on the pair · Issue independent of Product ·
renamed products -> one id · NULL children -> '(not specified)' member · keep all 4.8M rows

### Still open
Product renames vs splits · `Submitted via` · `Tags` · rebuild cache for `Date sent to company` · NULL outcomes

