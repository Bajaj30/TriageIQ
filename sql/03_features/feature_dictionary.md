# Feature dictionary — `mv_features` and `v_model_input`

Every feature is **known on the day the complaint arrived** — nothing after it. Built in
`sql/03_features/` over **all 4,826,564 complaints** (2022–2024), before any sampling.

- **`mv_features`** — the feature store: 40 stored columns, one row per complaint, 1.75 GB, built in ~80 s.
- **`v_model_input`** — the **19 columns the model reads**. Training export and API both read this view.
  To change the model's inputs, edit that view — nowhere else.
- The answer (`paid`) is **never** in either. It is joined only when the training set is built.

**Frames** (`CLAUDE.md` trap 1): **A** = outcomes, up to 60 days before arrival · **B** = arrivals, up to
the day before · **C** = order within a company, tiebreak `(date_received, complaint_id)`.

## The 19 model inputs

| # | column | what it says | built in | frame | why it's in |
|---|---|---|---|---|---|
| 1 | `product_id` | product (11 values) | fact | — | payout rates differ hugely by product |
| 2 | `sub_product_id` | sub-product (62) | fact | — | finer than product; stable across the Aug-2023 change (D12) |
| 3 | `issue_id` | issue (93, renames merged — D17) | fact | — | what the complaint is about |
| 4 | `state_id` | consumer's state (62) | fact | — | weak, but known at intake |
| 5 | `is_older_american` | tagged Older American (62+) | 02 | — | 10.08% payout vs 1.06% untagged (all complaints) |
| 6 | `is_servicemember` | tagged servicemember | 02 | — | 2.43% payout vs 1.06% |
| 7 | `company_no_history` | no known company outcome yet | 04 | A | "no history" ≠ "never pays" |
| 8 | `company_issue_no_history` | same, for company × issue | 04 | A | as above |
| 9 | `company_issue_rate_s` | company's payout rate **on this issue**, smoothed (K = 5) | 04–05 | A | the main unit; >15% history → 28.74% real payouts |
| 10 | `company_rate_s` | company's overall payout rate, smoothed | 04–05 | A | company habit across issues |
| 11 | `issue_rate_s` | this issue's payout rate across companies, smoothed | 04–05 | A | how "money-bearing" the problem type is |
| 12 | `product_rate_s` | product's payout rate (2021 fallback before any exists) | 04–05 | A | the smoothing prior, also a feature |
| 13 | `company_untimely_rate` | share of the company's complaints it never answered (0 if no history) | 04 | A | companies that ignore the regulator |
| 14 | `company_share_90d` | company's share of all complaints, last 90 days | 07 | B | busy-ness without the volume drift |
| 15 | `company_issue_share_90d` | company × issue share, last 90 days | 07 | B | a flood on one problem |
| 16 | `issue_share_90d` | this issue's share of all complaints, last 90 days | 07 | B | a system-wide problem spreading |
| 17 | `company_trend_90d` | ln((last 90 d + 1) / (the 90 before + 1)) | 07 | B | rising (+) or falling (−) — 0.69 = doubled |
| 18 | `issue_trend_90d` | same, for the issue | 07 | B | as above |
| 19 | `company_quiet_days` | days since the company's previous complaint (first ever: days since data start — a lower bound) | 06 | C | bursts vs quiet periods (weak) |

NULLs: only `*_share_90d` on 2022-01-01 (535 complaints — no earlier day exists).

## Stored, but NOT model inputs — and why

| column | why it's out |
|---|---|
| `company_id` | 4,946 values: the model would memorise companies and fail on new ones. The rates (9–13) carry company behaviour instead. |
| `sub_issue_id` | trap 10: for 4 issues a blank sub-issue means "filed before Aug 2023" — it would teach the date. |
| `date_received` | the calendar itself; used for the split, never as an input. |
| `company_n_prior`, `company_tenure_days`, `days_since_start` | **clocks**: they grow with calendar time (tenure = days since start for 91.68% of complaints). Test-year values are all out of the training range. |
| `company_n_30d`, `company_n_90d`, `company_issue_n_90d`, `issue_n_90d`, `national_n_7d`, `national_n_90d`, `company_n_prev_90d`, `issue_n_prev_90d` | raw counts **drift** with total volume (avg company 90-day count ×5.5 from 2022 to 2024). Kept as the building blocks of the shares and trends. |
| `company_n_known`, `company_issue_n_known`, `issue_n_known`, `product_n_known` | grow with calendar time too; how reliable a rate is, is already inside the smoothed rate. |
| `company_rank_this_month` | grows with monthly volume — drifts like the raw counts. |
| `days_since_prev_company_complaint` | raw version of #19 (NULL for a company's first complaint). |

## Known limits

- **Warm-up (early 2022):** outcome rates start with no history (14.07% of 2022 complaints have none),
  and trends read high until mid-2022 (the earlier 90-day window reaches before the data). Decide the
  first training date in `04_training_set`.
- **The 60-day lag is an assumption** — CFPB never records when a company answered (D15).
- **K = 5 was tuned on each rate alone**, one quarter of data — re-check inside the model (Phase 2).
- **REFRESH is manual:** `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_features;` after new data. Stale
  data is silent. Phase 3 automates it.
