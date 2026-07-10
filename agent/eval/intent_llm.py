"""
intent_llm.py — LLM NL->operator classifier (deployable alternative to the regex
inferer, which overfits the grid lexicon: 28% on held-out paraphrases). Uses the
local opencode CLI (free model) so it runs without API keys. Tests on the same
held-out paraphrase set; reports op-accuracy and contrasts the regex baseline.
Run: cd agent && python eval/intent_llm.py [--n 18]
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eval.transform_paraphrase import CASES
from eval.transform_intent_infer import infer_op

OPS = ["weighted_mean","within_group_share","pct_point","dedup_then_agg","left_join_keep_all",
       "pooled_rate","median_not_mean","cumulative_running","topn_with_ties","nan_as_zero_sum",
       "count_includes_empty","proportion_true","zscore_within_group","dense_rank",
       "cumcount_per_group","rank_pct","clip_outlier"]
MODEL = "opencode/north-mini-code-free"


def classify(prompt: str, cols: list) -> str:
    q = (f"Classify the pandas transform intent into ONE operator id from this list: {', '.join(OPS)}. "
         f"Intent: \"{prompt}\" Columns: {cols}. Reply with ONLY the operator id, nothing else.")
    try:
        out = subprocess.run(["opencode","run","-m",MODEL,q], capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return "?"
    toks = out.replace("`"," ").replace("\n"," ").split()
    for t in reversed(toks):
        if t.strip(".,:") in OPS:
            return t.strip(".,:")
    return "?"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=len(CASES))
    ap.add_argument("--out-json", default="eval/results_generalize/intent_llm.json"); a = ap.parse_args()
    import json
    llm = rgx = 0; n = 0; recs = []
    for op, prompt, df in CASES[:a.n]:
        n += 1
        l = classify(prompt, list(df.columns)); r = infer_op(prompt)
        if l == op: llm += 1
        if r == op: rgx += 1
        recs.append({"true": op, "llm": l, "regex": r, "prompt": prompt, "cols": list(df.columns)})
        print(f"[{n:2d}] true={op:20} llm={l:20} regex={r}")
    summary = {"n": n, "llm_acc": round(100*llm/n), "regex_acc": round(100*rgx/n), "model": MODEL, "cases": recs}
    from pathlib import Path as _P; _P(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out_json, "w"), indent=2)
    print(f"\nN={n}  LLM op-acc {llm}/{n}={round(100*llm/n)}%  vs regex {rgx}/{n}={round(100*rgx/n)}%  -> {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
