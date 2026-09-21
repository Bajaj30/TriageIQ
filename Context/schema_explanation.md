# Schema — Explained Simply

Running notes for Phase 0.3. Each decision is tied back to the concept it rests on.

---

## The goal — never lose this

```
complaint arrives  →  will it cost us money?  →  senior analyst  /  template reply
```

Everything in this schema exists to answer that question **using only what was known the moment
the complaint arrived.** If a table makes it easy to accidentally use information from later, the
table is wrong.

---

## Three concepts you need

### 1. Grain — "one row per WHAT"

| table | grain |
|---|---|
| `fact_complaint` | one row per **complaint** |
| `complaint_events` | one row per **event** |
| `dim_company` | one row per **company** |

**The rule that trips everyone up:** grain is about **rows**, not about **values**.

```
complaint_id   company_id   date_received
  4102931        CHASE       2024-03-15
  4102955        CHASE       2024-03-15   <- company repeats. date repeats.
  4103012        WELLS       2024-03-15      Grain is STILL one row per complaint.
```

Repeated values in a column are completely normal — `company_id` repeats across 16,000 rows.
Grain only changes when **the number of rows changes**, and the only thing that does that is a
join that fans out.

**Why it matters:** if a join turns 1 complaint into 3 rows, every `SUM` triples and every
`COUNT` lies — silently, with no error.

**The habit:** after every join, check the row count. Ask *"did this add rows?"* — never
*"does this column repeat?"*

### 2. Fact vs Dimension vs Extension

| type | what it is | example |
|---|---|---|
| **Fact** | the thing that happened, with its measurements and foreign keys | `fact_complaint` |
| **Dimension** | describes an entity that **many facts share**; you group and filter by it | `dim_company`, `dim_product`, `dim_issue` |
| **Extension** | more attributes of the **same fact**, at the **same grain**, split out for performance | `complaint_narrative` |

**The test:** does it describe something many complaints have in common? → **dimension**.
Does it describe *this one complaint*? → **extension**.

### 3. Event log

An append-only table recording *what happened and when*. It has a **different grain** from the
fact — one complaint produces several event rows.

**Why bother:** a mutable `status` column overwrites history. An event log keeps it, which is the
only way to answer *"what did we know on 15 March?"* — the question this whole project rests on.

---

## Decisions made so far

### D1 — the narrative lives in its own table

**Concept:** extension table (same grain, split for performance).

`complaint_narrative (complaint_id, narrative)` — 1.64M rows, one-to-zero-or-one with the fact.

**Why:** the feature pipeline scans `fact_complaint` constantly — every window function, every CTE
— and **never reads the text**. Keeping ~650MB of narrative out means more rows fit per page and
every scan is faster. Text on the fact table is dead weight dragged through work that never
touches it.

**Not a dimension.** A dimension describes something many complaints share. The narrative belongs
to exactly one complaint. Calling it a dimension would tempt you to join it in the feature
pipeline — the exact cost you're avoiding.

### D2 — the outcome lives in `complaint_events`, not on the fact

**Concept:** leakage prevention through physical separation.

`Company response to consumer` is the **label**. It is only knowable *after* intake.

**Why:** a column on `fact_complaint` is one `SELECT *` away from becoming a feature. In the event
table it takes a deliberate, visible join. **You've made leakage require intent instead of
requiring vigilance.**

**The catch this introduces:** `complaint_events` has 2–3 rows per complaint. Join it to the fact
without aggregating first and your grain breaks. Aggregate first, then join.

### D3 — `date_received` lives in **both**

**Concept:** deliberate denormalisation, for the hottest column in the pipeline.

- On `fact_complaint` — it is the **point-in-time anchor**. Every window function partitions and
  orders by it. It must be one cheap column read, not a join.
- In `complaint_events` — so the log tells the complete story: received → sent to company → responded.

**The trade:** the same fact is stored twice and could drift. Accepted knowingly, because the
alternative — joining a 2–3-row-per-complaint table on every single feature query just to fetch a
date — reintroduces the fan-out risk everywhere.

*(A grain note, since this caused confusion: putting `date_received` on the fact does NOT break
its grain, even though thousands of complaints share a date. Repeated values ≠ repeated rows.)*

---

## The shape so far

```
        dim_company ─┐
        dim_product ─┤
        dim_issue   ─┼──<  fact_complaint  >── complaint_narrative
        dim_state   ─┘     (1 row/complaint)    (1 row/complaint that has text)
                                  │
                                  └──<  complaint_events
                                        (2-3 rows per complaint)
                                        received → sent → responded
                                        ^ the LABEL lives here
```

**Row counts:** `fact_complaint` = 4,826,564 (all complaints in window, including the 3.2M with no
text — they still count toward company volume). `complaint_narrative` = 1,639,068.

---

## Next

**Step 3 — the dimension tables.** The question to answer there: natural keys (company name) or
surrogate keys (integer id)? And what belongs *on* a dimension versus computed later in SQL.
