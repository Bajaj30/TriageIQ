"""The model at serving time — every step copies training exactly, so the live model sees what it learned from.

  text   -> word-pieces       tokenizer.json (training's tokenizer + [DATE]/[REDACTED]); "head" cut at 510 + [CLS]/[SEP]
                              (fusion_distilbert.ipynb cell 3; 1000/1000 identical ids, training/results/onnx_v3.json)
  inputs -> scaled numbers    log1p(company_quiet_days), then (x - train mean) / train std   (notebook cell 4,
                              preprocessing.json — fitted on train only, never refitted here)
  model  -> logit             model.onnx on ONNX Runtime, CPU (training/serving/export_onnx.py)
  logit  -> probability       p = sigmoid(a * (logit + offset) + b)   (training/serving/calibrate.py)
  probability -> route        p >= senior threshold -> "senior analyst", else "template response"
Feature logic is NOT here: the 19 inputs arrive from SQL (serving.model_input) — ground rule 4.
"""
import json, math
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class Scorer:
    def __init__(self, model_dir: Path, threads: int = 2):
        self.prep = json.loads((model_dir / "preprocessing.json").read_text())
        self.cal = json.loads((model_dir / "calibration.json").read_text())
        self.card = json.loads((model_dir / "model_card.json").read_text())
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.cls, self.sep = self.tok.token_to_id("[CLS]"), self.tok.token_to_id("[SEP]")
        self.max_body = self.prep["max_len"] - 2                      # 510 pieces + [CLS] + [SEP]
        self.num_cols, self.cat_cols = self.prep["num"], self.prep["cat"]
        self.mean = np.array([self.prep["mean"][c] for c in self.num_cols])
        self.std = np.array([self.prep["std"][c] for c in self.num_cols])
        self.log1p = [i for i, c in enumerate(self.num_cols) if c in self.prep["log1p"]]
        self.vocab = self.prep["vocab"]                               # embedding table sizes per category
        so = ort.SessionOptions()
        so.intra_op_num_threads, so.inter_op_num_threads = threads, 1
        self.sess = ort.InferenceSession(str(model_dir / "model.onnx"), sess_options=so,
                                         providers=["CPUExecutionProvider"])

    def table(self, inputs: dict) -> tuple[np.ndarray, np.ndarray]:
        """The 19 inputs as the model's two arrays: category ids (1, 4) and scaled numbers (1, 15)."""
        for c in self.cat_cols:                                       # an id the model never saw would crash ONNX
            if not 0 <= int(inputs[c]) < self.vocab[c]:
                raise ValueError(f"{c}={inputs[c]} is outside what the model was trained on")
        x = np.array([float(inputs[c]) for c in self.num_cols], dtype=np.float64)
        x[self.log1p] = np.log1p(x[self.log1p])
        return (np.array([[int(inputs[c]) for c in self.cat_cols]], np.int64),
                ((x - self.mean) / self.std).astype(np.float32)[None, :])

    def probability(self, logit: float) -> float:
        """Raw logit -> calibrated chance of a payout (case-control offset, then Platt)."""
        return 1.0 / (1.0 + math.exp(-(self.cal["a"] * (logit + self.cal["offset"]) + self.cal["b"])))

    def score(self, clean_text: str, inputs: dict) -> dict:
        body = self.tok.encode(clean_text, add_special_tokens=False).ids
        ids = [self.cls] + body[: self.max_body] + [self.sep]
        cat, num = self.table(inputs)
        feeds = {"input_ids": np.array([ids], np.int64),
                 "attention_mask": np.ones((1, len(ids)), np.int64), "cat": cat, "num": num}
        logit = float(self.sess.run(["logit"], feeds)[0][0])
        p = self.probability(logit)
        return {"probability": p, "senior": p >= self.cal["senior_threshold_p"], "logit": logit,
                "word_pieces": len(body), "cut_at_512": len(body) > self.max_body}
