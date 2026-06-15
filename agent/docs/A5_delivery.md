# A5 交付文档：消融开关（实验用）

> **任务卡**：`aaai_sprint_plan.md` §2 A5  
> **状态**：✅ 已完成  
> **负责人**：组员 A（方法 + 系统）  
> **前置依赖**：A1 `verify_fidelity`、A3 Best-of-N、pheromone 记忆链路  
> **核心文件**：`run_chain.py`、`app/services/single_chain_runner.py`、`app/services/judge.py`、`app/services/ablation_runner.py`、`scripts/run_ablation_suite.py`、`tests/test_smoke.py`

---

## 1. 一句话交付物

为 agent 内环提供 **三套（+pheromone 第四套）可复现消融配置**：CLI `--no-verifier` / `--no-bestof` / `--no-pheromone` 及对应环境变量，统一传入 `run_chain()`；每轮 `iteration_N.json` 记录 `ablation` 块；B 同学可用 **`scripts/run_ablation_suite.py` 一条命令** 批量产出 CSV 汇总表。

**论文用途**：分别量化 **硬保真验证器**、**Best-of-N 择优**、**pheromone 引导** 对 pass rate / overall_score 的边际贡献。

---

## 2. 解决什么问题

| 无开关（旧） | 新行为（A5） |
|--------------|--------------|
| 无法关闭 SVG 保真验证 | `--no-verifier` → judge 跳过 `verify_fidelity`，退回列名启发式 |
| BoN 只能改 `BEST_OF_N` 环境变量 | `--no-bestof` → 强制 `N=1`（与 env 双通道） |
| pheromone 无法对照 | `--no-pheromone` → 不写记忆、不追加 feedback 后缀 |
| 消融需手写多份脚本 | `run_ablation_suite.py` 四配置 × 多 case 一键跑 |

---

## 3. 交付清单

| # | 交付项 | 位置 | 状态 |
|---|--------|------|------|
| 1 | CLI：`--no-verifier` / `--no-bestof` / `--no-pheromone` | `run_chain.py` | ✅ |
| 2 | 环境变量：`NO_VERIFIER` / `NO_BESTOF` / `NO_PHEROMONE` | `single_chain_runner.run_chain` | ✅ |
| 3 | `run_chain(..., use_verifier, use_best_of_n, use_pheromone)` | `single_chain_runner.py` | ✅ |
| 4 | `judge(..., use_verifier=False)` 启发式保真路径 | `judge.py` | ✅ |
| 5 | `use_best_of_n=False` → `best_of_n=1` | 主循环 | ✅ |
| 6 | `use_pheromone=False` → 跳过 store / feedback suffix | `_append_pheromone_links` 等 | ✅ |
| 7 | `iteration_N.json` → `ablation` 块 | 每轮 selected | ✅ |
| 8 | 批量 suite：`ablation_runner.py` + `scripts/run_ablation_suite.py` | 产出 CSV/JSON | ✅ |
| 9 | 专项 pytest（**4 项 A5**） | `test_smoke.py` | ✅ |

**超出 plan 最小验收**：除「全开 / 关验证器 / 关 BoN」外，额外提供 **`no_pheromone`** 第四配置（同一 suite 命令）。

---

## 4. 系统位置

```
run_chain.py CLI
  ├─ --no-verifier  ─┐
  ├─ --no-bestof    ─┼─→ run_chain(use_verifier, use_best_of_n, use_pheromone)
  └─ --no-pheromone ─┘
        │
        ├─ use_verifier=False → judge(..., use_verifier=False)  【A1 关】
        ├─ use_best_of_n=False → round_candidates=1             【A3 关】
        └─ use_pheromone=False → 无 PheroStore 写入/后缀         【记忆关】
        │
        └─ iteration_N.json["ablation"] 落盘

scripts/run_ablation_suite.py
  └─ ablation_runner.run_ablation_suite()
        └─ for case × config in {full, no_verifier, no_bestof, no_pheromone}
              → run_chain(...) → ablation_runs.csv / ablation_aggregates.csv
```

---

## 5. 开关语义

### 5.1 参数与环境变量

