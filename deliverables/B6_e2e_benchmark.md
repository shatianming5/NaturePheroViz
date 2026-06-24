# B6 — 端到端基准 (E2E Benchmark)

## 实验设计

**目的**: 在简化但严格控制的场景下比较:
1. Ours(PlotTrace judge) vs Ours(SVG judge) — **judge 消融**
2. Ours vs GPT-4o/Claude one-shot — **框架对比**

**数据集**: 4 个 builtin fixtures (sales_bar, revenue_bar, trend_line, pop_bar)

**统一评估器**: 所有系统用同一个 PlotTrace oracle 评分 (排除自评偏误)

---

## 结果

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

---

## 分析

### 1. Judge 消融 (Ours PlotTrace vs Ours SVG)

- PlotTrace judge → DF = 1.00 (4/4)
- SVG judge → DF = 0.67 (3/4), trend_line exec-fail

**PlotTrace judge 使系统在简单任务上达到完美保真度**，而 SVG judge 在趋势线 (trend_line) 上无法取得有效收敛。

### 2. 框架对比 (Ours vs 单轮)

- 在 builtin 简单任务上，GPT-4o 和 Claude 单轮也能达到 DF=1.0
- Ours 的优势不在于简单任务，而在于复杂任务上的迭代修正能力 — 这在 MatPlotBench 更复杂任务上需要验证

### 3. 局限

- Builtin 任务过于简单 (4 个 toy datasets)
- Ours 在 MatPlotBench 复杂任务上 DF 仍然偏低 (0.289)
- 此结果仅展示框架在理想条件下的上限

---

## 复现命令

```bash
python eval/end2end_bench.py
```
