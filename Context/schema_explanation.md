# Schema — Explained Simply

Running notes for Phase 0.3. Each decision is tied back to the concept it rests on.
Numbers come from `Context/FACTS.md` (frame **F1** = all 4,826,564 complaints in the window).

---

## The goal — never lose this

```
complaint arrives  →  will it cost us money?  →  senior analyst  /  template reply
```

Everything in this schema exists to answer that question **using only what was known the moment
the complaint arrived.** If a table makes it easy to accidentally use information from later, the
table is wrong.

---

## Five concepts you need

### 1. Grain — "one row per WHAT"

| table | grain |
|---|---|
| `fact_complaint` | one row per **complaint** |
| `complaint_events` | one row per **event** (2–3 per complaint) |
| `dim_company` | one row per **company** |

**The rule that trips everyone up:** grain is about **rows**, not about **values**.

```
complaint_id   company_id   date_received
  4102931         1847       2024-03-15
  4102955         1847       2024-03-15   <- company repeats. date repeats.
  4103012         2210       2024-03-15      Grain is STILL one row per complaint.
```

Repeated values in a column are normal. Grain only changes when **the number of rows changes**,
and the only thing that does that is a join that fans out. If a join turns 1 complaint into 3 rows,
every `SUM` triples and every `COUNT` lies — silently.

**The habit:** after every join, check the row count. Ask *"did this add rows?"* — never
*"does this column repeat?"*

### 2. Fact vs Dimension vs Extension

| type | what it is | example |
|---|---|---|
| **Fact** | the thing that happened, with its foreign keys | `fact_complaint` |
| **Dimension** | describes an entity that **many facts share**; you group and filter by it | `dim_company`, `dim_product` |
| **Extension** | more attributes of the **same fact**, at the **same grain**, split out for performance | `complaint_narrative` |

**The test:** does it describe something many complaints share? → dimension.
Does it describe *this one complaint*? → extension.

### 3. Attribute vs Measure — what may live on a dimension

**The test: does it change when a new complaint arrives?**

| column | changes with new facts? | so it's… |
|---|---|---|
| `company_name` | no | an **attribute** — belongs on the dimension |
| `total_complaints`, `relief_rate` | yes, and differs by *when you ask* | a **measure** — computed as-of-date in Phase 1, never stored |

Storing `relief_rate` on `dim_company` would store the *all-time* rate — which includes the future.
That's leakage wearing a dimension's clothes.

### 4. Natural vs Surrogate keys

- **Natural key** — the real-world value (`'JPMORGAN CHASE & CO.'`). Readable.
- **Surrogate key** — a meaningless integer you mint (`1847`). Not readable — that's its cost, not a benefit.

### 5. "Two names, one thing" vs "One name, different things"

| | fix |
|---|---|
| **Two names, one thing** — CFPB renamed a product mid-window | **merge** → one id |
| **One name, different things** — `'Credit reporting'` is a sub-product under 3 different products | **keep separate** → one id per (parent, name) |

Getting these backwards either splits one entity's history in half or blurs different situations
together. Both silently corrupt features.

---

## Decisions made

### D1 — the narrative lives in its own table
**Concept:** extension table.
`complaint_narrative (complaint_id, narrative)` — 1,639,068 rows, one-to-zero-or-one with the fact.
**Why:** the feature pipeline scans `fact_complaint` constantly and **never reads the text**. Keeping
~650MB out means every scan is faster. The model never reads Postgres directly anyway — training
reads a Parquet snapshot, and at serving time the caller sends the text in the request.

### D2 — the outcome lives in `complaint_events`, not on the fact
**Concept:** leakage prevention through physical separation.
A label column on the fact is one `SELECT *` away from becoming a feature. In the event table it
takes a deliberate, visible join. **Leakage now requires intent instead of vigilance.**
**Catch:** events have 2–3 rows per complaint — aggregate before joining, or the grain breaks.

### D3 — `date_received` lives in both
**Concept:** deliberate denormalisation of the hottest column.
On the fact it's the point-in-time anchor every window function orders by. In the event log it
completes the story (received → sent → responded). Stored twice, knowingly.

