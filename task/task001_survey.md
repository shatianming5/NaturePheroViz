# 步骤1 调研：Test-Time Token Scaling × Token-Level Exploration → Code-First PheroREER

> **状态**：✅ **已完成**（Axis 1 + Axis 2 两轮检索均已核验合并）。所有论文事实经 3 票对抗式核验、引自一手 arXiv/会议论文（2023–2025）。
> **方法**：两轮 deep-research workflow（run `wf_73fa2501-a2c` + `wf_3935107e-d30`），各 5 路并行检索→抓取一手源→抽取可证伪主张→每条 3 票对抗核验（≥2/3 反驳才否决）→去重合成。两轮合计：43 源、211 主张、50 核验、45 证实、5 证伪、207 个 agent。
> **可信度标注**：✅=已核验（含 arXiv 号与逐字证据）；⚠️=反例/边界条件；❌=已证伪勿依赖；🔧=我方框架集成分析（设计推理，非论文事实）。

---

## 中文执行摘要

围绕「推理时多花 token（Axis 1）」与「token 粒度做探索（Axis 2）」两条线做穷尽调研，并把每篇工作映射到我们的 **Code-First PheroREER**（matplotlib 可视化代码闭环 agent）。五条核心结论：

1. **测试时算力要「难度自适应」，不要固定 Best-of-N**。Snell et al.（ICLR'25 Oral）证明：按题目难度分配算力比固定 BoN **效率高 >4×**；在 FLOPs 对齐下，小模型+测试时算力可在「有非平凡成功率」的题上**超过 14× 大模型**。→ 直接支撑我们用 14B/32B Coder + 单卡离线「修复/验证闭环」而非堆大模型，并为 Route 路由器提供理论依据。

2. **验证器/过程奖励（PRM）是测试时扩展的核心机制**。Lightman（PRM800K）在难 MATH 上过程监督 78.2% > 结果监督 72.4% > 多数投票 69.6%，且优势随 N 增大；rStar-Math 用 MCTS+过程偏好模型 PPM 让 7B 小模型超过 o1-preview。→ 我们的 **PlotTrace/plot_df 是「可执行证据」过程验证器**，能拿到 PRM 级稠密信号却**无需 PRM800K 人工标注**——这是我们最强的护城河。

3. **顺序扩展 + token 效率治理直接对应我们的预算控制**。s1 用「Wait」预算强制（AIME24 50→57%，仅 1000 条 SFT）；L1/LCPO 用「学习式长度控制」**优于硬截断**；TALE 砍 67% token 仅掉 <3% 准确率，且 **TALE-PT「离线把预算内化、部署无需提示」与我们「train-with-reasoning z / deploy code-only」结构同构**。

4. **「生成+测试驱动修复」的推理时闭环（无需改权重）就是我们内环的范式来源**。AlphaCodium 把 GPT-4 pass@5 从 19%→44%（2.34×，纯推理期）；Reflexion 用「言语反思+情景记忆」达 HumanEval 91%。→ 分别对应我们的 **Plan→Patch→Render→Judge 内环** 与 **Pheromone 证据记忆**。

5. **Axis 2（token 级探索）几乎全是 online RL，对我们只能迁「观察/原理」——唯二可整套搬的是 TDPO 与 RLOO 留一 baseline**。熵机制（Cui et al.）：RL 早期熵急塌（前 200 步消耗 73% 熵、贡献 76% 增益）；**forking-tokens**（NeurIPS'25）：仅 ~20% 高熵「分叉 token」驱动 RLVR，启发我们把 token 级 credit/解码探索**聚焦 δC 的少数关键编辑 token**——但**「token 熵是否映射到代码 diff 关键 token」无任何来源证实**（原文把编程列 future work，代码泛化与 token 位置稳定性均被证伪）；**TDPO**（ICML'24）per-token forward-KL 是少数真离线法，直接升级 Stage C 的 DPO 并保候选 render 多样性。

**最高杠杆优先采纳（research + 我方分析合并排序）**：① 难度自适应预算路由（Route）；② 可执行证据过程验证器（PlotTrace/plot_df=PRM 级信号免标注，最强护城河）；③ 测试驱动最小补丁修复闭环（Patch/Render）；④ TALE-PT 式离线内化（Stage A/C）；⑤ Pheromone 情景记忆；⑥ TDPO token 级偏好（Stage C）。**最大警示**：所有定量结论都来自 **数学/通用代码域、非可视化代码域**，且多为 online-RL，迁移到我们「离线·单卡·无 online RL」时只能借**观察与奖励/偏好形状**，可整套搬的仅 **TALE-PT（test-time 效率）与 TDPO（token 级偏好）**；任何「高熵 token=关键编辑 token」假设须**先实证**再投产。

---

## 0. 总纲：两轴挂载在框架的两个层面

| 轴线 | 本质 | 主要挂载层面 | 最相关组件 |
|---|---|---|---|
| **Axis 1：token 上增 / test-time scaling** | 推理时多花 token/compute 换质量 | **部署期＝内循环「花多少轮、怎么搜、何时停、怎么选」** | Route(µθ)、Judge/Verifier、Patch 的 Best-of-N、停机准则、Pheromone 作搜索缓存 |
| **Axis 2：token-level exploration** | token 粒度做探索（RL + 解码） | **训练/采集期＝rollout 多样性、熵不塌缩、token 级信用** | Stage B/C rollout 采样、DPO/ORPO 偏好对、δC 的 token 级 credit、解码温度 |

> 一句话：**Axis 1 决定「我们的内循环推理时该花多少 token、花在哪」；Axis 2 决定「采集 repair 轨迹 / 偏好对齐时，如何在 token 粒度保持有效探索而不退化」。** 交汇枢纽＝**C7 Pheromone**（对 Axis 1 是「搜索价值缓存/避免重复展开」，对 Axis 2 是「探索得到的成功证据/正样本库」）。

### 0.1 我们框架的组件与缺口（每条工作对照表）

