# Baseline head-to-head: silent-error detectors on the same 48-case grid

Truly-wrong (silent) results: 57   |   truly-correct results: 132

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| ours | 57/57 (100%) | 0/132 (0%) |
| exec_pass | 0/57 (0%) | 0/132 (0%) |
| validity | 0/57 (0%) | 0/132 (0%) |
| self_check | 35/57 (61%) | 53/132 (40%) |
| consistency | 0/57 (0%) | 0/132 (0%) |

## Reading
- exec_pass recall ~ 0: silent errors run fine, so 'did it run' detects nothing.
- validity recall low: plausible-shaped wrong output passes sanity checks.
- self_check limited: the model is blind to its own semantic errors (common-mode).
- consistency fails on common-mode classes: wrong implementations agree with each other.
- ours: high recall + low FP from goldless operator-semantic invariants.