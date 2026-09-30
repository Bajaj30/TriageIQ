"""Single source of truth for every number the project depends on.

Root cause of earlier doc errors: statistics were quoted without pinning WHICH
population they came from, so all-time figures stood in for windowed ones.
There are exactly three populations and they are not interchangeable.

Run:  python training/canonical_facts.py
      -> training/canonical_facts.json, Context/FACTS.md and sql/02_load/00_expected_facts.sql
The SQL file loads every number into Postgres, so 11_validate.sql checks against the SAME numbers.
Baselines are read from training/ablation_results.json (run verify_ablation.py first).
"""
import json
from pathlib import Path
import pandas as pd, pyarrow.parquet as pq

META  = "Data/data/interim/meta.parquet"
TRAIN = "Data/data/interim/triageiq_training_v2.parquet"
ABL   = Path("training/ablation_results.json")
LO, HI = "2022-01-01", "2024-12-31"
LABEL = "Closed with monetary relief"

cols = ["Complaint ID","Date received","Product","Sub-product","Issue","Sub-issue",
        "Company","State","Submitted via","Company response to consumer",
        "Timely response?","Tags","has_narrative","n_words"]
m = pq.read_table(META, columns=cols).to_pandas()
m["Date received"] = pd.to_datetime(m["Date received"])
f1 = m[m["Date received"].between(LO, HI)].copy()          # feature population
f2 = f1[f1.has_narrative]                                   # modeling population
f3 = pd.read_parquet(TRAIN)                                 # training artifact
f3["Date received"] = pd.to_datetime(f3["Date received"])
for c in ["Product","Sub-product","Issue","Sub-issue"]:
    f1[c] = f1[c].astype(object)
yl = lambda d: (d["Company response to consumer"].astype(str) == LABEL)

def stats(d, sv=True):
    y = yl(d)
    o = {"rows": len(d), "positives": int(y.sum()), "base_rate": float(y.mean())}
    for c in ["Product","Sub-product","Issue","Sub-issue","Company","State"]:
        o[f"n_{c}"] = int(d[c].nunique())
    for c in ["Sub-issue","State","Tags"]:
        o[f"null_{c}"] = float(d[c].isna().mean())
    if sv:
        o["n_Submitted_via"] = int(d["Submitted via"].nunique())
        o["timely_yes"] = float((d["Timely response?"].astype(str) == "Yes").mean())
    return o

F = {"F1": stats(f1), "F2": stats(f2), "F3": stats(f3, sv=False)}
ids = pd.to_numeric(f1["Complaint ID"], errors="coerce")
cd = f1.groupby(["Company", f1["Date received"].dt.date], observed=True).size()
F["schema"] = {
    "pk_unique_F1": bool(f1["Complaint ID"].is_unique),
    "id_numeric": bool(ids.notna().all()), "id_min": int(ids.min()), "id_max": int(ids.max()),
    "company_days": int(len(cd)), "company_day_multi": float((cd > 1).mean()),
    "company_day_max": int(cd.max()),
    "date_min": str(f1["Date received"].min().date()), "date_max": str(f1["Date received"].max().date()),
    "null_response_F1": int(f1["Company response to consumer"].isna().sum()),
}
F["no_narrative"] = {"rows": len(f1) - len(f2),
                     "positives": int(yl(f1).sum() - yl(f2).sum()),
                     "share_of_all_positives": float((yl(f1).sum() - yl(f2).sum()) / yl(f1).sum())}
F["submitted_via_F1"] = {k: int(v) for k, v in f1["Submitted via"].value_counts().items() if v}

def hier(parent, child):
    x = f1[[parent, child]].dropna().drop_duplicates()
    per = x.groupby(child)[parent].nunique(); multi = per[per > 1]
    return {"n_children": int(len(per)), "multi_parent": int(len(multi)),
            "rows_affected_share": float(f1[child].isin(multi.index).mean()),
            "null_child_rows": int(f1[child].isna().sum())}
F["hierarchy"] = {"sub_product_under_product": hier("Product", "Sub-product"),
                  "sub_issue_under_issue": hier("Issue", "Sub-issue"),
                  "issue_under_product": hier("Product", "Issue")}
pr = f1.groupby("Product")["Date received"].agg(["min", "max", "size"]).sort_values("min")
F["product_date_ranges"] = {p: {"from": str(r["min"].date()), "to": str(r["max"].date()),
                                "rows": int(r["size"])} for p, r in pr.iterrows()}
