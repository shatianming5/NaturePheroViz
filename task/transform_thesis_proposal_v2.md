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

#### 1.3.1 独立复制 + 规模扩大(2026-06-27,downloads/ 3896 篇全新爬取)

为进一步消除"切片偶然"质疑,自建爬虫深翻 Nature 2016-2026 全年段、抓得 **3896 篇带 Source Data 的真实文章**(13451 图-数据对,完整流程见 §8.x / `scripts/deep_nature_crawl.py`),在此**全新独立语料**上重跑同一套 auto 切片实验(`nature_real_auto.py`,gpt-4o+claude,模糊/澄清,goldless oracle):

| 指标 | 原 841 切片(71 篇) | **新 800 切片(229 篇,独立复制)** |
|---|---|---|
| 模糊 silent 率 | 77% [75-79] | **1092/1408 = 78% [95% CI 75-80]** |
| 澄清后 silent 率 | 10% | 316/1539 = 21% [19-23] |
| oracle recall | 98% | **1398/1408 = 99% [99-100]** |
| oracle FP | 0%(4/1855) | **2/1539 = 0% [0-0]** |

> **77% 的警钟数字在跨 229 篇独立 Nature 论文的全新语料上精确复现**(原 71 篇 → 229 篇,**3× 文章多样性**),模糊 silent 78% [75-80]、CI 同样紧;recall 99%/FP 0% 检测近乎完美。这次独立复制把"77% silent / oracle 近完美"从单一切片升级为**跨语料可复制**的结论。
>
> **澄清后 21% 的来源(诚实拆解)**:按算子拆,残留几乎全来自 **median_not_mean(澄清后仍 40%)** 与 **nan_as_zero_sum(30%)**——这正是 §1.2 早已点名的"无论怎么措辞都修不掉的顽固盲区";其余算子澄清干净(within_group_share 0%、pooled_rate 2%、weighted_mean 13%)。本语料 median 任务占比高,故整体澄清残留(21%)高于原切片(10%),是**算子构成 × median 顽固性**的体现,与论文 §1.2 一致,非异常。
>
> **crash 记账(诊断+修复,已用干净重跑坐实)**:首轮无配速时 9% crash 经诊断为绝大多数代理过载(无间隔狂发→限流返回 None);**加重 retry+配速(pace 0.6/retry 7)整段 800 任务×2 条件×2 模型(3200 调用)干净重跑**后,crash 降到 **253/3200(7.9%)且分项坐实:代理 None 仅 73(2.3%)、真实 exec_fail 180(5.6%)**(模型在凌乱真实表上生成的代码跑挂:选错列/非数值列/重名列)。**代理 crash 被压到 2% 量级、不再是测量噪声主因**;silent 率全程只在 exec-ok 任务上计,代理打嗝无法稀释它。

#### 1.3.2 外部语料 DS-1000:打破 "our-tasks-our-gold" 循环(2026-06-27)

§1.3/1.3.1 的真实切片虽跨数百篇独立 Nature 论文,但**任务仍是我们出的算子语义题、gold 仍由我们的模板 oracle 判**——reviewer 可质疑 77% 是"我们出题/判分方式"的人工产物。本节用一个**任务与 gold 都不属于我们**的外部语料消除该循环:

- **任务 = 真实 StackOverflow 数据处理题**(DS-1000,`xlangai/DS-1000`,HuggingFace),自然语言意图由真实用户书写;
- **gold = DS-1000 自带的执行测试用例**(数据集作者验证过的参考输出),**全程不碰我们的 `transform_oracle`**;
- **信号 = 同一个量**:在**能执行**的解里,"悄悄做错"(跑通但结果错)相对"显式崩溃"的占比——DS-1000 判分器天然区分(exec 抛异常=crash;产出 result 但 assert 失败=silent)。

聚焦本文针对的歧义易错算子族,取其 completion-format 题(统一"赋值给 `result`"契约;16 道 insertion-format 因协议不同排除),共 **152 题 × 2 模型**(gpt-4o + claude-sonnet-4.6),带 95% Wilson CI:

| 指标(外部 DS-1000,真实 SO 任务 + 真实 gold) | 数值 |
|---|---|
| **silent 错率(over exec-ok)** | **70/273 = 26% [95% CI 21-31]** |
| crash 率(over total) | 31/304(代理 None 仅 10,其余为真实 exec_fail) |
| 整体正确率 | 203/304 |

