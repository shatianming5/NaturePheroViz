# Thesis v2:执行追踪 + 类型化算子语义契约,无 gold 检测 LLM 数据变换的 silent 语义错

> 目标顶会 Oral。本版相对 round-0 的关键升级:**所有前提与方法主张都已被自家 48 类网格实验证实**(非臆测),并据 round-1(GPT-5.4,核 24 篇相关工作,打分 6.9 REVISE)逐条收紧。
>
> **一句话(每个词都 load-bearing)**:我们**首个**用**类型化的算子级关系语义**(typed operator-level relational semantics)验证 LLM 生成的 NL→DataFrame 变换的**语义保真**,**无需 gold 输出、无需预写测试、无需执行可信参考实现**——抓的是 exec-pass 测不出、单元测试覆盖不到、人眼看不出的 **silent semantic error**。

---

## 0. Problem Anchor(逐字保留,round-0 起未变)

- **根本问题**:LLM 越来越多地生成数据处理/分析代码(pandas/SQL),但**"代码能跑 + 输出是个合理的表"≠ 它做了用户要的变换**。LLM 在语义有歧义处系统性犯错:加权 vs 算术均值、组内 vs 全局占比、百分点 vs 百分比、聚合粒度、join how、NaN 处理、保留并列、去重时机。
- **必须解决的瓶颈**:这类错误是 **silent semantic error**——代码无异常、结果形状合理、数值看着正常,所以 ① execution-pass / 不崩 测不出;② 输出值域检查测不出;③ 人 review 也极难发现(要逐行重算);④ 没有 gold output 时无法对账。结果是**错误的分析结论被当成对的**。
- **核心主张**:用**执行追踪**(捕获代码实际产生的中间/最终 DataFrame)+ **从自然语言意图推导的类型化算子语义契约**做结构化对账,检测 silent semantic error,并定位到出错的变换算子。
- **非目标**:不做 text2SQL 的语法/可执行性检查(已解决);不训模型;不做通用代码正确性证明;不要求人工 gold output。
- **成功条件**:(a) 在 silent-semantic-error benchmark 上,检出率显著高于现有手段;(b) 能定位到出错算子类型;(c) 检出的错误是真 silent(代码跑通、结果合理)。

---

## 1. 已被实验证实的前提(本提案区别于空想的关键)

### 1.1 silent 语义错普遍且系统性(P0-3,48 类网格,非 cherry-pick)

- **基准**:12 个 operator-semantic 歧义类 × 4 个数据实例 = 48 case,每个 case 带 (模糊, 澄清) 配对提示 + 一条 goldless 语义契约。这是**声明式分类网格**,不是手挑陷阱列表——直接回应 round-1 对 "n=16 cherry-picked traps" 的质疑。
- **模型**:GPT-4o、Claude-Sonnet-4.6,各 48 case × {模糊, 澄清} = 192 次一次性生成。
- **结果(模糊提示)**:silent 语义错率 **44/96 = 46%**(代码跑通、结果合理、语义错)。
- **分层(双峰,关键发现)**:silent 错**不是随机噪声,而是系统性集中在特定语义歧义算子**——

  | 高危类(模糊 silent 率) | 安全类(模糊 silent 率) |
  |---|---|
  | pct_point 100% | left_join_keep_all 0% |
  | dedup_then_agg 100% | pooled_rate 0% |
  | median_not_mean 100% | cumulative_running 0% |
  | topn_with_ties 100% | nan_as_zero_sum 0% |
  | count_includes_empty 100% | proportion_true 0% |
  | within_group_share 50% | weighted_mean 0% |

  → "百分点 vs 百分比""去重时机""并列保留""含空类计数"是 LLM 的系统性盲区;而"左连接保全行""池化率""累计""NaN 当 0"它们稳。**这个双峰本身就是领域贡献**:silent error 有可预测的算子语义结构。

