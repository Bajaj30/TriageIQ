"""Explanations, step 1 — split the shipped model into its two stages, so explaining a score is cheap.

WHY: the model has a slow part and a tiny part.
  stage 1  "the reader"   DistilBERT reads the text -> 128 numbers that summarise it          (~all of the cost)
  stage 2  "the judge"    those 128 numbers + the 19 track-record inputs -> one logit         (a few thousand sums)
To explain a score we must re-run the model many times with parts swapped out. Swapping a track-record input
only needs the judge again (free); only swapping SENTENCES needs the reader again. model.onnx has both stages
fused, so this script exports them as two files. model.onnx itself is not touched — /predict keeps using it.

WHAT IT BUILDS (in training/outputs/serving_v3/, git-ignored; local only — not shipped to the server):
  xai_encoder.onnx      (input_ids, attention_mask) -> text_vector (128)       the reader
  xai_head.onnx         (text_vector, cat, num)     -> logit                   the judge
  xai_background.npz    100 "typical" complaints: their text vectors + track-record inputs (already scaled)
                        = the comparison point "what would a typical complaint score?"
CHECK (the gate — nothing is written unless it passes): reader + judge must give the SAME logit as model.onnx on
1,000 test complaints (max |difference| <= 1e-4; we expect ~1e-6). Saved to training/results/xai_onnx_v3.json.

Background = 100 complaints from the VALIDATION split (Oct–Dec 2023): real payout rate (not the case-control
training sample, which is 25% payouts), and not the 2024 test set that the explanations are judged on.
Only their text and intake-time inputs are read — never the outcome.

Run:  USE_TF=0 python training/serving/export_xai_onnx.py
"""
import json, os, tempfile, shutil
from pathlib import Path
os.environ.setdefault("USE_TF", "0")
import numpy as np, pandas as pd, torch, torch.nn as nn
import onnxruntime as ort
from tokenizers import Tokenizer
from transformers import AutoConfig, AutoModel

RUN = Path("training/outputs/fusion_distilbert_full")
OUT = Path("training/outputs/serving_v3")
DATA = Path("Data/data/interim/triageiq_training_v3.parquet")
PREP = json.loads((OUT / "preprocessing.json").read_text())
BASE = "distilbert-base-uncased"
EMB = {"product_id": 4, "sub_product_id": 8, "issue_id": 12, "state_id": 8}   # same as the notebook
N_BACKGROUND, SEED, LIMIT = 100, 42, 1e-4
torch.manual_seed(SEED)

tok = Tokenizer.from_file(str(OUT / "tokenizer.json"))     # the SERVING tokenizer — what the API uses
CLS, SEP, L = tok.token_to_id("[CLS]"), tok.token_to_id("[SEP]"), PREP["max_len"] - 2


# ---------------------------------------------------------------- the model, exactly as in export_onnx.py
class Fusion(nn.Module):
    def __init__(self):
        super().__init__()
        cfg = AutoConfig.from_pretrained(BASE)
        self.enc = AutoModel.from_config(cfg, attn_implementation="eager")
        self.enc.resize_token_embeddings(tok.get_vocab_size())
        self.text = nn.Sequential(nn.Linear(cfg.hidden_size, 128), nn.GELU(), nn.Dropout(0.1))
        self.embs = nn.ModuleList([nn.Embedding(PREP["vocab"][c], EMB[c]) for c in PREP["cat"]])
        self.tab = nn.Sequential(nn.Linear(sum(EMB.values()) + len(PREP["num"]), 128), nn.GELU(), nn.Dropout(0.1),
                                 nn.Linear(128, 64), nn.GELU())
        self.head = nn.Sequential(nn.Linear(128 + 64, 64), nn.GELU(), nn.Dropout(0.1), nn.Linear(64, 1))


class Reader(nn.Module):                                   # stage 1: text -> 128 numbers
    def __init__(self, m):
        super().__init__(); self.enc, self.text = m.enc, m.text
    def forward(self, ids, att):
        return self.text(self.enc(input_ids=ids, attention_mask=att).last_hidden_state[:, 0])   # [CLS]


class Judge(nn.Module):                                    # stage 2: 128 numbers + 19 inputs -> logit
    def __init__(self, m):
        super().__init__(); self.embs, self.tab, self.head = m.embs, m.tab, m.head
    def forward(self, text_vector, cat, num):
        f = self.tab(torch.cat([e(cat[:, i]) for i, e in enumerate(self.embs)] + [num], 1))
        return self.head(torch.cat([text_vector, f], 1)).squeeze(1)


model = Fusion()
model.load_state_dict(torch.load(RUN / "model.pt", map_location="cpu"), strict=True)
model.eval()


