# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 43   rounds budget N=3   models=['(resummarized)']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 6/43 (14% [7-27]) | 1.37 | 1.37 | 0/43 (0%) | 0/43 (0%) |
| selfdebug | 2/43 (5% [1-15]) | 1.14 | 1.14 | 0/43 (0%) | 0/43 (0%) |
| targeted | 34/43 (79% [65-89]) | 1.19 | 1.19 | 0/43 (0%) | 0/43 (0%) |
| ceiling | 40/43 (93% [81-98]) | 1.14 | 1.14 | 2/43 (5%) | 0/43 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 5/43 (12%) | 32 | 0 | 0 | 6 | 5 |
| selfdebug | 8/43 (19%) | 35 | 0 | 0 | 0 | 8 |
| targeted | 0/43 (0%) | 0 | 41 | 0 | 2 | 0 |
| ceiling | 0/43 (0%) | 0 | 0 | 40 | 3 | 0 |

## per-family success (targeted vs selfdebug vs generic vs ceiling)
| operator | generic | selfdebug | targeted | ceiling |
|---|---|---|---|---|
| count_includes_empty | 0/6 | 0/6 | 4/6 | 4/6 |
| dedup_then_agg | 0/6 | 0/6 | 6/6 | 5/6 |
| dense_rank | 1/6 | 0/6 | 5/6 | 6/6 |
| median_not_mean | 1/2 | 1/2 | 2/2 | 2/2 |
| pct_point | 0/6 | 0/6 | 6/6 | 6/6 |
| topn_with_ties | 0/6 | 0/6 | 6/6 | 6/6 |
| weighted_mean | 0/2 | 0/2 | 2/2 | 2/2 |
| within_group_share | 3/3 | 1/3 | 3/3 | 3/3 |
| zscore_within_group | 1/6 | 0/6 | 0/6 | 6/6 |

## go/no-go gate
- **[PRIMARY] targeted 79% [65-89] vs STRONG self-debug 5% [1-15] (CIs disjoint)** -> PASS
- [floor] targeted vs generic 14% [7-27] -> PASS
- targeted over-repair rate 0% <= 10% (abs threshold): PASS
- targeted mean rounds 1.19 within budget N=3 (self-debug quits early @ 1.14): PASS
- no SIGNIFICANT per-family regression vs self-debug (disjoint CIs): PASS
- **VERDICT: GO (upgrade repair main line)**
