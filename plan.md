# 最常用：每轮修改后同步到 GitHub

```bash
./scripts/sync.sh -m "本轮修改说明"
```

- 默认流程：`pull --rebase --autostash` → `add -A` → `commit` → `push`
- 数据目录 `downloads/` / `downloads*` 已通过 `.gitignore` 忽略，不会上传

# Proposal：Code-First PheroREER（直接输出代码的 data→code→plot 训练与推理闭环）

> **核心主张（与你给的 PDF 摘要对齐）**：整个系统以 **可执行的 code/patch** 为中心，不强制先输出结构化 spec。可视化生成被定义为一个在统一 sandbox 里闭环运行的 **“intent → code/patch → render → judge → route”** 流程；每一步读取节点状态 **(g(v), Ω_v, H_v, Ξ_v, Γ)**，生成最小补丁 **δC**，执行渲染并记录运行信号，再由 Judge 评分与诊断并路由下一步。
> **同时（与你给的 pptx/REER 精神对齐）**：从已知高质量输出 **y（好代码/好图）** 出发，反推能产生它的深推理轨迹 **z**，通过局部搜索/迭代精炼让 **PPL(y|x,z)** 更低；训练时可用深推理提升能力，部署时仍保持 **code-only 输出**。

---

## 工程计划：`downloads/articles`（LangChain + Gemini 3.0 Flash：子图分割 + 数据检查）

> 处理目标：对 `downloads/articles` 下的文章数据做**目录级完整性检查**，并对 figure 图进行**子图（multi-panel）分割**；只保留**数据可视化相关**的子图（chart/plot/heatmap/table 等），输出裁剪图 + 可复现元数据（bbox/类型/置信度/来源路径），便于后续训练/检索/人工复核。
>
> 本节只补全计划：先写清楚“怎么做/产出什么/如何验收”，暂不实现与跑数据。

### A. 数据位置与约定

- 数据根目录（Windows）：`C:\Users\90646\Downloads\nature_dis\downloads\articles`
- 数据根目录（WSL）：`/mnt/c/Users/90646/Downloads/nature_dis/downloads/articles`
- 仓库内相对路径：`downloads/articles`（已被 `.gitignore` 忽略；所有派生大文件建议也写到 `downloads/` 内，避免推到 GitHub）

### B. 依赖与配置（待实现）

- 依赖：`langchain`（LCEL/Chains）、Gemini 适配器（如 `langchain-google-genai`）、`Pillow`、`pydantic`、（可选）`opencv-python`、`tenacity`、`tqdm`。
- 密钥：使用 `.env`（已忽略）提供 `GOOGLE_API_KEY`/`GEMINI_API_KEY`（以实际 SDK 为准），或使用 CLIProxyAPI 作为本地代理（推荐，见下），严禁把任何 key 写入仓库/日志。
- CLIProxyAPI 调用鉴权（入站 Bearer key）：默认优先读环境变量 `CLIPROXY_API_KEY`；若未设置则从 `CLIProxyAPI/config.yaml`（或 `CLIPROXY_CONFIG` 指定的 config）里的 `api-keys` 读取第一个。
- CLIProxyAPI 地址：默认优先读 `CLIPROXY_BASE_URL`；否则从 config 的 `port` 推断；再否则默认为 `http://localhost:8317`。
- 模型：Gemini **3.0 Flash**（以实际可用的 model id 为准；统一配置项 `MODEL_ID`）。
- 限流：并发数、QPS、重试与退避、缓存策略（见 E/F）。

### C. 目录扫描与“对应目录数据检查”（Preflight）

目的：不调 LLM，先把 `downloads/articles` 的真实结构扫描成 manifest，并检查每个 article/figure 目录下“该有的东西是否齐”。

- 扫描对象：
  - article-level：以“文章目录”为单位（如目录名/metadata 能反推出 `article_id`）。
  - figure-level：在文章目录内定位 figure 图片（`*.png/*.jpg/*.jpeg/*.tif/*.tiff`）。
- 检查项（记录缺失但不中断）：
  - `article_id` / URL / metadata（若存在）
  - figure 图片：尺寸(W,H)、文件大小、hash（用于缓存/去重）
  - caption：若目录中有 HTML/JSON/文本则抽取；否则标 `caption_missing=true`
  - Source Data：若目录中存在 `csv/xlsx/zip` 等，记录路径与大小；否则标 `source_data_missing=true`
- 产物（建议写到 `downloads/derived/`，保持 git 忽略）：
  - `downloads/derived/articles_manifest.jsonl`
  - `downloads/derived/figures_manifest.jsonl`
  - `downloads/derived/preflight_report.md`（缺失统计 + 样例）

### D. 子图分割（Subfigure / Panel Segmentation）

目标：对每张 figure 图输出 panels（bbox）并裁剪；同时给出每个 panel 的内容类型，便于筛选“数据可视化相关”。

1) 分割策略（建议：LLM 主导 + 本地后处理）
- 通过 LangChain 调用 Gemini Vision：输入 figure 原图（+可选 caption），输出 JSON：`panels[] = {panel_id, bbox, is_data_viz, viz_type, confidence}`。
- bbox 坐标约定：像素坐标，左上 (0,0)，`bbox=[x0,y0,x1,y1]`，必须在图像范围内。

2) 结构化输出（强制）
- 使用 Pydantic/JSON Schema 做校验；解析失败则进入“只修 JSON”的二次提示或失败队列。
- 要求按阅读顺序排序（A→B→C… 或 从左到右/从上到下）。

3) 后处理（本地）
- clip 越界 bbox；去重/合并重叠（必要时 NMS）；过滤过小框。
- 裁剪时做少量扩边（防止切掉坐标轴标签/legend）。

### E. “只保留数据可视化相关子图”的判定

