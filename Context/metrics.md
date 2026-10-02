# How TriageIQ keeps score — every metric, defined once

Values live in `Context/FACTS.md` ("Model comparison on training set v3"). This file only says **what each
metric means, how it is computed, where the code is, and why it is (or isn't) used.**

**The setting:** about 1 in 40 test complaints ends in a payout (2024 test: 2.31%). The desk's question is
not "pay or not?" but **"which complaints first?"** — so almost every metric here is a **ranking** metric.

---

## The headline: within-company AUC

| | |
|---|---|
| **Question** | Inside ONE company's queue, does the model put the complaints that will pay above the ones that won't? |
| **Computed** | ROC-AUC inside each company with ≥ 20 payouts and ≥ 200 test complaints (24 companies in 2024), then averaged, weighted by the company's complaint count |
| **Code** | `within()` in `training/test.ipynb` and `training/fusion_distilbert.ipynb` (same rule in both) |
| **Why headline** | It is what a deployed bank experiences: "which company" is constant inside its own queue, so the easy between-company signal can't inflate it |
| **Caveat** | Only 24 companies → noisy; always quote with its 95% range (below) |

## The three AUC frames (CLAUDE.md trap 5)

ROC-AUC = the chance that a randomly chosen payout complaint is scored above a randomly chosen
non-payout one. 0.5 = coin flip, 1.0 = perfect. Unaffected by how rare payouts are.

| frame | compares complaints… | flattered by | use |
|---|---|---|---|
| **pooled** | from anywhere in the test set | knowing that card complaints pay more than credit-report ones | context only — never alone |
| **within product × issue** | of the same product and issue (strata with ≥ 25 payouts, ≥ 150 complaints), size-weighted | company identity | how well the model reads the *case* |
| **within company** | of the same company | nothing structural | **the headline** |

## 95% range (bootstrap)

| | |
|---|---|
| **Question** | Is a difference between two models real, or luck? |
| **Computed** | Resample the test complaints inside each scored company (with replacement), recompute the within-company AUC; 1,000 times; report the 2.5th–97.5th percentiles |
| **Code** | `within_company_ci()` in `training/evaluate_fusion.py` |
| **Reading** | Ranges that don't overlap → the gap is real. Heavy overlap → may be luck. (Overlap is a conservative test; a paired bootstrap would be sharper.) |

## PR-AUC (average precision)

| | |
|---|---|
| **Question** | Along the ranking, how many of the complaints flagged so far are real payouts, as more payouts are found? |
| **Computed** | `average_precision_score` on the natural-prevalence test set |
| **Why** | Focuses on the rare class; at 2.31% payouts, ROC-AUC can look great while the top of the list is still mostly false alarms |
| **Caveat** | Moves with the base rate — only compare on the same test set; never on a resampled one (that would inflate it ~10×) |
| **Also** | **Selects the best epoch** (validation PR-AUC) in `fusion_distilbert.ipynb` |

## Riskiest X% catches Y% of payouts (recall at top-k)

| | |
|---|---|
| **Question** | If seniors read only the top 5 / 10 / 20% of complaints by score, what share of all payouts do they see? |
| **Computed** | Sort the 2024 test set by score; payouts in the top k% ÷ all payouts. Pooled across companies. |
| **Code** | cell 6c of `training/test.ipynb`; `recall_at` in `training/evaluate_fusion.py` |
| **Why** | The business sentence: "reading the riskiest 10% catches 93% of payouts" |

## Slice AUC — complaints cut at 512 vs complaints that fit

| | |
|---|---|
| **Question** | Does cutting long complaints at DistilBERT's 512-piece limit lose information? |
| **Computed** | ROC-AUC separately on test complaints longer than 510 word-pieces and on the rest |
| **Reading** | Compare the neural model's cut-slice score with TF-IDF's (which reads every word). Long complaints are harder for every model, so a gap alone proves nothing |

## Calibration — predicted share vs real share

| | |
|---|---|
| **Question** | When the model says "3% chance", do ~3% pay? |
| **Computed** | Mean predicted probability after the case-control correction (logit + offset −2.4165, from the manifest) vs the actual test payout rate |
| **Caveat** | The offset fixes the *sampling*, not the *drift* (payouts fall year by year) — trap 13. Ranking metrics are unaffected; any probability shown to a person must be re-tuned on recent data |

## Brier score

| | |
|---|---|
| **Question** | How close are the predicted probabilities to what happened (0 or 1)? |
| **Computed** | mean of (predicted − actual)² — lower is better |
| **Used** | Choosing the smoothing strength K (`sql/03_features/05a_choose_k.sql`, together with AUC) |

## Single-feature AUC (feature screening)

| | |
|---|---|
| **Question** | How much signal does one input carry on its own — pooled and inside a company? |
| **Used** | Deciding which of the 40 stored features become model inputs (`sql/03_features/feature_dictionary.md`) |
| **Caveat** | Company-level inputs can't score inside one company (they barely vary there) — weak alone ≠ useless |

## Training loss (binary cross-entropy)

What the network minimises while learning. Watched for stability (it should fall epoch by epoch); never
reported as a result — it is measured on the resampled training set.

---

## Deliberately NOT used

| metric | why not |
|---|---|
| **Accuracy** | Saying "no payout" to everything scores ~97.7% on 2024 and helps nobody (the accuracy paradox) |
| **F1 / F2-score** | They need a fixed yes/no cut-off. We rank instead. F2 (recall weighted ×2 — a missed payout costs more than an extra review) is the candidate **when the desk picks its cut-off** from its capacity |
| **Any score on a resampled test set** | Case-control sampling is applied to train only; val/test stay at the real payout rate |
