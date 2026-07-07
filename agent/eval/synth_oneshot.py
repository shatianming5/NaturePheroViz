"""
synth_oneshot.py — does a ONE-SHOT exemplar lift goldless-contract synthesis? (reviewer #1 lever)

The cross-vendor decomposition (e2e_scale_analyze) showed the dominant end-to-end miss is
CONTRACT SYNTHESIS: given the operator is correctly inferred, synthesis from the messy NL
succeeds only ~64% (23/36 CORE). The reviewer's highest-leverage ask: add ONE worked example
of a DIFFERENT operator's contract to the synthesis prompt and see if the conditional rate
lifts toward >=80%.

Controlled design (holds everything fixed except the exemplar):
  - intent = the SAME cached messy NL used by e2e_pipeline (results_e2e_scale/messy_queries.json)
  - operator is KNOWN by construction (per-candidate) -> this measures exactly the
    "synthesis given op correct" rate the decomposition isolated (the 64%).
  - baseline arm: synthesize with no exemplar (reproduces the e2e synth stage).
  - oneshot arm : synthesize with a fixed, leakage-free exemplar prepended.
  - CORE = synthesized contract FIRES on the silent slip AND PASSES the correct impl.

The exemplar is a rescale-to-percent-of-max RANGE invariant — an operator that is NOT in the
23-op evaluation set, so there is zero operator leakage; it only teaches the *style* of a
goldless invariant (check a property; read only inp/params/result; compute no reference answer).

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/synth_oneshot.py --model gpt-5.4
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa
import pandas as pd  # noqa
import warnings; warnings.filterwarnings("ignore")
from eval.w2_firing import _chat_api
from eval.autocontract_synth import SYNTH_PROMPT, _schema, _result_schema, wilson
from eval.e2e_pipeline import evaluate

# A single worked example for an operator OUTSIDE the eval set (rescale-to-percent-of-max):
# teaches the goldless-invariant STYLE (encode a RANGE property; read only inp/params/result;
# do not re-implement the transform / compute no reference answer).
EXEMPLAR = (
    "Before the task, here is ONE worked example for a DIFFERENT operator, to show the STYLE "
    "of a good goldless invariant (encode a checkable property; read only inp/params/result; "
    "compute NO reference answer; do not re-implement the transform).\n\n"
    "Example INTENT: rescale each score to a 0-100 percentage of the column's maximum.\n"
    "Example params: {\"value\": \"score\"}\n"
    "Example result: a DataFrame with column [\"score\"].\n"
    "Example contract:\n"
    "{\"code\": \"def contract(inp, params, result):\\n"
    "    v = params['value']\\n"
    "    got = pd.to_numeric(result[v], errors='coerce')\\n"
    "    # invariant: a percent-of-max lies in [0,100] and the max maps to 100\\n"
    "    if got.max() > 100 + 1e-6 or got.min() < -1e-6:\\n"
    "        return True\\n"
    "    return bool(abs(got.max() - 100.0) > 1e-4)\"}\n\n"
    "Now write the contract for the ACTUAL task below, in the same strict JSON format.\n\n"
)

# THREE diverse worked examples spanning DIFFERENT invariant families (range, conservation,
# structural/cardinality) — all for operators OUTSIDE the eval set. The point is to avoid the
# single-family bias of the one-shot exemplar: with several families shown, the synthesizer is
# cued to pick the family that fits the task rather than copy one style.
FEWSHOT = (
    "Before the task, here are THREE worked examples for DIFFERENT operators, spanning "
    "different KINDS of goldless invariant. Study the STYLE (encode a checkable property; read "
    "only inp/params/result; compute NO reference answer; do not re-implement the transform), "
    "then pick the invariant family that fits the ACTUAL task.\n\n"
    "Example A (RANGE) INTENT: rescale each score to a 0-100 percent of the column max.\n"
    "params {\"value\": \"score\"}; contract:\n"
    "{\"code\": \"def contract(inp, params, result):\\n    g = pd.to_numeric(result[params['value']], errors='coerce')\\n"
    "    return bool(g.max() > 100 + 1e-6 or g.min() < -1e-6 or abs(g.max()-100.0) > 1e-4)\"}\n\n"
    "Example B (CONSERVATION) INTENT: split each order total into per-item parts.\n"
    "params {\"total\": \"amount\", \"key\": \"order\"}; contract:\n"
    "{\"code\": \"def contract(inp, params, result):\\n    got = result.groupby(params['key'])['part'].sum()\\n"
    "    src = inp['df'].groupby(params['key'])[params['total']].first()\\n"
    "    return bool(not np.allclose(got.reindex(src.index).values, src.values, atol=1e-6))\"}\n\n"
    "Example C (STRUCTURE) INTENT: one-hot encode a category, one row per input row.\n"
    "params {\"category\": \"cat\"}; contract:\n"
    "{\"code\": \"def contract(inp, params, result):\\n    if len(result) != len(inp['df']):\\n        return True\\n"
    "    oh = result.select_dtypes('number')\\n    return bool(not np.allclose(oh.sum(axis=1).values, 1.0, atol=1e-6))\"}\n\n"
    "Now write the contract for the ACTUAL task below, in the same strict JSON format.\n\n"
)

_SHOTS = {"baseline": "", "oneshot": EXEMPLAR, "fewshot": FEWSHOT}


def synth(cand, intent_text, model, arm: str):
    inp = cand.fixture()
    cols, extra = _schema(inp)
    kind, rcols = _result_schema(cand.correct_fn(inp))
    prompt = SYNTH_PROMPT.format(intent=intent_text, cols=cols, extra=extra,
                                 params=cand.params, kind=kind, rcols=rcols)
    prompt = _SHOTS[arm] + prompt
    out = _chat_api([{"role": "user", "content": prompt}], model, max_tok=4000)
    m = re.search(r"\{.*\}", out or "", re.S)
    code = None
    if m:
        try:
            code = json.loads(m.group(0)).get("code")
        except Exception:
            code = None
    if code is None:
        m2 = re.search(r"def contract.*", out or "", re.S)
        code = m2.group(0) if m2 else None
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--cache", default="eval/results_e2e_scale/messy_queries.json")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or f"eval/results_synth_oneshot/{a.model.replace('/','_')}.json"

    from eval.core_candidates import CORE_CANDIDATES
    from eval.operator_expansion import CANDIDATES
    pool = list(CORE_CANDIDATES) + list(CANDIDATES)
    cands = [c for c in pool if isinstance(c.fixture().get("df"), pd.DataFrame)]
    cache = json.load(open(a.cache))

    recs = []
    b_core = o_core = f_core = n = 0
    for c in cands:
        nl = cache.get(c.operator)
        if not nl:
            continue
        n += 1
        base = evaluate(c, synth(c, nl, a.model, "baseline"))
        one = evaluate(c, synth(c, nl, a.model, "oneshot"))
        few = evaluate(c, synth(c, nl, a.model, "fewshot"))
        b_core += int(base["core"]); o_core += int(one["core"]); f_core += int(few["core"])
        recs.append({"op": c.operator, "baseline_core": base["core"], "oneshot_core": one["core"],
                     "fewshot_core": few["core"], "baseline_exec": base["exec_ok"]})
        def _m(x):
            return "CORE" if x else "fail"
        flag = ""
        if few["core"] and not base["core"]:
            flag = "  <-- FEWSHOT LIFTS"
        elif base["core"] and not few["core"]:
            flag = "  <-- FEWSHOT REGRESSES"
        print(f"  {c.operator:26} base={_m(base['core']):4} 1shot={_m(one['core']):4} "
              f"few={_m(few['core']):4}{flag}", flush=True)

    bc = wilson(b_core, n); oc = wilson(o_core, n); fc = wilson(f_core, n)
    summary = {"model": a.model, "n": n,
               "baseline_core": [b_core, n], "baseline_ci": bc,
               "oneshot_core": [o_core, n], "oneshot_ci": oc,
               "fewshot_core": [f_core, n], "fewshot_ci": fc, "cases": recs}
    outp = Path(out); outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(outp, "w"), indent=2)
    print(f"\n=== EXEMPLAR-LIFT synthesis (model {a.model}, same messy NL, op known) ===")
    print(f"baseline  CORE: {b_core}/{n} = {bc[0]}% [{bc[1]}-{bc[2]}]")
    print(f"one-shot  CORE: {o_core}/{n} = {oc[0]}% [{oc[1]}-{oc[2]}]   (delta {oc[0]-bc[0]:+.1f} pts)")
    print(f"few-shot  CORE: {f_core}/{n} = {fc[0]}% [{fc[1]}-{fc[2]}]   (delta {fc[0]-bc[0]:+.1f} pts)")
    print(f"-> {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
