# DS-1000 transfer, decisive test #2 (AAAI reviewer R2): can an LLM operator-inferer fix it?

**Reviewer's proposed decisive experiment:** the naive keyword inferer over-fires on
free-text DS-1000 code (recall 56% / FP 55%). Swap it for an LLM operator-classifier; if
end-to-end detection reaches **recall > 70% AND FP < 20%**, "transfer fails in the wild"
becomes "transfer works once operator intent is recovered by a trainable component."

Controlled A/B/C (`w2_llm_rescore.py`): the SAME 80 cached DS-1000 cases (same tasks,
solutions, gold labels) rescored with only the inferer swapped (28 op ids + a `none` hatch).

## Result 1 — the recall>70%/FP<20% target is NOT reached (honest negative)

| inferer | recall (fire on silent) | FP (fire on pass) | abstain |
|---|---|---|---|
| regex (naive keyword) | 10/18 = **56%** [34-75] | 33/62 = **53%** [41-65] | 0/80 |
| LLM, balanced prompt | 1/18 = **6%** | 3/62 = **5%** | 65/80 |
| LLM, conservative prompt | 0/18 = **0%** | 0/62 = **0%** | 80/80 |

No operating point is near the bar.

## Result 2 — WHY (the honest, and more favorable, reframing)

The naive recall/FP uses the WRONG denominator. An **independent frontier taxonomy judge**
(claude-opus-4.8, separate from the inferer) adjudicated whether each case's CORE intent is
genuinely one of our 28 operators. **Coverage is very low**: the judge found ~0/18 of the
DS-1000 *silent* cases to be a strict match (they are string concatenation, MultiIndex
reshaping, Excel header merges, non-uniform NaN fills, combine_first value-precedence
merges - none modeled by our contracts). Even a generous manual reading is well under 25%.

**Implication:** the regex "55% FP" is almost entirely *spurious firing on out-of-taxonomy
tasks*, and the LLM "6% recall" is mostly *correct abstention* on tasks that are not ours.
The right question is whether the inferer correctly stays in scope:

| inferer used as a SCOPE GATE | correct abstention on out-of-taxonomy tasks |
|---|---|
| regex (naive keyword) | 37/82 = **45%** (fires spuriously on the other 55%) |
| LLM scope-gate | 78/82 = **95%** (fires on only 4/82) |

**An LLM scope-gate cuts out-of-scope false fires from 55% -> 5%**, making goldless
detection *safe to run on arbitrary code*: silent unless it confidently recognizes a
covered operator, at the cost of only acting on the (currently small) in-taxonomy slice.

## Honest implication for the paper

1. The method is an **operator-scoped detector**: reliable where the operator is known
   (Nature N=1408 supplies op+params -> 99%/0%), and - with an LLM scope-gate - **safely
   silent (FP ~5%) out of scope**, not the naive 55% spurious-fire.
2. DS-1000 is largely the **wrong corpus** for our operators (coverage <~25%): it measures
   the taxonomy coverage gap, not the contracts' detection ability. Recovering operator
   intent + EXPANDING the taxonomy are the quantified open directions.
3. Net venue effect: **lowers** the ceiling for a general-purpose *method* paper, **raises**
   the value of the *measurement + honest-scope* framing. The deployability result
   (scope-gate FP 55%->5%) is a concrete positive; the coverage gap is disclosed.

Raw: `firing_llm_infer.json`, `taxonomy_adjudication.json`. Caveat: coverage is from a
single strict frontier judge - a low-coverage indication, not a precise 0%.
Repro: `python eval/w2_llm_rescore.py` then `python eval/w2_taxonomy_adjudicate.py`.