| # | 组件 | 当前机制 | 失败模式＝外部工作切入点 |
|---|---|---|---|
| C1 | **Patch δC** | 最小代码补丁（diff） | 倾向整段重写；不编译；过度修正；不知哪几行 token 是关键修复 |
| C2 | **Render + PlotTrace** | sandbox 执行 + monkey-patch 抽隐式 spec + dump plot_df | exec 通过但**画错**（silent wrong-but-runs） |
| C3 | **Judge (J_form,J_fid,J_coh) + 诊断 Q** | 规则 + 可选 VLM | judge 脆弱/可 reward-hack；诊断层级判错→路由错 |
| C4 | **Route µθ {stay/deeper/bubble-up/jump-root}** | 规则路由 | 选错层→浪费轮次；两层间死循环 |
| C5 | **HCT L1–L4 + Ω_v 掩码** | 分层限制可改区域 | 动作空间过死/过松 |
| C6 | **Γ 全局约束** | palette/font/scale/unit 跨 panel | 跨 panel 不一致（Series Cohesion 失分） |
| C7 | **Pheromone 证据记忆** | typed+timestamped link | **重复推导同一修复**；无迁移；检索不命中 |
| C8 | **推理预算（轮数）** | 固定 rounds，≥0.75 早停 | 欠思考早停 / 过思考烧 token |
| C9 | **Rollout 采集（喂 Stage B/C）** | 闭环 logged traj | 多样性不足→DPO 对子弱；熵塌缩→模式坍塌 |
| C10 | **训练 A/B/C（离线·单卡·无 online RL）** | A:Code-SFT；B:Repair-SFT；C:DPO/ORPO；µθ 离线 BC→KL-PG | 偏好对噪声；序列级信用粗糙 |

---

## 1. Axis 1 — Test-Time / Token Scaling（已核验）

> 体例：**工作**（arXiv，venue）— 一句话。`Inspires`。Why / How(→组件) / ⚠️Caveat / ✅证据。

### 1.1 Compute-optimal allocation（怎么分配预算）— 最高杠杆

**✅ Snell et al. 2024「Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Parameters」**（arXiv:2408.03314, **ICLR 2025 Oral**）— 提出两种测试时算力机制：(1) 对稠密**过程验证器(PRM)**做搜索；(2) 测试时**自适应修订**响应分布。`Inspires: YES`
- **Why**：我们的内循环**同时实例化了这两种机制**——机制1＝Judge/Verifier 引导的 rollout 路由；机制2＝Sense→Plan→Patch→Render→Judge 迭代修复＝自适应分布修订。其「最优策略随题目难度剧变」的结论，**直接判定「对绘图 rollout 用固定 Best-of-N」是浪费**。
- 🔧 **How(→C4 Route, 训练/选型)**：(a) 让 µθ **难度自适应**——用首轮 render 的 Judge 严重度/exec-pass 估难度，据此分配修复预算（最大节点数/深度/rollout 数），度量「预算-保真」效率曲线；(b) 这是**单卡离线选型的正当性依据**：14B/32B Coder + 测试时修复/验证闭环 ＞ 堆更大模型。
- ⚠️ **Caveat**：结论来自 MATH/PaLM-2，>4× 与 14× 对绘图是**激励性非保证**；**最难题（难度 4/5）任何方法都无显著进展**，高预算下 beam search 可能不如 BoN——故对「检测为难」的任务要封顶预算并回退 BoN/jump-root。
- ✅ 逐字：「improve the efficiency of test-time compute scaling by **more than 4x** compared to a best-of-N baseline」；「test-time compute can be used to **outperform a 14x larger model**」（FLOPs-matched，限于小模型有非平凡成功率的题）。投票 3-0（合并 3 主张）。

### 1.2 Sequential scaling & budget forcing（最易落地）

**✅ s1「Simple test-time scaling」**（arXiv:2501.19393, **EMNLP 2025 main**）— 「budget forcing」：模型想停时强行追加「Wait」让它复核并常修正错误步，或强制截断；仅用 1000 条精选轨迹 s1K（按难度/多样性/质量选）SFT 即得强推理。`Inspires: Partial→YES`
- **Why**：「多花算力去复核+自纠」正是我们 fidelity 低时重入 Patch/Render/Judge 的过程，「Wait」＝重入循环复核的自然语言版；s1K 的 1000 例结论**直接支撑我们「小高质量集 + 离线单卡 SFT、无 online RL」的前提**。
- 🔧 **How(→C8/C10)**：(a) Stage A/B 采纳 s1K 的**按难度/多样性/质量精选**而非堆量（原文约 7 H100-时，单卡可达）；(b) 实现「预算强制」类比：最小迭代下限（「持续验保真直到 N 项通过」）+ 硬上限（早停/接受当前最优）。
- ⚠️ **Caveat**：budget forcing **约 6× 后变平**、受上下文窗口限、且**非单调**（「Mirage of Test-Time Scaling」2506.04210、「Wait, We Don't Need to Wait!」2506.08343 显示多想会变差）——对绘图要**用 Judge 检测到「可改进诊断」时才追加迭代**，而非无条件。AIME24 仅 30 题，7pp≈2 题，量级仅供参考。
- ✅ 逐字：「**from 50% to 57% on AIME24**」；「s1K of **1,000 questions**…difficulty, diversity, and quality」。3-0。

### 1.3 Search + PRM-guided（与我们 Judge 同构）

