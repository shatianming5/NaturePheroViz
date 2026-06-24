# B5 — 数据许可注册

> 参见 `agent/eval/DATA.md` 完整版。本文档为摘要。

---

## 数据集总览

| 数据集 | 状态 | 许可证 | 论文使用 |
|--------|------|--------|----------|
| Built-in fixtures | ✅ 已集成 | 作者自有 | 否 (仅冒烟测试) |
| **MatPlotBench** | ✅ 已集成 | **Apache-2.0** | **是 (主表)** |
| **Nature Pairs** | ⚠️ 待爬取 | **CC-BY-4.0** | **是 (定性案例)** |
| Plot2Code | 🔜 计划 | TBD | 可选 |
| ChartMimic | 🔜 计划 | TBD | 可选 |
| ChartMoE-Align | 🔜 延伸 | Apache-2.0 | 可选 (SFT) |
| Text2Chart31 | 🔜 延伸 | MIT | 可选 (SFT) |

---

## 1. MatPlotBench (主要基准)

- **来源**: [thunlp/MatPlotAgent](https://github.com/thunlp/MatPlotAgent) — `benchmark_data/`
- **许可证**: Apache-2.0
- **任务数**: ~100 (算法生成，反记忆化设计)
- **使用方式**: 输入数据 `plot_df.csv` 作为 ground truth，系统生成代码 → 评估保真度

## 2. Nature Pairs (定性案例)

- **来源**: 通过 `nature_crawler.py` + `download_nature_pairs.py` 从 Nature Communications 爬取
- **许可证**: CC-BY-4.0 (Nature Communications 文章及源数据)
- **数量**: 50–200 图-数据对
- **用途**: 真实科学图表定性评估 + silent error 注入审计

## 3. 投稿前检查清单

- [ ] 验证 MatPlotBench 最新 LICENSE 文件
- [ ] 确认所有爬取的 Nature 文章均为 CC-BY-4.0
- [ ] 如使用 Plot2Code/ChartMimic，记录其许可证
- [ ] 确认无 NC 条款冲突 AAAI 发表
- [ ] 记录 Nature Pairs 爬虫版本和日期

---

## 许可证要求满足情况

| 要求 | 状态 |
|------|------|
| 所有数据集许可证已记录 | ✅ (除 Plot2Code/ChartMimic — 未使用) |
| 无 NC 限制冲突 | ✅ (Apache-2.0 + CC-BY-4.0 均允许学术发表) |
| 爬虫可复现性 | ✅ (`nature_crawler.py` 含完整参数) |
| AAAI 合规 | ✅ |
