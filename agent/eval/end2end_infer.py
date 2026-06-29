"""
end2end_infer.py — W3 end-to-end: NL prompt -> inferred (op,params) -> goldless oracle.
No params handed in, no gold seen by the oracle. Measures, on the 68 grid:
  (1) operator-class accuracy of the inferer,
  (2) param-key accuracy (group/value/key/category recovered),
  (3) END-TO-END recall: with INFERRED params, does the oracle fire on a silent
      default and stay silent on the gold? Compares to the params-given upper bound.
Run: cd agent && python eval/end2end_infer.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval.transform_bench import _cases, gold_of  # noqa: E402
from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.transform_intent_infer import infer  # noqa: E402


def _wilson(k, n):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n; z = 1.96; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p), round(100 * (c - h)), round(100 * (c + h)))


# a classic SILENT default per op (runs fine, plausible, wrong) for recall test
def _silent(op, df, df2, P):
    g = P.get("group"); v = P.get("value")
    if op == "weighted_mean":
        return pd.DataFrame({"wavg": [float(df[P["value"]].mean())]})
    if op == "within_group_share":
        return df.assign(**{P["share_col"]: df["sales"] / df["sales"].sum()})
    if op == "pct_point":
        return df.assign(pp=(df[P["new"]] - df[P["old"]]))[["team", "pp"]]
    if op == "dedup_then_agg":
        return df.groupby(g, as_index=False)[v].sum()
    if op == "left_join_keep_all":
        return df.merge(df2, on="id", how="inner")
    if op == "pooled_rate":
        return df.groupby(g).apply(lambda x: (x[P["num"]] / x[P["den"]]).mean(), include_groups=False).reset_index(name=P["out"])
    if op == "median_not_mean":
        return df.groupby(g, as_index=False)[v].mean()
    if op == "cumulative_running":
        return df.assign(balance=df[v])[["day", "balance"]]
    if op == "cumcount_per_group":
        return df.assign(occurrence=range(1, len(df) + 1))
    if op == "topn_with_ties":
        return df.sort_values(v, ascending=False).head(P["n"]).reset_index(drop=True)
    if op == "nan_as_zero_sum":
        return df.groupby(g, as_index=False)[v].sum()
    if op == "count_includes_empty":
        return df.groupby(P["category"], observed=True).size().reset_index(name="n")
    if op == "proportion_true":
        return df.groupby(g, as_index=False)[P["flag"]].sum().rename(columns={P["flag"]: P["out"]})
    if op == "zscore_within_group":
        return df.assign(z=(df[v] - df[v].mean()) / df[v].std(ddof=0))
    if op == "dense_rank":
        return df.assign(rank=df[v].rank(method="min", ascending=False).astype(int))
    if op == "rank_pct":
        return df.assign(pct=df[v].rank())
    if op == "clip_outlier":
        return df[(df[v] >= P["lo"]) & (df[v] <= P["hi"])]
    return None


_KEYS = {"group", "value", "key", "category", "weight", "num", "den", "new", "old", "flag"}


def main():
    cases = _cases()
    op_ok = pk_ok = pk_tot = 0
    rec_inf = rec_given = fp = 0; n = 0
    for c in cases:
        n += 1
        df = c["df"]; df2 = c.get("df2"); P_gold = c["params"]
        op_i, P_i = infer(c["ambiguous"], df, df2)
        if op_i == c["op"]:
            op_ok += 1
        # param-key accuracy on the keys both dicts care about
        for k in _KEYS & set(P_gold):
            pk_tot += 1
            if P_i.get(k) == P_gold[k]:
                pk_ok += 1
        # end-to-end: inferred op+params (FP on gold, recall on silent)
        inp = {"df": df, **({"df2": df2} if df2 is not None else {})}
        if op_i == c["op"]:
            try:
                r = oracle_check(op_i, inp, P_i, _silent(op_i, df, df2, P_i))
                if r and r.fired:
                    rec_inf += 1
            except Exception:
                pass
            try:
                gc = oracle_check(op_i, inp, P_i, gold_of(c) if isinstance(gold_of(c), pd.DataFrame) else pd.DataFrame({"wavg": [float(gold_of(c))]}))
                if gc and gc.fired:
                    fp += 1
            except Exception:
                pass
        # params-given upper bound recall
        try:
            r2 = oracle_check(c["op"], inp, P_gold, _silent(c["op"], df, df2, P_gold))
            if r2 and r2.fired:
                rec_given += 1
        except Exception:
            pass
    print(f"N={n} cases (17 ops x4)")
    print(f"op-class accuracy : {op_ok}/{n} = {_wilson(op_ok,n)[0]}% {_wilson(op_ok,n)[1:]}")
    print(f"param-key accuracy: {pk_ok}/{pk_tot} = {round(100*pk_ok/pk_tot)}%")
    print(f"end2end recall (INFERRED params): {rec_inf}/{n} = {_wilson(rec_inf,n)[0]}% {_wilson(rec_inf,n)[1:]}")
    print(f"recall (params GIVEN, upper bnd): {rec_given}/{n} = {_wilson(rec_given,n)[0]}%")
    print(f"false-fire on gold (inferred)   : {fp}/{op_ok} = {round(100*fp/max(op_ok,1))}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
