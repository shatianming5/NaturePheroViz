# Does exemplar prompting fix the synthesis bottleneck? NO (cross-vendor ablation)

Controlled A/B/C: same cached messy NL, operator KNOWN (isolates the synthesis stage the
decomposition flagged). CORE = synthesized contract fires on the slip AND passes the correct impl.
Exemplars are leakage-free (operators outside the 23-op eval set).

| model | N | baseline (zero-shot) | one-shot | few-shot (3 families) |
|---|---|---|---|---|
| gpt-5.4 | 23 | 19/23=83% [63-93] | 15/23=65% [45-81] | 13/23=57% [37-74] |
| gemini-3.1-pro-preview | 23 | 15/23=65% [45-81] | 12/23=52% [33-71] | 13/23=57% [37-74] |
| **POOLED** | **46** | **34/46=74% [60-84]** | **27/46=59% [44-72]** | **26/46=57% [42-70]** |

**Finding:** zero-shot is best (74%); one-shot -15 pts, few-shot -17 pts.
Exemplars ANCHOR the synthesizer to their invariant family, degrading task-appropriate synthesis;
more exemplars do not help. The synthesis residual is genuine reasoning difficulty on
mechanically-complex operators (index alignment, dtype coercion, resample boundaries), a
fine-tuning/tool-use target, NOT a prompting fix. This ablation validates the paper's zero-shot choice.
