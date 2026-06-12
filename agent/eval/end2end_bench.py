"""
end2end_bench.py — unified end-to-end benchmark (Task 1 + Task 2 in one table).

Answers two questions with ONE experiment, on the SAME tasks, scored by the SAME
independent oracle (PlotTrace read-back of the final chart vs the input data):

  Task 1 (judge-driven inner loop): does a BETTER in-loop judge yield a more
    faithful final chart?  -> compare `ours_trace` vs `ours_svg`.
  Task 2 (baseline main table): how does our code-first agent compare to
    one-shot LLM code generation?  -> compare `ours_*` vs `gpt4o_oneshot` /
    `claude_oneshot`.

Systems:
  ours_trace     : our agent inner loop, JUDGE_MODE=trace (PlotTrace, ours)
  ours_svg       : our agent inner loop, JUDGE_MODE=svg   (SVG/VisEval ablation)
  gpt4o_oneshot  : single LLM prompt -> plotting code (gpt-4o)
  claude_oneshot : single LLM prompt -> plotting code (claude-sonnet-4.6)

Metric (per system, per task):
  exec_pass      : did the final code render a chart?
  data_fidelity  : PlotTrace(final chart) vs input data, structure-aware F1.
                   This is the SAME oracle for every system (no self-judging).

Requires LLM proxy env (LLM_API_BASE / LLM_API_KEY / LLM_MODEL).
Run:  cd agent && python eval/end2end_bench.py --rounds 2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app.services import fidelity_verifier as fv  # noqa: E402
from app.services.plot_trace import PlotTracer  # noqa: E402
from app.services.single_chain_runner import run_chain  # noqa: E402

SYSTEMS = ["gpt4o_oneshot", "claude_oneshot", "ours_svg", "ours_trace"]


def _tasks() -> List[Dict[str, Any]]:
    return [
        {"name": "sales_bar", "family": "bar", "goal": "monthly sales as a bar chart",
         "intent": {"x": "month", "y": "sales"},
         "data": pd.DataFrame({"month": ["Jan", "Feb", "Mar", "Apr", "May"],
                               "sales": [120.0, 135.0, 98.0, 150.0, 110.0]})},
        {"name": "revenue_bar", "family": "bar", "goal": "revenue by category",
         "intent": {"x": "cat", "y": "rev"},
         "data": pd.DataFrame({"cat": ["A", "B", "C", "D"], "rev": [1300.0, 900.0, 1100.0, 1450.0]})},
        {"name": "trend_line", "family": "line", "goal": "value trend over quarters",
         "intent": {"x": "q", "y": "v"},
         "data": pd.DataFrame({"q": ["Q1", "Q2", "Q3", "Q4"], "v": [10.0, 22.0, 18.0, 30.0]})},
        {"name": "pop_bar", "family": "bar", "goal": "population by city",
         "intent": {"x": "city", "y": "pop"},
         "data": pd.DataFrame({"city": ["NY", "LA", "SF", "BOS", "CHI"], "pop": [840.0, 390.0, 88.0, 69.0, 270.0]})},
    ]


def _spec_for(task: Dict[str, Any]) -> Dict[str, Any]:
    mark = "line" if task["family"] == "line" else "bar"
    return {"overlays": [{"mark": mark, "x": task["intent"]["x"], "y": task["intent"]["y"], "yaxis": "left"}]}


# --- shared oracle: trace read-back of a rendered chart vs input data ---------


def _oracle_fidelity(trace_rows: List[Dict[str, Any]], data: pd.DataFrame, spec: Dict[str, Any]) -> Optional[float]:
    if not trace_rows:
        return None
    tdf = pd.DataFrame(trace_rows)
    if not {"series", "x", "value"}.issubset(tdf.columns):
        return None
    pred = fv._coerce_pred_table(tdf[["series", "x", "value"]], data, spec)
    if pred is None or pred.empty:
        return None
    gt_norm, x_col, y_col, g_col = fv._normalize_ground_truth(data, spec)
    if g_col and g_col != "series" and "series" in pred.columns and g_col not in pred.columns:
        pred = pred.rename(columns={"series": g_col})
    f = fv._safe_match(pred, gt_norm, x_col, y_col, g_col).get("data_fidelity")
    return float(f) if f is not None else None


def _trace_render(code_body: str, data: pd.DataFrame, workdir: Path, tag: str) -> Dict[str, Any]:
    """Render a plotting-code body (uses df, ax) with execution trace."""
    png = workdir / f"{tag}.png"
    tracer = PlotTracer()
    ns: Dict[str, Any] = {"df": data.copy()}
    src = ("import matplotlib; matplotlib.use('Agg')\n"
           "import matplotlib.pyplot as plt, pandas as pd, numpy as np\n"
           "fig, ax = plt.subplots(figsize=(5,3))\n"
           f"{code_body}\n"
           "fig.tight_layout()\n"
           f"fig.savefig({str(png)!r}, dpi=80)\n"
           "plt.close('all')\n")
    try:
        with tracer.install():
            exec(compile(src, f"<{tag}>", "exec"), ns)  # noqa: S102
        return {"exec_pass": png.exists(), "trace_rows": tracer.to_records()}
    except Exception:
        return {"exec_pass": False, "trace_rows": []}


# --- one-shot LLM baselines ---------------------------------------------------


def _oneshot_code(task: Dict[str, Any], model: str) -> Optional[str]:
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    cols = list(task["data"].columns)
    prompt = f"""Write matplotlib code to plot this data. Goal: {task['goal']}.
