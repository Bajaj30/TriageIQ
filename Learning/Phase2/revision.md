# Phase 2 — Revision: training set, DistilBERT fusion, honest evaluation

Interview prep for `sql/04_training_set/`, `sql/05_export/`, `training/` (notebooks, evaluation, error
analysis). Metrics are defined once in `Context/metrics.md`; results are in `Context/FACTS.md`
("Model comparison on training set v3"). Unless stated, scores are on **the 2024 test set: 150,000
complaints, 3,471 payouts (2.31%)**.

**The one-line version:** *"DistilBERT reading the complaint, fused with 19 SQL track-record inputs,
scores 0.8224 inside a single company on 2024 data — beating text-only (0.8036) and a TF-IDF baseline
(0.8115) — and the ablation, a half-data test and error analysis show the remaining gap is the company's
own decision, which isn't in the text."*

---

## A. The training set (`sql/04_training_set/02_training_set.sql`, v3)

### 1. Split by time, never at random
- **Idea:** the model will face the *future*, so test it on the future.
- **In TriageIQ:** train < 2023-10-01 · val Oct–Dec 2023 · test 2024. Payouts fall every year (complaints
  with text: 2.74% → 2.51% → 1.71%) — a random split would hide that.
- **Q:** Why temporal? → **A:** A random split lets the model learn from complaints *after* the ones it's
  tested on and hides drift; production never gets that luxury.

### 2. Group leakage — one text, one split
- **Idea:** identical texts in train and test let the model "remember" answers.
- **In TriageIQ:** a text belongs to the split where it *first* appeared; later copies are dropped, never
  moved (106,942 complaints dropped, only 9 of them payouts). At most 25 copies of one text (195,545 dropped,
  14 payouts). Unique texts pay 3.84%; texts seen 2+ times ≤ 0.05% (complaints with text, from April 2022)
  — templates almost never pay.
- **Q:** What is group leakage? → **A:** Related rows (same text, same user) split across train and test,
  so the test measures memory, not generalisation.
- **Watch/Read:** paper — Kapoor & Narayanan, "Leakage and the Reproducibility Crisis in ML-based Science" (2023).

### 3. Case-control sampling + the correction you can undo
- **Idea:** keep **every** payout and only some non-payouts so training is fast and balanced; afterwards
  shift every prediction back by a known amount.
- **In TriageIQ:** train = all 15,735 payouts + 3 non-payouts each = 62,940 (25% payouts). Non-payouts kept:
  8.92% → correction **logit + ln(0.0892) = −2.4165** (read from the manifest, never typed). Val/test stay at
  the real rate. Only train is resampled — PR-AUC on a resampled test would be inflated.
- **Q:** Why is the offset ln(keep-fraction)? → **A:** Keeping a fraction f of negatives multiplies the odds
  of a payout by 1/f; adding ln f to the log-odds undoes exactly that.
- **Watch:** StatQuest — "Odds and Log(Odds), Clearly Explained!!!". *Paper:* King & Zeng (2001), "Logistic
  Regression in Rare Events Data".

### 4. Text quality and the warm-up
- **In TriageIQ:** ≥ 20 real words (one rule instead of min-words + "≤ 30% blanks"); start 2022-04-01 (the
  first months have no track record yet). Seed 42 via `md5('42:' || complaint_id)` → same rows every run.

---

## B. Reading the text

### 5. Tokenization — word-pieces
- **Idea:** models read sub-word pieces from a fixed vocabulary ("charged" → "charged"; rare words split into
  pieces). DistilBERT reads at most **512** pieces. *(tech: WordPiece, a cousin of BPE)*
- **In TriageIQ:** 1.24 pieces per word (median) → 512 ≈ 410 words; 91.8% of complaints fit (20k sample of
  complaints with text). In the 2024 test, 8.4% get cut.
- **Q:** Why not lemmatize/remove stopwords to fit more? → **A:** Measured: even a perfect lemmatizer fits
  only 22% of long complaints, and stopword lists delete *not / no / never* — meaning lost.
- **Watch:** Andrej Karpathy — "Let's build the GPT Tokenizer".

### 6. Redactions → special tokens, in SQL
- **Idea:** the CFPB hides private details as `XXXX`; collapse each run into one marker — keep *that* a blank
  was there, drop the wasted pieces.
- **In TriageIQ:** 15.5% of all pieces were blanks (20k sample). `clean_narrative()` (SQL) → `[DATE]`,
  `[REDACTED]`, registered as **special tokens** (otherwise `[REDACTED]` = 5 pieces) + embeddings resized.
  Training export **and** the API call the same SQL function → no train/serve skew.
- **Q:** Why in SQL, not Python? → **A:** One implementation shared by training and serving.

---

## C. The models

### 7. Baseline first — TF-IDF + logistic regression
- **Idea:** TF-IDF = word counts, weighted down for words every complaint uses; logistic regression = a
  weighted sum of inputs squeezed into a probability by the sigmoid.
