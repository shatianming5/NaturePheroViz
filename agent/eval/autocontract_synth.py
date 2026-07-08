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
    # core operators
    "weighted_mean": "Compute the average of the value column WEIGHTED by the weight column (sum(value*weight)/sum(weight)), not the plain arithmetic mean.",
    "within_group_share": "Add a share column = each row's value divided by ITS OWN GROUP's total, so shares sum to 1 WITHIN each group (not across the whole table).",
    "pct_point": "Compute the change in percentage POINTS (new - old, on a 0-100 point scale), not the relative percent change (new-old)/old.",
    "dedup_then_agg": "Deduplicate by the key first (one row per key), THEN aggregate the value per group, so duplicate line-items are not double-counted.",
    "left_join_keep_all": "Attach the lookup columns onto the left table with a LEFT/outer join that KEEPS every left row (unmatched rows get nulls), not an inner join that drops them.",
    "pooled_rate": "Compute each group's rate as SUM(numerator)/SUM(denominator) over the group (a pooled rate), not the mean of per-row ratios.",
    "median_not_mean": "Compute the MEDIAN of the value within each group (robust to outliers), not the mean.",
    "cumulative_running": "Compute the running cumulative sum of the value in order, so each row shows the balance up to that point, not the raw per-row value.",
    "topn_with_ties": "Return the top-N by value but KEEP ALL rows tied at the cutoff (do not arbitrarily drop a tie to force exactly N rows).",
    "nan_as_zero_sum": "Sum the value per group treating missing values as zero, so a group is not reported as NaN just because one member is missing.",
    "count_includes_empty": "Count rows per category INCLUDING categories with zero rows (report them as 0), not only the categories that happen to appear.",
    "proportion_true": "Compute the PROPORTION of true flags per group (mean of the boolean = rate in [0,1]), not the raw count of trues.",
}

