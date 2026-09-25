# 04_training_set — Stage 2: the funnel, AFTER features exist
has narrative -> quality filters -> temporal split -> case-control sample.
Target: train 71,460 · val 80,000 · test 150,000 (Context/FACTS.md).
Sampling must be deterministic — hash of complaint_id, never random().
