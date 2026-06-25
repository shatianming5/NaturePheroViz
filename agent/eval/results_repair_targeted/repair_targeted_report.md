# Experiment 1 — generic vs targeted vs gold-diff repair  [OFFLINE STUB — plumbing only, NOT a result]

usable silent starts: 24   rounds budget N=3   models=['stub']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 0/24 (0% [0-14]) | 1.00 | 1.00 | 0/24 (0%) | 0/24 (0%) |
| targeted | 24/24 (100% [86-100]) | 1.00 | 1.00 | 0/24 (0%) | 0/24 (0%) |
| ceiling | 24/24 (100% [86-100]) | 1.00 | 1.00 | 0/24 (0%) | 0/24 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 0/24 (0%) | 24 | 0 | 0 | 0 | 0 |
| targeted | 0/24 (0%) | 0 | 24 | 0 | 0 | 0 |
| ceiling | 0/24 (0%) | 0 | 0 | 24 | 0 | 0 |

## per-family success (targeted vs generic vs ceiling)
| operator | generic | targeted | ceiling |
|---|---|---|---|
| cumcount_per_group | 0/2 | 2/2 | 2/2 |
| cumulative_running | 0/2 | 2/2 | 2/2 |
| dedup_then_agg | 0/2 | 2/2 | 2/2 |
| median_not_mean | 0/2 | 2/2 | 2/2 |
| nan_as_zero_sum | 0/2 | 2/2 | 2/2 |
| pct_point | 0/2 | 2/2 | 2/2 |
| pooled_rate | 0/2 | 2/2 | 2/2 |
| proportion_true | 0/2 | 2/2 | 2/2 |
| rank_pct | 0/2 | 2/2 | 2/2 |
| weighted_mean | 0/2 | 2/2 | 2/2 |
| within_group_share | 0/2 | 2/2 | 2/2 |
| zscore_within_group | 0/2 | 2/2 | 2/2 |

## go/no-go gate
- targeted success 100% [86-100] vs generic 0% [0-14] (CIs disjoint) -> PASS
- targeted over-repair rate 0% <= 10% (abs threshold): PASS
- rounds not increased: PASS
- no SIGNIFICANT per-family regression (disjoint CIs): PASS
- **VERDICT: GO (upgrade repair main line)   [stub — verdict is illustrative only]**
