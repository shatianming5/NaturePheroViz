"""
dpo_common.py — shared, OFFLINE building blocks for the Repair-DPO pipeline.

The whole Repair-DPO experiment reuses the existing goldless detection/repair
harness so that train == eval == the published §8.4 repair distribution:

  prompt   = the EXACT repair prompt the online harness sends
             (transform_repair._online_step -> ambiguity_calibration._llm_code):
             schema preamble + task (ambiguous) + targeted typed-contract feedback.
  signal   = the GOLDLESS operator contract (transform_oracle) — "does the true-op
             contract still substantively fire on the executed result?". This is the
             ONLY reward used to pick chosen/rejected. Never gold.
  scorer   = the hidden gold (ambiguity_calibration._gold_correct) — used ONLY at eval
             time, never shown to the model. Non-circular, mirrors the detection line.

Nothing here calls the frontier proxy: candidate code is produced by a LOCAL HF model
(HFGen), executed by ambiguity_calibration._exec, and labelled by the oracle. Fully
offline -> runs on gpudev2 with no internet.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo/agent

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import eval.transform_repair as R  # noqa: E402
from eval.transform_bench import _cases, expansion_cases  # noqa: E402
from eval.ambiguity_calibration import _exec, _gold_correct  # noqa: E402


# --------------------------------------------------------------------------- #
# prompt construction — byte-for-byte the wrapping ambiguity_calibration._llm_code
# builds, so the DPO prompt distribution matches the deployed repair harness.
# --------------------------------------------------------------------------- #
def _llm_wrap(item: Dict[str, Any], prompt_text: str) -> str:
    cols = list(item["df"].columns)
    extra = (f"\nA second dataframe `df2` columns={list(item['df2'].columns)}."
             if "df2" in item else "")
    slash = "/`df2`" if "df2" in item else ""
    return (f"pandas `df` columns={cols}.{extra}\n"
            f"{prompt_text}\n"
            f"The dataframe(s) `df`{slash} ALREADY EXIST in scope with the real data.\n"
            "Do NOT re-create or re-assign them, do NOT import anything, do NOT print.\n"
            f"Use only the given `df`{slash}, assign the final answer to `result`.\n"
            'Return ONLY strict JSON: {"code": "<pandas code defining result>"}.')


def repair_prompt(item: Dict[str, Any], feedback: str) -> str:
    """The user-message content for a repair turn (task + feedback, wrapped)."""
    return _llm_wrap(item, f"{item['ambiguous']}\n\n{feedback}")


def initial_prompt(item: Dict[str, Any]) -> str:
    """The user-message content for the FIRST (buggy-start) generation."""
    return _llm_wrap(item, item["ambiguous"])


# --------------------------------------------------------------------------- #
# code extraction — models emit {"code": "..."} but may fence / add prose.
# --------------------------------------------------------------------------- #
def extract_code(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.strip()
    # 1) strict/loose JSON object with a "code" field
    for m in re.finditer(r"\{.*?\}", t, re.S):
        try:
            obj = json.loads(m.group(0))
        except Exception:
            continue
        if isinstance(obj, dict) and "code" in obj:
            return str(obj["code"])
    # 2) a "code": "..." (possibly with escaped newlines) without valid whole-JSON
    m = re.search(r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"', t, re.S)
    if m:
        try:
            return json.loads('"' + m.group(1) + '"')
        except Exception:
            return m.group(1).encode().decode("unicode_escape")
    # 3) a fenced code block
    m = re.search(r"```(?:python|py)?\s*(.+?)```", t, re.S)
    if m:
        return m.group(1)
    # 4) last resort: if it looks like it assigns result, take raw
    if "result" in t and "=" in t:
        return t
    return None


# --------------------------------------------------------------------------- #
# goldless labelling of an executed result
# --------------------------------------------------------------------------- #
def _exec_safe(item: Dict[str, Any], code: Optional[str]) -> Optional[pd.DataFrame]:
    """Execute model code, returning None on any failure (incl. code is None)."""
    if not code:
        return None
    try:
        return _exec(item, code)
    except Exception:
        return None


def label(item: Dict[str, Any], result: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Goldless PASS/FIRE + (for logging only) hidden-gold correctness."""
    if result is None:
        return {"ok": False, "contract_pass": False, "gold_correct": False,
                "other_fires": 0}
    fires = R._true_op_fires(item, result)
    others = len(R._other_fire_set(item, result))
    try:
        gc = bool(_gold_correct(item, result))
    except Exception:
        gc = False
    return {"ok": True, "contract_pass": (not fires), "gold_correct": gc,
            "other_fires": others}


