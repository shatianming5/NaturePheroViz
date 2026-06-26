# B1 — 评测 Harness

> **当前主线：数据变换保真验证（Transform Fidelity Verification）**  
> 早期绘图 Harness 保留于文末附录。

---

## §1 Transform Benchmark 架构

### 1.1 系统结构

```
eval/
├── transform_oracle.py        # goldless oracle — 17 类算子语义契约
├── ambiguity_calibration.py   # 模糊/澄清配对实验主入口
├── baseline_compare.py        # 5 检测器并排评测
├── transform_cases/           # 合成测试用例 (CSV + YAML spec)
│   ├── 48grid/                # 核心 12 类 × 4 instance
│   └── 68grid/                # 扩展 17 类 × 4 instance
└── results_*/                 # 各次实验结果目录
```

### 1.2 Goldless Oracle（`transform_oracle.py`）

**设计哲学**：不需要参考输出（gold output），而是对每类数据变换算子定义**不变量契约（invariant contract）**，只要 LLM 生成的代码违反契约即报错。

| 契约类型 | 例子 | 检测能力 |
|---------|------|---------|
| 形状契约 | 行数不变 / group_by 后行数变化 | 行删除 / 行复制 |
| 统计不变量 | zscore 后 per-group mean ≈ 0 | 全局 vs 组内标准化 |
| 单调性契约 | rank 后必须 1→N 连续 | rank 映射错误 |
| 集合包含契约 | 输出列需包含 pct_group = val/group_total | pct_point 混淆 |
| 幂等性契约 | dedup 后再 dedup 结果不变 | 去重策略错误 |

目前支持 **17 类算子**，核心 12 类契约完整，另 5 类（zscore_within_group, dense_rank, cumcount, rank_pct, clip_outlier）契约仍在完善中。

### 1.3 歧义校准实验（`ambiguity_calibration.py`）

**实验设计**：对每个 test case 生成一对 (模糊提示, 澄清提示)，LLM 生成代码后用 oracle 检验。

```
task_spec.yaml → prompt_builder → ambiguous_prompt
                              → clarified_prompt
                  ↓
              LLM (model × 2)
                  ↓
            generated_code
                  ↓
        executor → result_df
                  ↓
        transform_oracle → ContractResult(passed/failed, reason)
                  ↓
        ambcal_records.json → ambcal_report.md
```

**关键配置**：

```python
MODELS = ["gpt-4o", "claude-sonnet-4.6"]   # ambiguity_calibration.py
# 实际 proxy 使用 gpt-5.4 替代 gpt-4o（proxy 不支持 gpt-4o 端点）
LLM_API_BASE = "http://1.14.177.180:4141/v1"
LLM_MODEL    = "gpt-4.1-mini"              # agent/.env
```

### 1.4 5-Detector 对比（`baseline_compare.py`）

对同一批 LLM 生成并排运行 5 个检测器：

| 检测器 | 入口函数 | 机制 |
|--------|---------|------|
| `d_ours` | `oracle_check(op, inp, params, result)` | goldless invariant |
| `d_exec_pass` | `result is None` | 能否产出 DataFrame |
| `d_validity` | shape + non-null check | 形状合法性 |
| `d_self_check` | LLM API call | 同模型自问 |
| `d_consistency` | K=3 生成 majority vote | 多次一致性 |

**运行方式**：

```bash
# 完整跑（需 LLM API，含 self-check 和 consistency）
python eval/baseline_compare.py --model gpt-4.1-mini

# 快速跑（仅 oracle，无 API 调用）
python eval/baseline_compare.py --quick
```

### 1.5 Transform Benchmark 数据集

| 数据集 | 算子类别数 | Instance 数 | 总 Cases | 生成次数（×模型数×2条件） |
|--------|:---------:|:-----------:|:--------:|:----------------------:|
| 48-grid（合成核心） | 12 | 4 | 48 | 96 |
| 68-grid（合成扩展） | 17 | 4 | 68 | 136 |
| 841-tasks（真实 Nature） | — | 841篇文章切片 | 841 | 1682 |

**算子类别（12 核心类）**：`zscore_global`, `zscore_within_group`, `pct_point`, `pct_group`, `dedup_keep_first`, `dedup_keep_last`, `dedup_keep_min`, `rank_asc`, `rank_desc`, `pivot`, `median_group`, `cumsum_group`

