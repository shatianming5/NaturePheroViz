#!/usr/bin/env python3
"""
Semi-automatic header/layout repair for Nature source-data sheets.

Real-world Nature Excel conventions break `pandas header=0`:
  (1) the real header sits a few rows down (row 0 is a title like
      "Data associated with Extended Data Fig 3a")
  (2) several sub-tables are laid out SIDE BY SIDE, separated by an all-empty
      spacer column ("Unnamed: N" that is entirely NaN)
  (3) the header is split across 2 rows (name row + unit row, e.g.
      "Temperature" / "K", "Resistivity" / "mOhm cm")

This repairer reads a sheet with NO header, then:
  - splits into horizontal blocks on fully-empty columns
  - for each block, finds the header row(s) by scanning the first few rows for
    the one that is mostly text and is followed by mostly-numeric rows
  - merges a unit row into the header when present
  - emits one tidy numeric DataFrame per block

Output per sheet: list of blocks, each {header: [...], n_numeric_cols, shape, df}.
This is the candidate plot-data; a human still confirms x/y/series mapping.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path("nature_pairs")


def _is_number(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return not (isinstance(v, float) and pd.isna(v))
    try:
        float(str(v).replace(",", "").replace("%", "").strip())
        return True
    except (ValueError, TypeError):
        return False


def _row_numeric_frac(row) -> float:
    cells = [c for c in row if not (pd.isna(c) if not isinstance(c, str) else c.strip() == "")]
    if not cells:
        return 0.0
    return sum(_is_number(c) for c in cells) / len(cells)


def _row_text_frac(row) -> float:
    cells = [c for c in row if not (pd.isna(c) if not isinstance(c, str) else c.strip() == "")]
    if not cells:
        return 0.0
    txt = sum(1 for c in cells if isinstance(c, str) and not _is_number(c) and c.strip())
    return txt / len(cells)


def _empty_col(series) -> bool:
    return series.apply(lambda v: pd.isna(v) or (isinstance(v, str) and not v.strip())).all()


def split_horizontal_blocks(raw: pd.DataFrame):
    """Split columns into blocks separated by fully-empty spacer columns."""
    blocks = []
    cur = []
    for ci in range(raw.shape[1]):
        if _empty_col(raw.iloc[:, ci]):
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(ci)
    if cur:
        blocks.append(cur)
    return blocks


def find_header(block: pd.DataFrame, scan=6):
    """
    Return (header_names, data_start_row). Strategy:
      - find first row that is mostly TEXT and whose NEXT row(s) are mostly numeric
      - if the row right after is also mostly text (unit row), merge "name (unit)"
    Falls back to (synthetic names, 0) if no header found but data is numeric.
    """
    n = min(scan, block.shape[0])
    for r in range(n):
        row = block.iloc[r].tolist()
        if _row_text_frac(row) < 0.5:
            continue
        # need numeric data somewhere below
        below = block.iloc[r + 1 : r + 4]
        if below.empty:
            continue
        numeric_below = max((_row_numeric_frac(below.iloc[k]) for k in range(len(below))), default=0)
        if numeric_below < 0.5:
            continue
        names = [str(x).strip() if not pd.isna(x) else f"col{j}" for j, x in enumerate(row)]
        data_start = r + 1
        # unit row?
        unit_row = block.iloc[r + 1].tolist()
        if _row_text_frac(unit_row) >= 0.5 and _row_numeric_frac(unit_row) < 0.5:
            units = [str(x).strip() if not pd.isna(x) else "" for x in unit_row]
            names = [f"{nm} ({u})" if u and u.lower() != "nan" else nm for nm, u in zip(names, units)]
            data_start = r + 2
        return names, data_start
    # no text header found; if block itself is numeric, synthesize
    if _row_numeric_frac(block.iloc[0]) >= 0.5:
        return [f"col{j}" for j in range(block.shape[1])], 0
    return None, None


def repair_sheet(path: Path, sheet: str):
    raw = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
    # drop fully-empty trailing rows
    raw = raw.dropna(how="all").reset_index(drop=True)
    if raw.empty:
        return []
    col_blocks = split_horizontal_blocks(raw)
    out = []
    for cols in col_blocks:
        block = raw.iloc[:, cols].reset_index(drop=True)
        # Trim to THIS block's own extent: side-by-side sub-tables have very
        # different lengths, so a short block is otherwise padded with NaN rows
        # left behind by a longer neighbour. Drop rows that are all-NaN within
        # the block only.
        block = block.dropna(how="all").reset_index(drop=True)
        if block.empty:
            continue
        names, start = find_header(block, scan=6)
        if names is None:
            out.append({"status": "no_header", "header": None, "shape": list(block.shape)})
            continue
        data = block.iloc[start:].reset_index(drop=True)
        data.columns = names[: data.shape[1]] + [f"col{j}" for j in range(len(names), data.shape[1])]
        # coerce numeric where possible
        numeric_cols = 0
        for c in data.columns:
            coerced = pd.to_numeric(data[c], errors="coerce")
            if coerced.notna().mean() >= 0.5:
                data[c] = coerced
                numeric_cols += 1
        data = data.dropna(how="all").reset_index(drop=True)
        status = "ok" if (numeric_cols >= 1 and data.shape[0] >= 2) else "weak"
        out.append(
            {
                "status": status,
                "header": list(data.columns),
                "n_numeric_cols": numeric_cols,
                "shape": list(data.shape),
                "preview": data.head(2).to_dict("records"),
            }
        )
    return out


def main():
    picked = json.load(open(ROOT / "_probe_pick.json"))
    n_ok = n_weak = n_fail = 0
    for i, s in enumerate(picked, 1):
        f = ROOT / s["data_path"]
        try:
            blocks = repair_sheet(f, s["sheet"])
        except Exception as e:
            print(f"\n{i:2}. {s['sheet']:28} REPAIR-CRASH {repr(e)[:50]}")
            n_fail += 1
            continue
        ok_blocks = [b for b in blocks if b.get("status") == "ok"]
        tag = "OK  " if ok_blocks else ("WEAK" if any(b.get("status") == "weak" for b in blocks) else "FAIL")
        if ok_blocks:
            n_ok += 1
        elif tag == "WEAK":
            n_weak += 1
        else:
            n_fail += 1
        print(f"\n{i:2}. [{tag}] {s['article_id']} {s['figure_key']} '{s['sheet']}' -> {len(blocks)} block(s), {len(ok_blocks)} usable")
        for b in blocks:
            if b.get("status") == "ok":
                hdr = [h for h in b["header"] if not str(h).startswith("col")][:6]
                print(f"        block {b['shape']}  {b['n_numeric_cols']} numeric cols  header={hdr}")
    print(f"\n=== summary: {n_ok} OK / {n_weak} WEAK / {n_fail} FAIL  (of {len(picked)}) ===")
    print(f"    baseline header=0 usable was ~5/20; repaired OK = {n_ok}/{len(picked)}")


if __name__ == "__main__":
    main()
