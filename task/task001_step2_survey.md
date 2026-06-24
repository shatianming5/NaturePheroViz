# 步骤2 调研：Agentic Data-Viz + Vision-LLM for Charts → Code-First PheroREER

> **状态**：✅ **已完成**（两轮 deep-research 并行检索均已核验合并）。论文事实经 3 票对抗式核验、引自一手 arXiv/会议论文（2022–2025）。
> **方法**：两轮 workflow（Pass1 `wf_59b947a5-62b` agentic & code/NL 生成；Pass2 `wf_aa089137-349` chart VLM）。两轮合计：**50 源、244 主张、50 核验、42 证实、8 证伪、215 个 agent**。
> **标注**：✅=已核验；⚠️=反例/边界；❌=已证伪；🔧=我方框架集成分析。
> **与步骤1 关系**：步1 挂载在「搜索/探索/训练动力学」层；步2 挂载在「**感知·数据·评测**」层，且工作就在我们领域内，可直接当**数据集/基线/Judge/保真预言机**。

---

## 中文执行摘要

围绕「agent 数据可视化 + vision-LLM + agentic 可视化」做穷尽调研，映射到 **Code-First PheroREER**。六条核心结论：

1. **我们「代码优先、无显式 spec」的设计被直接印证**。LIDA（微软, ACL'23）就是 grammar-agnostic 生成**可执行 matplotlib 代码**而非 Vega-Lite spec；其 generate→execute→filter + 自评维度可作 C3 评分参照。

2. **「render→VLM 批评→repair」的 agentic 环已被量化证明有效，正是我们 C2/C3/C4**。MatPlotAgent 的**视觉反馈环单独贡献 +7.72 分**（隔离消融）；PlotGen 的 **Numeric/Lexical/Visual 三反馈 agent** 给了我们 C3 typed 诊断 Q 的天然结构；Text2Vis 的 actor-critic 把 GPT-4o 26%→42%。

3. **离线开源单卡 SFT+RL 配方已被证可行——直接印证 C10**。Text2Chart31（EMNLP'24, **MIT**）用 **LoRA 微调 Llama-3-8B/Code-Llama-13B + PPO**，在「描述→图表代码」上**胜过 Claude 3 Opus / GPT-4o**，并提供 **11,128 组带数据表的 SFT 语料** + **循环一致性奖励**模板（可作 Stage-A/B/C）。

4. **最关键战略洞见：现有基准大多不测「数据保真」，只测视觉/代码相似**。仅 **VisEval（SVG 反解析读回所绘数据做确定性 type/data/order 核查）** 与 **Text2Vis（chart accuracy=意图 AND 底层数据）** 真验数据正确；ChartMimic 等只测视觉相似。Nguyen et al.（EMNLP'24）更证现有 Text-to-Vis 基准各只测一面、唯一真实的 PlotCoder 不可执行。→ **这正是 C2(plot_df)+C3(Data Fidelity) 要补的缺口，是我们的差异化护城河。**

5. **chart-VLM 还不足以单独当 C3 Judge**（Pass2）。前沿 VLM 在真实图上远逊人类（GPT-4o 47% vs 人 80% on CharXiv；Gemini-2.5-Pro 63% vs 93% on ChartMuseum），**纯视觉推理掉 35–55pt**、在「缺失/矛盾」regime **编造而非弃答**（ChartHal）——恰是「画错但能跑」最该抓处。→ **VLM-Judge 只能 optional/advisory，置于可执行证据之后。**

6. **数据保真的可行实现 = chart→table 往返**：**OneChart（0.2B，单卡 + 置信度弃答）** 读回数值与 plot_df 比对；但**必须结构感知比对**（base DePlot RNSS 84.55% 但 RMS-F1 仅 30.62%＝数字对、类别映射错），且现成模型非 turnkey、可能需领域微调。