**按歧义易错算子族拆分(silent / exec-ok,降序)——本文点名的"高危算子"正是外部 silent 率最高者**:

| 算子族 | silent / exec-ok | 95% CI |
|---|---|---|
| pivot(重塑 pivot/melt/stack) | 21/47 = **45%** | [31-59] |
| fillna/nan | 12/34 = **35%** | [21-52] |
| dedup(去重) | 6/17 = **35%** | [17-59] |
| sort/topk | 6/17 = **35%** | [17-59] |
| apply/map | 17/75 = 23% | [15-33] |
| groupby/agg | 25/112 = 22% | [16-31] |
| cumulative | 2/10 = 20% | [6-51] |
| median/mean | 4/28 = 14% | [6-31] |
| merge/join | 6/46 = 13% | [6-26] |
| rank | 0/6 = 0% | [0-39] |

> **驱动器自检(关键)**:把 DS-1000 **自带 reference_code** 灌进我们的判分驱动器,得 **152/152 全 pass、0 silent、0 crash**——证明 pass/silent/crash 三分类与 gold 接线正确,silent 不是判分过严的假象;人工核对 silent 样例确属语义错(apply 阈值算错值、条件 dedup 留错行),非 index/列序比较假象。
>
> **现象解读(诚实)**:在一个**我们既没设计任务、也没编写 gold** 的外部语料上,真实用户的 pandas 意图仍有 **26% [21-31]** 概率被"跑得通、结果错"的代码满足。这个数低于 Nature 切片的 77% 是预期的——DS-1000 多为单解的"标准"SO 题,而我们的 Nature 网格刻意构造算子歧义;但 **26% 全是 silent(非 crash),无 gold 时用户根本无从察觉**,且 crash 31/304 里仅 10 个是代理 None、其余为真实 exec_fail(检测正交于 silent)。最有说服力的是:**外部 silent 率最高的几族(pivot 45%、fillna/dedup/sort 各 35%)恰是本文契约重点覆盖的歧义算子**——这把"silent 现象 + 算子定位"从我们自出的题/gold,**锚定到完全外部的真实语料**,直接回应"循环论证"质疑。
>
> **脚本/报告**:`agent/eval/ds1000_real_intent.py`(`--offline` 跑 reference 自检,`--families` 选算子族);`agent/eval/results_ds1000/ds1000_report.md`。

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
5. **外部效度(已得,跨语料三层)**:(i) 自动大切片 **841 任务跨 71 篇 + 独立复制 800 任务跨 229 篇** 独立 Nature 论文,**模糊 silent 77% [75-80]、oracle recall 98-100% / FP 0%**;(ii) 全新外部语料 **DS-1000(真实 StackOverflow 任务 + 自带执行 gold,任务与 gold 均非我们所出)silent 26% [21-31]**,且外部 silent 率最高的算子族(pivot 45%、fillna/dedup/sort 35%)恰是本文契约重点——**打破 our-tasks-our-gold 循环**(详见 §1.3.1 / §1.3.2)。
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
- ✅ **外部效度(跨语料)**:Nature 真实切片 800 任务 / 229 篇模糊 silent 77% [75-80]、oracle 100% / FP 0%;**外部 DS-1000(真实 SO 任务 + 自带 gold)silent 26% [21-31]**,高危算子族(pivot 45% / fillna·dedup·sort 35%)与本文契约重点一致——打破 our-tasks-our-gold 循环(§1.3.1 / §1.3.2)。
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

---

## 8. 下一阶段:从检测到定向修复(repair extension roadmap)

