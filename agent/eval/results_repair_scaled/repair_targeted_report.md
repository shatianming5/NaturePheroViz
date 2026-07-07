# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 65   rounds budget N=3   models=['gpt-5.4', 'gpt-5.5', 'gpt-5.3-codex', 'gemini-3.1-pro-preview']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 12/65 (18% [11-30]) | 1.62 | 1.62 | 0/65 (0%) | 0/65 (0%) |
| selfdebug | 8/65 (12% [6-22]) | 1.38 | 1.38 | 0/65 (0%) | 0/65 (0%) |
| localize | 34/65 (52% [40-64]) | 1.65 | 1.65 | 0/65 (0%) | 0/65 (0%) |
| targeted | 49/65 (75% [64-84]) | 1.08 | 1.08 | 2/65 (3%) | 0/65 (0%) |
| ceiling | 60/65 (92% [83-97]) | 1.12 | 1.12 | 4/65 (6%) | 0/65 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 2/65 (3%) | 48 | 0 | 0 | 15 | 2 |
| selfdebug | 1/65 (2%) | 60 | 0 | 0 | 4 | 1 |
| localize | 0/65 (0%) | 0 | 45 | 0 | 20 | 0 |
| targeted | 0/65 (0%) | 0 | 64 | 0 | 1 | 0 |
| ceiling | 1/65 (2%) | 0 | 0 | 60 | 4 | 1 |

## per-family success (generic vs selfdebug vs localize vs targeted vs ceiling)
| operator | generic | selfdebug | localize | targeted | ceiling |
|---|---|---|---|---|---|
| dedup_then_agg | 0/12 | 0/12 | 4/12 | 11/12 | 9/12 |
| dense_rank | 2/8 | 0/8 | 3/8 | 3/8 | 8/8 |
| median_not_mean | 1/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| pct_point | 0/11 | 0/11 | 4/11 | 11/11 | 11/11 |
| topn_with_ties | 0/12 | 0/12 | 8/12 | 12/12 | 12/12 |
| weighted_mean | 0/3 | 2/3 | 3/3 | 3/3 | 2/3 |
| within_group_share | 5/5 | 2/5 | 5/5 | 5/5 | 5/5 |
| zscore_within_group | 4/12 | 2/12 | 5/12 | 2/12 | 11/12 |

## go/no-go gate
- **[PRIMARY] targeted 75% [64-84] vs STRONG self-debug 12% [6-22] (CIs disjoint)** -> PASS
- **[ABLATION] targeted 75% vs localization-only 52% [40-64] (CIs overlap)** -> invariant adds +23 pts (if disjoint, the TYPED INVARIANT — not just localization — is necessary)
- [floor] targeted vs generic 18% [11-30] -> PASS
- targeted over-repair rate 3% <= 10% (abs threshold): PASS
- targeted mean rounds 1.08 within budget N=3 (self-debug quits early @ 1.38): PASS
- no SIGNIFICANT per-family regression vs self-debug (disjoint CIs): PASS
- **VERDICT: GO (upgrade repair main line)**
