# Transform-Thesis Score Evolution

| Round | PF | MethodSpec | ContribQ | Frontier | Feas | ValFocus | VenueReady | Overall | Verdict |
|-------|----|----|----|----|----|----|----|----|----|
| 1     | 9  | 6  | 7  | 7  | 7  | 6  | 5  | 6.9 | REVISE |
| 2     | 9  | 7  | 7  | 8  | 8  | 6  | 6  | 7.5 | REVISE |
| 3     | 9.0 | 7.8 | 8.1 | 8.0 | 8.3 | 7.8 | 7.5 | 8.1 | REVISE (clears Oral >=8) |

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
