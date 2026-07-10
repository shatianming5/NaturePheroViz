"""
eval_dpo.py — held-out Repair-DPO evaluation. Runs on gpudev2 (offline).

Three arms on the SAME frozen buggy start per held-out case (so every arm repairs
the identical silent error), greedy decode:

  base_generic   : base model + generic "you may be wrong" feedback  (no-typed lower bound)
  base_targeted  : base model + goldless typed-contract feedback     (no-train baseline)
  tuned_targeted : DPO-LoRA model + the same typed feedback           (ours)

Success is the HIDDEN gold (ambiguity_calibration._gold_correct), never shown to any
model. We also report the goldless contract-pass rate and over-repair (a NEW other-
contract fire on a non-correct commit). Wilson 95% CIs; the honest question is whether
tuned_targeted > base_targeted.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dpo_common as D  # noqa: E402

import eval.transform_repair as R  # noqa: E402
from eval.ambiguity_calibration import _gold_correct  # noqa: E402


def wilson(k: int, n: int):
    if n == 0:
        return (0.0, 0.0, 0.0)
    z = 1.96
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(p, 3), round((c - h) / d, 3), round((c + h) / d, 3))


def score(item, buggy_res, result):
    """Return (success, contract_pass, over_repair) for a committed repair."""
    success = False
    try:
        success = bool(_gold_correct(item, result)) if result is not None else False
    except Exception:
        success = False
    contract_pass = (result is not None) and (not R._true_op_fires(item, result))
    over = 0
    if not success and result is not None:
        over = len(R._other_fire_set(item, result) - R._other_fire_set(item, buggy_res))
    return success, contract_pass, int(over > 0)


def bestn(g, prompt, item, buggy_res, n, temp):
    """Best-of-N with GOLDLESS contract-gated selection: sample n repairs, commit the
    FIRST whose executed result passes the true-op contract (else candidate 0). Score the
    committed pick by hidden gold. `any_gold` = a gold-correct repair existed among the n
    (the reachable ceiling; independent of selection)."""
    cands = g.generate(prompt, n=n, temperature=temp, seed=17)
    results = [D._exec_safe(item, D.extract_code(t)) for t in cands]
    pick = None
    for res in results:
        if res is not None and not R._true_op_fires(item, res):
            pick = res; break
    if pick is None:
        pick = results[0] if results else None
    s, cp, ov = score(item, buggy_res, pick)
    any_gold = False
    for res in results:
        try:
            if res is not None and _gold_correct(item, res):
                any_gold = True; break
        except Exception:
            pass
    return s, cp, ov, any_gold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", required=True, help="DPO LoRA adapter dir")
    ap.add_argument("--split", required=True, help="split.json from build_pairs")
    ap.add_argument("--out", default="eval_out")
    ap.add_argument("--max-cases", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=640)
    ap.add_argument("--sample-n", type=int, default=6, help="best-of-N candidates")
    ap.add_argument("--sample-temp", type=float, default=0.8)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    heldout_uids = set(json.loads(Path(args.split).read_text())["heldout_uids"])
    cases = [c for c in D.all_cases() if c["_uid"] in heldout_uids]
    if args.max_cases:
        cases = cases[: args.max_cases]
    print(f"[eval] {len(cases)} held-out cases, {len(set(c['op'] for c in cases))} ops",
          flush=True)

    print("[load] base", flush=True)
    base = D.HFGen(args.model, max_new_tokens=args.max_new_tokens)
    print("[load] tuned (base+adapter)", flush=True)
    tuned = D.HFGen(args.model, max_new_tokens=args.max_new_tokens, adapter=args.adapter)

    arms = {"base_generic": [], "base_targeted": [], "tuned_targeted": [],
            "base_bestN": [], "tuned_bestN": []}
    over = {k: [] for k in arms}
    cpass = {k: [] for k in arms}
    extra = {"base_anygold": [], "tuned_anygold": []}  # ceiling: a gold repair exists in N
    records = []
    n_eval = 0
    for i, item in enumerate(cases):
        bug = D.make_buggy(item, base)  # base elicits the shared bug
        if bug is None:
            records.append({"uid": item["_uid"], "note": "no_firing_buggy_start"})
            print(f"[{i+1}/{len(cases)}] {item['_uid']:<28} SKIP (no firing bug)", flush=True)
            continue
        buggy_res, _ = bug
        fb_t = R.fb_targeted(item, buggy_res)
        fb_g = R.fb_generic(item, buggy_res)
        plans = {
            "base_generic": (base, D.repair_prompt(item, fb_g)),
            "base_targeted": (base, D.repair_prompt(item, fb_t)),
            "tuned_targeted": (tuned, D.repair_prompt(item, fb_t)),
        }
        rec = {"uid": item["_uid"], "op": item["op"]}
        for arm, (g, prompt) in plans.items():
            txt = g.generate(prompt, n=1, temperature=0.0)[0]
            res = D._exec_safe(item, D.extract_code(txt))
            s, cp, ov = score(item, buggy_res, res)
            arms[arm].append(int(s)); cpass[arm].append(int(cp)); over[arm].append(ov)
            rec[arm] = {"success": s, "contract_pass": cp, "over_repair": ov}
        # best-of-N, contract-GATED selection (deployment-realistic, goldless): sample N
        # repairs, commit the FIRST that passes the goldless contract (else candidate 0).
        prompt_t = D.repair_prompt(item, fb_t)
        for arm, g in (("base_bestN", base), ("tuned_bestN", tuned)):
            s, cp, ov, anyg = bestn(g, prompt_t, item, buggy_res,
                                    args.sample_n, args.sample_temp)
            arms[arm].append(int(s)); cpass[arm].append(int(cp)); over[arm].append(ov)
            extra["base_anygold" if arm == "base_bestN" else "tuned_anygold"].append(int(anyg))
            rec[arm] = {"success": s, "contract_pass": cp, "over_repair": ov, "any_gold": anyg}
        records.append(rec); n_eval += 1
        print(f"[{i+1}/{len(cases)}] {item['_uid']:<26} "
              f"g={rec['base_generic']['success']:d} "
              f"bt={rec['base_targeted']['success']:d} "
              f"tt={rec['tuned_targeted']['success']:d} | "
              f"bN={rec['base_bestN']['success']:d} "
              f"tN={rec['tuned_bestN']['success']:d}", flush=True)

    summary = {"n_eval": n_eval, "arms": {}}
    for arm in arms:
        k = sum(arms[arm]); n = len(arms[arm])
        p, lo, hi = wilson(k, n)
        summary["arms"][arm] = {
            "success": p, "success_ci": [lo, hi], "n": n, "k": k,
            "contract_pass_rate": round(sum(cpass[arm]) / n, 3) if n else None,
            "over_repair_rate": round(sum(over[arm]) / n, 3) if n else None}
    bt = summary["arms"]["base_targeted"]; tt = summary["arms"]["tuned_targeted"]
    summary["delta_tuned_minus_base_targeted"] = round(tt["success"] - bt["success"], 3)
    summary["disjoint_ci"] = tt["success_ci"][0] > bt["success_ci"][1] or \
        bt["success_ci"][0] > tt["success_ci"][1]
    bn = summary["arms"]["base_bestN"]; tn = summary["arms"]["tuned_bestN"]
    summary["delta_tuned_minus_base_bestN"] = round(tn["success"] - bn["success"], 3)
    summary["disjoint_ci_bestN"] = tn["success_ci"][0] > bn["success_ci"][1] or \
        bn["success_ci"][0] > tn["success_ci"][1]
    n = summary["n_eval"] or 1
    summary["ceiling_any_gold_in_N"] = {
        "base": round(sum(extra["base_anygold"]) / n, 3),
        "tuned": round(sum(extra["tuned_anygold"]) / n, 3)}

    (out / "eval_records.json").write_text(json.dumps(records, indent=2))
    (out / "eval_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n==== HELD-OUT REPAIR (hidden-gold success) ====", flush=True)
    for arm, s in summary["arms"].items():
        print(f"  {arm:<16} {s['success']*100:5.1f}%  CI[{s['success_ci'][0]*100:.0f},"
              f"{s['success_ci'][1]*100:.0f}]  contract_pass={s['contract_pass_rate']}  "
              f"over_repair={s['over_repair_rate']}  (k={s['k']}/{s['n']})", flush=True)
    print(f"  greedy delta(tuned-base_targeted) = {summary['delta_tuned_minus_base_targeted']*100:+.1f} pts"
          f"  disjoint_CI={summary['disjoint_ci']}", flush=True)
    print(f"  best-of-{args.sample_n} delta(tuned-base) = {summary['delta_tuned_minus_base_bestN']*100:+.1f} pts"
          f"  disjoint_CI={summary['disjoint_ci_bestN']}", flush=True)
    print(f"  ceiling (any gold-correct in {args.sample_n}): base={summary['ceiling_any_gold_in_N']['base']} "
          f"tuned={summary['ceiling_any_gold_in_N']['tuned']}", flush=True)
    return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
