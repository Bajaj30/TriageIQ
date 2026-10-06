# Phase 3 — Revision: from a trained model to a public link

Interview prep for `training/serving/`, `sql/06_serving/`, `api/`, `deploy/`, `web/`, `docs/`. The day-by-day
build record is `CLAUDE.md` §12; the roadmap with the full lessons is `Learning/Phase3/directions.md`. Unless
stated, scores are on **the 2024 test set: 150,000 complaints, 3,471 payouts (2.31%)**.

**The one-line version:** *"The model runs on a CPU as ONNX behind FastAPI, on one small AWS server, with a
website on Vercel in front. The live track records come from the same SQL formulas as training, and a skew test
proved them identical on 20,773 complaints. Probabilities are re-calibrated on the newest data, because payouts
drift down every year."*

```
visitor ─https─▶ Vercel (static site) ─API paths + secret header─▶ NGINX (EC2, Sydney): 403 without the secret,
                                                                    5 req/s per visitor
        FastAPI ◀───────────────────────────────────────────────────┘
          ├─ Postgres `serving`: 19 inputs via serving.model_input() · text via serving.clean_narrative()
          └─ tokenizer → ONNX (DistilBERT + 19 inputs) → logit → offset → Platt → p → senior if p ≥ 0.0367
```

---

## A. Turning a score into a decision (`training/serving/calibrate.py`)

### 1. Calibration — does "10%" mean 10%?
- **Idea:** a weather forecaster who says "30% rain" should see rain on about 30 of every 100 such days.
  Ranking (who is riskier) and calibration (how risky) are separate skills.
- **In TriageIQ:** after the case-control offset (−2.4165) the model predicted 3.11% payouts on 2024 vs 2.31%
  actual. The offset fixes *sampling*; the rest is *drift* — payouts fall every year.
- **Q:** Your model ranks well; why calibrate? → **A:** The website shows a percentage and a desk staffs from it.
  A ranking can be right while every number is 35% too high.

### 2. Platt scaling, checked honestly
- **Idea:** fit a tiny logistic regression on the model's own score: p = sigmoid(a·z + b). Two numbers.
- **In TriageIQ:** fitted on the newest labelled data, Jul–Dec 2024 (a 0.7025, b −0.7621). The check came first:
  fit on Jan–Jun, test on Jul–Dec → predicted 2.22% vs actual 2.10% (the offset alone said 2.91%).
  **Isotonic rejected:** its flat steps create ties, which lowered within-company AUC (0.8296 → 0.8290).
- **Q:** Why fit on the test year — isn't that cheating? → **A:** The test year was used for the reported AUC
  first; calibration only reshapes probabilities and can't change the ranking (within-company stays 0.8224).
  I validated the method on a split (H1 → H2) before refitting on the newest months.
- **Q:** Platt or isotonic? → **A:** Isotonic is more flexible but needs lots of data and creates ties; with a
  2% base rate Platt's two numbers are stable and keep the order.

### 3. The threshold is a business rule
- **Idea:** a probability isn't a decision. Pick the cut-off from what the desk can afford.
- **In TriageIQ:** "seniors read the riskiest 10%" → p ≥ 0.0367. That 10% catches 92.6% of payouts; 21.4% of
  them pay vs 0.19% of the template pile.
- **Q:** Why 10%? → **A:** It's a capacity assumption, stated openly; the curve on the essay shows the trade-off
  for any other capacity.
- **Watch:** StatQuest "Odds and Log(Odds)" + "Logistic Regression". *Read (no good lecture exists):*
  scikit-learn user guide, "Probability calibration".

---

## B. Packaging the model (`training/serving/export_onnx.py`)

### 4. ONNX — the model as one portable file
- **Idea:** `model.pt` is just weights; it needs the Python class and PyTorch to run. ONNX stores the network
  *and* the weights as a graph any runtime can execute — like exporting a document to PDF.
- **In TriageIQ:** model.onnx 266 MB; ONNX Runtime on CPU, no PyTorch in the image (the API venv is 210 MB).
  Checked: tokenizer 1000/1000 identical; max logit difference vs PyTorch 1e-5; rank correlation 0.999999.
- **Q:** Why ONNX over shipping PyTorch? → **A:** Smaller image, faster CPU inference, one file with no code
  dependency — and I proved it gives the same answers before switching.

### 5. Latency — measure p50 and p95, on the real machine
- **Idea:** the median (p50) is the typical wait; p95 is what the unlucky 1 in 20 sees. Long texts are slower.
- **In TriageIQ:** model alone on the M4 laptop p50 20 ms / p95 81 ms; on the 2-core cloud server p50 218 ms /
  p95 803 ms — about 10× slower. The feature lookup is 0.6 ms: the model is nearly the whole cost.
- **Q:** Would you quantize to int8? → **A:** Only if a measured need appears. Memory was fine (api ~550 MiB of
  ~1.8 GB) and 0.2 s is fine for a triage desk; int8 must also pass the same ranking checks before it ships.
