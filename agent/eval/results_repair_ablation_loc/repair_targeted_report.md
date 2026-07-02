# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 31   rounds budget N=3   models=['gpt-5.4', 'claude-opus-4.8', 'gpt-5.5']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 3/31 (10% [3-25]) | 1.16 | 1.16 | 0/31 (0%) | 0/31 (0%) |
| selfdebug | 1/31 (3% [1-16]) | 1.03 | 1.03 | 0/31 (0%) | 0/31 (0%) |
| localize | 14/31 (45% [29-62]) | 2.06 | 2.06 | 0/31 (0%) | 0/31 (0%) |
| targeted | 25/31 (81% [64-91]) | 1.16 | 1.16 | 3/31 (10%) | 0/31 (0%) |
| ceiling | 27/31 (87% [71-95]) | 1.26 | 1.26 | 2/31 (6%) | 0/31 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 3/31 (10%) | 26 | 0 | 0 | 2 | 3 |
| selfdebug | 3/31 (10%) | 28 | 0 | 0 | 0 | 3 |
| localize | 1/31 (3%) | 0 | 15 | 0 | 15 | 1 |
| targeted | 2/31 (6%) | 0 | 27 | 0 | 2 | 2 |
| ceiling | 1/31 (3%) | 0 | 0 | 27 | 3 | 1 |

## per-family success (generic vs selfdebug vs localize vs targeted vs ceiling)
| operator | generic | selfdebug | localize | targeted | ceiling |
|---|---|---|---|---|---|
| count_includes_empty | 0/6 | 0/6 | 1/6 | 4/6 | 5/6 |
| dedup_then_agg | 0/6 | 0/6 | 2/6 | 5/6 | 4/6 |
| median_not_mean | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| pct_point | 0/6 | 0/6 | 1/6 | 6/6 | 6/6 |
| topn_with_ties | 0/6 | 0/6 | 4/6 | 5/6 | 6/6 |
| weighted_mean | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 |
| within_group_share | 2/2 | 0/2 | 2/2 | 2/2 | 2/2 |
| zscore_within_group | 0/2 | 0/2 | 1/2 | 0/2 | 1/2 |

## go/no-go gate
- **[PRIMARY] targeted 81% [64-91] vs STRONG self-debug 3% [1-16] (CIs disjoint)** -> PASS
- **[ABLATION] targeted 81% vs localization-only 45% [29-62] (CIs disjoint)** -> invariant adds +35 pts (if disjoint, the TYPED INVARIANT — not just localization — is necessary)
- [floor] targeted vs generic 10% [3-25] -> PASS
- targeted over-repair rate 10% <= 10% (abs threshold): PASS
- targeted mean rounds 1.16 within budget N=3 (self-debug quits early @ 1.03): PASS
- no SIGNIFICANT per-family regression vs self-debug (disjoint CIs): PASS
- **VERDICT: GO (upgrade repair main line)**
