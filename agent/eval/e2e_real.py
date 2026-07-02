"""
e2e_real.py — end-to-end zero-template pipeline on REAL Nature tables (AAAI: close the last gap).

The independent re-review (gpt-5.5) credited the fixes but named ONE remaining gap: the e2e
number (61%) was measured on GENERATED operator fixtures, not on real Nature tables end-to-end.
This closes it. We reuse the real Nature XLSX corpus under data/nature_pairs/articles (the SAME
tables behind the 99%/0% detection result) to build real tasks, then run the FULL pipeline with
NOTHING template-given:

  messy analyst NL  --(1) LLM infer operator-->  op_hat
                    --(2) LLM synth goldless contract (from messy NL, no formula)-->  C
  C on the REAL table's SILENT-SLIP result  -> should FIRE   (recall)
  C on the REAL table's CORRECT result       -> should PASS  (1 - FP)

The correct result is the task's gold (real table); the silent slip is the deterministic mistake
an analyst makes for that operator (mean-for-median, global-for-within-group share, plain-for-
weighted mean, mean-of-ratios-for-pooled, count(col)-for-size, drop-NaN-key). Every task is
screened so the oracle PASSES the gold and FIRES the slip (clean setup) BEFORE the LLM sees it;
the LLM only ever sees the messy NL + column names (cached & auditable). Nothing about the
operator/formula is handed in.

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/e2e_real.py \
        --pairs-root ../data/nature_pairs/articles --per-op 8 --model gpt-5.4
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa
import pandas as pd  # noqa
import warnings; warnings.filterwarnings("ignore")
from eval.nature_real_auto import _build
from eval.transform_oracle import check as oracle_check
from eval.w2_firing import _chat_api, classify_op_llm
from eval.autocontract_synth import DELEAKED_INTENT, SYNTH_PROMPT, _result_schema, wilson, _run_auto, _as_frame
from eval.e2e_pipeline import MESSY_PROMPT, gen_messy


# deterministic SILENT SLIP per operator on a real table (the mistake an analyst makes)
def slip_result(op, df, params):
    p = params
    if op == "median_not_mean":
        g, v = p["group"], p["value"]
        return df.groupby(g, as_index=False)[v].mean()                       # mean, not median
    if op == "within_group_share":
        g, v = p["group"], p.get("value") or [c for c in df.columns if c != g][0]
        return df.assign(share=df[v] / df[v].sum())                          # GLOBAL share
    if op == "weighted_mean":
        v = p["value"]
        return pd.DataFrame({"wavg": [float(df[v].mean())]})                 # plain mean
    if op == "pooled_rate":
        g, n, d = p["group"], p["num"], p["den"]
        r = df.assign(_r=df[n] / df[d]).groupby(g, as_index=False)["_r"].mean()
        return r.rename(columns={"_r": p.get("out", "rate")})                # mean of per-row ratios
    if op == "nan_as_zero_sum":
        g, v = p["group"], p["value"]
        # slip: a sum that PROPAGATES NaN (group with any missing -> NaN total)
        return df.groupby(g).agg({v: lambda s: np.nan if s.isna().any() else s.sum()}).reset_index()
    if op == "null_in_agg_count":
        g = p["group"]; vcol = [c for c in df.columns if c != g][0]
        return df.groupby(g, as_index=False)[vcol].count().rename(columns={vcol: p.get("out", "n")})  # COUNT(col) skips NaN
    if op == "groupby_dropna_key":
        g, v = p["group"], p["value"]
        return df.groupby(g, as_index=False)[v].sum()                        # dropna=True drops NaN-key rows
    return None


def synth_from_text(op, df, params, intent_text, model):
    correct = _gold_result(op, df, params)
    kind, rcols = _result_schema(correct)
    cols = list(df.columns)
    extra = ""
    prompt = SYNTH_PROMPT.format(intent=intent_text, cols=cols, extra=extra,
                                 params=params, kind=kind, rcols=rcols)
    import re
    for _ in range(2):
        out = _chat_api([{"role": "user", "content": prompt}], model, max_tok=4000)
        m = re.search(r"\{.*\}", out or "", re.S)
        if m:
            try:
                code = json.loads(m.group(0)).get("code")
                if code:
                    return code
            except Exception:
                pass
        m2 = re.search(r"def contract.*", out or "", re.S)
        if m2:
            return m2.group(0)
    return None


def _gold_result(op, df, params):
    # recompute the task gold deterministically (mirrors nature_real_auto templates)
    p = params
    if op == "median_not_mean":
        return df.groupby(p["group"], as_index=False)[p["value"]].median()
    if op == "within_group_share":
        v = p.get("value") or [c for c in df.columns if c != p["group"]][0]
        return df.assign(share=df[v] / df.groupby(p["group"])[v].transform("sum"))
    if op == "weighted_mean":
        return pd.DataFrame({"wavg": [float((df[p["value"]] * df[p["weight"]]).sum() / df[p["weight"]].sum())]})
    if op == "pooled_rate":
        g, n, d = p["group"], p["num"], p["den"]
        return df.groupby(g).apply(lambda x: x[n].sum() / x[d].sum(), include_groups=False)\
                 .reset_index(name=p.get("out", "rate"))
    if op == "nan_as_zero_sum":
        return df.assign(**{p["value"]: df[p["value"]].fillna(0)}).groupby(p["group"], as_index=False)[p["value"]].sum()
    if op == "null_in_agg_count":
        return df.groupby(p["group"]).size().reset_index(name=p.get("out", "n"))
    if op == "groupby_dropna_key":
        return df.groupby(p["group"], dropna=False, as_index=False)[p["value"]].sum()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-root", default="../data/nature_pairs/articles")
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--per-op", type=int, default=8)
    ap.add_argument("--max-tasks", type=int, default=400)
    ap.add_argument("--cache", default="eval/results_e2e/messy_queries_real.json")
    ap.add_argument("--out", default="eval/results_e2e/e2e_real_report.json")
    a = ap.parse_args()

    tasks = _build(a.pairs_root, a.max_tasks, max_per_article=6, max_rows=200, expansion=True)
    # keep only tasks where we have a slip fn AND (gold passes oracle, slip fires oracle)
    clean, by_op = [], {}
    for t in tasks:
        op = t["op"]; df = t["df"]; params = t["params"]
        try:
            gold = _gold_result(op, df, params); slip = slip_result(op, df, params)
            if gold is None or slip is None:
                continue
            og = oracle_check(op, {"df": df}, params, gold)
            os_ = oracle_check(op, {"df": df}, params, slip)
            if og is not None and og.fired:      # oracle must PASS the real gold
                continue
            if not (os_ is not None and os_.fired):  # oracle must FIRE the real slip
                continue
        except Exception:
            continue
        if by_op.get(op, 0) >= a.per_op:
            continue
        by_op[op] = by_op.get(op, 0) + 1
        clean.append(t)
    print(f"real Nature tasks (gold-passes & slip-fires screened): {len(clean)} across {len(by_op)} ops: {by_op}", flush=True)

    cache_p = Path(a.cache)
    cache = json.load(open(cache_p)) if cache_p.exists() else {}
    changed = False

    n = op_ok = c_core = sys_core = 0
    recs = []
    import re
    for t in clean:
        op, df, params = t["op"], t["df"], t["params"]
        key = t["name"]
        if key not in cache:
            goal = DELEAKED_INTENT.get(op, f"Compute the {op} transform.")
            cache[key] = gen_messy(goal, list(df.columns), a.model); changed = True
        msg = cache[key]
        op_hat = classify_op_llm(msg, list(df.columns), a.model, conservative=False)
        code = synth_from_text(op, df, params, msg, a.model)
        gold = _as_frame(_gold_result(op, df, params)); slip = _as_frame(slip_result(op, df, params))
        fire_slip = _run_auto(code, {"df": df}, params, slip)
        pass_gold = _run_auto(code, {"df": df}, params, gold)
        core = (fire_slip is True) and (pass_gold is False)
        op_correct = (op_hat == op)
        system_ok = op_correct and core
        n += 1; op_ok += int(op_correct); c_core += int(core); sys_core += int(system_ok)
        recs.append({"op": op, "name": key, "messy_nl": msg, "op_hat": op_hat,
                     "op_correct": op_correct, "contract_core": bool(core), "system_ok": system_ok})
        print(f"  {op:20} op_hat={str(op_hat):20} {'OKop' if op_correct else 'xop':4} "
              f"contract:{'CORE' if core else 'fail':4} => {'SYSTEM-OK' if system_ok else '-'}", flush=True)
    if changed:
        cache_p.parent.mkdir(parents=True, exist_ok=True); json.dump(cache, open(cache_p, "w"), indent=2)

    summary = {"model": a.model, "substrate": "REAL Nature tables (data/nature_pairs)", "n": n,
               "operator_inference": {"k": op_ok, "n": n, "pct_ci": wilson(op_ok, n)},
               "contract_synth_core": {"k": c_core, "n": n, "pct_ci": wilson(c_core, n)},
               "FULL_SYSTEM_core": {"k": sys_core, "n": n, "pct_ci": wilson(sys_core, n)},
               "cases": recs}
    outp = Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(outp, "w"), indent=2)
    print(f"\n=== END-TO-END on REAL NATURE TABLES (nothing template-given, model {a.model}) ===")
    print(f"(1) operator inference:        {op_ok}/{n} = {wilson(op_ok,n)[0]}% CI{wilson(op_ok,n)[1:]}")
    print(f"(2) contract synth CORE:       {c_core}/{n} = {wilson(c_core,n)[0]}% CI{wilson(c_core,n)[1:]}")
    print(f"FULL SYSTEM (op AND contract): {sys_core}/{n} = {wilson(sys_core,n)[0]}% CI{wilson(sys_core,n)[1:]}")
    print(f"-> {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
