# Experiment 2b — single-agent vs dual-agent targeted repair  [OFFLINE STUB]

N=24  rounds=3  models=['stub']

| arm | success | mean rounds | mean llm-calls (cost) | over-repair(a) |
|---|---|---|---|---|
| single | 24/24 (100%) | 1.00 | 1.00 | 0/24 (0%) |
| dual | 24/24 (100%) | 1.00 | 2.00 | 0/24 (0%) |

## reading
- single success 100%, dual success 100%; dual costs 2.0x the llm-calls.
- dual does NOT materially beat single -> SUPPORTS the thesis: the headline is the typed-attribution SIGNAL, not the agent count. Dual-agent stays an ablation, not a contribution.
