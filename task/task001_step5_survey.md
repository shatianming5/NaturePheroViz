# 步骤2 第五轮（收尾）：NL2Vis 工具 + Captioning + 剩余 Chart→Table 读取器 → Code-First PheroREER

> **状态**：✅ **已完成**（但两路 workflow 都在**最终合成阶段 StructuredOutput 失败**——这是已知的 harness 不稳定点；**验证阶段均已完成**，本文从两路 journal 的 127 条核验主张直接取证，结论可靠）。两路合计：约 45 源、~250 主张、50 核验、~42 证实、~11 证伪。
> **为何有第五轮**：前四轮一直未 grounded 的**最外围**工作——NL2Vis 工具（ChartGPT/NL4DV/ncNet/Chat2VIS）、VisText captioning、剩余 chart→table 读取器（UniChart/DocOwl/StructChart/ChartReader）、Plot2Code 许可。本轮**收尾**，回答三个判定：
> 1. **NL2Vis 工具是否比已采纳的 nvBench2.0（L1/L2 五步 schema）更值得加**？
> 2. **VisText 的三级 caption 分类是否提升 C3 可读性评分 / 现有 `alt_text.py`（L4）**？
> 3. **有没有比 OneChart-0.2B/TinyChart-3B/ChartMoE-8B 更小/更准的单卡 chart→table 保真读取器**？Plot2Code 许可可用否？
> **标注**：✅=已核验；⚠️=反例/边界；❌=已证伪；🔧=我方集成分析。

---

## 中文执行摘要

第五轮收尾。回答三个判定，**无一颠覆既有蓝图**，但新增一个有价值的轻量选项：

1. **chart→table 读取器（最有价值的新发现）**：**UniChart-201M** 是**最轻量、且有直接结构感知指标**的单卡 chart→table 读取器——Donut 式 201M（比 MatCha 快 >11×、比 TinyChart-3B/ChartMoE-8B 小 15–40×），ChartQA 上 **RMS_F1 91.10**（vs TinyChart-3B 93.78，模型小 15 倍）。→ **加入候选**（与 OneChart-0.2B 同为「最轻」档）。⚠️**无明确 model 许可**（代码公开但未附协议，再分发前须确认）。**结论：已采纳的 OneChart/TinyChart/ChartMoE 不被颠覆，UniChart 作新增轻量选项。**

2. **NL2Vis 工具**：**ChartGPT**（IEEE TVCG'24，**端到端 Apache-2.0**，FLAN-T5-XL/Llama-3-8B 变体）的 **6 步分解**（选列/过滤/聚合 → 图型/编码/排序）比已采纳的 nvBench2.0 五步**多拆出「过滤/聚合/排序」**，可借作 spec.compose 的 CoT 模板（增量小）；**NL4DV**（离线意图解析器）可选；ncNet/Chat2VIS 被 nvBench2.0 + 我们的 LLM 取代。

3. **VisText captioning**：**12,441 对**，三级语义（L1 元素/L2 统计/L3 感知）→ 可作现有 `agent/app/services/alt_text.py` 的**生成 rubric** + C3 可读性「是否覆盖 L1/L2 语义」检查项（L3 上下文慎用易幻觉）。

4. **Plot2Code 许可仍未裁决**；StructChart/ChartReader/DocOwl 作独立读取器本轮亦未 grounded。

> ⚠️ **方法说明**：本轮两路 workflow 都在**最终合成阶段 StructuredOutput 失败**（已知 harness 不稳定）；但**验证阶段已完成**，本文结论从两路 journal 的 127 条已核验主张直接取证，可靠性不受影响。

---

## 0. 缺口挂载表（收尾三类）

