# 一周冲刺分工（AAAI 投稿核心实验 + 初稿）

> 目标：一周内做出**能撑起强投稿（争 Oral）的实验核心 + 论文初稿**。
> 论文一句话卖点：**现有 viz 生成的评测/判官只看「视觉/代码相似」，不验「画出来的数字是否真等于数据」；我们用 code-first agent + 可执行证据（读数回译 + 结构感知 diff）在修复内环里当判官，显著提升数据保真。**
> 默认假设：**训练-free**（在现成 LLM 上做推理时 agent），不训模型。若有 GPU 且想做 Stage-A SFT，作为 stretch（见末尾）。

---

## 0. 先读：现在代码长什么样（两人都要懂）

- 入口：`agent/run_chain.py <data.csv> "<目标>" <chart_family> --rounds N [--intent '{"x":..,"y":..,"group":..}']`
  - 例：`python run_chain.py data/sales_demo.csv "季度对比" bar --rounds 1`
  - 数据是带表头的 CSV（如 `月份,品类,销量,转化率`）。
- 内环主控：`agent/app/services/single_chain_runner.py`
  - 轮循环在 `:637`（`for round_idx in range(1, rounds+1)`）；停机在 `:903`（`visual_form>=0.75 且 data_fidelity>=0.75`）；LLM 温度 `:151`（0.2）。
- **判官**：`agent/app/services/judge.py` 的 `judge(png_path, exec_log, df, spec)`（`:301`）
  - 有 VLM 分支 `_call_vlm_judge`（OpenAI 兼容；环境变量 `LLM_API_BASE / VLM_API_KEY / VLM_MODEL`）。
  - **规则回退分支的 data_fidelity 极弱**（`:322-327`）：`fid = 0.5 + 0.25*(列名同时在表里的 overlay 数 / overlay 总数)`——**只检查「列名是否存在」，根本不看画出来的数值！这就是我们要攻击的 gap，就在我们自己代码里。**
  - **目前根本不产出 series_cohesion**（只返回 visual_form + data_fidelity + diagnostics）。
  - `_image_nonempty_score`（`:242`）是 visual_form 的「像素方差」回退启发式。
- 判官配置：`agent/configs/judge_rules.yml`（权重只有 visual_form/data_fidelity 各 0.5）、`diagnostics_map.yml`（诊断 key→slot+hint）。
- 记忆：`agent/app/services/pheromones.py` 的 `PheroStore` 是 **append-only**（无 TTL/检索）。
- **`plot_df`/PlotTrace（plan.md 里写的「把真正喂给 matplotlib 的数据 dump 出来」）尚未实现**——所以保真验证走 **SVG 反解析**（VisEval 做法，低风险）为主、chart→table VLM 为辅。
- 每轮产物：`runs/<时间戳>/`
  - `code_round_N.py`、`figure_round_N.png`、`slots_round_N.json`
  - `iteration_N.json`，顶层键：`round, png_path, scores, diagnostics, spec, slots, stderr, stages, debug`

---

## 1. ⭐ 唯一的接口契约：统一 run 记录（Day 1 两人一起敲定，之后各干各的）

两人只在这一处耦合。约定**每个 benchmark 样本**跑完后，落一个目录：
```
results/<system>/<task_id>/
  code.py            # 生成的绘图代码
  chart.png          # 渲染图
  chart.svg          # 渲染的 SVG（A 的验证器要用；savefig 同时存 svg）
  plot_df.csv        # ground-truth：本图应当画出的数据表（A 的验证器对照用）
  pred_table.csv     # 验证器从图里「读回来」的表（A 产出）
  record.json        # 见下
```
`record.json` schema（**两人共同字段，缺一不可**）：
```json
{
  "task_id": "matplotbench_017",
  "system": "ours | matplotagent | lida | chartcoder | qwen_zeroshot | gpt4o_oneshot",
  "exec_pass": true,                 // 代码是否无异常跑出图
  "scores": {                        // 0-1
    "visual_form": 0.0,
    "data_fidelity": 0.0,            // ← 我们的新指标（A 的验证器算）
    "series_cohesion": 0.0
  },
  "fidelity_detail": {               // A 产出
    "rms_f1": 0.0,                   // 结构感知 (row,col,value) 匹配 F1
    "rnss": 0.0,                     // 位置无关数字集相似（对照用）
    "mismatches": [ {"series":"B","x":"Feb","gt":130000,"pred":90000,"type":"wrong_value"} ]
  },
  "rounds_used": 1,
  "tokens": 0,
  "ground_truth_ref": "path/to/plot_df.csv",
  "notes": ""
}
```
> **谁产哪段**：B 跑各系统产出 `code.py/chart.png/chart.svg/plot_df.csv` 和 `exec_pass/rounds_used/tokens`；A 的验证器吃 `chart.svg + plot_df.csv` 产出 `pred_table.csv + scores.data_fidelity/series_cohesion + fidelity_detail`。两人各写自己那半，按这个 json 拼。

