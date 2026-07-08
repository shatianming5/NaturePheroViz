# End-to-end scale + miss decomposition (cross-vendor)

Pooled N = 115 (5 vendors x ~23 operators). Generated-fixture path (real Nature corpus not required); messy NL cached & shared across vendors for a fair comparison.

## Per-vendor

| vendor | N | op-infer | contract-synth CORE | full-system |
|---|---|---|---|---|
| gpt-5.3-codex | 23 | 18/23 = 78.3% [58.1-90.3] | 18/23 = 78.3% [58.1-90.3] | 15/23 = 65.2% [44.9-81.2] |
| gemini-3.1-pro-preview | 23 | 18/23 = 78.3% [58.1-90.3] | 15/23 = 65.2% [44.9-81.2] | 11/23 = 47.8% [29.2-67.0] |
| gpt-5.4 | 23 | 18/23 = 78.3% [58.1-90.3] | 16/23 = 69.6% [49.1-84.4] | 12/23 = 52.2% [33.0-70.8] |
| gpt-5.5 | 23 | 19/23 = 82.6% [62.9-93.0] | 18/23 = 78.3% [58.1-90.3] | 16/23 = 69.6% [49.1-84.4] |
| claude-opus-4.8 | 23 | 19/23 = 82.6% [62.9-93.0] | 14/23 = 60.9% [40.8-77.8] | 12/23 = 52.2% [33.0-70.8] |
| **POOLED** | **115** | **92/115 = 80.0% [71.8-86.3]** | **81/115 = 70.4% [61.5-78.0]** | **66/115 = 57.4% [48.3-66.0]** |

Contract-synth CORE *given the operator is correct*: 66/92 = 71.7% [61.8-79.9] (isolates the synthesis stage from operator inference).

## Where the end-to-end miss comes from (decomposition)

Of 49 full-system misses (pooled), split by failing stage:

| failing stage | count | share of misses |
|---|---|---|
| operator-inference only (contract would fire) | 15 | 31% |
| contract-synthesis only (operator correct) | 26 | 53% |
| both stages fail | 8 | 16% |

## Per-operator miss attribution (pooled)

| operator | trials | full-ok | dominant failure |
|---|---|---|---|
| count_includes_empty | 5 | 5/5 | - |
| cumulative_running | 5 | 5/5 | - |
| dedup_then_agg | 5 | 5/5 | - |
| dtype_coerce | 5 | 0/5 | BOTH |
| groupby_dropna_key | 5 | 4/5 | SYNTH_only |
| index_align | 5 | 0/5 | OP_only |
| join_fanout | 5 | 0/5 | OP_only |
| latlon_swap | 5 | 1/5 | OP_only |
| left_join_keep_all | 5 | 3/5 | SYNTH_only |
| lookahead_return | 5 | 1/5 | SYNTH_only |
| median_not_mean | 5 | 2/5 | SYNTH_only |
| nan_as_zero_sum | 5 | 4/5 | OP_only |
| null_in_agg_count | 5 | 1/5 | OP_only |
| order_dependent_dedup | 5 | 5/5 | - |
| pct_point | 5 | 0/5 | SYNTH_only |
| pooled_rate | 5 | 5/5 | - |
| proportion_true | 5 | 5/5 | - |
| resample_boundary | 5 | 2/5 | SYNTH_only |
| scale_before_split_leakage | 5 | 2/5 | SYNTH_only |
| string_normalize_join | 5 | 3/5 | SYNTH_only |
| topn_with_ties | 5 | 4/5 | SYNTH_only |
| weighted_mean | 5 | 5/5 | - |
| within_group_share | 5 | 4/5 | SYNTH_only |
