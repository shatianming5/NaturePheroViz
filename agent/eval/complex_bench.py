"""
complex_bench.py — end-to-end benchmark on COMPLEX charts (multi-series, twin-axis).

Simple single-series charts are solved by one-shot LLMs, so they can't show the
value of the verifier-driven inner loop. THIS is the real test: charts where a
one-shot LLM is more likely to mis-map columns, drop a series, or mis-bind a
twin axis — and where an exact execution-traced judge should help most.

Systems (same as end2end_bench): gpt4o_oneshot / claude_oneshot / ours_svg /
ours_trace. Same independent PlotTrace oracle (final chart vs input data), so
multi-series fidelity is measured apples-to-apples.

Tasks: multi-line (2 series), grouped bar (2 series), twin-axis (bar + line on
a right axis — the classic "ratio vs absolute" trap), 3-series line.

Requires LLM proxy env. Run:  cd agent && python eval/complex_bench.py --rounds 2
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
matplotlib.rcParams["font.family"] = "DejaVu Sans"  # server has no Arial
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
        {"name": "multi_line2", "family": "line", "goal": "plot actual and target as two lines over quarters",
         "ys": ["actual", "target"], "x": "q",
         "data": pd.DataFrame({"q": ["Q1", "Q2", "Q3", "Q4"],
                               "actual": [10.0, 22.0, 18.0, 30.0],
                               "target": [12.0, 20.0, 21.0, 28.0]})},
        {"name": "grouped_bar2", "family": "bar", "goal": "compare 2023 and 2024 by region as grouped bars",
         "ys": ["y2023", "y2024"], "x": "region",
         "data": pd.DataFrame({"region": ["N", "S", "E", "W"],
                               "y2023": [50.0, 70.0, 65.0, 80.0],
                               "y2024": [55.0, 68.0, 72.0, 90.0]})},
        {"name": "three_line", "family": "line", "goal": "plot prod_a, prod_b, prod_c sales across months",
         "ys": ["prod_a", "prod_b", "prod_c"], "x": "month",
         "data": pd.DataFrame({"month": ["Jan", "Feb", "Mar", "Apr", "May"],
                               "prod_a": [100.0, 120.0, 90.0, 140.0, 110.0],
                               "prod_b": [80.0, 85.0, 95.0, 70.0, 100.0],
                               "prod_c": [60.0, 75.0, 65.0, 90.0, 80.0]})},
        {"name": "twin_axis", "family": "bar", "goal": "bar of sales (left axis) with a line of conversion rate (right axis)",
         "ys": ["sales", "rate"], "x": "month", "twin": True,
         "data": pd.DataFrame({"month": ["Jan", "Feb", "Mar", "Apr"],
                               "sales": [1200.0, 1350.0, 980.0, 1500.0],
                               "rate": [0.12, 0.11, 0.13, 0.10]})},
    ]


def _spec_for(task: Dict[str, Any]) -> Dict[str, Any]:
    mark = "line" if task["family"] == "line" else "bar"
    overlays = []
    for i, y in enumerate(task["ys"]):
        ov = {"mark": mark, "x": task["x"], "y": y, "yaxis": "left"}
        if task.get("twin") and i == len(task["ys"]) - 1:
            ov["yaxis"] = "right"
            ov["mark"] = "line"  # rate as a line on the right axis
        overlays.append(ov)
    return {"overlays": overlays}


# --- shared oracle ------------------------------------------------------------


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
    except Exception as e:
        return {"exec_pass": False, "trace_rows": [], "err": repr(e)[:120]}


def _oneshot_code(task: Dict[str, Any], model: str) -> Optional[str]:
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    cols = list(task["data"].columns)
    twin_hint = ""
    if task.get("twin"):
        twin_hint = (f"\nIMPORTANT: plot '{task['ys'][0]}' as bars on the LEFT y-axis, and "
                     f"'{task['ys'][-1]}' as a line on a SEPARATE RIGHT y-axis (use ax.twinx()).")
    prompt = f"""Write matplotlib code to plot this data. Goal: {task['goal']}.
DataFrame `df` has columns {cols}. Use the existing `df` and `ax` (matplotlib Axes).
Plot x={task['x']}, and these series as y: {task['ys']}.{twin_hint}
Return ONLY strict JSON: {{"code": "<plotting code body using df and ax>"}}. No explanation."""
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.2, "response_format": {"type": "json_object"}, "max_tokens": 600},
                          timeout=(10, 45))
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


def _run_ours(task: Dict[str, Any], judge_mode: str, rounds: int, workdir: Path) -> Dict[str, Any]:
    csv_path = workdir / f"{task['name']}_{judge_mode}.csv"
    task["data"].to_csv(csv_path, index=False)
    intent: Dict[str, Any] = {"x": task["x"], "y": task["ys"][0]}
    if len(task["ys"]) > 1:
        intent["y_extra"] = task["ys"][1:]  # hint extra series (runner may use or ignore)
    os.environ["JUDGE_MODE"] = judge_mode
    os.environ.setdefault("BEST_OF_N", "2")
    try:
        result = run_chain(excel_path=str(csv_path), user_goal=task["goal"],
                           chart_family=task["family"], rounds=rounds, intent=intent)
    except Exception as e:
        return {"exec_pass": False, "data_fidelity": None, "err": repr(e)[:100]}
    finally:
        os.environ.pop("JUDGE_MODE", None)
    png = result.get("png_path") if isinstance(result, dict) else None
    if not png or not Path(png).exists():
        return {"exec_pass": False, "data_fidelity": None}
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
    ap = argparse.ArgumentParser(description="Complex-chart end-to-end benchmark")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--out", default="eval/results_complex")
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
                print(f"[{task['name']}] {s:15} exec={d.get('exec_pass')} DF={'n/a' if fid is None else f'{fid:.2f}'} {d.get('err','')}")
            rows.append(rec)

    report = _report(rows)
    (out_dir / "complex_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "complex_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n[saved] {out_dir}/complex_report.md")
    return 0


def _report(rows: List[Dict[str, Any]]) -> str:
    label = {"gpt4o_oneshot": "GPT-4o one-shot", "claude_oneshot": "Claude one-shot",
             "ours_svg": "Ours (SVG judge)", "ours_trace": "Ours (PlotTrace judge)"}
    lines = ["# Complex-Chart End-to-End Benchmark\n",
             "Multi-series / twin-axis charts (where one-shot LLMs mis-map / drop series).",
             "Same independent PlotTrace oracle (final chart vs input data). DF: structure-aware F1.\n",
             "| Task | " + " | ".join(label[s] for s in SYSTEMS) + " |",
             "|" + "---|" * (len(SYSTEMS) + 1)]
    agg = {s: [] for s in SYSTEMS}; ex = {s: 0 for s in SYSTEMS}; n = len(rows)
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
    lines.append("- On complex charts one-shot LLMs are expected to slip (wrong mapping / dropped series / twin-axis).")
    lines.append("- The verifier-driven inner loop can catch and repair these — IF the judge is exact (PlotTrace).")
    lines.append("- Ours(PlotTrace) vs Ours(SVG): does the exact judge give higher final DF on hard charts?")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
