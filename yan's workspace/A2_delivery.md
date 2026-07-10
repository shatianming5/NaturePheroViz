# A2 交付文档：系列一致性 `series_cohesion` + 综合分 `overall_score`

> **任务卡**：`aaai_sprint_plan.md` §2 A2  
> **状态**：✅ 已完成（含渲染优先 cohesion 增强）  
> **负责人**：组员 A（方法 + 系统）  
> **前置依赖**：A1 `verify_fidelity`（`data_fidelity`）、matplotlib 同目录 `.svg`  
> **核心文件**：`app/services/judge.py`、`configs/judge_rules.yml`、`configs/diagnostics_map.yml`、`app/services/single_chain_runner.py`、`app/services/feedback_builder.py`、`run_chain.py`、`tests/test_smoke.py`

---

## 1. 一句话交付物

在 Judge 中新增第三维 **`series_cohesion`（多系列版式是否协调）**，**优先从渲染 SVG 读回图例 / 样式 / 轴文本 / x 顺序**；并按 `judge_rules.yml` 权重计算 **归一化综合分 `overall_score`**，接入停机、反馈与 CLI 展示。

**与 A1 分工**：A1 验「数对不对」（SVG 几何 → 数值）；A2 验「多条线/多组柱放在一起好不好读、会不会误导」（SVG 版式 → 协调规则）。

---

## 2. 解决什么问题

| 旧行为 | 新行为（A2） |
|--------|--------------|
| Judge 只有 `visual_form` + `data_fidelity` | 增加 `series_cohesion` |
| 停机条件：`VF≥0.75 且 DF≥0.75` | 停机条件：**`overall_score ≥ 0.75`** |
| `judge_rules.yml` 权重写了但未消费 | `_weighted_score()` 真正参与打分 |
| 多系列问题无专门分 | **渲染侧**规则检查 + 诊断 + 扣分 |
| 早期 A2 只看 `spec`（说明书合规） | **当前：渲染结果优先**，spec 作兜底 |

**典型能抓的问题**（数可能对，但图很糟）：

- 两条线/两组柱 **渲染出来同色** → `series.style.conflict`
- 多系列但 **SVG 里没有 `legend_*`**（即使 spec 写了 `outside right`）→ `legend.missing.multi`
- `share_ratio` 与 `sales` **挤在同一 y 轴**（spec 兜底）或双轴但左右单位模式相同（SVG 启发式）→ `ratio.axis.mismatch`
- x 轴 **类目顺序**与数据表不一致（VisEval 思路）→ `x.inconsistent`
- 不同 overlay 使用不同 x 列名（spec）→ `x.inconsistent`

---

## 3. 交付清单

| # | 交付项 | 位置 | 状态 |
|---|--------|------|------|
| 1 | `_series_cohesion()` 渲染优先评分 | `judge.py` | ✅ |
| 2 | SVG 辅助：line/bar 样式、legend、轴文本、x tick | `judge.py` | ✅ |
| 3 | `cohesion_checks` 配置开关 | `judge_rules.yml` | ✅ |
| 4 | cohesion 诊断映射 | `diagnostics_map.yml` | ✅ |
| 5 | `judge()` 返回 `series_cohesion` / `overall_score` | `judge.py`（VLM / 规则两路） | ✅ |
| 6 | 停机改用 `overall_score` | `single_chain_runner.py` | ✅ |
| 7 | `iteration_N.json` 写入四项分数 | `single_chain_runner.py` | ✅ |
| 8 | 下一轮反馈展示综合分 | `feedback_builder.py` | ✅ |
| 9 | CLI 展示 J / VF / DF / Cohesion | `run_chain.py` | ✅ |
| 10 | 专项 pytest（**9 项 A2**） | `test_smoke.py` | ✅ |
| 11 | 全链路 smoke | `runs/20260610T212253/` 等 | ✅ |

**不在 A2 范围**：Best-of-N（A3）、预算停机 / `stop_reason`（A4）、`--no-verifier` 等消融（A5）、跨 panel / 复杂 legend 布局、完整单位语义解析。

---

## 4. 系统位置（与 A1、VLM 的关系）

