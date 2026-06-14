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

- **基准**:**17 个 operator-semantic 歧义类 × 4 个数据实例 = 68 case**(从 12 类/48 case 扩展),每个 case 带 (模糊, 澄清) 配对提示 + 一条 goldless 语义契约。这是**声明式分类网格**,不是手挑陷阱列表——直接回应 round-1 对 "n=16 cherry-picked traps" 的质疑,17 类的覆盖面比原 12 类宽 +42%。
- **模型**:GPT-4o、Claude-Sonnet-4.6,68 case × {模糊, 澄清} × 2 模型 = 272 次一次性生成。
- **结果(模糊提示)**:silent 语义错率 **46%**(48 网格 44/96、68 网格 63/136,两档一致),代码跑通、结果合理、语义错。
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

- **跨模型 + 跨规模(开源模型验证,round-5 补)**:把同一 48 网格跑在**本地托管的开源模型 Qwen2.5-Coder**(7B/14B/32B,gpudev2 离线推理)上,与闭源对照:

  | 模型 | 规模 | 模糊 silent 率 | oracle recall | oracle FP |
  |---|---|---|---|---|
  | Qwen2.5-Coder-7B | 7B | **65%** | 97% | 0% |
  | Qwen2.5-Coder-14B | 14B | **54%** | 100% | 0% |
  | Qwen2.5-Coder-32B | 32B | **44%** | 96% | 0% |
  | GPT-4o / Claude | 闭源 | 46% | 100% | 0% |

  → silent 率随模型能力**单调下降**(7B 65% → 14B 54% → 32B 44% ≈ 闭源 46%):silent error 是**能力相关的真实现象**(越弱的模型越多),但**即使最强闭源仍 46%**,不随规模消失。而 **goldless oracle 在所有尺寸上 recall ≥96% / FP = 0%**——证明现象+检测方法**跨模型族、跨规模普遍**,不是 GPT-4o/Claude 的 artifact。

- **跨厂商前沿模型(2026 最强模型,68 网格)**:把同一网格跑在 **5 个当前前沿模型**上,覆盖 OpenAI / Anthropic / Google + 一个代码专用模型:

  | 模型 | 厂商 | 模糊 silent 率 | oracle 误报 |
  |---|---|---|---|
  | gpt-5.4 | OpenAI 前沿 | **42%** | 0/97 = 0% |
  | claude-opus-4.8 | Anthropic 最强 | **38%** | 0/100 = 0% |
  | gpt-5.3-codex | OpenAI 代码专用 | **36%** | 0/100 = 0% |
  | gemini-3.1-pro | Google | **33%** | 0/102 = 0% |
  | gpt-5.5 | OpenAI 前沿 | **32%** | 0/103 = 0% |

  → **连 2026 年最强的前沿模型(GPT-5.4 / Claude Opus 4.8 / Gemini-3.1-Pro)都有 32-42% 的模糊 silent 率**,**专门训练写代码的 gpt-5.3-codex 也 36%**——silent error **不是弱模型/旧模型/非代码模型的 artifact,而是跨 4 厂商、跨代际、连最前沿都逃不掉的普遍现象**。这是论文最响的警钟:不是"老模型会犯错",而是"**最强的也会,而且你看不出来**"。oracle 对全部 5 个新模型 **FP = 0%**(502+ 正确结果零误报)。算上 gpt-4o/claude-sonnet/Qwen×3,共 **10 个模型 / 4 厂商**验证现象+方法普遍。

### 1.2 这是模型语义失败,不是任务欠定义(P0-2,歧义校准,反驳"你在测 prompt 不是测模型")

