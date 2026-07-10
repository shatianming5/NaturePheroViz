# A3 交付文档：Best-of-N + verifier 择优

> **任务卡**：`aaai_sprint_plan.md` §2 A3  
> **状态**：✅ 已完成  
> **负责人**：组员 A（方法 + 系统）  
> **前置依赖**：A1 `verify_fidelity`、A2 `overall_score` / `series_cohesion`（择优指标）  
> **核心文件**：`app/services/single_chain_runner.py`、`app/services/bon_comparison.py`、`scripts/compare_best_of_n.py`、`tests/test_smoke.py`

---

## 1. 一句话交付物

在 `single_chain_runner` 的**每一轮修复阶段**（第 2 轮起）对同一 feedback 状态采样 **N 个 LLM 候选**（默认 N=3），各自 render + `judge()`，按 **`exec_pass` + `overall_score`** 择优接受；**落败候选完整落盘**，并可用脚本对比 **N=1 vs N=3** 的难例收益。

**与 A1/A2 分工**：A1/A2 负责「怎么打分」；A3 负责「同一轮里试多个补丁、选最好的进入下一轮」。

---

## 2. 解决什么问题

| 旧行为 | 新行为（A3） |
|--------|--------------|
| 每轮 LLM 只出 1 套 slots | 第 2 轮起默认 **N=3** 候选 |
| 一次采样不佳只能等下一轮 | 同轮内择优，提高 pass@k 式成功率 |
| `iteration_N.json` 只有赢家 | 增加 `selected_index` + `candidates[]` |
| 无 BoN 消融对照 | `BEST_OF_N=1` 等价单候选；难例脚本可量化增益 |
| 多轮 feedback 曾引用未定义变量 | 已改为使用 **赢家** 的 `diagnostics` |

**典型场景**：

- 第 1 轮 default slots 图不达标 → 第 2 轮 LLM 改 L2–L4  
- 3 个候选里：1 个 exec 失败、1 个分中等、1 个 cohesion/保真更好 → **自动选第 3 个**进入下一轮或停机

---

## 3. 交付清单

| # | 交付项 | 位置 | 状态 |
|---|--------|------|------|
| 1 | `_best_of_n_count()` / `BEST_OF_N` | `single_chain_runner.py` | ✅ |
| 2 | 每轮 `run_candidate()` 闭包（独立 ctx/spec/slots/render/judge） | `single_chain_runner.py` | ✅ |
| 3 | 择优排序（exec_pass → overall_score → 诊断数 → index） | `single_chain_runner.py` | ✅ |
| 4 | 第 2 轮起 LLM `temperature=0.7` | `SlotLLMClient.chat_json` + `_candidate_temperature` | ✅ |
| 5 | 第 1 轮 **N=1**（default slots，避免 3 份相同代码） | `round_candidates = best_of_n if round_idx > 1 else 1` | ✅ |
| 6 | `iteration_N.json`：`selected_index` + `candidates[]` + `temperature` | `single_chain_runner.py` | ✅ |
| 7 | 落败者产物：`figure/code/slots_round_R_cand_K.*` | `runs/<ts>/` | ✅ |
| 8 | 多轮 feedback 用赢家 diagnostics | `compose_feedback(..., selected.get("diagnostics"))` | ✅ |
| 9 | 难例对比 harness | `bon_comparison.py` + `scripts/compare_best_of_n.py` | ✅ |
| 10 | 专项 pytest（**4 项 A3**） | `test_smoke.py` | ✅ |
| 11 | 参考 smoke | `runs/bon_compare_manual/` | ✅ |

**不在 A3 范围**：预算停机 / `stop_reason`（A4）、`--no-bestof` CLI（A5，当前可用 `BEST_OF_N=1`）、并行采样、真实 LLM 大规模 benchmark 报告。

---

## 4. 系统位置

```
run_chain → single_chain_runner.run_chain()
  │
  for round_idx in 1..rounds:
  │
  ├─ round_candidates = (round_idx > 1) ? BEST_OF_N : 1
  │
  ├─ for candidate_idx in 1..round_candidates:
  │     L1–L4 slots（round1=DEFAULT_V2；round≥2=LLM @ temp）
  │     → assemble → execute_script → judge()
  │     → 记录 candidate 分数与产物
  │
  ├─ ranked = sort(candidates)  # exec_pass, overall_score, ...
  ├─ chosen = ranked[0]
  ├─ 写入 iteration_{round}.json（含 candidates + selected_index）
  ├─ overall_score >= 0.75 → break
  └─ compose_feedback(赢家的 diagnostics) → 下一轮
```

| 组件 | 作用 |
|------|------|
| `judge()` | 每个候选独立打分；**择优主指标**为 `overall_score`（含 A1+A2） |
| `overall_score` | A2 归一化加权；BoN **不另造公式** |
| `feedback_builder` | 只接收**赢家**诊断，驱动下一轮 LLM |