- 统一 label：`viz_type`（line/bar/scatter/heatmap/box/violin/table/network/map/flow/other）+ `is_data_viz`。
- 建议两种模式（二选一，先从简单开始）：
  - **单次调用模式**：分割时直接输出 `is_data_viz`（成本低）。
  - **二段复核模式**：先分割得到 panels，再对每个裁剪 panel 复核 `is_data_viz`（更稳）。
- 边界策略：
  - 混合内容（照片+图表）默认保留但标 `mixed_content=true`。
  - 纯 legend/colorbar 面板默认不单独保留（可标 `aux_panel=true`）。

### F. 输出组织、缓存与断点续跑（建议）

- 输出目录（建议全部放 `downloads/derived/`，保持忽略）：
  - `downloads/derived/subfigures/{article_id}/{figure_id}/`
    - `panels.json`（最终 bbox + 分类 + 版本信息：`model_id`、prompt hash、时间戳）
    - `panel_A.png`, `panel_B.png`...（仅 `is_data_viz=true`）
    - `overlay.png`（可选：原图叠加 bbox，方便抽检）
- 缓存 key：`figure_hash + model_id + prompt_version`；若 `panels.json` 已存在且校验通过则跳过。
- 失败记录：`downloads/derived/errors.jsonl`（便于 `--only-failed` 重跑）。

### G. 并行、限流与稳健性（必须在计划里明确）

- LLM 调用必须限流（worker 数/QPS/token 预算）；本地裁剪/写盘可并行。
- 对 429/5xx 做指数退避重试；对超时/解析失败进入失败队列。
- 全流程可 `--dry-run`：只跑 Preflight 不调用 LLM。

### H. CLI 入口（当前已实现）

- Preflight（只扫描、不调 LLM）：`python -m tools.process_articles preflight --input downloads/articles --output downloads/derived --progress`
- 子图分割：`python -m tools.process_articles segment --backend cliproxy --model models/gemini-3-flash-preview --input downloads/articles --output downloads/derived --progress`
- 常用参数：`--limit`（默认 10，`0`=不限制）、`--resume`、`--save-overlay`、`--pad-px`、`--pad-frac`（防止切掉坐标轴/标签）、`--progress`、`--timeout-s`。

### I. 验收标准（DoD）

- preflight 产出 manifest/report，能回答“有哪些文章/有哪些 figure/缺了什么”。
- 抽检 N 张 figure：多 panel 分割基本不漏、不切轴；`is_data_viz` 过滤符合预期。
- 可重复、可断点续跑、失败可重跑；输出与输入一一可追溯（路径 + hash）。

---

## 0. 摘要（Executive Summary）

本 proposal 提出一个 **Code-First** 的自动可视化生成系统：输入表格数据与自然语言意图，**直接输出可执行的 Python（matplotlib 优先）绘图代码**。系统内部采用与 PDF 摘要一致的 **search–repair 闭环**：生成最小 patch → sandbox 渲染 → judge 评分/诊断 → 路由下一步，并将编辑决策组织在 **分层树 HCT（L1–L4）** 上，辅以 **共享约束 Γ（跨 panel 一致性）** 与 **带类型/时间戳的 pheromone 证据记忆** 来实现跨迭代、跨 panel 的稳定复用，显著提升 **Data Fidelity** 与 **Series Cohesion**。

同时，本方案把 pptx 中的 **REER（反推推理轨迹 + 局部搜索 + 迭代精炼）** 用在数据构建与训练：构造 **DeepPlot-XXK**（x: data-brief+指令+tables；y: canonical code；z*: REER 搜到的深推理轨迹；以及运行日志/PlotTrace/渲染图/judge 诊断）。训练采用 **三阶段（Code-only SFT → Repair/patch SFT → DPO/ORPO）**，可选训练路由器 **µθ**。系统在单卡 **H200 96GB** 场景下可现实落地（先 14B 跑通，后 32B QLoRA 冲上限）。

---

## 1. 研究目标与需求定义

### 1.1 输入（x）

系统统一输入信号（与 PDF 摘要描述对齐）：

1. **tables**：CSV/XLSX，多表可选（可包含 join key）。
2. **caption/abstract 或用户自然语言指令**：描述要表达的事实与图形意图。
3. **data-brief**（强制）：对表结构的摘要，用于稳定模型理解与校验。

**data-brief 推荐包含：**

* 每个表的：列名、类型（数值/类别/时间/文本/布尔）、缺失率、基数（unique count）、范围/分位数、潜在单位（从列名/元数据推断）、候选主键/外键、可疑异常值提示。
* 候选编码（candidate encodings）：可能的 x/y/color/facet 候选列集合与置信度。
* 多表关系：join 候选键、join 风险（多对多等）。

> 这套输入协议是所有系统共享的“共同地基”，避免各阶段数据解释漂移。

---

### 1.2 输出（y）

**只输出可执行 Python 绘图代码（matplotlib 优先）**

* 默认：**仅输出代码**（你要的“更自由”）。
* Debug 模式（可选）：允许输出 patch 日志或结构化诊断，但不强制输出 spec。
* 强制约束（建议默认）：

  * 不用 seaborn（除非你允许）。
  * 统一 `savefig()` 到指定路径。
  * 统一 rcParams / figsize / dpi（降低风格噪声，提高一致性与可比性）。

---

### 1.3 系统能力目标（Success Criteria）

1. **One-shot**：直接产出 **能跑**、**数据语义正确**、**可读性良好** 的绘图代码。
2. **Iterative repair**：若一发不完美，能借助 sandbox + judge + 记忆在有限预算内快速修到 publish-grade。
3. **Multi-panel 系列一致性**（重点）：同一 figure 下多 panel 在单位、刻度、palette、legend policy、字体、分辨率等方面保持一致（即 **Series Cohesion**）。

---

## 2. 总体系统架构（不输出 spec，但仍然可验证）

### 2.1 总体模块地图（组件全览）

无论你处于哪个阶段，最终系统由以下模块组成（差异在于“是否启用/复杂度”）：

1. **Data I/O + Data Brief**

   * 读取 CSV/XLSX，多表管理
   * 生成 data-brief（列类型、单位、缺失、候选编码等）

