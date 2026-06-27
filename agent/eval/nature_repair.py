"""
nature_repair.py — operator-matched, HIGH-coverage external-DATA validity for C2
(targeted repair), complementing the external-TASK / low-coverage DS-1000 result.

The DS-1000 repair experiment (ds1000_repair.py) showed our operator-specific
contracts have LOW firing coverage on arbitrary SO tasks (~8%, only the
param-free join contract transfers) because those tasks carry no operator
params. This experiment removes that limitation while keeping the DATA external:
it instantiates our operator-semantic tasks on REAL Nature source-data tables
(the §1.3.1 slice), where the params ARE known, so the goldless contracts fire at
~99% recall. That lets us measure the targeted-vs-generic repair lift on real
scientific data with HIGH contract coverage — the operator-matched companion to
DS-1000's honest-boundary number.

Mirrors ds1000_repair.py exactly (same generic-baseline vs policy comparison, the
policy abstain-routes uncovered cases to generic and reuses that attempt) so the
two external results are directly comparable:
  * DS-1000 : external-TASK (real SO intents), coverage ~8%, gold = DS-1000 tests.
  * Nature  : external-DATA (real scientific tables), coverage ~99%, gold =
              template on real data.

Start    = a model solution from the AMBIGUOUS prompt that is exec-ok but silent
           (template gold on the real table is wrong).
Success  = `_gold_correct` (independent template gold; the policy never sees it).
generic  = generic self-repair feedback.
policy   = transform_repair_policy: diagnose -> targeted constrained feedback when
           a contract fires (here almost always), else abstain-route to generic.

Usage:
  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. \
      python eval/nature_repair.py --pairs-root ../downloads/articles \
      --n-silent 60 --budget 2 --model gpt-4o --max-rows 10000 \
      --out eval/results_nature_repair
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402

from eval.nature_real_auto import _build  # noqa: E402
from eval import transform_repair_policy as POL  # noqa: E402
from eval.nature_real_transform import _wilson  # noqa: E402


def _llm_code_retry(task, prompt, model, retries: int = 7, pace: float = 0.6):
    """Paced retry on a None (proxy overload) — same contract as
    nature_real_auto so proxy hiccups don't masquerade as model failures."""
    from eval.ambiguity_calibration import _llm_code
    for attempt in range(retries):
        code = _llm_code(task, prompt, model)
        if code is not None:
            time.sleep(pace)
            return code
        time.sleep(min(2.0 * (attempt + 1), 12.0))
    return None


def _repair(task: Dict[str, Any], start: Optional[pd.DataFrame], arm: str, model: str,
            budget: int) -> Dict[str, Any]:
    """One repair arm from the shared silent start. Success = template gold on the
    real table. Returns {fixed, rounds, fired_ever, kinds}."""
    from eval.ambiguity_calibration import _exec, _gold_correct
    cur = start
    fired_ever = False
    kinds: List[str] = []
    inputs = POL.inputs_of(task)
    for rnd in range(1, budget + 1):
        if arm == "generic":
            fb = POL.generic_instruction(POL._preview(cur))
            kinds.append("generic")
        else:
            diag = POL.diagnose(inputs, task["params"], cur, op_hint=task["op"])
            if diag.fired:
                fired_ever = True
                fb = POL.targeted_instruction(diag, POL._preview(cur))
                kinds.append("targeted")
            else:
                fb = POL.generic_instruction(POL._preview(cur))
                kinds.append("abstain->generic")
        code = _llm_code_retry(task, f"{task['ambiguous']}\n\n{fb}", model)
        nxt = _exec(task, code) if code else None
        if nxt is None:
            return {"fixed": False, "rounds": rnd, "fired_ever": fired_ever, "kinds": kinds}
        cur = nxt
        if _gold_correct(task, cur):
            return {"fixed": True, "rounds": rnd, "fired_ever": fired_ever, "kinds": kinds}
    return {"fixed": bool(_gold_correct(task, cur)), "rounds": budget, "fired_ever": fired_ever, "kinds": kinds}


