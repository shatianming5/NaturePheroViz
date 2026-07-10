# Method 提案 v2：Execution-Traced Fidelity —— 用执行证据抓出并修复"画错的数"

> 目标：顶会 Oral。本版据 GPT-5.4 round-1 review 收敛——**C1 单一主张扛全篇**，C2/C3 降为支撑/扩展，补全对齐层规格与决定性实验。
> 一句话卖点见 §0。

---

## 0. 一句话卖点（单一主张）

> **对于"自己写绘图代码"的可视化 agent，我们在执行期验证 matplotlib 真正收到的"变换后、渲染前"数值数组——这是任何只看渲染图/SVG 的判官观测不到的。凭此抓出并修复肉眼可见图上"画错的数"（silent numeric error）。**

能力命名：**silent-error self-repair**。**这是全篇唯一的中心贡献（C1）。**

---

## 1. Problem Anchor（每轮逐字保留）

- **根本问题**：写 matplotlib 代码的 LLM agent 常产出"视觉合理但画出的数 ≠ 该画的数"的图（silent error：错值 / 漏系列 / 错映射）。现有 viz 判官只比视觉/代码相似,不验"画出来的数是否等于该画的数"。
- **必须解决的瓶颈**：缺一个能验**可执行数据保真**且能驱动修复的**内环判官**。现有判官 = 列名启发式（只查列名在不在表里）或 chart-VLM（数据缺失时编造表、不可靠）。
- **非目标**：不训大模型；不做多面板全局一致性；不自造大数据集；不刷视觉美学 SOTA。
- **约束**：默认训练-free 推理时 agent；单卡 QLoRA 仅 stretch；离线；code-first agent 在 Sense→Plan→Patch→Render→Judge→Route 内环；已实现 HCT L1–L4 分层动作空间 + 逐层 guard；已实现 Best-of-N 且落盘全部候选。
- **成功条件**：(a) 在含真实 Nature 图的基准上，以高 precision/recall 抓出列名/VLM 判官漏掉的 silent error；(b) 内环修复之；(c)【可选扩展】证明该保真信号能驱动 VLM/SVG 噪声信号无法驱动的标签-free 自改进。

---

## 2. 技术 gap：执行追踪 vs 看图反推

| | 现有工作 | 我们 |
|---|---|---|
| 能拿到什么 | 只有**最终渲染图**（PNG/SVG） | agent 自己执行代码 → 拿到**执行现场** |
| 怎么验保真 | 从图**反推**（几何误差、需 VLM 兜底、复杂图型覆盖差） | 在 `ax.bar/plot/...` 被调用瞬间**插桩截获实参数组**（对受支持图型 exact） |
| 抓得到哪类 bug | 看不到 `load→transform→render` 之间的数据逻辑错 | 截到**变换后、渲染前**数组 = 代码数据逻辑的输出 |

**为什么以前没人做**：现有评测器不生成代码，没有执行现场的访问权。**这个结构性不对称 = novelty 的根，也是 vs VisEval 的本质区别**——VisEval 仍从已渲染产物重建（估计），我们在执行点直接读（精确）。

> 注：`plan.md` 里这叫 PlotTrace；团队为一周冲刺改走 VisEval 式 SVG 反解析（低风险但 incremental）。本提案捡回执行追踪作主路，**SVG 反解析降级为 fallback**（评测无法插桩的 baseline 系统时用，保证公平对照）。

---

## 3. 中心贡献 C1：Execution-Traced Fidelity

### 3.1 难点不在 hook，在"对齐层"（reviewer 标 CRITICAL，本版补全）

真正的技术核心**不是** monkeypatch `Axes.bar/plot`（那是 trivial），而是**把原始 artist 调用轨迹对齐回语义 `(series, x, value)` 单元**，并处理：stacked（堆叠基线累加）、transform（log/二次坐标）、twinx（左右轴绑定）、类目重排、errorbar、归一化。

**规格：Canonical Trace IR + 按图型匹配算法**

