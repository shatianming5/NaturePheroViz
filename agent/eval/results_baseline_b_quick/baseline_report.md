# Baseline head-to-head: silent-error detectors on the same 48-case grid

Truly-wrong (silent) results: 10   |   truly-correct results: 23

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| ours | 9/10 (90%) | 0/23 (0%) |
| exec_pass | 0/10 (0%) | 0/23 (0%) |
| validity | 0/10 (0%) | 0/23 (0%) |
| self_check | 8/10 (80%) | 5/23 (22%) |
| consistency | 0/10 (0%) | 0/23 (0%) |

## Reading
- exec_pass recall ~ 0: silent errors run fine, so 'did it run' detects nothing.
- validity recall low: plausible-shaped wrong output passes sanity checks.
- self_check limited: the model is blind to its own semantic errors (common-mode).
- consistency fails on common-mode classes: wrong implementations agree with each other.
- ours: high recall + low FP from goldless operator-semantic invariants.