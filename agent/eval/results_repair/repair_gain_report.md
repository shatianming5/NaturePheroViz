# Judge-Driven One-Step Repair Gain (real LLM)

Buggy render → judge feedback → LLM rewrites code → re-render. FINAL fidelity
measured by an INDEPENDENT PlotTrace oracle (chart vs input data), not the driving judge.

| Case | start (buggy) | SVG-driven final | PlotTrace-driven final |
|---|---|---|---|
| wrong_column | 0.00 | 1.00 | 1.00 |
| dropped_series | 0.67 | 1.00 | 1.00 |
| wrong_transform | 0.00 | 1.00 | 1.00 |
| scaled_wrong | 0.00 | 1.00 | 1.00 |
| **Mean** | — | 1.00 | 1.00 |

## Reading
- start = fidelity of the buggy chart (low: it draws the wrong data).
- final = fidelity after the LLM repairs using each judge's feedback.
- Thesis holds if PlotTrace-driven final > SVG-driven final: exact, localized
  feedback points the LLM at the real bug; SVG's noisy feedback misleads it.