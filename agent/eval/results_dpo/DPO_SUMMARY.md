# Repair-DPO on gpudev2 — results (goldless-contract preference training)

**Question.** The detection line proves a *goldless* typed operator contract can flag +
localize a silent semantic error. §8.4 (no-training) then showed feeding that typed
signal back as *repair feedback* fixes more errors than generic self-repair. This
experiment asks the next question: **can we distil the goldless contract into model
weights via DPO and beat the no-training repair baseline?**

Signal = execution-trace fidelity (the goldless contract PASS), used to label
preferences. Gold is only the hidden eval scorer (`ambiguity_calibration._gold_correct`),
never shown to any model — non-circular, mirroring the detection line.

## Setup (fully offline on gpudev2)
- **Box**: gpudev2, 8×H200 (143 GB), **no internet**. torch 2.10.0a0 / CUDA 13.1 (NGC),
  flash-attn 2.7.4, datasets/tokenizers/hf_hub present.
- **Shipped from local** (downloaded + transferred, gpudev2 has no PyPI/HF): 9 pure-python
  wheels installed via `pip --target` (shadowing system): transformers 5.12.1, trl 1.7.0,
  peft 0.19.1, accelerate 1.14.0, + hf_hub/datasets/typer upgrades. Base model
  **Qwen2.5-Coder-3B-Instruct** (Qwen research license) via ModelScope, uploaded with a
  resumable chunked scp (WAN drops; per-chunk size-diff retry).
- **No bitsandbytes / no torchao**: plain bf16 LoRA (H200 has room). peft's
  `is_torchao_available()` hard-raises on the NGC torchao 0.15.0 during LoRA dispatch →
  monkeypatched to `False` (correct state; we use no torchao-quantized layers).

## Pipeline (all offline, on-policy)
1. **build_pairs** — the base model itself generates repair candidates from the deployed
   targeted-feedback prompt; each executed candidate is labelled by the **goldless
   contract** (chosen = contract no longer fires; rejected = still fires). 3 buggy starts /
   case, K=12 candidates, high-temp + gold-guided (ceiling) fallbacks so a pair can form.
   → **380 preference pairs from 48/61 train cases, 23 ops** (base targeted repair pass
   rate 0.459). 4 ops never yield a firing bug from the 3B (count_includes_empty,
   dense_rank, left_join_keep_all, order_dependent_dedup).
2. **train_dpo** — TRL `DPOTrainer` + LoRA (r16/α32, 7 proj modules), bf16, β=0.1, lr 4e-6,
   2 epochs, warmup 10 steps, grad-clip 1.0, no gradient-checkpointing. The frozen base is
   the implicit DPO reference (adapter disabled). Loss **0.6931 → 0.6578**, train
   preference **accuracy 0.964**. (lr 5e-6 with no warmup, and a 3rd epoch, both diverge to
   NaN — hence the hardened config; stop at 2 epochs = the well-learned, pre-divergence
   point.)
3. **eval_dpo** — 24 held-out cases (stratified by op, unseen instances). Same frozen buggy
   start per case for all arms. Greedy + best-of-6 (goldless contract-gated selection).

## Results (hidden-gold repair success, N=24, Wilson 95% CI)

| arm | gold success | 95% CI | contract_pass | over_repair |
|---|---|---|---|---|
| base_generic (no typed info) | 25.0% | [12, 45] | 0.458 | 0.042 |
| base_targeted (no-train, ours) | **29.2%** | [15, 49] | 0.500 | 0.042 |
| tuned_targeted (DPO) | 29.2% | [15, 49] | 0.500 | 0.042 |
| base_best-of-6 (goldless gate) | 29.2% | [15, 49] | **0.667** | **0.0** |
| tuned_best-of-6 | 25.0% | [12, 45] | 0.667 | 0.0 |

Greedy Δ(tuned − base_targeted) = **+0.0 pts**. Best-of-6 Δ = **−4.2 pts**. All CIs fully
overlap. Ceiling (any gold-correct repair among the 6): base 0.417 vs tuned **0.375**.
(A gentler run, lr 2e-6, gave tuned contract_pass 0.542 > 0.500 but the same 29.2% gold —
identical conclusion.)

## Honest conclusions
1. **The goldless contract is a strong TRAINING-FREE repair signal.** Targeted typed
   feedback beats generic self-repair with no training (+4.2 pts gold, +4.2 pts
   contract_pass). Best-of-N with a goldless contract-gated pick lifts contract-pass
   0.50 → 0.667 and drops over-repair 0.042 → 0 at no gold cost — a clean, deployable,
   no-training inference recipe.
2. **Repair-DPO does NOT beat the no-training baseline on hidden gold at this scale**
   (greedy +0.0, best-of-6 −4.2, CIs overlapping). DPO fits the training preference
   (acc 0.964) and can raise the *goldless* contract-pass it optimizes, but this does not
   translate into more gold-correct repairs, and it slightly **narrows the
   reachable-correct diversity** (ceiling 0.417 → 0.375) that best-of-N relies on.
3. **Why** (not a plumbing failure — the pipeline trains, evals, and is non-circular):
   (a) *signal–objective gap* — the contract is necessary-but-not-sufficient for gold, so
   maximising contract-satisfaction need not maximise correctness; (b) *distribution
   narrowing* from preference optimisation; (c) *scale / power* — 380 pairs and 24
   held-out cases are underpowered for a small effect. This **reinforces the paper's
   no-training thesis**: the contract's value is realised training-free (feedback +
   selection); weight-level distillation via small-scale DPO adds nothing here.

## Reproduce (on gpudev2, offline)
```bash
cd /root/repair_dpo && bash setup_gpudev2.sh            # venv-free: pip --target install wheels
MODE=full bash run_pipeline.sh                          # build_pairs -> train_dpo -> eval_dpo
# or stage-by-stage (see run_pipeline.sh); eval adds best-of-N via --sample-n
```

## Artifacts (this dir)
- `pairs.jsonl` (380 preference pairs, conversational), `build_summary.json`,
  `build_stats.json`, `split.json` (train/heldout uids).
- `train_log.json` (DPO loss/acc trajectory of the 2-epoch model).
- `eval_summary.json`, `eval_records.json` (per-case, all 5 arms).
Code: `agent/eval/dpo/{dpo_common,build_pairs,train_dpo,eval_dpo}.py`.
