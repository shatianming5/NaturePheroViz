# Method 提案（一页）：Silent-Error Self-Repair —— 用执行证据画对数据

> 目标：把当前 incremental 的方法（SVG 反解析 + best-of-N）抬升到 **Oral 级 novelty**。
> 一句话卖点见下；C1/C2/C3 是一个闭环，不是三个独立模块。

---

## 0. 一句话卖点

> **因为我们的 agent 是写代码画图的，所以能在绘图函数被调用的那一刻截获"真正喂给它的数据"，用它当判官——这是只看最终图片的所有现有方法做不到的。于是我们能修复肉眼看不见的数据错误，并把这个能力变成无需人工标注的自我改进信号。**

能力命名：**silent-error self-repair**（静默错误自修复）。

---

## 1. 核心 wedge：执行追踪 vs 看图反推

| | 现有工作 | 我们 |
|---|---|---|
| 能拿到什么 | 只有**最终渲染图**（PNG/SVG） | agent 自己执行代码，能拿到**执行现场** |
| 怎么验保真 | 从图**反推**画了什么（几何误差、需 VLM 兜底、复杂图型覆盖不全） | 在 `ax.bar/plot/...` 被调用的瞬间**插桩截获实际输入数组**（exact，非估计） |
| 关键 bug 在哪 | 看不到 `load→transform→render` 之间的数据逻辑错误 | 截到**变换后、渲染前**的数组，精确定位是哪一步错了 |

**为什么以前没人做**：现有评测器不生成代码，拿不到执行现场。这个结构性不对称就是 novelty 的根。

> 注：`plan.md` 里这叫 **PlotTrace / plot_df**。团队为一周冲刺主动放弃它、改走 VisEval 的 SVG 反解析（低风险但 incremental）。**要 Oral 必须把它捡回来。** SVG 反解析降级为 fallback（评测 baseline 系统时仍用，保证公平对照）。

---

## 2. 三个递进的 novelty 主张

### C1 — 执行追踪式保真验证（Execution-Traced Fidelity）
- **做什么**：插桩 matplotlib Artist，捕获每个 mark 的实际输入数组，与真值表做结构感知 diff（按 `(series, x)` 配对，容差 ~1.5%），产出 `data_fidelity`(=rms_f1) + typed mismatches。
- **新在哪**：VisEval 是 post-hoc 看 SVG（估计）；我们是 in-execution exact（精确）。天然覆盖 scatter/stacked/heatmap/twin-axis/errorbar——不管画成什么，artist 输入都被截到。
- **vs**：VisEval（黑盒 SVG）、MatPlotAgent（GPT-4V 软判）、DePlot/OneChart（chart→table 有噪）。

### C2 — 类型化、按层归因的过程奖励（Typed, Layer-Attributed Process Reward）
- **做什么**：`wrong_value / missing_series / wrong_mapping` 不只是诊断，而是**归因到具体决策层**（L1 数据 / L2 变换 / L3 编码 / L4 样式）的 typed credit。
- **新在哪**：现有 PRM（Math-Shepherd 等）是学出来的、有噪、针对文本推理。我们这个是**确定性、可分解、针对代码-agent 分层动作空间**的 PRM——错误可反查到"哪一层的哪个决策"。
- **现成基础**：HCT 的 **L1–L4 分层 + layer_guards 已存在**，只差"错误类型→责任层"映射。

### C3 — 无标注、以验证器为精确偏好预言机的离线优化（Label-Free Exact-Oracle Preference Optimization）
- **做什么**：每条修复轨迹的（败选, 胜选）候选自动成为 DPO/ORPO 偏好对，**偏好信号 = 执行追踪保真度，精确无噪、无需人标、无需训练 RM**。
- **新在哪**：这是"会学习、能泛化"的部分（Oral 最看重）。核心论点：**奖励 = 数据本身，保真维度上不存在 reward hacking**——agent 没法骗奖励，只能真把数画对。
- **现成基础**：Best-of-N（A3）已落盘所有候选——**就是 DPO 偏好对的原料，白来的**。