2. **Code Generator（code-first）**

   * 输入：instruction + data-brief +（可选）上次代码/错误/渲染图/诊断/记忆
   * 输出：完整可执行 Python 绘图代码（matplotlib）

3. **Sandbox Runner**

   * 固定环境执行代码（隔离、超时、限制 IO）
   * 保存 runtime signals：exceptions/stack trace、stdout/stderr、render artifacts（图片/元数据）

4. **Judge / Verifier**

   * 输出三类信号：

     * **Visual Form & Readability**（形式/可读性）
     * **Data-Grounded Fidelity**（数据一致性）
     * **Series Cohesion**（系列一致性，多 panel）
   * 同时输出结构化诊断 **Q**（告诉下一步修什么、去哪层修）

5. **Repair Loop（迭代修复）**

   * 使用 (runtime log + last render + diagnosis Q + constraints Γ + memory) 促使模型修复
   * 可先“整段重写”，再升级为“最小 patch δC”

6. **（进阶）HCT + Γ + pheromone + Router µθ**

   * **HCT（L1–L4）**：分层治理编辑空间
   * **Γ（全局约束）**：跨 panel 共享一致性规则
   * **pheromone 证据记忆**：把有效 patch/决策持久化复用
   * **Router µθ**：决定 stay/deeper/bubble-up/jump-root 的探索策略

---

### 2.2 内循环：Sense → Plan → Patch → Render → Judge → Route（代码为中心）

严格沿用你给的 PDF 摘要中的 node loop，只是**不显式产 spec**：

1. **Sense**：读取节点状态
   [
   s_v = (g(v), \Omega_v, H_v, \Xi_v, \Gamma)
   ]

   * **g(v)**：该节点的子目标/当前要修复的目标（例如“修 scale/统计”）。
   * **Ω_v**：该层允许操作的 action mask（“这层可以改什么、不能改什么”）。
   * **H_v**：历史摘要（过往 patch、运行日志摘要、分数变化轨迹）。
   * **Ξ_v**：局部上下文（当前 panel、data-brief 摘要、候选编码、上轮诊断 Q 的统计等）。
   * **Γ**：全局共享约束（palette/font/dpi/legend policy/units/scale 等）。

2. **Plan**：产生一个 altitude-consistent 行动

   * 只规划当前层允许的修改方向（例如 L3 只动统计与刻度，不碰布局）。

3. **Patch**：生成最小代码补丁 **δC**（不整段重写）

   * patch 是系统核心对象（与你给的 PDF 摘要一致）。

4. **Render**：sandbox 运行

   * 捕获 exceptions/stack traces
   * 保存渲染图（bitmap）与 metadata（例如 figsize/dpi）
   * 记录 runtime artifacts

5. **Judge**：输出

   * 分数 (J=(J_{\text{form}}, J_{\text{fid}}, J_{\text{coh}}))
   * 诊断 (Q)（结构化：问题类型、严重度、建议路由层级）

6. **Route**：Router µθ 决策下一步动作集合

   * ({\text{stay}, \text{deeper}, \text{bubble-up}, \text{jump-root}})

> **关键点**：闭环的中心始终是 **code/patch**；不要求先产 spec。

---

## 3. 不输出 spec 如何保证 fidelity：用“可执行证据 + 代码侧观测”替代显式 spec

### 3.1 PlotTrace：在 sandbox 中自动生成“隐式 spec”

你不要求模型输出 spec，但我们在执行时**自动抽取**一个结构化证据：`plot_trace.json`。

**PlotTrace 需要回答：**

* 最终用于绘图的列/数组来自哪些表/哪些列？
* 做了什么数据处理：filter、groupby-agg、sort、resample、rolling、log/标准化等
* 画了哪些几何对象：线/点/柱/箱线/直方/面积
* axis label、title、legend label、scale（log/linear）、单位字符串、facet/subplot 布局
* 图中系列数量（lines/bars）、每个系列的标签与数据长度

**实现方式（工程上简单可控）：**

1. **monkey-patch / wrapper**

   * 包装/钩住：

     * `pandas.DataFrame.plot`
     * `matplotlib.axes.Axes.plot / bar / scatter / hist / boxplot / imshow / fill_between ...`
   * 记录调用参数、输入数组形状、label、色彩/marker、轴设置等

2. **强制保存绘图前最终数据（plot_df dump）**

   * 在运行环境注入 helper：

     * `dump_plot_df(df, name="panel_A")`
   * 简化实现路径：

     * 约定模型在绘图前有 `plot_df = ...`（最小约束，不是 spec）
     * 或在 wrapper 中捕获传入数组并反向关联来源（高级可做，MVP 可先不用）

最终得到：

* `plot_trace.json`（结构化）
* `plot_df.parquet/csv`（可选但强烈建议，用于严格 fidelity）

> 这相当于“执行生成的 spec”，比“语言输出的 spec”更可信、更贴近真实执行。

---

### 3.2 Verifier（训练/筛选/评测）——不用 spec 也能严格打分

Verifier 只依赖 sandbox artifacts + PlotTrace/plot_df：

1. **Exec Pass（硬门槛）**

   * 能否运行成功
   * 是否触发异常/超时

2. **Data Fidelity（核心）**

   * 合成数据：有真值（我们知道应使用哪些列、怎么 agg/filter）
   * 对比方式：

     * PlotTrace 的列映射是否匹配真值
     * plot_df 与真值 df 的行数/统计量/关键序列是否一致（可容许数值误差）

3. **Series Cohesion（多 panel 核心）**

   * 检查 Γ：单位、刻度、palette、legend policy、grid、font 是否一致
   * 对齐策略：

     * 同类型轴共享同单位/scale
     * 共享 color mapping 的类别→颜色一致

