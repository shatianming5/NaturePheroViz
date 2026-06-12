"""
repair_gain.py — Task 1: does a BETTER judge make the LLM actually FIX a render bug?

The decisive experiment's second half (reviewer: "repair, not just detection").
We don't only compare detection; we let each judge's feedback DRIVE a real-LLM
one-step repair and measure whether the chart ends up matching the data.

Semantics (clarified): the bug is a RENDER bug — the plotting code draws the
chart WRONG vs its (correct) input data: wrong column mapping, a dropped series,
a wrong aggregation. The ground truth is the INPUT DATA itself (the agent can
see it). A judge compares chart-vs-data, reports mismatches, and that feedback
is handed to the LLM to rewrite the code.

Per case:
  1. Start from buggy plotting code → render a wrong chart (PNG+SVG+trace).
  2. Judge (trace OR svg) compares the rendered chart to the input data and
     emits a mismatch report.
  3. Feed (buggy code + judge's mismatch report) to the real LLM → it rewrites
     the code → re-render.
  4. INDEPENDENT oracle: PlotTrace read-back of the REPAIRED chart vs the input
     data (exact). Higher = the feedback led to a real fix.

Thesis: trace feedback (exact, localized) guides the LLM to the real bug;
svg feedback (noisy / mis-located on real charts) misleads it → worse repair.

Requires LLM proxy env (LLM_API_BASE / LLM_API_KEY / LLM_MODEL).
Run:  cd agent && python eval/repair_gain.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402

from app.services import fidelity_verifier as fv  # noqa: E402
from app.services.plot_trace import PlotTracer  # noqa: E402

JUDGE_MODES = ["svg", "trace"]


# ===========================================================================
# Cases: each has clean input data, a spec, and a BUGGY plotting function whose
# rendered chart disagrees with the data. The repair target is "chart == data".
# Buggy code is expressed as a string the LLM will rewrite.
# ===========================================================================


def _cases() -> List[Dict[str, Any]]:
    out = []

    # 1. wrong column mapping: code plots the WRONG y column
    df1 = pd.DataFrame({"month": ["Jan", "Feb", "Mar", "Apr"],
                        "sales": [120.0, 135.0, 98.0, 150.0],
                        "cost": [40.0, 50.0, 30.0, 60.0]})
    out.append({
        "name": "wrong_column",
        "data": df1,
        "spec": {"overlays": [{"mark": "bar", "x": "month", "y": "sales", "yaxis": "left"}]},
        "intent": "Plot monthly SALES as a bar chart.",
        "buggy_code": "ax.bar(df['month'], df['cost'], label='sales')  # BUG: plots cost, not sales",
    })

    # 2. dropped series: should plot two lines, code plots only one
    df2 = pd.DataFrame({"q": ["Q1", "Q2", "Q3", "Q4"],
                        "actual": [10.0, 22.0, 18.0, 30.0],
                        "target": [12.0, 20.0, 21.0, 28.0]})
    out.append({
        "name": "dropped_series",
        "data": df2,
        "spec": {"overlays": [{"mark": "line", "x": "q", "y": "actual", "yaxis": "left"},
                              {"mark": "line", "x": "q", "y": "target", "yaxis": "left"}]},
        "intent": "Plot BOTH actual and target as two lines.",
        "buggy_code": "ax.plot(df['q'], df['actual'], label='actual')  # BUG: 'target' series is missing",
    })

    # 3. wrong aggregation: should plot raw values, code halves them
    df3 = pd.DataFrame({"cat": ["A", "B", "C", "D"], "v": [50.0, 70.0, 65.0, 80.0]})
    out.append({
        "name": "wrong_transform",
        "data": df3,
        "spec": {"overlays": [{"mark": "bar", "x": "cat", "y": "v", "yaxis": "left"}]},
        "intent": "Plot v by category (raw values).",
        "buggy_code": "ax.bar(df['cat'], df['v'] / 2.0, label='v')  # BUG: values halved",
    })

    # 4. swapped mapping: x and y mixed up conceptually -> wrong heights
    df4 = pd.DataFrame({"city": ["NY", "LA", "SF", "BOS"], "pop": [840.0, 390.0, 88.0, 69.0]})
    out.append({
        "name": "scaled_wrong",
        "data": df4,
        "spec": {"overlays": [{"mark": "bar", "x": "city", "y": "pop", "yaxis": "left"}]},
        "intent": "Plot population by city.",
        "buggy_code": "ax.bar(df['city'], df['pop'] * 0.6, label='pop')  # BUG: scaled by 0.6",
    })
    return out


# ===========================================================================
# Render a plotting-code snippet (the body that uses `df` and `ax`) to PNG+SVG
# with execution trace. Returns artifact paths + trace rows.
# ===========================================================================

_RENDER_TMPL = """\
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd, numpy as np
fig, ax = plt.subplots(figsize=(5,3))
CODE_BODY
fig.tight_layout()
fig.savefig(PNG, dpi=80)
fig.savefig(SVG, format="svg")
plt.close("all")
"""


def _render(code_body: str, data: pd.DataFrame, workdir: Path, tag: str) -> Dict[str, Any]:
    png = workdir / f"{tag}.png"
    svg = workdir / f"{tag}.svg"
    tracer = PlotTracer()
    # inject df directly into the namespace (no JSON round-trip; pandas 3.0
    # read_json no longer accepts a raw JSON string)
    ns: Dict[str, Any] = {"df": data.copy()}
    src = (_RENDER_TMPL
           .replace("PNG", repr(str(png)))
           .replace("SVG", repr(str(svg)))
           .replace("CODE_BODY", code_body))
    try:
        with tracer.install():
            exec(compile(src, f"<{tag}>", "exec"), ns)  # noqa: S102 (controlled fixtures)
        ok = png.exists()
    except Exception as e:
        return {"ok": False, "err": repr(e)[:160], "png": None, "svg": None, "trace_rows": []}
    return {"ok": ok, "png": str(png), "svg": str(svg), "trace_rows": tracer.to_records()}


# ===========================================================================
# Judges → mismatch report (the feedback that drives repair).
# ===========================================================================


def _svg_mismatches(svg_path: str, data: pd.DataFrame, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        svg = fv._read_text(svg_path)
        pred = fv._collect_predictions(svg, spec)
    except Exception:
        return []
    if pred is None or pred.empty:
        return []
    gt_norm, x_col, y_col, g_col = fv._normalize_ground_truth(data, spec)
    pred = fv._tag_predicted_series(pred, spec)
    return fv._safe_match(pred, gt_norm, x_col, y_col, g_col).get("mismatches", [])


def _trace_mismatches(trace_rows: List[Dict[str, Any]], data: pd.DataFrame, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not trace_rows:
        return []
    tdf = pd.DataFrame(trace_rows)
    if not {"series", "x", "value"}.issubset(tdf.columns):
        return []
    pred = fv._coerce_pred_table(tdf[["series", "x", "value"]], data, spec)
    if pred is None or pred.empty:
        return []
    gt_norm, x_col, y_col, g_col = fv._normalize_ground_truth(data, spec)
    if g_col and g_col != "series" and "series" in pred.columns and g_col not in pred.columns:
        pred = pred.rename(columns={"series": g_col})
    return fv._safe_match(pred, gt_norm, x_col, y_col, g_col).get("mismatches", [])


# ===========================================================================
# Real-LLM one-step repair.
# ===========================================================================


def _llm_repair(buggy_code: str, mismatch_report: List[Dict[str, Any]], intent: str, data_cols: List[str]) -> Optional[str]:
    base = os.environ["LLM_API_BASE"].rstrip("/")
    key = os.environ["LLM_API_KEY"]
    model = os.getenv("LLM_MODEL", "gpt-4o")
    report_txt = json.dumps(mismatch_report[:12], ensure_ascii=False, indent=2) if mismatch_report else "(no mismatches reported)"
    prompt = f"""You are fixing a matplotlib plotting bug. The code below draws a chart that