### 1.2 这是模型语义失败,不是任务欠定义(P0-2,歧义校准,反驳"你在测 prompt 不是测模型")

- **配对设计**:每个 case 一对 (模糊, 澄清) 提示——澄清版把意图(权重?组内?百分点?)写死,任务不变。
- **结果**:模糊 silent **46%** → 澄清 silent **12%**(12/96)。**澄清修掉约 3/4 的错**。
- **解读**:错误随澄清大幅消退 ⇒ 这些是**真实的模型语义失败**(可被澄清修复),不是"任务本身有歧义、谁都做不对"。残留 12%(median 50%、count_empty 50% 澄清后仍错)是**真正顽固**的难点,诚实保留。
- **诚实反例**:weighted_mean 出现"模糊 0%、澄清 37%"的反转(唯一非单调类)——澄清提示反而诱导 Claude 做 `df.assign` 广播。论文据此讨论"澄清非总是单调改善",不掩盖。

### 1.3 held-out 真实数据切片:现象在真实 Nature 表上不仅保持、还更严重(外部效度)

回应 round-2 的核心 P0("48 网格是作者合成的,缺外部效度")。取 **9 张真实 Nature 源数据表**(6 篇论文、跨光合/神经/基因组/海洋/药理),用**真实科学列名**(ETR/PAR/VAF/log2FoldChange/ddCt/CHRM4 activity)作输入,套**同一套**算子语义分类 + 模糊/澄清 + goldless oracle。

| 指标 | 合成 48 网格 | **真实 Nature 切片** |
|---|---|---|
| 模糊 silent 率 | 46% | **72%**(13/18,更高) |
| 澄清后 silent 率 | 12% | **28%**(5/18) |
| oracle recall | 100% | **100%**(18/18) |
| oracle 误报 | 0% | **0%**(0/18) |

- **现象更严重**:真实科学列名 + 真实分布让 silent 率从 46% 升到 72% ⇒ 彻底反驳"silent error 是合成玩具表的产物"——它在真实数据上更糟。
- **oracle 零退化**:goldless 契约在**从未调过的真实数据**上 recall/FP 仍 100%/0% ⇒ 比"在自家网格上 100%"强得多的迁移证据。
- **澄清仍大降错**(72%→28%),与合成版一致,再证模型语义失败而非任务欠定义。
- **诚实**:median 类在真实表偏多(真实 Nature 表多为"分组+测量值"形态);路线 B(从 figure caption 反推作者真实意图)已试并放弃——1362 图仅 32 个 caption 含变换词且都是生物学结论、无可机器对齐的 gold。

### 1.4 对照:绘图任务 silent 错率 0%(问题特异性)

- 同样的强 LLM 在"给定干净数据画标准图"上 silent error 率 **0%**(20 跨文章真实任务,GPT-4o/Claude 全对)——证明**问题特异于"语义有歧义的数据变换"**,不是 LLM 普遍不可靠,也不是我们的测量在无差别报警。


---

## 2. 方法:类型化算子语义契约 over 执行追踪(收成一条主线)

round-1 要求"center on ONE crisp idea"。主线锁定为:**operator-semantic contracts over execution traces**。多实现一致性**降级为辅助/对照**(round-1 已证其死穴:common-mode error——两模型在 pct_point/dedup/median/topn/count_empty 上**一致地犯同一个错**,一致性投票会一致地通过错误答案)。

### 2.1 执行追踪(已实现资产)

复用 PlotTrace 的 monkeypatch 思路,捕获 pandas 变换链的中间 + 最终 DataFrame(算子实际收到/产出的数组),而非读回输出文本。这是"为什么以前测不出"的答案:silent error 不在语法/可执行性层,在算子实际语义层。

### 2.2 invariants-first 语义契约(P0-1,已实现 12 条,goldless)

