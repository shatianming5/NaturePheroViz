#!/usr/bin/env bash
# Batched, rate-limit-resilient Nature "Source Data" crawl.
#
# Nature aggressively rate-limits the SEARCH endpoint (Akamai "Client Challenge")
# for bulk discovery, while article/data downloads are fine. This driver gathers
# candidates ONE YEAR at a time (≤~1000 results/year => few gentle search pages),
# downloads them in parallel, cools down between years, and on a bot-challenge
# block (exit code 2) backs off and retries. Progress is resumable via
# downloads/state.json, so it is safe to stop/re-run any time.
#
# Usage (from repo root):
#   scripts/batched_nature_crawl.sh                 # defaults: target 5000, 2026..2016
#   TARGET=2000 SLEEP_S=5 scripts/batched_nature_crawl.sh
#
# Tunables (env vars):
#   TARGET          target distinct downloaded articles to stop at   (default 5000)
#   OUT             output dir (gitignored)                          (default downloads)
#   WORKERS         parallel download workers                        (default 4)
#   SLEEP_S         per-search-page delay (gentler = safer)          (default 4)
#   CAND_PER_YEAR   max candidates gathered per year                 (default 1200)
#   YEAR_END/START  inclusive year range, newest first              (default 2026/2016)
#   COOLDOWN        seconds to wait between years                    (default 180)
#   BLOCK_COOLDOWN  seconds to wait after a rate-limit block         (default 900)
#   MAX_BLOCK_RETRY retries per year on block before skipping        (default 3)
#   INITIAL_SLEEP   seconds to wait BEFORE the first search          (default 0)
#                   (set to a few hours to let an aggressive IP rate-limit reset)
set -u

OUT="${OUT:-downloads}"
TARGET="${TARGET:-5000}"
WORKERS="${WORKERS:-4}"
SLEEP_S="${SLEEP_S:-4}"
CAND_PER_YEAR="${CAND_PER_YEAR:-1200}"
YEAR_END="${YEAR_END:-2026}"
YEAR_START="${YEAR_START:-2016}"
COOLDOWN="${COOLDOWN:-180}"
BLOCK_COOLDOWN="${BLOCK_COOLDOWN:-900}"
MAX_BLOCK_RETRY="${MAX_BLOCK_RETRY:-3}"
INITIAL_SLEEP="${INITIAL_SLEEP:-0}"
PY="${PY:-python3}"

count_articles() { ls "$OUT/articles" 2>/dev/null | wc -l | tr -d ' '; }

if [ "$INITIAL_SLEEP" -gt 0 ]; then
  echo "[batched] initial cooldown ${INITIAL_SLEEP}s (let the search rate-limit reset) ..."
  sleep "$INITIAL_SLEEP"
fi

echo "[batched] start target=$TARGET years=$YEAR_END..$YEAR_START workers=$WORKERS sleep=$SLEEP_S"
echo "[batched] initial articles=$(count_articles)"

for ((y=YEAR_END; y>=YEAR_START; y--)); do
  have=$(count_articles)
  if [ "$have" -ge "$TARGET" ]; then
    echo "[batched] target reached ($have >= $TARGET) — stopping."
    break
  fi
  echo "[batched] ===== year $y (have $have/$TARGET) ====="
  retry=0
  while :; do
    "$PY" pipeline/collect/download_nature_pairs.py \
      --max-articles 0 --max-candidates "$CAND_PER_YEAR" \
      --skip-images --max-data-file-mb 20 \
      --split-by-year --year-start "$y" --year-end "$y" \
      --workers "$WORKERS" --sleep-s "$SLEEP_S" --out-dir "$OUT"
    rc=$?
    if [ "$rc" -eq 2 ]; then
      retry=$((retry + 1))
      if [ "$retry" -gt "$MAX_BLOCK_RETRY" ]; then
        echo "[batched] year $y still blocked after $MAX_BLOCK_RETRY retries — skipping to next year."
        break
      fi
      echo "[batched] year $y rate-limited (rc=2); cooldown ${BLOCK_COOLDOWN}s then retry #$retry"
      sleep "$BLOCK_COOLDOWN"
    else
      echo "[batched] year $y finished (rc=$rc); articles now $(count_articles)"
      break
    fi
  done
  # cool down between years to avoid re-tripping the search rate-limit
  if [ "$y" -gt "$YEAR_START" ]; then
    echo "[batched] cooldown ${COOLDOWN}s before next year"
    sleep "$COOLDOWN"
  fi
done

echo "[batched] FINISHED. total articles=$(count_articles)"
