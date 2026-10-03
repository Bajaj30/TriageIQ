# tests — hand-verified checks: compute a feature by hand for one company, compare with the query

- `03_volume_check.sql` — recounts 22 complaints (20 random + both ends of the busiest company-day) with plain `WHERE … BETWEEN`; all 22 PASS. ✅
- `04_outcome_rates_check.sql` — (A) recounts 21 complaints with plain `date <= d - 60`, 21/21; (B) **leak test**: flips one company-day's answers inside BEGIN…ROLLBACK — day 0 and day 59 unchanged, day 60 changed, 3/3. ✅
- `06_sequence_check.sql` — recounts 22 complaints with a plain row comparison `(date, id) < (d, id)`; busiest day: first gets gap 1, last gets 0, ranks 4,244 apart; 22/22. ✅
- `07_trends_check.sql` — recounts the 91–180-day windows and national 90-day volume, rebuilds trends and shares; 21/21. ✅
- `06_serving_check.sql` — **skew test**: snapshot built as of 3 past days (2022-03-15 warm-up, 2023-08-28 form change, 2024-12-10 busiest), 20,773 complaints through `serving.model_input` vs `v_model_input`: 19/19 inputs PASS, max difference 0 (incl. 57 no-company-history, 21 first-ever, ~19,855 same-day ties). ✅
