# Ambiguity Calibration: model failure vs prompt underspecification

Matched (ambiguous, clarified) prompts per transform. Oracle = goldless invariants.

## (1) Silent-error rate drops when intent is clarified
- ambiguous prompts: 63/136 silent-wrong (46%)
- clarified prompts: 19/136 silent-wrong (14%)
- A sharp drop => the errors are genuine MODEL semantic failures (fixable by clarification),
  not ill-posed tasks. (If clarified is still high, the task itself is the problem.)

## (2) Oracle detection recall on actual silent errors
- oracle fired on 66/82 truly-wrong results (80%)

## (3) Oracle false-positive rate on correct results
- oracle fired on 0/190 truly-correct results (0%) — lower is better

## Reading
- Claims for the paper: (1) clarification fixes most errors => real semantic failure;
  (2) high oracle recall on the silent errors; (3) low oracle false-positive on correct outputs.