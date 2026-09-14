TriageIQ — What It Is, Why It Exists, and What It Actually Solves
What the project is

TriageIQ is an end-to-end machine learning system that reads incoming customer support tickets and predicts, in real time, which ones are likely to escalate — meaning the ticket will blow up into something expensive: a senior agent intervention, a refund, or a cancelled customer, within the next 14 days.

Under the hood it's three systems working as one pipeline:

• A PostgreSQL layer that holds the company's business reality — orders, payments, refunds, subscriptions, ticket history — and turns that raw history into meaningful features (spend trends, refund ratios, ticket velocity) using layered SQL.
• A transformer model (fine-tuned DistilBERT) that reads the actual text of the ticket and understands what the customer is saying and how they're saying it.
• A fusion model + deployed API that combines both signals into one risk score, served from a Docker container in the cloud, pulling live features from the database on every request.

A support manager's version: "When a ticket comes in, the system instantly tells you how likely it is to become a fire, so you can hand it to a senior agent before it burns."

Why I built it

Two reasons, one practical and one technical.

The practical reason: I wanted one project that proves I can carry a system from raw data to a live production URL — not three disconnected tutorial projects (a SQL notebook here, a Kaggle model there, a Docker hello-world somewhere else). Everything in between — schema design, feature engineering, model training, evaluation, containerization, deployment, monitoring — lives in a single coherent pipeline where each piece exists because the next piece needs it.

The technical reason: most real business problems don't live in one data world. They live at the intersection of structured data (what a customer has done — numbers in tables) and unstructured data (what a customer is saying — free text). Most student projects pick one world. I deliberately picked a problem that is unsolvable with either alone, because that forces a genuinely non-trivial architecture instead of a decorative one.

The actual problem it affects

Every support team on earth does triage, and almost all of them do it the same way: a human skims the queue and guesses which tickets matter. That guess fails in a specific, costly way — it can only see the text.

The text is systematically misleading on its own:

• A furious, ALL-CAPS email from a customer who spent ₹500 once, two years ago → looks urgent, isn't.
• A polite two-line "hey, small issue with my invoice" from a customer paying ₹2 lakh/year, whose spend has been quietly declining and who has filed three tickets this month → looks routine, is actually a churn event in progress.

The human triager doesn't have the second customer's payment history, refund pattern, and ticket velocity in their head — and even if the CRM shows it, nobody cross-references five tables per ticket at queue speed. So high-value quiet complaints get junior responses, and the company finds out the customer was angry when the cancellation email arrives. Escalations cost real money: senior agent time, refunds, and — worst — churned high-value accounts, where retention is famously many times cheaper than reacquisition.

How it solves the problem uniquely

The uniqueness isn't "AI reads tickets" — sentiment classifiers have existed for a decade, and they inherit exactly the flaw described above. The uniqueness is in what the model gets to see, and how honestly the system delivers it:

It judges the ticket with the customer's full history attached. The model fuses the semantic meaning of the text with SQL-engineered behavioral features computed as of the moment the ticket was created — is this relationship growing or decaying, is this their 4th ticket this month, was their last payment a failed one, are they complaining about their very first purchase. It's the judgment a great support lead would make if they had time to read five tables per ticket — automated to happen in milliseconds, on every ticket, without fatigue.

Both signals live in one database. Ticket embeddings are stored in PostgreSQL itself (pgvector), next to the transactions. One query retrieves a customer's numbers and their ticket's vector together — no separate vector database, no synchronization problem, no extra infrastructure. The two data worlds are unified at the storage layer, not just at the model layer.

There is exactly one feature definition, everywhere. The deployed API doesn't accept pre-computed features — it takes a customer ID and queries the same SQL feature view the model was trained on. This kills the classic silent failure of production ML: training features and serving features drifting apart because they're implemented twice. In this system, they can't drift, because there's only one implementation.

It explains itself. Alongside the risk score, the system retrieves the most similar historical tickets and shows what happened to them — "here are five near-identical past tickets; four of them escalated." A support manager doesn't need to trust a black-box number; they see precedent.

It's honest about time. Every feature, and the train/test split itself, respects what was knowable when — the model is trained on the past and evaluated on the future, exactly as it would face reality in production. That makes the reported numbers a truthful preview of deployment behavior, not an inflated lab result.

The one-paragraph version

Support teams triage tickets by reading text, but the text alone lies — the most expensive escalations often arrive politely, from valuable customers whose behavioral data has been screaming for weeks. TriageIQ fuses what a customer is saying (transformer over ticket text) with what that customer has been doing (SQL-engineered features over their transaction history) into a single escalation risk score, served live from a containerized API that reads its features from the same database queries it was trained on. It catches the fires the human eye structurally cannot see — and shows its receipts.

That last paragraph, near-verbatim, is your README opener and your interview elevator pitch. The rest of this explanation is your answer script for the inevitable follow-up: "walk me through why this needed both data types."