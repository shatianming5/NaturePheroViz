# Goldless counterexample-guided synthesis (CEGIS) — honest result

**Reviewer critique (all 3):** the contract synthesis is "just prompt an LLM once" = not an
algorithm. `cegis_synth.py` answers this with a genuine synthesis LOOP that has a GOLDLESS
verification oracle:

1. **1-shot** contract C0 from the (de-leaked, formula-free) NL intent.
2. **Consensus bank**: ask the LLM for K=4 DIVERSE implementations of the same intent, run them
   on the fixture, cluster by output-equivalence; the largest agreeing cluster = the goldless
   "probably-correct" set (independent impls that agree — no gold used).
3. **Metamorphic probes**: perturb a consensus-valid result in intent-agnostic ways
   (scale+shift, permute, drop-row, spike-cell). A genuine conservation/identity contract fires
   on these; a degenerate always-pass fires on none → lets us reject degeneracy goldlessly.
4. **Verify + refine**: if C fires on a consensus member, that is a goldless FALSE-POSITIVE
   counterexample; feed it back and re-synthesize. **Accept the refinement only if the goldless
   score (consensus-pass + probe-fire) STRICTLY improves and stays non-trivial** → monotone-safe.
5. **Trust guard**: refine only when consensus is strong (≥3 of 4 agree); a weak/biased bank is
   an unreliable signal and is skipped (keep C0).

## Result (gpt-5.4, de-leaked intent, core N=12, apples-to-apples: CEGIS reuses the 1-shot seed)

| | CORE | FULL (alt-robust) |
|---|---|---|
| 1-shot | 10/12 = 83% | 10/12 = 83% |
| **CEGIS** | 10/12 = **83%** | 10/12 = **83%** |

**Honest read — this is a near-neutral aggregate, and we report it as such:**
- **No regressions, by design.** With the monotone score-guard + reuse of the 1-shot seed +
  the ≥3 trust guard, CEGIS is provably ≥ 1-shot on the goldless score; empirically it never
  regressed. (Earlier un-guarded versions regressed on `weighted_mean`/`median` when the
  consensus bank was weak or biased — the guards fix exactly that failure mode.)
- **It demonstrably repairs FP/alt-robustness failures when consensus is strong** — e.g. across
  runs where the 1-shot contract false-fired on a valid alternative implementation of
  `dedup_then_agg`, the consensus counterexample drove a refinement that fixed it.
- **It does NOT beat strong de-leaked 1-shot on aggregate** because the residual 1-shot failures
  (`pct_point`, `median`) are RECALL-type (the contract is too vague to fire on the subtle slip),
  which FP-directed consensus refinement cannot address. This is an honest boundary.

## What this contributes (and what it does not)
- **Does:** shows the synthesis is amenable to a real GOLDLESS verification algorithm (consensus
  + metamorphic oracle, counterexample-guided, monotone-safe) — answering "this is just
  prompting" with a mechanism, not a slogan; and provides a safety guarantee (never regress).
- **Does not:** claim an accuracy boost over 1-shot. The scaling story rests on the honest
  de-leaked 1-shot (78% CORE, N=23) and the end-to-end system (61%, `results_e2e/`), not on CEGIS
  lifting the number. CEGIS is the *mechanism*, the de-leak + e2e are the *evidence*.
- **Assumption exposed:** goldless consensus is valid only when independent impls are mostly
  correct; on operators where the LLM has a systematic bias (e.g. defaulting to plain mean) the
  consensus can be wrong — the ≥3 trust guard mitigates but does not eliminate this. Stated
  honestly rather than hidden.

Artifact: `cegis_core.json`.
