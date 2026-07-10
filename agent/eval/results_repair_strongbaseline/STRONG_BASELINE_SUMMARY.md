# Strong-baseline repair (AAAI Fix #1) — targeted contract signal vs SOTA self-debug

**Reviewer ask (W2):** the "targeted 80% vs generic 18%" gap uses a *strawman* generic
baseline ("your result may be wrong, retry"). A fair test must compare against a STRONG
no-gold self-repair baseline (Reflexion / Self-Debug style): step-by-step re-derivation,
explicit enumeration of every error-prone semantic decision, hand-tracing values, self-
critique — **without** any contract signal or disambiguation. Does the typed contract
signal still win, or was it just "any specific hint beats no hint"?

## Setup
`transform_repair.py --grid core`, 4 arms, 3 frontier models (gpt-5.4, claude-opus-4.8,
gpt-5.5), **N=43 shared silent starts**, round budget N=3. The ONLY variable across arms
is the feedback content. Success = hidden gold (never shown to any arm). The new
`selfdebug` arm gets the strong scaffolding but the SAME ambiguous intent as every arm.

## Result (`results_repair_strongbaseline/`)

| arm | success [95% Wilson CI] | over-repair | note |
|---|---|---|---|
| generic (retry only) | 6/43 = **14%** [7–27] | 0% | weak floor |
| **selfdebug (strong: re-derive + enumerate decisions + self-critique)** | 2/43 = **5%** [1–15] | 0% | **SOTA no-gold self-repair — still barely fixes** |
| **targeted (our typed contract signal)** | **34/43 = 79%** [65–89] | **0%** | CI **disjoint** from selfdebug |
| ceiling (gold-diff upper bound) | 40/43 = 93% [81–98] | 5% | give-the-answer ceiling |

**Gate: GO.** targeted 79% vs strong self-debug 5%, **CIs fully disjoint**; over-repair 0%;
mean rounds 1.19 within budget; no significant per-family regression.

## Why this kills the strawman objection

The strong self-debug baseline does **not** just fail to help — it scores **below** the
weak generic retry (5% < 14%). Reason (from the stop-reason telemetry): self-debug drives
the model to **confidently re-derive the same wrong answer** (35/43 fixpoint stops) — more
elaborate reasoning without a *ground-truth-independent error signal* mostly rationalises
the original mistake. Only the **typed contract signal** — a checkable invariant the model
cannot see is satisfiable without actually fixing the operator — flips the outcome
(41/43 targeted runs stop on `contract_pass`).

Per-operator, the decisive families: `pct_point`, `topn_with_ties`, `dedup_then_agg`,
`weighted_mean` are **6/6 or 2/2 (targeted) vs 0/6 or 0/2 (self-debug)**. Honest blind
spot: `zscore_within_group` targeted 0/6 (a pre-declared §3.7 contract blind spot; ceiling
6/6 confirms it is fixable given the answer) — disclosed, not hidden.

**Takeaway for the paper:** the repair win is attributable to the **typed contract signal
itself**, not to "prompting the model to think harder". This directly answers the
strawman-baseline critique.

Raw: `repair_targeted.json` (43 starts × 4 arms × 3 models). Repro:
`LLM_API_BASE=.. LLM_API_KEY=.. python eval/transform_repair.py --grid core --models gpt-5.4,claude-opus-4.8,gpt-5.5 --out eval/results_repair_strongbaseline`.