```
judge(png, exec_log, df, spec)
  │
  ├─ [A1] verify_fidelity(svg, ...)  → data_fidelity, fidelity_detail, pred_table
  ├─ [A2] _series_cohesion(spec, df, png_path, df)
  │         └─ 读 png 同目录 .svg（复用 fidelity_verifier 的 bounds/ticks 工具）
  ├─ visual_form                       → 规则像素启发式 或 VLM 软分
  └─ [A2] _weighted_score(...)         → overall_score

single_chain_runner
  └─ overall_score >= 0.75 → break（停机）
```

| 分数 | 问什么 | 数据来源 |
|------|--------|----------|
| `data_fidelity` | 数字对不对 | A1：SVG 几何 / VLM·CSV fallback |
| `series_cohesion` | 多系列是否协调 | **A2：SVG 渲染为主**，spec + df 兜底 |
| `visual_form` | 图是否像样 | 像素启发式 / VLM |
| `overall_score` | 综合是否达标 | 三项加权归一化 |

**注意**：`_call_vlm_judge` 仍是软评委；`data_fidelity` 以 A1 为准。`series_cohesion` 在 VLM / 规则两路都会由 `_series_cohesion` 重算，不采信 VLM 的协调分。

---

## 5. `series_cohesion` 算法（渲染优先）

### 5.1 何时打分

```python
distinct_series_count = _expected_distinct_series_count(spec, df)
# overlay 的 y/id 去重；若有 group 列则用 df[group].nunique()

if len(overlays) <= 1 and distinct_series_count <= 1:
    return 1.0, []   # 真·单系列，跳过
```

- **多 overlay** 或 **单 overlay + `group` 多系列**（分组柱图）→ 进入检查。
- 需要 `png_path` 同目录存在 `.svg`；读失败时样式检查回退到 `overlay.style` 签名。

### 5.2 数据流

```
figure_round_N.png
figure_round_N.svg  ← cohesion 主输入（与 A1 同源）
        │
        ├─ _extract_plot_bounds / _extract_ticks     （fidelity_verifier）
        ├─ _has_rendered_legend                      （legend_* 区块）
        ├─ _extract_rendered_line_styles             （line2d_*，过滤 grid）
        ├─ _extract_rendered_bar_styles              （patch_*）
        ├─ _axis_unit_modes                          （左右 y 轴 tick 文本）
        └─ _rendered_x_order_mismatch                （x tick vs df 类目顺序）
```

### 5.3 检查项一览

| 检查项 | 配置键 | 主信号 | 兜底 / 补充 | 扣分 | 诊断 key |
|--------|--------|--------|-------------|------|----------|
| x 列名一致 | `consistent_x_across_overlays` | spec：`overlays[].x` 列名 | — | 0.35 | `x.inconsistent` |
| x 类目顺序 | `consistent_x_across_overlays` | SVG x tick 顺序 vs `df[x]` 首次出现顺序 | — | 0.20 | `x.inconsistent` |
| 多系列图例 | `require_legend_if_multi_series` | SVG 是否存在 `<g id="legend_N">` | 多系列判定：`overlays` 的 y/id 去重 > 1 | 0.20 | `legend.missing.multi` |
| 样式区分 | `distinct_series_styles` | SVG `line2d_*` stroke / `patch_*` fill | 无 SVG 时用 spec `overlay.style` | 0.25 | `series.style.conflict` |
| 比例轴分离 | `separate_ratio_axes` | SVG 左右轴单位模式 + spec `yaxis` | 比例列与绝对值同 `yaxis`（spec） | 0.35 | `ratio.axis.mismatch` |
| 缺列 | — | spec 引用的 x/y 不在 `df` 表头 | — | ≤0.20 | （无独立 key，只扣分） |

**样式冲突判定**（有 SVG 时）：

```python
signatures = line_signatures or bar_signatures   # 混合图目前优先 line
expected_series = distinct_series_count
冲突 ⇔ len(set(signatures)) < min(len(signatures), expected_series) 且 len(signatures) >= 2
```

**line 样式提取过滤 grid**（避免误报）：

- 路径须在 plot bounds 内，且带 `clip-path`
- x、y 坐标各至少 2 个不同值（排除水平/垂直 grid 线）
- 要求 `stroke:` 存在

**bar 样式提取**：扫 `patch_*`，排除 `fill:none`、白色底、过小矩形。

**比例轴 SVG 启发式**（`_axis_unit_modes`）：

