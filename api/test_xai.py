"""Tests for api/xai.py — the maths against answers known by hand, the text splitting, and (when the local model
files exist) the real model. Run from the repo root:  python -m unittest api.test_xai -v"""
import unittest
from itertools import permutations
from pathlib import Path

import numpy as np

from api.xai import (coalitions_on, sampled_orders, shapley_exact, shapley_from_orders, split_units)

MODEL_DIR = Path("training/outputs/serving_v3")


def game(fn, n):
    """All 2**n coalition values of a set function fn(set_of_players)."""
    return np.array([fn({i for i in range(n) if m >> i & 1}) for m in range(2 ** n)], dtype=float)


class TheMaths(unittest.TestCase):
    def test_known_answer(self):
        # v = 2·[A] + 3·[B] + 1·[A and B]: the shared 1 is split evenly -> A 2.5, B 3.5, C 0
        v = game(lambda s: 2 * (0 in s) + 3 * (1 in s) + (0 in s and 1 in s), 3)
        self.assertTrue(np.allclose(shapley_exact(v, 3), [2.5, 3.5, 0.0]))

    def test_matches_brute_force_over_all_orders(self):
        rng = np.random.default_rng(0)
        v = rng.normal(size=2 ** 5); v[0] = 0
        orders = [list(p) for p in permutations(range(5))]          # all 120 orders = the definition itself
        brute = shapley_from_orders(dict(enumerate(v)), 5, orders)
        self.assertTrue(np.allclose(shapley_exact(v, 5), brute))

    def test_shares_always_add_up(self):
        rng = np.random.default_rng(1)
        v = rng.normal(size=2 ** 7)
        self.assertAlmostEqual(shapley_exact(v, 7).sum(), v[-1] - v[0])
        orders = sampled_orders(7, 16, seed=3)                      # sampled orders add up exactly too
        phi = shapley_from_orders(dict(enumerate(v)), 7, orders)
        self.assertAlmostEqual(phi.sum(), v[-1] - v[0])

    def test_sampled_orders_come_in_reverse_pairs(self):
        o = sampled_orders(6, 8, seed=42)
        self.assertEqual(len(o), 8)
        self.assertTrue(all(o[k] == o[k + 1][::-1] for k in range(0, 8, 2)))
        self.assertIn(2 ** 6 - 1, coalitions_on(o))

    def test_sampled_close_to_exact_on_an_additive_game(self):
        w = np.arange(1, 11, dtype=float)                           # no interactions: every order gives the truth
        v = game(lambda s: sum(w[i] for i in s), 10)
        phi = shapley_from_orders(dict(enumerate(v)), 10, sampled_orders(10, 4, seed=0))
        self.assertTrue(np.allclose(phi, w))


class TheSplitting(unittest.TestCase):
    def check_cover(self, text, spans):
        self.assertEqual(" ".join(text[s:e] for s, e in spans).split(), text.split())   # every word, in order, once

    def test_sentences(self):
        t = "I was charged {$35.00} twice. I called on [DATE]!\nThey refused. Please refund it."
        spans = split_units(t)
        self.assertEqual([t[s:e] for s, e in spans],
                         ["I was charged {$35.00} twice.", "I called on [DATE]!", "They refused.", "Please refund it."])
        self.check_cover(t, spans)

    def test_run_on_text_is_chunked(self):
        t = " ".join(f"w{i}" for i in range(100))                    # no punctuation at all
        spans = split_units(t, max_words=40)
        self.assertEqual(len(spans), 3)
        self.check_cover(t, spans)

    def test_at_most_16_pieces(self):
        t = " ".join(f"Sentence number {i}." for i in range(50))
        spans = split_units(t)
        self.assertEqual(len(spans), 16)
        self.check_cover(t, spans)


@unittest.skipUnless(all((MODEL_DIR / f).is_file() for f in ("xai_encoder.onnx", "xai_head.onnx",
                                                               "xai_background.npz", "model.onnx")),
                     "local model files not present")
class TheRealModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.scorer import Scorer
        from api.xai import Explainer
        cls.scorer = Scorer(MODEL_DIR)
        cls.x = Explainer(MODEL_DIR, cls.scorer, threads=4)
        b = np.load(MODEL_DIR / "xai_background.npz")
        # a plausible complaint: the first typical complaint's category ids, average numbers (scaled 0 -> raw)
        cls.inputs = {c: int(b["cat"][0, i]) for i, c in enumerate(cls.scorer.cat_cols)}
        for i, c in enumerate(cls.scorer.num_cols):
            raw = cls.scorer.mean[i]
            cls.inputs[c] = float(np.expm1(raw)) if i in cls.scorer.log1p else float(raw)
        cls.text = ("On [DATE] I was charged an overdraft fee of {$35.00} although my balance was positive. "
                    "I called the bank twice. They refused to refund the fee. I want it reversed.")

    def test_checks_pass(self):
        r = self.x.explain(self.text, self.inputs)
        for name, err in r["checks"].items():
            self.assertLess(err, 1e-4, name)
        self.assertEqual(len(r["factors"]), 11)
        self.assertEqual(len(r["sentences"]), 4)
        self.assertEqual(r["sentence_method"], "exact: all 16 combinations")

    def test_probability_is_the_live_one(self):
        r = self.x.explain(self.text, self.inputs)
        self.assertAlmostEqual(r["probability"], self.scorer.score(self.text, self.inputs)["probability"], places=9)


if __name__ == "__main__":
    unittest.main()
