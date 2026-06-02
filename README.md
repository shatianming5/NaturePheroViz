# nature_dis + PheroViz

这是 `nature_dis` 与 `PheroViz` 的集成工作目录。两个原始 Git 仓库保留在 `_sources/`，根目录展开了一份可直接联动使用的工作副本。

## 目录结构

- `_sources/nature_dis/`：`https://github.com/shatianming5/nature_dis.git` 的完整 clone。
- `_sources/PheroViz/`：`https://github.com/shatianming5/PheroViz.git` 的完整 clone。
- `agent/`：PheroViz Slot Pipeline，可根据数据自动生成 Matplotlib 可视化。
- `nature_download/`：PheroViz 中的 Nature 检索、图像和 Source data 抓取入口。
- `download_nature_pairs.py`：nature_dis 中的 Nature 图文/数据下载脚本。
- `tools/process_articles.py`：nature_dis 中的文章预检、子图分割和派生数据处理工具。
- `docs/`、`scripts/`：nature_dis 的代理 API 文档与辅助脚本。

## 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install
```

如需调用 LLM/VLM，请在 `.env` 中配置 `LLM_API_KEY`、`OPENAI_API_KEY`、`LLM_API_BASE`、`LLM_MODEL` 或 `VLM_API_KEY` 等变量。

## 常用入口

Nature Source Data 配对采集与下载：

```bash
python download_nature_pairs.py --max-articles 10 --max-candidates 1000 --out-dir downloads/nature_pairs
```

输出包括：

- `downloads/nature_pairs/pairs.jsonl`：图像与 Source Data 的配对记录。
- `downloads/nature_pairs/articles/<article-id>/images/`：图像文件。
- `downloads/nature_pairs/articles/<article-id>/data/`：Source Data 文件。
- `downloads/nature_pairs/skipped.jsonl`：已检查但没有可配对 Source Data 的文章。

`--max-articles` 表示“成功下载到至少一组图片 + Source Data 配对的文章数”。没有可配对数据的候选文章会写入 `skipped.jsonl`，不占用成功名额。`--max-candidates` 用来限制最多检查多少候选文章，避免大批量搜索无限延伸。

也可以直接给定文章 URL：

```bash
python download_nature_pairs.py --urls-file urls.txt --out-dir downloads/nature_pairs
```

PheroViz 可视化流水线：

```bash
cd agent
python run_chain.py data/sales_demo.csv "季度对比" bar --rounds 1
```

Nature all-in-one 检索与抓取：

```bash
cd nature_download
python nature_all_in_one.py search --query "cancer" --max 20 --out outputs/search_run
python nature_all_in_one.py postfetch --jsonl outputs/search_run/articles.jsonl --out outputs/nature_content --max-figs 12
```

`postfetch` 会独立尝试下载 Source Data；即使 figure 页面没有抓到图，只要 Source Data 下载成功，文章目录也会保留。

nature_dis 下载脚本：

```bash
python download_nature_pairs.py --help
```

文章预检与子图处理：

```bash
python -m tools.process_articles preflight --input downloads/articles --output downloads/derived --progress
```

对于 `download_nature_pairs.py` 的输出，预检入口是：

```bash
python -m tools.process_articles preflight --input downloads/nature_pairs/articles --output downloads/nature_pairs/derived --progress
```

## 同步上游仓库

原始 clone 保留在 `_sources/` 中，需要更新时运行：

```bash
git -C _sources/nature_dis pull --ff-only
git -C _sources/PheroViz pull --ff-only
```

更新 `_sources/` 后，如需刷新根目录集成副本，可重新将两个源目录的非 `.git` 文件同步到根目录，并再次检查 README、依赖与忽略规则。