- 仅当存在 **ratio-like 列名** 且 spec 声明 **右轴 overlay** 时，才用 SVG 判断 `rendered_mismatch`
- `rendered_mismatch` ⇔ 左、右轴 tick 文本的「是否像比例」模式相同（避免正确双绝对值轴误报）
- spec 兜底：比例类 y 与绝对值 y 落在同一 `yaxis` 仍扣分（不依赖 SVG）

**比例类列名启发式**（`_is_ratio_like`）：`rate` / `ratio` / `share` / `percent` / `pct` / `%`。

### 5.4 spec 与渲染的分工

| 场景 | 行为 |
|------|------|
| spec 写 `legend.loc: outside right`，图里没 legend | **扣分**（信渲染） |
| spec 写 `legend.loc: none`，图里画了 legend | **不扣** legend 项（信渲染） |
| 有 grid、系列可区分 | **不扣** style（grid 已过滤） |
| 无 `.svg` | legend 视为缺失；style 回退 spec 签名 |

### 5.5 仍不检查 / 已知局限

| 项 | 说明 |
|----|------|
| 完整单位语义 | 轴文本仅为第一版启发式（`%` / percent / 0–1 小数） |
| 单 overlay + `group` 缺 legend | style 已用 `group.nunique`；legend 仍看 `overlays` y/id 计数，**可能漏扣** |
| line + bar 混合图 | `line_signatures or bar_signatures` 只取一类 |
| 跨 panel / 子图 Γ | 单图 scope |
| legend 在图内直接标注（无 legend 块） | 仍可能扣 `legend.missing.multi` |
| `_diagnose` / `visual_form` 加分 | 部分仍看 spec `legend.loc`（与 cohesion 独立，见 §11.3） |

---

## 6. `overall_score` 加权公式

### 6.1 公式

```
overall_score = Σ (w_i × clip(s_i, 0, 1)) / Σ w_i
```

`configs/judge_rules.yml`：

```yaml
weights:
  visual_form: 0.5
  data_fidelity: 0.5
  series_cohesion: 0.3
```

```
overall_score = (0.5×VF + 0.5×DF + 0.3×Cohesion) / 1.3
```

实现见 `judge.py:_weighted_score`。

### 6.2 停机阈值

```python
# single_chain_runner.py
if last_scores["overall_score"] >= 0.75:
    break
```

阈值 **0.75 写死在代码**，未放入 `judge_rules.yml`。

### 6.3 综合分直觉（VF=DF=1 时）

| series_cohesion | overall_score（约） | 是否停机（≥0.75） |
|-----------------|---------------------|-------------------|
| 1.0 | 1.00 | ✅ |
| 0.80 | 0.95 | ✅ |
| 0.55 | 0.90 | ✅ |
| 0.0 | 0.77 | ✅（刚过线） |

协调分需**多项重罚**才能把综合分拉到 0.75 以下；设计上是加权项而非一票否决。

---

## 7. 主 API 与落盘格式

### 7.1 `judge()` 返回字段

```python
{
  "visual_form": float,
  "data_fidelity": float,
  "series_cohesion": float,
  "overall_score": float,
  "diagnostics": [...],       # 含 cohesion + visual 诊断
  "fidelity_detail": {...},
  "pred_table": DataFrame,
}
```

### 7.2 `iteration_N.json` 参考 smoke

**推荐参考**：`runs/20260610T212253/iteration_1.json`（渲染优先 cohesion）

```json
{
  "scores": {
    "visual_form": 1.0,
    "data_fidelity": 1.0,
    "series_cohesion": 0.8,
    "overall_score": 0.9538461538461538
  },
  "diagnostics": [
    { "key": "low.contrast.series.2", "slot": "theme.palette", "sev": 1 },
    { "key": "legend.missing.multi", "slot": "legend.apply", "sev": 2 }
  ],
  "spec": {
    "layout": { "legend": { "loc": "outside right" } }
  }
}
```

说明：spec 声明有图例，但 **SVG 无 `legend_*`** → cohesion 扣 0.2；四条线渲染样式可区分 → **不扣** style（修复 grid 误报前曾误扣至 0.55）。

**历史对比**：`runs/20260610T174006/` 在「只看 spec」时期 `series_cohesion: 1.0`；同一类图在渲染优先下应重新评估。

### 7.3 `feedback_builder` 格式

```
Prev J: Overall=0.95  VisualForm=1.00  DataFidelity=1.00  SeriesCohesion=0.80
```