DataFrame `df` has columns {cols}. Use the existing `df` and `ax` (a matplotlib Axes).
Plot x={task['intent']['x']}, y={task['intent']['y']} as a {task['family']} chart.
Return ONLY strict JSON: {{"code": "<plotting code body using df and ax>"}}. No explanation."""
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.2, "response_format": {"type": "json_object"}, "max_tokens": 400},
                          timeout=(10, 60))
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        obj = json.loads(m.group(0) if m else content)
        c = obj.get("code")
        return c if isinstance(c, str) and c.strip() else None
    except Exception:
        return None


def _run_oneshot(task: Dict[str, Any], model: str, workdir: Path, tag: str) -> Dict[str, Any]:
    code = _oneshot_code(task, model)
    if not code:
        return {"exec_pass": False, "data_fidelity": None}
    r = _trace_render(code, task["data"], workdir, tag)
    fid = _oracle_fidelity(r["trace_rows"], task["data"], _spec_for(task)) if r["exec_pass"] else None
    return {"exec_pass": r["exec_pass"], "data_fidelity": fid}


# --- our agent inner loop (trace / svg judge) ---------------------------------


def _run_ours(task: Dict[str, Any], judge_mode: str, rounds: int, workdir: Path) -> Dict[str, Any]:
    csv_path = workdir / f"{task['name']}_{judge_mode}.csv"
    task["data"].to_csv(csv_path, index=False)
    os.environ["JUDGE_MODE"] = judge_mode
    os.environ.setdefault("BEST_OF_N", "2")
    try:
        result = run_chain(excel_path=str(csv_path), user_goal=task["goal"],
                           chart_family=task["family"], rounds=rounds, intent=task["intent"])
    except Exception as e:
        return {"exec_pass": False, "data_fidelity": None, "err": repr(e)[:100]}
    finally:
        os.environ.pop("JUDGE_MODE", None)

    png = result.get("png_path") if isinstance(result, dict) else None
    if not png or not Path(png).exists():
        return {"exec_pass": False, "data_fidelity": None}
    # SAME oracle: trace read-back of the final chart vs input data
    trace_csv = Path(png).with_suffix(".trace.csv")
    rows = []
    if trace_csv.exists():
        try:
            rows = pd.read_csv(trace_csv).to_dict("records")
        except Exception:
            rows = []
    fid = _oracle_fidelity(rows, task["data"], _spec_for(task))
    return {"exec_pass": True, "data_fidelity": fid}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Unified end-to-end benchmark")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default="eval/results_e2e")
    args = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (the proxy).")
        return 1

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    tasks = _tasks()
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for task in tasks:
            rec: Dict[str, Any] = {"task": task["name"]}
            rec["gpt4o_oneshot"] = _run_oneshot(task, "gpt-4o", wd, f"{task['name']}_gpt4o")
            rec["claude_oneshot"] = _run_oneshot(task, "claude-sonnet-4.6", wd, f"{task['name']}_claude")
            rec["ours_svg"] = _run_ours(task, "svg", args.rounds, wd)
            rec["ours_trace"] = _run_ours(task, "trace", args.rounds, wd)
            for s in SYSTEMS:
                d = rec[s]; fid = d.get("data_fidelity")
                print(f"[{task['name']}] {s:15} exec={d.get('exec_pass')} DF={'n/a' if fid is None else f'{fid:.2f}'}")
            rows.append(rec)

    report = _report(rows)
    (out_dir / "e2e_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "e2e_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n[saved] {out_dir}/e2e_report.md")
    return 0


def _report(rows: List[Dict[str, Any]]) -> str:
    label = {"gpt4o_oneshot": "GPT-4o one-shot", "claude_oneshot": "Claude one-shot",
             "ours_svg": "Ours (SVG judge)", "ours_trace": "Ours (PlotTrace judge)"}
    lines = ["# Unified End-to-End Benchmark\n",
             "Same tasks, same independent oracle (PlotTrace read-back of FINAL chart vs input data).",
             "exec = rendered a chart; DF = data fidelity (structure-aware F1, 1.0 = perfect).\n",
             "| Task | " + " | ".join(label[s] for s in SYSTEMS) + " |",
             "|" + "---|" * (len(SYSTEMS) + 1)]
    agg = {s: [] for s in SYSTEMS}
    ex = {s: 0 for s in SYSTEMS}
    n = len(rows)
    for r in rows:
        cells = []
        for s in SYSTEMS:
            d = r[s]; fid = d.get("data_fidelity")
            if d.get("exec_pass") and fid is not None:
                agg[s].append(fid); ex[s] += 1
            cells.append("FAIL" if not d.get("exec_pass") else ("n/a" if fid is None else f"{fid:.2f}"))
        lines.append(f"| {r['task']} | " + " | ".join(cells) + " |")
    lines.append("| **mean DF** | " + " | ".join((f"{np.mean(agg[s]):.2f}" if agg[s] else "n/a") for s in SYSTEMS) + " |")
    lines.append("| **exec-pass** | " + " | ".join(f"{ex[s]}/{n}" for s in SYSTEMS) + " |")
    lines.append("\n## Reading")
    lines.append("- Task 1 (judge ablation): Ours(PlotTrace) vs Ours(SVG) — does the better in-loop judge give higher final DF?")
    lines.append("- Task 2 (baselines): Ours vs one-shot GPT-4o / Claude — does the code-first agent + verifier loop beat one-shot generation?")
    lines.append("- All scored by the same trace oracle, so the comparison is apples-to-apples and self-judging is excluded.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