### D4 — surrogate keys on every dimension
**Concept:** natural vs surrogate.
**Why:** `PARTITION BY company_id` runs on 4.8M rows constantly — integer beats text; ~10MB instead
of ~145MB in the fact table; and it fixes name collisions (`'ATM OPS Inc'` vs `'ATM OPS INC'` —
one company, two strings — map to one id).
**Accepted costs:** `SELECT *` shows numbers not names; IDs must be assigned **once and never
change** (persist the mapping, never regenerate it); load must resolve name → id.

### D5 — `dim_company` stays thin
**Concept:** attribute vs measure.
`dim_company (company_id, company_name, first_seen_in_window)`.
CFPB gives no industry, size or location, so the dimension is legitimately thin. No counts, no rates.
**Naming caveat:** `first_seen_in_window` means *first complaint in our 2022–24 data*, not the
company's real age. A company active since 2015 shows 2022. Never call it "tenure".

### D6 — hierarchies are two tables, child unique on the pair
**Concept:** one name, different things.
```
dim_product      (product_id, product_name)
dim_sub_product  (sub_product_id, product_id → dim_product, sub_product_name)
                  UNIQUE (product_id, sub_product_name)          -- NOT UNIQUE(sub_product_name)
```
Same shape for `dim_issue` / `dim_sub_issue`.
**Why:** 16 of 58 sub-product names sit under more than one product (87.5% of F1 rows); 29 of 212
sub-issues sit under more than one issue (20% of rows). Unique-on-name would fail the load or
silently merge different sub-products.
**Why two tables, not one combined:** product needs to be a real entity with its own id — the rename
fix (D8) lives in one row there, and there are product-level features.

### D7 — Issue is independent of Product
**Concept:** check the hierarchy before assuming one.
55% of issues appear under more than one product (`'Improper use of your report'` under 10). They are
separate dimensions. No link between them.

### D8 — renamed products map to one canonical id
**Concept:** two names, one thing.
`'Credit reporting, credit repair services, …'` runs to 2023-08-25; `'Credit reporting or other
personal consumer reports'` starts 2023-08-24. A clean cutover — CFPB renamed it. Kept as two ids,
every credit-reporting feature resets to zero history six weeks before val begins — on ~62% of
complaints. `dim_product` stores the canonical name plus the raw names that map to it.
**Still to verify:** which other product pairs are renames and which are **splits** (one old product
becoming two new ones — a split cannot simply be merged). See `FACTS.md` → product date ranges.

### D9 — NULL children get a placeholder member, never a NULL key
**Concept:** inner joins silently drop NULLs.
122,207 complaints (2.53%) have an issue but no sub-issue. A NULL `sub_issue_id` means
`INNER JOIN dim_sub_issue` drops all of them — the grain bug arriving through a different door.
Each issue gets a `'(not specified)'` sub-issue row instead.

### D10 — all 4.8M rows stay; no pre-computed ratio columns
**Concept:** store raw facts, compute features from them.
Proposal considered: drop the 3.2M complaints with no narrative and keep a count/ratio column instead.
**Rejected, on evidence:** those rows hold **25,577 payout outcomes — 42% of all positives.** Company
relief rates computed without them are off by a median 15%, up to 100%, differently per company.
And a ratio isn't one number — "Chase's relief rate" differs on every date, so a single column
either leaks the future or becomes the feature table. **You can recompute a count from rows; you can
never recover rows from a count.**
Also: these rows are metadata only (~300MB), so they cost nothing on the GPU — training reads a 44MB
slice of the training artifact, never the database.

### D11 — `product_id` and `sub_product_id` both on the fact
**Concept:** same as D3 — hot columns live on the fact.
`sub_product_id` implies the product, but product-level `PARTITION BY` runs constantly and shouldn't
pay a join each time. Same for `issue_id` / `sub_issue_id`.


### D12 — split products route by sub-product (bottom-up)
**Concept:** generalisation — derive the parent from the child, for this specific case only.
For the product families changed in the 2023-08-24 CFPB form change, the canonical product is **derived
from the sub-product** rather than the sub-product hanging under a given product. Verified: every
affected old sub-product maps to **exactly one** new product.

