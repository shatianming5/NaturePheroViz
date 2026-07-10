# 步骤2 第四轮（重核补齐）：学习式 Viz 先验 + ChartMoE → Code-First PheroREER

> **状态**：✅ **已完成**（两路并行检索均已核验合并）。两路合计：**39 源、187 主张、50 核验、47 证实、3 证伪、203 个 agent**。论文事实经 3 票对抗式核验。
> **为何有第四轮**：第三轮因核验 agent 多次 `StructuredOutput` 失败，导致 **VizML / DeepEye / Data2Vis / Data Formulator / ChartMoE** 等**未 grounded（未验证非证伪）**。本轮专门**重核**。
> **标注**：✅=已核验；⚠️=反例/边界；❌=已证伪；🔧=我方集成分析。

---

## 中文执行摘要

第四轮重核成功 grounding 了第三轮失败的工作，得到**两个净判定** + **一个互补发现**：

1. **ChartMoE（ICLR 2025）全部关键事实锁定**——backbone=InternLM-XComposer2、**8.4B（单张 24GB 卡可推理）**、MoE connector 4 专家（含 chart→table/JSON/code 对齐）、**ChartMoE-Align ~1M chart-table-JSON-code 四元组、Apache-2.0、HF 公开 54.6GB**、ChartQA 80.48→84.64。
2. **净判定·Stage-A 数据**：**ChartMoE-Align 取代/补强 ReachQA 为首选**（Apache-2.0 + ~1M vs 3k + table/JSON/code 三联监督，JSON 风格还能喂 C6 Γ）——但是**模板/DePlot 反推的 matplotlib 风、非 Nature 风**，须与我们的 Nature pairs + ReachQA 混合补风格。⚠️ 衍生权重继承 InternLM-XComposer2 基座许可，商用前单独核验。
3. **净判定·C3 Judge**：**ChartMoE(8B) vs TinyChart-3B 是二选一非超越**——ChartMoE 胜在「读数语义保真 + 与 Stage-A 同源 + Apache-2.0」，TinyChart 胜在「最轻 3B + 有直接 chart→table RMS-F1 93.78」。建议**两者都接 `judge.py:_call_vlm_judge` 钩子原型对比**;两者都仍 advisory、须自建错配图 held-out 校准。
4. **互补发现·VizML**：从 ~1M Plotly 对学 5 个设计选择、**CARS 88.96 达人类水平**——其 841 维特征 MLP 是**经验学习式**，与第三轮采纳的 Draco **符号约束正交互补**，可作 C3 的学习式 Visual-Form 子分 + L1/L2 先验（许可未声明，需 A/B 验证是否还胜过 Qwen-Coder 零样本）。
5. **L3 范式·Data Formulator（MIT）**：「概念绑定 + agent 驱动数据 reshape 先于编码」干净映射到 L3（注:我们当前 reshape 在 SCHEMA_L2，可上移）。**DeepEye/Data2Vis 跳过**（前者决策树与 Draco 规则冗余，后者仅观察）。

**一句话**：第四轮把 ChartMoE 从「未知」变成「Stage-A 数据首选 + C3 Judge 强候选」，并新增 VizML（学习式 Visual-Form 特征）和 Data Formulator（L3 reshape 范式）两件可选增强；NL4DV/ncNet/Chat2VIS/ChartGPT/VisText 仍未 grounded（可选第五轮）。

---

## 0. 缺口挂载表（本轮重核两类）

