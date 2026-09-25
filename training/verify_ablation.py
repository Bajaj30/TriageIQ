"""Reproduce the ablation numbers quoted in TriageIQ.md 2.4 / CLAUDE.md 7.

These numbers existed nowhere in the repo (audit finding T1-1). This script is
the missing artifact. Run: python training/verify_ablation.py
"""
import json, sys
import numpy as np, pandas as pd, pyarrow.parquet as pq
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, average_precision_score

SEED, N_SAMPLE, K = 42, 500_000, 50
NARR = "Consumer complaint narrative"
META = "Data/data/interim/meta.parquet"

def smoothed_rate(tr, frames, key, label, prior, k=K):
    """Target-encode `key` on train only, apply to each frame."""
    g = tr.groupby(key, observed=True)[label].agg(["sum", "size"])
    rate = (g["sum"] + k * prior) / (g["size"] + k)
    out = []
    for f in frames:
        idx = f[key] if isinstance(key, str) else pd.MultiIndex.from_frame(f[key])
        out.append(pd.Series(pd.Index(idx).map(rate)).fillna(prior).values)
    return out

def within_strata_auc(te, y, p, keys=("Product", "Issue"), min_pos=25, min_n=150):
    aucs, wts = [], []
    for _, idx in te.groupby(list(keys), observed=True).indices.items():
        yy = y[idx]
        if yy.sum() < min_pos or yy.sum() == len(yy) or len(yy) < min_n:
            continue
        aucs.append(roc_auc_score(yy, p[idx])); wts.append(len(yy))
    return float(np.average(aucs, weights=np.array(wts, float))), len(aucs)

def within_company_auc(te, y, p, min_pos=20, min_n=200):
    """AUC computed inside each company, volume-weighted. What a single deployed bank sees."""
    aucs, wts = [], []
    for _, idx in te.groupby("Company", observed=True).indices.items():
        yy = y[idx]
        if yy.sum() < min_pos or yy.sum() == len(yy) or len(yy) < min_n:
            continue
        aucs.append(roc_auc_score(yy, p[idx])); wts.append(len(yy))
    return float(np.average(aucs, weights=np.array(wts, float))), len(aucs)

def run(d, tag):
    tr = d[d["Date received"] < "2024-01-01"]
    te = d[d["Date received"] >= "2024-01-01"].reset_index(drop=True)
    ytr, yte = tr.y.values, te.y.values
    print(f"\n### {tag}: train {len(tr):,} / test {len(te):,} / test base {yte.mean():.2%}")

    vec = TfidfVectorizer(max_features=80_000, ngram_range=(1, 2), min_df=5,
                          sublinear_tf=True, strip_accents="unicode")
    Xtr = vec.fit_transform(tr[NARR].astype(str)); Xte = vec.transform(te[NARR].astype(str))

    prior = ytr.mean(); cols = {}
    for key in ["Product", "Issue", "Company", "Sub-product",
                ["Product", "Issue"], ["Company", "Issue"]]:
        nm = key if isinstance(key, str) else "x".join(key)
        cols[nm] = smoothed_rate(tr, [tr, te], key, "y", prior)
    names = list(cols)
    Mtr = np.column_stack([cols[n][0] for n in names] + [tr.n_words.values])
    Mte = np.column_stack([cols[n][1] for n in names] + [te.n_words.values])

    res = {}
    for label, (A, B) in {
        "text":     (Xtr, Xte),
        "metadata": (sparse.csr_matrix(Mtr), sparse.csr_matrix(Mte)),
        "fusion":   (sparse.hstack([Xtr, sparse.csr_matrix(Mtr)]).tocsr(),
                     sparse.hstack([Xte, sparse.csr_matrix(Mte)]).tocsr()),
    }.items():
        p = LogisticRegression(max_iter=800, solver="liblinear").fit(A, ytr).predict_proba(B)[:, 1]
        wa, nstr = within_strata_auc(te, yte, p)
        wc, nco = within_company_auc(te, yte, p)
        res[label] = {"pooled_auc": float(roc_auc_score(yte, p)),
                      "pooled_pr": float(average_precision_score(yte, p)),
                      "within_strata_auc": wa, "n_strata": nstr,
                      "within_company_auc": wc, "n_companies": nco}
        print(f"  {label:<9} pooled AUC {res[label]['pooled_auc']:.4f}  "
              f"PR {res[label]['pooled_pr']:.4f}  within-strata {wa:.4f} ({nstr})  "
              f"within-company {wc:.4f} ({nco})")
    res["_test_base_rate"] = float(yte.mean()); res["_n_train"] = len(tr); res["_n_test"] = len(te)
    return res

if __name__ == "__main__":
    out = {}
    # --- A. the experiment the quoted numbers came from: 500k random sample, all products
    d = pq.read_table(META, columns=["Date received", "Product", "Sub-product", "Issue",
                                     "Company", NARR, "Company response to consumer",
                                     "has_narrative", "n_words"],
                      filters=[("has_narrative", "==", True)]).to_pandas()
    d["Date received"] = pd.to_datetime(d["Date received"])
    d = d[d["Date received"].between("2022-01-01", "2024-12-31")]
    d = d.sample(N_SAMPLE, random_state=SEED).copy()
    d["y"] = (d["Company response to consumer"].astype(str) == "Closed with monetary relief").astype(int)
    out["A_quoted_experiment_500k_raw_sample"] = run(d, "A) 500k raw sample (as originally quoted)")

    # --- B. the same ablation on the SHIPPED v2 artifact
    v2 = pd.read_parquet("Data/data/interim/triageiq_training_v2.parquet")
    v2["Date received"] = pd.to_datetime(v2["Date received"])
    v2 = v2[v2.split.isin(["train", "test"])].copy()
    out["B_shipped_v2_artifact"] = run(v2, "B) shipped v2 artifact (train=case-control, test=natural)")

    json.dump(out, open("training/ablation_results.json", "w"), indent=2)
    print("\nwrote training/ablation_results.json")
