# End-to-end scale + miss decomposition (cross-vendor)

Pooled N = 46 (2 vendors x ~23 operators). Generated-fixture path (real Nature corpus not required); messy NL cached & shared across vendors for a fair comparison.

## Per-vendor

| vendor | N | op-infer | contract-synth CORE | full-system |
|---|---|---|---|---|
| gemini-3.1-pro-preview | 23 | 18/23 = 78.3% [58.1-90.3] | 15/23 = 65.2% [44.9-81.2] | 11/23 = 47.8% [29.2-67.0] |
| gpt-5.4 | 23 | 18/23 = 78.3% [58.1-90.3] | 16/23 = 69.6% [49.1-84.4] | 12/23 = 52.2% [33.0-70.8] |
| **POOLED** | **46** | **36/46 = 78.3% [64.4-87.7]** | **31/46 = 67.4% [53.0-79.1]** | **23/46 = 50.0% [36.1-63.9]** |

Contract-synth CORE *given the operator is correct*: 23/36 = 63.9% [47.6-77.5] (isolates the synthesis stage from operator inference).

## Where the end-to-end miss comes from (decomposition)

Of 23 full-system misses (pooled), split by failing stage:

| failing stage | count | share of misses |
|---|---|---|
| operator-inference only (contract would fire) | 8 | 35% |
| contract-synthesis only (operator correct) | 13 | 57% |
| both stages fail | 2 | 9% |

## Per-operator miss attribution (pooled)

| operator | trials | full-ok | dominant failure |
|---|---|---|---|
| count_includes_empty | 2 | 2/2 | - |
| cumulative_running | 2 | 2/2 | - |
| dedup_then_agg | 2 | 2/2 | - |
| dtype_coerce | 2 | 0/2 | BOTH |
| groupby_dropna_key | 2 | 1/2 | SYNTH_only |
| index_align | 2 | 0/2 | OP_only |
| join_fanout | 2 | 0/2 | OP_only |
| latlon_swap | 2 | 0/2 | OP_only |
| left_join_keep_all | 2 | 1/2 | SYNTH_only |
| lookahead_return | 2 | 1/2 | SYNTH_only |
| median_not_mean | 2 | 0/2 | SYNTH_only |
| nan_as_zero_sum | 2 | 1/2 | OP_only |
| null_in_agg_count | 2 | 0/2 | OP_only |
| order_dependent_dedup | 2 | 2/2 | - |
| pct_point | 2 | 0/2 | SYNTH_only |
| pooled_rate | 2 | 2/2 | - |
| proportion_true | 2 | 2/2 | - |
| resample_boundary | 2 | 1/2 | SYNTH_only |
| scale_before_split_leakage | 2 | 0/2 | SYNTH_only |
| string_normalize_join | 2 | 1/2 | SYNTH_only |
| topn_with_ties | 2 | 1/2 | SYNTH_only |
| weighted_mean | 2 | 2/2 | - |
| within_group_share | 2 | 2/2 | - |
