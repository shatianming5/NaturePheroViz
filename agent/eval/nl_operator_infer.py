"""
nl_operator_infer.py — can we RECOVER the operator from the NL task description on REAL
Nature tasks? (AAAI W1' — lift the "operator must be given" ceiling on the target domain).

Reviewer's residual ceiling (W1'): the Nature 99%/0% detection assumes op+params are
template-GIVEN; on arbitrary free-text CODE (DS-1000) operator inference fails. But the
deployment setting for a data-analysis assistant is NL TASK DESCRIPTIONS, not raw code.
This experiment tests the intermediate, realistic setting: given the natural-language task
(the clarified intent used in the prevalence study) + the REAL Nature column name, can a
frontier LLM recover the operator? If yes, detection runs end-to-end WITHOUT the operator
being handed in — lifting the conditional-validity limit on the domain that matters.

We reconstruct the clarified NL for real Nature tasks (from results_real_scaled records,
which carry the true op + the real article/column in `name`), run the LLM operator
classifier, and report: (a) top-1 inference accuracy vs the true op, (b) end-to-end
detection RETENTION = fraction of originally-detected silent errors that are still detected
when the operator is INFERRED rather than given (inferred==true AND was oracle-fired).

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/nl_operator_infer.py --per-op 30
"""
from __future__ import annotations
import argparse, json, math, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.w2_firing import classify_op_llm
from eval.transform_intent_infer import infer_op as regex_infer_op

# the clarified-intent templates (mirrors nature_real_auto.py), filled with the REAL column
CLARIFIED = {
    "median_not_mean": "The MEDIAN {v} per {cat} (not the mean). Columns {cat}, {v}.",
    "within_group_share": ("Add 'share' = each row's {v} / its OWN {cat} group's total {v} "
                           "(within-group share, not the grand total). Keep {cat}, {v}, share."),
    "weighted_mean": "The weight-WEIGHTED average {v} (weight each {v}; one number, column 'wavg').",
    "pooled_rate": ("The rate per {cat} = TOTAL numerator / TOTAL denominator in that group "
                    "(pooled sum/sum, NOT the mean of per-row ratios). Columns {cat}, rate."),
    "nan_as_zero_sum": "Total {v} per {cat}, treating MISSING values as 0. Columns {cat}, {v}.",
}


def _parse_col(name):
    # name like "median::s41586-...:5a Left:mitosis (min)" -> value column after the last ':'
    tail = name.split("::", 1)[-1]
    parts = tail.split(":")
    col = parts[-1].strip() if parts else "value"
    return col or "value"


def wilson(k, m):
    if m == 0:
        return [0, 0, 0]
    p = k / m; z = 1.96; d = 1 + z * z / m
    c = (p + z * z / (2 * m)) / d; h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
    return [round(100 * p), round(100 * (c - h)), round(100 * (c + h))]


def _was_silent_fired(rec):
    """Did the oracle originally fire on a silent error for this task (any model, ambiguous)?"""
    amb = rec.get("ambiguous", {})
    for m, r in amb.items():
        if r.get("tag") == "SILENT" and r.get("oracle_fired"):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default="eval/results_real_scaled/real_auto_records.json")
    ap.add_argument("--model", default="gpt-5.4")
    ap.add_argument("--per-op", type=int, default=30, help="sample this many tasks per operator")
    ap.add_argument("--out", default="eval/results_nl_infer/nl_operator_infer.json")
    a = ap.parse_args()
    random.seed(0)
    recs = json.load(open(a.records))
    by_op = {}
    for r in recs:
        by_op.setdefault(r["op"], []).append(r)
    sample = []
    for op, rs in by_op.items():
        random.shuffle(rs)
        sample.extend(rs[: a.per_op])
    print(f"real Nature tasks: {len(recs)}; sampling {len(sample)} ({len(by_op)} operators)", flush=True)

    n = llm_ok = rgx_ok = 0
    detn = det_retained = 0
    cases = []
    for r in sample:
        op = r["op"]
        col = _parse_col(r["name"])
        nl = CLARIFIED[op].format(v=col, cat="group")
        cols = ["group", col] if op != "weighted_mean" else [col, "weight"]
        inferred = classify_op_llm(nl, cols, a.model, conservative=False)
        rgx = regex_infer_op(nl)
        n += 1
        llm_ok += int(inferred == op)
        rgx_ok += int(rgx == op)
        # end-to-end detection retention on the originally-detected silent errors
        was = _was_silent_fired(r)
        if was:
            detn += 1
            det_retained += int(inferred == op)  # same true op recovered -> same oracle fires
        cases.append({"op": op, "col": col, "inferred": inferred, "regex": rgx,
                      "llm_correct": inferred == op, "was_silent_detected": was})
        print(f"  {op:20} col={col[:22]:22} inferred={str(inferred):20} {'OK' if inferred==op else 'x'}", flush=True)

    acc = wilson(llm_ok, n); racc = wilson(rgx_ok, n)
    ret = wilson(det_retained, detn)
    summary = {"model": a.model, "n": n, "operators": sorted(by_op),
               "llm_infer_acc": {"k": llm_ok, "n": n, "pct_ci": acc},
               "regex_infer_acc": {"k": rgx_ok, "n": n, "pct_ci": racc},
               "detection_retention_inferred_vs_given": {"k": det_retained, "n": detn, "pct_ci": ret},
               "cases": cases}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out, "w"), indent=2)
    print(f"\n=== operator inference from NL TASK on REAL Nature (model {a.model}) ===")
    print(f"LLM top-1 accuracy:  {llm_ok}/{n} = {acc[0]}% CI{acc[1:]}")
    print(f"regex baseline:      {rgx_ok}/{n} = {racc[0]}% CI{racc[1:]}")
    print(f"detection retention (inferred vs given op): {det_retained}/{detn} = {ret[0]}% CI{ret[1:]}")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
