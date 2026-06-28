# 步骤2 第三轮（覆盖补齐）：Viz-Quality 模型 + 指令微调 Chart-VLM → Code-First PheroREER

> **状态**：✅ **已完成**（两路并行检索均已核验合并）。两路合计：**37 源、185 主张、50 核验、31 证实、19 证伪、202 个 agent**。论文事实经 3 票对抗式核验。
> **为何有第三轮**：步骤2 两轮把锚点工作核验了，但 **Draco/VizML（viz 质量模型）、指令微调 chart-VLM（候选单卡 C3 Judge）、ChartCoder/Plot2Code（chart→code 数据）** 等未在 3 票核验中存活。本轮专补这两个**精确缺口**（见 §0 缺口挂载表）。
> **标注**：✅=已核验；⚠️=反例/边界；❌=已证伪；🔧=我方集成分析。

---

## 中文执行摘要

第三轮专补步骤2 的两个精确缺口，得到两个**可直接落地的工程决定** + 一个**架构范式**：

1. **C3 缺的「有原则的 Visual-Form 评分器」→ 用 Draco/Draco 2**（IEEE VIS，**BSD/开源、符号、无 GPU**）。它把可视化设计知识编码为 ASP 硬约束（有效性）+ 加权软约束（偏好），用**线性代价 + RankSVM 学习权重**给图打分，**经验学习权重碾压手调（93% vs 65%）**——正好替换我们 `judge_rules.yml` 的手写规则/权重，并把 C6 Γ 一致性表达为硬约束。**唯一门槛**：Draco 作用于 Vega-Lite **声明式 spec 而非代码**，需先建「matplotlib→spec 适配器」（从 PlotTrace/plot_df 抽图型/编码/刻度）。

2. **C3 缺的「单卡可跑本地 VLM-Judge」→ 用 TinyChart-3B**（EMNLP'24，~6–8GB）。它 **ChartQA 83.60 超 13B 模型和 GPT-4V**，且**唯一同时具备实测 chart→table 抽取（RMS-F1 93.78）和 PoT 数值推理（78.98 vs 56.64）**——正是数据保真验证所需两个属性。**用法**：接到 `judge.py:_call_vlm_judge`，PoT 模式抽表 + 发可执行 Python 回我们 C2 执行、与 plot_df 比对。ChartGemma-3B 次优（多了图表声明事实核查 70–74%）；**ChartVLM 的「先 chart→table 再判」级联值得抄成 C3 控制流**。

3. **Stage-A chart→code 数据 → 首选 ReachQA（MIT，释出可执行代码）**；Chart2Code-160k 更大但 **CC-BY-NC + 有代码错误**（研究用回退）；ChartX 给 image/CSV/code/text 四元组但许可未核验、评测是 GPT 评分非执行验证。

4. **DracoGPT（IEEE VIS'24）决定性回答「LLM 能否自评 visual form」：不能可靠自评，且 task-dependent**（值比较任务对齐、汇总任务反向）→ 印证「保留符号 Draco 评分器 + VLM-Judge 仅 advisory」，并提示可按任务类型在两者间路由。

**最大诚实警示**：**没有任何工作直接测过这些小 VLM 检测「错配图」的可靠性**（都只报 QA/抽取/事实核查准确率）——TinyChart/ChartGemma 当 C3 Judge **前必须自建「扰动 plot_df vs 渲染」held-out 集校准**。覆盖上，VizML/DeepEye/Data Formulator 与 ChartMoE 因核验 agent 多次 StructuredOutput 失败**未 grounded**（未验证非证伪），列为可选第四轮。
---

## 0. 缺口挂载表（本轮精确补两个洞）

