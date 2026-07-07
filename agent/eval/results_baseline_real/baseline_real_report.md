# Baseline detectors on REAL Nature tasks (closes e1-F4) — RECOVERED from interrupted run

Real Nature Source-Data tables; silent (wrong): 182 | correct: 207 | models=['gpt-4o','claude-sonnet-4.6'] | K=5 | NOTE: process was interrupted at 389 scored rows before the final writer; these tallies are recovered from the run log.

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| ours | 180/182 (99%) | 0/207 (0%) |
| exec_pass | 0/182 (0%) | 0/207 (0%) |
| validity | 0/182 (0%) | 0/207 (0%) |
| self_check | 105/182 (58%) | 123/207 (59%) |
| consistency | 0/182 (0%) | 1/207 (0%) |

## Reading
- exec_pass / validity / consistency recall on REAL data confirms the synthetic-grid 0% —
  now genuinely on Nature tables (not the grid).
- self_check = the real-data self-critique baseline.
- ours = the goldless operator contracts (high recall / near-0 FP).