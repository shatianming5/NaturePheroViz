# Baseline detectors on REAL Nature tasks (closes e1-F4) — clean writer-generated run

Real Nature Source-Data tables; silent (wrong): 50 | correct: 69 | models=['gpt-4o', 'claude-sonnet-4.6'] | K=5.

This is a clean, crash-safe (checkpointed) re-run. It reproduces the detector profile of the
earlier 389-row pass (ours ~99-100% recall / 0% FP; exec_pass/validity/consistency 0% recall;
self_check ~58-62% recall with high FP), now written by the run itself (no log-recovery).

| detector | recall (flags/silent) | false-positive (flags/correct) |
|---|---|---|
| ours | 50/50 (100%) | 0/69 (0%) |
| exec_pass | 0/50 (0%) | 0/69 (0%) |
| validity | 0/50 (0%) | 0/69 (0%) |
| self_check | 31/50 (62%) | 46/69 (67%) |
| consistency | 0/50 (0%) | 0/69 (0%) |

## Reading
- exec_pass / validity / consistency recall on REAL data confirms the synthetic-grid 0% —
  these numbers are now genuinely on Nature tables (not the grid).
- self_check recall/FP is the real-data self-critique baseline (fires almost indiscriminately).
- ours = the goldless operator contracts (high recall / near-0 FP).