**新增 5 类（68-grid 扩展）**：`dense_rank`, `cumcount`, `rank_pct`, `clip_outlier`, `zscore_ddof0_vs_ddof1`

---

## §2 评估指标

### Transform 主线指标

每次 oracle 调用返回 `ContractResult(op, passed, reason)`：

| 指标 | 计算方式 | 说明 |
|------|---------|------|
| **Silent Error Rate** | failed / (failed + passed) | 模型语义失败率 |
| **Oracle Recall** | TP / (TP + FN) | oracle 检出真实错误的比例 |
| **Oracle FP Rate** | FP / (FP + TN) | oracle 对正确结果的误报率 |
| **F1** | 2PR/(P+R) | 综合检测能力 |

**结果目录结构**：

```
results_*/
├── ambcal_records.json    # 逐条记录（op, model, condition, oracle_passed, ...）
├── ambcal_report.md       # 聚合报告
└── baseline_records.json  # baseline compare 专用格式
```

---

## §3 关键文件索引

| 文件 | 用途 |
|------|------|
| `eval/transform_oracle.py` | 17 类算子契约定义，核心 |
| `eval/ambiguity_calibration.py` | 模糊/澄清校准实验 |
| `eval/baseline_compare.py` | 5 检测器并排 |
| `eval/transform_cases/48grid/` | 合成 benchmark cases |
| `agent/.env` | LLM API 配置（proxy 地址、key、model） |
| `agent/eval/results_*/` | 各次实验结果目录 |

---

---

## 附录：早期绘图实验 Harness（MatPlotBench）

> 以下内容属于项目早期"绘图保真"阶段，保留供参考。

### A.1 架构概览

`eval/run_benchmark.py` 是早期统一评测入口，支持多系统、多数据集批量评测。

```
run_benchmark.py
├── _load_tasks()           # 加载任务 (MatPlotBench CSV + builtin fixtures)
├── _run_task()             # 单任务执行: system runner → 执行代码 → PlotTrace 评估
├── _execute_and_score()    # 执行生成代码 → 渲染图表 → 计算 data_fidelity
├── main()                  # argparse 入口
└── 各 system runner 注册到 SYSTEM_RUNNERS dict
```

### A.2 支持的系统

| 系统名 | Runner 函数 | 说明 |
|--------|------------|------|
| `ours` | `baseline_runners.run_ours` | NaturePheroViz PlotTrace 主系统 |
| `gpt4o_oneshot` | `baseline_runners.run_gpt4o_oneshot` | GPT-4o 单轮生成 |
| `claude_oneshot` | `baseline_runners.run_claude_oneshot` | Claude 单轮生成 |
| `qwen_zeroshot` | `baseline_runners.run_qwen_zeroshot` | Qwen-plus 零样本生成 |
| `lida` | `baseline_runners.run_lida` | LIDA 自动可视化框架 |
| `matplotagent` | `baseline_runners.run_matplotagent` | MatPlotAgent 占位 |

### A.3 数据集

| 数据集 | 来源 | 任务数 |
|--------|------|--------|
| `matplotbench` | MatPlotBench CSV 文件 | ~100（当前使用 17 个主任务） |
| `builtin` | 自建 fixtures | 4（sales_bar, revenue_bar, trend_line, pop_bar） |

### A.4 评估指标（绘图）

每次运行记录 `record.json`：

```json
{
  "task_id": "84",
  "exec_pass": true,
  "scores": {
    "data_fidelity": 0.67,
    "visual_form": 1.0,
    "series_cohesion": 0.8
  },
  "rounds_used": 2
}
```

- **exec_pass**：代码能否运行并生成图表
- **data_fidelity**：结构感知 F1（输出数据 vs 输入数据，1.0=完美）
- **visual_form**：图表类型正确性
- **series_cohesion**：数据系列完整性

### A.5 运行命令

```bash
python eval/run_benchmark.py --system gpt4o_oneshot --dataset matplotbench --out eval/results_bench
python eval/run_benchmark.py --system ours --dataset matplotbench --limit 5
python eval/metrics.py --results eval/results_bench --out eval/results_bench/aggregate
```