| 我们的组件 | 本轮工作如何补 | 典型工作 |
|---|---|---|
| **C3 Visual-Form 评分器**（现仅手写规则） | **Draco/Draco2 把感知最佳实践编码为 ASP 软/硬约束**（可学权重）→ 规则化/排序；VizML/DeepEye 学习式设计先验 | Draco, Draco2, VizML, DeepEye （详见 §1/§2）|
| **C6 Γ 一致性约束** | Draco 的跨编码一致性约束直接充实 Γ | Draco （详见 §1/§2）|
| **L1/L2 意图·编码** | 设计选择预测 + NL→viz 拆解 → 图型/编码先验 | VizML, ncNet, ChartGPT, Chat2VIS, NL4DV （详见 §1/§2）|
| **L3 数据变换** | Data Formulator 的「概念绑定 + 迭代数据变换」范式 | Data Formulator 1/2 （详见 §1/§2）|
| **C3 VLM-Judge 本体（单卡候选）** | 小体量指令 chart-VLM，评其可靠性能否当本地 Judge | ChartGemma-3B, TinyChart-3B(PoT), ChartVLM, ChartMoE （详见 §1/§2）|
| **C10 Stage-A 数据** | chart→code 语料 + 基线 | ChartCoder(Chart2Code-160k), Plot2Code, ChartX （详见 §1/§2）|
| **C3 自判可信度** | LLM 的 viz 偏好是否合规（能否自评 form） | DracoGPT （详见 §1/§2）|

> **本轮要回答的两个判定**：(1) **有没有一个现成的「有原则的 Visual-Form 评分器」**能替我们手写规则（Draco 最有希望）？(2) **有没有一个单卡可跑、且足够可靠的 chart-VLM** 能当本地 C3 Judge（步骤2 已证大 VLM 不可靠，小 VLM 更存疑）？

---

## 1. Pass A — Viz 质量/推荐模型 + NL→viz（✅ 已核验，覆盖窄但决定性）

> 22 源、110 主张、25 核验、**15 证实、10 证伪**。⚠️**本轮只有 Draco 家族通过 3 票核验**（VizML/DeepEye/Data Formulator/ChartGPT 等的核验 agent 多次 StructuredOutput 失败、未出票——是**未验证非证伪**）。但 **Draco 家族正是「有原则的 Visual-Form 评分器」这一问题的头号答案**。

### 1.1 Draco / Draco 2 — 有原则的 Visual-Form 评分器（头号答案）
**✅ Draco**（Moritz et al., **IEEE InfoVis 2019**, idl.uw.edu/papers/draco, **BSD**）— 把可视化设计知识形式化为 **ASP 硬约束（必满足有效性，如「shape 编码不能表达定量值」）+ 加权软约束（偏好，如「时间值默认用 x 轴」）**，Clingo 求解；**符号、非 LLM**。`Inspires: YES（方法迁移 C3+C6）`
- 🔧 **How(→C3/C6)**：硬/软约束分离正是充实我们 `configs/judge_rules.yml` 手写 visual_checks（need_title/need_legend_if_multi/min_contrast:0.12）的范式，并把 **C6 Γ 跨 panel 一致性（palette/font/scale/unit）表达为硬约束**。**成本可忽略**（Clingo 符号求解，无 GPU/LLM；成本是写 .lp 约束文件的工程）。
- **✅ 评分机制**：Draco 用**线性代价 Cost(v)=xᵀw**（x=软约束违反计数向量）排序，**权重经 RankSVM 从有序对学习**（非手调）→ 可移植为**数据驱动 Visual-Form 评分器**（数值代价而非 pass/fail 布尔）。
- **✅ 学习权重碾压手调：93% vs 65% 成对排序准确率**（手调 CompassQL「仅略高于随机」）→ 印证用经验学习权重替我们手调 judge_rules.yml 权重。⚠️ 限 scatter/bar/line 受限空间、需 ~250+ 对。
- **✅ Draco 2**（arXiv:2308.14247, **IEEE VIS 2023**, cmudig/draco2）— 维护中，同架构，**Draco-Learn 学权重，违反向量可作 ML 特征**，pip 可装 → **当前可直接 build-on 的实现**。

