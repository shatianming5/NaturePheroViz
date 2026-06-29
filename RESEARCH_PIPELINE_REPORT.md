# Research Pipeline Report — NaturePheroViz

## Run header
- Date: 2026-06-29
- Mode: dentist-research-loop (autonomous, AUTO_PROCEED=true)
- Type: resume (no prior REVIEW_STATE.json; reusing all docs/ + agent/eval artifacts)
- Active objective: advance the strongest current story to a submission-ready package.

## Active direction
Transform thesis v2 — `docs/proposals/transform_thesis_proposal_v2.md`.
Goldless **typed operator-level relational semantic contracts** detect *silent semantic
errors* in LLM NL→DataFrame transforms (no gold output, no tests, no trusted reference).
idea-refine converged 6.9→7.5→8.1→8.7→9.0 READY (5 rounds, `docs/refine-logs-transform/`).

## Evidence baseline (verified to compile/test)
- compileall pipeline+agent OK; `pytest agent/tests` = 31 passed.
- Master table reconciled: `agent/eval/results_master/master_table.md`.
- Silent rate: 48-grid 46% ambig; DS-1000 external 26% [21-31]; Nature 72-78%.
- Oracle: recall 100% / FP 0% (calib + real slice). Baselines 0% recall; self-check 61%/40%.
- Known gap: targeted-repair table is a deterministic gold STUB ("illustrative only").

## Score progression
6.9 → 7.5 → 8.1 → 8.7 → 9.0 (transform idea-refine). This loop = post-READY hardening.

## Review loop (this pass) — COMPLETED
- Reviewer: aris-reviewer @ claude-opus-4.6. Round 1: 7.5/10 ALMOST (vs self 9.0).
- Implemented min fixes: (W1) canonical repair report → real online 80/18 (N=87, 3 models, ==ceiling); (W2) added master-table rows 9–10 surfacing DS-1000 oracle-transfer (8% covered, abstain-safe). Verified oracle deterministically; 31 tests pass.
- Score progression: idea-refine 6.9→9.0; fresh review 7.5 ALMOST. Stub blocker removed.
- Remaining (write-time/decisive): scale oracle transfer beyond 6 DS-1000 covered cases; NL→params classifier; PBT positioning. These need LLM regen / prose — not code blockers.

## Pass 2 (W2/W3/W5 closed) — COMPLETED
- R2 review 7.5→8.0 ALMOST. W1 verified clean.
- W3: NL→(op,params)→oracle (new transform_intent_infer.py + end2end_infer.py + 3 tests): grid op/param 100%, e2e recall 84%==upper bound, FP 0% (disclosed: templated co-designed UB).
- W2: oracle_transfer.py DS-1000 — keyword 17% but precision 10% → true 2%; honest boundary (free-text needs ML classifier), not a lift.
- W5: proposal §4 PBT/Hypothesis rebuttal + first-claim dimension.
- master rows 11-12, score-history R7, 34 tests pass. Strength = detection C1 + repair C2 (N=87 real).
