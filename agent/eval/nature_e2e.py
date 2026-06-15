"""
nature_e2e.py — ② end-to-end on REAL Nature data, to actually challenge baselines.

Simple/synthetic charts are solved by one-shot LLMs (they hit 4/4). Real Nature
source-data sheets are different: genuine scientific column names, units, many
columns, non-obvious x/series — exactly where a one-shot LLM is likelier to
mis-map columns or drop a series, and where the verifier-driven inner loop with
an exact judge should help.

Reuses silent_error_audit._load_nature_fixtures (sheet -> data+spec+plot, with a
self-consistency gate that only admits cleanly-alignable sheets). Each fixture's
(data, spec) is fed to all four systems; the SAME PlotTrace oracle scores the
final chart vs the sheet data.

Systems: gpt4o_oneshot / claude_oneshot / ours_svg / ours_trace.
Requires LLM proxy env. Run:  cd agent && python eval/nature_e2e.py --cases 8 --rounds 2
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
from eval.silent_error_audit import _load_nature_fixtures, _value_cols  # noqa: E402

SYSTEMS = ["gpt4o_oneshot", "claude_oneshot", "ours_svg", "ours_trace"]


def _task_from_fixture(fx) -> Dict[str, Any]:
    """Extract (x, ys, goal) from a silent_error_audit Fixture's spec."""
    overlays = fx.spec.get("overlays", [])
    xs = [ov.get("x") for ov in overlays if ov.get("x")]
    x = xs[0] if xs else (fx.data.columns[0] if len(fx.data.columns) else "x")
    ys = _value_cols(fx.spec)
    family = "line"  # nature fixtures render as multi-line
    goal = f"plot {', '.join(ys)} against {x}"
    return {"name": fx.name, "data": fx.data, "spec": fx.spec, "x": x, "ys": ys, "family": family, "goal": goal}


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


def _oneshot(task: Dict[str, Any], model: str, workdir: Path, tag: str) -> Dict[str, Any]:
    base = os.environ["LLM_API_BASE"].rstrip("/"); key = os.environ["LLM_API_KEY"]
    cols = list(task["data"].columns)
    prompt = f"""Write matplotlib code to plot this real scientific data.
DataFrame `df` columns: {cols}. Use existing `df` and `ax`.
Plot x={task['x']!r}; plot these as separate series (lines): {task['ys']}.
Goal: {task['goal']}.
Return ONLY strict JSON: {{"code": "<plotting body using df and ax>"}}. No explanation."""
    try:
        r = requests.post(base + "/chat/completions",
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                          json={"model": model, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.2, "response_format": {"type": "json_object"}, "max_tokens": 700},
                          timeout=(10, 45))
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        code = json.loads(m.group(0) if m else content).get("code")
    except Exception:
        code = None
    if not code:
        return {"exec_pass": False, "data_fidelity": None}
    rr = _trace_render(code, task["data"], workdir, tag)
    fid = _oracle_fidelity(rr["trace_rows"], task["data"], task["spec"]) if rr["exec_pass"] else None
    return {"exec_pass": rr["exec_pass"], "data_fidelity": fid}