---

## 2. 组员 A 的任务卡（方法 + 系统）

> 主线：**实现可执行证据保真验证器**（论文 novelty），并把内环加上 Best-of-N + 预算停机。
> 用 AI：**Codex 写边界清晰的代码**（SVG 解析、RMS diff、Best-of-N 循环）；**Claude 做接口/架构设计 + 代码审查 + 写 method 章节配合**。

### A1（最高优先，命脉）保真验证器 `verify_fidelity`
- 新文件：`agent/app/services/fidelity_verifier.py`
- 函数：`verify_fidelity(svg_path: str, ground_truth_table: "DataFrame", spec: dict, png_path: str|None=None) -> dict`
  返回 `{"data_fidelity": float, "rms_f1": float, "rnss": float, "pred_table": DataFrame, "mismatches": [...]}`
- 算法：
  1. **读数回译**：解析 matplotlib 存的 SVG，按几何对象恢复 `(series, x_category, value)`——柱:bar 高度→值；折线/散点:点的 y 坐标经轴反变换→值。（VisEval 的 SVG-deconstruction 思路；优先做 bar+line，覆盖 80% 样本。）
     - 失败兜底：调 chart→table VLM（**UniChart-201M** 或 **OneChart-0.2B**，单卡）对 PNG 出表。
  2. **ground truth**：`ground_truth_table` 就是「这张图应当画出的值」（B 提供的 `plot_df.csv`）。
  3. **结构感知匹配**：按 (series,x) 配对，比较 pred 值 vs gt 值（容差 ~1-2%）→ 算 precision/recall/F1 = `rms_f1`；另算位置无关的 `rnss`（数字集）作对照。`data_fidelity = rms_f1`。
  4. **诊断**：每个 mismatch 产一条 typed 诊断（wrong_value / missing_series / wrong_mapping）。
- **接进判官**：改 `agent/app/services/judge.py:judge()`——把 `:322-327` 那段「列名存在」启发式**替换/补强**为调用 `verify_fidelity`（当能拿到 svg + gt 表时用真验证器，否则回退旧启发式）。
- ✅ 验收：给一张「数字对、但 B 类柱画成了 90000（真值 130000）」的图，旧 data_fidelity 仍 ≈0.75，**新 data_fidelity < 0.4 且 mismatches 列出那条**。

### A2 补 `series_cohesion`
- 在 `judge()` 返回的 `scores` 里加 `series_cohesion`；`agent/configs/judge_rules.yml` 加权重项。
- 单图先做：检查 overlay 间 单位/scale/palette/legend/类目顺序 一致性（顺序检查可借 VisEval）。
- ✅ 验收：左右轴单位不一致 / palette 冲突时 cohesion 明显下降，`iteration_N.json.scores` 里出现该项。

### A3 Best-of-N + verifier 择优
- 在 `single_chain_runner.py` 每轮：对同一 state 采 **N=3** 个候选补丁（把温度 `:151` 升到 ~0.7 或用 min-p），各自 render，用 `judge` 选 (exec_pass 且综合分最高) 者接受；落败者也存下来（给消融/未来 DPO）。
- ✅ 验收：`iteration_N.json` 里记录 N 个候选的分数 + 被选 index；难例上接受分高于 N=1。

