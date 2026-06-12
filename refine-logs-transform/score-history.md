# Transform-Thesis Score Evolution

| Round | PF | MethodSpec | ContribQ | Frontier | Feas | ValFocus | VenueReady | Overall | Verdict |
|-------|----|----|----|----|----|----|----|----|----|
| 1     | 9  | 6  | 7  | 7  | 7  | 6  | 5  | 6.9 | REVISE |

R1 (GPT-5.4, 24 related works checked): novel enough for a serious paper, NOT yet Oral.
Novelty = intersection (goldless + no-tests + dataframe transforms + silent semantic + typed attribution).
Closest threats: SemGuard(ASE25 semantic-no-tests), DS-1000/ARCADE(have gold), mlinspect(operator-level but distribution not intent).
P0 fixes: (1) commit to invariants-first + operator-semantic-library oracle; DEMOTE multi-impl consistency (dead end — common-mode error: both LLMs made SAME silent error on 3 cases). (2) ambiguity-calibration pairs experiment (ambiguous vs clarified) — else "measuring prompt underspecification not model failure". (3) center on ONE idea: operator-semantic contracts over execution traces. (4) expand benchmark 16->50-100 real+preregistered.
The Oral-defining claim: "first to verify semantic fidelity of NL->dataframe transforms via typed operator-level relational semantics, WITHOUT gold outputs / pre-written tests / executing generated code."
