# Reading *Designing Machine Learning Systems* (Chip Huyen, O'Reilly 2022)

How to read and understand this book, and how each chapter connects to TriageIQ. You already know how to
learn from lectures. This file turns that habit into one for books.

## You already know how to do this

| with a lecture you… | with this book you… |
|---|---|
| watch a part | read **one section** (one heading), not a whole chapter |
| pause and take notes | **close the book** and write what you remember, in your own words |
| code along | fill the **book → TriageIQ** table: where does this idea live in our project? |
| build the project | do **one small action** in TriageIQ per chapter |
| rewatch a confusing bit | re-read the paragraph **once**; still unclear → mark `?` and move on |

The book is the lecture. TriageIQ is the lab.

---

## The loop for every chapter (two sittings of about an hour each; an estimate)

**1. Survey (10 min, before reading anything properly).**
Read the chapter intro, every heading, every figure and table, and the summary at the end. Then write:
- 3 questions you expect the chapter to answer;
- 1 question about TriageIQ ("does our pipeline do this?").

This is the trailer before the film. Your brain now knows where to put things.

**2. Read one section at a time (20–30 min each).**
- Read to *understand*, not to finish. Pencil or a notes app, never a highlighter (highlighting feels like
  learning but isn't).
- Mark only two kinds of thing: **!** = surprised you or contradicts what you thought; **→T** = connects to
  TriageIQ.
- Skip footnotes and paper references on the first pass. The book cites a lot of papers; follow one only if
  you're curious afterwards.

**3. Close the book and recall (5 min per section).**
- Write 3–5 bullet points from memory, in your own words. Only then open the book and check what you
  missed. This is the step that makes it stick: pulling an idea out of memory beats re-reading it.
  *(tech: retrieval practice)*
- If you can't write anything, the section didn't land. Re-read it once.

**4. Connect it to TriageIQ.** For each main idea, one row:

| idea from the book | where it is in TriageIQ | same / different / missing? |
|---|---|---|

"Missing" rows are the gold: they're either a gap in the project or a good interview answer
("I didn't do X because…").

**5. Act: one small thing in the project per chapter.** Suggestions are in the chapter plan below.

**6. Review.**
- **Next day:** spend 5 minutes reading your notes.
- **End of the week:** explain the chapter out loud in 2 minutes, as if to an interviewer. Where you stumble
  is exactly what to re-read.
- Bring the leftover `?` marks to the main chat (the gap rule).

### Notes template (one per chapter; keep them in `Learning/book_DMLS_notes.md`)

```
## Ch N — <title>                         read: <date>
Before: my 3 questions + 1 TriageIQ question
Recall (my words, book closed):
- ...
Book → TriageIQ:
| idea | where in TriageIQ | same / different / missing |
One action in the project:
Still confused (?):
2-minute explanation done: yes / no
```

### Reading critically
- The book is from 2022. **The principles last; the tool names date.** When it names a tool, ask "what
  problem does this solve?" and remember that, not the brand.
- Disagreeing is allowed. TriageIQ made choices the book might not, e.g. features in SQL rather than a
  feature store. Write down why. That's an interview answer.

---

## Which chapters, in which order (not cover to cover)

**Start with chapters about things you've already done.** You'll recognise most of it, so you can practise
the reading loop without also fighting new ideas. Then read each Phase 3 chapter just before its step.

| order | chapter | when | why now |
|---|---|---|---|
| 1 | **Ch 1**: Overview of ML Systems | Weekend 1 | short; sets the vocabulary (research vs production ML) |
| 2 | **Ch 5**: Feature Engineering | Weekend 1 | you lived it (Phase 1): the easiest place to practise the loop |
| 3 | **Ch 4**: Training Data | weekdays | you lived it too (Phase 2): sampling, labels, class imbalance |
| 4 | **Ch 6**: Model Development and Offline Evaluation | before step 3.1 | baselines, **calibration**, slice-based evaluation |
| 5 | **Ch 7**: Model Deployment and Prediction Service | before 3.2–3.3 | batch vs online prediction, model compression |
| 6 | **Ch 8**: Data Distribution Shifts and Monitoring | before 3.9 | drift types, what to monitor |
| 7 | **Ch 9**: Continual Learning and Test in Production | before 3.9 | retraining, shadow / A/B / canary |
| 8 | **Ch 10**: Infrastructure and Tooling for MLOps | around 3.6 | schedulers, feature stores, build vs buy |
| 9 | **Ch 2**: Introduction to ML Systems Design | before interviews | framing: business vs ML objectives, requirements |
| 10 | **Ch 11**: The Human Side of ML | before interviews | user experience, responsible AI |
| — | **Ch 3**: Data Engineering Fundamentals | skim | you know most of it; read "formats" and "modes of dataflow" |

---

## Chapter by chapter: what to look for, and what to do

### Ch 1 — Overview of ML Systems
- **Look for:** how ML in production differs from ML in research, and when *not* to use ML.
- **TriageIQ question:** could a simple rule have done the job? *(We measured: a "low-payout products get a
  template" rule would template a $200k student-loan case. Phase 0 story.)*

### Ch 5 — Feature Engineering ← start here
- **Look for:** the section on **data leakage** and its list of common causes.
- **Act:** audit our pipeline against that list, one row per cause. You'll find most are handled:
  - random split of time data → our split is by date;
  - scaling before splitting → we standardise with train-only statistics;
  - filling gaps with statistics from the test split → our smoothing prior is as-of date;
  - duplicates across splits → the "one text, one split" rule;
  - group leakage → the same rule;
  - leakage from how the data is generated → the label lives in the event log; post-intake columns are never
    features.

  Write down the ones you'd defend in an interview.
- **Connect:** `Learning/Phase1/revision.md`, cards 1, 7, 10.

### Ch 4 — Training Data
- **Look for:** *natural labels* and *feedback loop length*; sampling methods; the **class imbalance** section
  (metrics, resampling, cost-sensitive and focal losses).
- **TriageIQ:**
  - Our label is a natural label with a long loop (we assume up to 60 days).
  - Case-control sampling is a form of weighted sampling.
  - Our four imbalance options are in `Phase2/revision.md` card 15.
- **Act:** find one method in the book we didn't consider, and write one line on whether it would help.

### Ch 6 — Model Development and Offline Evaluation
- **Look for:** **baselines** (random, heuristic, simple model); the evaluation methods: perturbation tests,
  invariance tests, **model calibration**, slice-based evaluation.
- **TriageIQ:** TF-IDF = our baseline; the 512 slice = slice-based evaluation; calibration = step 3.1.
- **Act (ideas for 3.1–3.2):**
  - an **invariance test**: change only the `state_id` of 1,000 test complaints and measure how much scores move;
  - a **perturbation test**: delete the dollar amount from the text and see if the score drops.

### Ch 7 — Model Deployment and Prediction Service
- **Look for:** batch vs online prediction; **model compression** (distillation, pruning, quantization).
- **TriageIQ:**
  - Our design is a hybrid: the 150k demo complaints are scored in advance (batch); typed-in complaints are
    scored on request (online).
  - DistilBERT is itself a distilled model. int8 = quantization (step 3.2).
- **Act:** write 3 lines on why online scoring needs the feature snapshot (step 3.3) and batch scoring doesn't.

### Ch 8 — Data Distribution Shifts and Monitoring
- **Look for:** covariate shift vs label shift vs concept drift; *degenerate feedback loops*; what to monitor.
- **TriageIQ:**
  - 2024's falling payout rate = label shift.
  - The "clock" features we removed = covariate shift.
  - Feedback-loop question for interviews: if seniors handle the top-scored complaints, could that *change*
    whether they pay, and so change the labels the next model learns from?
- **Act:** step 3.9's month-by-month drift report.

### Ch 9 — Continual Learning and Test in Production
- **Look for:** stateless retraining vs stateful training; how often to update; shadow deployment, A/B tests,
  canary releases.
- **TriageIQ question:** how would you safely replace the v3 model with a retrained one? Write the answer in
  5 lines; it goes into step 3.9's "Explain it back".

### Ch 10 — Infrastructure and Tooling for MLOps
- **Look for:** schedulers vs orchestrators; the **feature store**; build vs buy.
- **TriageIQ:** our "feature store" is a materialized view plus SQL; the missing refresh job is a scheduler's
  job. Interview answer: why we didn't use a feature-store product.

### Ch 2 — Introduction to ML Systems Design
- **Look for:** business objective vs ML objective; reliability, scalability, maintainability, adaptability.
- **TriageIQ:** the business goal is "seniors see the costly complaints first", so the ML objective is a
  *ranking* (AUC, recall at top 10%), not accuracy.

### Ch 11 — The Human Side of ML
- **Look for:** user experience of ML predictions; responsible AI.
- **TriageIQ question:** `is_older_american` is an input, and it raises scores (Older Americans pay 10.08% vs
  1.06% untagged, all complaints). Is it fair to use? Write your answer. It's a likely interview question.

---

## If reading feels slow
That's normal at the start. A technical chapter read properly takes far longer than a novel. Two sittings per
chapter is fine. Understanding 3 chapters deeply beats skimming 11. When a chapter is done, tick it here:

- [ ] Ch 1 · [ ] Ch 5 · [ ] Ch 4 · [ ] Ch 6 · [ ] Ch 7 · [ ] Ch 8 · [ ] Ch 9 · [ ] Ch 10 · [ ] Ch 2 · [ ] Ch 11 · [ ] Ch 3 (skim)