### 闭环
```
控制执行 → PlotTrace 精确读回(C1)
        → 按层归因 typed reward(C2)
        → 驱动内环修复 + 当离线 DPO 的精确预言机(C3)
        → 学到的策略再进内环 → 自我改进
```

---

## 3. 论文叙事（Oral 很吃这个）

不写"我们提出一个有 ABCD 模块的系统"，写**一个反直觉的能力**：

> 现有 viz agent 全靠"看图"判好坏，对"视觉完美、数据被悄悄改错"的图完全无能为力。我们让 agent 靠"执行证据"判断，从而能修复肉眼不可见的数据错误，并把这个证据变成无标注自我改进的奖励。

- **开场图**：一张漂亮但 B 系列真值 13 万、画成 9 万的图 → VisEval/GPT-4V 全判通过，我们检出并自动修好。
- **主张顺序**：C1（能力基础）→ C2（为什么能精确修）→ C3（为什么能学会、泛化）。

---

## 4. 证据来源：真实 Nature 数据（关键弹药）

- 现有 **54 篇 / 510 配对**「真实 Nature 图 + 真实源数据表」（`nature_pairs/`，仍在续爬至 ~150）。
- 经对齐探测（`probe_alignment.py`）+ 表头修复（`repair_headers.py`），可 cura 出 **50–80 条真实保真 gold set**。
- **杀手实验**：给 agent 真实数据 + caption → 复现 Nature 图 → 执行追踪 verifier 验"画出的数 == 真值"。
- **为什么是命门**：MatPlotBench 合成数据（简单 bar/line）发不了强会；"真实科学图表上也能抓出数据错"必须有真实数据撑——让方法从 claim 变 evidence。

---

## 5. 要 build 什么（映射现有代码，按优先级）

| 优先级 | 做什么 | 落到哪 |
|---|---|---|
| **P0 命脉** | `plot_trace.py`：执行期插桩 Artist，dump 实际绘图数组 | 新文件 + 改 `execute_script` |
| **P0** | 错误类型 → L1–L4 责任层映射 | `fidelity_verifier.py` + `feedback_builder.py` |
| **P1** | `build_dpo_pairs.py`：run 目录 → 偏好对 | 新 `scripts/`，吃 A3 已落盘候选 |
| **P1** | QLoRA Repair-DPO 一轮（Qwen2.5-Coder） | C3 的"会学习"主张需要它 |
| **降级** | SVG 反解析（现 `fidelity_verifier.py` 主路） | 改为 fallback：评测 baseline / 无法插桩时用 |

---

## 6. 诚实风险与应对

| 主张 | 可能被质疑 | 应对 |
|---|---|---|
| C1 | "插桩不就是 trivial hook？" | 难点在**把 artist 输入对齐回 (series,x,value) 并做结构 diff**，覆盖 transform/twin-axis/stacked 的归一化；用覆盖率表撑 |
| C2 | "层归因准吗？" | 小实验：注入已知层的错误，验证是否归因到该层 |
| C3 | "DPO 真提升、非过拟合？" | held-out 提升曲线 + **证明 VLM/SVG-judge 训不出此效果**（信号有噪/可 hack）。即使"先不管 eval"，这条最小验证也必须有 |

---

## 7. 与当前已实现部分的关系

- A1（SVG 保真验证器）→ 降级为 fallback，主路换 PlotTrace。
- A2（series_cohesion）→ 辅助过程维度，论文一句话带过，不当 novelty。
- A3（Best-of-N）→ 升级为 C3 的偏好对来源（已落盘候选直接复用）。
- ⚠️ 现有停机 `overall_score≥0.75` 把 data_fidelity 权重稀释到 ~0.38，与"重视保真"的卖点冲突——需给 DF 加硬门槛或提到 BoN 择优首排序键。

---

**一句话收尾**：捡回 PlotTrace（执行追踪），让保真从"事后看图反推"变成"执行期精确读回"，再让它产出按层归因 typed reward、当无标注 DPO 的精确预言机——"因为写代码所以能插桩验证、所以能无作弊地自我改进画对数据"这个 **silent-error self-repair** 能力，就是能撑 Oral 的方法 novelty；真实 Nature 数据是把它从 claim 变 evidence 的关键弹药。