| 我们的组件 | 本轮工作 | 关键判定 |
|---|---|---|
| **C3 Data-Fidelity 读取器** | ChartMoE（chart→table/JSON/code 专家）、UniChart、DocOwl | 是否比 TinyChart-3B 更强的「读数回译」？ （详见 §1/§2）|
| **C10 Stage-A 数据** | ChartMoE-Align（~1M 四元组，若 Apache-2.0）、Plot2Code | 是否比 ReachQA(MIT 3k) 更大且许可可用？ （详见 §1/§2）|
| **L1/L2 设计先验** | VizML（5 个设计选择）、DeepEye、Data2Vis | 数据驱动图型/编码先验，互补 Draco 符号约束 （详见 §1/§2）|
| **C3 Visual-Form 特征** | VizML 特征 | 作 Draco 之外的学习式特征 （详见 §1/§2）|
| **L3 数据变换** | Data Formulator 1/2 | 概念绑定 + 迭代数据变换范式 → L3 （详见 §1/§2）|
| **L4 可读性/语义** | VisText | 图表 captioning → 语义层 （详见 §1/§2）|
| **基线/L1-L2** | ChartGPT、Chat2VIS、ncNet、NL4DV | NL→viz 意图先验/基线 （详见 §1/§2）|

> **本轮净判定**（待回填）：(1) ChartMoE 是否 supersede TinyChart-3B + ReachQA？(2) 有没有值得加的学习式 L1/L2/L3 先验？

---

## 1. Pass A — 学习式 Viz 先验 + NL→viz（✅ 已核验）

> 22 源、108 主张、25 核验、**23 证实、2 证伪**。**4 个锚点 grounded**（VizML/DeepEye/Data2Vis/Data Formulator）；NL4DV/ncNet/Chat2VIS/ChartGPT/VisText 仍未 grounded（未验证非证伪）。

### 1.1 VizML — 最强：学习式 L1/L2 先验 + Visual-Form 特征
**✅ VizML**（Hu et al., arXiv:1808.04819, **CHI 2019**）— 从 ~1M Plotly 对学 **5 个设计选择**：L1=VisType(VT)、Has-Shared-Axis(HSA)；L2=MarkType(MT)、Is-Shared-Axis(ISA)、Is-on-X/Y(XY)。2 类准确率 VisType 86.0/HSA 97.3/MarkType 84.9/ISA 98.3/XY 83.1；**CARS 共识基准 88.96 > Turkers 86.66、≈Plotly 用户 90.35（2019 已人类水平）**，超 Data2Vis 75.61、DeepEye 79.12。`Inspires: YES（互补 Draco）`
- 🔧 **How(→C3/C5)**：(a) **C3 Visual-Form 子分**——VizML 的 841 维特征 MLP 是**经验学习式**，与 Draco 的**符号约束正交互补**，可作 `judge_rules.yml` 之外的学习式 Visual-Form 特征；(b) **L1/L2 先验**——VT→L1 图型、MT/XY/ISA→L2 编码。**成本低**（小 MLP）。
- ⚠️ **Caveat**：**语料许可未声明**（repos mitmedialab/vizml、vizmlauthors/vizml-data）；去重后仅 119,815 数据集；是否仍胜过 Qwen2.5-Coder 零样本图型选择**需离线 A/B**。⚠️「5 选择确切拆分」framing 投票 1-2（但拆分本身在主 finding 3-0 确认）。

### 1.2 Data Formulator 1/2 — 最干净的 L3 方法迁移（MIT）
**✅ Data Formulator 1/2**（arXiv:2309.10094 IEEE TVCG 2023 / 2408.16119 Microsoft CHI 2025, **MIT**）— **概念绑定分离「高层意图（定义概念、绑定通道）」与「低层数据变换」**，AI agent 在编码前把表 reshape 成 tidy 形。`Inspires: YES（L3 范式）`
- 🔧 **How(→L3)**：采纳「**agent 驱动的 L3 reshape 先于编码**」——spec.compose 前先把数据整形到 tidy。**MIT、无权重、无 GPU**。⚠️ 注:我们当前代码里 reshape 算子在 `prompts_chain.py` 的 **SCHEMA_L2 而非 SCHEMA_L3**（研究读了我们代码）→ 可据此把数据变换上移到 L3。

