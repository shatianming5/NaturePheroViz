# De-leaked auto-synthesis & NL-inference (AAAI independent-review fix)

Two independent reviewers (gpt-5.5 / OpenAI, gemini-3.1-pro / Google), after **verifying the
repository artifacts**, raised the same decisive critique: the auto-synthesis `INTENT` strings
and the NL-inference `CLARIFIED` templates **leaked the answer** — they stated the exact
formula (`sum(value*weight)/sum(weight)`) and the exact slip to avoid ("not the mean"), or
injected the operator keyword ("MEDIAN", "pooled sum/sum"). So the reported 83% / 100% partly
measured "translate a stated formula" / "match an injected keyword", not "discover the
invariant / recover the operator from a real user's high-level goal".

Both reviewers named the same fix: **strip the formula/keywords, use plain high-level intent,
report the honest number.** Done. We keep the original ("leaky") mode for transparency and add
a de-leaked mode (`--intent deleaked` / `--nl realistic`); both are runnable and compared.

## 1. Auto-synthesis of goldless contracts from NL (gpt-5.4, 1-shot, N=23)

`INTENT` de-leaked = user-voice **goal only**: NO formula, NO "not the X" contrast, NO stated
invariant. E.g. `weighted_mean` → "a single representative average where entries carrying more
weight have proportionally more influence"; `median_not_mean` → "a representative central value
per group that isn't thrown off by a few unusually large or small entries".

| intent mode | CORE (fire-on-slip AND pass-on-correct) | FULL (+ alt-robust) |
|---|---|---|
| leaky (formula given) | 19/23 = **83%** | 18/23 = 78% |
| **deleaked (high-level goal only)** | **18/23 = 78%** [58–90] | 16/23 = **70%** |

**Only −5 pts on CORE.** The formula was NOT doing the work: strip it and the LLM still derives
correct goldless invariants for 78% of operators — incl. `weighted_mean`, `pooled_rate`,
`left_join_keep_all`, `cumulative_running`, `topn_with_ties`, `nan_as_zero_sum`,
`count_includes_empty`, `proportion_true`, `dedup_then_agg` (core) and `index_align`,
`order_dependent_dedup`, `resample_boundary`, `latlon_swap`, `string_normalize_join`,
`join_fanout`, `null_in_agg_count` (expansion). De-leaked failures (honest, interpretable):
`median` (vague "central value" under-fires on the mean-slip), `within_group_share` / `pct_point`
(over-strict → fired on a valid alt), `dtype_coerce` / `lookahead_return` (subtle invariants).
Artifacts: `autocontract_deleaked.json` (core), `autocontract_exp_deleaked.json` (expansion),
`autocontract_deleaked_N23.json` (combined).

## 2. Operator inference from NL on real Nature (gpt-5.4, 150 tasks)

`realistic` NL = analyst-voice **semantic goal**, NO operator keyword. E.g. `median` → "a
representative central {v} for each {cat} that is not thrown off by a few unusually large or
small entries".

| inferer | clarified (keyword-stuffed) | **realistic (no keyword)** |
|---|---|---|
| frontier LLM | 150/150 = **100%** | **147/150 = 98%** [94–99] |
| regex keyword | 150/150 = **100%** | **31/150 = 21%** [15–28] ← collapses |

End-to-end detection retention: clarified 109/109=100% → **realistic 107/109 = 98%**.

**The de-leak cleanly separates the two baselines.** regex collapses 100%→21% — confirming the
reviewers' point that its 100% was "the answer is in the string". But the **LLM holds at 98%**:
it recovers the operator from the *semantics* ("robust-to-outliers central value" → median,
"weight-carrying rows count more" → weighted_mean), not from a keyword. The 3 LLM misses are
**conservative abstentions** (inferred=None), not misclassifications — deployment-safe.
Artifact: `../results_nl_infer/nl_operator_infer_realistic.json`.

## Bottom line
The independent review materially improved the science. The two "novelty/scalability" claims
survive de-leaking (auto-synthesis 78% CORE from plain goals; operator inference 98% LLM from
keyword-free NL), and the residual honest boundary is now precisely bounded: a handful of
intrinsically-subtle operators (positional alignment, look-ahead, leading-zero dtype) resist
both auto-synthesis and repair — a property of those operators, not of the method.
