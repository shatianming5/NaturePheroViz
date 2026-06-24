# B1 — 评测 Harness

## 概述

`eval/run_benchmark.py` 是统一的评测入口，支持多系统、多数据集的批量评测。

## 架构

```
run_benchmark.py
├── _load_tasks()           # 加载任务 (MatPlotBench CSV + builtin fixtures)
├── _run_task()             # 单任务执行: system runner → 执行代码 → PlotTrace 评估
├── _execute_and_score()    # 执行生成代码 → 渲染图表 → 计算 data_fidelity
├── main()                  # argparse 入口
└── 各 system runner 注册到 SYSTEM_RUNNERS dict
```

## 支持的系统

| 系统名 | Runner 函数 | 说明 |
|--------|------------|------|
| `ours` | `baseline_runners.run_ours` | NaturePheroViz PlotTrace 主系统 |
| `gpt4o_oneshot` | `baseline_runners.run_gpt4o_oneshot` | GPT-4o 单轮生成 |
| `claude_oneshot` | `baseline_runners.run_claude_oneshot` | Claude 单轮生成 |
| `qwen_zeroshot` | `baseline_runners.run_qwen_zeroshot` | Qwen-plus 零样本生成 |
| `lida` | `baseline_runners.run_lida` | LIDA 自动可视化框架 |
| `matplotagent` | `baseline_runners.run_matplotagent` | MatPlotAgent 占位 |

## 数据集支持

| 数据集 | 来源 | 任务数 |
|--------|------|--------|
| `matplotbench` | MatPlotBench CSV 文件 | ~100 (当前使用 17 个主任务) |
| `builtin` | 自建 fixtures | 4 (sales_bar, revenue_bar, trend_line, pop_bar) |

## 评估指标

每次运行记录 `record.json`:

```json
{
  "task_id": "84",
  "exec_pass": true,
  "scores": {
    "data_fidelity": 0.67,
    "visual_form": 1.0,
    "series_cohesion": 0.8
  },
  "rounds_used": 2,
  "generated_code": "...",
  "error": null
}
```

- **exec_pass**: 代码能否运行并生成图表
- **data_fidelity**: 结构感知 F1 (输出数据 vs 输入数据, 1.0=完美)
- **visual_form**: 图表类型正确性 (bar/line/scatter)
- **series_cohesion**: 数据系列完整性

## 使用方式

```bash
# 单系统单数据集
python eval/run_benchmark.py --system gpt4o_oneshot --dataset matplotbench --out eval/results_bench

# 限制任务数
python eval/run_benchmark.py --system ours --dataset matplotbench --limit 5

# 汇总所有结果
python eval/metrics.py --results eval/results_bench --out eval/results_bench/aggregate
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `eval/run_benchmark.py` | 主入口 |
| `eval/baseline_runners.py` | 各 baseline runner 实现 |
| `eval/metrics.py` | 结果汇总与指标计算 |
| `eval/silent_error_audit.py` | Silent error 注入审计 |
| `eval/end2end_bench.py` | 端到端 E2E 基准 |
