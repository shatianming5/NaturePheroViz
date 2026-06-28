# Thesis round-0：执行追踪验证 LLM 数据变换的语义保真

> 目标顶会 Oral。本提案的前提已被自家 go/no-go 实验验证（非臆测）。
> 一句话：LLM 生成的数据处理代码（pandas groupby/pivot/加权/占比/join）经常**能跑、结果看着合理、但语义错**（GPT-4o 38% / Claude 25% silent 错率）；我们用**执行追踪 + 参考语义对账**抓出这类 silent semantic error——exec-pass 测不出、单元测试覆盖不到、人眼看不出。

---

## 0. Problem Anchor（每轮逐字保留）

- **根本问题**：LLM 越来越多地生成数据处理/分析代码（pandas/SQL），但**"代码能跑 + 输出是个合理的表"≠ 它做了用户要的变换**。LLM 在语义有歧义处系统性犯错：加权 vs 算术均值、组内 vs 全局占比、百分点 vs 百分比、聚合粒度、join how、NaN 处理、保留并列、去重时机。
- **必须解决的瓶颈**：这类错误是 **silent semantic error**——代码无异常、结果形状合理、数值看着正常，所以 ① execution-pass / 不崩 测不出；② 输出值域检查测不出；③ 人 review 也极难发现（要逐行重算）；④ 没有 gold output 时无法对账。结果是**错误的分析结论被当成对的**。
- **核心主张**：用**执行追踪**（捕获代码实际产生的中间/最终 DataFrame）+ **从自然语言意图推导的参考语义**做结构化对账，检测 silent semantic error，并定位到出错的变换算子。
- **非目标**：不做 text2SQL 的语法/可执行性检查（那是已解决的）；不训模型；不做通用代码正确性证明；不要求有人工 gold output（要能在无 gold 时工作）。
- **成功条件**：(a) 在一个 silent-semantic-error benchmark 上，检出率显著高于现有手段（exec-pass / 输出合法性 / LLM-self-check / 单元测试式断言）；(b) 能定位到出错算子类型；(c) 检出的错误是真 silent（代码跑通、结果合理）。

---

## 1. go/no-go 已验证的前提（这是本提案区别于空想的关键）

- 16 个陷阱变换 × {GPT-4o, Claude}，**silent 语义错率 GPT-4o 38% / Claude 25%**（代码跑通但结果错）。
- 两模型都 silent 错的 case：`pct_point_change`（百分点）、`share_within_group`（组内占比）、`running_balance`（累计）。
- 对照：同样的强 LLM 在"给定干净数据画标准图"上 silent error 率 **0%**——证明**问题特异于"语义有歧义的数据变换"**，不是 LLM 普遍不可靠。

---

## 2. 这不是什么（预先划清，省得被归类）

| 近似工作 | 它做什么 | 与本提案的区别 |
|---|---|---|
| **text2SQL 验证 / Spider 执行准确率** | 比对 SQL 执行结果 vs gold query 结果 | 它**需要 gold query/output**；我们要在**无 gold** 时靠"意图→参考语义"对账。且我们针对 pandas 多步变换 + silent 语义错分类 |
| **pandas/代码生成 benchmark（DS-1000/ARCADE/Lemur）** | 测代码能否通过隐藏单元测试 | 它们靠**预写的 test cases**；silent error 恰恰是 test 没覆盖的语义歧义。我们不依赖预写 test |
| **execution-based eval / self-debugging** | 跑代码看报错/输出，LLM 自我修正 | 它们抓 **crash**；silent semantic error **不 crash**。self-check 用同一个 LLM，对自己的语义盲区无能为力 |
| **LLM-as-judge for code** | 让 LLM 判代码对不对 | 我们已知 LLM 对自己的语义错有盲区（两模型都错同一题）；需要**确定性的执行对账**而非又一个 LLM 判官 |
| **数据流/计算溯源（provenance）** | 追踪数据如何流经算子 | 偏系统/DB；我们针对"LLM 生成代码的语义意图是否匹配"，且做成 LLM-codegen 的验证层 |