> 状态:检测线(§1-§7)已 READY 9.0;本节是**下一阶段(repair)的方向与"还要做的事情"**,据 2026-06-24 组会纪要落地。
> 完整讨论与邻居比对见 `task/aaai_repair_direction_memo.md`。
> **本节是活文档,随实验推进勾选 ☑ / 更新数字。**
>
> ⚠️ **边界(与既有提案 deconflict)**:① 本 repair 属 **transform 线**(NL→DataFrame 语义/契约 judge),与 viz 线 `oral_method_proposal.md` 已命名的 "silent-error self-repair"(matplotlib 画错的数 / PlotTrace judge)是**不同对象、不同 judge 的不同论文**,headline 措辞不共用;② **C2(targeted repair)已由实验1 实证**(83% vs 10%,§8.4);**C3(abstain-routing)与 dual-agent 经实验为诚实负/中性结果**(不作 claim);仍沿用"不夸大未证部分、负结果照实报"的纪律;③ 本节是 §1-§7 detection 主线的**扩展**,detection 仍是独立、已 READY 的贡献,**不被本节替换**。
>
> 🧭 **主线决策(2026-06-25 已定 + 实验1 已扩样本验证)**:脊柱锁定 **typed operator-semantic attribution**(非 detection/repair/dual-agent 任一动作)。**实验1(generic vs targeted)真实 LLM 跑通并扩样本**:**N=87、3 模型跨厂商(gpt-4o + claude-sonnet-4.6 + gemini-3.5-flash)**,**targeted 80% [95%CI 71-87] vs generic 18% [12-28](CI 分离)**,over-repair 3%、无显著 per-family 回退 ⇒ 过 go/no-go 门、**主线升级为 attribution-driven targeted repair**。回落条款(NO-GO 退 detection)未触发。

### 8.0 一句话定位

> **把已 READY 的 `goldless operator-semantic detection` 闭环成 `typed, constrained, abstention-calibrated repair`**——主 claim:**typed semantic attribution 能比 generic self-repair 更可靠、更高效地修复真实 pandas notebook 里的 silent 语义错**。

### 8.1 为什么"检测后定向修 + 双智能体"单独不够(避免撞 crowded 邻居)

近两年 program/agent repair 已很拥挤,若主贡献只写成"先检测再修复"或"引入两个 agent 分工",reviewer 会问"和已有 agent repair 的本质区别"。需主动区分的最近邻居:

| 邻居 | 年份 | 已覆盖的点 | 链接 |
|---|---|---|---|
| RepairAgent | 2024 | 自主收集信息 + 选工具 + 验证的 LLM repair agent | arxiv.org/abs/2403.17134 |
| SEIDR | 2025 | iterative **multi-agent** debugging & repair | arxiv.org/abs/2503.07693 |
| InspectCoder | 2025 | **dual-agent** + debugger 协作、runtime debugging | arxiv.org/abs/2510.18327 |
| SelfHeal | 2026 | fix agent + critic agent(双智能体框架本身已不新) | arxiv.org/abs/2604.17699 |
| PracRepair | 2026 | 先诊断形成 repair hypothesis 再迭代(接近 diagnosis-driven repair 叙述) | arxiv.org/abs/2606.17612 |

→ **"双智能体"只能算实现手段,不能当第一创新点。**

### 8.2 真正的 novelty 与四条贡献(headline 从"系统堆叠"改成"语义诊断如何驱动可靠修复")

承接已有资产(§2.3 typed 归因、§2.4 abstain、§3.6 family 剪枝),把辨识度建立在**operator-level typed attribution 反向驱动受约束修复**这条线上:

- **C1 — typed semantic diagnosis**:goldless、operator-level attribution(不止 binary detect,而是定位到出错的算子语义)。**已有**(§3.6 归因 recall 25/25=100%、cross-fire 2%)。
- **C2 — contract-guided targeted repair**:把 violated invariant 转成**受约束 patch**(限定 slot / API / transformation),而非开放式 self-repair。**✅ 已证(实验1)**:targeted 83% vs generic 10%,逼近/超过 gold 天花板。
- **C3 — abstain-aware repair routing**:~~诊断/覆盖不足时 abstain 或退回 generic 以减误修~~。**⚠️ repair-time 收益未获实证(实验2a:force 50% ≥ route 25% on uncovered,over-repair 均 0)**;降级——**abstain 仅作 detection-time 安全属性**(未覆盖算子 FP≈0,§3.7/§2.4),**不作 repair-time claim**。
- **C4 — real-world validation**:**✅ 部分已证**:operator prevalence(实验3:12 族 1.64M 真实文件)+ 真实数据 coverage/abstain(§3.5 841 任务 recall 98%/FP 0%);受控 notebook 语料 per-notebook 统计为可选加强(需下载)。

