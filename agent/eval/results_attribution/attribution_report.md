# Typed-attribution accuracy: does the oracle localize to the right operator?

## (1) Attribution recall (true-op contract fires on its silent errors)
- 29/29 = 100%

## (2) Cross-fire specificity (other-op contracts on CORRECT results)
- 188/938 other-op contract evaluations fired = 20% (lower = more operator-specific)

## Reading
- High attribution recall => when the oracle flags a silent error, the firing contract
  points at the correct operator semantics (typed localization, not just a binary flag).
- Low cross-fire => contracts are operator-specific; an unrelated contract rarely
  misfires on a correct result, so the attribution label is trustworthy.