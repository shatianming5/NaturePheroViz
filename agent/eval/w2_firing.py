"""
w2_firing.py — W2 done properly: not just keyword COVERAGE on DS-1000, but whether
the goldless oracle actually FIRES on real external silent errors. Pipeline:
  pick DS-1000 tasks the inferer covers -> generate a solution with opencode (free,
  no API key) -> drive DS-1000's own harness (_capture) for the real label
  (pass/silent/crash via DS-1000 gold) -> infer (op,params) from prompt+input df ->
  run the oracle on the produced result. Report real recall (fire on silent) and
  FP (fire on pass). This is the per-task firing the R2 review asked for.
Run: cd agent && python eval/w2_firing.py --n 14
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from eval.ds1000_real_intent import _load_pandas, _extract_code
from eval.ds1000_repair import _capture
from eval.transform_intent_infer import infer
from eval.transform_oracle import check as oracle_check

MODEL = "opencode/north-mini-code-free"


def gen(prompt: str) -> str:
    q = ("Solve this pandas problem. Reply with ONLY the code that assigns the answer to `result`, "
         "no prose, no fences.\n\n" + prompt)
    try:
        out = subprocess.run(["opencode","run","-m",MODEL,q], capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return ""
    return _extract_code(out) or out.strip()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--out-json", default="eval/results_w2_firing/firing.json"); a = ap.parse_args()
    import json, math
    def wilson(k, m):
        if m == 0: return [0, 0, 0]
        p = k/m; z = 1.96; d = 1+z*z/m
        c = (p+z*z/(2*m))/d; h = z*math.sqrt(p*(1-p)/m+z*z/(4*m*m))/d
        return [round(100*p), round(100*(c-h)), round(100*(c+h))]
    tasks = [t for t in _load_pandas(0, None, all_pandas=True) if infer(t["prompt"], pd.DataFrame())[0]]
    from pathlib import Path as _P; _P(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    print(f"covered tasks: {len(tasks)}; sampling {a.n}")
    silent=fire_on_silent=pas=fire_on_pass=crash=0; recs=[]
    for t in tasks[:a.n]:
        code = gen(t["prompt"])
        outcome, result, indf = _capture(t, code)
        op, P = infer(t["prompt"], indf if indf is not None else pd.DataFrame())
        fired = False
        if result is not None and indf is not None and op:
            try:
                r = oracle_check(op, {"df": indf}, P, result); fired = bool(r and r.fired)
            except Exception:
                fired = False
        if outcome == "silent":
            silent += 1; fire_on_silent += fired
        elif outcome == "pass":
            pas += 1; fire_on_pass += fired
        else:
            crash += 1
        recs.append({"pid": t["problem_id"], "op": op, "outcome": outcome, "oracle_fired": fired,
                     "code": code[:400]})
        print(f"  pid={t['problem_id']} op={op} outcome={outcome} oracle_fired={fired}", flush=True)
        # incremental write so a long run is crash/stop-safe
        rec_ci = wilson(fire_on_silent, silent); fp_ci = wilson(fire_on_pass, pas)
        json.dump({"model": MODEL, "n": a.n, "done": len(recs), "silent": silent, "pass": pas,
                   "crash": crash, "recall": f"{fire_on_silent}/{silent}", "recall_ci": rec_ci,
                   "fp": f"{fire_on_pass}/{pas}", "fp_ci": fp_ci, "cases": recs},
                  open(a.out_json, "w"), indent=2)
    rec_ci = wilson(fire_on_silent, silent); fp_ci = wilson(fire_on_pass, pas)
    summary = {"model": MODEL, "n": a.n, "silent": silent, "pass": pas, "crash": crash,
               "recall": f"{fire_on_silent}/{silent}", "recall_ci": rec_ci,
               "fp": f"{fire_on_pass}/{pas}", "fp_ci": fp_ci, "cases": recs}
    from pathlib import Path as _P; _P(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out_json, "w"), indent=2)
    print(f"\n=== W2 real firing on DS-1000 (model {MODEL}) ===")
    print(f"silent={silent} pass={pas} crash={crash}")
    print(f"oracle RECALL on real silent: {fire_on_silent}/{silent} = {rec_ci[0]}% CI{rec_ci[1:]} ")
    print(f"oracle FP on real pass:       {fire_on_pass}/{pas} = {fp_ci[0]}% CI{fp_ci[1:]} -> {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
