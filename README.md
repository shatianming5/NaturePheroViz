# NaturePheroViz

NaturePheroViz is a research data pipeline for collecting Nature article figures, matching them with Source Data files, validating the downloaded corpus, and generating visualization outputs with the PheroViz agent.

The project is organized as a single working codebase:

- `download_nature_pairs.py`: collect Nature article pages and download matched figure + Source Data pairs.
- `tools/process_articles.py`: preflight downloaded articles, build manifests, and prepare figure-level processing outputs.
- `nature_download/`: alternate all-in-one Nature search/download utilities for metadata, figures, and Source Data.
- `agent/`: PheroViz slot pipeline for data-driven Matplotlib chart generation.
- `docs/` and `scripts/`: supporting docs and local automation.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

For LLM/VLM features, create `.env` with the relevant values:

```bash
LLM_API_KEY=...
OPENAI_API_KEY=...
LLM_API_BASE=...
LLM_MODEL=...
VLM_API_KEY=...
```

## Collect Figure and Source Data Pairs

Run the main collector:

```bash
python download_nature_pairs.py \
  --max-articles 10 \
  --max-candidates 1000 \
  --out-dir downloads/nature_pairs
```

`--max-articles` means successful articles: an article counts only when at least one figure + Source Data pair is downloaded. Articles without pairable Source Data are written to `skipped.jsonl` and do not consume the success target.

`--max-candidates` limits how many candidate article URLs are inspected while trying to reach the success target.

You can also provide explicit article URLs:

```bash
python download_nature_pairs.py \
  --urls-file urls.txt \
  --max-articles 10 \
  --out-dir downloads/nature_pairs
```

Collector output:

- `downloads/nature_pairs/pairs.jsonl`: one record per matched figure + Source Data pair.
- `downloads/nature_pairs/articles/<article-id>/article.json`: article metadata and extracted pair metadata.
- `downloads/nature_pairs/articles/<article-id>/images/`: downloaded figure images.
- `downloads/nature_pairs/articles/<article-id>/data/`: downloaded Source Data files.
- `downloads/nature_pairs/skipped.jsonl`: inspected articles without pairable Source Data.
- `downloads/nature_pairs/errors.jsonl`: article-level failures.
- `downloads/nature_pairs/state.json`: resumable processed-URL state.

## Validate Downloaded Articles

Run preflight over the collected article folders:

```bash
python -m tools.process_articles preflight \
  --input downloads/nature_pairs/articles \
  --output downloads/nature_pairs/derived \
  --progress
```

Preflight output:

- `articles_manifest.jsonl`: article-level inventory.
- `figures_manifest.jsonl`: figure-level inventory with matched Source Data files.
- `preflight_report.md`: summary counts for articles, figures, captions, and Source Data matches.

## Segment Figures

Figure segmentation uses a VLM backend and writes derived panel metadata and cropped data-viz panels.

```bash
python -m tools.process_articles segment \
  --input downloads/nature_pairs/articles \
  --output downloads/nature_pairs/derived \
  --backend cliproxy \
  --model models/gemini-3-flash-preview \
  --progress
```

## Nature Search and Source Data Utilities

The `nature_download/` directory contains a secondary CLI for search-first workflows:

```bash
cd nature_download
python nature_all_in_one.py search --query "cancer" --max 20 --out outputs/search_run
python nature_all_in_one.py postfetch \
  --jsonl outputs/search_run/articles.jsonl \
  --out outputs/nature_content \
  --max-figs 12
```

`postfetch` downloads Source Data independently from figure discovery. If Source Data succeeds but no figure is fetched, the article is still kept and marked processed.

## PheroViz Agent

Run the chart-generation agent from `agent/`:

```bash
cd agent
python run_chain.py data/sales_demo.csv "季度对比" bar --rounds 1
```

Generated run artifacts are written under `agent/runs/` and are ignored by Git.

## Tests

```bash
python -m compileall -q download_nature_pairs.py tools agent nature_download
python -m pytest -q agent/tests
```

## Data and Git Hygiene

Generated data and downloads are intentionally ignored:

- `downloads/`
- `outputs/`
- `agent/runs/`
- `nature_download/outputs/`

Keep API keys in `.env`; do not commit real credentials.