- **In TriageIQ:** `training/test.ipynb` — text 0.7956 · SQL features 0.7500 · fusion **0.8115** (the bar).
- **Q:** Why build a baseline? → **A:** Without one, you can't say whether the expensive model earns its cost.
- **Watch:** StatQuest — "Logistic Regression" series.

### 8. Transformers, BERT, DistilBERT
- **Idea:** *attention* lets each word look at every other word to decide what it means in context. BERT is
  pre-trained by guessing hidden words in huge text, then **fine-tuned** on your task. DistilBERT is BERT
  *distilled*: a smaller student trained to copy a big teacher — 40% smaller, 60% faster, ~97% of the skill.
- **In TriageIQ:** `distilbert-base-uncased`; the `[CLS]` position's 768-number output summarises the text.
- **Q:** Why DistilBERT, not a bigger/long-context model? → **A:** Free T4 GPU; and measured: the read-every-word
  baseline ties it on long complaints (0.9614 = 0.9614), so length isn't the bottleneck.
- **Watch:** 3Blue1Brown — "Attention in transformers, step-by-step"; StatQuest — "Transformer Neural Networks";
  Stanford CS224N — the Transformers and Pretraining lectures; Hugging Face course ch. 1–3 (has videos).

### 9. The fusion architecture
- **Idea:** two branches, one head: a text branch and a table branch, joined before the final decision.
- **In TriageIQ (`training/fusion_distilbert.ipynb`):**
  text: `[CLS]` 768 → 128 · table: **embeddings** for the 4 categories (product 4, sub-product 8, issue 12,
  state 8 numbers each) + 15 numeric/flag inputs standardised with **train** mean/std → 128 → 64 ·
  head: 192 → 64 → 1 logit.
- **Q:** What's an embedding for a category? → **A:** A small learned vector per value, so similar categories
  end up close — better than one-hot for many values. Preprocessing is fitted on train only and saved
  (`preprocessing.json`) for serving.
- **Watch:** fast.ai *Practical Deep Learning* — the collaborative-filtering / embeddings lesson.

