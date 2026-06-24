"""
qwen_local_eval.py — open-model validation on gpudev2 (round-5 optional, FrontierLeverage).

Runs the SAME transform-fidelity protocol with a locally-hosted open model
(Qwen2.5-Coder) instead of the proxy's closed models, to show the silent-error
phenomenon + goldless-oracle detection are not specific to GPT-4o / Claude.

This script is SELF-CONTAINED for gpudev2 (which is offline and can't reach the
4142 proxy): it loads Qwen from a local path via transformers, generates pandas
code for each case, and judges with the existing oracle. It reuses the case grids
and the exec/gold/sanitize helpers from the existing eval modules (pure-python,
no network).

Usage (on gpudev2, model already on the shared disk):
  cd agent && python eval/qwen_local_eval.py \
      --model /mnt/cephfs_home_tianming.sha/qwen_models/Qwen2.5-Coder-7B-Instruct \
      --bench --out eval/results_qwen_7B
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.ambiguity_calibration import _exec, _gold_correct, _sanitize_code  # noqa: E402
from eval.transform_bench import _cases as _bench_cases  # noqa: E402


# ---- local Qwen generation (transformers, no network) ----------------------

class _Qwen:
    def __init__(self, model_path: str, max_new_tokens: int = 1024):
        import torch  # noqa
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype="auto", device_map="auto", trust_remote_code=True)
        self.max_new_tokens = max_new_tokens

    def code(self, item: Dict[str, Any], prompt_text: str) -> Optional[str]:
        cols = list(item["df"].columns)
        extra = f"\nA second dataframe `df2` columns={list(item['df2'].columns)}." if "df2" in item else ""
        prompt = (
            f"pandas `df` columns={cols}.{extra}\n{prompt_text}\n"
            f"The dataframe(s) `df`{'/`df2`' if 'df2' in item else ''} ALREADY EXIST in scope with the real data.\n"
            "Do NOT re-create or re-assign them, do NOT import anything, do NOT print.\n"
            f"Use only the given `df`{'/`df2`' if 'df2' in item else ''}, assign the final answer to `result`.\n"
            'Return ONLY strict JSON: {"code": "<pandas code defining result>"}.'
        )
        text = self.tok.apply_chat_template(
            [{"role": "user", "content": prompt}], tokenize=False, add_generation_prompt=True)
        inputs = self.tok(text, return_tensors="pt").to(self.model.device)
        out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens,
                                   do_sample=False, temperature=None, top_p=None,
                                   pad_token_id=self.tok.eos_token_id)
        gen = self.tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        m = re.search(r"\{.*\}", gen, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0)).get("code")
        except Exception:
            # fallback: a ```python block
            b = re.search(r"```(?:python)?\n(.*?)```", gen, re.S)
            return b.group(1) if b else None


def _exec_qwen(item, code):
    """exec with the same sanitize as the proxy path."""
    if not code:
        return None
    return _exec(item, _sanitize_code(code))


def _grid(bench: bool) -> List[Dict[str, Any]]:
    seen: Counter = Counter()
    out = []
    for c in _bench_cases():
        seen[c["op"]] += 1
        out.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="local path to the Qwen model dir")
    ap.add_argument("--bench", action="store_true", help="use the 48-case grid")
    ap.add_argument("--out", default="eval/results_qwen")
    ap.add_argument("--label", default=None, help="model label for the report")
    a = ap.parse_args(argv)

    label = a.label or Path(a.model).name
    qwen = _Qwen(a.model)
    cases = _grid(a.bench)
    print(f"[qwen] {label}: {len(cases)} cases x (ambiguous, clarified)", flush=True)

    silent = {c: 0 for c in ("ambiguous", "clarified")}
    total = {c: 0 for c in ("ambiguous", "clarified")}
    fire_wrong = wrong = fire_right = right = 0
    rows = []
    for item in cases:
        rec = {"name": item["name"], "op": item["op"]}
        for cond in ("ambiguous", "clarified"):
            code = qwen.code(item, item[cond])
            result = _exec_qwen(item, code)
            exec_ok = result is not None
            correct = exec_ok and _gold_correct(item, result)
            oc = oracle_check(item["op"], {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})},
                              item["params"], result)
            fired = bool(oc and oc.fired)
            total[cond] += 1
            if exec_ok and not correct:
                silent[cond] += 1
            if exec_ok:
                if correct:
                    right += 1; fire_right += int(fired)
                else:
                    wrong += 1; fire_wrong += int(fired)
            tag = "ok" if correct else ("SILENT" if exec_ok else "crash")
            print(f"[{item['name']:20}] {cond:10} {label:24} {tag:7} oracle_fired={fired}", flush=True)
            rec.setdefault(cond, {})[label] = {"tag": tag, "oracle_fired": fired}
        rows.append(rec)

    def pct(c): return f"{100*silent[c]/total[c]:.0f}%" if total[c] else "n/a"
    report = [
        f"# Open-model validation: {label} on the transform-fidelity grid\n",
        "Same 48-case grid, (ambiguous, clarified) prompts, goldless oracle — but the",
        "generator is a LOCAL open model (Qwen2.5-Coder) instead of a proxy closed model.\n",
        "## (1) Silent-error rate (open model)",
        f"- ambiguous: {silent['ambiguous']}/{total['ambiguous']} ({pct('ambiguous')})",
        f"- clarified: {silent['clarified']}/{total['clarified']} ({pct('clarified')})\n",
        "## (2) Oracle recall on open-model silent errors",
        f"- fired on {fire_wrong}/{wrong} truly-wrong ({100*fire_wrong/wrong:.0f}%)" if wrong else "- (no wrong)",
        "\n## (3) Oracle false-positive on open-model correct results",
        f"- fired on {fire_right}/{right} truly-correct ({100*fire_right/right:.0f}%)" if right else "- (no correct)",
        "\n## Reading",
        "- If the open model also shows a high ambiguous silent-error rate AND the goldless",
        "  oracle keeps high recall / low FP, the phenomenon + method generalize beyond the",
        "  two closed models, not a GPT-4o/Claude artifact.",
    ]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "qwen_report.md").write_text("\n".join(report), encoding="utf-8")
    (out / "qwen_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(report))
    print(f"\n[saved] {out}/qwen_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
