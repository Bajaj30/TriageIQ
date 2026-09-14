**TriageIQ --- Engineering Bible**

**Project:** Support ticket escalation prediction --- PostgreSQL feature
engineering + transformer fusion model + containerized cloud
deployment**Audience:** You (solo builder), and any hiring manager who
opens the repo**Status of this doc:** Living document. Every design
decision below states *what it does, why we chose it, how to implement
it, what to expect, and where it will hurt.* When reality contradicts
this doc, update the doc --- that habit is itself a portfolio signal.

**0. Ground Rules and Constraints (read first, re-read often)**

These constraints shape every decision below. Never violate them without
writing down why.

1.  **Sequencing constraint:** SQL is being learned *now*, MLOps
    > *later*. Phases are ordered so each is completable with only the
    > skills available at that point, and each phase ends in a
    > standalone, demo-able artifact.

2.  **No JavaScript, ever.** The \"frontend\" is FastAPI\'s
    > auto-generated Swagger UI. Full stop.

3.  **Budget constraint:** Everything must run on free tiers or a
    > student laptop. No GPU cloud bills. Fine-tuning happens on
    > Colab/Kaggle free GPU or a local GPU if you have one.

4.  **One source of truth for features:** All feature logic lives in SQL
    > inside Postgres. Python never re-implements a feature. This is the
    > training/serving consistency guarantee and the project\'s central
    > architectural claim.

5.  **No data leakage:** Every feature attached to a ticket must be
    > computable using only information that existed *at the moment the
    > ticket was created.* This rule appears in Phase 0 (labels), Phase
    > 1 (window frames), and Phase 2 (train/test split). It is the most
    > common way this class of project silently dies.

6.  **Everything reproducible:** Synthetic data has a fixed random seed.
    > Dataset exports are versioned snapshots. Model runs log their
    > config. If you can\'t rebuild an artifact from the repo, it
    > doesn\'t count as done.

**Definition of done for the whole project:** a public GitHub repo where
a stranger can (a) rebuild the database, (b) rerun feature engineering,
(c) retrain the model from a snapshot, (d) spin up the full stack
locally with one Docker Compose command, and (e) hit a live cloud URL
and get a prediction.

**Phase 0 --- Data Foundation (Weeks 1--2)**

**Goal:** A populated, normalized PostgreSQL database containing
realistic ticket text + a coherent transactional world around it, with a
defensible escalation label.**Exit criteria:** ERD committed; all
tables loaded; row counts and integrity checks documented; label
distribution measured and written down.

**0.1 Development environment**

**What:** Local PostgreSQL 16+ running in Docker, managed with a single
Compose file from day one. Client tooling: psql for scripted work,
DBeaver or pgAdmin for visual inspection.

**Why Docker for Postgres even though \"MLOps comes later\":** You need
Postgres *now*, and installing it natively creates a machine-specific
setup you\'ll have to unlearn. Running the official Postgres image with
a mounted volume costs you two commands and quietly starts your Docker
education months early --- by Phase 3, containers already feel normal.
This is deliberate scaffolding, not scope creep.

**How:** One Compose service: the official Postgres image, a named
volume for data persistence, port 5432 published locally, password
supplied via an environment file that is git-ignored. Add the
pgvector-enabled image variant (pgvector/pgvector) from the start so
Phase 2 requires zero database migration.

**Expect:** 30--60 minutes of setup. The most common early confusion is
data disappearing because you forgot the volume, or port 5432 already
being occupied by a native Postgres install.

**Pitfalls:**

-   Committing credentials. Create .gitignore before the first commit;
    > add an .env.example with dummy values as documentation.

    > Using latest image tags. Pin versions (e.g., Postgres 16). \"Works
    > on my machine because my machine pulled a different image\" is a
    > bug class you can delete for free.

**0.2 Source text dataset**

**What:** A real customer-support ticket corpus as the text backbone.
Primary candidates: the \"Customer Support Ticket Dataset\" family on
Kaggle, or a Hugging Face customer-support dataset. Requirements: ≥10k
tickets, English, subject and/or body text of non-trivial length, some
categorical metadata (type, priority, channel).

**Why real text instead of synthetic text:** The transformer branch is
the DL showcase. Synthetic text (template-generated complaints) has
near-zero linguistic variance, the model would hit 99% trivially, and
any interviewer who reads five examples would see through it.
Transactions can be synthetic because their *statistical shape* is what
matters; text cannot, because its *semantic content* is what matters. Be
ready to articulate exactly this asymmetry --- it\'s a great interview
answer.