> **据实验更新的贡献结构**:**C1(检测)+ C2(targeted repair,8× 增益)是双主线**;C4 提供外部效度;**C3 与 dual-agent 均降级为诚实负/中性结果**(C3 repair-time 无收益;dual-agent 无增益反更贵),作"我们试过且诚实报告"的可信度资产,不进 headline。

候选标题(择一收敛):
- Typed Semantic Attribution for Reliable Repair of Data-Wrangling Code
- Contract-Guided Targeted Repair with Abstention for Pandas Transformations
- From Goldless Detection to Targeted Repair in Real-World Pandas Notebooks

### 8.3 现有资产与关键缺口

| 资产 | 文件 | 状态 |
|---|---|---|
| typed attribution 评测 | `agent/eval/attribution_eval.py` | ✅ 已有(recall 25/25、cross-fire 2%) |
| operator contracts 库 | `agent/eval/transform_oracle.py` | ✅ 已有(核心 12 类成熟 + 5 族建设中) |
| 在线 repair loop(**viz 线** render-bug) | `agent/app/services/single_chain_runner.py`、`agent/eval/repair_gain.py` | ⚠️ 存在但属绘图线(PlotTrace chart-vs-data),**未与 transform 线打通** |
| transform 线 typed→targeted repair 闭环 | `agent/eval/transform_repair.py` | ✅ 已建+实验1 已出数(GO):targeted 83% vs generic 10% |
| **在线定向修复策略(§8.3 缺口闭合件)** | `agent/eval/transform_repair_policy.py` | ✅ **已建**:exp1 闭环抽成可复用两段式策略(诊断器+受约束修复器+abstain 路由),10/10 离线单测 + 在线 smoke 5/6(83%) |

> **核心缺口(✅ 2026-06-27 已闭合)**:~~已能"检测 + 定位到 operator family",但还没把 typed diagnosis 变成 **online targeted repair policy**~~。**已闭合**:`transform_repair_policy.py` 把 exp1 证明的 targeted 闭环抽成可复用在线策略(结构化诊断 → 受约束修复 → goldless `contract_pass` 终止),10/10 确定性单测 + 真实 LLM smoke 5/6=83%(详见 §8.7)。

### 8.4 决定性实验(实验1 = go/no-go 门,P0)

#### 实验1 — generic vs targeted repair(★ gating,先跑这个)

**核心原则(立论命门)**:三臂**唯一变量 = 回灌的 feedback 内容**;模型、起点 buggy 代码、预算 N 轮、温度、随机种子、重写 prompt 模板**全部锁死**——否则增益归因不干净。

- **样本**:`transform_bench._cases()` 中**模糊提示下 exec-ok 但 silent(gold 判错)** 的 case(真正需要修的);按 `op` 分层,记录 true operator family(per-family 指标用)。
- **三臂(非两臂——加天花板才挡得住"那 gold 能修多少")**:

  | 臂 | 回灌 feedback | 角色 |
  |---|---|---|
  | A. generic(下界) | "结果可能有误,请检查并修正" + 模型自查,**不给任何 typed 信息** | baseline,须是**最强无契约版**,不得打稻草人 |
  | B. targeted(ours) | `violated invariant + 出错算子 + allowed patch scope`(`transform_oracle.check().detail` + `attribution_eval._run_all_contracts(prune=True)` 定位) | 主张 |
  | C. gold-diff(天花板) | 直接 gold 对账("哪个值该是多少") | 上界,证明 goldless 的 B **逼近**有 gold 的 C |

  → B 离 C 越近、离 A 越远 = 故事越硬。
