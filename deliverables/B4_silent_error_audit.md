# B4 — 歧义变换 Silent Error Audit

> **当前主线**：歧义算子语义 → LLM 静默失败 → goldless oracle 检出  
> 早期"注入绘图错误"实验保留于文末附录。

---

## §1 核心问题

**Silent Semantic Error（静默语义错误）**：LLM 生成的代码可执行、输出结构合理（形状、类型、列名均对），但**变换的语义是错的**——执行 wrong operation（如全局 z-score 替代组内 z-score、pct 计算分母错误等）。人眼无法从输出 DataFrame 单独判断，需要知道预期变换的语义。

**关键特征**：
- 代码 `exec-pass = True`
- 输出 shape / dtype 合法
- 值在合理数值范围内
- 同一 LLM 被要求"check your output"时通常认为"correct"
- 换同一个 LLM 生成 K 次，K 次均犯同一个错（common-mode failure）

---

## §2 实验 1：歧义校准——Silent Rate 定量测量

### 2.1 设计

**Benchmark**：48-grid（核心 12 类算子 × 4 instance），每 case 两条提示：
- **模糊提示（ambiguous）**：不指定分母/窗口/ddof 等语义歧义点
- **澄清提示（clarified）**：明确说明算子精确语义

每条提示 → LLM 生成代码 → 执行 → goldless oracle 检验 → silent or correct

**模型**：gpt-5.4 + claude-sonnet-4.6（各 96 次 = 48 cases × 2 conditions）

### 2.2 结果

| 提示类型 | Cases | Silent 数 | Silent 率 | 95% Wilson CI |
|---------|------:|:---------:|:---------:|:-------------:|
| 模糊（ambiguous） | 96 | 44 | **46%** | [36%, 56%] |
| 澄清（clarified） | 96 | 12 | **12%** | [7%, 21%] |
| **降幅（Δ）** | — | — | **−34 pp** | — |

**Oracle 性能**：Recall 56/56 = 100%，FP 0/135 = 0%（Clopper-Pearson [0%, 3%]）

### 2.3 Oracle 盲区：`zscore_within_group` ddof 问题

**发现**：oracle 对 `zscore_within_group` 存在一个已知盲区。

当 LLM 使用 `ddof=1`（Bessel 校正，pandas 默认）而非 `ddof=0`（NumPy 默认）时，两种写法都满足"per-group mean(z) ≈ 0"的不变量，oracle 无法区分。

**分析验证**（3 组，每组 3 条）：
- ddof=0（gold）：每组 z-scores = [-1.225, 1.225, 0.000]，per-group mean = 0
- ddof=1（LLM 错误）：每组 z-scores = [-1.000, 1.000, 0.000]，per-group mean = 0

两者 per-group mean 均为 0，现有不变量无法分辨。

**影响范围**：2/68 = 2.9% 的 cases（`zscore_within_group#1 × {gpt-5.4, claude-sonnet-4.6}`），仅在"澄清"条件下出现（澄清提示未显式指定 ddof）。

**处置决策**：记录为 oracle limitation（见 `task/transform_thesis_proposal_v2.md` §5），不修复。原因：
1. 仅影响 2/68 cases，不影响核心 12 类主张
2. 修复需要 ddof 感知不变量（如 `var(z) ≈ (N-1)/N` vs `1`），超出当前契约表达力

### 2.4 按算子类别分析

| 算子类别 | 模糊 silent | 澄清 silent | oracle 盲区 |
|---------|:-----------:|:-----------:|:----------:|
| zscore_global | 4/8 = 50% | 0/8 = 0% | 无 |
| zscore_within_group | 4/8 = 50% | 2/8 = 25% | ddof |
| pct_point vs pct_group | 8/8 = 100% | 0/8 = 0% | 无 |
| dedup_keep_first/last/min | 12/24 = 50% | 2/24 = 8% | 无 |
| rank_asc/desc | 8/16 = 50% | 4/16 = 25% | 无 |
| pivot | 4/8 = 50% | 2/8 = 25% | 无 |
| median_group | 4/8 = 50% | 2/8 = 25% | 无 |
| cumsum_group | 0/8 = 0% | 0/8 = 0% | 无（低歧义） |

