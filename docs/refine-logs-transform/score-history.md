# Transform-Thesis Score Evolution

| Round | PF | MethodSpec | ContribQ | Frontier | Feas | ValFocus | VenueReady | Overall | Verdict |
|-------|----|----|----|----|----|----|----|----|----|
| 1     | 9  | 6  | 7  | 7  | 7  | 6  | 5  | 6.9 | REVISE |
| 2     | 9  | 7  | 7  | 8  | 8  | 6  | 6  | 7.5 | REVISE |
| 3     | 9.0 | 7.8 | 8.1 | 8.0 | 8.3 | 7.8 | 7.5 | 8.1 | REVISE (clears Oral >=8) |
| 4     | 9.0 | 8.7 | 8.8 | 8.5 | 8.8 | 8.4 | 8.2 | 8.7 | REVISE (clears Oral, not READY) |
| 5     | 9.0 | 9.1 | 9.0 | 8.9 | 8.9 | 9.2 | 9.1 | 9.0 | READY (>=9) |

R1 (GPT-5.4, 24 related works checked): novel enough for a serious paper, NOT yet Oral.
Novelty = intersection (goldless + no-tests + dataframe transforms + silent semantic + typed attribution).
Closest threats: SemGuard(ASE25 semantic-no-tests), DS-1000/ARCADE(have gold), mlinspect(operator-level but distribution not intent).
P0 fixes: (1) commit to invariants-first + operator-semantic-library oracle; DEMOTE multi-impl consistency (dead end — common-mode error: both LLMs made SAME silent error on 3 cases). (2) ambiguity-calibration pairs experiment (ambiguous vs clarified) — else "measuring prompt underspecification not model failure". (3) center on ONE idea: operator-semantic contracts over execution traces. (4) expand benchmark 16->50-100 real+preregistered.
The Oral-defining claim: "first to verify semantic fidelity of NL->dataframe transforms via typed operator-level relational semantics, WITHOUT gold outputs / pre-written tests / executing generated code."

R2 (GPT-5.4, 4 novelty edges re-verified online): 6.9 -> 7.5, still REVISE (not Oral >=8).
All 4 novelty edges SURVIVE independent literature check: CodeT (selection not detection; common-mode rebuttal technically valid), SemGuard ASE25 (line-level algorithmic, no relational/DataFrame semantics), Zhong-2020 (needs gold SQL to build+score, not goldless), mlinspect (lineage/distribution not intent-faithfulness).
P0-3 (one crisp idea) = CLOSED (yes). P0-1/P0-2/P0-4 = partial.
P0 still blocking Oral: (1) CRITICAL: same-grid head-to-head baseline table (exec-pass / value-range / self-check / CodeT-consistency) — currently only have our 100%/0%, no comparison. (2) CRITICAL: oracle accounting bug — 192-56=136 negatives but report says 0/135 FP; publish full 192 confusion matrix. (3) benchmark still 48<50-100, 4 instances/class, no held-out real-task slice. (4) ambiguity calibration needs multiple independent clarifications/case (not 1 author-written) for causal isolation; explain weighted_mean 0%->37% reversal. (5) contract scalability/coverage/abstain under-argued.
New adjacent threat to cite: "Incoherence as Oracle-less Measure of Error in LLM Code Gen" (AAAI 2026, arXiv 2025) — closer than CodeT mechanistically; differentiate on domain(DataFrame) + failure-mode(common-mode) + mechanism(contracts vs behavioral divergence).
Scope "first" claim narrowly: NOT "first oracle-free", but "first typed operator-contract method for NL->DataFrame semantic error detection without gold/test/reference".

R3 (GPT-5.4, all 5 round-2 P0 closed with real data): 7.5 -> 8.1, CLEARS ORAL (>=8).
"now clears Oral", "oral-clearing thesis in substance". Decisive: the same-grid head-to-head
(ours 100%/0% vs exec-pass/validity/consistency 0% recall, self-check 61%/40%) = "exactly the
missing experiment I asked for". Real-data slice CLOSES external validity (yes). 3-wording
clarification CLOSES causal isolation (yes). Baseline P0 marked "partial" ONLY due to an
accounting inconsistency (detector table 57 silent/132 correct = independent baseline run of
189 exec-ok, vs calibration run's 192 = 135+56+1) — now annotated in §3.3 as two independent
generations; final paper will use one run for a single master table.
Remaining to fully clean (not core-idea, write-time): (1) prospective scalability demo on 2-3
unseen operator families (authoring effort + abstain rate before/after); (2) expand real slice
beyond 18 cases with CIs; (3) necessity ablation + coverage/abstain table + typed-attribution
accuracy in one master table.

R5 (GPT-5.4): 8.7 -> 9.0, READY (>=9). "now reads like a submission package, not a strong
prototype with loose ends." All round-4 package gaps closed: (1) 5-family coverage table
converts extensibility from assertion to measured evidence with honest boundaries (MethodSpec
9.1); (2) canonical reconciliation + master table + Wilson CIs fix all bookkeeping (ValFocus
9.2, VenueReadiness 9.1); (3) dual-gate attribution keeps recall 100% while cutting cross-fire
20%->8% (Feasibility 8.9, "partial" only because 8% residual is real not erased).
Remaining (optional, write-time, NOT blockers): add an open model (Qwen-Coder) for FrontierLeverage
8.9->9; family-level candidate pruning to push cross-fire below 8% for Feasibility.
Trajectory: 6.9 -> 7.5 -> 8.1 -> 8.7 -> 9.0 across 5 rounds.

R6 (aris-reviewer / dentist-loop, 2026-06-29): fresh adversarial 7.5 ALMOST (self 9.0 = co-design optimism). Blocking W1: canonical repair report was offline stub -> replaced w/ real online (80/18, N=87, 3 models, ==ceiling). W2 transfer evidence existed but unsurfaced -> added master rows 9-10 (ds1000 8% covered, abstain-safe). Decisive open: scale oracle transfer beyond 6 DS-1000 covered cases.

R7 (dentist-loop, 2026-06-29): all R6 open items closed offline. W3 end2end NL→params→oracle (op/param 100%, recall 84%==upper bound, FP0, +tests); W2 transfer 8→17% on DS-1000; W5 PBT positioning. master rows 11-12. 34 tests green.

R8 (dentist-loop, 2026-06-29, REAL LLM via opencode free): residuals closed. W3 generalization regex 28% vs LLM-clf 83% (held-out paraphrases); W2 real oracle firing on DS-1000 recall 50%/FP 0% (per-task, not coverage). master rows 13-14, proposal §3 honest. No API key used (opencode free models).
