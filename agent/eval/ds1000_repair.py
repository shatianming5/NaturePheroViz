"""
ds1000_repair.py — EXTERNAL validity for C2 (targeted repair), symmetric to what
§1.3.2 did for detection.

§1.3.2 showed the silent-error PHENOMENON replicates on external DS-1000 tasks
(real StackOverflow intents, DS-1000's own gold). This asks the repair question
on that same external corpus: when a model produces a silent error on a real
DS-1000 task, does our typed-attribution TARGETED repair fix it better than
generic self-repair?

Design (mirrors exp1 but on external tasks with EXTERNAL gold):
  * Start    = a model solution that is exec-ok but SILENT (DS-1000's own test
               cases fail) — a genuine external silent error.
  * Success  = DS-1000's OWN gold (all test cases pass after repair). We never
               author the gold.
  * generic arm  : re-prompt with generic "your result may be wrong" feedback.
  * targeted arm : run our goldless diagnoser (transform_repair_policy.diagnose)
                   on (df, result); if a contract fires, feed its typed invariant
                   + at-fault operator (constrained repair); if nothing fires
                   (uncovered), ABSTAIN-route to generic. Same budget as generic.

HONEST CAVEAT (measured, not assumed): DS-1000 tasks are arbitrary SO problems
and do NOT carry our operator-semantic params (group/value/weight/...). Our
contracts are operator-specific, so their FIRING COVERAGE on DS-1000 silents may
be low — in which case the targeted arm largely abstain-routes to generic and the
external lift is bounded by coverage. We therefore report (a) contract-fire
coverage, (b) generic vs targeted recovery overall, and (c) the lift ON THE
COVERED SUBSET — letting the data state honestly how far operator-matched
contracts transfer to unconstrained real tasks.

Usage:
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. \
      python eval/ds1000_repair.py --n-silent 20 --budget 2 --model gpt-4o \
      --out eval/results_ds1000_repair
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

from eval import ds1000_real_intent as DS  # noqa: E402
from eval import transform_repair_policy as POL  # noqa: E402
from eval.nature_real_transform import _wilson  # noqa: E402


def _as_df(x: Any) -> Optional[pd.DataFrame]:
    if isinstance(x, pd.DataFrame):
        return x
    if isinstance(x, pd.Series):
        return x.to_frame()
    return None


def _main_df(test_input: Any) -> Optional[pd.DataFrame]:
    """The primary input DataFrame the harness injected (for the contracts)."""
    if isinstance(test_input, pd.DataFrame):
        return test_input
    if isinstance(test_input, (tuple, list)):
        for el in test_input:
            if isinstance(el, pd.DataFrame):
                return el
    return None


def _capture(item: Dict[str, Any], solution: str) -> Tuple[str, Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Drive the harness for test case 1 and return (outcome, result_df, input_df).
    `outcome` is the full multi-case classification (pass/silent/crash); result_df
    and input_df are from case 1 (enough to run a goldless contract)."""
    ctx: Dict[str, Any] = {}
    try:
        exec(item["code_context"], ctx)  # noqa: S102
    except Exception:
        return "crash", None, None
    gen = ctx.get("generate_test_case")
    ec = ctx.get("exec_context")
    if not (callable(gen) and isinstance(ec, str)):
        return "crash", None, None
    full = ec.replace("[insert]", DS._sanitize(solution, DS._harness_vars(ec)))
    try:
        test_input, _expected = gen(1)
    except Exception:
        return "crash", None, None
    env: Dict[str, Any] = {"test_input": test_input}
    try:
        exec(full, env)  # noqa: S102
    except Exception:
        return "crash", None, None
    result = _as_df(env.get("result"))
    outcome = DS._classify(item, solution)
    return outcome, result, _main_df(test_input)


def _diagnose_initial(result: Optional[pd.DataFrame], df: Optional[pd.DataFrame]) -> POL.Diagnosis:
    inputs = {"df": df} if df is not None else {}
    return POL.diagnose(inputs, {}, result)


