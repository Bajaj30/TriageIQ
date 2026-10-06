# Kaggle setup — training set v3

Goal: get `triageiq_training_v3.parquet` onto a free Kaggle GPU **byte-for-byte identical** to the
file exported on the Mac, so every number trained there traces back to the SQL (ground rule 6).

Files (both in `Data/data/interim/`, both gitignored):

| file | size |
|---|---|
| `triageiq_training_v3.parquet` | 155 MB |
| `triageiq_training_v3.manifest.json` | 3 KB |

---

## Step 0 — one-time account setup

1. Sign in at kaggle.com.
2. Verify your phone number: profile picture → **Settings** → **Phone verification**.
   Without it, Kaggle hides the GPU and Internet switches.

## Step 1 — check the file on the Mac before uploading

```bash
shasum -a 256 Data/data/interim/triageiq_training_v3.parquet
```

It must print the same hash as `"sha256"` in the manifest (`16e3c412…`).
If it doesn't, re-run `python training/export_training_set.py` first.

*Why:* a sha256 is a fingerprint of the bytes. One changed byte gives a completely different hash.
Checking here and again on Kaggle proves the upload changed nothing.

## Step 2 — upload as a private Dataset

1. Kaggle left menu → **Datasets** → **+ New Dataset**.
2. Drag in **both** files: the `.parquet` and the `.manifest.json`.
3. Title: `triageiq-training-v3`.
4. Visibility: **Private** (check it before clicking).
5. Click **Create**. Wait until the page shows both files (the upload takes a minute or two).

*Why both files:* the manifest is the receipt. The notebook checks the Parquet against it.

## Step 3 — create a GPU notebook

1. On the dataset page → **New Notebook**. This attaches the dataset automatically.
2. Open the notebook's settings panel (right side, **Session options**, or menu **Settings**):
   - **Accelerator → GPU T4 x2.** Not P100: T4 has fast fp16, which the Phase 2 plan uses.
   - **Internet → On.** Needed later to download DistilBERT.
3. Rename the notebook `triageiq-v3-smoke` (top left).
4. The GPU clock runs while the session is on. Stop the session (power icon) when done.

## Step 4 — first cell: load, verify, confirm GPU

Paste this into the first cell and run it.

```python
# Cell 1 — load v3, prove it is the exact file exported on the Mac, confirm the GPU.
import glob, hashlib, json
import pandas as pd
import torch

ROOT = "/kaggle/input"   # Kaggle mounts attached datasets here, read-only

def find(name):
    hits = glob.glob(f"{ROOT}/**/{name}", recursive=True)
    assert len(hits) == 1, f"{name}: found {hits} - is the dataset attached?"
    return hits[0]

PQ = find("triageiq_training_v3.parquet")
manifest = json.load(open(find("triageiq_training_v3.manifest.json")))

# 1. fingerprint: same bytes as the Mac export?
h = hashlib.sha256()
with open(PQ, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):   # 1 MB at a time
        h.update(chunk)
assert h.hexdigest() == manifest["sha256"], "sha256 mismatch - upload differs from the export"
print("sha256 OK", h.hexdigest()[:12])

# 2. load; the columns and counts must be the ones the manifest promises
df = pd.read_parquet(PQ)
assert set(df.columns) == set(sum(manifest["columns"].values(), [])), "columns differ from manifest"
assert df["split"].value_counts().to_dict() == manifest["rows"], "rows per split differ"
assert df.groupby("split", observed=True)["paid"].sum().to_dict() == manifest["payouts"], "payouts differ"
print(df.groupby("split", observed=True)["paid"].agg(rows="size", payouts="sum", rate="mean"))

# 3. GPU
assert torch.cuda.is_available(), "no GPU - set Accelerator to GPU T4 x2, then rerun"
for i in range(torch.cuda.device_count()):
    p = torch.cuda.get_device_properties(i)
    print(f"cuda:{i} {p.name} {p.total_memory / 1e9:.1f} GB")
print("torch", torch.__version__)
```

## Step 5 — what "done" looks like

The cell prints, with no assertion error:

- `sha256 OK 16e3c4127dd1`
- rows and payouts per split, matching the manifest: train 62,940 / 15,735 · val 80,000 / 2,798 ·
  test 150,000 / 3,471. Train's rate is high on purpose (all payouts + 3× negatives).
- two lines `cuda:0 Tesla T4 …` and `cuda:1 Tesla T4 …`.

Report back the output. *(Done 2026-10-01; v3 baselines in `training/test.ipynb`, model runs in `training/results/`.)*

---

## If something fails

| message | fix |
|---|---|
| `found [] - is the dataset attached?` | right panel → **Add Input** → your dataset `triageiq-training-v3` |
| `sha256 mismatch` | delete the dataset version, re-upload from the Mac after Step 1 passes |
| `no GPU` | Accelerator not set, or phone not verified (Step 0). Changing it restarts the session |
| GPU option greyed out | weekly GPU hours used up; the quota resets weekly |
