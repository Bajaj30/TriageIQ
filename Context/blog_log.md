# TriageIQ — Blog log

Raw material for the project blog, written for **readers with little tech background**: plain words,
everyday comparisons, and the reason behind every choice. Technical names appear only as small
*(tech: …)* tags, so the blog can keep or drop them. New entries go at the bottom of their section.

**How numbers are described.** Every number says which group of complaints it comes from:
- **all complaints** — the 4,826,564 complaints from 2022–2024
- **complaints with a story** — the 1,639,068 where the customer's own written account is published
- **the training set** — the 301,460 complaints used to train and test the AI

*(Internally these are called F1 / F2 / F3 — never use those names in the blog; readers will think of
the "F1-score".)*

**How scores are described.** "Score out of 100" = take one complaint that ended with a payout and one
that didn't; how often does the model rank the payout one higher? 50 is a coin flip, 100 is perfect.
*(tech: ROC-AUC × 100)*

---

## 1. The story so far

1. **Getting to know the data.** The file was 9.2 GB — too big to open at once — so we read it in
   slices. We proved the complaints were written by real people, not a machine, and built a first
   training set.
2. **The big change of plan.** The original design invented customers with purchase histories. The
   public data has no customers at all — every complaint is anonymous — so the plan switched to tracking
   *companies* and how they handle each kind of problem.
3. **The honest-score moment.** The first scores looked amazing, but mostly because the model knew
   *which product* or *which company* a complaint was about. We changed how we test.
4. **Designing the database.** 17 decisions, each tied to one idea you could explain on a whiteboard.
5. **Loading the data.** 17.4 million raw complaints copied in, then sorted into linked tables. ✅ Done.
6. **Next:** build every company's track record in the database → train the AI reader → put it online.

---

## 2. Ideas we threw away — and why

1. **Inventing customers.** The complaints are anonymous, so there was no customer to attach a history
   to — and invented data can't be checked by anyone. → *Real data only; history is tracked per company
   and per kind of problem.*
2. **"Balancing" the data by capping each product at 16,000 complaints.** It quietly more than tripled
   the payout rate, from 2.16% to 7.5% (complaints with a story) — like judging how often people win the
   lottery by only asking people outside the lottery office. → *Keep the natural mix. When we need more
   payout examples, we sample in a way we can mathematically undo later.* (tech: case-control sampling)
3. **Deleting every duplicate complaint.** Real people copy-paste the same templates from online forums —
   that's genuine behaviour, not an error. But one template appeared 30,110 times. → *Keep at most 25
   copies of any text* (duplicates fell from 19.8% to 0.3%).
4. **A simple rule: "products that rarely pay out get a template reply".** Student-loan complaints pay
   out only about 1 in 90 times (all complaints), so the rule would send a template to someone whose
   $200,000 loan was never paid out. And the written words still sorted complaints well *inside* such
   products (early tests: mortgages 81, vehicle loans 77 out of 100). → *Score every complaint.*
5. **Predicting "any relief" — money or not.** The company's history alone predicted it so well that the
   AI reader would have been decoration. → *Predict money relief only.*
6. **Predicting how badly the customer was hurt.** No such label exists anywhere, so there's nothing to
   check the model against. → *Predict the company's cost instead — optionally multiplied by the amount
   the customer claims.*
7. **Throwing away the 3.2 million complaints with no written story.** They hold 25,577 payouts — 42% of
   all payouts (all complaints). Without them every company's track record is wrong, by a different amount
   for each company. A single summary number can't replace them either, because a track record is
   different on every date. → *Keep every complaint.*
8. **Moving the complaint date out of the main table because thousands of complaints share a date.** The
   table's rule is "one row per complaint" — that's about rows, not about values repeating. Company names
   repeat too. → *The date stays, and is also copied into the event history.* (tech: grain)
9. **Treating the complaint text like a lookup list.** Each text belongs to exactly one complaint — it's
   an attachment, not a list. → *A side table that holds the text.* (tech: extension table, not a dimension)
