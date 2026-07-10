# AAAI Problem Framing Notes: 图画对了，但没有满足分析需求

## 1. 当前问题的核心表述

我们现在遇到的现象，不适合笼统表述为“图没满足需求”。

如果要写成一篇可投稿 `AAAI` 的论文，需要把这个现象压缩成一个：

- 可定义的问题
- 可测量的现象
- 可诊断的错误类型
- 可优化的系统目标

更准确的问题表述应当是：

> `LLM` 生成的数据可视化，可能在代码执行、数据读取、表面图形上都“正确”，但在分析语义层面并没有满足用户真正的分析意图与偏好。

这类问题可以统称为：

`semantic visualization misalignment`

也就是：

- 图能运行
- 数据来源没错
- 图形表面也合理
- 但表达出来的分析语义不对，或者不符合任务需要

---

## 2. 这个问题应拆成两类

### 2.1 Silent data-fidelity error

第一类是更“硬”的错误：

图表面上像是对的，但画出来的数值语义不对。

典型情况包括：

- `wrong_value`：值画错
- `drop_series`：漏掉系列
- `swap_categories`：类目映射错
- `scale_series`：系列被错误缩放
- 比例和绝对值混轴
- 聚合口径错

这类错误的关键特点是：

- 代码能跑通
- 数据本身没坏
- 图也能正常显示
- 但图表达的数值关系不是“应该画出来的那个关系”

这就是一个典型的 `silent semantic error`。

### 2.2 Intent / preference misalignment

第二类是更高层的错位：

图的数值可能没错，但没有服务分析任务，也没有满足用户偏好。

典型情况包括：

- 用户想看“对比”，系统给了更像“趋势”的表达
- 用户想强调“占比”，系统画成绝对量
- 用户想看异常点，系统给了平均化的聚合图
- 用户不希望使用双轴，但系统用了双轴
- 用户希望按大小排序，但系统保留原顺序
- 用户需要参考线、基线、目标线，但图中没有
- 图型 technically correct，但分析上没有回答问题

这更接近：

`analytical intent misalignment`

或者：

`visualization preference misalignment`

---

## 3. 哪一类更适合先作为论文主线

从当前仓库已有结果看，最稳、最适合 `AAAI` 主打的是第一类：

`silent data-fidelity / semantic correctness`

原因不是因为第二类不重要，而是因为第一类已经具备论文最关键的四个条件：

- 问题定义更清楚
- 评测协议更容易建立
- 现有方法的缺陷更容易证明
- 我们已经有强实验结果

相比之下，`intent / preference misalignment` 虽然贴近真实需求，但当前仍然更像“方向”，还没有完全沉淀成：

- 统一标签
- 标准化 benchmark
- 稳定评分协议
- 明确基线系统

所以更务实的路线是：

1. 主论文先打透 `silent semantic error`
2. 把“需求和偏好没满足”作为更高层扩展问题
3. 后续再补成第二篇或扩展章节

---

## 4. 当前仓库已经支持到什么程度

本地项目 `NaturePheroViz/agent` 里，其实已经有一条比较完整的问题脉络：

- `silent_error`
- `judge`
- `fidelity_verifier`
- `clarify`
- `repair`
- `series_cohesion`

这说明当前工作已经不只是“感觉图不太对”，而是已经在往“语义错位的检测与修复”推进。

尤其关键的是，项目已经明确指出：

- 旧 judge 只检查列名是否存在
- 不检查画出来的数值是否真的正确
- 因而会系统性漏检 silent error

这正是论文问题的抓手。

---

## 5. 这个问题有多严重

### 5.1 在合成 / 控制实验上，silent error 很常见

根据：

- `NaturePheroViz/agent/eval/results_master/master_table.md`

已有关键数字：

- 在 `48-case calibration` 上，`ambiguous silent = 44/96 = 46%`

这说明当任务表达存在歧义时，系统大量产生“能运行但语义错”的结果。

### 5.2 Clarification 明显降低错误，说明问题不是随机噪声

根据：

- `NaturePheroViz/agent/eval/results_ambcal/ambcal_report.md`

结果显示：

- ambiguous prompts: `5/12 silent-wrong = 42%`
- clarified prompts: `0/12 silent-wrong = 0%`

这说明：

- 很多错误不是数据本身导致
- 也不是任务天然无解
- 而是系统没有正确理解分析意图

这点对后续把问题扩展到 `intent alignment` 非常关键。

### 5.3 在多模型上，这不是单个模型的偶发缺陷

根据：

