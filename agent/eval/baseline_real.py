"""
baseline_real.py — run the 5 silent-error DETECTORS on REAL Nature tasks (closes audit e1-F4).

The head-to-head baseline (baseline_compare.py) was measured on the synthetic operator grid;
the paper's tab:baselines was mislabeled "real Nature data". This runs the SAME five detectors
(exec_pass / validity / self_check / consistency / ours) on the REAL Nature tasks built by
nature_real_auto._build (real Source-Data tables), so the baseline recall/FP are actually on
real data. Requires the real Nature corpus locally (data/nature_pairs/articles).

Run: cd agent && LLM_API_BASE=.. LLM_API_KEY=.. \
     python eval/baseline_real.py --pairs-root ../data/nature_pairs/articles --max-tasks 200 --k 5
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collections import Counter
import warnings; warnings.filterwarnings("ignore")
from eval.nature_real_auto import _build
from eval.ambiguity_calibration import _llm_code, _exec, _gold_correct, MODELS
from eval.baseline_compare import (d_ours, d_exec_pass, d_validity, _self_check,
                                   _consistency)

DETECTORS = ["ours", "exec_pass", "validity", "self_check", "consistency"]


def _write_report(out: Path, wrong: int, right: int, fire_wrong, fire_right,
                  rows, models, k: int, partial: bool = False):
    """Serialize the report + records. Called periodically (checkpoint) and at the end so an
    interrupted run still leaves a valid writer-generated artifact (no log-recovery needed)."""
    def pct(n, d): return f"{100*n/d:.0f}%" if d else "n/a"
    header = "# Baseline detectors on REAL Nature tasks (closes e1-F4)"
    if partial:
        header += f" — CHECKPOINT (in progress, {len(rows)} rows so far)"
    lines = [header + "\n",
             f"Real Nature Source-Data tables; silent (wrong): {wrong} | correct: {right} | "
             f"models={models} | K={k}.\n",
             "| detector | recall (flags/silent) | false-positive (flags/correct) |",
             "|---|---|---|"]
    for d in DETECTORS:
        lines.append(f"| {d} | {fire_wrong[d]}/{wrong} ({pct(fire_wrong[d],wrong)}) | "
                     f"{fire_right[d]}/{right} ({pct(fire_right[d],right)}) |")
    lines += ["\n## Reading",
              "- exec_pass / validity / consistency recall on REAL data confirms (or revises) the",
              "  synthetic-grid 0% — these numbers are now genuinely on Nature tables (not the grid).",
              "- self_check recall/FP is the real-data self-critique baseline.",
              "- ours = the goldless operator contracts (should stay high recall / near-0 FP)."]
    out.mkdir(parents=True, exist_ok=True)
    (out / "baseline_real_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "baseline_real_records.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-root", default="../data/nature_pairs/articles")
    ap.add_argument("--max-tasks", type=int, default=200)
    ap.add_argument("--max-per-article", type=int, default=15)
    ap.add_argument("--k", type=int, default=5, help="K samples for the consistency detector")
    ap.add_argument("--models", default=None, help="comma-separated (default = ambiguity_calibration.MODELS)")
    ap.add_argument("--out", default="eval/results_baseline_real")
    ap.add_argument("--checkpoint-every", type=int, default=10,
                    help="write a partial report every N tasks (crash-safe; 0 disables)")
    a = ap.parse_args()
    models = [m.strip() for m in a.models.split(",")] if a.models else MODELS

    tasks = _build(a.pairs_root, a.max_tasks, a.max_per_article)
    if not tasks:
        raise SystemExit(f"no real tasks built from {a.pairs_root} — is the Nature corpus present?")

    wrong = right = 0
    fire_wrong = Counter(); fire_right = Counter()
    rows = []
    out = Path(a.out)
    for ti, t in enumerate(tasks, 1):
        for cond in ("ambiguous", "clarified"):
            for m in models:
                code = _llm_code(t, t[cond], m)
                result = _exec(t, code) if code else None
                if result is None:
                    continue  # crash: excluded from both denominators
                correct = bool(_gold_correct(t, result))
                extra = [result]
                for _ in range(max(0, a.k - 1)):
                    c2 = _llm_code(t, t[cond], m)
                    extra.append(_exec(t, c2) if c2 else None)
                flags = {
                    "ours": d_ours(t, result),
                    "exec_pass": d_exec_pass(t, result),
                    "validity": d_validity(t, result),
                    "self_check": _self_check(t, code, result, m),
                    "consistency": _consistency(t, extra),
                }
                if correct:
                    right += 1
                    for d in DETECTORS: fire_right[d] += int(flags[d])
                else:
                    wrong += 1
                    for d in DETECTORS: fire_wrong[d] += int(flags[d])
                rows.append({"op": t.get("op"), "cond": cond, "model": m,
                             "tag": "ok" if correct else "SILENT", "flags": flags})
                print(f"  [{str(t.get('op'))[:18]:18}] {cond:10} {m:20} "
                      f"{'ok' if correct else 'SILENT':7} "
                      + " ".join(f"{d}={int(flags[d])}" for d in DETECTORS), flush=True)
        if a.checkpoint_every and ti % a.checkpoint_every == 0:
            _write_report(out, wrong, right, fire_wrong, fire_right, rows, models, a.k, partial=True)
            print(f"  [checkpoint] {ti}/{len(tasks)} tasks -> {out}/baseline_real_report.md", flush=True)

    lines = _write_report(out, wrong, right, fire_wrong, fire_right, rows, models, a.k, partial=False)
    print("\n" + "\n".join(lines))
    print(f"\n[saved] {out}/baseline_real_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
