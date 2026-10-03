"""Step 3.1 — make the model's probabilities honest again (calibration), and pick the senior/template cut-off.

WHY: after the case-control offset (−2.4165) the model predicts 3.11% payouts on 2024 but 2.31% happened
(trap 13). The offset undoes the SAMPLING; it can't know payouts kept falling (2022 2.74% → 2024 1.71%,
complaints with text). Ranking is fine — only the probability numbers are off.

HOW (the golden rule: fit on one period, check on a LATER one — never grade a fix on the data it was fit on):
  z = model logit + offset (the case-control correction, read from the manifest)
  1. intercept shift : p = sigmoid(z + b)        one number  — fixes a change in the overall payout rate
  2. Platt scaling   : p = sigmoid(a*z + b)      two numbers — also fixes over/under-confidence
  3. isotonic        : a free-form staircase     many steps  — flexible, can overfit, creates ties
  Checks: fit on Jan–Jun 2024 → score Jul–Dec 2024; fit on Jul–Sep → score Oct–Dec.
  A monotone fix (1, 2) cannot change any ranking score; isotonic's ties can (measured below).
DEPLOY: refit the chosen method on the most recent 6 months (Jul–Dec 2024) — payouts are still falling, so
  the newest data is the best guess of "now". Threshold: the riskiest 10% → senior analyst.

Run:  python training/calibrate.py
  ->  training/outputs/fusion_distilbert_full/calibration.json   (shipped with the model; git-ignored)
      training/results/calibration_v3.json                       (tracked numbers)
"""
import json
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, log_loss

RUN = Path("training/outputs/fusion_distilbert_full")
DATA = Path("Data/data/interim/triageiq_training_v3.parquet")
OFFSET = json.loads(DATA.with_suffix(".manifest.json").read_text())["recalibration"]["logit_offset"]
SENIOR_SHARE = 0.10                                    # the desk reads the riskiest 10%

sig = lambda x: 1 / (1 + np.exp(-x))

# ---------------------------------------------------------------- data: 2024 test scores + truth + dates
p = pd.read_parquet(RUN / "test_predictions.parquet")
d = pd.read_parquet(DATA, columns=["complaint_id", "split", "paid", "date_received", "company_id"])
t = d[d.split == "test"].merge(p[["complaint_id", "logit"]], on="complaint_id", how="inner")
assert len(t) == 150_000, len(t)
t["z"] = t.logit + OFFSET
m = t.date_received.dt.month

def within_company(df, prob):
    """Same rule as everywhere: companies with >= 20 payouts and >= 200 complaints, size-weighted AUC."""
    aucs, wts = [], []
    for _, idx in df.groupby("company_id").indices.items():
        y = df.paid.values[idx]
        if y.sum() < 20 or y.sum() == len(y) or len(y) < 200: continue
        aucs.append(roc_auc_score(y, prob[idx])); wts.append(len(y))
    return float(np.average(aucs, weights=wts))

def ece(y, prob, bins=10):
    """Expected calibration error over 10 equal-count buckets (equal-width buckets would be almost all empty:
    most predictions are near 0)."""
    b = np.floor(pd.Series(prob).rank(method="first").to_numpy() * bins / (len(prob) + 1)).astype(int)
    return float(sum(abs(prob[b == k].mean() - y[b == k].mean()) * (b == k).mean() for k in range(bins)))
    # buckets by RANK, not by value: isotonic's ties would otherwise leave buckets empty

def fit(method, z, y):
    if method == "offset only":
        return lambda q: sig(q)
    if method == "intercept shift":                    # logistic regression with the slope fixed at 1
        lo, hi = -5.0, 5.0                             # solve mean(sigmoid(z + b)) = mean(y) by bisection
        for _ in range(60):
            b = (lo + hi) / 2
            lo, hi = (b, hi) if sig(z + b).mean() < y.mean() else (lo, b)
        return lambda q, b=b: sig(q + b)
    if method == "Platt":
        lr = LogisticRegression(C=1e6).fit(z.reshape(-1, 1), y)
        return lambda q, lr=lr: lr.predict_proba(q.reshape(-1, 1))[:, 1]
    if method == "isotonic":
        iso = IsotonicRegression(out_of_bounds="clip", y_min=1e-6, y_max=1 - 1e-6).fit(z, y)
        return lambda q, iso=iso: iso.predict(q)