### 10. Training mechanics
- **Idea → In TriageIQ:**
  - **Loss:** binary cross-entropy on the logit (`BCEWithLogitsLoss`).
  - **Optimizer:** AdamW, weight decay 0.01; **two learning rates** — encoder 2e-5 (gentle, it's pre-trained),
    new layers 1e-3; 5% warm-up.
  - **Freeze the encoder in epoch 1:** the new head starts random; its noisy gradients would damage the
    pre-trained weights. Train the head first, then everything. *(ULMFiT: gradual unfreezing)*
  - **Early stopping** on validation PR-AUC, ≤ 3 epochs, patience 1.
  - **fp16 mixed precision** + gradient scaler on the T4 (no bf16 on that GPU).
  - **Length-grouped batches:** 2.23× fewer padded pieces. Plain dynamic padding gave 1.00× — one long text
    per batch pads everything anyway.
  - ~481 s per epoch on one T4.
- **Q:** Why different learning rates? → **A:** Pre-trained layers need small nudges; new layers need to learn
  from scratch.
- **Watch:** StatQuest — "Neural Networks Part 6: Cross Entropy"; 3Blue1Brown — "Neural networks" series;
  *paper:* Howard & Ruder (2018), ULMFiT.

---

## D. Evaluation and what it taught

### 11. Three frames of AUC — and the honest one
- **Idea:** AUC = how often a random payout is ranked above a random non-payout. *Pooled* is flattered by
  "credit cards pay more than credit reports"; **within-company** is what one bank sorting its own queue sees.
- **In TriageIQ (DistilBERT fusion):** within product × issue 0.9492 · **within-company 0.8224**. Pooled is
  higher still (TF-IDF fusion: 0.9713).
- **Q:** Why is your headline the lowest number? → **A:** It matches deployment; the others include
  between-company differences no single bank can use.
- **Watch:** StatQuest — "ROC and AUC, Clearly Explained!".

### 12. Metrics we use — and refuse
- PR-AUC (focus on the rare class) · **recall at top-k**: the riskiest 10% catches **92.6%** of payouts ·
  slice AUC · Brier · **95% bootstrap range** (1,000 resamples inside each company): 0.815–0.830.
- **Refused:** accuracy — "never pays" is 97.7% accurate on 2024 and useless.
- **Q:** How do you know a gain isn't luck? → **A:** Bootstrap ranges; heavy overlap means maybe luck.
- **Watch:** StatQuest — "Bootstrapping Main Ideas!!!". Definitions: `Context/metrics.md`.

### 13. The ablation — is SQL + text worth it? (within-company, 95% range)

| model | score |
|---|---|
| SQL features, small network | 0.7537 (0.744–0.763) |
| DistilBERT, text only | 0.8036 (0.796–0.812) |
| TF-IDF fusion | 0.8115 |
| **DistilBERT fusion** | **0.8224 (0.815–0.830)** |

- **Q:** Did the SQL features matter? → **A:** Yes: text-only → fusion moves the range clear of overlap, and
  top-10% recall goes 88.8% → 92.6% — about 130 more payouts found for the same reading effort.

### 14. Slice evaluation — does cutting at 512 hurt?
- **In TriageIQ:** cut complaints (8.4% of the test set) pay more (3.41% vs 2.21%) and are harder for *every*
  model, even one that reads no text. DistilBERT on that slice 0.9614 = TF-IDF (reads every word) 0.9614 →
  the cut costs nothing.
- **Q:** How did you decide not to use a long-context model? → **A:** Compared against a read-everything
  baseline on exactly the cut slice — a tie.
- **Read:** Chip Huyen, ch. 6 (slice-based evaluation).

### 15. Class imbalance — options, and a cheap test before an expensive one
- **Options:** undersample (ours) · weighted loss on all rows (~34× weight) · SMOTE (rejected for text — two
  half-complaints aren't a complaint) · focal loss.
- **Half-data test:** train on 50% → 0.8166 vs 0.8224 — inside the range. If halving doesn't hurt, doubling
  won't help → saved ~3.5 GPU-hours. *(Read off a Kaggle draft session; not in FACTS.md.)*
- **Q:** Why not train on all 480k extra non-payouts? → **A:** They add no new payouts, and the half-data
  learning-curve check showed data isn't the bottleneck.
- **Watch:** Andrew Ng — *Structuring Machine Learning Projects* (Coursera). *Book:* Chip Huyen, ch. 4.

### 16. Error analysis — finding the ceiling
- **Idea:** read the worst mistakes yourself before trying a bigger model.
- **In TriageIQ (`training/error_analysis.py`):** missed payouts = "surprise" payouts on complaint types that
  almost never pay (credit reports, logins) — likely goodwill. False alarms read exactly like refunds (named
  fee, amount, unauthorised charge) — the company just said no. The deciding fact is inside the company.
- **Q:** How would you get to 0.9? → **A:** Probably not with a bigger reader: the missing information isn't
  in the text. It would need company-side data (policies, account history).
- **Watch:** Andrew Ng — "Carrying out error analysis" (Structuring ML Projects).

### 17. A new clue only helps if the model doesn't already have it
- **In TriageIQ (v4):** dollar amounts in the text (19.2% of complaints with text mention one; they pay
  7.10% vs 0.99%) lifted the SQL-only model 0.7537 → 0.7779 — but fusion stayed the same (0.8195 vs 0.8224):
  DistilBERT already reads "$760". Kept the simpler 19-input v3.
- **Q:** A feature helped one model but not another — why? → **A:** Information overlap.

### 18. Calibration drift
- **In TriageIQ:** after the −2.4165 offset, the model predicts 3.11% on 2024; 2.31% actually paid. The offset
  fixes the *sampling*, not the year-on-year fall (prior shift). Ranking is unaffected; probabilities must be
  re-tuned on recent data → Phase 3, step 3.1.

### 19. Reproducibility on a free GPU
- Manifest with sha256, row counts and the offset; Kaggle Cell 1 checks them before training · seed 42 ·
  results JSON per run → `canonical_facts.py` regenerates FACTS.md · Kaggle: only **Save Version** keeps
  outputs (a draft session's files vanish when it stops).

---

## What broke, and the fix

| what happened | fix | lesson |
|---|---|---|
| v2 code dropped whole 26+ copy clusters (docs said "cap at 25") | v3: a true cap of 25 | read the code, not the comment |
| 721 texts straddled train/val/test | "one text, one split" rule | duplicates are a leakage group |
| Kaggle log froze; the assistant advised stopping a healthy run | check the Output tab / metrics.json first | the UI isn't the job |
| Half-data run used text-only (default MODE), then draft outputs vanished | set MODE explicitly; Save Version | defaults and drafts bite |
| Mac: TensorFlow import broke transformers; MPS out of memory | `USE_TF=0`; smaller eval batch, test on CPU | laptop = smoke tests only |
| "0 dollar amounts found" | bash ate the `$` in the regex → run SQL from files | look at real rows before trusting a zero |
| `[REDACTED]` cost 5 pieces | special tokens + resized embeddings | measure the tokenizer's view |

## Numbers to know
Train **62,940** (15,735 payouts, 25%) · val **80,000** (Oct–Dec 2023, 3.50%) · test **150,000** (2024,
2.31%, 3,471 payouts) · offset **−2.4165** · fusion within-company **0.8224 (0.815–0.830)** · top 10% →
**92.6%** · predicted 3.11% vs actual 2.31% · ~481 s/epoch on one T4.

## Lectures to re-watch
- StatQuest: Logistic Regression · Odds and Log(Odds) · ROC and AUC · Bootstrapping · Cross Entropy ·
  Transformer Neural Networks.
- 3Blue1Brown: Neural networks series; "Attention in transformers, step-by-step".
- Andrej Karpathy: "Let's build the GPT Tokenizer".
- Stanford CS224N: Transformers; Pretraining.
- Hugging Face course ch. 1–3 · fast.ai embeddings lesson · Andrew Ng: Structuring ML Projects.
- *Books / papers:* Chip Huyen ch. 4, 6 · King & Zeng 2001 · Howard & Ruder 2018 (ULMFiT) · Sanh et al.
  2019 (DistilBERT) · Kapoor & Narayanan 2023 (leakage).
