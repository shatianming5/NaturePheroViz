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


def expansion_cases() -> List[Dict[str, Any]]:
    """The 10 NEW operator classes (D1 framework-mechanics + D2 cross-domain), x2 each.

    Kept SEPARATE from _cases() so the established 17-op / 68-case grid and its NL->op
    inferer stay unchanged; these are validated offline (below) and measured by
    eval/expansion_prevalence.py. latlon_swap and numpy_broadcast have viable goldless
    contracts but no natural NL->pandas-on-DataFrame transform, so they live in the
    oracle/probe only, not this generation grid."""
    cases: List[Dict[str, Any]] = []
    # ===================== expansion grid (D1 framework + D2 cross-domain) =====================

    # --- class 18: index_align (2) — combine two frames BY KEY, not by position ---
    ia_sets = [
        ([1, 2, 3, 4], [10.0, 20.0, 30.0, 40.0], [4, 1, 2], [4.0, 1.0, 2.0]),
        ([10, 11, 12], [5.0, 6.0, 7.0], [12, 10], [70.0, 50.0]),
    ]
    for bid, bv, aid, aw in ia_sets:
        base = pd.DataFrame({"id": bid, "v": bv}); other = pd.DataFrame({"id": aid, "w": aw})
        cases.append(_C("index_align", base, {"key": "id", "value": "v", "addend": "w", "out": "total"},
                        lambda d, d2: d.merge(d2, on="id", how="left").assign(
                            total=lambda x: x["v"] + x["w"].fillna(0.0))[["id", "v", "total"]],
                        "Add 'total' = each row's v plus its matching w from df2. Keep id, v, total.",
                        "Add 'total' = v + the w for the SAME id in df2 (match BY id, NOT by row order); "
                        "if an id has no w, use 0. Keep id, v, total.",
                        df2=other))

    # --- class 19: dtype_coerce (2) — keep identifier as string (leading zeros) ---
    dc_sets = [(["01001", "02134", "00501", "12345"], [10, 20, 30, 40]),
               (["007", "042", "100"], [1, 2, 3])]
    for zips, pop in dc_sets:
        df = pd.DataFrame({"zip": zips, "pop": pop})
        cases.append(_C("dtype_coerce", df, {"id_col": "zip", "out": "zkey"},
                        lambda d: d.assign(zkey=d["zip"].astype(str)),
                        "Add a key column 'zkey' from the zip code for joining. Keep zip, pop, zkey.",
                        "Add 'zkey' = the zip as a STRING identifier, preserving leading zeros exactly "
                        "(do NOT cast to int). Keep zip, pop, zkey."))

    # --- class 20: groupby_dropna_key (2) — NaN keys are their own group, not dropped ---
    gd_sets = [(["A", "A", None, "B", None], [10, 20, 30, 40, 50]),
               (["x", None, "y", "y", None, "x"], [1, 2, 3, 4, 5, 6])]
    for g, v in gd_sets:
        df = pd.DataFrame({"g": g, "v": v})
        cases.append(_C("groupby_dropna_key", df, {"group": "g", "value": "v"},
                        lambda d: d.groupby("g", dropna=False, as_index=False)["v"].sum(),
                        "Sum v for each group g. Return one row per group with columns g, v.",
                        "Sum v for each group g, INCLUDING rows whose g is missing (NaN) as their own "
                        "group — do not drop them. Columns g, v."))

    # --- class 21: order_dependent_dedup (2) — keep the MAX-order row, data unsorted ---
    od_sets = [([1, 1, 2, 2, 2], [1, 2, 1, 2, 3], [10, 99, 5, 7, 3]),
               ([5, 5, 6], [3, 1, 2], [50, 11, 22])]
    for i, t, v in od_sets:
        df = pd.DataFrame({"id": i, "ts": t, "v": v})
        cases.append(_C("order_dependent_dedup", df, {"key": "id", "order": "ts"},
                        lambda d: d.sort_values("ts").drop_duplicates("id", keep="last").reset_index(drop=True),
                        "Keep one row per id: the most recent record (highest ts). Keep id, ts, v.",
                        "For each id keep the row with the MAXIMUM ts (the data is NOT pre-sorted, so sort "
                        "by ts first or use idxmax — do not just take the first occurrence). Keep id, ts, v."))

    # --- class 22: resample_boundary (2) — right-closed/right-labelled hourly bins ---
    rs_sets = [["2026-01-01 00:00", "2026-01-01 00:30", "2026-01-01 01:00", "2026-01-01 01:30"],
               ["2026-03-01 09:00", "2026-03-01 09:45", "2026-03-01 10:00", "2026-03-01 11:00"]]
    for ts in rs_sets:
        df = pd.DataFrame({"t": pd.to_datetime(ts), "v": [1.0, 2.0, 3.0, 4.0]})
        cases.append(_C("resample_boundary", df,
                        {"time": "t", "value": "v", "closed": "right", "label": "right", "freq": "1h"},
                        lambda d: d.resample("1h", on="t", closed="right", label="right")
                                   .sum(numeric_only=True).reset_index(),
                        "Resample v into hourly sums. Columns t, v.",
                        "Resample v into hourly sums with RIGHT-closed, RIGHT-labelled bins "
                        "(closed='right', label='right'), so a point exactly on the hour falls in the "
                        "earlier bin. Columns t, v."))

    # --- class 23: string_normalize_join (2) — case/space-insensitive key match ---
    sn_sets = [(["Apple ", "banana", "CHERRY"], [1, 2, 3], ["apple", "banana", "cherry"], [10, 20, 30]),
               ([" Foo", "BAR ", "baz"], [4, 5, 6], ["foo", "bar", "baz"], [7, 8, 9])]
    for ln, q, rn, pr in sn_sets:
        L = pd.DataFrame({"name": ln, "qty": q}); R = pd.DataFrame({"name": rn, "price": pr})
        cases.append(_C("string_normalize_join", L, {"key": "name", "lookup_value": "price"},
                        lambda d, d2: (d.assign(_k=d["name"].str.strip().str.lower())
                                       .merge(d2.assign(_k=d2["name"].str.strip().str.lower())[["_k", "price"]],
                                              on="_k", how="left").drop(columns="_k")),
                        "Attach each row's price from df2 by matching name. Keep name, qty, price.",
                        "Attach price from df2 by matching name CASE- and WHITESPACE-insensitively "
                        "(strip and lowercase both sides before matching). Keep name, qty, price.",
                        df2=R))

    # --- class 24: join_fanout (2) — don't let a label-table join double-count a measure ---
    jf_sets = [([1, 2, 3], ["x", "y", "x"], [100.0, 200.0, 300.0], ["x", "x", "y"], ["t1", "t2", "t3"]),
               ([1, 2], ["a", "b"], [40.0, 60.0], ["a", "a", "a", "b"], ["p", "q", "r", "s"])]
    for oid, ocat, amt, tcat, tag in jf_sets:
        orders = pd.DataFrame({"oid": oid, "cat": ocat, "amt": amt})
        tags = pd.DataFrame({"cat": tcat, "tag": tag})
        cases.append(_C("join_fanout", orders, {"measure": "amt", "group": "cat"},
                        lambda d, d2: d.groupby("cat", as_index=False)["amt"].sum(),
                        "Total amt per cat. df is orders, df2 is the cat tags. Columns cat, amt.",
                        "Total amt per cat from df (orders) ONLY. df2 (tags) has SEVERAL rows per cat, so "
                        "joining it in would duplicate orders and inflate amt — aggregate orders without "
                        "fanning out on tags. Columns cat, amt.",
                        df2=tags))

    # --- class 25: null_in_agg_count (2) — count records (COUNT(*)), not non-null (COUNT(col)) ---
    nc_sets = [(["A", "A", "A", "B", "B"], [1.0, np.nan, 3.0, np.nan, 5.0]),
               (["g1", "g1", "g2"], [np.nan, np.nan, 7.0])]
    for g, resp in nc_sets:
        df = pd.DataFrame({"g": g, "resp": resp})
        cases.append(_C("null_in_agg_count", df, {"group": "g", "out": "n"},
                        lambda d: d.groupby("g").size().reset_index(name="n"),
                        "Count the number of records in each group g. Columns g, n.",
                        "Count ALL records per group g (every row, including those whose resp is missing "
                        "— use the group size, not a non-null count). Columns g, n."))

    # --- class 26: scale_before_split_leakage (2) — fit scaler on TRAIN only ---
    lk_sets = [(np.array([0, 1, 2, 3, 4, 50, 51, 52, 53, 54], float), ["train"] * 5 + ["test"] * 5),
               (np.array([10, 12, 11, 13, 40, 42, 41], float), ["train"] * 4 + ["test"] * 3)]
    for x, sp in lk_sets:
        df = pd.DataFrame({"x": x, "split": sp})
        cases.append(_C("scale_before_split_leakage", df,
                        {"feature": "x", "split": "split", "train_label": "train", "scaled": "xs"},
                        lambda d: d.assign(xs=(d["x"] - d.loc[d["split"] == "train", "x"].mean())
                                           / d.loc[d["split"] == "train", "x"].std(ddof=0)),
                        "Standardize x (z-score) into column 'xs'. Keep x, split, xs.",
                        "Standardize x into 'xs' using ONLY the train rows' mean and std "
                        "(fit on split=='train', then apply to every row) — do NOT include test rows in "
                        "the statistics. Keep x, split, xs."))

    # --- class 27: lookahead_return (2) — return uses PAST price only ---
    la_sets = [[100.0, 110.0, 115.0, 100.0, 130.0], [50.0, 55.0, 50.0, 60.0]]
    for prices in la_sets:
        df = pd.DataFrame({"day": list(range(1, len(prices) + 1)), "price": prices})
        cases.append(_C("lookahead_return", df, {"price": "price", "out": "ret"},
                        lambda d: d.assign(ret=(d["price"] - d["price"].shift(1)) / d["price"].shift(1)),
                        "Add 'ret' = the period-over-period return of price. Keep day, price, ret.",
                        "Add 'ret' = (price[t]-price[t-1])/price[t-1], using only PAST prices "
                        "(the first row's ret is NaN; never use a future price). Keep day, price, ret."))

    return cases


def gold_of(case: Dict[str, Any]):
    return case["gold"](case["df"], case["df2"]) if "df2" in case else case["gold"](case["df"])


def _validate_offline() -> int:
    """No LLM: confirm every gold is well-formed AND the oracle PASSES on the gold
    (oracle must not false-fire on the known-correct transform). Covers the established
    grid (_cases) AND the expansion grid (expansion_cases)."""
    cases = _cases() + expansion_cases()
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