```python
use_verifier = bool(use_verifier) and not _env_flag("NO_VERIFIER", default=False)
use_best_of_n = bool(use_best_of_n) and not _env_flag("NO_BESTOF", default=False)
use_pheromone = bool(use_pheromone) and not _env_flag("NO_PHEROMONE", default=False)
```

| 开关 | CLI | 环境变量 | 关闭后的行为 |
|------|-----|----------|--------------|
| 保真验证器 | `--no-verifier` | `NO_VERIFIER=1` | `judge` 不调用 `verify_fidelity`；`data_fidelity` 走列名/VLM 启发式 |
| Best-of-N | `--no-bestof` | `NO_BESTOF=1` | `best_of_n=1`，第 2 轮起也仅 1 候选 |
| Pheromone | `--no-pheromone` | `NO_PHEROMONE=1` | 不 `_append_pheromone_links`；feedback 无 pheromone 尾注 |

**优先级**：CLI 传入 `use_*=False` 与环境变量 **叠加生效**（任一为关则关）。

### 5.2 `--no-verifier` 与 A1 的关系

```python
# judge.py
if use_verifier:
    fidelity = verify_fidelity(...)
else:
    fidelity = { 'data_fidelity': nan, ... }  # 跳过硬验证
# 非 VLM 路径下用 overlay 列名匹配启发式 fid
```

消融 **硬保真** 时用这个开关；**不是**删除 A1 代码路径。

### 5.3 `--no-bestof` 与 A3 的关系

```python
best_of_n = _best_of_n_count() if use_best_of_n else 1
round_candidates = best_of_n if round_idx > 1 else 1
```

等价于 `BEST_OF_N=1`，但 CLI 更利于 B 侧 benchmark runner 传参。

### 5.4 `--no-pheromone`

关闭时：

- 不创建/写入 `PheroStore` 链接  
- `iteration_N.json` 中 `pheromone_summary.total == 0`  
- 第 2 轮起 LLM prompt **不含** `Pheromone memory:` 后缀  

开启时，诊断项按类型写入 store，并通过 `_pheromone_feedback_suffix` 注入最近 tail。

---

## 6. 落盘格式

### 6.1 `iteration_N.json` → `ablation`

```json
{
  "ablation": {
    "use_verifier": true,
    "use_best_of_n": true,
    "use_pheromone": false,
    "best_of_n": 3
  },
  "pheromone_summary": { "total": 0, "by_type": {} },
  "pheromone_tail": []
}
```

`best_of_n` 反映 **实际候选数上限**（关 BoN 时为 1）。

### 6.2 批量 suite 产出

运行：

```powershell
cd NaturePheroViz/agent
python scripts/run_ablation_suite.py --rounds 2 --output-dir runs/ablation_demo
```

产出目录：

| 文件 | 内容 |
|------|------|
| `ablation_runs.json` | 全量 run 记录 |
| `ablation_runs.csv` | 每 case×config 一行（含 `stop_reason`, scores） |
| `ablation_aggregates.csv` | 按 config 聚合均值 |

默认 **4 配置**：

```python
DEFAULT_CONFIGS = [
    {"name": "full",         "use_verifier": True,  "use_best_of_n": True,  "use_pheromone": True},
    {"name": "no_verifier",  "use_verifier": False, "use_best_of_n": True,  "use_pheromone": True},
    {"name": "no_bestof",    "use_verifier": True,  "use_best_of_n": False, "use_pheromone": True},
    {"name": "no_pheromone", "use_verifier": True,  "use_best_of_n": True,  "use_pheromone": False},
]
```

默认 **3 个 smoke case**（`data/actual_target_plan.csv` 等）；可在代码中扩展 `DEFAULT_CASES`。

---

## 7. 验收标准与测试

| 验收项（plan） | 测试 |
|----------------|------|
| B 用同一命令跑全开 / 关验证器 / 关 BoN | `test_run_ablation_suite_writes_summary_tables` |
| `--no-bestof` → N=1 | `test_run_chain_no_bestof_forces_single_candidate_in_later_rounds` |
| `--no-verifier` → judge 不走 verifier | `test_run_chain_no_verifier_disables_fidelity_verifier_path` |
| `--no-pheromone` / 开 pheromone 行为差 | `test_run_chain_pheromone_changes_round_two_feedback` |

