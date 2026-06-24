# B2 — Baseline 结果详情

## 实验设置

- **数据集**: MatPlotBench (17 task) + Builtin fixtures (4 task) = 共 24 任务
- **指标**: exec-pass rate, data_fidelity (结构感知 F1)
- **参考系统**: GPT-4o, Claude, Qwen, LIDA, Ours (PlotTrace)

---

## 1. GPT-4o One-shot

**模型**: `gpt-4o`  
**策略**: 单轮 prompt → 直接生成 matplotlib 代码

| 指标 | 值 |
|------|-----|
| Tasks | 24 |
| Exec-pass | 19/24 (79.2%) |
| Mean DF | 0.387 |
| Median DF | 0.093 |
| Fid分布 | [0-.25):12, [.75-1]:7 |

**分析**: 执行通过率最高 (79.2%)，但数据保真度偏低 (0.387)。GPT-4o 擅长生成可运行代码，但经常画错数据 — 这正是 "silent error" 问题。12/19 个通过任务的数据保真度 < 0.25。

---

## 2. Claude One-shot

**模型**: `claude-3-5-sonnet`  
**策略**: 单轮 prompt → 直接生成 matplotlib 代码

| 指标 | 值 |
|------|-----|
| Tasks | 24 |
| Exec-pass | 17/24 (70.8%) |
| Mean DF | 0.599 |
| Median DF | 1.000 |
| Fid分布 | [0-.25):7, [.75-1]:10 |

**分析**: 执行通过率中等 (70.8%)，但保真度两极分化 — 10 个任务 DF=1.0，7 个任务 DF=0。Claude 要么画对要么画错，很少有中间状态。

---

## 3. Qwen Zero-shot ⭐ (新加入)

**模型**: `qwen-plus` (阿里百炼 DashScope)  
**策略**: 单行代码生成 prompt → 鲁棒代码提取

| 指标 | 值 |
|------|-----|
| Tasks | 22 |
| Exec-pass | 18/22 (81.8%) |
| Mean DF | 0.670 |
| Median DF | 1.000 |
| Fid分布 | [0-.25):5, [.25-.50):1, [.50-.75):1, [.75-1]:11 |

**分析**: **最强 baseline** — 执行通过率最高 (81.8%)且数据保真度最高 (0.670)。11/18 个通过任务达到 DF=1.0。详见 [Qwen 调优笔记](Qwen_tuning_notes.md)。

---

## 4. LIDA

**策略**: LIDA 自动可视化框架 (goal → visualization)

| 指标 | 值 |
|------|-----|
| Tasks attempted | 3 |
| Exec-pass | 0/3 (0.0%) |
| Mean DF | 0.000 |

**分析**: LIDA 在 MatPlotBench 上完全失败 — 生成的代码要么不运行，要么严重偏离数据。3 个任务全部 exec-fail。

---

## 5. Ours (NaturePheroViz + PlotTrace)

**策略**: Code agent → PlotTrace verifier loop (最多 3 轮)

| 指标 | 值 |
|------|-----|
| Tasks | 23 |
| Exec-pass | 15/23 (65.2%) |
| Mean DF | 0.289 |
| Median DF | 0.000 |
| Mean VF | 0.656 |
| Mean SC | 0.694 |
| Mean rounds | 1.5 |
| Fid分布 | [0-.25):10, [.50-.75):2, [.75-1]:3 |

**分析**: 当前 Ours 系统 DF 偏低 (0.289)，需要排查:
- 8/23 任务 3 轮耗尽 exec-fail (verifier 反馈可能未能有效驱动代码修正)
- 10/15 可执行任务 DF=0.00 (代码能跑但数据画错 — verifier 可能未检测到问题)
- 仅 3 个任务 DF > 0.75 (0.67, 1.00, 0.67, 1.00, 1.00 on builtin)

---

## 6. MatPlotAgent (占位)

**状态**: 未集成。需要 clone [thunlp/MatPlotAgent](https://github.com/thunlp/MatPlotAgent) 仓库。

---

## 逐任务对比

| Task | GPT-4o | Claude | Qwen | Ours |
|------|--------|--------|------|------|
| 76 | PASS 0.00 | PASS 0.00 | **PASS 1.00** | FAIL 0.00 |
| 77 | PASS 1.00 | PASS 1.00 | PASS 1.00 | PASS 0.67 |
| 78 | PASS 0.00 | PASS 1.00 | **PASS 1.00** | FAIL 0.00 |
| 79 | PASS 1.00 | PASS 1.00 | PASS 0.00 | PASS 0.00 |
| 80 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | PASS 0.00 |
| 81 | PASS 0.00 | PASS 0.00 | PASS 0.00 | FAIL 0.00 |
| 83 | PASS 0.00 | PASS 0.00 | PASS 0.40 | PASS 0.00 |
| 84 | **PASS 0.86** | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| 85 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | FAIL 0.00 |
| 86 | FAIL 0.00 | FAIL 0.00 | FAIL 0.00 | FAIL 0.00 |
| 87 | PASS 0.19 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 |
| 88 | FAIL 0.00 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 |
| 89 | PASS 0.00 | PASS 0.00 | PASS 0.00 | **PASS 1.00** |
| 90 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | FAIL 0.00 |
| 91 | PASS 0.09 | FAIL 0.00 | PASS 0.67 | PASS 0.00 |
| 92 | PASS 0.00 | FAIL 0.00 | **PASS 1.00** | PASS 0.00 |
| 93 | PASS 1.00 | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| 95 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 | PASS 0.00 |
| 96 | PASS 1.00 | PASS 1.00 | PASS 0.00 | PASS 0.67 |
| 97 | PASS 0.03 | PASS 1.00 | PASS 1.00 | **PASS 1.00** |
| 99 | PASS 0.18 | PASS 0.18 | PASS 0.00 | PASS 0.00 |
| 100 | PASS 0.00 | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| builtin_001 | PASS 1.00 | PASS 1.00 | - | PASS 1.00 |
| builtin_002 | PASS 1.00 | PASS 1.00 | - | - |
