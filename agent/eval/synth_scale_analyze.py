"""
synth_scale_analyze.py — pool cross-vendor goldless-contract synthesis (#3).

Reads results_autocontract_scale/synth_*_deleaked.json (one per vendor), pools the
per-operator CORE outcomes to N = n_ops x n_vendors (>=50), and reports per-vendor and
POOLED CORE recall with Wilson CI. CORE = the auto-synthesized contract fires on the
silent slip AND passes the correct implementation (the paper's headline synthesis metric).

Run: cd agent && python eval/synth_scale_analyze.py
"""
from __future__ import annotations
import argparse, glob, json, math
from pathlib import Path


def wilson(k, n):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n; z = 1.96; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * (c - h), 1), round(100 * (c + h), 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="eval/results_autocontract_scale/synth_*_deleaked.json")
    ap.add_argument("--out", default="eval/results_autocontract_scale/SYNTH_SCALE_SUMMARY.md")
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(a.glob) if "SUMMARY" not in f)
    if not files:
        raise SystemExit(f"no files match {a.glob}")

    per_vendor, pooled = [], []
    for f in files:
        d = json.load(open(f))
        model = d.get("model", Path(f).stem)
        cases = d.get("cases", [])
        for c in cases:
            c["_model"] = model
        pooled.extend(cases)
        n = len(cases)
        core = sum(int(c.get("core_correct", False)) for c in cases)
        full = sum(int(c.get("correct", False)) for c in cases)
        per_vendor.append({"model": model, "n": n, "core": core, "full": full})

    N = len(pooled)
    CORE = sum(int(c.get("core_correct", False)) for c in pooled)
    FULL = sum(int(c.get("correct", False)) for c in pooled)

    lines = ["# Goldless contract synthesis at scale (cross-vendor, de-leaked intent)\n"]
    lines.append(f"Pooled N = {N} ({len(files)} vendors x ~{N // max(len(files),1)} operators), "
                 "de-leaked high-level-goal intent (no formula, no operator keyword).\n")
    lines.append("| vendor | N | CORE (fire-slip & pass-correct) | FULL (+ alt-robust) |")
    lines.append("|---|---|---|---|")
    for v in per_vendor:
        cc = wilson(v["core"], v["n"]); ff = wilson(v["full"], v["n"])
        lines.append(f"| {v['model']} | {v['n']} | {v['core']}/{v['n']} = {cc[0]}% [{cc[1]}-{cc[2]}] "
                     f"| {v['full']}/{v['n']} = {ff[0]}% [{ff[1]}-{ff[2]}] |")
    cc = wilson(CORE, N); ff = wilson(FULL, N)
    lines.append(f"| **POOLED** | **{N}** | **{CORE}/{N} = {cc[0]}% [{cc[1]}-{cc[2]}]** "
                 f"| **{FULL}/{N} = {ff[0]}% [{ff[1]}-{ff[2]}]** |")
    Path(a.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    js = a.out.replace(".md", ".json")
    json.dump({"pooled_n": N, "core": [CORE, N], "full": [FULL, N],
               "core_ci": wilson(CORE, N), "per_vendor": per_vendor}, open(js, "w"), indent=2)
    print(f"\n-> {a.out}")


if __name__ == "__main__":
    raise SystemExit(main())