- `NaturePheroViz/agent/eval/results_multimodel/multimodel_report.md`

五个前沿模型在 ambiguous setting 下仍然有较高 silent error：

- `gpt-5.4`: `42%`
- `gpt-5.5`: `32%`
- `gpt-5.3-codex`: `36%`
- `gemini-3.1-pro-preview`: `33%`
- `claude-opus-4.8`: `38%`

说明：

- 这不是弱模型问题
- 也不是旧模型问题
- 而是当前主流 `LLM-for-visualization` 共同面临的结构性问题

### 5.4 在真实数据上，问题更严重

根据：

- `NaturePheroViz/agent/eval/results_real841/real_auto_report.md`

在真实 Nature 数据任务上：

- `841 tasks`
- `71 independent articles`
- ambiguous silent: `1296/1682 = 77%`
- clarified silent: `175/1682 = 10%`

这个数字非常有冲击力。

说明：

- 问题不只是 toy benchmark 上存在
- 在真实 scientific visualization 任务中更严重
- prompt clarification 能显著缓解问题，但不能完全解决问题

### 5.5 现有 judge 基本测不出这个问题

根据：

- `NaturePheroViz/agent/eval/results/silent_error_report.md`

关键结论：

- 旧列名启发式 judge：`0% recall`
- SVG/VisEval：会触发，但 clean chart 上误报严重
- PlotTrace verifier：高 recall，零 false alarm，且 localization 更准

这说明问题不仅存在，而且：

> 现有主流“执行通过 / 图看起来合理 / 简单视觉 judge”并不能有效发现这类错误。

这就是非常标准的论文立论点。

---

## 6. 适合论文的正式问题定义

建议把论文核心问题表述成：

> `LLM-generated visualizations can be execution-correct and visually plausible, yet semantically misaligned with the intended analytical task.`

如果要更聚焦，可以表述成：

> `Silent semantic errors in LLM-generated visualizations are common, hard to detect with render-only judges, and harmful for downstream data analysis.`

如果要保留“需求和偏好”的表达，则可作为扩展版：

> `Analytical intent misalignment in LLM-generated visualizations: charts can be numerically or visually acceptable while still failing the user's analytical goal and preference constraints.`

---

## 7. 论文命名建议

### 7.1 最稳的命名

- `Silent Semantic Errors in LLM-Generated Visualizations`
- `Transform Fidelity for Reliable LLM Visualization`
- `When Correct Charts Are Semantically Wrong`

### 7.2 如果想强调意图和偏好

- `Analytical Intent Misalignment in LLM-Generated Visualizations`
- `Beyond Correct Rendering: Measuring Intent Alignment in LLM Visualization`
- `Execution-Correct but Analysis-Wrong Visualizations`

### 7.3 当前最推荐的命名策略

最推荐：

- 主标题打 `silent semantic error / transform fidelity`
- 引言和讨论里再引出更高层的 `intent/preference alignment`

原因：

- 主标题更硬
- 问题边界更清晰
- 评测更容易说服 reviewer

---

## 8. 为什么不建议一开始就把主问题写成“偏好没满足”

因为“偏好”这个词对 reviewer 来说太宽，也太主观。

如果没有严格定义，很容易被质疑：

- 偏好到底是谁的偏好
- 是 aesthetic preference 还是 analytic preference
- 是标注者主观选择，还是任务必要条件
- 不同偏好冲突时，谁是标准答案

所以需要先把“偏好”往更客观的方向压缩成：

- `analysis intent`
- `task constraints`
- `semantic visualization contract`

换句话说，论文里尽量不要直接写“用户觉得不好”。

更好的写法是：

> 图没有满足任务约束、分析目标或声明的表达偏好。

这会更科学，也更容易评测。

---

## 9. 解决路线应该怎么写

解决方案不要写成泛泛的“做一个更强的 agent”。

更适合 `AAAI` 的路线是三段式：

### 9.1 Intent formalization

先把分析需求结构化，而不是直接把自然语言 prompt 扔给画图系统。

例如把任务意图结构化为：

- task type: `compare / trend / composition / ranking / anomaly`
- semantic target: `absolute / relative / change / distribution`
- preference constraints:
  - 是否允许双轴
  - 是否要求排序
  - 是否需要 baseline / reference line
  - 是否强调 group completeness
  - 是否要突出异常点

### 9.2 Semantic verification

然后验证图是否真的满足这些结构化意图。

这里又分两层：

- `fidelity verification`
  - 验证画出来的数值是否等于应该画的数值
- `intent-fit verification`
  - 验证图型、编码、排序、参照结构是否满足分析目标

