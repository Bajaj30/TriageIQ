"""Summarise a Kaggle fusion run into a small, tracked results file.

Reads (git-ignored, downloaded from Kaggle or made on the Mac):
  training/outputs/<run>/metrics.json           written by fusion_distilbert.ipynb
  training/outputs/<run>/test_predictions.parquet
  Data/data/interim/triageiq_training_v3.parquet for the true labels
Writes (tracked):  training/results/<run>_v3.json  -> rendered into Context/FACTS.md (the ablation table)

Run:  python training/evaluate_fusion.py training/outputs/text_distilbert_full     (one run)
      python training/evaluate_fusion.py                                          (every run folder)
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

def within_company_ci(t, reps=1000, seed=42):
    """95% range of the within-company AUC: resample complaints inside each company (with replacement),
    recompute the volume-weighted average, 1,000 times. Same company rule as everywhere: >= 20 payouts,
    >= 200 complaints. A gap between two runs smaller than these ranges may be luck."""
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)
    groups = [(g.paid.values, g.logit.values) for _, g in t.groupby("company_id")
              if g.paid.sum() >= 20 and g.paid.sum() < len(g) and len(g) >= 200]
    w = np.array([len(y) for y, _ in groups], float)
    stats = []
    for _ in range(reps):
        a = []
        for y, s in groups:
            i = rng.integers(0, len(y), len(y))
            a.append(roc_auc_score(y[i], s[i]) if 0 < y[i].sum() < len(i) else np.nan)
        a = np.array(a); ok = ~np.isnan(a)
        stats.append(np.average(a[ok], weights=w[ok]))
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))

def summarise(RUN: Path):
    m = json.loads((RUN / "metrics.json").read_text())
    p = pd.read_parquet(RUN / "test_predictions.parquet")
    d = pd.read_parquet("Data/data/interim/triageiq_training_v3.parquet", columns=["complaint_id", "split", "paid", "company_id"])
    t = d[d.split == "test"].merge(p, on="complaint_id", how="inner")
    assert len(t) == len(d[d.split == "test"]) == len(p), "predictions do not cover the test set exactly"

    y, order = t.paid.values, np.argsort(-t.logit.values)
    recall_at = {f"top_{int(s * 100)}pct": float(y[order[:int(len(y) * s)]].sum() / y.sum()) for s in (0.05, 0.10, 0.20)}

    lo, hi = within_company_ci(t)
    out = {"within_company_ci95": [lo, hi], "run": m["run"], "cfg": m["cfg"], "history": m["history"], "test": m["test"], "recall_at": recall_at,
           "n_test": int(len(t)), "test_payouts": int(y.sum())}
    Path("training/results").mkdir(exist_ok=True)
    Path(f"training/results/{RUN.name}_v3.json").write_text(json.dumps(out, indent=1))
    print(RUN.name, f"within-company {m['test']['within_company_auc']:.4f}  95% range {lo:.4f}-{hi:.4f}")
    print(json.dumps({"test": {k: round(v, 4) for k, v in m["test"].items()}, "recall_at": recall_at}, indent=1))

runs = [Path(a) for a in sys.argv[1:]] or sorted(p.parent for p in Path("training/outputs").glob("*_full/metrics.json"))
for r in runs:
    summarise(r)