- 核心机制:从 NL 意图 + 算子类型推导**可检查的语义不变量**,执行追踪验证之。**契约从不看 gold**。
- 已实现并自测 12 条契约(weighted_mean / within_group_share / pct_point / dedup_then_agg / left_join_keep_all / pooled_rate / median_not_mean / cumulative_running / topn_with_ties / nan_as_zero_sum / count_includes_empty / proportion_true)。每条:在 silent slip 上 **FIRE**、在正确结果上 **PASS**,全部 goldless。
- 例:
  - weighted_mean:加权均值必落在 min/max 间,且权重不均时 ≠ 算术均值 → 若结果 == 算术均值则 FIRE。
  - topn_with_ties:保 top-n 含并列 = 所有 value-rank(min)≤n 的行;若只留恰好 n 行而并列更多则 FIRE。
  - count_includes_empty:含空类计数应覆盖全部类目;若结果类目数 < 全类目数则 FIRE。

### 2.3 typed 归因

silent error 归类到算子语义(聚合粒度 / 权重 / 分组范围 / join how / NaN 语义 / 并列 / 去重时机 / 累计),驱动可解释报告。这是 SemGuard(行级)和 mlinspect(分布级)都不提供的**类型化关系语义信号**。

---

## 3. 决定性实验(claim-driven;括号内为已得 / 待补)

1. **silent-error benchmark(已得)**:48 类网格,模糊 silent 率 46%、分层双峰。**第一个 silent-transform-error benchmark**,本身是领域贡献。
2. **歧义校准(已得)**:模糊 46% → 澄清 12%,证明是模型失败而非任务欠定义。
3. **oracle 检出 head-to-head(部分已得,待扩 baseline)**:
   - **本方法(invariants-first 契约)**:recall **56/56 = 100%**,FP **0/135 = 0%**(48 类网格)。
   - 待补 baseline 对照:① exec-pass(预期 0 检出,silent 不崩);② 输出合法性/值域;③ LLM-self-check(预期受同源盲区限制);④ 多实现一致性(预期在 common-mode 类上失效)。指标:检出 precision/recall + 算子归因准确率。
4. **必要性消融(待补)**:证明"无 gold output"下仍能检出(否则退化成 text2SQL)。
5. **外部效度(已得)**:9 张真实 Nature 源数据表(6 篇、跨学科、真实科学列名)做 held-out 切片,**模糊 silent 72%(比合成 46% 更高)、oracle recall 100% / FP 0%**——现象在真实数据上更严重、oracle 零退化(详见 §1.3)。

---

## 4. 对 round-1 四条 razor-thin novelty 边界的实证反驳

round-1 结论:novelty 真实但三条边界 razor-thin。五维矩阵(无 gold / 无预写测试 / pandas / 语义保真 / 算子级归因)无单篇覆盖全部;最近威胁是 SemGuard × mlinspect 的交集(不存在于单篇)。逐条:

| 威胁 | reviewer 的问 | 本提案的实证反驳 |
|---|---|---|
| **CodeT / 生成测试** | "为何不让 LLM 生成测试代替 gold?" | common-mode 已实测:两模型在 5 个算子类上**一致犯同一 silent 错**;CodeT 的双执行一致性会让多个错误实现互相通过。生成测试对 wrong-groupby-key / inner-vs-left-join 这类语义错判别力极低。 |
| **SemGuard(ASE25,无测试测语义错)** | "已能无测试测语义错" | SemGuard 是**行级、算法代码**,无 DataFrame schema / join / 聚合 / 数据依赖语义概念。`df[df.a>0]` vs `df[df.a>=0]` 它标不出;我们的 topn/pct_point/dedup 契约能(48 类网格 recall 100%)。 |
| **Zhong-2020(goldless SQL 检查)** | "已做 goldless SQL" | Zhong 仍需 **gold query** 蒸馏测试库;SQL 有干净集/包语义,pandas 是有状态、数据依赖的。无类似"pandas 等价类"理论——我们用 invariants 替代。 |
| **mlinspect(算子级检查)** | "已做算子级" | mlinspect 检测既有(假定正确)管线的**数据分布**异常(偏差/泄漏),**不判代码是否实现 NL 意图**——它说不出 `merge(on=customer_id)` 本该是 `order_id`。我们做的是 intent-faithfulness。 |