4. **Visual Form & Readability**

   * 规则：

     * 缺失 title/xlabel/ylabel
     * tick 太密/重叠
     * legend 遮挡
     * 字体太小、线宽不合理、图像留白不足
   * 可选：VLM judge（把图片作为输入，输出更细的可读性诊断 Q）

> 对齐你给的 PDF 摘要：统一 sandbox 运行、记录异常与渲染 artifacts，由固定 Judge 给三个指标与诊断。

---

## 4. 把 pptx 的 REER 用起来：用于合成训练数据与推理轨迹（推理时仍只输出代码）

### 4.1 REER 三元组定义（不需要输出 spec）

* (x=(\text{tables}, \text{instruction/caption}, \text{data-brief}))
* (y=) **canonical high-quality plotting code**（标准答案代码：可跑、风格统一）
* (z=) “深推理轨迹/计划/自检痕迹”（训练时用，部署不输出）

目标保持 pptx 形式（你给的公式含义）：
[
z^*=\arg\min_z \text{PPL}(y \mid x, z)
]
用梯度无关的局部搜索：初始化 → 扩展/精炼 → 选择，反复迭代，让更深的推理轨迹使得 y 在模型下更可预测、更稳定。

**关键落地方式：**

* **训练阶段**：允许样本包含 z*（深推理），提升模型内部推理与错误规避能力。
* **部署阶段**：通过 prompt/stop tokens/输出约束实现 **code-only 输出**（不暴露 z）。

---

### 4.2 DeepPlot-XXK：Plot 领域的“DeepWriting-20K”同构数据集

每条样本至少包含：

* **x**：data-brief + 指令 + tables
* **y**：canonical code（风格统一、可复现）
* **z***：REER 搜索得到的深推理轨迹（可包含反思/迭代 patterns）
* **运行证据**：sandbox 执行日志、PlotTrace、渲染图、（可选）judge diagnosis

> pptx 的结论迁移：合成数据质量 + 迭代精炼/反思 tokens 往往是关键驱动；在 plot/code 任务中同样成立。

---

## 5. 数据构建策略（单卡友好）：合成优先，真实数据少量对齐

### 5.1 合成数据（主力，决定上限）

你需要一个 generator 生成：

1. **数据表**：覆盖真实论文/报表常见结构与坑

   * 时间序列：日/周/月、缺失、断点、异常峰
   * 分组对比：多类别、长尾、多层级类别
   * 分布：偏态、重尾、零膨胀
   * 多表：join（1-1、1-n、n-n 风险）、维表/事实表
   * 数据质量：缺失/重复键/编码混乱/单位混合

2. **指令（instruction）**：覆盖任务意图

   * 趋势：trend、rolling、同比/环比
   * 对比：group comparison、top-k、排序
   * 分布：hist/box/violin（可选）
   * 相关：scatter + 回归线/相关系数（可选）
   * 组成：stacked / 100% stacked / area（可选）
   * 统计要求：mean/sum/median/CI/top-k/log/normalize

3. **canonical code（标准答案）**

   * 统一风格（rcParams、figsize、dpi）
   * 统一保存路径
   * 强制可复现（固定 seed、固定版本）
   * 强制产出 PlotTrace/plot_df（用于严格 fidelity）

**合成数据的优势：**

* Fidelity 有真值可对齐，DPO/筛选干净
* 可强覆盖真实数据常见坑：单位/scale/cohesion/multi-panel policy
* 便于做系统性消融与回归评测

---

### 5.2 真实数据（小量但高价值）

少量真实数据用于对齐“publication-grade”要求（尤其 multi-panel cohesion）：

* tables + published figure + caption/abstract + panel split（若可获得同类数据）
* 重点用途：

  * 检验 Γ（跨 panel 一致性）是否满足真实审稿标准
  * 检验可读性（Form）细节：字体、留白、legend、标注

---

## 6. 训练方案（H200 96GB 可落地）：三阶段 + 可选 Router

### 6.1 模型选择（PlotCoder-Base）

给你两条清晰路线（与你草案一致）：

**路线 1（推荐上限更稳）**：`Qwen2.5-Coder-32B-Instruct + QLoRA 4bit`

* code-edit/patch 更稳
* 长上下文更可靠
* 96GB 内可训 LoRA adapter（需配合 checkpointing/小 batch）

**路线 2（先跑通系统）**：`Qwen2.5-Coder-14B-Instruct + LoRA/QLoRA`

* 迭代更快、工程闭环先稳定
* 闭环稳定后迁移到 32B 冲上限

> 最安全策略：先 14B 跑通闭环与评测，再无痛迁移到 32B（数据与训练脚本一致）。

---

### 6.2 Stage A：Code-Only SFT（one-shot 生成）

**训练样本：**

* Input：instruction + data-brief + 表路径/表结构
* Output：完整 python 绘图代码（只给 code，不强制 spec）

**关键训练约束：**

* 强制 matplotlib
* 统一 rcParams/figsize/savefig
* 强制 “最后保存图 + dump plot_trace + dump plot_df”（这是运行证据，不是 spec）

---

### 6.3 Stage B：Repair-SFT（学习最小 patch δC）

核心：让模型学会在闭环里 **“最小修改”**。

**样本来源：rollout 轨迹**

* Input：当前 code + runtime error + 上次渲染 artifact（可选）+ judge diagnosis Q + 约束 Γ
* Output：最小 patch δC（diff 或替换片段）

> 这一步通常比 Stage A 更决定系统“能用程度”：很多系统输在不会修、不会收敛。

---

### 6.4 Stage C：DPO/ORPO（用 verifier 做偏好对齐）

对同一状态采样多个候选 patch/code：

* winner：exec pass 且 Fidelity 更高、Cohesion 更好、Form 更好
* loser：单位/scale/聚合错误、跨 panel 不一致、可读性差

用 DPO/ORPO 做离线偏好优化（单卡友好，不需要在线 RL）。

---

### 6.5 Router µθ（可选但对 multi-panel 很有收益）

