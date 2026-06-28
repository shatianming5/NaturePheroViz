# AAAI 方向讨论纪要：定向修复 + 双智能体是否足够新

日期：2026-06-24
用途：组会/项目讨论用，帮助快速解释当前想法是否适合投 AAAI，以及下一步应该往哪里补强。

> 关联文档：本纪要是 `task/transform_thesis_proposal_v2.md`（检测线，已 READY 9.0）的**下一阶段（repair）方向讨论**。
> 落地的「还要做的事情」路线图见 `transform_thesis_proposal_v2.md` §8「下一阶段：从检测到定向修复」。

## 0. 与既有提案的边界（先读，避免和两份 READY 提案混淆）

task/ 下已有两份 READY 提案也涉及「silent error / 修复」，本纪要需与它们划清边界：

1. **对象/judge 不同，勿与 viz 线的 self-repair 混为一谈**：`oral_method_proposal.md`（viz 绘图线，READY 8.5）的中心能力已命名为 **"silent-error self-repair"**，但其对象是 **matplotlib 图里"画错的数"**（render bug）、judge 是 **PlotTrace 读回 chart-vs-data**。本纪要属 **transform 线**，对象是 **NL→DataFrame 的 silent 语义错**、judge 是 **operator-semantic contracts**。两者是**不同对象、不同 judge 的不同论文**，headline 措辞不应共用 "silent-error self-repair"。

2. **repair = 下一阶段、尚未实证，不声称端到端增益**：两份 READY 提案都靠"**repair 写成 in-loop future work、不声称已证明端到端修复增益**"才拿到高分（见 `oral_method_proposal.md` 措辞纪律）。本纪要把 repair 提为 AAAI 主线，但其 C2/C3/C4 与全部实验均标 **待建 / ☐**，属"motivated-but-not-yet-demonstrated"，与该纪律一致——**未实证前不得在论文里声称修复增益已成立**。

3. **是 transform 检测线的扩展，不替换其 detection 主线**：`transform_thesis_proposal_v2.md`（transform 检测，READY 9.0）的 detection 仍是**独立、已 READY 的贡献**；本 repair 方向是它的**下一阶段扩展**，不推翻、不取代其"无 gold 检测 silent 语义错"主线。

## 1. 一句话结论

如果创新点只写成：

- 检测完再定向修复
- 双智能体协作修复

那么单独看，**不够新，投 AAAI 风险偏大**。

更有机会的写法是：

- **typed semantic detection / attribution**
- **contract-guided targeted repair**
- **abstain-aware repair routing**
- **real-world pandas / notebook evaluation**

换句话说，重点不该是“我们也做了 repair agent”，而该是：

> 我们把 `goldless operator-semantic detection` 真正闭环成了 `typed, constrained, abstention-calibrated repair`。

## 2. 为什么“只做定向修 + 双智能体”不够

近两年已经有不少工作覆盖了“agent repair”“detect-then-repair”“multi-agent debugging/repair”这些关键词。

### 2.1 相关论文已经覆盖的点

1. `RepairAgent`（2024）
   主题：自主式 LLM program repair agent。
   关键信息：不是单轮修复，而是 agent 自主收集信息、选择工具、验证修复。
   链接：https://arxiv.org/abs/2403.17134

2. `SEIDR`（2025）
   主题：iterative multi-agent debugging and repair。
   关键信息：已经有多智能体、迭代调试、调试后修复。
   链接：https://arxiv.org/abs/2503.07693

3. `InspectCoder`（2025）
   主题：dual-agent + debugger collaboration。
   关键信息：已经明确提出双智能体，且强调 runtime debugging 和交互式诊断。
   链接：https://arxiv.org/abs/2510.18327

4. `SelfHeal`（2026）
   主题：fix agent + critic agent。
   关键信息：双智能体修复框架本身已经不是新点。
   链接：https://arxiv.org/abs/2604.17699

5. `PracRepair`（2026-06-16）
   主题：先诊断、形成 repair hypothesis，再迭代修复。
   关键信息：已经非常接近“diagnosis-driven repair”的叙述。
   链接：https://arxiv.org/abs/2606.17612

### 2.2 这意味着什么

如果论文主贡献写成：

- “我们先检测，再修复”
- “我们引入两个 agent 分工合作”

reviewer 很容易反问：

- 这和已有 agent repair 工作本质区别是什么？
- 为什么一定要两个 agent，而不是单 agent + prompt engineering？
- 你们的核心 scientific novelty 是什么，而不是系统堆叠？

所以，“双智能体”最多只能算**实现手段**，不应该是第一创新点。

## 3. 你们真正有机会成立的新点

你们当前代码和实验里最有辨识度的，不是 generic repair，而是下面这条线：