**How:** Download once, store the raw file untouched in a data/raw/
directory that is git-ignored (commit a small documented sample + a
download script/instructions instead). Profile it before anything else:
ticket length distribution, language mix, duplicate rate, class balance
of any status/priority fields, junk rate (empty bodies, boilerplate
auto-replies).

**Expect:** Every public support dataset is messier than its Kaggle page
claims. Budget a half-day purely for profiling and write the findings
into a short data_profile.md. That document is a data-analyst portfolio
artifact in its own right.

**Pitfalls:**

-   Datasets that are themselves synthetic/LLM-generated (common on
    > Kaggle since \~2023). Check for suspicious uniformity ---
    > near-identical lengths, repeated phrasings. If the best available
    > corpus is partially synthetic, acknowledge it in the README rather
    > than hiding it; honesty about data limitations reads as seniority.

    > Licensing: check the dataset license permits redistribution before
    > committing any of it; when in doubt, ship the download
    > instructions, not the data.

**0.3 Relational schema design**

**What:** A normalized schema of seven tables. This is *the*
data-engineering deliverable of Phase 0.

-   **customers** --- identity, signup date, region, acquisition
    > channel.

    > **subscriptions** --- plan tier, start/end dates, monthly value;
    > one-to-many with customers (plan changes over time --- this
    > history powers \"recently downgraded\" features later).

    > **orders** --- customer FK, order date, amount, product category,
    > status.

    > **payments** --- order FK, method, status (settled/failed),
    > timestamp. Failed payments are a deliberate feature seed.

    > **refunds** --- order FK, amount, reason code, timestamp.

    > **tickets** --- customer FK, created timestamp, subject, body,
    > channel, initial priority. The embedding column is added here in
    > Phase 2.

    > **ticket_events** --- ticket FK, event type (priority_change,
    > reassignment, resolution, refund_linked), timestamp. This is an
    > *event log*, and it is where the label comes from.

**Why this shape:** (a) It forces multi-hop joins (customers → orders →
payments/refunds) so Phase 1 SQL is genuinely non-trivial. (b)
ticket_events as an append-only event log --- rather than mutable status
columns on tickets --- mirrors how real production systems record
history, and makes point-in-time correctness *possible*. A mutable
status column destroys history and makes leakage-free features
impossible; this single design choice is worth explaining in your
README. (c) Subscriptions as a history table rather than a current_plan
column, same reasoning.

**How:** Draw the ERD first (dbdiagram.io or Mermaid in the README),
review it against every feature you plan in Phase 1 (\"can this schema
answer this question at a point in time?\"), then write the DDL with
explicit primary keys, foreign keys, NOT NULL constraints, and CHECK
constraints (amounts non-negative, end dates after start dates).
Constraints are executable documentation and will catch generator bugs
in 0.4.

**Expect:** Two or three revision cycles. You will discover mid-Phase-1
that a feature needs a column you didn\'t create; that\'s normal --- add
a migration file rather than editing the original DDL, and you\'ve
accidentally learned schema migration discipline.

**Pitfalls:**

-   Timestamps without time zones. Use timestamp-with-timezone
    > everywhere, store UTC. Mixed-timezone bugs in window features are
    > miserable to debug.

    > Over-normalizing into 15 tables. Seven is the sweet spot between
    > \"shows skill\" and \"slows you down.\"

**0.4 Synthetic transactional data generation**

**What:** A Python generator (Faker + NumPy) that builds the
customer/order/payment/refund/subscription world *around*the real
tickets, then loads everything into Postgres.

**Why generate around the tickets rather than independently:** The whole
thesis is that text and transactions carry *correlated but distinct*
signal. If transactions are generated independently of ticket content,
the fusion model has nothing to fuse and Phase 2\'s ablation will show
fusion ≈ text-only, collapsing your headline claim. So the generator
must plant realistic correlations: customers with billing-topic tickets
get elevated failed-payment rates; customers with many rapid-fire
tickets get elevated refund ratios; high-tenure/high-spend customers are
rarer but their tickets carry higher escalation base rates, etc. Keep
correlations *noisy* (probabilistic, not deterministic) or the problem
becomes trivially learnable.

**How:**

1.  Assign each real ticket to a generated customer, clustering multiple
    > tickets per customer with realistic skew (most customers: 1
    > ticket; a long tail: many).

2.  Generate each customer\'s order/payment/refund history with
    > distributions conditioned on a small set of hidden \"persona\"
    > variables (value tier, frustration level) that also nudge ---
    > never determine --- the escalation label.

3.  Fix the random seed. Document every distribution choice in a
    > data_generation.md design note.

4.  Load via bulk COPY, not row-by-row inserts (10k+ rows row-by-row is
    > painfully slow and teaches a bad habit).

5.  Validate: run integrity queries --- orphaned FKs (should be zero,
    > constraints enforce it), date sanity (no orders after tickets that
    > reference them, no events before ticket creation), distribution
    > sanity (does spend follow the long tail you designed?). Commit
    > these checks as a permanent validation.sql.

**Expect:** This is the highest-motivation-risk task in the project (as
flagged in ideation). **Timebox: 4 evenings maximum.** Realistic-enough
with clean referential integrity beats a perfect economic simulation
nobody will inspect. Version 1 can be crude; you can enrich correlations
later if Phase 2 ablations look degenerate.

**Pitfalls:**

-   **Making the label a deterministic function of generated features.**
    > If escalated = (refund_ratio \> 0.3 AND tier = premium), the model
    > learns your generator, PR-AUC hits \~1.0, and the project becomes
    > unpresentable. Every label influence must pass through
    > probability, and the text must carry independent signal.

    > Generating timestamps that violate causality (a refund before its
    > order). Your CHECK constraints and validation queries exist to
    > catch exactly this.

**0.5 Label construction**

**What:** The binary target: *did this ticket escalate?* Defined from
ticket_events within a 14-day window after ticket creation: priority
raised, OR reassigned upward, OR linked refund/cancellation issued.

**Why a derived label instead of hand-labeling:** 10k+ hand labels is
not feasible solo, and deriving labels from event logs is exactly how
real companies define targets --- being able to discuss \"label
engineering\" and its failure modes (label noise, definition drift) is a
differentiator for both ML and analyst interviews.

**How:** Write the label as a SQL view over ticket_events --- not as a
column baked in at generation time --- so the definition is transparent,
versioned, and changeable. Measure the positive rate immediately.

**Expect:** Target a positive rate of 8--20%. Below \~5%, training gets
unstable at your data scale; above \~30%, \"escalation\" stops meaning
anything. Tune the generator\'s event frequencies to land in that band
and document that you did so (synthetic-data honesty again).

**Pitfalls:**

-   **Label leakage via the event log:** any feature computed from
    > ticket_events *after* ticket creation is leakage --- the label
    > lives in that table. Phase 1\'s rule: ticket_events may only
    > contribute features from *prior* tickets, never the current one.

    > The 14-day window means tickets created in the final 14 days of
    > your data range have undefined labels. Exclude them from training
    > explicitly and note it.

**Phase 1 --- SQL Feature Engineering (Weeks 3--6, your current learning
arc)**

**Goal:** A layered, leakage-free CTE pipeline producing one feature row
per ticket, exposed as a materialized view.**Exit criteria:**
feature_assembly materialized view built and refreshable; every feature
documented in a feature dictionary; anti-leakage spot checks pass.

**1.1 Pipeline architecture: why layered CTEs**

**What:** One master SQL file structured as a chain of named CTEs ---
cleaned_tickets → customer_financials → behavioral_windows →
feature_assembly --- materialized as a view at the end.

**Why CTEs over nested subqueries or a pile of temp tables:**
Readability and reviewability. Each CTE is a named, testable unit; a
reader (or interviewer) can materialize any intermediate layer alone and
inspect it. This is the SQL equivalent of writing functions instead of
one 500-line script. Why a *materialized* view at the end: the pipeline
involves multiple window scans and is too slow to run per-request;
materializing gives you a physical table that training exports and the
Phase 3 inference service both read --- one artifact, two consumers,
which *is* the training/serving consistency story.

**How to build it as a learner:** Do not write the master file top-down.
Build one CTE at a time in a scratch session: write it, SELECT from it,
eyeball 20 rows, check row counts against expectation, then append it to
the master file with a comment block stating its contract (grain,
one-line purpose, invariants --- e.g., \"grain: one row per customer;
invariant: spend_lifetime ≥ 0\"). The master file grows by accretion of
verified pieces.

**Expect:** This phase is where your SQL learning compounds fastest. The
window-function layer will take 2--3× longer than you estimate; that\'s
the curriculum working, not you failing.

**1.2 Layer 1 --- Cleaning CTEs**

**What/How:** Deduplicate tickets (same customer + near-identical
subject within 60 minutes → keep earliest, using a row-numbering window
over a partition); filter test/internal accounts; normalize currency to
one unit; coalesce NULL categoricals into an explicit unknown bucket;
standardize text fields minimally (trim, collapse whitespace) --- heavy
text cleaning belongs to the tokenizer in Phase 2, not SQL.

**Why in SQL, not pandas:** The inference service will read features
from Postgres directly; any cleaning done in pandas would need
re-implementation in the serving path --- exactly the dual-logic drift
Rule 4 forbids.

**Expect/Pitfalls:** Deduplication is your first practical window
function and your first grain-discipline test. The #1 beginner bug of
this entire phase: a join that silently changes grain (one row per
ticket becomes three because a customer has three subscriptions).
**After every join, check the row count.** Make it a reflex now.

**1.3 Layer 2 --- Aggregation CTEs (customer financial profile)**

**What:** Per-customer aggregates joined across customers → orders →
payments → refunds: lifetime spend, average order value, order count,
refund count and total, **refund ratio**, failed-payment count,
days-since-last-purchase, distinct categories purchased, current plan
tier and tenure, plan-downgrade-within-90-days flag.

**Why each feature earns its place:** refund ratio and failed payments =
friction/frustration proxies; lifetime spend and tier = stakes (how
costly is losing this customer); category breadth and tenure =
relationship depth (broad, old relationships escalate differently than
one-off buyers); recent downgrade = a pre-churn tremor. Write one
sentence like this per feature in a feature_dictionary.md --- name,
definition, grain, business rationale, expected range. That document is
*the* artifact analyst-track interviewers will read.

**How --- the point-in-time discipline:** These aggregates must be
**as-of ticket creation**, not as-of today. A customer\'s lifetime spend
\"now\" includes purchases made after the ticket --- leakage.
Mechanically: join orders/payments/refunds to tickets with the condition
*event timestamp \< ticket created timestamp*, and aggregate at the
(ticket, customer) grain rather than pure customer grain. This makes
Layer 2 heavier than a naive GROUP BY --- that\'s the cost of
correctness, and articulating it is a top-tier interview moment.

**Expect:** LEFT-join semantics everywhere (customers with zero orders
must survive with zeros, not vanish); COALESCE aggregates explicitly.
Division-by-zero on refund ratio for zero-order customers --- decide the
convention (0, with a has_orders flag) and record it in the dictionary.

**Pitfalls:** Fan-out again --- aggregating payments and refunds in the
*same* join before grouping multiplies rows and inflates sums. Aggregate
each child table in its own CTE first, then join the pre-aggregated
results. This \"aggregate-then-join\" pattern is one of the most
important SQL habits this project teaches.

**1.4 Layer 3 --- Window function CTEs (behavioral trajectories)**

**What:** The temporal features that plain GROUP BY cannot express:

-   **Spend trend:** last-90-day spend vs. the prior-90-day window
    > before each ticket; express as a ratio with explicit
    > zero-denominator handling. Signals a decaying relationship.

    > **Ticket velocity:** count of the customer\'s tickets in the 30
    > days before this one (strictly before --- exclude the current
    > row). The 4th ticket this month ≠ a first contact.

    > **Time since previous ticket:** LAG over the customer\'s tickets
    > ordered by time; NULL for first-timers (keep as a first_ticket
    > flag + imputed large value --- first contact is signal, not
    > missing data).

    > **Order rank:** is the complaint about the customer\'s first
    > order? First-purchase disputes are disproportionately
    > churn-predictive.

    > **Prior escalation count:** how many of this customer\'s
    > *previous* tickets escalated --- computed from
    > ticket_eventsstrictly before the current ticket\'s creation.
    > Powerful, and the single most leakage-dangerous feature in the
    > project; the frame boundaries must exclude the current ticket
    > entirely.

**Why windows specifically:** Every feature here is \"for each row, look
at *other rows* of the same entity, ordered in time.\" That is the
definition of a window function, and correctly framing windows
(partition, ordering, frame bounds, exclusion of the current row) is
precisely the SQL depth that separates you from GROUP-BY-only
candidates.

**How:** One trajectory concept per CTE. For each, write a manual
verification: pick one busy customer, list their events chronologically
by hand, compute the feature on paper, compare with the query. Keep
those checks in a tests/sql/directory --- hand-verified window functions
are your test suite before you know testing frameworks.

**Expect:** Off-by-one boundary errors constantly (is the window \<
created_at or \<= created_at? Inclusive frames silently include the
current row). Budget real time here; this layer is the heart of the SQL
portfolio claim.

**Pitfalls:** Date-range windows vs. row-count windows --- \"last 90
days\" is a *range* concept; a row-count frame gives you \"last N
orders\" instead, which is a different (sometimes also useful) feature.
Know which one each feature means.

**1.5 Layer 4 --- Assembly, the label join, and the materialized view**

**What:** Final CTE stitching ticket-level fields + Layer 2 profile +
Layer 3 trajectories + the label view into one row per ticket;
materialized; refreshed manually now, on a schedule in Phase 3.

**How:** Enforce the grain contract with a uniqueness check on ticket id
after building. Add B-tree indexes on the view\'s ticket id and customer
id --- Phase 3\'s per-request lookups need them, and \"I indexed the
serving path\" is a nice systems detail. Exclude the undefined-label
tail window (0.5). Target: 15--25 features. More is not better; every
feature must have a dictionary entry or it doesn\'t ship.

**Expect:** First full refresh may take noticeably long (minutes) at
your scale --- fine. Note the runtime; you\'ll reference it when
explaining why the view is materialized.

**Pitfalls:** Materialized views go stale silently. Write \"REFRESH is a
manual step, automated in Phase 3\" in the README now so future-you
doesn\'t debug \"why didn\'t my new data appear.\"

**1.6 Phase 1 deliverables checklist**

-   ERD (image or Mermaid) in README

    > DDL + migrations + validation.sql

    > Master feature pipeline SQL, commented, layer contracts stated

    > feature_dictionary.md (name, definition, grain, rationale, range,
    > leakage note per feature)

    > Hand-verification queries in tests/sql/

    > A short leakage.md explaining the point-in-time design ---
    > genuinely rare in student projects, disproportionately impressive

**Phase 2 --- Embeddings, Fusion Model, Evaluation (Weeks 7--11)**

**Goal:** A fine-tuned transformer + tabular fusion model with an
ablation study proving both modalities matter, plus pgvector-powered
similarity search.**Exit criteria:** Ablation table complete; chosen
model artifact versioned with its config and metrics; embeddings stored
in pgvector with a working similarity query.

**2.1 pgvector embedding store**

**What:** Enable the pgvector extension; add a vector column (dimension
= your encoder\'s hidden size, e.g., 384 or 768) on tickets; batch-embed
all tickets and write vectors back.

**Why Postgres-as-vector-DB instead of Pinecone/Weaviate/FAISS:** (a)
One database = one query can return a ticket\'s numbers *and* its vector
--- the literal embodiment of the project\'s \"unify two data worlds\"
thesis. (b) It\'s the real-world pragmatic default: production teams
commonly start with pgvector and graduate to a dedicated vector DB only
at scale --- knowing *when that graduation point is* (tens of millions
of vectors, high QPS ANN) is the interview answer. (c) Zero new
infrastructure, zero new cost.

**How:** Batch job (script, not notebook) that pages through tickets
without embeddings, encodes with the *base* pretrained encoder in
batches, writes back. Record the model name + version used for embedding
in a metadata table or column --- if you later change encoders, stale
vectors from a different model are silently incompatible garbage, and
provenance is how you catch it. For \~10--50k vectors, exact
nearest-neighbor search is fast enough; add an HNSW index only if
similarity queries feel slow, and note the recall-vs-speed tradeoff
either way.

**Expect:** CPU embedding of 10k tickets: minutes to an hour depending
on model size. Choose a small encoder (DistilBERT or a MiniLM-class
sentence model) --- at your data scale, a large encoder buys nothing
except training pain.

**Pitfalls:** Dimension mismatch between the declared column and the
encoder output fails loudly (good); *model*mismatch fails silently (bad)
--- hence the provenance metadata.

**2.2 Training data export --- versioned snapshots**

**What:** A script that reads feature_assembly, joins ticket text, and
writes a versioned Parquet snapshot (snapshot_v1_YYYYMMDD.parquet) plus
a sidecar manifest: row count, feature list, label rate, pipeline git
commit hash.

**Why snapshots instead of training straight off the live DB:**
Reproducibility (\"model v3 was trained on snapshot v2, commit abc123\")
and stability (a mid-experiment view refresh silently changing your
training data is an unholy debugging experience). This is data
versioning done manually --- mention DVC as the industrial-strength
equivalent you\'d adopt at scale; using the concept matters more than
the tool.

**How --- the split, which is a design decision, not a utility call:**
Split **temporally** --- train on earlier tickets, validate/test on
later ones --- never randomly. Random splits leak in two ways at once:
same-customer tickets straddle the split (the model memorizes
customers), and future-period statistics bleed backward. Temporal split
honestly simulates deployment (\"trained on the past, scoring the
future\") and depresses your metrics relative to a random split ---
*expect this, and say it proudly.* A slightly worse honest number beats
a great leaky one, and knowing that is a hiring signal.

**Pitfalls:** Preprocessing (scaling, encoding) must be fit on train
only and applied to val/test --- the classic subtle leak. Persist the
fitted preprocessing alongside the model; Phase 3 needs the identical
transform at inference.

**2.3 Fusion model architecture**

**What:** Two branches + a head, trained end-to-end in PyTorch/Hugging
Face:

-   **Text branch:** DistilBERT (or equivalent small encoder),
    > fine-tuned, pooled representation out.

    > **Tabular branch:** small MLP (two hidden layers is plenty) over
    > the 15--25 standardized features, projecting to a compact vector
    > (e.g., 64-dim).

    > **Fusion head:** concatenate both representations → one or two
    > dense layers with dropout → sigmoid.

**Why this over alternatives you should be able to discuss:**

-   *vs. gradient boosting on tabular + text-embedding features:*
    > XGBoost on frozen embeddings is a strong, honest baseline --- so
    > **build it as a baseline** and beat it. Beating a credible
    > baseline is worth more than any architecture diagram.

    > *vs. frozen embeddings + MLP:* this is your cheap first fusion
    > version; full fine-tuning is the upgrade. Report both --- the
    > delta *is* your \"why fine-tune\" evidence.

    > *vs. cross-attention / gated fusion:* legitimate, but at 10k
    > samples they overfit and over-complicate. Late concatenation is
    > the right complexity for the data size; knowing why is more senior
    > than reaching for the fancy option.

    > *Balance trap:* a 768-dim text vector concatenated with 25 raw
    > features lets the text branch drown the tabular signal --- hence
    > projecting tabular up (and optionally text down) so neither branch
    > dominates by dimensionality alone. This detail signals real
    > architectural thinking.

**How (training regime):** Two-phase schedule --- first epoch(s) with
encoder frozen (train tabular branch + head), then unfreeze with a much
lower encoder learning rate (discriminative LRs, e.g., 2e-5 encoder /
1e-3 head). Handle class imbalance with a positively-weighted loss
before reaching for samplers. Early stopping on validation PR-AUC. Log
every run\'s config + metrics (a CSV/JSON log is fine; MLflow is the
named industrial equivalent).

**Expect:** On free-tier GPU, fine-tuning a distilled encoder over \~10k
short texts is minutes-per-epoch. The entire experimental program
(baselines + ablations + tuning) fits comfortably in free compute --- by
design.

**Pitfalls:**

-   Notebook-only training. Notebooks for exploration, but the final
    > training path must be a script with a config file, because Phase 3
    > needs a rebuildable artifact and interviewers will look for
    > exactly this.

    > Metric obsession. Past \"clearly better than baselines,\" more
    > tuning has near-zero portfolio value; the ablation story is the
    > value.

**2.4 Evaluation and the ablation study --- the project\'s centerpiece**

**What:** A single table, reported on the temporal test set:

  ---------------------------------- ---------- --------------------------
    Model	                         PR-AUC	      Recall @ 80% precision
    
    Majority / random baseline	        …	                …
    Tabular only (XGBoost or MLP)	    …	                …
    Text only (fine-tuned encoder)	    …	                …
    Fusion (frozen embeddings)	        …	                …
    Fusion (fine-tuned, end-to-end)	    …	                …                                            
                                                    
  ---------------------------------- ---------- --------------------------

**Why these metrics:** With 8--20% positives, accuracy is a lie (predict
\"no escalation\" always → 85%+ accuracy). PR-AUC measures ranking
quality where it matters; recall-at-fixed-precision translates directly
into the business sentence: *\"at a precision the support team can
tolerate, we catch X% of escalations.\"* Practice saying that sentence
--- it\'s the demo.

**Why the ablation is the centerpiece:** It is the empirical proof of
the entire architecture. Fusion beating both single-modality models
justifies every design decision upstream. Supplement with a brief error
analysis: 5--10 examples fusion gets right that text-only misses
(expected shape: mild text + alarming transaction history) and vice
versa. Concrete examples in a README beat a 0.02 metric delta for
storytelling.

**What to expect and the contingency:** If fusion ≈ text-only, your
synthetic correlations (0.4) are too weak or too text-redundant ---
revisit the generator, strengthen the *transaction-only* pathways to
escalation (e.g., personas whose escalations are driven by payment
friction with neutral ticket text), regenerate, retrain. **This loop is
likely, plan for one iteration of it.** Document the iteration; \"my
first data version had X flaw, here\'s how I diagnosed and fixed it\" is
a better story than a clean first try.

**2.5 Similarity search feature**

**What:** For any ticket: the 5 nearest historical tickets by embedding
distance, each with its escalation outcome. Phase 3 exposes it as an
endpoint.

**Why:** (a) Instant interpretability for the demo --- \"the model
flagged this, and look, here are five near-identical past tickets, four
escalated\" lands with non-ML interviewers better than any metric. (b)
It exercises pgvector\'s distance operators, completing the \"Postgres
as vector store\" claim. (c) It\'s a mini retrieval system --- adjacent
to RAG, the highest-demand pattern in the market --- achieved with zero
extra infrastructure.

**How:** Cosine distance, nearest-neighbor query over the vector column,
join back to outcomes. Decide and document: similarity uses the *base*
encoder\'s embeddings (comparable across time), not the fine-tuned
classifier\'s representations.

**Phase 3 --- MLOps & Deployment (Weeks 12--16, learned just-in-time)**

**Goal:** The trained system live behind a public URL, containerized,
talking to a managed Postgres, with CI/CD and prediction logging.**Exit
criteria:** One-command local stack via Compose; cloud URL serving
predictions; push-to-deploy pipeline green; predictions logging back to
Postgres.

**3.1 FastAPI inference service**

**What:** Four endpoints ---

-   POST /predict: accepts a customer id + ticket text (the \"new
    > ticket\" case). Server-side: fetch that customer\'s point-in-time
    > features from Postgres, tokenize the text, run the fusion model,
    > return score + top-level factors + model version.

    > GET /similar-tickets: the pgvector nearest-neighbor lookup.

    > GET /health: cheap liveness (also checks DB connectivity) --- load
    > balancers and container platforms require it.

    > GET /model-info: model version, training snapshot id, feature list
    > --- operational transparency in one endpoint.

**Why FastAPI:** Python-native (your stack), async-capable, Pydantic
request/response validation (malformed input rejected with clear errors
before touching the model), and **auto-generated Swagger UI** --- your
interactive, zero-JS frontend. The request/response schemas you define
*are* the API documentation.

**Why the caller sends identifiers, not features --- the design decision
to defend hardest:** If clients computed and sent features, feature
logic would exist twice (client + SQL), and drift between them is the
classic silent production-ML killer. By fetching features server-side
from the same view training used, there is exactly one feature
implementation. Trade-off you must be able to state: this adds a DB
round-trip of latency per request, and couples the API to DB
availability --- a price you pay knowingly for consistency. Senior
engineers narrate trade-offs, not just choices.

**How:** Load model + tokenizer + fitted preprocessing once at
application startup, never per-request. Use a connection pool for
Postgres. Log every request\'s inputs, score, latency, and model version
(see 3.5).

**Expect:** CPU inference with a distilled encoder: tens to a few
hundred ms per request --- fine for a demo; note batchability as the
scale answer.

**Pitfalls:** Preprocessing drift --- inference must apply the
*persisted* transform from training, not a re-fit. New-customer cold
start: a customer with no history returns NULL-ish features; handle
explicitly (the first_ticket / has_orders flags from Phase 1 exist for
this) rather than 500-ing.

**3.2 Containerization**

**What:** One image for the API (app + model weights + tokenizer), built
multi-stage: a builder stage installs dependencies, a slim runtime stage
copies only what\'s needed. Postgres stays a separate service ---
Compose locally, managed in the cloud.

**Why multi-stage / why Postgres outside the app image:** Image size
(PyTorch images balloon past 5GB unmanaged; CPU-only torch wheels and
multi-stage discipline can more than halve that --- cold-start and
deploy times care). One-process-per-container is the composability
principle the whole container ecosystem assumes; bundling the DB into
the app image is the classic beginner tell.

**How:** Compose file with two services (api + postgres), a shared
network, DB credentials via env file, healthcheck-based startup ordering
(the API must wait for Postgres readiness, not just container start ---
first-run race conditions here are near-universal). Model weights: bake
into the image for simplicity at this size; note \"pull from object
storage at startup\" as the at-scale alternative.

**Expect:** The first Dockerfile is a full day of iteration; that\'s
normal. docker compose up bringing up the whole stack on a clean machine
is the phase\'s most satisfying checkpoint --- record a short demo GIF
for the README.

**Pitfalls:** Using localhost as the DB host inside a container
(services address each other by service name on the Compose network);
forgetting .dockerignore (shipping data/raw/ into the build context
makes builds crawl); pinning nothing (pin the base image and Python deps
--- requirements.txt with exact versions minimum).

**3.3 Cloud deployment**

**What/Why:**

-   **Database → Supabase or Neon** (managed Postgres, pgvector
    > supported, free tier). Managed = backups, TLS, uptime are someone
    > else\'s job --- the correct build-vs-buy call at every company
    > size, and you should say so.

    > **API → Google Cloud Run** (deploy a container directly,
    > scale-to-zero, generous free tier; AWS App Runner is the
    > interchangeable alternative --- knowing they\'re interchangeable
    > is itself the skill). Scale-to-zero introduces cold starts
    > (seconds while your image spins up) --- acceptable for a
    > portfolio, and *explaining the cold-start/latency trade-off* is
    > another senior moment.

**How:** Recreate schema on the managed instance (your DDL + migrations
replay --- reproducibility payoff), load data, refresh the view,
backfill embeddings. Push the image to the platform\'s registry; deploy;
inject DB credentials via the platform\'s secret manager --- **the same
image runs locally and in prod, only environment differs.** That
sentence is the whole point of 12-factor config; internalize it.
Restrict the DB to TLS connections and create a **read-only role** for
the API (it needs SELECT on the feature view + tickets, INSERT only on
the prediction log table --- least privilege, cheap to do,
disproportionately impressive to mention).

**Expect:** A day of IAM/permissions friction on first cloud deploy.
Everyone pays this tax once; it is not a sign you\'re doing it wrong.

**Pitfalls:** Free-tier managed Postgres pauses on inactivity (first
request after idle is slow --- know this before the live demo and warm
it up); accidentally leaving a paid resource running (set billing alerts
*first*, before creating anything).

**3.4 CI/CD**

**What:** GitHub Actions (you\'re already on GitHub): on every push ---
lint, run tests (a handful of API tests with a mocked/ephemeral DB +
your SQL validation checks), build the image; on main --- push to
registry and redeploy.

**Why:** It converts \"deployment\" from a ritual into a property of the
repo. Even minimal, it signals production-mindedness louder than model
metrics, and it\'s the difference between \"I deployed once\" and \"my
system deploys itself.\"

**How:** Build it incrementally --- lint-only first, then tests, then
build, then deploy. Cloud credentials live in GitHub Actions secrets,
never in the workflow file.

**Pitfalls:** Docker builds in CI are slow without layer caching (enable
the cache action); don\'t gold-plate --- four steps that always run beat
twelve that are flaky.

**3.5 Monitoring and the closed loop**

**What:** Every prediction inserted into a prediction_log table in
Postgres (timestamp, customer id, score, latency, model version). Drift
checks are then *just more SQL*: a window-function query comparing this
week\'s score distribution to the trailing month\'s, run on demand or on
a schedule.

**Why this design:** It closes the project\'s loop with poetic economy
--- monitoring analytics land back in the same database, analyzed with
the same skill (SQL windows) the project started with. When an
interviewer asks \"how would you know your model went stale?\", you have
a concrete, running answer plus the scale-up narrative
(Evidently/Grafana as the industrial versions).

**How:** Log asynchronously (a logging failure must never fail a
prediction). Also automate the materialized-view refresh here (Cloud
Scheduler or a scheduled Action) --- retiring the Phase 1 manual step.

**Cross-Cutting: Repo, Narrative, Risks**

**Repository structure**

Top-level README leads with the architecture diagram, the one-line
pitch, the ablation table, and the live URL --- a hiring manager gives
you 90 seconds; the proof goes above the fold. Directories: db/ (DDL,
migrations, validation), sql/(feature pipeline + tests), datagen/,
training/ (scripts + configs, notebooks quarantined in notebooks/),
api/, deploy/(Dockerfiles, Compose, CI workflows), docs/
(data_profile.md, data_generation.md, feature_dictionary.md, leakage.md,
design_decisions.md). The design-decisions doc records every \"why X
over Y\" in this bible in your own words --- it is the single most
senior-reading artifact in the repo.

**Risk register (ranked by expected pain)**

1.  **Weak synthetic correlations → fusion shows no lift** (Phase 2\'s
    > centerpiece collapses). *Mitigation:* plant transaction-only
    > escalation pathways in the generator; budget one
    > regenerate-retrain iteration.

2.  **Data leakage somewhere subtle** (metrics too good → project
    > unpresentable). *Mitigation:* point-in-time joins, temporal split,
    > prior_escalations frame discipline, and a smell test --- if PR-AUC
    > \> \~0.95, hunt for the leak before celebrating.

3.  **Synthetic-data rabbit hole** (motivation death). *Mitigation:* the
    > 4-evening timebox, enforced.

4.  **Scope creep in Phase 3** (Kubernetes, Terraform, feature
    > stores...). *Mitigation:* the stack defined above is complete;
    > extras go in a \"future work\" README section, which costs nothing
    > and reads just as well.

5.  **Cold-start/pause behavior ruining a live interview demo.**
    > *Mitigation:* warm both the DB and the Cloud Run instance five
    > minutes before any demo; keep a local Compose fallback.

**The narrative arc you\'re building toward**

For **ML/DL roles**: lead with Phase 2 --- fusion architecture,
fine-tuning deltas, ablation, error analysis. For **data
engineer/analyst fallback**: lead with Phases 0--1 --- schema design,
event-log modeling, layered CTEs, window functions, leakage discipline,
and the SQL-native monitoring loop. Same repo, two rehearsed openings.
Write both 2-minute versions down *now*, and refine them as the
artifacts materialize --- the project isn\'t finished when it deploys;
it\'s finished when you can tell it.
