# Open-model validation: Qwen2.5-Coder-7B on the transform-fidelity grid

Same 48-case grid, (ambiguous, clarified) prompts, goldless oracle — but the
generator is a LOCAL open model (Qwen2.5-Coder) instead of a proxy closed model.

## (1) Silent-error rate (open model)
- ambiguous: 31/48 (65%)
- clarified: 7/48 (15%)

## (2) Oracle recall on open-model silent errors
- fired on 37/38 truly-wrong (97%)

## (3) Oracle false-positive on open-model correct results
- fired on 0/46 truly-correct (0%)

## Reading
- If the open model also shows a high ambiguous silent-error rate AND the goldless
  oracle keeps high recall / low FP, the phenomenon + method generalize beyond the
  two closed models, not a GPT-4o/Claude artifact.