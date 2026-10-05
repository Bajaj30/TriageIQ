# TriageIQ — frontend brief

**Part A** is the design brief: paste it into Claude Design. **Part B** is the build contract: how the site is
put together and what each screen calls.
Status (2026-10-05): brief only — nothing built yet. The API runs on AWS behind NGINX (`/docs` = Swagger UI).

---

## The decision: a JavaScript site on Vercel, the API stays on AWS

*Decided by Shivam on 2026-10-05: ground rule 2 ("no JavaScript") is lifted. It existed only because he
doesn't write frontend code himself; Claude builds the site.*

```
visitor ──https──▶ Vercel (triageiq.vercel.app)
                     ├─ the pages (HTML/CSS/JS, served from Vercel's CDN, close to the visitor)
                     └─ /predict, /complaint/…, /options/…, /model-info, /docs ──rewrite──▶ AWS server (NGINX → API)
```

- **A static site.** HTML, CSS and JavaScript (plain, or React if the design comes that way), with no server
  code on Vercel. It's hosted free on Vercel's Hobby plan (personal, non-commercial).
- **One address for everything.** The browser only ever talks to `https://<project>.vercel.app`. API calls
  go to the same address (e.g. `/predict`), and Vercel forwards them to the AWS server (a *rewrite*). So there is:
  - no "mixed content" block: an https page calling an http server is forbidden by browsers, but the page
    never calls the server directly;
  - no CORS setup: to the browser it's all one site;
  - one clean link for the resume, with the Swagger docs at `/docs` on the same address.
- **Server side:**
  - Vercel attaches a secret header to every request it forwards, and NGINX rejects anything without it;
  - rate limits use the visitor's real IP, which Vercel passes on.
- **Open check:** Vercel's docs show only `https` targets for rewrites, and our server is plain `http`. That's
  tested first. If it fails, the server gets free HTTPS (Let's Encrypt on an sslip.io name) and the rewrite
  targets that instead.

---

## Part A — Design brief (for Claude Design)

**Product.** TriageIQ predicts whether a consumer complaint sent to the US Consumer Financial Protection Bureau
(CFPB) will end with the company paying money. A compliance team can then send the riskiest complaints to a
senior analyst first. A fine-tuned language model reads the complaint; a database supplies the company's
track record.

**Who opens it.** Recruiters and interviewers clicking a link on a resume. Some are technical, some are not.
They use a laptop or a phone and give it about a minute of attention. A secondary persona is a compliance
analyst triaging a queue.

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
| Company | search box with live suggestions as you type (4,946 names) | unknown names are allowed; they're scored as "no track record" |
| Product | dropdown (11) | |
| Sub-product | dropdown that updates when the product changes | only the chosen product's sub-products (62 in total) |
| Issue | searchable dropdown (93) | long labels |
| State | dropdown, optional | 2-letter codes |
| Older American (62+) · Servicemember | two checkboxes | |
| Complaint | large text area with a live word counter | at least 20 words, at most 20,000 characters. Hint: "Written like CFPB complaints: amounts as {$35.00}, hidden details as XXXX" |

- **Two "try an example" buttons** that fill the form: "A fee refund (bank)" and "A credit-report dispute".
- **Primary button:** "Score it". It shows a loading state, because a score can take up to a few seconds.

**2. Result** (appears below the form, no page reload)
- **A big number:** "31.7% chance the company pays". A small animated gauge is fine.
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
- **Result tiles** (live numbers from `/model-info`):
  - within one company it ranks 82 of 100 paid/unpaid pairs correctly (range 0.815–0.830);
  - the riskiest 10% catches 92.6% of payouts;
  - tested on 150,000 complaints (3,471 payouts).
- **The limits list** (from `/model-info`).
- **Links:** API docs (`/docs`), GitHub, the blog.

### States to design
- an empty form;
- loading;
- field errors shown under the field, e.g. "write at least 20 words…" or "unknown sub-product — choose one of …";
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
- Desktop and mobile frames of the 4 screens and the states above.
- The colour palette and type scale.
- The code, if it can export it (HTML/CSS/JS or React).

---

## Part B — Build contract (for the implementation)

**Site layout** (static, on Vercel):

| page | path | calls |
|---|---|---|
| Home + form + result | `/` | at load: `GET /options/products`, `GET /options/issues`, `GET /options/states` (cache in memory) · while typing: `GET /options/companies?search=` (≥ 2 characters, wait ~250 ms after the last keystroke) · on submit: `POST /predict` |
| Real complaints | `/real` | `GET /complaint/random?paid=true\|false` |
| How it works | `/how` | `GET /model-info` |
| API docs | `/docs` | Swagger UI, forwarded to the API unchanged |

**`vercel.json` rewrites** (a static file wins first, so the site's own pages are never forwarded):
`/predict`, `/complaint/:path*`, `/options/:path*`, `/model-info`, `/health`, `/docs`, `/openapi.json` → the
same path on the AWS server. Plus the secret header (Vercel's `routes` transform), so NGINX accepts only
requests that come through Vercel.

**Request and response shapes:** exactly the API's (`/docs`). `POST /predict` takes
`{company, product, sub_product, issue, state, older_american, servicemember, narrative}` and returns
`{payout_probability, route, senior_threshold, model_version, features_as_of, inputs{19}, text_word_pieces,
text_cut_at_512, notes[], latency_ms}`.

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
- **422:** the message goes under the field it names. Pydantic's error has the field in `loc`; our name-lookup
  errors name the field in `detail`.
- **429:** "Too many requests — wait a few seconds".
- **500 / 502 / 503 / 504:** "The service is having trouble — try again in a minute".
- **Timeout:** abort after 20 s and show the same message.

**Out of scope:** logins, saved history, analytics or tracking scripts.