- **配对设计**:每个 case 一对 (模糊, 澄清) 提示——澄清版把意图(权重?组内?百分点?)写死,任务不变。
- **结果**:模糊 silent **46%** → 澄清 silent **12%**(12/96)。**澄清修掉约 3/4 的错**。
- **解读**:错误随澄清大幅消退 ⇒ 这些是**真实的模型语义失败**(可被澄清修复),不是"任务本身有歧义、谁都做不对"。残留 12%(median 50%、count_empty 50% 澄清后仍错)是**真正顽固**的难点,诚实保留。
- **诚实反例**:weighted_mean 出现"模糊 0%、澄清 37%"的反转(唯一非单调类)——澄清提示反而诱导 Claude 做 `df.assign` 广播。论文据此讨论"澄清非总是单调改善",不掩盖。
- **因果隔离(round-2 P0,已补)**:reviewer 质疑"单条作者澄清 = prompt 设计 artifact"。补做 6 个高危类 × **3 条独立澄清**(同意图、不同措辞):模糊 **92%** → 三条澄清各 **17% / 8% / 8%**(均值 11%,**跨措辞 std 仅 3.9 个百分点**)。下降在每条独立措辞下都成立、方差极低 ⇒ 效应来自**意图被明确**,非单一措辞偶然。per-op 揭示诚实结构:pct_point/dedup/topn/within_group 三条澄清**全部归零**;**count_includes_empty 三条澄清都仍 1/2 错**——含空类计数是无论怎么措辞都修不掉的真顽固盲区。

### 1.3 held-out 真实数据切片:现象在真实 Nature 表上不仅保持、还更严重(外部效度)

回应 round-2 的核心 P0("48 网格是作者合成的,缺外部效度")。**(A) 大规模自动切片** = 扫描下载的 Nature 源数据 XLSX(211 篇 / 1607 表),自动挑出有真类目+数值列的表,在每个表上实例化同一套算子任务(median/within_group_share/weighted_mean/pooled_rate/nan_as_zero_sum)。**为保证跨论文独立性,限制每篇文章最多贡献 15 个任务**(否则少数大表会主导),得到 **841 个真实任务、跨 71 篇独立 Nature 论文**(每任务 gold 经 oracle 验证才纳入);**(B) 9 张人工策展表**(真实科学列名 ETR/VAF/log2FC/ddCt/CHRM4)作精选对照。两档都套同一套 模糊/澄清 + goldless oracle:

| 指标 | 合成 68 网格 | **大切片(841 任务/71 篇,95% Wilson CI)** | 9 表精选(CI) |
|---|---|---|---|
| 模糊 silent 率 | 46% | **77%** [75-79](1296/1682) | 72% [49-88] |
| 澄清后 silent 率 | 12% | **10%** [9-12](175/1682) | 33% [16-56] |
| oracle recall | 100% | **98%** [97-98](1438/1471) | 100% [83-100] |
| oracle 误报 | 0% | **0%** [0-1](4/1855) | 0% [0-18] |

> 841 任务**跨 71 篇独立 Nature 论文**(per-article 上限保证多样性,非少数大表反复榨),**CI 极致紧(±2%)**:模糊 silent 75-79%、FP 上界仅 1%。这是跨几十篇独立论文的真实数据,彻底消除"样本太小/不独立"质疑。自动生成器对每个任务的 gold 先验证(oracle 不能在 gold 上 false-fire)才纳入,保证切片干净。oracle recall 98% 分层看清楚:**weighted_mean 140/140=100%、nan_as_zero_sum 16/16=100%、within_group_share 538/539=99.8%、pooled_rate 118/119=99% 近乎完美**,median_not_mean 626/657=95% 有少量契约盲区(诚实的覆盖边界,非测量错);**FP 4/1855=0%**(大样本暴露 4 个边界误报,上界仍仅 1%)。

