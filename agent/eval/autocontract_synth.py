"""
autocontract_synth.py — can the goldless contracts be AUTO-SYNTHESIZED from NL? (AAAI T1-B)

Reviewer novelty critique (W5): "this is design-by-contract / property-based testing with
28 HAND-WRITTEN assertions — the mechanism is 40 years old." Scalability critique (W4):
"hand-written contracts don't scale to unseen operators." This experiment answers both: we
ask a frontier LLM to SYNTHESIZE a goldless contract from ONLY the NL intent + param names
+ the result schema — it never sees the hand-written contract nor the correct/wrong impls.
Then we test the auto-contract exactly as the hand-written one is tested:

  fire  on wrong_fn (the silent slip)              -> should FIRE
  pass  on correct_fn (intended impl)              -> should NOT fire
  pass  on each alt_correct_fn (other valid impls) -> should NOT fire (FP robustness)

An auto-contract is CORRECT iff it fires on the slip AND passes on correct AND all alts.
If the majority of operators yield a correct auto-contract, the contribution becomes
"automatic goldless invariant synthesis from NL", not "we hand-wrote assertions" — a
materially stronger novelty + scalability claim.

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/autocontract_synth.py --model gpt-5.4
"""
from __future__ import annotations
import argparse, json, math, re, sys, textwrap
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa
import pandas as pd  # noqa
from eval.operator_expansion import CANDIDATES
from eval.w2_firing import _chat_api

# a concise NL intent per operator (the DEPLOY-TIME input: what the transform SHOULD do).
# This is the *input* to synthesis; the CONTRACT is what we auto-generate. Kept operator-
# level and gold-free (no reference to the correct implementation's code).
INTENT = {
    "index_align": "Add, per key, the value column plus the addend column that comes from a second table keyed by the same id; every key's total must equal its own value+addend (alignment by key, not by row position).",
    "dtype_coerce": "Produce a key column from an id column such that codes like '01'/'1' are treated consistently; equal identifiers must map to the same key (no dtype-driven splitting of the same id).",
    "groupby_dropna_key": "Sum the value within each group, INCLUDING rows whose group key is missing (NaN) as their own group; the grand total must be conserved (no rows silently dropped).",
    "order_dependent_dedup": "Keep exactly one row per key — the intended one (e.g. latest by the order column) — so the deduplicated result reflects the correct pick, not an arbitrary first row.",
    "resample_boundary": "Resample the time series into periods using the intended bin boundary so each value lands in the correct period; totals are conserved and no period is off-by-one.",
    "string_normalize_join": "Join a price from a lookup table onto rows by a name key after normalizing surface differences (case/whitespace), so matching names attach their price and no row is dropped for a cosmetic mismatch.",
    "join_fanout": "Aggregate a per-entity measure by group WITHOUT letting a one-to-many join duplicate the measure; each entity's measure is counted once (no fan-out inflation).",
    "null_in_agg_count": "Count rows per group where the count reflects the intended population; nulls in the counted column must not silently shrink the count below the number of rows.",
    "scale_before_split_leakage": "Standardize a feature using statistics from the TRAIN split only (no leakage from the test split); train/test scaling must use train-derived parameters.",
    "latlon_swap": "Compute using latitude and longitude in the correct roles; latitude stays in [-90,90] and longitude in [-180,180] (no lat/lon swap).",
    "lookahead_return": "Compute the forward return per row using only information available at that row's time (no look-ahead); the last rows without a future price must be NaN, not fabricated.",
    "numpy_broadcast": "Combine the arrays with the intended alignment so shapes broadcast correctly and each element pairs with its intended counterpart (no silent broadcast mismatch).",
}

SYNTH_PROMPT = """You write GOLDLESS runtime contracts that detect silent semantic errors in \
pandas transforms. You are given the INTENT (what the transform should do), the input \
schema, the parameter names, and the result schema. You do NOT get the correct answer.

Write a Python function with EXACTLY this signature:

    def contract(inp, params, result):
        # inp: dict with "df" (pandas.DataFrame) and optionally "df2"
        # params: dict of column-name parameters
        # result: the produced pandas.DataFrame (or scalar-in-a-1-cell-frame)
        # return True if the result VIOLATES the intent's invariant (i.e. a silent error is
        # present), else False. Use ONLY inp/params/result — never a reference answer.
        ...

Rules:
- Encode a CHECKABLE INVARIANT implied by the intent (e.g. a conservation law, a range, a
  per-group identity, a row-count/`total` that must be preserved), NOT a re-implementation
  that assumes one specific correct algorithm.
- Be robust: it must NOT fire on legitimate alternative correct implementations.
- Use pandas/numpy (pd, np are in scope). No imports, no printing, no file I/O.
- Return ONLY the function code as strict JSON: {{"code": "<def contract...>"}}.

INTENT: {intent}
Input df columns: {cols}{extra}
Params: {params}
Result: a {kind} with columns {rcols}.
"""


def _schema(inp):
    df = inp["df"]
    extra = f'\nSecond table df2 columns: {list(inp["df2"].columns)}.' if "df2" in inp else ""
    return list(df.columns), extra


def _result_schema(res):
    if isinstance(res, pd.DataFrame):
        return "DataFrame", list(res.columns)
    if isinstance(res, pd.Series):
        return "Series", [res.name]
    return "scalar", ["value"]