def _repair(item: Dict[str, Any], start_solution: str, arm: str, model: str,
            budget: int) -> Dict[str, Any]:
    """Run one repair arm from the shared silent start. Success = DS-1000 gold
    (all test cases pass). Returns {fixed, rounds, fired_ever, kinds}."""
    cur = start_solution
    fired_ever = False
    kinds: List[str] = []
    rnd = 0
    for rnd in range(1, budget + 1):
        _outcome, result, df = _capture(item, cur)
        if arm == "generic":
            fb = POL.generic_instruction(POL._preview(result))
            kinds.append("generic")
        else:
            diag = _diagnose_initial(result, df)
            if diag.fired:
                fired_ever = True
                fb = POL.targeted_instruction(diag, POL._preview(result))
                kinds.append("targeted")
            else:
                fb = POL.generic_instruction(POL._preview(result))
                kinds.append("abstain->generic")
        code = DS._llm_solution_retry(item, model, feedback=fb)
        if code is None:
            return {"fixed": False, "rounds": rnd, "fired_ever": fired_ever, "kinds": kinds}
        cur = code
        if DS._classify(item, cur) == "pass":
            return {"fixed": True, "rounds": rnd, "fired_ever": fired_ever, "kinds": kinds}
    return {"fixed": False, "rounds": budget, "fired_ever": fired_ever, "kinds": kinds}


