# External-DATA C2: targeted vs generic repair on REAL Nature silent errors (60 cases)

Operator-matched companion to the DS-1000 external-TASK result: same
generic-vs-policy repair comparison, but on REAL Nature source-data tables
(across 20 articles) where the operator params ARE known, so our goldless
contracts fire at high coverage. Success = template gold on the real table
(the policy never sees it). model=gpt-4o, budget=2. 95% Wilson CIs.

## (1) Contract-fire coverage on real silents (operator-matched => high)
- our contracts fire on: 41/60 (68% [95% CI 56-79])

## (2) Repair recovery (template gold on real data)
- generic baseline:        2/60 (3% [95% CI 1-11])
- policy (targeted+abstain): 33/60 (55% [95% CI 42-67])

## (3) Lift on the covered subset (the clean targeted-vs-generic test)
- generic:  2/41 (5% [95% CI 1-16])
- targeted: 33/41 (80% [95% CI 66-90])

## (4) By operator family (targeted/policy fixed vs generic fixed / total)
- median_not_mean      targeted 6/25 vs generic 0/25
- within_group_share   targeted 21/23 vs generic 0/23
- pooled_rate          targeted 3/8 vs generic 2/8
- weighted_mean        targeted 3/4 vs generic 0/4

## Reading
- With operator params known (real Nature tables, our operator-semantic
  tasks), contract coverage is high and the targeted lift over generic is
  realized on REAL scientific data — the external-DATA anchor for C2. Paired
  with DS-1000 (external-TASK, low coverage, honest boundary) this brackets
  how far contract-guided targeted repair transfers: strong where the
  operator semantics are identified, safely abstaining to generic elsewhere.