---

## 5. 算法细节

### 5.1 候选数 N

```python
def _best_of_n_count() -> int:
    raw = os.getenv("BEST_OF_N") or os.getenv("BON_N") or "3"
    ...
    return max(1, value)
```

| 环境变量 | 含义 |
|----------|------|
| `BEST_OF_N` | 主配置，默认 **3** |
| `BON_N` | 别名 |
| `BEST_OF_N=1` | 关闭 BoN（单候选），供消融 |

### 5.2 哪一轮启用 BoN

```python
round_candidates = best_of_n if round_idx > 1 else 1
```

| 轮次 | N | LLM | 原因 |
|------|---|-----|------|
| **第 1 轮** | 1 | 不走 LLM（`DEFAULT_STAGE_SLOTS_V2`） | 三份 default 完全相同，BoN 无收益 |
| **第 2 轮起** | `BEST_OF_N` | `_llm_generate_slots(..., temperature=0.7)` | 有 feedback，需要多样性 |

### 5.3 采样温度

```python
def _candidate_temperature(round_idx, candidate_idx, total_candidates):
    if total_candidates <= 1:
        return 0.2
    if round_idx <= 1:
        return 0.2
    return 0.7
```

- 单候选 / 第 1 轮：**0.2**（稳定）  
- 第 2 轮起多候选：**0.7**（plan 要求的「更散」采样）  
- 当前**未**按 `candidate_idx` 再细分温度；多样性主要来自 LLM 随机性

### 5.4 择优规则

```python
ranked = sorted(
    candidates,
    key=lambda item: (
        1 if item.get("exec_pass") else 0,
        float((item.get("scores") or {}).get("overall_score", 0.0)),
        -len(item.get("diagnostics") or []),
        -item.get("candidate_index", 0),
    ),
    reverse=True,
)
chosen = ranked[0]
```

优先级：

1. **`exec_pass`**（代码跑通、有 PNG）  
2. **`overall_score`** 越高越好  
3. 诊断条数越少越好（tie-break）  
4. `candidate_index` 越大越好（最后 tie-break）

### 5.5 状态继承

- 每个候选从 **同一轮开始时的 `ctx` / `spec` 深拷贝** 出发，互不影响。  
- 只有 **赢家** 的 `ctx` / `spec` 写回主循环，供下一轮使用。

---

## 6. 落盘格式

### 6.1 `iteration_N.json`（新增字段）

在原有 `round / scores / spec / slots / diagnostics / ...` 基础上：

```json
{
  "round": 2,
  "selected_index": 3,
  "scores": { "visual_form": 1.0, "data_fidelity": 0.14, "series_cohesion": 1.0, "overall_score": 0.67 },
  "candidates": [
    {
      "candidate_index": 1,
      "temperature": 0.7,
      "exec_pass": true,
      "png_path": "runs/.../figure_round_2_cand_1.png",
      "scores": { "...": 0.51 },
      "diagnostics": [ "..." ],
      "stderr": "...",
      "code_path": "runs/.../code_round_2_cand_1.py",
      "slots_path": "runs/.../slots_round_2_cand_1.json"
    }
  ]
}
```

顶层 `png_path / scores / diagnostics` = **赢家** 快照（与旧消费方兼容）。

### 6.2 文件命名

| 模式 | 示例 |
|------|------|
| 图 | `figure_round_{R}_cand_{K}.png` / `.svg` |
| 代码 | `code_round_{R}_cand_{K}.py` |
| slots | `slots_round_{R}_cand_{K}.json` |
| 迭代记录 | `iteration_{R}.json` |

---

## 7. 难例对比（N=1 vs N=3）

### 7.1 脚本

```powershell
cd NaturePheroViz/agent
python scripts/compare_best_of_n.py --output-dir runs/bon_compare_manual
```

产出：

- `bon_hard_case_compare.json` / `.csv`  
- `chain_runs/<timestamp>_n1/`、`..._n3/` 两套完整 run

### 7.2 难例设计（`bon_comparison.py`）

- 数据：两系列折线 `actual` / `target`（4 个月）  
- **第 1 轮**：三候选均渲染为「低分基线」（同色、无 legend、数值偏差）→ 不达标，进入第 2 轮  
- **第 2 轮**（mock 执行器按 `_cand_K` 渲染不同质量）：
  - cand 1：仍低分  
  - cand 2：中等  
  - cand 3：可分色 + legend + 更高保真  

### 7.3 参考结果（`runs/bon_compare_manual/bon_hard_case_compare.json`）

| 指标 | N=1 | N=3 |
|------|-----|-----|
| 第 2 轮 `overall_score` | **0.512** | **0.670** |
| `selected_index` | 1 | **3** |
| `series_cohesion` | 0.55 | **1.0** |
| 相对增益 | — | **+0.159** |