---

## 8. 与 B 同学 / `record.json` 的对接

### 8.1 sprint §1 字段

```json
{
  "scores": {
    "visual_form": 0.0,
    "data_fidelity": 0.0,
    "series_cohesion": 0.0
  }
}
```

`series_cohesion`：对 `chart.png` + 同目录 `chart.svg` + `plot_df.csv` + `spec` 调用 `judge()`（与 agent 内环同源）。

### 8.2 待对齐字段

| 字段 | 说明 |
|------|------|
| **`overall_score`** | 内环停机用；benchmark 可选落盘 |
| **`fidelity_detail`** | 见 [A1_delivery.md](./A1_delivery.md) |

---

## 9. 验收标准与测试

### 9.1 A2 专项测试（9 项）

| 测试 | 验证点 |
|------|--------|
| `test_judge_returns_series_cohesion_for_multi_series` | 无渲染 legend → `legend.missing.multi` |
| `test_judge_series_cohesion_ratio_axis_mismatch` | 比例与绝对值同轴（spec）→ `ratio.axis.mismatch` |
| `test_judge_series_cohesion_rendered_palette_conflict` | 同色渲染线 → `series.style.conflict` |
| `test_judge_series_cohesion_rendered_x_order_mismatch` | x tick 顺序错 → `x.inconsistent` |
| `test_judge_series_cohesion_distinct_series_with_grid_not_penalized` | 有 legend、可区分、带 grid → cohesion **1.0** |
| `test_judge_series_cohesion_dual_axis_correct_no_ratio_mismatch` | 正确双 y 轴 → **无** `ratio.axis.mismatch` |
| `test_judge_series_cohesion_bar_palette_conflict` | 同色分组柱 → `series.style.conflict` |
| `test_judge_overall_score_uses_configured_weights` | 加权公式 |
| `test_judge_uses_fidelity_verifier` | A1+A2 联合 |

### 9.2 运行命令

```powershell
cd NaturePheroViz/agent
python -m pytest tests/test_smoke.py -q --basetemp .\tmp_pytest
# 期望：19 passed（含 A1 与其余 smoke）
```

```powershell
python run_chain.py data/actual_target_plan.csv "实际与目标对比" line --rounds 1
# 检查 runs/<ts>/iteration_1.json → scores 含四项；同目录应有 figure_round_1.svg
```

---

## 10. 与 Related Work / Evaluation 的关系

| 维度 | A1 | A2 |
|------|----|----|
| 论文主创新 | 可执行证据保真 | 多系列过程分 / 协调约束 |
| 对照 VisEval | 数据 legality（读数） | **部分** order / 编码（x tick 顺序；palette 看渲染） |
| 对照 LIDA SEVQ | data encoding | aesthetics / encoding 协调 |
| 杀手实验 `fidelity_audit` | **主战场** | 不直接参与 |

写论文时：**主结论仍放 data fidelity**；`series_cohesion` 作辅助过程指标，并写明「基于 matplotlib SVG 的结构化版式规则，非 VLM 主观分」。

---

## 11. ⚠️ 未对齐 / 需注意

### 11.1 其他文档未同步

| 文件 | 问题 | 建议 |
|------|------|------|
| **`README.md`** | 仍可能写「VF 与 DF 均达 0.75 停止」 | 改为 **`overall_score ≥ 0.75`** |
| **`docs/全流程核对指南.md`** | 同上 | 同步 |
| **`docs/A1_delivery.md`** | §3 若仍写「A2 待做」 | 改为「见 A2_delivery.md」 |

### 11.2 行为变更（实验可比性）

| 变更 | 影响 |
|------|------|
| 停机 `VF∧DF` → `overall_score` | 与 MatPlotAgent 等双阈值不完全可比 |
| cohesion 渲染优先 | 同 spec 不同渲染 → 分数不同（**符合 plan 意图**） |
| cohesion 权重 0.3 | 协调很差时仍可能停机（§6.3） |

### 11.3 与 `visual_form` / `_diagnose` 的重叠

`iteration_1.json` 可能同时出现：

- `low.contrast.series.2`（`_diagnose`，**不扣** cohesion）
- `legend.missing.multi` / `series.style.conflict`（`_series_cohesion`）

规则分支 `visual_form` 在 spec 写「有图例」时仍 **+0.05**，**不看 SVG**——与 cohesion 独立，后续可对齐。

