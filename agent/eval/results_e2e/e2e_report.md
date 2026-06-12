# Unified End-to-End Benchmark

Same tasks, same independent oracle (PlotTrace read-back of FINAL chart vs input data).
exec = rendered a chart; DF = data fidelity (structure-aware F1, 1.0 = perfect).

| Task | GPT-4o one-shot | Claude one-shot | Ours (SVG judge) | Ours (PlotTrace judge) |
|---|---|---|---|---|
| sales_bar | 1.00 | 1.00 | FAIL | 1.00 |
| revenue_bar | 1.00 | 1.00 | 1.00 | 1.00 |
| trend_line | 1.00 | 1.00 | 0.00 | 1.00 |
| pop_bar | 1.00 | 1.00 | 1.00 | 1.00 |
| **mean DF** | 1.00 | 1.00 | 0.67 | 1.00 |
| **exec-pass** | 4/4 | 4/4 | 3/4 | 4/4 |

## Reading
- Task 1 (judge ablation): Ours(PlotTrace) vs Ours(SVG) — does the better in-loop judge give higher final DF?
- Task 2 (baselines): Ours vs one-shot GPT-4o / Claude — does the code-first agent + verifier loop beat one-shot generation?
- All scored by the same trace oracle, so the comparison is apples-to-apples and self-judging is excluded.