**✅ rStar-Math**（arXiv:2501.04519, **ICML 2025**）— MCTS 中小策略模型在 SLM 过程奖励引导下搜索，让小模型比肩/超过 o1-preview（Qwen2.5-Math-7B **58.8%→90.0%**、Phi3-mini **41.4%→86.4%**，+4.5%/+0.9%）。关键：用**过程偏好模型 PPM**（Bradley-Terry 成对偏好，最高Q vs 最低Q 步）替代有噪的逐步数值打分。`Inspires: Partial`
- **Why**：我们 Judge 已出 typed 步级诊断 Q；rStar-Math 证明 (a) 步级/过程奖励引导搜索优于纯结果，(b) **难评分的步用「成对偏好」比「绝对数值」更稳**——「这个 matplotlib 补丁多好」恰是 PPM 规避的那种有噪细粒度打分。
- 🔧 **How(→C10 Stage C, C4)**：(a) 按 rStar-Math 方式造偏好对——同节点 repair rollouts 里取**最高 ΔJ 补丁为正、最低/回退为负**，而非问模型/VLM 要 0-10 绝对保真分；(b) 可选对少量候选补丁做 Verifier 打分的 **MCTS-lite 浅搜索**。
- ⚠️ **Caveat**：完整 4 轮自演化 MCTS（747k 题、从零训 PRM）**远超单卡——勿复刻**；只取 **PPM 成对偏好思想 + 浅搜索**。头条数字是「重训练+测试搜索」合力，非现成测试时保证。
- ✅ 投票 3-0（合并 2 主张）。

**✅「Let's Verify Step by Step」/ PRM800K**（Lightman et al., arXiv:2305.20050, **ICLR 2024**）— 难 MATH 上**过程监督显著优于结果监督**；PRM 重排 best-of-N 解出 **78.2%**（vs ORM 72.4%、多数投票 69.6%），优势随 N 扩大。`Inspires: YES`
- **Why**：这是我们「Judge 做**步/过程级验证器**、出按层 typed 诊断（J=Form/Fidelity/Cohesion+Q）」而非单次终判 pass/fail 的**根本依据**；多步绘图修复里，稠密逐步反馈（哪层错、为何）比单一结果分**定位信用强得多**——正是 PRM>ORM。
- 🔧 **How(→C3/C2)**：(a) 把按层 (L1-L4) 过程分作为 rollout 重排/路由主信号，用于候选 render 的 best-of-N 选优；(b) 我们的 **exec-pass + PlotTrace列映射vs真值 + plot_df vs真值 + Γ-cohesion ＝ 可执行的过程验证器**，比学出来的 PRM 更可靠，且**无需 PRM800K 人工标注**。
- ⚠️ **Caveat**：PRM>ORM 部分**被「PRM 获得更多人类反馈」混淆**，且**非普适**（易 GSM8K 上与结果监督相当、整解验证可能失效）——但我们「难·多步·保真」恰是过程监督取胜的 regime。成本近零（信号来自执行而非训练模型）。
- ✅ 逐字「process supervision **significantly outperforms** outcome supervision…challenging MATH」；「solves **78%**…representative subset」。投票 mixed（[8]2-1, [9]3-0）。

### 1.4 Long-CoT + parallel scaling

**✅ DeepSeek-R1**（arXiv:2501.12948, 2025）— R1-Zero 纯 RL（无 SFT）使「思考时长」/CoT 随训练自发变长，伴随准确率上升（AIME24 pass@1 **15.6%→71.0%**）；并行 self-consistency 叠加：64 样本多数投票 **71.0%→86.7%**（追平 o1-0912）。`Inspires: Partial`
- **Why**：(a) 证「更长推理→更好」，支撑「train-with-reasoning z」；(b) 并行扩展在单条之外另有增益——关乎我们是否对候选补丁/render 多采+择优。
- 🔧 **How(→C4/C2)**：为绘图场景做**正确的并行扩展**——每节点采 K 个候选补丁、全部 render、用**可执行 Verifier（exec-pass+保真）择优**，而非 token 级多数投票（绘图输出不可「投票」，用 verifier 加权选优/最小贝叶斯风险）。
- ⚠️ **Caveat**：长度增长**部分是 GRPO 长度偏置假象**（Dr.GRPO 2503.20783，longer≠deeper）——**勿奖励长度本身，奖励已验证保真**；「**aha moment 顿悟**」相关主张**已证伪 0-3**；单卡 K 小，应重「选优质量(Verifier)」而非大 K。R1-Zero 纯在线 RL **超出我们范围**，只借观察。
- ✅ 逐字「**15.6% to…71.0%**」「majority voting…**86.7%**」。mixed（[10]2-1,[11]3-0）。

### 1.5 Inference-time 反思 / 自修复（与内环最像）

**✅ Reflexion**（Shinn et al., arXiv:2303.11366, **NeurIPS 2023**）— 不更新权重，靠**言语反馈存入情景记忆缓冲**、跨试错学习；HumanEval **pass@1 91%**（vs GPT-4 80%）。`Inspires: YES（强）`
- **Why**：这是我们 **Pheromone 证据记忆 + 迭代环的概念祖先**。我们「每成功步写 typed timestamped link r_t=(node,hash,κ,ΔJ,δC,M) 并按类型/panel/brief 相似度检索」正是 Reflexion「把反思文本存情景记忆以改进后续决策」的**接地（grounded）特化版**。它治的失败模式正是「naive 修复环**反复重推同一修复**烧预算」。
- 🔧 **How(→C7/C3)**：(a) 确保检索到的先验反思（typed 诊断 + 获胜补丁）注入相似节点/panel 的 Plan/Patch 上下文；(b) Reflexion 的言语反思源于反馈信号，我们 Judge 的 typed 诊断 Q 是其接地版。
- ⚠️ **Caveat**：其 91% **重度依赖自生成单测+执行**（假阳率仅 1.4%），同法在 **MBPP 上反而低于基线**——**我们记忆的价值取决于 Verifier(PlotTrace/plot_df) 给出低假阳证据**；无接地测试的言语反思很弱。GPU 成本近零。
- ✅ 逐字「episodic memory buffer…subsequent trials」「**91% pass@1…HumanEval**」。3-0。

