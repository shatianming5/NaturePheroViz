# Expansion operators — REAL Nature-data prevalence

Real Nature source-data tables (same pipeline as the 77% headline, nature_real_auto._build expansion=True). 12 tasks across 10 independent articles x 2 prompts x 2 models = 48 generations. Models=['opencode/big-pickle', 'opencode/deepseek-v4-flash-free']. 95% Wilson CIs.

## Headline (pooled)
- ambiguous silent rate (REAL data): 13/24 = 54% [35-72]
- clarified silent rate: 8/24 = 33% [18-53]
- oracle FALSE-POSITIVE on real-correct results: 0/27 = 0% [0-12]
- oracle recall vs strict gold label: 11/21 = 52% [32-72]
- exec crashes (excluded): 0 of 48

## Per-model
| model | ambiguous silent | clarified silent | oracle FP | crash |
|---|---|---|---|---|
| opencode/big-pickle | 7/12 = 58% [32-81] | 3/12 = 25% [9-53] | 0/14 (0%) | 0 |
| opencode/deepseek-v4-flash-free | 6/12 = 50% [25-75] | 5/12 = 42% [19-68] | 0/13 (0%) | 0 |

## Per-operator (pooled)
| operator | real tasks | ambiguous silent | oracle recall | oracle FP | crash |
|---|---|---|---|---|---|
| groupby_dropna_key | 6 | 12/12 (100%) | 10/20 (50%) | 0/4 (0%) | 0 |
| null_in_agg_count | 6 | 1/12 (8%) | 1/1 (100%) | 0/23 (0%) | 0 |