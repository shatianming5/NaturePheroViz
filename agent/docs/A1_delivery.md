# A1 交付文档：保真验证器 `verify_fidelity`

> **任务卡**：`aaai_sprint_plan.md` §2 A1  
> **状态**：✅ 已完成  
> **负责人**：组员 A（方法 + 系统）  
> **核心文件**：`app/services/fidelity_verifier.py`、`app/services/judge.py`、`tests/test_smoke.py`

---

## 1. 一句话交付物

实现 **可执行证据保真验证器**：从渲染图（主路 SVG 几何反解析）读回 `(series, x, value)`，与 ground truth 做 **结构感知匹配** 得到 `data_fidelity`（= `rms_f1`），并接入 `judge()` 驱动 agent 内环；SVG 不可靠时有多级 fallback（VLM 读表 / scaffold CSV / 择优）。

**论文卖点对应**：现有 viz 判官多只看视觉或列名；本模块验 **「画出来的数是否等于该画的数」**。

---

## 2. 解决什么问题

| 旧行为（`judge.py` 规则分支） | 新行为（A1） |
|------------------------------|--------------|
| 只检查 spec 里 x/y **列名是否在 CSV 表头** | 从 **图** 读回数值再比对 |
| B 系列真值 130000、图上画 90000 仍可能 ≈0.75 | 产出 `wrong_value` mismatch，`data_fidelity < 0.4` |
| 无 `pred_table` / `fidelity_detail` | 可落盘、可对接 B 的 `fidelity_audit` |

---

## 3. 交付清单

| # | 交付项 | 位置 | 状态 |
|---|--------|------|------|
| 1 | `verify_fidelity()` 主函数 | `fidelity_verifier.py` | ✅ |
| 2 | SVG bar + line 几何反解析 | `_extract_bar_rows` / `_extract_line_rows` | ✅ |
| 3 | 结构感知匹配 + 容差 1.5% | `_safe_match`, `FIDELITY_TOLERANCE` | ✅ |
| 4 | 诊断 `wrong_value` / `missing_series` / `wrong_mapping` | `_safe_match` | ✅ |
| 5 | chart→table VLM fallback（独立 env） | `_fallback_from_vlm`, `_chart_table_client_config` | ✅ |
| 6 | CSV 真匹配 fallback（宽表/多折线） | `_fallback_from_csv`, `_coerce_pred_table` | ✅ |
| 7 | SVG 差时与 CSV 择优 | `_pick_better_result`（阈值 0.75） | ✅ |
| 8 | 接入 `judge()` | `judge.py:309–361` | ✅ |
| 9 | 单元 / 集成测试 | `tests/test_smoke.py`（11 项 fidelity 相关） | ✅ |
| 10 | 环境变量说明 | `README.md` | ✅ |

**不在 A1 范围**（后续任务）：`series_cohesion`（A2）、Best-of-N（A3）、预算停机（A4）、`--no-verifier` 消融开关（A5）。

---

## 4. 系统位置（与 Judge 的关系）

```
run_chain.py
    → single_chain_runner（每轮渲染 figure_round_N.png / .svg / .csv）
        → judge(png, exec_log, df, spec)
              ├─ verify_fidelity(svg, gt=df, spec, png)   ← A1【硬保真，主结论】
              └─ _call_vlm_judge(png, ...)                  ← 已有【软评委，advisory】
                    data_fidelity 以 verify_fidelity 为准（覆盖 VLM 软分）
```

| 组件 | 输入 | 输出 | 角色 |
|------|------|------|------|
| `verify_fidelity` | `.svg` + `ground_truth_table` + `spec` + `.png` | `data_fidelity`, `rms_f1`, `rnss`, `pred_table`, `mismatches` | **硬验证器** |
| `_call_vlm_judge` | PNG + spec 文字 | `visual_form`, 软 `data_fidelity`, `diagnostics` | **软评委**（不保真主结论） |
| `_fallback_from_vlm`（在 verifier 内） | PNG | `pred_table` → 同样走 `_safe_match` | **读表备胎**（非 judge 软评） |

---

## 5. 主 API

### 5.1 `verify_fidelity`

```python
verify_fidelity(
    svg_path: str,
    ground_truth_table: pd.DataFrame,
    spec: dict,
    png_path: str | None = None,
) -> dict
```

**返回字段**（与 B 同学 `record.json` 对齐）：