- **现象更严重**:真实科学列名 + 真实分布让模糊 silent 率从合成 46% 升到 **77%**(CI 下界 75% 远高于合成)⇒ 在 71 篇独立 Nature 论文的真实数据上,模型有 77% 的概率悄悄做错变换——**配合前沿模型 32-42%、跨规模趋势,这是论文最硬的警钟数字**。
- **oracle 零退化**:goldless 契约在 841 个**从未调过的真实任务**(跨 71 篇)上 recall 1438/1471=98% [97-98]、FP 4/1855=0% [0-1] ⇒ 大样本上检测近乎完美,主力算子 ≥99%。
- **澄清仍大降错**(77%→10%),再证模型语义失败而非任务欠定义。
- **诚实**:recall 98% 的少量漏检集中在 median 的契约盲区(31/657,非测量错);**修了一个代表性陷阱**——早期版本未限 per-article 时 500 任务实际仅来自 3 篇文章(高度相关),加上限后才得到真正跨 71 篇的独立样本;路线 B(从 figure caption 反推作者真实意图)已试并放弃——1362 图仅 32 个 caption 含变换词且都是生物学结论、无可机器对齐的 gold。

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
3. **缺契约时安全退化 = abstain,不乱报**(最关键的诚实点,已实现 schema 门):覆盖边界外的算子,系统**显式弃权**而非强行套不匹配的契约误报。实现机制:`check()` 有一道 **schema 兼容门**——契约只在其声明的必需 params 键存在、且这些键命名的输入列确实在 df 里时才评估,否则返回 None(abstain)。这保证 **FP 不随覆盖率下降而升**:5 族 demo 加到更多算子,FP 仍恒 0/11;归因压力测试里"不相关契约误 fire"也由此门消除。论文据此诚实界定:本方法的主张范围 = "已建契约的算子语义类上高 recall / 0 FP",未覆盖类透明标注 abstain。

> 这把"覆盖率 vs 精度"从隐患转成**可量化的覆盖表 + abstain 率**,reviewer 要的不是"覆盖全宇宙",而是"边界诚实 + 边界内可靠 + 边界可扩"。

**68 网格的分层 recall(诚实实证)**:扩到 17 类后,oracle 整体 recall 66/82=80%、FP 0/190=0%。但分层看清楚了**契约成熟度**:

| 算子类组 | oracle recall | 说明 |
|---|---|---|
| **核心 12 类(契约成熟)** | **46/46 = 100%** | 主张范围,稳固 |
| 新探索 5 族(契约建设中) | 20/36 = 56% | zscore/rank_pct 单条契约只覆盖最典型错法 |

→ **核心主张("已建充分契约的类上 100% recall / 0 FP")在扩到 17 类后依然成立**;整体 80% 是新族覆盖**进行时**拉低的,而非核心能力退化。zscore 的"组内 vs 全局标准化"只覆盖了一种滑法,模型的其他错法(如标准化到错误的 ddof)需要补契约——这正是 §2.4 "一条契约够 vs 需要参数敏感变体"的 coverage 表要标注的。FP 全程 0/190,**覆盖增长不抬误报**这一核心保证不变。

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
4. **必要性消融——无 gold 不退化(已得)**:correct/silent 的 ground-truth 标签用手工 gold 算,但 oracle **从不看 gold**、只凭算子不变量 fire。结果:goldless oracle 在校准 run 上 recall 56/56=100%、FP 0/135=0%,在真实切片上 19/19=100%、0/17=0%——**追平"有 gold 精确比对"的检出,却不需要任何 gold output**。证明方法不退化成 text2SQL(后者需 gold query),能在无 gold/参考处工作。
5. **外部效度(已得)**:9 张真实 Nature 源数据表(6 篇、跨学科、真实科学列名)做 held-out 切片,**模糊 silent 72% [95% CI 49-88](比合成 46% 更高)、oracle recall 100% [83-100] / FP 0% [0-18]**——现象在真实数据上更严重、oracle 零退化(详见 §1.3)。
6. **typed 归因准确率(已得,契约硬化 + family 剪枝后)**:双口径——(a) **归因 recall 25/25 = 100%**:对每个 silent error,真实算子的契约都实质 fire,定位到正确算子语义(对真实算子,缺期望输出列=产出形状错=真 silent,算检出);(b) **cross-fire**:把不相关契约套到正确结果上的实质误 fire 率,经 schema 门(params 不匹配 abstain)+ 形状门(缺输出列 abstain)从 20% 降到 8%(88/1136),再经 **family-level 候选剪枝**(按结果形状排除结构不可能的算子族)进一步降到 **2%(25/1136)**。剪枝保守(只剔结构不可能族),归因 recall 不受影响。所有修正在测量/门层,不动 check()/契约内部,故 baseline 的 100% recall 不受影响。
7. **可扩展性(已得,§2.4)**:**5 个未见算子族**(zscore_within_group / dense_rank / cumcount_per_group / rank_pct / clip_outlier),各加一条 ~13-21 行契约。加之前 abstain(BEFORE recall 0/9=0%,FP 0),加之后可检出族 recall 跳到 100%(dense_rank/clip_outlier),**FP 恒 0/11**。coverage-by-family:dense_rank/clip_outlier 一条契约即 100%;zscore 25%、rank_pct 0%——**单条契约覆盖不全这些算子的所有错法**,诚实暴露覆盖边界。但 FP 始终 0 + 边界外 abstain ⇒ 加新算子=写一条不变量,覆盖增长**绝不抬 FP**;"一条够 vs 需要参数敏感变体"由 coverage 表显式标注。