F["base_rate_by_year_F2"] = {int(k): round(float(v), 4) for k, v in
                             yl(f2).groupby(f2["Date received"].dt.year).mean().items()}
F["splits_F3"] = {s: {"rows": int(len(g)), "positives": int(g.y.sum()), "rate": float(g.y.mean()),
                      "from": str(g["Date received"].min().date()), "to": str(g["Date received"].max().date())}
                  for s, g in f3.groupby("split")}
F["baselines"] = json.loads(ABL.read_text()) if ABL.exists() else None

# ------------------------------------------------ load expectations (independent of the SQL load)
# A SECOND implementation of the load rules, in pandas. sql/02_load must agree with it: if a crosswalk
# rule changes in only one place, 11_validate.sql FAILS — on purpose, so the change is deliberate.
PX = {  # (raw product, raw sub-product; None = any) -> canonical — mirrors sql/01_schema/02_product_crosswalk.sql
    ("Credit card or prepaid card", "General-purpose credit card or charge card"): "Credit card",
    ("Credit card or prepaid card", "Store credit card"): "Credit card",
    ("Credit card or prepaid card", "General-purpose prepaid card"): "Prepaid card",
    ("Credit card or prepaid card", "Government benefit card"): "Prepaid card",
    ("Credit card or prepaid card", "Gift card"): "Prepaid card",
    ("Credit card or prepaid card", "Payroll card"): "Prepaid card",
    ("Credit card or prepaid card", "Student prepaid card"): "Prepaid card",
    ("Credit reporting, credit repair services, or other personal consumer reports", "Credit reporting"):
        "Credit reporting or other personal consumer reports",
    ("Credit reporting, credit repair services, or other personal consumer reports", "Other personal consumer report"):
        "Credit reporting or other personal consumer reports",
    ("Credit reporting, credit repair services, or other personal consumer reports", "Credit repair services"):
        "Debt or credit management",
    ("Payday loan, title loan, or personal loan", None): "Payday loan, title loan, personal loan, or advance loan",
    ("Money transfer, virtual currency, or money service", "Debt settlement"): "Debt or credit management",
}
IX = {  # raw issue -> canonical — mirrors sql/01_schema/06_issue_crosswalk.sql
    "Problem with a credit reporting company's investigation into an existing problem":
        "Problem with a company's investigation into an existing problem",
}
NS = "(not specified)"
g = f1[["Product", "Sub-product", "Issue", "Sub-issue", "Company", "State"]].astype(object)
cp = pd.Series([PX.get((p, sp), PX.get((p, None), p)) for p, sp in zip(g["Product"], g["Sub-product"])],
               index=g.index)
ci = g["Issue"].map(lambda i: IX.get(i, i))
resp = f1["Company response to consumer"].astype(object)
F["load"] = {
    "events": 3 * len(f1),                                         # received + sent + responded
    "untimely": int((resp == "Untimely response").sum()),
    "products_rerouted": int((cp != g["Product"]).sum()),
    "issues_rerouted": int((g["Issue"].notna() & (ci != g["Issue"])).sum()),
    "dim_company": int(g["Company"].str.lower().nunique()),        # case-only duplicates merge
    "dim_state": int(g["State"].fillna(NS).nunique()),
    "dim_product": int(cp.nunique()),
    "dim_sub_product": int(pd.DataFrame({"p": cp, "s": g["Sub-product"].fillna(NS)}).drop_duplicates().shape[0]),
    "dim_issue": int(ci.fillna(NS).nunique()),
    "dim_sub_issue": int(pd.DataFrame({"i": ci.fillna(NS), "s": g["Sub-issue"].fillna(NS)}).drop_duplicates().shape[0]),
}
Path("training/canonical_facts.json").write_text(json.dumps(F, indent=2))

