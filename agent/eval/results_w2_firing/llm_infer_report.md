# DS-1000 transfer, decisive test #2 (AAAI reviewer R2): can an LLM operator-inferer fix it?

**Reviewer's proposed decisive experiment:** the naive keyword inferer over-fires on
free-text DS-1000 code (recall 56% / FP 55%). Swap it for an LLM operator-classifier
(the repo already has `intent_llm.py`); if end-to-end detection reaches **recall > 70%
AND FP < 20%**, the "transfer fails in the wild" story becomes "transfer works once the
operator intent is recovered by a trainable component" — the single most decisive fix.

**Controlled A/B/C** (`w2_llm_rescore.py`): the SAME 80 cached DS-1000 cases (same tasks,
same frontier-generated solutions, same DS-1000 gold labels) rescored with the inferer
swapped. The LLM classifier is given the 28 operator ids + an explicit `none` escape hatch.

## Result — the target is NOT reached (honest negative)

| inferer | recall (fire on silent) | FP (fire on pass) | abstain | hits >70%/<20%? |
|---|---|---|---|---|
| regex (naive keyword) | 10/18 = **56%** [34–75] | 33/62 = **53%** [41–65] | 0/80 | ✗ (FP too high) |
| LLM, balanced prompt | 1/18 = **6%** | 3/62 = **5%** | 65/80 | ✗ (recall collapses) |
| LLM, conservative prompt | 0/18 = **0%** | 0/62 = **0%** | 80/80 | ✗ (abstains on everything) |

**Neither endpoint works.** The regex inferer over-fires (FP 53%); the LLM inferer, once
given a `none` option, over-abstains (recall 0–6%). There is no operating point near the
reviewer's bar. The AAAI-decisive experiment **fails**, and we report it as such.

## Why (diagnosed per-case, honestly)

The 18 DS-1000 "silent" cases are the crux:
- Some genuinely ARE our operators but phrased unusually — e.g. pid 241/242 are
  merge-keep-left (`left_join_keep_all`), yet the LLM classifier abstained (missed the
  match). Frontier NL→operator classification is not reliable even on true positives.
- Many are only superficially similar — e.g. pid 42 "merge the first two header rows of an
  Excel sheet" (not a join at all), pid 225 "fill NaNs with non-uniform values" (not
  nan-as-zero) — where the regex inferer mis-fires and the LLM correctly abstains.

So the transfer bottleneck is a genuine **precision/recall tradeoff in operator inference**
that a prompt-based frontier classifier does not resolve: tighten it and recall dies, loosen
it and FP returns.

## Honest implication for the paper

1. This **confirms** the method is scoped to settings where operator-level intent is
   **given** (structured task specs — our Nature N=1408 pipeline supplies op+params), not
   recovered from arbitrary free-text code.
2. The optimistic "just add a classifier" patch does **not** work at frontier quality; a
   real solution needs a trained NL→operator+params parser with calibrated abstention —
   an open problem we now bound quantitatively, not hand-wave.
3. Net effect on venue fit: this **lowers** the ceiling for a general-purpose *method*
   paper and **raises** the value of the *measurement + honest-boundary* framing. The
   contribution is: silent errors are pervasive (measured), typed contracts solve detection
   +repair *given operator intent* (proven), and recovering that intent from raw code is
   the quantified open gap (this file).

Raw: `firing_llm_infer.json` (per-case op assignments for all three inferers). Repro:
`LLM_API_BASE=.. LLM_API_KEY=.. python eval/w2_llm_rescore.py --infer-model gpt-5.4`.