- **Watch:** Full Stack Deep Learning 2022, Lecture 5 (Deployment).

---

## C. Serving features (`sql/06_serving/`)

### 6. Offline vs online features — and train/serve skew
- **Idea:** a chef perfects a recipe with one brand of salt; the restaurant buys another. Same recipe, different
  dish, no error message. Skew is when serving computes an input differently from training.
- **In TriageIQ:** training read `mv_features` (16 GB database). The server gets a 187 MB `serving` schema: a
  "scoreboard" of counts per company / issue / product as of 2025-01-01, built by `build_serving_snapshot(date)`
  in ~12 s, and `serving.model_input()` that turns it into the 19 inputs with the same formulas.
- **Q:** How do you know live features match training? → **A:** A skew test: build the snapshot as of 3 past days,
  push those days' 20,773 complaints through the live function, compare with the training view — 19/19 inputs
  identical, max difference 0.
- **Q:** What did the test teach you? → **A:** A same-day rule: in training the 2nd complaint of a company on one
  day has a 0-day gap; a live complaint has no same-day predecessor. Tests find rules you didn't know you had.

### 7. One function for the text
- **In TriageIQ:** `serving.clean_narrative()` is copied from training's definition with `pg_get_functiondef`
  (2,000/2,000 identical) — blanks become `[DATE]` / `[REDACTED]`, the special tokens the model learned.
- **Q:** Why clean text in SQL, not Python? → **A:** One definition, used by the training export and the API,
  so the two can't drift.

### 8. "As of" is a limit — say it
- **In TriageIQ:** the data ends 2024-12-31, so a new complaint is scored with track records as of that date.
  Live freshness would need a refresh job (rebuild the snapshot nightly) — not built.

---

## D. The API (`api/`)

### 9. FastAPI and the request cycle
- **Idea:** an API is a waiter: takes an order in a fixed format, brings back a dish in a fixed format.
  FastAPI checks the order (Pydantic types) before the kitchen sees it and writes the menu (`/docs`) for free.
- **In TriageIQ:** `POST /predict` (names + text) · `GET /complaint/random` and `/complaint/{id}` (a real 2024
  complaint vs what happened) · `/options/*` (lists) · `/model-info` · `/health`. Model loaded once at startup
  (lifespan); a connection pool to Postgres; parameterised SQL.
- **Q:** Why does the API take names and text, never features? → **A:** So there is exactly one feature
  implementation (SQL). The cost: a DB round-trip per request and a dependency on the DB being up.
- **Q:** What happens with bad input? → **A:** 422 with the field named (fewer than 20 words, like training; an
  unknown product lists the valid ones). An unknown company is allowed: scored as "no track record", with a note.

### 10. Proving the API = the offline score
- **In TriageIQ:** 300 random 2024 complaints through the API vs the offline scores: max |Δp| 0.00017, same
  route 100%. Repeated in Docker (0.00024) and through the public link (0.00017).
- **Watch:** freeCodeCamp "Python API Development" (Sanjeev Thiyagarajan) — sections in `directions.md`.

---

## E. Docker (`deploy/api.Dockerfile`, `deploy/docker-compose.yml`)

### 11. Image, container, layers
- **Idea:** an image is a frozen lunchbox (code + libraries + model); a container is that lunchbox opened and
  running. Layers are cached, so unchanged steps don't rebuild.
- **In TriageIQ:** multi-stage build (install in one stage, copy only the result), python:3.11-slim, a non-root
  user `app`, the model baked in; a `.dockerignore` **allow-list** so the 9 GB CSV can never enter the build.
- **Q:** Why non-root? → **A:** If the app is broken into, the attacker isn't root inside the container.

### 12. Compose — services that find each other by name
- **In TriageIQ:** `db` (postgres:16-alpine, restores the 57 MB dump on first start, **no published port**),
  `api` (reaches the DB at hostname `db`), `nginx` (profile `public`, server only). A TCP healthcheck makes the
  API wait until the restore has finished, not just until the container exists. From an empty volume: data
  restored in ~3 s, API healthy ~6 s later.
- **Q:** Why does `localhost` fail inside a container? → **A:** Each container has its own network namespace;
  `localhost` is the container itself. Compose's DNS gives each service its name.
- **Gotcha:** the Mac builds ARM64 images → the server is ARM too (Graviton).
- **Watch:** TechWorld with Nana, "Docker Tutorial for Beginners".

---

## F. The cloud (AWS EC2, Sydney)

### 13. Renting one small computer, safely
- **In TriageIQ:** t4g.small (2 vCPU ARM, 2 GB RAM + 2 GB swap), Ubuntu 24.04, 20 GB encrypted disk, IMDSv2,
  an Elastic IP (`3.106.107.237`); security group: 80 open, 22 only from my IP, no 5432 / 8000. ≈ $21/month from
  $140 of free credits; a budget alarm at $25/month.
- **Q:** Why not Kubernetes / a managed DB? → **A:** One demo, low traffic, free credits: one server with Compose is
  the smallest thing that works. I'd move the DB to a managed service the day it held data that mattered.