### 1.3 DeepEye / Data2Vis — 弱 / 仅观察
**✅ DeepEye**（Luo et al., **ICDE 2018**）— 二元 good/bad 识别器（决策树 ~95% F，超 SVM/Bayes）over 14 维（图型=输入特征 7）+ LambdaMART 排序。`Inspires: Partial` → 作 **C3 Visual-Form/validity 分 + 排序配方**，**非编码生成器**。⚠️ **决策树 re-encode 了 Draco 已形式化的同一批符号规则（与 Draco 冗余）**；唯一增量 = **排序学习配方**（可作 C3 ranker）。❌ 证伪：「DeepEye 仅 4 图型作 L1 先验」（0-3，图型是输入特征非 4 型限定先验）。
**✅ Data2Vis**（Dibia & Demiralp, arXiv:1804.03126）— char 级 seq2seq → 整条 Vega-Lite spec（L1+L2+L3 捆绑）。`Inspires: No（仅观察）` → **NL2Vis 基线观察，CARS 75.61 最弱、不可分离**。

### 1.4 覆盖缺口（仍未 grounded）
**NL4DV、ncNet、Chat2VIS、ChartGPT（2311.01920）、VisText（2307.05356）** 仍无存活主张（未验证非证伪）→ 可选第五轮。

---

## 2. Pass B — ChartMoE 重核 + chart→table/code（✅ 已核验）

> 17 源、79 主张、25 核验、**24 证实、1 证伪**。**ChartMoE 全部关键事实已锁定**（重核成功）。净判定：**ChartMoE-Align 取代/补强 ReachQA 为 Stage-A 首选**；**C3 judge：ChartMoE(8B) vs TinyChart-3B = 精度/同源 vs 体量/直接指标，二选一非超越**。

### 2.1 ChartMoE — 全部关键事实锁定（ICLR 2025）
**✅ ChartMoE**（arXiv:2409.03277, **ICLR 2025**, Apache-2.0）`Inspires: YES（C3 保真读取器 + Stage-A 数据双用）`
- **✅ 体量/单卡**：backbone=InternLM-XComposer2（InternLM2-7B-ChatSFT + CLIP ViT-Large），**全模型 8.364B，MoE connector +63M（→8.427B）**；**fp16 推理峰值 23.86GB → 单张 24GB/A100-40G 可载**（训练 4×A100-40G）。
- **✅ 核心设计**：MoE connector 用 **4 个多样初始化专家**（1 vanilla + 3 个分别预训练于 **chart→table(CSV) / chart→JSON / chart→code(matplotlib)** 对齐）替换 2 层 MLP，top-K=2 门控，去 load-balancing loss，对齐时冻结视觉+LLM。⚠️ **专家是 connector 内部初始化、不能单独抽出当独立 chart→table 读取器——要用就跑整 8B 模型**。
- **✅ 数据 ChartMoE-Align**：**~1M chart-table-JSON-code 四元组**（ChartQA 18.3K+PlotQA 157K+ChartY 763.6K；微调 DePlot 反推属性 + 模板代码 + 编译/渲染过滤）；**HF Coobiw/ChartMoE-Data 54.6GB 公开**（chart2table/json/code.json）。
- **✅ 精度**：ChartQA **80.48%（前 SOTA=TinyChart+PoT）→ 84.64%（+PoT）**；自身 baseline 72.00%→81.20%（无 PoT）。
- **✅ 许可 = Apache-2.0**（代码+权重 HF IDEA-FinAI/chartmoe；数据 HF Coobiw/ChartMoE-Data；YAML+正文均明确）。⚠️**关键 nuance**：(i) 依据在 **HF 卡非 GitHub**（GitHub 无 LICENSE 文件）；(ii) **衍生权重基于 InternLM-XComposer2，继承其基座许可，再分发/商用前须单独核验**。
- 🔧 **How**：(a) **C3**——把 ChartMoE 服务在现有 `judge.py:_call_vlm_judge`（已是 OpenAI 兼容 + 返回 `scores.data_fidelity`），让它发出渲染图的 table/code，再喂 C2 执行、diff plot_df（闭环保真）；(b) **Stage-A**——ChartMoE-Align 的 chart→code 四元组直接作 Code-SFT（表→matplotlib 代码），JSON 风格属性还可喂 C6 Γ 一致性。

