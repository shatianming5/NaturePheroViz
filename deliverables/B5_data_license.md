# B5 — 数据与模型许可注册

> 完整版见 `agent/eval/DATA.md`。本文档为中文摘要，供投稿前 review 使用。  
> **更新时间**：2026-06-26（v2，新增 transform-bench、841-task slice、Qwen 权重、API 条款）

---

## 数据集与模型总览

| 数据集 / 模型 | 状态 | 许可证 | 论文使用 | AAAI 风险 |
|--------------|------|--------|:--------:|:---------:|
| Built-in fixtures | ✅ 已集成 | 作者自有 | 否（冒烟测试） | 无 |
| MatPlotBench | ✅ 已集成 | Apache-2.0 | 仅附录 | 无 |
| **Transform-Bench 合成数据** | ✅ 已集成 | 作者自有 | **是（表1/2/3）** | **无** |
| **Nature 841-task slice** | ✅ 已集成 | ⚠️ 待核实 CC-BY | **是（表1 第3行）** | **中** |
| **Qwen2.5-Coder (7B/14B/32B)** | ✅ 已集成 | Apache-2.0 | **是（表3B）** | **无** |
| **OpenAI GPT 系列** | ✅ 已集成 | OpenAI ToS（允许学术发表） | **是（表1/2/3A）** | 低 |
| **Anthropic Claude** | ✅ 已集成 | Anthropic 政策（允许学术发表） | **是（表1/2/3A）** | 无 |
| **Google Gemini** | ✅ 已集成 | Google AI Terms（允许学术发表） | **是（表3A）** | 无 |
| Plot2Code / ChartMimic | 未集成 | 待确认 | 否 | — |

---

## 1. Transform-Bench 合成数据（主线 benchmark）

**来源**：作者程序生成，无第三方数据依赖

- **脚本**：`eval/transform_oracle.py`（`_cases()` 函数）+ `eval/ambiguity_calibration.py`
- **规模**：48-grid（12 类 × 4 实例）+ 68-grid（17 类 × 4 实例）= 116 个唯一 case
- **许可证**：作者自有，无限制
- **可复现性**：完全可从代码重新生成，无外部依赖
- **AAAI 合规**：✅ 无任何限制

---

## 2. Nature 841-task slice（真实数据验证）

**来源**：`nature_crawler.py` 爬取 Nature 系列期刊的 Source Data XLSX 文件

- **规模**：扫描 211 篇文章 / 1607 个 source-data 表，过滤后取 71 篇独立文章的 841 个任务
  - 每篇文章最多 15 个任务（避免少数文章支配结果）
- **爬虫版本**：`nature_crawler.py` 合并版，subcommand `auto` + `postfetch`，使用 Crossref + Europe PMC 的 `is_open_access` 字段过滤
- **爬取日期**：2026-06（精确日期待补充）

### ⚠️ 许可证核实状态（AAAI 投稿前阻塞项）

**风险点**：爬虫的 `is_open_access=True` 筛选不等价于 CC-BY-4.0。相关情况如下：

| 期刊 | 许可证情况 |
|------|----------|
| **Nature Communications** (`s41467-*`) | 2014 年起全部 CC-BY-4.0 ✅ |
| **Nature**（主刊） | 混合模式：部分 CC-BY，部分传统版权 ⚠️ |
| 其他 Nature 系列期刊 | 逐文章不同 ⚠️ |

**Source Data 再分发**：本文仅使用 XLSX 数据构造 prompt 和运行 oracle，不在论文或补充材料中再分发原始 XLSX 文件。以聚合统计形式发表（silent rate 数字）属于合理分析，即便数据有版权限制也属于合理使用范畴。

**必做核实**（投稿前阻塞）：

```bash
# 检查 articles.csv 中所有 DOI 是否都是 s41467-* （Nature Communications）
grep doi articles.csv | grep -v "s41467" | head -20
```

若存在非 `s41467-` 的 DOI，需逐一确认其许可证。如无法确认，应从 841-task 集合中移除对应任务并重跑指标。

---

## 3. Qwen2.5-Coder 模型权重

| 模型 | HuggingFace ID | 本地路径 | 许可证 |
|------|---------------|---------|-------|
| 7B | `Qwen/Qwen2.5-Coder-7B-Instruct` | `/mnt/cephfs_home_tianming.sha/qwen_models/Qwen2.5-Coder-7B-Instruct` | Apache-2.0 |
| 14B | `Qwen/Qwen2.5-Coder-14B-Instruct` | `/mnt/cephfs_home_tianming.sha/qwen_models/Qwen2.5-Coder-14B-Instruct` | Apache-2.0 |
| 32B | `Qwen/Qwen2.5-Coder-32B-Instruct` | `/mnt/cephfs_home_tianming.sha/qwen_models/Qwen2.5-Coder-32B-Instruct` | Apache-2.0 |