**最高风险类别**：`pct_point vs pct_group`（模糊提示下 100% silent 率）——"计算百分比"这一表述在中文科学文本中语义最为模糊。

---

## §3 实验 2：5 检测器并排（见 B2 详细版）

**摘要**：在同一批 57 个 silent error + 132 个 correct 上：

| 检测器 | Recall | FP Rate | F1 |
|--------|:------:|:-------:|:--:|
| **Ours（oracle）** | **100%** | **0%** | **1.000** |
| self-check | 61% | 40% | 0.483 |
| exec-pass / validity / consistency | 0% | 0% | 0.000 |

**Common-mode 证据**：`pct_point/dedup/median` 类别上，consistency K=3 生成全部犯同一错误，多数票与错误答案一致，故 consistency recall = 0%。

---

## §4 实验 3：真实 Nature 数据（841 任务/71 论文）

| 指标 | 值 | 95% CI |
|------|:--:|:------:|
| 模糊 silent 率 | 77% (1296/1682) | [75%, 79%] |
| 澄清 silent 率 | 10% (175/1682) | [9%, 12%] |
| Oracle Recall | 98% (1438/1471) | [97%, 98%] |
| Oracle FP | 0% (0/211) | [0%, 1%] |

**与合成数据对比**：真实 Nature 任务 silent 率（77%）显著高于合成网格（46%），说明真实科学描述中的语义歧义远超精心设计的合成 benchmark。

---

## §5 复现命令

```bash
# 歧义校准实验（合成 48-grid）
python eval/ambiguity_calibration.py --bench --out results_ambcal_bench

# 快速 oracle 检验（无 LLM API）
python eval/baseline_compare.py --quick

# 完整 5 检测器对比（需 API）
python eval/baseline_compare.py --model gpt-4.1-mini
```

---

---

## 附录：早期绘图实验——PlotTrace 注入审计

> 以下内容属于项目早期"绘图保真"阶段，核心问题是"图表是否画错数据"而非"变换语义是否正确"。保留供参考。

### A.1 实验设计

**核心问题**：图表生成后，如何判断数据是否被正确绘制？

**实验**：对清洁图表注入 **单一静默数值错误**，测试各 judge 能否检测。

**被测试的 Judge**：

| Judge | 原理 |
|-------|------|
| 列名启发式（Col-name） | 仅检查列名是否存在 |
| SVG/VisEval | 逆向渲染 SVG 几何 → 反向推断值 |
| **PlotTrace（Ours）** | Hook matplotlib → 读取实际传入的数组 |

**注入的 4 种错误类型**：`wrong_value`, `scale_series`, `drop_series`, `swap_categories`

### A.2 检测召回率

| 错误类型 | Col-name | SVG/VisEval | **PlotTrace** |
|----------|----------|-------------|---------------|
| wrong_value | 0% | 100% | **100%** |
| scale_series | 0% | 100% | **100%** |
| drop_series | 0% | 100% | **100%** |
| swap_categories | 0% | 100% | **100%** |
| **Overall** | **0%** | **100%** | **100%** |

### A.3 定位精确度

| 错误类型 | SVG/VisEval | **PlotTrace** |
|----------|-------------|---------------|
| wrong_value | 3/4 (75%) | **4/4 (100%)** |
| scale_series | 3/4 (75%) | **4/4 (100%)** |
| drop_series | 1/2 (50%) | **2/2 (100%)** |
| swap_categories | 3/4 (75%) | **4/4 (100%)** |
| **Overall** | **71%** | **100%** |

SVG/VisEval 倾向于"泛洪"——把所有点都标记为异常。

### A.4 误报率（清洁图表）

| 指标 | Col-name | SVG/VisEval | **PlotTrace** |
|------|----------|-------------|---------------|
| False alarms | 0/4 | **3/4** | **0/4** |
| Mean fidelity | 0.75 | 0.25 | **1.00** |

### A.5 结论

**PlotTrace 是早期唯一三维最优的 judge**：100% 检测 + 100% 定位 + 0 误报。渲染后逆向（SVG/VisEval）可检测但精度不足，且噪音误报多。

```bash
python eval/silent_error_audit.py   # 复现命令
```
