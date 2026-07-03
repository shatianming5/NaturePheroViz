# AAAI paper skeleton — Silent Semantic Errors in LLM Data-Transform Code

A complete, compilable AAAI-style paper skeleton that organizes the project's
verified evidence into a submittable structure. Every number in `main.tex` is
drawn from `../docs/STORYLINE.md` and the result artifacts under
`../agent/eval/results_*` (see the claim→artifact map below).

## Build

```bash
# minimal (self-contained, no bibtex needed) — what this repo ships:
pdflatex main.tex && pdflatex main.tex      # -> main.pdf (4 pp.)
```

The skeleton compiles with a **minimal pdflatex** (manual `thebibliography`).
`references.bib` is provided for the real build.

## Switch to the official AAAI style for submission

1. Download the **AAAI-2026 Author Kit** and drop `aaai2026.sty` (+ `aaai2026.bst`) here.
2. In `main.tex` replace the block marked *"SELF-CONTAINED FALLBACK PREAMBLE"* with:
   ```latex
   \documentclass[letterpaper]{article}
   \usepackage{aaai2026}
   \usepackage{times}\usepackage{helvet}\usepackage{courier}
   \usepackage[hyphens]{url}\usepackage{graphicx}\usepackage{booktabs}
   \setcounter{secnumdepth}{0}
   ```
3. Swap the manual `thebibliography` for `\bibliographystyle{aaai2026}\bibliography{references}`
   and run `pdflatex; bibtex; pdflatex; pdflatex`.

All section content is written to survive that swap unchanged.

## Remaining author work (markers in `main.tex`)

- `\todo{...}` — prose/citation gaps (verify/extend `references.bib`).
- `\fig{...}` — two figures to render: (a) prevalence across models, (b) the
  reach/expressivity or detection schematic. Put PDFs in `figures/`.
- Expand from 4 pp. toward the AAAI 7-pp. limit: add the per-operator detection
  breakdown, the repair ablation table (generic/self-debug/localize/targeted/
  ceiling), and a method/pipeline figure.

## Claim → artifact map (for the auditable numbers)

| Claim in paper | Source artifact |
|---|---|
| 77% prevalence; simple checks 0%; self-critique 61%/40% | `docs/STORYLINE.md` A00, A5; `agent/eval/baseline_compare.py` |
| Detection 99%/0% real Nature ($N{=}1408$/$1539$) | `agent/eval/results_real_scaled/`, `nature_real_auto.py` |
| Auto-synthesis de-leaked 78% / leaky 83% ($N{=}23$) | `agent/eval/results_autocontract/autocontract_deleaked_N23.json` |
| Cross-model synthesis 83% (GPT-5.4/5.5, Gemini-3.1) | `agent/eval/results_autocontract/AUTOCONTRACT_SUMMARY.md` |
| NL operator inference: LLM 98% vs regex 21% | `agent/eval/results_nl_infer/nl_operator_infer_realistic.json` |
| E2E synthetic 61% | `agent/eval/results_e2e/e2e_report.json` |
| E2E real Nature 58% | `agent/eval/results_e2e/e2e_real_report.json` |
| E2E full-NL (op+params+contract) 51%; params 74%/83% | `agent/eval/results_e2e/e2e_real_fullparams.json` |
| Cross-substrate SQL 10/10 | `agent/eval/results_crossdomain/crossdomain_sql.json` |
| CEGIS monotone-safe, neutral 83%=83% | `agent/eval/results_cegis/CEGIS_SUMMARY.md` |
| Repair 79% vs 5% vs 45% | `agent/eval/results_repair_strongbaseline/`, `results_repair_ablation_loc/` |

## Positioning

Measurement-first framing (see STORYLINE A00): (1) measurement of a common,
invisible failure mode; (2) a goldless detector; (3) grounding an informal
request into a verifiable constraint (the AI contribution, vs. an SE tools
paper). Target: AAAI main / NeurIPS D&B / ICSE·FSE.