### 11.4 配置陷阱

| 陷阱 | 说明 |
|------|------|
| 无 `.svg` | cohesion 退化：legend 当缺失；style 用 spec |
| 权重和 1.3 | 合法，代码做归一化 |
| 关某项检查 | `cohesion_checks.*: false` |
| 真单系列 | `series_cohesion` 恒 1.0 |

### 11.5 测试覆盖缺口

| 缺口 | 优先级 |
|------|--------|
| `single_chain_runner` 停机 integration test | 中 |
| 单 overlay + `group` 无 legend | 低 |
| line + bar 混合图 style | 低 |
| VLM 分支 `overall_score` 单独测 | 低 |

### 11.6 与 A1 的交叉点

- A1 CSV 择优与 A2 无关。
- 停机只看 `overall_score`，不单独要求 `data_fidelity ≥ 0.75`。

---

## 12. 配置文件速查

### `judge_rules.yml`

```yaml
weights:
  visual_form: 0.5
  data_fidelity: 0.5
  series_cohesion: 0.3

cohesion_checks:
  require_legend_if_multi_series: true
  distinct_series_styles: true
  consistent_x_across_overlays: true
  separate_ratio_axes: true
```

### cohesion 诊断 key（`diagnostics_map.yml`）

| key | 建议 slot |
|-----|-----------|
| `legend.missing.multi` | `legend.apply` |
| `x.inconsistent` | `spec.compose` |
| `series.style.conflict` | `theme.palette` |
| `ratio.axis.mismatch` | `scales.y_right.kind` |

---

## 13. 复现与调试

```python
from pathlib import Path
from app.services.judge import judge
import pandas as pd

gt = pd.DataFrame({
    "month": ["Jan", "Feb"],
    "actual": [120.0, 135.0],
    "target": [130.0, 140.0],
})
spec = {
    "layout": {"legend": {"loc": "best"}},
    "overlays": [
        {"id": "line", "mark": "line", "x": "month", "y": "actual"},
        {"id": "line_1", "mark": "line", "x": "month", "y": "target"},
    ],
}
png = "runs/20260610T212253/figure_round_1.png"
assert Path(png).with_suffix(".svg").exists(), "cohesion 需要同目录 .svg"

result = judge(png, "", gt, spec)
print("cohesion", result["series_cohesion"], "overall", result["overall_score"])
print([d["key"] for d in result["diagnostics"]])
```

手动验证 grid 过滤：

```python
from app.services import fidelity_verifier as fv
from app.services.judge import _extract_rendered_line_styles

svg = fv._read_text("runs/20260610T212253/figure_round_1.svg")
bounds = fv._extract_plot_bounds(svg)
styles = _extract_rendered_line_styles(svg, bounds)
print(len(styles), len(set(styles)))  # 期望：4 条数据线，4 种样式
```

---

## 14. 后续工作（A3–A5 与可选增强）

| 任务 | 与 A2 关系 |
|------|------------|
| **A3 Best-of-N** | 择优可用 `overall_score` |
| **A4 预算停机** | `stop_reason`、ΔJ 早停 |
| **A5 消融** | `--no-cohesion` 或权重置零 |
| legend 用 `group.nunique` 判定多系列 | 修复 grouped bar 漏扣 |
| line + bar 合并 signatures | 混合图 style |
| `_diagnose` / `visual_form` 对齐 SVG legend | 减少 spec/渲染分裂 |
| 更强单位解析 | 替代 tick 启发式 |

---

## 15. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-10 | A2 初版：spec 规则 cohesion + overall_score + 停机/反馈/CLI |
| 2026-06-10 | 全链路 smoke：`runs/20260610T174006`（当时 cohesion 仍偏 spec） |
| 2026-06-10 | **渲染优先**：读 SVG legend / line·bar 样式 / x 顺序 / 轴文本；9 项 A2 pytest；19 passed |
| 2026-06-10 | grid 过滤、bar+group、双轴误报修复；smoke `runs/20260610T212253`（cohesion 0.8，仅 legend 扣分） |

---

**签收**：A2（含渲染优先 cohesion）可标记为 **Done**。请 B 按 §8 确认 `record.json`；请 lead 同步 README / 全流程文档。

**相关文档**：[A1_delivery.md](./A1_delivery.md)
