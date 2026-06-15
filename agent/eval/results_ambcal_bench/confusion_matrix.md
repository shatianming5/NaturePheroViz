# 192-generation confusion matrix (full accounting)

Closes the round-2 reviewer's "135 vs 136" credibility hole: the missing case is
the 1 crash (no produced frame), excluded from both the FP and recall denominators.

| ground truth \ oracle | FIRED (flags error) | did NOT fire | row total |
|---|---|---|---|
| correct (exec ok, right)      | 0 (false positive) | 135 (true negative)  | 135 |
| silent error (exec ok, wrong) | 56 (true positive)  | 0 (false negative)   | 56  |
| crash (no output)             | 1                   | 0                    | 1   |
| **column total**              | 57                  | 135                  | **192** |

- recall (TP / silent total) = 56/56 = 100%
- false-positive rate (FP / correct total) = 0/135 = 0%
- the 1 crash (weighted_mean#1, claude, clarified): produced no frame, excluded from both denominators
- 135 correct + 56 silent + 1 crash = 192 total
