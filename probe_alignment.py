#!/usr/bin/env python3
"""
Probe how many CLEAN (figure-panel <-> source-data sheet) eval samples we can
build from the crawled Nature pairs.

For each labeled pair (figure image <-> source-data xlsx), we:
  1. parse every sheet name into (kind, fig_number, panels) via regex
  2. keep sheets whose parsed (kind, fig_number) matches the pair's figure_key
  3. check the sheet actually holds a usable numeric table (header + numbers,
     reasonable shape) — i.e. something a fidelity verifier could diff against
  4. report per-pair and aggregate yield

This tells us how much of the 359 xlsx-labeled pairs is *directly usable* as a
real-world fidelity benchmark, vs needs manual cleanup.
"""
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path("nature_pairs")
PAIRS = ROOT / "pairs.jsonl"

# sheet-name -> (kind, fig_no, panels[])  e.g.
#   "Figure 1a"          -> ("main", 1, ["a"])
#   "Data Fig. 1"        -> ("main", 1, [])
#   "ED Data Fig. 4c"    -> ("extended", 4, ["c"])
#   "ED Data Fig. 1a-b"  -> ("extended", 1, ["a","b"])
#   "Extended Data Fig 2a"-> ("extended", 2, ["a"])
_PANEL = r"([a-z](?:\s*[-,–]\s*[a-z])*)?"
_SHEET_RE = re.compile(
    r"(?:source\s*data\s*)?"
    r"(?P<ext>extended\s*data|ed(?:\s*data)?)?\s*"
    r"(?:data\s*)?fig(?:ure)?\.?\s*"
    r"(?P<num>\d+)\s*"
    r"(?P<panel>[a-z](?:\s*[-,–]\s*[a-z])*)?",
    re.IGNORECASE,
)


def parse_sheet_name(name: str):
    m = _SHEET_RE.search(name or "")
    if not m:
        # Fallback: abbreviated forms with no "Fig" token, e.g. "ED 1a", "ED 3b-2".
        # "ED <num><panel>" = Extended Data Figure <num> panel.
        m2 = re.search(r"\bED\s*(?P<num>\d+)\s*(?P<panel>[a-z](?:\s*[-,–]\s*[a-z])*)?", name or "", re.IGNORECASE)
        if not m2:
            return None
        try:
            num = int(m2.group("num"))
        except (TypeError, ValueError):
            return None
        panels = re.findall(r"[a-z]", (m2.group("panel") or "").lower())
        return "extended", num, panels
    kind = "extended" if m.group("ext") else "main"
    try:
        num = int(m.group("num"))
    except (TypeError, ValueError):
        return None
    panel_raw = (m.group("panel") or "").lower()
    panels = re.findall(r"[a-z]", panel_raw)
    return kind, num, panels


def sheet_is_numeric_table(df: pd.DataFrame) -> bool:
    """A sheet usable for fidelity diffing: has numbers, plausible table shape."""
    if df is None or df.empty:
        return False
    if df.shape[0] < 2 or df.shape[1] < 1:
        return False
    # count numeric-coercible cells
    num = 0
    total = 0
    for col in df.columns:
        s = pd.to_numeric(df[col], errors="coerce")
        num += int(s.notna().sum())
        total += len(s)
    if total == 0:
        return False
    return (num / total) >= 0.30  # at least 30% of cells are real numbers


def figure_key_of(kind: str, num: int) -> str:
    return f"{kind}:{num}"


def main():
    recs = [json.loads(l) for l in open(PAIRS, encoding="utf-8")]
    labeled_xlsx = [
        r for r in recs if r.get("data_label") and r["data_path"].endswith(".xlsx")
    ]
    print(f"labeled xlsx pairs: {len(labeled_xlsx)}")

    # cache opened workbooks
    book_cache: dict[str, pd.ExcelFile | None] = {}

    def book(path: str):
        if path not in book_cache:
            try:
                book_cache[path] = pd.ExcelFile(Path(ROOT, path))
            except Exception:
                book_cache[path] = None
        return book_cache[path]

    stats = Counter()
    clean_samples = []  # (article, figure_key, sheet, shape)
    per_pair_matched = []

    for r in labeled_xlsx:
        stats["pairs_seen"] += 1
        fk = r["figure_key"]  # e.g. "main:1"
        try:
            want_kind, want_num = fk.split(":")
            want_num = int(want_num)
        except Exception:
            stats["bad_figure_key"] += 1
            continue
        xl = book(r["data_path"])
        if xl is None:
            stats["xlsx_open_fail"] += 1
            continue

        matched_sheets = []
        for sh in xl.sheet_names:
            parsed = parse_sheet_name(sh)
            if not parsed:
                continue
            kind, num, panels = parsed
            if kind == want_kind and num == want_num:
                matched_sheets.append((sh, panels))

        if not matched_sheets:
            stats["no_sheet_match"] += 1
            continue
        stats["pair_has_matching_sheet"] += 1

        # check numeric usability of matched sheets
        usable = 0
        for sh, panels in matched_sheets:
            try:
                df = xl.parse(sh, header=0, nrows=200)
            except Exception:
                continue
            if sheet_is_numeric_table(df):
                usable += 1
                clean_samples.append(
                    {
                        "article_id": r["article_id"],
                        "figure_key": fk,
                        "image_path": r["image_path"],
                        "data_path": r["data_path"],
                        "sheet": sh,
                        "panels": panels,
                        "rows": int(df.shape[0]),
                        "cols": int(df.shape[1]),
                    }
                )
        if usable:
            stats["pair_has_usable_numeric_sheet"] += 1
            per_pair_matched.append((fk, usable, len(matched_sheets)))

    print("\n=== aggregate ===")
    for k in [
        "pairs_seen",
        "xlsx_open_fail",
        "bad_figure_key",
        "no_sheet_match",
        "pair_has_matching_sheet",
        "pair_has_usable_numeric_sheet",
    ]:
        print(f"  {k}: {stats[k]}")

    n = stats["pairs_seen"] or 1
    print(f"\n  sheet-name match rate:   {stats['pair_has_matching_sheet']}/{n} = {stats['pair_has_matching_sheet']/n:.0%}")
    print(f"  usable-numeric rate:     {stats['pair_has_usable_numeric_sheet']}/{n} = {stats['pair_has_usable_numeric_sheet']/n:.0%}")
    print(f"\n  CLEAN panel-level eval samples (sheet granularity): {len(clean_samples)}")
    arts = {s['article_id'] for s in clean_samples}
    print(f"  spanning distinct articles: {len(arts)}")

    # write the clean sample manifest
    out = ROOT / "eval_alignment_probe.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for s in clean_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\n  wrote manifest: {out}")

    print("\n=== sample clean alignments ===")
    for s in clean_samples[:8]:
        print(f"  {s['article_id']} {s['figure_key']:11} sheet='{s['sheet']}' panels={s['panels']} shape=({s['rows']},{s['cols']})")


if __name__ == "__main__":
    main()