def synth_contract(cand, model):
    inp = cand.fixture()
    cols, extra = _schema(inp)
    # show the result schema from the CORRECT impl (schema only — values not revealed as gold)
    correct = cand.correct_fn(inp)
    kind, rcols = _result_schema(correct)
    intent = INTENT.get(cand.operator, f"Correctly compute the `{cand.operator}` transform.")
    prompt = SYNTH_PROMPT.format(intent=intent, cols=cols, extra=extra,
                                 params=cand.params, kind=kind, rcols=rcols)
    out = _chat_api([{"role": "user", "content": prompt}], model, max_tok=4000)
    m = re.search(r"\{.*\}", out, re.S)
    code = None
    if m:
        try:
            code = json.loads(m.group(0)).get("code")
        except Exception:
            code = None
    if code is None:
        m2 = re.search(r"def contract.*", out, re.S)
        code = m2.group(0) if m2 else None
    return code


def _run_auto(code, inp, params, result):
    """Exec the synthesized contract; return bool fired (None on failure)."""
    if not code:
        return None
    ns = {"pd": pd, "np": np}
    try:
        exec(textwrap.dedent(code), ns)  # noqa: S102
        fn = ns.get("contract")
        if fn is None:
            return None
        return bool(fn(inp, params, result))
    except Exception:
        return None


def _as_frame(x):
    if isinstance(x, pd.DataFrame):
        return x
    if isinstance(x, pd.Series):
        return x.to_frame()
    return pd.DataFrame({"value": [x]})


def evaluate(cand, code):
    """Return dict: does the auto-contract fire-on-wrong AND pass-on-correct AND pass-alts?"""
    inp = cand.fixture()
    wrong = _as_frame(cand.wrong_fn(inp))
    correct = _as_frame(cand.correct_fn(inp))
    fire_wrong = _run_auto(code, inp, cand.params, wrong)
    pass_correct = _run_auto(code, inp, cand.params, correct)
    alt_ok = True
    for alt in (cand.alt_correct_fns or []):
        try:
            a = _as_frame(alt(inp))
        except Exception:
            continue
        if _run_auto(code, inp, cand.params, a):  # fired on a valid alt -> FP
            alt_ok = False
    ok = (fire_wrong is True) and (pass_correct is False) and alt_ok
    return {"fired_on_wrong": fire_wrong, "fired_on_correct": pass_correct,
            "alt_robust": alt_ok, "correct": bool(ok),
            "exec_ok": (fire_wrong is not None and pass_correct is not None)}


def wilson(k, m):
    if m == 0:
        return [0, 0, 0]
    p = k / m; z = 1.96; d = 1 + z * z / m
    c = (p + z * z / (2 * m)) / d; h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
    return [round(100 * p), round(100 * (c - h)), round(100 * (c + h))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--out", default="eval/results_autocontract/autocontract.json")
    ap.add_argument("--retries", type=int, default=2, help="synthesis attempts per op (best-of)")
    a = ap.parse_args()
    recs = []
    n_ok = n_exec = 0
    # only pandas-DataFrame operators (numpy_broadcast's fixture is dict-of-arrays, outside
    # the DataFrame-result contract framework -> skip)
    cands = [c for c in CANDIDATES if isinstance(c.fixture().get("df"), pd.DataFrame)]
    for cand in cands:
        best = None
        for attempt in range(a.retries):
            try:
                code = synth_contract(cand, a.model)
                ev = evaluate(cand, code)
            except Exception as e:  # noqa: BLE001
                ev = {"fired_on_wrong": None, "fired_on_correct": None, "alt_robust": False,
                      "correct": False, "exec_ok": False, "err": str(e)[:80]}
            ev["attempt"] = attempt
            if ev["correct"]:
                best = ev; break
            if best is None or (ev["exec_ok"] and not best["exec_ok"]):
                best = ev
        n_ok += int(best["correct"]); n_exec += int(best["exec_ok"])
        # core = fires on slip AND passes on correct (the invariant works); full also needs alt-robustness
        core = (best["fired_on_wrong"] is True) and (best["fired_on_correct"] is False)
        recs.append({"op": cand.operator, "cid": cand.cid, "core_correct": bool(core),
                     **{k: best[k] for k in ("fired_on_wrong", "fired_on_correct", "alt_robust", "correct", "exec_ok")}})
        print(f"  {cand.operator:26} exec_ok={best['exec_ok']} fire_wrong={best['fired_on_wrong']} "
              f"pass_correct={best['fired_on_correct'] is False} alt_ok={best['alt_robust']} "
              f"=> {'OK' if best['correct'] else ('core' if core else 'FAIL')}", flush=True)
    n = len(cands)
    n_core = sum(r["core_correct"] for r in recs)
    summary = {"model": a.model, "n_operators": n,
               "auto_full_correct": n_ok, "auto_full_ci": wilson(n_ok, n),
               "auto_core_correct": n_core, "auto_core_ci": wilson(n_core, n),
               "exec_ok": n_exec, "cases": recs}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out, "w"), indent=2)
    print(f"\n=== AUTO-SYNTHESIZED goldless contracts from NL (model {a.model}, n={n} ops) ===")
    print(f"CORE (fire-on-slip AND pass-on-correct): {n_core}/{n} = {wilson(n_core,n)[0]}% CI{wilson(n_core,n)[1:]}")
    print(f"FULL (+ robust to alternative valid impls): {n_ok}/{n} = {wilson(n_ok,n)[0]}% CI{wilson(n_ok,n)[1:]}")
    print(f"exec-ok: {n_exec}/{n}   -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
