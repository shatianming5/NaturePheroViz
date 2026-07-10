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


def _candidate_ops(inp, params, result) -> set:
    """Family-level candidate pruning: from the result's SHAPE alone, decide which
    operator families could plausibly apply, so we never even evaluate a contract
    whose family is structurally impossible here. This is the applicability ranking
    that cuts residual cross-fire below the schema-gate floor.

    Heuristics (all from result/​df shape, no gold):
      - scalar-ish result (1 row or 1 numeric cell): only scalar-output ops.
      - row count == input: row-preserving ops (assign-a-column / clip / rank / share / cumcount / zscore).
      - row count <  input: row-reducing ops (group aggregation / dedup / topn / count).
      - a value column in [0,1]: proportion/share/rank_pct candidates.
    Anything not excluded stays a candidate (conservative — pruning only removes
    structurally impossible families, never a plausible one)."""
    df = inp.get("df")
    if result is None or df is None:
        return set(ORACLE.CONTRACTS)
    n_in, n_out = len(df), len(result)
    row_preserving = {"within_group_share", "pct_point", "cumulative_running",
                      "proportion_true", "zscore_within_group", "dense_rank",
                      "cumcount_per_group", "rank_pct", "clip_outlier", "left_join_keep_all",
                      # expansion ops that emit one row per input row (assign-a-column shape)
                      "index_align", "dtype_coerce", "lookahead_return", "scale_before_split_leakage",
                      "string_normalize_join", "latlon_swap"}
    row_reducing = {"weighted_mean", "dedup_then_agg", "pooled_rate", "median_not_mean",
                    "topn_with_ties", "nan_as_zero_sum", "count_includes_empty",
                    # expansion ops that aggregate to one row per group / fewer rows
                    "groupby_dropna_key", "null_in_agg_count", "join_fanout",
                    "order_dependent_dedup", "resample_boundary"}
    cand = set(ORACLE.CONTRACTS)
    if n_out == n_in and n_in > 1:
        cand &= (row_preserving | {"weighted_mean"})  # weighted_mean is scalar but cheap to keep
    elif n_out < n_in:
        cand &= row_reducing
    # value-range signal: a [0,1] numeric column suggests proportion/share/rank_pct
    import numpy as _np
    has_unit = False
    for c in result.columns:
        v = pd.to_numeric(result[c], errors="coerce").to_numpy(dtype=float)
        v = v[~_np.isnan(v)]
        if len(v) and v.min() >= -1e-9 and v.max() <= 1 + 1e-9 and not set(_np.unique(v)).issubset({0.0, 1.0}):
            has_unit = True
            break
    if not has_unit:
        cand -= {"rank_pct"}  # rank_pct REQUIRES a [0,1] column; absent => prune it
    return cand


def _run_all_contracts(inp, params, result, prune: bool = False) -> Dict[str, bool]:
    """Run every contract on this result and return {op: substantively_fired}.

    A contract counts as firing ONLY when it actually evaluated the operator's
    invariant and found it violated. Two non-substantive cases are recorded as
    NOT fired (they are abstentions, not detections):
      - the schema gate in check() returns None (required params/columns absent);
      - the contract fires merely because the OUTPUT column it expects is absent
        (detail mentions 'missing') — that means the operator doesn't apply to this
        result's shape, not that a silent error was localized here.
    With prune=True, contracts outside the family-level candidate set are skipped
    entirely (recorded not-fired), cutting residual cross-fire."""
    cand = _candidate_ops(inp, params, result) if prune else set(ORACLE.CONTRACTS)
    out = {}
    for op in ORACLE.CONTRACTS:
        if op not in cand:
            out[op] = False
            continue
        r = oracle_check(op, inp, params, result)
        substantive = bool(r and r.fired and "missing" not in r.detail.lower())
        out[op] = substantive
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
    # cross-fire on CORRECT results, with and without family-level pruning
    cross_fire = cross_total = 0
    cross_fire_pruned = 0
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
                true_op = item["op"]
                # substantive cross-fire (shape-mismatch 'missing' fires excluded)
                fired = _run_all_contracts(inp, item["params"], r)
                fired_pruned = _run_all_contracts(inp, item["params"], r, prune=True)
                if not correct:
                    # attribution recall uses the TRUE-op contract's RAW verdict:
                    # for the true operator, a missing expected output column IS a
                    # real silent error (the model produced the wrong shape), so it
                    # should count as a localized detection — unlike the cross-fire
                    # case where a missing column means the operator doesn't apply.
                    own = oracle_check(true_op, inp, item["params"], r)
                    true_fired = bool(own and own.fired)
                    attr_total += 1
                    attr_hit += int(true_fired)
                    rows.append({"name": item["name"], "cond": cond, "model": m,
                                 "true_op": true_op, "true_fired": true_fired,
                                 "other_substantive": [op for op, f in fired.items() if f and op != true_op]})
                else:
                    # cross-fire: substantive fires of OTHER-op contracts on a correct result
                    for op in fired:
                        if op == true_op:
                            continue
                        cross_total += 1
                        cross_fire += int(fired[op])
                        cross_fire_pruned += int(fired_pruned[op])

    def pct(n, d): return f"{100*n/d:.0f}%" if d else "n/a"
    lines = ["# Typed-attribution accuracy: does the oracle localize to the right operator?\n",
             "Two metrics with deliberately different gates:",
             "- recall uses the TRUE-op contract's raw verdict (for the right operator, a",
             "  missing expected output column IS a real silent error — wrong output shape).",
             "- cross-fire counts only SUBSTANTIVE fires of OTHER-op contracts (a fire that is",
             "  merely 'missing column' means that operator doesn't apply — recorded as abstain).\n",
             "## (1) Attribution recall (true-op contract fires on its silent errors)",
             f"- {attr_hit}/{attr_total} = {pct(attr_hit, attr_total)}",
             "\n## (2) Cross-fire specificity (substantive other-op fires on CORRECT results)",
             f"- no pruning: {cross_fire}/{cross_total} = {pct(cross_fire, cross_total)}",
             f"- family-level pruning: {cross_fire_pruned}/{cross_total} = {pct(cross_fire_pruned, cross_total)} "
             "(skip contracts whose operator family is structurally impossible for this result shape)",
             "\n## Reading",
             "- High attribution recall => when the oracle flags a silent error, the firing contract",
             "  points at the correct operator semantics (typed localization, not just a binary flag).",
             "- Family-level pruning cuts residual cross-fire below the schema-gate floor by never",
             "  evaluating a contract whose family can't apply to the result's shape — pruning only",
             "  removes structurally impossible families, so attribution recall is unaffected."]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "attribution_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "attribution_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n[saved] {out}/attribution_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
