# B3 — 汇总主表 (Aggregate Metrics)

## 系统 × 指标 总表

| System | Tasks | Exec-pass | Data Fidelity | Visual Form | Series Cohesion | Rounds | Pass@1 |
|--------|-------|-----------|---------------|-------------|-----------------|--------|--------|
| **qwen_zeroshot** | 22 | **18/22 (81.8%)** | **0.670** | 0.000 | 0.000 | 1.0 | 0.818 |
| gpt4o_oneshot | 24 | 19/24 (79.2%) | 0.387 | 0.000 | 0.000 | 1.0 | 0.792 |
| claude_oneshot | 24 | 17/24 (70.8%) | 0.599 | 0.000 | 0.000 | 1.0 | 0.708 |
| ours | 23 | 15/23 (65.2%) | 0.289 | 0.656 | 0.694 | 1.5 | 0.652 |
| lida | 3 | 0/3 (0.0%) | 0.000 | 0.000 | 0.000 | 0.0 | 0.000 |

> **注**: visual_form 和 series_cohesion 仅 Ours 系统有值（由 PlotTrace verifier 计算），单轮 baseline 无此指标。

---

## 各系统详细统计

### qwen_zeroshot
- Tasks: 22
- Exec-pass: 18/22 (81.8%) — **最高**
- Mean DF: 0.670 — **最高**
- Median DF: 1.000
- Fidelity distribution: `[0-.25):5  [.25-.50):1  [.50-.75):1  [.75-1.0]:11`
- 强项: 一半以上任务达到完美保真度

### gpt4o_oneshot
- Tasks: 24
- Exec-pass: 19/24 (79.2%)
- Mean DF: 0.387
- Median DF: 0.093
- Fidelity distribution: `[0-.25):12  [.50-.75):0  [.75-1.0]:7`
- 弱项: 大量 silence error — 12 个通过任务的 DF < 0.25

### claude_oneshot
- Tasks: 24
- Exec-pass: 17/24 (70.8%)
- Mean DF: 0.599
- Median DF: 1.000
- Fidelity distribution: `[0-.25):7  [.75-1.0]:10`
- 特点: 两极分化 — 要么全对要么全错

### ours
- Tasks: 23
- Exec-pass: 15/23 (65.2%)
- Mean DF: 0.289
- Median DF: 0.000
- Mean VF: 0.656 | Mean SC: 0.694 | Mean rounds: 1.5
- Fidelity distribution: `[0-.25):10  [.50-.75):2  [.75-1.0]:3`
- 需要改进: 10 个可执行任务 DF=0

### lida
- Tasks: 3 (attempted)
- Exec-pass: 0/3 (0.0%)
- Mean DF: 0.000

---

## 关键发现

1. **Qwen-plus 零样本是当前最强 baseline** — 81.8% 执行率 + 0.67 DF，远超 GPT-4o 和 Claude
2. **GPT-4o 的 silent error 问题最严重** — 最高执行率但最低 DF (0.39)，说明 LLM 容易生成可运行但数据错误的代码
3. **Ours 系统 DF 偏低** — 需要排查 verifier 反馈质量或 agent 配置
4. **Visual form + Series Cohesion 是 Ours 独有的评估维度** — 单轮 baseline 的 VF/SC 未计算
