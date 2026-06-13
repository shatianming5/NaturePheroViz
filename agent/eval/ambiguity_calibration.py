"""
ambiguity_calibration.py — P0-2: prove we measure MODEL semantic failure, not prompt underspecification.

Reviewer's decisive missing experiment. For each transform we author a matched
pair:
  - AMBIGUOUS prompt: the natural, underspecified way a user would ask
    (e.g. "the average price", "each region's share of sales").
  - CLARIFIED prompt: the same task with the intended semantics spelled out
    (e.g. "the QUANTITY-WEIGHTED average price", "share of ITS OWN region's total").

We then show three things (each is a separate claim a reviewer demanded):
  (1) silent-error rate drops sharply ambiguous -> clarified
      => the errors are real model semantic failures the clarification fixes,
         not unsolvable/ill-posed tasks.
  (2) the invariants oracle FIRES on the ambiguous-prompt failures
      => the verifier catches exactly the silent errors that occur.
  (3) the oracle does NOT over-flag the clarified controls when the model is right
      => low false-positive rate; we're not just flagging everything.

Goldless throughout: the oracle never sees a reference output (transform_oracle).
Requires LLM proxy env. Run:  cd agent && python eval/ambiguity_calibration.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402

MODELS = ["gpt-4o", "claude-sonnet-4.6"]


# Each item: op_type (-> oracle contract), input df(s), oracle params, a GOLD fn
# (used ONLY to label ground-truth correct/wrong for measuring rates — the oracle
# itself never sees it), and an (ambiguous, clarified) prompt pair.
def _items() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    df = pd.DataFrame({"product": ["a", "b", "c"], "price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})
    out.append({
        "name": "weighted_mean", "op": "weighted_mean", "df": df,
        "params": {"value": "price", "weight": "qty"},
        "gold": lambda d: (d["price"] * d["qty"]).sum() / d["qty"].sum(),
        "ambiguous": "Give the average price across products (one number, column 'wavg').",
        "clarified": "Give the QUANTITY-WEIGHTED average price (weight each product's price by qty; one number, column 'wavg').",
        "result_kind": "scalar",
    })

    df2 = pd.DataFrame({"region": ["N", "N", "S", "S"], "city": ["a", "b", "c", "d"], "sales": [30, 10, 20, 20]})
    out.append({
        "name": "within_group_share", "op": "within_group_share", "df": df2,
        "params": {"group": "region", "share_col": "share"},
        "gold": lambda d: d.assign(share=d["sales"] / d.groupby("region")["sales"].transform("sum")),
        "ambiguous": "Add a column 'share' = each city's share of sales. Keep region, city, sales, share.",
        "clarified": "Add a column 'share' = each city's sales divided by ITS OWN REGION's total sales (within-region share, NOT of the grand total). Keep region, city, sales, share.",
        "result_kind": "frame",
    })

    df3 = pd.DataFrame({"team": ["A", "B"], "rate_2023": [0.20, 0.50], "rate_2024": [0.30, 0.55]})
    out.append({
        "name": "pct_point", "op": "pct_point", "df": df3,
        "params": {"new": "rate_2024", "old": "rate_2023", "out": "pp"},
        "gold": lambda d: d.assign(pp=(d["rate_2024"] - d["rate_2023"]) * 100)[["team", "pp"]],
        "ambiguous": "Add column 'pp' = the change in rate from 2023 to 2024. Keep team, pp.",
        "clarified": "Add column 'pp' = the change in rate from 2023 to 2024 in PERCENTAGE POINTS (e.g. 0.20->0.30 is 10 points, i.e. (rate_2024-rate_2023)*100). Keep team, pp.",
        "result_kind": "frame",
    })

    df4 = pd.DataFrame({"region": ["N", "N", "N", "S"], "order_id": [1, 1, 2, 3], "rev": [50, 50, 30, 40]})
    out.append({
        "name": "dedup_then_agg", "op": "dedup_then_agg", "df": df4,
        "params": {"key": "order_id", "value": "rev", "group": "region"},
        "gold": lambda d: d.drop_duplicates("order_id").groupby("region", as_index=False)["rev"].sum(),
        "ambiguous": "Total revenue per region. Columns region, rev.",
        "clarified": "Total revenue per region, counting each order_id only ONCE (rows are duplicated line-items of the same order; de-duplicate by order_id before summing). Columns region, rev.",
        "result_kind": "frame",
    })

    L = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    R = pd.DataFrame({"id": [1, 3], "score": [88, 99]})
    out.append({
        "name": "left_join", "op": "left_join_keep_all", "df": L, "df2": R,
        "params": {},
        "gold": lambda d, d2: d.merge(d2, on="id", how="left"),
        "ambiguous": "Attach score from df2 to df on id.",
        "clarified": "Attach score from df2 to df on id, KEEPING ALL rows of df even when there's no matching score (missing score becomes NaN). Do a left join.",
        "result_kind": "frame",
    })

    df6 = pd.DataFrame({"region": ["N", "N", "S"], "clicks": [1, 99, 50], "imps": [10, 100, 100]})
    out.append({
        "name": "pooled_rate", "op": "pooled_rate", "df": df6,
        "params": {"group": "region", "num": "clicks", "den": "imps", "out": "ctr"},
        "gold": lambda d: d.groupby("region").apply(lambda g: g["clicks"].sum() / g["imps"].sum(), include_groups=False).reset_index(name="ctr"),
        "ambiguous": "Click-through rate (ctr) per region. Columns region, ctr.",
        "clarified": "Click-through rate per region = TOTAL clicks / TOTAL impressions in that region (pooled sum/sum, NOT the average of per-row ratios). Columns region, ctr.",
        "result_kind": "frame",
    })

    return out


def _gold_correct(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> bool:
    """Ground-truth correctness label (for measuring rates only; oracle never sees this)."""
    if result is None or not isinstance(result, pd.DataFrame) or result.empty:
        return False
    try:
        g = item["gold"](item["df"], item["df2"]) if "df2" in item else item["gold"](item["df"])
    except Exception:
        return False
    if item["result_kind"] == "scalar":
        gv = float(g) if np.isscalar(g) else float(pd.Series(g).iloc[0])
        # find the single numeric cell in result
        for c in result.columns:
            s = pd.to_numeric(result[c], errors="coerce")
            if s.notna().sum() == 1:
                return abs(float(s.dropna().iloc[0]) - gv) <= max(abs(gv) * 1e-4, 1e-6)
        return False
    gd = g if isinstance(g, pd.DataFrame) else g.to_frame()
    return _frame_equal(result, gd)


def _frame_equal(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """True if result `a` contains all of gold `b`'s columns with matching values.

    Subset match on columns: extra intermediate columns in `a` (e.g. a model that
    keeps a 'total_sales_region' helper alongside the required 'share') do NOT make
    the result wrong, as long as every gold column is present and its values match
    after row-alignment. Values must still match (a wrong value in a gold column is
    still wrong), so this only forgives harmless extra columns, not semantic errors."""
    try:
        a = a.copy(); a.columns = [str(c) for c in a.columns]
        b = b.copy(); b.columns = [str(c) for c in b.columns]
        if not set(b.columns).issubset(set(a.columns)):
            return False
        if len(a) != len(b):
            return False
        # restrict result to the gold columns, then compare as sets of rows
        a = a[list(b.columns)]

        def norm(d):
            d = d[sorted(d.columns)].copy()
            for c in d.columns:
                if pd.api.types.is_float_dtype(d[c]):
                    d[c] = d[c].round(6)
            return d.sort_values(list(d.columns)).reset_index(drop=True)
        na, nb = norm(a), norm(b)
        return na.equals(nb)
    except Exception:
        return False


def _llm_code(item: Dict[str, Any], prompt_text: str, model: str) -> Optional[str]:
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    cols = list(item["df"].columns)
    extra = f"\nA second dataframe `df2` columns={list(item['df2'].columns)}." if "df2" in item else ""
    prompt = f"""pandas `df` columns={cols}.{extra}
{prompt_text}
The dataframe(s) `df`{"/`df2`" if "df2" in item else ""} ALREADY EXIST in scope with the real data.
Do NOT re-create or re-assign them, do NOT import anything, do NOT print.
Use only the given `df`{"/`df2`" if "df2" in item else ""}, assign the final answer to `result`.
Return ONLY strict JSON: {{"code": "<pandas code defining result>"}}."""
    try:
        # GPT-5 / o-series reasoning models reject `max_tokens` and `temperature`;
        # they use `max_completion_tokens` and a fixed temperature. Branch on name.
        ml = model.lower()
        reasoning = ml.startswith(("gpt-5", "o1", "o3", "o4")) or "codex" in ml
        payload: Dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if reasoning:
            payload["max_completion_tokens"] = 8000  # reasoning eats tokens before the answer
        else:
            payload["temperature"] = 0.0
            payload["max_tokens"] = 4000
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json=payload, timeout=(10, 180))
        r.raise_for_status()
        choices = r.json().get("choices") or []
        if not choices:
            return None
        c = choices[0]["message"]["content"]
        m = re.search(r"\{.*\}", c, re.S)
        return json.loads(m.group(0) if m else c).get("code")
    except Exception:
        return None


def _sanitize_code(code: str) -> str:
    """Strip markdown fences and drop lines that re-create df/df2 or import — the
    real frames are pre-injected, so a model that hallucinates `df = pd.DataFrame(...)`
    must NOT clobber them (that would measure the model on fake data)."""
    code = re.sub(r"^```[a-zA-Z]*\n?|```$", "", code.strip(), flags=re.M)
    kept = []
    for ln in code.splitlines():
        s = ln.strip()
        if re.match(r"^(import|from)\s", s):
            continue
        if re.match(r"^df2?\s*=", s):  # re-assigns df / df2 at statement start
            continue
        kept.append(ln)
    return "\n".join(kept)


def _exec(item: Dict[str, Any], code: str) -> Optional[pd.DataFrame]:
    ns: Dict[str, Any] = {"df": item["df"].copy(), "pd": pd, "np": np}
    if "df2" in item:
        ns["df2"] = item["df2"].copy()
    try:
        exec(_sanitize_code(code), ns)  # noqa: S102
        res = ns.get("result")
        if isinstance(res, pd.Series):
            res = res.to_frame()
        if isinstance(res, pd.DataFrame):
            return res
        # scalar result (e.g. a weighted mean) -> wrap into a 1-cell frame so the
        # oracle (_single_value) and _gold_correct (scalar branch) can read it.
        # Both scan for the single numeric cell, so the column name is irrelevant.
        if isinstance(res, (int, float, np.integer, np.floating)) and not isinstance(res, bool):
            return pd.DataFrame({"value": [float(res)]})
        return None
    except Exception:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Ambiguity-calibration: model failure vs prompt underspecification")
    ap.add_argument("--out", default="eval/results_ambcal")
    ap.add_argument("--bench", action="store_true",
                    help="use the systematic 48-case transform_bench grid (12 classes x4) instead of the built-in 6")
    ap.add_argument("--models", default=None,
                    help="comma-separated model list to override the default GPT-4o/Claude pair")
    args = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY."); return 1

    models = [m.strip() for m in args.models.split(",")] if args.models else MODELS
    print(f"[models] {models}")

    if args.bench:
        from collections import Counter
        from eval.transform_bench import _cases
        seen: Counter = Counter()
        items = []
        for c in _cases():
            seen[c["op"]] += 1
            items.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})
        print(f"[bench] {len(items)} systematic cases across {len(seen)} operator-semantic classes")
    else:
        items = _items()
    # counters
    silent = {cond: 0 for cond in ("ambiguous", "clarified")}   # exec ok but wrong (ground truth)
    total = {cond: 0 for cond in ("ambiguous", "clarified")}
    oracle_fire_on_wrong = 0; wrong_total = 0      # (2) recall: oracle fires on actual silent errors
    oracle_fire_on_right = 0; right_total = 0      # (3) false positives: oracle fires when model correct
    rows = []
    for item in items:
        rec = {"item": item["name"]}
        for cond in ("ambiguous", "clarified"):
            for m in models:
                code = _llm_code(item, item[cond], m)
                result = _exec(item, code) if code else None
                exec_ok = result is not None
                correct = exec_ok and _gold_correct(item, result)
                oc = oracle_check(item["op"], {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}, item["params"], result)
                fired = bool(oc and oc.fired)
                total[cond] += 1
                if exec_ok and not correct:
                    silent[cond] += 1
                # oracle quality (only when exec produced something to judge)
                if exec_ok:
                    if correct:
                        right_total += 1; oracle_fire_on_right += int(fired)
                    else:
                        wrong_total += 1; oracle_fire_on_wrong += int(fired)
                tag = "ok" if correct else ("SILENT" if exec_ok else "crash")
                print(f"[{item['name']:20}] {cond:10} {m:18} {tag:7} oracle_fired={fired}", flush=True)
                rec.setdefault(cond, {})[m] = {"tag": tag, "oracle_fired": fired}
        rows.append(rec)

    def rate(d, c): return f"{100*silent[c]/total[c]:.0f}%" if total[c] else "n/a"
    report = [
        "# Ambiguity Calibration: model failure vs prompt underspecification\n",
        "Matched (ambiguous, clarified) prompts per transform. Oracle = goldless invariants.\n",
        "## (1) Silent-error rate drops when intent is clarified",
        f"- ambiguous prompts: {silent['ambiguous']}/{total['ambiguous']} silent-wrong ({rate(None,'ambiguous')})",
        f"- clarified prompts: {silent['clarified']}/{total['clarified']} silent-wrong ({rate(None,'clarified')})",
        "- A sharp drop => the errors are genuine MODEL semantic failures (fixable by clarification),",
        "  not ill-posed tasks. (If clarified is still high, the task itself is the problem.)\n",
        "## (2) Oracle detection recall on actual silent errors",
        f"- oracle fired on {oracle_fire_on_wrong}/{wrong_total} truly-wrong results "
        f"({100*oracle_fire_on_wrong/wrong_total:.0f}%)" if wrong_total else "- (no wrong results to detect)",
        "\n## (3) Oracle false-positive rate on correct results",
        f"- oracle fired on {oracle_fire_on_right}/{right_total} truly-correct results "
        f"({100*oracle_fire_on_right/right_total:.0f}%) — lower is better" if right_total else "- (no correct results)",
        "\n## Reading",
        "- Claims for the paper: (1) clarification fixes most errors => real semantic failure;",
        "  (2) high oracle recall on the silent errors; (3) low oracle false-positive on correct outputs.",
    ]
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ambcal_report.md").write_text("\n".join(report), encoding="utf-8")
    (out_dir / "ambcal_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(report))
    print(f"\n[saved] {out_dir}/ambcal_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
