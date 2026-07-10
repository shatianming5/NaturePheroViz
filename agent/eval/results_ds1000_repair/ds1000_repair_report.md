# External C2: targeted vs generic repair on DS-1000 silent errors (80 cases)

Symmetric to §1.3.2 (detection on external DS-1000): here we REPAIR the
external silent errors. Success = DS-1000's OWN gold (test cases pass);
targeted feedback = our goldless contracts (abstain->generic when none fire). models=['gpt-4o'], budget=2. 95% Wilson CIs.

## (1) Contract-fire coverage on external silents (honest boundary)
- our contracts fire on: 6/80 (8% [95% CI 3-15])
  (the rest, 74/80, are UNCOVERED — policy abstain-routes to generic)
  - by localized operator: left_join_keep_all 6

## (2) Repair recovery (DS-1000 gold), all silents
- generic baseline:        14/80 (18% [95% CI 11-27])
- policy (targeted+abstain): 16/80 (20% [95% CI 13-30])
  (policy == generic on the uncovered majority, so they differ only on covered cases)

## (3) Lift ON THE COVERED SUBSET (where a contract actually fires — the clean test)
- generic:  1/6 (17% [95% CI 3-56])
- targeted: 3/6 (50% [95% CI 19-81])

## Reading
- Coverage bounds the external targeted lift: where our operator-specific
  contracts fire (mostly the param-free join/how contract — most contracts need
  operator-semantic params arbitrary SO tasks do not carry), targeted feedback
  applies; elsewhere the policy correctly abstain-routes to generic (no blind
  edits). This honestly bounds how far operator-matched contracts transfer to
  unconstrained real SO tasks — the operator-matched external-DATA C2 evidence is
  the Nature slice (§1.3.1), where params are known and contracts fire ~99% recall.
