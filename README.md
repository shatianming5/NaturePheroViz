# NaturePheroViz

NaturePheroViz is a research data pipeline for collecting Nature article figures, matching them with Source Data files, validating the downloaded corpus, and generating visualization outputs with the PheroViz agent.

The project is organized into clear top-level domains:

- `pipeline/`: Nature data-collection pipeline.
  - `pipeline/collect/`: download matched figure + Source Data pairs (`download_nature_pairs.py`, `nature_crawler.py`, `nature_all_in_one.py`).
  - `pipeline/process/`: preflight articles, build manifests, segment figures (`process_articles.py`).
  - `pipeline/helpers/`: alignment/repair helpers (`probe_alignment.py`, `repair_headers.py`).
- `agent/`: PheroViz slot pipeline for data-driven Matplotlib chart generation (+ `agent/eval/` research suite).
- `data/`: generated corpora and outputs (`downloads/`, `nature_pairs/`, `outputs/`); Git-ignored.
- `docs/`: docs, proposals (`docs/proposals/`), and refinement logs.
- `scripts/`: local automation (sync, crawl drivers, git hooks).

## Project Layout

```text
NaturePheroViz/
├── pipeline/              # Nature data-collection pipeline
│   ├── collect/           #   download figure + Source Data pairs
│   ├── process/           #   preflight / manifests / figure segmentation
│   └── helpers/           #   sheet-alignment + header-repair utilities
├── agent/                 # PheroViz chart-generation agent (L1–L4 slot pipeline)
│   ├── app/services/      #   orchestrator, plot_trace, fidelity_verifier, judge, slots
│   ├── configs/           #   judge rules + diagnostics map
│   ├── eval/              #   research / evaluation suite (+ results_*/)
│   └── data/              #   bundled sample datasets (tracked)
├── data/                  # generated corpora + outputs (Git-ignored)
│   ├── downloads/         #   Source-Data corpus
│   ├── nature_pairs/      #   figure ↔ Source-Data pairs
│   └── outputs/           #   search / postfetch outputs
├── docs/                  # docs, proposals/, refinement logs, plan.md
└── scripts/               # local automation (sync, crawl drivers, git hooks)
```

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
python pipeline/collect/download_nature_pairs.py \
  --max-articles 10 \
  --max-candidates 1000 \
  --out-dir data/downloads/nature_pairs
```

`--max-articles` means successful articles: an article counts only when at least one figure + Source Data pair is downloaded. Articles without pairable Source Data are written to `skipped.jsonl` and do not consume the success target.

`--max-candidates` limits how many candidate article URLs are inspected while trying to reach the success target.

You can also provide explicit article URLs:

```bash
python pipeline/collect/download_nature_pairs.py \
  --urls-file urls.txt \
  --max-articles 10 \
  --out-dir data/downloads/nature_pairs
```

Collector output:

- `data/downloads/nature_pairs/pairs.jsonl`: one record per matched figure + Source Data pair.
- `data/downloads/nature_pairs/articles/<article-id>/article.json`: article metadata and extracted pair metadata.
- `data/downloads/nature_pairs/articles/<article-id>/images/`: downloaded figure images.
- `data/downloads/nature_pairs/articles/<article-id>/data/`: downloaded Source Data files.
- `data/downloads/nature_pairs/skipped.jsonl`: inspected articles without pairable Source Data.
- `data/downloads/nature_pairs/errors.jsonl`: article-level failures.
- `data/downloads/nature_pairs/state.json`: resumable processed-URL state.

## Validate Downloaded Articles

Run preflight over the collected article folders:

```bash
python -m pipeline.process.process_articles preflight \
  --input data/downloads/nature_pairs/articles \
  --output data/downloads/nature_pairs/derived \
  --progress
```

Preflight output:

- `articles_manifest.jsonl`: article-level inventory.
- `figures_manifest.jsonl`: figure-level inventory with matched Source Data files.
- `preflight_report.md`: summary counts for articles, figures, captions, and Source Data matches.

## Segment Figures

Figure segmentation uses a VLM backend and writes derived panel metadata and cropped data-viz panels.

```bash
python -m pipeline.process.process_articles segment \
  --input data/downloads/nature_pairs/articles \
  --output data/downloads/nature_pairs/derived \
  --backend cliproxy \
  --model models/gemini-3-flash-preview \
  --progress
```

## Nature Search and Source Data Utilities

The `pipeline/collect/nature_all_in_one.py` CLI provides search-first workflows:

```bash
python pipeline/collect/nature_all_in_one.py search --query "cancer" --max 20 --out data/outputs/search_run
python pipeline/collect/nature_all_in_one.py postfetch \
  --jsonl data/outputs/search_run/articles.jsonl \
  --out data/outputs/nature_content \
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
python -m compileall -q pipeline agent
python -m pytest -q agent/tests
```

## Data and Git Hygiene

Generated data and downloads are intentionally ignored:

- `data/` (downloads, nature_pairs, outputs)
- `agent/runs/`

Keep API keys in `.env`; do not commit real credentials.
