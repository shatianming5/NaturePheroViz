# Experiment 2a — abstain-aware repair routing (C3)  [OFFLINE STUB]

N=14  rounds=3  uncovered(simulated)=['zscore_within_group', 'dense_rank', 'cumcount_per_group', 'rank_pct', 'clip_outlier']

| policy | covered success | covered over-repair | UNCOVERED success | UNCOVERED over-repair |
|---|---|---|---|---|
| generic | 0/9 (0%) | 0/9 (0%) | 0/5 (0%) | 0/5 (0%) |
| force | 9/9 (100%) | 0/9 (0%) | 5/5 (100%) | 0/5 (0%) |
| route | 9/9 (100%) | 0/9 (0%) | 0/5 (0%) | 0/5 (0%) |

## reading (data-driven)
- COVERED: route success 100% == force 100% (route==targeted on covered) — OK.
- UNCOVERED: force success 100% / over-repair 0%; route success 0% / over-repair 0%; generic success 0%.
- => abstain-routing did NOT show a repair-time safety benefit here: forcing targeted feedback on uncovered operators did not raise the (proxy) over-repair and did not lose success (force 100% vs route 0%). HONEST READ: the over_a proxy (new fires of still-covered contracts) under-measures mis-repair on uncovered ops, and degraded targeted feedback was not harmful in this set. The abstain value is therefore a DETECTION-time property (FP≈0 on uncovered, §3.7), NOT a demonstrated repair-time gain — C3 stays exploratory, not a claim.
