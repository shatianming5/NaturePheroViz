# Expansion operators — REAL-LLM silent-error prevalence (cross-model)

Generator: ['gpt-5.4', 'claude-opus-4.8', 'gpt-5.3-codex', 'gemini-3.1-pro-preview', 'gpt-5.5'] (attempts=2). 20 cases x 2 prompts x 5 models = 200 generations. Same protocol as ambiguity_calibration (generate -> exec -> label vs gold -> goldless oracle). 95% Wilson CIs.

## Headline (pooled across models)
- ambiguous silent rate: 53/100 = 53% [43-62]
- clarified silent rate: 20/100 = 20% [13-29] (drop => genuine model semantic failure, fixable by intent)
- oracle FALSE-POSITIVE on real-correct results: 0/119 = 0% [0-3] (the trustworthy oracle-quality metric)
- oracle recall vs strict gold label: 51/73 = 70% [59-79] (understated by gold-format artifacts — see EXPANSION_SUMMARY)
- exec crashes (loud, excluded from silent): 8 of 200

## Per-model (is the phenomenon model-specific?)
| model | ambiguous silent | clarified silent | oracle FP | crash |
|-------|------------------|------------------|-----------|-------|
| gpt-5.4 | 11/20 = 55% [34-74] | 4/20 = 20% [8-42] | 0/21 (0%) | 4 |
| claude-opus-4.8 | 11/20 = 55% [34-74] | 6/20 = 30% [15-52] | 0/23 (0%) | 0 |
| gpt-5.3-codex | 11/20 = 55% [34-74] | 4/20 = 20% [8-42] | 0/23 (0%) | 2 |
| gemini-3.1-pro-preview | 8/20 = 40% [22-61] | 2/20 = 10% [3-30] | 0/28 (0%) | 2 |
| gpt-5.5 | 12/20 = 60% [39-78] | 4/20 = 20% [8-42] | 0/24 (0%) | 0 |

## Per-operator (pooled across models)
| operator | ambiguous silent | clarified silent | oracle recall | oracle FP | crash |
|----------|------------------|------------------|---------------|-----------|-------|
| index_align | 10/10 (100%) | 0/10 (0%) | 10/10 (100%) | 0/10 (0%) | 0 |
| dtype_coerce | 6/10 (60%) | 6/10 (60%) | 4/12 (33%) | 0/8 (0%) | 0 |
| groupby_dropna_key | 10/10 (100%) | 2/10 (20%) | 10/12 (83%) | 0/8 (0%) | 0 |
| order_dependent_dedup | 0/10 (0%) | 0/10 (0%) | 0/0 (n/a) | 0/20 (0%) | 0 |
| resample_boundary | 5/10 (50%) | 2/10 (20%) | 5/7 (71%) | 0/5 (0%) | 8 |
| string_normalize_join | 10/10 (100%) | 0/10 (0%) | 10/10 (100%) | 0/10 (0%) | 0 |
| join_fanout | 2/10 (20%) | 0/10 (0%) | 2/2 (100%) | 0/18 (0%) | 0 |
| null_in_agg_count | 0/10 (0%) | 0/10 (0%) | 0/0 (n/a) | 0/20 (0%) | 0 |
| scale_before_split_leakage | 10/10 (100%) | 10/10 (100%) | 10/20 (50%) | 0/0 (n/a) | 0 |
| lookahead_return | 0/10 (0%) | 0/10 (0%) | 0/0 (n/a) | 0/20 (0%) | 0 |