### 1.2 ⚠️ 决定性迁移风险 — Draco 作用于 spec 不是 code
**✅** 所有 Draco 约束作用于**抽象声明式 spec（Vega-Lite，经 vl2asp/asp2vl，ASP 求解）而非渲染代码**。→ 迁到我们 matplotlib-code Judge **需先建「matplotlib→声明式 spec 适配器」**（把 C2 PlotTrace/plot_df + 解析的绘图调用 → 图型/编码/刻度 facts）再套约束。`Inspires: Partial（机制可迁，适配器是门槛工作）`
- ⚠️ 部分 matplotlib 特有缺陷（低对比、刻度重叠、DPI、字体）**在 Vega-Lite fact 层无法表达**，仍需 C3 定制规则。

### 1.3 DracoGPT — LLM 能否自评 visual form？（答：不能，且 task-dependent）
**✅ DracoGPT**（Wang/Gordon/Battle/Heer, arXiv:2408.06845, **IEEE VIS 2024**）— 用 DracoGPT-Rank（判别式成对排序）+ DracoGPT-Recommend（生成式补全）抽取 LLM viz 偏好，经 RankSVM 编码为 Draco 权重，与经验学习权重同空间对比。`Inspires: YES（C3 诊断/评估方法）`
- **✅ 决定性发现**：GPT-4-Turbo 的 Rank↔Recommend 互相中度相关（r=0.70），但与人类感知学习代价**仅弱相关**——**LLM 不能可靠复现经验最佳实践**；**且 task-dependent**：对**值比较任务**中度对齐（r~0.67–0.69），对**汇总/聚合任务**发散/反向（r=-0.18/-0.32）。→ **C3 不能靠 LLM 自评 visual form，需保留符号 Draco-经验评分器。**
- 🔧 **启示(→C4)**：可按**分析任务类型**在「LLM 自评」与「Draco 符号评分」间路由（开放：judge 时如何检测任务类型）。⚠️「一律不可信」笼统表述已证伪 1-2，只有 task-dependent 版本成立。

### 1.4 覆盖缺口（本轮未 grounded）
**VizML、Data2Vis、DeepEye、Data Formulator 1/2、ChartGPT、Chat2VIS、NL4DV、ncNet、Seq2Vis、VisText** 未通过 3 票核验（核验 agent 多次 StructuredOutput 失败，**未验证非证伪**）。VizML（百万对语料学 5 个设计选择→L1/L2）、Data Formulator（数据变换→L3）的映射**仍待后续验证**。

---

## 2. Pass B — 指令微调 Chart-VLM + Chart→Code 数据（✅ 已核验）

> 15 源、75 主张、25 核验、**16 证实、9 证伪**。**直接回答 round-3 问题 (2)(3)**：单卡 C3 Judge 选 **TinyChart-3B**；Stage-A 干净许可数据选 **ReachQA(MIT)**。⚠️**关键诚实结论**：**没有任何工作直接测小 VLM「检测错误/不匹配图」的可靠性**——PoT/chart→table 是**数值保真的间接证据非证明**，采用前须自建「错配图」held-out 集校准。

### 2.1 单卡 C3 VLM-Judge 候选（TinyChart-3B 胜出）
**✅ TinyChart-3B**（arXiv:2404.16635, **EMNLP 2024**）— **3B**（SigLIP+Phi-2，TinyLLaVA 初始化，Visual Token Merging 扩到 512/768），**ChartQA 83.60**（aug 93.86/human 73.34）——**超 13B ChartAst(79.90)、ChartLlama(69.66)，且超 GPT-4V(78.50)/Gemini-Ultra(80.80)/Qwen-VL-Max(79.80)**。~6–8GB fp16 单卡。`Inspires: YES（C3 VLM-Judge 本体首选）`
- **✅ PoT 提数值保真（最相关）**：计算型 ChartQA **PoT 78.98 vs Direct 56.64**（Combine 80.42）；训练于 ChartQA-PoT（140,584 题→可执行 Python）；**chart→table 值抽取 RMS-F1 93.78**（超 ChartAst 91.60/ChartLlama 90.00）→ **直接回答问题(c)：PoT+chart→table 头确实提数值保真**。
- 🔧 **How(→C3 `judge.py:_call_vlm_judge`)**：(i) 作本地 VLM-judge backend（drop-in 推理，无需训练）；(ii) **PoT 模式当 Data-Fidelity 读取器**——让 TinyChart 抽出渲染图的表 + 发出可执行 Python，喂回我们 C2 Render+PlotTrace 执行，与 plot_df 比对出保真诊断 Q（中成本：接线）。Phi-2 谱系 MIT 友好（须确认）。