**✅ AlphaCodium**（Ridnik et al., arXiv:2401.08500, 2024）— 测试驱动多阶段迭代流（问题反思→公测推理→生成多解→排序→生成 AI 测试→初版码→在公测/AI 测试上迭代）；GPT-4 **pass@5 19%→44%**（CodeContests，纯推理期，2.34×）。`Inspires: YES（结构最契合）`
- **Why**：它是「把生成拆成 Plan→生成/排序→执行→测试→修复 优于一次性生成」对**代码**的标杆证明——正是我们内环 Sense→Plan→Patch→Render→Judge→Route 用于 matplotlib。治的是「一次性出图代码无纠错」。
- 🔧 **How(→C2/C1/C3)**：(a) 直接背书我们整套 Render+Judge+Route；(b) 其「在 AI 生成测试上迭代」＝我们的**自动保真检查（PlotTrace 列映射 vs 真值、plot_df vs 真值）作为「图可被 run against」的测试预言机**；(c) 采纳「针对具体失败测试/trace 的定向修复」＝**最小 diff δC 非整段重写**。
- ⚠️ **Caveat**：约 **15-20 次 LLM 调用/解**＝**计算重**，单卡上**正好要求我们的预算/Route 封顶迭代**；数字是竞赛编程非绘图，2.34× 仅方向性。
- ✅ 3-0。

### 1.6 Length-control & overthinking（治 C8 反面）

**✅ L1 / LCPO**（Aggarwal & Welleck, CMU, arXiv:2503.04697, 2025）— Length Controlled Policy Optimization：prompt 加「Think for [n] tokens」，GRPO 训双奖励 r=1[正确]−α·|n_gold−n_y|；**学习式长度控制比 s1 硬截断高 100% 相对/20% 绝对**。`Inspires: Partial`
- **Why**：把「每题花多少算力」当**可学策略**而非硬规则——直接关乎 Route 预算与 Patch 迭代数控制；「学习式 > 硬截断」警示别用粗暴迭代上限。
- 🔧 **How(→C4/C10)**：若学 µθ（离线 BC→KL-PG），借 LCPO **双目标形状：奖励=已验证保真增益 − 预算/迭代惩罚**，让路由器在易 panel 早停、难 panel 多花（难度自适应，呼应 Snell）。
- ⚠️ **Caveat**：LCPO 是 **online GRPO**，我们离线——只借**奖励形状/长度控制原则**，离线近似＝把预算条件烤进 Stage A/B SFT 目标（见 TALE-PT）。数学域，绘图迁移未验证。
- ✅ 逐字「LCPO…accuracy and adherence to…length」「outperforms S1 by up to **100% relative and 20% absolute**」。3-0。

**✅ TALE「Token-Budget-Aware LLM Reasoning」**（Han et al., arXiv:2412.18547, **ACL 2025 Findings**）— 推理链高度冗余可压：TALE-EP 平均**砍 67% token、准确率掉 <3%**；**TALE-PT 离线后训练（SFT 或 DPO 于「预算最优目标」）把预算意识内化，部署时无需任何预算提示**。`Inspires: YES（强，配方直接同构）`
- **Why**：(a)「推理可压、治过思考」是我们闭环任何 token 效率组件的核心动机（修复环会膨胀 token/迭代去重推同一修复）；(b) **TALE-PT「离线用预算最优目标训练、部署不带预算提示」与我们「train-with-reasoning z / DEPLOY code-only」结构同构**，也与离线 Stage A(SFT)+Stage C(DPO) 同构。
- 🔧 **How(→C10 A/C, C3)**：(a) 直接采纳 TALE-PT：**一次性离线**生成预算/质量最优的 canonical code(+精简 z) 目标，再 SFT(A)/DPO(C)，使部署模型无需预算指令即出高效 code-only（**这是我们 deploy-without 方案最近的外部先例，单卡友好**）；(b) DPO 偏好对部分按 token/迭代效率定义（精简且正确的 render 优先）。
- ⚠️ **Caveat**：离线一次性（GSM8K 约 354 min A100），主风险是「准确率-压缩权衡」（数学 <3%，绘图里小遗漏可能破坏保真）——**压缩须锚定 Verifier，绝不用保真换简洁**；**prompt-only 预算杠杆（「use less than [budget] tokens」）已证伪 1-2**，优先走 TALE-PT 内化路径。
- ✅ 逐字「**67% reduction in token usage**…less than a **3%** decrease」「TALE-PT internalizes…**without explicit token constraints in the prompt**」。3-0。

---

## 2. Axis 2 — Token-Level Exploration（已核验，第二轮专项）

> 第二轮 `wf_3935107e-d30` 完成：21 源、104 主张、25 核验、23 证实、2 证伪。**核心结论：除 TDPO（真·离线偏好法，方法可整套迁移）与 RLOO 留一 baseline 外，Axis-2 几乎全是 online RL，对我们只能迁「观察/原理」而非方法**；且「token 熵是否映射到代码 diff 关键编辑 token」这一最关键问题**尚无任何来源证实**（forking-tokens 原文把编程列为 future work，其代码泛化与「token 位置跨训练稳定」两项均被证伪 1-2）。

### 2.1 RLVR 熵机制（探索的「物理学」）— 已核验

**✅「The Entropy Mechanism of RL for Reasoning LLMs」**（Cui et al., arXiv:2505.22617, 2025）— 策略熵在 RL 早期急塌、与增益饱和同步：**前 200 步（1/12 训练）消耗 73% 熵、贡献 76% 增益**，前 800 步（1/3）贡献 >93% 增益；机制上**熵变由「动作概率 × logit 变化」的协方差驱动**（PG 下 ∝ advantage），协方差长期为正→熵单调降。`Inspires: Partial`
- **Why**：即便我们离线，**Stage C 偏好优化（DPO/ORPO）与可选 µθ 的 KL-PG 都可能过早丢探索/多样性**（坍缩到单一图风/补丁族），损 pass@k；熵塌缩给出量化警示——「移动」多发生在极早期，故**多样性须早保护**。
- 🔧 **How(→C10/C9)**：(a) Stage C / µθ-PG：用 **KL 锚定 base + entropy bonus/clip-higher 类控制**，并把「补丁类型/图编码多样性」作为健康度指标监控；(b) 在 Verifier 择优**之前**用温度/top-p/对比解码采多样候选补丁，保 pass@k。
- ⚠️ **Caveat**：证据来自 online GRPO/PPO，**迁移到离线 DPO 是类比非证明**；后续 2510.10150、2511.05993 在批评/精化熵干预；**确定性「熵→性能律」R=-a·exp(H)+b 已证伪 1-2**——只把熵/协方差当**诊断**，别当硬预测。GPU 成本近零。
- ✅ 逐字「**73% of the entropy consumption and 76% of the performance gain…first 200 gradient steps**」「covariance between action probability and the change in logits…∝ advantage」。3-0。

