# Complex-Chart End-to-End Benchmark

Multi-series / twin-axis charts (where one-shot LLMs mis-map / drop series).
Same independent PlotTrace oracle (final chart vs input data). DF: structure-aware F1.

| Task | GPT-4o one-shot | Claude one-shot | Ours (SVG judge) | Ours (PlotTrace judge) |
|---|---|---|---|---|
| multi_line2 | 1.00 | 1.00 | FAIL | 1.00 |
| grouped_bar2 | 1.00 | 1.00 | 0.13 | 1.00 |
| three_line | 1.00 | 1.00 | 1.00 | 1.00 |
| twin_axis | 1.00 | 1.00 | 0.13 | FAIL |
| **mean DF** | 1.00 | 1.00 | 0.42 | 1.00 |
| **exec-pass** | 4/4 | 4/4 | 3/4 | 3/4 |

## Reading
- On complex charts one-shot LLMs are expected to slip (wrong mapping / dropped series / twin-axis).
- The verifier-driven inner loop can catch and repair these — IF the judge is exact (PlotTrace).
- Ours(PlotTrace) vs Ours(SVG): does the exact judge give higher final DF on hard charts?