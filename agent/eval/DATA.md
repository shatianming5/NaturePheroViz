# Dataset & License Registry

This file registers every dataset used in the NaturePheroViz evaluation,
including source, license, and any usage restrictions. Keep this up to date
before AAAI submission — missing or incompatible licenses can block publication.

---

## 1. Built-in Test Fixtures

| Field | Value |
|-------|-------|
| **Name** | Built-in test fixtures (`_builtin_tasks()`) |
| **Source** | Hand-crafted by the authors |
| **Count** | 4 tasks (bar × 3, line × 1) |
| **License** | Authors' own — no restrictions |
| **Purpose** | Smoke-testing the harness; NOT used in reported results |
| **Notes** | Toy data (sales, revenue, trend, population). Zero overlap with eval sets. |

---

## 2. MatPlotBench

| Field | Value |
|-------|-------|
| **Name** | MatPlotBench |
| **Source** | [thunlp/MatPlotAgent](https://github.com/thunlp/MatPlotAgent) — `benchmark_data/` |
| **Count** | ~100 tasks (code→chart with paired data) |
| **License** | Apache-2.0 (per MatPlotAgent repo LICENSE) |
| **Purpose** | Primary quantitative benchmark |
| **Notes** | Designed to be anti-memorization: tasks are algorithmically generated, so LLMs trained on GitHub code have not seen them. Each task provides input data + a query; the system must produce correct plotting code. We use the input data as `plot_df.csv` (ground truth). |

---

## 3. Nature Pairs (Self-collected)

| Field | Value |
|-------|-------|
| **Name** | Nature Pairs |
| **Source** | Crawled from Nature Communications articles via `nature_crawler.py` + `download_nature_pairs.py` |
| **Count** | Varies by crawl; typically 50–200 figure-source-data pairs |
| **License** | Nature Communications articles are CC-BY-4.0. Source data (Excel sheets) distributed with articles under the same license. |
| **Purpose** | Qualitative case studies + real-world complex chart evaluation |
| **Notes** | These are real published scientific figures with their underlying source data. We use them as qualitative evidence (not aggregate metrics) because (a) there is no "ground truth" plotting code, and (b) the source data sheets require manual alignment. For the silent-error audit, we synthesize plotting code from the source data and inject corruptions. |

---

## 4. Plot2Code (potential)

| Field | Value |
|-------|-------|
| **Name** | Plot2Code |
| **Source** | [Plot2Code](https://github.com/) — chart→code benchmark |
| **Count** | ~50 tasks (planned subset) |
| **License** | TBD — verify before use |
| **Purpose** | Chart→code visual comparison baseline |
| **Notes** | **NOT YET INTEGRATED.** Plot2Code measures visual similarity (chart→code), not data fidelity. Useful as adjacent comparison to show that visual-only metrics are insufficient. |

---

## 5. ChartMimic (potential)

| Field | Value |
|-------|-------|
| **Name** | ChartMimic |
| **Source** | [ChartMimic](https://github.com/) — chart reproduction benchmark |
| **Count** | ~50 tasks (planned subset) |
| **License** | TBD — verify before use |
| **Purpose** | Chart→code visual reproduction baseline |
| **Notes** | **NOT YET INTEGRATED.** Similar to Plot2Code: measures visual fidelity, not data fidelity. |

---

## 6. ChartMoE-Align (potential stretch)

| Field | Value |
|-------|-------|
| **Name** | ChartMoE-Align |
| **Source** | [ChartMoE-Align](https://huggingface.co/) — ~1M chart-code pairs |
| **Count** | ~1M pairs |
| **License** | Apache-2.0 |
| **Purpose** | Optional Stage-A Code-SFT (stretch goal, not on critical path) |
| **Notes** | **NOT YET USED.** Would be used only for the optional SFT experiment comparing "SFT + our inner loop" vs "zero-shot + our inner loop". |

---

## 7. Text2Chart31 (potential stretch)

| Field | Value |
|-------|-------|
| **Name** | Text2Chart31 |
| **Source** | [Text2Chart31](https://huggingface.co/) |
| **Count** | 31 chart types |
| **License** | MIT |
| **Purpose** | Alternative Stage-A SFT data (stretch goal) |
| **Notes** | **NOT YET USED.** |

---

## Summary

| Dataset | Status | License | Used in Paper? |
|---------|--------|---------|---------------|
| Built-in fixtures | Integrated | Authors' own | No (smoke test only) |
| MatPlotBench | Integrated | Apache-2.0 | Yes (primary quantitative) |
| Nature Pairs | Integrated | CC-BY-4.0 | Yes (qualitative cases) |
| Plot2Code | Planned | TBD | Optional |
| ChartMimic | Planned | TBD | Optional |
| ChartMoE-Align | Stretch | Apache-2.0 | Optional |
| Text2Chart31 | Stretch | MIT | Optional |

## Checklist Before Submission

- [ ] Verify MatPlotBench license in the latest MatPlotAgent repo
- [ ] Verify Nature Pairs CC-BY-4.0 applies to all crawled articles
- [ ] If Plot2Code/ChartMimic are included, verify and record their licenses
- [ ] Confirm no dataset has a non-commercial (NC) clause that would conflict with AAAI publication
- [ ] Document exact crawler version/date for Nature Pairs reproducibility