- **指标(per-arm × per-family)**:① final repair success(N 轮后 `_gold_correct` 判对率,主指标);② 平均轮数 / token / cost;③ **over-repair 率(双定义)**——(a) 修复后**新引入**其它契约 fire,(b) gold 上**本来对的子结构被改坏**;④ abstain 正确性(见消融)。
- **避免循环论证(关键)**:repairer **全程只看 goldless 契约**,成功判据用**独立 gold**(`_gold_correct`,模型不可见)——与检测线"oracle 不看 gold、标签用 gold 算"同构,须在论文讲死。
- **公平性(审稿人必攻,先堵)**:① generic 臂给**最强自查 prompt**,不得故意弱化;② 三臂共用**同一份 buggy 起点代码**(同一次模糊生成产物),不各自重生成;③ 温度固定(`_llm_code` 已 temp=0)、跨**多模型**(GPT-4o/Claude/≥1 开源)证明非单模型 artifact。
- **go/no-go 门(写死,不事后挪)**:targeted **同时**满足 ① final success 显著 > generic、② **over-repair 率 ≤ 绝对阈值 10%**(注:generic 几乎不改动→over-repair 天然≈0,拿"不修"当基准不合理,故用绝对阈值而非"≤generic")、③ 轮数不增、④ **无显著 per-family 回退**(per-family Wilson CI **分离**才算回退;小样本噪声/§3.7 盲点的 raw 非赢透明列出但不否决,避免单族噪声否决压倒性总量) ⇒ 升级 repair 主线;否则回落 detection。
- **新文件**:`agent/eval/transform_repair.py`,复用 `transform_bench._cases` / `ambiguity_calibration.{_llm_code,_exec,_gold_correct}` / `transform_oracle.check` / `attribution_eval._run_all_contracts`;LLM 走 `LLM_API_BASE/KEY/MODEL`;`--offline` 跑结构自测、`--resummarize <json>` 改门后从已存 JSON 重算。

##### ✅ 实验1 结果(2026-06-25,首轮真实 LLM:gpt-4o + claude-sonnet-4.6,N=29 silent case,N轮=3)

| 臂 | success | mean rounds | over-repair(a) 新fire | over-repair(b) 破坏正确 | 停机主因 |
|---|---|---|---|---|---|
| A generic(下界) | **3/29 = 10%** | 1.17 | 0% | 0% | 26/29 **fixpoint**(模型重导出同一错值) |
| B targeted(ours) | **24/29 = 83%** | 1.14 | 1/29 = 3% | 0% | 27/29 contract_pass |
| C gold-diff(天花板) | 22/29 = 76% | 1.45 | 1/29 = 3% | 0% | 22 gold_match / 6 budget |

**go/no-go:全 PASS ⇒ VERDICT GO**(success 83%>10%、over-repair 3%≤10%、轮数不增、无 per-family 回退)。

关键发现(诚实):
- **8× 增益**:typed 契约 feedback 把 silent-error 修复率从 generic 的 10% 拉到 83%。
- **B(83%)≥ C 天花板(76%)**:契约说清"你算成算术均值/比率,应是加权/百分点"比单纯给 gold 数字**更可操作**——`pct_point` B=4/4 而 C=1/4 最典型。这是比预期更强的结果。
- **公平**:generic 主要靠 26/29 **fixpoint**失败(模型看不出 silent 错、重导出同值),malformed 仅 10%——非 harness artifact;且 generic 非全 0(`cumcount`1/1、`clip_outlier`2/4),未被人为压低。
- **诚实边界**:`zscore_within_group` B=0/2(§3.7 单契约盲点)但 C=2/2(证明可补契约修复),与 §2.4/§3.7 覆盖边界自洽。
- 数据留痕:`agent/eval/results_repair_targeted/`(`first_run_raw.log` 首轮原始 + 复跑生成的 report/json)。

##### ✅✅ 实验1 扩样本复核(2026-06-25,**N=87、3 模型跨厂商** gpt-4o + claude-sonnet-4.6 + **gemini-3.5-flash**,带 95% Wilson CI)

| 臂 | success [95% CI] | mean rounds | over-repair(a) | 停机主因 |
|---|---|---|---|---|
| A generic(下界) | **16/87 = 18% [12-28]** | 1.34 | 0% | 71 fixpoint / 8 malformed(9%) |
| B targeted(ours) | **70/87 = 80% [71-87]** | 1.10 | 3/87 = 3% | 83 contract_pass |
| C gold-diff(天花板) | 70/87 = 80% [71-87] | 1.33 | 2/87 = 2% | 70 gold_match / 14 budget |

**go/no-go:GO**——targeted 80% [71-87] vs generic 18% [12-28] **CI 完全分离**;over-repair 3%≤10%;轮数不增;**无显著 per-family 回退**(唯一 raw 非赢 `zscore_within_group` targeted 1/8 vs generic 2/8,CI 重叠=噪声、且为 §3.7 已声明盲点,透明列出不否决)。
- **跨厂商稳健**:加入 Google gemini-3.5-flash 后结论不变(targeted 仍 4-5× 于 generic),非单厂商/双模型 artifact;CI 收紧(±~8pt)。
- **per-family**:targeted 在 10 族中 9 族 ≥ generic;`pct_point` 12/12 vs C 仅 6/12、`topn_with_ties` 12/12——契约反馈再证比 gold 数字更可操作。
- 数据留痕:`agent/eval/results_repair_expanded/`(`run_raw.log` + report/json)。canonical N=29 首轮与 N=87 扩样本**结论一致**(83%/10% → 80%/18%,差异为采样)。