def clean_pass(item: Dict[str, Any], result: Optional[pd.DataFrame],
               buggy: Optional[pd.DataFrame]) -> bool:
    """A CHOSEN-eligible repair: the true-op goldless contract no longer substantively
    fires. This is the honest reward signal (execution-trace fidelity). We deliberately
    do NOT also require zero other-contract cross-fires: correct results routinely
    cross-fire shared-`value`-column contracts (a measurement-layer artefact), and
    filtering on it would starve the chosen pool. Over-repair is measured separately
    at eval time as a set-difference vs the buggy start."""
    lab = label(item, result)
    return bool(lab["ok"] and lab["contract_pass"])


# --------------------------------------------------------------------------- #
# train / heldout split — stratified by op, deterministic. Every op appears in
# both splits (in-distribution repair-improvement test).
# --------------------------------------------------------------------------- #
def all_cases() -> List[Dict[str, Any]]:
    cs = _cases() + expansion_cases()
    for i, c in enumerate(cs):
        c["_uid"] = f"{c['op']}#{i}"
    return cs


def split_cases(cases: List[Dict[str, Any]], heldout_frac: float = 0.30
                ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    from collections import defaultdict
    by_op: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for c in cases:
        by_op[c["op"]].append(c)
    train, held = [], []
    for op in sorted(by_op):
        grp = by_op[op]  # stable order = bench definition order
        n_h = max(1, round(len(grp) * heldout_frac)) if len(grp) > 1 else 0
        held.extend(grp[len(grp) - n_h:])
        train.extend(grp[: len(grp) - n_h])
    return train, held


# --------------------------------------------------------------------------- #
# local HF text generation (lazy import so this module is importable without torch)
# --------------------------------------------------------------------------- #
class HFGen:
    def __init__(self, model_path: str, dtype: str = "bfloat16",
                 device_map: str = "auto", max_new_tokens: int = 640,
                 adapter: Optional[str] = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.max_new_tokens = max_new_tokens
        self.tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        if self.tok.pad_token_id is None:
            self.tok.pad_token = self.tok.eos_token
        self.tok.padding_side = "left"
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=getattr(torch, dtype),
            device_map=device_map, trust_remote_code=True)
        if adapter:
            # gpudev2 (NGC) ships torchao 0.15.0; peft's is_torchao_available() RAISES on
            # torchao<0.16.0 during LoRA dispatch. Plain bf16 adapter -> force "unavailable".
            import peft.import_utils as _piu
            import peft.tuners.lora.torchao as _plt
            _piu.is_torchao_available = lambda: False
            _plt.is_torchao_available = lambda: False
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, adapter)
        self.model.eval()

    def _apply(self, user_content: str) -> str:
        msgs = [{"role": "user", "content": user_content}]
        return self.tok.apply_chat_template(msgs, tokenize=False,
                                            add_generation_prompt=True)

    def generate(self, user_content: str, n: int = 1, temperature: float = 0.0,
                 top_p: float = 0.95, seed: Optional[int] = None) -> List[str]:
        if seed is not None:
            self.torch.manual_seed(seed)
        text = self._apply(user_content)
        enc = self.tok(text, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        do_sample = temperature and temperature > 0
        gen_kwargs = dict(max_new_tokens=self.max_new_tokens,
                          pad_token_id=self.tok.pad_token_id,
                          num_return_sequences=n)
        if do_sample:
            gen_kwargs.update(do_sample=True, temperature=temperature, top_p=top_p)
        else:
            gen_kwargs.update(do_sample=False)
        with self.torch.no_grad():
            out = self.model.generate(**enc, **gen_kwargs)
        gen = out[:, enc["input_ids"].shape[1]:]
        return [self.tok.decode(g, skip_special_tokens=True) for g in gen]


# --------------------------------------------------------------------------- #
# produce a shared buggy start (exec-ok, gold-WRONG, true-op contract FIRES)
# --------------------------------------------------------------------------- #
def make_buggy(item: Dict[str, Any], gen: "HFGen", tries: int = 6,
               seed_base: int = 100) -> Optional[Tuple[pd.DataFrame, str]]:
    """Model-generated silent error to repair. Returns (buggy_result, buggy_code) or
    None if we could not elicit a firing silent error. Prefers a real model bug (so the
    targeted feedback has genuine content AND we get a usable rejected completion); falls
    back to the numeric gold perturbation only if it happens to fire the contract."""
    temps = [0.0, 0.7, 0.9, 1.1, 0.7, 1.0]
    for t in range(tries):
        temp = temps[t % len(temps)]
        outs = gen.generate(initial_prompt(item), n=1, temperature=temp, seed=seed_base + t)
        code = extract_code(outs[0])
        if not code:
            continue
        res = _exec_safe(item, code)
        if res is None:
            continue
        if _gold_correct(item, res):
            continue  # correct -> not a silent error
        if R._true_op_fires(item, res):
            return res, code
    # fallback: numeric perturbation of gold (only usable if it actually fires)
    pert = R._make_buggy_start(item, None, offline=True)
    if pert is not None and R._true_op_fires(item, pert):
        return pert, "<perturbation>"
    return None
