# TriageIQ — frontend brief

**Part A** is the design brief: paste it into Claude Design. **Part B** is the build contract: what each screen
calls and shows, so the approved design can be wired to the live API.
Status (2026-10-05): brief only — nothing built yet. The API runs behind NGINX (`/docs` = Swagger UI).

---

## The decision: server-rendered pages, no JavaScript

- **The JSON API stays exactly as it is** (Swagger UI, Postman). The website is a few extra pages served by
  the same FastAPI app: HTML built on the server from templates (Jinja2). A form submits to the server, and the
  answer comes back as a page.
- **Why:**
  - ground rule 2 ("no JavaScript, ever") holds;
  - the pages live on the same server and the same address as the API, so there's no cross-site (CORS) setup;
  - it works over plain HTTP today and over HTTPS later, unchanged.
- **The alternative and its costs:** a JavaScript app hosted somewhere else would break ground rule 2. It would
  also need CORS on the API, plus HTTPS on the API: a browser blocks an https page from calling an http API
  ("mixed content").
- **So the design must work with plain HTML + CSS.** Native HTML already gives us everything the design needs:
  - dropdowns, including dropdowns grouped into sections;
  - type-ahead suggestions (`<datalist>`);
  - checkboxes and text areas;
  - expandable sections (`<details>`).

  It does not give live search, client-side charts or animations driven by script. CSS effects are fine.

---

## Part A — Design brief (for Claude Design)

**Product.** TriageIQ predicts whether a consumer complaint sent to the US Consumer Financial Protection Bureau
(CFPB) will end with the company paying money. A compliance team can then send the riskiest complaints to a
senior analyst first. A fine-tuned language model reads the complaint; a database supplies the company's
track record.

**Who opens it.** Recruiters and interviewers clicking a link on a resume. Some are technical, some are not. They
use a laptop or a phone and give it about a minute of attention. A secondary persona is a compliance analyst
triaging a queue.

**The one-minute goal.** Understand what it does → try it once → see that it's real and honest (it shows its
misses too).

**Tone and look.**
- Calm and credible: a tool a bank's compliance team would trust.
- Light background, one accent colour, clear type, generous spacing, big readable numbers.
- No stock photos, no hype.
- Accessible: AA contrast, a visible label on every field, works with the keyboard, readable at 375 px wide.

### Screens

**1. Home: "Score a complaint"**
- **Header:** the name and a one-line pitch ("Will this complaint cost the company money?").
- **Navigation:** Score · Real 2024 complaints · How it works · API docs ↗ · GitHub ↗.
- **The form:**

| field | control | notes |
|---|---|---|
| Company | text input with type-ahead suggestions (4,946 names) | unknown names are allowed; they're scored as "no track record" |
| Product | dropdown (11) | |
| Sub-product | dropdown grouped by product (62 in total) | must belong to the chosen product |
| Issue | dropdown (93) | long labels, so it needs width |
| State | dropdown, optional | 2-letter codes |
| Older American (62+) · Servicemember | two checkboxes | |
| Complaint | large text area | at least 20 words, at most 20,000 characters. Hint: "Written like CFPB complaints: amounts as {$35.00}, hidden details as XXXX" |

- **Two "try an example" links** that open the form pre-filled: "A fee refund (bank)" and "A credit-report dispute".
- **Primary button:** "Score it".

**2. Result** (shown under the form)
- **A big number:** "31.7% chance the company pays".
- **A route badge:** **Senior analyst** (accent colour) or **Template response** (neutral). Below it: "Seniors read
  the riskiest 10% — complaints at 3.67% or more."
- **"What the model saw":** the company's track record (6–8 numbers with plain labels, see Part B), plus a note
  when the text was too long to read in full.
- **Notes,** e.g. "This company isn't in our data — scored as a company with no track record."
- **Footer line:** "Track records as of 1 Jan 2025 (the data ends 31 Dec 2024)."

