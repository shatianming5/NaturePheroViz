"""
nature_expansion_prevalence.py — REAL Nature-data prevalence for the expansion operators.

Closes the external-validity gap for the new operator families: the framework-mechanics
ops whose silent trigger is MISSING DATA (groupby_dropna_key, null_in_agg_count) genuinely
occur in real scientific tables (missing category labels / missing measurements). This
runs them through the SAME real-Nature pipeline that produced the 77% headline
(nature_real_auto._build, expansion=True), with the SAME (ambiguous, clarified) + goldless
oracle protocol, but opencode-backed so it runs without cloud LLM keys.

Run:
  cd agent && python eval/nature_expansion_prevalence.py \
      --pairs-root ../data/nature_pairs/articles --max-per-op 6 \
      --models opencode/big-pickle,opencode/deepseek-v4-flash-free
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.nature_real_auto import _build  # noqa: E402
from eval.ambiguity_calibration import _exec, _gold_correct  # noqa: E402
from eval.expansion_prevalence import _oc_code, _wilson, EXPANSION_OPS  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Real-Nature prevalence for expansion operators")
    ap.add_argument("--out", default="eval/results_expansion")
    ap.add_argument("--pairs-root", default="../data/nature_pairs/articles")
    ap.add_argument("--models", default="opencode/big-pickle,opencode/deepseek-v4-flash-free")
    ap.add_argument("--max-per-op", type=int, default=6, help="real tasks per operator")
    ap.add_argument("--max-per-article", type=int, default=15)
    ap.add_argument("--max-rows", type=int, default=200)
    ap.add_argument("--max-build", type=int, default=600)
    ap.add_argument("--attempts", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--backend", choices=("opencode", "api"), default="opencode",
                    help="opencode: local free models. api: cloud frontier via LLM_API_BASE/LLM_API_KEY.")
    args = ap.parse_args(argv)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if args.backend == "api":
        import os
        if not (os.getenv("LLM_API_BASE") and os.getenv("LLM_API_KEY")):
            print("[error] --backend api needs LLM_API_BASE / LLM_API_KEY.")
            return 1
        from eval.ambiguity_calibration import _llm_code as _gen_api
        _gen = lambda item, prompt, model: _gen_api(item, prompt, model)  # noqa: E731
    else:
        _gen = lambda item, prompt, model: _oc_code(item, prompt, model, timeout=args.timeout)  # noqa: E731

    built = _build(args.pairs_root, max_tasks=args.max_build,
                   max_per_article=args.max_per_article, max_rows=args.max_rows, expansion=True)
    seen: Dict[str, int] = defaultdict(int)
    items: List[Dict[str, Any]] = []
    for t in built:
        if t["op"] not in EXPANSION_OPS:
            continue
        seen[t["op"]] += 1
        if seen[t["op"]] > args.max_per_op:
            continue
        items.append(t)
    arts = len({t["name"].split("::")[1] for t in items}) if items else 0
    by_op = defaultdict(int)
    for t in items:
        by_op[t["op"]] += 1
    print(f"[real-grid] {len(items)} REAL Nature tasks across {arts} articles; "
          f"by_op={dict(by_op)}; models={models}", flush=True)
    if not items:
        print("[error] no real expansion tasks found — check --pairs-root")
        return 1

    rows: List[Dict[str, Any]] = []
    obs: List[Dict[str, Any]] = []
    for item in items:
        op = item["op"]
        inp = {"df": item["df"]}
        rec: Dict[str, Any] = {"item": item["name"], "op": op}
        for cond in ("ambiguous", "clarified"):
            for m in models:
                code = result = None
                for _ in range(max(1, args.attempts)):
                    code = _gen(item, item[cond], m)
                    result = _exec(item, code) if code else None
                    if result is not None:
                        break
                exec_ok = result is not None
                correct = bool(exec_ok and _gold_correct(item, result))
                oc = oracle_check(op, inp, item["params"], result)
                fired = bool(oc and oc.fired)
                tag = "ok" if correct else ("SILENT" if exec_ok else "crash")
                short = item["name"].split("::", 1)[-1]
                print(f"[{short[:34]:34}] {cond:9} {m:32} {tag:7} fired={fired}", flush=True)
                rec.setdefault(cond, {})[m] = {"tag": tag, "oracle_fired": fired,
                                               "exec_ok": exec_ok, "correct": correct,
                                               "code": (code or "")[:300]}
                obs.append({"op": op, "model": m, "cond": cond, "exec_ok": exec_ok,
                            "correct": correct, "oracle_fired": fired})
        rows.append(rec)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nature_expansion_records.json").write_text(json.dumps(rows, indent=2, default=str))

    def _tally(sub):
        c = dict(amb_s=0, amb_t=0, clar_s=0, clar_t=0, rec_f=0, rec_t=0, fp_f=0, fp_t=0, crash=0)
        for d in sub:
            st = "amb" if d["cond"] == "ambiguous" else "clar"
            c[st + "_t"] += 1
            if not d["exec_ok"]:
                c["crash"] += 1
            elif not d["correct"]:
                c[st + "_s"] += 1
            if d["exec_ok"]:
                if d["correct"]:
                    c["fp_t"] += 1; c["fp_f"] += int(d["oracle_fired"])
                else:
                    c["rec_t"] += 1; c["rec_f"] += int(d["oracle_fired"])
        return c

    def _ci(k, n):
        p, lo, hi = _wilson(k, n)
        return f"{k}/{n} = {100*p:.0f}% [{100*lo:.0f}-{100*hi:.0f}]" if n else f"{k}/{n} = n/a"

    def _pct(k, n):
        return f"{k}/{n} ({100*k/n:.0f}%)" if n else f"{k}/{n} (n/a)"

    pooled = _tally(obs)
    L: List[str] = []
    L.append("# Expansion operators — REAL Nature-data prevalence\n")
    L.append(f"Real Nature source-data tables (same pipeline as the 77% headline, "
             f"nature_real_auto._build expansion=True). {len(items)} tasks across {arts} "
             f"independent articles x 2 prompts x {len(models)} models = "
             f"{len(items)*2*len(models)} generations. Models={models}. 95% Wilson CIs.\n")
    L.append("## Headline (pooled)")
    L.append(f"- ambiguous silent rate (REAL data): {_ci(pooled['amb_s'], pooled['amb_t'])}")
    L.append(f"- clarified silent rate: {_ci(pooled['clar_s'], pooled['clar_t'])}")
    L.append(f"- oracle FALSE-POSITIVE on real-correct results: {_ci(pooled['fp_f'], pooled['fp_t'])}")
    L.append(f"- oracle recall vs strict gold label: {_ci(pooled['rec_f'], pooled['rec_t'])}")
    L.append(f"- exec crashes (excluded): {pooled['crash']} of {len(items)*2*len(models)}\n")
    L.append("## Per-model")
    L.append("| model | ambiguous silent | clarified silent | oracle FP | crash |")
    L.append("|---|---|---|---|---|")
    for m in models:
        c = _tally([d for d in obs if d["model"] == m])
        L.append(f"| {m} | {_ci(c['amb_s'], c['amb_t'])} | {_ci(c['clar_s'], c['clar_t'])} "
                 f"| {_pct(c['fp_f'], c['fp_t'])} | {c['crash']} |")
    L.append("\n## Per-operator (pooled)")
    L.append("| operator | real tasks | ambiguous silent | oracle recall | oracle FP | crash |")
    L.append("|---|---|---|---|---|---|")
    for op in sorted(by_op):
        c = _tally([d for d in obs if d["op"] == op])
        L.append(f"| {op} | {by_op[op]} | {_pct(c['amb_s'], c['amb_t'])} "
                 f"| {_pct(c['rec_f'], c['rec_t'])} | {_pct(c['fp_f'], c['fp_t'])} | {c['crash']} |")
    report = "\n".join(L)
    (out_dir / "nature_expansion_report.md").write_text(report)
    print("\n" + report)
    print(f"\n[written] {out_dir/'nature_expansion_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