```powershell
cd NaturePheroViz/agent
python -m pytest tests/test_smoke.py -q -k "no_bestof or no_verifier or pheromone or ablation" --basetemp .\tmp_pytest
# 期望：4 passed
```

---

## 8. B 同学对接指南

### 8.1 单样本 CLI

```powershell
# 全开（默认）
python run_chain.py data/actual_target_plan.csv "计划与实际趋势" line --rounds 3

# 关验证器
python run_chain.py data/actual_target_plan.csv "计划与实际趋势" line --rounds 3 --no-verifier

# 关 BoN
python run_chain.py data/actual_target_plan.csv "计划与实际趋势" line --rounds 3 --no-bestof

# 关 pheromone
python run_chain.py data/actual_target_plan.csv "计划与实际趋势" line --rounds 3 --no-pheromone

# 组合消融
python run_chain.py data/actual_target_plan.csv "goal" line --rounds 3 --no-verifier --no-bestof
```

### 8.2 批量 harness

```powershell
python scripts/run_ablation_suite.py --rounds 2 --output-dir runs/ablation_matplot_smoke
```

读 `ablation_aggregates.csv` 对比 `avg_overall_score` / `avg_rounds_used` / config 列。

### 8.3 建议写入 `record.json` 的字段

从 `run_chain` 返回值或最后一轮 `iteration_N.json` 提取：

- `ablation.use_verifier` / `use_best_of_n` / `use_pheromone`  
- `scores.overall_score` / `data_fidelity` / `series_cohesion`  
- `stop_reason`（见 [A4_delivery.md](./A4_delivery.md)）  
- `round`（实际使用轮数）

---

## 9. 与 A1 / A3 / A4 的关系

| 模块 | A5 如何关 / 留 |
|------|----------------|
| **A1** | `--no-verifier` 关闭硬保真；A1 代码仍部署，消融对照用 |
| **A3** | `--no-bestof` 或 `NO_BESTOF=1`；等价 `BEST_OF_N=1` |
| **A4** | 消融 run 仍受 budget-forcing 约束；可用 `FORCE_ALL_ROUNDS` 固定成本 |
| **A2** | 无独立开关；cohesion 始终参与 `overall_score` |

论文表格建议行：`Full` / `-Verifier` / `-BoN` / `-Pheromone` / `-Verifier-BoN`（后项可用 CLI 组合）。

---

## 10. ⚠️ 已知局限

| 项 | 说明 |
|----|------|
| 无 `--no-cohesion` | plan 未要求；cohesion 与 visual 未拆开关 |
| suite 默认 3 个本地 CSV | MatPlotBench 大规模跑需 B 侧替换 `cases` |
| env 与 CLI 双通道 | 同时设 env 关、CLI 开时以 **合并 AND** 为准（见 §5.1） |
| README 可能未列全 flag | 以本文与 `run_chain.py --help` 为准 |

---

## 11. 配置速查

```powershell
# 环境变量方式（适合 shell 批跑）
$env:NO_VERIFIER = "1"
$env:NO_BESTOF = "1"
$env:NO_PHEROMONE = "1"
python run_chain.py data/product_scatter.csv "区域品类分布" scatter --rounds 2

# 清除
Remove-Item Env:NO_VERIFIER, Env:NO_BESTOF, Env:NO_PHEROMONE -ErrorAction SilentlyContinue
```

---

## 12. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-15 | A5 完成：CLI + env + ablation 落盘 + suite 脚本 + 4 项 pytest |
| 2026-06-15 | suite 第四配置 `no_pheromone`（超 plan 最小三套） |

---

**签收**：A5 可标记为 **Done**。B 可用 `run_ablation_suite.py` 或 CLI flag 复现消融。

**相关文档**：[A1_delivery.md](./A1_delivery.md) · [A3_delivery.md](./A3_delivery.md) · [A4_delivery.md](./A4_delivery.md)
