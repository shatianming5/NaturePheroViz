"""
attribution_eval.py — round-3 P0 (VenueReadiness): typed-attribution accuracy.

The oracle doesn't just say "wrong"; it says WHICH operator semantics is violated.
This measures whether that attribution is correct: given a silent error, we run ALL
contracts (not just the case's own), and check that the contract for the TRUE
operator family fires — i.e. the oracle localizes the error to the right operator
semantics, not a random one.

Two numbers:
  - attribution recall: of silent errors where the true-op contract is applicable,
    how often does it fire (localizes correctly).
  - cross-fire specificity: when we run an UNRELATED contract on a correct result,
    how often does it wrongly fire (should be low — contracts are operator-specific).

Run:  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/attribution_eval.py
      cd agent && python eval/attribution_eval.py --offline   # gold-based sanity, no LLM
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

import eval.transform_oracle as ORACLE  # noqa: E402
from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.transform_bench import _cases  # noqa: E402


def _run_all_contracts(inp, params, result) -> Dict[str, bool]:
    """Run every contract on this result via check() (so the schema gate applies);
    return {op: fired}. A contract whose required params/columns aren't present
    abstains (check returns None) and is recorded as not-fired."""
    out = {}
    for op in ORACLE.CONTRACTS:
        r = oracle_check(op, inp, params, result)
        out[op] = bool(r and r.fired)
    return out


def _offline() -> int:
    """Sanity without LLM: inject the known silent slip per case, confirm the TRUE
    contract fires. (Cross-fire needs real outputs; measured in the --run path.)"""
    from collections import Counter
    cases = _cases()
    seen: Counter = Counter()
    ok = correct_attr = total = 0
    for c in cases:
        seen[c["op"]] += 1
        if seen[c["op"]] > 1:
            continue  # one per op for the offline sanity
        # craft a wrong result by perturbing the gold minimally is op-specific;
        # instead reuse the gold and confirm the true contract at least APPLIES
        # (doesn't crash) and PASSES on gold — full slip injection is in --run.
        df = c["df"]
        g = c["gold"](df, c["df2"]) if "df2" in c else c["gold"](df)
        res = g if isinstance(g, pd.DataFrame) else pd.DataFrame({"value": [float(g)]})
        inp = {"df": df, **({"df2": c["df2"]} if "df2" in c else {})}
        own = oracle_check(c["op"], inp, c["params"], res)
        total += 1
        if own is not None and not own.fired:
            ok += 1
    print(f"offline sanity: true-op contract passes-on-gold for {ok}/{total} ops")
    return 0 if ok == total else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--out", default="eval/results_attribution")
    a = ap.parse_args(argv)
    if a.offline:
        return _offline()
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (or --offline)."); return 1

    from collections import Counter
    from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct, MODELS

    seen: Counter = Counter()
    cases = []
    for c in _cases():
        seen[c["op"]] += 1
        if seen[c["op"]] > 2:   # 2 instances per op is enough for attribution
            continue
        cases.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})

    # attribution: on silent errors, does the TRUE-op contract fire?
    attr_hit = attr_total = 0
    # cross-fire: on CORRECT results, how often does a DIFFERENT-op contract fire?
    cross_fire = cross_total = 0
    rows = []
    for item in cases:
        inp = {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}
        for cond in ("ambiguous", "clarified"):
            for m in MODELS:
                code = _llm_code(item, item[cond], m)
                r = _exec(item, code) if code else None
                if r is None:
                    continue
                correct = _gold_correct(item, r)
                fired = _run_all_contracts(inp, item["params"], r)
                true_op = item["op"]
                if not correct:
                    attr_total += 1
                    attr_hit += int(fired.get(true_op, False))
                    rows.append({"name": item["name"], "cond": cond, "model": m,
                                 "true_op": true_op, "true_fired": fired.get(true_op, False),
                                 "other_fired": [op for op, f in fired.items() if f and op != true_op]})
                else:
                    # cross-fire: count other-op contracts that fire on a correct result
                    for op, f in fired.items():
                        if op == true_op:
                            continue
                        cross_total += 1
                        cross_fire += int(f)

    def pct(n, d): return f"{100*n/d:.0f}%" if d else "n/a"
    lines = ["# Typed-attribution accuracy: does the oracle localize to the right operator?\n",
             "## (1) Attribution recall (true-op contract fires on its silent errors)",
             f"- {attr_hit}/{attr_total} = {pct(attr_hit, attr_total)}",
             "\n## (2) Cross-fire specificity (other-op contracts on CORRECT results)",
             f"- {cross_fire}/{cross_total} other-op contract evaluations fired = {pct(cross_fire, cross_total)} "
             "(lower = more operator-specific)",
             "\n## Reading",
             "- High attribution recall => when the oracle flags a silent error, the firing contract",
             "  points at the correct operator semantics (typed localization, not just a binary flag).",
             "- Low cross-fire => contracts are operator-specific; an unrelated contract rarely",
             "  misfires on a correct result, so the attribution label is trustworthy."]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "attribution_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "attribution_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n[saved] {out}/attribution_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