### 2.2 高熵 forking tokens（最novel，但代码映射未验证）

**✅「Beyond the 80/20 Rule: High-Entropy Minority Tokens Drive Effective RLVR」**（S. Wang/Qwen+Tsinghua, arXiv:2506.01939, **NeurIPS 2025**）— CoT 中仅 ~20% 高熵「分叉 token」是关键决策点（AIME 上仅 20% token 熵>0.672）；**只在这 20% 上做策略梯度更新**，在 Qwen3-8B 上匹配全 token、在 14B/32B 上**显著超越**（32B AIME'25 **+11.04**、AIME'24 +7.71；14B +4.79/+5.21）；反过来只训底部 80% 低熵 token 则显著退化。`Inspires: YES`
- **Why**：这是判断「**token 熵是否映射到代码 diff 的关键编辑 token**」的实证基础，也是对抗候选 render mode-collapse 的直接解药——我们 δC 里真正决定成败的也是少数 token（mean→sum、log→linear、列名/单位字面量）。
- 🔧 **How(→C10/C1/C9)**：方法（在线 PG 掩码）不可迁，**观察可迁**。(a) C10：把 Code-SFT/Repair-SFT/DPO 的 token 级损失向 δC 的高熵决策 token 加权，token 熵**一次性从 base Qwen2.5-Coder logits 预计算**（无 online RL）；(b) C1：在高熵位置偏向多样化解码分支；(c) C9：per-token 熵作 rollout 多样性诊断。成本近零（每序列一次 base 前向缓存熵 + 标量掩码）。
- ⚠️ **Caveat（关键）**：**代码 diff 映射未验证**——原文明确把编程列为 future work；其 (i) **代码泛化**（LiveCodeBench 仅 30.36 vs 30.03）与 (ii) **「高熵 token 位置跨训练稳定」（可离线从 base logits 识别）两项均被证伪 1-2**。若位置不稳定→无法离线可靠识别关键 token→2.2 退化为**仅 C1 推理期解码启发式**（见 2.5），而非训练期 credit。20% 是超参非定律（NeurIPS meta-review 亦称「不太可能普适」）。
- ✅ 逐字「only 20% of the tokens…comparable to full-gradient…significantly surpassing…+11.04 on AIME'25」。合并 6 主张多为 3-0。

### 2.3 token 级信用 / critic-free（多为诊断，反对 learned critic）

**✅ VinePPO**（Kazemnejad et al., arXiv:2410.01679, **ICML 2025**）— PPO 的 value 网络在长推理 step 级 credit 上**接近随机**（5 选 1 时约 20% chance，且随推理变长 MAE 恶化）；改用**无偏蒙特卡洛** return 估计（从中间状态分叉 K 条辅助 rollout）替代 value 网络。`Inspires: Partial（诊断）`
- **Why/How(→C10/C9)**：佐证 C10 **不要 learned critic**（我们本就不用），改用 verifier/MC credit；「从中间状态分叉」的离线类比＝对某中间代码状态采 K 个候选 δC、各自**重执行 C2(Render+PlotTrace)** 拿 verifier 打分的 MC 价值估计（这是离线 rollout 采集 C9，非在线 RL）。成本：每个被评状态 K 次 matplotlib 渲染（轻）。
- ⚠️ **Caveat**：辅助 rollout 本质在线；2025 有反方（AsyPPO 2510.01656、Value-Calibrated PPO 2503.01491 主张 critic 可修非弃）。

**✅ RLOO / Back-to-Basics**（Ahmadian et al., arXiv:2402.14740, **ACL 2024**）— 留一法 per-prompt baseline（用其余 k-1 样本估期望回报），**无 value 网络即超 PPO、少载一个模型副本**；并提出**关键反向论点**：奖励只归终端 token、环境确定→整条生成可视为**单 bandit 动作**，token 级 credit「非必要」。`Inspires: Partial + 载力反论`
- **Why/How(→C10/C9)**：critic-free/少一模型副本契合**单卡显存**；C9→C10 用 RLOO 式留一奖励 baseline 对 k 个已验证 render 排序/加权偏好对（无 critic）。**张力解法**：以**序列/终端级 verifier 奖励为主信号**（端到端验证下 bandit 论成立），把高熵 token 重加权（2.2）当**可选**辅助 credit 整形，而非必需 critic。
- ⚠️ **Caveat**：RLOO 是序列级、**无法定位「哪个编辑 token 起作用」**；bandit 论限于 RLHF reward-model 设定，长 CoT RLVR 下被 VinePPO/forking 争议。

### 2.4 token 级偏好（直接对接 Stage C，且方法可离线迁移）

**✅ TDPO「Token-level DPO」**（Zeng et al., arXiv:2404.11999, **ICML 2024**）— 在 **token 级**做偏好对齐：对每个 token 施加 forward-KL 约束（Bradley-Terry token 奖励），比 DPO 更好平衡对齐与**生成多样性**（TDPO2 加 stop-gradient+α 调权衡）。`Inspires: YES（且 ★方法可直接迁移——少数真·离线的 Axis-2 工作★）`
- **Why/How(→C10 Stage C)**：TDPO 本就是离线（偏好对+参考模型，无 online RL），**方法整套可搬**。在 verifier 定义的对子（chosen=高 Judge 分 render 的补丁，rejected=低）上用 TDPO 的 per-token forward-KL 替/增强 vanilla DPO，用 per-token KL **保护编辑 token 的多样性**，使多轮 DPO 不坍缩到单一 render 风格。成本≈DPO+一次参考模型前向（DPO 本需）+per-token KL，单卡 QLoRA 14B/32B 可忽略。
- ⚠️ **Caveat**：多样性用 KL 度量（非 pass@k/distinct-n），实验在情感/对话**非代码**；「保 pass@k」是我们的外推。

