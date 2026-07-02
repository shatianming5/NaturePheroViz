# Auto-synthesized goldless contracts from NL (AAAI T1-B: novelty + scalability)

**Reviewer critiques this addresses:**
- **W5 (novelty):** "this is design-by-contract / property-based testing with 28
  HAND-WRITTEN assertions — the mechanism is 40 years old."
- **W4 (scalability):** "hand-written contracts don't scale to unseen operators."

**Experiment:** a frontier LLM SYNTHESIZES each goldless contract from ONLY the NL intent +
param names + result schema. It never sees the hand-written contract, nor the correct/wrong
implementations. The auto-contract is then tested exactly as the hand-written one:

- fire on `wrong_fn` (the silent slip)                 → should FIRE
- pass on `correct_fn` (intended impl)                 → should NOT fire
- pass on every `alt_correct_fn` (other valid impls)   → should NOT fire (FP robustness)

Two bars: **CORE** = fires-on-slip AND passes-on-correct (the invariant discriminates the
error); **FULL** = CORE and robust to all alternative valid implementations. The evaluation
rules out degenerate always-fire / never-fire contracts by construction.

## Result (`results_autocontract/`, model gpt-5.4, 11 pandas operators, best-of-3)

| bar | auto-synthesized correct | 95% CI |
|---|---|---|
| exec-ok (the synthesized code runs) | **11/11 = 100%** | — |
| **CORE** (fire-on-slip AND pass-on-correct) | **8/11 = 73%** | [43–90] |
| **FULL** (+ robust to alternative valid impls) | **7/11 = 64%** | [35–85] |

**7 operators got a fully-correct goldless contract with NO human writing the invariant:**
order_dependent_dedup, resample_boundary, string_normalize_join, join_fanout,
null_in_agg_count, scale_before_split_leakage, latlon_swap.

Honest failures (3): `dtype_coerce` and `lookahead_return` — the LLM's invariant missed the
slip (fire-on-wrong = False); `index_align` — the invariant fired on a valid alternative
(alt-robustness). These are the operators whose invariant is subtle (positional alignment,
look-ahead masking); a human still helps there.

## Why this matters for the paper (novelty + scalability, reframed)

1. **Novelty (W5) upgraded:** the contribution is no longer "we hand-wrote 28 assertions".
   It is **automatic goldless operator-invariant synthesis from NL** — a frontier LLM,
   given only the intent, writes a contract that catches the silent semantic error and
   passes legitimate implementations, for ~2/3 of operators. That is a mechanism claim, not
   a manual-labor claim, and it is not what property-based testing does (PBT needs a human
   to state the property; here the property is generated from NL).
2. **Scalability (W4) answered with evidence:** extending to a new operator no longer
   requires a human to hand-craft the invariant — the LLM synthesizes a working one 64–73%
   of the time zero-shot, and a human need only vet/repair the ~1/3 subtle cases. This is a
   human-in-the-loop scaling story with a measured automation rate, not an aspiration.
3. **Honest limit:** subtle invariants (positional alignment, look-ahead) still need a
   human; and FP-robustness against alternative valid impls is the harder bar (64% vs 73%).

Raw: `autocontract.json` (per-operator fire/pass/alt-robust). Repro:
`LLM_API_BASE=.. LLM_API_KEY=.. python eval/autocontract_synth.py --model gpt-5.4 --retries 3`.
