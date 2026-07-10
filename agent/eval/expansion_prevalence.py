"""
expansion_prevalence.py — REAL-LLM silent-error prevalence for the 10 expansion operators.

Turns the offline method-viability probe (operator_expansion.py) into a measured
prevalence: a real model GENERATES pandas code from an (ambiguous | clarified) prompt,
we EXECUTE it on the pre-injected frames, LABEL correct/silent against the hand gold
(label only), and run the GOLDLESS oracle contract for detection. Same protocol as
ambiguity_calibration.py, but (a) restricted to the new expansion operators and (b)
backed by the local `opencode` CLI so it runs without cloud LLM_API_BASE/KEY.

Per operator it reports: ambiguous vs clarified silent rate, oracle recall on real
silent errors, and oracle false-positive on real-correct results.

Run:
  cd agent && python eval/expansion_prevalence.py --max-per-op 1 \
      --models opencode/north-mini-code-free
"""
from __future__ import annotations

import argparse
import codecs
import json
import math
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.transform_bench import expansion_cases  # noqa: E402
from eval.ambiguity_calibration import _sanitize_code, _exec, _gold_correct  # noqa: E402

# the 10 expansion operators that map to NL->pandas-on-DataFrame generation
EXPANSION_OPS = [
    "index_align", "dtype_coerce", "groupby_dropna_key", "order_dependent_dedup",
    "resample_boundary", "string_normalize_join", "join_fanout", "null_in_agg_count",
    "scale_before_split_leakage", "lookahead_return",
]


def _prompt(item: Dict[str, Any], prompt_text: str) -> str:
    cols = list(item["df"].columns)
    extra = f"\nA second dataframe `df2` columns={list(item['df2'].columns)}." if "df2" in item else ""
    dfref = "`df`/`df2`" if "df2" in item else "`df`"
    return (
        f"pandas `df` columns={cols}.{extra}\n{prompt_text}\n"
        f"The dataframe(s) {dfref} ALREADY EXIST in scope with the real data.\n"
        f"Do NOT re-create or re-assign them, do NOT import anything, do NOT print.\n"
        f"Use only the given {dfref}, assign the final answer to `result`.\n"
        f'Return ONLY strict JSON: {{"code": "<pandas code defining result>"}}.'
    )