### 2.5 解码期探索（零训练即插即用）

> ⚠️ 本子主题的专项合成 finding 因一次 structured-output 失败未单独成条；下列基于已抓取核验的一手源 + 短名单 idea 5。
- **✅ min-p sampling**（arXiv:2407.01082）及 nucleus/top-p、typical、contrastive/DoLa、熵自适应动态温度（一手源 2506.13681、2403.14541、2210.15097）。`Inspires: Partial（C9/C1）`
- 🔧 **How**：采集 rollout/BoN 时用 **min-p 或动态温度**扩多样；作为 DAPO clip-higher 的**离线类比**——当 C9 检测到候选 render 趋同（mode-collapse）时，在 C1 提议补丁的高熵位置注入解码探索。纯推理期、零训练成本。

### 2.6 熵坍缩与多样性（护栏 + 2025 理论精化）

**✅ DAPO**（ByteDance Seed/Tsinghua, arXiv:2503.14476, 2025）— **clip-higher** 解耦 PPO clip 上下界、抬高 ε_high 给低概率「探索」token 空间以**对抗熵坍缩**；token 级（非样本级）PG 损失避免长响应 token 被低估（治 gibberish/重复）。`Inspires: Partial`
- 🔧 **How(离线)**：迁移观察非在线 clip 机制。(a) C9 诊断：每轮跟踪候选 render 多样性/熵，趋同即视为熵坍缩、在 C1 注入 min-p/升温（clip-higher 的离线类比）；(b) C10：用 **token 级（长度归一）损失聚合**替样本级平均，避免长程序/补丁被低估。零额外训练成本。
- ✅ 逐字「increase ε_high to leave more room for…low-probability tokens」「nearly identical…limited exploration」。

**✅ STEER（arXiv:2510.10150）+「Revisiting Entropy」（arXiv:2511.05993）**（2025 follow-up）— STEER 给出 token 级熵变化的**四因子**解析近似（clipping/advantage/token 概率/token 熵），批评 clip-higher、entropy bonus 只调 1-2 因子；Revisiting 证明**正优势 token 是熵坍缩主因**，提出正优势重加权（熵 0.118→0.187 趋向目标 0.2；AIME'24 Avg@64 34.38 vs GRPO 28.75）。`Inspires: Partial（理论/诊断）`
- 🔧 **How(离线)**：理论/观察可迁（解释什么控制熵），但 token 重加权/正优势重加权是**在线 PG 不可迁**。离线用法：把「训练数据多样性」当可控杠杆（C9/Code-SFT 精选多样 render 目标抗坍缩）；监控候选 render 多样性作熵代理；**对 2.2「只选高熵 token」保持谨慎**（STEER 批其为不完整启发式 + 位置稳定性已证伪）。

---

## 3. 重点项的代码级集成设计（🔧 grounded in 当前实现）

> 已核实三处现状缺口，外部工作正好补：
> - **G1 Pheromone 是 append-only**：`agent/app/services/pheromones.py` 的 `PheroStore` 只有 `append/tail(n)`，**无** plan §8.2 要求的 TTL/score-eviction/相似度检索；`single_chain_runner.py` 只 `history_ref.append(...)` 记摘要，**未「检索历史成功证据指导本轮」**。（↔ Reflexion / rStar-Math PPM）
> - **G2 单链、无 Best-of-N**：`single_chain_runner.py:637` 固定 `for round_idx in range(1, rounds+1)`，每轮只生成 1 个 δC，LLM 温度 0.2（`:151`）；无同状态多采择优。（↔ Snell / R1 并行 / Verifier 择优）
> - **G3 停机扁平 + Series Cohesion 缺失**：停机＝`visual_form≥0.75 且 data_fidelity≥0.75`（`:903`）；`configs/judge_rules.yml` 权重只有 visual_form/data_fidelity 各 0.5，**无 series_cohesion**（实跑 Judge 输出 `SeriesCohesion:"NA"`）。（↔ Lightman PRM / s1 budget forcing / TALE）

| 项 | 来源工作（§） | 触及文件 | 现状 → 改动 | 新增数据/指标 | 成本(单卡离线) |
|---|---|---|---|---|---|
| **P1 Pheromone 检索记忆** | Reflexion 1.5 / rStar-Math PPM 1.3 | `pheromones.py`,`single_chain_runner.py` | 给 `PheroStore` 加 `retrieve(state,κ,panel,brief)`+TTL/score 淘汰（补全 plan §8.2）；Sense 把命中 δC 注入 prompt | link 增 `score/ttl/brief_key`；命中率、命中后 ΔJ/轮、收敛轮数 | **低**（纯工程，无训练） |
| **P2 同状态 Best-of-N + Verifier 择优** | Snell 1.1 / R1 1.4 / Lightman 1.3 | `single_chain_runner.py:637`,`judge.py` | 每轮对同 state 采 N(=2~4) δC（升温或 min-p），Verifier 选 exec-pass 且 J 最高者；落败者直接进 Stage C 的 loser | N、被选率、BoN 的 ΔJ；偏好对(winner,loser) | 中（推理×N，**仅难例开**） |
| **P3 Budget forcing 停机/续跑** | s1 1.2 / TALE 1.6 | `single_chain_runner.py:903`,`:629` | 扁平 0.75 阈值→「预算感知」：未达标且预算未尽→强制 deeper；连续两轮 ΔJ≈0→提前停（治死循环） | 每轮 ΔJ、token 花费、停机原因 | **低**（改控制流） |
| **P4 难度自适应预算** | Snell 1.1 / L1 1.6 | `single_chain_runner.py`,`judge.py` | 用首轮 J+诊断严重度估难度：易例少轮/不开 BoN，难例多轮+BoN+浅搜索 | 难度桶×预算×成功率表 | 中 |
| **P5 Γ-Cohesion Verifier（过程分）** | Lightman 1.3 / rStar-Math 1.3 | `configs/judge_rules.yml`,`judge.py` | 补 `series_cohesion` 权重项与跨 panel 一致性检查；Judge 不止总分，给**每修补步过程分** | series_cohesion 分；每步 ΔJ 作 process reward | 中 |
| **P6 关键修补 token 聚焦** | forking tokens 2.2 / TDPO 2.4 | （训练侧）Stage B/C | 对 δC 做 token 熵分析，credit/正则聚焦少数「分叉 token」；Stage C 用 token 级 DPO 替序列级 | token 熵分布、关键 token 命中、TDPO vs DPO | 中（单卡 LoRA 可做） |
| **P7 离线预算内化** | TALE-PT 1.6 | Stage A/C 数据 | 一次性离线造「预算/质量最优」canonical code(+z) 目标，SFT(A)/DPO(C) 内化，部署 code-only 无需预算提示 | token/任务、保真不降验证 | 中（一次性离线） |
| **P8 Rollout 多样化** | 熵机制 2.1 / min-p 2.5 / DAPO 2.3 | rollout 采集,`single_chain_runner.py` | 采集 repair 轨迹用 min-p/适度高温扩多样；过滤「全对/全错」无信息组（DAPO dynamic sampling） | rollout pass@k、对子有效率、熵曲线 | 低~中 |