**最大撞车风险**：text2SQL 的 "execution accuracy" 和 DS-1000 的 test-based 评估。**区分点必须是**：(1) 无需 gold output / 预写 test；(2) 针对 silent **语义**歧义（非语法/可执行性）；(3) 输出 typed 错误归因（哪个算子语义错）。**这个区分点成立与否，是 reviewer 要狠查的，也是 go/no-go 之后下一个要确认的。**

---

## 3. 方法（最小机制）

1. **执行追踪**：复用已实现的 PlotTrace 思路，扩展到捕获 pandas 变换链的**中间 + 最终 DataFrame**（monkeypatch / AST 插桩 groupby/merge/pivot/agg 等）。
2. **参考语义对账**：核心难点——无 gold output 时，怎么判"结果是否符合意图"？候选机制（择一/组合，待 idea-refine 收敛）：
   - (a) **多实现一致性**：用 N 个独立方式（不同 LLM / 不同 prompt / 符号化）生成同一变换，执行追踪对比中间结果分歧 → 分歧处即可疑（类似 self-consistency 但在执行层）。
   - (b) **意图→可检查属性**：从 NL 意图抽出可验证的不变量（如"占比应 sum=1"、"加权均值应落在 min/max 之间且≠算术均值当权重不均"、"join 后行数关系"），执行追踪验证这些属性。
   - (c) **参考实现库**：对常见变换维护确定性参考算子，匹配意图后对账（覆盖率换精度）。
3. **typed 归因**：silent error 归类到算子语义（聚合粒度 / 权重 / 分组范围 / join how / NaN 语义 / 并列处理），驱动可解释报告或修复。

> 哪种对账机制是主路，是 idea-refine 要砍定的核心。(a) 多实现一致性最不依赖人工、最 scalable，可能是 oral 卖点。

---

## 4. 决定性实验（claim-driven）

1. **silent-error benchmark**：扩到 50-100 个陷阱变换（覆盖算子类型 × 歧义类型），多模型（GPT-4o/Claude/开源），报告 silent 语义错率。这本身是领域贡献（第一个 silent-transform-error benchmark）。
2. **检测 head-to-head**：我们的执行追踪对账 vs ① exec-pass ② 输出合法性检查 ③ LLM-self-check ④（若做 a）多实现一致性。指标：silent-error 检出 precision/recall + 算子归因准确率。预期：exec-pass 0 检出，self-check 受同源盲区限制，执行追踪显著更高。
3. **必要性消融**：证明"无 gold output"下仍能检出（否则退化成 text2SQL）。

---

## 5. 诚实风险

- **撞车风险（最高）**：§2 的区分点如果站不住（已有工作其实覆盖了 silent 语义错检测），整篇塌。**idea-refine 第一要务就是查这个**。
- **参考语义对账的可靠性**：(a) 多实现一致性可能"一致地错"（两模型都错同一题已出现！）→ 需要 (b) 属性检查兜底。这是方法的最大技术风险。
- **意图歧义本身**：有些"silent error"可能是意图真的有歧义（百分点 vs 百分比用户没说清）→ 要区分"模型理解错" vs "意图本就欠定义"，否则被批 benchmark 不公。

---

## 6. 与已有资产的关系

- **执行追踪基础设施**：PlotTrace（monkeypatch 截获 + 对齐 + 容差匹配 + typed mismatch）已实现并验证，扩展到 pandas 变换链是增量。
- **go/no-go harness**：`eval/transform_gonogo.py`（16 陷阱变换 + 手算 gold + silent/crash 三分类）是 benchmark 雏形。
- **判官消融经验**：之前证明"执行追踪 >> 渲染反推判官"的方法论可复用到"执行对账 >> exec-pass/self-check"。