**最高杠杆优先采纳**：① Text2Chart31（SFT+RL 配方+数据，MIT）；② MatPlotBench+MatPlotAgent（离线 eval+基线+视觉环）；③ VisEval SVG 反解析（移植为 C2/C3 的 CPU-only 保真校验）；④ Text2Vis（SFT+4 轴 judge，MIT）；⑤ PlotGen 三通道（→C3 typed 诊断）；⑥ OneChart（→Data-Fidelity 预言机）；⑦ nvBench2.0 五步（→HCT 层）。**最大风险**：① agentic 增益多用 GPT-4V critic，换离线开源 VLM 后增益幅度未知；② Text2Chart31/ChartMimic/nvBench2.0 有再散布/版权/share-alike 风险（Text2Vis/Text2Chart31 仓库 MIT 最干净）。

---

## 0. 总纲：step-2 工作挂载在「感知·数据·评测」层

| 我们的组件 | step-2 工作如何插入 | 典型工作 |
|---|---|---|
| **C2 Render+PlotTrace / Verifier** | ✅**chart→table（读数回译）+ SVG 反解析 = Data-Fidelity 预言机**：渲染→读回所绘数据→与 plot_df **结构感知**比对（RMS-F1/keyed diff，**非数字集**）。OneChart 0.2B 单卡+置信度；VisEval SVG 逻辑 CPU-only | OneChart, DePlot, **VisEval(SVG)** |
| **C3 Judge（规则分支）** | ✅**可执行/确定性检查**（VisEval type/data/order；LIDA SEVQ 6 维；Text2Vis 4 轴）→ Visual Form/Data Fidelity/Series Cohesion | VisEval, LIDA-SEVQ, Text2Vis |
| **C3 Judge（typed 诊断 Q）** | ✅**PlotGen 的 Numeric/Lexical/Visual 三反馈通道** = 我们 typed 诊断的结构，分别路由 HCT 层 | PlotGen |
| **C3 Judge（VLM-judge 分支）** | ⚠️**实测 chart-VLM 不足以单独仲裁**（真实/纯视觉图远逊人类、absent regime 编造）→ optional/advisory，置于确定性证据之后 | CharXiv/ChartMuseum/ChartHal（警示） |
| **C10 Stage A/B SFT 数据** | ✅**chart→code 语料**直接作 Code-SFT/Repair-SFT；cycle-consistency 作 Stage-C 奖励 | **Text2Chart31(MIT,11128)**, Text2Vis(MIT), nvBench2.0 |
| **离线 eval + 基线** | ✅**MatPlotBench(100,防记忆)** 作主 eval；MatPlotAgent/Text2Chart31-8B/13B/LIDA 作基线 | MatPlotBench, MatPlotAgent, ChartMimic |
| **C1 Patch / 内环** | ✅**render→critique→repair 视觉反馈环**（+7.72 消融）= 我们内环直接先例 | MatPlotAgent, PlotGen, Text2Vis |
| **C5 HCT L1–L4 / 意图** | ✅**nvBench2.0 五步拆解** → 层分配 schema | nvBench2.0 |
| **C6 Γ / C3 Visual Form 规则** | 可视化设计约束/质量模型（待第三轮 grounded） | Draco/VizML `[未核验]` |

> **一句话**：步2 回答三个工程问题——(1) **数据/eval 从哪来**（Text2Chart31/Text2Vis/MatPlotBench/nvBench2.0）；(2) **保真验证器/Judge 用谁**（VisEval SVG + OneChart 往返 > 不可靠的 VLM-judge）；(3) **打败谁**（MatPlotAgent/PlotGen/Text2Chart31-8B/13B/ChartMimic）。

---

## 1. Pass 1 — Agentic & Code/NL 可视化生成（✅ 已核验）

> 23 源、113 主张、25 核验、21 证实、4 证伪。

### 1.1 Code-first NL→viz（印证我们核心设计）
**✅ LIDA**（Dibia, Microsoft, **ACL 2023 demo**, arXiv:2303.02927）— grammar-agnostic 生成**可执行代码**（matplotlib/seaborn/altair/d3，非声明式 spec）；VISGENERATOR 做 generate→execute→filter + 6 维 GPT-4 自评 SEVQ（code accuracy/data transformation/goal compliance/viz type/data encoding/aesthetics）+ 用户触发 repair。`Inspires: YES`
- 🔧 **How(→基线/C3)**：作架构 baseline；**SEVQ 6 维直接映射我们 Visual Form/Data Fidelity/Series Cohesion** 的评分维度；纯 prompting 模式，离线换 Qwen+开源 VLM 零训练成本。
- ⚠️ **Caveat（2-1）**：LIDA 核心是**一次性 ranked-candidate pipeline**，refine/repair 在独立、用户触发、非自治子模块——「闭环自治」说法夸大，但 C2/C3/C4 映射成立。

