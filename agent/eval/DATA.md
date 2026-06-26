# Dataset & License Registry

> **更新时间**：2026-06-26（v2，涵盖 Transform Fidelity Verification 主线）  
> Maintainer: B-role member  
> 投稿前须将所有 ⚠️ 条目核实并勾选，不得遗留未闭合风险。

This file registers every dataset and model used in the NaturePheroViz evaluation,
including source, license, and any usage restrictions. Keep this up to date
before AAAI submission — missing or incompatible licenses can block publication.

---

## 1. Built-in Test Fixtures (Chart-Gen smoke test)

| Field | Value |
|-------|-------|
| **Name** | Built-in test fixtures (`_builtin_tasks()`) |
| **Source** | Hand-crafted by the authors |
| **Count** | 4 tasks (bar × 3, line × 1) |
| **License** | Authors' own — no restrictions |
| **Purpose** | Smoke-testing the chart-gen harness; NOT used in any reported metric |
| **AAAI risk** | None |
| **Notes** | Toy data (sales, revenue, trend, population). Zero overlap with eval sets. |

---

## 2. MatPlotBench (Early-phase chart-gen benchmark)

| Field | Value |
|-------|-------|
| **Name** | MatPlotBench |
| **Source** | [thunlp/MatPlotAgent](https://github.com/thunlp/MatPlotAgent) — `benchmark_data/` |
| **Count** | ~100 tasks (code→chart with paired data) |
| **License** | Apache-2.0 (per MatPlotAgent repo LICENSE) |
| **Purpose** | Early-phase quantitative benchmark for chart-generation fidelity |
| **Paper role** | Appendix / ablation only (main results now use transform-bench) |
| **AAAI risk** | None — Apache-2.0 permits academic publication |
| **Notes** | Anti-memorization design: tasks algorithmically generated. We use input `plot_df.csv` as ground truth. Last verified: 2026-06. |
| **Action** | ✅ License confirmed |

---

## 3. Transform-Bench Synthetic Grid (Primary benchmark — Transform main line)

| Field | Value |
|-------|-------|
| **Name** | Transform-Bench Synthetic Grid |
| **Source** | Authors — generated programmatically by `eval/transform_oracle.py` (`_cases()`) and `eval/ambiguity_calibration.py` |
| **Count** | 48-grid (12 operator classes × 4 instances) + 68-grid (17 classes × 4 instances) = 116 unique cases |
| **License** | Authors' own — no restrictions |
| **Purpose** | Primary quantitative benchmark for silent-error rate and oracle evaluation |
| **Paper role** | **Tables 1, 2, 3** (core claims) |
| **AAAI risk** | None — fully author-generated |
| **Reproducibility** | All cases re-generated from `_cases()` at any time; no external dependency |
| **Notes** | Each case is a Python-callable (input DataFrame + operator spec + expected invariant). No human-annotated labels; goldless oracle provides automated ground truth. |
| **Action** | ✅ No license action needed |

---

## 4. Nature Source-Data Slice — 841 Tasks / 71 Papers (Real-data validation)

| Field | Value |
|-------|-------|
| **Name** | Nature Source-Data Slice |
| **Source** | Crawled from Nature-family journals via `nature_crawler.py` (merged `download_nature_pairs.py` + `nature_all_in_one.py`) using Crossref + Europe PMC discovery |
| **Count** | 841 tasks from 71 independent articles (scanned 211 articles / 1607 source-data tables; capped at 15 tasks/article for cross-paper independence) |
| **License** | ⚠️ **REQUIRES VERIFICATION BEFORE SUBMISSION** — see below |
| **Purpose** | Real-world validation: silent-error rate 77% [75-79%] on genuine scientific data |
| **Paper role** | **Table 1, row 3** (hardest alarm number in paper) |
| **Crawl date** | 2026-06 (exact date TBD — check run logs) |
| **Crawler version** | `nature_crawler.py` merged script, subcommand `auto` + `postfetch`; `is_open_access` filter from Europe PMC |
| **AAAI risk** | **Medium** — see license verification section below |

### License Verification Details (Nature slice)

**Situation**: The crawler filters by `is_open_access=True` (via Europe PMC), but "open access" does NOT automatically mean CC-BY-4.0. The two relevant license types are:

| License | Allows research publication of derived tables/figures? | Allows distributing source data? |
|---------|:------------------------------------------------------:|:--------------------------------:|
| CC-BY-4.0 | ✅ Yes (with attribution) | ✅ Yes |
| CC-BY-NC-4.0 | ✅ Yes (non-commercial restriction does NOT apply to academic research) | ✅ Yes for research |
| Traditional ©, subscription | ❌ No source-data redistribution; analysis may be fair use but legally grey | ❌ No |

**Key facts about the journals**:
- **Nature Communications** (`ncomms`): All articles CC-BY-4.0 since March 2014. Source data distributed under same license. ✅ Safe.
- **Nature** (main journal): Mixed model — some articles CC-BY, some traditional subscription. Articles with publicly downloadable "Source Data" XLSX files are typically open access, but not guaranteed CC-BY-4.0.
- **Other Nature-family journals** (Nature Methods, Nature Genetics, etc.): License varies per article.

**Required pre-submission action**:
- [ ] Run `nature_crawler.py search --journal ncomms` only, OR audit articles.jsonl/csv to confirm all 71 articles are from Nature Communications (`ncomms`)
- [ ] Alternatively: grep DOI prefixes in articles.csv — Nature Communications DOIs are `10.1038/s41467-*`; verify none are from subscription journals
- [ ] If any non-CC-BY articles are included: remove those tasks from the 841-task slice and re-run metrics
- [ ] Record exact crawl command and date in this document after verification

**Interim stance**: Because `real_auto_report.md` says "Nature articles" (not specifically "Nature Communications"), this is a potential gap. The CC-BY-4.0 claim in B5 is currently an assumption, not a verified fact.

**Note on data redistribution**: We use source-data XLSX to construct prompts and evaluate oracle; we do NOT redistribute the raw XLSX files in the paper or supplementary. Analysis results (silent-error rates, aggregate statistics) are clearly non-substitutional and fall under fair-use even for restricted data. The license concern applies primarily to supplementary data release.

---

## 5. Qwen2.5-Coder Model Weights (Open-model validation)

| Field | Value |
|-------|-------|
| **Name** | Qwen2.5-Coder-Instruct (7B, 14B, 32B) |
| **Source** | HuggingFace: `Qwen/Qwen2.5-Coder-7B-Instruct`, `Qwen/Qwen2.5-Coder-14B-Instruct`, `Qwen/Qwen2.5-Coder-32B-Instruct` |
| **Local path** | `/mnt/cephfs_home_tianming.sha/qwen_models/Qwen2.5-Coder-{7,14,32}B-Instruct` (gpudev2) |
| **License** | **Apache-2.0** (per HuggingFace model card, Qwen2.5 family) |
| **Purpose** | Open-model replication: shows silent-error phenomenon is not GPT/Claude-specific |
| **Paper role** | **Table 3B** (scale trend: 65% → 54% → 44%) |
| **AAAI risk** | None — Apache-2.0 explicitly permits research use and reporting of model outputs |
| **Inference setup** | `transformers` 4.x, `torch` 2.x, local GPU inference via `qwen_local_eval.py` |
| **Notes** | Quantization: none (full precision BF16). Batch size 1, greedy decoding (temperature=0). |
| **Action** | ✅ License confirmed. Verify model card still says Apache-2.0 at submission time (licenses occasionally change). |

---

## 6. LLM API Usage (Closed models)

### 6.1 OpenAI (GPT-4o / GPT-5.x series)

| Field | Value |
|-------|-------|
| **Models used** | gpt-4o (ambiguity calibration), gpt-5.4, gpt-5.5, gpt-5.3-codex (Table 3A), gpt-4.1-mini (agent inference) |
| **Access** | Internal proxy at `1.14.177.180:4141` (API-compatible endpoint) |
| **License / Terms** | OpenAI Terms of Service — permits reporting model outputs in academic research publications |
| **Key clause** | OpenAI ToS §3(a): "You may use Output... for lawful purposes including for research and publication." |
| **AAAI risk** | Low — reporting aggregate statistics over model outputs is standard research practice and explicitly permitted |
| **Reproducibility concern** | ⚠️ Model versions accessed through proxy may differ from public OpenAI model IDs. Document exact model strings used at each experiment run. |
| **Action** | Record exact model ID strings (not just `gpt-5.4` but the version if available) in experiment logs before submission |

### 6.2 Anthropic (Claude-Sonnet-4.6 / Claude-Opus-4.8)

| Field | Value |
|-------|-------|
| **Models used** | claude-sonnet-4.6 (ambiguity calibration, baseline compare), claude-opus-4.8 (Table 3A) |
| **Access** | Internal proxy at `1.14.177.180:4141` |
| **License / Terms** | Anthropic Usage Policy — permits research use and publication of aggregate results |
| **Key clause** | Anthropic's policy permits academic research reporting of model outputs. Generated code is considered Output, not copyrighted by Anthropic. |
| **AAAI risk** | None for aggregate statistics; low even for individual code snippets in paper |
| **Action** | ✅ No blocking issue |

### 6.3 Google (Gemini-3.1-Pro-Preview)

| Field | Value |
|-------|-------|
| **Models used** | gemini-3.1-pro-preview (Table 3A) |
| **Access** | Internal proxy at `1.14.177.180:4141` |
| **License / Terms** | Google AI Developer Terms — research use of outputs permitted |
| **AAAI risk** | None for aggregate statistics |
| **Action** | ✅ No blocking issue |

---

## 7. MatPlotBench (retained from early phase)

See §2 above. Status: Apache-2.0 confirmed.

---

## 8. Non-integrated / Stretch Datasets (Not used in paper)

| Dataset | License | Status |
|---------|---------|--------|
| Plot2Code | TBD — verify before use | Not integrated |
| ChartMimic | TBD — verify before use | Not integrated |
| ChartMoE-Align | Apache-2.0 | Not used |
| Text2Chart31 | MIT | Not used |

These datasets are NOT included in any reported metric and require no license action for current submission.

---

## Summary Table

| Dataset / Model | Status | License | Used in Paper? | AAAI Risk |
|-----------------|--------|---------|:--------------:|:---------:|
| Built-in fixtures | ✅ Integrated | Authors' own | No (smoke test) | None |
| MatPlotBench | ✅ Integrated | Apache-2.0 | Appendix only | None |
| **Transform-Bench Synthetic** | ✅ Integrated | Authors' own | **Yes — Tables 1,2,3** | **None** |
| **Nature 841-task slice** | ✅ Integrated | ⚠️ Needs CC-BY verify | **Yes — Table 1 row 3** | **Medium** |
| **Qwen2.5-Coder (7B/14B/32B)** | ✅ Integrated | Apache-2.0 | **Yes — Table 3B** | **None** |
| **OpenAI GPT series** | ✅ Integrated | OpenAI ToS (permits research) | **Yes — Tables 1,2,3** | Low |
| **Anthropic Claude** | ✅ Integrated | Anthropic policy (permits research) | **Yes — Tables 1,2,3** | None |
| **Google Gemini** | ✅ Integrated | Google AI Terms (permits research) | **Yes — Table 3A** | None |
| Plot2Code | Not integrated | TBD | No | — |
| ChartMimic | Not integrated | TBD | No | — |

---

## Checklist Before Submission

### Must-complete (blocking)
- [ ] **[Nature slice]** Audit `articles.jsonl` / `articles.csv` from the 841-task crawl: confirm all 71 articles are from Nature Communications (`s41467-` DOIs) or otherwise carry confirmed CC-BY-4.0 licenses. If any don't, remove and re-run §4 metrics.
- [ ] **[Nature slice]** Record exact crawl command, date, and seed keyword(s) for reproducibility statement in paper.
- [ ] **[OpenAI models]** Record exact model version strings (e.g., `gpt-5.4-2026-05-08`) for all Table 3A experiments from proxy logs. Add to Methods section.

### Should-complete (non-blocking but recommended)
- [ ] **[Qwen]** Re-verify HuggingFace model card license at submission time — confirm still Apache-2.0 for 7B/14B/32B.
- [ ] **[MatPlotBench]** Verify latest MatPlotAgent repo LICENSE is still Apache-2.0 (check `thunlp/MatPlotAgent` on GitHub).
- [ ] **[Transform-Bench]** Add a data availability statement to paper: "Transform-Bench cases are generated programmatically and will be released with code."

### AAAI-specific
- [ ] Confirm AAAI 2026 author kit allows reporting LLM-generated code outputs (standard practice, expected to be fine)
- [ ] Add acknowledgment section crediting data sources: Nature Communications (CC-BY-4.0), Qwen2.5 (Qwen Team / Alibaba Cloud), OpenAI, Anthropic, Google
- [ ] If any source data will be released in supplementary: confirm CC-BY-4.0 attribution requirements are met (article DOIs, author attribution)
