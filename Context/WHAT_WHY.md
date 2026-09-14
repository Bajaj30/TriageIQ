# TriageIQ — What It Is, Why It Exists, and What It Actually Solves

*v2. The v1 framing (synthetic customers, churn prediction) is archived at `WHAT_WHY_v1_archive.md`.
See `TriageIQ.md` §0.5 for why it changed.*

## What the project is

TriageIQ is an end-to-end machine learning system that reads incoming consumer complaints filed with
the US Consumer Financial Protection Bureau and predicts, in real time, which ones will **cost the
company money** — a complaint that ends in monetary relief rather than an explanation.

Under the hood it's three systems working as one pipeline:

- **A PostgreSQL layer** holding 4.8 million real complaints, which turns that raw history into
  point-in-time features — how often this company has paid out on this kind of complaint *as of the
  day this one arrived*, whether its complaint volume is climbing, whether this issue type is
  spiking industry-wide — using layered SQL.
- **A fine-tuned DistilBERT** that reads the actual narrative the consumer wrote and understands what
  they are describing and how concretely they describe it.
- **A fusion model + deployed API** that combines both signals into one payout-risk score, served
  from a Docker container in the cloud, pulling live features from the database on every request.

A compliance manager's version: *"Complaints land in the queue with a 15-day regulatory clock
running. The system tells you which ones are going to end in a payout, so you put a senior analyst
on those instead of finding out six weeks later."*

## Why I built it

Two reasons, one practical and one technical.

**The practical reason:** I wanted one project that proves I can carry a system from raw data to a
live production URL — not three disconnected tutorial projects. Everything in between — schema
design, feature engineering, model training, evaluation, containerization, deployment, monitoring —
lives in a single pipeline where each piece exists because the next piece needs it.

**The technical reason:** most real business problems don't live in one data world. They live at the
intersection of structured data (what has happened before — numbers in tables) and unstructured data
(what someone is saying — free text). Most student projects pick one world. I deliberately picked a
problem that is measurably unsolvable with either alone.

And I can prove that claim rather than assert it. Holding product and issue type constant, so
metadata can't cheat:

| signal | ROC-AUC |
|---|---|
| narrative text only | 0.898 |
| structured metadata only | 0.940 |
| **both, fused** | **0.945** |

Neither modality subsumes the other. That measurement is the justification for the entire
architecture, and I ran it before writing a line of the pipeline.

## The actual problem it affects

Every bank, card issuer, and fintech in the US has a CFPB response desk. Complaints arrive forwarded
from the regulator with a hard 15-day response deadline, and a human skims the queue deciding which
ones need a senior analyst and which get a templated reply.

That guess fails in a specific, costly way — it can only see the text, one complaint at a time.

The text is systematically incomplete on its own. Two complaints can describe the same dispute in
near-identical words, and one ends in a refund while the other ends in a form letter — because of
who they're filed against, what issue category they fall into, and how that company has historically
handled that exact kind of dispute. The person triaging doesn't have the company's rolling payout
rate by issue type in their head, and nobody cross-references a year of outcome history per
complaint at queue speed.

The cost of getting it wrong runs both directions: a senior analyst spent on a complaint that was
never going to matter, or a genuine liability answered with a template and escalated into a
regulatory problem.

## How it solves the problem uniquely

The uniqueness isn't "AI reads complaints." It's what the model gets to see, and how honestly the
system reports on itself.

**It judges the complaint with the institution's own track record attached.** The model fuses the
semantic content of the narrative with SQL-engineered features computed *as of the moment the
complaint was received* — is this company's payout rate on this issue climbing, is its complaint
volume deteriorating, is this issue type spiking across the industry this month. It's the judgment a
great compliance lead would make with a year of outcome data in front of them, automated to happen
in milliseconds, on every complaint, without fatigue.

**Both signals live in one database.** Complaint embeddings are stored in PostgreSQL itself
(pgvector), next to the outcome history. One query retrieves a complaint's structured features and
its vector together — no separate vector database, no synchronization problem, no extra
infrastructure.

**There is exactly one feature definition, everywhere.** The deployed API doesn't accept
pre-computed features — it takes identifiers and text, and queries the same SQL feature view the
model was trained on. This kills the classic silent failure of production ML: training and serving
features drifting apart because they're implemented twice. Here they can't drift, because there's
only one implementation. The price is a database round-trip per request, and I'd rather pay it
knowingly than discover the drift in production.

**It explains itself.** Alongside the risk score, the system retrieves the most similar historical
complaints and shows what happened to them — *"here are five near-identical past complaints, four of
them ended in monetary relief."* A manager doesn't need to trust a black-box number; they see
precedent. The same endpoint, reframed, answers a consumer's question: *"complaints like yours got
relief four times out of five."*

**It's honest about time, and about itself.** Every feature and the train/test split respect what
was knowable when — trained on the past, evaluated on the future, exactly as it would face reality
in production. And because pooled metrics on this data are flattered by differences *between*
companies and products, I report the stratified numbers too. Pooled ROC-AUC is 0.979; held within
product and issue it's 0.945; inside a single company it's 0.768. All three are true, they answer
different questions, and quoting only the first would be the easiest lie in the project.

**What it deliberately does not claim.** The model predicts whether a complaint costs the *company*
money — not how badly the consumer was harmed. CFPB publishes no severity label, so a severity model
would be unvalidatable, and I'd rather ship a narrower claim I can defend than a broader one I can't.
A thin ranking layer recovers the magnitude intuition where the narrative states a dollar figure:
a $200,000 loan disbursement failure at 1.2% payout probability outranks a $10 card dispute at 28.5%,
because expected cost is $2,400 against $3.

## The one-paragraph version

Compliance desks triage regulatory complaints by reading text under a 15-day clock, but the text
alone is incomplete — whether a complaint ends in a payout depends as much on the institution's own
history with that kind of dispute as on what the consumer wrote. TriageIQ fuses what the consumer is
saying (a fine-tuned transformer over the narrative) with what the institution has been doing
(SQL-engineered point-in-time features over 4.8 million real CFPB complaints) into a single payout
risk score, served live from a containerized API that reads its features from the same database
queries it was trained on. It's built entirely on public data anyone can download and check — and it
reports the honest stratified numbers, not just the flattering pooled one.