### 2.2 净判定（ChartMoE vs 第三轮选择）
- **✅ Stage-A 数据：ChartMoE-Align 取代/补强 ReachQA 为首选**——Apache-2.0 + **~1M（vs ReachQA 3k）** + 自带 table+JSON+code 三联监督（正合 plan §6.2 表→代码 + JSON 喂 Γ）。ReachQA(MIT) 留作推理风互补。⚠️ ChartMoE-Align 是**模板/DePlot 反推的 matplotlib、非 Nature 风** → 须与 Nature pairs（`download_nature_pairs.py`）+ ReachQA 混合补风格。
- **✅ C3 Judge：ChartMoE(8B) vs TinyChart-3B 是二选一非超越**——选 **ChartMoE** 若重「读数语义保真 + 与 Stage-A 同源 + Apache-2.0」；保留 **TinyChart-3B(3B,~6-8GB)** 若重「最轻单卡 + 有**直接 chart→table RMS-F1 93.78**」（ChartMoE 只报 ChartQA 准确率、无专门 chart→table 保真指标）。**两者都仍 advisory，须自建错配图 held-out 校准**。建议**两者都接到同一 `_call_vlm_judge` 钩子原型对比**。

### 2.3 本轮未 grounded
**UniChart、mPLUG-DocOwl 1.5/DocOwl2、Plot2Code（许可/规模仍未确认）、StructChart/ChartReader** 本轮无存活主张（**OneChart 0.2B 已在第三轮 grounded** 作单卡 chart→table 候选）。

---

## 3. 净判定 + 跨四轮收敛的工程决定

**本轮净判定**：

| 维度 | 决定 | 依据 |
|---|---|---|
| **C10 Stage-A 数据** | **ChartMoE-Align 为首选**（取代/补强 ReachQA），混 Nature pairs + ReachQA 补风格 | Apache-2.0 + ~1M + table/JSON/code 三联监督 |
| **C3 Judge（VLM）** | **ChartMoE(8B) 与 TinyChart-3B 二选一，原型对比**；都 advisory + 须校准 | 精度/同源/许可 vs 体量/直接 chart→table 指标 |
| **C3 Visual-Form 评分器** | **Draco2（符号）+ VizML（学习式特征）双管** | 二者正交互补（符号约束 vs 经验 MLP） |
| **L3 数据变换** | 采 **Data Formulator** 的 agent 驱动 reshape 范式（MIT） | 概念绑定分离意图/变换 |
| **跳过** | DeepEye（与 Draco 规则冗余）、Data2Vis（仅观察） | CARS 最弱 / 不可分离 |

**跨四轮（步骤2）形成的完整工程蓝图**（C3 Judge + Stage-A 数据 + 评测）：
- **C3 数据保真** = 主路「可执行证据」(plot_df + PlotTrace + **VisEval SVG 反解析**) + 副路 chart→table 往返(**OneChart 0.2B** 轻量 / **TinyChart-3B** 有直接指标 / **ChartMoE-8B** 同源)；**VLM-Judge 一律 advisory**。
- **C3 视觉形态** = **Draco2 符号约束 + VizML 学习式特征**，替/补 `judge_rules.yml` 手写规则。
- **C3 诊断结构** = **PlotGen 的 Numeric/Lexical/Visual 三通道**。
- **Stage-A 数据** = **ChartMoE-Align(~1M, Apache-2.0)** 为主 + **Text2Chart31/Text2Vis(MIT)** + **ReachQA(MIT)** + 自采 Nature pairs。
- **离线 eval + 基线** = **MatPlotBench** + MatPlotAgent/ChartCoder/Text2Chart31-8B/13B。
- **内环范式** = AlphaCodium/MatPlotAgent 的 render→critique→repair（步骤2）。

