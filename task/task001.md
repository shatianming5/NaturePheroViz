## 步骤1: 调研token shang 增 和token level的 去做 探索的 这部分工作

想尽的联网搜索相关的 工作, 并且每一个工作,对应的是否可能对我们的工作有启发,启发的原因,如果要加入到我们的框架中 会怎么样  完整的做一个想尽的调研,竭尽所有能力

---

### ✅ 已完成 — 交付物：[`task001_survey.md`](./task001_survey.md)

两轮 deep-research 联网检索（5 路并行 → 抓一手源 → 抽可证伪主张 → 每条 3 票对抗核验 → 合成），
合计 43 源 / 211 主张 / 50 核验 / 45 证实 / 5 证伪 / 207 agent。覆盖：
- **Axis 1（test-time token scaling）**：Snell compute-optimal、s1 budget-forcing、rStar-Math、PRM800K、DeepSeek-R1、Reflexion、AlphaCodium、L1/LCPO、TALE。
- **Axis 2（token-level exploration）**：熵机制、Beyond-80/20 forking-tokens、VinePPO、RLOO、TDPO、DAPO、STEER/Revisiting-Entropy、min-p。

每篇均标注：是否启发 / 为何（绑定我们 loop 的具体失败模式）/ 如何加入框架（触及哪个组件 C1–C10、具体改动、单卡离线成本）。
另含：框架 10 组件×失败模式挂载表、代码级集成设计 P1–P8（grounded 真实文件/行号）、排序短名单、12 条开放问题、5 条已证伪清单。