#### 实验2 — 消融(`agent/eval/transform_repair_ablation.py`,实验1 过门后)
- ⚠️ **abstain-aware routing 臂(C3 实证 → 未获支持,诚实负结果)**:`--mode abstain`(gpt-4o+claude,N=17)。covered 子集 route==force==**89%**(generic 0%)符合预期;但 **uncovered 子集:force 50% > route 25%**、over-repair 三策略均 **0%**。⇒ **repair 时的 abstain-routing 安全收益未被验证**——在未覆盖算子上硬给 targeted 反馈既没抬 over-repair(proxy 偏弱)也没掉成功率。诚实结论:**abstain 是 detection-time 属性**(未覆盖算子 FP≈0,§3.7),**不是已证的 repair-time 收益**;**C3 降级为 exploratory、不作 claim**(详见 `results_repair_ablation/ablation_abstain_report.md`)。
- ✅ **single-agent vs dual-agent**:`--mode dual`(gpt-4o+claude,N=30)。**single 83% vs dual 77%**(dual 略**差**)、dual 成本 **2.2×** calls、over-repair 7% vs 3%。⇒ **dual-agent 不带来增益、反而更贵更易误修**,强证"headline 是 typed-attribution **signal**、非 agent 数";直接回答 reviewer"为何两个 agent"。**仅消融,不进 headline**。

#### 实验3 — real-world operator prevalence + coverage/abstain(`agent/eval/operator_prevalence.py`,✅ 已出数)
- ✅ **prevalence(GitHub 公开 Python 代码搜索,2026-06-25)**:12 个契约覆盖的算子族**全部高频出现于真实代码**,合计 **1,637,552 个文件**;最高危的也最常见——NaN 处理 304,896、cumulative 320,640、median 175,792、dedup 170,368、join-how 161,344。⇒ silent-error 面**非合成**,是真实世界最高频的 wrangling 算子。
- ✅ **coverage/abstain(真实数据,复用 §3.5)**:841 任务/71 篇 recall 98%/FP 0%;未覆盖算子退化为 **abstain** 而非误报(配合实验2a 路由)。
- ☐ **可选加强(需下载)**:受控 notebook 语料的 per-notebook 算子频率/abstain——PandasBench(2506.02345)/CoCoNote(2409.13551)/JunoBench(2510.18013)/ARCADE(2212.09248)/KGTorrent(2103.10558)。

### 8.5 执行顺序(短期,gate-first)

1. ✅ **P0(完成)**:`agent/eval/transform_repair.py` 建成 + 离线自测 + **实验1 真实 LLM 出数**(gpt-4o+claude,N=29):**GO**。
2. ✅ **决策点(已过门)**:targeted 83% vs generic 10%、over-repair 3%、无回退 ⇒ **升级 repair 主线**(§8.2 标题)。
3. ✅ 过门后实验全部跑完:实验2(✅ dual:single 83% vs dual 77%@2.2×→无增益;⚠️ abstain:repair-time 无收益、C3 降级)+ 实验3(✅ prevalence 1.64M 文件 + §3.5 coverage/abstain)。
4. ✅ **扩样本复核完成**:N=29→**N=87、3 模型跨厂商(加 gemini-3.5-flash)、95% Wilson CI**——targeted 80% [71-87] vs generic 18% [12-28] **CI 分离**,跨厂商稳健。
5. 🟢 **扩数据量(2000–5000 篇 Nature)就绪**:`download_nature_pairs.py` 已加 `--skip-images` + `--max-data-file-mb`;并把文章解析从 playwright 改为 **requests+BeautifulSoup**(`extract_pairs_from_article_requests`)——Nature 对 playwright(无头/有头)有 "Client Challenge" 反爬、但 requests 能过,端到端冒烟 2/2 成功。推荐(仅 transform 线、省 ~75% 存储):
   `python download_nature_pairs.py --max-articles 5000 --skip-images --max-data-file-mb 20 --out-dir downloads`
   预估存储:仅数据+20MB上限 ≈ **~9 GB@2000 / ~23 GB@5000**(全量含图为 ~40/~100 GB);benchmark 规模 ≈ **8000/20000 任务**(按 §3.5 比例)。