### 1.2 Agentic render→critique→repair（= C2/C3/C4 的直接先例）
**✅ MatPlotAgent + MatPlotBench**（Yang et al., **ACL Findings 2024**, arXiv:2402.11453）— LLM agent + 视觉反馈；**视觉反馈环单独贡献 +7.72 分**（隔离消融, 3-0）。**MatPlotBench=100 人工核验用例**（75 Matplotlib Gallery + 25 OriginLab，**数据替换防 GPT-4 记忆**，人写真值）。`Inspires: YES（高）`
- 🔧 **How(→C2/C3/C4 + eval)**：**作主离线 EVAL 集 + baseline，并把视觉反馈环作 C2/C3/C4 参考实现**；其 GPT-4V 评分换我们离线 Judge。
- ⚠️ **Caveat**：自纠约 3 轮（claim 2-1）；仅 100 例（且「数据替换」仅适用 75 个 Matplotlib 例，25 个 OriginLab 保留原数据）→ 配 Text2Vis/Text2Chart31 扩量。

**✅ PlotGen**（2025, arXiv:2502.00988）— 多 agent：Query Planning + Code Generation + **3 个 typed 反馈 agent（Numeric / Lexical / Visual）**经自反思迭代精化**数据准确性/文本标签/视觉正确性**；matplotlib 输出。`Inspires: YES（高）`
- 🔧 **How(→C3)**：**Numeric/Lexical/Visual 三通道 = 我们 C3 typed 诊断 Q 的现成结构**——数值反馈≈plot_df 保真、视觉反馈≈VLM-Judge、词法反馈≈规则诊断，分别路由到对应 HCT 层。

**✅ Text2Vis**（Rahman et al., **EMNLP 2025 Main**, arXiv:2507.19969, **MIT**）— 1,985 样本/20+ 图型，(表, query, answer, **可执行 matplotlib/seaborn 代码**, 图)；**首个 cross-modal actor-critic**（render→critique→repair，GPT-4o **26%→42%**）；**4 轴 LLM 评测含 "chart accuracy"=意图 AND 底层数据**。`Inspires: YES`
- 🔧 **How(→C10/C3)**：train split 作 Stage-A SFT、test1/2 作 eval；**4 轴 judge（尤其 chart accuracy）作 C3 rubric**。
- ⚠️ **Caveat（2-1）**：actor-critic **仅 1 轮**精化（vs 我们多轮树路由）；chart accuracy 是软 VLM 1–5（pass≥3.5），**非硬数值 diff**——瞄准保真但不硬抽取。

### 1.3 离线开源 SFT+RL 配方已被证可行（印证 C10）
**✅ Text2Chart31**（Pesaran et al., SNU/KAIST/NAVER, **EMNLP 2024 Main Oral**, arXiv:2410.04064, **MIT**）— **11,128 组覆盖 31 种 matplotlib 图型**（含 3D/网格/不规则；8,166 组含原始数据表+推理），GPT-3.5/4 生成 + cycle-consistency + 运行错误过滤，**无人工标注**。RL=偏好奖励（SFT 输出为负、真值代码为正）+ 对齐奖励（原描述 vs 代码再生描述的 BERTScore 循环一致性），**PPO via LoRA on Llama-3-8B / Code-Llama-13B**。结果：RL 使 8B 总执行错误率 **16.09%→14.55%（胜 Claude 3 Opus 14.90%）**；SFT+RL 13B→**9.21%（胜 GPT-4o 13.00%）**。`Inspires: YES`
- 🔧 **How(→C10)**：**印证整个 Qwen2.5-Coder + (Q)LoRA + SFT→RL 离线计划**；(i) 11,128 组作 Stage-A Code-SFT、8,166 组作「数据表→代码」SFT；(ii) **cycle-consistency（代码再生描述比相似）作 C3/Stage-C 信号**；(iii) 8B/13B 数字作 baseline。**显式单卡 LoRA on 8B/13B 可达**。
- ⚠️ **Caveat**：「错误率」仅测**无崩溃执行、非数据保真**（弱信号）；OpenAI 生成，**再散布依 OpenAI 输出条款**。

