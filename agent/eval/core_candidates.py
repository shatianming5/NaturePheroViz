"""
core_candidates.py — Candidate-shaped fixtures for the 12 CORE operators, so the
auto-contract-synthesis experiment (autocontract_synth.py) can cover them too, taking the
total to N=23 operators (12 core + 11 expansion) — above the reviewer's N>=17 bar.

Each core operator's (fixture, params, wrong_fn=silent slip, correct_fn=intended) is the
same pair the oracle self-test uses; we add alt_correct_fns (other VALID implementations)
so the FULL (FP-robustness) bar is a real test. These objects expose exactly the attributes
autocontract_synth reads: operator, cid, fixture, params, wrong_fn, correct_fn, alt_correct_fns.
"""
from __future__ import annotations
from types import SimpleNamespace
import numpy as np
import pandas as pd


def _c(operator, fixture, params, wrong_fn, correct_fn, alt_correct_fns):
    return SimpleNamespace(cid=f"CORE-{operator}", operator=operator, fixture=fixture,
                           params=params, wrong_fn=wrong_fn, correct_fn=correct_fn,
                           alt_correct_fns=alt_correct_fns)


CORE_CANDIDATES = []

# weighted_mean
CORE_CANDIDATES.append(_c(
    "weighted_mean",
    lambda: {"df": pd.DataFrame({"price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})},
    {"value": "price", "weight": "qty"},
    lambda inp: pd.DataFrame({"wavg": [inp["df"]["price"].mean()]}),
    lambda inp: pd.DataFrame({"wavg": [(inp["df"]["price"] * inp["df"]["qty"]).sum() / inp["df"]["qty"].sum()]}),
    [lambda inp: pd.DataFrame({"wavg": [np.average(inp["df"]["price"], weights=inp["df"]["qty"])]})]))

# within_group_share
CORE_CANDIDATES.append(_c(
    "within_group_share",
    lambda: {"df": pd.DataFrame({"region": ["N", "N", "S", "S"], "sales": [30, 10, 20, 20]})},
    {"group": "region", "share_col": "share"},
    lambda inp: inp["df"].assign(share=inp["df"]["sales"] / inp["df"]["sales"].sum()),
    lambda inp: inp["df"].assign(share=inp["df"]["sales"] / inp["df"].groupby("region")["sales"].transform("sum")),
    [lambda inp: inp["df"].assign(share=inp["df"].groupby("region")["sales"].apply(lambda s: s / s.sum()).reset_index(level=0, drop=True))]))

# pct_point
CORE_CANDIDATES.append(_c(
    "pct_point",
    lambda: {"df": pd.DataFrame({"team": ["A", "B"], "r0": [0.20, 0.50], "r1": [0.30, 0.55]})},
    {"new": "r1", "old": "r0", "out": "pp"},
    lambda inp: inp["df"].assign(pp=(inp["df"]["r1"] - inp["df"]["r0"]) / inp["df"]["r0"])[["team", "pp"]],
    lambda inp: inp["df"].assign(pp=(inp["df"]["r1"] - inp["df"]["r0"]) * 100)[["team", "pp"]],
    [lambda inp: inp["df"].assign(pp=(inp["df"]["r1"] * 100 - inp["df"]["r0"] * 100))[["team", "pp"]]]))

# dedup_then_agg
CORE_CANDIDATES.append(_c(
    "dedup_then_agg",
    lambda: {"df": pd.DataFrame({"region": ["N", "N", "N", "S"], "order_id": [1, 1, 2, 3], "rev": [50, 50, 30, 40]})},
    {"key": "order_id", "value": "rev", "group": "region"},
    lambda inp: inp["df"].groupby("region", as_index=False)["rev"].sum(),
    lambda inp: inp["df"].drop_duplicates("order_id").groupby("region", as_index=False)["rev"].sum(),
    [lambda inp: inp["df"].drop_duplicates("order_id").groupby("region")["rev"].sum().reset_index()]))

# left_join_keep_all
CORE_CANDIDATES.append(_c(
    "left_join_keep_all",
    lambda: {"df": pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]}),
             "df2": pd.DataFrame({"id": [1, 3], "score": [88, 99]})},
    {},
    lambda inp: inp["df"].merge(inp["df2"], on="id", how="inner"),
    lambda inp: inp["df"].merge(inp["df2"], on="id", how="left"),
    [lambda inp: inp["df"].merge(inp["df2"], on="id", how="outer")]))

