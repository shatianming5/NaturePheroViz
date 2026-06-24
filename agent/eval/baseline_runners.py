"""
baseline_runners.py — unified baseline system runners (B2).

Each runner takes (task_dict, out_dir) and produces the standard results/
directory per the §1 contract. This file supplements run_benchmark.py with
runners for external baselines:

  qwen_zeroshot   : Qwen2.5-Coder zero-shot (OpenAI-compatible API)
  matplotagent    : MatPlotAgent (github.com/thunlp/MatPlotAgent) — external
  lida            : LIDA (pip install lida) — external
  chartcoder      : ChartCoder (HuggingFace) — external, chart→code

Only qwen_zeroshot runs without external repos. The others require the
respective repo cloned and dependencies installed.

Usage:
  cd agent
  # Qwen zero-shot (needs LLM_API_BASE/LLM_API_KEY pointing to Qwen endpoint)
  python eval/run_benchmark.py --system qwen_zeroshot --dataset builtin

  # External baselines (after cloning repos):
  python eval/baseline_runners.py --system matplotagent --dataset builtin
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests

from app.services import fidelity_verifier as fv
from app.services.plot_trace import PlotTracer


# ═══════════════════════════════════════════════════════════════════════════
# Shared utilities
# ═══════════════════════════════════════════════════════════════════════════

def _spec_for(task: Dict[str, Any]) -> Dict[str, Any]:
    mark = "line" if task.get("family") == "line" else "bar"
    return {
        "overlays": [{
            "mark": mark,
            "x": task["intent"]["x"],
            "y": task["intent"]["y"],
            "yaxis": "left",
        }]
    }


def _oracle_fidelity(
    trace_rows: List[Dict[str, Any]],
    data: pd.DataFrame,
    spec: Dict[str, Any],
) -> Optional[float]:
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


def _render_and_score(
    code_body: str, task: Dict[str, Any], out_dir: Path, tag: str
) -> Dict[str, Any]:
    """Render code with PlotTrace and compute oracle fidelity."""
    png = out_dir / f"{tag}.png"
    svg = out_dir / f"{tag}.svg"
    tracer = PlotTracer()
    ns: Dict[str, Any] = {"df": task["data"].copy()}
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
    except Exception:
        return {"exec_pass": False, "trace_rows": [], "png_path": None, "svg_path": None}

    exec_pass = png.exists()
    spec = _spec_for(task)
    fid = _oracle_fidelity(tracer.to_records(), task["data"], spec) if exec_pass else None
    return {
        "exec_pass": exec_pass,
        "png_path": str(png) if exec_pass else None,
        "svg_path": str(svg) if exec_pass else None,
        "trace_rows": tracer.to_records(),
        "data_fidelity": fid,
    }


def _write_record(
    task_id: str, system: str, exec_pass: bool, fid: Optional[float],
    task_dir: Path, gt_path: str, **extra,
) -> Dict[str, Any]:
    record = {
        "task_id": task_id,
        "system": system,
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
        "ground_truth_ref": gt_path,
        "notes": extra.get("notes", ""),
    }
    (task_dir / "record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


# ═══════════════════════════════════════════════════════════════════════════
# Qwen2.5-Coder zero-shot
# ═══════════════════════════════════════════════════════════════════════════

QWEN_MODELS = {
    "qwen_zeroshot": "gpt-5.4",
    "qwen_zeroshot_14b": "gpt-5.4",
    "qwen_zeroshot_32b": "gpt-5.4",
}


_Q_LAST = 0.0  # throttle for DashScope rate limit

def _qwen_generate(task: Dict[str, Any], model: str) -> Optional[str]:
    """Call Qwen via OpenAI-compatible API to generate plotting code."""
    global _Q_LAST
    base = os.environ.get("QWEN_API_BASE") or os.environ.get("LLM_API_BASE", "")
    key = os.environ.get("QWEN_API_KEY") or os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        print("[warn] QWEN_API_BASE/QWEN_API_KEY or LLM_API_BASE/LLM_API_KEY not set")
        return None
    base = base.rstrip("/")
    cols = list(task["data"].columns)
    prompt = (
        f"Write a SINGLE line of matplotlib code to plot this data.\n"
        f"Goal: {task['goal']}.\n"
        f"DataFrame `df` has columns {cols}. Use existing `df` and `ax`.\n"
        f"Plot x='{task['intent']['x']}', y='{task['intent']['y']}' as a {task['family']} chart.\n"
        f"Output ONLY the code, nothing else. Example: ax.bar(df['x_col'], df['y_col'])"
    )

    # Rate limiting + retry
    for attempt in range(3):
        # Enforce minimum interval between calls
        elapsed = time.time() - _Q_LAST
        if elapsed < 0.6:
            time.sleep(0.6 - elapsed)
        _Q_LAST = time.time()

        try:
            r = requests.post(
                base + "/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 400,
                },
                timeout=(10, 60),
            )
            if r.status_code == 401 or r.status_code == 429:
                wait = 2 * (attempt + 1)
                print(f"  retry {attempt+1}/3 after {wait}s...", end="")
                time.sleep(wait)
                continue
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return _extract_code(content, task)
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (401, 429):
                wait = 2 * (attempt + 1)
                time.sleep(wait)
                continue
            print(f"[warn] Qwen API call failed: {e}")
            return None
        except Exception as e:
            print(f"[warn] Qwen API call failed: {e}")
            return None
    print(f"[warn] Qwen API call failed after 3 retries")
    return None


def _extract_code(content: str, task: Dict[str, Any]) -> Optional[str]:
    """Robustly extract plotting code from model output."""
    if not content or not content.strip():
        return None
    content = content.strip()

    # 1) Try JSON: {"code": "..."}
    try:
        m = re.search(r"\{[^{}]*\"code\"\s*:\s*\"([^\"]+)\"[^{}]*\}", content, re.S)
        if m:
            code = m.group(1)
            if code.strip():
                return code.strip()
    except Exception:
        pass

    # 2) Try full JSON parse
    try:
        m = re.search(r"\{.*\}", content, re.S)
        if m:
            obj = json.loads(m.group(0))
            code = obj.get("code", "")
            if isinstance(code, str) and code.strip():
                return code.strip()
    except Exception:
        pass

    # 3) Extract from ```python ... ``` blocks
    m = re.search(r"```(?:python)?\s*\n?(.*?)```", content, re.S)
    if m:
        code = _pick_best_line(m.group(1).strip(), task)
        if code:
            return code

    # 4) Extract any line starting with ax. or plt.
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("ax.") or line.startswith("plt."):
            if "(" in line and ")" in line:
                return line

    # 5) Fallback: pick the most plausible code-looking line
    return _pick_best_line(content, task)


def _pick_best_line(text: str, task: Dict[str, Any]) -> Optional[str]:
    """Pick the most plausible plotting code line from multi-line text."""
    candidates = []
    x_col = task["intent"]["x"]
    y_col = task["intent"]["y"]
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("import") or line.startswith("from"):
            continue
        if "ax." in line and "(" in line and ")" in line:
            score = 0
            if x_col in line: score += 2
            if y_col in line: score += 2
            if task["family"] in line.lower(): score += 1
            candidates.append((score, line))
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]
    return None


def run_qwen_zeroshot(
    task: Dict[str, Any], out_dir: Path, model_name: str = "qwen-plus"
) -> Dict[str, Any]:
    """Run Qwen2.5-Coder zero-shot on one task."""
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    code = _qwen_generate(task, model_name)
    if not code:
        return _write_record(task_id, "qwen_zeroshot", False, None, task_dir, str(gt_path),
                             notes="API call failed")

    (task_dir / "code.py").write_text(code, encoding="utf-8")
    result = _render_and_score(code, task, task_dir, "chart")
    return _write_record(
        task_id, "qwen_zeroshot", result["exec_pass"], result.get("data_fidelity"),
        task_dir, str(gt_path),
    )


# ═══════════════════════════════════════════════════════════════════════════
# MatPlotAgent (external)
# ═══════════════════════════════════════════════════════════════════════════

def run_matplotagent(
    task: Dict[str, Any], out_dir: Path,
    matplotagent_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Run MatPlotAgent on one task.

    Requires: git clone https://github.com/thunlp/MatPlotAgent
    The agent is called via subprocess: python run.py --data ... --query ...

    Note: MatPlotAgent expects its own data format. We write a compatible
    input and parse its output.
    """
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    mpa_path = Path(matplotagent_path) if matplotagent_path else Path("eval/MatPlotAgent")
    if not mpa_path.exists():
        return _write_record(task_id, "matplotagent", False, None, task_dir, str(gt_path),
                             notes=f"MatPlotAgent not found at {mpa_path}")

    # Write input in MatPlotAgent format
    input_dir = task_dir / "mpa_input"
    input_dir.mkdir(exist_ok=True)
    csv_path = input_dir / "data.csv"
    task["data"].to_csv(csv_path, index=False)

    meta = {
        "query": task["goal"],
        "chart_type": task["family"],
        "x_col": task["intent"]["x"],
        "y_col": task["intent"]["y"],
    }
    (input_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, str(mpa_path / "run.py"),
             "--data", str(csv_path),
             "--query", task["goal"],
             "--chart_type", task["family"],
             "--output_dir", str(task_dir / "mpa_output")],
            capture_output=True, text=True, timeout=300,
            cwd=str(mpa_path),
        )
    except subprocess.TimeoutExpired:
        return _write_record(task_id, "matplotagent", False, None, task_dir, str(gt_path),
                             notes="timeout")
    except FileNotFoundError:
        return _write_record(task_id, "matplotagent", False, None, task_dir, str(gt_path),
                             notes=f"run.py not found in {mpa_path}")

    # Try to find the generated code
    output_dir = task_dir / "mpa_output"
    code_files = list(output_dir.glob("**/*.py")) if output_dir.exists() else []
    if not code_files:
        return _write_record(task_id, "matplotagent", False, None, task_dir, str(gt_path),
                             notes=f"no code output, stderr: {result.stderr[:200]}")

    code = code_files[0].read_text(encoding="utf-8")
    # MatPlotAgent code may not use our 'df'/'ax' convention; wrap it
    wrapped = _wrap_matplotagent_code(code, task)
    (task_dir / "code.py").write_text(wrapped, encoding="utf-8")

    render_result = _render_and_score(wrapped, task, task_dir, "chart")
    return _write_record(
        task_id, "matplotagent", render_result["exec_pass"],
        render_result.get("data_fidelity"), task_dir, str(gt_path),
    )


