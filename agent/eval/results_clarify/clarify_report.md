# Clarification robustness: the ambiguity effect is not a one-phrasing fluke

High-risk ops: ['within_group_share', 'pct_point', 'dedup_then_agg', 'median_not_mean', 'topn_with_ties', 'count_includes_empty']
Each op: 1 ambiguous + 3 INDEPENDENT clarifications, x 2 models (denom per condition = 12).

## Silent-error rate: ambiguous vs each clarification variant
- ambiguous: 11/12 (92%)
- clarification #1: 2/12 (17%)
- clarification #2: 1/12 (8%)
- clarification #3: 1/12 (8%)

- clarified mean: 11%   std across variants: 3.9 pts

## Reading
- The drop holds under EVERY independent clarification, with low variance across
  wordings => the effect is the intent being specified, not one lucky phrasing.
- per-op detail:
  - within_group_share     ambiguous 1/2 -> clarified [0, 0, 0] (each /2)
  - pct_point              ambiguous 2/2 -> clarified [0, 0, 0] (each /2)
  - dedup_then_agg         ambiguous 2/2 -> clarified [0, 0, 0] (each /2)
  - median_not_mean        ambiguous 2/2 -> clarified [1, 0, 0] (each /2)
  - topn_with_ties         ambiguous 2/2 -> clarified [0, 0, 0] (each /2)
  - count_includes_empty   ambiguous 2/2 -> clarified [1, 1, 1] (each /2)