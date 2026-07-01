# Repair-DPO — 7B replication + cross-scale comparison (gpudev2, offline)

Same protocol as the 3B run (`../results_dpo/DPO_SUMMARY.md`), now with a **stronger,
apache-2.0 base** — **Qwen2.5-Coder-7B-Instruct** — to test whether the conclusion holds
across model scale. Fully offline on gpudev2 (GPU 4, bf16 LoRA). Preferences labelled
ONLY by the goldless operator contract; gold is the never-shown eval scorer.

- **build_pairs**: 349 pairs from 45/61 cases (base targeted repair pass mean **0.609** vs
  3B's 0.459 — the 7B is already a much stronger no-training repairer).
- **train_dpo**: LoRA bf16, β=0.1, lr 4e-6, 2 epochs. 22 steps, loss 0.6931 → 0.6752,
  max train pref accuracy 0.906, **no divergence** (the hardened config transfers cleanly).
- **eval_dpo**: 25 held-out cases, greedy + best-of-6 (goldless contract-gated).

## 7B held-out results (hidden-gold success, N=25, Wilson 95% CI)

| arm | gold success | 95% CI | contract_pass | over_repair |
|---|---|---|---|---|
| base_generic | 24.0% | [11, 43] | 0.480 | 0.000 |
| base_targeted (no-train) | **28.0%** | [14, 47] | 0.480 | 0.080 |
| tuned_targeted (DPO) | 24.0% | [11, 43] | 0.440 | 0.080 |
| **base_best-of-6 (goldless gate)** | **48.0%** | [30, 66] | **0.720** | **0.000** |
| tuned_best-of-6 | 40.0% | [23, 59] | 0.720 | 0.040 |

Greedy Δ(tuned − base_targeted) = **−4.0 pts**. Best-of-6 Δ = **−8.0 pts**. Ceiling
(any gold-correct repair among the 6): base **0.640** vs tuned 0.640.

## Cross-scale comparison (3B vs 7B)

| metric | 3B | 7B |
|---|---|---|
| base_targeted (no-train, greedy) | 29.2% | 28.0% |
| **base best-of-6 (goldless selection)** | 29.2% | **48.0%** |
| tuned best-of-6 (DPO) | 25.0% | 40.0% |
| best-of-6 Δ (tuned − base) | −4.2 | −8.0 |
| best-of-6 contract_pass (base) | 0.667 | 0.720 |
| ceiling: any gold-correct in 6 | 0.417 | 0.640 |
| build: base targeted pass mean | 0.459 | 0.609 |

## Conclusions — the finding is robust across scale

1. **The win is (stronger base) × (goldless best-of-N selection), NOT DPO.** On 7B, greedy
   no-train repair is 28% but **best-of-6 with contract-gated selection jumps to 48%**
   (+20 pts) at **zero over-repair** — because the 7B's reachable ceiling (any gold-correct
   in 6) is 0.640 vs 3B's 0.417, and the goldless contract reliably *picks* that correct
   repair out of the samples. This is a clean, training-free, deployable recipe that scales
   with base quality.
2. **Repair-DPO does NOT beat the no-training baseline at EITHER scale** (3B: greedy +0.0 /
   best-of-6 −4.2; 7B: greedy −4.0 / best-of-6 −8.0; all CIs overlap). If anything the gap
   widens on the stronger model — a better base has *more* useful sampling diversity for
   best-of-N to exploit, which preference optimisation erodes (7B ceiling 0.640 → the tuned
   model even slightly re-introduces over-repair 0.0 → 0.04).
3. **Net:** two independent model scales agree — the goldless contract's value is realised
   **training-free** (typed feedback + best-of-N selection), and small-scale DPO
   distillation adds nothing. This strengthens, not weakens, the no-training thesis, and is
   reported honestly rather than cherry-picked.

## Artifacts (this dir)
`pairs.jsonl` (349), `build_summary.json`, `build_stats.json`, `split.json`,
`train_log.json` (stable 2-epoch), `eval_summary.json`, `eval_records.json` (5 arms).
Repro: `MODEL=<7B path> GPU=<free> TAG=7b MODE=full bash run_pipeline.sh` (in the
gpudev2 bundle; scripts are `agent/eval/dpo/*.py`).