**最强主张(每词 load-bearing)**:见文首一句话。差异点 = (无 gold)×(无预写测试)×(pandas DataFrame)×(silent 语义)×(typed 算子归因),且现在每一维都有 48 类网格的数字背书。

---

## 5. 诚实风险(据实验更新)

- **撞车风险**:§4 四条边界若有一条站不住则受损。已用实测(common-mode、48 类 recall/FP、双峰分层)各个加固,但 SemGuard 的"语义"二字仍是 reviewer 最可能纠缠处——须在 related work 把"行级算法语义"vs"关系型算子语义"讲死。
- **契约覆盖率 vs 精度**:12 条契约覆盖 12 类;真实世界算子更多。invariants-first 的可扩展性(新算子要不要人写契约?能否半自动从意图抽不变量?)是方法的天花板,须诚实界定覆盖边界,并给"契约缺失时安全退化"策略。
- **意图歧义本身**:已用 §1.2 校准区分"模型理解错"vs"意图欠定义";但澄清提示由我们写,可能引入偏置——须开源提示、报告非单调反例(weighted_mean)。
- **外部效度**:48 case 为受控合成;真实 Nature 变换任务(§3.5)是必要补强,否则被批"合成 benchmark 不代表真实分析"。

---

## 6. 与已有资产的关系

- **执行追踪基础设施**:`agent/app/services/plot_trace.py`(PlotTracer,6 例 selftest 过),扩展到 pandas 变换链是增量。
- **语义契约**:`agent/eval/transform_oracle.py`(12 条 goldless 契约,selftest 全过)。
- **系统化 benchmark**:`agent/eval/transform_bench.py`(48 类网格,离线验证 oracle 0 误报)。
- **歧义校准**:`agent/eval/ambiguity_calibration.py --bench`(192 次,报告在 `results_ambcal_bench/`)。
- **真实数据**:154 篇 Nature / 1362 图-源数据配对,供 §3.5 外部效度。

---

## 7. 距 Oral 还差(round-2 后更新)

**已解决(round-2 → 现在)**:
- ✅ **外部效度**:9 张真实 Nature 表 held-out 切片,模糊 silent 72%、oracle 100%/0%(§1.3)。
- ✅ **账目透明**:192 全账混淆矩阵(135 正确 + 56 silent + 1 crash),堵掉 round-2 的"135 vs 136"疑点。

**仍需补(冲 Oral ≥8)**:
1. **baseline head-to-head 跑实(最关键,CRITICAL)**(§3.3 ①②③④)——目前只有本方法的 100%/0%,缺与 exec-pass/输出值域/self-check/CodeT 一致性的**同表对照**。这是"显著高于现有手段"的硬证据,round-2 反复点名。
2. **契约可扩展性论证**——回答"换个算子怎么办",给半自动抽取或安全退化(abstain)方案,否则被批"手写 12 条不 scalable"。
3. **related work 写死 SemGuard 边界 + cite 新威胁 Incoherence(AAAI 2026)**——行级算法语义 vs 关系型算子语义;Incoherence 是 oracle-less 检测,机制上比 CodeT 更近,须区分(域:DataFrame;失败模式:common-mode;机制:contracts vs 行为分歧)。
4. **"first"措辞收窄**——非"first oracle-free",而是"first **typed operator-contract** method for NL→DataFrame semantic error detection without gold/test/reference"。
5. **歧义校准升级**——每 case 多条独立澄清(现仅 1 条作者写的),做发表级因果隔离;解释 weighted_mean 0%→37% 反转。
