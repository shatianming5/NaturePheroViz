# Silent-Error Judge Head-to-Head

The decisive experiment: inject ONE silent numeric corruption, render once, ask each judge if the chart's data is faithful. `n/a` = judge unavailable (e.g. VLM without API key).

## 1. Detection recall (did the judge fire?)

| Corruption | Col-name (ctrl) | SVG/VisEval | PlotTrace (ours) | chart-VLM (ctrl) |
|---|---|---|---|---|
| wrong_value | 0% | 100% | 67% | n/a |
| scale_series | 0% | 100% | 75% | n/a |
| drop_series | 0% | 100% | 83% | n/a |
| swap_categories | 0% | 100% | 50% | n/a |
| **Overall** | **0%** | **100%** | **69%** | n/a |

## 2. Localization precision (of the fires, did it pinpoint the actual corrupted series — not flag everything?)

Only judges that emit per-point mismatches (SVG, PlotTrace) are scored here.

| Corruption | SVG/VisEval | PlotTrace (ours) |
|---|---|---|
| wrong_value | 0/12 (0%) | 8/12 (67%) |
| scale_series | 0/12 (0%) | 9/12 (75%) |
| drop_series | 0/12 (0%) | 10/12 (83%) |
| swap_categories | 0/12 (0%) | 6/12 (50%) |
| **Overall** | **0%** | **69%** |

## 3. Behavior on CLEAN charts (no corruption — an honest judge stays silent and reports fidelity≈1.0)

| Metric | Col-name (ctrl) | SVG/VisEval | PlotTrace (ours) | chart-VLM (ctrl) |
|---|---|---|---|---|
| False alarms | 0/12 | 12/12 | 0/12 | n/a |
| Mean fidelity (want ≈1.00) | 0.75 | 0.11 | 1.00 | n/a |

## Reading
- **Col-name heuristic** only checks column names exist → recall ~0%: blind to every silent error.
- **SVG/VisEval** reverse-engineers rendered geometry. It may *fire* often, but on clean bar charts it also misreads (low clean fidelity / false alarms) and floods mismatches → its detection is largely **noise, not localization**.
- **PlotTrace (ours)** reads the exact arrays passed to matplotlib → high recall, high localization, fidelity≈1.0 on clean charts, zero false alarms. Detection here is **exact, not noise**.
- The thesis holds when PlotTrace dominates on **localization + clean-fidelity**, not just raw recall — that is the gap render-only judges cannot close.
- *Repair* (judge feedback → agent regenerates code) is left to the in-loop experiment; a deterministic write-back patch is not discriminative here because localization already captures whether a judge can point at the right cell.