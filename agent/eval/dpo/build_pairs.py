"""
build_pairs.py — generate on-policy Repair-DPO preference pairs, labelled by the
GOLDLESS operator contract (no gold, no proxy). Runs on gpudev2 (offline).

For each TRAIN case, for each of --n-bugs distinct buggy starts:
  1. elicit a buggy start (exec-ok, gold-wrong, true-op contract FIRES);
  2. build the targeted-feedback repair prompt (the deployed 8.4 prompt);
  3. sample K repair candidates from the base model (temp>0);
  4. label each executed candidate by the goldless contract:
       chosen  <- true-op contract no longer FIRES  (a fix);
       rejected<- contract still FIRES               (silent error persists);
  5. fallbacks so a pair can form: extra high-temp samples for rejected, the buggy
     start's own code for rejected, and a gold-GUIDED (ceiling) teacher turn for chosen;
  6. emit up to --pairs-per-case (prompt, chosen, rejected) rows (conversational).

Output: pairs.jsonl (+ split.json with heldout uids, + build_stats.json/summary).
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dpo_common as D  # noqa: E402

import eval.transform_repair as R  # noqa: E402


def as_msgs(user: str, assistant: str):
    return ([{"role": "user", "content": user}],
            [{"role": "assistant", "content": assistant}])


def build_for_bug(item, gen, buggy_res, buggy_code, k, hi_temp, temp):
    """Return (prompt, chosen_list, rejected_list, pass_rate) for one buggy start."""
    fb = R.fb_targeted(item, buggy_res)
    prompt = D.repair_prompt(item, fb)
    chosen, rejected = [], []
    n_pass = 0
    for txt in gen.generate(prompt, n=k, temperature=temp, seed=7):
        res = D._exec_safe(item, D.extract_code(txt))
        if D.clean_pass(item, res, buggy_res):
            n_pass += 1; chosen.append(txt.strip())
        elif (res is not None and R._true_op_fires(item, res)) or D.extract_code(txt) is None:
            rejected.append(txt.strip())
    if not rejected:  # extra rejected via high-temp sampling
        for txt in gen.generate(prompt, n=max(4, k // 2), temperature=hi_temp, seed=13):
            res = D._exec_safe(item, D.extract_code(txt))
            if (res is not None and R._true_op_fires(item, res)) or D.extract_code(txt) is None:
                rejected.append(txt.strip())
    if not rejected and buggy_code and buggy_code != "<perturbation>":
        rejected.append(json.dumps({"code": buggy_code}))  # buggy start's own firing code
    if not chosen:  # gold-GUIDED (ceiling) teacher chosen
        tprompt = D.repair_prompt(item, R.fb_ceiling(item, buggy_res))
        for t in gen.generate(tprompt, n=5, temperature=0.6, seed=11):
            if D.clean_pass(item, D._exec_safe(item, D.extract_code(t)), buggy_res):
                chosen.append(t.strip())
    return prompt, _dedup(chosen), _dedup(rejected), round(n_pass / max(1, k), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", default="pairs")
    ap.add_argument("--k", type=int, default=12, help="repair candidates per buggy start")
    ap.add_argument("--n-bugs", type=int, default=3, help="distinct buggy starts per case")
    ap.add_argument("--pairs-per-case", type=int, default=8)
    ap.add_argument("--temp", type=float, default=0.9)
    ap.add_argument("--hi-temp", type=float, default=1.15)
    ap.add_argument("--heldout-frac", type=float, default=0.30)
    ap.add_argument("--max-cases", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=640)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    cases = D.all_cases()
    train, held = D.split_cases(cases, heldout_frac=args.heldout_frac)
    (out / "split.json").write_text(json.dumps({
        "heldout_frac": args.heldout_frac,
        "train_uids": [c["_uid"] for c in train],
        "heldout_uids": [c["_uid"] for c in held]}, indent=2))
    if args.max_cases:
        train = train[: args.max_cases]
    print(f"[split] {len(train)} train / {len(held)} heldout cases "
          f"({len(cases)} total, {len(set(c['op'] for c in cases))} ops)", flush=True)
    print(f"[load] {args.model}", flush=True)
    gen = D.HFGen(args.model, max_new_tokens=args.max_new_tokens)

    pf = (out / "pairs.jsonl").open("w")
    stats, n_pairs = [], 0
    for i, item in enumerate(train):
        rec = {"uid": item["_uid"], "op": item["op"], "n_pairs": 0,
               "n_chosen": 0, "n_rejected": 0, "passes": [], "note": ""}
        try:
            case_pairs = []
            for b in range(args.n_bugs):
                bug = D.make_buggy(item, gen, seed_base=100 + 40 * b)
                if bug is None:
                    continue
                buggy_res, buggy_code = bug
                prompt, chosen, rejected, pr = build_for_bug(
                    item, gen, buggy_res, buggy_code, args.k, args.hi_temp, args.temp)
                rec["passes"].append(pr)
                rec["n_chosen"] += len(chosen); rec["n_rejected"] += len(rejected)
                for ch, rj in list(product(chosen, rejected)):
                    case_pairs.append((prompt, ch, rj))
            if not case_pairs and not rec["passes"]:
                rec["note"] = "no_firing_buggy_start"
            case_pairs = _cap(case_pairs, args.pairs_per_case)
            for prompt, ch, rj in case_pairs:
                p_msgs, ch_msgs = as_msgs(prompt, ch)
                _, rj_msgs = as_msgs(prompt, rj)
                pf.write(json.dumps({"prompt": p_msgs, "chosen": ch_msgs,
                                     "rejected": rj_msgs}) + "\n")
            pf.flush()
            rec["n_pairs"] = len(case_pairs); n_pairs += len(case_pairs)
        except Exception as e:  # noqa: BLE001
            rec["note"] = f"error:{type(e).__name__}:{e}"[:160]
        stats.append(rec)
        pm = round(sum(rec["passes"]) / len(rec["passes"]), 2) if rec["passes"] else None
        print(f"[{i+1}/{len(train)}] {rec['uid']:<26} pass={pm} "
              f"chosen={rec['n_chosen']} rej={rec['n_rejected']} pairs={rec['n_pairs']} "
              f"{rec['note']}", flush=True)

    pf.close()
    (out / "build_stats.json").write_text(json.dumps(stats, indent=2))
    allp = [p for s in stats for p in s["passes"]]
    summary = {"n_train_cases": len(train), "n_pairs": n_pairs,
               "cases_with_pairs": sum(1 for s in stats if s["n_pairs"] > 0),
               "base_targeted_pass_mean": round(sum(allp) / len(allp), 3) if allp else None}
    (out / "build_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[done] {n_pairs} pairs from {summary['cases_with_pairs']}/{len(train)} cases; "
          f"base targeted pass mean={summary['base_targeted_pass_mean']}", flush=True)
    return 0


def _cap(pairs, n):
    if len(pairs) <= n:
        return pairs
    step = len(pairs) / n
    return [pairs[int(j * step)] for j in range(n)]


def _dedup(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
