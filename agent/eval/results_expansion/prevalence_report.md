# Expansion operators — REAL-LLM silent-error prevalence (cross-model)

Generator: opencode ['opencode/north-mini-code-free', 'opencode/deepseek-v4-flash-free', 'opencode/mimo-v2.5-free'] (attempts=2). 20 cases x 2 prompts x 3 models = 120 generations. Same protocol as ambiguity_calibration (generate -> exec -> label vs gold -> goldless oracle). 95% Wilson CIs.

## Headline (pooled across models)
- ambiguous silent rate: 34/60 = 57% [44-68]
- clarified silent rate: 11/60 = 18% [11-30] (drop => genuine model semantic failure, fixable by intent)
- oracle FALSE-POSITIVE on real-correct results: 0/69 = 0% [0-5] (the trustworthy oracle-quality metric)
- oracle recall vs strict gold label: 36/45 = 80% [66-89] (understated by gold-format artifacts — see EXPANSION_SUMMARY)
- exec crashes (loud, excluded from silent): 6 of 120

## Per-model (is the phenomenon model-specific?)
| model | ambiguous silent | clarified silent | oracle FP | crash |
|-------|------------------|------------------|-----------|-------|
| opencode/north-mini-code-free | 11/20 = 55% [34-74] | 4/20 = 20% [8-42] | 0/21 (0%) | 4 |
| opencode/deepseek-v4-flash-free | 11/20 = 55% [34-74] | 4/20 = 20% [8-42] | 0/25 (0%) | 0 |
| opencode/mimo-v2.5-free | 12/20 = 60% [39-78] | 3/20 = 15% [5-36] | 0/23 (0%) | 2 |

## Per-operator (pooled across models)
| operator | ambiguous silent | clarified silent | oracle recall | oracle FP | crash |
|----------|------------------|------------------|---------------|-----------|-------|
| index_align | 6/6 (100%) | 0/6 (0%) | 6/6 (100%) | 0/6 (0%) | 0 |
| dtype_coerce | 1/6 (17%) | 1/6 (17%) | 2/2 (100%) | 0/10 (0%) | 0 |
| groupby_dropna_key | 6/6 (100%) | 3/6 (50%) | 6/9 (67%) | 0/3 (0%) | 0 |
| order_dependent_dedup | 0/6 (0%) | 1/6 (17%) | 1/1 (100%) | 0/11 (0%) | 0 |
| resample_boundary | 5/6 (83%) | 0/6 (0%) | 5/5 (100%) | 0/4 (0%) | 3 |
| string_normalize_join | 6/6 (100%) | 0/6 (0%) | 6/6 (100%) | 0/4 (0%) | 2 |
| join_fanout | 4/6 (67%) | 0/6 (0%) | 4/4 (100%) | 0/8 (0%) | 0 |
| null_in_agg_count | 0/6 (0%) | 0/6 (0%) | 0/0 (n/a) | 0/12 (0%) | 0 |
| scale_before_split_leakage | 6/6 (100%) | 6/6 (100%) | 6/12 (50%) | 0/0 (n/a) | 0 |
| lookahead_return | 0/6 (0%) | 0/6 (0%) | 0/0 (n/a) | 0/11 (0%) | 1 |