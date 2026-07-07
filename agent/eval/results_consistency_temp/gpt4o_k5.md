# Consistency baseline at temperature 0.8 (K=5, model=gpt-4o)

Silent (wrong): 38 | correct: 95 | tasks with >1 distinct sample: 10/133 (8%) — confirms samples are genuinely diverse at temp>0.

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| consistency @T=0.8 | 0/38 (0%) | 0/95 (0%) |
| consistency @T=0 (head-to-head baseline) | 0% (by construction: identical samples) | 0% |

## Reading
- At T=0.8 the K samples ARE diverse (8% of tasks show >1 distinct output),
  so this is a faithful CodeT/self-consistency test, not a temp-0 artifact.
- Consistency recall is 0%: if ~0%, the silent errors are COMMON-MODE (the
  diverse samples still agree on the WRONG answer) — a stronger 'invisible' result than temp-0;
  if high, the earlier 0% was a temp-0 artifact and should be revised.
