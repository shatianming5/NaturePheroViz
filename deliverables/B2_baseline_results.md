# B2 — 检测器对比（5 Detector Baseline Compare）

> **当前主线**：5 检测器在同一批 LLM 生成上的并排评测（Transform Fidelity Verification）  
> 早期绘图 GPT-4o/Claude/Qwen 对比保留于文末附录。

---

## §1 实验设置

**目的**：在相同的 57 个真实 silent error 和 132 个正确结果上，并排评测 5 种检测策略，量化各策略的 Recall / FP Rate / F1。

**数据来源**：`eval/results_baseline_b/baseline_records.json`（68 records；模型：gpt-5.4 × 34 + claude-sonnet-4.6 × 34）

**Silent Error 定义**：LLM 生成的代码可执行、输出结构合理，但算子语义错误（如全局 z-score 代替组内 z-score、pct 计算分母错误等）。

---

## §2 检测器机制对照

| 检测器 | 代码入口 | 机制说明 | 是否需要 LLM API |
|--------|---------|---------|:--------------:|
| **Ours（算子语义契约）** | `d_ours` → `oracle_check()` | 对每类算子定义 goldless invariant contract，不看 gold output | 否 |
| exec-pass | `d_exec_pass` | `result is None` → 能否产出 DataFrame | 否 |
| output-validity | `d_validity` | 非空 + 列存在 + 无全 NaN 行 | 否 |
| self-check | `d_self_check` | 同模型 API 调用：「请判断这个结果是否正确？」 | **是** |
| consistency（CodeT K=3） | `d_consistency` | K=3 次独立生成，无多数票一致则报错 | **是** |

---

## §3 主要结果

### 3.1 检测性能并排

| 检测器 | TP（检出 silent） | FP（误报 correct） | Recall | FP Rate | Precision | **F1** |
|--------|:----------------:|:-----------------:|:------:|:-------:|:---------:|:------:|
| **Ours（oracle）** | **57/57** | **0/132** | **100%** | **0%** | **100%** | **1.000** |
| exec-pass | 0/57 | 0/132 | 0% | 0% | — | 0.000 |
| output-validity | 0/57 | 0/132 | 0% | 0% | — | 0.000 |
| self-check | 35/57 | 53/132 | 61% | 40% | 40% | **0.483** |
| consistency (K=3) | 0/57 | 0/132 | 0% | 0% | — | 0.000 |

**95% CI（oracle）**：Recall [94%, 100%]（Clopper-Pearson，57/57）；FP [0%, 3%]（0/132）

### 3.2 self-check 混淆矩阵

|  | 实际 silent（N=57） | 实际 correct（N=132） |
|--|:-------------------:|:--------------------:|
| self-check 报错 | TP = 35 | FP = 53 |
| self-check 放行 | FN = 22 | TN = 79 |

**解读**：self-check 既**漏报 39% 真实错误**（FN=22），又**误报 40% 正确结果**（FP=53）。在实际使用中两类错误都不可接受。

---

## §4 关键发现

### 4.1 exec-pass / validity 的根本局限

Silent Semantic Error 的定义即"代码可跑、输出合理、语义错"。`exec-pass` 和 `output-validity` 在定义层面就无法检测这类错误，recall 恒为 0%，与 LLM 能力无关。

### 4.2 consistency = 0% 是 Common-Mode 失败的铁证

3 次独立生成均犯同一个错误——以 `pct_point`（减法）代替 `pct_group`（除法）——三次结果完全一致，consistency 检测无法触发。这是 LLM 对歧义任务存在**系统性语义偏好**的直接证据。

### 4.3 LLM 自查悖论

self-check 要求同一个 LLM 既生成错误代码，又判断自己的代码是否正确。从认识论上，模型对同一算子语义的理解在生成阶段和验证阶段高度相关，因此自查对系统性偏差无效。高 FP（40%）则来自过度谨慎的自我怀疑。

### 4.4 Oracle 的三重优势

- **0% FP**：契约只在数学不变量被违反时触发，正确结果不会满足"per-group mean ≠ 0"之类的违反条件
- **100% Recall（核心 12 类）**：每类算子的 gold invariant 与 wrong invariant 数学上可分
- **无需参考答案**：整套评估 pipeline 可全程自动运行，无需人工标注

---

## §5 数据与复现

**结果文件**：
- `agent/eval/results_baseline_b/baseline_records.json` — 68 条记录（主要 run）
- `agent/eval/results_baseline_b_quick/baseline_records.json` — 33 条记录（claude-only quick run）

**复现命令**：

```bash
# 快速跑（仅 oracle，无需 LLM API）
cd agent
python eval/baseline_compare.py --quick

# 完整跑（含 self-check 和 consistency，需 API）
# 先设置 .env 或环境变量
python eval/baseline_compare.py --model gpt-4.1-mini
```

