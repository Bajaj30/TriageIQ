# Phase 3 — Learning Directions: from a trained model to a public link

> [!IMPORTANT]
> **How to use this file.** One step at a time, in order. Every step has six parts:
> 1. **Assumes:** what you must already know. Each item points to a prerequisite (P1–P11) or an earlier
>    step. If you can't do its self-test, do that first.
> 2. **Watch:** the lectures for this step, in order, with exact sections.
> 3. **Learn:** the *whole* concept, intuition first, even where TriageIQ uses only part of it.
> 4. **Build:** the same idea inside TriageIQ. **Bridge** notes say where our setup differs from the course.
> 5. **Explain it back:** say the answers without notes. These are also your interview questions.
> 6. **Done when:** the check that closes the step.
>
> Come back to the main chat after each step. Keep your own notes in `learning_log.md`, as in Phase 0.
> The plan behind this file is in `CLAUDE.md` §12, and every number is in `Context/FACTS.md`.

> [!NOTE]
> **The gap rule.** Every assumption a step makes is written under **Assumes**. If you still hit a word or idea
> you don't know, stop: write the exact term in `learning_log.md` and bring it to the main chat. It gets
> explained, then **added to this file**, so the gap is closed for good.

> [!NOTE]
> **Build status (2026-10-06).** Steps **3.1–3.6 are built and live**; **3.7** is built except the read-only DB role;
> **3.8** (CI) and **3.9** (monitoring) are deferred; **3.10**: README and the essay are done, the screen recording and
> the final teardown are left. The *learning* side (the lectures and the book) is still ahead — after exams.
> **As built, differs from the picture below:** the front is a website on Vercel, not only Swagger UI; NGINX sits in
> front of the API; there's no `prediction_log` yet (3.9). What each step actually built, condensed for interviews:
> **`Learning/Phase3/revision.md`**.

