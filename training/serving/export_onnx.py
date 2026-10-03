"""Step 3.2 — turn the trained PyTorch model into one ONNX file that runs on a CPU without PyTorch.

WHY: the server has a CPU, ~2 GB RAM, no GPU. model.pt holds only the learned numbers (state_dict); the
network's shape lives in the notebook's Python code. Exporting writes the recipe AND the numbers into one
.onnx file that ONNX Runtime can run anywhere — no PyTorch in the serving image.

WHAT IT BUILDS — the serving bundle, everything the API needs, in one folder:
  training/outputs/serving_v3/   (git-ignored: 266 MB)
    model.onnx          the fusion model: (input_ids, attention_mask, cat, num) -> logit
    tokenizer.json      DistilBERT's word-pieces + the [DATE] / [REDACTED] markers (fast-tokenizer file)
    preprocessing.json  the train-only means/stds and the input order (copied from the training run)
    calibration.json    offset + Platt a, b + the senior threshold (from training/serving/calibrate.py)
CHECKS (printed, and saved to training/results/onnx_v3.json):
  1. tokenizer: the serving tokenizer (tokenizers library) gives the SAME ids as training's (transformers)
  2. parity: ONNX vs PyTorch on 1,000 test complaints — the same math, so differences ~1e-5
  3. vs Kaggle: our CPU fp32 logits vs the T4's fp16 logits — small differences, ranking unchanged
  4. speed: one complaint at a time on 2 CPU threads (≈ a small cloud server), p50 / p95 by length

Run:  USE_TF=0 python training/serving/export_onnx.py
"""
import json, os, shutil, time
from pathlib import Path
os.environ.setdefault("USE_TF", "0")
import numpy as np, pandas as pd, torch, torch.nn as nn
import onnxruntime as ort
from tokenizers import Tokenizer
from transformers import AutoConfig, AutoModel, AutoTokenizer

RUN = Path("training/outputs/fusion_distilbert_full")
OUT = Path("training/outputs/serving_v3")
DATA = Path("Data/data/interim/triageiq_training_v3.parquet")
PREP = json.loads((RUN / "preprocessing.json").read_text())
BASE = "distilbert-base-uncased"
EMB = {"product_id": 4, "sub_product_id": 8, "issue_id": 12, "state_id": 8}   # same as the notebook
OUT.mkdir(parents=True, exist_ok=True)
torch.manual_seed(42)

# ---------------------------------------------------------------- the tokenizer (as in training, cell 3)
tok = AutoTokenizer.from_pretrained(BASE)
tok.add_special_tokens({"additional_special_tokens": PREP["markers"]})
tok.backend_tokenizer.save(str(OUT / "tokenizer.json"))
L = PREP["max_len"] - 2                                    # room for [CLS] and [SEP]

def encode(texts):                                         # training's encode(), "head" truncation
    body = tok(list(texts), add_special_tokens=False, truncation=False)["input_ids"]
    return [[tok.cls_token_id] + b[:L] + [tok.sep_token_id] for b in body]

# ---------------------------------------------------------------- the model (as in training, cell 6, MODE=fusion)
class Fusion(nn.Module):
    def __init__(self):
        super().__init__()
        cfg = AutoConfig.from_pretrained(BASE)
        self.enc = AutoModel.from_config(cfg, attn_implementation="eager")   # weights come from model.pt
        self.enc.resize_token_embeddings(len(tok))
        self.text = nn.Sequential(nn.Linear(cfg.hidden_size, 128), nn.GELU(), nn.Dropout(0.1))
        self.embs = nn.ModuleList([nn.Embedding(PREP["vocab"][c], EMB[c]) for c in PREP["cat"]])
        self.tab = nn.Sequential(nn.Linear(sum(EMB.values()) + len(PREP["num"]), 128), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(128, 64), nn.GELU())
        self.head = nn.Sequential(nn.Linear(128 + 64, 64), nn.GELU(), nn.Dropout(0.1), nn.Linear(64, 1))
    def forward(self, ids, att, cat, num):
        t = self.text(self.enc(input_ids=ids, attention_mask=att).last_hidden_state[:, 0])      # [CLS]
        f = self.tab(torch.cat([e(cat[:, i]) for i, e in enumerate(self.embs)] + [num], 1))
        return self.head(torch.cat([t, f], 1)).squeeze(1)

model = Fusion()
model.load_state_dict(torch.load(RUN / "model.pt", map_location="cpu"), strict=True)   # every weight must match
model.eval()                                               # dropout OFF — inference mode

# ---------------------------------------------------------------- 1,000 real test complaints, prepared like training
d = pd.read_parquet(DATA)
te = d[d.split == "test"].sample(1000, random_state=42).reset_index(drop=True)
x = te[PREP["num"]].astype("float64").copy()
x[PREP["log1p"]] = np.log1p(x[PREP["log1p"]])
te_num = ((x - pd.Series(PREP["mean"])) / pd.Series(PREP["std"])).to_numpy(np.float32)
te_cat = te[PREP["cat"]].to_numpy(np.int64)
te_ids = encode(te.text)