你给的 PDF 摘要里 µθ 读取 state（包含 level/altitude、Ω mask、Q typed counts、Γ 等）并决定动作：stay/deeper/bubble-up/jump-root。
落地建议：

1. 先用 **规则 Router（足够强且可控）**：

   * diagnosis=scale/unit/statistics → L3
   * diagnosis=readability → L4
   * diagnosis=layout/subplot organization → L1/L2
2. 闭环稳定后再训练 µθ：

   * offline behavior cloning（从 logged rollouts 学）
   * 再做 KL-regularized policy gradients（可选）

---

## 7. HCT 分层治理 + Γ 全局约束（不输出 spec 也能严格可控）

### 7.1 HCT（L1–L4）定义与允许操作（Ω_v）

把编辑空间拆成四层，避免“乱改”：

* **L1：Chart family / Layout（全局布局）**

  * subplot 网格、panel 数、整体布局策略、主标题
* **L2：Encodings / Mapping（编码映射）**

  * x/y/color/facet/size 的选择与映射、legend 分组策略
* **L3：Scales & Statistics（统计与刻度）**

  * 聚合（groupby-agg）、归一化、log/linear、resample/rolling、单位处理
* **L4：Readability & Annotation（可读性与标注）**

  * axis label、tick 密度与格式、legend 位置、注释、网格线、字体大小

每层通过 **Ω_v** 限制可改区域：

* L3 不允许动布局与 subplot 数
* L4 不允许改统计与列选择
* ……（按你的 rubrics 固化）

---

### 7.2 Γ（Global Constraints）——跨 panel 共享一致性

Γ 由上层（L1/L2）维护并向下传播，建议至少包含：

* palette / color mapping（类别→颜色）
* font family / font size policy
* dpi / figsize policy
* grid / spine policy
* legend policy（共享 legend vs 每 panel 一个、位置规则）
* unit policy（同类量同单位、转换规则）
* scale policy（同类轴共享 log/linear）

---

## 8. Pheromone 证据记忆（你要“效果好”的硬条件）

你给的 PDF 摘要明确指出：**去掉 typed/time-stamped pheromone links 会对 Data Fidelity 与 Series Cohesion 造成最大降幅**。因此该组件必须落地。

### 8.1 Pheromone link 的结构（存什么）

每次成功 step 写入一条 pheromone link：

[
r_t=(v_t, h(v_t), \kappa_t, \Delta J_t, \delta C_t, M_t)
]

* **v_t**：产生该 patch 的节点
* **h(v_t)**：节点哈希/摘要（与任务/面板/上下文绑定）
* **κ_t**：证据类型（typed）

  * `constraint`（单位/scale/统计决策）
  * `style`（字体/palette/legend policy）
  * `geom`（几何对象/mark 类型）
  * `layout`（subplot/grid）
  * `ref`（可复用 patch 模板/示例）
* **ΔJ_t**：该 patch 带来的分数增量
* **δC_t**：最小补丁内容
* **M_t**：附带证据（PlotTrace 片段、render 截图指纹、关键日志摘要等）

### 8.2 记忆管理

* **TTL + score eviction**：基于时效与收益保留高价值证据，淘汰低价值/过期证据
* **检索策略**：

  * 按 `κ_t` 类型过滤
  * 按 panel/任务类型（趋势/对比/分布）过滤
  * 按 data-brief 相似度或关键词（列名、单位、chart family）检索

### 8.3 ST-Hyperlinks（跨 panel 传播）

做多 panel 时，最需要的是把 Γ 与关键约束在 panel 间同步传播（“单位/scale/palette 一次修好全局复用”）。

---

## 9. Baseline 定义（后续所有改进的参照系）

你要求“一个 baseline”，并且与 PDF 框架对齐。我建议把 baseline 定义为：

### 9.1 主 baseline：Flat Iterative Self-Repair（扁平迭代自修复）

> 一次生成 code → sandbox 运行 → 把 runtime error + last render snapshot（可选）+ judge diagnosis 喂回去 → 同一个 coder 模型重写/更新 code → 循环 K 次。
> 不做 HCT，不做 pheromone，不做跨 panel memory。

这正对应你草案里提到的 iterative baseline：额外消费 runtime errors、last render snapshot、VLM/规则 judge diagnosis 来 self-revise，但**没有跨 panel 记忆**。

---

### 9.2 Baseline 必须实现的功能（最小闭环）

* 输入：tables + instruction + data-brief
* `gen_code()`：生成完整 python 代码
* `sandbox_run(code)`：执行并返回 (ok/err, logs, render_path)
* `judge(render, logs)`：输出 score + diagnosis Q
* `repair_prompt(prev_code, logs, render, Q)`：生成更新后的 code
* 最大迭代轮数 K：达到阈值或无提升停止

---

### 9.3 Baseline 输入/输出协议（建议固定，便于消融）

**输入协议**

```json
{
  "instruction": "...",
  "tables": [{"name": "...", "path": "..."}],
  "data_brief": {},
  "constraints": {
    "must_use": "matplotlib",
    "forbid": ["seaborn"],
    "output_path": "out.png"
  }
}
```

**输出协议**

```json
{
  "final_code": "...",
  "artifacts": {
    "render_path": "...",
    "runtime_log_path": "...",
    "history": [
      {"iter": 0, "code": "...", "score": {}, "diagnosis": {}},
      {"iter": 1, "code": "...", "score": {}, "diagnosis": {}}
    ]
  }
}
```

---

### 9.4 论文/实验对照组（至少 3 条，都是 code-first）

1. **Gen-only baseline**：只生成一次代码就结束
2. **Iterative baseline（主 baseline）**：flat self-repair，无 cross-panel memory
3. **Template baseline（可选）**：按 chart family 用固定模板拼装（用于证明不是模板取胜）

之后你的方法逐步加：minimal patch、HCT、Γ、pheromone、learned routing µθ。

---

## 10. 分阶段路线图（每个阶段实现哪些功能）

