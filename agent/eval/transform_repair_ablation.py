"""
transform_repair_ablation.py — §8 Experiment 2 (ablations; run AFTER Experiment 1 GO).

Two ablations, each reusing the Experiment-1 harness (eval/transform_repair.py):

(2b) single-agent vs dual-agent targeted repair  [--mode dual]
    Tests whether SPLITTING diagnosis from repair (the dual-agent positioning) is a
    real gain or a gimmick. The thesis says the headline is the typed-attribution
    SIGNAL, not the agent count — so dual-agent should be (at most) a small,
    cost-paying refinement, NOT the contribution. We test honestly either way.
      - single : one LLM call gets (buggy task + contract feedback) -> rewrite.
                 (identical to Experiment-1 arm B "targeted".)
      - dual   : Agent-A (diagnoser) LLM turns the raw contract report into a
                 structured fix instruction; Agent-B (repairer) LLM applies only
                 that instruction. 2 calls/round (2x cost).
    Metrics: success, rounds, llm-calls (cost), over-repair. If dual ~= single,
    that SUPPORTS "the signal matters, not the agent count" — dual stays an ablation.

(2a) abstain-aware repair routing (C3)            [--mode abstain]
    Tests that on operators OUTSIDE contract coverage, the router ABSTAINS to
    generic repair instead of forcing a targeted patch off a mis-localized cross-
    firing contract. We SIMULATE "uncovered" by removing the 5 scalability-family
    contracts from the oracle, then mix them with covered operators.
      - route (ours) : true-op contract applicable & fires -> targeted; else (abstain)
                       -> generic. Never repairs off a contract that doesn't apply.
      - force        : always targeted, building feedback from whatever contract
                       fires (on an uncovered op that is a CROSS-FIRE -> mis-repair).
      - generic      : generic everywhere (reference).
    Decisive metric: over-repair on the UNCOVERED subset (force should be worse;
    route should match generic there) while route keeps covered-subset success high.

Run:
  cd agent && python eval/transform_repair_ablation.py --mode dual    --offline
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/transform_repair_ablation.py --mode dual
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/transform_repair_ablation.py --mode abstain
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

import eval.transform_oracle as ORACLE  # noqa: E402
from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.transform_bench import _cases as bench_cases  # noqa: E402
from eval.scalability_demo import _cases as scal_cases  # noqa: E402
from eval.attribution_eval import _run_all_contracts  # noqa: E402
import eval.transform_repair as TR  # noqa: E402


# --------------------------------------------------------------------------- #
# (2b) dual-agent: diagnoser + repairer
# --------------------------------------------------------------------------- #
def _diagnose(item: Dict[str, Any], result: Optional[pd.DataFrame], model: str) -> str:
    """Agent-A: turn the raw goldless contract report into a short structured fix
    instruction (operator + exactly what to change). Goldless — only the contract."""
    from eval.ambiguity_calibration import _llm_code  # reuse the same chat plumbing
    op = item["op"]
    cr = oracle_check(op, TR._inp(item), item["params"], result)
    detail = cr.detail if cr is not None else "(operator not applicable / abstain)"
    # we abuse _llm_code's JSON discipline by asking for a {"code": "<diagnosis text>"}
    # envelope, so we get a clean string back through the same parser.
    probe = {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}
    msg = (f"A goldless semantic contract reports a violation in a pandas transform.\n"
           f"Operator at fault: `{op}`. Contract report: {detail}\n"
           f"Buggy result:\n{TR._preview(result)}\n"
           "State in ONE sentence the precise fix (which computation to change and how). "
           'Return ONLY JSON {"code": "<the one-sentence fix instruction>"}.')
    out = _llm_code(probe, msg, model)
    return (out or f"Fix the `{op}` computation per: {detail}").strip()


def _dual_step(item: Dict[str, Any], result: Optional[pd.DataFrame], model: str) -> Tuple[Optional[pd.DataFrame], int]:
    """One dual-agent round: diagnoser -> repairer. Returns (result, n_calls=2)."""
    diagnosis = _diagnose(item, result, model)
    feedback = (f"A diagnostician examined your result and identified the bug:\n{diagnosis}\n"
                f"Apply ONLY that fix; keep everything else. Previous result:\n{TR._preview(result)}")
    nxt, _ = TR._online_step(item, item["ambiguous"], feedback, model)
    return nxt, 2


def run_dual(item: Dict[str, Any], buggy: pd.DataFrame, rounds: int, model: str) -> Dict[str, Any]:
    from eval.ambiguity_calibration import _gold_correct
    cur = buggy.copy()
    calls = 0
    stop = "budget"
    for rnd in range(1, rounds + 1):
        nxt, c = _dual_step(item, cur, model)
        calls += c
        if nxt is None:
            stop = "malformed"
            break
        cur = nxt
        if not TR._true_op_fires(item, cur):
            stop = "contract_pass"
            break
    success = bool(_gold_correct(item, cur))
    over_a = 0 if success else max(0, TR._other_fires(item, cur) - TR._other_fires(item, buggy))
    return {"success": success, "rounds": rnd, "calls": calls, "over_repair_a": over_a, "stop_reason": stop}


def mode_dual(rounds: int, models: List[str], per_op: int, offline: bool, out_dir: str) -> Dict[str, Any]:
    seen: Counter = Counter()
    items: List[Dict[str, Any]] = []
    for c in bench_cases():
        seen[c["op"]] += 1
        if seen[c["op"]] > per_op:
            continue
        items.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})

    agg = {"single": defaultdict(float), "dual": defaultdict(float)}
    rows: List[Dict[str, Any]] = []
    n = 0
    for item in items:
        for model in models:
            buggy = TR._make_buggy_start(item, model, offline)
            if buggy is None or not TR._true_op_fires(item, buggy):
                continue
            n += 1
            single = TR.run_arm(item, "targeted", buggy.copy(), rounds, model, offline)
            dual = run_dual(item, buggy.copy(), rounds, model) if not offline else \
                {"success": True, "rounds": 1, "calls": 2, "over_repair_a": 0, "stop_reason": "contract_pass"}
            for k, r in (("single", single), ("dual", dual)):
                agg[k]["n"] += 1
                agg[k]["success"] += int(r["success"])
                agg[k]["rounds"] += r["rounds"]
                agg[k]["calls"] += r["calls"]
                agg[k]["over_a"] += r["over_repair_a"]
            rows.append({"case": item["name"], "model": model or "stub", "single": single, "dual": dual})
            print(f"[{n:3d}] {item['name']:22s} {model or 'stub':18s} "
                  f"single={int(single['success'])} dual={int(dual['success'])} "
                  f"calls(s/d)={single['calls']}/{dual['calls']}", file=sys.stderr, flush=True)

    lines = ["# Experiment 2b — single-agent vs dual-agent targeted repair"
             + ("  [OFFLINE STUB]" if offline else ""), ""]
    lines.append(f"N={n}  rounds={rounds}  models={[m or 'stub' for m in models]}")
    lines.append("")
    lines.append("| arm | success | mean rounds | mean llm-calls (cost) | over-repair(a) |")
    lines.append("|---|---|---|---|---|")
    for k in ("single", "dual"):
        d = agg[k]; nn = d["n"] or 1
        lines.append(f"| {k} | {TR._rate(d['success'], d['n'])} | {d['rounds']/nn:.2f} "
                     f"| {d['calls']/nn:.2f} | {TR._rate(d['over_a'], d['n'])} |")
    lines.append("")
    sS = agg["single"]["success"] / (agg["single"]["n"] or 1)
    sD = agg["dual"]["success"] / (agg["dual"]["n"] or 1)
    cS = agg["single"]["calls"] / (agg["single"]["n"] or 1)
    cD = agg["dual"]["calls"] / (agg["dual"]["n"] or 1)
    lines.append("## reading")
    lines.append(f"- single success {sS:.0%}, dual success {sD:.0%}; dual costs {cD/max(cS,1e-9):.1f}x the llm-calls.")
    if sD <= sS + 0.05:
        lines.append("- dual does NOT materially beat single -> SUPPORTS the thesis: the headline is the "
                     "typed-attribution SIGNAL, not the agent count. Dual-agent stays an ablation, not a contribution.")
    else:
        lines.append(f"- dual beats single by {sD-sS:+.0%} -> dual-agent is a real (cost-paying) refinement; "
                     "still positioned as mechanism, not headline.")
    text = "\n".join(lines)
    _write(out_dir, "ablation_dual", text, {"aggregate": {k: dict(agg[k]) for k in agg}, "cases": rows, "offline": offline})
    print(text)
    return {"text": text}


# --------------------------------------------------------------------------- #
# (2a) abstain-aware routing
# --------------------------------------------------------------------------- #
UNCOVERED = ["zscore_within_group", "dense_rank", "cumcount_per_group", "rank_pct", "clip_outlier"]


def _policy_arm(item: Dict[str, Any], buggy: pd.DataFrame, policy: str) -> str:
    """Decide which feedback arm to use for this case under a routing policy."""
    if policy == "generic":
        return "generic"
    if policy == "force":
        return "targeted"  # always targeted, even when the contract abstains (mis-localize)
    # policy == "route": targeted ONLY when the true-op contract is applicable & fires.
    return "targeted" if TR._true_op_fires(item, buggy) else "generic"


def mode_abstain(rounds: int, models: List[str], offline: bool, out_dir: str) -> Dict[str, Any]:
    # build mixed set: covered (core bench) + uncovered (scalability families)
    seen: Counter = Counter()
    covered: List[Dict[str, Any]] = []
    for c in bench_cases():
        if c["op"] in UNCOVERED:
            continue
        seen[c["op"]] += 1
        if seen[c["op"]] > 1:
            continue
        covered.append({**c, "name": f"{c['op']}#cov", "_covered": True})
    uncovered = [{**c, "name": f"{c['op']}#unc", "_covered": False} for c in scal_cases()]

    # SIMULATE "uncovered": remove their contracts from the oracle so the true-op
    # contract abstains (returns None) — exactly the coverage boundary of §2.4.
    removed = {op: ORACLE.CONTRACTS.pop(op) for op in UNCOVERED if op in ORACLE.CONTRACTS}
    try:
        items = covered + uncovered
        policies = ("generic", "force", "route")
        # agg split by covered/uncovered subset
        agg = {p: {"cov": defaultdict(float), "unc": defaultdict(float)} for p in policies}
        rows = []
        n = 0
        for item in items:
            sub = "cov" if item["_covered"] else "unc"
            for model in models:
                buggy = TR._make_buggy_start(item, model, offline)
                # for uncovered the contract is gone, so _true_op_fires can't gate the
                # silent-start filter; require exec-ok & gold-wrong instead.
                if buggy is None:
                    continue
                if item["_covered"] and not TR._true_op_fires(item, buggy):
                    continue
                n += 1
                rec = {"case": item["name"], "model": model or "stub", "sub": sub}
                for p in policies:
                    arm = _policy_arm(item, buggy, p)
                    r = TR.run_arm({**item, "op": item["op"]}, arm, buggy.copy(), rounds, model, offline)
                    a = agg[p][sub]
                    a["n"] += 1
                    a["success"] += int(r["success"])
                    a["over_a"] += r["over_repair_a"]
                    rec[p] = {"arm": arm, **{k: r[k] for k in ("success", "over_repair_a")}}
                rows.append(rec)
                print(f"[{n:3d}] {item['name']:22s} {model or 'stub':18s} sub={sub} "
                      f"route_arm={rec['route']['arm']}", file=sys.stderr, flush=True)
    finally:
        ORACLE.CONTRACTS.update(removed)  # restore

    lines = ["# Experiment 2a — abstain-aware repair routing (C3)"
             + ("  [OFFLINE STUB]" if offline else ""), ""]
    lines.append(f"N={n}  rounds={rounds}  uncovered(simulated)={UNCOVERED}")
    lines.append("")
    lines.append("| policy | covered success | covered over-repair | UNCOVERED success | UNCOVERED over-repair |")
    lines.append("|---|---|---|---|---|")
    for p in ("generic", "force", "route"):
        cov, unc = agg[p]["cov"], agg[p]["unc"]
        lines.append(f"| {p} | {TR._rate(cov['success'], cov['n'])} | {TR._rate(cov['over_a'], cov['n'])} "
                     f"| {TR._rate(unc['success'], unc['n'])} | {TR._rate(unc['over_a'], unc['n'])} |")
    lines.append("")
    # DATA-DRIVEN verdict (do not pre-assume the C3 win): the routing benefit holds only
    # if, on the UNCOVERED subset, route has LOWER over-repair than force AND route does
    # not lose much success, while keeping covered success == force.
    cov = {p: agg[p]["cov"] for p in ("generic", "force", "route")}
    unc = {p: agg[p]["unc"] for p in ("generic", "force", "route")}
    def _r(d):
        return (d["success"] / d["n"] if d["n"] else 0.0, d["over_a"] / d["n"] if d["n"] else 0.0)
    f_succ, f_over = _r(unc["force"]); r_succ, r_over = _r(unc["route"]); g_succ, _ = _r(unc["generic"])
    cov_ok = abs(_r(cov["route"])[0] - _r(cov["force"])[0]) < 1e-9
    routing_helps = (r_over < f_over - 1e-9) and (r_succ >= f_succ - 0.05)
    lines.append("## reading (data-driven)")
    lines.append(f"- COVERED: route success {_r(cov['route'])[0]:.0%} == force {_r(cov['force'])[0]:.0%} "
                 f"(route==targeted on covered) — {'OK' if cov_ok else 'MISMATCH'}.")
    lines.append(f"- UNCOVERED: force success {f_succ:.0%} / over-repair {f_over:.0%}; "
                 f"route success {r_succ:.0%} / over-repair {r_over:.0%}; generic success {g_succ:.0%}.")
    if routing_helps:
        lines.append("- => abstain-routing REDUCES mis-repair on uncovered operators (lower over-repair, no success "
                     "loss) while preserving covered success — C3 supported.")
    else:
        lines.append("- => abstain-routing did NOT show a repair-time safety benefit here: forcing targeted feedback "
                     "on uncovered operators did not raise the (proxy) over-repair and did not lose success "
                     f"(force {f_succ:.0%} vs route {r_succ:.0%}). HONEST READ: the over_a proxy (new fires of still-"
                     "covered contracts) under-measures mis-repair on uncovered ops, and degraded targeted feedback "
                     "was not harmful in this set. The abstain value is therefore a DETECTION-time property (FP≈0 on "
                     "uncovered, §3.7), NOT a demonstrated repair-time gain — C3 stays exploratory, not a claim.")
    text = "\n".join(lines)
    _write(out_dir, "ablation_abstain", text, {"aggregate": {p: {s: dict(agg[p][s]) for s in agg[p]} for p in agg},
                                               "cases": rows, "offline": offline})
    print(text)
    return {"text": text}


# --------------------------------------------------------------------------- #
def _write(out_dir: str, stem: str, text: str, payload: Dict[str, Any]) -> None:
    d = Path(__file__).resolve().parents[1] / out_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}_report.md").write_text(text + "\n", encoding="utf-8")
    (d / f"{stem}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Experiment 2 ablations: dual-agent / abstain-routing")
    ap.add_argument("--mode", choices=["dual", "abstain"], required=True)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--models", default=None)
    ap.add_argument("--per-op", type=int, default=2)
    ap.add_argument("--out", default="eval/results_repair_ablation")
    a = ap.parse_args(argv)

    if not a.offline and (not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY")):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (or --offline).")
        return 1
    from eval.ambiguity_calibration import MODELS
    models = [m.strip() for m in a.models.split(",")] if a.models else (MODELS if not a.offline else [None])

    if a.mode == "dual":
        mode_dual(a.rounds, models, a.per_op, a.offline, a.out)
    else:
        mode_abstain(a.rounds, models, a.offline, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
