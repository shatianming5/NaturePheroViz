# Measurement 提案 round-0：可执行数据保真——viz-codegen 评测的缺失维度

> ⚠️ **作废（2026-06-13）**：本提案的"绘图 silent error"前提已被 go/no-go 证伪——
> 强 LLM 在"给定干净数据画标准图"上 silent-error 率 **0%**（20 跨文章真实任务，GPT-4o/Claude 全对）。
> **但发现真问题在上游**：LLM 生成的**数据变换代码**（groupby/pivot/加权/占比/join）silent 语义错率
> **GPT-4o 38% / Claude 25%**（16 陷阱变换）。方向已转为"执行追踪验证数据变换语义"——
> 见后续 transform 方向。本文件保留作探索留档。

> 路线 A（领域测量/警钟论文）。目标顶会 Oral。
> 一句话：现有 viz-codegen 评测全漏了"画出来的数 == 该画的数"这一维；我们第一个用**执行追踪**系统性测量它，发现连最强 LLM 在真实科学图上也有不可忽视的 silent data error，而所有现有 benchmark 测不出。

---

## 0. Problem Anchor

- **根本问题**：LLM 生成 matplotlib 代码画图已广泛使用，但**没有任何评测测量"图里画出来的数值是否等于输入/意图数据"**。现有 benchmark（MatPlotBench/Plot2Code/ChartMimic 等）测的是代码相似、视觉相似、execution-pass，**默认"只要图画出来了、看着对，数据就对"**——这个默认是错的。
- **要测量/揭示的现象**：silent data error——图视觉合理、代码能跑、但画出来的数被悄悄画错（错列映射/漏系列/错聚合/双轴误绑）。这类错误**人眼和现有判官都发现不了**，却让图传达错误信息。
- **核心测量主张**：用执行追踪（捕获 matplotlib 实际收到的数组）作为 ground-truth 读回，**系统性测量主流 LLM 在受控+真实任务上的 silent data error 率**，并量化现有判官（列名/SVG/VLM）对这些错误的漏检率。
- **非目标**：不主张"我们的生成器更好"（已证伪）；不训模型；不做新生成方法。这是 measurement/audit 论文，不是 method 论文。
- **成功条件**：(a) 一个可信、可复现的 silent-error 测量协议；(b) 报告多个强 LLM 的 silent error 率（受控注入 + 真实任务两档）；(c) 量化现有判官漏检率 vs 执行追踪检出率，证明这一维确实被漏测且重要。

---

## 1. 为什么这是"领域测量"而非"又一个判官"

- **重新定位**：执行追踪不再是"我们的方法卖点",而是**测量工具**(就像用更准的尺子去量整个领域之前没量的东西)。
- **vs VisEval**：VisEval 做 SVG 反解析验 legality，但 ① 它是 post-hoc 框架不是领域测量；② 我们已实测 SVG 反解析在真实科学图上定位率 0%（噪声），所以**SVG 不足以做这个测量,必须用执行追踪**——这正是"为什么以前没人系统测过"的答案。
- **vs 现有 codegen benchmark**：它们的指标里**根本没有 data-fidelity 这一列**。我们补上这一列,并证明补上后,排名/结论会变（强模型在视觉/exec 上满分,但在 data-fidelity 上漏洞）。

---

## 2. 测量协议（论文核心，要可信可复现）

**两档测量**：

### 档1：受控注入（precision 可控，量化判官漏检率）
- 取正确 (data, 标准绘图代码)，注入已知 silent 损坏（wrong_value/drop_series/scale/swap/twin-misbind）。
- 对每张损坏图，四判官（列名/SVG/VLM/执行追踪）各判：检出率 + 定位率。
- **已有结果**（synthetic+real Nature）：列名 0% recall；SVG 真实数据定位 0%、clean 误报 14/15；执行追踪 clean 1.0、检出+定位最高。→ **这就是"现有判官测不出、执行追踪能测"的硬证据**。

### 档2：真实生成的 silent error 率（领域警钟，要做大）
- 取 N 个绘图任务（受控合成 + 真实数据表），让多个强 LLM（GPT-4o/Claude/...）一次性生成绘图代码。
- 用执行追踪 oracle 测每个产出的 data-fidelity。
- **报告每个模型的 silent error 率** = (画出来的数 ≠ 输入数据) 的比例，按任务复杂度（单系列/多系列/双轴/真实科学列名）分层。
- **关键警钟数字**：即使 exec-pass 100%、视觉合理，silent error 率仍 > 0（尤其复杂/真实任务）。

---

## 3. 已有资产（复用，不重造）

- **执行追踪 oracle**：`plot_trace.py`（6 例 selftest 过，对齐层处理 grouped-bar offset / twinx / 类目）+ 覆盖表（7/7 图型 RESOLVED）。
- **四判官对比 harness**：`eval/silent_error_audit.py`（档1，合成+真实双版本已跑）。
- **真实数据**：154 篇 Nature / 1362 图-源数据配对 + 自洽过滤（界定可干净测量的子集）。
- **端到端生成 harness**：`eval/end2end_bench.py / nature_e2e.py`（档2雏形，已能跑多模型 oneshot + oracle）。

---

## 4. 要补什么才到 Oral（最薄弱处）

1. **测量规模与代表性**：现在真实数据样本小且不独立（8 个 task 全来自同一篇文章）。要扩到**几十~上百个跨文章、跨学科的真实任务**，silent error 率才可信。
2. **多模型覆盖**：至少 GPT-4o / Claude / 一个开源（Qwen-Coder 等），证明 silent error 是**普遍现象**而非单模型缺陷。
3. **silent error 率必须够"惊人"**：如果强模型在真实复杂图上 silent error 率只有 2%，警钟不够响。要找到/构造**真实但易错**的任务分层，让数字有冲击力。
4. **"现有 benchmark 测不出"的正面证明**：取一个现有 benchmark（如 MatPlotBench）的若干样本，证明其指标对 silent error 全过、而执行追踪检出——直接打脸现有评测。

---

## 5. 诚实风险

- **最大风险**：万一强 LLM 的真实 silent error 率其实很低（它们生成确实强），警钟就不响,论文降级为"我们补了个评测维度"(solid 但非 oral)。**必须先快速测一批真实任务确认 silent error 率到底多高**——这是 go/no-go 的关键前置实验。
- **样本代表性**：真实数据自洽过滤会偏向易对齐的 sheet,可能低估也可能高估错误率,要诚实界定测量范围。
- **vs VisEval 的区分**：必须强调"测量"定位 + "执行追踪是唯一够格的尺子"(SVG 不够),否则被归为 VisEval 增量。

---

## 6. go/no-go 前置实验（最优先）

**在投入扩规模前，先回答：强 LLM 在真实复杂绘图任务上的 silent error 率到底有多高？**
- 快速跑：30-50 个跨文章真实任务 × (GPT-4o/Claude) 一次性生成 × 执行追踪 oracle。
- 若 silent error 率（尤其多系列/双轴/真实列名）显著 > 0（比如 >15%）→ 警钟成立,路线 A 可行,投入扩规模。
- 若 < 5% → 警钟不响,回退到"判官方法论文"(已 READY 8.5)或换路线。