| 我们的组件 | 本轮工作 | 关键判定 |
|---|---|---|
| **L1/L2 意图先验** | ChartGPT（stepwise）、NL4DV（任务+属性解析器）、ncNet、Chat2VIS | 比 nvBench2.0 五步更干净/更值得加？ （详见 §1）|
| **L4 可读性 / alt-text** | VisText（L1/L2/L3 三级 caption 分类）| 提升 C3 可读性评分 / `agent/app/services/alt_text.py`？ （详见 §1）|
| **C3 chart→table 读取器** | UniChart、DocOwl1.5/2、StructChart、ChartReader | 比 OneChart-0.2B/TinyChart-3B/ChartMoE-8B 更小/更准（带结构感知指标）？ （详见 §2）|
| **Stage-A/eval** | Plot2Code | 许可（Apache-2.0?）可用作 Stage-A/eval？ （详见 §2）|

> **净判定（见 §3）**：(1) chart→table 轻量档**新增 UniChart-201M**，已采纳三选项不被颠覆；(2) VisText 三级 caption **可选**喂 alt_text/L4；(3) NL2Vis 工具**低增量**（ChartGPT 6 步模板 + NL4DV 可选，其余被取代）。

---

## 1. Pass A — NL2Vis 工具 + Captioning（✅ 已核验，合成失败→journal 取证）

> ⚠️ 本路 workflow 同样在**合成阶段 StructuredOutput 失败而中止**，但**验证已完成（61 条核验主张在 journal）**，下列直接取证。

### 1.1 ChartGPT — 6 步分解 + Apache-2.0（最值得看的 NL2Vis）
**✅ ChartGPT**（Tian et al., arXiv:2311.01920, **IEEE TVCG 2024**, **Apache-2.0**）— **微调 LLM（非 API 包装）**，原 base=FLAN-T5-XL(~3B)，另释 **Llama-3-8B-Instruct 变体**，单卡。`Inspires: Partial（L1/L2/L3 schema）`
- **✅ 6 步分解**（数据变换 3 + 可视化变换 3，逐步执行）：**Step1 选列 / Step2 加过滤 / Step3 加聚合（→L3 数据变换）；Step4 选图型 / Step5 选编码 / Step6 加排序（→L1 图型 / L2 编码）**。
- 🔧 **How**：6 步比 nvBench2.0 五步**更细地拆出「过滤/聚合/排序」**，可作 spec.compose 前的 CoT 模板；HF（yuan-tian/chartgpt + dataset + 基座 FLAN-T5-XL）**端到端 Apache-2.0**。⚠️ 训练集小（1,538 三元组），与 nvBench2.0 重叠度高，增量=过滤/聚合/排序。

### 1.2 NL4DV / ncNet — 离线意图解析器 / NL2Vis 基线
**✅ NL4DV**（Narechania et al., arXiv:2008.10723, **IEEE VIS 2020**）— Python 包:表+NL query → JSON（**数据属性 + 分析任务 + Vega-Lite specs**）；**本地离线运行**（Stanford CoreNLP/spaCy）。`Inspires: Partial` → **可作 L1/L2 离线意图/属性解析器**喂 spec.compose。
**✅ ncNet**（Luo et al., via nvBench arXiv:2112.12926, **IEEE VIS 2021**）— Transformer seq2seq → **Vega-Zero**（Vega-Lite-like），slot=(mark, data, encoding, transform)。`Inspires: Partial` → L1/L2 先验/nvBench 基线。

### 1.3 Chat2VIS — 仅 LLM-prompting 观察
**✅ Chat2VIS**（Maddigan & Susnjak, arXiv:2302.02094, **IEEE Access 2023**）— ChatGPT/Codex/GPT-3 prompt 工程 → viz 代码，**无训练**。`Inspires: No（观察/基线）` → 我们的 LLM 已覆盖此模式。