### A4 预算停机（budget-forcing）
- 把 `:903` 的扁平 `>=0.75` 换成：达标即停 **或** 连续两轮 ΔJ≈0 提前停（治死循环）**或** 预算耗尽；未达标且预算未尽 → 强制再来一轮 deeper。
- ✅ 验收：构造一个修不动的例子，旧逻辑空转满 rounds，新逻辑 2 轮无进展即停并记 `stop_reason`。

### A5 消融开关（给实验用）
- 加环境变量/参数：`--no-verifier`（退回旧 data_fidelity）、`--no-bestof`（N=1）、`--no-pheromone`。
- ✅ 验收：B 能用同一命令跑出「全开 / 关验证器 / 关 BoN」三套结果。

**A 的 Codex 示例 prompt**：
> "在 `agent/app/services/fidelity_verifier.py` 写 `verify_fidelity(svg_path, ground_truth_table, spec, png_path=None)`。解析 matplotlib 存的 SVG 恢复柱状/折线每个 (series,x) 的数值（点用 axes transform 反算），与 ground_truth_table 按 (series,x) 配对算 RMS-style precision/recall/F1，容差 1.5%，返回 dict 含 data_fidelity/rms_f1/rnss/pred_table/mismatches。先覆盖 bar 和 line。给 pytest。"

---

## 3. 组员 B 的任务卡（评测 + 基线 + 数据）

> 主线：**评测 harness + 指标 + baseline + 杀手实验**。
> 用 AI：**Codex 写各 baseline 的 runner 和指标脚本**；**Claude 设计实验矩阵 + 对齐评测协议 + 写 experiments 章节配合**。

### B1 评测 harness + 数据集
- 新文件：`eval/run_benchmark.py`，对一个数据集逐样本调某 system，产出 §1 的 `results/<system>/<task_id>/`。
- 数据集（优先级）：
  1. **MatPlotBench**（100 题，防记忆；来自 `thunlp/MatPlotAgent` 仓库 `benchmark_data/`）——主力。
  2. **我们自采的 Nature pairs**（`download_nature_pairs.py` 产物）做**质化案例 + 真实复杂图**。
  3. Plot2Code / ChartMimic 子集（各取 ~50）——作 chart→code 视觉对照（注意它们只测视觉相似）。
- **关键**：每个样本要有 **`plot_df.csv`（ground-truth 数据表）**。MatPlotBench 自带输入数据；自采题需你确定「正确该画的值」。
- ✅ 验收：`python eval/run_benchmark.py --system ours --dataset matplotbench` 跑完产出 100 个标准目录。

### B2 baseline runner（每个包成统一接口：吃 (data, 指令) 出 (code, png)）
- **Qwen2.5-Coder 零样本**（一次性 prompt 出 code）—— 最重要的下界。
- **GPT-4o 一次性**（同上，闭源上界对照）。
- **MatPlotAgent**（github thunlp/MatPlotAgent，自带视觉反馈环）—— 主竞品。
- **LIDA**（`pip install lida`）。
- **ChartCoder**（HF，chart→code；注意它输入是图不是表，作相邻对照）。
- ✅ 验收：5 个 baseline 都能在 MatPlotBench 上跑出 `results/<system>/...`。

### B3 指标脚本
- `eval/metrics.py`：聚合 `record.json` 算 **exec-pass率、data_fidelity(我们的 rms_f1) 均值、visual_form、pass@1、pass@k(k=3)**；出 CSV/表。
- visual_form 用 VisEval 风格的可读性检查（CPU）或 GPT-4V 打分（二选一，对齐协议）。
- ✅ 验收：一条命令出「systems × metrics」主表。

### B4 ⭐ 杀手实验「保真审计」（命门，B 主导，和 A 的验证器对接）
- 新文件：`eval/fidelity_audit.py`
- 做法：取一批正确的 (code, data)，**扰动数据后用原代码重渲染**，造出「视觉合理但数据错」的 silent-wrong 图。扰动类型：
  - `swap_categories`（A/B 类目值互换）、`scale_series`（某系列乘 0.7）、`drop_series`（少画一个系列）、`permute_labels`（标签错位）。