**✅ ChartGemma-3B**（arXiv:2407.04172, **COLING 2025 Industry**）— **3B**（PaliGemma=SigLIP+Gemma-2B，~6GB），**从图像像素（非底层表）生成指令数据**；ChartQA 80.16；**报告图表声明事实核查 ChartFC 70.33%/ChartCheck T1 71.50%/T2 74.31%**——**最接近「检测错误图表声明」这一 C3 任务的实测代理**。`Inspires: YES（次优 + 错配检测信号）`
- 🔧 **How(→C3 错配检测)**：用其 fact-check 头判 caption/指令声明是否匹配渲染图；亦支持 PoT + Chart-to-Markdown（重建表）。⚠️ 但**无定量抽取指标**（vs TinyChart RMS-F1）→ 数据保真角色 TinyChart 优先。

### 2.2 chart→table-FIRST 架构（C3 控制流范式）
**✅ ChartVLM**（Base-7.3B/Large-8.3B, arXiv:2402.12185）— **级联解码：永远先做 image→CSV 结构抽取再做认知任务**（为可解释性）；ChartX SCRM AP 超 GPT-4V / ChartAst-13B / ChartLlama-13B。`Inspires: YES（架构最契合）`
- 🔧 **How(→C3 控制流)**：**采纳「先结构抽取再判」级联**——强制本地 VLM 先从渲染图发出 CSV/表再评保真，正好镜像我们 plot_df 比对。⚠️ SCRM 是作者自家 ChartX 基准（home-team）。