**3. Real 2024 complaints: the model vs what actually happened**
- **Three buttons:** "Any" · "One the company paid" · "One it didn't".
- **A card showing:**
  - company · product · issue · date;
  - the complaint text, with `[REDACTED]` and `[DATE]` shown as small grey chips and a one-line caption
    explaining them;
  - the model's call (probability + route) side by side with what happened ("Closed with monetary relief",
    "Closed with explanation", …);
  - a verdict badge: **caught** · **missed** · **correctly left to a template** · **false alarm**.
- **An honest caption:** "Tested on 150,000 complaints from 2024 it never saw. It isn't always right — the
  company's own decision often isn't in the text."

**4. How it works**
- **A 3-step picture:** the complaint text is read by the language model, while the company and issue track
  record comes from the database → one combined score → senior analyst or template.
- **Result tiles** (live numbers from the API):
  - within one company it ranks 82 of 100 paid/unpaid pairs correctly (range 0.815–0.830);
  - the riskiest 10% catches 92.6% of payouts;
  - tested on 150,000 complaints (3,471 payouts).
- **The limits list** (from the API).
- **Links:** API docs, GitHub, the blog.

### States to design
- an empty form;
- field errors, inline under the field, e.g. "write at least 20 words…" or "unknown sub-product — choose one of …";
- the unknown-company note;
- a result;
- "Too many requests — wait a few seconds";
- "The service is having trouble — try again in a minute".

### Sample content for the mockups (real outputs of the live model)

| example | chance it pays | route |
|---|---|---|
| Overdraft-fee refund, JPMorgan Chase, checking account | 31.7% | Senior analyst |
| Credit-report dispute, Equifax | under 0.01% | Template response |
| The same fee text, an unknown credit union, Older American | 40.5% | Senior analyst + "no track record" note |
| Real 2024 complaint: Synchrony credit card, "duped into signing up" | 2.5% | Template — **missed** (the company paid) |

### What to hand back
- Desktop and mobile frames of the 4 screens and the error states.
- The colour palette and type scale.
- HTML/CSS if it can export them. JavaScript isn't needed or wanted.

---

## Part B — Build contract (for the implementation)

**Routes** — added to the FastAPI app; the JSON API doesn't change:

| page | route | does |
|---|---|---|
| Home + form | `GET /` | the lists (products → sub-products, issues, states, all company names), read once at startup from schema `serving` |
| Score | `POST /score` (an HTML form) | the same steps as `POST /predict` → renders the result on the Home page |
| Real complaints | `GET /real?paid=true\|false` | the same as `GET /complaint/random` |
| How it works | `GET /how` | renders the contents of `GET /model-info` |
| API docs | `/docs` | unchanged (today `/` redirects there; `/` becomes the Home page) |

**Display labels for the model's inputs:**

| input | label | show as |
|---|---|---|
| `company_issue_rate_s` | This company's payout rate on this kind of problem | % (1 decimal; below 0.1% → "under 0.1%") |
| `company_rate_s` | This company's payout rate overall | % |
| `issue_rate_s` | Payout rate for this kind of problem, all companies | % |
| `product_rate_s` | Payout rate for this product | % |
| `company_no_history`, `company_issue_no_history` | No track record yet (company / on this problem) | yes / no |
| `company_untimely_rate` | Complaints this company never answered | % |
| `company_share_90d` | Its share of all complaints, last 90 days | % |
| `company_trend_90d`, `issue_trend_90d` | Complaint volume, last 90 days vs the 90 before | e^value as "1.2× more" / "0.8× (fewer)" |
| `company_quiet_days` | Days since the company's previous complaint | number |

Ids and the two tags are the visitor's own choices, so they aren't repeated back.

**How errors are shown:**
- **422:** the message goes under the field it names. Pydantic's error says which field; our name-lookup errors
  name the field in the message.
- **429** (from NGINX): a banner, "Too many requests — wait a few seconds".
- **500 / 503:** a banner, "The service is having trouble — try again in a minute".

**Constraints:**
- no JavaScript;
- one CSS file;
- a system font stack unless the design needs a web font;
- the company suggestion list is about 200 KB (estimated). If that turns out too heavy, use a two-step "find
  your company" form instead.

**Out of scope:** logins, saved history, live search, charts drawn by script.