### 1.4 评测与「Data Fidelity 缺口」（最关键战略洞见）
**✅ VisEval**（Microsoft, **IEEE VIS 2024 / TVCG**, arXiv:2407.00981）— validity / legality / readability；**legality 用 SVG 反解析从渲染的 matplotlib 抽出实际所绘数据**，经 SVG `id` 解析图型/轴/图例，再**确定性核查 chart type / DATA / ORDER vs 标注真值（非像素相似）**；readability 另用 GPT-4V 1–5。`Inspires: YES`
- 🔧 **How(→C2/C3)**：**把 legality 的 SVG 反解析逻辑移植为 C2 的 CPU-only 保真验证器/交叉校验**——当 monkey-patch 拦截不全时，对保存的图 SVG 反解析回收所绘值，跑 type/data/order 检查。**纯 CPU、无 GPU/API、便宜**；仅 readability 需（可替换的）VLM。
- ⚠️ **Caveat**：3 个 sibling 证伪——**VisEval 不是 code-first matplotlib SFT 语料（0-3）、其 3 维 ≠ 我们 C3 三元组（0-3）**；只采**机制**，不当 SFT 数据。

**✅ Nguyen et al.**（Sydney+CSIRO, **EMNLP 2024 Main**, arXiv:2407.19726）— 对比 nvBench/ChartDialogs/PlotCoder vs The Stack 真实代码：分布差距大；**各只测一面**（代码合成 OR 数据呈现 OR 美学），唯一贴近真实的 PlotCoder（Spearman 0.7–0.9）**不可执行**（无输入数据/无输出图/无库版本）→ 视觉输出无法对用户目标验证。`Inspires: YES（理据）`
- 🔧 **How**：**现有基准无法验证渲染图是否匹配数据=正是 C2/C3 要补的缺口**的最强外部证据；据此建**复合 eval**（MatPlotBench + Text2Vis + VisEval 式数据检查），勿信单一基准；若用 PlotCoder 须自合成输入数据并渲染。
- ⚠️ **Caveat**：nvBench「>80% 柱状偏斜」具体数字**证伪 1-2**，但分布差距总结成立。

**✅ ChartMimic**（**ICLR 2025**, arXiv:2406.09961）— 4,800（图,指令,代码）三元组（取自科学论文），Matplotlib-only，image→code；评 17 LMM（含可单卡的开源）。**只测视觉相似、不测数据保真**（「does not enforce consistency with the underlying structured data」）。`Inspires: Partial`
- 🔧 **How**：作 **chart→code 领先 baseline + 仅 Visual-Form 二级 eval**；配 VisEval/Text2Vis 补保真。作 SFT 有**版权风险**（源自受版权论文）；image→code 输入模态与我们 table+instruction 不同（相邻非同任务）。

### 1.5 NL2Vis 拆解 → HCT 层
**✅ nvBench 2.0**（HKUSTDial, **NeurIPS 2025**, arXiv:2503.12880, **CC BY-SA 4.0**）— 7,878 NL query / 24,076 viz / 780 表 / 153 域，控制式歧义注入反向生成；**5 步拆解：Data Selection / Chart Type / Channel Mapping / Data Transformation / Visualization Synthesis**（模型 Step-Text2Vis）。`Inspires: Partial`
- 🔧 **How(→C5 HCT)**：**5 步映射到 HCT 层**（Chart Type/Channel Mapping→L2 编码、Data Transformation→L3 统计、Data Selection→意图解析），作层分配 schema + 可蒸馏为 Stage-A 推理 SFT。
- ⚠️ **Caveat**：CC BY-SA **share-alike**（衍生须同协议）；是否测 data fidelity **未决**（sibling 1-2）。

