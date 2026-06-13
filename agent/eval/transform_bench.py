"""
transform_bench.py — P0-3: structured benchmark, 12 operator-semantic classes x multiple instances.

Answers the reviewer's "cherry-picked traps (n=16)" objection by making the
benchmark SYSTEMATIC: a fixed taxonomy of operator-semantic ambiguity classes,
each instantiated multiple times with different data (column names, sizes,
values), every case carrying its oracle contract + an (ambiguous, clarified)
prompt pair. This is not a hand-picked trap list; it's a grid over a declared
taxonomy — which is the defensible form for a measurement claim.

Each case: {op, df[, df2], params, gold, ambiguous, clarified, result_kind}.
- op           : operator-semantic class (-> transform_oracle contract)
- gold         : ground-truth (for LABELING correct/wrong only; oracle never sees it)
- ambiguous    : natural underspecified prompt (where LLMs slip)
- clarified    : same task, intent spelled out (calibration control)

Used by run_bench() below and importable by ambiguity_calibration / detection
experiments. Run `python eval/transform_bench.py` to validate all golds+oracle
contracts offline (no LLM), then the LLM experiments consume _cases().
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402


def _C(op, df, params, gold, amb, clar, kind="frame", df2=None):
    c = {"op": op, "df": df, "params": params, "gold": gold,
         "ambiguous": amb, "clarified": clar, "result_kind": kind}
    if df2 is not None:
        c["df2"] = df2
    return c


def _cases() -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    rng_sets = [  # different data instances reused across classes
        (["a", "b", "c"], [10.0, 20.0, 30.0], [100, 10, 1]),
        (["p", "q", "r", "s"], [5.0, 15.0, 25.0, 35.0], [1, 1, 50, 2]),
        (["u", "v"], [8.0, 40.0], [9, 1]),
        (["m", "n", "o", "x", "y"], [2.0, 4.0, 6.0, 8.0, 100.0], [50, 50, 50, 50, 1]),
    ]

    # --- class 1: weighted_mean (4 instances) ---
    for i, (names, price, qty) in enumerate(rng_sets):
        df = pd.DataFrame({"item": names, "price": price, "qty": qty})
        cases.append(_C("weighted_mean", df, {"value": "price", "weight": "qty"},
                        lambda d: (d["price"] * d["qty"]).sum() / d["qty"].sum(),
                        "Give the average price (one number, column 'wavg').",
                        "Give the QUANTITY-WEIGHTED average price (weight each price by qty; column 'wavg').",
                        kind="scalar"))

    # --- class 2: within_group_share (4) ---
    grp_sets = [
        (["N", "N", "S", "S"], ["a", "b", "c", "d"], [30, 10, 20, 20]),
        (["E", "E", "E", "W"], ["a", "b", "c", "d"], [1, 2, 3, 4]),
        (["g1", "g1", "g2", "g2", "g2"], list("abcde"), [5, 5, 10, 10, 10]),
        (["x", "y", "y"], ["a", "b", "c"], [50, 25, 25]),
    ]
    for region, city, sales in grp_sets:
        df = pd.DataFrame({"region": region, "city": city, "sales": sales})
        cases.append(_C("within_group_share", df, {"group": "region", "share_col": "share"},
                        lambda d: d.assign(share=d["sales"] / d.groupby("region")["sales"].transform("sum")),
                        "Add 'share' = each city's share of sales. Keep region, city, sales, share.",
                        "Add 'share' = each city's sales / ITS OWN REGION's total (within-region share, NOT grand total). Keep region, city, sales, share."))

    # --- class 3: pct_point (4) ---
    pp_sets = [([0.20, 0.50], [0.30, 0.55]), ([0.1, 0.9], [0.2, 0.8]),
               ([0.05, 0.45, 0.7], [0.15, 0.40, 0.9]), ([0.33], [0.66])]
    for r0, r1 in pp_sets:
        df = pd.DataFrame({"team": [f"T{i}" for i in range(len(r0))], "r0": r0, "r1": r1})
        cases.append(_C("pct_point", df, {"new": "r1", "old": "r0", "out": "pp"},
                        lambda d: d.assign(pp=(d["r1"] - d["r0"]) * 100)[["team", "pp"]],
                        "Add 'pp' = the change in rate from r0 to r1. Keep team, pp.",
                        "Add 'pp' = change from r0 to r1 in PERCENTAGE POINTS, i.e. (r1-r0)*100. Keep team, pp."))

    # --- class 4: dedup_then_agg (4) ---
    dd_sets = [
        (["N", "N", "N", "S"], [1, 1, 2, 3], [50, 50, 30, 40]),
        (["A", "A", "B", "B", "B"], [1, 2, 2, 2, 3], [10, 20, 5, 5, 5]),
        (["x", "x"], [7, 7], [99, 99]),
        (["g", "g", "h", "h"], [1, 1, 2, 2], [3, 3, 4, 4]),
    ]
    for region, oid, rev in dd_sets:
        df = pd.DataFrame({"region": region, "order_id": oid, "rev": rev})
        cases.append(_C("dedup_then_agg", df, {"key": "order_id", "value": "rev", "group": "region"},
                        lambda d: d.drop_duplicates("order_id").groupby("region", as_index=False)["rev"].sum(),
                        "Total revenue per region. Columns region, rev.",
                        "Total revenue per region, counting each order_id only ONCE (rows are duplicated line-items; dedup by order_id first). Columns region, rev."))

    # --- class 5: left_join_keep_all (4) ---
    lj_sets = [([1, 2, 3], [1, 3]), ([1, 2, 3, 4], [2]),
               ([10, 20], [10, 20]), ([1, 2, 3, 4, 5], [1, 5])]
    for lids, rids in lj_sets:
        L = pd.DataFrame({"id": lids, "name": [f"n{i}" for i in lids]})
        R = pd.DataFrame({"id": rids, "score": [i * 11 for i in rids]})
        cases.append(_C("left_join_keep_all", L, {},
                        lambda d, d2: d.merge(d2, on="id", how="left"),
                        "Attach score from df2 to df on id.",
                        "Attach score from df2 on id, KEEPING ALL rows of df even with no match (missing score = NaN). Left join.",
                        df2=R))

    # --- class 6: pooled_rate (4) ---
    pr_sets = [
        (["N", "N", "S"], [1, 99, 50], [10, 100, 100]),
        (["A", "B", "B"], [5, 1, 9], [50, 10, 90]),
        (["x", "x", "x"], [1, 1, 1], [2, 4, 6]),
        (["g", "h"], [3, 7], [30, 14]),
    ]
    for region, clk, imp in pr_sets:
        df = pd.DataFrame({"region": region, "clicks": clk, "imps": imp})
        cases.append(_C("pooled_rate", df, {"group": "region", "num": "clicks", "den": "imps", "out": "ctr"},
                        lambda d: d.groupby("region").apply(lambda g: g["clicks"].sum() / g["imps"].sum(), include_groups=False).reset_index(name="ctr"),
                        "Click-through rate (ctr) per region. Columns region, ctr.",
                        "CTR per region = TOTAL clicks / TOTAL impressions (pooled sum/sum, NOT average of per-row ratios). Columns region, ctr."))

    # --- class 7: median_not_mean (4) ---
    md_sets = [
        (["x", "x", "x", "y", "y", "y"], [1.0, 2.0, 9.0, 4.0, 5.0, 60.0]),
        (["a", "a", "b", "b"], [10.0, 90.0, 1.0, 2.0]),
        (["g", "g", "g"], [5.0, 5.0, 500.0]),
        (["p", "q", "q", "q", "q"], [3.0, 1.0, 2.0, 3.0, 100.0]),
    ]
    for grp, v in md_sets:
        df = pd.DataFrame({"grp": grp, "v": v})
        cases.append(_C("median_not_mean", df, {"group": "grp", "value": "v"},
                        lambda d: d.groupby("grp", as_index=False)["v"].median(),
                        "A typical value of v per group. Columns grp, v.",
                        "The MEDIAN of v per group (not the mean — data is skewed). Columns grp, v."))

    # --- class 8: cumulative_running (4) ---
    cu_sets = [[10, -5, 8, -3], [1, 2, 3, 4], [-1, -1, 5], [100, -50, -50, 10]]
    for j, delta in enumerate(cu_sets):
        df = pd.DataFrame({"day": list(range(1, len(delta) + 1)), "delta": delta})
        cases.append(_C("cumulative_running", df, {"value": "delta", "out": "balance"},
                        lambda d: d.sort_values("day").assign(balance=lambda x: x["delta"].cumsum())[["day", "balance"]].reset_index(drop=True),
                        "Add 'balance' from delta over days. Columns day, balance.",
                        "Add 'balance' = RUNNING (cumulative) sum of delta ordered by day. Columns day, balance."))

    # --- class 9: topn_with_ties (4) ---
    tn_sets = [([10, 9, 9, 7], 2), ([5, 5, 5, 1], 2), ([8, 7, 6, 6, 6], 3), ([100, 100, 50], 1)]
    for scores, n in tn_sets:
        df = pd.DataFrame({"name": [f"r{i}" for i in range(len(scores))], "score": scores})
        cases.append(_C("topn_with_ties", df, {"value": "score", "n": n},
                        lambda d, _n=n: d[d["score"].rank(method="min", ascending=False) <= _n].sort_values("score", ascending=False).reset_index(drop=True),
                        f"The top {n} rows by score. Keep name, score.",
                        f"The rows in the top {n} by score VALUE, keeping ALL ties (if rows share the cutoff rank, keep them all). Keep name, score."))

    # --- class 10: nan_as_zero_sum (4) ---
    nz_sets = [
        (["x", "x", "y"], [10.0, np.nan, 5.0]),
        (["a", "b", "b"], [np.nan, 1.0, np.nan]),
        (["g", "g", "g", "h"], [1.0, np.nan, 2.0, np.nan]),
        (["p", "q"], [np.nan, 7.0]),
    ]
    for grp, v in nz_sets:
        df = pd.DataFrame({"grp": grp, "v": v})
        cases.append(_C("nan_as_zero_sum", df, {"group": "grp", "value": "v"},
                        lambda d: d.assign(v=d["v"].fillna(0)).groupby("grp", as_index=False)["v"].sum(),
                        "Total v per group. Columns grp, v.",
                        "Total v per group, treating MISSING values as 0 (a group with one value 10 and one missing totals 10). Columns grp, v."))

    # --- class 11: count_includes_empty (4) ---
    ce_sets = [
        (["a", "a", "c"], ["a", "b", "c"]),
        (["x"], ["x", "y", "z"]),
        (["p", "q", "p"], ["p", "q", "r", "s"]),
        (["m", "m", "m"], ["m", "n"]),
    ]
    for vals, cats in ce_sets:
        df = pd.DataFrame({"cat": pd.Categorical(vals, categories=cats), "v": list(range(len(vals)))})
        cases.append(_C("count_includes_empty", df, {"category": "cat"},
                        lambda d: d.groupby("cat", observed=False).size().reset_index(name="n"),
                        "Number of rows per category. Columns cat, n.",
                        "Number of rows per category INCLUDING categories with ZERO rows (they should appear with n=0). Columns cat, n."))

    # --- class 12: proportion_true (4) ---
    pt_sets = [
        (["x", "x", "x", "y", "y"], [True, False, True, False, False]),
        (["a", "a", "b"], [True, True, False]),
        (["g", "g", "g", "g"], [False, False, False, True]),
        (["p", "q", "q"], [True, False, True]),
    ]
    for grp, passed in pt_sets:
        df = pd.DataFrame({"grp": grp, "passed": passed})
        cases.append(_C("proportion_true", df, {"group": "grp", "flag": "passed", "out": "pass_rate"},
                        lambda d: d.groupby("grp", as_index=False)["passed"].mean().rename(columns={"passed": "pass_rate"}),
                        "Add 'pass_rate' per group from the passed column. Columns grp, pass_rate.",
                        "Add 'pass_rate' = FRACTION of rows where passed is True, per group (a value in [0,1]). Columns grp, pass_rate."))

    # --- class 13: zscore_within_group (4) ---
    zs_sets = [
        (["A", "A", "A", "B", "B", "B"], [10.0, 12.0, 11.0, 50.0, 52.0, 51.0]),
        (["x", "x", "y", "y", "y"], [1.0, 3.0, 20.0, 22.0, 24.0]),
        (["g1", "g1", "g1", "g2", "g2"], [5.0, 7.0, 9.0, 100.0, 104.0]),
        (["p", "p", "q", "q"], [2.0, 6.0, 30.0, 38.0]),
    ]
    for grp, val in zs_sets:
        df = pd.DataFrame({"batch": grp, "value": val})
        cases.append(_C("zscore_within_group", df, {"group": "batch", "value": "value", "out": "z"},
                        lambda d: d.assign(z=d.groupby("batch")["value"].transform(lambda s: (s - s.mean()) / s.std(ddof=0))),
                        "Add 'z' = the z-score of value. Keep batch, value, z.",
                        "Add 'z' = z-score of value computed WITHIN each batch (subtract that batch's own mean, divide by that batch's own std). Keep batch, value, z."))

    # --- class 14: dense_rank (4) ---
    dr_sets = [[10, 9, 9, 7], [5, 5, 5, 1], [8, 7, 6, 6, 6], [100, 90, 90, 80, 70]]
    for scores in dr_sets:
        df = pd.DataFrame({"team": [f"t{i}" for i in range(len(scores))], "pts": scores})
        cases.append(_C("dense_rank", df, {"value": "pts", "out": "rank"},
                        lambda d: d.assign(rank=d["pts"].rank(method="dense", ascending=False).astype(int)),
                        "Add 'rank' ranking teams by pts (highest = 1). Keep team, pts, rank.",
                        "Add 'rank' by pts (highest=1) using DENSE ranking: tied teams share a rank and the next rank is consecutive with NO gaps (1,2,2,3). Keep team, pts, rank."))

    # --- class 15: cumcount_per_group (4) ---
    cc_sets = [
        (["u1", "u1", "u1", "u2", "u2", "u3"]),
        (["a", "a", "b", "b", "b"]),
        (["x", "y", "y", "y", "z", "z"]),
        (["g", "g", "g", "g"]),
    ]
    for users in cc_sets:
        df = pd.DataFrame({"user": users, "event": [f"e{i}" for i in range(len(users))]})
        cases.append(_C("cumcount_per_group", df, {"group": "user", "out": "occurrence"},
                        lambda d: d.assign(occurrence=d.groupby("user").cumcount() + 1),
                        "Add 'occurrence' = a running count of events for each user. Keep user, event, occurrence.",
                        "Add 'occurrence' = a running count that RESETS per user (each user's first event is 1, then 2, 3...). Keep user, event, occurrence."))

    # --- class 16: rank_pct (4) ---
    rp_sets = [[1200, 1850, 1500, 1500, 2100, 1000], [10, 20, 30, 40], [5, 5, 8, 9, 9], [100, 50, 75, 60, 90]]
    for elo in rp_sets:
        df = pd.DataFrame({"player": [f"p{i}" for i in range(len(elo))], "elo": elo})
        cases.append(_C("rank_pct", df, {"value": "elo", "out": "pct"},
                        lambda d: d.assign(pct=d["elo"].rank(pct=True)),
                        "Add 'pct' ranking players by elo. Keep player, elo, pct.",
                        "Add 'pct' = the PERCENTILE rank of elo, a value in [0,1] (rank(pct=True)), not an absolute 1..n rank. Keep player, elo, pct."))

    # --- class 17: clip_outlier (4) ---
    cl_sets = [
        ([5.0, 120.0, 47.0, 3.0, 99.0, 150.0, 60.0, -8.0], 0.0, 100.0),
        ([1.0, 2.0, 50.0, 99.0, 200.0], 0.0, 100.0),
        ([-20.0, 5.0, 10.0, 15.0, 30.0], 0.0, 20.0),
        ([0.5, 1.5, 2.5, 3.5, 4.5], 1.0, 3.0),
    ]
    for vals, lo, hi in cl_sets:
        df = pd.DataFrame({"sensor": [f"s{i}" for i in range(len(vals))], "reading": vals})
        cases.append(_C("clip_outlier", df, {"value": "reading", "lo": lo, "hi": hi, "out": "reading"},
                        lambda d, _lo=lo, _hi=hi: d.assign(reading=d["reading"].clip(_lo, _hi)),
                        f"Limit 'reading' to the range {lo} to {hi}. Keep sensor, reading.",
                        f"CLIP 'reading' to [{lo}, {hi}]: cap values above {hi} and below {lo}, KEEPING every row (do not drop out-of-range rows). Keep sensor, reading."))

    return cases


def gold_of(case: Dict[str, Any]):
    return case["gold"](case["df"], case["df2"]) if "df2" in case else case["gold"](case["df"])


def _validate_offline() -> int:
    """No LLM: confirm every gold is well-formed AND the oracle PASSES on the gold
    (oracle must not false-fire on the known-correct transform)."""
    cases = _cases()
    from collections import Counter
    by_op = Counter(c["op"] for c in cases)
    print(f"{len(cases)} cases across {len(by_op)} operator-semantic classes:")
    for op, n in sorted(by_op.items()):
        print(f"  {op:22} x{n}")
    fp = 0
    for c in cases:
        try:
            g = gold_of(c)
            g = g if isinstance(g, pd.DataFrame) else pd.DataFrame({list(c["params"].values())[0] if c["params"] else "v": [float(g)]})
            inp = {"df": c["df"], **({"df2": c["df2"]} if "df2" in c else {})}
            # build a result frame matching what the oracle expects from gold
            res = gold_of(c)
            if not isinstance(res, pd.DataFrame):
                res = pd.DataFrame({"wavg": [float(res)]})
            oc = oracle_check(c["op"], inp, c["params"], res)
            if oc and oc.fired:
                fp += 1
                print(f"  [FALSE-FIRE] {c['op']} oracle fired on its own GOLD: {oc.detail}")
        except Exception as e:
            fp += 1
            print(f"  [GOLD-ERR] {c['op']}: {repr(e)[:80]}")
    if fp:
        print(f"\nVALIDATION FAILED: {fp} false-fires/errors (oracle must pass on gold).")
        return 1
    print(f"\nVALIDATION OK: all {len(cases)} golds well-formed; oracle PASSES on every gold (0 false-fire).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_validate_offline())