### 1.4 VisText — 三级语义 caption（→ L4 / alt_text）
**✅ VisText**（Tang et al., arXiv:2307.05356, **ACL 2023 Outstanding**）— **12,441 chart-caption 对**；图有 3 表示（位图、数据表、**scene graph**）；采 Lundgard & Satyanarayan 语义**前 3 级：L1 元素/编码（轴/标记）、L2 统计/关系、L3 感知/上下文**。`Inspires: Partial（L4/alt-text）`
- 🔧 **How(→L4/C3)**：**三级语义分类可作 `agent/app/services/alt_text.py` 的生成 rubric**（L1 描述编码、L2 描述统计、L3 慎用——上下文易幻觉），并作 C3 可读性「是否覆盖 L1/L2 语义」的检查项。

### 1.5 小结
NL2Vis/captioning **多为低增量或被已采纳项覆盖**：ChartGPT 6 步（增量=过滤/聚合/排序，Apache-2.0 模板可借）、NL4DV（离线意图解析器，可选）、VisText（三级 caption → alt_text rubric，可选）值得**小幅借鉴**；ncNet/Chat2VIS 基本被 nvBench2.0 + 我们的 LLM 取代。**无一颠覆既有蓝图。**

---

## 2. Pass B — 剩余 Chart→Table 读取器 + Plot2Code（✅ 已核验，合成失败→journal 取证）

> ⚠️ 本路 workflow 在**最终合成阶段 StructuredOutput 失败而中止**，但**验证已完成（66 条核验主张在 journal）**，下列从 journal 直接取证。

### 2.1 UniChart — 新增的最小单卡 chart→table 读取器（带直接指标）
**✅ UniChart**（Masry et al., arXiv:2305.14761, **EMNLP 2023**）— **201M 参数（~0.2B）**，Donut 式（Swin 编码器 + BART 解码器，OCR-free，从 Donut 初始化），**比 MatCha(282M) 快 >11×、少 28% 参数**，比 TinyChart-3B/ChartMoE-8B/DocOwl-8B **小 15–40×**。4 个预训练目标含 **Data Table Generation**（「给图像生成扁平化数据表」，601,686 例）。`Inspires: YES（最轻量单卡保真读取器）`
- **✅ 直接 chart→table 指标**：ChartQA 上 **RNSS 94.01 | RMS_F1 91.10**（WebCharts 60.73|43.21）；MatCha 85.21|83.49。→ **RMS_F1 91.10 是结构感知指标**，略低于 TinyChart-3B 的 93.78 但**模型小 ~15×**。
- 🔧 **How(→C2/C3 Data-Fidelity)**：作**最轻量**「读数回译」读取器——渲染→UniChart 出表→与 plot_df 做 RMS 式结构感知 diff；201M 单卡几乎零负担。
- ⚠️ **Caveat（许可）**：**代码+语料公开（github vis-nlp/UniChart）但无明确 model 许可**——全文 "Apache" 仅出现 1 次且指 Web Data Commons **数据**（增强用）、非模型 → **再分发前须向作者确认许可**。

### 2.2 净判定：最佳单卡 chart→table 读取器（全候选比较）
| 候选 | 参数 | chart→table 指标 | 许可 | 定位 |
|---|---|---|---|---|
| **UniChart** | **201M** | **RMS_F1 91.10 (ChartQA)** | ⚠️ 无明确 model 许可 | **最轻 + 有直接指标** |
| OneChart | 0.2B | AP（含置信度弃答） | 开源 | 最轻 + 自带弃答 |
| TinyChart-3B | 3B | **RMS-F1 93.78（最高）** | Phi-2 谱系 MIT? | 精度最高、稍大 |
| ChartMoE-8B | 8B | 无专门 RMS-F1 | **Apache-2.0** | 与 Stage-A 同源、最大 |

> **建议**：轻量优先 **UniChart(201M, RMS_F1 91.10) 或 OneChart(0.2B, 有弃答)** 二选一；精度优先 **TinyChart-3B(93.78)**；许可干净优先 **ChartMoE(Apache-2.0)**。都仍 advisory，须自建错配图 held-out 校准。**结论:已采纳的三选项不被颠覆，UniChart 作「最轻 + 有直接指标」新增选项。**