### 1.6 覆盖缺口（Pass 1 未 grounded → 需第三轮）
**Data Formulator/2、ChartGPT、DracoGPT、Chat2VIS、NL4DV、ncNet、Seq2Vis、ChartX、ChartVLM、ChartCoder、Plot2Code、VisPath、Draco/Draco2、VizML、Data2Vis、DeepEye、VisText、Text2Analysis** 未在本轮 3 票核验存活——**不代表无关**，需专项核验（尤其 **Draco/VizML 作 C3 Visual-Form 质量模型**、**ChartCoder/ChartX 作 chart→code 数据**）。

---

## 2. Pass 2 — Vision-LLM for Charts（✅ 已核验）

> 27 源、131 主张、25 核验、**21 证实、4 证伪**。
> **决定性结论**：**chart-VLM 还不足以单独充当 C3 多模态 Judge / silent-wrong 检测器**——前沿 VLM 在真实图上远逊人类，且**恰在「纯视觉推理」和「不可答/缺失/矛盾」两个 regime 最差**，正是「画错但能跑」最需抓处。**更稳的路是 chart→table 往返做 Data-Fidelity**（尤其 **OneChart 0.2B 单卡+置信度弃答**），但必须**结构感知比对**。→ **强力印证我们核心赌注：可执行证据 > VLM 看像素。**

### 2.1 Chart QA / 推理基准 — VLM 在真实图上远逊人类（C3 警示）
**✅ CharXiv**（arXiv:2406.18521, **NeurIPS 2024**）— **GPT-4o 47.1% vs 人类 80.5%**（~33pt）；**压力测试掉最多 34.5%**。
**✅ ChartMuseum**（arXiv:2505.13444）— **Gemini-2.5-Pro 63% vs 人 93%**，Qwen2.5-VL-72B 仅 38.5%；**纯视觉题比文本题掉 35–55pt**（72B 文本 59.9% vs 视觉 4.9%）。
**✅ ChartQAPro**（arXiv:2504.05506, **ACL 2025 Findings**）— **Claude 3.5 从 ChartQA 90.5%→55.81%**；经典 ChartQA 已饱和。
**✅ EvoChart**（arXiv:2409.01577, **AAAI 2025**）— 真实图 **GPT-4o 仅 49.8%**。**ChartBench**（arXiv:2312.15915）— 去标注逼模型从颜色/图例/坐标推值；18+3 MLLM 能力有限。
- 🔧 **映射 C3**：VLM-Judge 继承这种脆弱性，**不能在自然/复杂/纯视觉图上单独仲裁**；经典 ChartQA 85–90% 饱和掩盖真实差距。⚠️ CharXiv 47.1% framing 投票 2-1。

### 2.2 Chart 幻觉 — 集中在 silent-wrong regime（最致命）
**✅ ChartHal**（arXiv:2509.17481, 2025）— **GPT-5 34.46%、o4-mini 22.79%**，最佳（Qwen2.5-VL-72B）仅 54.24%；**幻觉集中在「信息缺失/矛盾」题，模型编造而非弃答**。`Inspires: YES（核心警示）`
- 🔧 **映射 C3**：图静默漏画/错编时，问 VLM「图里有没有 X」正落 absent/contradictory regime → **倾向幻觉确认**（验证器最坏行为）。⚠️ ChartHal 评作答者非裁判（judge 映射是可辩护下界，2-1）；「Qwen2.5-VL-7B 仅 14.53% 弃答」**证伪 0-3，勿引用**。

### 2.3 Chart→table 抽取 — 保真预言机的可行路径（C2/C3）
**✅ DePlot**（arXiv:2212.10505, **ICML 2023**）+ **MatCha**（arXiv:2212.09662, **ACL 2023**）— plot→线性化表；DePlot **标准化 plot-to-table 并定义 RMS 指标**（(row,col,value) 映射 P/R/F1，可复用打分）；DePlot+LLM one-shot 超 finetuned SOTA **~24–29pt**（绝对，human ChartQA）。`Inspires: YES（高）`
**✅ OneChart**（arXiv:2404.09987, **ACM MM 2024 Oral**）— **仅 0.2B 参数**（SAM-base+OPT-125M）chart→Python-dict 表，辅助 `<Chart>` token+额外 decoder（+19.1–29.4% AP），**自带自评置信度/弃答**（丢低置信 +9.95% AP@strict）。`Inspires: YES（最适单卡）`
- 🔧 **映射 C2/C3**：渲染→OneChart/DePlot 读回表→与 plot_df **结构化比对**（RMS-F1/keyed diff）；OneChart 置信度门控信任。**0.2B≈0.4–0.8GB，单卡轻松**；de-rendering 语料作 Stage-A 数据。

