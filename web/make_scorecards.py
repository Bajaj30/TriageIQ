"""Build the "Production score cards for SQL features" on the How it works page  ->  web/scorecards.js

For two REAL 2024 complaints (the test set the model never saw) — one the company paid, one it didn't — it shows
the 19 numbers the model read next to the text, each with a plain-language reading.

  values  : from PRODUCTION — GET https://triageiq-mu.vercel.app/complaint/{id} (the live API)
  counts  : from the full local database (docker compose up -d; port 5433): the raw counts behind each value
            (payouts out of complaints, last-90-day counts), recounted with plain WHERE clauses
  check   : every rate and share is recomputed from those counts and must equal the live value (else it stops).
            This is a check only — the model's inputs are computed in SQL (ground rule 4), never here.
  score   : how the score was made, with the PRODUCTION scoring code (api/scorer.py, api/xai.py) and model files
            (training/outputs/serving_v3/):
              where it came from — Shapley factors ("Why this score?"): typical complaint x factors = final
              the final calculation — raw model output -> calibration -> chance -> route
            Checked: the chance equals the live one, and the factors multiply out to it exactly.

Run from the repo root (needs onnxruntime + tokenizers, i.e. the API's venv):
    .venv-api/bin/python web/make_scorecards.py        (then reload /how)
"""
import json, math, subprocess, sys, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api.scorer import Scorer                       # noqa: E402 — the production scoring code
from api.xai import Explainer, GROUPS, WORDS        # noqa: E402
MODEL = Scorer(ROOT / "training/outputs/serving_v3", threads=4)
EXPLAIN = Explainer(ROOT / "training/outputs/serving_v3", MODEL, 4, batch=8)

LIVE = "https://triageiq-mu.vercel.app"
IDS = {"paid": 9307696, "not_paid": 9628925}     # same product + issue (Checking or savings account · Managing an
                                                  # account), both called right by the model; different companies
OUT = Path(__file__).resolve().parent / "scorecards.js"
PSQL = ["docker", "exec", "-i", "triageiq-postgres", "psql", "-U", "triageiq", "-d", "triageiq", "-At", "-F", "\t"]


def live(cid: int) -> dict:
    with urllib.request.urlopen(f"{LIVE}/complaint/{cid}", timeout=60) as r:
        return json.load(r)


def counts(cid: int) -> dict:
    """Raw counts as of the day the complaint arrived — the training frames (CLAUDE.md trap 1):
    outcomes = complaints received on or before day - 60 · volume = day - 90 .. day - 1 · trend = the 90 before."""
    sql = f"""
    WITH x AS (SELECT * FROM mv_features WHERE complaint_id = {cid}),
    o AS (SELECT b.* FROM v_base b, x WHERE b.date_received <= x.date_received - 60)
    SELECT x.date_received, x.company_n_known, x.company_issue_n_known, x.issue_n_known, x.product_n_known,
           (SELECT coalesce(sum(paid), 0)     FROM o WHERE o.company_id = x.company_id),
           (SELECT coalesce(sum(untimely), 0) FROM o WHERE o.company_id = x.company_id),
           (SELECT coalesce(sum(paid), 0)     FROM o WHERE o.company_id = x.company_id AND o.issue_id = x.issue_id),
           (SELECT coalesce(sum(paid), 0)     FROM o WHERE o.issue_id = x.issue_id),
           (SELECT coalesce(sum(paid), 0)     FROM o WHERE o.product_id = x.product_id),
           x.company_n_90d, x.company_issue_n_90d, x.issue_n_90d, x.national_n_90d,
           x.company_n_prev_90d, x.issue_n_prev_90d, x.company_quiet_days,
           x.product_id, x.sub_product_id, x.issue_id, x.state_id, x.is_older_american, x.is_servicemember,
           (SELECT value FROM feature_params WHERE param = 'k'),
           (SELECT value FROM feature_params WHERE param = 'fallback_prior')
    FROM x;"""
    row = subprocess.run(PSQL + ["-c", "SET max_parallel_workers_per_gather = 0;" + sql], check=True,
                         capture_output=True, text=True).stdout.strip().splitlines()[-1].split("\t")
    keys = ["day", "co_n", "ci_n", "i_n", "p_n", "co_pay", "co_untimely", "ci_pay", "i_pay", "p_pay",
            "co_90", "ci_90", "i_90", "nat_90", "co_prev", "i_prev", "quiet",
            "product_id", "sub_product_id", "issue_id", "state_id", "is_older_american", "is_servicemember",
            "k", "fallback"]
    c = dict(zip(keys, row))
    return {k: (date.fromisoformat(v) if k == "day" else float(v) if k == "fallback" else int(float(v)))
            for k, v in c.items()}


