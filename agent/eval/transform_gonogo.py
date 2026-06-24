"""
transform_gonogo.py — go/no-go: do LLMs get DATA TRANSFORMS wrong?

The plotting go/no-go showed strong LLMs draw clean data correctly (0% silent
error). The remaining hypothesis: LLMs slip on DATA TRANSFORMS (groupby/pivot/
filter/merge/topN/unit) where the intent is ambiguous or multi-step. If true,
execution-traced verification of the *transform output* is where the real value
is. This probe measures the transform error rate directly.

Each case: (raw df, natural-language request, gold transform). The LLM writes
pandas code producing `result`; we exec it and compare to the gold DataFrame
(values + shape, order-insensitive). Error = result != gold (or exec fail).

Requires LLM proxy env. Run:  cd agent && python eval/transform_gonogo.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

MODELS = ["gpt-4o", "claude-sonnet-4.6"]


# ===========================================================================
# Cases: (name, raw_df, request, gold_fn). gold_fn(df)->DataFrame is the
# CORRECT transform (hand-written). Designed around where LLMs are known to
# slip: aggregation grain, join keys/how, filter boundaries, pivot, topN ties,
# unit/ratio, multi-step.
# ===========================================================================


def _cases() -> List[Dict[str, Any]]:
    """Trap/ambiguous transforms — where LLMs are likely to misread intent.
    (Simple transforms like groupby-sum are trivially correct and uninformative;
    these probe genuine ambiguity / common mistakes.)"""
    out: List[Dict[str, Any]] = []

    # 1. weighted mean, not arithmetic: avg price WEIGHTED by quantity
    df1 = pd.DataFrame({"product": ["a", "b", "c"], "price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})
    out.append({"name": "weighted_mean_price", "df": df1,
                "req": "The quantity-weighted average price (weight each product's price by its qty).",
                "gold": lambda d: pd.DataFrame({"wavg": [(d["price"] * d["qty"]).sum() / d["qty"].sum()]})})

    # 2. month-over-month growth RATE (pct change vs previous month), first = NaN dropped
    df2 = pd.DataFrame({"month": ["Jan", "Feb", "Mar", "Apr"], "rev": [100.0, 150.0, 120.0, 180.0]})
    out.append({"name": "mom_growth_rate", "df": df2,
                "req": "Month-over-month growth rate of rev (fractional change vs the previous month). "
                       "Return month and growth, excluding the first month which has no prior.",
                "gold": lambda d: pd.DataFrame({"month": ["Feb", "Mar", "Apr"],
                                                "growth": [0.5, -0.2, 0.5]})})

    # 3. share of GROUP total (not grand total) — common confusion
    df3 = pd.DataFrame({"region": ["N", "N", "S", "S"], "city": ["a", "b", "c", "d"], "sales": [30, 10, 20, 20]})
    out.append({"name": "share_within_group", "df": df3,
                "req": "For each city, its sales as a fraction of ITS OWN region's total (within-region share, not of grand total).",
                "gold": lambda d: d.assign(share=d["sales"] / d.groupby("region")["sales"].transform("sum"))})

    # 4. join that should be LEFT (keep all left rows) despite missing matches
    df4 = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    df4b = pd.DataFrame({"id": [1, 3], "score": [88, 99]})
    out.append({"name": "left_join_keep_all", "df": df4, "df2": df4b,
                "req": "Attach score from df2 to df, but KEEP ALL rows of df even when there is no matching score (missing score stays empty/NaN).",
                "gold": lambda d, d2: d.merge(d2, on="id", how="left")})

    # 5. NaN-aware mean: average ignoring missing, AND report count of non-missing
    df5 = pd.DataFrame({"grp": ["x", "x", "x", "y", "y"], "val": [10.0, np.nan, 20.0, 5.0, np.nan]})
    out.append({"name": "mean_skipna_with_count", "df": df5,
                "req": "Per group: the mean of val ignoring missing values, and n = count of NON-missing val.",
                "gold": lambda d: d.groupby("grp").agg(mean=("val", "mean"), n=("val", "count")).reset_index()})

    # 6. dedup before aggregate: total revenue per region counting each ORDER once
    df6 = pd.DataFrame({"region": ["N", "N", "N", "S"], "order_id": [1, 1, 2, 3], "rev": [50, 50, 30, 40]})
    out.append({"name": "dedup_then_sum", "df": df6,
                "req": "Total revenue per region, but each order_id must be counted only ONCE (rows are duplicated line-items of the same order).",
                "gold": lambda d: d.drop_duplicates("order_id").groupby("region", as_index=False)["rev"].sum()})

    # 7. cumulative sum within group, ordered by month
    df7 = pd.DataFrame({"grp": ["x", "x", "y", "x", "y"], "month": [1, 2, 1, 3, 2], "v": [10, 20, 5, 30, 15]})
    out.append({"name": "cumsum_within_group", "df": df7,
                "req": "Running (cumulative) total of v within each grp, ordered by month. Keep grp, month, and the cumulative value.",
                "gold": lambda d: (d.sort_values(["grp", "month"])
                                   .assign(cum=lambda x: x.groupby("grp")["v"].cumsum())
                                   [["grp", "month", "cum"]].reset_index(drop=True))})

    # 8. topN PER group (not overall): top-2 products by sales within each region
    df8 = pd.DataFrame({"region": ["N", "N", "N", "S", "S", "S"], "product": list("abcdef"),
                        "sales": [5, 9, 3, 8, 2, 6]})
    out.append({"name": "top2_per_group", "df": df8,
                "req": "The top 2 products by sales WITHIN EACH region (not top 2 overall).",
                "gold": lambda d: (d.sort_values("sales", ascending=False).groupby("region").head(2)
                                   .sort_values(["region", "sales"], ascending=[True, False]).reset_index(drop=True))})

    # 9. median not mean (LLM often defaults to mean)
    df9 = pd.DataFrame({"grp": ["x", "x", "x", "y", "y", "y"], "v": [1.0, 2.0, 9.0, 4.0, 5.0, 60.0]})
    out.append({"name": "median_per_group", "df": df9,
                "req": "The MEDIAN of v per group (not the mean).",
                "gold": lambda d: d.groupby("grp", as_index=False)["v"].median()})

    # 10. percentage points vs ratio: difference of two rates expressed in pct points
    df10 = pd.DataFrame({"team": ["A", "B"], "rate_2023": [0.20, 0.50], "rate_2024": [0.30, 0.55]})
    out.append({"name": "pct_point_change", "df": df10,
                "req": "Change from rate_2023 to rate_2024 in PERCENTAGE POINTS (e.g. 0.20->0.30 is 10 points), column 'pp'.",
                "gold": lambda d: d.assign(pp=(d["rate_2024"] - d["rate_2023"]) * 100)[["team", "pp"]]})

    # 11. count includes zeros: per category count, categories with 0 must appear
    df11 = pd.DataFrame({"cat": pd.Categorical(["a", "a", "c"], categories=["a", "b", "c"]), "v": [1, 2, 3]})
    out.append({"name": "count_with_zero_cats", "df": df11,
                "req": "Number of rows per category INCLUDING categories with zero rows (category b should show 0).",
                "gold": lambda d: d.groupby("cat", observed=False).size().reset_index(name="n")})

    # 12. cumulative over global order, not reset per group
    df12 = pd.DataFrame({"day": [1, 2, 3, 4], "delta": [10, -5, 8, -3]})
    out.append({"name": "running_balance", "df": df12,
                "req": "Running balance: cumulative sum of delta ordered by day, column 'balance'.",
                "gold": lambda d: d.sort_values("day").assign(balance=lambda x: x["delta"].cumsum())[["day", "balance"]].reset_index(drop=True)})

    # 13. rate = sum/sum, NOT mean of per-row rates (Simpson-ish trap)
    df13 = pd.DataFrame({"region": ["N", "N", "S"], "clicks": [1, 99, 50], "imps": [10, 100, 100]})
    out.append({"name": "ctr_pooled", "df": df13,
                "req": "Click-through rate per region = total clicks / total impressions (pooled, not the average of per-row ratios). Column 'ctr'.",
                "gold": lambda d: (d.groupby("region").apply(lambda g: g["clicks"].sum() / g["imps"].sum(), include_groups=False)
                                   .reset_index(name="ctr"))})

    # 14. keep ties at the cutoff: all rows tied for rank<=2 by score
    df14 = pd.DataFrame({"name": list("abcd"), "score": [10, 9, 9, 7]})
    out.append({"name": "rank_keep_ties", "df": df14,
                "req": "Rows whose score rank is in the top 2 by VALUE, keeping ALL ties (so if two share 2nd place, keep both).",
                "gold": lambda d: d[d["score"].rank(method="min", ascending=False) <= 2].sort_values("score", ascending=False).reset_index(drop=True)})

    # 15. fill missing then sum (NaN should count as 0 in the total here)
    df15 = pd.DataFrame({"grp": ["x", "x", "y"], "v": [10.0, np.nan, 5.0]})
    out.append({"name": "sum_treat_nan_zero", "df": df15,
                "req": "Total v per group, treating missing values as 0 (so a group with one value 10 and one missing totals 10).",
                "gold": lambda d: d.assign(v=d["v"].fillna(0)).groupby("grp", as_index=False)["v"].sum()})

    # 16. proportion of rows meeting condition (mean of boolean), per group
    df16 = pd.DataFrame({"grp": ["x", "x", "x", "y", "y"], "passed": [True, False, True, False, False]})
    out.append({"name": "pass_rate_per_group", "df": df16,
                "req": "Pass rate per group = fraction of rows where passed is True. Column 'pass_rate'.",
                "gold": lambda d: d.groupby("grp", as_index=False)["passed"].mean().rename(columns={"passed": "pass_rate"})})

    return out


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Canonicalize for order-insensitive comparison: sort cols, sort rows, reset."""
    d = df.copy()
    d.columns = [str(c) for c in d.columns]
    d = d[sorted(d.columns)]
    # round floats to avoid fp noise
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].round(6)
    d = d.sort_values(list(d.columns)).reset_index(drop=True)
    return d