# ---------------------------------------------------------------- render FACTS.md
pc = lambda x: f"{x*100:.2f}%"
a, b, c, s, h = F["F1"], F["F2"], F["F3"], F["schema"], F["hierarchy"]
L = []; w = L.append
w("# TriageIQ — Canonical Facts\n")
w("**Generated by `training/canonical_facts.py`. Do not hand-edit — re-run it.**")
w("Every number in every other document must match this file. If they disagree, this file wins.\n")
w("## The three populations — always state which one a number comes from\n")
w("| frame | what it is | rows |\n|---|---|---|")
w(f"| **F1 — feature population** | every complaint in the window. Loaded into Postgres; aggregates computed here | **{a['rows']:,}** |")
w(f"| **F2 — modeling population** | F1 rows that have a narrative. Only these can be training rows | **{b['rows']:,}** |")
w(f"| **F3 — training artifact** | the shipped sampled parquet (train / val / test) | **{c['rows']:,}** |\n")
w(f"Window {s['date_min']} .. {s['date_max']} · label `Company response to consumer == '{LABEL}'`\n")
w("## Label counts\n\n| frame | rows | positives | base rate |\n|---|---|---|---|")
w(f"| F1 | {a['rows']:,} | {a['positives']:,} | {pc(a['base_rate'])} |")
w(f"| F2 | {b['rows']:,} | {b['positives']:,} | {pc(b['base_rate'])} |")
w(f"| F3 | {c['rows']:,} | {c['positives']:,} | mixed — use the split table below |\n")
nn = F["no_narrative"]
w(f"**Why F1 keeps the {nn['rows']:,} rows with no narrative:** they hold **{nn['positives']:,} payout "
  f"outcomes — {nn['share_of_all_positives']:.0%} of all positives.** Company-level relief rates computed "
  "without them are biased by a different amount for every company.\n")
w("Base rate by year (F2): " + " · ".join(f"{k} {v*100:.2f}%" for k, v in F["base_rate_by_year_F2"].items())
  + " — **test is genuinely harder than train.**\n")
w("## Cardinality — size the DDL from F1\n\n| field | F1 | F2 | F3 |\n|---|---|---|---|")
for fld in ["Product","Sub-product","Issue","Sub-issue","Company","State"]:
    w(f"| {fld} | **{a['n_'+fld]:,}** | {b['n_'+fld]:,} | {c['n_'+fld]:,} |")
w("\n> 21 / 85 / 173 / 266 / 63 are **all-time** values. Never use them for this project.\n")
w("## Null rates\n\n| field | F1 | F2 | F3 |\n|---|---|---|---|")
for fld in ["Sub-issue","State","Tags"]:
    w(f"| {fld} | {pc(a['null_'+fld])} | {pc(b['null_'+fld])} | {pc(c['null_'+fld])} |")
w("\n## Hierarchies — children repeat across parents\n")
w("| child under parent | distinct children | under >1 parent | F1 rows affected | NULL child rows |\n|---|---|---|---|---|")
for k, lbl in [("sub_product_under_product","Sub-product under Product"),
               ("sub_issue_under_issue","Sub-issue under Issue"),
               ("issue_under_product","Issue under Product")]:
    x = h[k]
    w(f"| {lbl} | {x['n_children']} | {x['multi_parent']} | {pc(x['rows_affected_share'])} | {x['null_child_rows']:,} |")
w("\nConsequence: a child dimension must be **unique on (parent_id, child_name)**, never on the name "
  "alone. Issue is **not** a child of Product — they are independent dimensions.\n")
w("## Product name date ranges — renames and splits\n\n| product | first seen | last seen | rows |\n|---|---|---|---|")
for p, r in F["product_date_ranges"].items():
    w(f"| {p} | {r['from']} | {r['to']} | {r['rows']:,} |")
w("\nA product that stops on the day another starts is a **rename**, and must map to one canonical "
  "`product_id` — otherwise every product-level feature resets to zero history mid-window.\n")
w("## Schema-critical facts\n")
w(f"- `Complaint ID` unique across F1: **{s['pk_unique_F1']}**; all numeric: **{s['id_numeric']}**; "
  f"range {s['id_min']:,} .. {s['id_max']:,} → **BIGINT** (text sort ≠ numeric sort)")
w(f"- Company-days: {s['company_days']:,}; **{pc(s['company_day_multi'])} hold >1 complaint**; "
  f"max **{s['company_day_max']:,}** in one company-day")
w(f"- NULL `Company response to consumer` in F1: **{s['null_response_F1']}** — unknown; **label 0** (decided 2026-09-29 — the shipped training set already does this)")
w(f"- `Submitted via`: 1 value in F2, **{a['n_Submitted_via']} in F1** — "
  + ", ".join(f"{k} {v:,}" for k, v in F["submitted_via_F1"].items()) + "\n")