- 不只是 binary detect
- 而是 **operator-level typed attribution**
- 支持 **abstain**
- 然后把 attribution 结果反向驱动 repair

这条线在当前工作里比 “multi-agent” 更强。

## 4. 建议的论文主线

建议把项目从“普通 repair agent”改写成：

> **A typed semantic debugger for pandas/data-wrangling code that supports goldless attribution and targeted repair.**

更具体一点，可以写成：

1. **Typed semantic detection**
   不只是说“错了”，而是判断错在什么 operator semantics。

2. **Contract-guided targeted repair**
   修复不是开放式 self-repair，而是依据 violated invariant 做受约束 patch。

3. **Abstain-aware routing**
   当 contract 不足以支持高置信修复时，系统 abstain 或退回 generic repair，而不是乱修。

4. **Real notebook validation**
   在真实 pandas/notebook code 上统计这些高危 operator 的出现频率、覆盖率、abstain 率、修复收益。

## 5. 为什么这个写法比“双智能体”更强

因为它回答的是一个更像 AAAI 的问题：

> 如何把结构化语义诊断信号变成更可靠、更高效的修复决策？

这个问题比“怎么多加一个 agent”更像算法/框架创新。

双智能体如果要保留，建议降级成：

- 系统实现策略
- 或消融项

而不是 headline contribution。

## 6. 结合当前仓库，已经有的支撑证据

### 6.1 你们已经不是从零开始

仓库里已经有以下基础：

- `typed attribution` 评测脚本
  文件：`agent/eval/attribution_eval.py`

- `operator contracts` 库
  文件：`agent/eval/transform_oracle.py`

- 在线 repair loop
  文件：`agent/app/services/single_chain_runner.py`

问题在于：
**现在 attribution 和 repair loop 还是断开的。**

也就是说，你们已经能“检测 + 定位到 operator family”，但还没有把这个 typed diagnosis 变成 online targeted repair policy。

> 备注（2026-06-25 仓库核对）：现有的在线 repair loop（`agent/app/services/single_chain_runner.py`、`agent/eval/repair_gain.py`）属于**绘图（viz）线**的 render-bug 修复（PlotTrace 读回 chart-vs-data），与 transform 线的 `attribution_eval.py` / `transform_oracle.py` **目前没有打通**——这正是下一阶段要补的闭环。

### 6.2 现有结果已经能支撑“该往这条路走”

1. `typed attribution` 已有很强信号
   内部结果：`agent/eval/results_attribution/attribution_report.md`

   关键数字：

   - attribution recall：`25/25 = 100%`
   - cross-fire：`8% -> 2%`（加 family pruning 后）

   说明：

   - 你们的定位不是瞎猜
   - contract firing 已经足够准，可以进一步拿来驱动 repair

2. 真实数据上 silent error 很常见
   内部结果：`agent/eval/results_real841/real_auto_report.md`

   关键数字：

   - 841 tasks / 71 independent articles
   - ambiguous silent rate：`77%`
   - oracle recall：`98%`
   - false positive：`4/1855`

   说明：

   - 问题真实存在，不是 toy benchmark
   - 检测值得做，修复也有现实意义

3. uncovered operator 可以 abstain
   内部结果：`agent/eval/results_scalability/scalability_report.md`

   关键数字：

   - BEFORE recall：`0/9`，但 false positive 不上升
   - AFTER 每个新 family 加一条小 contract，recall 上升

   说明：

   - abstain 不是失败，而是 coverage boundary
   - 这很适合发展成 `abstain-aware repair routing`

## 7. AAAI 视角下，什么写法更像“够用”

### 7.1 不太够的版本

题目如果接近：

- Multi-Agent Repair for Pandas Code
- Detect-then-Repair for Notebook Bugs

通常显得太工程、太 crowded。

### 7.2 更像 AAAI 会接受的版本

题目和主张应更接近：

- Typed Semantic Attribution for Reliable Repair of Data-Wrangling Code
- Contract-Guided Targeted Repair with Abstention for Pandas Transformations
- From Goldless Detection to Targeted Repair in Real-World Pandas Notebooks

这类表述更强调：

- reasoning structure
- explicit decision policy
- reliability / abstention
- real-world setting

## 8. 建议的贡献写法

开题或论文里建议写成下面四条。

### Contribution 1

提出一个 **typed semantic diagnosis framework**，对 pandas/data-wrangling code 的 silent semantic errors 做 goldless、operator-level attribution。

### Contribution 2

提出一个 **contract-guided targeted repair policy**，把 attribution 结果转化为受约束修复动作，而非 generic self-repair。

### Contribution 3

提出一个 **abstain-aware repair routing mechanism**：当诊断置信不足或 operator coverage 不足时，系统选择 abstain 或 fallback repair，从而减少误修。

