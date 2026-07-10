# Localization-only ablation (AAAI reviewer R2, decisive test #1)

**Reviewer's mechanism-level critique (W2′):** the targeted arm conflates three advantages
over self-debug — (1) certainty ("IS wrong" vs "may be wrong"), (2) localization ("the
`<op>` step"), and (3) the specific violated invariant. Without disentangling, one cannot
claim the *typed contract signal* (3) is the key — maybe knowing *which operator* is wrong
+ certainty (1+2) already suffices, which would be far cheaper than the contract machinery.

**The ablation arm (`localize`):** identical to `targeted` EXCEPT it withholds the invariant
detail. It says "your result IS wrong; the at-fault step is `<op>`; fix only that step" —
certainty + localization, but NOT *how/why* it is wrong. Same stopping signal as targeted
(contract-pass), same everything else. This isolates advantage (3).

## Result (`results_repair_ablation_loc/`, core grid, 3 frontier models, N=31)

| arm | signal it carries | success [95% Wilson CI] |
|---|---|---|
| generic | "may be wrong", retry | 3/31 = **10%** [3–25] |
| selfdebug | "may be wrong" + strong self-reasoning | 1/31 = **3%** [1–16] |
| **localize** | **certainty + WHICH operator (no invariant)** | 14/31 = **45%** [29–62] |
| **targeted** | **+ the typed violated invariant** | 25/31 = **81%** [64–91] |
| ceiling | gold diff | 27/31 = 87% [71–95] |

**The typed invariant adds +35 pts on top of localization (45% → 81%), and the CIs are
DISJOINT ([29–62] vs [64–91]).** Both components matter, and the invariant's contribution
is large and statistically significant — the claim does NOT collapse to "localization
suffices".

## Nuance (per-operator, honest)

- **Invariant is decisive** where the error is "which statistic / which rows":
  `pct_point` 1/6 → 6/6, `count_includes_empty` 1/6 → 4/6, `dedup_then_agg` 2/6 → 5/6.
  Knowing *which step* is not enough; the model needs to be told *what invariant it
  violated* (e.g. "per-group shares must sum to 1", "count dropped NaN-key rows").
- **Localization suffices** where the fix is obvious once the step is named:
  `weighted_mean` 2/2, `within_group_share` 2/2 already at localize.
- **Blind spot preserved**: `zscore_within_group` targeted 0/2 (pre-declared §3.7 contract
  blind spot) — disclosed.

## What this settles for the paper

The repair gain is **not** merely "any specific hint beats no hint" and **not** merely
"knowing which step is wrong". Decomposed against three progressively stronger baselines:
generic 10% < self-debug (strong scaffolding) 3% < localization-only 45% < **typed
invariant 81%**. The typed contract signal carries a large, statistically-significant,
independent share of the repair gain (+35 pts over localization alone). This directly
answers the mechanism-level confound.

Raw: `repair_targeted.json` (31 starts × 5 arms × 3 models). Repro:
`LLM_API_BASE=.. LLM_API_KEY=.. python eval/transform_repair.py --grid core --models gpt-5.4,claude-opus-4.8,gpt-5.5 --out eval/results_repair_ablation_loc`.