ld = F["load"]
w("## Load expectations — what the SQL load must produce (F1, after the crosswalks)\n")
w("Computed here in pandas, independently of the SQL load; `sql/02_load/11_validate.sql` checks against them.\n")
w("| fact | value |\n|---|---|")
for k, v in ld.items():
    w(f"| `load.{k}` | {v:,} |")
w("")
sp = F["splits_F3"]
w("## Splits (F3)\n\n| split | period | rows | positives | rate | sampling |\n|---|---|---|---|---|---|")
for k, samp in [("train","case-control, ALL positives kept"),("val","natural"),("test","natural")]:
    x = sp[k]
    w(f"| {k} | {x['from']} .. {x['to']} | {x['rows']:,} | {x['positives']:,} | {pc(x['rate'])} | {samp} |")
w("\nNegative keep-fraction in train **0.104639** → recalibrate with logit offset **−2.2572**.\n")
w("## Baselines — measured on F3, the data that actually ships\n")
if F["baselines"]:
    B = F["baselines"]["B_shipped_v2_artifact"]
    w("Reproduce with `training/verify_ablation.py` (TF-IDF + logistic regression).\n")
    w("| model | pooled AUC | pooled PR | within (Product×Issue) AUC | within-company AUC |\n|---|---|---|---|---|")
    for mdl in ["text","metadata","fusion"]:
        x = B[mdl]; bold = "**" if mdl == "fusion" else ""
        w(f"| {bold}{mdl}{bold} | {x['pooled_auc']:.4f} | {x['pooled_pr']:.4f} | {x['within_strata_auc']:.4f} | "
          + (f"{x['within_company_auc']:.4f}" if "within_company_auc" in x else "—") + " |")
    w(f"\nTest base rate {B['_test_base_rate']*100:.2f}% · {B['_n_train']:,} train / {B['_n_test']:,} test rows.\n")
    w("Three numbers, three different claims: **pooled** is flattered by between-company and "
      "between-product differences; **within-strata** holds product and issue fixed; **within-company** is "
      "what a single bank triaging its own queue would actually experience. Report the honest one.\n")
    w("> The metadata branch is depressed on F3 because target encoding was fitted on "
      "case-control-resampled train data (25% positive vs ~3.4%). **Entity rates must be computed over F1 "
      "in Postgres, never over resampled training rows.**")
Path("Context/FACTS.md").write_text("\n".join(L) + "\n")

# ---------------------------------------------------------------- render the SQL seed
def leaves(o, prefix=""):
    """Every NUMERIC leaf of the JSON as (dotted key, value). Booleans and strings are skipped."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield prefix, o
rows = sorted(leaves(F))
q = lambda t: t.replace("'", "''")
sql = ["-- GENERATED by training/canonical_facts.py from training/canonical_facts.json — DO NOT HAND-EDIT.",
       "-- Re-generate:  python training/canonical_facts.py",
       "-- ============================================================",
       "-- 02_load/00_expected_facts.sql",
       "-- TARGET  : table expected_facts  +  function expected(fact)",
       "-- PURPOSE : ONE source for every expected number. 11_validate.sql reads its expectations from here,",
       "--           so Context/FACTS.md and the SQL checks can never disagree.",
       "-- USE     : SELECT expected('F1.rows');   -- keys are the JSON paths, e.g. 'load.dim_company'",
       "--           A missing key returns NULL, which 11_validate shows as FAIL — never a silent PASS.",
       "-- ============================================================",
       "DROP TABLE IF EXISTS expected_facts;",
       "CREATE TABLE expected_facts (",
       "    fact   TEXT    PRIMARY KEY,",
       "    value  NUMERIC NOT NULL",
       ");",
       "INSERT INTO expected_facts (fact, value) VALUES",
       ",\n".join(f" ('{q(k)}', {v!r})" for k, v in rows) + ";",
       "",
       "CREATE OR REPLACE FUNCTION expected(k TEXT) RETURNS NUMERIC",
       "LANGUAGE sql STABLE AS $$ SELECT value FROM expected_facts WHERE fact = k $$;",
       "",
       f"-- sanity: expect {len(rows)} facts",
       "SELECT count(*) AS facts FROM expected_facts;",
       ""]
Path("sql/02_load/00_expected_facts.sql").write_text("\n".join(sql))
print(f"wrote training/canonical_facts.json, Context/FACTS.md and sql/02_load/00_expected_facts.sql ({len(rows)} facts)")