> 下面是你草案里的阶段 0–8，我把“目标/实现功能/产物（验收点）”全部保留并组织为工程可执行路线图；所有阶段保持 **code-first（不先输出 spec）**。

---

### 阶段 0：可复现执行环境 + 数据入口（地基）

**目标**：任何绘图代码都能稳定运行、记录、复现。

**实现功能**

* 固定 python/pandas/matplotlib 版本（建议 docker）
* Sandbox Runner：执行、超时、隔离、产出 artifacts
* 统一落盘：render bitmap + metadata、异常栈、stdout/stderr
* Data Brief 生成器：列类型、缺失率、单位推断、候选编码

**产物（验收）**

* 任意 100 段 matplotlib 脚本都能稳定跑，artifacts 完整可回放

---

### 阶段 1：Gen-only（单次生成代码）— 最弱基线

**目标**：先有一个“能画出来”的系统（不保证对）。

**实现功能**

* prompt 模板：instruction + data-brief → 直接输出完整代码（code-only）
* 单次 `gen_code()` → `sandbox_run()`
* Judge 先做最小规则：

  * exec pass/fail
  * 是否有 title/xlabel/ylabel、是否 savefig

**产物**

* Exec pass rate（能跑起来的比例）

---

### 阶段 2：Flat Iterative Self-Repair（主 baseline）

**目标**：具备“出错能自修复”的能力（先不引入 HCT/记忆/路由）。

**实现功能**

* 迭代 loop：生成 → 跑 → 评 → 修 → 再跑（K 轮）
* 诊断 Q 结构化（先规则标签化）：

  * `runtime_error`
  * `missing_labels`
  * `scale_suspect`
  * `unit_inconsistent`
  * `too_many_categories`
  * `legend_overlap`
  * ……

**产物**

* 稳定 baseline：固定数据集上可复现平均 exec pass、平均分、平均迭代轮数

---

### 阶段 3：把 Judge 做“可衡量”——三指标骨架（先规则、后 VLM）

**目标**：评测稳定，否则训练与迭代会“瞎跑”。

**实现功能**

* **Data Fidelity（规则版）**

  * 合成数据：严格对齐真值
  * 真实数据：弱规则 + 抽检
* **Series Cohesion（多 panel）**

  * 单位、刻度、legend policy、palette 一致
* **Visual Form**

  * tick 密度、label 缺失、legend 遮挡、字体过小等规则
  * 可选 VLM judge

**产物**

* 一个能自动打分 + 结构化诊断 Q 的 judge/verifier

---

### 阶段 4：引入最小补丁 δC（从重写 → patch）

**目标**：修复更稳定、更可复用、更可审计。

**实现功能**

* Patch 表示：

  * unified diff 或“代码块替换 edit script”（推荐后者，鲁棒）
* Patch Applier：`apply_patch(C, δC) -> C'`
* 记录每一步 patch（为 pheromone 铺路）

**产物**

* 修复轨迹由 `C0,C1,C2...` 变为 `C0 + δC0 + δC1...`
* 可统计：高频 patch 类型、有效性分布

---

### 阶段 5：上 HCT（分层治理）+ Γ（全局约束）+ 规则路由

**目标**：避免全局/局部反复乱改；让修复路径更可控。

**实现功能**

* HCT 数据结构（L1–L4）
* 每层 rubrics / Ω_v：

  * L1：chart family/layout/panel arrangement
  * L2：encodings/subplots mapping
  * L3：scales/statistics（聚合、log、resample、单位）
  * L4：readability（ticks、label、legend 位置）
* 规则 Router：

  * scale/unit/stat → L3
  * readability → L4
  * layout → L1/L2
* Γ 在所有 panel 共享并向下传播

**产物**

* 迭代更“按问题类型去对层修”，收敛更稳

---

### 阶段 6：上 pheromone（持久化证据）— 关键增益点

**目标**：把“修对一次”的单位/尺度/legend policy 跨 panel 复用，降低回归。

**实现功能**

* 存储 pheromone link：(r_t=(v_t,h(v_t),\kappa_t,\Delta J_t,\delta C_t,M_t))
* TTL+score eviction
* 检索与继承：修复前检索相关 pheromone 注入 prompt/state
* ST-Hyperlinks（简化版先做）：跨 panel 同步 Γ/constraint

**产物**

* Multi-panel 的单位/刻度一致性显著提升，回归减少

---

### 阶段 7：学习路由 µθ（可选但建议）

**目标**：减少无效探索，提高预算效率。

**实现功能**

* 收集 logged rollouts（已有 patch+ΔJ+Q）
* 训练小 policy（MLP 也可）输出 {stay,deeper,bubble-up,jump-root}
* 训练策略：先 BC，再 KL-regularized policy gradients（可选）

**产物**

* 固定预算下更少迭代、更高平均 ΔJ

---

### 阶段 8：训练模型（从“能跑 baseline”到“强模型”）

**目标**：把能力固化进参数，尤其 patch 修复与统计/尺度决策。

**实现功能（推荐顺序）**

1. Codegen-SFT（one-shot 更强，减少迭代）
2. Patch-SFT（学习 δC）
3. DPO/ORPO（用 verifier 选 winner/loser）
4. （可选）REER 风格数据增强：训练用 z*，部署仍 code-only

---

## 11. 一个“可完整运行”的工程蓝图（repo 结构 + MVP）

### 11.1 repo 结构（与你草案一致，完整保留）