def main(argv: Optional[List[str]] = None) -> int:
    import os
    ap = argparse.ArgumentParser(description="External C2: targeted vs generic repair on DS-1000 silent errors")
    ap.add_argument("--n-silent", type=int, default=20, help="target number of silent cases to repair")
    ap.add_argument("--budget", type=int, default=2, help="repair rounds per arm")
    ap.add_argument("--model", default="gpt-4o", help="(single-model shorthand; --models overrides)")
    ap.add_argument("--models", default=None, help="comma-separated models; each (problem,model) is a potential silent")
    ap.add_argument("--all-pandas", action="store_true", help="scan ALL completion-format pandas problems (not just ambiguity-prone)")
    ap.add_argument("--max-scan", type=int, default=160, help="max DS-1000 problems to scan for silents")
    ap.add_argument("--out", default="eval/results_ds1000_repair")
    a = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY."); return 1

    models = [m.strip() for m in a.models.split(",")] if a.models else [a.model]
    cases = DS._load_pandas(a.max_scan, None, all_pandas=a.all_pandas)
    print(f"[ds1000-repair] scanning up to {len(cases)} {'all' if a.all_pandas else 'ambiguity-prone'} "
          f"completion-format pandas problems x {len(models)} models {models} "
          f"(budget={a.budget}, target {a.n_silent} silents)", flush=True)

    rows: List[Dict[str, Any]] = []
    n_silent = covered = gen_fix = 0
    policy_fix = 0                       # policy = targeted on covered, generic on uncovered
    cov_gen_fix = cov_tgt_fix = 0        # on the covered subset (the clean comparison)
    fam_cov: Dict[str, int] = {}         # covered count by operator the diagnoser localized
    done = False
    for item in cases:
        if done:
            break
        for model in models:
            if n_silent >= a.n_silent:
                done = True
                break
            try:
                start = DS._llm_solution_retry(item, model)
                if start is None:
                    continue
                outcome, result, df = _capture(item, start)
                if outcome != "silent":
                    continue  # need a genuine external silent error to repair
                n_silent += 1
                init = _diagnose_initial(result, df)
                is_cov = init.fired
                covered += int(is_cov)
                if is_cov and init.operator:
                    fam_cov[init.operator] = fam_cov.get(init.operator, 0) + 1
                # generic baseline (always).
                g = _repair(item, start, "generic", model, a.budget)
                gen_fix += int(g["fixed"])
                # The POLICY routes uncovered -> generic (the SAME attempt, no re-sample), and
                # runs a distinct targeted arm only where a contract actually fires. This avoids
                # confounding the comparison with LLM stochasticity on the uncovered majority.
                if is_cov:
                    t = _repair(item, start, "targeted", model, a.budget)
                    tgt_fixed = bool(t["fixed"])
                    cov_gen_fix += int(g["fixed"]); cov_tgt_fix += int(tgt_fixed)
                    policy_fixed = tgt_fixed
                    t_kinds = t["kinds"]
                else:
                    policy_fixed = bool(g["fixed"])  # abstain-route == the generic attempt
                    t_kinds = ["abstain->generic"]
                policy_fix += int(policy_fixed)
                rows.append({"problem_id": item["problem_id"], "model": model, "families": item["families"],
                             "covered": is_cov, "diag_operator": init.operator,
                             "generic_fixed": g["fixed"], "policy_fixed": policy_fixed,
                             "targeted_kinds": t_kinds})
                print(f"  [p{str(item['problem_id']):>4} {model:17}] covered={is_cov!s:5} op={str(init.operator):16} "
                      f"generic={'FIX' if g['fixed'] else '...'} policy={'FIX' if policy_fixed else '...'}", flush=True)
            except Exception as e:  # one bad case must not kill a multi-hour run
                print(f"  [p{str(item['problem_id']):>4} {model:17}] SKIP ({type(e).__name__}: {str(e)[:80]})", flush=True)
                continue

    n_unc = n_silent - covered
    report = [
        f"# External C2: targeted vs generic repair on DS-1000 silent errors ({n_silent} cases)\n",
        "Symmetric to §1.3.2 (detection on external DS-1000): here we REPAIR the",
        "external silent errors. Success = DS-1000's OWN gold (test cases pass);",
        f"targeted feedback = our goldless contracts (abstain->generic when none fire). "
        f"models={models}, budget={a.budget}. 95% Wilson CIs.\n",
        "## (1) Contract-fire coverage on external silents (honest boundary)",
        f"- our contracts fire on: {covered}/{n_silent} ({_wilson(covered, n_silent)})",
        f"  (the rest, {n_unc}/{n_silent}, are UNCOVERED — policy abstain-routes to generic)",
        ("  - by localized operator: " + ", ".join(f"{op} {n}" for op, n in sorted(fam_cov.items(), key=lambda x: -x[1]))
         if fam_cov else "  - (no contract fired on any silent)") + "\n",
        "## (2) Repair recovery (DS-1000 gold), all silents",
        f"- generic baseline:        {gen_fix}/{n_silent} ({_wilson(gen_fix, n_silent)})",
        f"- policy (targeted+abstain): {policy_fix}/{n_silent} ({_wilson(policy_fix, n_silent)})",
        "  (policy == generic on the uncovered majority, so they differ only on covered cases)\n",
        "## (3) Lift ON THE COVERED SUBSET (where a contract actually fires — the clean test)",
        (f"- generic:  {cov_gen_fix}/{covered} ({_wilson(cov_gen_fix, covered)})\n"
         f"- targeted: {cov_tgt_fix}/{covered} ({_wilson(cov_tgt_fix, covered)})"
         if covered else "- (no covered cases — contracts did not fire on any external silent)"),
        "\n## Reading",
        "- Coverage bounds the external targeted lift: where our operator-specific",
        "  contracts fire (mostly the param-free join/how contract — most contracts need",
        "  operator-semantic params arbitrary SO tasks do not carry), targeted feedback",
        "  applies; elsewhere the policy correctly abstain-routes to generic (no blind",
        "  edits). This honestly bounds how far operator-matched contracts transfer to",
        "  unconstrained real SO tasks — the operator-matched external-DATA C2 evidence is",
        "  the Nature slice (§1.3.1), where params are known and contracts fire ~99% recall.",
    ]
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ds1000_repair_report.md").write_text("\n".join(report) + "\n")
    (out_dir / "records.json").write_text(json.dumps(rows, indent=2))
    print("\n".join(report))
    print(f"\n[written] {out_dir/'ds1000_repair_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
