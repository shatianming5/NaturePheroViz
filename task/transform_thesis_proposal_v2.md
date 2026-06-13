# Thesis v2:执行追踪 + 类型化算子语义契约,无 gold 检测 LLM 数据变换的 silent 语义错

> 目标顶会 Oral。本版相对 round-0 的关键升级:**所有前提与方法主张都已被自家 48 类网格 + 真实 Nature 数据切片实验证实**(非臆测),并据 round-1/round-2(GPT-5.4,核 24+ 篇相关工作,6.9→7.5 REVISE)逐条收紧。
>
> **一句话(每个词都 load-bearing,措辞已据 round-2 收窄)**:我们是**首个用类型化算子级关系语义契约**(typed operator-level relational semantic contracts)检测 LLM 生成的 NL→DataFrame 变换的 silent 语义错、**无需 gold 输出 / 预写测试 / 可信参考实现**的方法。**不主张**"首个 oracle-free 代码检测"(CodeT、Incoherence 在先);load-bearing 的是 (typed 算子契约)×(NL→DataFrame 域)×(无 gold/测试/参考)这一交集。抓的是 exec-pass 测不出、单元测试覆盖不到、人眼看不出的 **silent semantic error**。

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
- **因果隔离(round-2 P0,已补)**:reviewer 质疑"单条作者澄清 = prompt 设计 artifact"。补做 6 个高危类 × **3 条独立澄清**(同意图、不同措辞):模糊 **92%** → 三条澄清各 **17% / 8% / 8%**(均值 11%,**跨措辞 std 仅 3.9 个百分点**)。下降在每条独立措辞下都成立、方差极低 ⇒ 效应来自**意图被明确**,非单一措辞偶然。per-op 揭示诚实结构:pct_point/dedup/topn/within_group 三条澄清**全部归零**;**count_includes_empty 三条澄清都仍 1/2 错**——含空类计数是无论怎么措辞都修不掉的真顽固盲区。

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

### 2.4 契约可扩展性:回答"手写 12 条不 scalable"(round-2 P0)

reviewer 必问:"换个算子怎么办?手写契约不可扩展。"三层回应:

1. **契约不是 per-task,是 per-operator-semantic-class**。12 条覆盖的是**算子语义类**(加权/组内/百分点/去重粒度/join how/NaN/并列/累计…),不是 12 个具体任务。pandas 的高频歧义算子是**有限且可枚举**的(groupby-agg、merge、pivot、rank、cumsum、fillna 等核心几十个),不是开放集。一次写好覆盖一个语义家族,跨无数具体任务复用——48 网格 + 9 真实表共 57 个不同任务,只用了这 12 条。
2. **半自动抽取路径**(降低边际成本):不变量可从 **pandas API 的类型签名 + 关系代数语义**半自动派生——`groupby.agg` 的输出基数关系、`merge(how=)` 的行数上下界、`rank(method=)` 的并列语义,都是 API 文档里**确定性**的关系性质,可模板化生成契约骨架,人只需确认。这把"为每个算子手写"降为"为每个算子family审一次"。
3. **缺契约时安全退化 = abstain,不乱报**(最关键的诚实点):覆盖边界外的算子,系统**显式弃权**(报告"无契约,不判定"),而非强行套不匹配的契约误报。这保证 **FP 不随覆盖率下降而升**——宁可漏报未覆盖算子,不可在覆盖内误报。论文据此诚实界定:本方法的主张范围 = "已建契约的算子语义类上 100% recall / 0% FP",未覆盖类透明标注 abstain 率。

> 这把"覆盖率 vs 精度"从隐患转成**可量化的覆盖表 + abstain 率**,reviewer 要的不是"覆盖全宇宙",而是"边界诚实 + 边界内可靠 + 边界可扩"。

---

## 3. 决定性实验(claim-driven;括号内为已得 / 待补)

1. **silent-error benchmark(已得)**:48 类网格,模糊 silent 率 46%、分层双峰。**第一个 silent-transform-error benchmark**,本身是领域贡献。
2. **歧义校准(已得)**:模糊 46% → 澄清 12%,证明是模型失败而非任务欠定义。
3. **检出 head-to-head(已得,同表对照)**:48 网格同一批 LLM 产物上 5 个检测器并排。

   > **数源说明(避免与 §1 校准混淆)**:这是一次**独立的 baseline run**(为给 consistency 检测器额外生成 K=3 实现而重跑),产出 **189 个 exec-ok 结果(57 silent / 132 correct)**——与 §1.1/§7 校准 run 的 192 次(135 correct + 56 silent + 1 crash)是**两次独立生成**,温度 0 下因 LLM 抽样仍有自然抖动(56↔57 silent),各自内部自洽,不应跨表相加。论文终稿会用**同一次** run 同时驱动校准与 baseline,合并为一张 master 账目表。

   同一批产物(57 silent / 132 correct),5 检测器:

   | 检测器 | recall(真错上报警) | FP(正确上误报) |
   |---|---|---|
   | **ours(invariants 契约)** | **57/57 = 100%** | **0/132 = 0%** |
   | exec-pass(代码跑通) | 0/57 = 0% | 0% |
   | output-validity(形状/值域) | 0/57 = 0% | 0% |
   | LLM-self-check(同模型自查) | 35/57 = 61% | **53/132 = 40%** |
   | consistency(CodeT 式 K=3 一致) | 0/57 = 0% | 0% |

   - **exec-pass / validity / consistency 全 0 检出**:现有"能跑/形状对/多次一致"对 silent 语义错零效。
   - **consistency 0% 是 common-mode 铁证**:57 个 silent 里 3 次独立生成都一致地错,投票一个没抓。
   - **self-check 61% recall 但 40% FP**:LLM 自查既漏近 4 成真错、又把 4 成正确误判——不可用作判官。
   - **ours 100%/0%** 唯一可靠。这就是"显著优于现有手段"的硬证据(round-2 唯一 CRITICAL)。
