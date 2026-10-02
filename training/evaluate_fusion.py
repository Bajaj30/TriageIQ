"""Summarise a Kaggle fusion run into a small, tracked results file.

Reads (git-ignored, downloaded from Kaggle):
  training/outputs/fusion_full/metrics.json           written by fusion_distilbert.ipynb
  training/outputs/fusion_full/test_predictions.parquet
  Data/data/interim/triageiq_training_v3.parquet       for the true labels
Writes (tracked):  training/results/fusion_full_v3.json  -> rendered into Context/FACTS.md

Run:  python training/evaluate_fusion.py
"""
import json
from pathlib import Path
import numpy as np, pandas as pd

RUN = Path("training/outputs/fusion_full")
m = json.loads((RUN / "metrics.json").read_text())
p = pd.read_parquet(RUN / "test_predictions.parquet")
d = pd.read_parquet("Data/data/interim/triageiq_training_v3.parquet", columns=["complaint_id", "split", "paid"])
t = d[d.split == "test"].merge(p, on="complaint_id", how="inner")
assert len(t) == len(d[d.split == "test"]) == len(p), "predictions do not cover the test set exactly"

y, order = t.paid.values, np.argsort(-t.logit.values)
recall_at = {f"top_{int(s * 100)}pct": float(y[order[:int(len(y) * s)]].sum() / y.sum()) for s in (0.05, 0.10, 0.20)}

out = {"run": m["run"], "cfg": m["cfg"], "history": m["history"], "test": m["test"], "recall_at": recall_at,
       "n_test": int(len(t)), "test_payouts": int(y.sum())}
Path("training/results").mkdir(exist_ok=True)
Path("training/results/fusion_full_v3.json").write_text(json.dumps(out, indent=1))
print(json.dumps({"test": {k: round(v, 4) for k, v in m["test"].items()}, "recall_at": recall_at}, indent=1))
