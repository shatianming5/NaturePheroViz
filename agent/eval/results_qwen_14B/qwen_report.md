# Open-model validation: Qwen2.5-Coder-14B on the transform-fidelity grid

Same 48-case grid, (ambiguous, clarified) prompts, goldless oracle — but the
generator is a LOCAL open model (Qwen2.5-Coder) instead of a proxy closed model.

## (1) Silent-error rate (open model)
- ambiguous: 26/48 (54%)
- clarified: 8/48 (17%)

## (2) Oracle recall on open-model silent errors
- fired on 34/34 truly-wrong (100%)

## (3) Oracle false-positive on open-model correct results
- fired on 0/62 truly-correct (0%)

## Reading
- If the open model also shows a high ambiguous silent-error rate AND the goldless
  oracle keeps high recall / low FP, the phenomenon + method generalize beyond the
  two closed models, not a GPT-4o/Claude artifact.