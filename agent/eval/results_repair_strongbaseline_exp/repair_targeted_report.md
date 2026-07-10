# Experiment 1 — generic vs targeted vs gold-diff repair

usable silent starts: 7   rounds budget N=3   models=['gpt-5.4', 'claude-opus-4.8', 'gpt-5.5']

| arm | success [95% Wilson CI] | mean rounds | mean calls | over-repair(a) new-fire | over-repair(b) broke-correct |
|---|---|---|---|---|---|
| generic | 0/7 (0% [0-35]) | 1.29 | 1.29 | 6/7 (86%) | 0/7 (0%) |
| selfdebug | 0/7 (0% [0-35]) | 1.14 | 1.14 | 0/7 (0%) | 0/7 (0%) |
| targeted | 1/7 (14% [3-51]) | 2.71 | 2.71 | 6/7 (86%) | 0/7 (0%) |
| ceiling | 7/7 (100% [65-100]) | 1.00 | 1.00 | 0/7 (0%) | 0/7 (0%) |

## fairness telemetry (malformed rate + stop reasons)
| arm | malformed steps | stop: fixpoint | contract_pass | gold_match | budget | malformed |
|---|---|---|---|---|---|---|
| generic | 2/7 (29%) | 5 | 0 | 0 | 0 | 2 |
| selfdebug | 2/7 (29%) | 5 | 0 | 0 | 0 | 2 |
| targeted | 0/7 (0%) | 0 | 1 | 0 | 6 | 0 |
| ceiling | 0/7 (0%) | 0 | 0 | 7 | 0 | 0 |

## per-family success (targeted vs selfdebug vs generic vs ceiling)
| operator | generic | selfdebug | targeted | ceiling |
|---|---|---|---|---|
| dtype_coerce | 0/1 | 0/1 | 1/1 | 1/1 |
| index_align | 0/6 | 0/6 | 0/6 | 6/6 |

## go/no-go gate
- **[PRIMARY] targeted 14% [3-51] vs STRONG self-debug 0% [0-35] (CIs overlap)** -> PASS
- [floor] targeted vs generic 0% [0-35] -> PASS
- targeted over-repair rate 86% <= 10% (abs threshold): FAIL
- targeted mean rounds 2.71 within budget N=3 (self-debug quits early @ 1.14): PASS
- no SIGNIFICANT per-family regression vs self-debug (disjoint CIs): PASS
- **VERDICT: NO-GO (fall back to detection paper)**
