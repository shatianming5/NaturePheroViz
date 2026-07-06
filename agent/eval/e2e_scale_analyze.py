"""
e2e_scale_analyze.py — aggregate cross-vendor end-to-end runs (#3) and decompose the
end-to-end miss into operator-inference vs contract-synthesis failures (#4).

Reads every results_e2e_scale/e2e_*.json produced by e2e_pipeline.py (one per vendor),
pools the per-case records to N = n_ops x n_vendors (>=50), and reports:
  - per-vendor and POOLED operator-inference / contract-synth / full-system with Wilson CI
  - a decomposition of every full-system MISS into:
      OP-only   : operator inferred wrong, but the (oracle) contract would have fired
      SYNTH-only: operator inferred right, but the synthesized contract failed
      BOTH      : operator wrong AND contract failed
No LLM calls; pure post-processing of the cached JSON, so a reviewer can re-derive it.

Run: cd agent && python eval/e2e_scale_analyze.py --glob 'eval/results_e2e_scale/e2e_*.json'
"""
from __future__ import annotations
import argparse, glob, json, math
from pathlib import Path


def wilson(k, n):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * (c - h), 1), round(100 * (c + h), 1))


def classify_miss(rec):
    op_ok = bool(rec.get("op_correct"))
    core = bool(rec.get("core"))
    if op_ok and core:
        return None  # system-ok, not a miss
    if not op_ok and core:
        return "OP_only"
    if op_ok and not core:
        return "SYNTH_only"
    return "BOTH"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="eval/results_e2e_scale/e2e_*.json")
    ap.add_argument("--out", default="eval/results_e2e_scale/E2E_SCALE_SUMMARY.md")
    a = ap.parse_args()

    files = sorted(glob.glob(a.glob))
    files = [f for f in files if "SCALE" not in f]
    if not files:
        raise SystemExit(f"no files match {a.glob}")

    per_vendor = []
    pooled = []
    for f in files:
        d = json.load(open(f))
        model = d.get("model", Path(f).stem)
        cases = d.get("cases", [])
        for c in cases:
            c["_model"] = model
        pooled.extend(cases)
        n = len(cases)
        op_ok = sum(int(c.get("op_correct", False)) for c in cases)
        core = sum(int(c.get("core", False)) for c in cases)
        full = sum(int(c.get("system_ok", False)) for c in cases)
        per_vendor.append({"model": model, "n": n, "op_ok": op_ok, "core": core, "full": full})

    N = len(pooled)
    OP = sum(int(c.get("op_correct", False)) for c in pooled)
    CORE = sum(int(c.get("core", False)) for c in pooled)
    FULL = sum(int(c.get("system_ok", False)) for c in pooled)
    # contract-synth given the operator is correct (isolates the synth stage)
    op_right = [c for c in pooled if c.get("op_correct")]
    CORE_GIVEN_OP = sum(int(c.get("core", False)) for c in op_right)

    misses = [c for c in pooled if not c.get("system_ok")]
    dec = {"OP_only": 0, "SYNTH_only": 0, "BOTH": 0}
    for c in misses:
        k = classify_miss(c)
        if k:
            dec[k] += 1

    lines = []
    lines.append("# End-to-end scale + miss decomposition (cross-vendor)\n")
    lines.append(f"Pooled N = {N} ({len(files)} vendors x ~{N // max(len(files),1)} operators). "
                 "Generated-fixture path (real Nature corpus not required); messy NL cached & shared "
                 "across vendors for a fair comparison.\n")
    lines.append("## Per-vendor\n")
    lines.append("| vendor | N | op-infer | contract-synth CORE | full-system |")
    lines.append("|---|---|---|---|---|")
    for v in per_vendor:
        oi = wilson(v["op_ok"], v["n"]); cs = wilson(v["core"], v["n"]); fs = wilson(v["full"], v["n"])
        lines.append(f"| {v['model']} | {v['n']} | {v['op_ok']}/{v['n']} = {oi[0]}% [{oi[1]}-{oi[2]}] "
                     f"| {v['core']}/{v['n']} = {cs[0]}% [{cs[1]}-{cs[2]}] "
                     f"| {v['full']}/{v['n']} = {fs[0]}% [{fs[1]}-{fs[2]}] |")
    oi = wilson(OP, N); cs = wilson(CORE, N); fs = wilson(FULL, N); cg = wilson(CORE_GIVEN_OP, len(op_right))
    lines.append(f"| **POOLED** | **{N}** | **{OP}/{N} = {oi[0]}% [{oi[1]}-{oi[2]}]** "
                 f"| **{CORE}/{N} = {cs[0]}% [{cs[1]}-{cs[2]}]** "
                 f"| **{FULL}/{N} = {fs[0]}% [{fs[1]}-{fs[2]}]** |")
    lines.append(f"\nContract-synth CORE *given the operator is correct*: "
                 f"{CORE_GIVEN_OP}/{len(op_right)} = {cg[0]}% [{cg[1]}-{cg[2]}] "
                 "(isolates the synthesis stage from operator inference).\n")

    tot = max(len(misses), 1)
    lines.append("## Where the end-to-end miss comes from (decomposition)\n")
    lines.append(f"Of {len(misses)} full-system misses (pooled), split by failing stage:\n")
    lines.append("| failing stage | count | share of misses |")
    lines.append("|---|---|---|")
    lines.append(f"| operator-inference only (contract would fire) | {dec['OP_only']} | {round(100*dec['OP_only']/tot)}% |")
    lines.append(f"| contract-synthesis only (operator correct) | {dec['SYNTH_only']} | {round(100*dec['SYNTH_only']/tot)}% |")
    lines.append(f"| both stages fail | {dec['BOTH']} | {round(100*dec['BOTH']/tot)}% |")
    lines.append("\n## Per-operator miss attribution (pooled)\n")
    lines.append("| operator | trials | full-ok | dominant failure |")
    lines.append("|---|---|---|---|")
    ops = {}
    for c in pooled:
        ops.setdefault(c["op"], []).append(c)
    for op in sorted(ops):
        cs_ = ops[op]
        nn = len(cs_); ok = sum(int(x.get("system_ok", False)) for x in cs_)
        ms = [classify_miss(x) for x in cs_ if not x.get("system_ok")]
        ms = [m for m in ms if m]
        dom = max(set(ms), key=ms.count) if ms else "-"
        lines.append(f"| {op} | {nn} | {ok}/{nn} | {dom} |")

    outp = Path(a.out)
    outp.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\n-> {outp}")
    js = a.out.replace(".md", ".json")
    json.dump({"pooled_n": N, "op_infer": [OP, N], "synth_core": [CORE, N],
               "synth_core_given_op": [CORE_GIVEN_OP, len(op_right)],
               "full_system": [FULL, N], "decomposition": dec,
               "per_vendor": per_vendor}, open(js, "w"), indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
