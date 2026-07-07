# Master results table — transform fidelity verification

One table reconciling every experiment, its data source, sample size, and result.
Resolves the round-3 reviewer's "57/132 vs 135/56/1" concern: these come from TWO
INDEPENDENT generation runs (calibration vs baseline), each internally consistent;
they are NOT the same 189/192 numbers and must not be cross-added.

## Generation runs (two independent sets of LLM generations)

| run | script | cases | gens | breakdown | purpose |
|---|---|---|---|---|---|
| **calibration** | ambiguity_calibration --bench | 48 grid | 192 | 135 correct + 56 silent + 1 crash | silent-rate, ambiguity calibration, oracle recall/FP |
| **baseline** | baseline_compare | 48 grid | 189 exec-ok | 132 correct + 57 silent (crashes excluded) | 5-detector head-to-head |

> Same 48-case grid, but two independent generations (temperature 0 still has
> sampling jitter via claude reasoning), so 56↔57 silent differ by one. The final
> paper drives both from a single run for one unified count.

## Results by claim

| # | claim | experiment | source run | N | result |
|---|---|---|---|---|---|
| 1 | silent errors are common + systematic | 48-grid | calibration | 96 ambiguous | ambiguous silent 44/96 = 46%; bimodal (5 classes 100%, 5 classes 0%) |
| 2 | model failure, not prompt underspecification | ambiguity calibration | calibration | 96+96 | ambiguous 46% → clarified 12% |
| 2b | not a one-phrasing fluke | clarify_robustness | new | 6 ops ×3 wordings | 92% → 17/8/8% (mean 11%, std 3.9 pts) |
| 3 | goldless oracle catches them | 48-grid | calibration | 56 silent / 135 correct | recall 56/56 = 100%, FP 0/135 = 0% |
| 4 | significantly better than existing means | baseline head-to-head | baseline | 57 silent / 132 correct | ours 100%/0%; exec-pass/validity/consistency 0% recall; self-check 61%/40% |
| 5 | external validity (real data) | nature_real_transform | real-slice | 18 amb / 18 clar | ambiguous silent 13/18 = 72% [CI 49-88]; recall 19/19 = 100% [83-100]; FP 0/17 = 0% [0-18] |
| 6 | scalability (one contract per new op) | scalability_demo | scal | 5 unseen ops | BEFORE abstain 0/9 recall + 0 FP; AFTER 1 contract each → recall up, FP 0/11 |
| 7 | typed attribution localizes the operator | attribution_eval | attr | 25 silent / 1136 cross-evals | attribution recall 25/25 = 100%; cross-fire 8% (88/1136) → 2% (25/1136) with family pruning |
| 8 | phenomenon generalizes across models + scale | qwen_local_eval | qwen (gpudev2) | 48-grid x 3 sizes | ambiguous silent 7B 65% / 14B 54% / 32B 44% (vs closed 46%); oracle recall ≥96%, FP 0% all sizes |
| 9 | typed feedback drives targeted repair (SCALED, one run) | transform_repair | results_repair_scaled | 65 silent / 4 models (gpt-5.4/5.5/5.3-codex + gemini-3.1-pro) | ONE consistent run, all 5 arms on same starts (fixes prior N=43/N=31 splice): generic 18% [11-30], strong self-debug 12% [6-22], localization-only 52% [40-64], **targeted 75% [64-84]**, ceiling 92% [83-97]; over-repair 3%. targeted vs self-debug CIs disjoint; invariant adds +23pts over localization |
| 10 | oracle transfer to external silents (honest bound) | ds1000_repair | results_ds1000_repair | 80 ext silents | contract-fire coverage 6/80=8% (param-free join only); policy 20% ≥ generic 18% via safe abstain; covered subset targeted 3/6 vs generic 1/6 |
| 11 | end-to-end NL→params→oracle (no params handed in) | end2end_infer | results_e2e_infer | 68 grid | op-acc 100%, param-key 100%; recall 84% = params-given UB; FP 0%. NOTE: grid prompts templated → 100% is co-designed UB (see row 13 for real generalization) |
| 12 | NL inferer on external (honest boundary) | oracle_transfer | results_transfer | 275 DS-1000 | keyword coverage 17% but precision 10% (ref-code audit) → true coverage 2% < hand-param 8%: regex needs ML classifier (row 13), confirms params-needed boundary |
| 13 | NL→op generalization (held-out paraphrases) | transform_paraphrase / intent_llm | results_generalize | 19 off-lexicon | regex 26% (overfits grid, abstain-safe: 2/19 miswired) vs **LLM classifier 84%** (16/19, opencode free, per-case JSON) — deployable NL→op; contracts unchanged |
| 14 | oracle REAL firing on external silents (not coverage) | w2_firing | results_w2_firing | DS-1000 (opencode free) | pilot N=12: recall 3/6=50%, FP 0/2; scaled N=30: recall 2/5=40% [12-77], FP 1/6=17% [3-56], crash 19/30 (free-model gen quality) — per-task firing real; small N honest, API model = scale-up |
| 15 | end-to-end scaled cross-model | e2e_pipeline + e2e_scale_analyze | results_e2e_scale | **92** (23 ops × 4 models: gpt-5.4/5.5/5.3-codex + gemini-3.1-pro) | full-system 54/92=**59%** [49-68] (CI width 38→19 vs N=23); op-infer 79%; synth-CORE 73%. Zero-template (only messy NL + raw table). Per-vendor 48-70%. (opus/Anthropic 3rd vendor discarded: proxy timeouts → 0/23 exec-ok, not a real result) |
| 16 | end-to-end miss DECOMPOSITION | e2e_scale_analyze | results_e2e_scale | 38 misses pooled (N=92) | **50% contract-synthesis** (op right, invariant wrong), **34% operator-inference** (auto-synth contract would fire), 16% both → larger share is invariant SYNTHESIS (19 vs 13; CIs overlap → directional) |
| 17 | goldless synthesis scaled cross-model | autocontract_synth + synth_scale_analyze | results_autocontract_scale | **92** (23 ops × 4 models) deleaked | CORE 77/92=**84%** [75-90] (gpt-5.5 96%, codex 87%, gpt-5.4 78%, gemini 74%); FULL 75/92=82%; tightens N=46 [62-86]; de-leaked high-level-goal intent |
| 18 | exemplar prompting does NOT fix synthesis (k=3 reproducibility) | synth_oneshot + repro_aggregate | results_synth_oneshot | 46 × k=3 runs/vendor | reasoning models not bit-reproducible even at temp 0 → k-repeat mean±sd: zero-shot **72±10%** (GPT 83±0% stable, 19/23 every run) > one-shot 57±9% > few-shot 54±7%; run-to-run sd ≈ effect → exemplars don't reliably improve (not a significant backfire); zero-shot is right default |
| 19 | FULL FP-robustness with diverse alts (m2-F9 fix) | core_candidates + autocontract_synth | results_autocontract_scale | 12 core ops | core alts were output-identical to correct_fn (FULL vacuous); added reversed-order valid alts (oracle passes them = order-robust); gpt-5.4 core CORE=FULL=11/12=**92%** → FP-robustness real, not an artifact of vacuous alts |
| 20 | method/experiment audit corrections (5 research agents + self) | (paper) | main.tex | ~25 findings | fixed: circularity framing (table-level not task-level; recompute reference = gold template; pure-invariant within-group-share = non-circular core), mislabels (tab:baselines on synthetic grid not "real Nature"; tab:crossmodel = 20-case EXPANSION grid not "operator grid"), FP failure-analysis logic error (FN mechanism under FP heading), de-leak "no invariant" overclaim, CEGIS "never regresses" scoped to goldless score; repositioned measurement-first |
| 21 | detection recall split by CONTRACT TYPE | (re-partition of tab:perop) | results_real841 | 1471 real | **pure-invariant** (within-group-share, no reference value) 538/539=**99.8%** (non-circular core); **recompute** (weighted/pooled/median/nan-as-zero, reference = gold template) 900/932=**96.6%** → "goldless" signal carried by genuine invariants; recompute conceded as parameterized on-the-fly reference under known operator |