### 2.3 Chart→code 数据（Stage-A）— 许可是硬约束
**✅ ReachQA**（arXiv:2410.18798, **EMNLP 2025 Findings, MIT**）— **唯一明确宽松许可**：3k 推理图+20k QA，**Code-as-Intermediary Translation**（代码先生成，33 个 Matplotlib seed 经 Self/Evol-Instruct 扩展），**释出可执行 matplotlib 代码**（execute_code.py）。`Inspires: YES（Stage-A 干净数据首选）`
- ⚠️ 偏推理 QA、非 Nature 风；HF parquet 仅含 image/QA（代码须从 GitHub 取）；用前确认仓库 MIT。
**✅ ChartCoder ~7B + Chart2Code-160k**（arXiv:2501.06598, **ACL 2025**）— code-first chart→code MLLM（SigLIP+deepseek-coder-6.7b）+ **最大数据集 160k/27 图型**，但 **CC-BY-NC-4.0（非商业）+ 作者已声明部分代码含错误**（修复版在另一 VinciCoder 发布）。`Inspires: YES（设计）/ Partial（数据 NC+错误）` → 研究用 Stage-A 数据（须过滤错误或用 VinciCoder 版）+ baseline。
**✅ ChartX**（arXiv:2402.12185）— 48K/18 图型/**4 对齐模态（图,CSV,Python,文本）** + chart→code「Redrawing」任务。`Inspires: Partial` → SFT-ready 四元组，但 redrawing 是 **GPT 评分(0-5) 非执行验证**（弱于我们 C2/C3 标准）；许可未核验。

### 2.4 ⚠️ 诚实结论 + 未核验
- **关键**：**无任何工作直接测小 VLM 检测「错配图」的可靠性**（都只报 QA/抽取/事实核查）→ TinyChart/ChartGemma 当 C3 Judge **前须自建「扰动 plot_df vs 渲染」held-out 集校准**。
- **ChartMoE**（arXiv:2409.03277，MoE connector + ~1M ChartMoE-Align 四元组 + 称 Apache-2.0）**未通过核验**（0-0/1-0）——若属实则对 C3 保真读取器 + Stage-A 都极契合，**值得第四轮重核**。Plot2Code 许可/数字本轮亦未确认（ChartMimic 已在步骤2 Pass1 grounded）。

---

## 3. 排序短名单（已核验，按落地优先）

| 排名 | 采纳项 | 来源(§) | 角色 | 许可/成本 |
|---|---|---|---|---|
| 1 | **Draco 2 约束 + RankSVM 学习权重** → C3 Visual-Form 评分器 + C6 Γ 硬约束（替手写 `judge_rules.yml`） | 1.1 | **C3/C6 评分器** | BSD，符号无 GPU；**需先建 matplotlib→spec 适配器** |
| 2 | **TinyChart-3B（PoT 模式）** → C3 本地 VLM-Judge + Data-Fidelity 读取器（接 `judge.py:_call_vlm_judge`，发可执行 Python 回 C2 比对 plot_df） | 2.1 | **C3 Judge 本体** | ~6–8GB 单卡；Phi-2 谱系 MIT（须确认）；**采用前自校准** |
| 3 | **ReachQA（MIT，可执行代码）** → Stage-A Code-SFT 数据 | 2.3 | **C10 数据** | MIT；低成本 |
| 4 | **ChartVLM「先 chart→table 再判」级联** → C3 控制流范式 | 2.2 | **C3 架构** | 控制流改动 |
| 5 | **ChartGemma-3B 事实核查头** → C3 错配/声明检测（caption vs 图） | 2.1 | **C3 错配检测** | ~6GB 单卡 |
| 6 | **DracoGPT 协议** → 按任务类型在「LLM 自评 vs Draco 符号评分」间路由（C4） | 1.3 | **C4 路由依据** | 复用现有 LLM |
| 备 | Chart2Code-160k（研究用，须过滤错误/用 VinciCoder 版）、ChartX 四元组 | 2.3 | Stage-A 回退 | NC / 许可未核 |

> **本轮净结论**：两个缺口都补上了——**Visual-Form 评分器 = Draco2（符号、需 spec 适配器）**；**本地 VLM-Judge = TinyChart-3B（但须自校准）**。两者都**不取代**而是**补强**我们「可执行证据」主路（步骤2 的护城河结论不变）。

---

## 4. 开放问题 / 风险（已核验）

1. **Draco 符号约束能否真迁到「matplotlib 代码输出」？** → 已确认是**主门槛**：Draco 作用于 Vega-Lite/ASP facts，需先建 **matplotlib→声明式 spec 适配器**（从 PlotTrace/plot_df + 解析绘图调用抽图型/编码/刻度）；且**部分 matplotlib 缺陷（低对比/刻度重叠/DPI/字体）在 Vega-Lite fact 层无法表达**，仍需 C3 定制规则。适配器覆盖率未知。
2. **小 VLM（3B）当 Judge 检测「画错」的可靠性** → **无任何工作直接测**（都只报 QA/抽取/事实核查）。**必须自建 held-out 错配集**（扰动 plot_df 后渲染，看 VLM 能否抓）并校准 precision/recall 再信。
3. **PoT/chart→table 头是否真提数值忠实度到可当 verifier？** → **间接证据强**（TinyChart RMS-F1 93.78、PoT 78.98 vs 56.64），但**非「检测错配」直接证明**；最佳验证 = 把 TinyChart 的 PoT 输出**喂回我们 C2 执行器**做闭环执行验证（无人做过，是可原型化的新集成）。
4. **chart→code 数据许可** → ReachQA **MIT**（确认仓库 LICENSE）；Chart2Code-160k **CC-BY-NC + 有代码错误**；ChartX 许可**未核验**。商用须清权或自产（复刻 ReachQA 的 code-first 生成→执行过滤配方）。
5. **能否为离线设定训出 Draco 式学习评分器（无大 ranked-pair 语料）？** → Draco 93% 需感知实验对、<250 对就退化；开放:能否用 C7/C9 的 pheromone rollouts 合成足够 ranked matplotlib 对，或复用 Draco 预学的 Vega-Lite 权重。
6. **第四轮可选**：VizML/DeepEye（→L1/L2 设计先验）、Data Formulator（→L3 数据变换）、**ChartMoE**（MoE + ~1M 四元组 + 称 Apache-2.0，若属实对 C3+Stage-A 都极契合）因 StructuredOutput 失败**未 grounded**，值得重核。

---

## 5. 已证伪 / 未 grounded（❌/⚠️ 透明记录）

| 主张 | 状态 | 源 | 含义 |
|---|---|---|---|
| LLM viz 偏好「一律」与经验指南背离（不分任务） | ❌ 证伪 1-2 | 2408.06845 | 只有 **task-dependent 版本成立**（值任务对齐、汇总任务反向） |
| ChartMoE：InternLM-XComposer2 backbone / Apache-2.0 / ChartQA 80.48→84.64 / ~1M ChartMoE-Align 四元组 | ⚠️ 未 grounded 0-0/1-0 | 2409.03277 | **未验证非证伪**；若属实极契合，须第四轮重核，勿假设 |
| Plot2Code Apache-2.0 许可 / 具体数字 / 「前沿 VLM 不可靠」 | ⚠️ 未 grounded 0-0 | 2405.07990 | 本轮未确认；「前沿 VLM 不可靠」引步骤2 Pass2 即可 |
| VizML 百万对语料 / 5 个可学设计选择 | ⚠️ 未 grounded 0-0 | 1808.04819 | L1/L2 先验映射待第四轮验证 |

## 附录 A：一手来源（已核验）
**Pass A（viz 质量/NL2Vis）**：2019-Draco-InfoVis（Draco, IEEE InfoVis 2019, BSD）、2308.14247（Draco 2, IEEE VIS 2023）、2408.06845（DracoGPT, IEEE VIS 2024）。
**Pass B（chart-VLM/chart→code）**：2404.16635（TinyChart-3B, EMNLP 2024）、2407.04172（ChartGemma-3B, COLING 2025）、2402.12185（ChartVLM/ChartX）、2410.18798（ReachQA, EMNLP 2025, MIT）、2501.06598（ChartCoder/Chart2Code-160k, ACL 2025, CC-BY-NC）。

## 附录 B：覆盖核对
- [x] Pass A：Draco/Draco2/DracoGPT 带引用核验（VizML/DeepEye/Data Formulator/ChartGPT/Chat2VIS/NL4DV/ncNet/VisText 因 StructuredOutput 失败未 grounded）
- [x] Pass B：TinyChart/ChartGemma/ChartVLM/ChartCoder(Chart2Code-160k)/ReachQA/ChartX 带引用核验（ChartMoE/Plot2Code 未 grounded）
- [x] 中文执行摘要 + 缺口挂载表 + 排序短名单 + 开放问题 + 证伪/未 grounded 清单
- [x] 回填步骤2 survey 的缺口：**C3 Visual-Form 评分器 = Draco2；C3 本地 VLM-Judge = TinyChart-3B；Stage-A 数据 = ReachQA(MIT)**
- [ ] **可选第四轮**：VizML/DeepEye/Data Formulator + **ChartMoE 重核**（StructuredOutput 失败导致本轮未出票）
- 两路合计：37 源、185 主张、50 核验、31 证实、19 证伪、202 个 agent
