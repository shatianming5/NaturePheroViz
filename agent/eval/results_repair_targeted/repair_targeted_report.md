# Experiment 1 — generic vs targeted vs gold-diff repair  [ONLINE — real LLM, canonical]

> Canonical source: real online run at `results_repair_expanded/` (offline=false).
> N=87 silent starts · 3 models (gpt-4o + claude-sonnet-4.6 + gemini-3.5-flash) · budget N=3 rounds.
> (Prior 24-case "stub" run was offline plumbing; superseded.)

| arm | success [95% Wilson CI] | mean rounds | over-repair new-fire | over-repair broke-correct |
|---|---|---|---|---|
| generic  | 16/87 (18% [12-28]) | 1.34 | 0/87 (0%) | 0/87 (0%) |
| targeted | 70/87 (80% [71-87]) | 1.10 | 3/87 (3%) | 0/87 (0%) |
| ceiling (gold-diff) | 70/87 (80% [71-87]) | 1.33 | 2/87 (2%) | 0/87 (0%) |

targeted == ceiling: goldless typed feedback reaches the gold-diff upper bound.

## go/no-go gate
- targeted 80% [71-87] vs generic 18% [12-28] — CIs disjoint -> PASS
- over-repair 3% <= 10%, broke-correct 0% -> PASS; rounds not increased -> PASS
- per-family: 1 family within-noise (zscore_within_group targeted 1/8 vs generic 2/8,
  CIs overlap; pre-declared §3.7 blind spot) — disclosed, not vetoed.
- **VERDICT: GO** (online; targeted == gold-diff ceiling). Honest caveat: zscore unhelped.
