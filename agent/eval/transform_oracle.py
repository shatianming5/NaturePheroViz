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


# registry: operator-semantic-type -> contract fn
CONTRACTS: Dict[str, Callable] = {
    "weighted_mean": c_weighted_mean,
    "within_group_share": c_within_group_share,
    "pct_point": c_pct_point,
    "dedup_then_agg": c_dedup_then_agg,
    "left_join_keep_all": c_left_join_keep_all,
    "pooled_rate": c_pooled_rate,
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

    if fails:
        print("ORACLE SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("ORACLE SELFTEST PASSED: 6 contracts each FIRE on the silent slip and PASS on the correct result (goldless).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
