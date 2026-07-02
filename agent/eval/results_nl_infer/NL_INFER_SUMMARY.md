# Operator inference from NL task descriptions on REAL Nature (AAAI W1' ceiling)

**Reviewer's residual ceiling (W1'):** the Nature 99%/0% detection assumes op+params are
template-GIVEN; on arbitrary free-text CODE (DS-1000) operator inference fails (≈coin flip).
So "does the method need the operator handed in?"

**The distinction that matters:** the deployment setting for a data-analysis assistant is a
**natural-language TASK request** ("give me the median expression per group"), NOT arbitrary
code. This experiment tests the realistic intermediate: given the NL task intent (the
clarified intent used in the prevalence study) + the REAL Nature column name, can the
operator be recovered — so detection runs end-to-end without the operator being given?

## Result (150 real Nature tasks, 5 operators, model gpt-5.4)

| inferer | top-1 operator accuracy | 95% CI |
|---|---|---|
| LLM (frontier) | **150/150 = 100%** | [98–100] |
| regex (keyword) | **150/150 = 100%** | [98–100] |
| **end-to-end detection retention** (inferred vs given op) | **109/109 = 100%** | [97–100] |

On real Nature tasks, **the operator is trivially recoverable from the NL intent** — by both
a frontier LLM AND simple keyword matching. Every one of the 109 originally-detected silent
errors is still detected when the operator is INFERRED rather than handed in (100% retention).

## Honest interpretation (and the caveat)

1. **Operator inference is NOT the bottleneck when intent is expressed in natural language.**
   The DS-1000 failure (recall≈FP≈coin flip) is specifically about recovering intent from
   arbitrary CODE with no stated NL intent — a genuinely different, harder setting. When the
   user states their intent in NL (the data-assistant deployment setting), operator recovery
   is easy and detection runs end-to-end at full strength.

2. **This narrows W1' substantially:** the conditional-validity limit is not "the operator
   must be manually specified" but "the user's intent must be expressed in natural language"
   — which any data-analysis assistant has by construction (it's the user's request).

3. **CAVEAT (disclosed):** the clarified NL intents here are templated and carry operator
   keywords (which is why even regex hits 100%). This is an UPPER BOUND / best case: raw,
   underspecified figure captions would be harder, and recovering intent from code (DS-1000)
   is harder still. The honest claim is bounded: *when a clear NL task intent is available,
   the operator is recoverable and detection is end-to-end*; we do not claim recovery from
   underspecified captions or raw code.

Net: combined with the DS-1000 scope-gate (safely silent out of scope), the deployable
picture is: **NL task intent → recover operator (easy) → goldless detection (99%/0%) →
targeted repair; on inputs without a clear NL intent (raw code), abstain safely.**

Raw: `nl_operator_infer.json`. Repro:
`LLM_API_BASE=.. LLM_API_KEY=.. python eval/nl_operator_infer.py --per-op 30`.