# pooled_rate
CORE_CANDIDATES.append(_c(
    "pooled_rate",
    lambda: {"df": pd.DataFrame({"region": ["N", "N", "S"], "clicks": [1, 99, 50], "imps": [10, 100, 100]})},
    {"group": "region", "num": "clicks", "den": "imps", "out": "ctr"},
    lambda inp: inp["df"].assign(_r=inp["df"]["clicks"] / inp["df"]["imps"]).groupby("region")["_r"].mean().reset_index(name="ctr"),
    lambda inp: inp["df"].groupby("region").apply(lambda g: g["clicks"].sum() / g["imps"].sum(), include_groups=False).reset_index(name="ctr"),
    [lambda inp: (inp["df"].groupby("region")["clicks"].sum() / inp["df"].groupby("region")["imps"].sum()).reset_index(name="ctr")]))

# median_not_mean
CORE_CANDIDATES.append(_c(
    "median_not_mean",
    lambda: {"df": pd.DataFrame({"grp": ["x", "x", "x", "y", "y", "y"], "v": [1.0, 2.0, 9.0, 4.0, 5.0, 60.0]})},
    {"group": "grp", "value": "v"},
    lambda inp: inp["df"].groupby("grp", as_index=False)["v"].mean(),
    lambda inp: inp["df"].groupby("grp", as_index=False)["v"].median(),
    [lambda inp: inp["df"].groupby("grp")["v"].median().reset_index()]))

# cumulative_running
CORE_CANDIDATES.append(_c(
    "cumulative_running",
    lambda: {"df": pd.DataFrame({"day": [1, 2, 3, 4], "delta": [10, -5, 8, -3]})},
    {"value": "delta", "out": "balance"},
    lambda inp: inp["df"].assign(balance=inp["df"]["delta"])[["day", "balance"]],
    lambda inp: inp["df"].sort_values("day").assign(balance=lambda x: x["delta"].cumsum())[["day", "balance"]],
    [lambda inp: inp["df"].assign(balance=inp["df"].sort_values("day")["delta"].cumsum())[["day", "balance"]]]))

# topn_with_ties
CORE_CANDIDATES.append(_c(
    "topn_with_ties",
    lambda: {"df": pd.DataFrame({"name": list("abcd"), "score": [10, 9, 9, 7]})},
    {"value": "score", "n": 2},
    lambda inp: inp["df"].sort_values("score", ascending=False).head(2).reset_index(drop=True),
    lambda inp: inp["df"][inp["df"]["score"] >= 9].reset_index(drop=True),
    [lambda inp: inp["df"].nlargest(2, "score", keep="all").reset_index(drop=True)]))

# nan_as_zero_sum
CORE_CANDIDATES.append(_c(
    "nan_as_zero_sum",
    lambda: {"df": pd.DataFrame({"grp": ["x", "x", "y"], "v": [10.0, np.nan, 5.0]})},
    {"group": "grp", "value": "v"},
    lambda inp: pd.DataFrame({"grp": ["x", "y"], "v": [np.nan, 5.0]}),
    lambda inp: inp["df"].assign(v=inp["df"]["v"].fillna(0)).groupby("grp", as_index=False)["v"].sum(),
    [lambda inp: inp["df"].fillna({"v": 0}).groupby("grp", as_index=False)["v"].sum()]))

# count_includes_empty
CORE_CANDIDATES.append(_c(
    "count_includes_empty",
    lambda: {"df": pd.DataFrame({"cat": pd.Categorical(["a", "a", "c"], categories=["a", "b", "c"]), "v": [1, 2, 3]})},
    {"category": "cat"},
    lambda inp: inp["df"].groupby("cat", observed=True).size().reset_index(name="n"),
    lambda inp: inp["df"].groupby("cat", observed=False).size().reset_index(name="n"),
    [lambda inp: inp["df"]["cat"].value_counts().reindex(inp["df"]["cat"].cat.categories, fill_value=0).rename_axis("cat").reset_index(name="n")]))

# proportion_true
CORE_CANDIDATES.append(_c(
    "proportion_true",
    lambda: {"df": pd.DataFrame({"grp": ["x", "x", "x", "y", "y"], "passed": [True, False, True, False, False]})},
    {"group": "grp", "flag": "passed", "out": "pass_rate"},
    lambda inp: inp["df"].groupby("grp", as_index=False)["passed"].sum().rename(columns={"passed": "pass_rate"}),
    lambda inp: inp["df"].groupby("grp", as_index=False)["passed"].mean().rename(columns={"passed": "pass_rate"}),
    [lambda inp: inp["df"].assign(passed=inp["df"]["passed"].astype(float)).groupby("grp", as_index=False)["passed"].mean().rename(columns={"passed": "pass_rate"})]))