### Contribution 4

在真实 notebook / pandas code 上系统评估：

- 高频高危 operator 的真实出现情况
- 当前 coverage 和 abstain rate
- targeted repair 相对 generic repair 的收益

## 9. 双智能体应该怎么放

建议保留，但重新定位。

### 推荐定位

- Agent A：diagnoser
  输出 `operator posterior + violated invariants + allowed patch scope`

- Agent B：repairer
  只在受限空间里改指定 slot / 指定 API / 指定 transformation

### 不推荐定位

- “因为现在都流行 multi-agent，所以我们也做双智能体”

### 最好的说法

双智能体是为了**解耦 diagnosis 和 repair 的 search space**，不是为了“看起来更复杂”。

## 10. 最关键的实验建议

如果目标是 AAAI，至少要补下面三组实验。

### 实验 1：generic vs targeted

比较：

- generic self-repair
- targeted repair（用 typed attribution 驱动）

指标建议：

- final repair success
- 平均轮数
- 平均 token / cost
- 误修率
- 对不同 operator family 的分项表现

### 实验 2：single-agent vs dual-agent

比较：

- 单 agent targeted repair
- 双 agent targeted repair

目的：

- 证明双智能体不是噱头
- 看它是否真正降低误修，或减少 repair rounds

### 实验 3：real notebook prevalence / coverage / abstain

在真实 notebook 代码上统计：

- operator frequency
- 高危 operator frequency
- contract coverage
- abstain rate
- risk-weighted coverage

这组实验是外部效度关键。

## 11. 可参考的 notebook / pandas 相关资料

1. `PandasBench`（2025）
   真实 pandas notebook benchmark。
   链接：https://arxiv.org/abs/2506.02345

2. `CoCoMine / CoCoNote`（2024）
   大规模 notebook data-wrangling 语料。
   链接：https://arxiv.org/abs/2409.13551

3. `JunoBench`（2025）
   真实 Kaggle notebook crash benchmark。
   链接：https://arxiv.org/abs/2510.18013

4. `ARCADE`（2022）
   交互式 pandas notebook code generation benchmark。
   链接：https://arxiv.org/abs/2212.09248

5. `KGTorrent`（2021）
   Kaggle notebook 语料来源之一。
   链接：https://arxiv.org/abs/2103.10558

## 12. 当前最稳的主 claim

建议统一成一句话：

> **Typed semantic error attribution enables more reliable and efficient repair than generic self-repair in real-world pandas notebooks.**

这句话的好处是：

- 比“我们做了双智能体”更有辨识度
- 比“我们也做 repair”更有 scientific angle
- 能把 detection、repair、abstain、real notebooks 全串起来

## 13. 会议上可以直接说的结论版

可以直接这样解释：

1. 只做“检测后定向修 + 双智能体”，创新性不够强，因为最近 program repair / agent repair 论文已经很多。
2. 我们真正独特的地方，不是 multi-agent 本身，而是 `operator-semantic typed attribution + abstain + targeted repair`。
3. 因此论文主线要从“系统堆叠”改成“语义诊断如何驱动可靠修复”。
4. 双智能体可以保留，但只作为实现这一主线的机制，不作为 headline novelty。
5. 如果补上真实 notebook 代码的覆盖率 / abstain 率 / targeted repair 增益，这个方向才更像 AAAI 可接受的工作。

## 14. 下一步决策建议

短期建议按下面顺序推进：

1. 先做 `typed attribution -> targeted repair` 的在线闭环原型。
2. 再做 `single-agent vs dual-agent` 消融。
3. 同时启动真实 notebook 语料统计，补 operator 频率、coverage、abstain。
4. 最后再决定 AAAI 投稿标题和主故事。

## 15. 最终判断

### 当前状态

- 有潜力
- 但还没有到“只靠现有点子就足够 AAAI”的程度

### 如果按建议升级后

当工作被重新表述为：

- typed semantic attribution
- contract-guided targeted repair
- abstain-aware routing
- real notebook external validity

那么它就**有机会形成一条比较像 AAAI 的主线**。

---

## 附：本 memo 使用的外部参考

- RepairAgent: https://arxiv.org/abs/2403.17134
- SEIDR: https://arxiv.org/abs/2503.07693
- InspectCoder: https://arxiv.org/abs/2510.18327
- SelfHeal: https://arxiv.org/abs/2604.17699
- PracRepair: https://arxiv.org/abs/2606.17612
- PandasBench: https://arxiv.org/abs/2506.02345
- CoCoMine / CoCoNote: https://arxiv.org/abs/2409.13551
- JunoBench: https://arxiv.org/abs/2510.18013
- ARCADE: https://arxiv.org/abs/2212.09248
- KGTorrent: https://arxiv.org/abs/2103.10558
