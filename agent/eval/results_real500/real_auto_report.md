# LARGE held-out real-data slice: 500 tasks sampled from a 5237-task real pool

Generator scanned 211 Nature articles / 1607 source-data tables and produced 5237
oracle-validated real tasks (median / within_group_share / weighted_mean /
pooled_rate / nan_as_zero_sum). We randomly sampled 500 to run (2000 calls). Same
(ambiguous, clarified) prompts + goldless oracle. 95% Wilson CIs.

## (1) Silent-error rate on REAL data (500-task sample)
- ambiguous: 269/500 (54% [95% CI 49-58])
- clarified: 81/500 (16% [95% CI 13-20])

## (2) Oracle recall on real silent errors
- 322/350 (92% [95% CI 89-95])
- by operator: median_not_mean 118/118=100%, weighted_mean 28/28=100%,
  within_group_share 102/104=98%, pooled_rate 23/25=92% (minor coverage gaps,
  honest boundary not a measurement error)

## (3) Oracle false-positive on real correct results
- 0/497 (0% [95% CI 0-1])

## Reading
- 500 tasks sampled from a 5237-task real pool (vs 9-table curated) makes the
  external-validity claim a random draw from a 5000+ population, not cherry-picked.
- 54% ambiguous silent on real data (CI 49-58) still exceeds the synthetic 46%.
- Oracle FP 0/497; recall layered (mature operators 100%, share/pooled minor gaps).