```json
{
  "data_fidelity": 0.0,
  "rms_f1": 0.0,
  "rnss": 0.0,
  "pred_table": "<DataFrame>",
  "mismatches": [
    {
      "type": "wrong_value | missing_series | wrong_mapping",
      "series": "B",
      "x": "Feb",
      "gt": 130000.0,
      "pred": 90000.0
    }
  ]
}
```

| 字段 | 含义 |
|------|------|
| `data_fidelity` | **主指标**，当前等于 `rms_f1`（0–1） |
| `rms_f1` | 按 `(series, x)` 配对的结构感知 F1 |
| `rnss` | 位置无关数字集 F1（对照用，说明为何不能只比数字 bag） |
| `pred_table` | 从图/CSV/VLM 读回的 long 表：`series, x, value` |
| `mismatches` | 可解释错误列表，供反馈与 killer experiment |

### 5.2 `judge()` 合并后的字段

`judge()` 在原有 `visual_form` / `data_fidelity` / `diagnostics` 上增加：

- `fidelity_detail`: `{ rms_f1, rnss, mismatches }`
- `pred_table`

写入 `runs/<ts>/iteration_N.json` 的 `scores` 中 **`data_fidelity` 来自 verifier**。

---

## 6. 算法流程

### 6.1 决策树

```
verify_fidelity(svg_path, ground_truth_table, spec, png_path)
│
├─ [A] SVG 存在且可解析出 pred
│     ├─ ground truth 宽表多 y 列 → _normalize_ground_truth 转 long
│     ├─ _safe_match(pred, gt_norm) → result
│     └─ 若 data_fidelity < 0.75
│           └─ 尝试 CSV fallback，_pick_better_result(SVG, CSV)
│
└─ [B] SVG 缺失 / 异常 / pred 为空
      └─ _fallback_after_svg_failure
            ├─ 1) _fallback_from_vlm (chart→table API)
            └─ 2) _fallback_from_csv (scaffold 落盘 CSV + 真匹配)
```

### 6.2 主路：SVG 反解析（VisEval 思路）

1. `_extract_plot_bounds`：从 SVG 找绘图区矩形  
2. `_extract_ticks`：解析 x/y 轴刻度标签与像素位置  
3. `_extract_bar_rows` / `_extract_line_rows`：从 `patch_*` / `line2d_*` 几何反算数据值  
4. `_tag_predicted_series`：结合 spec overlays 标注 series  
5. `_safe_match`：与 ground truth 按 `(series, x)` 配对  

**容差**：`|pred - gt| ≤ max(|gt| × FIDELITY_TOLERANCE, 1.0)`，默认 `FIDELITY_TOLERANCE=0.015`（1.5%）。

### 6.3 Ground truth 形态

| 输入形态 | 处理 |
|----------|------|
| long 表：`series, x, value` | 直接使用 |
| 宽表：多列 y（如 `actual`, `target`）+ 单 x | `_normalize_ground_truth` 按 overlay 拆成长表 |
| agent 内环传入的 `df` | 与 spec.overlays 投影后作为「应画真值」 |

> **与 B 的接口**：benchmark 应用 `plot_df.csv`（「该图应画出的值」）；agent 内环暂用输入 `df` + overlays。长期可统一为 PlotTrace / `plot_df.csv`。

### 6.4 Fallback 说明

| 层级 | 触发条件 | 方法 | 成本 |
|------|----------|------|------|
| 主路 | SVG 可解析 | CPU 几何反解析 | 极低 |
| 择优 | SVG 分 < 0.75 且存在 sidecar CSV | 与 CSV 结果比高下 | 极低 |
| VLM | SVG 完全失败 | PNG → chart→table HTTP API | API / 本地 serving |
| CSV | VLM 不可用 | 读 `figure_round_N.csv`（scaffold `encoded.to_csv`）真匹配 | 极低 |

**说明**：OneChart / UniChart 以 **OpenAI 兼容 HTTP 端点** 接入（独立 `ONECHART_*` / `UNICHART_*`），非内嵌加载权重；本地模型自建 serving 后填 base URL 即可。

---

## 7. 评价指标定义（对接 Evaluation 草案）

### 7.1 本模块产出的指标