```text
code_first_pheroreer/
  env/
    Dockerfile                # 固定 python/pandas/matplotlib 版本
    requirements.txt
  data/
    synth/                    # 合成数据 & canonical code
    rollouts/                 # rollout轨迹（code, patch, logs, scores）
  src/
    brief/
      make_data_brief.py      # types/units/candidate encodings
    sandbox/
      runner.py               # 执行代码、捕获log、保存图
      trace_hooks.py          # PlotTrace 采集（matplotlib/pandas wrapper）
    judge/
      verifier.py             # exec pass + plot_trace fidelity + cohesion
      judge_vlm.py            # 可选 VLM judge
    memory/
      pheromone_store.py      # 写 r_t, TTL+score eviction
      constraints.py          # Γ 的维护与合并
    hct/
      tree.py                 # HCT 节点结构
      router_rules.py         # 规则版 µθ
      router_train.py         # 可选训练 µθ
    model/
      gen.py                  # code生成
      patch.py                # patch生成（diff）
  train/
    01_make_synth.py
    02_collect_rollouts.py
    03_sft_codegen.py
    04_sft_patch.py
    05_dpo_patch.py
  eval/
    eval_single.py
    eval_multipanel.py
```

### 11.2 MVP（最小可行实现）的功能边界

* 不做 VLM judge：先做 deterministic verifier（exec + PlotTrace fidelity + cohesion）
* 不训练 µθ：先用规则路由
* 先训练 14B（或先不训练，只把闭环跑通）

---

## 12. H200 96GB 训练默认配置（可直接用作起点）

> 这里给的是“不会离谱”的默认起点；你可以基于实际显存/吞吐微调。

### 12.1 32B QLoRA（推荐最终版）

* 4-bit NF4 quant
* bf16
* LoRA：r=16 或 32，alpha=32/64，dropout=0.05
* seq_len：先 4096，再升 8192（repair 很吃上下文）
* micro-batch：1～2 + grad_accum
* gradient checkpointing：开启
* lr：1e-4（LoRA 常见量级）+ warmup 3%

### 12.2 14B（快速验证闭环）

* 同上，但 seq_len/batch 可更宽松

---

## 13. 评测与“效果好”的定义（与 PDF 三指标对齐）

### 13.1 三指标（Judge 输出）

1. **Visual Form & Readability（J_form）**

   * 规则：label/ticks/legend/字体/遮挡
   * 可选 VLM：更细粒度可读性诊断

2. **Data-Grounded Fidelity（J_fid）**

   * 核心依赖 PlotTrace/plot_df 与真值对齐（合成数据最严格）

3. **Series Cohesion（J_coh）**

   * 多 panel 时检查 Γ 一致性（单位/scale/palette/legend policy 等）

> 单图任务可将 cohesion 置为 N/A，但系统要从一开始就支持 Γ 的概念，为 multi-panel 做准备。

### 13.2 统一 sandbox 与运行信号

所有评测都必须在同一 sandbox 里跑，并记录：

* runtime errors/stack trace
* render artifacts（png/svg 等）
* PlotTrace/plot_df
* judge diagnosis Q

---

## 14. LangChain/LangGraph 落地方案（用于编排闭环，而非替代 sandbox）

你草案里强调用 **LangChain（LangGraph）** 做循环 workflow，我把“定位/要用到的能力/baseline 图结构/阶段映射/伪代码/关键提醒”全部保留并整理为一个可执行设计。

### 14.1 LangChain 在这里的定位（四类能力）

1. **编排（Orchestration）**：用 LangGraph 把多步循环和条件跳转组织成 State/Nodes/Edges。
2. **工具（Tools）**：把 sandbox_run/judge/profile_data 等封装成工具函数（节点里调用）。
3. **结构化输出（Structured Output）**：让 LLM 输出可解析对象（patch JSON、路由决策），避免脆弱字符串解析。
4. **可观测与评测（Observability/Evals）**（可选）：用 tracing/evals 记录每一步输入输出与分数变化，用于回归分析。

> 注意：LangChain 负责**编排**，真正的代码执行必须走你自己的隔离 sandbox。

---

### 14.2 LangGraph baseline：Flat Iterative Self-Repair（4 节点够用）

**Baseline 定义**（与上文一致）：

* 生成代码 → sandbox 运行 → judge 诊断 → repair → 循环 K 次。

#### (A) 建议 State（字段全量）

* `instruction: str`
* `tables: list[TableRef]`（路径、表名）
* `data_brief: dict`
* `code: str`
* `iter: int`
* `max_iter: int`
* `run_ok: bool`
* `runtime_log: str`
* `render_path: str | None`
* `score: dict`（form/fid/coh 或 total）
* `diagnosis: dict`（结构化 Q）
* `done: bool`

#### (B) Nodes（4 个）

1. `generate_code_node(state) -> update`
2. `sandbox_run_node(state) -> update`
3. `judge_node(state) -> update`
4. `repair_node(state) -> update`

#### (C) Edges（条件跳转）

* START → generate → run → judge
* judge → 如果 `done=True` 或 `iter>=max_iter` → END
* judge → 否则 → repair → run → judge → …

---

### 14.3 分阶段与 LangChain 的对应关系（完整保留）

* 阶段 0：把 sandbox_run/make_data_brief/judge(规则版) 做成 Tools/节点
* 阶段 1：Gen-only：`prompt | llm | parser` 放进 graph 或直接跑
* 阶段 2：baseline 循环：LangGraph 的条件边实现循环
* 阶段 3：最小 patch：用 structured output（Pydantic/JSON schema）产 patch，再 apply_patch
* 阶段 4：三指标 judge：工具节点升级；可选接 VLM judge
* 阶段 5：HCT：主图路由 + L1/L2/L3/L4 子图（subgraph）更合适
* 阶段 6：pheromone：在 repair 前加 `retrieve_memory_node`，state 加 `gamma_constraints/retrieved_pheromones`
* 阶段 7：µθ：替换规则路由为学习路由
* 阶段 8：训练：不影响 LangGraph 编排，只影响节点里调用的模型版本/适配器

---

### 14.4 baseline 伪代码骨架（保留你草案语义）