does NOT match the intended data. A fidelity judge compared the rendered chart
to the data and reported these (series, x, gt, pred) mismatches — `gt` is what
the data says should be drawn, `pred` is what the chart actually drew:

MISMATCH REPORT:
{report_txt}

INTENT: {intent}
AVAILABLE DataFrame columns: {data_cols}
BUGGY CODE (uses `df` and `ax`):
    {buggy_code}

Return ONLY the corrected one-line (or few-line) plotting code body that uses
`df` and `ax`, as strict JSON: {{"code": "<corrected code>"}}. No explanation."""
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
        code = obj.get("code")
        return code if isinstance(code, str) and code.strip() else None
    except Exception:
        return None


def _final_fidelity(trace_rows: List[Dict[str, Any]], data: pd.DataFrame, spec: Dict[str, Any]) -> Optional[float]:
    """Independent oracle: trace read-back of repaired chart vs input data."""
    ms = _trace_mismatches(trace_rows, data, spec)
    if not trace_rows:
        return None
    tdf = pd.DataFrame(trace_rows)
    pred = fv._coerce_pred_table(tdf[["series", "x", "value"]], data, spec)
    if pred is None or pred.empty:
        return None
    gt_norm, x_col, y_col, g_col = fv._normalize_ground_truth(data, spec)
    if g_col and g_col != "series" and "series" in pred.columns and g_col not in pred.columns:
        pred = pred.rename(columns={"series": g_col})
    f = fv._safe_match(pred, gt_norm, x_col, y_col, g_col).get("data_fidelity")
    return float(f) if f is not None else None


def _run_case(case: Dict[str, Any], judge_mode: str, workdir: Path) -> Dict[str, Any]:
    data, spec = case["data"], case["spec"]
    # 1. render buggy chart
    buggy = _render(case["buggy_code"], data, workdir, f"{case['name']}_{judge_mode}_buggy")
    if not buggy["ok"]:
        return {"start_fid": None, "final_fid": None, "ok": False, "err": "buggy-render-failed"}
    start_fid = _final_fidelity(buggy["trace_rows"], data, spec)  # fidelity of the buggy chart
    # 2. judge → mismatch report
    if judge_mode == "svg":
        report = _svg_mismatches(buggy["svg"], data, spec)
    else:
        report = _trace_mismatches(buggy["trace_rows"], data, spec)
    # 3. LLM repair
    fixed_code = _llm_repair(case["buggy_code"], report, case["intent"], list(data.columns))
    if not fixed_code:
        return {"start_fid": start_fid, "final_fid": start_fid, "ok": False, "err": "llm-no-fix", "n_report": len(report)}
    # 4. re-render + independent oracle
    fixed = _render(fixed_code, data, workdir, f"{case['name']}_{judge_mode}_fixed")
    if not fixed["ok"]:
        return {"start_fid": start_fid, "final_fid": start_fid, "ok": False, "err": "fixed-render-failed", "n_report": len(report)}
    final_fid = _final_fidelity(fixed["trace_rows"], data, spec)
    return {"start_fid": start_fid, "final_fid": final_fid, "ok": final_fid is not None,
            "n_report": len(report), "fixed_code": fixed_code[:160]}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Judge-driven one-step repair gain (real LLM)")
    ap.add_argument("--out", default="eval/results_repair")
    ap.add_argument("--cases", type=int, default=4)
    args = ap.parse_args(argv)

    if not os.getenv("LLM_API_BASE") or not os.getenv("LLM_API_KEY"):
        print("[error] needs LLM_API_BASE / LLM_API_KEY (the proxy).")
        return 1

    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    cases = _cases()[: args.cases]
    rows: List[Dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for case in cases:
            rec = {"case": case["name"]}
            for jm in JUDGE_MODES:
                r = _run_case(case, jm, wd)
                rec[jm] = r
                sf = r.get("start_fid"); ff = r.get("final_fid")
                print(f"[{case['name']}] judge={jm:5} start={'n/a' if sf is None else f'{sf:.2f}'} "
                      f"-> final={'n/a' if ff is None else f'{ff:.2f}'} (report={r.get('n_report','?')} {r.get('err','')})")
            rows.append(rec)

    report = _report(rows)
    (out_dir / "repair_gain_records.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (out_dir / "repair_gain_report.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\n[saved] {out_dir}/repair_gain_report.md")
    return 0


def _report(rows: List[Dict[str, Any]]) -> str:
    lines = ["# Judge-Driven One-Step Repair Gain (real LLM)\n",
             "Buggy render → judge feedback → LLM rewrites code → re-render. FINAL fidelity",
             "measured by an INDEPENDENT PlotTrace oracle (chart vs input data), not the driving judge.\n",
             "| Case | start (buggy) | SVG-driven final | PlotTrace-driven final |",
             "|---|---|---|---|"]
    sv, tr = [], []
    for r in rows:
        s = r.get("svg", {}); t = r.get("trace", {})
        start = s.get("start_fid") if s.get("start_fid") is not None else t.get("start_fid")
        sf, tf = s.get("final_fid"), t.get("final_fid")
        if sf is not None: sv.append(sf)
        if tf is not None: tr.append(tf)
        f = lambda x: "n/a" if x is None else f"{x:.2f}"
        lines.append(f"| {r['case']} | {f(start)} | {f(sf)} | {f(tf)} |")
    f = lambda xs: f"{np.mean(xs):.2f}" if xs else "n/a"
    lines.append(f"| **Mean** | — | {f(sv)} | {f(tr)} |")
    lines.append("\n## Reading")
    lines.append("- start = fidelity of the buggy chart (low: it draws the wrong data).")
    lines.append("- final = fidelity after the LLM repairs using each judge's feedback.")
    lines.append("- Thesis holds if PlotTrace-driven final > SVG-driven final: exact, localized")
    lines.append("  feedback points the LLM at the real bug; SVG's noisy feedback misleads it.")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
