"""
w2_llm_rescore.py — the DECISIVE transfer experiment (AAAI reviewer R2, gap #2).

Controlled A/B on the SAME cached DS-1000 external cases (firing_frontier.json): same
tasks, same frontier-generated solutions, same DS-1000 gold labels — the ONLY thing that
changes is the operator INFERER:
  - regex  : the naive keyword inferer (over-fires -> the honest 56% recall / 55% FP)
  - llm    : a calibrated LLM op-classifier WITH a 'none' escape hatch (should ABSTAIN on
             non-covered tasks, suppressing the spurious fires that drive FP up).

For each cached case we re-capture the input df + result, run the chosen inferer to get
(op, params), and re-run the goldless oracle. We recompute recall (fire on real silent)
and FP (fire on real pass). If the LLM inferer pushes recall up and FP down, the
"transfer fails in the wild" story becomes "transfer works once operator intent is
recovered by a trainable component" — the single most decisive fix for AAAI.

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/w2_llm_rescore.py \
        --in eval/results_w2_firing/firing_frontier.json --infer-model gpt-5.4
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from eval.ds1000_real_intent import _load_pandas
from eval.ds1000_repair import _capture
from eval.transform_intent_infer import infer as regex_infer, infer_params
from eval.transform_oracle import check as oracle_check
from eval.w2_firing import classify_op_llm


def wilson(k, m):
    if m == 0:
        return [0, 0, 0]
    p = k / m; z = 1.96; d = 1 + z * z / m
    c = (p + z * z / (2 * m)) / d; h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
    return [round(100 * p), round(100 * (c - h)), round(100 * (c + h))]


def _infer(mode, prompt, indf, model):
    if mode == "regex":
        return regex_infer(prompt, indf if indf is not None else pd.DataFrame())
    conservative = (mode == "llm_conservative")
    op = classify_op_llm(prompt, list(indf.columns) if indf is not None else [], model,
                         conservative=conservative)
    if op is None:
        return None, {}
    P = infer_params(op, indf if indf is not None else pd.DataFrame(), None, prompt)
    return op, P


def score(mode, cases, tasks, model):
    sil = sf = pas = pf = abst = 0; recs = []
    for c in cases:
        t = tasks.get(c["pid"])
        if t is None:
            continue
        outcome, result, indf = _capture(t, c["code"])
        if outcome not in ("silent", "pass"):
            continue
        op, P = _infer(mode, t["prompt"], indf, model)
        fired = False
        if op is None:
            abst += 1
        elif result is not None and indf is not None:
            try:
                r = oracle_check(op, {"df": indf}, P, result); fired = bool(r and r.fired)
            except Exception:
                fired = False
        if outcome == "silent":
            sil += 1; sf += fired
        else:
            pas += 1; pf += fired
        recs.append({"pid": c["pid"], "model": c.get("model"), "outcome": outcome,
                     "op": op, "fired": fired})
    return {"silent": sil, "recall": f"{sf}/{sil}", "recall_ci": wilson(sf, sil),
            "pass": pas, "fp": f"{pf}/{pas}", "fp_ci": wilson(pf, pas),
            "abstained": abst, "labelable": sil + pas, "cases": recs}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="eval/results_w2_firing/firing_frontier.json")
    ap.add_argument("--out", default="eval/results_w2_firing/firing_llm_infer.json")
    ap.add_argument("--infer-model", default="gpt-5.4")
    a = ap.parse_args()
    data = json.load(open(a.inp))
    cases = data["cases"]
    tasks = {t["problem_id"]: t for t in _load_pandas(0, None, all_pandas=True)}
    print(f"re-scoring {len(cases)} cached DS-1000 cases; inferer sweep (regex vs llm={a.infer_model})", flush=True)
    regex = score("regex", cases, tasks, a.infer_model)
    print(f"[regex]            recall {regex['recall']}={regex['recall_ci'][0]}%  "
          f"FP {regex['fp']}={regex['fp_ci'][0]}%  abstain={regex['abstained']}", flush=True)
    llm_bal = score("llm_balanced", cases, tasks, a.infer_model)
    print(f"[llm balanced]     recall {llm_bal['recall']}={llm_bal['recall_ci'][0]}%  "
          f"FP {llm_bal['fp']}={llm_bal['fp_ci'][0]}%  abstain={llm_bal['abstained']}", flush=True)
    llm_con = score("llm_conservative", cases, tasks, a.infer_model)
    print(f"[llm conservative] recall {llm_con['recall']}={llm_con['recall_ci'][0]}%  "
          f"FP {llm_con['fp']}={llm_con['fp_ci'][0]}%  abstain={llm_con['abstained']}", flush=True)
    out = {"source": a.inp, "infer_model": a.infer_model,
           "regex": regex, "llm_balanced": llm_bal, "llm_conservative": llm_con}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=2)
    print(f"\n=== DECISIVE transfer sweep (same tasks/solutions/labels, inferer swapped) ===")
    print(f"regex:            recall {regex['recall_ci'][0]}%  FP {regex['fp_ci'][0]}%")
    print(f"llm balanced:     recall {llm_bal['recall_ci'][0]}%  FP {llm_bal['fp_ci'][0]}%  (abstain {llm_bal['abstained']})")
    print(f"llm conservative: recall {llm_con['recall_ci'][0]}%  FP {llm_con['fp_ci'][0]}%  (abstain {llm_con['abstained']})")
    print(f"target for AAAI: recall>70% AND FP<20% -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