> Repair (claim 9) numbers are the real online run; the 24-case `results_repair_targeted` file
> was an offline stub and is superseded. Claim 10 is the honest external-transfer boundary that
> rebuts oracle-benchmark circularity: contracts abstain (no blind edits) where params are absent.

\* attribution recall uses the true-op contract's raw verdict (a missing expected
output column on the RIGHT operator is a real silent error). cross-fire counts only
substantive fires of OTHER-op contracts — a 'missing column' fire means that
operator doesn't apply (shape mismatch → abstain), not a mis-attribution. The
params schema gate + this shape gate together cut cross-fire from 20% to 8%, all at
the measurement layer, so the baseline 100% recall is untouched.

## Necessity of goldless (no-gold ablation)

The ground-truth labels (correct/silent) are computed WITH the hand gold, but the
oracle NEVER sees it — it fires from operator invariants alone. So:
- "with gold" (exact-match to a reference) is the upper-bound detector by construction.
- our goldless oracle reaches recall 56/56 = 100% / FP 0/135 = 0% on the calibration
  run and 18/18 / 0/18 on real data — i.e. it MATCHES gold-based detection without
  any gold output. Removing the gold requirement costs nothing in detection here.
- This is the necessity argument: the method does not degrade to text2SQL (which
  needs a gold query); it operates where no gold/reference exists.