def _wrap_matplotagent_code(raw_code: str, task: Dict[str, Any]) -> str:
    """Wrap MatPlotAgent-generated code to use our df/ax convention."""
    # MatPlotAgent typically generates standalone scripts with plt.figure() etc.
    # Try to extract the plotting logic and adapt it.
    # Remove plt.show() / plt.savefig() / plt.figure() / plt.subplots()
    cleaned = re.sub(r'plt\.show\(\)', '', raw_code)
    cleaned = re.sub(r'plt\.savefig\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'plt\.figure\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'fig,\s*ax\s*=\s*plt\.subplots\([^)]*\)', '', cleaned)

    # If it reads CSV, replace with our df
    cleaned = re.sub(r"pd\.read_csv\([^)]*\)", "df", cleaned)

    # Remove imports (will be in our wrapper)
    cleaned = re.sub(r'^import\s+.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^from\s+.*import.*$', '', cleaned, flags=re.MULTILINE)

    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = f"ax.{task['family']}(df['{task['intent']['x']}'], df['{task['intent']['y']}'])"
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# LIDA (external)
# ═══════════════════════════════════════════════════════════════════════════

def run_lida(
    task: Dict[str, Any], out_dir: Path,
) -> Dict[str, Any]:
    """Run LIDA on one task.

    Requires: pip install lida
    LIDA generates visualization code from natural language + data summary.
    """
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    try:
        from lida import Manager, TextGenerationConfig, llm
    except ImportError:
        return _write_record(task_id, "lida", False, None, task_dir, str(gt_path),
                             notes="lida not installed: pip install lida")

    # LIDA needs a file path, not a CSV string.
    # LIDA internally uses openai.OpenAI() which reads OPENAI_API_KEY env var.
    data_csv_path = task_dir / "_lida_input.csv"
    task["data"].to_csv(data_csv_path, index=False)

    # Save original env and set our API credentials
    _saved_key = os.environ.get("OPENAI_API_KEY")
    _saved_base = os.environ.get("OPENAI_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY", "sk-intern")
    api_base = os.environ.get("LLM_API_BASE", "http://1.14.177.180:4141/v1")
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = api_base

    try:
        lida_cfg = TextGenerationConfig(n=1, temperature=0.2, model="gpt-5.4")
        lida_manager = Manager(text_gen=llm("openai"))
        summary = lida_manager.summarize(
            str(data_csv_path),
            textgen_config=lida_cfg,
        )
        charts = lida_manager.visualize(
            summary=summary,
            goal=task["goal"],
            textgen_config=lida_cfg,
        )
        if not charts or len(charts) == 0:
            return _write_record(task_id, "lida", False, None, task_dir, str(gt_path),
                                 notes="no charts generated")

        chart = charts[0]
        code = chart.code if hasattr(chart, 'code') else str(chart)
    except Exception as e:
        # Restore env before returning
        if _saved_key is None: del os.environ["OPENAI_API_KEY"]
        else: os.environ["OPENAI_API_KEY"] = _saved_key
        if _saved_base is None: os.environ.pop("OPENAI_BASE_URL", None)
        else: os.environ["OPENAI_BASE_URL"] = _saved_base
        return _write_record(task_id, "lida", False, None, task_dir, str(gt_path),
                             notes=f"LIDA error: {e}")

    # Wrap LIDA code
    wrapped = _wrap_lida_code(code, task)
    (task_dir / "code.py").write_text(wrapped, encoding="utf-8")

    render_result = _render_and_score(wrapped, task, task_dir, "chart")
    return _write_record(
        task_id, "lida", render_result["exec_pass"],
        render_result.get("data_fidelity"), task_dir, str(gt_path),
    )


