# tests — hand-verified checks: compute a feature by hand for one company, compare with the query

- `03_volume_check.sql` — recounts 22 complaints (20 random + both ends of the busiest company-day) with plain `WHERE … BETWEEN`; all 22 PASS. ✅
- `04_outcome_rates_check.sql` — (A) recounts 21 complaints with plain `date <= d - 60`, 21/21; (B) **leak test**: flips one company-day's answers inside BEGIN…ROLLBACK — day 0 and day 59 unchanged, day 60 changed, 3/3. ✅
