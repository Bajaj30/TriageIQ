"""Why did the model give THIS score? — Shapley values over the shipped model. Local use only (see below).

THE IDEA (Shapley values, the maths behind "SHAP"): share a team's result fairly among its players. Add the
players one at a time in some order and note how much the score jumps when each one joins; a player's fair
share is its average jump over all orders. The shares add up exactly:
        score of a typical complaint  +  every player's share  =  this complaint's score       (in logit units)

THE PLAYERS
  1. the complaint's words (all of them together)
  2–11. ten groups of the 19 track-record inputs (GROUPS below). Inputs that only make sense together are one
     player — e.g. product and sub-product (a "credit card" product with a "checking account" sub-product
     never exists), or a rate and its "no history yet" flag.
"Taking a player out" = giving it the value from a typical complaint: 100 real complaints from Oct–Dec 2023
(xai_background.npz, built by training/serving/export_xai_onnx.py), averaged.

WHY IT'S FAST: the model is two stages (export_xai_onnx.py) — the reader (DistilBERT, slow) turns the text into
128 numbers once; the judge (tiny) combines them with the inputs. Words vs track record needs only the judge,
so all 2^11 = 2,048 combinations × 100 typical complaints are computed EXACTLY in one batch (~0.2 s).

WHICH SENTENCES: the text is cut into up to 16 pieces (sentences; long ones split). Here the players are the
pieces and "taking one out" = deleting it and re-reading the rest — every combination costs a full DistilBERT
pass. ≤ 8 pieces: all combinations, exact. More: 16 random orders (8 orders + their reverses), ~250 re-reads.
Baseline for sentences = the empty complaint. Caveat: a complaint with sentences deleted is text the model never
saw in training — this measures how the model reacts, not the customer's true meaning.

UNITS FOR PEOPLE: the API returns logit shares, and each share as an ODDS factor, exp(a × share) — "this raises
the odds of a payout ×2.4". Exact in calibrated space: calibrated log-odds = a·(logit + offset) + b.

WHAT IT IS NOT: the model's reasons, not the company's. Error analysis (CLAUDE.md trap 14): the deciding fact is
often a company decision that isn't in the text.

SERVING: needs the three xai_* files (git-ignored; GitHub Release model-v3). When they're present the scorer runs
the same two halves (api/scorer.py), so explanations share its DistilBERT — no second copy in memory. On the
small server an explanation takes up to about a minute, so the API runs them one at a time from a queue
(api/main.py) and visitors wait their turn.
"""
import re
from math import factorial
from pathlib import Path

import numpy as np
import onnxruntime as ort

FILES = ("xai_encoder.onnx", "xai_head.onnx", "xai_background.npz")

GROUPS = [   # (name shown to people, the inputs it holds) — every one of the 19 inputs exactly once
    ("The product", ["product_id", "sub_product_id", "product_rate_s"]),
    ("The kind of problem", ["issue_id", "issue_rate_s"]),
    ("This company's record on this kind of problem", ["company_issue_rate_s", "company_issue_no_history"]),
    ("This company's record overall", ["company_rate_s", "company_no_history"]),
    ("Complaints this company never answered", ["company_untimely_rate"]),
    ("How busy this company has been lately", ["company_share_90d", "company_issue_share_90d",
                                               "company_trend_90d", "company_quiet_days"]),
    ("How common this kind of problem is lately", ["issue_share_90d", "issue_trend_90d"]),
    ("Older American tag", ["is_older_american"]),
    ("Servicemember tag", ["is_servicemember"]),
    ("The customer's state", ["state_id"]),
]
WORDS = "The complaint's words"
MAX_UNITS, MAX_WORDS, EXACT_UP_TO, ORDERS = 16, 40, 8, 16


def available(model_dir: Path) -> bool:
    return all((model_dir / f).is_file() for f in FILES)


# ---------------------------------------------------------------- the maths (pure, unit-tested)
def shapley_exact(v: np.ndarray, n: int) -> np.ndarray:
    """v[mask] = value of the coalition `mask` (bit i set = player i present), for all 2**n masks.
    phi_i = sum over coalitions S without i of  |S|! (n-|S|-1)! / n!  * (v[S + i] - v[S])."""
    masks = np.arange(2 ** n)
    size = np.array([bin(m).count("1") for m in masks])
    weight = np.array([factorial(s) * factorial(n - s - 1) / factorial(n) for s in range(n)])
    phi = np.zeros(n)
    for i in range(n):
        without = masks[(masks >> i) & 1 == 0]
        phi[i] = np.sum(weight[size[without]] * (v[without | (1 << i)] - v[without]))
    return phi