6. ☐ 据结果**收敛 AAAI 标题与主故事**:主线 = C1 检测 + C2 targeted repair;C3/dual-agent 作诚实负结果。可选:再加开源模型。

### 8.6 双智能体的定位(降级为机制/消融)

保留但重新定位——**目的是解耦 diagnosis 与 repair 的 search space,不是"看起来更复杂"**:
- Agent A(diagnoser):输出 `operator posterior + violated invariants + allowed patch scope`。
- Agent B(repairer):只在受限空间里改指定 slot / API / transformation。
- ❌ 不可写成"因为流行 multi-agent 所以也做";双智能体仅作实现策略或消融项,不作 headline novelty。

### 8.7 在线定向修复策略(✅ 闭合 §8.3 缺口,2026-06-27)

exp1 证明了"typed attribution 反馈 → 受约束修复"有效,但那套逻辑**缠在 3 臂实验 harness 里、绑定 transform_bench 的 case 结构**,不是可复用的在线策略。本节把它抽成 §8.6 两段式**可复用在线策略** `agent/eval/transform_repair_policy.py`(**不碰 viz 线 `single_chain_runner.py`,transform 线自洽**;复用 `transform_oracle`/`attribution_eval`/`ambiguity_calibration`,**不重复实现契约**):

- **Agent A 诊断器** `diagnose(inputs, params, result) -> Diagnosis`:跑 goldless 契约(family 剪枝)输出**结构化诊断** = `{fired, operator, violated_invariant, localized_contracts, allowed_scope, confidence}`。**解耦**——不依赖 case 的 op/gold,任意 `(inputs, params, result)` 可用。
- **Agent B 修复器**:消费 `Diagnosis` → 受约束指令("只改 `<op>` 这一步"),经**注入式** `code_fn/exec_fn` 产出新结果(注入使整条策略**离线确定性可测**、在线 LLM-agnostic)。
- **策略环** `TargetedRepairPolicy.repair(...) -> RepairOutcome`:锁定目标算子 → 每轮以**该算子自身契约**为 goldless 停机信号(`contract_pass`),非"所有契约静默"(避免无关契约 cross-fire 把已正确结果误判为仍需修);预算上限封顶。
- **abstain-aware routing**(诚实降级):未覆盖算子(无契约 fire)且调用方断言出错(`assume_wrong`)时,按 `abstain_policy` 路由 `generic` 回退或 `abstain` 停手。**按 §8.2 C3 不 claim repair-time 收益**,仅作 detection-confidence 驱动的安全 knob。

**验证(两层)**:

| 层 | 内容 | 结果 |
|---|---|---|
| 离线确定性单测(`_selftest`,无 LLM) | 诊断结构化输出 + 策略环 + abstain 路由 + 预算/malformed/no_error 边界 | **10/10 通过** |
| 在线 smoke(`--online-smoke`,proxy 真实 LLM) | 策略在真实 silent case 上跑,**独立 gold**(策略全程不可见)判对 | **5/6 = 83%**,`contract_pass` 终止 |

> **意义**:把"检测 + 算子定位"正式闭合成 **online targeted repair policy**——同一条 typed-attribution signal,既驱动 §1 的 goldless 检测,又驱动 §8 的受约束修复;在线 smoke 83% 与 exp1 的 80-83% 一致,证明这不是实验 harness 的产物,而是**可复用、可部署、goldless 自停**的修复策略。C1(检测)+ C2(targeted repair)双主线由此各有可运行落地件(`attribution_eval.py` / `transform_repair_policy.py`),dual-agent 解耦在策略里体现为"诊断器/修复器"分工但**不作 novelty**。

##### 外部 C2 验证(DS-1000,诚实覆盖边界,2026-06-27)

把该策略跑到**完全外部**的 DS-1000 silent 错上(`agent/eval/ds1000_repair.py`,gpt-4o,80 个真实 silent 错,**成功判据 = DS-1000 自带 gold**,与 §1.3.2 对检测做的事对称),诚实测得算子专属契约对"任意"真实 SO 任务的迁移边界:

