"""Copy the SQL training set (view v_training_export) into a Parquet file + manifest for Kaggle.

This script only MOVES rows. Every rule, feature and label lives in SQL (ground rule 4):
  sql/04_training_set/02_training_set.sql   which complaints, which split, the sampling
  sql/05_export/01_training_export.sql      which columns
Reads Postgres through `docker exec ... psql COPY` — no database driver needed.

Run:  python training/export_training_set.py
  ->  Data/data/interim/triageiq_training_v3.parquet
      Data/data/interim/triageiq_training_v3.manifest.json
"""
import hashlib, io, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

OUT = Path("Data/data/interim")
NAME = "triageiq_training_v3"
PSQL = ["docker", "exec", "-i", "triageiq-postgres", "psql", "-U", "triageiq", "-d", "triageiq"]

ROLES = {
    "id":          ["complaint_id"],
    "split":       ["split"],
    "label":       ["paid"],
    "text":        ["text"],
    "categorical": ["product_id", "sub_product_id", "issue_id", "state_id"],
    "flags":       ["is_older_american", "is_servicemember", "company_no_history", "company_issue_no_history"],
    "numeric":     ["company_issue_rate_s", "company_rate_s", "issue_rate_s", "product_rate_s",
                    "company_untimely_rate", "company_share_90d", "company_issue_share_90d",
                    "issue_share_90d", "company_trend_90d", "issue_trend_90d", "company_quiet_days"],
    "eval_only":   ["date_received", "company_id"],   # never model inputs
}

def psql(sql: str) -> str:
    return subprocess.run(PSQL + ["-At", "-c", sql], check=True, capture_output=True, text=True).stdout

# 1. the rows — ORDER BY complaint_id so the file is byte-identical on every run
csv = subprocess.run(
    PSQL + ["-c", "COPY (SELECT * FROM v_training_export ORDER BY complaint_id) TO STDOUT WITH (FORMAT csv, HEADER true)"],
    check=True, capture_output=True, text=True).stdout
d = pd.read_csv(io.StringIO(csv), keep_default_na=False, na_values=[""])

# 2. types — small and explicit, so Kaggle loads exactly what SQL produced
for c in ROLES["id"] + ROLES["categorical"] + ["company_id"]:
    d[c] = d[c].astype("int64")
for c in ROLES["label"] + ROLES["flags"]:
    d[c] = d[c].astype("int8")
for c in ROLES["numeric"]:
    d[c] = d[c].astype("float64")
d["date_received"] = pd.to_datetime(d["date_received"])
d["split"] = d["split"].astype("category")

# 3. guards — the same checks as the SQL file, on the file that actually ships
expected = {"train": 62940, "val": 80000, "test": 150000}
got = d["split"].value_counts().to_dict()
assert got == expected, f"rows per split {got} != {expected}"
assert d.drop(columns=[]).isna().sum().sum() == 0, "NULLs in export"
assert set(sum(ROLES.values(), [])) == set(d.columns), "column roles out of sync with v_training_export"

# 4. write + manifest
OUT.mkdir(parents=True, exist_ok=True)
pq_path = OUT / f"{NAME}.parquet"
d.to_parquet(pq_path, index=False)
sha = hashlib.sha256(pq_path.read_bytes()).hexdigest()
db_manifest = dict(line.split("|", 1) for line in psql("SELECT key, value FROM training_manifest ORDER BY key").splitlines())
manifest = {
    "file": pq_path.name, "sha256": sha, "exported_at": datetime.now(timezone.utc).isoformat(),
    "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
    "rows": {s: int(n) for s, n in got.items()},
    "payouts": {s: int(d.loc[d.split == s, "paid"].sum()) for s in expected},
    "columns": ROLES,
    "model_inputs": ROLES["categorical"] + ROLES["flags"] + ROLES["numeric"],
    "recalibration": {
        "negative_keep_fraction": float(db_manifest["train.negative_keep_fraction"]),
        "logit_offset": float(db_manifest["recalibration_logit_offset"]),
        "how": "add logit_offset to the model's logit for train-sampled predictions -> true payout odds",
    },
    "text_markers": ["[DATE]", "[REDACTED]"],
    "text_markers_note": "register both as SPECIAL tokens in the tokenizer (else [REDACTED] = 5 word-pieces)",
    "sql_manifest": db_manifest,
}
(OUT / f"{NAME}.manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"wrote {pq_path} ({pq_path.stat().st_size / 1e6:.1f} MB, {len(d):,} rows) + manifest; sha256 {sha[:12]}…")
print({s: (manifest["rows"][s], manifest["payouts"][s]) for s in expected})