### 2.4 ⚠️ 决定性 Caveat — 往返作预言机的真实风险
**✅ arXiv:2501.04675**（2025）— **base DePlot 简单柱状图 RNSS 84.55% 但 RMS-F1 仅 30.62%**＝**数字对、类别/标签映射错**＝**正是 silent-wrong，naive 数字集比对抓不到**。`Inspires: YES（关键约束）`
- 🔧 **映射 C3**：Data-Fidelity **必须结构感知比对**（RMS 式/对 plot_df 的 keyed diff），**非 bag-of-numbers**；现成 chart→table **非 turnkey 预言机，可能需领域微调**。⚠️ 同源两条更强主张（微调提 RMS-F1 至 91%、喂表降 MAPE 至 3.66%）**证伪 1-2，勿引用**。

### 2.5 覆盖缺口（Pass 2 未 grounded）
请求的指令微调 chart-VLM（**ChartLlama/ChartInstruct/ChartAst/ChartGemma/TinyChart-PoT/ChartVLM/DocOwl/ChartMoE**）与 chart→code（**ChartMimic*/Plot2Code/ChartCoder/Chart2Code/ChartReformer**）**未在本轮核验存活**（*ChartMimic 由 Pass1 grounded）。需**第三轮专项**核验「哪个小 VLM 可单卡当 C3 Judge / 哪些 chart→code 数据可作 Stage-A」。已抓取源：2404.16635、2409.03277、2407.04172、2501.06598(ChartCoder)、2405.07990(Plot2Code)。

---

## 3. 排序短名单（两轮合并，OFFLINE 单卡）

| 排名 | 采纳项 | 来源(§) | 角色 | 许可/可得 | 成本 |
|---|---|---|---|---|---|
| 1 | **Text2Chart31**：11,128 组 Stage-A SFT + cycle-consistency 作 Stage-C 奖励 + LoRA-8B/13B 配方 | 1.3 | **数据+配方+基线** | **MIT**（但数据 OpenAI 生成，散布存疑） | 低（一次性） |
| 2 | **MatPlotBench + MatPlotAgent**：主离线 eval + 基线 + 视觉反馈环作 C2/C3/C4 参考 | 1.2 | **eval+基线+组件** | 公开下载 | 低 |
| 3 | **VisEval SVG 反解析 legality**：移植为 C2/C3 的 **CPU-only 数据保真验证器** | 1.4 | **组件(C2/C3)** | 微软开源 | 极低(CPU) |
| 4 | **Text2Vis**：train/test 作 SFT/eval + 4 轴 judge（含 chart accuracy）作 C3 rubric | 1.2 | **数据+eval rubric** | **MIT** | 低 |
| 5 | **PlotGen 三反馈通道**：Numeric/Lexical/Visual = C3 typed 诊断 Q 结构 | 1.2 | **组件(C3/C4)** | — | 低 |
| 6 | **OneChart(0.2B) + 结构感知比对**：chart→table 往返作 Data-Fidelity 预言机 | 2.3/2.4 | **组件(C2/C3)** | 开源 | 低(单卡) |
| 7 | **nvBench2.0 五步拆解**：→ HCT L1/L2/L3 层 schema + 推理 SFT | 1.5 | **schema+数据** | CC BY-SA（share-alike） | 低 |
| — | **不做**：把 chart-VLM 当主 C3 Judge | 2.1/2.2 | 反面教训 | — | — |

> **复合 eval 建议**：MatPlotBench（视觉+综合）+ Text2Vis（含 chart accuracy）+ VisEval 式 SVG 数据检查（硬保真）三者并用，**不信任任何单一基准**（Nguyen et al.）。

---

## 4. 开放问题 / 风险（已核验）

