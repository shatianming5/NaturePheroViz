# NaturePheroViz — 可交付实验报告汇总

> 生成时间: 2026-06-14  
> 当前阶段: AAAI 投稿冲刺 — 组员 B 负责的评测实验

---

## 文档索引

| 编号 | 文档 | 内容 | 状态 |
|------|------|------|------|
| B1 | [评测 Harness](B1_benchmark_harness.md) | `run_benchmark.py` 架构、MatPlotBench 数据集适配 | ✅ |
| B2 | [Baseline 结果](B2_baseline_results.md) | GPT-4o / Claude / Qwen / LIDA / Ours 全量对比 | ✅ |
| B3 | [汇总主表](B3_main_table.md) | 系统 × 指标聚合表格 + 逐任务分解 | ✅ |
| B4 | [杀手实验: Silent Error Audit](B4_silent_error_audit.md) | PlotTrace vs SVG/VisEval vs 列名启发式 | ✅ |
| B5 | [数据许可注册](B5_data_license.md) | MatPlotBench / Nature Pairs / 各数据集版权 | ✅ |
| B6 | [端到端基准](B6_e2e_benchmark.md) | Ours (PlotTrace) vs Ours (SVG) vs 单轮基线 | ✅ |
| - | [Qwen 调优笔记](Qwen_tuning_notes.md) | Qwen API 连通、Rate limit 处理、代码提取改进 | ✅ |

---

## 快速摘要

### 主表 (MatPlotBench, 24 任务)

| System | Exec-pass | Data Fidelity |
|--------|-----------|---------------|
| **Qwen zero-shot** | **81.8%** | **0.670** |
| GPT-4o one-shot | 79.2% | 0.387 |
| Claude one-shot | 70.8% | 0.599 |
| Ours (PlotTrace) | 65.2% | 0.289 |

### Silent Error Audit

| 指标 | 列名启发式 | SVG/VisEval | **PlotTrace (Ours)** |
|------|-----------|-------------|---------------------|
| 检测召回率 | 0% | 100% | **100%** |
| 定位精确度 | - | 71% | **100%** |
| 清洁图表误报 | 0/4 | 3/4 | **0/4** |
| 清洁图表保真度 | 0.75 | 0.25 | **1.00** |

### E2E 基准 (4 任务)

| System | DF |
|--------|----|
| Ours (PlotTrace judge) | **1.00** |
| GPT-4o one-shot | 1.00 |
| Claude one-shot | 1.00 |
| Ours (SVG judge) | 0.67 |

---

## 剩余待办

| 优先级 | 内容 | 说明 |
|--------|------|------|
| 🔴 | 提升 Ours DF | 当前 0.289，需排查 Verifier/BON 配置 |
| 🔴 | Nature 数据 silent error audit | 需运行爬虫获取 Nature Pairs |
| 🟡 | 消融实验 (关验证器/关BON) | 需要 A 组员提供开关 |
| 🟡 | MatPlotAgent / LIDA | 外部依赖 (需 clone 仓库) |
| 🟢 | 论文图表可视化 | 数据已齐，可直接做 |
