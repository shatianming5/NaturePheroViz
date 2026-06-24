# B4 — 杀手实验: Silent Error Audit

## 实验设计

**核心问题**: 图表生成后，如何判断数据是否被正确绘制？

**实验**: 对清洁图表注入 **单一静默数值错误**，测试各 judge 能否检测。

**被测试的 Judge**:

| Judge | 原理 |
|-------|------|
| 列名启发式 (Col-name) | 仅检查列名是否存在 |
| SVG/VisEval | 逆向渲染 SVG 几何 → 反向推断值 |
| **PlotTrace (Ours)** | Hook matplotlib → 读取实际传入的数组 |
| chart-VLM | 视觉语言模型看图判断 (n/a — 无 API) |

**注入的 4 种错误类型**:
- `wrong_value`: 随机替换单个数据点
- `scale_series`: 缩放整个数据系列 10x
- `drop_series`: 删除一个数据系列
- `swap_categories`: 交换两个类别的值

---

## 结果 1: 检测召回率 (Detection Recall)

> 法官是否触发警报？

| 错误类型 | Col-name | SVG/VisEval | **PlotTrace (Ours)** | chart-VLM |
|----------|----------|-------------|---------------------|-----------|
| wrong_value | 0% | 100% | **100%** | n/a |
| scale_series | 0% | 100% | **100%** | n/a |
| drop_series | 0% | 100% | **100%** | n/a |
| swap_categories | 0% | 100% | **100%** | n/a |
| **Overall** | **0%** | **100%** | **100%** | n/a |

**关键发现**: 列名启发式对任何静默错误都**完全盲视** — 召回率 0%。

---

## 结果 2: 定位精确度 (Localization Precision)

> 触发的警报是否精确指向被破坏的具体数据系列？（而非全员报警）

| 错误类型 | SVG/VisEval | **PlotTrace (Ours)** |
|----------|-------------|---------------------|
| wrong_value | 3/4 (75%) | **4/4 (100%)** |
| scale_series | 3/4 (75%) | **4/4 (100%)** |
| drop_series | 1/2 (50%) | **2/2 (100%)** |
| swap_categories | 3/4 (75%) | **4/4 (100%)** |
| **Overall** | **71%** | **100%** |

**关键发现**: SVG/VisEval 虽然能检测到错误 (100% recall)，但定位精度只有 71%。它倾向于"泛洪" — 把所有点都标记为异常。PlotTrace 精确定位到被破坏的系列。

---

## 结果 3: 清洁图表行为 (False Alarm Rate)

> 对**无错误**的清洁图表，诚实法官应保持沉默 (fidelity ≈ 1.0)

| 指标 | Col-name | SVG/VisEval | **PlotTrace (Ours)** | chart-VLM |
|------|----------|-------------|---------------------|-----------|
| False alarms | 0/4 | **3/4** | **0/4** | n/a |
| Mean fidelity | 0.75 | 0.25 | **1.00** | n/a |

**关键发现**:
- SVG/VisEval 在 3/4 的清洁图表上产生**误报** — 将干净的柱状图误读为错误
- PlotTrace 在所有清洁图表上保持 fidelity=1.0，**零误报**

---

## 结论

| 维度 | Col-name | SVG/VisEval | **PlotTrace** |
|------|----------|-------------|---------------|
| 检测 | ❌ 0% | ✅ 100% | ✅ 100% |
| 定位 | - | ⚠️ 71% | ✅ 100% |
| 误报 | ✅ 0 | ❌ 3/4 | ✅ 0 |
| 清洁保真度 | ⚠️ 0.75 | ❌ 0.25 | ✅ 1.00 |

**PlotTrace 是唯一在三个维度都达到最优的 judge**: 100% 检测 + 100% 定位 + 0 误报。

核心洞察: 渲染后逆向的方法 (SVG/VisEval) 虽然能检测但精度不足，且会产生大量噪音误报。只有**直接读取传给 matplotlib 的数组** (PlotTrace) 才能实现精确无误的静默错误检测。

---

## 复现命令

```bash
python eval/silent_error_audit.py
```

> Nature 真实数据的 silent error audit 待 Nature Pairs 数据就绪后补充。