### 14. Burstable CPUs — the server that started out of breath
- **Idea:** T-family servers bank CPU credits while idle and spend them under load; at zero they're held to a
  baseline (20% here). A new one starts with none.
- **In TriageIQ:** first test p50 501 ms / p95 3,590 ms (throttled); at full speed p50 210 ms / p95 807 ms
  (0% steal). Kept **standard** mode: *unlimited* is always fast but can bill extra.

### 15. Regions are policy, not just geography
- **In TriageIQ:** Mumbai was denied by the AWS Organization's policy (an SCP) — not a missing permission of
  mine — so the server lives in Sydney.
- **Watch:** MIT Missing Semester, Lecture 5 (SSH) and Lecture 9 (security); freeCodeCamp §14 (Ubuntu deploy).

---

## G. Security and the front door (`deploy/nginx/default.conf.template`, `web/vercel.json`)

### 16. Reverse proxy + rate limit
- **Idea:** NGINX is a receptionist: the API never faces the internet directly.
- **In TriageIQ:** 5 requests/s per visitor with a burst of 20, then 429; request bodies ≤ 64 KB.

### 17. Locking the server to the website
- **Idea:** the site on Vercel forwards API calls (same https address → no CORS, no mixed content). But anyone
  could call the server's IP, and every visitor arrives from Vercel's IPs.
- **In TriageIQ:** Vercel adds a secret header (48 chars, made on the server, never printed or committed); NGINX
  returns 403 without it and rate-limits on Vercel's `x-real-ip` **only when the secret matches**, so a forged
  header can't dodge the limit. Checked: direct calls 403; 40 rapid calls → 22 × 200 / 18 × 429.
- **Q:** What would you add next? → **A:** A read-only DB role for the API (least privilege), HTTPS on the server
  itself if anything but Vercel ever needed it.

---

## H. Not built — and how I'd build it

### 18. CI (step 3.8)
On every push: `ruff` (lint), `pytest` (a few API tests: /health, one known complaint's score, a 422), and a
`docker build`. Four steps that always run beat twelve that are flaky.

### 19. Monitoring and delayed labels (step 3.9)
- **Idea:** you can't measure accuracy live — a complaint's outcome arrives weeks later. So watch the *inputs*
  and the *scores* now, and the accuracy later.
- **Plan:** a `prediction_log` table; a SQL query comparing this week's score distribution with last month's;
  replay 2024 month by month to show drift. Evidence so far: ranking didn't decay in 2024 (within-company Jul–Dec
  0.8296 vs full year 0.8224); the drift is in the base rate, which calibration handles.
- **Watch:** Full Stack Deep Learning 2022, Lecture 6 (Continual Learning).

---

## What broke, and the fix

| what happened | fix | lesson |
|---|---|---|
| Probabilities 35% too high on 2024 (3.11% vs 2.31%) | Platt on the newest data | the sampling correction doesn't fix drift |
| Isotonic calibration lowered AUC slightly | Platt | ties are a ranking cost |
| A same-day gap rule differed between training and serving | written into the skew test | tests find rules you didn't know |
| First server test 2–4× slow | wait for CPU credits; re-measure | measure on the real machine, at the real state |
| EC2 denied in Mumbai | Sydney | org policies (SCPs) override your own permissions |
| NGINX crash-loop: `could not build map_hash` (48-char secret) | `map_hash_bucket_size 128` | test with production-like values |
| `vercel env add` ignored piped input | pass `--value` from a shell variable | CLIs behave differently without a terminal |
| Postman 404 at `/get/health` | the method isn't part of the path | GET is the verb, `/health` the path |
| Dark Reader hid the blog's diagram | CSS variables + HTML buttons | don't draw text in SVG for themed pages |

## Numbers to know
Serving schema **187 MB** (dump **57 MB**) · snapshot as of **2025-01-01** · skew test **19/19** on **20,773** ·
model.onnx **266 MB** · API vs offline max |Δp| **0.00017** · threshold **0.0367** = riskiest 10% → **92.6%** of
payouts · server: model p50 **218 ms** / p95 **803 ms**, API p50 **210** / p95 **807 ms** · RAM api ~**550 MiB** ·
cost ≈ **$21/month** of **$140** credits, plan ends **2027-04-02**.

## Lectures to re-watch
- StatQuest: "Odds and Log(Odds)", "Logistic Regression" (calibration).
- Full Stack Deep Learning 2022: Lecture 5 (Deployment), Lecture 6 (Continual Learning).
- freeCodeCamp, "Python API Development" (Sanjeev Thiyagarajan): the sections listed in `directions.md`.
- TechWorld with Nana: "Docker Tutorial for Beginners".
- MIT Missing Semester: Lecture 5 (command line, SSH), Lecture 9 (security).
- *Book:* Chip Huyen, *Designing Machine Learning Systems* — ch. 7 (deployment), ch. 8 (shift and monitoring), ch. 9 (continual learning).
