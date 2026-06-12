# PlotTrace per-family coverage

Clean self-consistency: does PlotTrace recover the chart's own inputs?
RESOLVED = fidelity≥0.99 (exact); AMBIGUOUS = 0.5–0.99; UNSUPPORTED = <0.5 / no trace.
**'exact' claims in the paper apply ONLY to RESOLVED families.**

| Chart family | clean fidelity | status |
|---|---|---|
| bar | 1.00 | RESOLVED |
| line | 1.00 | RESOLVED |
| scatter | 1.00 | RESOLVED |
| grouped_bar | 1.00 | RESOLVED |
| twinx | 1.00 | RESOLVED |
| stacked_bar | 1.00 | RESOLVED |
| fill_between | 1.00 | RESOLVED |

RESOLVED: 7/7 families. AMBIGUOUS/UNSUPPORTED families fall back to SVG/VLM (the paper does not claim exact there).

*Note on stacked_bar / fill_between:* these are RESOLVED because PlotTrace captures the ARGUMENTS passed to the call (`ax.bar(x, b, bottom=a)` → we read `b`; `fill_between(x, 0, y)` → we read `y`), which equal the source-data values. This is precisely the execution-trace advantage: stacking baselines / band geometry distort what a render-only judge sees, but not the call-time arguments. If the verification target were instead the *rendered cumulative height*, that would be a different (geometry) question.