def _ours(task: Dict[str, Any], judge_mode: str, rounds: int, workdir: Path) -> Dict[str, Any]:
    csv_path = workdir / f"{task['name']}_{judge_mode}.csv"
    task["data"].to_csv(csv_path, index=False)
    os.environ["JUDGE_MODE"] = judge_mode
    os.environ.setdefault("BEST_OF_N", "2")
    try:
        result = run_chain(excel_path=str(csv_path), user_goal=task["goal"],
                           chart_family=task["family"], rounds=rounds, intent={"x": task["x"], "y": task["ys"][0]})
    except Exception as e:
        return {"exec_pass": False, "data_fidelity": None, "err": repr(e)[:100]}
    finally:
        os.environ.pop("JUDGE_MODE", None)
    png = result.get("png_path") if isinstance(result, dict) else None
    if not png or not Path(png).exists():
        return {"exec_pass": False, "data_fidelity": None}
    rows = []
    tc = Path(png).with_suffix(".trace.csv")
    if tc.exists():
        try:
            rows = pd.read_csv(tc).to_dict("records")
        except Exception:
            rows = []
    return {"exec_pass": True, "data_fidelity": _oracle_fidelity(rows, task["data"], task["spec"])}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Real-Nature-data end-to-end benchmark")
    ap.add_argument("--cases", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--max-per-article", type=int, default=2, help="cap fixtures per Nature article for cross-article diversity (0=unlimited)")
    ap.add_argument("--out", default="eval/results_nature_e2e")
    ap.add_argument("--baselines-only", action="store_true", help="only run one-shot baselines (fast go/no-go on silent-error rate)")
    args = ap.parse_args(argv)
    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (the proxy).")
        return 1
    systems = ["gpt4o_oneshot", "claude_oneshot"] if args.baselines_only else SYSTEMS

    fixtures = _load_nature_fixtures(limit=args.cases, max_per_article=args.max_per_article)
    if not fixtures:
        print("[error] no nature fixtures (need nature_pairs/eval_alignment_probe.jsonl).")
        return 1
    tasks = [_task_from_fixture(fx) for fx in fixtures]
    tasks = [t for t in tasks if t["ys"]]  # need at least one value column
    print(f"[info] {len(tasks)} real Nature tasks")

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for ti, task in enumerate(tasks):
            print(f"[task {ti+1}/{len(tasks)}] {task['name'][:30]} (ys={task['ys']})", flush=True)
            rec: Dict[str, Any] = {"task": task["name"][:30], "ncols": len(task["ys"])}
            runners = {
                "gpt4o_oneshot": lambda: _oneshot(task, "gpt-4o", wd, f"{task['name']}_g"),
                "claude_oneshot": lambda: _oneshot(task, "claude-sonnet-4.6", wd, f"{task['name']}_c"),
                "ours_svg": lambda: _ours(task, "svg", args.rounds, wd),
                "ours_trace": lambda: _ours(task, "trace", args.rounds, wd),
            }
            for s in systems:
                try:
                    rec[s] = runners[s]()
                except Exception as e:  # isolate: one system's failure can't sink the task/batch
                    rec[s] = {"exec_pass": False, "data_fidelity": None, "err": repr(e)[:100]}
                d = rec[s]; fid = d.get("data_fidelity")
                print(f"  {s:15} exec={d.get('exec_pass')} DF={'n/a' if fid is None else f'{fid:.2f}'} {d.get('err','')}", flush=True)
            rows.append(rec)

    report = _report(rows, systems)
    (out_dir / "nature_e2e_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "nature_e2e_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n[saved] {out_dir}/nature_e2e_report.md")
    return 0


def _report(rows: List[Dict[str, Any]], systems: List[str]) -> str:
    label = {"gpt4o_oneshot": "GPT-4o 1shot", "claude_oneshot": "Claude 1shot",
             "ours_svg": "Ours(SVG)", "ours_trace": "Ours(PlotTrace)"}
    lines = ["# Real-Nature-Data Silent-Error Measurement\n",
             "Tasks = cross-article real Nature source-data sheets (genuine scientific columns).",
             "Oracle = PlotTrace read-back of generated chart vs sheet data. DF = structure-aware F1.",
             "**silent-error = exec succeeded but DF < 1.0** (chart renders fine but draws wrong numbers).\n",
             "| Task (sheet) | #series | " + " | ".join(label[s] for s in systems) + " |",
             "|" + "---|" * (len(systems) + 2)]
    agg = {s: [] for s in systems}; ex = {s: 0 for s in systems}
    silent = {s: 0 for s in systems}  # exec_pass but DF<1.0
    n = len(rows)
    for r in rows:
        cells = []
        for s in systems:
            d = r[s]; fid = d.get("data_fidelity")
            if d.get("exec_pass") and fid is not None:
                agg[s].append(fid); ex[s] += 1
                if fid < 0.999:
                    silent[s] += 1
            cells.append("FAIL" if not d.get("exec_pass") else ("n/a" if fid is None else f"{fid:.2f}"))
        lines.append(f"| {r['task']} | {r.get('ncols','?')} | " + " | ".join(cells) + " |")
    lines.append("| **mean DF** | | " + " | ".join((f"{np.mean(agg[s]):.2f}" if agg[s] else "n/a") for s in systems) + " |")
    lines.append("| **exec-pass** | | " + " | ".join(f"{ex[s]}/{n}" for s in systems) + " |")
    # silent-error rate among successfully-rendered charts (the go/no-go number)
    lines.append("| **silent-error rate** | | " + " | ".join(
        (f"{silent[s]}/{ex[s]} ({100*silent[s]/ex[s]:.0f}%)" if ex[s] else "n/a") for s in systems) + " |")
    lines.append("\n## Reading (go/no-go for the measurement paper)")
    lines.append("- silent-error rate = of charts that rendered fine, how many drew WRONG numbers (DF<1.0).")
    lines.append("- If strong LLMs show a high silent-error rate on real scientific data, the 'missing fidelity")
    lines.append("  dimension' alarm is real and the measurement paper is viable.")
    lines.append("- If it's near 0%, strong LLMs are reliable here and the alarm doesn't ring — reconsider the framing.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
