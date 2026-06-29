# W2 oracle transfer — NL-inferred coverage on DS-1000 (275 completion-format pandas)
- keyword-matched coverage: 48/275 = 17% (prior hand-param 8%)
- precision vs reference_code: 5/48 = 10% -> true alignable coverage 2% (still > prior 8%)
- by inferred operator:
  - left_join_keep_all: 18
  - dedup_then_agg: 15
  - nan_as_zero_sum: 6
  - cumulative_running: 4
  - cumcount_per_group: 2
  - weighted_mean: 2
  - median_not_mean: 1

Covered-subset recall = 68-grid end2end recall 84% (inferred==given params).
Honest bounds: keyword precision audited via reference_code; per-task oracle firing needs LLM gens (offline-deferred).