def _equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    try:
        na, nb = _normalize(a), _normalize(b)
        if na.shape != nb.shape or list(na.columns) != list(nb.columns):
            return False
        return na.equals(nb) or np.all([np.array_equal(na[c].to_numpy(), nb[c].to_numpy()) for c in na.columns])
    except Exception:
        return False


def _gold(case: Dict[str, Any]) -> pd.DataFrame:
    if "df2" in case:
        return case["gold"](case["df"], case["df2"])
    return case["gold"](case["df"])


def _llm_transform_code(case: Dict[str, Any], model: str) -> Optional[str]:
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    df_desc = f"`df` columns={list(case['df'].columns)}, {len(case['df'])} rows. Sample:\n{case['df'].head(4).to_string(index=False)}"
    extra = ""
    if "df2" in case:
        extra = f"\nA second dataframe `df2` columns={list(case['df2'].columns)}:\n{case['df2'].head(4).to_string(index=False)}"
    prompt = f"""You are given pandas dataframe(s). {df_desc}{extra}

Task: {case['req']}

Write pandas code that assigns the resulting dataframe to a variable named `result`.
Use the existing `df`{' and `df2`' if 'df2' in case else ''}. Return ONLY strict JSON:
{{"code": "<pandas code that defines result>"}}. No explanation."""
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.0, "response_format": {"type": "json_object"}, "max_tokens": 400},
                          timeout=(10, 45))
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        return json.loads(m.group(0) if m else content).get("code")
    except Exception:
        return None


