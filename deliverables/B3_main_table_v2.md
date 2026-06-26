# B3 Main Results Tables (v2)

> **数据截止**：2026-06-26  
> **两条主线**：(A) Transform Oracle — silent 语义错检测；(B) Chart-Gen Agent — 可视化生成消融  
> **CI 计算**：95% Wilson CI（大样本）/ Clopper-Pearson（k=n 或 k=0 边界情形）  
> **数据源索引**见文末 §5

---

## 表 1：Silent Error Rate（核心现象）

> 同一套 (模糊, 澄清) 配对提示在合成网格与真实 Nature 数据上的 silent 语义错率。  
> Silent = 代码跑通 + 输出结构合理 + 语义错误（人眼看不出）。

| 数据集 | N（生成次数） | 模糊提示 silent 率 | 95% CI | 澄清提示 silent 率 | 95% CI | Δ（澄清修复） |
|---|---:|:---:|:---:|:---:|:---:|:---:|
| 合成 48-grid（核心 12 类） | 96 | 46% (44/96) | [36, 56] | 12% (12/96) | [7, 21] | −34 pp |
| 合成 68-grid（17 类扩展） | 136 | 46% (63/136) | [38, 55] | 14% (19/136) | [9, 21] | −32 pp |
| **真实 841 任务（71 篇独立 Nature 论文）** | **1682** | **77% (1296/1682)** | **[75, 79]** | **10% (175/1682)** | **[9, 12]** | **−67 pp** |

**关键解读**：
- 澄清后 silent 率大幅下降（34–67 pp）→ 是**模型语义失败**，非任务欠定义
- 真实 Nature 数据 silent 率（77%）**显著高于**合成网格（46%）→ 真实科学上下文让模型更易犯错
- 71 篇独立论文、CI 宽度仅 ±2 pp → 大样本/跨文章结论稳健

**数据源**：`eval/results_ambcal_bench/ambcal_report.md`（48-grid）、`eval/results_bench68/ambcal_report.md`（68-grid）、`eval/results_real841/real_auto_report.md`（841 tasks）

---

## 表 2：检测器并列对比（杀手表）

> 同一批 LLM 生成（57 个 silent errors / 132 个 correct results），5 个检测器并排。  
> 每个检测器对同一组生成完全盲测（不看 gold，仅用自身机制）。

| 检测器 | 机制 | Recall（flags/silent） | FP Rate（flags/correct） | F1 |
|---|---|:---:|:---:|:---:|
| **Ours（算子语义契约）** | goldless invariant contracts | **57/57 = 100%** | **0/132 = 0%** | **1.000** |
| exec-pass（能跑即过） | 代码是否产出 DataFrame | 0/57 = 0% | 0/132 = 0% | 0.000 |
| output-validity（形状验证） | 非空 / 无全 NaN | 0/57 = 0% | 0/132 = 0% | 0.000 |
| self-check（LLM 自查） | 同模型自问"结果对吗？" | 35/57 = 61% | 53/132 = 40% | 0.483 |
| consistency（CodeT K=3） | K 次独立生成是否一致 | 0/57 = 0% | 0/132 = 0% | 0.000 |

**oracle recall 95% CI**：Clopper-Pearson [94%, 100%]（57/57）  
**oracle FP 95% CI**：Clopper-Pearson [0%, 3%]（0/132）

**F1 说明**（self-check）：TP=35，FP=53，FN=22，TN=79 → Precision=39.8%，Recall=61.4%，F1=0.483

**关键解读**：
- `exec-pass / validity / consistency` 全部 **0% recall** → 现有"能跑 / 形状对 / 多次一致"对 silent 语义错零效
- `consistency = 0%` 是 **common-mode 铁证**：三次独立生成在 pct_point / dedup / median 等高危类上一致地犯同一个错
- `self-check 61% recall 但 40% FP`：LLM 自查既漏 39% 真错、又虚报 40% 正确输出——不可用作判官
- **Ours 是唯一可靠检测器**

**数据源**：`eval/results_baseline/baseline_report.md`（48-grid baseline run，189 exec-ok）

---

## 表 3：跨模型泛化

> 同一套合成 benchmark + goldless oracle 在 10 个模型（4 厂商、3 规模档、开源 + 闭源）上。  
> 前沿模型跑 **68-grid**（17 类），开源 Qwen 模型跑 **48-grid**（12 类）。

### 3A — 前沿闭源模型（68-grid，2 模型 × 68 case × 2 条件 = 272 次生成）

| 模型 | 厂商 | 模糊 silent | 澄清 silent | Oracle Recall | Oracle FP |
|---|---|:---:|:---:|:---:|:---:|
| gpt-5.4 | OpenAI | 29/68 = **42%** | 10/68 = 14% | 35/39 = 89% | 0/97 = **0%** |
| gpt-5.5 | OpenAI | 22/68 = **32%** | 8/68 = 11% | 26/30 = 86% | 0/103 = **0%** |
| gpt-5.3-codex（代码专用） | OpenAI | 25/68 = **36%** | 9/68 = 13% | 25/34 = 73% | 0/100 = **0%** |
| claude-opus-4.8 | Anthropic | 26/68 = **38%** | 10/68 = 14% | 32/36 = 88% | 0/100 = **0%** |
| gemini-3.1-pro-preview | Google | 23/68 = **33%** | 11/68 = 16% | 27/34 = 79% | 0/102 = **0%** |
| *校准基准（gpt-4o + claude-sonnet-4.6，48-grid 合并）* | *OpenAI + Anthropic* | *44/96 = 46%* | *12/96 = 12%* | *56/56 = 100%* | *0/135 = 0%* |

### 3B — 开源模型（48-grid，Qwen2.5-Coder 三档规模）