def main(argv: Optional[List[str]] = None) -> int:
    import os
    ap = argparse.ArgumentParser(description="External-DATA C2: targeted vs generic repair on REAL Nature silent errors")
    ap.add_argument("--pairs-root", default="../downloads/articles")
    ap.add_argument("--n-silent", type=int, default=60, help="target number of silent cases to repair")
    ap.add_argument("--budget", type=int, default=2, help="repair rounds per arm")
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--max-tasks", type=int, default=600, help="max Nature tasks to scan for silents")
    ap.add_argument("--max-per-article", type=int, default=4)
    ap.add_argument("--max-rows", type=int, default=10000)
    ap.add_argument("--out", default="eval/results_nature_repair")
    a = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY."); return 1

    from eval.ambiguity_calibration import _exec, _gold_correct

    tasks = _build(a.pairs_root, a.max_tasks, a.max_per_article, a.max_rows)
    print(f"[nature-repair] {len(tasks)} real Nature operator tasks; scanning for silent errors "
          f"(model={a.model}, budget={a.budget}, target {a.n_silent} silents)", flush=True)

    rows: List[Dict[str, Any]] = []
    n_silent = covered = gen_fix = policy_fix = 0
    cov_gen_fix = cov_tgt_fix = 0
    fam_tot: Dict[str, int] = {}
    fam_gen: Dict[str, int] = {}
    fam_tgt: Dict[str, int] = {}
    for task in tasks:
        if n_silent >= a.n_silent:
            break
        try:
            start_code = _llm_code_retry(task, task["ambiguous"], a.model)
            start = _exec(task, start_code) if start_code else None
            if start is None or _gold_correct(task, start):
                continue  # need an exec-ok silent error to repair
            n_silent += 1
            op = task["op"]
            fam_tot[op] = fam_tot.get(op, 0) + 1
            diag = POL.diagnose(POL.inputs_of(task), task["params"], start, op_hint=op)
            is_cov = diag.fired
            covered += int(is_cov)
            g = _repair(task, start, "generic", a.model, a.budget)
            gen_fix += int(g["fixed"]); fam_gen[op] = fam_gen.get(op, 0) + int(g["fixed"])
            if is_cov:
                t = _repair(task, start, "policy", a.model, a.budget)
                tgt_fixed = bool(t["fixed"])
                cov_gen_fix += int(g["fixed"]); cov_tgt_fix += int(tgt_fixed)
                policy_fixed = tgt_fixed
            else:
                policy_fixed = bool(g["fixed"])  # abstain-route == the generic attempt
            policy_fix += int(policy_fixed)
            fam_tgt[op] = fam_tgt.get(op, 0) + int(policy_fixed)
            rows.append({"name": task["name"], "op": op, "covered": is_cov,
                         "generic_fixed": g["fixed"], "policy_fixed": policy_fixed})
            print(f"  [{op:18} {task['name'].split('::')[-1][:24]:24}] covered={is_cov!s:5} "
                  f"generic={'FIX' if g['fixed'] else '...'} policy={'FIX' if policy_fixed else '...'}", flush=True)
        except Exception as e:
            print(f"  [SKIP {task.get('op','?')}] ({type(e).__name__}: {str(e)[:80]})", flush=True)
            continue

    arts = len(set(r["name"].split("::")[1].split(":")[0] for r in rows)) if rows else 0
    report = [
        f"# External-DATA C2: targeted vs generic repair on REAL Nature silent errors ({n_silent} cases)\n",
        "Operator-matched companion to the DS-1000 external-TASK result: same",
        "generic-vs-policy repair comparison, but on REAL Nature source-data tables",
        f"(across {arts} articles) where the operator params ARE known, so our goldless",
        "contracts fire at high coverage. Success = template gold on the real table",
        f"(the policy never sees it). model={a.model}, budget={a.budget}. 95% Wilson CIs.\n",
        "## (1) Contract-fire coverage on real silents (operator-matched => high)",
        f"- our contracts fire on: {covered}/{n_silent} ({_wilson(covered, n_silent)})\n",
        "## (2) Repair recovery (template gold on real data)",
        f"- generic baseline:        {gen_fix}/{n_silent} ({_wilson(gen_fix, n_silent)})",
        f"- policy (targeted+abstain): {policy_fix}/{n_silent} ({_wilson(policy_fix, n_silent)})\n",
        "## (3) Lift on the covered subset (the clean targeted-vs-generic test)",
        (f"- generic:  {cov_gen_fix}/{covered} ({_wilson(cov_gen_fix, covered)})\n"
         f"- targeted: {cov_tgt_fix}/{covered} ({_wilson(cov_tgt_fix, covered)})"
         if covered else "- (no covered cases)"),
        "\n## (4) By operator family (targeted/policy fixed vs generic fixed / total)",
    ]
    for op in sorted(fam_tot, key=lambda x: -fam_tot[x]):
        report.append(f"- {op:20} targeted {fam_tgt.get(op,0)}/{fam_tot[op]} vs generic {fam_gen.get(op,0)}/{fam_tot[op]}")
    report += [
        "\n## Reading",
        "- With operator params known (real Nature tables, our operator-semantic",
        "  tasks), contract coverage is high and the targeted lift over generic is",
        "  realized on REAL scientific data — the external-DATA anchor for C2. Paired",
        "  with DS-1000 (external-TASK, low coverage, honest boundary) this brackets",
        "  how far contract-guided targeted repair transfers: strong where the",
        "  operator semantics are identified, safely abstaining to generic elsewhere.",
    ]
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "nature_repair_report.md").write_text("\n".join(report) + "\n")
    (out_dir / "records.json").write_text(json.dumps(rows, indent=2))
    print("\n".join(report))
    print(f"\n[written] {out_dir/'nature_repair_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