1. **现有 viz 基准是否测 data fidelity？** → **已答：大多不测**，只有 VisEval（SVG 后解析）与 Text2Vis（软 VLM chart accuracy）真涉保真，ChartMimic 等只测视觉相似。**但两者都非硬数值 diff**——VisEval 仅对 SVG-可解析的 matplotlib 有效，Text2Vis 是软 VLM 判。**我们的 plot_df 硬数值 diff 仍是更强的保真信号**（差异化）。
2. **VLM-Judge 可靠吗？** → **已答：不可靠**（CharXiv/ChartMuseum/ChartHal）；纯视觉+absent regime 最差且编造。→ VLM-Judge **只作 advisory**。开放：单卡小 VLM 能否**可靠弃答**而非编造？精度/召回**未测**（7B 弃答数字已证伪）。
3. **chart→table 往返够准做预言机吗？** → **部分答**：base DePlot RMS-F1 仅 30.62%（需结构感知比对 + 可能领域微调）。开放：**OneChart 在我们 matplotlib 图风上的 RMS-F1 够不够**，还是需 in-domain 微调？往返「保真 vs silent-wrong」的阈值与数字集比对的假通过率？
4. **离线开源迁移真实吗？** → 开放（最大风险）：MatPlotAgent +7.72、Text2Vis 26→42% **都用 GPT-4V/4o critic**；换离线开源 VLM judge（Qwen2-VL/InternVL）增益是否保留**未验证**，多轮树路由的 C8 预算成本 vs 单轮基线？
5. **硬 data-fidelity 指标怎么定？** → 开放：能否用 VisEval SVG 抽取值作真值来**验证我们 monkey-patch 的 plot_df dump**，拦截会漏掉哪些（变换/聚合后的系列）？
6. **训练数据再散布许可** → 开放：Text2Chart31（OpenAI 条款）、ChartMimic（版权论文）、nvBench2.0（CC BY-SA share-alike）能否清权？若不能，可否**自产**（描述/表→代码→执行过滤→cycle-consistency）复刻 Text2Chart31 配方而不散布其数据？
7. **领域差** → 多数 chart VLM/数据训于 ChartQA 风格简单图，对 **Nature 级复杂多 panel 图**泛化未知。

---

## 5. 已证伪 / 勿依赖（❌ 3 票核验否决）

| 主张 | 投票 | 源 | 含义 |
|---|---|---|---|
| VisEval 是 code-first matplotlib 代码 SFT 语料 | 0-3 | 2407.00981 | **只采其 SVG 保真机制，勿当 SFT 数据** |
| VisEval 的 validity/legality/readability 三维 = 我们 C3 三元组 | 0-3 | 2407.00981 | 维度不等价，勿直接套 |
| nvBench「>80% 柱状图」偏斜（须重平衡） | 1-2 | 2407.19726 | 具体数字未决（分布差距结论仍成立） |
| nvBench2.0 无 data-fidelity 指标 / 88.06%·46% 歧义占比 | 1-2 | 2503.12880 | 是否测保真**未决**，勿假设其验保真 |
| 开源 VLM（InternVL 29.2%）弱→离线 judge 必弱 | 0-3 | 2406.18521 | 源实际称其为**最强开源**，勿据此贬低离线 judge |
| Qwen2.5-VL-7B 仅 14.53% 弃答（单卡 judge 可靠性下界） | 0-3 | 2509.17481 | 小模型弃答下界**未测**，勿引用该数字 |
| 微调 DePlot 把 RMS-F1 提到 91% / 喂表降 MAPE 至 3.66% | 1-2 | 2501.04675 | 往返作硬预言机的**正面证据不足**，仅 base 误映射结果成立 |

---

## 6. 代码级集成设计（🔧 grounded in 当前实现）

> step-2 的工作可直接落到现有 `agent/` 代码——尤其 **Judge 已有 VLM-judge 钩子**与 **PlotTrace 保真**两处。

- **现状钩子**：`agent/app/services/judge.py` 已有 `_call_vlm_judge(...)`（读 `LLM_API_BASE/VLM_API_KEY/VLM_MODEL`，把 PNG base64 发给 VLM）。→ **Pass2 结论：保留它但降级为 advisory**，不要让它主导 Data-Fidelity 判定。