| 指标 | 定义 | 谁算 |
|------|------|------|
| **data_fidelity** | `rms_f1`，结构感知 (series,x) 匹配 F1 | A1 `verify_fidelity` |
| **rms_f1** | precision/recall 基于 keyed 配对，容差 1.5% | 同上 |
| **rnss** | 不看 (series,x) 位置，仅数字 bag 匹配 F1 | 同上（ablation 对照） |

### 7.2 与 Related Work 的定位

| 工作 | 测什么 | 本模块关系 |
|------|--------|------------|
| **VisEval** legality | SVG 反解析验 data/order | **方法论同源**；我们嵌入 agent 内环 + rms_f1 |
| **MatPlotAgent** | GPT-4V 视觉反馈 | 竞品；我们用 **确定性 verifier** 作保真主路 |
| **Text2Vis** chart accuracy | 软 VLM 1–5 分 | rubric 参考；我们作 **硬 diff** |
| **DePlot / OneChart** | chart→table RMS_F1 | fallback 读表能力；主路仍是 SVG |
| **旧 judge 列名启发式** | 列名是否存在 | **killer experiment 对照组①** |

### 7.3 可能被质疑的点与应对

| 质疑 | 应对 |
|------|------|
| 只支持 bar/line | 声明覆盖范围；MatPlotBench 统计覆盖率；复杂图走 fallback |
| ground truth 从哪来 | MatPlotBench 官方数据；内环用 df+overlays；benchmark 用 B 的 `plot_df.csv` |
| 与 VisEval 重复 | 我们是 **in-the-loop 判官**，非 post-hoc 框架；多 rms_f1 + fidelity_audit |
| VLM fallback 不可靠 | 仅 fallback；主结论靠 SVG；fidelity_audit 三列对比 |
| 多折线 legend 干扰 | SVG+CSV 择优；smoke 已覆盖宽表多折线 |
| OneChart 非内嵌权重 | serving 层抽象；`ONECHART_API_BASE` 指向本地端点 |

---

## 8. 环境变量

### 8.1 验证器专用

| 变量 | 默认 | 说明 |
|------|------|------|
| `FIDELITY_TOLERANCE` | `0.015` | 相对容差（1.5%） |
| `CHART2TABLE_API_BASE` | — | chart→table 服务 URL（优先于 `LLM_API_BASE`） |
| `CHART2TABLE_API_KEY` | — | API Key |
| `CHART2TABLE_MODEL` | — | 模型名 |
| `CHART2TABLE_API_PATH` | `/chat/completions` | 路径 |
| `CHART2TABLE_PROVIDER` | 自动推断 | `onechart` / `unichart` / `chart2table` / `vlm` |
| `ONECHART_*` / `UNICHART_*` | — | 与 `CHART2TABLE_*` 同语义，优先级更高 |

### 8.2 与 Judge VLM 的关系

- **Verifier fallback**：优先 `CHART2TABLE_*` → `UNICHART_*` → `ONECHART_*` → 共享 `LLM_API_BASE`  
- **Judge 软评**：`_call_vlm_judge` 使用 `LLM_API_BASE` / `VLM_*`（可配同一服务，职责不同）

---

## 9. 验收标准（A1 Definition of Done）

| 验收项 | 标准 | 验证方式 |
|--------|------|----------|
| 错值检出 | 真值 130000、图上 90000 → `data_fidelity < 0.4` 且 `wrong_value` mismatch | `test_verify_fidelity_wrong_value_for_series_b` |
| line 图 | 单折线 / 宽表多折线 roundtrip ≥ 0.99 | `test_verify_fidelity_line_chart_roundtrip` 等 |
| judge 接入 | `judge()` 返回 `fidelity_detail` 且保真分来自 verifier | `test_judge_uses_fidelity_verifier` |
| VLM fallback | SVG 缺失时 mock API 读表并检出错值 | `test_verify_fidelity_uses_vlm_table_fallback_when_svg_fails` |
| 独立 chart2table env | `ONECHART_*` 优先于共享 VLM | `test_verify_fidelity_prefers_chart2table_env_over_shared_vlm` |
| CSV 真匹配 | 非列名启发式，宽表多系列 | `test_verify_fidelity_uses_csv_fallback_with_real_matching` 等 |
| SVG/CSV 择优 | SVG 解析差时用 CSV 高分结果 | `test_verify_fidelity_prefers_csv_when_svg_parse_is_worse` |
| 全链路 | `run_chain.py` 产出 iteration json 含合理分数 | 手动 smoke（见 §10） |

---

