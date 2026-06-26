# 组员 B 工作流 Prompt 清单

> 按顺序逐个发给 Claude，每个 prompt 执行完确认后再发下一个。
> 前置条件：工作目录为 `E:\NaturePheroViz-main`

---

## Prompt 1：理解 A 的新代码架构

```
请帮我梳理以下文件的架构和调用关系，用一张清晰的调用图 + 每个文件的核心功能说明：

1. agent/eval/transform_oracle.py — 核心 oracle 的 check() 函数签名、支持的算子类型、ContractResult 结构
2. agent/eval/transform_bench.py — _cases() 生成了多少类/多少 case、每个 case 的 schema
3. agent/eval/ambiguity_calibration.py — _llm_code()、_exec()、_gold_correct() 的作用、MODELS 配置
4. agent/eval/baseline_compare.py — 5 个检测器的实现逻辑
5. agent/eval/nature_real_auto.py — 如何从 Nature XLSX 自动生成任务

重点回答：
- 跑一次完整实验的命令是什么？需要哪些环境变量？
- 结果落盘在哪里、格式是什么？
- 我（组员 B）的评测 harness (eval/run_benchmark.py) 和这些新文件之间有没有复用关系？
```

---

## Prompt 2：离线验证 benchmark 可复现

```
请帮我离线验证 A 的 transform benchmark 的正确性（不需要调 LLM API）：

1. 运行 `cd agent && python eval/transform_bench.py`，确认 68 个 case 的 gold + oracle contract 全部通过
2. 运行 `cd agent && python eval/nature_real_auto.py --offline`（如果支持 offline 模式），确认 Nature 真实数据的 oracle sanity check 通过
3. 检查 eval/results_master/master_table.md 中引用的数字与实际结果文件是否一致：
   - results_ambcal_bench/ 中的 192 generations 分布 (135 correct + 56 silent + 1 crash)
   - results_baseline/ 中的 189 exec-ok (132 correct + 57 silent)
   - results_real841/ 中的 841 tasks / 71 articles

如果有不一致或报错，请列出具体差异。如果全部通过，确认可复现。
```

---

## Prompt 3：跑消融实验

```
请帮我用 A 提供的消融开关，在 transform benchmark 上跑消融实验：

1. 先阅读 agent/docs/A5_delivery.md 的 B 同学对接指南（§8），确认消融命令的正确用法
2. 用 agent/scripts/run_ablation_suite.py 跑四配置消融（full / no_verifier / no_bestof / no_pheromone）：
   - `cd agent && python scripts/run_ablation_suite.py --rounds 3 --output-dir runs/ablation_transform`
3. 如果 run_ablation_suite.py 的默认 cases 不是 transform benchmark 的 case，需要改造或手动用 CLI 跑：
   - full: `python run_chain.py <data> "<goal>" <type> --rounds 3`
   - no_verifier: 加 `--no-verifier`
   - no_bestof: 加 `--no-bestof`
   - no_pheromone: 加 `--no-pheromone`
4. 产出 ablation_aggregates.csv，对比各配置的 avg_overall_score / avg_rounds_used / stop_reason 分布

注意：这一步需要 LLM API。如果当前环境没有配置 API key，请告诉我需要设置哪些环境变量。
```

---

## Prompt 4：验证/复现 5 检测器正面对比

```
请帮我验证 A 的 baseline_compare 实验结果：

1. 阅读 agent/eval/baseline_compare.py 的完整代码，理解 5 个检测器的实现
2. 检查 agent/eval/results_baseline/baseline_report.md 中的数据：
   - ours: 57/57 recall, 0/132 FP
   - exec_pass: 0/57 recall, 0/132 FP
   - validity: 0/57 recall, 0/132 FP
   - self_check: 35/57 recall, 53/132 FP
   - consistency: 0/57 recall, 0/132 FP
3. 如果环境有 API key，尝试跑 `cd agent && python eval/baseline_compare.py --quick`（12-case 子集）验证结果趋势一致
4. 如果无 API，请从已有的 results JSON 文件中独立复算上述数字，确认报告无误

输出：确认结果是否可复现，如有差异列出。
```

---

## Prompt 5：汇总主表

