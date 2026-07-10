#!/usr/bin/env bash
# setup_gpudev2.sh — create an isolated venv (inheriting the NGC system torch/flash_attn/
# datasets/etc) and install the shipped offline wheels. Fully offline.
set -euo pipefail
ROOT="/root/repair_dpo"
cd "$ROOT"

echo "[1/3] create venv --system-site-packages (inherits torch 2.10 / flash_attn / tokenizers)"
python3 -m venv --system-site-packages venv

echo "[2/3] install shipped wheels offline (--no-index --no-deps; deps already present at runtime)"
# order: leaf upgrades first, then the 4 libs. --no-deps because torch is invisible to pip
# (NGC installs it outside pip metadata) yet present at runtime.
./venv/bin/pip install --no-index --no-deps \
  wheels/huggingface_hub-*.whl \
  wheels/datasets-*.whl \
  wheels/annotated_doc-*.whl wheels/colorama-*.whl wheels/typer-*.whl \
  wheels/accelerate-*.whl wheels/transformers-*.whl wheels/peft-*.whl wheels/trl-*.whl

echo "[3/3] smoke import"
./venv/bin/python - <<'PY'
import torch, transformers, peft, trl, accelerate, datasets, huggingface_hub, tokenizers
print("torch        ", torch.__version__, "cuda", torch.version.cuda, "gpus", torch.cuda.device_count())
print("transformers ", transformers.__version__)
print("peft         ", peft.__version__)
print("trl          ", trl.__version__)
print("accelerate   ", accelerate.__version__)
print("datasets     ", datasets.__version__)
print("hf_hub       ", huggingface_hub.__version__)
print("tokenizers   ", tokenizers.__version__)
from trl import DPOTrainer, DPOConfig  # noqa
from peft import LoraConfig            # noqa
print("OK: DPOTrainer + LoraConfig importable")
PY
echo "SETUP DONE"