10. **Assuming each sub-category belongs to one category.** False: the same sub-category name appears
    under several categories (29 sub-issue names sit under 2 or more issues; 87.5% of all complaints carry
    a sub-product name that's shared). → *A sub-category is identified by its name AND its parent.*
11. **Treating "issue" as a sub-category of "product".** 51 of 93 issues show up under several products.
    → *Two separate lists.*
12. **Matching renamed products by name.** One old product ("Credit card or prepaid card") split into two
    new ones — a name alone can't say which. → *Route each complaint by its sub-product; 14 product names
    become 11.*
13. **Leaving "no sub-issue" blank.** Blanks make 122,207 complaints silently vanish whenever tables are
    combined. → *An explicit "(not specified)" entry.*
14. **Storing the complaint date with a time of day.** The source only records the day; a time would
    invent a fake "midnight". → *Day only.*
15. **Trusting the database's default "look back" setting.** When many complaints share a day, the
    default quietly includes the complaint's *own* outcome in its own history — the answer key leaks into
    the exam. → *Three explicit look-back rules, chosen by what each number means.* (tech: window frames)
16. **One tie-breaking rule for every look-back.** The database refuses it for date-range look-backs.
    → *Pick the rule per feature.*
17. **Working out company payout rates from the training sample.** The sample is 25% payouts, reality
    is about 3.4% — the rates came out distorted and the history-only score lost about 3 points out of 100.
    → *Compute rates in the database, over all 4.8 million complaints.*
18. **Switching now to an AI reader that handles very long texts** (ModernBERT and similar). It's 2.3×
    bigger, its speed trick needs newer GPUs than the free ones, and payouts peak at medium-length
    complaints then *fall*. → *DistilBERT, reading up to 512 word-pieces. For the 8% of complaints that
    are longer: keep the beginning + the end, and check separately how well the model does on them.
    Only if they suffer: read them in 2–3 pieces, and as a last resort, a bigger model.*
19. **The textbook training speed-up** (pad each batch only to its longest text). Measured: no gain at
    all (1.00×) — almost every batch contains one very long complaint. → *Group similar-length complaints
    together: 2.23× less wasted work.*
20. **Google Cloud's $300 free credits for GPUs.** Free-trial accounts have historically been blocked from
    GPUs, and upgrading allows real charges (not re-checked). → *Kaggle's free GPU.*
21. **Using the database already installed on the laptop.** It clashed with the new one, and the project
    must rebuild from a single file. → *A fresh database in Docker.*
22. **Fixing the renamed issue later, inside the analysis.** "Issue" would then mean two different things
    in two places. Nothing depended on it yet, so fixing it at the source took minutes. → *A translation
    table in the database.*
23. **Leaving out complaints the company never answered.** The assistant suggested it, since their final
    outcome is unknown. Rejected: the question is "did this cost the company money?" — and for those
    2,785 complaints no money was paid. → *Count them as "no payout"; only the 19 truly blank outcomes
    are left out.*
24. **Shrinking long complaints with classic text cleanup** — reducing words to their dictionary form
    ("charged" → "charge") or deleting common words. We measured before trying: even a *perfect*
    dictionary-form tool would squeeze only 22% of the long complaints under the limit, and it hands the
    AI unnatural sentences ("I was charge twice"). Deleting common words fits 55% — but the list of
    "common words" includes *not, no, never, nothing*: "I did **not** authorise this charge" becomes
    "authorise charge". → *Only collapse the CFPB's XXXX privacy blanks (meaning survives), keep the
    beginning + end, and read the longest ones in pieces if needed.* (tech: lemmatization, stopword removal)

---

## 3. Surprises

1. **One model, three honest-sounding scores.** On 150,000 complaints from 2024 (the training set's
   test part): **96** when comparing any two complaints, **93** when both are about the same product and
   problem, **80** when both come from the same company. The easy test rewards knowing that credit-card
   complaints pay out more than credit-report ones — true, but useless to a bank sorting its *own* inbox.
2. **Which matters more — the words or the history? It depends who's asking.** Same product and problem:
   history wins (91 vs 89). Inside one company: the words win (79 vs 75). Together they beat both (93, 80).
3. **The answer was almost decided before anyone read the complaint.** In early tests, knowing only the
   product scored 96; knowing only the company scored 98. That's exactly why we test *inside* groups.
4. **The complaints aren't where the money is.** Credit reports: 83% of all complaints, 3% of payouts.
   Credit cards + bank accounts: 6% of complaints, 76% of payouts (all complaints).
5. **Complaints the AI can't read still matter.** 42% of all payouts sit in complaints with no written story.
6. **Payouts are getting rarer every year.** 2.7% → 2.5% → 1.7% (complaints with a story, 2022 → 2024).
   Over the whole public database it's 9.09% in 2012 down to 0.48% in 2025. The final exam is harder than
   the lessons — a test on the future shows this; a random test would hide it.
7. **The regulator changed its own categories halfway through.** In August 2023 the CFPB renamed and
   split products. Loaded naively, credit-report history restarts from zero weeks before our test period.
   1,334,958 complaints were re-labelled (all complaints).
8. **Ties everywhere.** On 43% of the days a company received complaints, it received more than one —
   once, 4,245 in a single day. "The complaints before this one" means nothing without a rule.
9. **Copy-paste was proof of real people.** The most repeated opening line turned out to be legal wording
   (from the Fair Credit Reporting Act) that consumers copy from credit-repair forums — not a machine template.
10. **The database doesn't make the AI faster — it makes its job easier.** Training time is the same. But
    without the database's company histories, the AI would have to guess the company from the text and
    memorise the payout habits of 4,946 companies from just 71,460 examples.
11. **"Reproducible" was a claim, not a fact.** The headline numbers came from scripts nobody saved, and
    the project had no version history for weeks. Re-running on the real training set dropped the
    history-only score from 94 to 91.
12. **Same company, different capital letters.** 4 companies appeared twice ("ATM OPS Inc" / "ATM OPS
    INC") and were merged.
13. **"Missing" wasn't really missing.** All 122,207 complaints with no sub-issue (all complaints) have a
    reason: 45 issues never have one, 3 lack it only for payday loans, and 4 mortgage/payment issues only
    got sub-issues when the form changed in August 2023. For those 4, a blank secretly means "filed
    before August 2023" — a model would learn the *date*, not the problem.
14. **The time window we picked had a trap inside it.** We picked 2022–2024 to balance *how much* data we
    had against *how recent* it was (payout rates keep falling, so old years look different) — not because
    it had the most payouts; 2025 has more. But the CFPB changed its complaint form in late August 2023,
    right in the middle. Products were renamed and split — and, found only *after* loading the main table,
    an **issue** was renamed too: "…a credit reporting company's investigation…" became "…a company's
    investigation…". Same day, same products, same sub-issues: 893,566 complaints under the two names
    (18.5% of all complaints). **It wasn't a leak** — both names are known the moment a complaint arrives.
    It was a *history reset*: the most common issue's track record would have restarted from zero five
    weeks before testing began. **The fix was a small design change** — one translation rule, one extra
    column for the original name — then a full rebuild (337,252 complaints re-labelled). It took minutes,
    only because nothing depended on the old layout yet.
15. **Some companies simply ignore the regulator.** 2,785 complaints are marked "Untimely response"
    (all complaints): the company never answered, so no final outcome exists at all. It's almost entirely
    tiny companies — those with fewer than 10 complaints ignored 13.27% of them; companies with over 1,000
    complaints ignored 21 out of 4.6 million. 77 companies with at least 5 complaints never answered a
    single one. "Late" is different: 18,374 answers came late, and 15,589 of those still closed normally
    (637 even with money paid).
16. **The AI's 512-piece reading limit is roomier than it sounds.** It reads in word-pieces, not words —
    but the typical complaint needs only 1.24 pieces per word, so 512 pieces ≈ 410 words. 92% of
    complaints fit completely; only 8% get cut (random sample of 20,000 complaints with a story). The
    CFPB's "XXXX" privacy blanks cost extra pieces: 1.28 per word with them, 1.17 without.
17. **One in six things the AI reads is a privacy blank.** The CFPB hides names, dates and account
    numbers as "XXXX" — and the AI splits each one into 2 pieces (a hidden date costs 6). Across a random
    20,000 complaints with a story, 15.5% of everything the AI would read is blanks; for 8.6% of
    complaints it's at least 40%. The blanks don't confuse it much — it learns to skip them — but they
    crowd real words out of its 512-piece window. Fix: one short marker per blank. Not deleting them,
    because *where* the blanks are is a clue too: a formal dispute full of hidden account numbers reads
    differently from a short angry story.

18. **"Mostly empty" doesn't mean useless.** The tags column is blank for 94.49% of all complaints —
    it looks like junk. But blank means "no tag", not "missing": consumers tick a box if they're a
    servicemember or an older American (62+). Older Americans' complaints end in a payout 10.08% of the
    time vs 1.06% untagged — and it isn't just which products they complain about: on credit cards it's
    26.41% vs 13.81%. Always ask what a blank *means* before throwing a column away.
---

## 4. Classroom ideas that turned out to matter

- **Word variety** *(tech: type-token ratio)* — how many *different* words a text uses. Machine-written text
  tends to reuse the same words. Twist: the raw data scored 0.065, *below* our own 0.08 "suspicious" line;
  it rose to 0.081 after removing copy-paste floods. The "real people" verdict rested on the other tests.
- **Longer texts reuse more words** *(tech: Heaps' law)* — so word variety only compares fairly at the same
  length. We always measured on exactly 100,000 words.
- **How uneven sentence lengths are** *(tech: coefficient of variation)* — people write unevenly (0.94);
  machine text is suspiciously regular (below 0.35).
- **Accuracy lies about rare events.** A model that always says "no payout" is right almost 99% of the
  time (all complaints) — and useless. We measure how well it *finds* the rare payouts instead, and test on
  data with the real-world rarity. *(tech: PR-AUC, not accuracy)*
- **Missing a payout is worse than a wasted review.** So catching payouts ("recall") comes first. A score
  that weights catching twice as much as precision is a candidate for setting the final cut-off — not used
  yet. *(tech: F2-score)*
- **Sampling you can undo** — keep every payout plus 3 non-payouts for each, then correct the predictions by
  a known amount afterwards. *(tech: case-control sampling; correction −2.2572 on the log-odds scale, from
  keeping 10.46% of non-payouts)*
- **A group average can hide what happens inside the group** *(tech: between- vs within-group variation, a
  cousin of Simpson's paradox)* — the 96 / 93 / 80 scores.
- **No peeking at the future** *(tech: data leakage)* — use only what was known the day a complaint arrived.
- **Test on the future, not a random sample** *(tech: temporal split)* — learn on 2022–Sep 2023, tune on
  late 2023, final exam on 2024.
- **A leak and a shift are different problems** — a leak uses information you wouldn't have yet; a shift
  means the future simply looks different from the past. The 2023 form change was a shift, fixed by
  translating old names into new ones.
- **Don't trust a small sample's average** *(tech: smoothing / shrinkage, empirical Bayes)* — a company with
  3 complaints and 1 payout isn't really a "33% payer"; that's luck. The fix is one line:

  > **smoothed rate = (payouts + K × product rate) / (complaints + K)**

  Read it as: *before looking at a company, pretend it already has K imaginary complaints that paid out at
  its product's usual rate — then add its real ones.* A company with 3 complaints is mostly imaginary
  complaints, so it leans on its product's rate. A company with 5,000 real complaints drowns the imaginary
  ones out and speaks for itself. K sets how many imaginary complaints: small K trusts small samples, big K
  ignores them. (The default is the product's rate, not the overall rate — the overall rate is mostly
  credit reports, which almost never pay.)

  | 3 complaints, 1 paid, a credit card company (product rate ≈ 15%) | smoothed rate |
  |---|---|
  | K = 0 — trust the 3 complaints completely | 33.3% |
  | K = 5 | 21.9% |
  | K = 50 | 16.0% |
  | K = 200 — ignore the company's own history | 15.3% |

  **We measured K instead of guessing it.** On complaints from Oct–Dec 2023 (never the 2024 final exam),
  we tried 12 values and asked: how well does the smoothed rate alone separate complaints that paid from
  those that didn't? For companies with little history, raw rates scored 87 out of 100; smoothing with K = 5
  scored 89; K = 50 (our first guess) 88; K = 500 only 85. Anything from 2 to 7 was about equally good —
  the big win is smoothing *at all*. We picked **K = 5**: just 5 imaginary complaints are enough.

  One puzzle left: on the very first days of 2022, *no* outcome is known yet — not even a product's rate.
  So the default for the default is last year's overall payout rate (2.86% in 2021), which was public
  before our data starts — it can't give anything away. After 60 days every product has its own rate.
- **A translation dictionary for renamed categories** *(tech: crosswalk / mapping table)* — the same tool
  governments use when medical or industry codes get renumbered. A two-column list "old name → new name";
  every complaint looks itself up in it: found → take the new name, not found → keep its own.
- **Database design basics** *(tech: dimensional modelling)* — decide what one row means, keep lists apart
  from events, give every item a stable id number.
- **"Unknown" is not "no" — usually** *(tech: NULL)* — the database keeps blanks as blanks. For the label we
  made a deliberate exception: 19 complaints with no recorded outcome count as "no payout" — 19 out of
  4.8 million can't move anything, and it keeps the rule simple: every complaint gets an answer.
- **Let the database refuse nonsense** *(tech: foreign keys, CHECK constraints)* — it rejects, say, a
  mortgage sub-product filed under credit cards.
- **Look-back windows** *(tech: window functions)* — "how often did this company pay in everything *before*
  today?"
- **Run it twice, get the same result** *(tech: idempotency)* — every load can be safely re-run.
- **Names that change over time** *(tech: crosswalk / concordance table; slowly changing dimension, type 1)* —
  when the regulator renamed categories mid-way, we kept a small translation table (old name → today's
  name) so every complaint shows today's name and each company's history stays in one piece. The
  original name is kept alongside, so nothing is lost.
- **When one box can hold two answers** *(tech: one-hot vs multi-hot encoding)* — the tags column can say
  "Older American", "Servicemember", or both. Treating "both" as a separate, unrelated category would
  hide that it *is* an older American. Two yes/no switches — one per fact — let "both" simply flip both.
- **AI readers have a length limit** — DistilBERT reads at most 512 word-pieces.
- **Old text-cleanup tricks can hurt modern AI readers** *(tech: lemmatization, stopword removal)* —
  they were made for models that just count words. A modern reader understands "charged" vs "charge"
  and needs "not"; stripping them saves little and loses meaning.
- **Long tails** — a few extreme cases (a 30,110-copy template, a few very long complaints) can break
  methods built for typical cases.
- **Older free GPUs can't use the newest number format** *(tech: fp16 vs bf16)* — so we use the older one.

---

## 5. How the database does the heavy lifting

- **Everything lives in one database** (PostgreSQL, in Docker) — it even survived the laptop's Docker
  stopping overnight.
- **Copy the raw data first, clean it second** — all 17,355,295 complaints went in untouched, like
  photocopying documents before marking them up.
- **Saved filters** *(tech: views)* — "only 2022–2024" and "with names translated" are written once and
  reused everywhere, so no step can quietly use a different definition.
- **Rules kept as data, not buried in code** — two small translation tables (12 product rules, 1 issue
  rule) re-label 1,334,958 and 337,252 complaints. Anyone can open them and check.
- **Every step proves itself** — one file per table, and each file ends by checking its own numbers.
- **Run twice, nothing doubles** — every load can be repeated safely.
- **Shrink first, then match** — 4.8 million rows boil down to 293 unique pairs before any matching.
- **Fail loudly, never quietly** — if a complaint's category can't be found, the whole load stops with an
  error instead of silently dropping it. 4,826,564 complaints went in in 81 seconds.
- **Read once, write three times** — each complaint becomes 3 history rows (received, sent, answered) in
  a single pass: 14,479,692 rows in under 2 minutes.
- **"Nothing happened" can still use up ticket numbers** — re-running the history load added 0 rows but
  used up 14.5 million id numbers, like pulling a deli ticket and then leaving the queue. Harmless — and
  a reason never to rely on an id number meaning anything.
- **Change the design early** — the issue fix meant rebuilding every table, which took minutes. Later, the
  same change would break everything built on top.
- **The database refuses bad data** — 12 out of 12 deliberately wrong inserts were rejected.
- **The answer key lives in exactly one place** *(tech: the label as a view)* — "did it pay?" is one saved
  question, not a column copied into many tables. Every later step asks it the same way, so the answer
  can never mean two different things. It returns all 4.8 million answers in about a second.
- **An index is a book's index** — instead of reading all 4.8 million complaints to find one company's
  history on one problem, the database looks it up: 797 complaints found in 0.19 milliseconds, without
  opening the main table at all. Building all 6 indexes took 11 seconds.
- **The answer sheet lives in one place** — the numbers the final exam checks against come from one file,
  produced by a *separate* program that re-does the whole load in a different language (Python instead of
  SQL). Both arrive at the same 10 load numbers independently — much stronger evidence than one program
  checking itself. And the docs and the checks read the same file, so they can never disagree.
- **The database was doing its homework on the floor** — the first volume check ran for over 11 minutes.
  The reason: by default Postgres gets only 4 MB of memory to sort with, so each sort of 4.8 million
  complaints spilled onto the disk — 28 GB of scratch files. Giving it 256 MB brought the same check down
  to 16 seconds. Same answers, same code — one setting. *(tech: work_mem)*
- **Two methods, one answer** — each volume number was recounted a second, completely different way
  (plain counting instead of window functions) for 22 complaints, including both ends of the busiest
  company-day in the data (4,245 complaints). All 22 matched.
- **Proving there's no peeking** — we secretly flipped the answers of 3,495 complaints from one company's
  busiest day (paid ↔ not paid), then recomputed that company's track record. Complaints on the same day
  and up to 59 days later: not a single digit moved. On day 60, the rate jumped from 0.0034% to 0.34% —
  exactly when those outcomes are allowed to be known. Then we undid the flip. A test that can also
  *fail* is the only kind worth trusting. *(tech: leakage test inside a rolled-back transaction)*
- **The track record works before the AI reads a word** — complaints whose company had paid out over 15%
  of the time on that kind of problem really paid 28.74% of the time; where it had paid up to 1%, only
  0.03% did (all complaints).
- **One final exam for the whole load** — a single query checks 21 things at once (every table's size,
  one row per complaint, exactly 3 history rows each, the payout count against the raw file, both
  translation tables) and prints PASS or FAIL for each, in 27 seconds. And we tested the tester: feed it
  one wrong expected number and it flags FAIL. A check that can't fail proves nothing.
- **Why a database at all?** One source of truth: training and the live service read the same numbers
  from the same place. The heavy work on 4.8 million complaints stays in the database; the GPU only sees
  the 301,460-complaint training set.
- **Coming next:** company track records built with look-back windows, the "did it pay?" answer as a saved
  query, and a repeatable way to draw the training sample.

---

## 6. Mistakes and fixes — ours and the AI assistant's

- **Numbers without their group.** Figures from different groups (all years vs 2022–24, a sample vs the
  real training set) got mixed up in the documents, forcing a full correction round. Fix: one generated
  file is now the only source of numbers.
- **The AI assistant said it had done things it hadn't** (a file "saved", a fix "done"). Rule since then:
  never claim something without checking.
- **My own wrong reasons, caught early:** "id numbers are easier to read than names" (backwards — they're
  harder; the real reasons are speed, size and stability); calling the text a "lookup list"; thinking
  repeated dates broke the table; "each sub-category has one parent" (false for 87.5% of complaints).
- **Measuring bugs that looked like data problems:** a search pattern counted the CFPB's "XXXX" privacy
  blanks as template placeholders; 40-character "words" turned out to be web links; one number was measured
  on the wrong group.
- **Tests that assumed fixed id numbers failed** — the database never re-uses an id, even after a failed
  insert. Look things up by name.
- **No version history for weeks**, while the rules said "reproducible".

---

## 7. Loose ends

- Word variety sat below our own threshold on the raw data — explain it properly, or drop that test.
- Smoothing: pull small companies toward their product's rate, not the overall rate — decide when
  building the track records.
- 721 complaint texts appear in more than one of learn / tune / exam — fix before training the AI.
- Where to draw the "send to a senior" line — decide from how many complaints the team can handle.
- We *assume* outcomes are known within 60 days — the CFPB never records when a company answered.
- "Payouts peak at medium length (39.6%)" — the group behind that number wasn't recorded; re-check it
  before publishing.

---

## 8. Pictures to build for the web page

> 🔔 **Reminder:** when building the blog web page, turn each diagram into a proper visual —
> hover or click to see what each table or step holds, how big it is, and *why* it exists.

**Source of truth: [`README.md`](../README.md).** Copy the diagrams from there when building the page —
never keep a second copy here; two copies drift apart. What to reuse, by README section:

| README section | visual |
|---|---|
| 1. The problem | the routing decision · "needle in a haystack" pie · complaints vs payouts pies |
| 2. The idea | two readers, one score |
| 3. Playing fair | no peeking at the future · learn → tune → final exam |
| 4. The data | 17.4M → 301k funnel · the category translation example |
| **5. Under the hood** | **the snowflake** · the journey from raw file to score · the seven track-record steps |
| 6. Results so far | the three tests (bar chart) · words vs track record |
| 7. What changes | without vs with TriageIQ |
| 8. Where the project is | the roadmap |
