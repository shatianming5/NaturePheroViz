"""
operator_expansion.py — feasibility probe for BROADENING the silent-error operator taxonomy.

Motivation (reviewer/PI pushback): the current 17 contracts in transform_oracle.py are
all "pick-the-wrong-statistic" gotchas inside single-step pandas aggregation — i.e. the
WELL-KNOWN concept traps a careful analyst already anticipates (median vs mean, join how,
weighted mean...). To strengthen the measurement claim we need error sources that are NOT
"sources everyone already knows":

  Direction 1 (depth / same pandas domain, FRAMEWORK-MECHANICS errors):
    the code looks right and the concept is simple, but a pandas/numpy DEFAULT silently
    changes the numbers (index alignment, dtype coercion, dropna-on-keys, keep= order,
    resample boundary, string-key normalization).

  Direction 2 (breadth / ADJACENT codegen domains):
    the same "silent + no-gold" phenomenon in SQL-style joins, ML preprocessing data
    LEAKAGE, time-series look-ahead, numpy broadcasting, and geospatial conventions.

This module is the OFFLINE feasibility harness (no LLM, like transform_bench's offline
gold+oracle validation). For each candidate operator it ships:
  - a fixture,
  - wrong_fn   : the realistic SILENT-DEFAULT implementation an LLM/naive analyst writes,
  - correct_fn : the intended implementation (used only to LABEL; the contract never sees it),
  - contract   : a GOLDLESS invariant predicate (input df + intent params + result only).

A candidate is METHOD-VIABLE iff, on the fixture:
  (a) wrong_fn runs WITHOUT raising and yields a plausible (silent) result,
  (b) the contract FIRES on the wrong result, and
  (c) the contract does NOT fire on the correct result (no false positive).

We also record whether a GENERIC baseline (exec-pass / shape-or-range validity) would
ALSO catch it — a candidate is high-NOVELTY only when those generic checks miss it
(exec-pass and value-range are exactly the 0%-recall baselines in baseline_compare.py).

Run:  cd agent && python eval/operator_expansion.py
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval.transform_oracle import ContractResult  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _num(series) -> np.ndarray:
    return pd.to_numeric(pd.Series(series), errors="coerce").to_numpy(dtype=float)


def _close(a, b, tol: float = 1e-6) -> bool:
    if a is None or b is None:
        return False
    a = float(a); b = float(b)
    if np.isnan(a) or np.isnan(b):
        return False
    return abs(a - b) <= max(abs(b) * tol, tol)


@dataclass
class Candidate:
    cid: str
    direction: str            # "D1-framework" | "D2-cross-domain"
    operator: str
    why_silent: str           # why the wrong result passes exec + looks plausible
    why_nonobvious: str       # why it is NOT a "source everyone already knows"
    fixture: Callable[[], Dict[str, Any]]          # -> {"df":..., optional "df2":...}
    params: Dict[str, Any]
    wrong_fn: Callable[[Dict[str, Any]], Any]      # silent-default (LLM-like) impl
    correct_fn: Callable[[Dict[str, Any]], Any]    # intended impl (label only)
    contract: Callable[[Dict[str, Any], Dict[str, Any], Any], ContractResult]
    generic_catch: str        # which generic baseline (if any) would also catch it
    boundary: str = ""        # honest limitation / when it is NOT detectable
    # alternative VALID implementations: a robust contract must NOT fire on any of
    # them (guards against the contract being hand-fitted to one correct_fn = FP risk)
    alt_correct_fns: List[Callable[[Dict[str, Any]], Any]] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# DIRECTION 1 — framework-mechanics silent errors (same pandas domain)
# --------------------------------------------------------------------------- #

# D1-1  index auto-alignment: combining two columns pairs by INDEX/position, not by key
def _fx_index_align():
    base = pd.DataFrame({"id": [1, 2, 3, 4], "v": [10.0, 20.0, 30.0, 40.0]})
    adj = pd.DataFrame({"id": [4, 1, 2], "w": [4.0, 1.0, 2.0]})  # different order, missing id=3
    return {"df": base, "df2": adj}


def _wrong_index_align(fx):
    base, adj = fx["df"], fx["df2"]
    # naive: "just add the two columns" -> pandas aligns adj['w'] onto base's RangeIndex
    # by POSITION, silently mis-pairing ids and NaN-ing the 4th row.
    return base.assign(total=base["v"] + adj["w"])


def _correct_index_align(fx):
    base, adj = fx["df"], fx["df2"]
    m = base.merge(adj, on="id", how="left")
    return m.assign(total=m["v"] + m["w"].fillna(0.0))[["id", "v", "total"]]


def _c_index_align(inp, params, result) -> ContractResult:
    name = "index_align"
    base, adj = inp["df"], inp["df2"]
    key, vcol, wcol = params["key"], params["value"], params["addend"]
    if result is None or "total" not in result.columns or key not in result.columns:
        return ContractResult(name, True, "missing total/key column")
    wmap = dict(zip(adj[key].tolist(), _num(adj[wcol])))
    exp = {int(r[key]): float(r[vcol]) + float(wmap.get(r[key], 0.0)) for _, r in base.iterrows()}
    got = dict(zip(result[key].astype(int), _num(result["total"])))
    bad = [k for k, ev in exp.items() if not _close(got.get(k), ev)]
    if bad:
        return ContractResult(name, True, f"by-key combine wrong at id(s) {bad} (positional mis-alignment / spurious NaN)")
    return ContractResult(name, False, "every id's combined value matches by-key recomputation")


# D1-2  dtype coercion: identifier with leading zeros silently cast to int
def _fx_dtype_coerce():
    return {"df": pd.DataFrame({"zip": ["01001", "02134", "00501", "12345"], "pop": [10, 20, 30, 40]})}


def _wrong_dtype_coerce(fx):
    df = fx["df"]
    return df.assign(zkey=df["zip"].astype(int))  # 01001 -> 1001, leading zero lost


def _correct_dtype_coerce(fx):
    df = fx["df"]
    return df.assign(zkey=df["zip"].astype(str))


def _c_dtype_coerce(inp, params, result) -> ContractResult:
    name = "dtype_coerce"
    df = inp["df"]; src, out = params["id_col"], params["out"]
    if result is None or out not in result.columns:
        return ContractResult(name, True, f"missing {out}")
    orig = df[src].astype(str).tolist()
    got = [str(x) for x in result[out].tolist()]
    lost = [(o, g) for o, g in zip(orig, got) if o != g]
    if lost:
        return ContractResult(name, True, f"identifier altered (leading-zero/precision loss), e.g. {lost[:2]}")
    return ContractResult(name, False, "identifier preserved exactly as string")


# D1-3  groupby silently DROPS rows whose key is NaN (dropna=True default)
def _fx_groupby_dropna():
    return {"df": pd.DataFrame({"g": ["A", "A", None, "B", None], "v": [10, 20, 30, 40, 50]})}


def _wrong_groupby_dropna(fx):
    return fx["df"].groupby("g")["v"].sum().reset_index()


def _correct_groupby_dropna(fx):
    return fx["df"].groupby("g", dropna=False)["v"].sum().reset_index()


def _c_groupby_dropna(inp, params, result) -> ContractResult:
    name = "groupby_dropna_key"
    df = inp["df"]; vcol = params["value"]
    if result is None or vcol not in result.columns:
        return ContractResult(name, True, f"missing {vcol}")
    total_in = float(_num(df[vcol]).sum())
    total_out = float(_num(result[vcol]).sum())
    if _close(total_out, total_in):
        return ContractResult(name, False, f"group totals conserve all {total_in:g}")
    return ContractResult(name, True, f"total {total_out:g} < input {total_in:g}: NaN-key rows silently dropped")


# D1-4  drop_duplicates keep= / unsorted: keeps an ARBITRARY row, not the intended one
def _fx_order_dedup():
    return {"df": pd.DataFrame({"id": [1, 1, 2, 2, 2], "ts": [1, 2, 1, 2, 3], "v": [10, 99, 5, 7, 3]})}


def _wrong_order_dedup(fx):
    return fx["df"].drop_duplicates("id")  # keeps FIRST -> id1 ts1, id2 ts1


def _correct_order_dedup(fx):
    return fx["df"].sort_values("ts").drop_duplicates("id", keep="last")


def _c_order_dedup(inp, params, result) -> ContractResult:
    name = "order_dependent_dedup"
    df = inp["df"]; key, order = params["key"], params["order"]
    if result is None or key not in result.columns or order not in result.columns:
        return ContractResult(name, True, "missing key/order column")
    want = df.loc[df.groupby(key)[order].idxmax()].set_index(key)[order].to_dict()
    got = dict(zip(result[key], result[order]))
    bad = [k for k, ts in want.items() if not _close(got.get(k), ts)]
    if bad:
        return ContractResult(name, True, f"kept non-latest row for id(s) {bad} (drop_duplicates keep=first on unsorted)")
    return ContractResult(name, False, "kept the max-order row per key")


# D1-5  resample boundary: default closed='left'/label='left' bins differ from intent
def _fx_resample():
    idx = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:30",
                          "2026-01-01 01:00", "2026-01-01 01:30"])
    return {"df": pd.DataFrame({"t": idx, "v": [1.0, 2.0, 3.0, 4.0]})}


def _wrong_resample(fx):
    return fx["df"].resample("1h", on="t").sum(numeric_only=True).reset_index()  # default closed/label='left'


def _correct_resample(fx):
    p = {"closed": "right", "label": "right"}
    return fx["df"].resample("1h", on="t", closed=p["closed"], label=p["label"]).sum(numeric_only=True).reset_index()


def _c_resample(inp, params, result) -> ContractResult:
    name = "resample_boundary"
    df = inp["df"]; tcol, vcol = params["time"], params["value"]
    closed, label = params["closed"], params["label"]
    if result is None or vcol not in result.columns:
        return ContractResult(name, True, f"missing {vcol}")
    intended = (df.resample("1h", on=tcol, closed=closed, label=label)
                  .sum(numeric_only=True).reset_index())
    iv = np.sort(_num(intended[vcol])); gv = np.sort(_num(result[vcol]))
    if len(iv) == len(gv) and np.allclose(iv, gv):
        return ContractResult(name, False, "bin sums match intended closed/label convention")
    return ContractResult(name, True, f"bin sums {gv.tolist()} != intended {iv.tolist()} (wrong closed/label boundary)")


# D1-6  string-key normalization: join misses on case/whitespace, silently NaN
def _fx_str_norm():
    left = pd.DataFrame({"name": ["Apple ", "banana", "CHERRY"], "qty": [1, 2, 3]})
    lookup = pd.DataFrame({"name": ["apple", "banana", "cherry"], "price": [10, 20, 30]})
    return {"df": left, "df2": lookup}


def _wrong_str_norm(fx):
    return fx["df"].merge(fx["df2"], on="name", how="left")  # only 'banana' matches


def _correct_str_norm(fx):
    L = fx["df"].assign(_k=fx["df"]["name"].str.strip().str.lower())
    R = fx["df2"].assign(_k=fx["df2"]["name"].str.strip().str.lower())
    return L.merge(R[["_k", "price"]], on="_k", how="left").drop(columns="_k")


def _c_str_norm(inp, params, result) -> ContractResult:
    name = "string_normalize_join"
    L, R = inp["df"], inp["df2"]; key, val = params["key"], params["lookup_value"]
    if result is None or val not in result.columns:
        return ContractResult(name, True, f"missing {val}")
    norm = {str(k).strip().lower() for k in R[key]}
    miss = []
    for lk, pv in zip(L[key], _num(result[val])):
        if str(lk).strip().lower() in norm and (pv is None or np.isnan(pv)):
            miss.append(lk)
    if miss:
        return ContractResult(name, True, f"NaN lookup for key(s) {miss} that DO match after normalization")
    return ContractResult(name, False, "all normalizable keys matched")


# --------------------------------------------------------------------------- #
# DIRECTION 2 — cross-domain silent errors
# --------------------------------------------------------------------------- #

# D2-1  JOIN fan-out: many-to-many join duplicates left rows, inflating an additive measure
def _fx_join_fanout():
    orders = pd.DataFrame({"oid": [1, 2, 3], "cat": ["x", "y", "x"], "amt": [100.0, 200.0, 300.0]})
    tags = pd.DataFrame({"cat": ["x", "x", "y"], "tag": ["t1", "t2", "t3"]})  # cat 'x' duplicated
    return {"df": orders, "df2": tags}


def _wrong_join_fanout(fx):
    j = fx["df"].merge(fx["df2"], on="cat")          # x rows duplicated x2
    return j.groupby("cat")["amt"].sum().reset_index()


def _correct_join_fanout(fx):
    return fx["df"].groupby("cat")["amt"].sum().reset_index()


def _c_join_fanout(inp, params, result) -> ContractResult:
    name = "join_fanout"
    orders = inp["df"]; amt, grp = params["measure"], params["group"]
    if result is None or amt not in result.columns:
        return ContractResult(name, True, f"missing {amt}")
    total_in = float(_num(orders[amt]).sum())
    total_out = float(_num(result[amt]).sum())
    if _close(total_out, total_in):
        return ContractResult(name, False, f"additive measure conserved ({total_in:g})")
    return ContractResult(name, True, f"measure total {total_out:g} != pre-join {total_in:g}: join fan-out duplicated rows")


# D2-2  NULL semantics: COUNT(col) skips NULL, COUNT(*) doesn't
def _fx_null_count():
    return {"df": pd.DataFrame({"g": ["A", "A", "A", "B", "B"], "resp": [1.0, np.nan, 3.0, np.nan, 5.0]})}


def _wrong_null_count(fx):
    return fx["df"].groupby("g")["resp"].count().reset_index(name="n")  # skips NaN


def _correct_null_count(fx):
    return fx["df"].groupby("g").size().reset_index(name="n")


def _c_null_count(inp, params, result) -> ContractResult:
    name = "null_in_agg_count"
    df = inp["df"]; grp, out = params["group"], params["out"]
    if result is None or out not in result.columns or grp not in result.columns:
        return ContractResult(name, True, "missing group/count column")
    size = df.groupby(grp).size().to_dict()
    got = dict(zip(result[grp].astype(str), _num(result[out])))
    bad = [g for g, sz in size.items() if not _close(got.get(str(g)), sz)]
    if bad:
        return ContractResult(name, True, f"record count != group size for {bad}: COUNT(col) dropped NULL rows")
    return ContractResult(name, False, "per-group count equals group size")


# D2-3  DATA LEAKAGE: standardize using GLOBAL stats (fit on train+test) -- the crown jewel
def _fx_leakage():
    x = np.array([0, 1, 2, 3, 4, 50, 51, 52, 53, 54], float)  # train low, test high (differ)
    split = np.array(["train"] * 5 + ["test"] * 5)
    return {"df": pd.DataFrame({"x": x, "split": split})}


def _wrong_leakage(fx):
    df = fx["df"].copy()
    mu, sd = df["x"].mean(), df["x"].std(ddof=0)        # fit on ALL data -> leakage
    df["xs"] = (df["x"] - mu) / sd
    return df


def _correct_leakage(fx):
    df = fx["df"].copy()
    tr = df["split"] == "train"
    mu, sd = df.loc[tr, "x"].mean(), df.loc[tr, "x"].std(ddof=0)  # fit on TRAIN only
    df["xs"] = (df["x"] - mu) / sd
    return df


def _c_leakage(inp, params, result) -> ContractResult:
    name = "scale_before_split_leakage"
    splitc, lab, out = params["split"], params["train_label"], params["scaled"]
    if result is None or out not in result.columns or splitc not in result.columns:
        return ContractResult(name, True, "missing scaled/split column")
    tr = result[result[splitc] == lab][out]
    m, s = float(_num(tr).mean()), float(_num(tr).std())
    # invariant: a train-fitted standardizer centers the TRAIN slice at mean~0.
    # Key on the MEAN offset (robust to ddof=0/1 std conventions); std is corroboration.
    if abs(m) <= 5e-2:
        return ContractResult(name, False, f"train slice mean={m:.3f} (~0), std={s:.3f}: fit on train, no leakage")
    return ContractResult(name, True, f"train slice mean={m:.3f} != 0 (std={s:.3f}): scaled with GLOBAL stats (test leaked into fit)")


# D2-4  numpy broadcasting: (n,) op (n,1) silently expands to (n,n)
def _fx_broadcast():
    a = np.array([1.0, 2.0, 3.0, 4.0])          # (4,)
    b = np.array([[10.0], [20.0], [30.0], [40.0]])  # (4,1), e.g. from df[["b"]].values
    return {"df": {"a": a, "b": b}}


def _wrong_broadcast(fx):
    a, b = fx["df"]["a"], fx["df"]["b"]
    return a - b   # (4,4) broadcast


def _correct_broadcast(fx):
    a, b = fx["df"]["a"], fx["df"]["b"]
    return a - b.ravel()  # (4,)


def _c_broadcast(inp, params, result) -> ContractResult:
    name = "numpy_broadcast"
    n = int(params["n"])
    arr = np.asarray(result)
    if arr.size == n and arr.ndim == 1:
        return ContractResult(name, False, f"result is length-{n} vector as intended")
    return ContractResult(name, True, f"result shape {arr.shape} (size {arr.size}) != length-{n}: silent broadcast")


# D2-5  geospatial: lat/lon swapped (lat out of [-90,90])
def _fx_latlon():
    return {"df": pd.DataFrame({"lat": [35.7, 40.7, -33.9], "lon": [139.7, -74.0, 151.2]})}  # Tokyo/NY/Sydney


def _wrong_latlon(fx):
    df = fx["df"]
    return pd.DataFrame({"lat": df["lon"].to_numpy(), "lon": df["lat"].to_numpy()})  # swapped


def _correct_latlon(fx):
    return fx["df"].copy()


def _c_latlon(inp, params, result) -> ContractResult:
    name = "latlon_swap"
    latc = params["lat"]
    if result is None or latc not in result.columns:
        return ContractResult(name, True, f"missing {latc}")
    lat = _num(result[latc])
    bad = lat[np.abs(lat) > 90.0]
    if bad.size:
        return ContractResult(name, True, f"latitude out of [-90,90]: {bad[:3].tolist()} (lat/lon swapped)")
    return ContractResult(name, False, "latitude within [-90,90]")


# D2-6  time-series look-ahead: return computed from FUTURE price
def _fx_lookahead():
    return {"df": pd.DataFrame({"day": [1, 2, 3, 4, 5], "price": [100.0, 110.0, 115.0, 100.0, 130.0]})}


def _wrong_lookahead(fx):
    p = fx["df"]["price"]
    return fx["df"].assign(ret=(p.shift(-1) - p) / p)  # forward-looking


def _correct_lookahead(fx):
    p = fx["df"]["price"]
    return fx["df"].assign(ret=(p - p.shift(1)) / p.shift(1))  # past-only


def _c_lookahead(inp, params, result) -> ContractResult:
    name = "lookahead_return"
    df = inp["df"]; pcol, out = params["price"], params["out"]
    if result is None or out not in result.columns:
        return ContractResult(name, True, f"missing {out}")
    p = _num(df[pcol])
    past = np.full(len(p), np.nan); past[1:] = (p[1:] - p[:-1]) / p[:-1]
    fwd = np.full(len(p), np.nan); fwd[:-1] = (p[1:] - p[:-1]) / p[:-1]
    got = _num(result[out])

    def _match(ref):
        m = ~np.isnan(ref) & ~np.isnan(got)
        return m.sum() >= max(2, (~np.isnan(ref)).sum() - 1) and np.allclose(got[m], ref[m], atol=1e-6)

    if _match(past):
        return ContractResult(name, False, "return uses PAST price (no look-ahead)")
    if _match(fwd):
        return ContractResult(name, True, "return uses FUTURE price (look-ahead leakage)")
    return ContractResult(name, True, "return series does not match past-only definition")


# --------------------------------------------------------------------------- #
# alternative VALID implementations (FP-robustness: contract must NOT fire on these)
# --------------------------------------------------------------------------- #
def _alt_index_align(fx):
    base, adj = fx["df"], fx["df2"]
    s = base.set_index("id")["v"].add(adj.set_index("id")["w"], fill_value=0.0)
    return base.assign(total=base["id"].map(s))[["id", "v", "total"]]


def _alt_dtype_coerce(fx):
    df = fx["df"]
    return df.assign(zkey=df["zip"].astype(str).str.zfill(5))  # still string, preserved


def _alt_groupby_dropna(fx):
    d = fx["df"].copy(); d["g"] = d["g"].fillna("Unknown")
    return d.groupby("g")["v"].sum().reset_index()


def _alt_order_dedup(fx):
    d = fx["df"]
    return d.loc[d.groupby("id")["ts"].idxmax()].reset_index(drop=True)


def _alt_resample(fx):
    return (fx["df"].groupby(pd.Grouper(key="t", freq="1h", closed="right", label="right"))
            .sum(numeric_only=True).reset_index())


def _alt_str_norm(fx):
    R = fx["df2"]; m = {str(k).strip().lower(): v for k, v in zip(R["name"], R["price"])}
    L = fx["df"]
    return L.assign(price=[m.get(str(k).strip().lower(), np.nan) for k in L["name"]])


def _alt_join_fanout(fx):
    t = fx["df2"].drop_duplicates("cat")[["cat"]]
    return fx["df"].merge(t, on="cat").groupby("cat")["amt"].sum().reset_index()


def _alt_null_count(fx):
    return fx["df"].groupby("g").agg(n=("resp", "size")).reset_index()


def _alt_leakage(fx):
    df = fx["df"].copy(); tr = df["split"].eq("train")
    mu, sd = df.loc[tr, "x"].mean(), df.loc[tr, "x"].std(ddof=1)  # SAMPLE std (different convention)
    df["xs"] = (df["x"] - mu) / sd
    return df


def _alt_broadcast(fx):
    a, b = fx["df"]["a"], fx["df"]["b"]
    return np.subtract(a, b.reshape(-1))


def _alt_latlon(fx):
    return fx["df"].assign(_ok=1).drop(columns="_ok")  # identity (values unchanged)


def _alt_lookahead(fx):
    return fx["df"].assign(ret=fx["df"]["price"].pct_change(fill_method=None))


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
CANDIDATES: List[Candidate] = [
    Candidate("D1-1", "D1-framework", "index_align",
              "mis-paired/NaN values are plausible numbers; code runs clean",
              "not a statistic choice — pandas aligns by index/position, not by key",
              _fx_index_align, {"key": "id", "value": "v", "addend": "w"},
              _wrong_index_align, _correct_index_align, _c_index_align,
              "none (exec-pass + range both miss)",
              "undetectable only if result drops the key AND the value multiset coincides",
              alt_correct_fns=[_alt_index_align]),
    Candidate("D1-2", "D1-framework", "dtype_coerce",
              "1001 is a valid-looking number; no error on astype(int)",
              "a framework cast, not a math error; classic leading-zero ID loss",
              _fx_dtype_coerce, {"id_col": "zip", "out": "zkey"},
              _wrong_dtype_coerce, _correct_dtype_coerce, _c_dtype_coerce,
              "weak: a dtype-aware validity check could notice the type change",
              "only matters for codes with leading zeros / >15-digit precision",
              alt_correct_fns=[_alt_dtype_coerce]),
    Candidate("D1-3", "D1-framework", "groupby_dropna_key",
              "fewer-but-plausible group totals; no error",
              "groupby silently drops NaN KEYS by default (dropna=True)",
              _fx_groupby_dropna, {"group": "g", "value": "v"},
              _wrong_groupby_dropna, _correct_groupby_dropna, _c_groupby_dropna,
              "none (totals look fine in isolation)",
              "no firing if the key column has no NaN",
              alt_correct_fns=[_alt_groupby_dropna]),
    Candidate("D1-4", "D1-framework", "order_dependent_dedup",
              "one row per id is returned; values are real rows",
              "drop_duplicates keeps FIRST on UNSORTED data, not the intended latest/max",
              _fx_order_dedup, {"key": "id", "order": "ts"},
              _wrong_order_dedup, _correct_order_dedup, _c_order_dedup,
              "none",
              "needs an explicit 'which row' intent (latest/max) to define correctness",
              alt_correct_fns=[_alt_order_dedup]),
    Candidate("D1-5", "D1-framework", "resample_boundary",
              "totals conserve; a normal hourly table is returned",
              "default closed='left'/label='left' silently moves boundary points to the wrong bin",
              _fx_resample, {"time": "t", "value": "v", "closed": "right", "label": "right"},
              _wrong_resample, _correct_resample, _c_resample,
              "none (sum conservation holds for both — only per-bin differs)",
              "requires intent to pin closed/label; pure conservation cannot distinguish",
              alt_correct_fns=[_alt_resample]),
    Candidate("D1-6", "D1-framework", "string_normalize_join",
              "a left join returns all rows; missing prices are just NaN",
              "case/whitespace mismatch silently fails the match, not a logic error",
              _fx_str_norm, {"key": "name", "lookup_value": "price"},
              _wrong_str_norm, _correct_str_norm, _c_str_norm,
              "none (NaN lookups look like genuine misses)",
              "cannot tell intended-miss from normalization-miss without a normalization rule",
              alt_correct_fns=[_alt_str_norm]),
    Candidate("D2-1", "D2-cross-domain", "join_fanout",
              "a clean per-cat total; just numerically inflated",
              "many-to-many join duplicates rows (SQL fan-out), the #1 silent SQL bug",
              _fx_join_fanout, {"measure": "amt", "group": "cat"},
              _wrong_join_fanout, _correct_join_fanout, _c_join_fanout,
              "none",
              "only additive left-measures; counts/ratios need a different invariant",
              alt_correct_fns=[_alt_join_fanout]),
    Candidate("D2-2", "D2-cross-domain", "null_in_agg_count",
              "smaller counts that look like real group sizes",
              "COUNT(col) vs COUNT(*) NULL semantics (pandas .count skips NaN)",
              _fx_null_count, {"group": "g", "out": "n"},
              _wrong_null_count, _correct_null_count, _c_null_count,
              "none",
              "no firing if the counted column has no NULLs",
              alt_correct_fns=[_alt_null_count]),
    Candidate("D2-3", "D2-cross-domain", "scale_before_split_leakage",
              "model trains/scores fine; ONLY the held-out score is silently optimistic",
              "test stats leak into the scaler — invalidates the whole evaluation, not one cell",
              _fx_leakage, {"split": "split", "train_label": "train", "scaled": "xs"},
              _wrong_leakage, _correct_leakage, _c_leakage,
              "none (exec-pass + range both miss; this is the highest-impact case)",
              "only OBSERVABLE when train/test distributions differ — but that is exactly when it biases results",
              alt_correct_fns=[_alt_leakage]),
    Candidate("D2-4", "D2-cross-domain", "numpy_broadcast",
              "downstream .mean() of the (n,n) array is a plausible scalar",
              "silent broadcasting of (n,) vs (n,1), not an algorithm error",
              _fx_broadcast, {"n": 4},
              _wrong_broadcast, _correct_broadcast, _c_broadcast,
              "shape validity could catch it BEFORE it is aggregated to a scalar",
              "once reduced to a scalar the shape evidence is gone; catch it at the array step",
              alt_correct_fns=[_alt_broadcast]),
    Candidate("D2-5", "D2-cross-domain", "latlon_swap",
              "points still plot; just in the wrong place",
              "lat/lon order convention differs across libraries",
              _fx_latlon, {"lat": "lat", "lon": "lon"},
              _wrong_latlon, _correct_latlon, _c_latlon,
              "YES: a generic [-90,90] range check also catches it (lower novelty)",
              "undetectable when all true longitudes also fall within [-90,90]",
              alt_correct_fns=[_alt_latlon]),
    Candidate("D2-6", "D2-cross-domain", "lookahead_return",
              "a normal-looking return column; backtests just look too good",
              "uses FUTURE data (look-ahead bias) — silent and devastating in finance/forecasting",
              _fx_lookahead, {"price": "price", "out": "ret"},
              _wrong_lookahead, _correct_lookahead, _c_lookahead,
              "none",
              "constant-growth series make past==future returns; needs varying returns to expose",
              alt_correct_fns=[_alt_lookahead]),
]


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
def _run_one(c: Candidate) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "cid": c.cid, "direction": c.direction, "operator": c.operator,
        "why_silent": c.why_silent, "why_nonobvious": c.why_nonobvious,
        "generic_catch": c.generic_catch, "boundary": c.boundary,
    }
    try:
        fx = c.fixture()
    except Exception as e:  # pragma: no cover
        rec.update(verdict="ERROR", error=f"fixture: {e}")
        return rec

    # (a) wrong runs without raising (silent)
    try:
        wrong = c.wrong_fn(fx)
        rec["silent_runs"] = True
    except Exception as e:
        rec.update(silent_runs=False, verdict="NOT-SILENT",
                   error=f"wrong_fn raised (loud, not silent): {e}")
        return rec

    try:
        correct = c.correct_fn(fx)
    except Exception as e:  # pragma: no cover
        rec.update(verdict="ERROR", error=f"correct_fn: {e}")
        return rec

    # (b) contract fires on wrong ; (c) contract passes on correct
    try:
        rw = c.contract(fx, c.params, wrong)
        rc = c.contract(fx, c.params, correct)
    except Exception as e:  # pragma: no cover
        rec.update(verdict="ERROR", error=f"contract raised: {e}\n{traceback.format_exc()}")
        return rec

    rec["fires_on_wrong"] = bool(rw.fired)
    rec["passes_on_correct"] = (not rc.fired)
    rec["wrong_detail"] = rw.detail
    rec["correct_detail"] = rc.detail

    # FP-robustness: contract must NOT fire on any ALTERNATIVE valid implementation
    fp_hits: List[str] = []
    for i, alt in enumerate(c.alt_correct_fns):
        try:
            ra = c.contract(fx, c.params, alt(fx))
            if ra.fired:
                fp_hits.append(f"alt#{i}: {ra.detail}")
        except Exception as e:  # pragma: no cover
            fp_hits.append(f"alt#{i} raised: {e}")
    rec["n_alt_correct"] = len(c.alt_correct_fns)
    rec["fp_robust"] = (len(fp_hits) == 0)
    if fp_hits:
        rec["fp_hits"] = fp_hits

    if rw.fired and not rc.fired and not fp_hits:
        rec["verdict"] = "VIABLE"
    elif rw.fired and not rc.fired and fp_hits:
        rec["verdict"] = "VIABLE-FRAGILE"   # detects, but false-positives on a valid variant
    elif rw.fired and rc.fired:
        rec["verdict"] = "FALSE-POSITIVE"    # fires on correct too -> contract too loose
    elif (not rw.fired):
        rec["verdict"] = "MISS"              # cannot detect the silent error -> not viable
    else:
        rec["verdict"] = "UNCLEAR"
    return rec


def main() -> int:
    results = [_run_one(c) for c in CANDIDATES]
    out_dir = Path(__file__).resolve().parent / "results_expansion"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "expansion_records.json").write_text(json.dumps(results, indent=2, default=str))

    viable = [r for r in results if r.get("verdict") == "VIABLE"]
    fragile = [r for r in results if r.get("verdict") == "VIABLE-FRAGILE"]
    hi_nov = [r for r in viable if r["generic_catch"].startswith("none")]

    lines: List[str] = []
    lines.append("# Operator-taxonomy expansion — feasibility probe\n")
    lines.append(f"Probed {len(results)} candidate operators (goldless-contract method-viability, "
                 f"offline, no LLM). VIABLE = silent wrong runs + contract fires on wrong + "
                 f"passes on correct + 0 false-positives across alternative valid implementations.\n")
    lines.append(f"- VIABLE (detects + FP-robust across {sum(r.get('n_alt_correct',0) for r in results)} alt impls): {len(viable)}/{len(results)}")
    lines.append(f"- VIABLE-FRAGILE (detects but false-positives on a valid variant): {len(fragile)}/{len(results)}")
    lines.append(f"- of the VIABLE, HIGH-NOVELTY (generic exec-pass/validity baselines miss it): "
                 f"{len(hi_nov)}/{len(viable)}\n")
    lines.append("| id | dir | operator | silent? | fires✗ | pass✓ | FP-robust | verdict | generic baseline | non-obvious source |")
    lines.append("|----|-----|----------|---------|--------|-------|-----------|---------|------------------|--------------------|")
    for r in results:
        lines.append("| {cid} | {d} | {op} | {s} | {fw} | {pc} | {fp} | **{v}** | {g} | {nob} |".format(
            cid=r["cid"], d=r["direction"].split("-")[0], op=r["operator"],
            s="✓" if r.get("silent_runs") else "✗",
            fw="✓" if r.get("fires_on_wrong") else "✗",
            pc="✓" if r.get("passes_on_correct") else "✗",
            fp="✓ {}/{}".format(r.get("n_alt_correct", 0), r.get("n_alt_correct", 0)) if r.get("fp_robust") else "✗",
            v=r.get("verdict", "?"), g=r["generic_catch"],
            nob=r["why_nonobvious"]))
    lines.append("\n## Per-operator evidence (wrong vs correct, as the goldless contract sees it)\n")
    for r in results:
        lines.append(f"### {r['cid']} {r['operator']} — {r.get('verdict','?')}")
        lines.append(f"- why silent: {r['why_silent']}")
        lines.append(f"- fire on WRONG: {r.get('wrong_detail','-')}")
        lines.append(f"- pass on CORRECT: {r.get('correct_detail','-')}")
        if r.get("boundary"):
            lines.append(f"- honest boundary: {r['boundary']}")
        if r.get("error"):
            lines.append(f"- error: {r['error']}")
        lines.append("")
    report = "\n".join(lines)
    (out_dir / "expansion_report.md").write_text(report)
    print(report)
    print(f"\n[written] {out_dir/'expansion_report.md'}\n[written] {out_dir/'expansion_records.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