def _run_case(case: Dict[str, Any], model: str) -> Dict[str, Any]:
    code = _llm_transform_code(case, model)
    if not code:
        return {"ok": False, "correct": False, "err": "no-code"}
    ns: Dict[str, Any] = {"df": case["df"].copy(), "pd": pd, "np": np}
    if "df2" in case:
        ns["df2"] = case["df2"].copy()
    try:
        exec(code, ns)  # noqa: S102 (controlled probe)
        result = ns.get("result")
        if not isinstance(result, pd.DataFrame):
            return {"ok": True, "correct": False, "err": "result-not-df", "code": code[:120]}
    except Exception as e:
        return {"ok": False, "correct": False, "err": f"exec:{repr(e)[:60]}", "code": code[:120]}
    correct = _equal(result, _gold(case))
    return {"ok": True, "correct": correct, "code": code[:120]}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="LLM data-transform error-rate go/no-go")
    ap.add_argument("--out", default="eval/results_transform")
    ap.add_argument("--reps", type=int, default=1, help="repeat each case N times (LLM is near-deterministic at temp 0)")
    args = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY.")
        return 1

    cases = _cases()
    rows: List[Dict[str, Any]] = []
    # three outcomes: correct / silent (exec ok but wrong result) / crash (exec fail or no code)
    stats = {m: {"correct": 0, "silent": 0, "crash": 0, "total": 0} for m in MODELS}
    for case in cases:
        rec = {"case": case["name"]}
        for m in MODELS:
            outcomes = []
            for _ in range(args.reps):
                r = _run_case(case, m)
                stats[m]["total"] += 1
                if r["correct"]:
                    stats[m]["correct"] += 1; outcomes.append("ok")
                elif r["ok"]:  # exec succeeded but result wrong = SILENT semantic error
                    stats[m]["silent"] += 1; outcomes.append("SILENT")
                else:
                    stats[m]["crash"] += 1; outcomes.append("crash")
            rec[m] = {"outcomes": outcomes, "last_err": r.get("err", "")}
            print(f"[{case['name']:22}] {m:18} {outcomes} {r.get('err','')}", flush=True)
        rows.append(rec)

    def pct(m, key):
        t = stats[m]["total"]
        return f"{100*stats[m][key]/t:.0f}%" if t else "n/a"

    lines = ["# LLM Data-Transform Errors: Silent vs Crash (go/no-go)\n",
             "Trap/ambiguous transforms. Each cell = per-rep outcomes (ok / SILENT / crash).",
             "**SILENT = code ran fine, result looks plausible, but is semantically WRONG** —",
             "the failure mode that a verifier must catch (crashes are already visible).\n",
             "| Case | " + " | ".join(MODELS) + " |", "|" + "---|" * (len(MODELS) + 1)]
    for r in rows:
        lines.append(f"| {r['case']} | " + " | ".join("/".join(r[m]["outcomes"]) for m in MODELS) + " |")
    lines.append("| **correct** | " + " | ".join(pct(m, "correct") for m in MODELS) + " |")
    lines.append("| **SILENT semantic-error** | " + " | ".join(pct(m, "silent") for m in MODELS) + " |")
    lines.append("| **crash/no-code** | " + " | ".join(pct(m, "crash") for m in MODELS) + " |")
    lines.append("\n## Go/no-go reading")
    lines.append("- The KEY number is the SILENT semantic-error rate: code runs, output looks fine, but it's wrong.")
    lines.append("- High SILENT rate => execution-traced verification of transform SEMANTICS is the real-value")
    lines.append("  direction (these errors are invisible to exec-pass checks and to the eye).")
    lines.append("- Crashes don't count for the thesis (they're already caught by running the code).")
    report = "\n".join(lines)

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "transform_report.md").write_text(report, encoding="utf-8")
    (out_dir / "transform_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
