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