# DE-LEAKED intents (AAAI independent-review fix). Two independent reviewers (gpt-5.5,
# gemini-3.1-pro) verified that the INTENT strings above leak the answer: they spell out the
# exact formula (e.g. "sum(value*weight)/sum(weight)") and the exact slip to avoid ("not the
# mean"), so the LLM is merely TRANSLATING a stated formula, not DISCOVERING an invariant from
# high-level intent. These DELEAKED intents describe only the user's GOAL in plain domain
# language — NO formula, NO "not the X" contrast, NO checkable invariant stated. The LLM must
# now derive the goldless invariant itself. We report BOTH numbers so the reader sees exactly
# how much the synthesis result depends on the leaked formula hint.
DELEAKED_INTENT = {
    "index_align": "For each key, the output total should combine that key's own value with the corresponding addend for the same key taken from the second table.",
    "dtype_coerce": "Group by the id so that entries referring to the same identifier are treated as one, regardless of how the id happens to be formatted.",
    "groupby_dropna_key": "Total the value within each group, and don't discard rows just because their group label is missing — those rows still belong to the population.",
    "order_dependent_dedup": "Reduce to one row per key, choosing the intended representative (for example the most recent according to the order column).",
    "resample_boundary": "Aggregate the time series into calendar periods so each observation is counted in the period it actually belongs to.",
    "string_normalize_join": "Attach each row's price from the lookup by matching on name, allowing for superficial formatting differences so genuinely equal names still match.",
    "join_fanout": "Summarize each entity's measure by group; joining against a table that has several rows per entity should not distort an entity's contribution.",
    "null_in_agg_count": "Report how many rows fall into each group.",
    "scale_before_split_leakage": "Standardize the feature for modeling so that the scaling is derived from the training portion of the data.",
    "latlon_swap": "Compute the geographic result from the latitude and longitude columns, each used in its proper geographic role.",
    "lookahead_return": "For each row, compute a forward-looking return based only on information that would have been available at that row's point in time.",
    "numpy_broadcast": "Combine the two arrays so that each element is paired with its intended counterpart.",
    "weighted_mean": "Report a single representative average of the value where entries carrying more weight have proportionally more influence on the result.",
    "within_group_share": "For each row, report its value as a share of the total for its own group.",
    "pct_point": "Report how much the percentage figure moved from the old value to the new value, expressed on the same 0-100 scale.",
    "dedup_then_agg": "Total the value per group after collapsing repeated line-items that refer to the same key, so the same item isn't counted twice.",
    "left_join_keep_all": "Attach the lookup columns to the table while retaining every original row, including rows that have no match in the lookup.",
    "pooled_rate": "Report each group's overall rate by combining all of that group's members together.",
    "median_not_mean": "Report a representative central value for each group that isn't thrown off by a few unusually large or small entries.",
    "cumulative_running": "Show a running total of the value in order, so each row reflects the amount accumulated up to and including it.",
    "topn_with_ties": "Return the highest-ranked N rows by value, and if several rows are tied at the cutoff, include all of them.",
    "nan_as_zero_sum": "Total the value for each group so that a group with some missing entries still gets a numeric total rather than becoming undefined.",
    "count_includes_empty": "Report a count for every category, giving zero for categories that have no rows rather than omitting them.",
    "proportion_true": "For each group, report the fraction of its rows whose flag is true.",
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


def _parse_code(out):
    m = re.search(r"\{.*\}", out or "", re.S)
    if m:
        try:
            c = json.loads(m.group(0)).get("code")
            if c:
                return c
        except Exception:
            pass
    m2 = re.search(r"def contract.*", out or "", re.S)
    return m2.group(0) if m2 else None


def synth_contract(cand, model, intent_map=INTENT):
    inp = cand.fixture()
    cols, extra = _schema(inp)
    # show the result schema from the CORRECT impl (schema only — values not revealed as gold)
    correct = cand.correct_fn(inp)
    kind, rcols = _result_schema(correct)
    intent = intent_map.get(cand.operator, f"Correctly compute the `{cand.operator}` transform.")
    prompt = SYNTH_PROMPT.format(intent=intent, cols=cols, extra=extra,
                                 params=cand.params, kind=kind, rcols=rcols)
    # reasoning-heavy models (opus/sonnet) sometimes spend the whole budget "thinking" and emit
    # empty content on a long structured prompt. Retry with a terse directive + bigger budget.
    for attempt in range(3):
        p = prompt if attempt == 0 else (
            prompt + "\n\nIMPORTANT: output ONLY the JSON object now, no analysis or explanation.")
        out = _chat_api([{"role": "user", "content": p}], model, max_tok=4000 + attempt * 8000)
        code = _parse_code(out)
        if code:
            return code
    return None


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
    ap.add_argument("--source", choices=("expansion", "core", "all"), default="expansion",
                    help="which operator set to synthesize contracts for")
    ap.add_argument("--intent", choices=("leaky", "deleaked"), default="leaky",
                    help="leaky = original formula-stating intent; deleaked = high-level goal "
                         "only (no formula/no 'not-X'/no invariant), the AAAI independent-review fix")
    a = ap.parse_args()
    intent_map = DELEAKED_INTENT if a.intent == "deleaked" else INTENT
    recs = []
    n_ok = n_exec = 0
    pool = list(CANDIDATES)
    if a.source in ("core", "all"):
        from eval.core_candidates import CORE_CANDIDATES
        pool = (list(CORE_CANDIDATES) + pool) if a.source == "all" else list(CORE_CANDIDATES)
    # only pandas-DataFrame operators (numpy_broadcast's fixture is dict-of-arrays, outside
    # the DataFrame-result contract framework -> skip)
    cands = [c for c in pool if isinstance(c.fixture().get("df"), pd.DataFrame)]
    for cand in cands:
        best = None
        for attempt in range(a.retries):
            try:
                code = synth_contract(cand, a.model, intent_map)
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
    summary = {"model": a.model, "intent_mode": a.intent, "n_operators": n,
               "auto_full_correct": n_ok, "auto_full_ci": wilson(n_ok, n),
               "auto_core_correct": n_core, "auto_core_ci": wilson(n_core, n),
               "exec_ok": n_exec, "cases": recs}
    out = a.out
    if a.intent == "deleaked" and out == ap.get_default("out"):
        out = out.replace(".json", "_deleaked.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(out, "w"), indent=2)
    print(f"\n=== AUTO-SYNTHESIZED goldless contracts from NL (model {a.model}, intent={a.intent}, n={n} ops) ===")
    print(f"CORE (fire-on-slip AND pass-on-correct): {n_core}/{n} = {wilson(n_core,n)[0]}% CI{wilson(n_core,n)[1:]}")
    print(f"FULL (+ robust to alternative valid impls): {n_ok}/{n} = {wilson(n_ok,n)[0]}% CI{wilson(n_ok,n)[1:]}")
    print(f"exec-ok: {n_exec}/{n}   -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