> **落地顺序建议**：P1→P3→P2→P5→P7→P4→（训练侧）P6/P8。P1/P3 纯工程、当晚可做，且**直接补全 plan 已承诺但代码缺失的能力**（最高性价比）。

---

## 4. 排序短名单（research 排序 + 我方分析，合并）

| 排名 | 想法 | 来源 | 杠杆/理由 | 成本 |
|---|---|---|---|---|
| 1 | **难度自适应预算路由**（C4） | Snell+L1 | 最大效率杠杆（源域 >4×），直接修「固定 BoN 浪费预算」；复用 Judge 严重度作难度信号 | 低 |
| 2 | **可执行证据过程验证器**（C2/C3） | Lightman PRM>ORM + AlphaCodium 测试预言机 | **我们的 PlotTrace/plot_df 给 PRM 级稠密反馈却无需 PRM800K 标注——最强护城河** | 低 |
| 3 | **测试驱动最小补丁修复闭环**（C1/C2） | AlphaCodium + Reflexion | 背书整个内环；采「针对具体失败 trace 的定向修复」＝最小 diff δC | 低 |
| 4 | **TALE-PT 离线内化**（C10 A/C） | TALE | 唯一可整套搬的离线配方，与「train-with-z / deploy code-only」同构；治过思考 | 中 |
| 5 | **Pheromone 情景记忆**（C7） | Reflexion | 防重复推导同一修复；近零成本；补全 plan §8.2 缺口 | 低 |
| 6 | **成对偏好造 DPO 对子**（C10 C） | rStar-Math PPM | 用 ΔJ 排序成对偏好，避开有噪绝对打分（仅借思想，勿复刻 MCTS 训练） | 中 |
| 7 | **熵/KL 多样性控制**（C9/C10） | 熵机制 2.1 / DAPO 2.6 / STEER 2.6 | Stage C 防坍缩、保 pass@k 的诊断与正则 | 低 |

**Axis-2 专项排序（research 给出，OFFLINE 单卡视角）**：

| 排名 | 想法 | 来源 | 可迁性 | 成本 |
|---|---|---|---|---|
| A1 | **TDPO per-token forward-KL**（C10 Stage C） | TDPO 2.4 | ★**方法可直接迁移**（真离线）★，直接保 verifier 对子的多样性 | 低 |
| A2 | **高熵/关键编辑 token 损失重加权**（C10 SFT+DPO），token 熵从 base Coder logits 一次性缓存 | forking 2.2 | observation 可迁、近零 GPU、**最novel 但代码映射未验证**（实验性，先验证再投产） | 中 |
| A3 | **RLOO 留一奖励 baseline**（C9→C10，对 k 个已验证 render 排序加权对子） | RLOO 2.3 | critic-free、省一个模型副本 | 低 |
| A4 | **token 级（长度归一）损失聚合**替样本级平均（C10） | DAPO 2.6 | 零成本、防长程序被低估 | 零 |
| A5 | **解码期探索 min-p/动态温度**（C1，检测坍缩时注入） | min-p 2.5 | 纯推理期、离线版 clip-higher | 低 |
| A6 | **不用 learned value critic**（C10，用 verifier+重执行 MC） | VinePPO/RLOO 2.3 | 证实现设计 | 零 |

> **交汇洞见**：**Pheromone(C7) 是两轴枢纽**——对 Axis 1 是搜索价值缓存、对 Axis 2 是探索正样本库。优先做扎实，两轴收益叠加。

---

## 5. 开放问题 / 风险

**来自 research（已核验的边界）**：
1. **外部效度是头号风险**：所有定量结论来自**数学/通用代码域，无一在 matplotlib/可视化代码**；>4×、14×、19→44%、91%、67% 等量级仅在源域成立，对我们是**激励性**。
2. **online-RL → 我们离线的失配**：rStar-Math/R1/L1/熵机制均 online RL；**唯一可整套搬的是 TALE-PT**。其余只借观察与奖励/偏好形状。
3. **过程监督在「可视化代码」是否真的 > 结果监督？**（Lightman 是 MATH-scoped、非普适）——须先实证：按层 (L1-L4) Judge 信号是否真比单次终判更利修复，并量化 plan 假设的「Pheromone 消融最伤 Data Fidelity & Series Cohesion」。
4. **过思考非单调**（Mirage 2506.04210、Wait-We-Don't-Need 2506.08343、Dr.GRPO 长度偏置）——**额外 Patch/Render/Judge 迭代何时开始「伤」保真**（过编辑正确图、漂离 Γ）？需「Judge 检测到可改进诊断才续跑」的停机准则。
5. **离线能否学到难度自适应 Route + LCPO 式双奖励，而不诱发早期熵塌缩/单图风坍缩？** 用什么 diversity/pass@k 指标监控？

