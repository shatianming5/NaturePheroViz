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


def gen_api(prompt: str, model: str) -> str:
    """Frontier-API generator (OpenAI-compatible /v1/chat/completions via env). Stronger
    and faster than the free opencode model, so we get more valid/labelable DS-1000
    solutions -> more fireable external cases for the oracle-transfer measurement."""
    import json, os, re, requests
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    q = ("Solve this pandas problem. Reply with ONLY the code that assigns the answer to "
         "`result`, no prose, no fences.\n\n" + prompt)
    ml = model.lower()
    reasoning = ml.startswith(("gpt-5", "o1", "o3", "o4")) or "codex" in ml
    payload = {"model": model, "messages": [{"role": "user", "content": q}]}
    if reasoning:
        payload["max_completion_tokens"] = 8000
    else:
        payload["temperature"] = 0.0; payload["max_tokens"] = 4000
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json=payload, timeout=(10, 180))
        r.raise_for_status()
        c = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        return _extract_code(c) or c.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--out-json", default="eval/results_w2_firing/firing.json")
    ap.add_argument("--backend", choices=("opencode", "api"), default="opencode",
                    help="opencode: local free model. api: frontier via LLM_API_BASE/KEY (more valid cases).")
    ap.add_argument("--models", default="gpt-5.4",
                    help="api backend: comma-separated frontier models to pool over (more cases).")
    a = ap.parse_args()
    import json, math
    def wilson(k, m):
        if m == 0: return [0, 0, 0]
        p = k/m; z = 1.96; d = 1+z*z/m
        c = (p+z*z/(2*m))/d; h = z*math.sqrt(p*(1-p)/m+z*z/(4*m*m))/d
        return [round(100*p), round(100*(c-h)), round(100*(c+h))]
    tasks = [t for t in _load_pandas(0, None, all_pandas=True) if infer(t["prompt"], pd.DataFrame())[0]]
    from pathlib import Path as _P; _P(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    models = [m.strip() for m in a.models.split(",")] if a.backend == "api" else [MODEL]
    print(f"covered tasks: {len(tasks)}; sampling {a.n} x {len(models)} model(s) [{a.backend}]")
    from eval.transform_oracle import _REQUIRED_PARAMS
    def _schema_adequate(op, P, indf):
        """True if the inferred op's REQUIRED param keys are all present AND name real
        input columns — i.e. the inferer's op guess is schema-consistent with THIS task.
        When false, a fire/miss is an INFERER coverage error, not a contract verdict."""
        if not op or indf is None:
            return False
        req = _REQUIRED_PARAMS.get(op, ())
        for k in req:
            v = P.get(k)
            if v is None:
                return False
            if isinstance(v, str) and v not in indf.columns:
                return False
        return True
    silent=fire_on_silent=pas=fire_on_pass=crash=0; recs=[]
    # schema-adequate subset counters (honest: contract verdict only where op truly applies)
    sa_sil=sa_sil_fire=sa_pas=sa_pas_fire=0
    for t in tasks[:a.n]:
        for m in models:
            code = gen_api(t["prompt"], m) if a.backend == "api" else gen(t["prompt"])
            outcome, result, indf = _capture(t, code)
            op, P = infer(t["prompt"], indf if indf is not None else pd.DataFrame())
            adequate = _schema_adequate(op, P, indf)
            fired = False
            if result is not None and indf is not None and op:
                try:
                    r = oracle_check(op, {"df": indf}, P, result); fired = bool(r and r.fired)
                except Exception:
                    fired = False
            if outcome == "silent":
                silent += 1; fire_on_silent += fired
                if adequate: sa_sil += 1; sa_sil_fire += fired
            elif outcome == "pass":
                pas += 1; fire_on_pass += fired
                if adequate: sa_pas += 1; sa_pas_fire += fired
            else:
                crash += 1
            recs.append({"pid": t["problem_id"], "model": m, "op": op, "outcome": outcome,
                         "oracle_fired": fired, "schema_adequate": adequate, "code": code[:400]})
            print(f"  pid={t['problem_id']} model={m} op={op} adeq={int(adequate)} outcome={outcome} oracle_fired={fired}", flush=True)
            # incremental write so a long run is crash/stop-safe
            rec_ci = wilson(fire_on_silent, silent); fp_ci = wilson(fire_on_pass, pas)
            sa_rec_ci = wilson(sa_sil_fire, sa_sil); sa_fp_ci = wilson(sa_pas_fire, sa_pas)
            json.dump({"backend": a.backend, "models": models, "n": a.n, "done": len(recs),
                       "silent": silent, "pass": pas, "crash": crash,
                       "recall": f"{fire_on_silent}/{silent}", "recall_ci": rec_ci,
                       "fp": f"{fire_on_pass}/{pas}", "fp_ci": fp_ci,
                       "schema_adequate": {
                           "silent": sa_sil, "pass": sa_pas,
                           "recall": f"{sa_sil_fire}/{sa_sil}", "recall_ci": sa_rec_ci,
                           "fp": f"{sa_pas_fire}/{sa_pas}", "fp_ci": sa_fp_ci},
                       "cases": recs},
                      open(a.out_json, "w"), indent=2)
    rec_ci = wilson(fire_on_silent, silent); fp_ci = wilson(fire_on_pass, pas)
    sa_rec_ci = wilson(sa_sil_fire, sa_sil); sa_fp_ci = wilson(sa_pas_fire, sa_pas)
    summary = {"backend": a.backend, "models": models, "n": a.n, "silent": silent, "pass": pas,
               "crash": crash, "recall": f"{fire_on_silent}/{silent}", "recall_ci": rec_ci,
               "fp": f"{fire_on_pass}/{pas}", "fp_ci": fp_ci,
               "schema_adequate": {"silent": sa_sil, "pass": sa_pas,
                                   "recall": f"{sa_sil_fire}/{sa_sil}", "recall_ci": sa_rec_ci,
                                   "fp": f"{sa_pas_fire}/{sa_pas}", "fp_ci": sa_fp_ci},
               "cases": recs}
    from pathlib import Path as _P; _P(a.out_json).parent.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(a.out_json, "w"), indent=2)
    print(f"\n=== W2 real firing on DS-1000 (backend {a.backend}, models {models}) ===")
    print(f"silent={silent} pass={pas} crash={crash} (labelable={silent+pas})")
    print(f"[naive, all inferer-covered] RECALL {fire_on_silent}/{silent}={rec_ci[0]}% CI{rec_ci[1:]}  "
          f"FP {fire_on_pass}/{pas}={fp_ci[0]}% CI{fp_ci[1:]}")
    print(f"[schema-adequate subset]     RECALL {sa_sil_fire}/{sa_sil}={sa_rec_ci[0]}% CI{sa_rec_ci[1:]}  "
          f"FP {sa_pas_fire}/{sa_pas}={sa_fp_ci[0]}% CI{sa_fp_ci[1:]}  -> {a.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
