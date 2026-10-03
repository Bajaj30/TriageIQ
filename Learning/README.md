# Learning — how this folder works

Two jobs, two kinds of file:
- **`directions.md`** — a roadmap for a phase you are *building*: learn → build → explain back.
- **`revision.md`** — a phase that is *done*, condensed for **interview prep**: every concept we used, where
  it lives in TriageIQ, the question an interviewer asks, a crisp answer, and a lecture to re-watch.
- **`learning_log.md`** — **your own notes** (what confused you, how you resolved it). Only you write these.

| folder | files | status |
|---|---|---|
| `Phase0/` — data, schema, bulk load, label | `directions.md` · `learning_log.md` (yours, 0.1–0.3) · `revision.md` | done |
| `Phase1/` — point-in-time features in SQL | `revision.md` | done |
| `Phase2/` — training set, DistilBERT fusion, evaluation | `revision.md` | done |
| `Phase3/` — calibration, API, Docker, AWS, monitoring | `directions.md` (the roadmap you are on) · `learning_log.md` (start it at 3.0) | **now** |

**Where numbers come from:** `Context/FACTS.md` only (generated). Every number in these files states its group:
*all complaints* (4,826,564, 2022–24) · *complaints with text* (1,639,068) · *the 2024 test set* (150,000).

---

## Before an interview — read in this order (≈ 2–3 hours)

1. **The 2-minute story** (below) — say it out loud twice.
2. `Phase0/revision.md` → `Phase1/revision.md` → `Phase2/revision.md` → (after it's built) Phase 3.
   For each card: cover the answer, say it, then check.
3. `Context/metrics.md` — every metric, defined once.
4. `Context/interview.md` — "what broke and how we fixed it" stories (Phase 0 → Phase 2 planning).
5. `Context/FACTS.md` — glance at the headline numbers last, so they're fresh.

## The 2-minute story

1. **Problem.** A compliance desk gets CFPB complaints with a 15-day deadline. Few end in money paid
   (1.26% of all complaints, 2022–24). Goal: rank each new complaint by its chance of a payout, so seniors
   read the risky ones first.
2. **Data.** 4.8M real complaints in Postgres — a snowflake schema, an event log, the label as a view.
   1.6M have the consumer's text.
3. **Features.** Point-in-time company and issue track records, computed with window functions over all
   4.8M complaints, leak-tested, smoothed for small companies; 19 inputs chosen, "clock" features removed.
4. **Model.** DistilBERT reads the text; its output is fused with the 19 SQL inputs; trained on a free
   T4 GPU with case-control sampling and a recorded correction.
5. **Honest evaluation.** Scored *inside one company* (what a bank actually sees), on 2024 complaints the
   model never saw: **0.8224** (95% range 0.815–0.830) vs 0.8036 text-only and 0.8115 for a TF-IDF
   baseline. Reading the riskiest 10% catches 92.6% of payouts.
6. **What I learned.** The SQL features earn their place; more data and a longer-reading model don't
   help; error analysis shows the ceiling is the company's own decision, which isn't in the text.
7. **Deployment** *(fill in after Phase 3)*. CPU model behind FastAPI on AWS, features from the same SQL,
   calibrated probabilities, drift monitored by replaying 2024.

## Card format (all revision files)

> **Idea** — the intuition · **In TriageIQ** — where, with a number · **Q** — what an interviewer asks →
> **A** — a crisp answer · **Watch** — a lecture (or the best non-video source when no good lecture exists)