def batch(idx):
    ids = [te_ids[i] for i in idx]; mlen = max(map(len, ids))
    a = np.zeros((len(idx), mlen), np.int64); m = np.zeros((len(idx), mlen), np.int64)
    for j, s in enumerate(ids):
        a[j, :len(s)] = s; m[j, :len(s)] = 1
    return a, m, te_cat[idx], te_num[idx]

# ---------------------------------------------------------------- export
a, m, c, n = batch(np.arange(4))
torch.onnx.export(model, tuple(torch.from_numpy(v) for v in (a, m, c, n)), OUT / "model.onnx",
                  input_names=["input_ids", "attention_mask", "cat", "num"], output_names=["logit"],
                  dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                "cat": {0: "batch"}, "num": {0: "batch"}, "logit": {0: "batch"}},
                  opset_version=17, dynamo=False)
shutil.copy(RUN / "preprocessing.json", OUT / "preprocessing.json")
shutil.copy(RUN / "calibration.json", OUT / "calibration.json")
size_mb = (OUT / "model.onnx").stat().st_size / 1e6
print(f"exported model.onnx: {size_mb:.0f} MB")

# ---------------------------------------------------------------- check 1: serving tokenizer == training tokenizer
serve_tok = Tokenizer.from_file(str(OUT / "tokenizer.json"))
cls_id, sep_id = tok.cls_token_id, tok.sep_token_id
serve_ids = [[cls_id] + e.ids[:L] + [sep_id] for e in serve_tok.encode_batch(list(te.text), add_special_tokens=False)]
tok_same = sum(s == t for s, t in zip(serve_ids, te_ids))
print(f"tokenizer: {tok_same}/1000 complaints get identical ids · markers -> {serve_tok.encode('[DATE] [REDACTED]', add_special_tokens=False).ids}")

# ---------------------------------------------------------------- check 2 + 3: parity
order = np.argsort([len(s) for s in te_ids])               # similar lengths together: less padding
sess = ort.InferenceSession(str(OUT / "model.onnx"), providers=["CPUExecutionProvider"])
pt, ox = np.zeros(1000), np.zeros(1000)
with torch.no_grad():
    for k in range(0, 1000, 16):
        idx = order[k:k + 16]; a, m, c, n = batch(idx)
        pt[idx] = model(*(torch.from_numpy(v) for v in (a, m, c, n))).numpy()
        ox[idx] = sess.run(["logit"], {"input_ids": a, "attention_mask": m, "cat": c, "num": n})[0]
kaggle = te[["complaint_id"]].merge(pd.read_parquet(RUN / "test_predictions.parquet"), on="complaint_id").logit.values
sig = lambda z: 1 / (1 + np.exp(-z))
off = json.loads((OUT / "calibration.json").read_text())["offset"]
parity = {"onnx_vs_pytorch_max_abs_logit": float(np.abs(pt - ox).max()),
          "cpu_vs_kaggle_t4_max_abs_logit": float(np.abs(ox - kaggle).max()),
          "cpu_vs_kaggle_t4_max_abs_prob": float(np.abs(sig(ox + off) - sig(kaggle + off)).max()),
          "cpu_vs_kaggle_rank_corr": float(pd.Series(ox).corr(pd.Series(kaggle), method="spearman"))}
print("parity:", {k: round(v, 6) for k, v in parity.items()})

# ---------------------------------------------------------------- check 4: speed — one complaint at a time, 2 threads
so = ort.SessionOptions(); so.intra_op_num_threads = 2; so.inter_op_num_threads = 1
sess2 = ort.InferenceSession(str(OUT / "model.onnx"), sess_options=so, providers=["CPUExecutionProvider"])
lens = np.array([len(s) for s in te_ids]); ms = []
for i in range(300):
    a, m, c, n = batch(np.array([i]))
    t0 = time.perf_counter(); sess2.run(["logit"], {"input_ids": a, "attention_mask": m, "cat": c, "num": n})
    ms.append((time.perf_counter() - t0) * 1000)
ms = np.array(ms); l3 = lens[:300]
speed = {"p50_ms": float(np.percentile(ms, 50)), "p95_ms": float(np.percentile(ms, 95)),
         "p50_ms_by_tokens": {f"{lo}-{hi}": float(np.median(ms[(l3 > lo) & (l3 <= hi)]))
                              for lo, hi in [(0, 128), (128, 256), (256, 512)] if ((l3 > lo) & (l3 <= hi)).any()},
         "threads": 2, "machine": "MacBook M4 (a cloud vCPU is slower — re-measure on the server)"}
print("speed:", json.dumps(speed))
Path("training/results/onnx_v3.json").write_text(json.dumps(
    {"model_onnx_mb": size_mb, "tokenizer_identical_of_1000": tok_same, "parity": parity, "speed": speed}, indent=1))
print("bundle:", sorted(p.name for p in OUT.iterdir()))
