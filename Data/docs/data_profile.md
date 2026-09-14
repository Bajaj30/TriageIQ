# CFPB Data Profile — TriageIQ **v2**
Generated: 2026-09-11 · seed 42 · label = monetary relief

> v2 supersedes the v1 profile (40k product-capped sample). The product cap was removed: it
> flattened the product mix and silently tripled the label base rate. See `Context/TriageIQ.md` §0.5.

## Corpus
| | |
|---|---|
| raw rows | 17,355,295 (9.2 GB) |
| with narrative | 3,843,057 |
| window | 2022-01-01 .. 2024-12-31 |
| all complaints in window | 4,826,564 |

## Funnel — quality filters only, no product cap
| stage | rows |
|---|---|
| narratives (all time) | 3,843,057 |
| date window | 1,639,068 |
| >= 20 words | 1,569,044 |
| redaction density < 0.3 | 1,444,945 |
| dup cluster <= 25 | 1,105,370 |
| **eligible pool** | **1,105,370** |
| eligible positives | 34,848 (3.15%) |

The filters are **not** label-neutral, and that is fine: they retain 98.5%
of all positives while removing 33% of rows. Base rate
rises 2.16% -> 3.15% because the dup-cluster filter
strips templated credit-reporting complaints, which almost never end in monetary relief.

## Splits — temporal first, then sampled
| split | period | rows | positives | rate | |
|---|---|---|---|---|---|
| train | < 2023-10-01 | 71,460 | 17,865 | 25.00% | case-control |
| val | 2023-10-01 .. 2024-01-01 | 80,000 | 3,102 | 3.88% | natural |
| test | 2024 | 150,000 | 4,164 | 2.78% | natural |

Train keeps **every** positive and downsamples negatives (keep-fraction 0.1046).
Recalibrate predictions with logit offset **-2.2572** to return to the true prior.
val/test stay at natural prevalence — PR-AUC is base-rate sensitive, so scoring on a resampled test
set would inflate the headline number.

Base rate drifts **down** over time (2022 3.38% / 2023 3.49% / 2024 2.79%), so the test split is
genuinely harder than train. That is the honest direction for a temporal split.

## Product mix — natural, no cap
| product | share |
|---|---|
| Credit reporting or other personal consumer reports | 50.6% |
| Credit reporting, credit repair services, or other personal consumer reports | 11.2% |
| Debt collection | 9.6% |
| Checking or savings account | 7.9% |
| Credit card | 5.7% |
| Credit card or prepaid card | 3.6% |
| Mortgage | 3.1% |
| Money transfer, virtual currency, or money service | 2.6% |

v1's cap forced every product to ~9%. This is the real distribution: credit reporting dominates at
~62% across its two labels, and it almost never produces monetary relief. That is a property of the
problem, not a defect to sample away.

## Gate verdict — data is real
| metric | raw | threshold |
|---|---|---|
| exact-dup rate | 19.8% | — |
| sentence-length CV | 0.94 | < 0.35 suspicious |
| type-token ratio | 0.065 | < 0.08 suspicious |
| top opener | 3.7% | > 5% suspicious |

Top opener is FCRA boilerplate ("in accordance with the fair credit reporting act") that real
consumers copy-paste from credit-repair forums — evidence *for* authenticity, not against.

**Two false alarms, resolved — do not re-litigate.**
1. "Placeholders" are `{XXXX}`, CFPB's currency-redaction convention. The detector regex
   `\{[a-z_]+\}` ran with `case=False`, so `[a-z_]` matched uppercase X. Real LLM placeholders: 0.
2. "40+ char words" are URLs — 0.26% of rows, 0 documents materially corrupted. The genuine
   whitespace-collapse cases were already removed by the redaction filter, which cleaned a defect it
   was not aimed at.

## Field decisions for the DDL
| column | decision |
|---|---|
| `Consumer complaint narrative` | primary model input |
| `Complaint ID` | PK — unique across all 4,826,564 window rows; stored as text, **cast to BIGINT** |
| `Date received` | day granularity only; 43.5% of company-days hold >1 complaint -> `TriageIQ.md` §1.4a |
| `Company` | 4,950 distinct; only 53 in name-collision groups -> usable as a dim key |
| `Product` / `Sub-product` | 21 / 85 values |
| `Issue` / `Sub-issue` | 173 / 266 values; sub-issue 2.5% null |
| `State` | 63 values, 0.2% null |
| `Tags` | **drop** — 94.5% null |
| `Submitted via` | **drop** — single-valued ("Web") for narrative rows |
| `ZIP code` | **drop** — 100% populated but 19% redacted (`XXXXX`, `604XX`); thousands of levels; `State` alone scores only AUC 0.549, so ZIP adds noise + PII surface |
| `Company response to consumer` | **the label**. Post-intake — never a feature |
| `Date sent to company`, `Timely response?`, `Company public response` | **leakage** — post-intake, event-log only |

## Two-tier rule
This training set is **not** the feature population. Aggregates are computed in Postgres over all
4,826,564 window complaints (including the ~3.2M with no narrative, which still count toward
company volume). Only rows that *have* text can be training rows.

## Artifacts
- `data/interim/triageiq_training_v2.parquet` — 301,460 rows
- `data/interim/triageiq_training_v2.manifest.json` — filters, splits, sampling, recalibration offset
