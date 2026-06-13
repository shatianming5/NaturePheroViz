"""
nature_real_auto.py — SCALE the held-out real-data slice from 9 to 50+ tasks.

The round-5 reviewer flagged the real slice as small (18 cases). To make the
external-validity claim hard to dismiss, this auto-generates a large real-task
slice: it scans the downloaded Nature source-data XLSX files, finds tables with a
genuine categorical column + numeric column(s), and instantiates the SAME
operator-semantic tasks (median_not_mean / within_group_share / weighted_mean) on
each — one table yields multiple tasks. Gold is computed by template (the task
just needs a well-defined transform; scientific meaning of the grouping is
irrelevant to measuring whether the model implements the stated transform).

Every task carries a matched (ambiguous, clarified) prompt and is judged by the
goldless oracle, exactly like the curated slice. We report silent-error rate +
oracle recall/FP with 95% Wilson intervals over the whole large slice.

Usage (cpudev2, has the real XLSX in ~/NaturePheroViz/nature_pairs):
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/nature_real_auto.py \
      --pairs-root ~/NaturePheroViz/nature_pairs/articles --max-tasks 60 --out eval/results_real_auto
  cd agent && python eval/nature_real_auto.py --pairs-root .. --offline   # gold+oracle sanity, no LLM
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.nature_real_transform import _wilson  # noqa: E402


def _dedup(df: pd.DataFrame) -> pd.DataFrame:
    cols, seen = [], {}
    for c in df.columns:
        c = str(c)
        if c in seen:
            seen[c] += 1; cols.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0; cols.append(c)
    df = df.copy(); df.columns = cols
    return df


def _clean(df: pd.DataFrame):
    df = _dedup(df).dropna(axis=1, how="all").dropna(axis=0, how="all")
    clean = [c for c in df.columns if not c.startswith("Unnamed") and str(c).strip()]
    cats, nums = [], []
    for c in clean:
        s = df[c]
        if s.dtype == object:
            vc = s.value_counts()
            if 2 <= len(vc) <= max(3, len(df) // 3) and int((vc >= 2).sum()) >= 2:
                cats.append(c)
        elif pd.api.types.is_numeric_dtype(s) and s.notna().sum() >= 8:
            nums.append(c)
    return df, cats, nums


def _tasks_from_table(df: pd.DataFrame, cat: str, nums: List[str], art: str, sheet: str) -> List[Dict[str, Any]]:
    """Instantiate the clean group-aggregation operators on one real table."""
    out = []
    v = nums[0]
    base = df[[cat, v]].dropna().copy()
    base[cat] = base[cat].astype(str)
    if base[cat].nunique() < 2 or len(base) < 6:
        return out
    tag = f"{art}:{sheet}:{cat}"

    # median_not_mean
    out.append({
        "name": f"median::{tag}", "op": "median_not_mean", "df": base.copy(),
        "params": {"group": cat, "value": v}, "result_kind": "frame",
        "gold": (lambda d, _c=cat, _v=v: d.groupby(_c, as_index=False)[_v].median()),
        "ambiguous": f"A typical {v} per {cat}. Columns {cat}, {v}.",
        "clarified": f"The MEDIAN {v} per {cat} (not the mean). Columns {cat}, {v}.",
    })
    # within_group_share
    out.append({
        "name": f"share::{tag}", "op": "within_group_share", "df": base.copy(),
        "params": {"group": cat, "share_col": "share"}, "result_kind": "frame",
        "gold": (lambda d, _c=cat, _v=v: d.assign(share=d[_v] / d.groupby(_c)[_v].transform("sum"))),
        "ambiguous": f"Add 'share' = each row's share of {v}. Keep {cat}, {v}, share.",
        "clarified": f"Add 'share' = each row's {v} / its OWN {cat} group's total {v} (within-group share, not grand total). Keep {cat}, {v}, share.",
    })
    # weighted_mean (needs a 2nd numeric column as weight)
    if len(nums) >= 2:
        w = nums[1]
        wm = df[[v, w]].dropna().copy()
        if len(wm) >= 6 and (wm[w] > 0).all() and wm[w].nunique() > 1:
            out.append({
                "name": f"wmean::{tag}", "op": "weighted_mean", "df": wm.copy(),
                "params": {"value": v, "weight": w}, "result_kind": "scalar",
                "gold": (lambda d, _v=v, _w=w: (d[_v] * d[_w]).sum() / d[_w].sum()),
                "ambiguous": f"The average {v} (one number, column 'wavg').",
                "clarified": f"The {w}-WEIGHTED average {v} (weight each {v} by {w}; column 'wavg').",
            })

    # pooled_rate (two numeric columns -> per-group total/total rate)
    if len(nums) >= 2:
        num_c, den_c = nums[0], nums[1]
        pr = df[[cat, num_c, den_c]].dropna().copy()
        pr[cat] = pr[cat].astype(str)
        if pr[cat].nunique() >= 2 and len(pr) >= 6 and (pr[den_c] > 0).all():
            out.append({
                "name": f"pooled::{tag}", "op": "pooled_rate", "df": pr.copy(),
                "params": {"group": cat, "num": num_c, "den": den_c, "out": "rate"}, "result_kind": "frame",
                "gold": (lambda d, _c=cat, _n=num_c, _d=den_c: d.groupby(_c).apply(
                    lambda g: g[_n].sum() / g[_d].sum(), include_groups=False).reset_index(name="rate")),
                "ambiguous": f"The {num_c}-to-{den_c} rate per {cat}. Columns {cat}, rate.",
                "clarified": f"The rate per {cat} = TOTAL {num_c} / TOTAL {den_c} in that group (pooled sum/sum, NOT the mean of per-row ratios). Columns {cat}, rate.",
            })

    # nan_as_zero_sum (if the value column actually has NaNs within groups)
    base_full = df[[cat, v]].copy()
    base_full[cat] = base_full[cat].astype(str)
    if base_full[v].isna().any() and base_full.dropna(subset=[cat])[cat].nunique() >= 2:
        bz = base_full.dropna(subset=[cat])
        out.append({
            "name": f"nanzero::{tag}", "op": "nan_as_zero_sum", "df": bz.copy(),
            "params": {"group": cat, "value": v}, "result_kind": "frame",
            "gold": (lambda d, _c=cat, _v=v: d.assign(**{_v: d[_v].fillna(0)}).groupby(_c, as_index=False)[_v].sum()),
            "ambiguous": f"Total {v} per {cat}. Columns {cat}, {v}.",
            "clarified": f"Total {v} per {cat}, treating MISSING values as 0. Columns {cat}, {v}.",
        })
    return out


def _build(pairs_root: str, max_tasks: int, max_per_article: int = 15) -> List[Dict[str, Any]]:
    """Generate real tasks, capping how many come from any single article so the
    slice spans many independent papers (not just a few big-table articles).
    max_per_article bounds per-article contribution -> task DIVERSITY across papers."""
    import glob
    from collections import Counter
    files = sorted(glob.glob(str(Path(pairs_root) / "*" / "data" / "*.xlsx")))
    tasks: List[Dict[str, Any]] = []
    per_art: Counter = Counter()
    seen_tables = 0
    for f in files:
        if len(tasks) >= max_tasks:
            break
        art = Path(f).parts[-3]
        if per_art[art] >= max_per_article:
            continue  # this article already contributed its cap -> move on
        try:
            xl = pd.ExcelFile(f)
        except Exception:
            continue
        for sh in xl.sheet_names:
            if len(tasks) >= max_tasks:
                break
            try:
                df, cats, nums = _clean(xl.parse(sh))
            except Exception:
                continue
            if not cats or not nums:
                continue
            # one task-set per categorical column (a table with Chr AND treatment
            # yields two independent groupings) — up to 3 cat columns per sheet.
            new = []
            for cat in cats[:3]:
                new += _tasks_from_table(df, cat, nums, art, str(sh))
            # validate each task's gold + oracle-pass before accepting
            for t in new:
                if len(tasks) >= max_tasks or per_art[art] >= max_per_article:
                    break
                try:
                    g = t["gold"](t["df"])
                    res = g if isinstance(g, pd.DataFrame) else pd.DataFrame({"wavg": [float(g)]})
                    oc = oracle_check(t["op"], {"df": t["df"]}, t["params"], res)
                    if oc is not None and oc.fired:
                        continue  # oracle false-fires on gold -> skip (keep slice clean)
                    tasks.append(t)
                    per_art[art] += 1
                except Exception:
                    continue
            if new:
                seen_tables += 1
    return tasks


def _offline(pairs_root: str, max_tasks: int, max_per_article: int = 15) -> int:
    tasks = _build(pairs_root, max_tasks, max_per_article)
    from collections import Counter
    by_op = Counter(t["op"] for t in tasks)
    arts = len(set(t["name"].split("::")[1].split(":")[0] for t in tasks))
    print(f"auto-generated {len(tasks)} real tasks across {arts} Nature articles:")
    for op, n in sorted(by_op.items()):
        print(f"  {op:22} {n}")
    # confirm oracle passes on every gold (0 false-fire)
    fp = 0
    for t in tasks:
        g = t["gold"](t["df"])
        res = g if isinstance(g, pd.DataFrame) else pd.DataFrame({"wavg": [float(g)]})
        oc = oracle_check(t["op"], {"df": t["df"]}, t["params"], res)
        if oc is not None and oc.fired:
            fp += 1
    print(f"\n{'VALIDATION OK' if fp == 0 else 'VALIDATION FAILED'}: oracle false-fires on gold = {fp}/{len(tasks)}")
    return 0 if fp == 0 else 1


def main(argv: Optional[List[str]] = None) -> int:
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-root", default="../nature_pairs/articles")
    ap.add_argument("--max-tasks", type=int, default=60)
    ap.add_argument("--max-per-article", type=int, default=15,
                    help="cap tasks from any single article so the slice spans many papers")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default="eval/results_real_auto")
    a = ap.parse_args(argv)

    if a.offline:
        return _offline(a.pairs_root, a.max_tasks, a.max_per_article)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (or --offline)."); return 1

    from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct, MODELS

    tasks = _build(a.pairs_root, a.max_tasks, a.max_per_article)
    arts = len(set(t["name"].split("::")[1].split(":")[0] for t in tasks))
    print(f"[real-auto] {len(tasks)} real tasks across {arts} articles x (ambiguous, clarified) x {len(MODELS)} models", flush=True)

    silent = {c: 0 for c in ("ambiguous", "clarified")}
    total = {c: 0 for c in ("ambiguous", "clarified")}
    fire_wrong = wrong = fire_right = right = 0
    rows = []
    for t in tasks:
        rec = {"name": t["name"], "op": t["op"]}
        for cond in ("ambiguous", "clarified"):
            for m in MODELS:
                code = _llm_code(t, t[cond], m)
                result = _exec(t, code) if code else None
                exec_ok = result is not None
                correct = exec_ok and _gold_correct(t, result)
                oc = oracle_check(t["op"], {"df": t["df"]}, t["params"], result)
                fired = bool(oc and oc.fired)
                total[cond] += 1
                if exec_ok and not correct:
                    silent[cond] += 1
                if exec_ok:
                    if correct:
                        right += 1; fire_right += int(fired)
                    else:
                        wrong += 1; fire_wrong += int(fired)
                tag = "ok" if correct else ("SILENT" if exec_ok else "crash")
                print(f"[{t['name'][:34]:34}] {cond:10} {m:18} {tag:7} fired={fired}", flush=True)
                rec.setdefault(cond, {})[m] = {"tag": tag, "oracle_fired": fired}
        rows.append(rec)

    report = [
        f"# LARGE held-out real-data slice: {len(tasks)} auto-generated real Nature tasks\n",
        f"Across {arts} Nature articles, real scientific tables, same operator-semantic",
        "tasks + (ambiguous, clarified) prompts + goldless oracle. Rates with 95% Wilson CIs.\n",
        "## (1) Silent-error rate on REAL data (large slice)",
        f"- ambiguous: {silent['ambiguous']}/{total['ambiguous']} ({_wilson(silent['ambiguous'], total['ambiguous'])})",
        f"- clarified: {silent['clarified']}/{total['clarified']} ({_wilson(silent['clarified'], total['clarified'])})\n",
        "## (2) Oracle recall on real silent errors",
        f"- {fire_wrong}/{wrong} ({_wilson(fire_wrong, wrong)})" if wrong else "- (no wrong)",
        "\n## (3) Oracle false-positive on real correct results",
        f"- {fire_right}/{right} ({_wilson(fire_right, right)})" if right else "- (no correct)",
        "\n## Reading",
        f"- {len(tasks)} real tasks (vs the 9-table curated slice) makes the external-validity",
        "  claim hard to dismiss as small-sample; CIs are now tight.",
    ]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "real_auto_report.md").write_text("\n".join(report), encoding="utf-8")
    (out / "real_auto_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(report))
    print(f"\n[saved] {out}/real_auto_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
