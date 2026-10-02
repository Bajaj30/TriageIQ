"""Where does the fusion model go wrong INSIDE a company? Writes a readable report of its worst misses.

For each complaint in the 2024 test set we know its score and its rank inside its own company (0 = the
company's lowest score, 1 = its highest — the deployment view: one desk, one company's queue).
  missed payouts  = complaints that DID pay but sit near the bottom of their company's queue
  false alarms    = complaints that did NOT pay but sit at the top of their company's queue
Only the 24 companies scored in the within-company AUC (>= 20 payouts, >= 200 complaints).

Run:  python training/error_analysis.py [training/outputs/fusion_distilbert_full]
  ->  training/results/error_analysis_v3.md   (public CFPB text — no personal data beyond what CFPB publishes)
"""
import io, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd

RUN = Path(sys.argv[1] if len(sys.argv) > 1 else "training/outputs/fusion_distilbert_full")
PSQL = ["docker", "exec", "-i", "triageiq-postgres", "psql", "-U", "triageiq", "-d", "triageiq"]
def sql(q: str) -> pd.DataFrame:
    out = subprocess.run(PSQL + ["-c", f"COPY ({q}) TO STDOUT WITH (FORMAT csv, HEADER true)"],
                         check=True, capture_output=True, text=True).stdout
    return pd.read_csv(io.StringIO(out))

d = pd.read_parquet("Data/data/interim/triageiq_training_v3.parquet")
t = d[d.split == "test"].merge(pd.read_parquet(RUN / "test_predictions.parquet"), on="complaint_id")
t = (t.merge(sql("SELECT company_id, company_name FROM dim_company"), on="company_id")
      .merge(sql("SELECT product_id, product_name FROM dim_product"), on="product_id")
      .merge(sql("SELECT issue_id, issue_name FROM dim_issue"), on="issue_id"))

g = t.groupby("company_id").paid.agg(["sum", "size"])
keep = g[(g["sum"] >= 20) & (g["size"] >= 200)].index
t = t[t.company_id.isin(keep)].copy()
t["rank_in_company"] = t.groupby("company_id").logit.rank(pct=True)     # 0 = bottom of the queue, 1 = top

missed = t[t.paid == 1].nsmallest(25, "rank_in_company")
alarms = t[t.paid == 0].nlargest(25, "rank_in_company")

def block(df, title):
    lines = [f"## {title}\n"]
    for _, r in df.iterrows():
        lines.append(f"**{r.company_name}** · {r.product_name} · *{r.issue_name}* · rank in company "
                     f"{r.rank_in_company:.3f} · company×issue rate {r.company_issue_rate_s:.3f} · paid {int(r.paid)}\n")
        lines.append("> " + r.text[:600].replace("\n", " ") + ("…" if len(r.text) > 600 else "") + "\n")
    return lines

# summary: where do missed payouts sit, by issue — are they concentrated?
summ = (t[t.paid == 1].assign(bottom_half=lambda x: x.rank_in_company < 0.5)
        .groupby("issue_name").agg(payouts=("paid", "size"), in_bottom_half=("bottom_half", "sum"))
        .query("payouts >= 20").assign(share=lambda x: x.in_bottom_half / x.payouts)
        .sort_values("share", ascending=False).head(12))

L = ["# Error analysis — DistilBERT fusion, v3 test (2024), inside each company\n",
     f"Run: `{RUN.name}`. {len(t):,} complaints from the {len(keep)} companies scored within-company "
     f"({int(t.paid.sum()):,} payouts). Rank 0 = bottom of that company's queue, 1 = top.\n",
     "## Payouts the model ranks in the bottom half of their company's queue, by issue\n",
     "| issue | payouts | in bottom half | share |\n|---|---|---|---|\n"
     + "\n".join(f"| {i} | {r.payouts} | {int(r.in_bottom_half)} | {r.share:.1%} |" for i, r in summ.iterrows()), "\n"]
L += block(missed, "25 most-missed payouts (paid, but ranked lowest in their company)")
L += block(alarms, "25 strongest false alarms (not paid, but ranked highest in their company)")
Path("training/results/error_analysis_v3.md").write_text("\n".join(L))
print(summ.round(3).to_string())
print(f"\nwrote training/results/error_analysis_v3.md ({len(missed)} missed + {len(alarms)} false alarms)")