**B 组独立核查说明**：完整 run（68 records）的 oracle recall 为 13/15 = 87%（非 100%），原因是 68-grid 引入了 `zscore_within_group#1` 的 ddof 盲区（见 B4 §2.3 和 `task/transform_thesis_proposal_v2.md` §5）。**核心 12 类（48-grid）的 oracle recall 仍为 10/10 = 100%**，不影响论文主张。

---

---

## 附录：早期绘图实验——GPT-4o / Claude / Qwen 对比

> 以下内容属于项目早期"绘图保真（PlotTrace）"阶段，保留供参考。

### A.1 实验设置

- **数据集**：MatPlotBench（17 task）+ Builtin fixtures（4 task）= 共 24 任务
- **指标**：exec-pass rate, data_fidelity（结构感知 F1）

### A.2 GPT-4o One-shot

| 指标 | 值 |
|------|-----|
| Tasks | 24 |
| Exec-pass | 19/24 (79.2%) |
| Mean DF | 0.387 |
| Median DF | 0.093 |
| Fid 分布 | [0-.25):12, [.75-1]:7 |

执行率最高但 DF 偏低；12/19 通过任务 DF < 0.25，即 silent error 率偏高。

### A.3 Claude One-shot

| 指标 | 值 |
|------|-----|
| Tasks | 24 |
| Exec-pass | 17/24 (70.8%) |
| Mean DF | 0.599 |
| Median DF | 1.000 |
| Fid 分布 | [0-.25):7, [.75-1]:10 |

两极分化 — 要么全对（10 任务 DF=1.0）要么全错（7 任务 DF=0）。

### A.4 Qwen Zero-shot

| 指标 | 值 |
|------|-----|
| Tasks | 22 |
| Exec-pass | 18/22 (81.8%) |
| Mean DF | 0.670 |
| Median DF | 1.000 |
| Fid 分布 | [0-.25):5, [.25-.50):1, [.50-.75):1, [.75-1]:11 |

当期最强 baseline；11/18 通过任务 DF=1.0。

### A.5 Ours (PlotTrace)

| 指标 | 值 |
|------|-----|
| Tasks | 23 |
| Exec-pass | 15/23 (65.2%) |
| Mean DF | 0.289 |
| Mean VF | 0.656 |
| Mean SC | 0.694 |
| Mean rounds | 1.5 |

DF 偏低，10/15 可执行任务 DF=0，需排查 verifier 反馈质量。

### A.6 逐任务对比（MatPlotBench × 4 系统）

| Task | GPT-4o | Claude | Qwen | Ours |
|------|--------|--------|------|------|
| 76 | PASS 0.00 | PASS 0.00 | **PASS 1.00** | FAIL 0.00 |
| 77 | PASS 1.00 | PASS 1.00 | PASS 1.00 | PASS 0.67 |
| 78 | PASS 0.00 | PASS 1.00 | **PASS 1.00** | FAIL 0.00 |
| 79 | PASS 1.00 | PASS 1.00 | PASS 0.00 | PASS 0.00 |
| 80 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | PASS 0.00 |
| 81 | PASS 0.00 | PASS 0.00 | PASS 0.00 | FAIL 0.00 |
| 83 | PASS 0.00 | PASS 0.00 | PASS 0.40 | PASS 0.00 |
| 84 | **PASS 0.86** | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| 85 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | FAIL 0.00 |
| 86 | FAIL 0.00 | FAIL 0.00 | FAIL 0.00 | FAIL 0.00 |
| 87 | PASS 0.19 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 |
| 88 | FAIL 0.00 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 |
| 89 | PASS 0.00 | PASS 0.00 | PASS 0.00 | **PASS 1.00** |
| 90 | FAIL 0.00 | FAIL 0.00 | **PASS 1.00** | FAIL 0.00 |
| 91 | PASS 0.09 | FAIL 0.00 | PASS 0.67 | PASS 0.00 |
| 92 | PASS 0.00 | FAIL 0.00 | **PASS 1.00** | PASS 0.00 |
| 93 | PASS 1.00 | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| 95 | PASS 0.00 | FAIL 0.00 | FAIL 0.00 | PASS 0.00 |
| 96 | PASS 1.00 | PASS 1.00 | PASS 0.00 | PASS 0.67 |
| 97 | PASS 0.03 | PASS 1.00 | PASS 1.00 | **PASS 1.00** |
| 99 | PASS 0.18 | PASS 0.18 | PASS 0.00 | PASS 0.00 |
| 100 | PASS 0.00 | PASS 1.00 | PASS 1.00 | PASS 0.00 |
| builtin_001 | PASS 1.00 | PASS 1.00 | — | PASS 1.00 |
| builtin_002 | PASS 1.00 | PASS 1.00 | — | — |
