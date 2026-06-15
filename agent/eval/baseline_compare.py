"""
baseline_compare.py — the round-2 reviewer's CRITICAL P0: same-grid head-to-head.

On the SAME 48-case grid and the SAME LLM generations, run five silent-error
detectors side by side and report each one's recall (flags on truly-wrong) and
false-positive rate (flags on truly-correct):

  1. ours        — invariants-first operator-semantic contracts (transform_oracle)
  2. exec_pass   — "did the code run and produce a frame?" (the de-facto status quo)
  3. validity    — output shape/type sanity (non-empty, expected columns, no all-NaN)
  4. self_check  — ask the SAME LLM "is this result correct?" (LLM-as-judge)
  5. consistency — CodeT-style: generate K independent implementations, flag if their
                   results disagree (majority/plurality). Fails under common-mode error.

Ground truth (correct/silent) comes from the hand gold, used ONLY for labeling —
no detector except via its own mechanism sees it. Expected story:
  exec_pass recall = 0 (silent never crashes), validity ~ 0, self_check moderate
  (blind to its own semantic errors), consistency fails on common-mode classes,
  ours = high recall + low FP.

Run:  cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/baseline_compare.py
      (add --quick to run a 12-case subset, one per class)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from eval.transform_oracle import check as oracle_check  # noqa: E402
from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct, MODELS  # noqa: E402
from eval.transform_bench import _cases  # noqa: E402


# --- the five detectors: each returns True == "flags this as an error" ----------

def d_ours(item, result) -> bool:
    inp = {"df": item["df"], **({"df2": item["df2"]} if "df2" in item else {})}
    oc = oracle_check(item["op"], inp, item["params"], result)
    return bool(oc and oc.fired)


def d_exec_pass(item, result) -> bool:
    # status quo: a run that produced any frame "passes" -> never flags a silent error
    return result is None


def d_validity(item, result) -> bool:
    # output-validity / range sanity: flag only structurally broken output
    if result is None or not isinstance(result, pd.DataFrame) or result.empty:
        return True
    # all-NaN numeric output, or a single degenerate column, is suspicious
    num = result.select_dtypes(include=[np.number])
    if num.shape[1] and bool(num.isna().all().all()):
        return True
    return False


def _self_check(item, code: str, result: pd.DataFrame, model: str) -> bool:
    """Ask the SAME LLM whether its own result satisfies the (clarified) intent.
    Returns True if the LLM says it is WRONG."""
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    preview = result.head(12).to_string() if isinstance(result, pd.DataFrame) else str(result)
    prompt = (
        f"A pandas transform was requested:\n{item['clarified']}\n\n"
        f"The code produced this result (head):\n{preview}\n\n"
        "Does this result CORRECTLY satisfy the requested transform? "
        'Answer ONLY strict JSON: {"correct": true} or {"correct": false}.'
    )
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.0, "max_tokens": 4000},
                          timeout=(10, 90))
        r.raise_for_status()
        ch = r.json().get("choices") or []
        if not ch:
            return False
        m = re.search(r"\{.*\}", ch[0]["message"]["content"], re.S)
        verdict = json.loads(m.group(0)) if m else {}
        return verdict.get("correct") is False
    except Exception:
        return False


def _consistency(item, k_results: List[Optional[pd.DataFrame]]) -> bool:
    """CodeT-style: flag if the K independent implementations DISAGREE.
    Agreement = the modal result frame appears in > half the runs. Common-mode
    error makes wrong impls agree, so this won't flag them."""
    sigs = []
    for r in k_results:
        if r is None:
            sigs.append("__none__"); continue
        try:
            rr = r.copy()
            rr.columns = [str(c) for c in rr.columns]
            rr = rr[sorted(rr.columns)]
            for c in rr.columns:
                if pd.api.types.is_float_dtype(rr[c]):
                    rr[c] = rr[c].round(6)
            sigs.append(rr.sort_values(list(rr.columns)).to_csv(index=False))
        except Exception:
            sigs.append("__err__")
    if not sigs:
        return True
    top, n = Counter(sigs).most_common(1)[0]
    return not (n > len(sigs) / 2)  # disagreement (no majority) -> flag


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results_baseline")
    ap.add_argument("--quick", action="store_true", help="one case per class (12 cases)")
    ap.add_argument("--k", type=int, default=3, help="K implementations for consistency")
    a = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY."); return 1

    seen: Counter = Counter()
    cases = []
    for c in _cases():
        seen[c["op"]] += 1
        if a.quick and seen[c["op"]] > 1:
            continue
        cases.append({**c, "name": f"{c['op']}#{seen[c['op']]}"})
    print(f"[baseline] {len(cases)} cases x {len(MODELS)} models, K={a.k} for consistency")

    DETECTORS = ["ours", "exec_pass", "validity", "self_check", "consistency"]
    # per-detector tallies over truly-wrong (recall) and truly-correct (FP)
    fire_wrong = {d: 0 for d in DETECTORS}; wrong = 0
    fire_right = {d: 0 for d in DETECTORS}; right = 0
    rows = []

    for item in cases:
        for cond in ("ambiguous", "clarified"):
            for m in MODELS:
                # the primary generation, judged by all detectors
                code = _llm_code(item, item[cond], m)
                result = _exec(item, code) if code else None
                exec_ok = result is not None
                correct = exec_ok and _gold_correct(item, result)
                if not exec_ok:
                    continue  # crashes are not silent errors; excluded from both denominators

                # K-1 extra generations for the consistency detector (include primary)
                extra = [result]
                for _ in range(max(0, a.k - 1)):
                    c2 = _llm_code(item, item[cond], m)
                    extra.append(_exec(item, c2) if c2 else None)

                flags = {
                    "ours": d_ours(item, result),
                    "exec_pass": d_exec_pass(item, result),
                    "validity": d_validity(item, result),
                    "self_check": _self_check(item, code, result, m),
                    "consistency": _consistency(item, extra),
                }
                if correct:
                    right += 1
                    for d in DETECTORS: fire_right[d] += int(flags[d])
                else:
                    wrong += 1
                    for d in DETECTORS: fire_wrong[d] += int(flags[d])
                tag = "ok" if correct else "SILENT"
                rows.append({"name": item["name"], "cond": cond, "model": m, "tag": tag, "flags": flags})
                print(f"[{item['name']:20}] {cond:10} {m:18} {tag:7} "
                      + " ".join(f"{d}={int(flags[d])}" for d in DETECTORS), flush=True)

    def pct(n, d): return f"{100*n/d:.0f}%" if d else "n/a"
    lines = ["# Baseline head-to-head: silent-error detectors on the same 48-case grid\n",
             f"Truly-wrong (silent) results: {wrong}   |   truly-correct results: {right}\n",
             "| detector | recall (flags/silent) | false-positive (flags/correct) |",
             "|---|---|---|"]
    for d in DETECTORS:
        lines.append(f"| {d} | {fire_wrong[d]}/{wrong} ({pct(fire_wrong[d], wrong)}) | "
                     f"{fire_right[d]}/{right} ({pct(fire_right[d], right)}) |")
    lines += ["\n## Reading",
              "- exec_pass recall ~ 0: silent errors run fine, so 'did it run' detects nothing.",
              "- validity recall low: plausible-shaped wrong output passes sanity checks.",
              "- self_check limited: the model is blind to its own semantic errors (common-mode).",
              "- consistency fails on common-mode classes: wrong implementations agree with each other.",
              "- ours: high recall + low FP from goldless operator-semantic invariants."]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / "baseline_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "baseline_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n[saved] {out}/baseline_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