- **Trace IR**：每条绘图调用 → `TraceCall{method, ax_id, series_label, x_raw[], y_raw[], kwargs}`。一次 install 覆盖所有 axes（含 twinx 右轴）。
- **归一化算子**（按图型，把 y_raw 还原成"该比对的值"）：
  | 图型 | 对齐规则 | ambiguity 状态 |
  |---|---|---|
  | bar/barh | (x_i, height_i) 直接配对 | 无 |
  | plot/step/scatter | (x_i, y_i) 直接配对 | 多 fmt 段需拆 |
  | **stacked bar** | 第 k 段实值 = height_k（matplotlib 的 bottom 是累加基线，截获的是**增量**，需减基线还原绝对值） | 标 `STACKED_RESOLVED` |
  | **fill_between** | 取 y2 为值；y1≠0 时记 `BAND`（区间非点值） | 标 `BAND_AMBIGUOUS` |
  | **twinx** | 按 ax_id 分轴，series 各自归属 | 无 |
  | hist | 截获的是原始样本而非 bin 高度 → 记 `RAW_SAMPLES`，不参与 (x,value) 配对 | 标 `UNSUPPORTED` |
  | imshow/pcolormesh | 2D 矩阵 → 标 `MATRIX`（C1 v1 不展开，留 fallback） | 标 `UNSUPPORTED` |
- **匹配**：与 ground-truth 长表按 `(series, x)` 配对，容差 `|pred−gt| ≤ max(|gt|×1.5%, 1.0)`，产出 `rms_f1` + typed mismatch（`wrong_value/missing_series/wrong_mapping`）。
- **覆盖率表（必须有，reviewer 要求）**：论文报告每种图型的"可对齐率/ambiguity 率/UNSUPPORTED 率"，**只对 `RESOLVED` 图型声明 exact**，其余诚实标注走 fallback。

### 3.2 已验证（本提案附带的 spike）

`agent/app/services/plot_trace.py` 已实现并自测通过 4 例：**bar、多折线（series 标签保留）、twinx 右轴（一次 install 覆盖）、silent-error（真值 13万、代码画 9万 → 精确截获 90000，可 diff 出 wrong_value）**。证明对齐层在核心图型上成立。stacked/transform/hist 的归一化为下一步。

### 3.3 措辞收紧（reviewer 标 IMPORTANT）

删除绝对化表述：不说"natively covers 所有图型"，改"对 instrumented 且 RESOLVED 的图型 exact"；不说"exact oracle"，改"exact on supported chart families"。

---

## 4. 支撑贡献 C2（降级）：保真驱动的逐层修复路由

**不再当 co-equal 主张**（reviewer：typed feedback 已见于 PlotGen，PRM 分解已见于 Math-Shepherd，独立看 incremental）。重新定位为**"C1 使能的修复路由机制"**：把 typed mismatch 映射到 HCT 责任层（L1 数据/L2 变换/L3 编码/L4 样式），把**结构化 JSON mismatch 报告**喂回 patch policy（而非自由文本批评），让修复定向打在出错的层。

- 增量主张：mismatch 的数值信号来自**确定性执行追踪**（非外部读图）且挂到分层动作空间——这是 vs PlotGen 的唯一增量，**作为 C1 的应用呈现，不单列**。
- 最小验证（identifiability，否则只是路由启发式）：注入已知层的错误，检验是否归因到该层（混淆矩阵）。

---

## 5. 可选扩展 C3（明确降为后段）：保真信号的标签-free 自改进

**reviewer 明确警告漂移风险：不要把本文变成训练/DPO 论文**。C3 仅作末节"额外 result"，学习严格从属于 verifier 故事。

- 做法：修复轨迹的（败选,胜选）候选 → DPO 偏好对，信号 = 执行追踪保真度。Best-of-N 已落盘候选 = 现成原料。
- 仅当能给出**干净的 held-out 增益**、且**对照证明 VLM/SVG 噪声偏好信号训不出同等效果**时才进正文；否则只放附录。
- 措辞：删"no reward hacking"绝对化，改"保真维度上偏好信号无代理噪声，难以 game"。

---

## 6. 决定性实验（reviewer 指定的"唯一最重要缺失实验"）

**Judge-only head-to-head on controlled silent errors**（这一张表立则全篇立）：

