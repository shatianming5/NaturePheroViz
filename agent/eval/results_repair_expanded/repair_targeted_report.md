# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 87   rounds budget N=3   models=['(resummarized)']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 16/87 (18% [12-28]) | 1.34 | 1.34 | 0/87 (0%) | 0/87 (0%) |
| targeted | 70/87 (80% [71-87]) | 1.10 | 1.10 | 3/87 (3%) | 0/87 (0%) |
| ceiling | 70/87 (80% [71-87]) | 1.33 | 1.33 | 2/87 (2%) | 0/87 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 8/87 (9%) | 71 | 0 | 0 | 8 | 8 |
| targeted | 0/87 (0%) | 0 | 83 | 0 | 4 | 0 |
| ceiling | 3/87 (3%) | 0 | 0 | 70 | 14 | 3 |

## per-family success (targeted vs generic vs ceiling)
| operator | generic | targeted | ceiling |
|---|---|---|---|
| clip_outlier | 4/8 | 8/8 | 6/8 |
| count_includes_empty | 0/12 | 8/12 | 8/12 |
| cumcount_per_group | 2/2 | 2/2 | 2/2 |
| dedup_then_agg | 0/12 | 10/12 | 9/12 |
| dense_rank | 0/10 | 6/10 | 8/10 |
| median_not_mean | 3/3 | 3/3 | 3/3 |
| pct_point | 0/12 | 12/12 | 6/12 |
| topn_with_ties | 0/12 | 12/12 | 12/12 |
| within_group_share | 5/8 | 8/8 | 8/8 |
| zscore_within_group | 2/8 | 1/8 | 8/8 |

## go/no-go gate
- targeted success 80% [71-87] vs generic 18% [12-28] (CIs disjoint) -> PASS
- targeted over-repair rate 3% <= 10% (abs threshold): PASS
- rounds not increased: PASS
- no SIGNIFICANT per-family regression (disjoint CIs): PASS
  - raw non-wins (within noise, CIs overlap; e.g. §3.7 blind spots): ['zscore_within_group']
- **VERDICT: GO (upgrade repair main line)**
