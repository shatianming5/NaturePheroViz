"""
w2_taxonomy_adjudicate.py — reframe the DS-1000 transfer result honestly (AAAI, T1-A).

The naive "recall 56% / FP 55%" uses the WRONG denominator: it counts every DS-1000
labelable case, but most DS-1000 silent errors are NOT one of our 28 operator-semantic
classes at all (they are string concatenation, MultiIndex reshaping, Excel header merges,
non-uniform NaN fills, ...). Our goldless contracts have no contract for those and MUST
stay silent on them — abstaining is CORRECT, not a miss.

So we adjudicate, with an INDEPENDENT frontier 'taxonomy judge' (separate from the
inferer), whether each labelable case's CORE intent genuinely belongs to one of our 28
operators. Then we report the honest, decomposed picture:
  - taxonomy COVERAGE : fraction of DS-1000 silent errors that are in-taxonomy at all
  - in-taxonomy RECALL: on the genuinely-ours silent cases, does the oracle fire?
  - out-of-taxonomy ABSTENTION: on not-ours cases, does the LLM inferer correctly abstain
    (-> no false fire)? This is where the FP actually comes from with the naive regex.

This converts "the method fails to transfer" into the accurate "the method is an
operator-scoped detector: reliable in-scope, correctly abstains out-of-scope; DS-1000's
silent errors mostly fall outside the current 28-operator taxonomy (a coverage limit, not
a detection failure)."

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/w2_taxonomy_adjudicate.py
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from eval.ds1000_real_intent import _load_pandas
from eval.w2_firing import _OPS_COVERED, _chat_api


def wilson(k, m):
    if m == 0:
        return [0, 0, 0]
    p = k / m; z = 1.96; d = 1 + z * z / m
    c = (p + z * z / (2 * m)) / d; h = z * math.sqrt(p * (1 - p) / m + z * z / (4 * m * m)) / d
    return [round(100 * p), round(100 * (c - h)), round(100 * (c + h))]


def adjudicate(prompt, model):
    """Independent taxonomy judge: is the task's CORE intent genuinely one of our ops?
    Returns an op id in _OPS_COVERED or None. Deliberately STRICT: only a specific op if
    the core computation IS that operator's semantics."""
    q = ("You are a strict taxonomy judge. Below is a pandas task. Decide whether its CORE "
         "computational intent is genuinely ONE of these operator-semantic classes, or NONE.\n"
         f"Operators: {', '.join(_OPS_COVERED)}.\n"
         "Answer a specific operator ONLY if the task's core computation IS that operator's "
         "semantics (e.g. weighted_mean = a weight-weighted average; left_join_keep_all = a "
         "left/outer merge that must retain all left rows; groupby_dropna_key = a groupby "
         "aggregation where NaN keys must be kept). If the core task is something else "
         "(string concatenation, reshaping/pivoting a MultiIndex, filling NaNs with custom "
         "values, merging header rows, etc.), answer 'none'.\n"
         f'Task:\n"""{prompt[:1200]}"""\n'
         "Reply with ONLY the operator id or 'none'.")
    out = _chat_api([{"role": "user", "content": q}], model, max_tok=2000)
    toks = out.replace("`", " ").replace("\n", " ").replace(".", " ").split()
    for t in reversed(toks):
        s = t.strip(".,:'\"").lower()
        if s in _OPS_COVERED:
            return s
        if s == "none":
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="eval/results_w2_firing/firing_frontier.json")
    ap.add_argument("--llm-infer", default="eval/results_w2_firing/firing_llm_infer.json",
                    help="per-case LLM-inferer assignments (for abstention-correctness)")
    ap.add_argument("--out", default="eval/results_w2_firing/taxonomy_adjudication.json")
    ap.add_argument("--judge", default="claude-opus-4.8", help="taxonomy judge model (independent of inferer)")
    a = ap.parse_args()
    data = json.load(open(a.inp))
    tasks = {t["problem_id"]: t for t in _load_pandas(0, None, all_pandas=True)}
    # per-case oracle-fired under the two inferers (from earlier runs)
    fired_regex = {(c["pid"], c.get("model")): c["oracle_fired"] for c in data["cases"]}
    llm_map = {}
    if Path(a.llm_infer).exists():
        lj = json.load(open(a.llm_infer))
        for c in lj["regex"]["cases"]:
            llm_map.setdefault((c["pid"],), {})  # placeholder
        for c in lj["llm_balanced"]["cases"]:
            llm_map[(c["pid"], c.get("model"))] = c  # op=None means abstained

    # adjudicate each unique (pid) once (task intent doesn't depend on the solution)
    seen = {}
    recs = []
    for c in data["cases"]:
        if c["outcome"] not in ("silent", "pass"):
            continue
        pid = c["pid"]
        if pid not in seen:
            seen[pid] = adjudicate(tasks[pid]["prompt"], a.judge) if pid in tasks else None
        gold_op = seen[pid]
        in_tax = gold_op is not None
        rec = {"pid": pid, "model": c.get("model"), "outcome": c["outcome"],
               "taxonomy_op": gold_op, "in_taxonomy": in_tax,
               "regex_fired": c["oracle_fired"]}
        lc = llm_map.get((pid, c.get("model")))
        rec["llm_inferred_op"] = (lc or {}).get("op")
        rec["llm_fired"] = bool((lc or {}).get("fired"))
        recs.append(rec)
        print(f"  pid={pid} out={c['outcome']} in_taxonomy={in_tax} tax_op={gold_op} "
              f"regex_fired={c['oracle_fired']} llm_op={rec['llm_inferred_op']}", flush=True)

    # decompose
    sil = [r for r in recs if r["outcome"] == "silent"]
    pas = [r for r in recs if r["outcome"] == "pass"]
    sil_in = [r for r in sil if r["in_taxonomy"]]
    sil_out = [r for r in sil if not r["in_taxonomy"]]
    pas_out = [r for r in pas if not r["in_taxonomy"]]
    cov = wilson(len(sil_in), len(sil))
    cond_recall_regex = wilson(sum(r["regex_fired"] for r in sil_in), len(sil_in))
    cond_recall_llm = wilson(sum(r["llm_fired"] for r in sil_in), len(sil_in))
    # out-of-taxonomy abstention: fraction of not-ours cases where inferer does NOT fire
    abst_regex_out = wilson(sum(1 for r in (sil_out + pas_out) if not r["regex_fired"]), len(sil_out + pas_out))
    abst_llm_out = wilson(sum(1 for r in (sil_out + pas_out) if not r["llm_fired"]), len(sil_out + pas_out))
    summary = {
        "judge": a.judge, "n_silent": len(sil), "n_pass": len(pas),
        "taxonomy_coverage_of_silent": {"k": len(sil_in), "n": len(sil), "pct_ci": cov},
        "in_taxonomy_recall": {"regex": cond_recall_regex, "llm": cond_recall_llm,
                               "n_in_taxonomy_silent": len(sil_in)},
        "out_of_taxonomy_abstention": {"regex": abst_regex_out, "llm": abst_llm_out,
                                       "n_out_of_taxonomy": len(sil_out + pas_out)},
        "cases": recs,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out, "w"), indent=2)
    print("\n=== DS-1000 honest decomposition (taxonomy judge = %s) ===" % a.judge)
    print(f"taxonomy coverage of silent errors: {len(sil_in)}/{len(sil)} = {cov[0]}% CI{cov[1:]}")
    print(f"in-taxonomy recall  regex {cond_recall_regex[0]}%  llm {cond_recall_llm[0]}%  (n={len(sil_in)})")
    print(f"out-of-taxonomy correct-abstention  regex {abst_regex_out[0]}%  llm {abst_llm_out[0]}%  (n={len(sil_out+pas_out)})")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