def sampled_orders(n: int, orders: int, seed: int) -> list[list[int]]:
    """`orders` random orders of the players, in pairs: an order and its reverse ("antithetic" — the reverse
    sees every player join a nearly-full team instead of a nearly-empty one, which cancels a lot of noise)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(orders // 2):
        o = rng.permutation(n).tolist()
        out += [o, o[::-1]]
    return out


def shapley_from_orders(v: dict, n: int, orders: list[list[int]]) -> np.ndarray:
    """Average jump of each player over the given orders. v[mask] must hold every coalition on every path."""
    phi = np.zeros(n)
    for o in orders:
        mask = 0
        for i in o:
            phi[i] += v[mask | (1 << i)] - v[mask]
            mask |= 1 << i
    return phi / len(orders)


def coalitions_on(orders: list[list[int]]) -> set[int]:
    seen = {0}
    for o in orders:
        mask = 0
        for i in o:
            mask |= 1 << i
            seen.add(mask)
    return seen


def split_units(text: str, max_words: int = MAX_WORDS, max_units: int = MAX_UNITS) -> list[tuple[int, int]]:
    """Cut the text into at most `max_units` pieces: sentences, long sentences split into <= max_words words.
    Returns (start, end) character spans that cover every word in order, so joining the pieces with spaces
    gives the same word-pieces as the original (whitespace never changes DistilBERT's word-pieces)."""
    words = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    sentences, cur = [], []
    for k, (s, e) in enumerate(words):
        cur.append(k)
        nxt = words[k + 1][0] if k + 1 < len(words) else len(text)
        if re.search(r"[.!?][\"')\]]*$", text[s:e]) or "\n" in text[e:nxt]:
            sentences.append(cur); cur = []
    if cur:
        sentences.append(cur)
    units = []
    for sent in sentences:                                 # long run-ons -> balanced chunks of <= max_words
        parts = -(-len(sent) // max_words)
        size = -(-len(sent) // parts)
        units += [sent[i:i + size] for i in range(0, len(sent), size)]
    while len(units) > max_units:                          # too many -> merge the smallest neighbouring pair
        j = min(range(len(units) - 1), key=lambda i: len(units[i]) + len(units[i + 1]))
        units[j:j + 2] = [units[j] + units[j + 1]]
    return [(words[u[0]][0], words[u[-1]][1]) for u in units]


# ---------------------------------------------------------------- the explainer
class Explainer:
    def __init__(self, model_dir: Path, scorer, threads: int = 2, batch: int = 16):
        if getattr(scorer, "split", False):              # the scorer already runs the two halves: share them
            self.reader, self.judge = scorer.reader, scorer.judge
        else:
            so = ort.SessionOptions()
            so.intra_op_num_threads, so.inter_op_num_threads = threads, 1
            self.reader = ort.InferenceSession(str(model_dir / "xai_encoder.onnx"), sess_options=so,
                                               providers=["CPUExecutionProvider"])
            self.judge = ort.InferenceSession(str(model_dir / "xai_head.onnx"), sess_options=so,
                                              providers=["CPUExecutionProvider"])
        self.batch = batch                                 # texts per DistilBERT pass: smaller = less peak memory
        bg = np.load(model_dir / "xai_background.npz")
        self.bg_text, self.bg_cat, self.bg_num = bg["text_vector"], bg["cat"], bg["num"]
        self.s = scorer
        listed = [c for _, cols in GROUPS for c in cols]
        assert sorted(listed) == sorted(scorer.cat_cols + scorer.num_cols), "GROUPS must hold all 19 inputs once"
        n = 1 + len(GROUPS)                                 # player 0 = the words
        self.n = n
        self.bits = (np.arange(2 ** n)[:, None] >> np.arange(n)[None, :]) & 1
        group_of = {c: g + 1 for g, (_, cols) in enumerate(GROUPS) for c in cols}
        self.cat_player = [group_of[c] for c in scorer.cat_cols]
        self.num_player = [group_of[c] for c in scorer.num_cols]

    # -------------------------------------------------- the two stages
    def read(self, texts: list[str]) -> np.ndarray:
        """Text -> 128 numbers (DistilBERT), in batches of similar length, exactly as the scorer tokenises."""
        seqs = [[self.s.cls] + self.s.tok.encode(t, add_special_tokens=False).ids[: self.s.max_body] + [self.s.sep]
                for t in texts]
        out = np.zeros((len(seqs), 128), np.float32)
        order = np.argsort([len(q) for q in seqs])
        for k in range(0, len(seqs), self.batch):
            idx = order[k:k + self.batch]
            w = max(len(seqs[i]) for i in idx)
            ids, att = np.zeros((len(idx), w), np.int64), np.zeros((len(idx), w), np.int64)
            for j, i in enumerate(idx):
                ids[j, :len(seqs[i])], att[j, :len(seqs[i])] = seqs[i], 1
            out[idx] = self.reader.run(["text_vector"], {"input_ids": ids, "attention_mask": att})[0]
        return out

    def judge_logits(self, text_vec, cat, num) -> np.ndarray:
        return self.judge.run(["logit"], {"text_vector": text_vec.astype(np.float32), "cat": cat.astype(np.int64),
                                          "num": num.astype(np.float32)})[0].reshape(-1).astype(np.float64)

    # -------------------------------------------------- 1. words vs track-record groups (exact)
    def players(self, text_vec, cat, num) -> dict:
        """v[mask] = average logit over the 100 typical complaints when the players in `mask` keep THIS complaint's
        values and the rest take the typical complaint's. All 2^11 masks, exact Shapley."""
        B, v = len(self.bg_text), np.zeros(2 ** self.n)
        for k in range(0, 2 ** self.n, 256):               # 256 masks × 100 complaints per batch
            bits = self.bits[k:k + 256].astype(bool)
            m = len(bits)
            t = np.where(bits[:, 0, None, None], text_vec[None], self.bg_text[None])          # (m, B, 128)
            c = np.where(bits[:, self.cat_player][:, None, :], cat[None], self.bg_cat[None])  # (m, B, 4)
            x = np.where(bits[:, self.num_player][:, None, :], num[None], self.bg_num[None])  # (m, B, 15)
            v[k:k + m] = self.judge_logits(t.reshape(m * B, -1), c.reshape(m * B, -1),
                                           x.reshape(m * B, -1)).reshape(m, B).mean(1)
        phi = shapley_exact(v, self.n)
        return {"phi": phi, "typical": float(v[0]), "this": float(v[-1])}

    # -------------------------------------------------- 2. which sentences
    def sentences(self, text: str, cat, num, seed: int = 42, orders: int = ORDERS, force_sampled: bool = False) -> dict:
        enc = self.s.tok.encode(text, add_special_tokens=False)
        visible, unread = text, 0
        if len(enc.ids) > self.s.max_body:                 # the model reads 510 pieces: explain only those
            cut = enc.offsets[self.s.max_body - 1][1]
            m = re.search(r"\s", text[cut:])
            cut = cut + m.start() if m else len(text)
            visible, unread = text[:cut], len(text[cut:].split())
        spans = split_units(visible)
        n = len(spans)
        if n == 0:
            return {"spans": [], "phi": np.zeros(0), "empty": 0.0, "full": 0.0, "method": "no text", "unread": unread}
        exact = n <= EXACT_UP_TO and not force_sampled     # force_sampled: validation compares the two
        paths = None if exact else sampled_orders(n, orders, seed)
        masks = sorted(range(2 ** n)) if exact else sorted(coalitions_on(paths))
        texts = [" ".join(visible[s:e] for i, (s, e) in enumerate(spans) if mask >> i & 1) for mask in masks]
        vecs = self.read(texts)
        logits = self.judge_logits(vecs, np.repeat(cat, len(masks), 0), np.repeat(num, len(masks), 0))
        v = dict(zip(masks, logits))
        phi = shapley_exact(np.array([v[m] for m in range(2 ** n)]), n) if exact else shapley_from_orders(v, n, paths)
        return {"spans": spans, "phi": phi, "empty": float(v[0]), "full": float(v[2 ** n - 1]), "unread": unread,
                "rereads": len(masks),
                "method": f"exact: all {2 ** n} combinations" if exact else
                          f"estimated from {orders} random orders ({len(masks)} re-reads)"}

    # -------------------------------------------------- everything, in people's units
    def explain(self, text: str, inputs: dict, seed: int = 42) -> dict:
        cat, num = self.s.table(inputs)
        live = self.s.score(text, inputs)                  # the production path, for the check below
        tv = self.read([text])
        pl = self.players(tv[0], cat[0], num[0])
        st = self.sentences(text, cat, num, seed)
        a = self.s.cal["a"]
        odds = lambda phi: float(np.exp(a * phi))
        names = [WORDS] + [g for g, _ in GROUPS]
        cols = [[]] + [c for _, c in GROUPS]
        factors = [{"name": names[i], "logit": float(pl["phi"][i]), "odds_factor": odds(pl["phi"][i]),
                    "inputs": {c: float(inputs[c]) for c in cols[i]}} for i in range(self.n)]
        factors.sort(key=lambda f: -abs(f["logit"]))
        return {
            "probability": live["probability"], "senior": live["senior"],
            "typical_probability": self.s.probability(pl["typical"]),
            "factors": factors,
            "sentences": [{"start": s, "end": e, "text": text[s:e], "logit": float(p), "odds_factor": odds(p)}
                          for (s, e), p in zip(st["spans"], st["phi"])],
            "sentence_method": st["method"], "words_not_read": st["unread"],
            "checks": {   # all should be ~0; the API refuses to answer if they aren't
                "shares_add_up": abs(pl["typical"] + pl["phi"].sum() - pl["this"]),       # the maths
                "matches_live_model": abs(pl["this"] - live["logit"]),                    # two stages = model.onnx
                "sentences_add_up": abs(st["empty"] + st["phi"].sum() - st["full"]),      # the maths
                "pieces_rejoined_match": abs(st["full"] - live["logit"]) if st["spans"] else 0.0,  # the splitting
            },
            "_internal": {"players": pl, "sentences": st},   # for training/explain/validate_xai.py; dropped by the API
        }