def _extract_code(out: str) -> Optional[str]:
    out = (out or "").strip()
    if not out:
        return None
    # 1) JSON object with a "code" field (tolerates trailing junk / minor malformation)
    m = re.search(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"', out, re.S)
    if m:
        try:
            return codecs.decode(m.group(1), "unicode_escape")
        except Exception:
            return m.group(1)
    # 2) fenced code block
    m = re.search(r"```(?:python)?\s*\n(.*?)```", out, re.S)
    if m:
        return m.group(1)
    # 3) raw code that at least assigns result
    if re.search(r"\bresult\s*=", out):
        return out
    return None


def _oc_code(item: Dict[str, Any], prompt_text: str, model: str, timeout: int = 180) -> Optional[str]:
    prompt = _prompt(item, prompt_text)
    try:
        p = subprocess.run(["opencode", "run", "-m", model, prompt],
                           capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    return _extract_code(p.stdout)


def _wilson(k: int, n: int, z: float = 1.96):
    """Wilson 95% CI (matches the project's other reports). Returns (p, lo, hi) in [0,1]."""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / den
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Real-LLM prevalence for expansion operators (opencode-backed)")
    ap.add_argument("--out", default="eval/results_expansion")
    ap.add_argument("--models", default="opencode/north-mini-code-free",
                    help="comma-separated opencode model ids")
    ap.add_argument("--max-per-op", type=int, default=1, help="instances per operator (1..2)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--attempts", type=int, default=2,
                    help="retries to obtain a RUNNABLE program (crashes excluded from silent rate)")
    ap.add_argument("--backend", choices=("opencode", "api"), default="opencode",
                    help="opencode: local free models (no key). api: cloud frontier models via "
                         "LLM_API_BASE/LLM_API_KEY (one command to run GPT-5.x/Claude on this grid).")
    args = ap.parse_args(argv)
    if args.backend == "api":
        import os
        if not (os.getenv("LLM_API_BASE") and os.getenv("LLM_API_KEY")):
            print("[error] --backend api needs LLM_API_BASE / LLM_API_KEY in the environment.")
            return 1
        from eval.ambiguity_calibration import _llm_code as _gen_api  # noqa
        _gen = lambda item, prompt, model: _gen_api(item, prompt, model)  # noqa: E731
    else:
        _gen = lambda item, prompt, model: _oc_code(item, prompt, model, timeout=args.timeout)  # noqa: E731
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    seen: Dict[str, int] = defaultdict(int)
    items: List[Dict[str, Any]] = []
    for c in expansion_cases():
        if c["op"] not in EXPANSION_OPS:
            continue
        seen[c["op"]] += 1
        if seen[c["op"]] > args.max_per_op:
            continue
        items.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})
    print(f"[grid] {len(items)} cases x 2 prompts x {len(models)} models "
          f"(attempts={args.attempts}); models={models}", flush=True)

    rows: List[Dict[str, Any]] = []
    obs: List[Dict[str, Any]] = []  # flat observations for slice-and-dice aggregation
    for item in items:
        op = item["op"]
        rec: Dict[str, Any] = {"item": item["name"], "op": op}
        inp = {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}
        for cond in ("ambiguous", "clarified"):
            for m in models:
                code = result = None
                for _ in range(max(1, args.attempts)):
                    code = _gen(item, item[cond], m)
                    result = _exec(item, code) if code else None
                    if result is not None:
                        break  # got a runnable program; keep it
                exec_ok = result is not None
                correct = bool(exec_ok and _gold_correct(item, result))
                oc = oracle_check(op, inp, item["params"], result)
                fired = bool(oc and oc.fired)
                tag = "ok" if correct else ("SILENT" if exec_ok else "crash")
                print(f"[{item['name']:26}] {cond:9} {m:34} {tag:7} fired={fired}", flush=True)
                d = {"tag": tag, "oracle_fired": fired, "exec_ok": exec_ok,
                     "correct": correct, "code": (code or "")[:400]}
                rec.setdefault(cond, {})[m] = d
                obs.append({"op": op, "model": m, "cond": cond,
                            "exec_ok": exec_ok, "correct": correct, "oracle_fired": fired})
        rows.append(rec)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    # persist raw generations BEFORE building the report, so a long multi-model run is
    # never lost to a downstream formatting error.
    (out_dir / "prevalence_records.json").write_text(json.dumps(rows, indent=2, default=str))

    # ---- aggregation over flat observations ----
    def _tally(sub: List[Dict[str, Any]]) -> Dict[str, int]:
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
    lines: List[str] = []
    lines.append("# Expansion operators — REAL-LLM silent-error prevalence (cross-model)\n")
    lines.append(f"Generator: {models} (attempts={args.attempts}). "
                 f"{len(items)} cases x 2 prompts x {len(models)} models = "
                 f"{len(items)*2*len(models)} generations. Same protocol as ambiguity_calibration "
                 f"(generate -> exec -> label vs gold -> goldless oracle). 95% Wilson CIs.\n")
    lines.append("## Headline (pooled across models)")
    lines.append(f"- ambiguous silent rate: {_ci(pooled['amb_s'], pooled['amb_t'])}")
    lines.append(f"- clarified silent rate: {_ci(pooled['clar_s'], pooled['clar_t'])} "
                 f"(drop => genuine model semantic failure, fixable by intent)")
    lines.append(f"- oracle FALSE-POSITIVE on real-correct results: {_ci(pooled['fp_f'], pooled['fp_t'])} "
                 f"(the trustworthy oracle-quality metric)")
    lines.append(f"- oracle recall vs strict gold label: {_ci(pooled['rec_f'], pooled['rec_t'])} "
                 f"(understated by gold-format artifacts — see EXPANSION_SUMMARY)")
    lines.append(f"- exec crashes (loud, excluded from silent): {pooled['crash']} "
                 f"of {len(items)*2*len(models)}\n")

    lines.append("## Per-model (is the phenomenon model-specific?)")
    lines.append("| model | ambiguous silent | clarified silent | oracle FP | crash |")
    lines.append("|-------|------------------|------------------|-----------|-------|")
    for m in models:
        c = _tally([d for d in obs if d["model"] == m])
        lines.append(f"| {m} | {_ci(c['amb_s'], c['amb_t'])} | {_ci(c['clar_s'], c['clar_t'])} "
                     f"| {_pct(c['fp_f'], c['fp_t'])} | {c['crash']} |")

    lines.append("\n## Per-operator (pooled across models)")
    lines.append("| operator | ambiguous silent | clarified silent | oracle recall | oracle FP | crash |")
    lines.append("|----------|------------------|------------------|---------------|-----------|-------|")
    for op in EXPANSION_OPS:
        c = _tally([d for d in obs if d["op"] == op])
        lines.append(f"| {op} | {_pct(c['amb_s'], c['amb_t'])} | {_pct(c['clar_s'], c['clar_t'])} "
                     f"| {_pct(c['rec_f'], c['rec_t'])} | {_pct(c['fp_f'], c['fp_t'])} | {c['crash']} |")
    report = "\n".join(lines)

    (out_dir / "prevalence_report.md").write_text(report)
    print("\n" + report)
    print(f"\n[written] {out_dir/'prevalence_report.md'}\n[written] {out_dir/'prevalence_records.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