**🔧 我方补充**：
6. 绘图答案连续/多模态，**self-consistency 投票不适用**，必须靠 Verifier 择优——**Verifier 的保真判别力是上限瓶颈**。
7. **silent wrong-but-runs**：exec-pass≠画对；过程奖励/PlotTrace 断言的覆盖度决定 verifier-guided 的有效性。
8. **token 级 credit 的归因正确性**：高熵 token ≠ 关键修复 token 的充分条件，需在绘图域验证 2.2（forking tokens）可迁移性（第二轮+实证）。

**来自 Axis-2 第二轮（核验后的硬开放问题）**：
9. **token 熵能否定位 matplotlib diff 的关键编辑 token**，还是被代码低熵语法结构淹没（高熵 token 只是格式/变量名噪声）？——必须先实证再信 A2 的损失重加权（2506.01939 自己把编程列 future work）。
10. 既然「高熵 token 位置稳定性」+「代码泛化」**双双证伪 1-2**，「关键 token」**能否离线从 base logits 识别**？若不能，A2 退化为仅推理期解码启发式（A5），而非训练期 credit。
11. 端到端只在最后验证的 render：**RLOO bandit 论**（token credit 可跳）vs **VinePPO/forking 论**（长生成需 token credit）谁赢？——决定 C10 是否值得投任何 token 级 credit，还是把整条补丁当单 bandit 动作 + 序列级 verifier 奖励。
12. **熵坍缩/pass@k 萎缩在离线 DPO/ORPO 多轮是否真发生**（online RLVR 有记录，offline 未知）？per-token KL（TDPO）够不够，还是必须 C1 解码期多样性注入（min-p）配合？

---

## 6. 已证伪 / 勿依赖（❌ 3 票核验否决）

| 主张 | 投票 | 源 | 含义 |
|---|---|---|---|
| DeepSeek-R1「aha moment 顿悟」纯由 RL 涌现自反思 | 0-3 | 2501.12948 | 别把「RL 自动学会中途自纠」当既定事实 |
| 训练-free prompt 预算杠杆「use less than [budget] tokens」可靠 | 1-2 | TALE/2412.18547 | **改用 TALE-PT 离线内化**，别靠 prompt 限预算 |
| 确定性熵-性能律 R=-a·exp(H)+b（H=0 处定上限） | 1-2 | 2505.22617 | 熵/协方差只作诊断，别当硬预测 |
| 高熵 token 位置跨 RLVR 训练高度稳定（86.67%-100% 重叠）→ 可离线从 base logits 识别关键 token | 1-2 | 2506.01939 / OpenReview | **离线识别关键 token 不可靠**，A2 可能退化为推理期启发式 |
| 80/20 高熵优势泛化到 CODE（Codeforces/LiveCodeBench）与跨算法/模型族 | 1-2 | 2506.01939 / OpenReview | 代码迁移证据弱（LiveCodeBench 30.36 vs 30.03），勿假设直接适用 viz-code |

---

## 附录 A：一手来源（Axis 1，已核验）

| arXiv / 链接 | 工作 | venue |
|---|---|---|
| 2408.03314 | Snell — Compute-optimal test-time | ICLR 2025 Oral |
| 2501.19393 | s1 — Simple test-time scaling | EMNLP 2025 |
| 2501.04519 | rStar-Math | ICML 2025 |
| 2305.20050 | Let's Verify Step by Step / PRM800K | ICLR 2024 |
| 2501.12948 | DeepSeek-R1 | 2025 |
| 2303.11366 | Reflexion | NeurIPS 2023 |
| 2401.08500 | AlphaCodium | 2024 |
| 2503.04697 | L1 / LCPO | 2025 |
| 2412.18547 | TALE — Token-Budget-Aware | ACL 2025 Findings |
| 2505.22617 | Entropy Mechanism of RL | 2025 |
| 2503.20783 | Dr.GRPO（R1-Zero 长度偏置批评） | 2025 |
| 2506.04210 / 2506.08343 | Mirage / Wait-We-Don't-Need（过思考非单调） | 2025 |

**一手来源（Axis 2，已核验）**：

| arXiv | 工作 | venue |
|---|---|---|
| 2506.01939 | Beyond the 80/20 Rule（high-entropy forking tokens） | NeurIPS 2025 |
| 2410.01679 | VinePPO（MC step 级 credit） | ICML 2025 |
| 2402.14740 | RLOO / Back-to-Basics（REINFORCE 留一） | ACL 2024 |
| 2404.11999 | TDPO（token 级 DPO） | ICML 2024 |
| 2503.14476 | DAPO（clip-higher / token 级 loss） | 2025 |
| 2510.10150 | STEER（熵变化四因子） | 2025 |
| 2511.05993 | Revisiting Entropy（正优势驱动坍缩） | 2025 |
| 2407.01082 | min-p sampling | 2025 |
| 2210.15097 / 2403.14541 / 2506.13681 | contrastive/DoLa / 解码探索 | 2022–2025 |
| 2504.13837 | RL 是否超越 base / pass@k 之辩 | 2025 |
| 2503.20783 / 2510.01656 / 2503.01491 | Dr.GRPO / AsyPPO / Value-Calibrated PPO（critic 之辩） | 2025 |

## 附录 B：覆盖核对
- [x] Axis 1：compute-optimal / budget-forcing / MCTS+PRM / PRM800K / long-CoT+parallel / Reflexion / AlphaCodium / L1-LCPO / TALE 全部带引用核验
- [x] 我方框架 10 组件 × 失败模式 → 挂载表
- [x] 代码级集成设计 P1–P8（grounded 真实文件/行号 + 3 处现状缺口）
- [x] 排序短名单 + 开放问题 + 证伪清单
- [x] **Axis 2 第二轮**：forking-tokens(2506.01939) / VinePPO / RLOO / TDPO / DAPO / STEER+Revisiting / min-p 全部带引用核验，回填 §2.2–2.6、短名单 A1–A6、开放问题 9–12、证伪 2 条
- [x] 终稿：Axis 1 + Axis 2 合并完成
- 两轮合计：43 源、211 主张、50 核验、45 证实、5 证伪、207 个 agent
