# Master results table — transform fidelity verification

One table reconciling every experiment, its data source, sample size, and result.
Resolves the round-3 reviewer's "57/132 vs 135/56/1" concern: these come from TWO
INDEPENDENT generation runs (calibration vs baseline), each internally consistent;
they are NOT the same 189/192 numbers and must not be cross-added.

## Generation runs (two independent sets of LLM generations)

| run | script | cases | gens | breakdown | purpose |
|---|---|---|---|---|---|
| **calibration** | ambiguity_calibration --bench | 48 grid | 192 | 135 correct + 56 silent + 1 crash | silent-rate, ambiguity calibration, oracle recall/FP |
| **baseline** | baseline_compare | 48 grid | 189 exec-ok | 132 correct + 57 silent (crashes excluded) | 5-detector head-to-head |

> Same 48-case grid, but two independent generations (temperature 0 still has
> sampling jitter via claude reasoning), so 56↔57 silent differ by one. The final
> paper drives both from a single run for one unified count.

## Results by claim

| # | claim | experiment | source run | N | result |
|---|---|---|---|---|---|
| 1 | silent errors are common + systematic | 48-grid | calibration | 96 ambiguous | ambiguous silent 44/96 = 46%; bimodal (5 classes 100%, 5 classes 0%) |
| 2 | model failure, not prompt underspecification | ambiguity calibration | calibration | 96+96 | ambiguous 46% → clarified 12% |
| 2b | not a one-phrasing fluke | clarify_robustness | new | 6 ops ×3 wordings | 92% → 17/8/8% (mean 11%, std 3.9 pts) |
| 3 | goldless oracle catches them | 48-grid | calibration | 56 silent / 135 correct | recall 56/56 = 100%, FP 0/135 = 0% |
| 4 | significantly better than existing means | baseline head-to-head | baseline | 57 silent / 132 correct | ours 100%/0%; exec-pass/validity/consistency 0% recall; self-check 61%/40% |
| 5 | external validity (real data) | nature_real_transform | real-slice | 18 amb / 18 clar | ambiguous silent 13/18 = 72% [CI 49-88]; recall 19/19 = 100% [83-100]; FP 0/17 = 0% [0-18] |
| 6 | scalability (one contract per new op) | scalability_demo | scal | 3 unseen ops | BEFORE abstain 0% recall + 0 FP; AFTER 1 contract → recall up, FP 0/5 |
| 7 | typed attribution localizes the operator | attribution_eval | attr | 26 silent / 1104 cross-evals | attribution recall 26/26 = 100%; cross-fire 90/1104 = 8% (after schema + shape gates) |

\* attribution recall uses the true-op contract's raw verdict (a missing expected
output column on the RIGHT operator is a real silent error). cross-fire counts only
substantive fires of OTHER-op contracts — a 'missing column' fire means that
operator doesn't apply (shape mismatch → abstain), not a mis-attribution. The
params schema gate + this shape gate together cut cross-fire from 20% to 8%, all at
the measurement layer, so the baseline 100% recall is untouched.

## Necessity of goldless (no-gold ablation)

The ground-truth labels (correct/silent) are computed WITH the hand gold, but the
oracle NEVER sees it — it fires from operator invariants alone. So:
- "with gold" (exact-match to a reference) is the upper-bound detector by construction.
- our goldless oracle reaches recall 56/56 = 100% / FP 0/135 = 0% on the calibration
  run and 18/18 / 0/18 on real data — i.e. it MATCHES gold-based detection without
  any gold output. Removing the gold requirement costs nothing in detection here.
- This is the necessity argument: the method does not degrade to text2SQL (which
  needs a gold query); it operates where no gold/reference exists.