def _wrap_lida_code(raw_code: str, task: Dict[str, Any]) -> str:
    """Adapt LIDA-generated code to our df/ax convention."""
    cleaned = re.sub(r'plt\.show\(\)', '', raw_code)
    cleaned = re.sub(r'plt\.savefig\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'plt\.figure\([^)]*\)', '', cleaned)
    cleaned = re.sub(r'fig,\s*ax\s*=\s*plt\.subplots\([^)]*\)', '', cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        cleaned = f"ax.{task['family']}(df['{task['intent']['x']}'], df['{task['intent']['y']}'])"
    return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# ChartCoder (external)
# ═══════════════════════════════════════════════════════════════════════════

def run_chartcoder(
    task: Dict[str, Any], out_dir: Path,
) -> Dict[str, Any]:
    """Run ChartCoder on one task.

    ChartCoder (https://huggingface.co/) converts chart IMAGES to code.
    Since we don't have a pre-existing chart image, this is primarily
    useful as a chart→code baseline when we have reference images.

    For now, returns a placeholder noting the dependency.
    """
    task_id = task["task_id"]
    task_dir = out_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    gt_path = task_dir / "plot_df.csv"
    task["data"].to_csv(gt_path, index=False)

    return _write_record(
        task_id, "chartcoder", False, None, task_dir, str(gt_path),
        notes="ChartCoder requires a reference chart image (chart→code). "
              "Not applicable in zero-shot data→code setting. "
              "Use as adjacent comparison when reference images are available."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Main (standalone runner for external baselines)
# ═══════════════════════════════════════════════════════════════════════════

RUNNERS = {
    "qwen_zeroshot": run_qwen_zeroshot,
    "matplotagent": run_matplotagent,
    "lida": run_lida,
    "chartcoder": run_chartcoder,
}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="External baseline runners (B2)")
    ap.add_argument("--system", required=True, choices=list(RUNNERS.keys()),
                    help="Which baseline to run")
    ap.add_argument("--dataset", default="builtin", help="Dataset name or JSONL path")
    ap.add_argument("--out", default="eval/results_bench", help="Output root dir")
    ap.add_argument("--limit", type=int, default=0, help="Max tasks (0=all)")
    ap.add_argument("--matplotagent-path", default=None,
                    help="Path to MatPlotAgent repo")
    args = ap.parse_args(argv)

    # Load tasks
    from eval.run_benchmark import _builtin_tasks, _load_matplotbench

    if args.dataset == "builtin":
        tasks = _builtin_tasks()
    elif args.dataset == "matplotbench":
        tasks = _load_matplotbench()
        if not tasks:
            print("[error] MatPlotBench not found")
            return 1
    else:
        # Custom JSONL
        import json as _json
        custom_path = Path(args.dataset)
        tasks = []
        for line in custom_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = _json.loads(line)
            csv_path = Path(obj["csv_path"])
            df = pd.read_csv(csv_path)
            tasks.append({
                "task_id": obj.get("task_id", csv_path.stem),
                "name": obj.get("name", csv_path.stem),
                "family": obj.get("family", "bar"),
                "goal": obj.get("goal", ""),
                "intent": obj.get("intent", {"x": df.columns[0], "y": df.columns[-1]}),
                "data": df,
            })

    if args.limit > 0:
        tasks = tasks[:args.limit]

    system_name = args.system
    out_root = Path(args.out) / system_name
    out_root.mkdir(parents=True, exist_ok=True)

    runner = RUNNERS[system_name]
    pass_count = 0

    for i, task in enumerate(tasks):
        tid = task["task_id"]
        print(f"[{i+1}/{len(tasks)}] {tid} ...", end=" ", flush=True)

        kwargs = {}
        if system_name == "matplotagent" and args.matplotagent_path:
            kwargs["matplotagent_path"] = args.matplotagent_path

        rec = runner(task, out_root, **kwargs)
        ep = "PASS" if rec.get("exec_pass") else "FAIL"
        fid = rec.get("scores", {}).get("data_fidelity", "n/a")
        fid_str = f"DF={fid:.2f}" if isinstance(fid, (int, float)) and fid is not None else f"DF={fid}"
        print(f"{ep} {fid_str}")
        if rec.get("exec_pass"):
            pass_count += 1

    print(f"\nDone: {pass_count}/{len(tasks)} exec-pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
