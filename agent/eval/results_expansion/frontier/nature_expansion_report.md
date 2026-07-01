# Expansion operators — REAL Nature-data prevalence

Real Nature source-data tables (same pipeline as the 77% headline, nature_real_auto._build expansion=True). 12 tasks across 10 independent articles x 2 prompts x 2 models = 48 generations. Models=['claude-opus-4.8', 'gpt-5.4']. 95% Wilson CIs.

## Headline (pooled)
- ambiguous silent rate (REAL data): 13/24 = 54% [35-72]
- clarified silent rate: 12/24 = 50% [31-69]
- oracle FALSE-POSITIVE on real-correct results: 0/23 = 0% [0-14]
- oracle recall vs strict gold label: 10/25 = 40% [23-59]
- exec crashes (excluded): 0 of 48

## Per-model
| model | ambiguous silent | clarified silent | oracle FP | crash |
|---|---|---|---|---|
| claude-opus-4.8 | 6/12 = 50% [25-75] | 8/12 = 67% [39-86] | 0/10 (0%) | 0 |
| gpt-5.4 | 7/12 = 58% [32-81] | 4/12 = 33% [14-61] | 0/13 (0%) | 0 |

## Per-operator (pooled)
| operator | real tasks | ambiguous silent | oracle recall | oracle FP | crash |
|---|---|---|---|---|---|
| groupby_dropna_key | 6 | 12/12 (100%) | 10/18 (56%) | 0/6 (0%) | 0 |
| null_in_agg_count | 6 | 1/12 (8%) | 0/7 (0%) | 0/17 (0%) | 0 |