#!/usr/bin/env python3
"""
deep_nature_crawl.py — deep, rate-limit-resilient Nature "Source Data" crawl.

The Nature SEARCH endpoint tolerates only ~1-2 result pages per burst before it
serves an Akamai bot-challenge (rate-limit). A single year has up to ~1000 results
(~20 pages), so a one-shot per-year gather trips and never advances. This driver
instead PAGE-WALKS each year in tiny 2-page bursts (verified to return distinct
articles per page range) across BOTH date orders (date_desc + date_asc, so years
with >1000 results are fully reachable), cooling down between bursts and backing
off on a block. Article/data downloads (unaffected by the search limit) run in
parallel workers. Fully resumable via downloads/state.json — safe to stop/re-run.

Implements options 1 (finer splitting, via page windows) + 2 (dual date-order).

Each burst shells out to download_nature_pairs.py with a year+order search URL,
--start-page P --max-pages 2, which fetches those 2 pages and downloads new pairs.

Usage (from repo root):
  scripts/deep_nature_crawl.py                      # target 5000, years 2026..2016
  TARGET=5000 BURST_COOLDOWN=90 scripts/deep_nature_crawl.py

Tunables (env vars): TARGET, OUT, YEAR_END, YEAR_START, WORKERS, SLEEP_S,
  BURST_CANDIDATES, MAX_PAGE, BURST_COOLDOWN, BLOCK_COOLDOWN, MAX_BLOCK_RETRY,
  EXHAUST_STREAK, INITIAL_SLEEP.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import download_nature_pairs as dn  # for URL param building + the default search URL


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


TARGET = _env_int("TARGET", 5000)
OUT = os.environ.get("OUT", "downloads")
YEAR_END = _env_int("YEAR_END", 2026)
YEAR_START = _env_int("YEAR_START", 2016)
WORKERS = _env_int("WORKERS", 4)
SLEEP_S = os.environ.get("SLEEP_S", "8")
BURST_CANDIDATES = _env_int("BURST_CANDIDATES", 120)   # ~2 pages of 50 + margin
MAX_PAGE = _env_int("MAX_PAGE", 40)                    # walk pages 1,3,..,39 (≈2000/order cap)
BURST_PAGES = 2
BURST_COOLDOWN = _env_int("BURST_COOLDOWN", 60)        # between gentle bursts
BLOCK_COOLDOWN = _env_int("BLOCK_COOLDOWN", 1800)      # after a rate-limit block
MAX_BLOCK_RETRY = _env_int("MAX_BLOCK_RETRY", 3)
EXHAUST_STREAK = _env_int("EXHAUST_STREAK", 3)         # consecutive 0-new bursts => order done
INITIAL_SLEEP = _env_int("INITIAL_SLEEP", 0)
ORDERS = ("date_desc", "date_asc")


def count_articles() -> int:
    d = ROOT / OUT / "articles"
    return sum(1 for _ in d.iterdir()) if d.is_dir() else 0


def run_burst(year: int, order: str, start_page: int) -> int:
    """One gentle 2-page burst. Returns the crawler's exit code (2 == blocked)."""
    url = dn._replace_query_param(dn.DEFAULT_SEARCH_URL, "date_range", f"{year}-{year}")
    url = dn._replace_query_param(url, "order", order)
    cmd = [
        sys.executable, str(ROOT / "download_nature_pairs.py"),
        "--search-url", url,
        "--start-page", str(start_page), "--max-pages", str(BURST_PAGES),
        "--max-articles", "0", "--max-candidates", str(BURST_CANDIDATES),
        "--skip-images", "--max-data-file-mb", "20",
        "--workers", str(WORKERS), "--sleep-s", str(SLEEP_S),
        "--out-dir", OUT, "--no-progress",
    ]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def walk_order(year: int, order: str) -> None:
    """Page-walk one (year, order) in 2-page bursts until exhausted or target hit."""
    streak = 0
    page = 1
    while page <= MAX_PAGE:
        if count_articles() >= TARGET:
            return
        before = count_articles()
        retry = 0
        while True:
            rc = run_burst(year, order, page)
            if rc == 2:  # rate-limited
                retry += 1
                if retry > MAX_BLOCK_RETRY:
                    print(f"[deep] {year} {order} p{page}: blocked x{retry}, moving on", flush=True)
                    return
                print(f"[deep] {year} {order} p{page}: blocked, cooldown {BLOCK_COOLDOWN}s (retry {retry})", flush=True)
                time.sleep(BLOCK_COOLDOWN)
                continue
            break
        added = count_articles() - before
        total = count_articles()
        print(f"[deep] {year} {order} p{page}-{page+BURST_PAGES-1}: +{added} (total {total}/{TARGET})", flush=True)
        streak = streak + 1 if added == 0 else 0
        if streak >= EXHAUST_STREAK:
            print(f"[deep] {year} {order}: exhausted ({EXHAUST_STREAK} empty bursts)", flush=True)
            return
        page += BURST_PAGES
        time.sleep(BURST_COOLDOWN)


def main() -> int:
    if INITIAL_SLEEP > 0:
        print(f"[deep] initial cooldown {INITIAL_SLEEP}s ...", flush=True)
        time.sleep(INITIAL_SLEEP)
    print(f"[deep] start target={TARGET} years={YEAR_END}..{YEAR_START} workers={WORKERS} "
          f"burst={BURST_PAGES}pg/{BURST_CANDIDATES}cand cooldown={BURST_COOLDOWN}s", flush=True)
    print(f"[deep] initial articles={count_articles()}", flush=True)
    for year in range(YEAR_END, YEAR_START - 1, -1):
        if count_articles() >= TARGET:
            print(f"[deep] target reached ({count_articles()} >= {TARGET})", flush=True)
            break
        for order in ORDERS:
            if count_articles() >= TARGET:
                break
            print(f"[deep] ===== year {year} order {order} (have {count_articles()}/{TARGET}) =====", flush=True)
            walk_order(year, order)
    print(f"[deep] FINISHED. total articles={count_articles()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
