"""Explanations, step 2 — are they faithful, or decorative? Measured on real 2024 test complaints.

An explanation can add up perfectly and still be useless. These tests ask whether it describes what the model
really does. Sample: 100 complaints the company paid + 100 it didn't (2024 test set, seed 42) — a natural sample
would be ~98% credit-report disputes scored near zero, which explain nothing.

  1. DELETION (the main test). Delete the 1 / 3 pieces of text the explanation ranks as raising the score most:
     the score should fall MORE than when deleting 1 / 3 random pieces. Also the reverse: deleting the pieces
     ranked as LOWERING it should make the score rise. Same idea for the track record: reset the top-ranked
     group to typical values vs a random group.
  2. SAMPLING ERROR. Complaints with 5–8 pieces get exact values; re-run them with the 16-order estimate used for
     longer complaints and compare with the truth.
  3. STABILITY. Long complaints (estimated): a second random seed — do the rankings hold?
  4. A SECOND METHOD — LIME (own implementation of the lime package's text recipe: delete random subsets, weight
     each sample by how close it is to the full text, fit a weighted linear model). Do the two methods agree?
  5. THE BIG PICTURE. How much of each score comes from the words vs the track record.

Run:  USE_TF=0 python training/explain/validate_xai.py      (~15–20 min on the M4)  ->  training/results/xai_v3.json
"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.scorer import Scorer                                    # noqa: E402
from api.xai import Explainer, WORDS, GROUPS                     # noqa: E402

M = ROOT / "training/outputs/serving_v3"
SEED, N_EACH, N_LIME, LIME_SAMPLES = 42, 100, 60, 200
rng = np.random.default_rng(SEED)
s = Scorer(M)
x = Explainer(M, s, threads=8)
a = s.cal["a"]

d = pd.read_parquet(ROOT / "Data/data/interim/triageiq_training_v3.parquet",
                    columns=["split", "complaint_id", "paid", "text", *s.cat_cols, *s.num_cols])
t = d[d.split == "test"]
sample = pd.concat([t[t.paid == 1].sample(N_EACH, random_state=SEED), t[t.paid == 0].sample(N_EACH, random_state=SEED)])
del d, t


def spearman(u, v):
    u, v = np.asarray(u), np.asarray(v)
    if len(u) < 3 or u.std() == 0 or v.std() == 0:
        return None
    return float(np.corrcoef(np.argsort(np.argsort(u)), np.argsort(np.argsort(v)))[0, 1])


def text_score(text, spans, keep, cat, num):
    """Logit of the text with only the pieces in `keep` (exactly how the explainer builds coalitions)."""
    txt = " ".join(text[s0:e0] for i, (s0, e0) in enumerate(spans) if i in keep)
    return float(x.judge_logits(x.read([txt]), cat, num)[0])


def group_reset(tv, cat, num, g):
    """Logit with track-record group g set to the typical complaints' values (averaged), everything else kept."""
    B = len(x.bg_text)
    c, n = np.repeat(cat, B, 0), np.repeat(num, B, 0)
    for j, p in enumerate(x.cat_player):
        if p == g: c[:, j] = x.bg_cat[:, j]
    for j, p in enumerate(x.num_player):
        if p == g: n[:, j] = x.bg_num[:, j]
    return float(x.judge_logits(np.repeat(tv[None], B, 0), c, n).mean())


rows, ms, deletion, reverse, groups, sampling, stability = [], [], [], [], [], [], []
lime = []
for k, (_, r) in enumerate(sample.iterrows()):
    inputs = {c: r[c] for c in s.cat_cols + s.num_cols}
    t0 = time.perf_counter()
    e = x.explain(r.text, inputs, seed=SEED)
    ms.append((time.perf_counter() - t0) * 1000)
    st, pl = e["_internal"]["sentences"], e["_internal"]["players"]
    cat, num = s.table(inputs)
    spans, phi, n = st["spans"], st["phi"], len(st["spans"])
    rows.append({"paid": int(r.paid), "phi": pl["phi"].tolist(), "checks": e["checks"], "pieces": n})

    if n >= 4:                                                    # 1. deletion — text
        full = st["full"]
        order = np.argsort(-phi)
        for kk in (1, 3):
            top = full - text_score(r.text, spans, set(range(n)) - set(order[:kk].tolist()), cat, num)
            rnd = np.mean([full - text_score(r.text, spans, set(range(n)) - set(rng.choice(n, kk, replace=False).tolist()),
                                             cat, num) for _ in range(5)])
            deletion.append({"k": kk, "top": top, "random": float(rnd)})
        low = full - text_score(r.text, spans, set(range(n)) - {int(order[-1])}, cat, num)
        reverse.append({"lowest_ranked_drop": low, "phi_lowest": float(phi[order[-1]])})

    tv = x.read([r.text])[0]                                      # 1. deletion — track record
    gphi = pl["phi"][1:]
    gtop = int(np.argmax(gphi)) + 1
    others = [g for g in range(1, len(GROUPS) + 1) if g != gtop]
    groups.append({"top": pl["this"] - group_reset(tv, cat, num, gtop),
                   "random": float(np.mean([pl["this"] - group_reset(tv, cat, num, g) for g in others]))})

    if 5 <= n <= 8:                                               # 2. sampling error, where the truth is known
        est = x.sentences(r.text, cat, num, seed=SEED, force_sampled=True)["phi"]
        sampling.append({"spearman": spearman(phi, est), "top1_same": bool(np.argmax(phi) == np.argmax(est)),
                         "mean_abs_err_share": float(np.abs(phi - est).sum() / max(np.abs(phi).sum(), 1e-9))})
    if n > 8:                                                     # 3. stability across seeds
        other = x.sentences(r.text, cat, num, seed=SEED + 1)["phi"]
        stability.append({"spearman": spearman(phi, other), "top1_same": bool(np.argmax(phi) == np.argmax(other))})

    if n >= 4 and len(lime) < N_LIME:                             # 4. LIME, the lime package's text recipe
        Z = np.ones((LIME_SAMPLES, n), int)
        for i in range(1, LIME_SAMPLES):
            Z[i, rng.choice(n, rng.integers(1, n), replace=False)] = 0
        texts = [" ".join(r.text[s0:e0] for j, (s0, e0) in enumerate(spans) if z[j]) for z in Z]
        y = x.judge_logits(x.read(texts), np.repeat(cat, LIME_SAMPLES, 0), np.repeat(num, LIME_SAMPLES, 0))
        dist = (1 - Z.sum(1) / np.sqrt(n * np.maximum(Z.sum(1), 1))) * 100      # cosine distance to the full text ×100
        w = np.sqrt(np.exp(-dist ** 2 / 25 ** 2))                               # lime's kernel, width 25
        X = np.c_[np.ones(LIME_SAMPLES), Z]
        coef = np.linalg.solve(X.T @ (w[:, None] * X) + np.diag([0] + [1.0] * n), X.T @ (w * y))[1:]   # ridge, alpha 1
        lime.append({"spearman": spearman(phi, coef), "top1_same": bool(np.argmax(phi) == np.argmax(coef)),
                     "top3_overlap": len(set(np.argsort(-phi)[:3]) & set(np.argsort(-coef)[:3])) / 3})
    if (k + 1) % 25 == 0:
        print(f"{k + 1}/{len(sample)} complaints · explain p50 {np.median(ms):.0f} ms", flush=True)


