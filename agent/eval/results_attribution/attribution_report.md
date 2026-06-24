# Typed-attribution accuracy: does the oracle localize to the right operator?

Two metrics with deliberately different gates:
- recall uses the TRUE-op contract's raw verdict (for the right operator, a
  missing expected output column IS a real silent error — wrong output shape).
- cross-fire counts only SUBSTANTIVE fires of OTHER-op contracts (a fire that is
  merely 'missing column' means that operator doesn't apply — recorded as abstain).

## (1) Attribution recall (true-op contract fires on its silent errors)
- 25/25 = 100%

## (2) Cross-fire specificity (substantive other-op fires on CORRECT results)
- no pruning: 88/1136 = 8%
- family-level pruning: 25/1136 = 2% (skip contracts whose operator family is structurally impossible for this result shape)

## Reading
- High attribution recall => when the oracle flags a silent error, the firing contract
  points at the correct operator semantics (typed localization, not just a binary flag).
- Family-level pruning cuts residual cross-fire below the schema-gate floor by never
  evaluating a contract whose family can't apply to the result's shape — pruning only
  removes structurally impossible families, so attribution recall is unaffected.