def check(inp: dict, c: dict):
    """Recompute from the counts with the training formulas; every one must match the live value."""
    k = c["k"]
    prior = (c["p_pay"] + k * c["fallback"]) / (c["p_n"] + k)
    want = {
        "product_rate_s": prior,
        "company_rate_s": (c["co_pay"] + k * prior) / (c["co_n"] + k),
        "company_issue_rate_s": (c["ci_pay"] + k * prior) / (c["ci_n"] + k),
        "issue_rate_s": (c["i_pay"] + k * prior) / (c["i_n"] + k),
        "company_untimely_rate": c["co_untimely"] / c["co_n"] if c["co_n"] else 0,
        "company_share_90d": c["co_90"] / c["nat_90"],
        "company_issue_share_90d": c["ci_90"] / c["nat_90"],
        "issue_share_90d": c["i_90"] / c["nat_90"],
        "company_trend_90d": math.log((c["co_90"] + 1) / (c["co_prev"] + 1)),
        "issue_trend_90d": math.log((c["i_90"] + 1) / (c["i_prev"] + 1)),
    }
    want |= {"company_no_history": int(c["co_n"] == 0), "company_issue_no_history": int(c["ci_n"] == 0),
             "company_quiet_days": c["quiet"]}
    want |= {k2: c[k2] for k2 in ("product_id", "sub_product_id", "issue_id", "state_id",
                                   "is_older_american", "is_servicemember")}
    assert set(want) == set(inp), f"inputs not all checked: {set(inp) ^ set(want)}"
    for name, v in want.items():
        assert abs(v - inp[name]) < 2e-6, f"{name}: recount {v} != live {inp[name]}"


# ---------------------------------------------------------------- plain-language readings
def n(x) -> str:
    return f"{x:,}"


def pct(r: float) -> str:
    v = r * 100
    if v == 0: return "0%"
    if v >= 1: return f"{v:.1f}%"
    if v >= 0.1: return f"{v:.2f}%"
    return f"{v:.2g}%"


def one_in(part: int, whole: int) -> str:
    if part == 0: return "never"
    r = part / whole
    if r >= 0.45: return "about half the time"
    return f"about 1 in {n(round(whole / part))}"


def change(now: int, before: int) -> str:
    x = (now + 1) / (before + 1)
    if abs(x - 1) < 0.02: return "about level"
    return f"about {round((x - 1) * 100)}% more" if x > 1 else f"about {round((1 - x) * 100)}% fewer"


def day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def odds_text(x: float) -> str:
    if abs(x - 1) < 0.02: return "Leaves the odds of a payout about the same."
    return f"Raises the odds of a payout {x:.1f}×." if x > 1 else f"Lowers the odds of a payout to {x:.2f}×."