当前仓库在第一层已经很强：

- PlotTrace / verifier 路线已经能支撑数据语义验证

第二层目前还需要补 benchmark 和规则体系。

### 9.3 Typed repair

最后修复时，不要做无约束 generic self-repair，而是做 typed repair：

- 如果是 `fidelity` 错：修数据变换、映射、聚合、轴配置
- 如果是 `intent` 错：修 chart choice、encoding、layout、ordering、reference marks

所以整体路线应写成：

`intent parsing -> semantic verification -> typed repair`

这比“多 agent 修图”更有研究味道。

---

## 10. 当前最合理的论文 framing

### 10.1 推荐主线

主论文建议聚焦：

`silent semantic errors / transform fidelity in LLM visualization`

具体卖点可以是：

- 现有评测把“代码能跑”误当成“分析正确”
- render-only judge 看不出 silent semantic error
- 我们提出更可靠的 semantic verifier
- 真实数据上 silent error 很常见
- 更好的 verifier 能驱动更好的 repair

### 10.2 推荐扩展线

作为第二层扩展或 discussion：

`intent and preference alignment`

可以写成：

- silent semantic correctness 只是底线
- 真正高质量的图还必须满足分析任务与偏好约束
- 这引出一个更高层的新问题：`analytical intent alignment`

### 10.3 不建议的主线

目前不建议主打：

- “我们做了双 agent 修图”
- “我们做了 detect-then-repair”

因为这类叙述太容易撞已有 generic repair literature。

更好的 framing 是：

- 我们解决的是一个此前被忽略的 semantic evaluation gap
- repair 只是这个 gap 被显式建模之后的自然下游能力

---

## 11. 一句话判断：这篇论文真正该讲什么

最稳的一句话是：

> 当前 `LLM` 生成图表经常“能运行、像个图、甚至看起来合理”，但并不忠实表达应有的数据语义；而现有评测又常常测不出这一点。

如果再往上走一层，则可以扩展为：

> 即使图的数值没有明显错误，它也可能仍然没有满足用户真正的分析目标与表达偏好。

所以论文最适合的递进关系应该是：

1. 先证明 `semantic fidelity` 是一个真实且严重的问题
2. 再说明这只是更高层 `intent alignment` 问题的基础层
3. 最终把“图画对了但分析上不对劲”变成一个正式研究议题

---

## 12. 当前阶段的务实建议

### 12.1 短期建议

先把主问题定为：

`silent semantic error in LLM visualization`

原因：

- 你已经有数字
- 你已经有 verifier
- 你已经有真实数据结果
- 你已经有多模型对比
- 你已经有现有 judge 失效的直接证据

### 12.2 中期建议

在这个基础上，再补一个新的 benchmark，把“需求和偏好”结构化：

- 收集 `analysis intent spec`
- 定义 task categories
- 定义 preference constraints
- 定义 intent-fit 指标

这样第二阶段就能自然扩展到：

`intent-aware visualization generation and repair`

### 12.3 总体策略

不要把两个问题一开始混成一个大而模糊的问题。

更好的路线是：

- 第一篇：`semantic fidelity`
- 后续扩展：`intent / preference alignment`

这条路线风险更低，也更容易形成清晰贡献。

---

## 13. 后续可直接展开的讨论问题

接下来和合作者讨论时，可以直接围绕下面几个问题展开：

1. 我们是否同意主问题先定义为 `silent semantic error`，而不是泛化成“偏好没满足”？
2. `intent / preference misalignment` 是否作为本篇论文的扩展问题，而不是主贡献？
3. 当前已有结果是否已经足够支撑一篇以 `semantic fidelity verification` 为中心的 `AAAI` 投稿？
4. 如果要把“需求和偏好”纳入本篇，最小可行 benchmark 应该怎么定义？
5. 我们最终想投稿的是：
   - verifier / judge paper
   - repair paper
   - 还是 intent-aware visualization paper

---

## 14. 目前的初步结论

当前最稳的判断是：

- 你观察到的问题是真问题
- 而且不是小问题
- 它不应写成“图不够好看”或“偏好没满足”这种松散表述
- 更准确的核心是：`semantic misalignment`
- 其中当前最成熟、最适合投稿的子问题是：`silent semantic error / transform fidelity`

更进一步说：

> “图画对了，但分析上不对劲”

这句话背后的正式研究问题应该是：

> `LLM-generated visualizations may be execution-correct and visually plausible, yet semantically wrong for the intended analytical task.`

这就是当前最值得押注的论文 framing。
