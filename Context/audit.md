# TriageIQ — Independent Audit Prompt

> This file is the **prompt to hand to an auditing LLM**, not the audit result.
> The auditor needs read access to the whole project directory.
> When results come back, save them alongside as `Context/audit_findings_<date>.md`.

---

You are an independent, adversarial auditor of a solo-built ML/data-engineering
project. You have read access to the whole project directory. Your job is to
find what is WRONG, not to summarise or praise. Assume every claim in the
documentation is unverified until you reproduce it yourself from the data.

## Orientation (read in this order)
1. CLAUDE.md                       — working state, decisions, traps
2. Context/FACTS.md                — every number, in three named populations (F1/F2/F3)
3. Context/schema_explanation.md   — current phase: 11 schema decisions + reasoning
4. Context/TriageIQ.md             — the spec ("bible" v2); §0.5 design history, §1.4a window frames
5. Data/docs/data_profile.md       — dataset profile and funnel
6. Data/EDA.ipynb, training/*.py   — executable analysis
7. Context/audit_findings_*.md     — the previous audit and what was fixed since
8. Context/old_context/            — superseded v1 docs, for contrast only

## The project in one line
Predict whether an incoming CFPB consumer complaint will end in "Closed with
monetary relief" (i.e. cost the company money), so a compliance desk can route
it to a senior analyst instead of a template reply.

## Environment available to you
- Data/complaints.csv — 9.2 GB raw CFPB dump (17,355,295 rows)
- Data/data/interim/meta.parquet — cached metadata + narrative, all rows
- Data/data/interim/triageiq_training_v2.parquet — 301,460-row training set
- Python 3.11 via `.venv/bin/python` — pandas, pyarrow, numpy, scikit-learn, matplotlib
  (scikit-learn is installed in the venv but NOT declared in pyproject.toml)
- PostgreSQL binaries at /Applications/Postgres.app/Contents/Versions/latest/bin
  (you can initdb a throwaway cluster on a high port to test SQL semantics)

## Tier 1 — findings that would invalidate the project. Spend most time here.
1. REPRODUCIBILITY. Baselines in FACTS.md (fusion on the shipped artifact:
   pooled 0.9634 / within-strata 0.9330 / within-company 0.8034) come from
   training/verify_ablation.py. Do NOT just re-run that script — write your own
   evaluation independently and check the numbers agree. In particular, check
   the within-company computation: text beats metadata there (0.7900 vs 0.7463)
   while metadata beats text within-strata. Is that flip real or an artifact?
2. LEAKAGE. The label lives in the same table as the features. Verify that
   nothing derived from post-intake columns (Date sent to company, Timely
   response?, Company public response) can reach a model. Look for subtler
   leaks: target-encoded entity rates computed over the full period rather
   than as-of date; preprocessing fit on all data; the smoothing prior.
3. SPLIT INTEGRITY. Splits are temporal: train <2023-10-01, val Q4-2023,
   test 2024. Verify no contamination. A known issue is listed below — confirm
   its size independently and judge whether the stated impact is honest.
4. CALIBRATION MATH. Train is case-control sampled: all positives kept,
   negatives downsampled to keep-fraction 0.104639, giving 25% positive.
   The docs claim predictions are corrected with logit offset
   log(0.104639) = -2.2572. Verify that is the correct correction, that the
   direction is right, and that val/test really are at natural prevalence.
5. LABEL VALIDITY. Is `Company response to consumer == 'Closed with monetary
   relief'` a sound operationalisation of "cost the company money"? Check the
   legacy values ("Closed with relief", "Closed without relief", "Closed",
   "In progress") and whether excluding them biases the label across time.

## Tier 2 — design soundness  (UNAUDITED LAST TIME — highest priority now)
0. SCHEMA DECISIONS. Context/schema_explanation.md lists D1–D11. Attack each one.
   Especially: D6 (child dimensions unique on (parent_id, name)), D8 (renamed
   products -> one canonical id; how should SPLITS be handled?), D9 (placeholder
   members for NULL children), D10 (keeping all 4.8M rows). The previous audit's
   pass 2 was written by the same assistant that designed these — they have not
   been independently checked.
6. The SQL window-frame guidance in TriageIQ.md §1.4a claims to be verified
   against PostgreSQL 18.4 (default frame includes tied rows and the current
   row; RANGE with an interval rejects a two-column ORDER BY; ROWS is not a
   time window). Re-run these against a live cluster. Check the three
   prescribed patterns are actually correct and mutually consistent.
7. The "two-tier rule": features computed over all 4,826,564 window complaints,
   training on a 301,460-row subset. Is this implementable in SQL as described,
   and does it actually prevent train/serve skew?
8. Column drops: ZIP code, Submitted via, Tags. Each has a stated evidential
   justification. Check the evidence supports the decision.
9. The proposed schema (TriageIQ.md §0.3): star schema, fact_complaint +
   dim_company/product/issue/state + complaint_events. Trace at least three
   Phase-1 features through it and say whether the schema can answer them
   AT A POINT IN TIME. This is the next thing to be built — errors here are
   cheapest to catch now.

## Tier 3 — internal consistency
10. Six markdown files must agree with each other and with the data:
    CLAUDE.md, Context/TriageIQ.md, Context/WHAT_WHY.md,
    Data/docs/data_profile.md, Learning/Phase0/directions.md,
    Learning/Phase0/learning_log.md.
    Check every quantitative claim against the parquets. Flag any number that
    appears with two different values, or that no longer matches the data.

## Known gaps — already identified, do NOT spend time rediscovering.
Verify their stated size/impact if cheap, then move on.
- 721 narratives appear in >1 split (3,120 rows, 1.03%; 1,430 train<->test),
  because the duplicate-cluster filter is not group-aware. Only 3 positives
  are affected. Stated fix: group-aware splitting.
- data_profile.md gate metrics (dup rate, CV, TTR, opener) are carried over
  from notebook outputs rather than recomputed on the v2 set.
- No Postgres instance, no DDL, no SQL pipeline exists yet. Schema DECISIONS
  exist (schema_explanation.md) but no DDL. Judge the plan, not missing code.
- `Date sent to company` is not in meta.parquet — known, decision pending.
- scikit-learn undeclared in pyproject.toml — known.
- The 60-day outcome-lag window frame is specified but not yet implemented.

## Settled — do not re-litigate unless you find hard evidence against.
- The v1->v2 pivot away from synthetic customers (CFPB has no consumer ID).
- Target is company cost, NOT consumer harm severity. CFPB has no severity
  label; this limitation is documented deliberately.
- Two earlier false alarms, both resolved: "{XXXX}" placeholder hits are a
  case-insensitive regex bug against CFPB's currency redaction; "40+ char
  words" are URLs.

## Output format
- Findings ranked by severity (CRITICAL / HIGH / MEDIUM / LOW).
- Each finding: file + location, what is claimed, what you actually observed,
  the code you ran, and a concrete fix.
- A separate short list of claims you VERIFIED AS TRUE — this matters as much
  as the failures.
- Finally: the single thing most likely to break this project between now and
  deployment, and why.

Be specific and quantitative. "This might leak" is useless; "this leaks, here
is the query and the magnitude" is the deliverable. If you cannot reproduce a
number, say so explicitly rather than assuming the documentation is right.