```
请帮我把现有的所有实验结果汇总成论文级别的表格，输出到 deliverables/B3_main_table_v2.md：

需要包含以下表格：

### 表1：Silent Error Rate（核心现象）
- 数据源：ambiguity_calibration 68-grid 结果 + nature_real_auto 841 tasks
- 行：ambiguous / clarified
- 列：合成数据 silent rate / 真实数据 silent rate / 95% CI

### 表2：检测器正面对比（杀手表）
- 数据源：baseline_compare 结果
- 行：5 个检测器 (ours / exec_pass / validity / self_check / consistency)
- 列：Recall / FP rate / F1

### 表3：跨模型泛化
- 数据源：results_multimodel/ + results_qwen_7B/14B/32B/
- 行：各模型 (GPT-4o / Claude / Qwen-7B / 14B / 32B)
- 列：ambiguous silent rate / clarified silent rate / oracle recall / oracle FP

### 表4：消融实验
- 数据源：ablation 结果（步骤3的产出）
- 行：full / -verifier / -bestof / -pheromone
- 列：avg score / avg rounds / pass rate

请从 agent/eval/results_*/ 目录下的报告文件中提取数据，生成这四张表。
```

---

## Prompt 6：制作论文图表

```
请帮我为论文制作以下可视化图表，用 matplotlib 生成 PDF/PNG，保存到 deliverables/figures/：

### 图1：Silent Error Rate 对比柱状图
- 左组：合成数据 ambiguous vs clarified
- 右组：真实数据 ambiguous vs clarified
- 加 95% CI 误差线
- 数据来源：表1

### 图2：5 检测器 Recall vs FP 散点图
- x=FP rate, y=Recall
- 标注每个检测器名称
- ours 应在右上角(1.0, 0.0)位置
- 数据来源：表2

### 图3：模型规模趋势图 (Qwen 系列)
- x=模型参数量 (7B/14B/32B)
- y=ambiguous silent rate
- 加一条水平线标注闭源模型 (GPT-4o) 的 silent rate
- 数据来源：表3

### 图4：消融实验柱状图
- 并排柱：full / -verifier / -bestof / -pheromone
- y=avg_overall_score
- 数据来源：表4

要求：统一学术风格（无网格、serif 字体、适合双栏排版宽度 3.5in），配色用 colorblind-safe palette。
```

---

## Prompt 7：更新 deliverables 文档

```
请帮我更新 deliverables/ 目录下的文档，使其反映项目从「绘图保真」到「数据变换保真」的转型：

1. **deliverables/README.md** — 更新文档索引和快速摘要，反映新方向的实验结果
2. **deliverables/B1_benchmark_harness.md** — 补充 transform_bench / transform_oracle 架构说明，保留旧版 MatPlotBench 信息作为"早期实验"
3. **deliverables/B2_baseline_results.md** — 用新的 5 检测器对比替换旧的 GPT-4o/Claude/Qwen 对比
4. **deliverables/B3_main_table.md** — 用步骤5生成的 B3_main_table_v2.md 内容更新
5. **deliverables/B4_silent_error_audit.md** — 从旧版"注入绘图错误"更新为新版"歧义变换静默错误"，保留旧实验作为附录
6. **deliverables/B6_e2e_benchmark.md** — 更新为 transform 内环的 E2E 评估

保留旧内容在各文档底部的"附录：早期绘图实验"章节中，不要删除。
```

---

## Prompt 8：更新数据许可

```
请帮我更新 deliverables/B5_data_license.md 和 agent/eval/DATA.md，覆盖项目新用到的所有数据集：

新增需要记录的数据：
1. **transform_bench 合成数据** — 作者自建，代码中 _cases() 生成，确认无许可问题
2. **Nature Communications source-data XLSX** — 通过 nature_crawler.py 爬取，需确认：
   - 841 tasks 对应的 71 篇文章是否全部为 CC-BY-4.0
   - 爬虫版本和日期
   - 是否有 NC 条款文章混入
3. **Qwen 本地模型权重** — 从 HuggingFace 下载的 Qwen-7B/14B/32B，记录其许可证 (Apache-2.0 或其他)
4. **LLM API 使用** — GPT-4o/GPT-5/Claude API 的使用条款是否允许学术发表生成结果

更新投稿前检查清单，确保 AAAI 合规。
```

---

## 执行说明

- 每个 prompt 独立可执行，但有依赖关系：
  - Prompt 1-2 不依赖其他，可最先执行
  - Prompt 3-4 需要 API key（如无则跳过跑实验部分，只做结果验证）
  - Prompt 5 依赖 Prompt 3-4 的产出
  - Prompt 6 依赖 Prompt 5 的产出
  - Prompt 7-8 依赖 Prompt 5 的产出
- 如果某步出错，先修复再继续，不要跳步