## 10. 如何复现

### 10.1 单元测试

```powershell
cd NaturePheroViz/agent
python -m pytest tests/test_smoke.py -q --basetemp .\tmp_pytest
# 期望：11 passed
```

### 10.2 全链路 smoke

```powershell
python run_chain.py data/actual_target_plan.csv "实际与目标对比" line --rounds 1
```

检查 `runs/<timestamp>/`：

| 文件 | 说明 |
|------|------|
| `figure_round_1.png` / `.svg` / `.csv` | 图 + 矢量 + scaffold 数据落盘 |
| `iteration_1.json` | `scores.data_fidelity`、`fidelity_detail.mismatches` |

### 10.3 单独调用 verifier（调试）

```python
from app.services.fidelity_verifier import verify_fidelity
import pandas as pd

gt = pd.DataFrame({"x": ["Jan"], "value": [100.0]})
spec = {"overlays": [{"id": "bar", "x": "x", "y": "value", "mark": "bar"}]}
result = verify_fidelity(
    svg_path="runs/.../figure_round_1.svg",
    ground_truth_table=gt,
    spec=spec,
    png_path="runs/.../figure_round_1.png",
)
print(result["data_fidelity"], result["mismatches"])
```

---

## 11. 与 B 同学对接（`record.json`）

A 负责填充以下字段（见 `aaai_sprint_plan.md` §1）：

```json
{
  "scores": {
    "data_fidelity": 0.0
  },
  "fidelity_detail": {
    "rms_f1": 0.0,
    "rnss": 0.0,
    "mismatches": []
  },
  "ground_truth_ref": "path/to/plot_df.csv"
}
```

B 负责：`code.py`、`chart.png`、`chart.svg`、`plot_df.csv`、`exec_pass`、`rounds_used`、`tokens`。

**杀手实验 `fidelity_audit.py`**：对扰动图分别调  
① 旧列名启发式 ② VLM judge ③ `verify_fidelity` —— ③ 应由 A1 提供稳定 API。

---

## 12. 已知限制（诚实披露）

1. **图型覆盖**：主路 SVG 针对 matplotlib bar/line；饼图、热力图、复杂子图依赖 fallback。  
2. **ground truth 对齐**：宽表转 long 依赖 `spec.overlays` 正确声明各 y 列。  
3. **CSV fallback 语义**：读的是 scaffold **准备绘制** 的 `encoded` 表，不是从像素独立读数；择优逻辑缓解 SVG 误解析。  
4. **VLM fallback**：通用 chart→table prompt，未在 MatPlotBench 全量校准 precision/recall。  
5. **scatter**：SVG 线提取可部分覆盖，无专项测试。

---

## 13. 测试矩阵一览

| 测试函数 | 覆盖点 |
|----------|--------|
| `test_verify_fidelity_wrong_value_for_series_b` | bar 错值 + SVG 主路 |
| `test_verify_fidelity_line_chart_roundtrip` | 单折线 SVG 往返 |
| `test_verify_fidelity_wide_multi_line_roundtrip` | 宽表多折线 SVG |
| `test_judge_uses_fidelity_verifier` | judge 端到端 |
| `test_verify_fidelity_uses_vlm_table_fallback_when_svg_fails` | VLM 读表 fallback |
| `test_verify_fidelity_prefers_chart2table_env_over_shared_vlm` | OneChart 独立 env |
| `test_verify_fidelity_uses_csv_fallback_with_real_matching` | CSV 真匹配 + wrong_value |
| `test_verify_fidelity_prefers_csv_when_svg_parse_is_worse` | SVG/CSV 择优 |
| `test_verify_fidelity_wide_csv_fallback_roundtrip` | 宽表 CSV fallback |

---

## 14. 后续工作（A2–A5 预览）

| 任务 | 内容 |
|------|------|
| **A2** | `series_cohesion` + `judge_rules.yml` 权重 |
| **A3** | `single_chain_runner` Best-of-N (N=3) |
| **A4** | 预算停机 / `stop_reason` |
| **A5** | `--no-verifier` / `--no-bestof` / `--no-pheromone` |

---

## 15. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-10 | A1 完成：SVG 主路 + VLM/CSV fallback + 择优 + 11 pytest + run_chain smoke |

---

**签收**：A1 可标记为 **Done**；请 B 基于本文 §11 对接 `fidelity_audit` 与 `record.json` 落盘。
