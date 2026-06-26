# Baseline head-to-head: silent-error detectors on the same 48-case grid

Truly-wrong (silent) results: 15   |   truly-correct results: 53

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| ours | 13/15 (87%) | 0/53 (0%) |
| exec_pass | 0/15 (0%) | 0/53 (0%) |
| validity | 0/15 (0%) | 0/53 (0%) |
| self_check | 10/15 (67%) | 9/53 (17%) |
| consistency | 0/15 (0%) | 1/53 (2%) |

## Reading
- exec_pass recall ~ 0: silent errors run fine, so 'did it run' detects nothing.
- validity recall low: plausible-shaped wrong output passes sanity checks.
- self_check limited: the model is blind to its own semantic errors (common-mode).
- consistency fails on common-mode classes: wrong implementations agree with each other.
- ours: high recall + low FP from goldless operator-semantic invariants.