- **Apache-2.0** 明确允许：学术研究使用、报告模型输出结果、学术论文发表
- **NC 条款**：无（Apache-2.0 无非商业限制）
- **推理配置**：BF16 全精度，贪婪解码（temperature=0），batch=1
- **验证脚本**：`agent/eval/qwen_local_eval.py`（gpudev2 离线运行）

---

## 4. LLM API 使用（闭源模型）

### OpenAI（GPT 系列）

| 项目 | 内容 |
|------|------|
| 使用的模型 | gpt-4o（歧义校准）、gpt-5.4 / gpt-5.5 / gpt-5.3-codex（表3A）、gpt-4.1-mini（agent 推理） |
| 访问方式 | 内部代理 `1.14.177.180:4141`（API 兼容端点） |
| 许可条款 | OpenAI ToS §3(a)：允许将输出用于研究和发表 |
| AAAI 风险 | 低——报告模型输出的聚合统计是标准学术实践，明确允许 |
| ⚠️ 待补充 | 从代理日志中补充精确模型版本字符串（如 `gpt-5.4-2026-05-08`），写入论文 Methods |

### Anthropic（Claude 系列）

| 项目 | 内容 |
|------|------|
| 使用的模型 | claude-sonnet-4.6（歧义校准、baseline compare）、claude-opus-4.8（表3A） |
| 许可条款 | Anthropic 使用政策允许学术研究使用及发表结果 |
| AAAI 风险 | 无 |

### Google（Gemini）

| 项目 | 内容 |
|------|------|
| 使用的模型 | gemini-3.1-pro-preview（表3A） |
| 许可条款 | Google AI 开发者条款允许研究使用及发表 |
| AAAI 风险 | 无 |

---

## 5. MatPlotBench（早期阶段）

- **来源**：[thunlp/MatPlotAgent](https://github.com/thunlp/MatPlotAgent) — `benchmark_data/`
- **许可证**：Apache-2.0
- **论文用途**：仅用于附录消融实验，不作为主表数据
- **状态**：✅ 许可证已确认（2026-06）

---

## 投稿前检查清单

### 阻塞项（必须完成才能投稿）

- [ ] **【Nature slice CC-BY 核实】** 审计 `articles.jsonl` / `articles.csv`：确认 71 篇文章全部为 Nature Communications（DOI 前缀 `10.1038/s41467-`）或其他已确认 CC-BY-4.0 期刊。若有不符，移除对应任务并重跑 Table 1 第 3 行指标。
- [ ] **【爬虫日期记录】** 从运行日志补充精确爬取日期和关键词，写入论文 Appendix/Reproducibility Statement。
- [ ] **【OpenAI 模型版本】** 从代理调用日志提取实际模型版本字符串，补充进论文 §Methods（AAAI 可复现性要求）。

### 建议项（非阻塞，但提升质量）

- [ ] **【Qwen 许可证二次确认】** 投稿时重新检查 HuggingFace 模型卡（Qwen2.5-Coder-7B/14B/32B）确认仍为 Apache-2.0。
- [ ] **【MatPlotBench】** 确认 `thunlp/MatPlotAgent` 最新 repo LICENSE 仍为 Apache-2.0。
- [ ] **【数据可用性声明】** 在论文中加入："Transform-Bench 合成数据集将随代码一同发布；Nature slice 仅提供 DOI 列表，不发布原始 XLSX。"

### AAAI 格式要求

- [ ] 致谢章节中注明数据来源：Nature Communications (CC-BY-4.0)、Qwen2.5-Coder (Qwen Team / Alibaba Cloud, Apache-2.0)、OpenAI、Anthropic、Google DeepMind
- [ ] 若投 Responsible AI 子版块，需完成 AI 使用声明表

---

## 许可证矩阵（快速判断）

| 许可证 | 研究论文发表 | 模型输出发表 | 数据再分发 | 商业用途 |
|-------|:-----------:|:-----------:|:---------:|:-------:|
| 作者自有 | ✅ | ✅ | ✅ | ✅ |
| Apache-2.0 | ✅ | ✅ | ✅ | ✅ |
| CC-BY-4.0 | ✅ | N/A | ✅（需署名） | ✅ |
| CC-BY-NC-4.0 | ✅（学术=非商业） | N/A | ✅（需署名，非商业） | ❌ |
| OpenAI ToS | ✅ | ✅ | ❌ 不得再训练 | 受限 |
| Anthropic Policy | ✅ | ✅ | ❌ 不得再训练 | 受限 |
