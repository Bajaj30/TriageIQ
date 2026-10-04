"""Write training/outputs/serving_v3/model_card.json — what the API's GET /model-info returns.

Every number is READ from the tracked result files (never typed), so the live API can't drift from FACTS.md:
  training/results/fusion_distilbert_full_v3.json   test scores + 95% range
  training/results/calibration_v3.json              calibration and its checks
  Data/data/interim/triageiq_training_v3.manifest.json   training-set sizes
Run:  python training/serving/model_card.py
"""
import json
from pathlib import Path

R = Path("training/results")
OUT = Path("training/outputs/serving_v3")
run = json.loads((R / "fusion_distilbert_full_v3.json").read_text())
cal = json.loads((R / "calibration_v3.json").read_text())
man = json.loads(Path("Data/data/interim/triageiq_training_v3.manifest.json").read_text())
t = run["test"]

card = {
    "model_version": "triageiq-fusion-distilbert-v3",
    "what_it_predicts": "the chance that a CFPB complaint ends in 'Closed with monetary relief' (the company pays)",
    "model": "DistilBERT (distilbert-base-uncased, fine-tuned) reads the complaint text; a small network reads "
             "19 point-in-time track-record inputs computed in SQL; one head combines both",
    "trained_on": {"complaints": man["rows"]["train"], "payouts": man["payouts"]["train"],
                   "period": "2022-04-01 .. 2023-09-30",
                   "sampling": "every payout + 3 non-payouts each (case-control); corrected afterwards"},
    "tested_on_2024": {
        "complaints": run["n_test"], "payouts": run["test_payouts"],
        "within_company_auc": round(t["within_company_auc"], 4),
        "within_company_auc_95pct_range": [round(x, 3) for x in run["within_company_ci95"]],
        "within_product_and_issue_auc": round(t["within_strata_auc"], 4),
        "pr_auc": round(t["pooled_pr"], 4),
        "riskiest_10pct_catches_share_of_payouts": round(run["recall_at"]["top_10pct"], 3),
    },
    "calibration": {k: cal["calibration"][k] for k in ("method", "offset", "a", "b", "fit_on")},
    "routing": {"senior_threshold_probability": round(cal["calibration"]["senior_threshold_p"], 4),
                "rule": cal["calibration"]["senior_rule"],
                "in_2024_senior_group_payout_rate": round(cal["deployed_on_2024"]["payout_rate_in_senior"], 4),
                "in_2024_template_group_payout_rate": round(cal["deployed_on_2024"]["payout_rate_in_template"], 4)},
    "data_ends": "2024-12-31",
    "features_as_of": "2025-01-01",
    "limits": [
        "Track records are frozen at the end of 2024: a new complaint is scored as if it arrived on 2025-01-01.",
        "The label is company cost (money paid), not how badly the consumer was harmed.",
        "Inside one company the model ranks about 82 of 100 payout/non-payout pairs correctly; many misses are "
        "company decisions that the complaint text cannot show.",
        "The model learned from complaints as the CFPB publishes them: amounts written as {$35.00}, private details "
        "hidden as XXXX. Typed text in another style is still scored, but is less like what it learned from.",
    ],
}
(OUT / "model_card.json").write_text(json.dumps(card, indent=1))
print(json.dumps(card["tested_on_2024"]), card["routing"]["senior_threshold_probability"])