4. **必要性消融(待补)**:证明"无 gold output"下仍能检出(否则退化成 text2SQL)。
5. **外部效度(已得)**:9 张真实 Nature 源数据表(6 篇、跨学科、真实科学列名)做 held-out 切片,**模糊 silent 72%(比合成 46% 更高)、oracle recall 100% / FP 0%**——现象在真实数据上更严重、oracle 零退化(详见 §1.3)。

---

## 4. 对 novelty 边界的实证反驳(round-1 四条 + round-2 新增一条)

round-1 结论:novelty 真实但三条边界 razor-thin;round-2 联网复核**四条边界全部 SURVIVES**,但新增一个更近的邻居 Incoherence(AAAI 2026)。五维矩阵(无 gold / 无预写测试 / pandas / 语义保真 / 算子级归因)无单篇覆盖全部;最近威胁是 SemGuard × mlinspect 的交集(不存在于单篇)。逐条:

| 威胁 | reviewer 的问 | 本提案的实证反驳 |
|---|---|---|
| **CodeT / 生成测试** | "为何不让 LLM 生成测试代替 gold?" | common-mode 已实测:两模型在 5 个算子类上**一致犯同一 silent 错**;CodeT 的双执行一致性会让多个错误实现互相通过(同表 baseline 实测 consistency 在这些类上漏检)。生成测试对 wrong-groupby-key / inner-vs-left-join 判别力极低。 |
| **SemGuard(ASE25,无测试测语义错)** | "已能无测试测语义错" | SemGuard 是**行级、算法代码**(decoding-time 监督),无 DataFrame schema / join / 聚合 / 数据依赖语义概念。`df[df.a>0]` vs `df[df.a>=0]` 它标不出(它不理解列 `a` 在管线里的语义角色);我们的 topn/pct_point/dedup 契约能(48 类 recall 100%)。 |
| **Zhong-2020(goldless SQL 检查)** | "已做 goldless SQL" | Zhong 仍需 **gold query** 既建测试库又评分;SQL 有干净集/包语义,pandas 是有状态、数据依赖的。无类似"pandas 等价类"理论——我们用 invariants 替代。 |
| **mlinspect(算子级检查)** | "已做算子级" | mlinspect 检测既有(假定正确)管线的**数据分布**异常(偏差/泄漏),**不判代码是否实现 NL 意图**——它说不出 `merge(on=customer_id)` 本该是 `order_id`。我们做的是 intent-faithfulness。 |
| **Incoherence(AAAI 2026,arXiv 2507.00057,round-2 新增)** | "已有 oracle-less 错误检测" | Incoherence 在**通用算法代码**(HumanEval/MBPP)上给 oracle-free 错误下界,**检出约 2/3、漏 1/3**;无 DataFrame/关系语义、不针对 common-mode。我们:域=DataFrame、机制=typed 算子契约(非行为分歧下界)、检出=48 网格 + 真实切片均 100%。 |

**最强主张(每词 load-bearing,措辞已据 round-2 收窄)**:我们是**首个**用**类型化算子级关系语义契约**检测 **NL→DataFrame 变换**的 silent 语义错、**无需 gold 输出 / 预写测试 / 可信参考实现**的方法——**不是**"首个 oracle-free 代码检测"(CodeT/Incoherence 在先),而是首个把 typed operator-contract 用于此特定设定。差异点 = (无 gold)×(无预写测试)×(pandas DataFrame)×(silent 语义)×(typed 算子归因),每一维都有 48 类网格 + 真实切片的数字背书。

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

**已解决(round-2 → 现在,5 个 P0 全清)**:
- ✅ **baseline 同表对照(原唯一 CRITICAL)**:5 检测器并排,ours 100%/0% vs exec-pass/validity/consistency 全 0 recall、self-check 61%/40%——"显著优于现有手段"已实测(§3.3)。
- ✅ **外部效度**:9 张真实 Nature 表 held-out 切片,模糊 silent 72%、oracle 100%/0%(§1.3)。
- ✅ **账目透明**:192 全账混淆矩阵(135 正确 + 56 silent + 1 crash),堵掉 round-2 的"135 vs 136"疑点。
- ✅ **契约可扩展性**:per-operator-class 非 per-task、半自动从 API 签名派生、缺契约 abstain(§2.4)。
- ✅ **related work 边界 + Incoherence**:§4 加第五条边界,SemGuard 行级 vs 关系型语义讲死;"first"措辞收窄。
- ✅ **歧义校准因果隔离**:6 高危类 × 3 独立澄清,92%→11%(std 3.9 pts);weighted_mean 反转已诚实讨论(§1.2)。

**距 Oral 仅剩(非 P0,锦上添花)**:
1. **必要性消融**(§3.4)——形式化证明"无 gold"下仍检出(否则退化 text2SQL)。这是论文写作时的标准消融,机制已就位。
2. **更大规模 / 更多模型**——现 2 模型,可加开源(Qwen-Coder)证明 silent error 普遍性;benchmark 可从 48 扩到 100+。
3. **typed 归因准确率量化**——契约已分类,补一个归因正确率数字。