说明：该对比使用 **确定性 mock 渲染 + 真 judge**，用于证明择优逻辑与指标链路；论文主实验仍需 MatPlotBench + 真 LLM。

---

## 8. 验收标准与测试

| 验收项 | 测试 |
|--------|------|
| 第 2 轮 BoN 选最高分且跳过 exec_fail | `test_run_chain_best_of_n_selects_highest_scored_exec_pass_after_round_one` |
| 第 1 轮仅 1 候选 | `test_run_chain_round_one_uses_single_candidate_by_default` |
| 多轮 feedback 用赢家 diagnostics | `test_run_chain_multiround_feedback_uses_chosen_diagnostics` |
| N=3 难例优于 N=1 | `test_best_of_n_hard_case_comparison_shows_real_gain` |

```powershell
cd NaturePheroViz/agent
python -m pytest tests/test_smoke.py -q --basetemp .\tmp_pytest
# 期望：24 passed（含 A1/A2/A3 全量 smoke）
```

仅跑 A3 相关：

```powershell
python -m pytest tests/test_smoke.py -q -k "best_of_n or round_one_uses_single or multiround_feedback" --basetemp .\tmp_pytest
```

---

## 9. 与 A1 / A2 / A4 / A5 的关系

| 模块 | 关系 |
|------|------|
| **A1** | 每个候选各自 `verify_fidelity` → `data_fidelity` 进入 `overall_score` |
| **A2** | `series_cohesion` 影响择优；难例中 cand3 因 legend/样式更好而 cohesion↑ |
| **A4** | BoN 使每轮成本 ×N；预算停机需在 A4 与 BoN 联调 |
| **A5** | 计划 `--no-bestof`；**当前**用 `BEST_OF_N=1` 代替 |

写论文时：BoN 可作为 **process 指标**（pass@k / 同轮择优增益），与 A1 硬保真主结论互补。

---

## 10. ⚠️ 已知局限与注意事项

| 项 | 说明 |
|----|------|
| 第 1 轮不 BoN | 与 plan 字面「每轮 N=3」不同；**有意设计**，见 §5.2 |
| 候选顺序执行 | N 个候选串行跑，非并行；大 benchmark 需计 token×N |
| 温度不随 K 变化 | 同轮候选均为 0.7；未实现 per-candidate 温度 schedule |
| mock 难例 ≠ 真 LLM | 难例对比证明**机制**；真 API 下增益需另跑 |
| 无 `A5 --no-bestof` | 环境变量已够用；CLI 开关留给 A5 |
| README 未同步 | 仍可能写旧停机/无 BoN 描述 |

---

## 11. 配置速查

```powershell
# 默认 BoN=3
python run_chain.py data/actual_target_plan.csv "actual vs month" line --rounds 2

# 关闭 BoN（消融）
$env:BEST_OF_N = "1"
python run_chain.py data/actual_target_plan.csv "actual vs month" line --rounds 2

# 强制跑满 rounds（不因 0.75 提前停）
$env:FORCE_ALL_ROUNDS = "1"
```

---

## 12. 复现与调试

查看某轮全部候选分数：

```python
import json
from pathlib import Path

p = Path("runs/bon_compare_manual/chain_runs/20260611T230002_n3/iteration_2.json")
data = json.loads(p.read_text(encoding="utf-8"))
print("winner", data["selected_index"], data["scores"]["overall_score"])
for c in data["candidates"]:
    print(c["candidate_index"], c["exec_pass"], c["scores"]["overall_score"], c.get("temperature"))
```

---

## 13. 后续工作

| 任务 | 说明 |
|------|------|
| **A4** | 预算耗尽 / ΔJ 早停 / `stop_reason`；与 BoN 成本模型一起写进论文 |
| **A5** | `--no-bestof`、`--no-verifier`、`--no-pheromone` |
| **文档** | 同步 `README.md`、`A1_delivery.md` 中「A3 待做」表述 |
| **实验** | MatPlotBench 上 N=1 vs N=3 pass@k；落败候选池供 future DPO |

---

## 14. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-11 | A3 完成：BoN 择优 + 第 1 轮 N=1 + temp 0.7 + iteration 候选落盘 + 4 项 pytest |
| 2026-06-11 | 修复多轮 `compose_feedback` 使用赢家 diagnostics |
| 2026-06-11 | 难例脚本 `compare_best_of_n.py`；参考 `runs/bon_compare_manual/`（N=3 +0.159 overall） |

---

**签收**：A3 可标记为 **Done**。请 lead 同步 README；A5 补 CLI 别名 `--no-bestof`。

**相关文档**：[A1_delivery.md](./A1_delivery.md) · [A2_delivery.md](./A2_delivery.md)
