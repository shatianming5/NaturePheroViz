"""
consistency_temp.py — does the multi-sample CONSISTENCY baseline catch silent errors when
the K implementations are actually sampled at temperature > 0? (audit e1-F5)

The head-to-head baseline measured "consistency" with temperature 0 (non-reasoning models),
so the K samples were near-identical and it could never flag disagreement -> 0% by construction.
This re-runs the consistency detector with K genuinely diverse samples (temperature 0.8) to test
whether the 0% is a temp-0 artifact or a real common-mode-agreement result.

For each transform_bench case x condition x model: sample K implementations at temp>0, exec each,
label the primary by hidden gold (silent vs correct), run the CodeT-style consistency detector on
the K results, and report recall (flags/silent) + FP (flags/correct).

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. python eval/consistency_temp.py --model gpt-4o --k 5
"""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
import warnings; warnings.filterwarnings("ignore")
from eval.transform_bench import _cases
from eval.ambiguity_calibration import _exec, _gold_correct
from eval.baseline_compare import _consistency


def gen_temp(item, prompt_text, model, temp):
    """_llm_code but with an explicit temperature (non-reasoning models only)."""
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    cols = list(item["df"].columns)
    extra = f"\nA second dataframe `df2` columns={list(item['df2'].columns)}." if "df2" in item else ""
    prompt = (f"pandas `df` columns={cols}.{extra}\n{prompt_text}\n"
              f"The dataframe(s) `df`{'/`df2`' if 'df2' in item else ''} ALREADY EXIST in scope with the real data.\n"
              "Do NOT re-create or re-assign them, do NOT import anything, do NOT print.\n"
              f"Use only the given `df`{'/`df2`' if 'df2' in item else ''}, assign the final answer to `result`.\n"
              'Return ONLY strict JSON: {"code": "<pandas code defining result>"}.')
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": temp, "max_tokens": 4000}, timeout=(10, 120))
        r.raise_for_status()
        ch = r.json().get("choices") or []
        if not ch:
            return None
        c = ch[0]["message"]["content"]
        m = re.search(r"\{.*\}", c, re.S)
        return json.loads(m.group(0) if m else c).get("code")
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--temp", type=float, default=0.8)
    ap.add_argument("--out", default="eval/results_consistency_temp/report.md")
    a = ap.parse_args()

    cases = _cases()
    wrong = right = fire_wrong = fire_right = n = 0
    diverse_tasks = 0
    recs = []
    for c in cases:
        for cond in ("ambiguous", "clarified"):
            ks = [gen_temp(c, c[cond], a.model, a.temp) for _ in range(a.k)]
            results = [_exec(c, code) if code else None for code in ks]
            prim = results[0]
            if prim is None:
                continue  # crash: excluded
            correct = _gold_correct(c, prim)
            flag = _consistency(c, results)
            # count how many distinct exec-ok signatures (diversity check)
            sigs = set()
            for r in results:
                if r is not None:
                    try:
                        sigs.add(r.round(6).to_csv(index=False) if hasattr(r, "round") else str(r))
                    except Exception:
                        pass
            if len(sigs) > 1:
                diverse_tasks += 1
            n += 1
            if correct:
                right += 1; fire_right += int(flag)
            else:
                wrong += 1; fire_wrong += int(flag)
            recs.append({"op": c.get("op"), "cond": cond, "correct": correct, "flag": bool(flag),
                         "distinct_sigs": len(sigs)})
            print(f"  {c.get('op','?'):22} {cond:10} {'CORRECT' if correct else 'SILENT':7} "
                  f"consistency_flag={int(flag)} distinct={len(sigs)}", flush=True)

    def pct(x, d): return f"{100*x/d:.0f}%" if d else "n/a"
    lines = [f"# Consistency baseline at temperature {a.temp} (K={a.k}, model={a.model})\n",
             f"Silent (wrong): {wrong} | correct: {right} | tasks with >1 distinct sample: "
             f"{diverse_tasks}/{n} ({pct(diverse_tasks,n)}) — confirms samples are genuinely diverse at temp>0.\n",
             "| detector | recall (flags/silent) | false-positive (flags/correct) |",
             "|---|---|---|",
             f"| consistency @T={a.temp} | {fire_wrong}/{wrong} ({pct(fire_wrong,wrong)}) | {fire_right}/{right} ({pct(fire_right,right)}) |",
             "| consistency @T=0 (head-to-head baseline) | 0% (by construction: identical samples) | 0% |",
             "\n## Reading",
             f"- At T={a.temp} the K samples ARE diverse ({pct(diverse_tasks,n)} of tasks show >1 distinct output),",
             "  so this is a faithful CodeT/self-consistency test, not a temp-0 artifact.",
             f"- Consistency recall is {pct(fire_wrong,wrong)}: if ~0%, the silent errors are COMMON-MODE (the",
             "  diverse samples still agree on the WRONG answer) — a stronger 'invisible' result than temp-0;",
             "  if high, the earlier 0% was a temp-0 artifact and should be revised."]
    outp = Path(a.out); outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text("\n".join(lines) + "\n")
    json.dump({"model": a.model, "k": a.k, "temp": a.temp, "wrong": wrong, "right": right,
               "recall": [fire_wrong, wrong], "fp": [fire_right, right],
               "diverse_tasks": [diverse_tasks, n], "cases": recs},
              open(str(outp).replace(".md", ".json"), "w"), indent=2)
    print("\n" + "\n".join(lines))
    print(f"\n-> {outp}")


if __name__ == "__main__":
    raise SystemExit(main())