```python
# 概念伪代码：LangGraph baseline（flat iterative self-repair）

# State: {instruction, data_brief, code, iter, max_iter, runtime_log, render_path, diagnosis, done}

def generate_code_node(state):
    code = llm_invoke(prompt_for_codegen(state["instruction"], state["data_brief"]))
    return {"code": code}

def sandbox_run_node(state):
    ok, log, render_path = sandbox_run(state["code"])
    return {"run_ok": ok, "runtime_log": log, "render_path": render_path}

def judge_node(state):
    score, diagnosis = judge(render_path=state["render_path"], runtime_log=state["runtime_log"])
    done = score["total"] >= THRESH or state["iter"] >= state["max_iter"]
    return {"score": score, "diagnosis": diagnosis, "done": done}

def repair_node(state):
    new_code = llm_invoke(prompt_for_repair(
        code=state["code"],
        runtime_log=state["runtime_log"],
        render_path=state["render_path"],
        diagnosis=state["diagnosis"],
        data_brief=state["data_brief"],
    ))
    return {"code": new_code, "iter": state["iter"] + 1}

def route_after_judge(state):
    return "end" if state["done"] else "repair"
```

---

### 14.5 关键提醒（保留且强调）

不要把 LangChain 社区里常见的 `PythonREPL` 工具当你的 sandbox。
你这个任务属于“模型写代码并执行”，安全风险更高，必须使用你自己的隔离执行环境（docker/沙箱），然后把它包装成 tool/node 给 LangGraph 调用。

---

## 15. “不要 spec”反而更强的原因（完整保留你的论点）

1. 你的 PDF 框架本来就以 **code/patch** 为中心：node loop 的产物是 minimal patch，记忆里存的也是 patch 与约束。
2. spec-first 的主要价值是“可验证”，但我们用 **PlotTrace/plot_df dump（可执行证据）** 替代，且更贴近真实执行。
3. 对 coder 模型来说，直接学习 code 分布更自然；配合 repair/patch 数据，泛化更好、更稳。

---

## 16. 推荐的“最稳迭代顺序”（完整保留）

如果只记一个顺序，就记这个：

1. **Baseline（flat iterative）跑通**
2. **Judge 可衡量**（至少 exec + fidelity 可计算部分）
3. **最小补丁 δC**（从重写切到 patch）
4. **HCT + Γ**（分层治理 + 跨 panel 约束）
5. **pheromone**（把修复固化成证据，最大增益点）
6. **训练 patch 模型 / 训练 µθ**（把系统从规则/提示变成可学习）

---

## 17. 立即可执行的下一步（与你草案一致，但不依赖 spec）

你草案里最后建议的 3 件事，我保持不变（并把交付物说清楚）：

1. **定义 PlotTrace 采集协议（JSON schema）**

   * 明确记录字段：列映射、变换、几何对象、轴/legend 设置、subplots 信息
   * 这样 fidelity 可以自动算，不依赖模型自述

2. **给合成数据 generator 一套“像论文数据而不是玩具”的参数分布**

   * 覆盖单位混合、缺失、长尾、多表 join、异常值等
   * 同时产出 canonical code + 真值 PlotTrace/plot_df

3. **先以 14B 跑通 Stage A+B（codegen + patch）**

   * 在闭环与评测稳定后，再切 32B QLoRA 冲上限
   * 迁移成本低，因为数据/评测/闭环一致

---

## 18. 场景适配（不问你问题，直接给两套可并行的配置差异）

你草案末尾提到两类目标场景的差异，我在 proposal 里直接给出“分布与 Γ 的差异点”，你可直接选用：

### 18.1 偏“论文图复现 / Nature 风格”

* 数据分布：更多 multi-panel、更多单位/尺度严谨要求、更多统计注释（CI、显著性）
* Γ 更严格：字体、线宽、留白、legend 规范、颜色可打印性（灰度可分辨）
* Judge 更强调：cohesion + 可读性细节（tick formatting、panel 标号、注释）

### 18.2 偏“BI/业务报表”

* 数据分布：更强调 top-k、过滤器、交互式逻辑（但你这里先做静态图）
* Γ 更强调：一致模板、品牌色、可解释标签、标题信息密度
* Judge 更强调：信息密度与可读性（避免过多系列、标签溢出）

> 两者都不需要回到“先输出 spec”；差异主要落在合成数据分布与 Γ 约束上。

---

## 附录 A：建议的 Patch schema（结构化输出，不等同于 spec）

> 用于 repair 节点输出 δC，避免字符串解析；对外仍只输出最终 code。

```json
{
  "patch_type": "replace_block",
  "target_block": "imports | data_prep | plot | style | save",
  "replacement_code": "....",
  "rationale": "optional short reason",
  "constraints_respected": ["L3_only_stats", "keep_palette"]
}
```

---

## 附录 B：建议的 Diagnosis Q taxonomy（用于路由与修复模板）

```json
{
  "issues": [
    {"type": "runtime_error", "severity": 3, "evidence": "stack_trace_hash"},
    {"type": "scale_suspect", "severity": 2, "axis": "y", "suggested_level": "L3"},
    {"type": "unit_inconsistent", "severity": 2, "suggested_level": "L3"},
    {"type": "legend_overlap", "severity": 1, "suggested_level": "L4"},
    {"type": "missing_labels", "severity": 1, "suggested_level": "L4"},
    {"type": "layout_wrong", "severity": 2, "suggested_level": "L1"}
  ],
  "summary": "short",
  "recommended_route": "L3"
}
```

---

## 附录 C：参考链接（按系统约束放在代码块中）

```text
LangGraph Graph API overview:
https://docs.langchain.com/oss/python/langgraph/graph-api

LangChain Structured Output:
https://docs.langchain.com/oss/python/langchain/structured-output

LangSmith Observability:
https://www.langchain.com/langsmith/observability
```

---

如果你接下来希望我“继续把方案补齐到可直接开工的程度”，最能立刻提升落地质量的补充是两份清单（不改变你对外 code-only 输出）：

1. **PlotTrace JSON schema 的字段级定义 + 评分计算方式**（怎样从 trace/plot_df 计算 fidelity/cohesion）。
2. **Diagnosis Q → 修复模板（patch skeleton）对照表**（每类问题在 L1–L4 哪层修、允许改哪些块、常见 patch 范式）。