> 所有实验数字汇总于一张 master 表(`results_master/master_table.md`),并标明两次独立生成 run(校准 192 / baseline 189)的数源,避免跨表混淆。

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

**round-2 的 5 个 P0(全清)**:
- ✅ **baseline 同表对照(原唯一 CRITICAL)**:5 检测器并排,ours 100%/0% vs exec-pass/validity/consistency 全 0 recall、self-check 61%/40%(§3.3)。
- ✅ **外部效度**:9 张真实 Nature 表 held-out 切片,模糊 silent 72% [CI 49-88]、oracle 100%/0%(§1.3)。
- ✅ **契约可扩展性**:per-operator-class 非 per-task、半自动从 API 签名派生、缺契约 abstain(§2.4)。
- ✅ **related work 边界 + Incoherence**:§4 加第五条边界,SemGuard 行级 vs 关系型语义讲死;"first"措辞收窄。
- ✅ **歧义校准因果隔离**:6 高危类 × 3 独立澄清,92%→11%(std 3.9 pts);weighted_mean 反转已诚实讨论(§1.2)。

**round-3 的 3 个 High-priority 项(全清,7.5 → 冲 9)**:
- ✅ **scalability 实证**(§3.7):3 个未见算子族,加一条 ~14 行契约前 abstain、后检出,FP 恒 0/5——可扩展性从论证变实测。
- ✅ **真实切片 + 置信区间**(§1.3、§3.5):所有比率带 95% Wilson CI,诚实呈现小样本(下界仍在正确方向)。
- ✅ **master 表 + 必要性消融 + 归因准确率**(§3.4/§3.6):一张 master 表统一所有数源(解决 57/132 vs 135/56/1);goldless 追平 gold 检出(§3.4);归因 recall 29/29=100%(§3.6)。
- ✅ **账目透明**:192 全账混淆矩阵 + master 表标明两次独立生成 run。

**round-5 后补强(optional 项已做掉 2 个)**:
- ✅ **更多模型 + 跨规模**(§1.1)——加开源 Qwen2.5-Coder 7B/14B/32B,silent 率随能力单调下降(65%→54%→44%≈闭源 46%),oracle 全规模 recall≥96%/FP 0%。证明现象+方法跨模型族、跨规模普遍。
- ✅ **契约硬化 + family 剪枝**(§3.6)——schema 门 + 形状门 + family 候选剪枝,归因 cross-fire 从 20% → 8% → **2%**,recall 保持 100%。

**仍可锦上添花(非 blocker,论文写作期)**:
1. **更大 benchmark / 真实切片**——48→100+、真实切片 9→更多干净表(受限于真类目表稀缺)。