| raw product | raw sub-product | → canonical product |
|---|---|---|
| Credit card or prepaid card | General-purpose credit card or charge card · Store credit card | Credit card |
| Credit card or prepaid card | General-purpose prepaid card · Government benefit card · Gift card · Payroll card · Student prepaid card | Prepaid card |
| Credit reporting, credit repair services, … | Credit reporting · Other personal consumer report | Credit reporting or other personal consumer reports |
| Credit reporting, credit repair services, … | Credit repair services | Debt or credit management |
| Payday loan, title loan, or personal loan | *(any, incl. NULL)* | Payday loan, title loan, personal loan, or advance loan |
| Money transfer, virtual currency, or money service | Debt settlement | Debt or credit management |
| *everything else* | *(any)* | unchanged |

- **Canonical names = the NEW taxonomy**, because the API will receive today's CFPB names.
- **Two split-offs found that a name-level check would have missed:** `Credit repair services` left credit
  reporting, and `Debt settlement` (327 rows) left **Money transfer** — a product that otherwise never
  changed. Both moved cleanly (no overlap in dates).
- **Scope matters — key on (raw_product, raw_sub_product), never sub-product alone.** Bottom-up is only
  valid inside these families. Applied globally it collides with D6: `'Credit reporting'` is also a
  sub-product of *Checking* (1 row), which must stay under Checking.
- **Result:** 14 raw products → **11 canonical**. 1,334,958 rows (27.7% of F1) re-routed.
- **5 genuinely new sub-products** (478 rows — e.g. `Earned wage access`) have no history anywhere; their
  features correctly start from zero on 2023-08-25.

### D13 — the crosswalk is a table in Postgres
**Concept:** mappings are data, not hidden code (same reasoning as the label view).
`product_crosswalk` holds the 12 D12 rules; anything not listed keeps its raw name. Seeded in the DDL
file because the rows *are* the design decision. Every rule was verified against staging row counts.

### D14 — `date_received` is `DATE`, not `TIMESTAMPTZ`
**Concept:** don't store precision you don't have.
The source has no time of day. A timestamp would invent "midnight UTC" and suggest an ordering within
the day that doesn't exist. `RANGE` interval window frames work on `DATE` (verified in §1.4a tests).

### D15 — the `responded` event has no date
**Finding, not a choice:** CFPB records when a complaint was received and sent to the company — **never
when the company responded.** So `complaint_events.event_date` is NULL for `responded`, enforced by a
`CHECK`. This is exactly why the 60-day outcome lag in §1.4a is an *assumption*.

### D16 — the database enforces the denormalisation
**Concept:** composite foreign keys.
D11 puts `product_id` next to `sub_product_id` on the fact. A composite FK
`(sub_product_id, product_id) → dim_sub_product` makes it **impossible** to store a sub-product under
the wrong product. Same for issues. Verified: a Credit-card product with a Mortgage sub-product is rejected.

---

## The shape so far

```
   dim_product ──< dim_sub_product            dim_issue ──< dim_sub_issue
        │                │                         │               │
        └───────┬────────┘                         └───────┬───────┘
                │                                          │
 dim_company ───┼──────────<  fact_complaint  >────────────┘
 dim_state   ───┘          (1 row / complaint)
                           4,826,564 rows
                              │         │
                              │         └── complaint_narrative   (1 row / complaint WITH text)
                              │                1,639,068 rows
                              └──< complaint_events               (2–3 rows / complaint)
                                     received → sent → responded
                                     ^ the LABEL lives here
```

---

## Still open — decide before writing DDL

1. ~~Where the crosswalk lives~~ — **resolved: D13**, a table.
2. **`Submitted via`** — *kept as a fact column for now (cheap to drop)*. One value in narrative rows, **five** in F1 (Phone 67,953 · Referral 34,071 ·
   Postal 17,873). Dead for the model; not dead for company-volume features.
3. **`Tags`** — *kept as a nullable fact column for now*. 94.49% null in F1 but 87.82% in the training set. Drop, or keep as a sparse flag?
4. ~~`Date sent to company`~~ — **resolved**: loaded straight from the CSV into staging; no cache rebuild needed.
5. **NULL outcome** — 19 complaints in F1 have no response at all. Unknown ≠ negative: the label view
   must exclude them, not count them as 0.
