# A4 交付文档：预算停机（budget-forcing）

> **任务卡**：`aaai_sprint_plan.md` §2 A4  
> **状态**：✅ 已完成  
> **负责人**：组员 A（方法 + 系统）  
> **前置依赖**：A2 `overall_score`（停机判据）、A3 Best-of-N（每轮成本 ×N）  
> **核心文件**：`app/services/single_chain_runner.py`、`tests/test_smoke.py`

---

## 1. 一句话交付物

将旧版「跑满 `rounds` 或单一 `>=0.75` 早停」替换为 **三种互斥停机原因**（`score_threshold` / `no_progress` / `budget_exhausted`），并在检测到 **无进展** 时 **先强制一轮 deeper 修复**（追加更强 feedback），仅当 deeper 轮仍无改进才以 `no_progress` 停机；全程写入 `iteration_N.json` 的 `stop_reason` / `stop_detail`。

**与 A3 分工**：A3 负责「同轮试多个候选」；A4 负责「何时停止整条链、是否再给一次机会」。

---

## 2. 解决什么问题

| 旧行为 | 新行为（A4） |
|--------|--------------|
| 分数 < 0.75 时空转满 `rounds` | 连续无进展 → **deeper 一轮** → 仍无进展则 **提前停** |
| 无停机原因字段 | `stop_reason` + `stop_detail` 落盘 |
| 达标 0.75 即停（保留） | `stop_reason: score_threshold` |
| 预算用尽无显式标记 | `stop_reason: budget_exhausted` |
| 局部 tweak 反复无效 | deeper feedback 要求 **mapping / mark / scale / legend / layout 联合重审** |

**典型场景**（修不动难例）：

- 第 1 轮 default 图 `overall_score=0.50`
- 第 2 轮 LLM 微调仍 `0.50` → **不立刻停**，标记 `deeper_retry_forced`，追加 *Deeper retry required* feedback
- 第 3 轮仍 `0.50` → `stop_reason: no_progress`，`rounds=5` 时实际只跑 3 轮

---

## 3. 交付清单

| # | 交付项 | 位置 | 状态 |
|---|--------|------|------|
| 1 | 三种 `stop_reason` | `single_chain_runner.py` | ✅ |
| 2 | ΔJ 停滞检测（`stall_rounds` + `STALL_DELTA`） | `_stall_delta()` + 主循环 | ✅ |
| 3 | **deeper 强制轮**（预算未尽时延迟 `no_progress`） | `deeper_retry_used` / `request_deeper_retry` | ✅ |
| 4 | deeper feedback 文案注入 L1–L4 prompt | `feedback_text` 后缀 | ✅ |
| 5 | `iteration_N.json`：`stop_reason` / `stop_detail` / `deeper_retry_forced` | 主循环 | ✅ |
| 6 | `FORCE_ALL_ROUNDS` 绕过所有早停 | `_env_flag` | ✅ |
| 7 | `run_chain.py` 摘要展示停止原因 | CLI summary | ✅ |
| 8 | 专项 pytest（**2 项 A4**） | `test_smoke.py` | ✅ |

**不在 A4 范围**：消融开关（A5）、BoN 择优逻辑（A3）、自动扩 `rounds` 预算（仍由 CLI `--rounds` 控制）。

---

## 4. 系统位置

```
run_chain → single_chain_runner.run_chain(rounds=R)
  │
  for round_idx in 1..R:
  │   render + judge → current_overall
  │   improvement = current_overall - prev_overall
  │   if improvement <= STALL_DELTA → stall_rounds++
  │
  ├─ overall_score >= 0.75  → stop_reason=score_threshold → break
  │
  ├─ stall_rounds>=1 且 round_idx>=2:
  │     ├─ round_idx < R 且 deeper_retry_used=False
  │     │     → deeper_retry_forced=True，追加 deeper feedback → 继续下一轮
  │     └─ 否则 → stop_reason=no_progress → break
  │
  └─ round_idx >= R → stop_reason=budget_exhausted（写最后一轮 artifact）
```

