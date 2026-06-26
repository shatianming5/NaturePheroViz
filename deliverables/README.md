# NaturePheroViz — 可交付实验报告汇总

> **更新时间**：2026-06-26  
> **当前阶段**：AAAI 投稿冲刺 — Transform Fidelity Verification 主线  
> **方向转型**：从"绘图保真"（PlotTrace/SVG 注入审计）→ **"数据变换保真"（算子语义契约 + goldless oracle）**

---

## 文档索引

| 编号 | 文档 | 内容 | 状态 |
|------|------|------|------|
| B1 | [评测 Harness](B1_benchmark_harness.md) | transform_bench / transform_oracle 架构；MatPlotBench harness（附录） | ✅ |
| B2 | [检测器对比](B2_baseline_results.md) | 5 检测器并排（ours / exec-pass / validity / self-check / consistency） | ✅ |
| B3 | [汇总主表 v2](B3_main_table.md) | Silent Rate × 检测器 × 跨模型 × 消融 四张论文级表格 | ✅ |
| B4 | [歧义变换 Silent Error Audit](B4_silent_error_audit.md) | 17 类算子语义歧义 + goldless oracle 检出；绘图注入（附录） | ✅ |
| B5 | [数据许可注册](B5_data_license.md) | MatPlotBench / Nature Pairs / 各数据集版权 | ✅ |
| B6 | [Transform E2E 基准](B6_e2e_benchmark.md) | 模糊→澄清 E2E 流水线；旧版绘图 E2E（附录） | ✅ |
| - | [Qwen 调优笔记](Qwen_tuning_notes.md) | Qwen API 连通、Rate limit 处理、代码提取改进 | ✅ |
| - | [B3 主表 v2（独立版）](B3_main_table_v2.md) | 同 B3，含完整数据源索引 | ✅ |

### 论文图表

| 图 | 文件 | 内容 |
|----|------|------|
| Fig 1 | `figures/fig1_silent_rate.{pdf,png}` | Silent Rate 柱状图（合成 vs 真实，±CI） |
| Fig 2 | `figures/fig2_detector_scatter.{pdf,png}` | 检测器 Recall–FP 散点图 |
| Fig 3 | `figures/fig3_scale_trend.{pdf,png}` | Qwen 规模趋势 + 闭源基准线 |
| Fig 4 | `figures/fig4_ablation.{pdf,png}` | Chart-Gen 消融柱状图 |

---

## 快速摘要（最新结果）

### 核心现象：Silent Semantic Error Rate

| 数据集 | 模糊提示 silent 率 | 澄清后 silent 率 | 降幅 |
|--------|:-----------------:|:----------------:|:----:|
| 合成 48-grid（gpt-4o + claude） | 46% (44/96) | 12% (12/96) | −34 pp |
| **真实 841 任务（71 篇 Nature 论文）** | **77% [75-79]** | **10% [9-12]** | **−67 pp** |

### 检测器并排（杀手表）

| 检测器 | Recall | FP Rate | F1 |
|--------|:------:|:-------:|:--:|
| **Ours（算子语义契约）** | **100%** | **0%** | **1.000** |
| exec-pass | 0% | 0% | 0.000 |
| output-validity | 0% | 0% | 0.000 |
| self-check（LLM 自查） | 61% | 40% | 0.483 |
| consistency（CodeT K=3） | 0% | 0% | 0.000 |

### 跨模型：Oracle FP 全程 0%（10 个模型 / 4 厂商）

| 模型档 | 代表模型 | 模糊 silent 率 | Oracle FP |
|--------|---------|:-------------:|:---------:|
| 前沿闭源（最强） | gpt-5.5 / gemini-3.1-pro | 32–42% | 0% |
| 代码专用 | gpt-5.3-codex | 36% | 0% |
| 开源（32B） | Qwen2.5-Coder-32B | 44% | 0% |
| 开源（7B） | Qwen2.5-Coder-7B | 65% | 0% |

### 消融（Chart-Gen Pipeline）

| 配置 | Avg Overall Score | Avg Data Fidelity |
|------|:-----------------:|:-----------------:|
| Full（全开） | 0.915 | 0.778 |
| −Verifier | 0.904 (↓0.011) | 0.750 (↓0.028) |
| −Best-of-N | 0.915 (=) | 0.778 (=) |
| −Pheromone | 0.915 (=) | 0.778 (=) |

---

## 实验状态

| 项目 | 状态 | 说明 |
|------|------|------|
| Silent error benchmark（48/68-grid） | ✅ 完成 | 核心 12 类 oracle recall 100% / FP 0% |
| 歧义校准（模糊 vs 澄清） | ✅ 完成 | 澄清修复 3/4 错误，证明模型语义失败 |
| 5 检测器并排（baseline compare） | ✅ 完成 | ours F1=1.0 唯一可靠 |
| 跨模型泛化（10 模型 / 4 厂商） | ✅ 完成 | oracle FP 跨模型 0% |
| 真实 Nature 切片（841 任务/71 篇） | ✅ 完成 | recall 98% [97-98]，FP 0% [0-1] |
| Chart-Gen 消融实验（4 配置） | ✅ 完成（2026-06-26） | −verifier 唯一有效差异 |
| 论文图表（4 张 PDF/PNG） | ✅ 完成（2026-06-26） | deliverables/figures/ |
| Limitation 写入论文 | ✅ 完成（2026-06-26） | zscore ddof 盲区已写入 §5 |