# ---------------------------------------------------------------- inputs, prepared exactly like api/scorer.py
def scaled(frame):
    x = frame[PREP["num"]].astype("float64").copy()
    x[PREP["log1p"]] = np.log1p(x[PREP["log1p"]])
    num = ((x - pd.Series(PREP["mean"])) / pd.Series(PREP["std"])).to_numpy(np.float32)
    return frame[PREP["cat"]].to_numpy(np.int64), num


def padded(texts):
    seqs = [[CLS] + e.ids[:L] + [SEP] for e in tok.encode_batch(list(texts), add_special_tokens=False)]
    w = max(map(len, seqs))
    ids, att = np.zeros((len(seqs), w), np.int64), np.zeros((len(seqs), w), np.int64)
    for j, s in enumerate(seqs):
        ids[j, :len(s)], att[j, :len(s)] = s, 1
    return ids, att


d = pd.read_parquet(DATA, columns=["split", "complaint_id", "text", *PREP["cat"], *PREP["num"]])
test = d[d.split == "test"].sample(1000, random_state=SEED).reset_index(drop=True)
background = (d[d.split == "val"].sample(N_BACKGROUND, random_state=SEED)
              .sort_values("complaint_id").reset_index(drop=True))
del d

with tempfile.TemporaryDirectory(dir=OUT) as tmp:
    tmp = Path(tmp)
    ids, att = padded(test.text[:2])
    cat, num = scaled(test[:2])
    with torch.no_grad():
        torch.onnx.export(Reader(model), (torch.from_numpy(ids), torch.from_numpy(att)), tmp / "xai_encoder.onnx",
                          input_names=["input_ids", "attention_mask"], output_names=["text_vector"],
                          dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                        "text_vector": {0: "batch"}}, opset_version=17, dynamo=False)
        torch.onnx.export(Judge(model), (torch.zeros(2, 128), torch.from_numpy(cat), torch.from_numpy(num)),
                          tmp / "xai_head.onnx", input_names=["text_vector", "cat", "num"], output_names=["logit"],
                          dynamic_axes={"text_vector": {0: "batch"}, "cat": {0: "batch"}, "num": {0: "batch"},
                                        "logit": {0: "batch"}}, opset_version=17, dynamo=False)

    # ------------------------------------------------------------ the gate: reader + judge == model.onnx
    full = ort.InferenceSession(str(OUT / "model.onnx"), providers=["CPUExecutionProvider"])
    reader = ort.InferenceSession(str(tmp / "xai_encoder.onnx"), providers=["CPUExecutionProvider"])
    judge = ort.InferenceSession(str(tmp / "xai_head.onnx"), providers=["CPUExecutionProvider"])
    cat, num = scaled(test)
    order = np.argsort(test.text.str.len().to_numpy())     # similar lengths together: less padding
    ref, split = np.zeros(len(test)), np.zeros(len(test))
    for k in range(0, len(test), 16):
        i = order[k:k + 16]
        ids, att = padded(test.text.iloc[i])
        ref[i] = full.run(["logit"], {"input_ids": ids, "attention_mask": att, "cat": cat[i], "num": num[i]})[0]
        tv = reader.run(["text_vector"], {"input_ids": ids, "attention_mask": att})[0]
        split[i] = judge.run(["logit"], {"text_vector": tv, "cat": cat[i], "num": num[i]})[0]
    gap = float(np.abs(ref - split).max())
    print(f"reader + judge vs model.onnx, 1,000 test complaints: max |Δlogit| = {gap:.2e}")
    if gap > LIMIT:
        raise SystemExit(f"FAILED: the split model differs from model.onnx by {gap:.2e} (limit {LIMIT}) — nothing written")

    # ------------------------------------------------------------ the comparison point: 100 typical complaints
    bcat, bnum = scaled(background)
    vecs = []
    for k in range(0, N_BACKGROUND, 16):
        ids, att = padded(background.text.iloc[k:k + 16])
        vecs.append(reader.run(["text_vector"], {"input_ids": ids, "attention_mask": att})[0])
    np.savez_compressed(tmp / "xai_background.npz", text_vector=np.concatenate(vecs).astype(np.float32),
                        cat=bcat, num=bnum, complaint_id=background.complaint_id.to_numpy())
    for f in ("xai_encoder.onnx", "xai_head.onnx", "xai_background.npz"):
        shutil.copy(tmp / f, OUT / f)

result = {"split_vs_model_onnx_max_abs_logit": gap, "test_complaints": len(test), "limit": LIMIT,
          "background": {"rows": N_BACKGROUND, "split": "val (Oct–Dec 2023)", "seed": SEED},
          "sizes_mb": {f: round((OUT / f).stat().st_size / 1e6, 1)
                       for f in ("xai_encoder.onnx", "xai_head.onnx", "xai_background.npz")}}
Path("training/results/xai_onnx_v3.json").write_text(json.dumps(result, indent=1) + "\n")
print("written:", result["sizes_mb"])