**One book for the whole phase:** Chip Huyen, *Designing Machine Learning Systems* (O'Reilly, 2022).
How to read it, in which order, and what to do per chapter: **`Learning/book_DMLS.md`**.

---

## 3.P Prerequisites: check these first

Each one has a 2-minute self-test. Pass it → skip it. Can't → watch the source before the step that needs it.

| # | skill | self-test | if not → watch | needed by |
|---|---|---|---|---|
| P1 | Python modules and imports | What does `from api.main import app` look for on disk? | Corey Schafer, "Python Tutorial for Beginners 9: Import Modules" | 3.4 |
| P2 | Type hints | Read aloud: `def f(x: int \| None = None) -> dict[str, float]:` | FastAPI docs, "Python Types Intro" (text, 15 min; no lecture worth it, and FastAPI is built on this) | 3.4 |
| P3 | Decorators | What does `@app.get("/health")` do to the function under it? | Corey Schafer, "Python Tutorial: Decorators" | 3.4 |
| P4 | async / await, the idea | Why can one waiter serve many tables but one cook can't cook two dishes at once? | FastAPI docs, "Concurrency and async / await" (the burger story; the best explanation is this text) | 3.4 |
| P5 | Virtual environments, pinned requirements | conda env vs `venv`; why write `fastapi==0.x.y`, not `fastapi`? | freeCodeCamp API course §2: only the "virtual environment" videos (Mac) | 3.4–3.5 |
| P6 | Shell basics, permissions, env vars | What do `chmod 400 key.pem` and `$PATH` mean? What does a pipe `\|` do? | MIT Missing Semester, Lecture 1 (the shell) + Lecture 2 (shell tools) | 3.0, 3.6 |
| P7 | Git beyond commit | clone vs pull; what is a branch; what does `.gitignore` protect? | MIT Missing Semester, Lecture 6 (version control) | 3.6, 3.8 |
| P8 | JSON and YAML | Find the error: a YAML list with one item indented by 3 spaces | TechWorld with Nana, "YAML Tutorial" (~18 min) | 3.5, 3.8 |
| P9 | Odds, log-odds, sigmoid | Turn probability 0.2 into odds (0.25) and log-odds (−1.39) | StatQuest, "Odds and Log(Odds), Clearly Explained!!!" + "Logistic Regression" | 3.1 |
| P10 | PyTorch model basics | What's inside `state_dict`? What does `model.eval()` switch off? | done together: a walk through our notebook's model class at the start of 3.2 | 3.2 |
| P11 | Public-key cryptography, the idea | Why can you share a public key but never the private one? | MIT Missing Semester, Lecture 9 (security and cryptography) | 3.6–3.7 |

## The lectures, in one place (watch each part just before its step)

| source | parts | for step |
|---|---|---|
| CS50x 2024, Lecture 8 | the first part only (internet, TCP/IP, DNS, HTTP); stop when HTML starts | 3.0 |
| StatQuest | "Odds and Log(Odds)"; "Logistic Regression" | 3.1 |
| Full Stack Deep Learning 2022 | Lecture 5, Deployment | 3.2, 3.3 |
| Full Stack Deep Learning 2022 | Lecture 6, Continual Learning | 3.9 |
| freeCodeCamp, "Python API Development" (Sanjeev Thiyagarajan, 19 h) | §1, §3, §5, §6, §7, §8, §9, §11, §12 | 3.4 |
| | §15 (Docker) | 3.5 |
| | §14 (deploy on Ubuntu) | 3.6 |
| | §16 (testing; skip the voting tests) · §17 (CI/CD; skip the Heroku deploy) | 3.8 |
| | **skip:** §2 (except the venv videos), §4 (SQL basics, you're past it), §10 (votes), §13 (Heroku) | — |
| TechWorld with Nana, "Docker Tutorial for Beginners" (~3 h) | all | 3.5 |
| MIT Missing Semester | Lecture 5 (command-line environment, SSH) · Lecture 9 (security) | 3.6, 3.7 |

**Why the API course is watched almost whole, and in its own order:** later sections build on earlier ones.
§7 compares Pydantic with the ORM from §6. §16's tests use the logins from §8. §14 runs the migrations from §11.
Skipping a middle section, or reordering, is exactly how a "the course assumed I knew this" gap appears.
So §14 is watched before §15, as the course does, even though we build its part later (3.6). Re-watch §14's
NGINX / SSL / firewall videos at 3.6.

## Schedule

**Superseded (2026-10-03) by the compressed plan in `CLAUDE.md` §12:** build first, learn just-in-time while
building, and do the courses and the book after deploying. The steps and concepts below still apply; only
the timing changed.

---

## The big picture: what we are building

```
 someone opens the link  →  Swagger UI (a web page FastAPI makes for free)
        │  sends: company, product, sub-product, issue, state, tags + the complaint text
        ▼
 ┌──────────── one AWS server ─────────────────────────────────────────────┐
 │  [api container]                                                        │
 │    clean the text ........ clean_narrative()   (SQL, same as training)  │
 │    fetch the 19 inputs ... feature snapshot    (SQL, same formulas)     │
 │    tokenizer → ONNX model (CPU) → calibration → route                   │
 │    log the prediction                                                   │
 │  [postgres container]                                                   │
 │    snapshot as of 2024-12-31 · 150k test complaints · prediction_log    │
 └─────────────────────────────────────────────────────────────────────────┘
        ▼
 {"p_payout": 0.07, "route": "senior analyst", "model_version": "..."}
```

## The one idea under all of Phase 3: train/serve skew

**Intuition:** a chef perfects a recipe with one brand of salt. The restaurant buys another brand.
The recipe is the same but the dish isn't, and nobody gets an error message.

A model learned from inputs made one way. If serving makes them even slightly differently, its
answers quietly go wrong. In TriageIQ there are four places this could happen, and each one has a guard:

| where skew could creep in | our guard |
|---|---|
| the 19 SQL inputs | computed only in SQL (ground rule 4); the API never computes a feature in Python |
| the text cleaning | one SQL function, `clean_narrative()`, used by both the training export and the API |
| the tokenizer | ship the exact tokenizer files, special tokens `[DATE]` / `[REDACTED]` included |
| the probabilities | the calibration numbers ship with the model (step 3.1) |

Most deployment interview questions are a version of *"how did you make sure the live model sees
what it was trained on?"* This table is your answer.

## The steps at a glance

| # | step | the concept you learn | what gets built |
|---|---|---|---|
| 3.0 | Foundations | how a request travels the internet | nothing; you look at real traffic |
| 3.1 | Calibration | what a probability means; turning a probability into a decision | calibration numbers + the senior/template threshold |
| 3.2 | Packaging the model | serialization, ONNX, quantization, latency | the `.onnx` model + a results note |
| 3.3 | Serving features | offline vs online features, point-in-time, freshness | `sql/06_serving/` + a serving DB dump + a skew test |
| 3.4 | The API | HTTP, REST, FastAPI | `api/` with 4 endpoints, running on the Mac |
| 3.5 | Docker, completely | containers, images, layers, networks, volumes | `api/Dockerfile` + a two-service compose |
| 3.6 | Cloud + AWS + Linux | renting computers safely and cheaply | the public link |
| 3.7 | Security | attack surface, least privilege | a locked-down server + DB role |
| 3.8 | Testing + CI/CD | test pyramid, GitHub Actions | a green check on every push |
| 3.9 | Monitoring | drift, delayed labels, retraining | prediction log + a month-by-month drift report |
| 3.10 | Wrap-up | proof that outlives the server | README, recording, interview story, teardown |

---

## 3.0 Foundations: how a request travels

**Why:** every later step is this one idea in a different place: the API, Docker's ports,
AWS's firewall, HTTPS.

**Assumes:** P6 (shell). **Watch:** CS50x 2024 Lecture 8, the first part only (internet, TCP/IP, DNS, HTTP).

### Learn
- **Client and server.** A server is just a program waiting for messages. A client is anything that
  sends one: a browser, `curl`, another program.
- **IP address = a building's street address. Port = the flat number.** One machine runs many programs,
  each on its own port. That's why your Mac has Postgres.app on 5432 and the project DB on 5433.
- **DNS = the phone book.** It turns a name (`example.com`) into an IP address.
- **TCP:** the reliable delivery underneath. Just know it's there.
- **HTTP = the language of the message.**
  - A request has a method (GET reads, POST sends data to process), a path (`/predict`), headers,
    and a body (JSON).
  - A response has a status code and a body.
  - Status code families: **2xx** worked · **4xx** the caller's mistake (404 not found,
    422 bad input, 429 too many requests) · **5xx** the server broke.
- **HTTPS = HTTP inside a sealed envelope (TLS).** A certificate proves the server is who it says it
  is. Let's Encrypt gives free certificates.
- **`localhost` (127.0.0.1) = "this same machine".** This one word causes the classic Docker bug (3.5).
- **Firewall = the doorman.** It decides which ports outsiders may knock on.

### Build
- `curl -i https://api.github.com`: read the status line, the headers and the JSON body.
- `lsof -iTCP -sTCP:LISTEN -n -P | grep -E '5432|5433'`: see which program owns which port on your Mac.
- Explain our compose line `"5433:5432"` in these words, in your `learning_log.md`.

### Explain it back
- Someone opens our link. What happens, step by step, until they see the page?
- Why is a 422 the caller's fault and a 500 ours?

### Done when
You can draw: browser → DNS → IP:port → program, and mark where HTTPS and the firewall sit.

**Read:** MDN, "An overview of HTTP": https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview

---

## 3.1 Calibration: making "7%" mean 7%

**Why:** the API will show a probability. On the 150,000 test complaints from 2024, the model's
average prediction is **3.11%**, but **2.31%** actually paid (trap 13). The *ranking* is good. The
*numbers* aren't honest yet.

**Assumes:** P9 (odds, log-odds, sigmoid); Phase 2 revision cards 3, 11, 18 (the offset, AUC, the drift).
**Watch:** StatQuest "Odds and Log(Odds)" + "Logistic Regression". No good lecture on calibration itself, so
the best text is listed under Read below; the rest is taught in chat with our own data.

### Learn
- **What calibration means.** Among all complaints the model calls "10%", about 10 in 100 should pay.
  Think of a weather forecaster: on the days they said "30% rain", it should rain on about 30% of them.
- **Ranking and calibration are separate skills.**
  - AUC only checks the *order*.
  - A change that keeps the order (a *monotone* transform) leaves AUC exactly the same.
  - So calibrating can never change our within-company score.
- **Three reasons a model's probabilities drift off:**
  1. **Sampling.** We trained on 25% payouts on purpose (case-control). The −2.4165 offset already
     undoes this. *(tech: prior correction)*
  2. **The world changed.** Payouts among complaints with text fell: 2022 2.74% → 2023 2.51% →
     2024 1.71%. The offset can't know that. *(tech: prior / label shift)*
  3. **Neural nets tend to be overconfident.**
- **How to see it.**
  - A **reliability table** (or diagram): sort predictions into 10 buckets and compare the average
    *predicted* rate with the *actual* rate in each. On the diagonal means calibrated.
  - Scores: **Brier** (the average squared error of the probabilities) and **log loss**.
    **ECE** (expected calibration error) is the average gap between predicted and actual across
    the buckets.
- **The fixes, simplest first:**
  - **Intercept shift:** add one number to the logit. It fixes a change in the overall payout rate.
  - **Temperature scaling:** divide the logit by one number. Common for neural nets.
  - **Platt scaling:** both together, `p = σ(a · logit + b)`. A tiny logistic regression.
  - **Isotonic regression:** a free-form staircase. Needs lots of data and can overfit.
- **The golden rule:**
  - Fit the calibrator on data the model never trained on and that looks like the future.
  - Check it on data the calibrator never saw. You can't grade a fix on the data you fitted it to.
- **From a probability to a decision.** Routing is a *threshold*, and it isn't 0.5. Pick it from:
  - **capacity:** e.g. the senior team can read 10% of the queue, so senior = the riskiest 10%.
  - **cost:** what a missed payout costs vs what an analyst's hour costs.

  Today the riskiest 10% catches 92.6% of payouts (2024 test).

### Build
- Input: `training/outputs/fusion_distilbert_full/test_predictions.parquet` (the 2024 test scores plus
  the truth).
- The reliability table and Brier score **before** calibrating.
- Fit on Jan–Jun 2024 and check on Jul–Dec 2024. Compare intercept shift vs Platt vs isotonic.
- Refit the winner on all of 2024 (the most recent labelled data). Save its 1–2 numbers next to the model.
- Check: within-company AUC is unchanged. It must be, because the order didn't move.
- Choose the senior threshold and write down why.

### Explain it back
- Why can't calibration change AUC?
- Why not fit the calibrator on the validation set (Oct–Dec 2023, 3.50% payouts)?
- Why isn't the threshold 0.5?

### Done when
- Average predicted ≈ actual on Jul–Dec 2024.
- The reliability table sits near the diagonal.
- The calibration numbers are saved with the model, and the threshold is written down.

**Read:** scikit-learn, "Probability calibration": https://scikit-learn.org/stable/modules/calibration.html

---

## 3.2 Packaging the model: from a training file to a fast CPU program

**Why:** the server has a CPU, about 2 GB of RAM and no GPU. `model.pt` is 266 MB and needs PyTorch to
run, which is a very large install.

**Assumes:** P10 (done together at the start); Phase 2 revision cards 5, 6, 8 (tokenizer, special tokens, DistilBERT).
**Watch:** FSDL 2022 Lecture 5 (Deployment): the parts on model-as-service, ONNX, CPU vs GPU, distillation,
quantization.

### Learn
- **What's inside `model.pt`:** only the learned numbers, about 66 million weights at 4 bytes each.
  *(tech: state_dict)* The *shape* of the network lives in Python code. Weights without the code are
  answers without the questions.
- **Serialization** turns objects in memory into bytes on disk.
  - PyTorch saves with *pickle*, and a pickle file can run code when loaded.
  - So never load one from a stranger. That's why newer PyTorch loads weights only by default.
- **Computation graph:** a model is a recipe ("multiply by this, add that, apply this function").
  *Exporting* writes the recipe and the numbers into one file that no longer needs the original code.
- **ONNX is a universal recipe format.** ONNX Runtime is a fast kitchen that cooks any ONNX recipe.
  - Other kitchens: **TensorRT** (NVIDIA GPUs only, which is why we don't use it), **OpenVINO**
    (Intel CPUs), **Core ML** (Apple).
  - **Opset** = the version of the recipe language.
  - **Dynamic axes** = the file accepts any batch size and any text length.
- **Training mode vs inference mode.** At inference, turn dropout off (`model.eval()`) and skip
  gradients (`torch.no_grad()`). Forget `eval()` and predictions get noisy.
- **The family of "make it smaller and faster":**
  - **Quantization** stores numbers in 8 bits instead of 32, like saving a photo as a high-quality JPEG.
    - *Dynamic:* weights are int8, and activations are converted on the fly. No extra data needed.
    - *Static:* needs sample data to set the ranges.
    - *Quantization-aware training:* the model learns with 8 bits from the start.
  - **Distillation:** a small student learns from a big teacher. DistilBERT *is* this: a distilled
    BERT, 40% smaller and 60% faster, keeping about 97% of BERT's language understanding.
  - **Pruning:** remove the weights that are near zero.
- **Why int8 won't make us 4× smaller.** The vocabulary table (30,522 word-pieces × 768 = 23M numbers)
  usually stays 32-bit. Estimate: about 130–140 MB, not about 70.
- **Latency vs throughput.**
  - *Latency* is the time for one request. Report p50 (typical) and p95 (the slow ones).
  - *Throughput* is requests per second.
  - Batching raises throughput, but a single user only feels latency.
  - Text length drives latency: 512 word-pieces cost far more than 100.
- **The tokenizer is part of the model:** same vocabulary, same special tokens, same 512 limit.
  It ships with the model, always.

### Build
- `training/export_onnx.py`: load `model.pt` into the notebook's model class, switch to eval mode,
  and export with dynamic axes.
- **Check 1, same answers:** PyTorch vs ONNX on 1,000 test complaints. The largest difference should be
  tiny (about 1e-5).
- **Check 2, int8:** score all 150k test complaints and apply the ship rule (CLAUDE.md §12):
  - within-company stays inside 0.815–0.830;
  - top-10% recall holds;
  - count how many complaints flip between senior and template.
- **Check 3, speed on CPU:** p50 and p95 per complaint (short vs long texts) and peak RAM.

### Explain it back
- What does an `.onnx` file contain that `model.pt` doesn't?
- Why does int8 shrink the model only about 2×?
- Why not TensorRT?

### Done when
- One `.onnx` file exists (fp32 or int8, chosen by the ship rule), with the tokenizer files beside it.
- A short note records size, AUC, flips and latency.

**Read:** ONNX Runtime docs: https://onnxruntime.ai/docs/

---

## 3.3 Serving features: the same SQL, at request time

**Why:** a new complaint arrives with ids and text, but the model also needs its 19 inputs
(company × issue rate, shares, trends…). Training read those from `mv_features`. The 16 GB local DB is
not going to AWS.

**Assumes:** Phase 1 revision (all of it, especially cards 1, 3, 5, 6, 8). **Watch:** FSDL Lecture 5, the
first part (batch prediction vs model-as-service). *Book:* Chip Huyen ch. 7 (batch vs online prediction).
No lecture covers our exact design; we work it out together.

### Learn
- **Two ways to predict:**
  - **Batch:** score many rows on a schedule and store the answers (e.g. every night).
  - **Online (real time):** score one row when asked, in milliseconds.

  We do both: online for a typed-in complaint, batch for the 150k demo complaints (scored ahead of time).
- **Offline vs online features:**
  - *Offline* = the big history table for training: our `mv_features`, 4.8M rows.
  - *Online* = only the **latest** value per company / issue, built for fast lookups: our snapshot.
  - A **feature store** (e.g. Feast) is a tool that manages both and keeps them in sync.
    We do the same job by hand, in SQL.
- **Point-in-time correctness:** you already built this (as-of windows, the leak test). At serving
  time, "as of" means *now*. Our data ends 2024-12-31, so "now" is end-2024. That's a stated limit.
- **Freshness** is how old a feature may be. Ours is frozen. Real systems run a refresh job
  (a schedule that rebuilds the snapshot).
- **Cold start:** a company with no history. The no-history flags and smoothing toward the product rate
  already handle it. The API must never crash on it.
- **The strongest skew test:** rebuild a known past day through the serving path and compare it with
  the training table. Any difference is skew.

### Build
- `sql/06_serving/`: snapshot tables built by the **same formulas**, never re-written in Python. How to
  reuse `03_features` without copying formulas is the first design decision of this step; we make it
  together.
- The serving DB holds:
  - the dims;
  - the snapshot;
  - the 150k test complaints (19 inputs + clean text + true outcome);
  - the `clean_narrative()` function.

  `pg_dump` it. Estimate: about 300 MB.
- **Skew test:** build the snapshot as of a day in 2024. For complaints received that day, the
  snapshot's features must equal `mv_features` exactly.
- The lookup query for `/predict`: one row per entity, backed by an index, under 5 ms.

### Explain it back
- Why is the API not allowed to compute a feature in Python?
- What is train/serve skew, and how does your skew test catch it?
- A brand-new company sends a complaint. What happens?

### Done when
- The serving dump exists.
- The skew test passes.
- One lookup returns all 19 inputs for any (company, product, sub-product, issue, state, tags).

---

## 3.4 The API: FastAPI

**Why:** the resume link is an API with a web page (Swagger UI) where anyone can type in a complaint.
Ground rule 2: no JavaScript.

**Assumes:** P1–P5; step 3.0. **Watch:** freeCodeCamp API course §1, §3, §5, §6, §7, §8, §9, §11, §12.
**Bridge:**
- The course builds a social-media app with logins. Ours is mostly reads plus a model. Its structure
  (routers, schemas, dependencies, environment variables) is exactly ours.
- From §6 on, the course talks to the DB through an ORM (SQLAlchemy). We use plain SQL, as in §5, because
  features must stay in SQL (ground rule 4).
- Watch §6 anyway: you need it to follow §7 onwards. And "why no ORM?" is a good interview question.

### Learn
- **An API is a menu plus a waiter.** The menu (the endpoints) lists what you can ask for. The waiter
  takes the order to the kitchen (model + DB) and brings back the answer. You never enter the kitchen.
- **REST style:**
  - nouns as paths (`/complaint/{id}`);
  - verbs as HTTP methods (GET reads, POST sends data to process);
  - JSON in and out;
  - *stateless*: every request carries everything it needs.
- **A web framework handles the HTTP chores**, so you write plain Python functions. FastAPI's extras:
  - **Pydantic models** check input types and ranges automatically. Bad input gets a 422 without
    any code from you.
  - **OpenAPI:** a description of the API is generated from your code, and Swagger UI comes free.
- **The server program.**
  - **uvicorn** runs the app. *(tech: ASGI, the plug standard between server and app)*
  - **Workers** are copies of the app, and each holds its own model in RAM. On a 2 GB server:
    1 worker.
- **async vs sync.**
  - `async` helps when *waiting* (DB, network).
  - Model inference is CPU work, so write it as a plain `def`. FastAPI then runs it on a thread pool,
    and it doesn't freeze every other request.
- **Startup (lifespan):** load the model, tokenizer and DB pool **once**, when the app starts.
  Loading 266 MB per click would cost seconds every time.
- **Connection pool:** keep a few DB connections open and reuse them. Opening a new one each time costs
  tens of milliseconds.
- **Dependency injection** (`Depends`): FastAPI hands each endpoint what it needs, such as a DB connection.
- **Errors:** an unknown company id gets a clear 404 or 422, never a 500.
- **Traceability:** every answer carries the model version, and `/model-info` says which data and
  calibration it uses.

### Build: `api/`
- **`POST /predict`:** ids (picked from lists) + tags + text → SQL cleaning + feature lookup →
  tokenizer → ONNX → calibration → `{probability, route, model_version}`.
- **`GET /complaint/{id}`:** a real 2024 test complaint, its prediction, and what actually happened.
- **`GET /health`:** the app is up and the DB answers.
- **`GET /model-info`:** model version, data end date (2024-12-31), calibration, threshold, test scores.
- Run it locally against the local DB with `uvicorn api.main:app --reload` and try it at
  `localhost:8000/docs`.

### Explain it back
- Why does the API take ids + text and never features?
  Answer: one feature implementation. The cost is a DB round trip, and the API needs the DB to be up.
- Why load the model at startup?
- Why `def` and not `async def` for `/predict`?

### Done when
- All four endpoints work in Swagger on the Mac.
- `/complaint/{id}` gives the same probability as the offline score for that complaint.
  That's skew check #2.

**Read:** the FastAPI tutorial: https://fastapi.tiangolo.com/tutorial/

---

## 3.5 Docker, completely

**Why:** "works on my Mac" doesn't mean "works on AWS". Docker packs a program with everything it needs,
so the same box runs anywhere. You've used it since Phase 0.1 for Postgres. Now: what's under the
hood, and building your own image.

**Assumes:** P5, P6, P8; step 3.4 (an app to put in the box). **Watch:** TechWorld with Nana "Docker Tutorial for
Beginners" (all), then freeCodeCamp API course §15.
**Bridge:** the course uses Docker on the laptop. We also run the same compose file on the server (3.6).

### Learn
- **The problem.** An app needs particular system libraries, a Python version and packages.
  Installing them by hand on every machine drifts. *(the "works on my machine" problem)*
- **Container vs virtual machine.**
  - A **container** is a flat in one building. It has its own rooms but shares the building's plumbing
    (the host's Linux *kernel*), so it's light and starts in seconds.
  - A **VM** is a separate house with its own plumbing (a whole operating system). It's heavier and slower.
  - How the walls are built: Linux **namespaces** (each container sees only its own processes, network
    and files) and **cgroups** (limits on CPU and RAM).
- **On a Mac:** containers need a Linux kernel, so Docker Desktop runs a hidden Linux VM. That VM is
  where our 8 GB memory limit and 1 GB shared memory came from (traps 11–12).
- **Image vs container.** An image is a class: read-only, a template. A container is an object: a
  running instance, and one image can start many.
- **The Dockerfile is the recipe** for an image:
  - `FROM`: start from a base image, e.g. `python:3.12-slim`.
  - `WORKDIR`, `COPY`, `RUN` (install things), `ENV`, `EXPOSE`, `USER`.
  - `CMD` / `ENTRYPOINT`: what runs when the container starts.
- **Layers and cache.**
  - Each instruction adds a layer. Unchanged layers come from the cache.
  - So **order matters**: copy `requirements.txt` and install first, copy the code last.
    Code changes often; packages rarely.
- **Build context and `.dockerignore`.** `docker build` sends the folder to the builder. Without a
  `.dockerignore`, ours would send the 9.2 GB CSV.
- **Image size:**
  - slim base images;
  - **multi-stage builds**: build in one stage, copy only the results into a clean final stage;
  - CPU-only packages (ONNX Runtime instead of PyTorch).
- **Registries** are where images live: Docker Hub, AWS ECR, GitHub GHCR.
  - A **tag** is a version.
  - **Pin versions:** our compose pins `pgvector:0.8.0-pg16`, never `latest`.
- **CPU architecture.**
  - Your M4 builds **ARM64** images. Many cloud servers are **x86_64**, and an image built for one
    won't run on the other.
  - Fix: build for the server's type (`docker buildx build --platform linux/amd64 …`), or choose an
    ARM server.
- **Storage.** A container's files vanish when the container is removed. Two ways to keep data:
  - **Named volume:** Docker manages it. That's our `pgdata`.
  - **Bind mount:** a folder from the host. That's our `./Data:/import:ro`.

  `docker compose down -v` deletes volumes, which means **deletes the database**.
- **Networking.**
  - Each compose project gets a private network, and containers find each other **by service name**:
    the api connects to `postgres:5432`.
  - Inside a container, `localhost` means *that container itself*. That's the classic bug.
  - Port mapping `host:container` (our `5433:5432`) matters only for traffic from outside.
- **Config and secrets** go in env vars or an `env_file` at run time. **Never bake secrets into an
  image:** anyone who has the image can read them.
- **Compose runs many containers as one app:**
  - services;
  - `depends_on` + `healthcheck`: the API waits until Postgres *answers*, not just until it *starts*;
  - restart policies: `unless-stopped` restarts a container after a crash or a reboot.
- **Commands to know:** `build`, `run`, `ps`, `logs`, `exec`, `images`, `system df`, `prune`.

### Build
- Read our `docker-compose.yml` line by line and explain every line in `learning_log.md`.
- `api/Dockerfile`: multi-stage, slim, a non-root user, ONNX Runtime, no PyTorch.
- `.dockerignore`: `Data/`, `training/outputs/` (except the shipped model), `.env`, `.git`.
- A compose file with two services: postgres (restored from the serving dump) and api, with
  `depends_on: service_healthy`.
- The full stack running on the Mac: Swagger at `localhost:8000/docs`. Check the image size with
  `docker images`.

### Explain it back
- Container vs VM: what's shared, and what isn't?
- Why does the API fail with `localhost:5432` inside Docker?
- Why copy requirements before the code?
- What would `docker compose down -v` do to us?

### Done when
- `docker compose up` starts both services from nothing.
- You know the image size.
- `docker history` shows no secret inside the image.

**Read:** Docker, "Get started": https://docs.docker.com/get-started/

---

## 3.6 The cloud, AWS and a Linux server

**Why:** the link must be reachable by anyone for a few months, inside $100 of credits.

**Assumes:** P6, P7, P11; steps 3.0 and 3.5. **Watch:** MIT Missing Semester Lecture 5 (command-line
environment, SSH); freeCodeCamp API course §14 (deploy on Ubuntu).
**Bridge:**
- §14 runs the app directly on Ubuntu (gunicorn + systemd). We run `docker compose` on the server instead,
  but the server work is the same: SSH, packages, environment variables, NGINX, domain, SSL, firewall.
- The AWS-only parts (IAM, security group, budget alarms) are small. They're taught here and in chat.

### Learn
- **The cloud means renting someone else's computers by the hour.** You pay for what's switched on,
  including what you forgot to switch off.
- **Regions** (cities) and **availability zones** (separate buildings in a city). Resources live in one
  region, so pick one and stay in it.
- **The ladder of options**, from more control to less work:
  1. VM (EC2, Lightsail)
  2. managed containers (ECS/Fargate, App Runner)
  3. serverless functions (Lambda)
  4. managed ML (SageMaker endpoints)

  **Why we chose a VM:**
  - the cheapest steady price;
  - Postgres and the API fit on one box;
  - nothing goes to sleep (no cold starts);
  - you learn the most.
- **Lightsail vs EC2:** Lightsail is EC2 in a simple package at a fixed monthly price. EC2 exposes
  every knob.
- **IAM: who may do what.**
  - The **root user** is the owner: lock it away and turn MFA on.
  - **IAM users and roles** are for daily work.
  - **Policies** are JSON rules.
  - **Least privilege:** give each identity only what it needs.
  - **Access keys** are passwords for programs. Never put them in git (CLAUDE.md rule).
- **Networking.**
  - **VPC:** your private network inside AWS.
  - **Public IP vs static IP** (Elastic IP / Lightsail static IP). A static IP survives restarts.
  - **Security group = the doorman** (a stateful firewall): allow 80/443 from anywhere, 22 only from
    your IP, and **never 5432**.
- **SSH:** log into the server with a key pair. The private key stays on your Mac, is never shared,
  and is `chmod 400`.
- **Storage:** the server's disk (EBS). Snapshots are backups.
- **Money.**
  - Credits, and their **expiry date**.
  - **Budget alarms at $10 / $50 / $90, set before creating anything.**
  - What still bills after you *stop* a server: disks, unattached static IPs, snapshots.
- **Linux server basics:**
  - `apt install`, users and `sudo`;
  - `systemd` (services that start at boot);
  - `free -h` (RAM), `df -h` (disk), `htop`, logs;
  - **a swap file** (disk used as emergency RAM). On a 2 GB box with Postgres plus a model, a swap
    file prevents out-of-memory kills.
- **Getting things onto the server.** Code via `git clone`. Big files (model, DB dump) via
  `scp`/`rsync`, never git. Images are built there or pulled from a registry.
- **Reverse proxy: NGINX**, the same one the course uses in §14. A reverse proxy is a receptionist: it takes
  every visitor on 80/443 and walks them to the right room (our api container on port 8000).
- **Domain + HTTPS (optional).** Point the domain's DNS *A record* at the static IP. **certbot** gets a free
  Let's Encrypt certificate for NGINX (§14 shows it). *Alternative:* Caddy, which does HTTPS automatically;
  simpler, but not what the course teaches.

### Build
- Budget alarms first. MFA on root. An IAM user for yourself.
- One server (about 2 GB RAM), a static IP, the security group above, an SSH key.
- Install Docker, add swap, copy the model and the dump, then `docker compose up -d`.
- NGINX on the server forwards port 80 to the api container.
- Open `http://<static-ip>/docs` on your phone **with Wi-Fi off**. That proves it's public.
- Put a calendar reminder for the teardown date.

### Explain it back
- Why a VM, not Lambda or SageMaker?
- What does the security group allow, and why never 5432?
- What keeps costing money after you stop the server?

### Done when
- The link works from another network.
- The alarms are on.
- The real monthly cost is written down.

**Read:** AWS, "Security best practices in IAM":
https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html

---

## 3.7 Security for a public link

**Why:** anyone on the internet can call it, including bots that scan every IP address within hours of
it going live.

**Assumes:** P11; steps 3.4–3.6. **Watch:** MIT Missing Semester Lecture 9 (if not already watched for P11).

### Learn
- **Attack surface:** every open port and every input is a door. Fewer doors, safer house.
- **Secrets management.** Keep `.env` on the server only (`chmod 600`). At scale you'd use AWS Secrets
  Manager or SSM Parameter Store. Rotate any secret that leaks.
- **Least privilege in the DB.** The API's database role may SELECT the serving tables and INSERT into
  `prediction_log`, and nothing else. Then a bug can't delete data.
- **Input limits:** a maximum text length and only valid ids. Pydantic enforces both.
- **Rate limiting:** at most N requests per minute per IP, after which the caller gets a 429. This
  protects the 2 GB box, since every prediction costs CPU.
- **SQL injection.** Never build SQL by pasting user text into it. Always pass it as a parameter (`%s`).
  Learn the classic example of why.
- Containers run as **non-root**. Turn on automatic OS security updates (`unattended-upgrades`).
- **HTTPS** protects what users type while it travels.

### Build
- The read-only DB role.
- Pydantic limits on every input.
- Rate limiting, in NGINX or in the app.
- `USER` set to a non-root user in the Dockerfile.
- From outside, `nc -zv <ip> 5432` must **fail**.

### Explain it back
- How could a stranger hurt your server, and which line stops each attack?
- What is SQL injection, and why are you safe from it?

### Done when
- Port 5432 is unreachable from outside.
- The API role can't DELETE (try it).
- The request over the limit gets a 429.

---

## 3.8 Testing and CI/CD

**Why:** a machine should check every change, not your memory.

**Assumes:** P7, P8; step 3.4. **Watch:** freeCodeCamp API course §16 (skip the voting tests) and §17 (skip the
Heroku deploy). *Optional:* FSDL 2022 Lecture 3 (troubleshooting and testing ML).
**Bridge:** the course's tests create a throwaway test database through the ORM. Ours run the same idea with
plain SQL, plus the golden-example tests the course doesn't have.

### Learn
- **The test pyramid:**
  - many small **unit** tests (one function each);
  - fewer **integration** tests (API + DB together);
  - a few **end-to-end** tests (the whole stack, used the way a person would).
- **ML systems need three kinds of test:**
  - **data tests:** you already have these (`sql/tests/`, `11_validate.sql`);
  - **model tests:** *golden examples*, where a known complaint must score within a tiny margin of its
    saved value, plus the skew checks from 3.3 and 3.4;
  - **code tests:** e.g. the API returns 422 on bad input and 404 on an unknown id.
- **pytest** basics, and FastAPI's **TestClient**, which calls the API without starting a server.
- **CI (continuous integration):** on every push, a fresh machine runs lint, tests and the build.
  Red means don't merge. **CD (continuous delivery/deployment):** a green `main` ships automatically.
- **GitHub Actions vocabulary:**
  - **workflow:** a file in `.github/workflows/*.yml`;
  - **trigger:** e.g. `on: push`;
  - **job** and **step**;
  - **runner:** the rented machine that runs it;
  - **secrets:** stored in GitHub settings, never in the file.
- **Linting** (ruff) catches mistakes before the code ever runs.

### Build
- `tests/`: a handful of API tests plus 3 golden complaints.
- `.github/workflows/ci.yml`: ruff → pytest → docker build.
- The catch: the 266 MB model isn't in git, so CI can't load it. Decide at this step which tests run in
  CI (no model) and which run locally or on the server (golden ones).
- Optional CD: on `main`, SSH to the server and run `docker compose pull && docker compose up -d`.

### Explain it back
- What does CI catch that you'd miss?
- Why do ML systems need golden-example tests on top of code tests?

### Done when
- A push shows a green check on GitHub.
- A deliberately broken commit shows red.

**Read:** GitHub Actions docs: https://docs.github.com/en/actions

---

## 3.9 Monitoring and the closed loop

**Why:** a model is right on the day it ships, then slowly gets less right. You've already seen it:
among complaints with text, payouts fell from 2.74% (2022) to 1.71% (2024).

**Assumes:** step 3.1 (calibration); Phase 1 revision card 2 (window functions). **Watch:** FSDL 2022 Lecture 6
(Continual Learning). *Book:* Chip Huyen ch. 8–9.

### Learn
- **Two kinds of monitoring:**
  - **System health:** is it up? How slow? Any errors? How much CPU and RAM?
  - **Model health:** is it still right?
- **What changes in the world, by name:**
  - **Data drift:** the inputs change, e.g. more complaints about a new product.
  - **Prior / label shift:** the payout rate changes. That's our 2024 case.
  - **Concept drift:** the same complaint now gets a different outcome, e.g. a company changes its policy.
- **The catch: labels arrive late.** A company has 15 days to respond, and we assume up to 60 days
  (D15). So you watch the inputs and the predictions *now*, and accuracy *later*.
- **Measures:**
  - **PSI** (population stability index), which measures how far a distribution moved.
    Rule of thumb: < 0.1 stable · 0.1–0.25 watch · > 0.25 act.
  - **KS test.**
  - Average predicted vs actual over time (calibration drift).
  - AUC per month, once the labels arrive.
- **Logging.**
  - Every prediction becomes a row in `prediction_log`: time, a reference to the inputs, score,
    latency, model version.
  - Log without blocking. A logging failure must never fail a prediction.
  - Use **structured logs** (JSON) for the system side.
- **Alerting:** a check that messages you when a number crosses a line.
- **Retraining.**
  - On a schedule, or when a trigger fires.
  - A new model replaces the old one only if it beats it on the **newest** data.
    *(tech: champion vs challenger)*
  - Safe rollout:
    - **shadow:** the new model scores silently alongside the old one;
    - **canary:** it gets a small share of traffic first;
    - **rollback:** a way to switch back fast.
- **Model registry and versioning:** every model has an id, and every prediction records which model
  made it.

### Build
- The `prediction_log` table and a non-blocking insert in the API.
- **Simulated production:** replay the 150k 2024 test complaints month by month (Jan → Dec) through the
  same scoring code, as if they were arriving live. Use batch scoring; 150k separate web calls would take
  hours.
- A **SQL drift report** (window functions, your strongest skill). For each month vs the trailing 3 months:
  - PSI for the main inputs and for the score;
  - average predicted vs actual;
  - AUC per month.
- Read the report and write down the month you would have retrained, and why.
- The system side: latency p50/p95 from `prediction_log`, and RAM from `docker stats`.

### Explain it back
- Data drift vs concept drift vs prior shift: which one hit TriageIQ in 2024?
- How do you monitor a model when its labels arrive 60 days late?
- When would you retrain, and how would you know the new model is better?

### Done when
- A month-by-month drift table exists.
- You can point at the month you would have acted, and say why.

---

## 3.10 Wrap-up: proof that outlives the server

**Why:** the server gets deleted after a few months, but your resume keeps the link.

### Build
- **README:** the live link and the ⏳ placeholders filled in. Add a **60–90 second screen recording**
  (or GIF) of the demo; it survives the teardown.
- **blog_log.md:** the Phase 3 entries.
- **The 2-minute interview story:**
  1. the problem
  2. the data
  3. the SQL features (point-in-time, leak-tested)
  4. the model (the ablation: is SQL + text worth more than text alone?)
  5. deployment (skew-safe serving)
  6. monitoring (the drift you found)
  7. what you'd do next
- **Teardown on the reminder date:** delete the server, the static IP and the snapshots. Check that
  next month's bill is $0. Then update the README: "demo retired, recording here".

### What you can honestly claim
With 3.0–3.9 done: **the full lifecycle**, from raw data through features, training, deployment and
monitoring. Say these two limits out loud before anyone asks:
1. The data ends 2024-12-31, so the live demo scores against a frozen snapshot. There's no live
   refresh; it's designed (3.3) but not built.
2. Monitoring is shown by replaying 2024, not on real live traffic.

### Done when
Someone who never saw the live link can still watch it work (the recording) and read why every choice
was made.