| 指标(外部 DS-1000,80 silent,95% Wilson CI) | 数值 |
|---|---|
| 契约 fire 覆盖率 | **6/80 = 8% [3-15]**(全部 `left_join_keep_all`) |
| 整体恢复:generic 基线 | 14/80 = 18% [11-27] |
| 整体恢复:**policy(targeted+abstain)** | **16/80 = 20% [13-30]** |
| **covered 子集:generic** | 1/6 = 17% [3-56] |
| **covered 子集:targeted** | **3/6 = 50% [19-81]** |

> **诚实解读**:大多数算子契约需要 operator-semantic params(group/value/weight…),而 DS-1000 的任意 SO 题**不带**这些 params,故覆盖率被**结构性地压到 8%**——能迁移的几乎只有**免-params 的 `left_join_keep_all`(join/how 语义)**(6/6 covered 全是它)。这是算子专属契约对**无约束真实任务零样本迁移**的诚实边界,**不掩饰**。两个正面信号仍成立:① **policy 整体 ≥ generic**(20% vs 18%)——因为对未覆盖的 92% 策略**安全 abstain 回退 generic**(不盲改、不掉点),只在 covered 处加分;② **covered 子集 targeted 3/6 vs generic 1/6**——契约 fire 处 typed 反馈的提升方向与 exp1 一致(N 小,仅作方向性佐证)。**结论**:operator-matched 且**高覆盖**的外部-DATA C2 强证据是 **Nature §1.3.1 切片**(params 已知、契约 ~99% recall);DS-1000 提供的是**覆盖边界 + abstain 安全性**的诚实外部锚点。脚本/报告:`agent/eval/ds1000_repair.py` / `agent/eval/results_ds1000_repair/ds1000_repair_report.md`。

##### 外部 C2(Nature 真实数据,operator-matched 高覆盖,2026-06-27)

DS-1000 给的是 external-**TASK**(真实意图)但**低覆盖**的诚实边界。本节补上其**互补面**:把同一套 generic-vs-policy 修复跑到 external-**DATA**——**真实 Nature 源数据表**(§1.3.1 切片,跨 20 篇文章)上实例化我们的算子任务,params 已知,故契约**高覆盖**(`agent/eval/nature_repair.py`,gpt-4o,60 个真实 silent 错,成功判据 = 真实表上的模板 gold,策略全程不可见):

| 指标(真实 Nature,60 silent,95% Wilson CI) | 数值 |
|---|---|
| 契约 fire 覆盖率(算子匹配 ⇒ 高) | **41/60 = 68% [56-79]** |
| 整体恢复:generic 基线 | 2/60 = 3% [1-11] |
| 整体恢复:**policy(targeted+abstain)** | **33/60 = 55% [42-67]** |
| **covered 子集:generic** | 2/41 = 5% [1-16] |
| **covered 子集:targeted** | **33/41 = 80% [66-90]** |

分算子族(targeted vs generic / total):**within_group_share 21/23 vs 0/23**、weighted_mean 3/4 vs 0/4、pooled_rate 3/8 vs 2/8、median_not_mean 6/25 vs 0/25。

> **解读**:在 params 已知的真实科学表上,**covered 子集 targeted 80% [66-90] vs generic 5% [1-16](CI 完全分离)**——typed 契约反馈把真实数据上的 silent 修复率拉高 ~16×,与 exp1(80% vs 18%)一致甚至更强,**坐实 C2 在真实数据上的外部效度**。诚实点名:**median_not_mean 即便给 targeted 反馈也仅 6/25 修成**——这正是 §1.2 反复点名的"无论怎么提示都顽固"的算子(模型反复重算成均值),targeted 不是万能;但 within_group_share/weighted_mean 近乎全修。**两个外部实验夹逼出 C2 的完整图景**:DS-1000(external-TASK,覆盖 8%,诚实边界 + abstain 安全)+ Nature(external-DATA,覆盖 68%,targeted 80% vs generic 5%)⇒ **算子语义被识别处 targeted 强势、识别不到处安全 abstain 回退**,正面回答"你的 targeted 在真实世界到底有没有用"。脚本/报告:`agent/eval/nature_repair.py` / `agent/eval/results_nature_repair/nature_repair_report.md`。