| 组件 | 作用 |
|------|------|
| `overall_score` | A2 加权分；**唯一早停阈值判据**（0.75） |
| `compose_feedback` | 常规轮间 feedback；deeper 轮在其后追加固定段落 |
| `FORCE_ALL_ROUNDS` | 评测 / debug 用，禁用 score 与 no_progress 早停 |

---

## 5. 算法细节

### 5.1 停滞阈值

```python
def _stall_delta() -> float:
    raw = os.getenv("STALL_DELTA") or os.getenv("BUDGET_FORCE_DELTA") or "0.01"
    ...
    return max(0.0, value)
```

| 环境变量 | 含义 |
|----------|------|
| `STALL_DELTA` | 主配置，默认 **0.01** |
| `BUDGET_FORCE_DELTA` | 别名 |
| `FORCE_ALL_ROUNDS=1` | 跑满 `--rounds`，不因达标或无进展提前 break |

判定：`improvement = current_overall - prev_overall`；若 `improvement <= stall_threshold`，则 `stall_rounds += 1`，否则清零。

### 5.2 三种停机原因

| `stop_reason` | 触发条件 | `stop_detail` 要点 |
|---------------|----------|-------------------|
| `score_threshold` | `overall_score >= 0.75` 且未设 `FORCE_ALL_ROUNDS` | `threshold`, `overall_score` |
| `no_progress` | 已用过 deeper 强制轮 **或** 预算不足以再跑 deeper，且仍停滞 | `stall_rounds`, `stall_delta`, `improvement`, `deeper_retry_used` |
| `budget_exhausted` | 跑完 `--rounds` 仍未达标、未触发 no_progress 早停 | `max_rounds`, `overall_score` |

### 5.3 deeper 强制轮（新语义）

```python
if stall_rounds >= 1 and round_idx >= 2:
    if round_idx < max(1, rounds) and not deeper_retry_used:
        deeper_retry_used = True
        request_deeper_retry = True
        selected["deeper_retry_forced"] = True
    else:
        stop_reason = "no_progress"
        ...
        break
```

**语义对照 sprint 要求**：

1. **未达标**（`< 0.75`）  
2. **预算未尽**（`round_idx < rounds`）  
3. **已判断无进展**（`stall_rounds >= 1` 且 `round_idx >= 2`）  

→ **不立刻 `no_progress`**，而是消耗 **唯一一次** deeper 机会；deeper 轮结束后若分数仍不涨，才 `no_progress`。

deeper feedback 追加内容（固定英文，便于 LLM 解析）：

```
Deeper retry required:
- Previous round did not improve enough.
- Change more than surface styling; revisit mapping, mark choice, scale, legend, and layout together.
- Prefer a materially different repair over a local tweak.
```

**边界**：

- `rounds=2` 且第 2 轮停滞：无剩余预算给 deeper → **直接** `no_progress`（符合「预算未尽才 deeper」）  
- 每条链 **至多 1 次** deeper（`deeper_retry_used` 全局 flag）  
- deeper 轮若分数回升（`improvement > STALL_DELTA`），`stall_rounds` 清零，链继续正常迭代

---

## 6. 落盘格式

### 6.1 `iteration_N.json`（A4 相关字段）

**触发 deeper 的那一轮**（例如第 2 轮）：

```json
{
  "round": 2,
  "scores": { "overall_score": 0.50 },
  "deeper_retry_forced": true,
  "stop_reason": null
}
```

**最终 `no_progress` 停机轮**（例如第 3 轮）：

```json
{
  "round": 3,
  "stop_reason": "no_progress",
  "stop_detail": {
    "stall_rounds": 3,
    "stall_delta": 0.01,
    "overall_score": 0.50,
    "improvement": 0.0,
    "deeper_retry_used": true
  }
}
```

**达标早停**：

```json
{
  "stop_reason": "score_threshold",
  "stop_detail": { "threshold": 0.75, "overall_score": 0.80 }
}
```

顶层 `run_chain` 返回值同样携带 `stop_reason` / `stop_detail`，供 CLI 与 B 侧 harness 读取。

---

## 7. 验收标准与测试

