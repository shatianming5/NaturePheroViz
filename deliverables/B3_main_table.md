# B3 — 汇总主表 (v2)

> **更新时间**：2026-06-26（v2，替换旧版 MatPlotBench 聚合表）  
> 旧版内容见文末附录。  
> 完整独立版见 [B3_main_table_v2.md](B3_main_table_v2.md)。

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

---

## 表 2：检测器并列对比（杀手表）

> 同一批 LLM 生成（57 个 silent errors / 132 个 correct results），5 个检测器并排。

| 检测器 | 机制 | Recall（flags/silent） | FP Rate（flags/correct） | F1 |
|---|---|:---:|:---:|:---:|
| **Ours（算子语义契约）** | goldless invariant contracts | **57/57 = 100%** | **0/132 = 0%** | **1.000** |
| exec-pass（能跑即过） | 代码是否产出 DataFrame | 0/57 = 0% | 0/132 = 0% | 0.000 |
| output-validity（形状验证） | 非空 / 无全 NaN | 0/57 = 0% | 0/132 = 0% | 0.000 |
| self-check（LLM 自查） | 同模型自问"结果对吗？" | 35/57 = 61% | 53/132 = 40% | 0.483 |
| consistency（CodeT K=3） | K 次独立生成是否一致 | 0/57 = 0% | 0/132 = 0% | 0.000 |

**oracle recall 95% CI**：Clopper-Pearson [94%, 100%]（57/57）  
**oracle FP 95% CI**：Clopper-Pearson [0%, 3%]（0/132）

---

## 表 3：跨模型泛化（Oracle FP 全程 0%）

### 3A — 前沿闭源模型（68-grid）

| 模型 | 厂商 | 模糊 silent | 澄清 silent | Oracle Recall | Oracle FP |
|---|---|:---:|:---:|:---:|:---:|
| gpt-5.4 | OpenAI | 29/68 = **42%** | 10/68 = 14% | 35/39 = 89% | 0/97 = **0%** |
| gpt-5.5 | OpenAI | 22/68 = **32%** | 8/68 = 11% | 26/30 = 86% | 0/103 = **0%** |
| gpt-5.3-codex | OpenAI | 25/68 = **36%** | 9/68 = 13% | 25/34 = 73% | 0/100 = **0%** |
| claude-opus-4.8 | Anthropic | 26/68 = **38%** | 10/68 = 14% | 32/36 = 88% | 0/100 = **0%** |
| gemini-3.1-pro-preview | Google | 23/68 = **33%** | 11/68 = 16% | 27/34 = 79% | 0/102 = **0%** |
| *校准基准（48-grid）* | *OpenAI + Anthropic* | *44/96 = 46%* | *12/96 = 12%* | *56/56 = 100%* | *0/135 = 0%* |

### 3B — 开源 Qwen 模型（48-grid，规模效应）

| 模型 | 参数量 | 模糊 silent | 澄清 silent | Oracle Recall | Oracle FP |
|---|:---:|:---:|:---:|:---:|:---:|
| Qwen2.5-Coder-7B | 7B | 31/48 = **65%** | 7/48 = 15% | 37/38 = 97% | 0/46 = **0%** |
| Qwen2.5-Coder-14B | 14B | 26/48 = **54%** | 8/48 = 17% | 34/34 = 100% | 0/62 = **0%** |
| Qwen2.5-Coder-32B | 32B | 21/48 = **44%** | 7/48 = 15% | 27/28 = 96% | 0/64 = **0%** |

---

## 表 4：Chart-Gen Pipeline 消融实验

> 数据来源：`agent/runs/ablation_transform/ablation_aggregates.csv`（2026-06-26）

| 配置 | 关闭组件 | Avg Overall Score | Avg Data Fidelity | Avg Rounds | Pass Rate |
|---|---|:---:|:---:|:---:|:---:|
| **full**（全开） | — | **0.915** | **0.778** | 1.33 | 3/3 (100%) |
| −verifier | 硬保真验证器 | 0.904 (↓0.011) | 0.750 (↓0.028) | 1.33 | 3/3 (100%) |
| −bestof | Best-of-N 择优 | 0.915 (=) | 0.778 (=) | 1.33 | 3/3 (100%) |
| −pheromone | Pheromone 记忆 | 0.915 (=) | 0.778 (=) | 1.33 | 3/3 (100%) |

---

---

## 附录：早期绘图实验——MatPlotBench 聚合表（旧版 B3）

> 以下为项目早期"绘图保真"阶段的系统 × 指标总表，保留供参考。

| System | Tasks | Exec-pass | Data Fidelity | Visual Form | Series Cohesion | Rounds | Pass@1 |
|--------|-------|-----------|---------------|-------------|-----------------|--------|--------|
| **qwen_zeroshot** | 22 | **18/22 (81.8%)** | **0.670** | 0.000 | 0.000 | 1.0 | 0.818 |
| gpt4o_oneshot | 24 | 19/24 (79.2%) | 0.387 | 0.000 | 0.000 | 1.0 | 0.792 |
| claude_oneshot | 24 | 17/24 (70.8%) | 0.599 | 0.000 | 0.000 | 1.0 | 0.708 |
| ours | 23 | 15/23 (65.2%) | 0.289 | 0.656 | 0.694 | 1.5 | 0.652 |
| lida | 3 | 0/3 (0.0%) | 0.000 | 0.000 | 0.000 | 0.0 | 0.000 |

**旧版关键发现**：
1. Qwen-plus 零样本是当时最强 baseline（81.8% + DF 0.67）
2. GPT-4o silent error 最严重（最高执行率但最低 DF 0.39）
3. Ours 系统 DF 偏低（0.289），需排查 verifier 反馈
4. VF/SC 仅 Ours 有值（PlotTrace verifier 计算）

### 旧版各系统详细统计

#### qwen_zeroshot
- Tasks: 22 | Exec-pass: 18/22 (81.8%) | Mean DF: 0.670 | Median DF: 1.000
- Fidelity distribution: `[0-.25):5  [.25-.50):1  [.50-.75):1  [.75-1.0]:11`

#### gpt4o_oneshot
- Tasks: 24 | Exec-pass: 19/24 (79.2%) | Mean DF: 0.387 | Median DF: 0.093
- Fidelity distribution: `[0-.25):12  [.75-1.0]:7` — 大量 silent error

#### claude_oneshot
- Tasks: 24 | Exec-pass: 17/24 (70.8%) | Mean DF: 0.599 | Median DF: 1.000
- Fidelity distribution: `[0-.25):7  [.75-1.0]:10` — 两极分化

#### ours (PlotTrace)
- Tasks: 23 | Exec-pass: 15/23 (65.2%) | Mean DF: 0.289 | Median DF: 0.000
- Mean VF: 0.656 | Mean SC: 0.694 | Mean rounds: 1.5
