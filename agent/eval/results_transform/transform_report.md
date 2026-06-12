# LLM Data-Transform Errors: Silent vs Crash (go/no-go)

Trap/ambiguous transforms. Each cell = per-rep outcomes (ok / SILENT / crash).
**SILENT = code ran fine, result looks plausible, but is semantically WRONG** —
the failure mode that a verifier must catch (crashes are already visible).

| Case | gpt-4o | claude-sonnet-4.6 |
|---|---|---|
| weighted_mean_price | SILENT | crash |
| mom_growth_rate | ok | ok |
| share_within_group | SILENT | SILENT |
| left_join_keep_all | ok | ok |
| mean_skipna_with_count | crash | ok |
| dedup_then_sum | ok | ok |
| cumsum_within_group | SILENT | crash |
| top2_per_group | ok | crash |
| median_per_group | ok | ok |
| pct_point_change | SILENT | SILENT |
| count_with_zero_cats | SILENT | crash |
| running_balance | SILENT | SILENT |
| ctr_pooled | ok | SILENT |
| rank_keep_ties | ok | ok |
| sum_treat_nan_zero | ok | ok |
| pass_rate_per_group | ok | ok |
| **correct** | 56% | 50% |
| **SILENT semantic-error** | 38% | 25% |
| **crash/no-code** | 6% | 25% |

## Go/no-go reading
- The KEY number is the SILENT semantic-error rate: code runs, output looks fine, but it's wrong.
- High SILENT rate => execution-traced verification of transform SEMANTICS is the real-value
  direction (these errors are invisible to exec-pass checks and to the eye).
- Crashes don't count for the thesis (they're already caught by running the code).