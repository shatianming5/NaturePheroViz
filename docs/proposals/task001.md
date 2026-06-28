## 步骤1: 调研token shang 增 和token level的 去做 探索的 这部分工作

想尽的联网搜索相关的 工作, 并且每一个工作,对应的是否可能对我们的工作有启发,启发的原因,如果要加入到我们的框架中 会怎么样  完整的做一个想尽的调研,竭尽所有能力

---

### ✅ 已完成 — 交付物：[`task001_survey.md`](./task001_survey.md)

两轮 deep-research 联网检索（5 路并行 → 抓一手源 → 抽可证伪主张 → 每条 3 票对抗核验 → 合成），
合计 43 源 / 211 主张 / 50 核验 / 45 证实 / 5 证伪 / 207 agent。覆盖：
- **Axis 1（test-time token scaling）**：Snell compute-optimal、s1 budget-forcing、rStar-Math、PRM800K、DeepSeek-R1、Reflexion、AlphaCodium、L1/LCPO、TALE。
- **Axis 2（token-level exploration）**：熵机制、Beyond-80/20 forking-tokens、VinePPO、RLOO、TDPO、DAPO、STEER/Revisiting-Entropy、min-p。

每篇均标注：是否启发 / 为何（绑定我们 loop 的具体失败模式）/ 如何加入框架（触及哪个组件 C1–C10、具体改动、单卡离线成本）。
另含：框架 10 组件×失败模式挂载表、代码级集成设计 P1–P8（grounded 真实文件/行号）、排序短名单、12 条开放问题、5 条已证伪清单。


## 步骤2:  调研agent 数据可视化 相关的工作,以及vision llm 以及 agentic 数据可视化相关的的这部分工作
想尽的联网搜索相关的 工作, 并且每一个工作,对应的是否可能对我们的工作有启发,启发的原因,如果要加入到我们的框架中 会怎么样 完整的做一个想尽的调研,竭尽所有能力

---

### ✅ 已完成 — 交付物：[`task001_step2_survey.md`](./task001_step2_survey.md)

两轮 deep-research 并行检索，合计 50 源 / 244 主张 / 50 核验 / 42 证实 / 8 证伪 / 215 agent。覆盖：
- **Pass 1（agentic & code/NL 可视化生成）**：LIDA、MatPlotAgent+MatPlotBench、PlotGen、Text2Chart31、VisEval、Text2Vis、ChartMimic、Nguyen et al.、nvBench2.0。
- **Pass 2（chart 的 vision-LLM）**：CharXiv、ChartMuseum、ChartQAPro、EvoChart、ChartBench、ChartHal、DePlot、MatCha、OneChart。

每篇标注：是否启发 / 为何 / 如何加入框架（C1–C10）。核心结论：
1. 我们「代码优先+render→批评→repair 内环+离线单卡 SFT→RL」三大设计被 LIDA/MatPlotAgent/Text2Chart31 直接印证（Text2Chart31 LoRA-8B/13B 胜 Claude3 Opus/GPT-4o）；
2. **现有基准大多不测 data fidelity，chart-VLM 也不可靠** → 我们的「可执行证据(plot_df+PlotTrace+VisEval SVG)」是差异化护城河；保真用 **OneChart(0.2B 单卡) chart→table 结构感知往返**，VLM-Judge 仅 advisory；
3. 直接可用：Text2Chart31/Text2Vis(MIT) 作 Stage-A 数据、MatPlotBench 作 eval+基线、VisEval SVG 作 C2 保真校验、PlotGen 三通道作 C3 诊断、nvBench2.0 五步作 HCT 层。

另含：感知·数据·评测层挂载表、代码级集成设计 Q1–Q7（grounded `judge.py` 等）、排序短名单、7 条开放问题、7 条已证伪清单。

#### ✅ 第三轮（覆盖补齐）— 交付物：[`task001_step3_survey.md`](./task001_step3_survey.md)

