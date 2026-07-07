# End-to-end scale + miss decomposition (cross-vendor)

Pooled N = 92 (4 vendors x ~23 operators). Generated-fixture path (real Nature corpus not required); messy NL cached & shared across vendors for a fair comparison.

## Per-vendor

| vendor | N | op-infer | contract-synth CORE | full-system |
|---|---|---|---|---|
| gpt-5.3-codex | 23 | 18/23 = 78.3% [58.1-90.3] | 18/23 = 78.3% [58.1-90.3] | 15/23 = 65.2% [44.9-81.2] |
| gemini-3.1-pro-preview | 23 | 18/23 = 78.3% [58.1-90.3] | 15/23 = 65.2% [44.9-81.2] | 11/23 = 47.8% [29.2-67.0] |
| gpt-5.4 | 23 | 18/23 = 78.3% [58.1-90.3] | 16/23 = 69.6% [49.1-84.4] | 12/23 = 52.2% [33.0-70.8] |
| gpt-5.5 | 23 | 19/23 = 82.6% [62.9-93.0] | 18/23 = 78.3% [58.1-90.3] | 16/23 = 69.6% [49.1-84.4] |
| **POOLED** | **92** | **73/92 = 79.3% [70.0-86.4]** | **67/92 = 72.8% [63.0-80.9]** | **54/92 = 58.7% [48.5-68.2]** |

Contract-synth CORE *given the operator is correct*: 54/73 = 74.0% [62.9-82.7] (isolates the synthesis stage from operator inference).

## Where the end-to-end miss comes from (decomposition)

Of 38 full-system misses (pooled), split by failing stage:

| failing stage | count | share of misses |
|---|---|---|
| operator-inference only (contract would fire) | 13 | 34% |
| contract-synthesis only (operator correct) | 19 | 50% |
| both stages fail | 6 | 16% |

## Per-operator miss attribution (pooled)

| operator | trials | full-ok | dominant failure |
|---|---|---|---|
| count_includes_empty | 4 | 4/4 | - |
| cumulative_running | 4 | 4/4 | - |
| dedup_then_agg | 4 | 4/4 | - |
| dtype_coerce | 4 | 0/4 | BOTH |
| groupby_dropna_key | 4 | 3/4 | SYNTH_only |
| index_align | 4 | 0/4 | BOTH |
| join_fanout | 4 | 0/4 | OP_only |
| latlon_swap | 4 | 0/4 | OP_only |
| left_join_keep_all | 4 | 2/4 | SYNTH_only |
| lookahead_return | 4 | 1/4 | SYNTH_only |
| median_not_mean | 4 | 2/4 | SYNTH_only |
| nan_as_zero_sum | 4 | 3/4 | OP_only |
| null_in_agg_count | 4 | 1/4 | OP_only |
| order_dependent_dedup | 4 | 4/4 | - |
| pct_point | 4 | 0/4 | SYNTH_only |
| pooled_rate | 4 | 4/4 | - |
| proportion_true | 4 | 4/4 | - |
| resample_boundary | 4 | 2/4 | SYNTH_only |
| scale_before_split_leakage | 4 | 2/4 | SYNTH_only |
| string_normalize_join | 4 | 3/4 | SYNTH_only |
| topn_with_ties | 4 | 3/4 | SYNTH_only |
| weighted_mean | 4 | 4/4 | - |
| within_group_share | 4 | 4/4 | - |