def score_rows(a: dict) -> tuple[list, list]:
    """Step 1: where the score came from (Shapley factors). Step 2: the final calculation (logit -> chance -> route)."""
    cal = MODEL.cal
    s = MODEL.score(a["narrative"], a["inputs"])
    p = s["probability"]
    assert abs(p - a["payout_probability"]) < 5e-4, f"local {p} != live {a['payout_probability']}"
    r = EXPLAIN.explain(a["narrative"], a["inputs"])
    assert max(r["checks"].values()) < 1e-4, r["checks"]
    f = {x["name"]: x["odds_factor"] for x in r["factors"]}
    assert set(f) == {WORDS} | {g for g, _ in GROUPS}
    typ = r["typical_probability"]
    total = typ / (1 - typ) * math.prod(f.values())
    assert abs(total / (1 + total) - p) < 1e-6, "factors don't multiply out to the score"
    main = [
        (WORDS, "The complaint's words, read by DistilBERT"),
        ("This company's record on this kind of problem", "Company's record on this problem"),
        ("This company's record overall", "Company's record overall"),
        ("How busy this company has been lately", "How busy the company has been lately"),
        ("How common this kind of problem is lately", "How common this problem is lately"),
    ]
    what = {
        WORDS: "what the language model read in the complaint.",
        "This company's record on this kind of problem": "its payout rate on this kind of problem.",
        "This company's record overall": "its payout rate across all problems.",
        "How busy this company has been lately": "its share of complaints, its trend, days since its last complaint.",
        "How common this kind of problem is lately": "this problem's share of complaints and its trend.",
    }
    rest = [g for g, _ in GROUPS if g not in dict(main)]
    rest_f = math.prod(f[g] for g in rest)
    split = [["A typical complaint (the starting point)", pct(typ),
              "The model's score for an average complaint: 100 real ones from Oct–Dec 2023, mostly credit-report "
              "disputes, which almost never pay."]]
    split += [[label, f"×{f[g]:.1f}", f"{odds_text(f[g])} From {what[g]}"] for g, label in main]
    split += [["Everything else, together", f"×{rest_f:.1f}",
               f"{odds_text(rest_f)} From the product and the kind of problem (with their payout rates), the state, "
               "the two tick-boxes and the never-answered rate."]]
    split += [["= Chance of a payout", pct(p), "The starting odds multiplied by every factor above.", True]]

    lg, off, A, B = s["logit"], cal["offset"], cal["a"], cal["b"]
    z = lg + off
    y = A * z + B
    senior = p >= cal["senior_threshold_p"]
    line = f"{cal['senior_threshold_p'] * 100:.2f}%"
    num = lambda x: f"{x:.3f}".replace("-", "−")                 # a real minus sign
    par = lambda x: f"({num(x)})" if x < 0 else num(x)          # brackets around a negative inside a formula
    calc = [
        ["Model's raw output (logit)", num(lg),
         "One number from the model's last layer, where the words and the 19 inputs meet. Not a percentage yet."],
        ["Undo the training mix", f"{num(lg)} − {-off:.4f} = {num(z)}",
         "Training saw 1 payout in every 4 complaints, far more than real life. This puts the odds back."],
        ["Re-tune to 2024", f"{par(z)} × {A:.4f} − {-B:.4f} = {num(y)}",
         "Two numbers fitted on Jul–Dec 2024 complaints, when payouts were rarer than in training."],
        ["Turn into a chance", f"sigmoid({num(y)}) = {pct(p)}",
         "sigmoid(x) = 1 ÷ (1 + e^−x) turns any number into a chance between 0% and 100%."],
        ["Route", "Senior analyst" if senior else "Template reply",
         (f"{pct(p)} is above the senior line of {line}: the riskiest 10% of 2024 complaints go to a senior analyst."
          if senior else f"{pct(p)} is below the senior line of {line}, so it gets a template reply."), True],
    ]
    return split, calc


