"""
transform_oracle.py — P0-1: invariants-first semantic oracle (no gold, no tests, no voting).

The GPT-5.4 review killed multi-implementation consistency (common-mode error:
both LLMs made the SAME silent mistake). The surviving Oral-bet mechanism is:
derive CHECKABLE SEMANTIC INVARIANTS from the natural-language intent + the
operator type, and verify them over the EXECUTION-TRACED result. No gold output,
no pre-written tests, and crucially no second LLM that shares the blind spot.

Each operator-semantic contract is a deterministic predicate on (input df(s),
intent params, produced result). A contract FIRES (flags silent error) when the
result violates an invariant that the correct transform must satisfy.

Example contracts:
- weighted_mean : result must equal sum(v*w)/sum(w); and when weights are
  non-uniform it must DIFFER from the arithmetic mean (the classic silent slip).
- within_group_share : per-group shares sum to 1 (NOT global sum=1).
- pct_point : value == (a-b)*100, magnitude is "points" not ratio.
- dedup_then_agg : total after dedup <= total without dedup (key duplicated).
- left_join_keep_all : output rows == left rows (no rows dropped).
- pooled_rate : equals sum/sum, generally != mean of per-row ratios.

This file provides the contract library + a checker. It deliberately does NOT
look at any gold DataFrame — that is the whole point (goldless verification).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class ContractResult:
    contract: str
    fired: bool          # True => invariant violated => silent error flagged
    detail: str


# ---- helpers ----------------------------------------------------------------


def _num(series) -> np.ndarray:
    return pd.to_numeric(pd.Series(series), errors="coerce").to_numpy(dtype=float)


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    if a is None or b is None or (isinstance(a, float) and np.isnan(a)):
        return False
    return abs(float(a) - float(b)) <= max(abs(float(b)) * tol, tol)


def _single_value(result: pd.DataFrame, prefer_cols: Tuple[str, ...] = ()) -> Optional[float]:
    """Extract the single scalar a result is supposed to carry (e.g. a weighted mean)."""
    if result is None or not isinstance(result, pd.DataFrame) or result.empty:
        return None
    for c in prefer_cols:
        if c in result.columns:
            v = _num(result[c])
            if len(v) == 1:
                return float(v[0])
    # else: the only numeric cell
    num_cols = [c for c in result.columns if pd.api.types.is_numeric_dtype(result[c]) or pd.to_numeric(result[c], errors="coerce").notna().any()]
    if len(result) == 1 and len(num_cols) == 1:
        return float(_num(result[num_cols[0]])[0])
    return None


# ---- contracts: each takes (inp: dict of input dfs, params, result) ----------
# Return ContractResult(fired=True) if a silent-error invariant is VIOLATED.


def c_weighted_mean(inp, params, result) -> ContractResult:
    df = inp["df"]; vcol, wcol = params["value"], params["weight"]
    v, w = _num(df[vcol]), _num(df[wcol])
    correct = float((v * w).sum() / w.sum())
    arith = float(np.nanmean(v))
    got = _single_value(result)
    if got is None:
        return ContractResult("weighted_mean", True, "no single scalar result")
    if _close(got, correct):
        return ContractResult("weighted_mean", False, f"matches weighted mean {correct:.4f}")
    # the classic silent slip: returned the arithmetic mean instead
    if _close(got, arith):
        return ContractResult("weighted_mean", True, f"got arithmetic mean {arith:.4f}, should be weighted {correct:.4f}")
    return ContractResult("weighted_mean", True, f"got {got:.4f}, expected weighted {correct:.4f}")


def c_within_group_share(inp, params, result) -> ContractResult:
    grp, share = params["group"], params.get("share_col", "share")
    if result is None or share not in result.columns or grp not in result.columns:
        return ContractResult("within_group_share", True, f"missing {share}/{grp} column")
    # invariant: shares within each group sum to 1 (NOT globally)
    sums = result.groupby(grp)[share].sum()
    if all(_close(s, 1.0, tol=1e-4) for s in sums):
        return ContractResult("within_group_share", False, "per-group shares sum to 1")
    # common silent slip: shares are of GLOBAL total -> global sum is 1, per-group <1
    gsum = float(_num(result[share]).sum())
    if _close(gsum, 1.0, tol=1e-4):
        return ContractResult("within_group_share", True, "shares sum to 1 GLOBALLY (should be per-group)")
    return ContractResult("within_group_share", True, f"per-group share sums={dict(sums.round(3))}")


def c_pct_point(inp, params, result) -> ContractResult:
    df = inp["df"]; a, b = params["new"], params["old"]; out = params.get("out", "pp")
    if result is None or out not in result.columns:
        return ContractResult("pct_point", True, f"missing {out} column")
    expected = (_num(df[a]) - _num(df[b])) * 100.0
    got = _num(result[out])
    if len(got) == len(expected) and np.allclose(np.sort(got), np.sort(expected), atol=1e-4, equal_nan=True):
        return ContractResult("pct_point", False, "matches percentage-point delta")
    # silent slip: ratio change (a-b)/b instead of (a-b)*100
    ratio = (_num(df[a]) - _num(df[b])) / _num(df[b])
    if len(got) == len(ratio) and np.allclose(np.sort(got), np.sort(ratio), atol=1e-4):
        return ContractResult("pct_point", True, "got fractional ratio change, should be percentage POINTS")
    return ContractResult("pct_point", True, f"got {got[:3]}, expected {expected[:3]}")


def c_dedup_then_agg(inp, params, result) -> ContractResult:
    df = inp["df"]; key, val, grp = params["key"], params["value"], params["group"]
    if result is None or val not in result.columns:
        return ContractResult("dedup_then_agg", True, f"missing {val} column")
    correct = df.drop_duplicates(key).groupby(grp)[val].sum()
    naive = df.groupby(grp)[val].sum()  # the silent-wrong version (counts dup line-items)
    got_total = float(_num(result[val]).sum())
    if _close(got_total, float(correct.sum())):
        return ContractResult("dedup_then_agg", False, f"total {got_total} matches deduped {correct.sum()}")
    if _close(got_total, float(naive.sum())):
        return ContractResult("dedup_then_agg", True, f"total {got_total} == NAIVE (counts duplicate line-items); deduped should be {correct.sum()}")
    return ContractResult("dedup_then_agg", True, f"total {got_total}, deduped should be {correct.sum()}")


def c_left_join_keep_all(inp, params, result) -> ContractResult:
    left = inp["df"]
    if result is None:
        return ContractResult("left_join_keep_all", True, "no result")
    # invariant: a left join keeps every left row
    if len(result) == len(left):
        return ContractResult("left_join_keep_all", False, f"kept all {len(left)} left rows")
    return ContractResult("left_join_keep_all", True, f"output {len(result)} rows != {len(left)} left rows (rows dropped — likely inner join)")


def c_pooled_rate(inp, params, result) -> ContractResult:
    df = inp["df"]; grp, num, den, out = params["group"], params["num"], params["den"], params.get("out", "ctr")
    if result is None or out not in result.columns or grp not in result.columns:
        return ContractResult("pooled_rate", True, f"missing {out}/{grp}")
    pooled = df.groupby(grp).apply(lambda g: g[num].sum() / g[den].sum(), include_groups=False)
    mean_of_ratios = df.assign(_r=df[num] / df[den]).groupby(grp)["_r"].mean()
    rmap = dict(zip(result[grp].astype(str), _num(result[out])))
    ok = all(_close(rmap.get(str(g), None), pooled[g]) for g in pooled.index)
    if ok:
        return ContractResult("pooled_rate", False, "matches pooled sum/sum rate")
    if all(_close(rmap.get(str(g), None), mean_of_ratios[g]) for g in mean_of_ratios.index):
        return ContractResult("pooled_rate", True, "got MEAN OF PER-ROW RATIOS; should be pooled sum/sum")
    return ContractResult("pooled_rate", True, "rate does not match pooled sum/sum")


def c_median_not_mean(inp, params, result) -> ContractResult:
    df = inp["df"]; grp, val = params["group"], params["value"]; out = params.get("out", val)
    if result is None or grp not in result.columns:
        return ContractResult("median_not_mean", True, "missing group column")
    med = df.groupby(grp)[val].median(); mean = df.groupby(grp)[val].mean()
    vcol = out if out in result.columns else next((c for c in result.columns if c != grp), None)
    if vcol is None:
        return ContractResult("median_not_mean", True, "no value column")
    rmap = dict(zip(result[grp].astype(str), _num(result[vcol])))
    if all(_close(rmap.get(str(g), None), med[g]) for g in med.index):
        return ContractResult("median_not_mean", False, "matches per-group median")
    if all(_close(rmap.get(str(g), None), mean[g]) for g in mean.index):
        return ContractResult("median_not_mean", True, "got MEAN; should be MEDIAN")
    return ContractResult("median_not_mean", True, "does not match median")


def c_cumulative_running(inp, params, result) -> ContractResult:
    # invariant: a running/cumulative series is monotonic in count and its LAST
    # value equals the total sum of the delta column (cumulative, not per-row).
    df = inp["df"]; val = params["value"]; out = params.get("out", "balance")
    if result is None or out not in result.columns:
        return ContractResult("cumulative_running", True, f"missing {out}")
    got = _num(result[out]); total = float(_num(df[val]).sum())
    if len(got) == len(df) and _close(got[-1], total):
        return ContractResult("cumulative_running", False, f"last cum == total {total}")
    # silent slip: returned the raw per-row values (no cumulation) -> last != total
    if len(got) == len(df) and np.allclose(np.sort(got), np.sort(_num(df[val])), atol=1e-6):
        return ContractResult("cumulative_running", True, "returned raw per-row values, not cumulative")
    return ContractResult("cumulative_running", True, f"last value {got[-1] if len(got) else None} != total {total}")


def c_topn_with_ties(inp, params, result) -> ContractResult:
    # invariant: keeping top-n by VALUE with ties = all rows whose value-rank
    # (min method, descending) is <= n. So if rows tie for rank 1, they all count
    # toward the n slots. Expected count = #rows with rank <= n.
    df = inp["df"]; col, n = params["value"], params["n"]
    if result is None or col not in result.columns:
        return ContractResult("topn_with_ties", True, f"missing {col}")
    ranks = pd.Series(_num(df[col])).rank(method="min", ascending=False)
    expected = int((ranks <= n).sum())
    if len(result) == expected:
        return ContractResult("topn_with_ties", False, f"kept all {expected} rows with rank<= {n}")
    if len(result) == n and expected > n:
        return ContractResult("topn_with_ties", True, f"kept exactly {n}, dropped ties (should keep {expected})")
    return ContractResult("topn_with_ties", True, f"kept {len(result)}, expected {expected}")


def c_nan_as_zero_sum(inp, params, result) -> ContractResult:
    # invariant: summing with NaN treated as 0 => per-group total equals sum of
    # non-missing (pandas sum already skips NaN, so a group with [10, NaN] => 10).
    df = inp["df"]; grp, val = params["group"], params["value"]
    if result is None or grp not in result.columns or val not in result.columns:
        return ContractResult("nan_as_zero_sum", True, "missing columns")
    correct = df.assign(**{val: df[val].fillna(0)}).groupby(grp)[val].sum()
    rmap = dict(zip(result[grp].astype(str), _num(result[val])))
    if all(_close(rmap.get(str(g), None), correct[g]) for g in correct.index):
        return ContractResult("nan_as_zero_sum", False, "NaN treated as 0 in sums")
    # silent slip: produced NaN totals (didn't fill) -> a group total is NaN
    if any(np.isnan(v) for v in rmap.values()):
        return ContractResult("nan_as_zero_sum", True, "a group total is NaN (NaN not treated as 0)")
    return ContractResult("nan_as_zero_sum", True, "group totals don't match NaN-as-0 sums")


def c_count_includes_empty(inp, params, result) -> ContractResult:
    # invariant: counting per category must include categories with 0 rows.
    df = inp["df"]; cat = params["category"]
    n_categories = len(df[cat].cat.categories) if isinstance(df[cat].dtype, pd.CategoricalDtype) else df[cat].nunique()
    if result is None:
        return ContractResult("count_includes_empty", True, "no result")
    if len(result) >= n_categories:
        return ContractResult("count_includes_empty", False, f"all {n_categories} categories present")
    return ContractResult("count_includes_empty", True, f"only {len(result)} categories, should include all {n_categories} (zero-count ones dropped)")


def c_proportion_true(inp, params, result) -> ContractResult:
    # invariant: proportion (mean of boolean) per group is in [0,1] and equals
    # (#True)/(#rows), NOT the count of True.
    df = inp["df"]; grp, flag, out = params["group"], params["flag"], params.get("out", "pass_rate")
    if result is None or out not in result.columns or grp not in result.columns:
        return ContractResult("proportion_true", True, f"missing {out}/{grp}")
    correct = df.groupby(grp)[flag].mean()
    countT = df.groupby(grp)[flag].sum()
    rmap = dict(zip(result[grp].astype(str), _num(result[out])))
    if all(_close(rmap.get(str(g), None), correct[g]) for g in correct.index):
        return ContractResult("proportion_true", False, "matches proportion in [0,1]")
    if any((v is not None and not np.isnan(v) and v > 1.0) for v in rmap.values()):
        return ContractResult("proportion_true", True, "value > 1 — looks like COUNT of True, not proportion")
    if all(_close(rmap.get(str(g), None), float(countT[g])) for g in countT.index):
        return ContractResult("proportion_true", True, "got COUNT of True; should be proportion")
    return ContractResult("proportion_true", True, "does not match proportion")


# ============================================================================
# SCALABILITY DEMO (round-3): three PREVIOUSLY-UNSEEN operator families, each
# added as ONE contract, to show "a new operator = one invariant" rather than a
# redesign. Authoring effort per contract ~ the functions below (≈10 lines each).
# ============================================================================

def c_zscore_within_group(inp, params, result) -> ContractResult:
    # invariant: a within-group z-score standardizes EACH group to mean~0 / std~1,
    # so per-group mean of the output ~ 0. The silent slip uses the GLOBAL mean/std,
    # leaving per-group means != 0 (groups keep their original offset).
    df = inp["df"]; grp, val = params["group"], params["value"]; out = params.get("out", "z")
    if result is None or out not in result.columns or grp not in result.columns:
        return ContractResult("zscore_within_group", True, f"missing {out}/{grp}")
    g = result.groupby(grp)[out].mean()
    if all(abs(float(m)) <= 1e-3 for m in g):
        return ContractResult("zscore_within_group", False, "per-group mean ~ 0 (standardized within group)")
    # global z-score: overall mean ~ 0 but per-group means are not
    if abs(float(_num(result[out]).mean())) <= 1e-3:
        return ContractResult("zscore_within_group", True, "standardized GLOBALLY (per-group means != 0); should be within-group")
    return ContractResult("zscore_within_group", True, f"per-group means {dict(g.round(3))} != 0")


def c_dense_rank(inp, params, result) -> ContractResult:
    # invariant: dense rank gives consecutive ranks with NO gaps after ties
    # (1,2,2,3). The silent slip uses 'min' rank, which leaves gaps (1,2,2,4).
    df = inp["df"]; val = params["value"]; out = params.get("out", "rank")
    if result is None or out not in result.columns:
        return ContractResult("dense_rank", True, f"missing {out}")
    ranks = sorted(set(int(x) for x in _num(result[out]) if not np.isnan(x)))
    if not ranks:
        return ContractResult("dense_rank", True, "no ranks")
    consecutive = ranks == list(range(ranks[0], ranks[0] + len(ranks)))
    if consecutive and ranks[0] == 1:
        return ContractResult("dense_rank", False, "dense ranks consecutive from 1, no gaps")
    # min-rank slip: gaps appear (max rank > #distinct ranks)
    if max(ranks) > len(ranks):
        return ContractResult("dense_rank", True, f"rank gaps present (max {max(ranks)} > {len(ranks)} distinct) — looks like MIN rank, should be DENSE")
    return ContractResult("dense_rank", True, f"ranks {ranks} not dense from 1")


def c_cumcount_per_group(inp, params, result) -> ContractResult:
    # invariant: a per-group running count RESETS each group AND increases by 1
    # within the group (0,1,2 or 1,2,3). Two silent slips: (a) a global cumulative
    # count that never resets (later groups start above the first), or (b) a constant
    # (e.g. all 1s / a group size) that resets but does not increase.
    df = inp["df"]; grp = params["group"]; out = params.get("out", "occurrence")
    if result is None or out not in result.columns or grp not in result.columns:
        return ContractResult("cumcount_per_group", True, f"missing {out}/{grp}")
    starts = result.groupby(grp)[out].min()
    base = float(starts.min())
    reset = all(_close(float(s), base) for s in starts) and base in (0.0, 1.0)
    # within-group monotonic increase by 1 (allow 0- or 1-based)
    def _incr(s):
        v = _num(s.to_numpy())
        return len(v) <= 1 or np.allclose(np.diff(v), 1.0)
    increasing = all(_incr(g[out]) for _, g in result.groupby(grp))
    if reset and increasing:
        return ContractResult("cumcount_per_group", False, f"per-group counter resets at {base:.0f} and increments by 1")
    if reset and not increasing:
        return ContractResult("cumcount_per_group", True, "resets per group but does NOT increment by 1 (constant/size, not a running count)")
    return ContractResult("cumcount_per_group", True, f"group start values {dict(starts.astype(int))} differ — global count, not reset per group")


# registry: operator-semantic-type -> contract fn
CONTRACTS: Dict[str, Callable] = {
    "weighted_mean": c_weighted_mean,
    "within_group_share": c_within_group_share,
    "pct_point": c_pct_point,
    "dedup_then_agg": c_dedup_then_agg,
    "left_join_keep_all": c_left_join_keep_all,
    "pooled_rate": c_pooled_rate,
    "median_not_mean": c_median_not_mean,
    "cumulative_running": c_cumulative_running,
    "topn_with_ties": c_topn_with_ties,
    "nan_as_zero_sum": c_nan_as_zero_sum,
    "count_includes_empty": c_count_includes_empty,
    "proportion_true": c_proportion_true,
    # scalability-demo families (round-3): each is one added contract.
    "zscore_within_group": c_zscore_within_group,
    "dense_rank": c_dense_rank,
    "cumcount_per_group": c_cumcount_per_group,
}


def check(op_type: str, inp: Dict[str, pd.DataFrame], params: Dict[str, Any], result: Optional[pd.DataFrame]) -> Optional[ContractResult]:
    """Run the invariant contract for op_type over a produced result (goldless)."""
    fn = CONTRACTS.get(op_type)
    if fn is None:
        return None
    try:
        return fn(inp, params, result)
    except Exception as e:
        return ContractResult(op_type, True, f"contract error (likely malformed result): {repr(e)[:60]}")


# ---- self-test: contracts must FIRE on the known silent error, PASS on correct ----


def _selftest() -> int:
    fails = []

    # weighted_mean: weights 100/10/1, prices 10/20/30 -> weighted 11.08, arith 20
    df = pd.DataFrame({"price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})
    p = {"value": "price", "weight": "qty"}
    correct = pd.DataFrame({"wavg": [(df["price"] * df["qty"]).sum() / df["qty"].sum()]})
    wrong = pd.DataFrame({"wavg": [df["price"].mean()]})  # arithmetic mean = silent slip
    r1 = check("weighted_mean", {"df": df}, p, correct)
    r2 = check("weighted_mean", {"df": df}, p, wrong)
    if r1.fired: fails.append(f"weighted_mean fired on CORRECT: {r1.detail}")
    if not r2.fired: fails.append("weighted_mean did NOT fire on arithmetic-mean slip")

    # within_group_share
    df2 = pd.DataFrame({"region": ["N", "N", "S", "S"], "sales": [30, 10, 20, 20]})
    correct2 = df2.assign(share=df2["sales"] / df2.groupby("region")["sales"].transform("sum"))
    wrong2 = df2.assign(share=df2["sales"] / df2["sales"].sum())  # global share = slip
    if check("within_group_share", {"df": df2}, {"group": "region"}, correct2).fired:
        fails.append("within_group_share fired on CORRECT")
    if not check("within_group_share", {"df": df2}, {"group": "region"}, wrong2).fired:
        fails.append("within_group_share did NOT fire on global-share slip")

    # pct_point
    df3 = pd.DataFrame({"team": ["A", "B"], "r0": [0.20, 0.50], "r1": [0.30, 0.55]})
    correct3 = df3.assign(pp=(df3["r1"] - df3["r0"]) * 100)[["team", "pp"]]
    wrong3 = df3.assign(pp=(df3["r1"] - df3["r0"]) / df3["r0"])[["team", "pp"]]  # ratio slip
    if check("pct_point", {"df": df3}, {"new": "r1", "old": "r0"}, correct3).fired:
        fails.append("pct_point fired on CORRECT")
    if not check("pct_point", {"df": df3}, {"new": "r1", "old": "r0"}, wrong3).fired:
        fails.append("pct_point did NOT fire on ratio slip")

    # dedup_then_agg
    df4 = pd.DataFrame({"region": ["N", "N", "N", "S"], "order_id": [1, 1, 2, 3], "rev": [50, 50, 30, 40]})
    correct4 = df4.drop_duplicates("order_id").groupby("region", as_index=False)["rev"].sum()
    wrong4 = df4.groupby("region", as_index=False)["rev"].sum()  # counts dup line-items
    pp4 = {"key": "order_id", "value": "rev", "group": "region"}
    if check("dedup_then_agg", {"df": df4}, pp4, correct4).fired:
        fails.append("dedup_then_agg fired on CORRECT")
    if not check("dedup_then_agg", {"df": df4}, pp4, wrong4).fired:
        fails.append("dedup_then_agg did NOT fire on naive-sum slip")

    # left_join_keep_all
    L = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    R = pd.DataFrame({"id": [1, 3], "score": [88, 99]})
    correct5 = L.merge(R, on="id", how="left")
    wrong5 = L.merge(R, on="id", how="inner")  # drops id=2
    if check("left_join_keep_all", {"df": L}, {}, correct5).fired:
        fails.append("left_join fired on CORRECT")
    if not check("left_join_keep_all", {"df": L}, {}, wrong5).fired:
        fails.append("left_join did NOT fire on inner-join slip")

    # pooled_rate
    df6 = pd.DataFrame({"region": ["N", "N", "S"], "clicks": [1, 99, 50], "imps": [10, 100, 100]})
    correct6 = df6.groupby("region").apply(lambda g: g["clicks"].sum() / g["imps"].sum(), include_groups=False).reset_index(name="ctr")
    wrong6 = df6.assign(_r=df6["clicks"] / df6["imps"]).groupby("region")["_r"].mean().reset_index(name="ctr")
    pp6 = {"group": "region", "num": "clicks", "den": "imps"}
    if check("pooled_rate", {"df": df6}, pp6, correct6).fired:
        fails.append("pooled_rate fired on CORRECT")
    if not check("pooled_rate", {"df": df6}, pp6, wrong6).fired:
        fails.append("pooled_rate did NOT fire on mean-of-ratios slip")

    # median_not_mean
    d = pd.DataFrame({"grp": ["x", "x", "x", "y", "y", "y"], "v": [1.0, 2.0, 9.0, 4.0, 5.0, 60.0]})
    pp = {"group": "grp", "value": "v"}
    cok = d.groupby("grp", as_index=False)["v"].median()
    cw = d.groupby("grp", as_index=False)["v"].mean()
    if check("median_not_mean", {"df": d}, pp, cok).fired: fails.append("median fired on CORRECT")
    if not check("median_not_mean", {"df": d}, pp, cw).fired: fails.append("median did NOT fire on mean slip")

    # cumulative_running
    d = pd.DataFrame({"day": [1, 2, 3, 4], "delta": [10, -5, 8, -3]})
    pp = {"value": "delta", "out": "balance"}
    cok = d.sort_values("day").assign(balance=lambda x: x["delta"].cumsum())[["day", "balance"]]
    cw = d.assign(balance=d["delta"])[["day", "balance"]]  # raw, not cumulative
    if check("cumulative_running", {"df": d}, pp, cok).fired: fails.append("cumulative fired on CORRECT")
    if not check("cumulative_running", {"df": d}, pp, cw).fired: fails.append("cumulative did NOT fire on raw-values slip")

    # topn_with_ties
    d = pd.DataFrame({"name": list("abcd"), "score": [10, 9, 9, 7]})
    pp = {"value": "score", "n": 2}
    cok = d[d["score"] >= 9].reset_index(drop=True)        # keeps a,b,c (ties at 9)
    cw = d.sort_values("score", ascending=False).head(2).reset_index(drop=True)  # drops a tie
    if check("topn_with_ties", {"df": d}, pp, cok).fired: fails.append("topn fired on CORRECT")
    if not check("topn_with_ties", {"df": d}, pp, cw).fired: fails.append("topn did NOT fire on dropped-tie slip")

    # nan_as_zero_sum
    d = pd.DataFrame({"grp": ["x", "x", "y"], "v": [10.0, np.nan, 5.0]})
    pp = {"group": "grp", "value": "v"}
    cok = d.assign(v=d["v"].fillna(0)).groupby("grp", as_index=False)["v"].sum()
    cw = pd.DataFrame({"grp": ["x", "y"], "v": [np.nan, 5.0]})  # x total NaN (didn't fill)
    if check("nan_as_zero_sum", {"df": d}, pp, cok).fired: fails.append("nan_sum fired on CORRECT")
    if not check("nan_as_zero_sum", {"df": d}, pp, cw).fired: fails.append("nan_sum did NOT fire on NaN-total slip")

    # count_includes_empty
    d = pd.DataFrame({"cat": pd.Categorical(["a", "a", "c"], categories=["a", "b", "c"]), "v": [1, 2, 3]})
    pp = {"category": "cat"}
    cok = d.groupby("cat", observed=False).size().reset_index(name="n")     # 3 rows incl b=0
    cw = d.groupby("cat", observed=True).size().reset_index(name="n")        # 2 rows, drops b
    if check("count_includes_empty", {"df": d}, pp, cok).fired: fails.append("count_empty fired on CORRECT")
    if not check("count_includes_empty", {"df": d}, pp, cw).fired: fails.append("count_empty did NOT fire on dropped-zero slip")

    # proportion_true
    d = pd.DataFrame({"grp": ["x", "x", "x", "y", "y"], "passed": [True, False, True, False, False]})
    pp = {"group": "grp", "flag": "passed", "out": "pass_rate"}
    cok = d.groupby("grp", as_index=False)["passed"].mean().rename(columns={"passed": "pass_rate"})
    cw = d.groupby("grp", as_index=False)["passed"].sum().rename(columns={"passed": "pass_rate"})  # count not proportion
    if check("proportion_true", {"df": d}, pp, cok).fired: fails.append("proportion fired on CORRECT")
    if not check("proportion_true", {"df": d}, pp, cw).fired: fails.append("proportion did NOT fire on count slip")

    if fails:
        print("ORACLE SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("ORACLE SELFTEST PASSED: 12 contracts each FIRE on the silent slip and PASS on the correct result (goldless).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