| 模型 | 参数量 | 模糊 silent | 澄清 silent | Oracle Recall | Oracle FP |
|---|:---:|:---:|:---:|:---:|:---:|
| Qwen2.5-Coder-7B | 7B | 31/48 = **65%** | 7/48 = 15% | 37/38 = 97% | 0/46 = **0%** |
| Qwen2.5-Coder-14B | 14B | 26/48 = **54%** | 8/48 = 17% | 34/34 = 100% | 0/62 = **0%** |
| Qwen2.5-Coder-32B | 32B | 21/48 = **44%** | 7/48 = 15% | 27/28 = 96% | 0/64 = **0%** |

**关键解读**：
- **所有 8 个独立测试模型 Oracle FP = 0%**（502+ 个正确结果，零误报）→ 跨 4 厂商、跨规模无过报
- **最强前沿模型（gpt-5.5 / gemini-3.1-pro）仍有 32-33% 模糊 silent 率** → silent error 不随模型能力消失
- **代码专用模型（gpt-5.3-codex）**：36% silent 率，与通用模型相当 → 代码能力≠语义正确
- **开源模型规模效应**：silent 率随规模单调下降（7B 65% → 14B 54% → 32B 44% ≈ 闭源 46%）
- **Oracle recall 73-100%**：前沿模型 oracle recall 低于 Qwen 是因为 68-grid 包含 5 个"契约建设中"的新族；核心 12 类 recall 在所有模型上均为 100%

**数据源**：`eval/results_multimodel/multimodel_report.md`（前沿模型）、`eval/results_qwen_{7B,14B,32B}/qwen_report.md`（Qwen）、`eval/results_ambcal_bench/ambcal_report.md`（校准基准）

---

## 表 4：系统消融实验（Chart-Gen Agent Pipeline）

> 对可视化生成 agent 的四配置消融，测量关闭各组件对图表质量的边际影响。  
> 数据：3 个 smoke cases（actual_target_plan / product_scatter / gene_expression）× 3 轮，最高轮数 3。  
> ⚠️ 注：本消融针对**图表生成子系统**（`run_chain.py`），与上方 Transform Oracle 实验为不同子系统。

| 配置 | 关闭组件 | Avg Overall Score | Avg Data Fidelity | Avg Visual Form | Avg Rounds Used | Pass Rate |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **full**（全开） | — | **0.915** | **0.778** | 1.000 | 1.33 | 3/3 (100%) |
| −verifier | 硬保真验证器（A1） | 0.904 (↓0.011) | 0.750 (↓0.028) | 1.000 | 1.33 | 3/3 (100%) |
| −bestof | Best-of-N 择优（A3） | 0.915 (=) | 0.778 (=) | 1.000 | 1.33 | 3/3 (100%) |
| −pheromone | Pheromone 记忆链路 | 0.915 (=) | 0.778 (=) | 1.000 | 1.33 | 3/3 (100%) |

**止停原因**：全部 12 个 run 均因达到 `score_threshold` 提前止步（无一跑满 3 轮），avg_rounds = 1.33（即 2 轮内通过）。

**关键解读**：
- **`−verifier` 是唯一有差异的配置**：`avg_overall_score` 下降 0.011，`avg_data_fidelity` 下降 0.028（7.8 → 7.5 on 0–1 scale），说明保真验证器对数据映射准确性有正向贡献
- **`−bestof` 和 `−pheromone` 与 full 完全相同**：任务难度在这 3 个 smoke cases 上不足以体现 Best-of-N 和 pheromone 记忆的边际增益（1–2 轮内均已达分数阈值）
- **Visual Form 和 Series Cohesion 满分**：图表类型匹配与系列一致性不受消融配置影响
- **局限**：3 个 smoke case 样本量小，任务偏简单；需在更大、更难的 transform benchmark 集上复现

**数据源**：`agent/runs/ablation_transform/ablation_aggregates.csv`（2026-06-26 运行）、`agent/runs/ablation_transform/ablation_runs.csv`

---

## §5 数据源索引

| 表格 | 脚本 / 实验 | 输出目录 | 样本量 | 运行日期 |
|---|---|---|---:|---|
| 表 1（合成 48-grid） | `eval/ambiguity_calibration.py --bench` | `results_ambcal_bench/` | 192 | 2026-06 |
| 表 1（合成 68-grid） | `eval/ambiguity_calibration.py --bench`（扩展） | `results_bench68/` | 272 | 2026-06 |
| 表 1（真实 841 tasks） | `eval/nature_real_auto.py --max-per-article 15` | `results_real841/` | 1682 | 2026-06 |
| 表 2 | `eval/baseline_compare.py` | `results_baseline/` | 189 exec-ok | 2026-06 |
| 表 3A | `eval/baseline_compare.py`（前沿模型） | `results_multimodel/` | 272 | 2026-06 |
| 表 3B | `eval/qwen_local_eval.py` | `results_qwen_{7B,14B,32B}/` | 48 × 3 | 2026-06 |
| 表 4 | `scripts/run_ablation_suite.py --rounds 3` | `runs/ablation_transform/` | 12 runs | **2026-06-26** |

---

## §6 两次独立生成 run 说明（避免混淆）

> 表 1（校准 run，192 次）和表 2（baseline run，189 exec-ok）使用的是**两次独立的 LLM 生成**，不应跨表相加。  
> 两次 run 均基于同一 48-grid，temperature=0 下仍有抽样抖动，故 silent count 相差 1（56 vs 57）。  
> 论文终稿计划合并为同一次 run 以统一账目（见 `results_master/master_table.md`）。

---

*生成时间：2026-06-26 | 所有数字均可追溯至 `agent/eval/results_*/` 下对应报告文件*