### 2.3 本轮未 grounded
**Plot2Code（许可仍未确认）、StructChart、ChartReader、mPLUG-DocOwl 1.5/2（作独立 chart→table 读取器）** 本轮无存活主张（合成中止 + 这些工作核验未返回 grounded 结果）。**Plot2Code 许可裁决仍悬而未决**。

---

## 3. 净判定

| 判定 | 结论 |
|---|---|
| **最佳单卡 chart→table 读取器** | **轻量档新增 UniChart-201M（RMS_F1 91.10，但无明确许可）**，与 OneChart-0.2B（有弃答）并列最轻；精度档仍 TinyChart-3B（93.78）；许可档仍 ChartMoE（Apache-2.0）。**已采纳项不被颠覆。** |
| **Plot2Code 许可** | **仍未裁决**（本轮未 grounded）→ 暂不依赖；Stage-A 数据已有 ChartMoE-Align/ReachQA/Text2Chart31 充足 |
| **NL2Vis 工具** | **低增量**：ChartGPT 6 步（Apache-2.0，借「过滤/聚合/排序」模板）、NL4DV（离线意图解析器）可选；ncNet/Chat2VIS 被取代 |
| **VisText captioning** | **可选**：三级语义作 `alt_text.py` rubric + C3 可读性检查项 |

> **第五轮净增量**：仅 **UniChart-201M（最轻 chart→table 读取器）** 与 **ChartGPT 6 步/VisText 三级 caption 两个可选小借鉴**；其余被既有蓝图覆盖。**至此跨五轮的工程蓝图已收口、无重大缺口。**

## 4. 开放问题 / 风险（已核验）

1. **UniChart 许可**：代码/语料公开但**无明确 model 许可**（「Apache」仅指其增强用的 Web Data Commons 数据）→ 用前须向作者确认；否则退回 OneChart/ChartMoE。
2. **所有 chart→table 读取器在「我们 matplotlib 图风」上的实际精度**仍需自建错配图 held-out 集实测（UniChart/OneChart/TinyChart/ChartMoE 横评）——这是跨多轮反复强调的必做前置。
3. **Plot2Code / StructChart / ChartReader / DocOwl** 作独立读取器**仍未 grounded**（本轮合成失败 + 这些工作核验未返回结果）——可选第六轮，但**优先级低**（已有 UniChart/OneChart/TinyChart/ChartMoE 四个 grounded 候选足够）。
4. **VisText L3（感知/上下文）caption 易幻觉**——用于 alt_text 时只取 L1/L2 语义层。

## 附录 A：一手来源（已核验，journal 取证）
**Pass A**：2311.01920（ChartGPT, IEEE TVCG 2024, Apache-2.0）、2008.10723（NL4DV, IEEE VIS 2020）、2112.12926（ncNet/nvBench, IEEE VIS 2021）、2302.02094（Chat2VIS, IEEE Access 2023）、2307.05356（VisText, ACL 2023 Outstanding）。
**Pass B**：2305.14761（UniChart, EMNLP 2023；201M，chart→table RMS_F1 91.10@ChartQA；无明确 model 许可）。

## 附录 B：覆盖核对
- [x] Pass A：ChartGPT/NL4DV/ncNet/Chat2VIS/VisText 带引用核验（journal 取证）
- [x] Pass B：UniChart 带引用核验（含 RMS_F1 指标 + 许可）；Plot2Code/StructChart/ChartReader/DocOwl 未 grounded
- [x] 中文执行摘要 + 三类净判定 + 跨五轮蓝图收口声明
- [x] 透明记录：两路合成阶段 StructuredOutput 失败 → journal 取证（验证已完成）
- [ ] 可选第六轮（**优先级低**）：Plot2Code 许可 + StructChart/ChartReader/DocOwl 作读取器
- 两路合计（journal 计）：约 45 源、~250 主张、127 条核验主张取证
