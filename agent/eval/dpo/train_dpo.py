"""
train_dpo.py — Repair-DPO with LoRA (bf16) on H200. Runs on gpudev2 (offline).

Base policy = the same open model used to build the pairs and to eval. The reward
that produced the preferences is the GOLDLESS operator contract (execution-trace
fidelity); DPO just fits the preference. LoRA + bf16 (no bitsandbytes) fits a 7B
model on a single H200 with room to spare; the frozen base doubles as the implicit
DPO reference (adapter disabled), so no separate ref model is loaded.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--pairs", required=True, help="pairs.jsonl")
    ap.add_argument("--out", default="dpo_out")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--lr", type=float, default=2e-6)
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--max-len", type=int, default=2048)
    ap.add_argument("--max-prompt-len", type=int, default=1536)
    ap.add_argument("--warmup-steps", type=int, default=10)
    ap.add_argument("--grad-ckpt", action="store_true", help="enable gradient checkpointing (off by default; H200 has room)")
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import DPOConfig, DPOTrainer

    # gpudev2 (NGC) ships torchao 0.15.0; peft 0.19.1's is_torchao_available() RAISES on
    # torchao<0.16.0 during LoRA dispatch. We train plain bf16 LoRA (no torchao-quantized
    # layers), so the correct state is "torchao unavailable" -> force it to avoid the
    # spurious hard error (dispatch_torchao then just returns the normal Linear LoRA module).
    import peft.import_utils as _piu
    import peft.tuners.lora.torchao as _plt
    _piu.is_torchao_available = lambda: False
    _plt.is_torchao_available = lambda: False

    rows = [json.loads(l) for l in Path(args.pairs).read_text().splitlines() if l.strip()]
    print(f"[data] {len(rows)} preference pairs", flush=True)
    ds = Dataset.from_list(rows)

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, trust_remote_code=True)
    model.config.use_cache = False

    peft_cfg = LoraConfig(
        r=args.lora_r, lora_alpha=args.lora_alpha, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"])

    cfg = DPOConfig(
        output_dir=args.out, per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.accum, learning_rate=args.lr,
        num_train_epochs=args.epochs, beta=args.beta, max_length=args.max_len,
        bf16=True, logging_steps=2, max_grad_norm=1.0,
        save_strategy="epoch", lr_scheduler_type="cosine", warmup_steps=args.warmup_steps,
        gradient_checkpointing=args.grad_ckpt, report_to=[], seed=args.seed,
        remove_unused_columns=False)

    trainer = DPOTrainer(model=model, args=cfg, train_dataset=ds,
                         processing_class=tok, peft_config=peft_cfg)
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    log = getattr(trainer.state, "log_history", [])
    Path(args.out, "train_log.json").write_text(json.dumps(log, indent=2))
    losses = [h["loss"] for h in log if "loss" in h]
    print(f"\n[done] adapter -> {args.out} | "
          f"loss {losses[0]:.4f} -> {losses[-1]:.4f}" if losses else f"[done] -> {args.out}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
