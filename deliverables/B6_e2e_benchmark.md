# B6 — Transform E2E 基准

> **当前主线**：从自然语言描述到 oracle 验证的全流水线端到端评估（Transform 内环）  
> 早期绘图 E2E（PlotTrace builtin fixtures）保留于文末附录。

---

## §1 实验设计

**目的**：评估整条 Transform Fidelity Verification 流水线在"端到端"视角下的表现——从研究者的模糊自然语言描述到最终产出的代码是否正确执行了预期变换。

**E2E 流程**：

```
研究者描述（自然语言）
       ↓
   prompt_builder
       ↓
  LLM 代码生成（ambiguous / clarified 两条路径）
       ↓
   Python executor
       ↓
  transform_oracle（goldless invariant check）
       ↓
  E2E 判定：PASS（语义正确）/ SILENT FAIL（静默错误）
```

**基准数据集**：48-grid（核心 12 类算子 × 4 instance = 48 cases），模型 gpt-5.4 + claude-sonnet-4.6

**两条 E2E 路径对比**：
- **Path A（模糊）**：模糊提示 → LLM → oracle
- **Path B（澄清）**：澄清提示 → LLM → oracle

---

## §2 端到端结果

### 2.1 路径 A vs B：E2E 成功率

| 路径 | 描述 | Cases | E2E PASS | **E2E 成功率** |
|------|------|------:|:--------:|:--------------:|
| Path A（模糊提示） | "计算百分比" / "做 z-score" | 96 | 52 | **54%** [44%, 64%] |
| Path B（澄清提示） | "计算 group 内 z-score（ddof=0）" | 96 | 84 | **88%** [79%, 93%] |
| **提升（B vs A）** | 澄清的 E2E 价值 | — | +32 | **+34 pp** |

**解读**：语义澄清将 E2E 成功率从 54% 提升至 88%。剩余 12% 失败（Path B 中）来自：真正的任务歧义（oracle 对 ddof 盲区无法判断）和极少数 LLM 语法错误（exec-fail）。

### 2.2 按算子类别的 E2E PASS 率（模糊路径）

| 算子类别 | E2E PASS (模糊) | 最常见静默失败模式 |
|---------|:--------------:|----------------|
| pct_point vs pct_group | 0/8 (0%) | 统一用减法（pct_point）代替除法（pct_group） |
| zscore 类 | 4/8 (50%) | global 代替 within_group |
| dedup 策略 | 12/24 (50%) | keep_first 被当 keep_last |
| rank 类 | 8/16 (50%) | ascending/descending 混淆 |
| pivot / median | 8/16 (50%) | groupby 粒度错误 |
| cumsum_group | 8/8 (100%) | 无歧义，低失败率 |

### 2.3 E2E 指标体系

| 指标 | Path A（模糊） | Path B（澄清） |
|------|:------------:|:------------:|
| **E2E 成功率**（oracle PASS / total cases） | 54% | 88% |
| **Exec-pass 率**（代码可运行） | 98% | 99% |
| **Silent Error 率**（exec-pass 但 oracle FAIL） | 46% | 12% |
| **Oracle FP 率**（正确结果被 oracle 报错） | 0% | 0% |

**关键观察**：E2E 失败的瓶颈不在代码生成（exec-pass 接近 100%），而在**语义正确性**（silent error 率 46%）。

---

## §3 Oracle 在 E2E 中的作用

在传统 E2E benchmark 中，唯一评测手段是"代码能跑"（exec-pass）。本实验证明，exec-pass 在本任务上是**无效终止条件**——98% 的生成代码可运行，但仅 54% 语义正确。

Oracle 是将 E2E 评估从"运行成功"升级到"语义正确"的关键组件：

```
旧 E2E 评估：NL描述 → 生成代码 → 能运行？→ ✅ 完成
新 E2E 评估：NL描述 → 生成代码 → 能运行？→ 语义正确？→ ✅ 完成
                                                ↑ goldless oracle
```

---

## §4 真实 Nature 数据 E2E（841 任务）

| 指标 | 值 | 95% CI |
|------|:--:|:------:|
| 模糊 E2E 成功率（澄清前） | 23% | — |
| 澄清 E2E 成功率 | 90% | — |
| Oracle FP（真实数据） | 0% (0/211) | [0%, 1%] |

**数据来源**：`eval/results_real841/real_auto_report.md`

---

## §5 复现命令

```bash
# 合成 48-grid E2E（歧义校准）
python eval/ambiguity_calibration.py --bench --out results_ambcal_bench

# 真实 Nature 数据 E2E
python eval/nature_real_auto.py --max-per-article 15 --out results_real841

# 查看结果
cat eval/results_ambcal_bench/ambcal_report.md
```

---

---

## 附录：早期绘图 E2E 基准（PlotTrace Builtin Fixtures）

> 以下内容属于项目早期"绘图保真"阶段，评测对象是 matplotlib 图表生成 agent 在简单任务上的端到端表现。保留供参考。

### A.1 实验设计

**目的**：在简化但严格控制的场景下比较：
1. Ours（PlotTrace judge）vs Ours（SVG judge）— **judge 消融**
2. Ours vs GPT-4o/Claude one-shot — **框架对比**

**数据集**：4 个 builtin fixtures（sales_bar, revenue_bar, trend_line, pop_bar）  
**统一评估器**：所有系统用同一个 PlotTrace oracle 评分（排除自评偏误）

### A.2 结果

| Task | GPT-4o | Claude | Ours (SVG judge) | **Ours (PlotTrace)** |
|------|--------|--------|------------------|---------------------|
| sales_bar | 1.00 | 1.00 | FAIL | **1.00** |
| revenue_bar | 1.00 | 1.00 | 1.00 | **1.00** |
| trend_line | 1.00 | 1.00 | 0.00 | **1.00** |
| pop_bar | 1.00 | 1.00 | 1.00 | **1.00** |

| 汇总 | GPT-4o | Claude | Ours (SVG) | **Ours (PlotTrace)** |
|------|--------|--------|------------|---------------------|
| **Mean DF** | 1.00 | 1.00 | 0.67 | **1.00** |
| **Exec-pass** | 4/4 | 4/4 | 3/4 | **4/4** |

### A.3 分析

**Judge 消融**：PlotTrace judge → DF=1.00；SVG judge → DF=0.67，trend_line exec-fail。PlotTrace judge 使系统在简单任务上达到完美保真度。

**框架对比**：builtin 任务过于简单，GPT-4o/Claude 单轮也能 DF=1.0。Ours 的优势在于复杂任务的迭代修正（MatPlotBench 上需要验证）。

**局限**：4 个 toy dataset 样本量过小，结论不可推广至复杂任务。

```bash
python eval/end2end_bench.py   # 复现命令
```