def report(name, df, prob):
    y = df.paid.values
    return {"method": name, "n": len(df), "actual": y.mean(), "predicted": prob.mean(),
            "brier": brier_score_loss(y, prob), "log_loss": log_loss(y, np.clip(prob, 1e-7, 1 - 1e-7)),
            "ece": ece(y, prob), "within_company": within_company(df, prob)}

# ---------------------------------------------------------------- 1. fit early, check late
METHODS = ["offset only", "intercept shift", "Platt", "isotonic"]
checks = {}
for label, fit_mask, test_mask in [("fit Jan–Jun → check Jul–Dec", m <= 6, m >= 7),
                                   ("fit Jul–Sep → check Oct–Dec", m.between(7, 9), m >= 10)]:
    a, b = t[fit_mask.values], t[test_mask.values].reset_index(drop=True)
    rows = [report(k, b, fit(k, a.z.values, a.paid.values)(b.z.values)) for k in METHODS]
    checks[label] = rows
    print(f"\n{label}   (fit rows {len(a):,}, check rows {len(b):,})")
    print(pd.DataFrame(rows).set_index("method").round(5).to_string())

# ---------------------------------------------------------------- 2. the reliability table (before vs after)
a, b = t[(m <= 6).values], t[(m >= 7).values].reset_index(drop=True)
platt = fit("Platt", a.z.values, a.paid.values)
b["before"], b["after"] = sig(b.z.values), platt(b.z.values)
b["bucket"] = pd.qcut(b.before.rank(method="first"), 10, labels=[f"{k}" for k in range(1, 11)])
rel = b.groupby("bucket", observed=True).agg(complaints=("paid", "size"), actual=("paid", "mean"),
                                             predicted_before=("before", "mean"), predicted_after=("after", "mean"))
print("\nreliability, Jul–Dec 2024 (10 equal-count buckets by score; 10 = riskiest):")
print((rel * [1, 100, 100, 100]).round(3).rename(columns=lambda c: c if c == "complaints" else c + " %").to_string())

# ---------------------------------------------------------------- 3. deploy: refit on the newest 6 months
recent = t[(m >= 7).values]
lr = LogisticRegression(C=1e6).fit(recent.z.values.reshape(-1, 1), recent.paid.values)
A, B = float(lr.coef_[0, 0]), float(lr.intercept_[0])
p_all = sig(A * t.z.values + B)
cut = float(np.quantile(p_all, 1 - SENIOR_SHARE))     # riskiest 10% of 2024 test complaints
top = p_all >= cut
y = t.paid.values
cal = {
    "method": "Platt scaling on z = logit + offset:  p = sigmoid(a * z + b)",
    "offset": OFFSET, "a": A, "b": B,
    "fit_on": "2024-07-01..2024-12-31 test complaints (newest labelled data), n = %d" % len(recent),
    "senior_threshold_p": cut,
    "senior_share": SENIOR_SHARE,
    "senior_rule": "p >= senior_threshold_p -> senior analyst, else template (riskiest 10% of 2024 test complaints)",
    "data_end": "2024-12-31",
}
(RUN / "calibration.json").write_text(json.dumps(cal, indent=1))
summary = {"calibration": cal, "checks": checks,
           "deployed_on_2024": {"recall_of_payouts_in_senior": float(y[top].sum() / y.sum()),
                                "payout_rate_in_senior": float(y[top].mean()),
                                "payout_rate_in_template": float(y[~top].mean()),
                                "within_company_before": within_company(t, sig(t.z.values)),
                                "within_company_after": within_company(t, p_all)}}
Path("training/results/calibration_v3.json").write_text(json.dumps(summary, indent=1, default=float))
print(f"\nDEPLOY: a = {A:.4f}, b = {B:.4f}  ·  senior if p >= {cut:.4f}")
print({k: round(v, 4) for k, v in summary["deployed_on_2024"].items()})
