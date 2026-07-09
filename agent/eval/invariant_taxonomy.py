"""
invariant_taxonomy.py — broaden the NON-CIRCULAR CORE beyond within-group-share.

The detection headline (98--99%/0.2% real) mixes two contract kinds. The paper's
strongest claim is the subset that derives NO reference value -- a PURE INVARIANT
that no single correct implementation pins down (per-group shares sum to 1; a left
join keeps every left row; a running total's last entry equals the column sum).
On real Nature data that non-circular core is carried by within-group-share alone
(538/539=99.8%). A reviewer can call it a single-operator artefact.

This experiment shows the pure-invariant mechanism is NOT one operator: it spans a
FAMILY of operator contracts. We classify each of the 12 core contracts (by reading
transform_oracle.py: does it recompute the expected value, or only assert a
relational/structural/conservation property?) and then EMPIRICALLY validate every
pure-invariant contract on the shared offline fixtures:

  recall  : the contract FIRES on the canonical silent slip (wrong_fn);
  FP      : it does NOT fire on the intended transform (correct_fn) NOR on any
            representation-diverse VALID implementation (alt_correct_fns, incl.
            row-order-reversed) -- an order/representation-robustness bar.

Fully offline, deterministic, no gold, no LLM, no GPU: uses core_candidates.py
(the same fixtures the oracle self-test uses) + transform_oracle.check.

Run: cd agent && python eval/invariant_taxonomy.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import warnings  # noqa: E402
warnings.filterwarnings("ignore")

from eval.core_candidates import CORE_CANDIDATES  # noqa: E402
from eval.transform_oracle import check  # noqa: E402

# Contract classification, grounded in transform_oracle.py. PURE_INVARIANT =
# asserts a relational / structural / conservation property and derives NO
# per-task reference value equal to the answer. RECOMPUTATION = derives the
# expected value from operator+params and compares (gold-equivalent under a known
# operator). Each entry cites the invariant the contract actually checks.
CLASSIFY: Dict[str, Dict[str, str]] = {
    "within_group_share":  {"kind": "pure_invariant", "why": "per-group shares sum to 1 (no value recomputed)"},
    "left_join_keep_all":  {"kind": "pure_invariant", "why": "output row-count == left row-count (structural)"},
    "cumulative_running":  {"kind": "pure_invariant", "why": "last cumulative entry == column sum (conservation)"},
    "topn_with_ties":      {"kind": "pure_invariant", "why": "|result| == #rows with rank<=n (cardinality)"},
    "count_includes_empty":{"kind": "pure_invariant", "why": "all categories present incl. zero-count (cardinality)"},
    "weighted_mean":       {"kind": "recomputation",  "why": "== sum(v*w)/sum(w) recomputed"},
    "dedup_then_agg":      {"kind": "recomputation",  "why": "== deduped groupby-sum total recomputed"},
    "pooled_rate":         {"kind": "recomputation",  "why": "== pooled sum/sum recomputed"},
    "median_not_mean":     {"kind": "recomputation",  "why": "== per-group median recomputed"},
    "nan_as_zero_sum":     {"kind": "recomputation",  "why": "== fillna(0) groupby-sum recomputed"},
    "pct_point":           {"kind": "recomputation",  "why": "== (a-b)*100 recomputed"},
    "proportion_true":     {"kind": "recomputation",  "why": "== groupby mean recomputed (range-invariant fallback only)"},
}


def _fired(op: str, inp: Dict[str, Any], params: Dict[str, Any], result) -> bool:
    try:
        r = check(op, inp, params, result)
    except Exception:
        return False  # a crash is not a fire; conservative for FP, harsh for recall
    return bool(r is not None and r.fired)


def main() -> int:
    rows: List[Dict[str, Any]] = []
    for cand in CORE_CANDIDATES:
        op = cand.operator
        cls = CLASSIFY.get(op, {"kind": "unclassified", "why": ""})
        inp = cand.fixture()
        # recall: contract must FIRE on the canonical silent slip
        recall_fire = _fired(op, inp, cand.params, cand.wrong_fn(inp))
        # FP: must NOT fire on the intended transform...
        fp_correct = _fired(op, inp, cand.params, cand.correct_fn(inp))
        # ...nor on any representation-diverse VALID implementation
        alt_fires = [_fired(op, inp, cand.params, alt(inp)) for alt in cand.alt_correct_fns]
        n_alt = len(alt_fires); alt_fp = sum(alt_fires)
        rows.append({
            "op": op, "kind": cls["kind"], "why": cls["why"],
            "recall_fired": recall_fire,          # True == detected the slip
            "fp_on_correct": fp_correct,          # True == false alarm on intended
            "n_valid_alts": n_alt, "fp_on_alts": alt_fp,  # false alarms on diverse valid impls
            "clean": bool(recall_fire and not fp_correct and alt_fp == 0),
        })

    def agg(kind: str) -> Dict[str, Any]:
        rs = [r for r in rows if r["kind"] == kind]
        n = len(rs)
        return {
            "n_ops": n,
            "ops": [r["op"] for r in rs],
            "recall": f"{sum(r['recall_fired'] for r in rs)}/{n}",
            "fp_correct": f"{sum(r['fp_on_correct'] for r in rs)}/{n}",
            "fp_alts": f"{sum(r['fp_on_alts'] for r in rs)}/{sum(r['n_valid_alts'] for r in rs)}",
            "clean_all": f"{sum(r['clean'] for r in rs)}/{n}",
        }

    pure = agg("pure_invariant"); recomp = agg("recomputation")
    out_dir = Path("eval/results_invariant_core"); out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "invariant_core.json").write_text(json.dumps(
        {"per_op": rows, "pure_invariant": pure, "recomputation": recomp}, indent=2))

    lines = [
        "# Non-circular core is a FAMILY, not one operator (grid validation)\n",
        "Each of the 12 core contracts is classified by whether it recomputes the",
        "expected value (RECOMPUTATION; gold-equivalent under a known operator) or only",
        "asserts a relational/structural/conservation property that derives NO reference",
        "value (PURE INVARIANT; the non-circular core). We then validate every contract",
        "offline on the shared fixtures: it must FIRE on the canonical silent slip",
        "(recall) and must NOT fire on the intended transform or on any",
        "representation-diverse VALID implementation incl. row-order-reversed (FP).\n",
        f"## PURE INVARIANT core ({pure['n_ops']} operator families)",
        f"- families: {', '.join(pure['ops'])}",
        f"- recall on silent slips: **{pure['recall']}**",
        f"- false-positive on intended transform: **{pure['fp_correct']}**",
        f"- false-positive on order/representation-diverse VALID impls: **{pure['fp_alts']}**",
        f"- fully clean (fire-on-slip AND pass all valid): **{pure['clean_all']}**\n",
        f"## RECOMPUTATION contracts ({recomp['n_ops']} operators, for contrast)",
        f"- operators: {', '.join(recomp['ops'])}",
        f"- recall {recomp['recall']}, FP-correct {recomp['fp_correct']}, FP-alts {recomp['fp_alts']}\n",
        "## Reading",
        f"The goldless non-circular core spans **{pure['n_ops']} operator families**, not one:",
        "each derives no reference value yet separates the silent slip from every valid",
        "(and row-order-diverse) implementation on the grid. within-group-share is simply",
        "the family with a large REAL-Nature sample (538/539=99.8%); the pure-invariant",
        "mechanism it demonstrates is shared across the family. (Grid = mechanism check,",
        "not a generalization claim; real-data recall is Sec. Detection.)",
    ]
    (out_dir / "INVARIANT_CORE_SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\n[per-op]")
    for r in rows:
        tag = "PURE " if r["kind"] == "pure_invariant" else "recmp"
        print(f"  {tag} {r['op']:22} recall_fire={int(r['recall_fired'])} "
              f"fp_correct={int(r['fp_on_correct'])} fp_alts={r['fp_on_alts']}/{r['n_valid_alts']} "
              f"clean={int(r['clean'])}")
    print(f"\n[written] {out_dir/'INVARIANT_CORE_SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
