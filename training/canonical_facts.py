"""Single source of truth for every number the project depends on.

Root cause of prior doc errors: statistics were quoted without pinning WHICH
population they came from. There are exactly three, and they are not interchangeable.
Run: python training/canonical_facts.py  -> writes Context/FACTS.md
"""
import json
import pandas as pd, numpy as np, pyarrow.parquet as pq

META = "Data/data/interim/meta.parquet"
TRAIN = "Data/data/interim/triageiq_training_v2.parquet"
LO, HI = "2022-01-01", "2024-12-31"
NARR = "Consumer complaint narrative"
LABEL = "Closed with monetary relief"
F = {}

cols = ["Complaint ID","Date received","Product","Sub-product","Issue","Sub-issue",
        "Company","State","Submitted via","Company response to consumer",
        "Timely response?","Tags","has_narrative","n_words"]
m = pq.read_table(META, columns=cols).to_pandas()
m["Date received"] = pd.to_datetime(m["Date received"])

# ---- F1: FEATURE population — what gets loaded into Postgres ----
f1 = m[m["Date received"].between(LO, HI)]
# ---- F2: MODELING population — narrative rows in window (pre quality filters) ----
f2 = f1[f1.has_narrative]
# ---- F3: TRAINING artifact — the shipped parquet ----
f3 = pd.read_parquet(TRAIN)

def stats(d, name, has_sv=True):
    y = (d["Company response to consumer"].astype(str) == LABEL)
    o = {"rows": len(d), "positives": int(y.sum()), "base_rate": float(y.mean())}
    for c in ["Product","Sub-product","Issue","Sub-issue","Company","State"]:
        o[f"n_{c}"] = int(d[c].nunique())
    for c in ["Sub-issue","State","Tags"]:
        o[f"null_{c}"] = float(d[c].isna().mean())
    if has_sv:
        o["n_Submitted_via"] = int(d["Submitted via"].nunique())
        o["timely_yes"] = float((d["Timely response?"].astype(str) == "Yes").mean())
    return o

F["F1_feature_population"] = stats(f1, "F1")
F["F2_modeling_population"] = stats(f2, "F2")
F["F3_training_artifact"] = stats(f3, "F3", has_sv=False)

# ---- schema-critical facts ----
ids = pd.to_numeric(f1["Complaint ID"], errors="coerce")
cd = f1.groupby(["Company", f1["Date received"].dt.date], observed=True).size()
F["schema"] = {
    "pk_unique_in_F1": bool(f1["Complaint ID"].is_unique),
    "complaint_id_all_numeric": bool(ids.notna().all()),
    "complaint_id_min": int(ids.min()), "complaint_id_max": int(ids.max()),
    "company_day_groups": int(len(cd)),
    "company_day_multi_share": float((cd > 1).mean()),
    "company_day_max": int(cd.max()),
    "date_min": str(f1["Date received"].min().date()),
    "date_max": str(f1["Date received"].max().date()),
    "null_response_rows_F1": int(f1["Company response to consumer"].isna().sum()),
}
# submitted-via breakdown (the column whose verdict flipped by frame)
F["submitted_via_F1"] = {k: int(v) for k, v in f1["Submitted via"].value_counts().items()}
F["submitted_via_F2"] = {k: int(v) for k, v in f2["Submitted via"].value_counts().items() if v}
# label distribution
F["response_values_F1"] = {k: int(v) for k, v in f1["Company response to consumer"].value_counts(dropna=False).items()}
# base-rate drift
F["base_rate_by_year_F2"] = {int(k): round(float(v), 4) for k, v in
    f2.assign(y=(f2["Company response to consumer"].astype(str) == LABEL)).groupby(f2["Date received"].dt.year)["y"].mean().items()}
# split summary
f3["Date received"] = pd.to_datetime(f3["Date received"])
F["splits_F3"] = {s: {"rows": int(len(g)), "positives": int(g.y.sum()),
                      "rate": round(float(g.y.mean()), 4),
                      "from": str(g["Date received"].min().date()),
                      "to": str(g["Date received"].max().date())}
                  for s, g in f3.groupby("split")}
print(json.dumps(F, indent=2)[:600])
json.dump(F, open("training/canonical_facts.json", "w"), indent=2)
print("\n-> training/canonical_facts.json")