补步骤2 两个精确缺口（37 源 / 185 主张 / 50 核验 / 31 证实 / 19 证伪 / 202 agent）：
- **C3 缺的「有原则 Visual-Form 评分器」→ Draco/Draco2**（BSD 符号、RankSVM 学习权重 93% vs 65% 碾压手调，替 `judge_rules.yml`；唯一门槛=需建 matplotlib→spec 适配器）。
- **C3 缺的「单卡本地 VLM-Judge」→ TinyChart-3B**（ChartQA 83.60 超 GPT-4V；唯一同时有 chart→table RMS-F1 93.78 + PoT 78.98；接 `judge.py:_call_vlm_judge`，PoT 输出回 C2 执行比对 plot_df）；ChartGemma-3B 次优；ChartVLM「先抽表再判」级联作 C3 范式。
- **Stage-A chart→code 数据 → ReachQA(MIT 可执行代码)**；Chart2Code-160k 更大但 NC+有错。
- **DracoGPT 证 LLM 不能可靠自评 visual form（task-dependent）** → 保留符号评分器。
- 诚实警示：无人测过小 VLM 检测「错配图」可靠性 → 采用前须自建 held-out 校准。VizML/DeepEye/Data Formulator/ChartMoE 因 StructuredOutput 失败未 grounded（可选第四轮）。

#### ✅ 第四轮（重核补齐）— 交付物：[`task001_step4_survey.md`](./task001_step4_survey.md)

重核第三轮失败的工作（39 源 / 187 主张 / 50 核验 / 47 证实 / 3 证伪 / 203 agent）：
- **ChartMoE（ICLR 2025）全部锁定**：InternLM-XComposer2 基座、**8.4B 单张 24GB 卡可推理**、MoE 4 专家(chart→table/JSON/code)、**ChartMoE-Align ~1M 四元组、Apache-2.0、HF 公开 54.6GB**、ChartQA 80.48→84.64。
- **净判定**：(1) **Stage-A 数据 ChartMoE-Align 取代/补强 ReachQA 为首选**（须混 Nature pairs 补风格；衍生权重基座许可须单独核验）；(2) **C3 Judge：ChartMoE(8B) vs TinyChart-3B 二选一原型对比**（精度/同源 vs 体量/直接 chart→table 指标）。
- **VizML**（CARS 88.96 人类水平）作 C3 学习式 Visual-Form 特征，与 Draco 符号约束**正交互补**；**Data Formulator(MIT)** 的 agent 驱动 reshape 作 L3 范式；DeepEye/Data2Vis 跳过（冗余/仅观察）。
- 仍未 grounded：NL4DV/ncNet/Chat2VIS/ChartGPT/VisText + UniChart/DocOwl/Plot2Code（可选第五轮）。

> 四轮调研合计 ≈169 源 / 827 主张 / 200 核验，已形成完整的 C3 Judge + Stage-A 数据 + 评测工程蓝图（见各 survey 净判定）。

#### ✅ 第五轮（收尾）— 交付物：[`task001_step5_survey.md`](./task001_step5_survey.md)

收尾最外围工作（约 45 源 / ~250 主张 / 127 条核验主张取证）。⚠️ 两路 workflow 均在**最终合成阶段 StructuredOutput 失败**（已知 harness 不稳定）→ 从 journal 直接取证，结论可靠。
- **chart→table 读取器净增量**：**UniChart-201M**（Donut 式，比 MatCha 快 >11×，**RMS_F1 91.10@ChartQA**，比 TinyChart-3B 小 15×）作「最轻档」新增候选——但**无明确 model 许可**；已采纳的 OneChart/TinyChart/ChartMoE 不被颠覆。
- **NL2Vis 低增量**：ChartGPT（IEEE TVCG'24，**Apache-2.0**）6 步分解（选列/过滤/聚合/图型/编码/排序）可借作 spec.compose CoT 模板；NL4DV 离线意图解析器可选；ncNet/Chat2VIS 被取代。
- **VisText**（ACL'23）三级语义 caption → 可作 `alt_text.py` rubric + C3 可读性检查项。
- 仍未 grounded（优先级低）：Plot2Code 许可、StructChart/ChartReader/DocOwl 作读取器。

> **五轮调研收口**：合计 ≈214 源 / ~1080 主张 / 250 条 3 票核验。C3 Judge + Stage-A 数据 + 评测的工程蓝图已完整、无重大缺口。下一步可进入「落代码」或新步骤。
