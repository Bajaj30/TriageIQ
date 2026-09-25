# TriageIQ — Audit Findings
**Date:** 2026-09-12 · **Prompt:** `Context/audit.md`

## Provenance and bias disclosure — read first

This audit has **two authors**, and that matters for how much weight to give each part.

- **Pass 1 (independent).** An external model (Fable 5.1, via `claude_agent/chat.py`) ran the prompt
  cold and completed environment checks, corpus verification, cardinality/null profiling, and label
  archaeology. It **ran out of API credits** immediately before Tier 1 item 1 (the ablation
  reproduction) — the single most important item.
- **Pass 2 (NOT independent).** The rest was completed by the same assistant that produced the
  design and the numbers under audit. **This is a self-audit and is structurally biased.**

Mitigation applied in pass 2: every factual claim was re-derived from the parquets with freshly
written code, and the code is committed to the repo so a third party can re-run it. What this
audit **cannot** deliver is a check on *judgment* — whether the label is the right label, whether
the pivot was right, whether a better framing was missed. Tier 2 (design soundness) is therefore
largely **unaudited**. Give that section to an outside model before building on it.

---

## Verified TRUE

These claims were independently re-derived and hold:

| claim | verified |
|---|---|
| Ablation: text 0.971 / metadata 0.971 / fusion 0.979 pooled AUC | **0.9706 / 0.9714 / 0.9786** |
| Ablation within (Product×Issue): 0.898 / 0.940 / 0.945 | **0.8977 / 0.9400 / 0.9447** |
| Pooled fusion PR-AUC 0.438 | **0.4385** |
| Calibration offset −2.2572 corrects the case-control bias | mean pred 3.58× truth → **0.89× truth** |
| `Complaint ID` unique across all 4,826,564 window rows | true (also unique across all 17.3M) |
| Label column matches `y` in the shipped artifact | 100% consistent |
| Splits have no temporal overlap, no duplicate Complaint IDs | confirmed |
| Legacy response values absent from the window | `Closed`/`Closed with relief`/`Closed without relief`/`In progress` = **0 rows** |
| 43.5% of company-days hold >1 complaint, max 4,245 | **43.46%**, max 4,245 |
| Window counts: 4,826,564 all / 1,639,068 narrative / 35,375 positives | exact |
| Base rate drift 2022 3.38% → 2023 3.49% → 2024 2.79% | confirmed |

---

## CRITICAL

