#!/usr/bin/env bash
# run_pipeline.sh — Repair-DPO end-to-end on gpudev2 (offline).
#   MODE=smoke  -> tiny end-to-end sanity run (few cases, 1 epoch)
#   MODE=full   -> full run
set -euo pipefail
ROOT="/root/repair_dpo"; CODE="$ROOT/code/agent"
MODEL="$ROOT/model/Qwen2.5-Coder-3B-Instruct"
export PYTHONPATH="$ROOT/pylibs:$CODE"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
PY="python3"; MODE="${MODE:-full}"; cd "$CODE"
if [ "$MODE" = "smoke" ]; then
  echo "===== SMOKE ====="
  CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/build_pairs.py --model "$MODEL" --out "$ROOT/pairs_smoke" --k 4 --pairs-per-case 3 --max-cases 6
  CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/train_dpo.py --model "$MODEL" --pairs "$ROOT/pairs_smoke/pairs.jsonl" --out "$ROOT/dpo_smoke" --epochs 1 --batch 1 --accum 4
  CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/eval_dpo.py --model "$MODEL" --adapter "$ROOT/dpo_smoke" --split "$ROOT/pairs_smoke/split.json" --out "$ROOT/eval_smoke" --max-cases 4
  echo "SMOKE DONE"; exit 0
fi
echo "===== FULL: build pairs ====="
CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/build_pairs.py --model "$MODEL" --out "$ROOT/pairs" --k 8 --pairs-per-case 6 --temp 0.9
echo "===== FULL: train DPO (LoRA bf16) ====="
CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/train_dpo.py --model "$MODEL" --pairs "$ROOT/pairs/pairs.jsonl" --out "$ROOT/dpo_out" --epochs 3 --lr 5e-6 --beta 0.1 --batch 2 --accum 8
echo "===== FULL: eval held-out (base vs tuned vs generic) ====="
CUDA_VISIBLE_DEVICES=0 $PY eval/dpo/eval_dpo.py --model "$MODEL" --adapter "$ROOT/dpo_out" --split "$ROOT/pairs/split.json" --out "$ROOT/eval_out"
echo "===== RESULTS ====="; cat "$ROOT/eval_out/eval_summary.json"
