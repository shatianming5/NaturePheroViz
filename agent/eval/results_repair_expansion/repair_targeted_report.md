# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 33   rounds budget N=3   models=['gpt-5.4', 'claude-opus-4.8', 'gpt-5.5']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 4/33 (12% [5-27]) | 1.48 | 1.48 | 6/33 (18%) | 0/33 (0%) |
| targeted | 22/33 (67% [50-80]) | 1.30 | 1.30 | 3/33 (9%) | 0/33 (0%) |
| ceiling | 28/33 (85% [69-93]) | 1.21 | 1.21 | 0/33 (0%) | 0/33 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 4/33 (12%) | 23 | 0 | 0 | 6 | 4 |
| targeted | 3/33 (9%) | 0 | 25 | 0 | 5 | 3 |
| ceiling | 3/33 (9%) | 0 | 0 | 28 | 2 | 3 |

## per-family success (targeted vs generic vs ceiling)
| operator | generic | targeted | ceiling |
|---|---|---|---|
| dtype_coerce | 1/3 | 2/3 | 3/3 |
| groupby_dropna_key | 0/6 | 6/6 | 6/6 |
| index_align | 0/6 | 0/6 | 6/6 |
| join_fanout | 0/2 | 2/2 | 2/2 |
| resample_boundary | 0/4 | 2/4 | 1/4 |
| scale_before_split_leakage | 0/6 | 4/6 | 6/6 |
| string_normalize_join | 3/6 | 6/6 | 4/6 |

## go/no-go gate
- targeted success 67% [50-80] vs generic 12% [5-27] (CIs disjoint) -> PASS
- targeted over-repair rate 9% <= 10% (abs threshold): PASS
- rounds not increased: PASS
- no SIGNIFICANT per-family regression (disjoint CIs): PASS
- **VERDICT: GO (upgrade repair main line)**