def mean(xs, key=None):
    v = [q[key] if key else q for q in xs]
    v = [q for q in v if q is not None]
    return float(np.mean(v)) if v else None


P = np.array([q["phi"] for q in rows]) * a                      # shares in calibrated log-odds
names = [WORDS] + [g for g, _ in GROUPS]
paid = np.array([q["paid"] for q in rows]) == 1
by_k = {kk: [q for q in deletion if q["k"] == kk] for kk in (1, 3)}
result = {
    "sample": f"2024 test set: {N_EACH} paid + {N_EACH} not paid, seed {SEED}",
    "background": "100 complaints from the validation split (Oct–Dec 2023)",
    "checks_max": {c: float(max(q["checks"][c] for q in rows)) for c in rows[0]["checks"]},
    "latency_ms_mac_m4": {"p50": float(np.percentile(ms, 50)), "p95": float(np.percentile(ms, 95)), "threads": 8},
    "pieces_per_complaint": {"median": float(np.median([q["pieces"] for q in rows])),
                             "exact_share": float(np.mean([q["pieces"] <= 8 for q in rows]))},
    "deletion_text": {f"top{kk}": {"complaints": len(v), "mean_logit_drop_top": mean(v, "top"),
                                   "mean_logit_drop_random": mean(v, "random"),
                                   "share_top_beats_random": float(np.mean([q["top"] > q["random"] for q in v]))}
                      for kk, v in by_k.items()},
    "deleting_lowest_ranked_piece": {"complaints": len(reverse),
                                     "share_score_rose_when_phi_negative": float(np.mean(
                                         [q["lowest_ranked_drop"] < 0 for q in reverse if q["phi_lowest"] < 0]))
                                     if any(q["phi_lowest"] < 0 for q in reverse) else None},
    "deletion_track_record": {"complaints": len(groups), "mean_logit_drop_top_group": mean(groups, "top"),
                              "mean_logit_drop_random_group": mean(groups, "random"),
                              "share_top_beats_random": float(np.mean([q["top"] > q["random"] for q in groups]))},
    "sampling_vs_exact_5_to_8_pieces": {"complaints": len(sampling), "spearman_mean": mean(sampling, "spearman"),
                                        "top1_same_share": mean([float(q["top1_same"]) for q in sampling]),
                                        "error_as_share_of_total": mean(sampling, "mean_abs_err_share")},
    "seed_stability_over_8_pieces": {"complaints": len(stability), "spearman_mean": mean(stability, "spearman"),
                                     "top1_same_share": mean([float(q["top1_same"]) for q in stability])},
    "lime_vs_shapley_sentences": {"complaints": len(lime), "spearman_mean": mean(lime, "spearman"),
                                  "top1_same_share": mean([float(q["top1_same"]) for q in lime]),
                                  "top3_overlap_mean": mean(lime, "top3_overlap")},
    "mean_abs_log_odds_share": {nm: {"paid": float(np.abs(P[paid, i]).mean()), "not_paid": float(np.abs(P[~paid, i]).mean())}
                                for i, nm in enumerate(names)},
    "words_share_of_total_effect": {"paid": float((np.abs(P[paid, 0]) / np.abs(P[paid]).sum(1)).mean()),
                                    "not_paid": float((np.abs(P[~paid, 0]) / np.abs(P[~paid]).sum(1)).mean())},
    "words_is_biggest_factor_share": float(np.mean(np.abs(P).argmax(1) == 0)),
}
(ROOT / "training/results/xai_v3.json").write_text(json.dumps(result, indent=1) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "mean_abs_log_odds_share"}, indent=1))