| 项 | 来源(§) | 触及文件 | 改动 | 成本 |
|---|---|---|---|---|
| **Q1 SVG 反解析保真校验** | VisEval 1.4 | `judge.py`（新增 svg 检查）+ sandbox 存 SVG | 渲染时同时 `savefig(*.svg)`；反解析回收所绘值，跑 type/data/order vs plot_df/真值（CPU-only） | 极低 |
| **Q2 OneChart 往返保真预言机** | 2.3/2.4 | 新增 service + `judge.py` data_fidelity | 渲染 PNG→OneChart 读回 dict→**结构感知** keyed-diff vs plot_df；置信度门控 | 低(0.2B 单卡) |
| **Q3 三通道 typed 诊断** | PlotGen 1.2 | `judge.py` + `configs/diagnostics_map.yml` | 把诊断 Q 分 Numeric/Lexical/Visual 三类，分别路由 L3/L4/L1 | 低 |
| **Q4 series_cohesion 补全** | 步1 G3 + VisEval order 检查 | `configs/judge_rules.yml` | 补 `series_cohesion` 权重 + 跨 panel order/编码一致性（借 VisEval order 检查） | 低 |
| **Q5 Stage-A 语料接入** | Text2Chart31/Text2Vis 1.2/1.3 | 新增 data 管线 | 引入 11,128(Text2Chart31)+1,985(Text2Vis) 作 Code-SFT；cycle-consistency 作 Stage-C 奖励 | 中(一次性) |
| **Q6 MatPlotBench 评测接入** | 1.2 | 新增 eval 脚本 | 100 例作主回归 eval，对 MatPlotAgent 报基线；离线 Judge 替 GPT-4V | 低 |
| **Q7 nvBench2.0 五步 → HCT** | 1.5 | `default_slots_v2.py`(L1/L2) | 用五步拆解结构化 spec.compose 的意图→层分配 | 中 |

> **落地顺序**：Q1（CPU-only 保真，当晚可做）→ Q4 → Q3 → Q6 → Q2 → Q5 → Q7。

---

## 附录 A：一手来源

**Pass 1（agentic & code/NL 生成）**：2303.02927(LIDA)、2402.11453(MatPlotAgent/MatPlotBench)、2502.00988(PlotGen)、2410.04064(Text2Chart31,MIT)、2407.00981(VisEval)、2507.19969(Text2Vis,MIT)、2406.09961(ChartMimic)、2407.19726(Nguyen et al.)、2503.12880(nvBench2.0,CC BY-SA)。
**Pass 2（chart VLM）**：2406.18521(CharXiv)、2505.13444(ChartMuseum)、2504.05506(ChartQAPro)、2409.01577(EvoChart)、2312.15915(ChartBench)、2509.17481(ChartHal)、2212.10505(DePlot)、2212.09662(MatCha)、2404.09987(OneChart)、2501.04675(DePlot RMS-F1 caveat)。
**未核验（待第三轮）**：Draco/Draco2、VizML、Data2Vis、DeepEye、Data Formulator/2、ChartCoder、ChartX/ChartVLM、ChartGemma、TinyChart、Plot2Code、VisPath、VisText、Text2Analysis。

## 附录 B：覆盖核对
- [x] Pass1：LIDA/MatPlotAgent/PlotGen/Text2Chart31/VisEval/Text2Vis/ChartMimic/Nguyen/nvBench2.0 带引用核验
- [x] Pass2：CharXiv/ChartMuseum/ChartQAPro/EvoChart/ChartBench/ChartHal/DePlot/MatCha/OneChart/DePlot-caveat 带引用核验
- [x] 框架挂载表（感知·数据·评测层）+ 代码级集成设计 Q1–Q7（grounded `judge.py` 等）
- [x] 排序短名单 + 7 条开放问题 + 7 条证伪
- [ ] **第三轮（可选）**：Draco/VizML（C3 质量模型）、ChartCoder/ChartX、Data Formulator、指令微调 chart-VLM 候选 C3 Judge
- 两轮合计：50 源、244 主张、50 核验、42 证实、8 证伪、215 个 agent