| 验收项（plan） | 测试 / 证据 |
|----------------|-------------|
| 修不动例子：旧逻辑跑满 rounds，新逻辑 deeper 后仍无效则提前停 | `test_run_chain_stops_after_two_rounds_without_progress` |
| 无进展时 **先** deeper 再停 | `test_run_chain_forces_deeper_retry_before_no_progress_stop` |
| `iteration_N.json` 记 `stop_reason` | 两测试均断言 + artifact 落盘 |

### 7.1 `test_run_chain_stops_after_two_rounds_without_progress`

- 输入：`rounds=5`，mock judge 恒返回 `overall_score=0.50`  
- 期望：
  - 实际停在 **第 3 轮**（第 2 轮触发 deeper，第 3 轮仍停滞才停）
  - `stop_reason == "no_progress"`
  - `stop_detail.deeper_retry_used is True`
  - `feedback_calls == [1, 2]`（比旧版多跑一轮）

### 7.2 `test_run_chain_forces_deeper_retry_before_no_progress_stop`

- 输入：`rounds=3`，全程停滞  
- 期望：`progress_callback` 收到的 feedback 中含 **`Deeper retry required`**

```powershell
cd NaturePheroViz/agent
python -m pytest tests/test_smoke.py -q -k "stop or deeper" --basetemp .\tmp_pytest
# 期望：2 passed
```

全量 smoke（含 A1–A5）：

```powershell
python -m pytest tests/test_smoke.py -q --basetemp .\tmp_pytest
# 期望：31 passed（含 A4 两项）
```

---

## 8. 与 A1 / A2 / A3 / A5 的关系

| 模块 | 关系 |
|------|------|
| **A2** | `overall_score` 驱动达标停与 ΔJ 停滞检测 |
| **A3** | BoN 使每轮成本 ×N；A4 的 `rounds` 是 **外环轮数**，与 BoN 正交 |
| **A5** | `FORCE_ALL_ROUNDS` 可与 `--no-bestof` 等组合做消融 |
| **B harness** | 建议读 `stop_reason` / `rounds_used` 统计平均成本 |

写论文时：可将 **deeper retry** 描述为 budget-forcing 的「最后一搏」策略，与 flat-line 早停一起报告 **平均轮数 ↓** 且不牺牲 pass@1。

---

## 9. ⚠️ 已知局限

| 项 | 说明 |
|----|------|
| deeper 为 **prompt 级** 加深 | 未改 L1–L4 slot 权限或单独升温；靠 feedback 文案驱动 |
| 每条链仅 **1 次** deeper | 非可配置 N；足够覆盖 sprint 验收 |
| `rounds=2` 难例 | 无 budget 给 deeper，行为退化为「第 2 轮即 no_progress」 |
| 无独立 `score_threshold` / `budget_exhausted` 单测 | 逻辑已在主循环；可按需补 mock 测试 |
| README 可能未同步 | 停机语义以本文为准 |

---

## 10. 配置速查

```powershell
# 默认：最多 5 轮，达标 0.75 或无进展（含 deeper）早停
python run_chain.py data/actual_target_plan.csv "actual vs month" line --rounds 5

# 调停滞灵敏度（ΔJ <= 0.005 算无进展）
$env:STALL_DELTA = "0.005"

# 强制跑满 rounds（消融 / 对照旧行为）
$env:FORCE_ALL_ROUNDS = "1"
python run_chain.py data/actual_target_plan.csv "goal" line --rounds 5
```

---

## 11. 复现与调试

```python
import json
from pathlib import Path

run_dir = Path("runs/<timestamp>")
for p in sorted(run_dir.glob("iteration_*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    print(
        p.name,
        data.get("scores", {}).get("overall_score"),
        data.get("deeper_retry_forced"),
        data.get("stop_reason"),
    )
```

---

## 12. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-15 | A4 初版：三种 stop_reason + stall 检测 |
| 2026-06-15 | **新语义**：无进展时先 `deeper_retry_forced` 一轮，再 `no_progress`；2 项 pytest 更新 |

---

**签收**：A4 可标记为 **Done**。deeper 强制轮已实现并通过测试。

**相关文档**：[A2_delivery.md](./A2_delivery.md) · [A3_delivery.md](./A3_delivery.md) · [A5_delivery.md](./A5_delivery.md)
