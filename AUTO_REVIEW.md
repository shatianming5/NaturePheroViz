# AUTO_REVIEW — Transform Thesis (silent semantic error detection)

Reviewer: aris-reviewer (claude-opus-4.6). Loop: dentist-research-loop.

## Round 1 — 2026-06-29
Score 7.5/10 · Verdict ALMOST (self-scored idea-refine = 9.0; reviewer = -1.5 optimistic).

### Top weaknesses (ranked)
- W1 BLOCKING: repair_targeted_report.md is an OFFLINE STUB ("verdict illustrative only"); canonical artifact shows deterministic gold, not real LLM repair.
- W2 (decisive): oracle never run on DS-1000 external silents → circularity ("you wrote benchmark+oracle"). Need oracle transfer recall on truly external errors.
- W3: operator/params identification from NL assumed, not demonstrated.
- W4: 9.0 is co-design self-score; expect 7-8 from adversarial reviewer.
- W5: 5-way "first" intersection has no moat vs PBT/SemGuard/CodeT/Incoherence/mlinspect.

### Minimum fixes
1. Regenerate repair report from real online logs; mark ## Mode: ONLINE.
2. Run oracle on DS-1000 70 silents w/ constructed params → transfer recall + 0-FP. THE decisive exp.
3. NL→operator/params classification accuracy; end2end recall ≈ acc × 100%.
4. Drop "9.0/Oral" self-claim in paper.

### Cheapest convincing next step
Oracle on DS-1000 silents (harness exists; offline). Even 15/70 fire w/ 0 FP breaks tautology.

Bottom line: strong; ALMOST not Oral-READY. Fix stub artifact + external transfer.

### Actions taken (round 1)
- W1 FIXED: replaced canonical `results_repair_targeted/repair_targeted_report.md` stub with real ONLINE numbers (N=87, 3 models, targeted 80% [71-87] vs generic 18% [12-28], ==gold-diff ceiling). Disclosed zscore within-noise.
- W2 SURFACED: real oracle-transfer evidence already existed (ds1000_repair: 8% coverage, policy 20%≥generic 18%, abstain-safe, covered subset 3/6 vs 1/6). Added master-table rows 9+10 so the circularity rebuttal is visible. Remaining: scale beyond 6 covered cases (needs LLM regen).
- W3/W5: write-time only (NL→params classifier, PBT positioning); no code blocker.
- Verified: oracle fires on mean-when-median, passes correct; 31 tests pass.

### Status: ALMOST (7.5) — POSITIVE_STOP met. Stub-artifact blocker removed; external-transfer surfaced.

## Round 2 — 2026-06-29 (all open todos fixed)
- W3 CLOSED: end2end NL→(op,params)→oracle (new transform_intent_infer.py + end2end_infer.py): op-acc 100%, param 100%, recall 84% == params-given upper bound, FP 0% on 68 grid. Inferred params lose nothing. +3 unit tests (34 pass).
- W2 CLOSED: oracle_transfer.py over DS-1000 — NL-inferred alignable coverage 17% (48/275) vs prior 8%, abstain-safe; master rows 11-12.
- W5 CLOSED: proposal §4 adds PBT/Hypothesis rebuttal (NL-derived vs code-derived, single-trace, intent-faithfulness) + first-claim dimension.
- W1 already fixed R1 (online repair canonical). Verified offline; no LLM key.

### R2 precision audit (honest)
DS-1000 NL coverage 17% keyword but ref-code precision 10% → true 2% < hand-param 8%. W2 reframed: confirms 'contracts need operator params' boundary, not a lift. W3 grid 100% disclosed as templated/co-designed upper bound (deployability PoC). master rows 11-12 updated honest. Final: 8.0 ALMOST; strength = detection(C1)+repair(C2, N=87 real).

## Round 3 — 2026-06-29 (residuals closed with REAL LLM, opencode free)
- W3 real generalization: regex 28% on held-out off-lexicon paraphrases (honest, abstain-safe) vs LLM classifier 83% (intent_llm.py, opencode free) — NL→op deployable; grid 100% disclosed as templated UB. results_generalize/.
- W2 real firing (not coverage): w2_firing.py generates DS-1000 solutions (opencode free), DS-1000 gold labels them; goldless oracle recall 3/6=50% on real external silent, FP 0/2=0%. results_w2_firing/. master rows 13-14.
- precision audit kept (DS-1000 keyword precision 10% honest). Tests 4 in test_intent_infer (abstain-safe guard). 

### R3 residual closure — FINAL (real opencode-free runs, per-case JSON)
- W3 generalization: held-out 19 off-lexicon paraphrases — regex 26% (abstain-safe, 2 miswired) vs LLM-clf 84% (16/19). raw results_generalize/intent_llm.json.
- W2 real firing: w2_firing.py with --out-json + Wilson CI + incremental write. pilot N=12 recall 3/6=50% FP0/2; scaled N=30 recall 2/5=40% [12-77], FP 1/6=17% [3-56], crash 19/30 (free-model limit). raw results_w2_firing/firing.json. Honest: small N, API model = cheapest scale-up.
- master rows 13-14 updated with CIs. 35 tests pass. No API key used.
- Net: qualitative residuals CLOSED with real LLM evidence + audit trail; quantitative N bounded by free-model crash rate (disclosed, not hidden).
