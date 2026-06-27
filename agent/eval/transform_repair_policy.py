"""
transform_repair_policy.py — online targeted-repair POLICY (closes the §8.3 gap).

exp1 (`transform_repair.py`) PROVED that feeding typed operator-semantic
attribution back to the model repairs silent errors far better than generic
self-repair (targeted 80% vs generic 18%, CIs separated). But that logic lives
INSIDE a 3-arm experiment harness bound to the `transform_bench` case structure.
The §8.3 first-priority gap is to turn that proven mechanism into a reusable
ONLINE policy. This module does exactly that, as the §8.6 two-stage architecture
(WITHOUT claiming dual-agent as novelty — the headline is the typed *signal*):

  Agent A — Diagnoser:  diagnose(inputs, params, result) -> Diagnosis
      Runs the goldless operator-semantic contracts (transform_oracle via
      attribution_eval._run_all_contracts with family-level pruning) and returns
      a STRUCTURED diagnosis: which operator semantics is violated, the violated
      invariant text, every localized contract, the allowed patch scope, and a
      high/abstain confidence flag. Decoupled from any task/gold structure.

  Agent B — Repairer:   consumes the Diagnosis -> a CONSTRAINED repair
      instruction ("fix ONLY the <op> step …"), then calls an injected
      code_fn/exec_fn to produce a new result. Injection makes the whole policy
      deterministically unit-testable offline (no LLM needed).

  Policy loop (TargetedRepairPolicy.repair):
      diagnose -> route:
        * a contract fires (high confidence)  -> targeted constrained repair.
        * no contract fires:
            - if a contract fired earlier this session -> contract_pass (a
              targeted repair satisfied the invariant) -> STOP, success path.
            - elif the caller asserted the result is wrong (assume_wrong, e.g. an
              UNCOVERED operator a detector flagged) -> route per `abstain_policy`:
                  "generic" -> fall back to generic self-repair (default);
                  "abstain" -> stop and flag abstained (do not risk a blind edit).
            - else -> no_error (goldless: nothing detectable to fix) -> STOP.
      Budget caps the rounds.

Honesty (per §8.2): abstain-routing is a detection-confidence-driven SAFETY knob,
NOT a validated repair-time success gain (exp2a found none on uncovered ops). The
validated claim is C2 — contract-guided TARGETED repair >> generic.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.attribution_eval import _run_all_contracts  # noqa: E402


# --------------------------------------------------------------------------- #
# Agent A — structured diagnosis (the §8.6 diagnoser contract)
# --------------------------------------------------------------------------- #
@dataclass
class Diagnosis:
    """Structured output of the goldless diagnoser. `fired` is the only detection
    signal; everything else localizes/constrains the downstream repair."""
    fired: bool                          # a substantive operator contract is violated
    operator: Optional[str]              # primary at-fault operator family (or None)
    violated_invariant: Optional[str]    # the contract's human-readable detail
    localized_contracts: List[str] = field(default_factory=list)  # all fired (pruned)
    allowed_scope: Optional[str] = None  # patch scope hint ("the `<op>` step")
    confidence: str = "abstain"          # "high" when a contract fires, else "abstain"

    @property
    def is_actionable(self) -> bool:
        """A localizable, high-confidence diagnosis the repairer can constrain to."""
        return self.fired and self.operator is not None


def diagnose(inputs: Dict[str, pd.DataFrame], params: Dict[str, Any],
             result: Optional[pd.DataFrame], op_hint: Optional[str] = None) -> Diagnosis:
    """Agent A: run all goldless contracts (family-pruned) on `result` and build a
    structured diagnosis. `op_hint` (optional) is the suspected operator family —
    if its contract fires it is chosen as primary, otherwise the first localized
    contract is. NEVER consults gold."""
    fired_map = _run_all_contracts(inputs, params, result, prune=True)
    localized = [op for op, f in fired_map.items() if f]
    primary: Optional[str] = None
    if op_hint and fired_map.get(op_hint):
        primary = op_hint
    elif localized:
        primary = localized[0]
    if primary is None:
        return Diagnosis(fired=False, operator=None, violated_invariant=None,
                         localized_contracts=[], allowed_scope=None, confidence="abstain")
    cr = oracle_check(primary, inputs, params, result)
    detail = cr.detail if cr is not None else "(operator-semantic invariant violated)"
    return Diagnosis(
        fired=True,
        operator=primary,
        violated_invariant=detail,
        localized_contracts=localized,
        allowed_scope=f"the `{primary}` computation/step",
        confidence="high",
    )


def _op_fires(inputs: Dict[str, pd.DataFrame], params: Dict[str, Any],
              result: Optional[pd.DataFrame], op: str) -> Optional[str]:
    """Substantive single-operator stopping signal (matches exp1 `_true_op_fires`):
    return the violated-invariant detail if `op`'s OWN contract substantively fires
    (it actually evaluated the invariant and found it violated), else None. Using
    the target operator's own contract — not 'any contract is silent' — avoids an
    unrelated contract's cross-fire keeping the loop alive on an already-correct
    result."""
    cr = oracle_check(op, inputs, params, result)
    if cr is not None and cr.fired and "missing" not in cr.detail.lower():
        return cr.detail
    return None


# --------------------------------------------------------------------------- #
# Agent B — constrained repair instruction (driven by the Diagnosis)
# --------------------------------------------------------------------------- #
def _preview(result: Optional[pd.DataFrame], n: int = 6) -> str:
    if result is None:
        return "(no result / malformed)"
    try:
        return result.head(n).to_string()
    except Exception:
        return str(result)[:400]


def targeted_instruction(diag: Diagnosis, result_preview: str) -> str:
    """The CONSTRAINED feedback: name the violated invariant + at-fault operator +
    restrict the edit scope. This is the C2 signal exp1 validated."""
    loc = ", ".join(diag.localized_contracts) or (diag.operator or "")
    return ("A checkable semantic invariant is VIOLATED, so the result is wrong.\n"
            f"At-fault operator semantics: `{diag.operator}` (localized contracts: {loc}).\n"
            f"Violated invariant: {diag.violated_invariant}\n"
            f"Fix ONLY {diag.allowed_scope}. Do NOT alter parts of the pipeline that "
            "are already correct. Produce a corrected `result`.\n"
            f"Previous result:\n{result_preview}")


def generic_instruction(result_preview: str) -> str:
    """The fallback feedback when nothing is localizable (uncovered operator) and
    the caller still wants an attempt. No typed information — same strength as the
    exp1 generic arm so the comparison stays honest."""
    return ("Your previous result may be SEMANTICALLY INCORRECT (it runs and looks "
            "plausible but may not implement the requested transformation). Carefully "
            "re-read the task, double-check your aggregation/grouping/weighting choices, "
            "and produce a corrected `result`.\n"
            f"Previous result:\n{result_preview}")


# --------------------------------------------------------------------------- #
# Policy outcome
# --------------------------------------------------------------------------- #
@dataclass
class RepairOutcome:
    repaired_result: Optional[pd.DataFrame]
    terminated_reason: str          # contract_pass | budget | malformed | abstained | no_error
    rounds: int                     # number of repair attempts actually made
    abstained: bool
    diagnosis_trace: List[Diagnosis] = field(default_factory=list)
    instruction_trace: List[str] = field(default_factory=list)  # 'targeted'|'generic' per round

    @property
    def repaired(self) -> bool:
        """Goldless success signal: the loop ended because the contract stopped
        firing after at least one repair attempt."""
        return self.terminated_reason == "contract_pass" and self.rounds >= 1


# --------------------------------------------------------------------------- #
# The online targeted-repair policy
# --------------------------------------------------------------------------- #
CodeFn = Callable[[str, str], Optional[str]]   # (task, feedback) -> code | None
ExecFn = Callable[[Optional[str]], Optional[pd.DataFrame]]  # code -> result | None


class TargetedRepairPolicy:
    """Reusable online policy wrapping the exp1-proven targeted-repair loop.

    The repairer backend is INJECTED (code_fn/exec_fn) so the policy is
    deterministically testable offline and LLM-agnostic online. Use
    `make_llm_backend(item, model)` to bridge to the project's proxy LLM client.
    """

    def __init__(self, code_fn: CodeFn, exec_fn: ExecFn, *, budget: int = 3,
                 abstain_policy: str = "generic", preview_fn: Callable[[Optional[pd.DataFrame]], str] = _preview):
        if abstain_policy not in ("generic", "abstain"):
            raise ValueError("abstain_policy must be 'generic' or 'abstain'")
        if budget < 1:
            raise ValueError("budget must be >= 1")
        self.code_fn = code_fn
        self.exec_fn = exec_fn
        self.budget = budget
        self.abstain_policy = abstain_policy
        self.preview_fn = preview_fn

    def repair(self, task: str, inputs: Dict[str, pd.DataFrame], params: Dict[str, Any],
               initial_result: Optional[pd.DataFrame], *, op_hint: Optional[str] = None,
               assume_wrong: bool = False) -> RepairOutcome:
        """Diagnose -> constrained repair loop. Goldless throughout: the stopping
        signal is the TARGET operator's own contract no longer firing; success is
        judged by the caller with held-out gold (never inside this policy).

        The target operator is locked from the first diagnosis (or `op_hint`); each
        round repairs only that operator and stops when its invariant is satisfied.
        An unrelated contract's cross-fire on the (now-correct) result does NOT keep
        the loop alive — it is at most an over-repair signal for the caller."""
        cur = initial_result
        dtrace: List[Diagnosis] = []
        itrace: List[str] = []

        # Lock the target operator from the initial structured diagnosis.
        diag0 = diagnose(inputs, params, cur, op_hint)
        dtrace.append(diag0)
        target_op = diag0.operator  # None => nothing localizable fired

        if target_op is None:
            if not assume_wrong:
                return RepairOutcome(cur, "no_error", 0, False, dtrace, itrace)
            if self.abstain_policy == "abstain":
                return RepairOutcome(cur, "abstained", 0, True, dtrace, itrace)
            # uncovered operator the caller insists is wrong -> generic fallback route

        for rnd in range(1, self.budget + 1):
            if rnd > 1:
                dtrace.append(diagnose(inputs, params, cur, target_op or op_hint))

            if target_op is not None:
                detail = _op_fires(inputs, params, cur, target_op)
                if detail is None:
                    # target operator's invariant now satisfied (goldless success).
                    return RepairOutcome(cur, "contract_pass", rnd - 1, False, dtrace, itrace)
                diag = Diagnosis(True, target_op, detail, [target_op],
                                 f"the `{target_op}` computation/step", "high")
                feedback = targeted_instruction(diag, self.preview_fn(cur))
                kind = "targeted"
            else:
                # uncovered + assume_wrong + abstain_policy=='generic'
                feedback = generic_instruction(self.preview_fn(cur))
                kind = "generic"

            code = self.code_fn(task, feedback)
            nxt = self.exec_fn(code) if code else None
            itrace.append(kind)
            if nxt is None:
                return RepairOutcome(cur, "malformed", rnd, False, dtrace, itrace)
            cur = nxt

        # Budget exhausted: a final op-specific check decides pass vs budget.
        if target_op is not None and _op_fires(inputs, params, cur, target_op) is None:
            return RepairOutcome(cur, "contract_pass", self.budget, False, dtrace, itrace)
        return RepairOutcome(cur, "budget", self.budget, False, dtrace, itrace)


# --------------------------------------------------------------------------- #
# Online bridge to the project's proxy LLM client (kept out of the policy core)
# --------------------------------------------------------------------------- #
def make_llm_backend(item: Dict[str, Any], model: str):
    """Build (code_fn, exec_fn) backed by the proxy LLM client for an online run.
    `item` carries the real df(s); the policy itself stays decoupled from it."""
    from eval.ambiguity_calibration import _llm_code, _exec

    def code_fn(task: str, feedback: str) -> Optional[str]:
        return _llm_code(item, f"{task}\n\n{feedback}", model)

    def exec_fn(code: Optional[str]) -> Optional[pd.DataFrame]:
        return _exec(item, code) if code else None

    return code_fn, exec_fn


def inputs_of(item: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """Extract the contract `inputs` dict from a transform_bench item."""
    inp = {"df": item["df"]}
    if "df2" in item:
        inp["df2"] = item["df2"]
    return inp


# --------------------------------------------------------------------------- #
# Deterministic offline self-test (no LLM) — validates the policy loop + diagnoser
# --------------------------------------------------------------------------- #
def _fixture_weighted_mean():
    df = pd.DataFrame({"price": [10.0, 20.0, 30.0], "qty": [100, 10, 1]})
    params = {"value": "price", "weight": "qty"}
    correct = pd.DataFrame({"wavg": [(df["price"] * df["qty"]).sum() / df["qty"].sum()]})
    wrong = pd.DataFrame({"wavg": [df["price"].mean()]})  # arithmetic-mean slip
    return {"df": df}, params, correct, wrong


def _fixture_median():
    d = pd.DataFrame({"grp": ["x", "x", "x", "y", "y", "y"], "v": [1.0, 2.0, 9.0, 4.0, 5.0, 60.0]})
    params = {"group": "grp", "value": "v"}
    correct = d.groupby("grp", as_index=False)["v"].median()
    wrong = d.groupby("grp", as_index=False)["v"].mean()  # mean slip
    return {"df": d}, params, correct, wrong


def _const_backend(result_seq):
    """Backend whose exec returns successive results from `result_seq` (last one
    repeats). code_fn is a no-op marker. Lets a test script the repair trajectory."""
    state = {"i": 0}

    def code_fn(task, feedback):
        return "<scripted>"

    def exec_fn(code):
        i = min(state["i"], len(result_seq) - 1)
        state["i"] += 1
        r = result_seq[i]
        return None if r is None else r.copy()

    return code_fn, exec_fn


def _selftest() -> int:
    fails: List[str] = []
    inp, params, correct, wrong = _fixture_weighted_mean()

    # (1) diagnose on a WRONG result -> structured, actionable diagnosis
    d_wrong = diagnose(inp, params, wrong, op_hint="weighted_mean")
    if not d_wrong.fired:
        fails.append("diagnose did not fire on weighted_mean slip")
    if d_wrong.operator != "weighted_mean":
        fails.append(f"diagnose primary operator = {d_wrong.operator}, expected weighted_mean")
    if "weighted_mean" not in d_wrong.localized_contracts:
        fails.append("diagnose localized_contracts missing weighted_mean")
    if d_wrong.confidence != "high" or not d_wrong.is_actionable:
        fails.append("diagnose confidence/actionable wrong on a fired case")
    if not d_wrong.allowed_scope or "weighted_mean" not in d_wrong.allowed_scope:
        fails.append("diagnose allowed_scope missing operator")

    # (2) diagnose on a CORRECT result -> abstain
    d_ok = diagnose(inp, params, correct, op_hint="weighted_mean")
    if d_ok.fired or d_ok.confidence != "abstain" or d_ok.operator is not None:
        fails.append("diagnose should abstain on a correct result")

    # (3) targeted repair SUCCEEDS in one round -> contract_pass
    code_fn, exec_fn = _const_backend([correct])
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3)
    out = pol.repair("compute weighted mean", inp, params, wrong, op_hint="weighted_mean")
    if out.terminated_reason != "contract_pass" or not out.repaired or out.rounds != 1:
        fails.append(f"targeted-success: reason={out.terminated_reason} rounds={out.rounds} repaired={out.repaired}")
    if out.instruction_trace != ["targeted"]:
        fails.append(f"targeted-success: instruction_trace={out.instruction_trace}")

    # (4) stuck repairer (always re-returns the wrong result) -> budget, not repaired
    code_fn, exec_fn = _const_backend([wrong])
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3)
    out = pol.repair("compute weighted mean", inp, params, wrong, op_hint="weighted_mean")
    if out.terminated_reason != "budget" or out.repaired or out.rounds != 3:
        fails.append(f"stuck: reason={out.terminated_reason} rounds={out.rounds} repaired={out.repaired}")
    if out.instruction_trace != ["targeted", "targeted", "targeted"]:
        fails.append(f"stuck: instruction_trace={out.instruction_trace}")

    # (5) clean start, no assertion -> no_error (goldless: nothing to fix)
    code_fn, exec_fn = _const_backend([correct])
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3)
    out = pol.repair("compute weighted mean", inp, params, correct, op_hint="weighted_mean")
    if out.terminated_reason != "no_error" or out.rounds != 0:
        fails.append(f"no_error: reason={out.terminated_reason} rounds={out.rounds}")

    # (6) malformed rewrite -> malformed
    code_fn, exec_fn = _const_backend([None])
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3)
    out = pol.repair("compute weighted mean", inp, params, wrong, op_hint="weighted_mean")
    if out.terminated_reason != "malformed":
        fails.append(f"malformed: reason={out.terminated_reason}")

    # (7) abstain routing: uncovered (no contract fires) + assume_wrong + policy 'abstain'
    code_fn, exec_fn = _const_backend([correct])  # backend irrelevant; should not be called to fix
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3, abstain_policy="abstain")
    out = pol.repair("uncovered op", inp, params, correct, assume_wrong=True)
    if out.terminated_reason != "abstained" or not out.abstained or out.rounds != 0:
        fails.append(f"abstain-abstain: reason={out.terminated_reason} abstained={out.abstained} rounds={out.rounds}")

    # (8) abstain routing: uncovered + assume_wrong + policy 'generic' -> generic attempts to budget
    code_fn, exec_fn = _const_backend([correct])  # stays uncovered (no contract ever fires)
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=2, abstain_policy="generic")
    out = pol.repair("uncovered op", inp, params, correct, assume_wrong=True)
    if out.instruction_trace != ["generic", "generic"] or out.terminated_reason != "budget":
        fails.append(f"abstain-generic: trace={out.instruction_trace} reason={out.terminated_reason}")

    # (9) second fixture (median) end-to-end targeted success
    inp2, p2, ok2, bad2 = _fixture_median()
    code_fn, exec_fn = _const_backend([ok2])
    pol = TargetedRepairPolicy(code_fn, exec_fn, budget=3)
    out = pol.repair("per-group median", inp2, p2, bad2, op_hint="median_not_mean")
    if not out.repaired or out.terminated_reason != "contract_pass":
        fails.append(f"median targeted-success: reason={out.terminated_reason} repaired={out.repaired}")

    # (10) op_hint that does NOT fire but another contract does -> primary = the firing one
    d_nohint = diagnose(inp, params, wrong, op_hint="median_not_mean")  # wrong hint
    if not d_nohint.fired or d_nohint.operator != "weighted_mean":
        fails.append(f"op_hint fallback: operator={d_nohint.operator} (expected weighted_mean)")

    if fails:
        print("SELFTEST FAILED:")
        for f in fails:
            print("  -", f)
        return 1
    print("SELFTEST OK: 10 checks passed (diagnose structured output + policy loop + abstain routing).")
    return 0


# --------------------------------------------------------------------------- #
# Online smoke (real LLM via proxy) — the policy on real transform_bench silents
# --------------------------------------------------------------------------- #
def _online_smoke(models: List[str], n: int, budget: int) -> int:
    import os
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] online smoke needs LLM_API_BASE / LLM_API_KEY."); return 1
    from eval.transform_bench import _cases
    from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct

    cases = _cases()
    model = models[0]
    repaired = attempted = 0
    print(f"[smoke] policy on up to {n} real silent cases x model={model}, budget={budget}", flush=True)
    for c in cases:
        if attempted >= n:
            break
        # produce a real exec-ok-but-silent starting point from the ambiguous prompt
        code = _llm_code(c, c["ambiguous"], model)
        start = _exec(c, code) if code else None
        if start is None or _gold_correct(c, start):
            continue  # need a genuine silent error to repair
        attempted += 1
        code_fn, exec_fn = make_llm_backend(c, model)
        pol = TargetedRepairPolicy(code_fn, exec_fn, budget=budget)
        out = pol.repair(c["ambiguous"], inputs_of(c), c["params"], start, op_hint=c["op"])
        ok = _gold_correct(c, out.repaired_result)  # independent gold (policy never saw it)
        repaired += int(ok)
        print(f"  [{c['op']:22}] reason={out.terminated_reason:13} rounds={out.rounds} "
              f"gold_correct={ok}", flush=True)
    if attempted:
        print(f"\n[smoke] gold-correct repairs: {repaired}/{attempted} "
              f"({100 * repaired // attempted}%) — policy contract_pass loop drove targeted fixes.")
    else:
        print("[smoke] no silent starting points produced (try more cases).")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Online targeted-repair policy (closes §8.3 gap): "
                                             "structured goldless diagnosis -> constrained repair loop.")
    ap.add_argument("--online-smoke", action="store_true", help="run the policy on real silent cases via the proxy LLM")
    ap.add_argument("--models", default="gpt-4o", help="comma-separated models for the smoke")
    ap.add_argument("--n", type=int, default=6, help="max silent cases for the smoke")
    ap.add_argument("--budget", type=int, default=3, help="repair round budget")
    a = ap.parse_args(argv)
    if a.online_smoke:
        return _online_smoke([m.strip() for m in a.models.split(",")], a.n, a.budget)
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())