1. 取 **30–50 条真实 Nature（数据表+caption）** 案例（来自已爬的 510 配对，经 `repair_headers.py` cura）。
2. 在**数据逻辑步之后、视觉尚未明显异常之前**注入**一个** silent 数值损坏：错聚合 / 漏系列 / 错映射 / twin-axis 误绑 / stacked 归一化错。
3. 三判官对比：
   - **判官 precision/recall**：PlotTrace(C1) vs VisEval/SVG vs 强 VLM judge
   - **一步修复成功率**：同一 patch 模块分别由三判官驱动
4. 预期：旧判官几乎全漏、VLM 部分漏（absent 时编造）、PlotTrace 高检出 + 高修复率。**若此表不显著为正，整个 thesis 削弱。**

辅助：§3.1 覆盖率表；§4 层归因混淆矩阵；§5（可选）DPO held-out 曲线 + 噪声信号对照。

---

## 7. FM-era 定位（reviewer 的 Modernization）

主打 **verifier-guided test-time search / reranking**（Best-of-N 候选用 C1 保真分择优）——这才贴合"训练-free"约束的前沿故事，**而非以 QLoRA 领衔**。结构化 JSON mismatch 反馈进 patch policy。DPO 仅作可选叠加项。

---

## 8. 要 build 什么（按优先级，映射现有代码）

| 优先级 | 做什么 | 落点 | 状态 |
|---|---|---|---|
| **P0✅** | `plot_trace.py`：执行期插桩 Artist + 对齐成 (series,x,value) | `agent/app/services/plot_trace.py` | **骨架+4例自测已通过** |
| **P0** | 对齐层补 stacked/transform/twinx 归一化 + 覆盖率表 | `plot_trace.py` | 待做 |
| **P0** | 接进子进程 scaffold：在 Jinja 模板 `run()` 开头注入 tracer，savefig 旁 dump `.trace.csv` | `scaffold_elements_pro.py.j2`（~570/657 行）+ `sandbox_runner.py` | 待做 |
| **P0** | verifier 优先用 trace（SVG 降 fallback）+ typed mismatch→L1-L4 映射 | `fidelity_verifier.py` + `feedback_builder.py` | 待做 |
| **P1** | 决定性实验：注入器 + 三判官对比 harness | 新 `eval/silent_error_audit.py` | 待做 |
| **P2 可选** | `build_dpo_pairs.py` + QLoRA Repair-DPO 一轮 | 新 `scripts/` | C3 才需要 |

---

## 9. 与已实现部分的关系

- A1（SVG 保真验证器）→ 降 fallback；主路换 PlotTrace。
- A2（series_cohesion）→ 辅助维度，论文一句话带过。
- A3（Best-of-N）→ §7 test-time search 的择优 + C3 偏好对来源。
- ⚠️ 现停机 `overall_score≥0.75` 把 data_fidelity 权重稀释到 ~0.38，与"重保真"卖点冲突 → 给 DF 加硬门槛，或在 BoN 择优里把 DF 设为首排序键。

---

## 10. 诚实风险与应对

| 主张 | 质疑 | 应对 |
|---|---|---|
| C1（中心） | "插桩 trivial" | 价值在**对齐层**（§3.1 IR+按图型算法+覆盖率表），不是 hook |
| C1 | "覆盖不全会被攻" | 只对 RESOLVED 图型声明 exact，UNSUPPORTED 诚实走 fallback；覆盖率表撑 |
| C2（支撑） | "typed feedback 不新" | 不单列，作 C1 的修复路由应用；层归因混淆矩阵证可识别 |
| C3（扩展） | "RLEF 已有 / 变成训练论文" | 降末节；仅当 held-out 增益 + 噪声信号对照成立才进正文 |

---

## 11. 收尾

**全篇押一个不对称：image/SVG/VLM 判官观测不到"变换后、渲染前"的数值,所以对 silent numeric error 失明;我们在执行点读到它,于是能抓出并修复肉眼看不出的画错的数。** C1 扛全篇,C2 是它使能的修复路由,C3 是可选的自改进扩展;真实 Nature 数据上的 judge-only head-to-head 是立论命门。