- 对每张扰动图，让**三种判官**判：①旧规则判官(列名启发式) ②VLM 判官(GPT-4o) ③**我们的验证器(A 的 verify_fidelity)**。
- 出**主图/主表**：行=扰动类型，列=三种判官，格=「检测率(precision/recall)」。**预期：旧判官几乎全过(漏检)、VLM 部分漏(absent regime 编造)、我们的验证器高检出**——这一张就是 Oral 命门。
- ✅ 验收：一张让审稿人一眼信服「现有判官测不出数据错、我们能」的表。

### B5 数据/许可登记
- 一个 `eval/DATA.md` 记每个数据集来源 + 许可（MatPlotBench、Plot2Code、ChartMoE-Align 等，见五轮 survey 附录），避免投稿踩许可坑。

**B 的 Codex 示例 prompt**：
> "写 `eval/fidelity_audit.py`：输入一批 (matplotlib code, data.csv)，实现 4 种数据扰动(swap_categories/scale_series/drop_series/permute_labels)，用原 code 在扰动数据上重渲染存 png+svg，再分别调 (a) 旧规则判官 (b) OpenAI 兼容 VLM 判官 (c) agent/app/services/fidelity_verifier.verify_fidelity，统计每种扰动下三者的检测 precision/recall，输出汇总表 CSV。"

---

## 4. 七天时间线（每人每天目标）

| 天 | 组员 A | 组员 B | 你(lead) |
|---|---|---|---|
| D1 | 定 §1 schema；fidelity_verifier 骨架(bar) | 定 §1 schema；run_benchmark 跑通 + 拉 MatPlotBench | 起论文骨架(intro/method/related-work，related 直接用五轮 survey) |
| D2 | verifier 完成(bar+line)+接进 judge(A1) | Qwen 零样本 + GPT-4o + 我们的系统 跑出初步数(B1/B2) | 定主图/主表草样 + 一句话卖点 |
| D3 | series_cohesion(A2) | **杀手实验 fidelity_audit(B4) 出第一版表** | 写 method(保真验证器) |
| D4 | Best-of-N(A3)+预算停机(A4)+消融开关(A5) | 补 MatPlotAgent/LIDA/ChartCoder(B2)+指标(B3) | 看 D4 中期结果，砍范围 |
| D5 | 跑全量消融(验证器on/off、BoN、pheromone) | 全量主表 + pass@k | 写 experiments + 收数 |
| D6 | 修坑 + 补漏实验 | 画图做表 + 杀手实验定稿 | 写 abstract/intro/conclusion |
| D7 | buffer + 复跑确认 | buffer + 数据/许可登记(B5) | 全文通读 + 找人(或我/Codex)对抗审稿 |

---

## 5. 该砍的（否则一周必崩）
- ❌ 训模型（SFT/DPO）——非卖点，作 future work / stretch。
- ❌ Pheromone 完整持久化 + 学习路由 µθ——消融给轻量版即可。
- ❌ 多 panel + Γ 全局一致性大工程——先把单图保真故事讲透。
- ❌ 自造大数据集——MatPlotBench + 现成集 + Nature pairs 质化即可。

## 6. （可选）Stretch：若有空闲 GPU
- 用 **ChartMoE-Align(~1M, Apache-2.0)** 或 **Text2Chart31(MIT)** 做一个 Stage-A Code-SFT，对比「SFT 后基座 + 我们内环」vs「零样本基座 + 我们内环」，作论文的「方法正交可叠加」加分项。**不进关键路径。**

## 7. 验收（一周末两人各自的 Definition of Done）
- **A**：`verify_fidelity` 能跑、接进 judge、杀手实验里检出率显著高于旧判官+VLM；BoN+预算停机有消融数据。
- **B**：MatPlotBench 上「我们 vs ≥4 baselines」主表 + 「保真审计」命门表 + 三套消融结果，全部按 §1 schema 落盘、可一键复现。

> 任何阻塞，先保 **A1(验证器) + B4(杀手实验)** 这两块——它俩就是论文的核心证据，其余都是支撑。