## 4. 开放问题 / 风险（已核验）

1. **ChartMoE 衍生权重的基座许可**：HF 卡只 Apache-2.0 了**代码**，权重基于 InternLM-XComposer2、继承其许可——**商用/再分发前须单独核验基座条款**。
2. **ChartMoE-Align 风格迁移**：其图是模板/DePlot 反推的 matplotlib、**非 Nature 风**；与 Nature pairs(`download_nature_pairs.py`) + ReachQA 的**最优混合比例**对 Qwen2.5-Coder-14B/32B (Q)LoRA 未知。
3. **ChartMoE vs TinyChart 实际 chart→table 保真**：ChartMoE 只报 ChartQA 准确率、无专门 chart→table 指标；二者在**我们 matplotlib 图风**上的读数精度/召回需**自建错配图(扰动 plot_df 后渲染) held-out 集**实测——这是两轮反复强调的必做前置。
4. **VizML 2018 先验是否还胜 LLM**：需离线 A/B（VizML 图型选择 vs Qwen2.5-Coder 零样本，在 Nature 表上）；且 VizML/DeepEye **语料许可未声明**。
5. **第五轮（可选）**：ChartGPT(2311.01920) 的 L1/L2 拆解、VisText(2307.05356) 的 C3/L4 captioning、UniChart/DocOwl/Plot2Code(许可) 仍未 grounded。

## 5. 已证伪 / 勿依赖（❌ 3 票核验否决）

| 主张 | 投票 | 源 | 含义 |
|---|---|---|---|
| 「ChartMoE-Data Apache-2.0 ⇒ 直接确认 Stage-A 可用」 | 1-2 | Coobiw/ChartMoE-Data | over-claim；**Apache-2.0 事实本身 3-0 成立**，但「可用」须叠加基座许可核验 |
| VizML「确切 5 选择拆分」的精确表述 | 1-2 | VizML CHI'19 | 拆分本身在主 finding 3-0 确认，仅 framing 过细 |
| DeepEye 仅 4 图型(bar/line/pie/scatter)、可作 4 型 L1 先验 | 0-3 | DeepEye ICDE'18 | 图型是**输入特征非 4 型限定先验**，勿据此当 L1 生成器 |

## 附录 A：一手来源（已核验）
**Pass A（学习式先验）**：1808.04819（VizML, CHI 2019）、2309.10094（Data Formulator, IEEE TVCG 2023）、2408.16119（Data Formulator 2, CHI 2025, MIT）、ICDE'18（DeepEye）、1804.03126（Data2Vis）。
**Pass B（ChartMoE）**：2409.03277（ChartMoE, ICLR 2025, Apache-2.0；HF IDEA-FinAI/chartmoe + Coobiw/ChartMoE-Data）。

## 附录 B：覆盖核对
- [x] Pass A：VizML/DeepEye/Data2Vis/Data Formulator 1/2 带引用核验（NL4DV/ncNet/Chat2VIS/ChartGPT/VisText 仍未 grounded）
- [x] Pass B：ChartMoE 全部关键事实（backbone/体量/MoE 专家/~1M 数据/精度/Apache-2.0）带引用核验（UniChart/DocOwl/Plot2Code 仍未 grounded）
- [x] 中文执行摘要 + 净判定（ChartMoE vs 第三轮）+ 跨四轮工程蓝图 + 开放问题 + 证伪清单
- [x] 回填步骤3 §4 开放问题 6（ChartMoE 已重核：Apache-2.0 + ~1M，VizML/Data Formulator 已 grounded）
- [ ] **可选第五轮**：ChartGPT/VisText + UniChart/DocOwl/Plot2Code + StructChart（NL2Vis 工具与剩余 chart→table 读取器）
- 两路合计：39 源、187 主张、50 核验、47 证实、3 证伪、203 个 agent