def card(kind: str, cid: int) -> dict:
    a, c = live(cid), counts(cid)
    inp = a["inputs"]
    check(inp, c)
    split, calc = score_rows(a)
    d = c["day"]
    known_by, v_from, v_to = d - timedelta(days=60), d - timedelta(days=90), d - timedelta(days=1)
    yes = lambda v: "Yes" if v else "No"
    form = [
        ["Product", a["product"], "What the complaint is about."],
        ["Sub-product", a["sub_product"], "The finer category, as chosen on the form."],
        ["Issue", a["issue"], "The kind of problem the consumer picked."],
        ["State", a["state"], "Where the consumer lives — a weak clue on its own."],
        ["Older American (62+)", yes(inp["is_older_american"]),
         "Ticked on the form." if inp["is_older_american"] else
         "Not ticked. Complaints with this box ticked end in a payout about 10 times as often."],
        ["Servicemember", yes(inp["is_servicemember"]),
         "Ticked on the form." if inp["is_servicemember"] else
         "Not ticked. Complaints with this box ticked end in a payout about twice as often."],
    ]
    rec = [
        ["Company is new (no track record)", yes(inp["company_no_history"]),
         f"It has a track record: {n(c['co_n'])} of its complaints already had a known outcome by {day(known_by)}."
         if c["co_n"] else "None of its complaints had a known outcome yet — the model leans on the product's rate."],
        ["New to this kind of problem", yes(inp["company_issue_no_history"]),
         f"It had handled {n(c['ci_n'])} complaints of this kind before." if c["ci_n"] else
         "Its first known complaint of this kind — the model leans on the product's rate."],
        ["Company's payout rate on this problem", pct(inp["company_issue_rate_s"]),
         f"It paid on {n(c['ci_pay'])} of {n(c['ci_n'])} complaints like this — {one_in(c['ci_pay'], c['ci_n'])}. "
         "The most specific record: this company, this problem."],
        ["Company's payout rate, all problems", pct(inp["company_rate_s"]),
         f"It paid on {n(c['co_pay'])} of {n(c['co_n'])} of all its complaints — {one_in(c['co_pay'], c['co_n'])}."],
        ["Payout rate for this problem, all companies", pct(inp["issue_rate_s"]),
         f"Across every company, complaints about “{a['issue']}” were paid {n(c['i_pay'])} times out of "
         f"{n(c['i_n'])} — {one_in(c['i_pay'], c['i_n'])}."],
        ["Payout rate for this product", pct(inp["product_rate_s"]),
         f"All “{a['product']}” complaints: {n(c['p_pay'])} paid out of {n(c['p_n'])} — "
         f"{one_in(c['p_pay'], c['p_n'])}. The default the rates above lean on when a record is small."],
        ["Complaints the company never answered", pct(inp["company_untimely_rate"]),
         f"It answered all {n(c['co_n'])}." if c["co_untimely"] == 0 else
         f"It never answered {n(c['co_untimely'])} of {n(c['co_n'])}."],
        ["Company's share of all complaints", pct(inp["company_share_90d"]),
         f"{n(c['co_90'])} of the {n(c['nat_90'])} complaints filed nationwide from {day(v_from)} to {day(v_to)} "
         f"were about this company — {one_in(c['co_90'], c['nat_90'])}."],
        ["Share for this company on this problem", pct(inp["company_issue_share_90d"]),
         f"{n(c['ci_90'])} complaints about this company on this problem in those 90 days."],
        ["Share for this problem, all companies", pct(inp["issue_share_90d"]),
         f"{n(c['i_90'])} complaints on this problem nationwide in those 90 days — {one_in(c['i_90'], c['nat_90'])}."],
        ["Company's complaint trend", f"{inp['company_trend_90d']:+.3f}",
         f"{n(c['co_90'])} complaints in the last 90 days vs {n(c['co_prev'])} in the 90 before — "
         f"{change(c['co_90'], c['co_prev'])}."],
        ["Trend for this problem, all companies", f"{inp['issue_trend_90d']:+.3f}",
         f"{n(c['i_90'])} vs {n(c['i_prev'])} — {change(c['i_90'], c['i_prev'])}."],
        ["Days since the company's previous complaint", str(round(inp["company_quiet_days"])),
         "Another complaint about this company had already arrived that same day." if inp["company_quiet_days"] == 0
         else f"Its previous complaint arrived {round(inp['company_quiet_days'])} day(s) earlier."],
    ]
    paid, senior = a["actually_paid"], a["route"] == "senior analyst"
    stamp = {(True, True): "Caught", (True, False): "Missed", (False, True): "False alarm", (False, False): "Right call"}
    return {"kind": kind, "complaint_id": cid, "received": day(d), "known_by": day(known_by),
            "company": a["company"], "product": a["product"], "sub_product": a["sub_product"], "issue": a["issue"],
            "state": a["state"], "narrative": a["narrative"], "probability": a["payout_probability"],
            "route": a["route"], "what_happened": a["what_actually_happened"], "paid": paid,
            "stamp": stamp[(paid, senior)], "form": form, "record": rec, "split": split, "calc": calc}


cards = [card(kind, cid) for kind, cid in IDS.items()]
OUT.write_text("/* GENERATED by web/make_scorecards.py from the live API + the full database — don't hand-edit.\n"
               "   Production score cards for the SQL features (How it works page). */\n"
               f"window.SCORECARDS = {json.dumps(cards, indent=1, ensure_ascii=False)};\n")
for c in cards:
    print(f"{c['kind']:<9} {c['complaint_id']}  {c['company'][:28]:<28} p={c['probability']:.4f}  {c['route']:<17} "
          f"{c['what_happened']}  -> {c['stamp']}   (19 inputs = recount; score = live; factors multiply out)")
print("wrote", OUT)
