"""
run_benchmark.py — unified benchmark harness (B1).

Runs any system on a dataset, producing standardized results per the §1 contract:
  results/<system>/<task_id>/
    code.py            # generated plotting code
    chart.png          # rendered chart
    chart.svg          # rendered SVG
    plot_df.csv        # ground-truth data table (what SHOULD be drawn)
    pred_table.csv     # validator's read-back table (when validator runs)
    record.json        # standard record per §1 schema

Supported systems:
  ours          : our code-first agent inner loop (multi-round)
  gpt4o_oneshot : single GPT-4o prompt -> plotting code
  claude_oneshot: single Claude prompt -> plotting code

Datasets (priority):
  matplotbench  : MatPlotBench (100 tasks, from thunlp/MatPlotAgent)
  builtin       : built-in 4-fixture test set (smoke test)
  custom        : user-supplied JSONL with tasks

Usage:
  cd agent
  python eval/run_benchmark.py --system ours --dataset builtin --rounds 2
  python eval/run_benchmark.py --system gpt4o_oneshot --dataset builtin
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from app.services import fidelity_verifier as fv
from app.services.plot_trace import PlotTracer
from app.services.single_chain_runner import run_chain

# ── Task definitions ────────────────────────────────────────────────────────

def _builtin_tasks() -> List[Dict[str, Any]]:
    """Built-in tasks for smoke testing the harness itself."""
    return [
        {
            "task_id": "builtin_001",
            "name": "sales_bar",
            "family": "bar",
            "goal": "monthly sales as a bar chart",
            "intent": {"x": "month", "y": "sales"},
            "data": pd.DataFrame({
                "month": ["Jan", "Feb", "Mar", "Apr", "May"],
                "sales": [120.0, 135.0, 98.0, 150.0, 110.0],
            }),
        },
        {
            "task_id": "builtin_002",
            "name": "revenue_bar",
            "family": "bar",
            "goal": "revenue by category",
            "intent": {"x": "cat", "y": "rev"},
            "data": pd.DataFrame({
                "cat": ["A", "B", "C", "D"],
                "rev": [1300.0, 900.0, 1100.0, 1450.0],
            }),
        },
        {
            "task_id": "builtin_003",
            "name": "trend_line",
            "family": "line",
            "goal": "value trend over quarters",
            "intent": {"x": "q", "y": "v"},
            "data": pd.DataFrame({
                "q": ["Q1", "Q2", "Q3", "Q4"],
                "v": [10.0, 22.0, 18.0, 30.0],
            }),
        },
        {
            "task_id": "builtin_004",
            "name": "pop_bar",
            "family": "bar",
            "goal": "population by city",
            "intent": {"x": "city", "y": "pop"},
            "data": pd.DataFrame({
                "city": ["NY", "LA", "SF", "BOS", "CHI"],
                "pop": [840.0, 390.0, 88.0, 69.0, 270.0],
            }),
        },
    ]


def _spec_for(task: Dict[str, Any]) -> Dict[str, Any]:
    mark = "line" if task["family"] == "line" else "bar"
    return {"overlays": [{"mark": mark, "x": task["intent"]["x"], "y": task["intent"]["y"], "yaxis": "left"}]}


# ── Shared utilities ────────────────────────────────────────────────────────

def _oracle_fidelity(trace_rows: List[Dict[str, Any]], data: pd.DataFrame, spec: Dict[str, Any]) -> Optional[float]:
    """Independent oracle: PlotTrace read-back of final chart vs input data."""
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
    result = fv._safe_match(pred, gt_norm, x_col, y_col, g_col)
    return float(result["data_fidelity"]) if result.get("data_fidelity") is not None else None


def _render_code(code_body: str, data: pd.DataFrame, out_dir: Path, tag: str) -> Dict[str, Any]:
    """Render a plotting-code body with execution trace. Returns {exec_pass, png_path, svg_path, trace_rows}."""
    png = out_dir / f"{tag}.png"
    svg = out_dir / f"{tag}.svg"
    tracer = PlotTracer()
    ns: Dict[str, Any] = {"df": data.copy()}
    src = (
        "import matplotlib; matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt, pandas as pd, numpy as np\n"
        "fig, ax = plt.subplots(figsize=(5, 3))\n"
        f"{code_body}\n"
        "fig.tight_layout()\n"
        f"fig.savefig({str(png)!r}, dpi=80)\n"
        f"fig.savefig({str(svg)!r}, format='svg')\n"
        "plt.close('all')\n"
    )
    try:
        with tracer.install():
            exec(compile(src, f"<{tag}>", "exec"), ns)
        return {
            "exec_pass": png.exists(),
            "png_path": str(png) if png.exists() else None,
            "svg_path": str(svg) if svg.exists() else None,
            "trace_rows": tracer.to_records(),
        }
    except Exception:
        return {"exec_pass": False, "png_path": None, "svg_path": None, "trace_rows": []}


# ── System runners ──────────────────────────────────────────────────────────

def _run_ours(task: Dict[str, Any], rounds: int, out_dir: Path) -> Dict[str, Any]:
    """Run our code-first agent inner loop on one task."""
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # Save ground truth
    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    # Write CSV for run_chain input
    csv_path = task_dir / "input.csv"
    task["data"].to_csv(csv_path, index=False)

    t0 = time.time()
    try:
        result = run_chain(
            excel_path=str(csv_path),
            user_goal=task["goal"],
            chart_family=task["family"],
            rounds=rounds,
            intent=task["intent"],
        )
    except Exception as e:
        result = {"error": str(e)[:200]}
    elapsed = time.time() - t0

    if not isinstance(result, dict):
        result = {}

    png_path = result.get("png_path")
    exec_pass = bool(png_path and Path(png_path).exists())

    # Collect artifacts
    if exec_pass:
        # Copy chart.png / chart.svg to task_dir
        import shutil
        src_png = Path(png_path)
        dst_png = task_dir / "chart.png"
        if src_png != dst_png and src_png.exists():
            shutil.copy2(src_png, dst_png)

        svg_candidate = src_png.with_suffix(".svg")
        dst_svg = task_dir / "chart.svg"
        if svg_candidate.exists():
            shutil.copy2(svg_candidate, dst_svg)

        # Copy code.py if present
        code_candidate = src_png.parent / f"code_round_{result.get('round', 1)}.py"
        if code_candidate.exists():
            shutil.copy2(code_candidate, task_dir / "code.py")

        # Try to get trace
        trace_csv = src_png.with_suffix(".trace.csv")
        trace_rows = []
        if trace_csv.exists():
            try:
                trace_rows = pd.read_csv(trace_csv).to_dict("records")
            except Exception:
                pass

        spec = _spec_for(task)
        fid = _oracle_fidelity(trace_rows, task["data"], spec)

        # Also produce pred_table.csv if validator ran
        if fid is not None and svg_candidate.exists():
            try:
                verifier_result = fv.verify_fidelity(str(dst_svg), task["data"], spec, str(dst_png))
                pred_table = verifier_result.get("pred_table")
                if isinstance(pred_table, pd.DataFrame) and not pred_table.empty:
                    pred_table.to_csv(task_dir / "pred_table.csv", index=False)
            except Exception:
                pass
    else:
        fid = None

    scores = (result.get("scores") or {}) if isinstance(result, dict) else {}
    record = {
        "task_id": task_id,
        "system": "ours",
        "exec_pass": exec_pass,
        "scores": {
            "visual_form": float(scores.get("visual_form", 0.0)),
            "data_fidelity": float(fid) if fid is not None else 0.0,
            "series_cohesion": float(scores.get("series_cohesion", 0.0)),
        },
        "fidelity_detail": {
            "rms_f1": float(fid) if fid is not None else 0.0,
            "rnss": 0.0,
            "mismatches": [],
        },
        "rounds_used": result.get("round", rounds) if isinstance(result, dict) else rounds,
        "tokens": 0,
        "ground_truth_ref": str(gt_path),
        "notes": f"elapsed={elapsed:.1f}s",
    }
    (task_dir / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _oneshot_code(task: Dict[str, Any], model: str) -> Optional[str]:
    """Generate plotting code via a single LLM call."""
    base = os.environ["LLM_API_BASE"].rstrip("/")
    key = os.environ["LLM_API_KEY"]
    cols = list(task["data"].columns)
    prompt = (
        f"Write matplotlib code to plot this data. Goal: {task['goal']}.\n"
        f"DataFrame `df` has columns {cols}. Use the existing `df` and `ax` (a matplotlib Axes).\n"
        f"Plot x={task['intent']['x']}, y={task['intent']['y']} as a {task['family']} chart.\n"
        'Return ONLY strict JSON: {"code": "<plotting code body using df and ax>"}. No explanation.'
    )
    try:
        r = requests.post(
            base + "/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 800,
            },
            timeout=(10, 60),
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.S)
        obj = json.loads(m.group(0) if m else content)
        c = obj.get("code")
        return c if isinstance(c, str) and c.strip() else None
    except Exception:
        return None


def _run_oneshot(task: Dict[str, Any], model: str, system_name: str, out_dir: Path) -> Dict[str, Any]:
    """Run a one-shot LLM baseline on one task."""
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    # Save ground truth
    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    code = _oneshot_code(task, model)
    exec_pass = False
    fid = None

    if code:
        # Save the code
        (task_dir / "code.py").write_text(code, encoding="utf-8")

        render_result = _render_code(code, task["data"], task_dir, "chart")
        exec_pass = render_result["exec_pass"]

        if exec_pass:
            spec = _spec_for(task)
            fid = _oracle_fidelity(render_result["trace_rows"], task["data"], spec)

    record = {
        "task_id": task_id,
        "system": system_name,
        "exec_pass": exec_pass,
        "scores": {
            "visual_form": 0.0,
            "data_fidelity": float(fid) if fid is not None else 0.0,
            "series_cohesion": 0.0,
        },
        "fidelity_detail": {
            "rms_f1": float(fid) if fid is not None else 0.0,
            "rnss": 0.0,
            "mismatches": [],
        },
        "rounds_used": 1,
        "tokens": 0,
        "ground_truth_ref": str(gt_path),
        "notes": "",
    }
    (task_dir / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


# ── Dataset loaders ─────────────────────────────────────────────────────────

def _load_matplotbench() -> List[Dict[str, Any]]:
    """Load MatPlotBench dataset from the MatPlotAgent repo.

    Real layout (MatPlotAgent-main/):
      benchmark_data/
        benchmark_instructions.json   # array of {id, simple_instruction, expert_instruction}
        data/<task_id>/data.csv       # each task's CSV data (not all tasks have CSV)
        ground_truth/<task_id>.png    # ground-truth rendered chart

    Default search paths:
      agent/data/MatPlotAgent-main/benchmark_data/
      agent/data/matplotbench/benchmark_data/
    """
    # Search for the MatPlotAgent root
    candidates = [
        Path("data/MatPlotAgent-main"),
        Path("../data/MatPlotAgent-main"),
        Path("data/matplotbench"),
        Path("../data/matplotbench"),
    ]
    repo_root = None
    for c in candidates:
        instr_path = c / "benchmark_data" / "benchmark_instructions.json"
        if instr_path.exists():
            repo_root = c
            break
    if repo_root is None:
        return []

    bench_dir = repo_root / "benchmark_data"
    instructions_path = bench_dir / "benchmark_instructions.json"
    data_dir = bench_dir / "data"

    try:
        all_instructions = json.loads(instructions_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    tasks: List[Dict[str, Any]] = []
    for item in all_instructions:
        task_id = str(item.get("id", ""))
        if not task_id:
            continue

        # Load CSV data if exists
        csv_file = data_dir / task_id / "data.csv"
        if not csv_file.exists():
            # Some MatPlotBench tasks are code-only (no external data)
            continue
        try:
            df = pd.read_csv(csv_file)
        except Exception:
            continue

        goal = item.get("simple_instruction", item.get("query", f"Plot {task_id}"))
        # Try to guess chart family from instruction
        goal_lower = goal.lower()
        if "bar" in goal_lower or "histogram" in goal_lower:
            family = "bar"
        elif "line" in goal_lower or "trend" in goal_lower or "series" in goal_lower:
            family = "line"
        elif "scatter" in goal_lower:
            family = "scatter"
        elif "pie" in goal_lower:
            family = "pie"
        elif "box" in goal_lower:
            family = "box"
        elif "heatmap" in goal_lower or "imshow" in goal_lower:
            family = "heatmap"
        elif "violin" in goal_lower:
            family = "violin"
        else:
            family = "other"

        # Infer x/y columns from data
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        non_numeric_cols = [c for c in df.columns if c not in numeric_cols]
        x_col = non_numeric_cols[0] if non_numeric_cols else (numeric_cols[0] if len(numeric_cols) >= 2 else df.columns[0])
        y_col = numeric_cols[-1] if numeric_cols else df.columns[-1]

        tasks.append({
            "task_id": task_id,
            "name": f"matplotbench_{task_id}",
            "family": family,
            "goal": goal,
            "intent": {"x": x_col, "y": y_col},
            "data": df,
        })

    return tasks


def _load_dataset(dataset_name: str) -> Tuple[List[Dict[str, Any]], str]:
    """Return (tasks, dataset_label)."""
    if dataset_name == "builtin":
        return _builtin_tasks(), "builtin"
    elif dataset_name == "matplotbench":
        tasks = _load_matplotbench()
        if not tasks:
            print("[warn] MatPlotBench dataset not found. Place it at agent/data/matplotbench/benchmark_data/")
            print("       or clone from https://github.com/thunlp/MatPlotAgent")
        return tasks, "matplotbench"
    else:
        # Custom: treat as path to JSONL
        custom_path = Path(dataset_name)
        if not custom_path.exists():
            raise SystemExit(f"Dataset not found: {dataset_name}")
        tasks = []
        for line in custom_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            csv_path = Path(obj.get("csv_path", ""))
            if not csv_path.is_absolute():
                csv_path = custom_path.parent / csv_path
            if not csv_path.exists():
                continue
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                continue
            tasks.append({
                "task_id": obj.get("task_id", csv_path.stem),
                "name": obj.get("name", csv_path.stem),
                "family": obj.get("family", obj.get("chart_family", "bar")),
                "goal": obj.get("goal", obj.get("query", f"Plot {csv_path.stem}")),
                "intent": obj.get("intent", {"x": df.columns[0], "y": df.columns[-1]}),
                "data": df,
            })
        return tasks, "custom"


# ── Main ────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Unified benchmark harness (B1)")
    ap.add_argument("--system", required=True,
                    choices=["ours", "gpt4o_oneshot", "claude_oneshot", "qwen_zeroshot"],
                    help="Which system to run")
    ap.add_argument("--dataset", default="builtin",
                    help="Dataset: 'builtin', 'matplotbench', or path to JSONL")
    ap.add_argument("--rounds", type=int, default=2, help="Rounds for 'ours' system")
    ap.add_argument("--out", default="eval/results_bench", help="Output root dir")
    ap.add_argument("--limit", type=int, default=0, help="Max tasks to run (0=all)")
    ap.add_argument("--offset", type=int, default=0, help="Skip first N tasks")
    args = ap.parse_args(argv)

    # Load dataset
    tasks, dataset_label = _load_dataset(args.dataset)
    if not tasks:
        print(f"[error] No tasks found for dataset '{args.dataset}'")
        return 1
    if args.offset > 0:
        tasks = tasks[args.offset:]
    if args.limit > 0:
        tasks = tasks[: args.limit]

    print(f"[info] System: {args.system}, Dataset: {dataset_label}, Tasks: {len(tasks)}")
    if args.system == "ours":
        print(f"[info] Rounds: {args.rounds}")

    # Check LLM env for baselines that need it
    if args.system in ("gpt4o_oneshot", "claude_oneshot", "qwen_zeroshot"):
        if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
            print("[error] LLM_API_BASE / LLM_API_KEY required for LLM-based baselines")
            return 1

    # Map system name to canonical
    system_map = {
        "ours": "ours",
        "gpt4o_oneshot": "gpt4o_oneshot",
        "claude_oneshot": "claude_oneshot",
        "qwen_zeroshot": "qwen_zeroshot",
        "matplotagent": "matplotagent",
    }
    system_name = system_map[args.system]

    # Output: results/<system>/<task_id>/
    out_root = Path(args.out) / system_name
    out_root.mkdir(parents=True, exist_ok=True)

    records: List[Dict[str, Any]] = []
    pass_count = 0

    for i, task in enumerate(tasks):
        tid = task["task_id"]
        print(f"[{i+1}/{len(tasks)}] {tid} ...", end=" ", flush=True)

        if args.system == "ours":
            rec = _run_ours(task, args.rounds, out_root)
        elif args.system == "gpt4o_oneshot":
            rec = _run_oneshot(task, os.getenv("LLM_MODEL", "gpt-5.4"), system_name, out_root)
        elif args.system == "claude_oneshot":
            rec = _run_oneshot(task, os.getenv("LLM_MODEL", "claude-opus-4.8"), system_name, out_root)
        elif args.system == "qwen_zeroshot":
            from eval.baseline_runners import run_qwen_zeroshot
            rec = run_qwen_zeroshot(task, out_root)
        else:
            rec = {"task_id": tid, "system": args.system, "exec_pass": False}

        records.append(rec)
        ep = "PASS" if rec.get("exec_pass") else "FAIL"
        fid = rec.get("scores", {}).get("data_fidelity", "n/a")
        fid_str = f"DF={fid:.2f}" if isinstance(fid, (int, float)) and fid is not None else f"DF={fid}"
        print(f"{ep} {fid_str}")
        if rec.get("exec_pass"):
            pass_count += 1

    # Summary
    exec_rate = pass_count / len(tasks) if tasks else 0
    fids = [
        r["scores"]["data_fidelity"]
        for r in records
        if r.get("exec_pass") and r["scores"]["data_fidelity"] is not None
    ]
    mean_fid = np.mean(fids) if fids else 0.0

    summary = {
        "system": system_name,
        "dataset": dataset_label,
        "tasks_total": len(tasks),
        "exec_pass": pass_count,
        "exec_pass_rate": round(exec_rate, 4),
        "mean_data_fidelity": round(float(mean_fid), 4),
        "records": [r["task_id"] for r in records],
    }
    summary_path = out_root / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print final table
    print(f"\n{'='*60}")
    print(f"  Benchmark: {system_name} on {dataset_label}")
    print(f"  Tasks: {len(tasks)} | Exec-pass: {pass_count}/{len(tasks)} ({exec_rate:.0%})")
    print(f"  Mean Data Fidelity: {mean_fid:.3f}")
    print(f"  Results: {out_root}/")
    print(f"{'='*60}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