### C1 — The project has zero version control
```
$ git log --oneline   ->  fatal: your current branch 'master' does not have any commits yet
$ git ls-files | wc -l ->  0
```
A `git init` exists; **nothing has ever been committed**. Every file — the bible, CLAUDE.md, the
notebook, the derived parquets — is untracked. This directly violates ground rule 6 ("if you can't
rebuild an artifact from the repo, it doesn't count as done") at the most basic level, and one bad
command destroys weeks of work with no recovery.

**Fix:** commit now, before any schema work. `.gitignore` already excludes the 9.2GB CSV and
`Data/data/`, so the commit is small.

---

## HIGH

### H1 — The headline baselines do not correspond to the shipped dataset
The numbers quoted in `TriageIQ.md` §2.4 and `CLAUDE.md` §7 were produced on a **500k random
sample with a train<2024 / test-2024 split**. The shipped artifact
(`triageiq_training_v2.parquet`) uses a *different* split (train <2023-10-01, val Q4-23, test 2024)
and a case-control-sampled train. Re-running the identical ablation on each:

| model | quoted (500k raw sample) | **shipped v2 artifact** | delta |
|---|---|---|---|
| text, within-strata AUC | 0.8977 | **0.8905** | −0.007 |
| metadata, within-strata AUC | 0.9400 | **0.9076** | **−0.032** |
| fusion, within-strata AUC | 0.9447 | **0.9330** | −0.012 |
| fusion, pooled PR-AUC | 0.4385 | **0.4073** | −0.031 |

So "beat 0.945" is the wrong target; on the data that will actually be used it is **0.9330**.

**Root cause of the metadata collapse:** the target-encoded entity rates are computed on the
*case-control-resampled* train split, where the positive rate is 25% instead of the true ~3.4%.
The encoded rates and the smoothing prior are both distorted. This is a real methodological trap
and it validates the two-tier rule: entity rates must be computed over the **full population**
(in Postgres), never over the resampled training rows.

**Fix:** (a) restate the baselines using run B; (b) add an explicit warning that target encoding
must never be fitted on case-control-sampled data.

### H2 — Ablation code did not exist *(FIXED during this audit)*
The numbers had no code in the repo. Now at `training/verify_ablation.py`, with results written to
`training/ablation_results.json`. Runs in ~4 minutes.

### H3 — `scikit-learn` is required but undeclared
Not in `pyproject.toml`. The external auditor had to `pip install` it before reproducing anything.
Reproducibility claim fails for a clean checkout. **Fix:** `poetry add scikit-learn`.

### H4 — Duplicate narratives straddle the temporal splits
721 distinct narratives appear in more than one split — 3,120 rows (1.03%), of which 1,430 are in
train↔test groups. Cause: the duplicate-cluster filter caps copies at 25 but is **not group-aware**,
so identical text lands on both sides of the boundary.

**Severity is low in practice** — only **3 positives** are affected, so this is near-pure negative
contamination and will not materially move PR-AUC. But it is a genuine methodological hole and the
fix is cheap: assign each narrative hash to exactly one split before sampling.

---

## MEDIUM

### M1 — Cardinality figures in the docs are ALL-TIME; the project runs on the 2022–24 window
Every schema-sizing number is inflated:

| field | docs say | **actual in window** |
|---|---|---|
| Product | 21 | **14** |
| Sub-product | 85 | **58** |
| Issue | 173 | **93** |
| Sub-issue | 266 | **212** |
| State | 63 | **61** |

The DDL for Phase 0.3 is about to be written against these. Dimension tables would be sized on
values that do not occur in the working data.

### M2 — Null rates quoted from the wrong frame
| field | docs say | window (all rows) | window (narrative) | v2 train set |
|---|---|---|---|---|
| `Tags` null | 94.5% | 94.49% | **91.34%** | **87.82%** |
| `Sub-issue` null | 2.5% | 2.53% | **4.17%** | 5.31% |
| `State` null | 0.2% | 0.23% | 0.32% | 0.35% |

The docs quote the *all-rows* frame while the modelling population is *narrative rows*. `Tags` is
meaningfully less sparse than claimed (12.2% populated in the training set, not 5.5%) — the
"drop it" decision may deserve revisiting.

### M3 — `Timely response?` = 97.9% is a stale v1 number
Actual in window: **99.62%** (all rows) / 99.41% (narrative). The 97.9% figure came from the deleted
40k product-capped sample. It is quoted in `CLAUDE.md` §7 as if current.

### M4 — "`Submitted via` is DEAD" is true only for narrative rows
| frame | distinct values |
|---|---|
| window, narrative rows | 1 (`Web`) |
| **window, all rows (the two-tier FEATURE population)** | **5** |

`Web` 4,706,666 · `Phone` 67,953 · `Referral` 34,071 · `Postal mail` 17,873 · `Email` 1.

Dropping it from `fact_complaint` is defensible for the *model* (training rows are 100% Web, so it
carries no within-training variance), but it is **not** information-free in the feature layer — e.g.
"share of this company's complaints arriving by phone" is computable and is lost if the column is
never loaded. Decide deliberately; the current justification is stated for the wrong frame.

### M5 — One NULL outcome is silently labelled negative
`(response == "Closed with monetary relief").astype(int)` maps NULL → 0. There is exactly 1 such row
in the training set (19 in the window). Harmless at this scale, but a NULL outcome is *unknown*, not
*negative*, and should be excluded rather than assumed.

### M6 — Cold start is larger than the docs imply
The train split sees **1,627** companies; the test split contains **1,986**, of which **836 are unseen
in training** (2,107 test rows, 1.4%). The shipped training set covers only **2,745 of the 4,950**
companies in the window. Company-conditioned features will be null for a real share of production
traffic — the `has_history` flag pattern is not optional.

---

## LOW

- **L1** `narratives.parquet` (1.5 GB) is fully redundant with `meta.parquet`, which already carries
  the narrative column. Retained only because EDA cells 3b/4/5 read it.
- **L2** `learning_log.md:18` and `TriageIQ.md:112` still reference
  `Data/data/interim/triageiq_tickets_v1.parquet`, which was **deleted**.
- **L3** `TriageIQ.md:12` points v1 readers at `Context/TriageIQ_v1_archive.md`; the file moved to
  `Context/old_context/`.
- **L4** `pyproject.toml` description is still the v1 framing: *"Customer support ticket escalation
  prediction system."*
- **L5** `data_profile.md` gate metrics (dup rate, CV, TTR, opener) are carried over from Cell 3b
  outputs on the *raw* corpus; they were never recomputed on the v2 set.

---

## Tier 2 — NOT AUDITED

Design soundness was deliberately not assessed, because the auditor for pass 2 authored the design.
Unexamined: whether monetary relief is the right operationalisation; whether the star schema can
answer the Phase-1 features at a point in time; whether the 60-day outcome-lag frame is the right
conservatism; whether the two-tier rule survives contact with real SQL. **Hand these to an
independent model before writing the DDL.**

---

## The single thing most likely to break this project

**Not** the modelling. It is **C1 — no commits.** Every other finding here is a number to correct or
a filter to make group-aware. C1 is the one where a single mistake erases the 9.2GB-derived
artifacts, the notebook, and every document, with no way back. Fix it in the next five minutes.

Second place: **H1's root cause** — target encoding fitted on resampled data. It cost 0.032 AUC in a
toy baseline; wired into the Postgres feature pipeline and then contradicted at serving time, it is
exactly the silent train/serve skew ground rule 4 exists to prevent.

---

## Resolution status — updated 2026-09-25

The findings above are left exactly as written; this section tracks what happened to each.

| finding | status | how |
|---|---|---|
| **C1** no version control | ✅ **fixed** | committed and pushed to GitHub; personal docs gitignored; secret scan before first push |
| **H1** baselines on the wrong dataset | ✅ **fixed** | every doc now quotes shipped-artifact (F3) numbers from `FACTS.md` |
| **H2** ablation code missing | ✅ **fixed** | `training/verify_ablation.py`; within-company AUC added |
| **H3** scikit-learn undeclared | ⏳ open | still not in `pyproject.toml` |
| **H4** narratives straddling splits | ⏳ open | needs group-aware splitting in EDA Cell 8 before Phase 2 |
| **M1** all-time cardinalities | ✅ **fixed** | `FACTS.md` states three frames; DDL sizing uses F1 |
| **M2** null rates from wrong frame | ✅ **fixed** | same |
| **M3** stale `Timely response?` figure | ✅ **fixed** | 99.62% (F1) |
| **M4** `Submitted via` wrong-frame verdict | 🔶 decision pending | schema open item |
| **M5** NULL outcome labelled 0 | 🔶 decided, not built | label view will exclude NULLs; the v2 parquet still holds 1 such row |
| **M6** cold start | 📝 noted | `has_history` flags required in the feature view |
| **L1** redundant `narratives.parquet` | ⏳ open | |
| **L2** references to deleted file | ✅ **fixed** | |
| **L3** stale archive path | ✅ **fixed** | |
| **L4** v1 description in `pyproject.toml` | ⏳ open | |
| **L5** gate metrics not recomputed on v2 | ⏳ open | |
| **Tier 2** design soundness | ⚠️ **still unaudited** | `audit.md` now points the next auditor at the 11 schema decisions |

**Found after the audit, also fixed:**
- `FACTS.md` claimed to be generated by `canonical_facts.py`, but that script only wrote JSON — re-running
  it would not have regenerated the file. It now renders `FACTS.md` itself and reads baselines from
  `ablation_results.json`.
- The bible's §0.3 still advised ordering windows by `(date_received, complaint_id)` "everywhere" —
  contradicting its own §1.4a, which proved that breaks `RANGE` interval frames.
- `WHAT_WHY.md` quoted a within-company AUC of 0.768 from a different experiment (a five-product subset).
  Measured on the shipped data it is **0.8034** — and it revealed that within a company, **text beats
  metadata** (0.7900 vs 0.7463), the reverse of the within-strata ordering.
