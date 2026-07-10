"""
transform_intent_infer.py — close the W3 deployment gap: who gives the oracle its
`params`? Until now the contracts assumed (operator, params) are known. This module
INFERS (op, params) from ONLY the natural-language prompt + the dataframe schema —
no gold output, no executed result, no LLM. It makes the end-to-end claim honest:
NL intent -> inferred operator+params -> goldless oracle, recall ~= class-acc x oracle.

Deterministic and dependency-free: keyword/regex over the prompt, column-role
inference from dtypes (numeric vs categorical) + name hints. The point is not a
perfect NLU; it is to QUANTIFY how much the goldless oracle still catches when
params are not handed in. Where intent is unrecognisable -> ABSTAIN (op=None).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# operator -> ordered (regex) signals on the lowercased prompt. First strong hit wins.
_OP_SIGNALS: List[Tuple[str, List[str]]] = [
    ("pct_point", [r"percentage point", r"\bpp\b", r"change in rate", r"change from .* to "]),
    ("pooled_rate", [r"click-through", r"\bctr\b", r"pooled", r"total .*/ ?total", r"rate per"]),
    ("weighted_mean", [r"weighted average", r"weight(ed)? .* by", r"average .* by qty", r"average (price|value)"]),
    ("within_group_share", [r"share of", r"share .* total", r"each .* share"]),
    ("dedup_then_agg", [r"order_id", r"each .* only once", r"dedup", r"duplicat", r"line-items"]),
    ("nan_as_zero_sum", [r"missing .* as 0", r"treat .* missing", r"fill.*0", r"na as zero"]),
    ("left_join_keep_all", [r"attach .* from df2", r"left join", r"keep(ing)? all rows", r"\bmerge\b", r"\bjoin\b"]),
    ("median_not_mean", [r"\bmedian\b", r"typical value"]),
    ("cumulative_running", [r"running .* sum", r"cumulative", r"\bbalance\b", r"running total"]),
    ("cumcount_per_group", [r"running count", r"occurrence", r"count .* resets", r"per user"]),
    ("topn_with_ties", [r"top \d+", r"keep(ing)? all ties", r"\bties\b"]),
    ("count_includes_empty", [r"including .* zero", r"per category", r"number of rows per"]),
    ("proportion_true", [r"fraction .* true", r"pass[_ ]?rate", r"proportion"]),
    ("zscore_within_group", [r"z-score", r"zscore", r"within each .* mean"]),
    ("dense_rank", [r"dense", r"rank.*highest", r"no gaps"]),
    ("rank_pct", [r"percentile", r"rank\(pct", r"\[0, ?1\] rank"]),
    ("clip_outlier", [r"\bclip\b", r"limit .* range", r"cap values", r"range \d+ to \d+"]),
]


def infer_op(prompt: str) -> Optional[str]:
    p = prompt.lower()
    for op, sigs in _OP_SIGNALS:
        for s in sigs:
            if re.search(s, p):
                return op
    return None


def _cols_by_role(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    num, cat, boolean = [], [], []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            boolean.append(c)
        elif pd.api.types.is_numeric_dtype(s):
            num.append(c)
        else:
            cat.append(c)
    return num, cat, boolean


def _out_name(prompt: str) -> Optional[str]:
    m = re.search(r"column '([^']+)'", prompt) or re.search(r"add '([^']+)'", prompt.lower())
    return m.group(1) if m else None


def infer_params(op: str, df: pd.DataFrame, df2: Optional[pd.DataFrame], prompt: str) -> Dict[str, Any]:
    num, cat, boolean = _cols_by_role(df)
    out = _out_name(prompt)
    g = cat[0] if cat else (df.columns[0] if len(df.columns) else None)   # group = first categorical
    v = num[-1] if num else None                                          # value = a numeric col
    P: Dict[str, Any] = {}
    if op == "weighted_mean":
        P = {"value": num[0] if num else v, "weight": num[1] if len(num) > 1 else v}
    elif op == "within_group_share":
        P = {"group": g, "share_col": out or "share"}
    elif op == "pct_point":
        P = {"new": num[1] if len(num) > 1 else v, "old": num[0] if num else v, "out": out or "pp"}
    elif op == "dedup_then_agg":
        key = next((c for c in df.columns if "id" in c.lower()), num[0] if num else None)
        P = {"key": key, "value": v, "group": g}
    elif op == "left_join_keep_all":
        P = {}
    elif op == "pooled_rate":
        P = {"group": g, "num": num[0] if num else None, "den": num[1] if len(num) > 1 else None, "out": out or "ctr"}
    elif op in ("median_not_mean", "nan_as_zero_sum"):
        P = {"group": g, "value": v}
    elif op == "cumulative_running":
        P = {"value": v, "out": out or "balance"}
    elif op == "cumcount_per_group":
        P = {"group": g, "out": out or "occurrence"}
    elif op == "topn_with_ties":
        m = re.search(r"top (\d+)", prompt.lower())
        P = {"value": v, "n": int(m.group(1)) if m else 2}
    elif op == "count_includes_empty":
        P = {"category": g}
    elif op == "proportion_true":
        P = {"group": g, "flag": boolean[0] if boolean else cat[-1], "out": out or "pass_rate"}
    elif op == "zscore_within_group":
        P = {"group": g, "value": v, "out": out or "z"}
    elif op in ("dense_rank", "rank_pct"):
        P = {"value": v, "out": out or ("rank" if op == "dense_rank" else "pct")}
    elif op == "clip_outlier":
        nums = re.findall(r"-?\d+\.?\d*", prompt)
        lo, hi = (float(nums[0]), float(nums[1])) if len(nums) >= 2 else (0.0, 100.0)
        P = {"value": v, "lo": lo, "hi": hi, "out": v}
    return {k: x for k, x in P.items() if x is not None}


def infer_op_schema(prompt: str, df: pd.DataFrame) -> Optional[str]:
    """Schema-aware disambiguation for terse prompts where keywords are absent
    (e.g. 'Total per group' could be dedup vs nan-sum vs median). Uses dtypes +
    column-name hints + requested output name. Falls back to keyword infer_op."""
    op = infer_op(prompt)
    if op is not None:
        return op
    p = prompt.lower(); out = (_out_name(prompt) or "").lower()
    if out in ("pct",) and df.select_dtypes("number").shape[1]:
        return "rank_pct"
    if any("id" in c.lower() for c in df.columns) and ("total" in p or "sum" in p):
        return "dedup_then_agg"
    if df.isna().any().any() and ("total" in p or "sum" in p):
        return "nan_as_zero_sum"
    return None


def infer(prompt: str, df: pd.DataFrame, df2: Optional[pd.DataFrame] = None) -> Tuple[Optional[str], Dict[str, Any]]:
    op = infer_op_schema(prompt, df)
    if op is None:
        return None, {}
    return op, infer_params(op, df, df2, prompt)
